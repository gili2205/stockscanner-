"""
AI Scanner Optimizer
====================
Calls Claude to analyze 180-day backtest performance, suggest scoring weight
changes, and estimates win-rate impact via shadow-backtest before saving a
recommendation to Firebase for human approval.

Usage (on GCP VM):
    python ai_optimizer.py                 # analyze 1m window, generate recommendation
    python ai_optimizer.py --window 1w     # different return window (1w/2w/1m/2m/3m)
    python ai_optimizer.py --all-windows   # run for every window, pick best
    python ai_optimizer.py --apply         # apply latest APPROVED recommendation
"""

import os, sys, json, logging, argparse, re
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# ── .env loader ───────────────────────────────────────────────────────────────
def _load_dotenv():
    for candidate in [Path(__file__).parent / ".env", Path("/home/scanner/.env")]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return
_load_dotenv()

import anthropic
import firebase_admin
from firebase_admin import credentials, db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FIREBASE_URL  = os.environ["FIREBASE_URL"]
FIREBASE_CRED = os.environ["FIREBASE_CRED"]
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

cred = credentials.Certificate(FIREBASE_CRED)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})
hist_ref       = db.reference("/scanner/history")
ai_recs_ref    = db.reference("/scanner/ai_recommendations")
weights_ref    = db.reference("/scanner/approved_weights")


# ════════════════════════════════════════════════════════════════════════════════
# CURRENT WEIGHTS  (mirrors live_scanner.py score_stock — keep in sync!)
# ════════════════════════════════════════════════════════════════════════════════

DEFAULT_WEIGHTS = {
    # ── BREAKOUT TRACK ──────────────────────────────────────────────────────────
    # Each key is the MAX points; graduated tiers scale proportionally.
    "breakout_momentum_max":   28,   # 1M momentum (>=25%:28, >=15%:22, >=8%:15, >=3%:9, >=0%:4)
    "breakout_ema_full":       22,   # EMA 10>20>50 and price above 10EMA
    "breakout_ema_partial":    12,   # EMA 10>20 only
    "breakout_hh_hl_strong":    6,   # Higher-highs/higher-lows ratio >= 0.85
    "breakout_hh_hl_ok":        3,   # HH/HL ratio >= 0.70
    "breakout_atr_max":        12,   # ATR compression (<=0.20:12, <=0.25:9, <=0.30:6, <=0.40:2)
    "breakout_vol_max":         8,   # Volume contraction (<=0.50:8, <=0.65:5, <=0.80:2)
    "breakout_dist_max":       18,   # Distance to level (<=1%:18, <=2%:14, <=3.5%:9, <=6%:4, <=10%:1)
    "breakout_liquidity_max":   7,   # Dollar volume (>=200M:7, >=50M:5, >=20M:3, else:1)
    # ── Penalties ───────────────────────────────────────────────────────────────
    "penalty_weak_ema":        18,   # Subtracted when ema_stack == "weak"
    "penalty_far_dist":        12,   # Subtracted when dist_to_level > 15%
    "penalty_neg_mom":         12,   # Subtracted when momentum_1m < -5%
    "penalty_high_vol_atr":     8,   # Subtracted when atr_c > 0.7 AND mom1m < 10%
    # ── Status thresholds ───────────────────────────────────────────────────────
    "threshold_ready":         72,   # Min score → READY
    "threshold_watch":         55,   # Min score → WATCH  (below = BUILDING, not surfaced)
}

