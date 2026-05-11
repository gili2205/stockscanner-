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

def load_picks(window="1m"):
    """Load all historical picks that have a return for the given window."""
    log.info("Loading historical picks from Firebase...")
    history = hist_ref.get() or {}

    picks = []
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
            pick["_return"] = ret
            pick["_day"]    = day_str
            picks.append(pick)

    log.info(f"Loaded {len(picks)} picks with {window} returns ({skipped} skipped — no return data yet)")
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
    return {
        "window":        window,
        "total_picks":   len(picks),
        "scan_days":     len(days),
        "date_range":    f"{days[0]} → {days[-1]}" if days else "—",
        "win_rate":      win_rate(rets),
        "avg_return":    round(mean(rets), 2)   if rets else None,
        "med_return":    round(median(rets), 2) if rets else None,
        "best":          round(max(rets), 2)    if rets else None,
        "worst":         round(min(rets), 2)    if rets else None,
    }


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--window",   default="1m",
                        help="Return window to analyze: 1w, 2w, 1m, 2m, 3m (default: 1m)")
    parser.add_argument("--all-windows", action="store_true",
                        help="Run analysis for all windows")
    args = parser.parse_args()

    windows = ["1w", "2w", "1m", "2m", "3m"] if args.all_windows else [args.window]

    all_reports = {}

    for window in windows:
        picks = load_picks(window)

        if len(picks) < 20:
            log.warning(f"Not enough picks with {window} return data ({len(picks)}). "
                        f"Need at least 20. Run backtest first or wait for more history.")
            continue

        stats   = overall_stats(picks, window)
        factors = run_factor_analysis(picks, window)
        bands   = score_band_analysis(picks, window)

        print_report(stats, factors, bands, window)

        all_reports[window] = {
            "stats":   stats,
            "factors": factors,
            "bands":   bands,
        }

    if not all_reports:
        log.error("No reports generated — not enough data with returns. "
                  "Run the backtest first and wait for at least 1 week of forward returns.")
        sys.exit(1)

    # Save to Firebase
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    try:
        report_ref.child(ts).set({
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
