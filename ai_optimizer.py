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
    Read latest approved AI recommendation from Firebase and write the new
    weights to /scanner/scoring_weights. live_scanner.py reads weights from
    there at startup — no file patching, no git commits, per-environment safe.
    """
    # Key aliases: old AI-rec keys → unified scoring_weights keys
    KEY_ALIAS = {
        "breakout_ema_full":      "ema_full",
        "breakout_ema_partial":   "ema_partial",
        "breakout_hh_hl_strong":  "hh_hl_85",
        "breakout_hh_hl_ok":      "hh_hl_70",
        "breakout_atr_max":       "atr_020",
        "breakout_vol_max":       "vc_050",
        "breakout_dist_max":      "dist_1",
        "breakout_liquidity_max": "liquidity_200m",
        "penalty_weak_ema":       "penalty_weak_ema",
        "penalty_far_dist":       "penalty_far_dist",
        "penalty_neg_mom":        "penalty_neg_mom",
        "penalty_high_vol_atr":   "penalty_high_vol_atr",
        "threshold_ready":        "threshold_ready",
        "threshold_watch":        "threshold_watch",
    }

    log.info("Looking for approved AI recommendations in Firebase...")
    all_recs = ai_recs_ref.get() or {}

    approved = [
        (ts, rec) for ts, rec in all_recs.items()
        if rec.get("status") == "approved" and not rec.get("applied")
    ]
    if not approved:
        log.info("No pending approved recommendations found.")
        return False

    approved.sort(key=lambda x: x[0], reverse=True)
    ts, rec = approved[0]
    changes = rec.get("proposed_weights", {})
    log.info(f"Applying AI recommendation from {ts}: {len(changes)} weight changes")

    # Load current weights from Firebase (to merge on top)
    weights_ref = db.reference("/scanner/scoring_weights")
    current = weights_ref.get() or {}

    applied = []
    skipped = []
    for key, new_val in changes.items():
        canonical = KEY_ALIAS.get(key, key)  # translate old keys; pass through new ones
        current[canonical] = new_val
        applied.append(f"{canonical}: → {new_val}")
        log.info(f"  {canonical} = {new_val}")

    if not applied:
        log.warning("No weight changes to apply.")
        return False

    weights_ref.set(current)
    log.info(f"Written {len(applied)} weight(s) to /scanner/scoring_weights in Firebase.")

    applied_at = datetime.now().isoformat()
    ai_recs_ref.child(ts).update({
        "applied":         True,
        "applied_at":      applied_at,
        "applied_changes": applied,
    })
    log.info(f"Marked AI recommendation {ts} as applied.")
    log.info("Restart live_scanner (scanner.service) to load the new weights.")
    return True


def apply_stat_suggestions():
    """
    Apply statistically-derived suggestions queued by the Optimizer UI.
    Reads /scanner/optimizer_suggestions, merges approved weights into
    /scanner/scoring_weights in Firebase. live_scanner.py reads from there
    at startup — no file patching, no git commits, per-environment safe.
    """
    sugs_ref = db.reference("/scanner/optimizer_suggestions")
    all_sugs = sugs_ref.get() or {}

    pending = [
        (rec_id, rec) for rec_id, rec in all_sugs.items()
        if rec.get("status") == "approved" and not rec.get("applied")
    ]
    if not pending:
        log.info("No pending stat suggestions to apply.")
        return False

    log.info(f"Found {len(pending)} stat suggestion(s) to apply")

    # Load current weights from Firebase
    weights_ref = db.reference("/scanner/scoring_weights")
    current = weights_ref.get() or {}

    applied_ids = []
    applied_at  = datetime.now().isoformat()

    for rec_id, rec in pending:
        param   = rec.get("param")
        new_val = rec.get("proposed_pts")
        if not param or new_val is None:
            log.warning(f"  Skipping {rec_id}: missing param or proposed_pts")
            continue
        current[param] = new_val
        applied_ids.append(rec_id)
        log.info(f"  {param} = {new_val}")

    if not applied_ids:
        log.warning("No stat suggestions could be applied.")
        return False

    # Write merged weights back to Firebase
    weights_ref.set(current)
    log.info(f"Written {len(applied_ids)} weight(s) to /scanner/scoring_weights.")

    # Mark individual param records as applied
    for rec_id in applied_ids:
        sugs_ref.child(rec_id).update({"applied": True, "applied_at": applied_at})
    log.info("Marked suggestions as applied in Firebase.")

    # Mark the batch record in stat_recommendations as applied (UI row status)
    batch_ids = set()
    for rec_id, rec in pending:
        if rec_id in applied_ids and rec.get("batch_id"):
            batch_ids.add(rec.get("batch_id"))
    if batch_ids:
        stat_rec_ref = db.reference("/scanner/stat_recommendations")
        for bid in batch_ids:
            try:
                stat_rec_ref.child(bid).update({
                    "applied":    True,
                    "applied_at": applied_at,
                    "status":     "applied"
                })
                log.info(f"Marked stat_recommendations/{bid} as applied.")
            except Exception as e:
                log.warning(f"Could not mark stat_recommendations/{bid}: {e}")

    log.info("Restart live_scanner (scanner.service) to load the new weights.")
    return True


def restart_scanner():
    """
    Kill live_scanner.py so the watchdog cron restarts it with updated weights.
    The watchdog runs every 5 min: pgrep -f live_scanner.py || sudo bash start.sh restart
    """
    import subprocess
    log.info("Restarting live_scanner.py so new scoring weights take effect...")
    try:
        result = subprocess.run(
            ["pkill", "-f", "live_scanner.py"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            log.info("Scanner process killed — watchdog will restart it within 5 minutes.")
        else:
            # Try sudo version as fallback
            result2 = subprocess.run(
                ["sudo", "bash", "/home/scanner/start.sh", "restart"],
                capture_output=True, text=True, timeout=30
            )
            log.info(f"start.sh restart: {result2.stdout.strip() or 'done'}")
    except Exception as e:
        log.error(f"Could not restart scanner automatically: {e}")
        log.info("Please restart manually: sudo bash /home/scanner/start.sh restart")


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
        apply_approved_recommendation()   # AI recommendations
        apply_stat_suggestions()          # Statistical optimizer suggestions
        sys.exit(0)

    if args.check_and_run:
        did_something = False

        # ── 0. Auto-apply any approved AI recommendations ────────────────────
        ai_applied = apply_approved_recommendation()
        if ai_applied:
            did_something = True
            restart_scanner()   # kill scanner; watchdog restarts with new weights

        # ── 1. Auto-apply any pending stat suggestions (accepted in the UI) ──
        stat_applied = apply_stat_suggestions()
        if stat_applied:
            did_something = True
            restart_scanner()   # kill scanner; watchdog restarts with new weights

        # ── 2. Run AI analysis if user requested it in the UI ─────────────────
        flag_ref = db.reference("/scanner/run_ai_requested")
        flag = flag_ref.get()
        if flag and flag.get("status") == "pending":
            log.info("Pending AI request found — starting analysis...")
            flag_ref.update({"status": "running", "started_at": datetime.now().isoformat()})
            try:
                rec = run_analysis(window="1m")
                if rec:
                    flag_ref.set({"status": "done", "completed_at": datetime.now().isoformat()})
                    log.info("AI analysis complete.")
                    did_something = True
                else:
                    flag_ref.set({"status": "error", "error": "Not enough pick data",
                                  "completed_at": datetime.now().isoformat()})
                    log.warning("Analysis skipped — not enough data.")
            except Exception as e:
                flag_ref.set({"status": "error", "error": str(e),
                              "completed_at": datetime.now().isoformat()})
                log.error(f"AI analysis failed: {e}")
        elif not did_something:
            log.info("Nothing pending — no stat suggestions, no AI request.")

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