WEIGHT_DESCRIPTIONS = {
    "breakout_momentum_max":  "Max pts for 1-month price momentum (strong uptrend = high score)",
    "breakout_ema_full":      "Pts for full EMA upstack (10>20>50, price above all) — cleanest trend",
    "breakout_ema_partial":   "Pts for partial EMA stack (10>20 only) — developing trend",
    "breakout_hh_hl_strong":  "Pts for healthy HH/HL ratio >= 0.85 (strong higher-highs structure)",
    "breakout_hh_hl_ok":      "Pts for acceptable HH/HL ratio >= 0.70",
    "breakout_atr_max":       "Max pts for ATR compression (coiling tightly before breakout)",
    "breakout_vol_max":       "Max pts for volume contraction (drying up before explosion)",
    "breakout_dist_max":      "Max pts for being close to the breakout level (nearest = best)",
    "breakout_liquidity_max": "Max pts for high daily dollar volume (liquid = safer breakout)",
    "penalty_weak_ema":       "Points REMOVED when EMA stack is weak/bearish",
    "penalty_far_dist":       "Points REMOVED when stock is > 15% below breakout level",
    "penalty_neg_mom":        "Points REMOVED when 1M momentum is below -5% (falling knife)",
    "penalty_high_vol_atr":   "Points REMOVED when ATR > 0.7 AND momentum < 10% (choppy/noisy)",
    "threshold_ready":        "Score cutoff for READY status (highest urgency, shown prominently)",
    "threshold_watch":        "Score cutoff for WATCH status (monitoring zone)",
}


# ════════════════════════════════════════════════════════════════════════════════
# SHADOW SCORER  (re-implement breakout scoring with configurable weights)
# ════════════════════════════════════════════════════════════════════════════════

def compute_breakout_score(pick, W):
    """Re-score a historical pick's BREAKOUT track using the given weight dict."""
    mom1m = float(pick.get("momentum_1m") or 0)
    mom3m = float(pick.get("momentum_3m") or mom1m)
    ema   = str(pick.get("ema_stack") or "weak")
    hh_hl = float(pick.get("hh_hl") or 0)
    atr_c = float(pick.get("atr") or 1)
    vc    = float(pick.get("vol_contraction") or 1)
    dist  = float(pick.get("dist_to_level") or 10)

    if mom3m < -30:
        return 0

    ba = 0

    # 1. Momentum
    m = W["breakout_momentum_max"]
    if   mom1m >= 25: ba += m
    elif mom1m >= 15: ba += round(m * 22/28)
    elif mom1m >= 8:  ba += round(m * 15/28)
    elif mom1m >= 3:  ba += round(m * 9/28)
    elif mom1m >= 0:  ba += round(m * 4/28)

    # 2. EMA trend structure
    if   ema == "full":    ba += W["breakout_ema_full"]
    elif ema == "partial": ba += W["breakout_ema_partial"]
    if   hh_hl >= 0.85: ba += W["breakout_hh_hl_strong"]
    elif hh_hl >= 0.70: ba += W["breakout_hh_hl_ok"]

    # 3. ATR compression
    a = W["breakout_atr_max"]
    if   atr_c <= 0.20: ba += a
    elif atr_c <= 0.25: ba += round(a * 9/12)
    elif atr_c <= 0.30: ba += round(a * 6/12)
    elif atr_c <= 0.40: ba += round(a * 2/12)

    # 4. Volume contraction
    v = W["breakout_vol_max"]
    if   vc <= 0.50: ba += v
    elif vc <= 0.65: ba += round(v * 5/8)
    elif vc <= 0.80: ba += round(v * 2/8)

    # 5. Distance to level
    d = W["breakout_dist_max"]
    if   dist <= 1.0: ba += d
    elif dist <= 2.0: ba += round(d * 14/18)
    elif dist <= 3.5: ba += round(d * 9/18)
    elif dist <= 6.0: ba += round(d * 4/18)
    elif dist <= 10:  ba += 1

    # 6. Liquidity (stored picks don't have dollar_vol; use mid-tier as neutral)
    ba += round(W["breakout_liquidity_max"] * 5/7)

    # Penalties
    if ema == "weak":               ba = max(0, ba - W["penalty_weak_ema"])
    if dist > 15:                   ba = max(0, ba - W["penalty_far_dist"])
    if mom1m < -5:                  ba = max(0, ba - W["penalty_neg_mom"])
    if atr_c > 0.7 and mom1m < 10: ba = max(0, ba - W["penalty_high_vol_atr"])

    return min(95, ba)


