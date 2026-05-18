"""
Scanner Optimizer
=================
Reads historical picks + returns from Firebase and produces a factor
analysis report showing which signals actually predict winning stocks.

Usage:
    python optimizer.py              # analyze all available history
    python optimizer.py --min-days 5 # only include picks with ≥5 days of returns data
    python optimizer.py --window 1m  # analyze a specific return window (1w/2w/1m/2m/3m)

Output:
    - Console report
    - /scanner/optimization_reports/<timestamp> in Firebase
    - /tmp/optimizer_report.json locally
"""

import os, sys, json, logging, argparse
from datetime import datetime, date
from pathlib import Path
from collections import defaultdict

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

import numpy as np
import firebase_admin
from firebase_admin import credentials, db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FIREBASE_URL  = os.environ["FIREBASE_URL"]
FIREBASE_CRED = os.environ["FIREBASE_CRED"]

cred = credentials.Certificate(FIREBASE_CRED)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})
hist_ref   = db.reference("/scanner/history")
report_ref = db.reference("/scanner/optimization_reports")
exp_ref    = db.reference("/scanner/experiments")


# ── Helpers ────────────────────────────────────────────────────────────────────

def mean(values):
    return sum(values) / len(values) if values else None

def median(values):
    if not values: return None
    s = sorted(values)
    n = len(s)
    return (s[n//2-1] + s[n//2]) / 2 if n % 2 == 0 else s[n//2]

def win_rate(returns):
    if not returns: return None
    return round(sum(1 for r in returns if r > 0) / len(returns) * 100, 1)

def fmt_pct(v):
    if v is None: return "  —   "
    return f"{v:+6.1f}%"

def fmt_wr(v):
    if v is None: return "  —  "
    return f"{v:5.1f}%"


# ── Load data ──────────────────────────────────────────────────────────────────

def load_picks(window="1m", source_ref=None, label="production"):
    """Load historical picks that have a return for the given window.

    Deduplicates to the FIRST occurrence of each ticker (same logic as the
    analytics dashboard's buildPicks()). This ensures optimizer stats match
    what the user sees in the analytics page.

    source_ref : Firebase DatabaseReference | None
        Reference to load history from. Defaults to /scanner/history.
        Pass exp_ref.child(name).child("history") for experiment data.
    label : str
        Human-readable name shown in log messages.
    """
    ref = source_ref or hist_ref
    log.info(f"Loading {label} picks from Firebase ({window} window)...")
    history = ref.get() or {}

    # Collect all occurrences keyed by (day, ticker)
    all_picks = []
    skipped = 0
    for day_str, day_data in history.items():
        if not isinstance(day_data, dict):
            continue
        for ticker, pick in day_data.items():
            if not isinstance(pick, dict):
                continue
            returns = pick.get("returns", {})
            if not isinstance(returns, dict):
                continue
            ret = returns.get(window)
            if ret is None:
                skipped += 1
                continue
            p = dict(pick)
            p["_return"] = ret
            p["_day"]    = day_str
            p["_ticker"] = ticker
            all_picks.append(p)

    # Deduplicate: keep only the earliest scan date per ticker
    # (mirrors analytics dashboard buildPicks() which uses first-seen)
    first_seen = {}
    for p in all_picks:
        t = p["_ticker"]
        if t not in first_seen or p["_day"] < first_seen[t]["_day"]:
            first_seen[t] = p

    picks = list(first_seen.values())

    log.info(f"Loaded {len(picks)} {label} picks with {window} returns "
             f"({skipped} skipped — no return data yet; "
             f"{len(all_picks)-len(picks)} duplicate ticker-days removed)")
    return picks


# ── Factor analysis ────────────────────────────────────────────────────────────

def analyze_factor(picks, factor_name, condition_fn, label="with signal"):
    """Split picks into with/without a condition and compare returns."""
    with_sig  = [p for p in picks if condition_fn(p)]
    without   = [p for p in picks if not condition_fn(p)]

    rets_with = [p["_return"] for p in with_sig]
    rets_wout = [p["_return"] for p in without]

    return {
        "factor":        factor_name,
        "label":         label,
        "n_with":        len(with_sig),
        "n_without":     len(without),
        "wr_with":       win_rate(rets_with),
        "wr_without":    win_rate(rets_wout),
        "avg_ret_with":  round(mean(rets_with), 2)  if rets_with  else None,
        "avg_ret_wout":  round(mean(rets_wout), 2)  if rets_wout  else None,
        "med_ret_with":  round(median(rets_with), 2) if rets_with else None,
        "med_ret_wout":  round(median(rets_wout), 2) if rets_wout else None,
        "wr_diff":       round((win_rate(rets_with) or 0) - (win_rate(rets_wout) or 0), 1),
        "avg_diff":      round((mean(rets_with) or 0) - (mean(rets_wout) or 0), 2),
    }


def run_factor_analysis(picks, window):
    """Run all factor analyses and return sorted results."""

    factors = [
        # EMA stack
        ("EMA stack = FULL",      lambda p: p.get("ema_stack") == "full"),
        ("EMA stack = PARTIAL",   lambda p: p.get("ema_stack") == "partial"),
        ("EMA stack = WEAK",      lambda p: p.get("ema_stack") == "weak"),

        # Level
        ("Level = ATH",           lambda p: "ATH" in str(p.get("level",""))),
        ("Level = 52-week high",  lambda p: "52" in str(p.get("level",""))),
        ("Level = multi-year",    lambda p: "multi" in str(p.get("level","")).lower()),

        # Volume contraction
        ("Vol dry ≤ 50%",         lambda p: (p.get("vol_contraction") or 1) <= 0.5),
        ("Vol dry ≤ 70%",         lambda p: (p.get("vol_contraction") or 1) <= 0.7),
        ("Vol dry ≤ 90%",         lambda p: (p.get("vol_contraction") or 1) <= 0.9),
        ("Vol dry > 100%",        lambda p: (p.get("vol_contraction") or 1) > 1.0),

        # ATR compression
        ("ATR ≤ 0.25",            lambda p: (p.get("atr") or 1) <= 0.25),
        ("ATR ≤ 0.35",            lambda p: (p.get("atr") or 1) <= 0.35),
        ("ATR > 0.50",            lambda p: (p.get("atr") or 0) > 0.50),

        # HH/HL trend structure
        ("HH/HL ≥ 0.85",          lambda p: (p.get("hh_hl") or 0) >= 0.85),
        ("HH/HL ≥ 0.70",          lambda p: (p.get("hh_hl") or 0) >= 0.70),

        # Momentum
        ("Momentum 1M ≥ +15%",    lambda p: (p.get("momentum_1m") or 0) >= 15),
        ("Momentum 1M ≥ +8%",     lambda p: (p.get("momentum_1m") or 0) >= 8),
        ("Momentum 1M ≥ +3%",     lambda p: (p.get("momentum_1m") or 0) >= 3),
        ("Momentum 1M negative",  lambda p: (p.get("momentum_1m") or 0) < 0),

        # Score bands
        ("Score ≥ 72 (READY)",    lambda p: (p.get("score") or 0) >= 72),
        ("Score 55-71 (WATCH)",   lambda p: 55 <= (p.get("score") or 0) < 72),
        ("Score < 55 (BUILDING)", lambda p: (p.get("score") or 0) < 55),
        ("Score ≥ 80",            lambda p: (p.get("score") or 0) >= 80),
        ("Score ≥ 65",            lambda p: (p.get("score") or 0) >= 65),

        # RS percentile
        ("RS %ile ≥ 90",          lambda p: (p.get("rs_percentile") or 0) >= 90),
        ("RS %ile ≥ 80",          lambda p: (p.get("rs_percentile") or 0) >= 80),
        ("RS %ile ≥ 70",          lambda p: (p.get("rs_percentile") or 0) >= 70),

        # Setups
        ("Pre-breakout",          lambda p: bool(p.get("pre_breakout"))),
        ("Bull flag",             lambda p: bool(p.get("bull_flag"))),

        # Status
        ("Status = READY",        lambda p: p.get("status") == "READY"),
        ("Status = WATCH",        lambda p: p.get("status") == "WATCH"),
    ]

    results = []
    for name, fn in factors:
        r = analyze_factor(picks, name, fn)
        if r["n_with"] >= 10:  # skip factors with too few samples
            results.append(r)

    # Sort by win rate difference (most predictive first)
    results.sort(key=lambda x: x["wr_diff"], reverse=True)
    return results


def simulate_suggestions(picks):
    """
    Derive weight suggestions from factor analysis and simulate their impact
    by re-scoring ALL historical picks with the proposed weights.

    Uses the same FACTOR_PATCH_MAP as the UI (app.py) so suggestions are consistent.
    Returns a dict with baseline vs projected win rate / avg return, stored in the report.
    """
    factors = run_factor_analysis(picks, "simulation")

    # Mirror of FACTOR_PATCH_MAP in app.py — keep in sync
    FACTOR_PATCH_MAP = {
        'EMA stack = FULL':    {'param': 'ema_full',    'curPts': 25, 'boostPts': 30, 'reducePts': 18},
        'EMA stack = PARTIAL': {'param': 'ema_partial', 'curPts': 15, 'boostPts': 19, 'reducePts': 10},
        'ATR ≤ 0.25':          {'param': 'atr_025',     'curPts': 15, 'boostPts': 19, 'reducePts': 10},
        'ATR ≤ 0.35':          {'param': 'atr_030',     'curPts': 10, 'boostPts': 13, 'reducePts':  7},
        'Vol dry ≤ 50%':       {'param': 'vc_050',      'curPts': 15, 'boostPts': 18, 'reducePts': 10},
        'Vol dry ≤ 70%':       {'param': 'vc_065',      'curPts': 10, 'boostPts': 13, 'reducePts':  7},
        'HH/HL ≥ 0.85':        {'param': 'hh_hl_85',   'curPts': 12, 'boostPts': 16, 'reducePts':  8},
        'HH/HL ≥ 0.70':        {'param': 'hh_hl_70',   'curPts':  8, 'boostPts': 11, 'reducePts':  5},
        'Dist ≤ 1%':           {'param': 'dist_1',      'curPts': 20, 'boostPts': 24, 'reducePts': 14},
        'Dist ≤ 3%':           {'param': 'dist_3p5',    'curPts': 11, 'boostPts': 14, 'reducePts':  8},
    }

    # Condition functions that match each param to a pick's signals
    PARAM_CONDITIONS = {
        'atr_025':    lambda p: (p.get('atr') or 1)              <= 0.25,
        'atr_030':    lambda p: (p.get('atr') or 1)              <= 0.35,
        'vc_050':     lambda p: (p.get('vol_contraction') or 1)  <= 0.50,
        'vc_065':     lambda p: (p.get('vol_contraction') or 1)  <= 0.65,
        'ema_full':   lambda p: p.get('ema_stack') == 'full',
        'ema_partial':lambda p: p.get('ema_stack') == 'partial',
        'hh_hl_85':   lambda p: (p.get('hh_hl') or 0)           >= 0.85,
        'hh_hl_70':   lambda p: (p.get('hh_hl') or 0)           >= 0.70,
        'dist_1':     lambda p: (p.get('dist_to_level') or 100)  <= 1.0,
        'dist_3p5':   lambda p: (p.get('dist_to_level') or 100)  <= 3.5,
    }

    # Determine which patches to apply (lift >= 5% → boost, <= -5% → reduce)
    patches = []
    for f in factors:
        pm = FACTOR_PATCH_MAP.get(f['factor'])
        if not pm:
            continue
        lift = f['wr_diff']
        if lift >= 5:
            patches.append({'param': pm['param'], 'delta': pm['boostPts'] - pm['curPts'],
                             'factor': f['factor'], 'direction': 'boost'})
        elif lift <= -5:
            patches.append({'param': pm['param'], 'delta': pm['reducePts'] - pm['curPts'],
                             'factor': f['factor'], 'direction': 'reduce'})

    if not patches:
        return None

    # Baseline — all picks shown
    all_rets = [p['_return'] for p in picks]
    baseline_wr  = round(win_rate(all_rets) or 0, 1)
    baseline_avg = round(mean(all_rets) or 0, 2)

    # Re-score each pick: add deltas for active signals, keep score >= 0
    simulated_rets = []
    for p in picks:
        base_score = p.get('score_buy_now') or p.get('score') or 0
        delta = sum(
            patch['delta']
            for patch in patches
            if PARAM_CONDITIONS.get(patch['param'], lambda _: False)(p)
        )
        new_score = max(0, base_score + delta)
        # Only count picks that would still surface (score >= 40 = WATCH threshold)
        if new_score >= 40:
            simulated_rets.append(p['_return'])

    if len(simulated_rets) < 20:
        return None

    projected_wr  = round(win_rate(simulated_rets) or 0, 1)
    projected_avg = round(mean(simulated_rets) or 0, 2)

    return {
        'baseline_wr':   baseline_wr,
        'baseline_avg':  baseline_avg,
        'baseline_n':    len(picks),
        'projected_wr':  projected_wr,
        'projected_avg': projected_avg,
        'projected_n':   len(simulated_rets),
        'wr_delta':      round(projected_wr  - baseline_wr,  1),
        'avg_delta':     round(projected_avg - baseline_avg, 2),
        'patches':       patches,
    }


def score_band_analysis(picks, window):
    """Break down performance by score decile."""
    bands = defaultdict(list)
    for p in picks:
        score = p.get("score") or 0
        band  = (score // 10) * 10  # 0,10,20,...,90
        bands[band].append(p["_return"])

    rows = []
    for band in sorted(bands.keys()):
        rets = bands[band]
        rows.append({
            "score_range": f"{band}-{band+9}",
            "n_picks":     len(rets),
            "win_rate":    win_rate(rets),
            "avg_return":  round(mean(rets), 2) if rets else None,
            "med_return":  round(median(rets), 2) if rets else None,
        })
    return rows


def overall_stats(picks, window):
    rets = [p["_return"] for p in picks]
    days = sorted(set(p["_day"] for p in picks))
    best_val  = round(max(rets), 2)  if rets else None
    worst_val = round(min(rets), 2)  if rets else None
    best_pick  = next((p for p in picks if round(p["_return"], 2) == best_val),  None)
    worst_pick = next((p for p in picks if round(p["_return"], 2) == worst_val), None)
    return {
        "window":        window,
        "total_picks":   len(picks),
        "scan_days":     len(days),
        "date_range":    f"{days[0]} → {days[-1]}" if days else "—",
        "win_rate":      win_rate(rets),
        "avg_return":    round(mean(rets), 2)   if rets else None,
        "med_return":    round(median(rets), 2) if rets else None,
        "best":          best_val,
        "best_ticker":   best_pick.get("_ticker", "") if best_pick else "",
        "worst":         worst_val,
        "worst_ticker":  worst_pick.get("_ticker", "") if worst_pick else "",
    }


# ── Experiment comparison ──────────────────────────────────────────────────────

def print_comparison(prod_picks, exp_picks, exp_name, window):
    """Print a side-by-side comparison of production vs experiment picks."""
    SEP = "─" * 80

    def stats(picks):
        rets = [p["_return"] for p in picks]
        days = sorted(set(p["_day"] for p in picks))
        return {
            "n":        len(picks),
            "win_rate": win_rate(rets),
            "avg":      round(mean(rets), 2) if rets else None,
            "med":      round(median(rets), 2) if rets else None,
            "best":     round(max(rets), 2) if rets else None,
            "worst":    round(min(rets), 2) if rets else None,
            "days":     len(days),
            "versions": sorted(set(p.get("scoring_version", "unknown") for p in picks)),
        }

    ps = stats(prod_picks)
    es = stats(exp_picks)

    def delta(a, b):
        if a is None or b is None: return "  —  "
        d = b - a
        return f"{d:+.1f}%" if isinstance(d, float) else f"{d:+d}"

    print(f"\n{'═'*80}")
    print(f"  EXPERIMENT COMPARISON: production  vs  {exp_name}")
    print(f"  Return window: {window.upper()}   |   Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═'*80}\n")
    print(f"  {'Metric':<20} {'Production':>14} {'Experiment':>14} {'Delta':>10}")
    print(f"  {'─'*20} {'─'*14} {'─'*14} {'─'*10}")
    print(f"  {'Picks':<20} {ps['n']:>14,} {es['n']:>14,} {es['n']-ps['n']:>+10,}")
    print(f"  {'Scan days':<20} {ps['days']:>14} {es['days']:>14} {'':>10}")
    print(f"  {'Win rate':<20} {fmt_wr(ps['win_rate']):>14} {fmt_wr(es['win_rate']):>14} {delta(ps['win_rate'], es['win_rate']):>10}")
    print(f"  {'Avg return':<20} {fmt_pct(ps['avg']):>14} {fmt_pct(es['avg']):>14} {delta(ps['avg'], es['avg']):>10}")
    print(f"  {'Median return':<20} {fmt_pct(ps['med']):>14} {fmt_pct(es['med']):>14} {delta(ps['med'], es['med']):>10}")
    print(f"  {'Best pick':<20} {fmt_pct(ps['best']):>14} {fmt_pct(es['best']):>14} {'':>10}")
    print(f"  {'Worst pick':<20} {fmt_pct(ps['worst']):>14} {fmt_pct(es['worst']):>14} {'':>10}")
    print(f"  {'Scoring version':<20} {str(ps['versions'][0] if ps['versions'] else '?'):>14} "
          f"{str(es['versions'][0] if es['versions'] else '?'):>14}")

    # Factor comparison
    if prod_picks and exp_picks:
        print(f"\n\nFACTOR WIN-RATE LIFT — production vs experiment")
        print(SEP)
        prod_factors = {f["factor"]: f for f in run_factor_analysis(prod_picks, window)}
        exp_factors  = {f["factor"]: f for f in run_factor_analysis(exp_picks,  window)}
        all_factors  = sorted(set(prod_factors) | set(exp_factors))
        print(f"  {'Factor':<30} {'Prod WR lift':>12} {'Exp WR lift':>12} {'Change':>10}")
        print(f"  {'─'*30} {'─'*12} {'─'*12} {'─'*10}")
        for fname in all_factors:
            pf = prod_factors.get(fname)
            ef = exp_factors.get(fname)
            pd_lift = pf["wr_diff"] if pf else None
            ed_lift = ef["wr_diff"] if ef else None
            ch = f"{(ed_lift - pd_lift):+.1f}%" if pd_lift is not None and ed_lift is not None else "  —"
            print(f"  {fname:<30} {fmt_wr(pd_lift):>12} {fmt_wr(ed_lift):>12} {ch:>10}")

    # Verdict
    print(f"\n\nVERDICT")
    print(SEP)
    wr_delta  = (es["win_rate"] or 0) - (ps["win_rate"] or 0)
    avg_delta = (es["avg"] or 0) - (ps["avg"] or 0)
    if wr_delta >= 3 and avg_delta >= 0:
        verdict = "✅ PROMOTE — experiment beats production on both win rate and avg return"
    elif wr_delta >= 3:
        verdict = "🟡 MIXED — higher win rate but lower avg return, review carefully"
    elif wr_delta <= -3:
        verdict = "❌ REJECT — experiment underperforms production"
    else:
        verdict = "⚪ NEUTRAL — no significant difference, need more data"
    print(f"  {verdict}")
    print(f"  Win rate:   {fmt_wr(ps['win_rate'])} → {fmt_wr(es['win_rate'])}  ({wr_delta:+.1f}%)")
    print(f"  Avg return: {fmt_pct(ps['avg'])} → {fmt_pct(es['avg'])}  ({avg_delta:+.2f}%)")
    print(f"\n{'═'*80}\n")


# ── Print report ───────────────────────────────────────────────────────────────

def print_report(stats, factors, bands, window):
    SEP = "─" * 80

    print(f"\n{'═'*80}")
    print(f"  SCANNER FACTOR ANALYSIS REPORT  —  {window.upper()} return window")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═'*80}\n")

    print("OVERALL PERFORMANCE")
    print(SEP)
    print(f"  Picks analyzed : {stats['total_picks']:,}  ({stats['scan_days']} scan days)")
    print(f"  Date range     : {stats['date_range']}")
    print(f"  Win rate       : {fmt_wr(stats['win_rate'])}")
    print(f"  Avg return     : {fmt_pct(stats['avg_return'])}")
    print(f"  Median return  : {fmt_pct(stats['med_return'])}")
    print(f"  Best pick      : {fmt_pct(stats['best'])}")
    print(f"  Worst pick     : {fmt_pct(stats['worst'])}")

    print(f"\n\nPERFORMANCE BY SCORE BAND")
    print(SEP)
    print(f"  {'Score':10} {'N':>6} {'Win rate':>10} {'Avg ret':>10} {'Med ret':>10}")
    print(f"  {'─'*10} {'─'*6} {'─'*10} {'─'*10} {'─'*10}")
    for b in bands:
        print(f"  {b['score_range']:10} {b['n_picks']:>6} {fmt_wr(b['win_rate']):>10} "
              f"{fmt_pct(b['avg_return']):>10} {fmt_pct(b['med_return']):>10}")

    print(f"\n\nFACTOR ANALYSIS  (sorted by win-rate lift, min 10 picks)")
    print(SEP)
    print(f"  {'Factor':<30} {'N':>5} {'WR with':>8} {'WR w/o':>8} {'Lift':>7} {'Avg+':>8} {'Avg-':>8} {'Edge':>7}")
    print(f"  {'─'*30} {'─'*5} {'─'*8} {'─'*8} {'─'*7} {'─'*8} {'─'*8} {'─'*7}")

    for f in factors:
        lift = f["wr_diff"]
        edge = "🟢 STRONG" if lift >= 10 else "🟡 MILD" if lift >= 5 else "⚪ WEAK" if lift >= 0 else "🔴 HURTS"
        print(f"  {f['factor']:<30} {f['n_with']:>5} "
              f"{fmt_wr(f['wr_with']):>8} {fmt_wr(f['wr_without']):>8} "
              f"{lift:>+6.1f}% "
              f"{fmt_pct(f['avg_ret_with']):>8} {fmt_pct(f['avg_ret_wout']):>8}  {edge}")

    print(f"\n\nKEY INSIGHTS")
    print(SEP)
    strong = [f for f in factors if f["wr_diff"] >= 10]
    hurts  = [f for f in factors if f["wr_diff"] <= -5]

    if strong:
        print("  ✅ STRONG PREDICTORS (consider increasing weight):")
        for f in strong:
            print(f"     • {f['factor']}: +{f['wr_diff']:.1f}% win rate lift")
    else:
        print("  ℹ️  No factors with >10% win rate lift found yet (need more data)")

    if hurts:
        print("\n  ❌ HURTS PERFORMANCE (consider decreasing weight):")
        for f in hurts:
            print(f"     • {f['factor']}: {f['wr_diff']:.1f}% win rate drag")

    print(f"\n{'═'*80}\n")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scanner factor analysis optimizer")
    parser.add_argument("--window",     default="1m",
                        help="Return window to analyze: 1w, 2w, 1m, 2m, 3m (default: 1m)")
    parser.add_argument("--all-windows", action="store_true",
                        help="Run analysis for all windows")
    parser.add_argument("--experiment", type=str, default=None,
                        help="Analyze an experiment instead of production data. "
                             "Loads from /scanner/experiments/{NAME}/history.")
    parser.add_argument("--compare",   type=str, default=None,
                        help="Compare experiment NAME side-by-side with production. "
                             "Prints a comparison table and a PROMOTE/REJECT verdict.")
    args = parser.parse_args()

    windows = ["1w", "2w", "1m", "2m", "3m"] if args.all_windows else [args.window]

    # ── Compare mode ────────────────────────────────────────────────────────────
    if args.compare:
        exp_name    = args.compare
        exp_history = exp_ref.child(exp_name).child("history")
        exp_meta    = exp_ref.child(exp_name).child("meta").get() or {}
        log.info(f"Experiment meta: {exp_meta}")

        for window in windows:
            prod_picks = load_picks(window, label="production")
            exp_picks  = load_picks(window, source_ref=exp_history, label=exp_name)
            if len(prod_picks) < 20 or len(exp_picks) < 20:
                log.warning(f"Not enough picks for window {window} — need ≥20 in both datasets")
                continue
            print_comparison(prod_picks, exp_picks, exp_name, window)
        sys.exit(0)

    # ── Experiment or production analysis ───────────────────────────────────────
    if args.experiment:
        source_ref = exp_ref.child(args.experiment).child("history")
        label      = args.experiment
        save_ref   = exp_ref.child(args.experiment).child("report")
        log.info(f"Analyzing experiment: {args.experiment}")
    else:
        source_ref = None
        label      = "production"
        save_ref   = report_ref
        log.info("Analyzing production history")

    all_reports = {}

    for window in windows:
        picks = load_picks(window, source_ref=source_ref, label=label)

        if len(picks) < 20:
            log.warning(f"Not enough picks with {window} return data ({len(picks)}). "
                        f"Need at least 20. Run backtest first or wait for more history.")
            continue

        stats   = overall_stats(picks, window)
        factors = run_factor_analysis(picks, window)
        bands   = score_band_analysis(picks, window)

        # Simulate proposed weight changes on all picks for this window
        simulation = simulate_suggestions(picks)
        if simulation:
            log.info(f"Simulation ({window}): WR {simulation['baseline_wr']}% → "
                     f"{simulation['projected_wr']}% ({simulation['wr_delta']:+.1f}%) "
                     f"on {simulation['baseline_n']} picks")

        print_report(stats, factors, bands, window)

        all_reports[window] = {
            "stats":      stats,
            "factors":    factors,
            "bands":      bands,
            "simulation": simulation,
        }

    if not all_reports:
        log.error("No reports generated — not enough data with returns. "
                  "Run the backtest first and wait for at least 1 week of forward returns.")
        sys.exit(1)

    # Save to Firebase (experiment report path or production report path)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    try:
        if args.experiment:
            save_ref.set({
                "generated_at": datetime.now().isoformat(),
                "experiment":   args.experiment,
                "windows":      list(all_reports.keys()),
                "reports":      all_reports,
            })
            log.info(f"Report saved to /scanner/experiments/{args.experiment}/report")
            log.info(f"Compare vs production: python optimizer.py --compare {args.experiment}")
        else:
            save_ref.child(ts).set({
                "generated_at": datetime.now().isoformat(),
                "windows":      list(all_reports.keys()),
                "reports":      all_reports,
            })
            log.info(f"Report saved to Firebase at /scanner/optimization_reports/{ts}")
    except Exception as e:
        log.warning(f"Could not save to Firebase: {e}")

    # Save locally
    out = Path("/tmp/optimizer_report.json")
    out.write_text(json.dumps(all_reports, indent=2))
    log.info(f"Report saved locally to {out}")