def shadow_backtest(picks, weights):
    """Return performance stats for picks re-scored with the given weights."""
    all_rets, ready_rets = [], []
    for p in picks:
        ret = p.get("_return")
        if ret is None:
            continue
        new_score = compute_breakout_score(p, weights)
        if new_score >= weights["threshold_watch"]:
            all_rets.append(ret)
            if new_score >= weights["threshold_ready"]:
                ready_rets.append(ret)

    def stats(rets):
        if not rets:
            return {"n": 0, "win_rate": None, "avg_return": None}
        return {
            "n":          len(rets),
            "win_rate":   round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1),
            "avg_return": round(sum(rets) / len(rets), 2),
        }

    return {"all": stats(all_rets), "ready": stats(ready_rets)}


# ════════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ════════════════════════════════════════════════════════════════════════════════

def load_picks(window="1m", days=180):
    """Load picks from last N days that have return data for the given window."""
    log.info(f"Loading picks from last {days} days (window={window})...")
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    history = hist_ref.get() or {}
    picks = []
    for day_str, day_data in history.items():
        if day_str < cutoff or not isinstance(day_data, dict):
            continue
        for ticker, pick in day_data.items():
            if not isinstance(pick, dict):
                continue
            ret = (pick.get("returns") or {}).get(window)
            if ret is None:
                continue
            pick["_return"] = float(ret)
            pick["_day"]    = day_str
            picks.append(pick)
    log.info(f"Loaded {len(picks)} picks with '{window}' returns")
    return picks


# ════════════════════════════════════════════════════════════════════════════════
# FACTOR ANALYSIS
# ════════════════════════════════════════════════════════════════════════════════

def factor_analysis(picks):
    """Compute win-rate lift for each factor signal."""
    def analyze(label, condition):
        with_s  = [p["_return"] for p in picks if condition(p)]
        without = [p["_return"] for p in picks if not condition(p)]
        if len(with_s) < 10:
            return None
        wr_with  = round(sum(1 for r in with_s  if r > 0) / len(with_s)  * 100, 1)
        wr_wout  = round(sum(1 for r in without if r > 0) / len(without)  * 100, 1) if without else None
        avg_with = round(sum(with_s)  / len(with_s),  2)
        avg_wout = round(sum(without) / len(without), 2) if without else None
        return {
            "factor":      label,
            "n":           len(with_s),
            "wr_with":     wr_with,
            "wr_without":  wr_wout,
            "wr_lift":     round(wr_with - (wr_wout or 0), 1),
            "avg_with":    avg_with,
            "avg_without": avg_wout,
        }

    checks = [
        ("EMA = FULL",            lambda p: p.get("ema_stack") == "full"),
        ("EMA = PARTIAL",         lambda p: p.get("ema_stack") == "partial"),
        ("EMA = WEAK",            lambda p: p.get("ema_stack") == "weak"),
        ("Vol ≤ 50%",             lambda p: (p.get("vol_contraction") or 1) <= 0.5),
        ("Vol ≤ 70%",             lambda p: (p.get("vol_contraction") or 1) <= 0.7),
        ("Vol > 100%",            lambda p: (p.get("vol_contraction") or 1) > 1.0),
        ("ATR ≤ 0.25",            lambda p: (p.get("atr") or 1) <= 0.25),
        ("ATR ≤ 0.35",            lambda p: (p.get("atr") or 1) <= 0.35),
        ("ATR > 0.50",            lambda p: (p.get("atr") or 0) > 0.50),
        ("HH/HL ≥ 0.85",          lambda p: (p.get("hh_hl") or 0) >= 0.85),
        ("HH/HL ≥ 0.70",          lambda p: (p.get("hh_hl") or 0) >= 0.70),
        ("Momentum 1M ≥ +15%",   lambda p: (p.get("momentum_1m") or 0) >= 15),
        ("Momentum 1M ≥ +8%",    lambda p: (p.get("momentum_1m") or 0) >= 8),
        ("Momentum 1M ≥ +3%",    lambda p: (p.get("momentum_1m") or 0) >= 3),
        ("Momentum 1M < 0%",     lambda p: (p.get("momentum_1m") or 0) < 0),
        ("Dist ≤ 1%",             lambda p: (p.get("dist_to_level") or 99) <= 1),
        ("Dist ≤ 3%",             lambda p: (p.get("dist_to_level") or 99) <= 3),
        ("Dist > 10%",            lambda p: (p.get("dist_to_level") or 0) > 10),
        ("Pre-breakout flag",     lambda p: bool(p.get("pre_breakout"))),
        ("Bull flag",             lambda p: bool(p.get("bull_flag"))),
        ("Status = READY",        lambda p: p.get("status") == "READY"),
        ("Status = WATCH",        lambda p: p.get("status") == "WATCH"),
        ("Score ≥ 80",            lambda p: (p.get("score") or 0) >= 80),
        ("Score ≥ 72 (READY)",   lambda p: (p.get("score") or 0) >= 72),
        ("Score 55-71 (WATCH)",  lambda p: 55 <= (p.get("score") or 0) < 72),
    ]

    results = [r for label, fn in checks if (r := analyze(label, fn)) is not None]
    results.sort(key=lambda x: x["wr_lift"], reverse=True)
    return results


def score_band_breakdown(picks):
    """Win rate and avg return by score decile."""
    bands = defaultdict(list)
    for p in picks:
        band = ((p.get("score") or 0) // 10) * 10
        bands[band].append(p["_return"])
    rows = []
    for band in sorted(bands):
        rets = bands[band]
        wr  = round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1) if rets else 0
        avg = round(sum(rets) / len(rets), 2) if rets else 0
        rows.append({"range": f"{band}-{band+9}", "n": len(rets), "win_rate": wr, "avg_return": avg})
    return rows


# ════════════════════════════════════════════════════════════════════════════════
# CLAUDE API CALL
# ════════════════════════════════════════════════════════════════════════════════

def call_claude(picks, factors, bands, window):
    """Send analysis to Claude; returns parsed JSON suggestion."""
    if not ANTHROPIC_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set in .env file")

    rets    = [p["_return"] for p in picks]
    ov_wr   = round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1) if rets else 0
    ov_avg  = round(sum(rets) / len(rets), 2) if rets else 0
    ov_best = round(max(rets), 1) if rets else 0
    ov_wst  = round(min(rets), 1) if rets else 0

    factors_txt = "\n".join(
        f"  {f['factor']}: n={f['n']}, WR_with={f['wr_with']}%, WR_without={f['wr_without']}%, "
        f"lift={f['wr_lift']:+.1f}%, avg_with={f['avg_with']:+.2f}%, avg_without={f['avg_without']:+.2f}%"
        for f in factors if f["wr_with"] is not None
    )
    bands_txt = "\n".join(
        f"  {b['range']}: n={b['n']}, win_rate={b['win_rate']}%, avg_return={b['avg_return']:+.2f}%"
        for b in bands
    )
    weights_txt = "\n".join(
        f"  {k}: {v}  # {WEIGHT_DESCRIPTIONS.get(k,'')}"
        for k, v in DEFAULT_WEIGHTS.items()
    )

    prompt = f"""You are a quantitative analyst helping improve a NASDAQ breakout stock scanner.

## Context
The scanner scores stocks on a BREAKOUT track (0–95 pts, capped). Stocks scoring ≥{DEFAULT_WEIGHTS['threshold_ready']}
become READY (highest urgency), ≥{DEFAULT_WEIGHTS['threshold_watch']} become WATCH.
You will analyze historical pick performance and suggest specific weight changes.

## Return Window: {window}
(Each pick's return is measured {window} after the scanner surfaced it)

## Overall Performance — last 180 days ({len(picks)} picks with data)
  Win rate:    {ov_wr}%
  Avg return:  {ov_avg:+.2f}%
  Best pick:   {ov_best:+.1f}%
  Worst pick:  {ov_wst:+.1f}%

## Performance by Score Band
{bands_txt}

## Factor Analysis — which signals actually predict winning trades
(WR_lift = win-rate WITH signal minus win-rate WITHOUT signal)
{factors_txt}

## Current Scoring Weights
{weights_txt}

## Instructions
1. Identify which factors show strong win-rate lift (≥+5%) → these are under-weighted, increase their points
2. Identify which factors show negative or zero lift → these may be over-weighted, consider decreasing
3. Consider whether score thresholds (READY/WATCH) should shift based on which score bands perform best
4. Be conservative: max 8 changes, each change ≤ 40% of current value
5. Ensure total max score (sum of all positive weights before cap) stays roughly 90-115 pts

Return ONLY valid JSON, no markdown fences, no extra text:
{{
  "reasoning": "2-3 paragraph detailed analysis citing specific numbers from the data",
  "summary": "One sentence: the single most important insight",
  "confidence": "HIGH or MEDIUM or LOW",
  "changes": [
    {{
      "weight_key": "exact key from current weights above",
      "current_value": <number>,
      "proposed_value": <number>,
      "reason": "cite specific win-rate lift or band data that justifies this change"
    }}
  ]
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    log.info("Calling Claude API (claude-opus-4-5)...")
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    # Strip markdown fences if model adds them
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw.strip())
    return json.loads(raw)


# ════════════════════════════════════════════════════════════════════════════════
# APPLY APPROVED RECOMMENDATION TO live_scanner.py
# ════════════════════════════════════════════════════════════════════════════════

def apply_approved_recommendation():
    """
    Read latest approved recommendation from Firebase and patch live_scanner.py.
    Creates a backup before making any changes.
    """
    log.info("Looking for approved recommendations in Firebase...")
    all_recs = ai_recs_ref.get() or {}

    approved = [
        (ts, rec) for ts, rec in all_recs.items()
        if rec.get("status") == "approved" and not rec.get("applied")
    ]
    if not approved:
        log.info("No pending approved recommendations found.")
        return

    # Take the most recent approved one
    approved.sort(key=lambda x: x[0], reverse=True)
    ts, rec = approved[0]
    changes = rec.get("proposed_weights", {})

    log.info(f"Applying recommendation from {ts}: {len(changes)} weight changes")

    scanner_path = Path(__file__).parent / "live_scanner.py"
    if not scanner_path.exists():
        log.error("live_scanner.py not found")
        return

    # Backup
    backup_path = scanner_path.with_suffix(f".py.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    backup_path.write_text(scanner_path.read_text())
    log.info(f"Backup created: {backup_path}")

    code = scanner_path.read_text()
    applied = []

    # Map weight keys to the exact patterns in live_scanner.py
    PATCH_PATTERNS = {
        "breakout_momentum_max":  (r"(# 1\. Momentum.*?ba\+=)28",            "28",   "max momentum pts"),
        "breakout_ema_full":      (r"(if\s+ema==\"full\":\s+ba\+=)22",       "22",   "ema full pts"),
        "breakout_ema_partial":   (r"(elif\s+ema==\"partial\":\s+ba\+=)12",  "12",   "ema partial pts"),
        "breakout_hh_hl_strong":  (r"(hh_hl>=0\.85:\s+ba\+=)6",             "6",    "hh_hl strong pts"),
        "breakout_hh_hl_ok":      (r"(hh_hl>=0\.70:\s+ba\+=)3",             "3",    "hh_hl ok pts"),
        "breakout_atr_max":       (r"(atr_c<=0\.20:\s+ba\+=)12",             "12",   "atr max pts"),
        "breakout_vol_max":       (r"(vc<=0\.50:\s+ba\+=)8",                 "8",    "vol max pts"),
        "breakout_dist_max":      (r"(dist<=1\.0:\s+ba\+=)18",               "18",   "dist max pts"),
        "breakout_liquidity_max": (r"(avg_dollar_vol>=200_000_000:\s+ba\+=)7","7",   "liquidity max pts"),
        "penalty_weak_ema":       (r"(if\s+ema==\"weak\".*?ba-=)18",         "18",   "weak ema penalty"),
        "penalty_far_dist":       (r"(if\s+dist>15.*?ba-=)12",               "12",   "far dist penalty"),
        "penalty_neg_mom":        (r"(if\s+mom1m<-5.*?ba-=)12",              "12",   "neg mom penalty"),
        "penalty_high_vol_atr":   (r"(atr_c>0\.7.*?ba-=)8",                 "8",    "high vol penalty"),
        "threshold_ready":        (r"(status\s*=\s*\"READY\"\s+if\s+score>=)72", "72", "ready threshold"),
        "threshold_watch":        (r"(\"WATCH\"\s+if\s+score>=)55",          "55",   "watch threshold"),
    }

    import re as re_mod
    for key, new_val in changes.items():
        if key not in PATCH_PATTERNS:
            continue
        pattern, old_val, desc = PATCH_PATTERNS[key]
        current = DEFAULT_WEIGHTS.get(key)
        if new_val == current:
            continue
        new_code = re_mod.sub(
            pattern.replace(old_val, str(current)),
            lambda m, nv=str(new_val): m.group(1) + nv,
            code, flags=re_mod.DOTALL
        )
        if new_code != code:
            code = new_code
            applied.append(f"  {key}: {current} → {new_val}  ({desc})")
            log.info(f"  Patched {key}: {current} → {new_val}")
        else:
            log.warning(f"  Could not patch {key} (pattern not matched) — edit manually")

    if not applied:
        log.warning("No changes could be applied automatically. Edit live_scanner.py manually.")
        return

    scanner_path.write_text(code)
    log.info(f"live_scanner.py updated. Changes applied:\n" + "\n".join(applied))

    # Mark as applied in Firebase
    experiment_id = rec.get("experiment_id", f"ai_{ts}")
    ai_recs_ref.child(ts).update({
        "applied":         True,
        "applied_at":      datetime.now().isoformat(),
        "applied_changes": applied,
    })
    log.info(f"Marked recommendation {ts} as applied in Firebase.")
    log.info("Next steps:")
    log.info("  1. Restart live_scanner.py for the new scoring to take effect in production")
    log.info(f"  2. Run a real experiment backtest to verify on historical data:")
    log.info(f"       python backtest.py --days 60 --experiment {experiment_id}")
    log.info(f"       python optimizer.py --compare {experiment_id}")
    log.info(f"  3. Bump SCORING_VERSION in backtest.py to document the change")


# ════════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════════

def run_analysis(window="1m"):
    picks = load_picks(window=window, days=180)

    if len(picks) < 30:
        log.warning(f"Only {len(picks)} picks with '{window}' returns. Need ≥30. "
                    "Run backtest --update-returns first or wait for more history.")
        return None

    # Current performance baseline
    factors = factor_analysis(picks)
    bands   = score_band_breakdown(picks)
    current = shadow_backtest(picks, DEFAULT_WEIGHTS)

    log.info(f"Current baseline: {current['all']['n']} picks, "
             f"WR={current['all']['win_rate']}%, avg={current['all']['avg_return']:+.2f}%")

    # Call Claude
    suggestion = call_claude(picks, factors, bands, window)
    log.info(f"Claude confidence: {suggestion.get('confidence')}")
    log.info(f"Summary: {suggestion.get('summary')}")
    log.info(f"Changes proposed: {len(suggestion.get('changes', []))}")

    # Build proposed weights
    proposed_weights = dict(DEFAULT_WEIGHTS)
    changes_applied  = {}
    for ch in suggestion.get("changes", []):
        key = ch.get("weight_key")
        val = ch.get("proposed_value")
        if key in proposed_weights and val is not None:
            proposed_weights[key] = val
            changes_applied[key]  = val

    # Shadow backtest with proposed weights
    projected = shadow_backtest(picks, proposed_weights)
    log.info(f"Projected:  {projected['all']['n']} picks, "
             f"WR={projected['all']['win_rate']}%, avg={projected['all']['avg_return']:+.2f}%")

    wr_delta  = round((projected["all"]["win_rate"]  or 0) - (current["all"]["win_rate"]  or 0), 1)
    avg_delta = round((projected["all"]["avg_return"] or 0) - (current["all"]["avg_return"] or 0), 2)

    ts           = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    experiment_id = f"ai_{ts}"   # matches /scanner/experiments/{experiment_id} convention

    rec = {
        "generated_at":     datetime.now().isoformat(),
        "window":           window,
        "n_picks":          len(picks),
        "status":           "pending",
        "applied":          False,
        "experiment_id":    experiment_id,   # ← links to experiment framework
        "claude_summary":   suggestion.get("summary"),
        "claude_reasoning": suggestion.get("reasoning"),
        "claude_confidence":suggestion.get("confidence"),
        "current_stats":    current,
        "projected_stats":  projected,
        "win_rate_delta":   wr_delta,
        "avg_return_delta": avg_delta,
        "current_weights":  DEFAULT_WEIGHTS,
        "proposed_weights": proposed_weights,
        "changes":          suggestion.get("changes", []),
    }

    ai_recs_ref.child(ts).set(rec)
    log.info(f"Recommendation saved to Firebase: /scanner/ai_recommendations/{ts}")
    log.info(f"Win rate delta: {wr_delta:+.1f}%  |  Avg return delta: {avg_delta:+.2f}%")
    log.info(f"Shadow backtest used re-scored historical picks (fast estimate).")
    log.info(f"To run a real backtest with the proposed weights and compare:")
    log.info(f"  1. Edit score_stock_historical() in backtest.py with the proposed changes")
    log.info(f"  2. python backtest.py --days 60 --experiment {experiment_id}")
    log.info(f"  3. python optimizer.py --compare {experiment_id}")

    # Also save locally
    out = Path("/tmp/ai_recommendation.json")
    out.write_text(json.dumps(rec, indent=2))
    log.info(f"Saved locally to {out}")

    return rec


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Scanner Optimizer")
    parser.add_argument("--window",        default="1m",
                        help="Return window: 1w, 2w, 1m, 2m, 3m (default: 1m)")
    parser.add_argument("--all-windows",   action="store_true",
                        help="Run for all windows and pick best projected improvement")
    parser.add_argument("--apply",         action="store_true",
                        help="Apply latest APPROVED recommendation to live_scanner.py")
    parser.add_argument("--check-and-run", action="store_true",
                        help="Check Firebase flag and run analysis if requested (for cron)")
    args = parser.parse_args()

    if args.apply:
        apply_approved_recommendation()
        sys.exit(0)

    if args.check_and_run:
        flag_ref = db.reference("/scanner/run_ai_requested")
        flag = flag_ref.get()
        if not flag or flag.get("status") != "pending":
            log.info("No pending AI analysis request — nothing to do.")
            sys.exit(0)
        log.info("Pending AI request found — starting analysis...")
        flag_ref.update({"status": "running", "started_at": datetime.now().isoformat()})
        try:
            rec = run_analysis(window="1m")
            if rec:
                flag_ref.set({"status": "done", "completed_at": datetime.now().isoformat()})
                log.info("AI analysis complete. Flag reset to 'done'.")
            else:
                flag_ref.set({"status": "error", "error": "Not enough pick data",
                              "completed_at": datetime.now().isoformat()})
                log.warning("Analysis skipped — not enough data.")
        except Exception as e:
            flag_ref.set({"status": "error", "error": str(e),
                          "completed_at": datetime.now().isoformat()})
            log.error(f"AI analysis failed: {e}")
        sys.exit(0)

    windows = ["1w", "1m", "2m", "3m"] if args.all_windows else [args.window]
    best_rec, best_delta = None, -999

    for w in windows:
        rec = run_analysis(window=w)
        if rec and rec["win_rate_delta"] > best_delta:
            best_delta = rec["win_rate_delta"]
            best_rec   = rec

    if best_rec:
        log.info("=" * 60)
        log.info(f"DONE — best window: {best_rec['window']}")
        log.info(f"  Win rate:  {best_rec['current_stats']['all']['win_rate']}% → "
                 f"{best_rec['projected_stats']['all']['win_rate']}% "
                 f"({best_rec['win_rate_delta']:+.1f}%)")
        log.info(f"  Avg ret:   {best_rec['current_stats']['all']['avg_return']:+.2f}% → "
                 f"{best_rec['projected_stats']['all']['avg_return']:+.2f}%")
        log.info(f"  Summary:   {best_rec['claude_summary']}")
        log.info("View and approve at: /ai tab in the scanner dashboard")
