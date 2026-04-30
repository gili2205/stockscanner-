"""
NASDAQ Momentum Screener
========================
Combines the best of three open-source scanners:
  - Qullamaggie breakout scanner (VladPetrariu) — backbone, backtested edge
  - Bull flag detector (saturn-amarbat / Ross Cameron style)
  - Pattern quality scoring (slimbiggins007)

Run:
    python scanner.py              # full scan, opens HTML dashboard
    python scanner.py --watch      # intraday monitor (polls every 5 min)
    python scanner.py --nasdaq     # NASDAQ-only filter (default is on)
    python scanner.py --min-score 80
"""

import argparse
import json
import os
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

# Ensure nasdaq_scanner/factors package is importable when running from repo root
_pkg_root = str(Path(__file__).resolve().parent / "nasdaq_scanner")
if _pkg_root not in sys.path:
      sys.path.insert(0, _pkg_root)

import pandas as pd

from config import (
    SCANS_DIR, MIN_SCORE_DEFAULT, NASDAQ_ONLY,
    WEIGHT_QULLAMAGGIE, WEIGHT_BULL_FLAG, WEIGHT_PATTERN
)
from data import download_prices, get_nasdaq_universe
from factors.market_context import classify_market_regime
from factors.consolidation import score_consolidation
from factors.relative_strength import score_rs
from factors.catalyst import score_catalyst
from factors.breakout_level import classify_breakout_level
from factors.weekly import score_weekly_confluence
from factors.bull_flag import detect_bull_flag, score_bull_flag
from factors.pattern import score_pattern_quality
from ranking import rank_stocks, quality_gate, assign_rs_percentiles
from dashboard import render_dashboard


def parse_args():
    p = argparse.ArgumentParser(description="NASDAQ Momentum Screener")
    p.add_argument("--watch", action="store_true", help="Intraday monitor mode")
    p.add_argument("--no-nasdaq-filter", action="store_true", help="Include NYSE too")
    p.add_argument("--min-score", type=int, default=MIN_SCORE_DEFAULT)
    p.add_argument("--no-open", action="store_true", help="Don't auto-open dashboard")
    return p.parse_args()


def analyze_stock(ticker: str, df: pd.DataFrame, benchmark_df: pd.DataFrame) -> dict | None:
    """Run all factor analyses on a single stock. Returns result dict or None if disqualified."""
    if df is None or len(df) < 60:
        return None

    try:
        # --- Qullamaggie factors ---
        consolidation = score_consolidation(df)
        rs = score_rs(df, benchmark_df)
        catalyst = score_catalyst(df)
        breakout_level = classify_breakout_level(df)
        weekly = score_weekly_confluence(df)

        # --- Bull flag (Ross Cameron / saturn-amarbat) ---
        flag_detected, flag_data = detect_bull_flag(df)
        bull_flag_score = score_bull_flag(flag_data) if flag_detected else 0

        # --- Pattern quality (slimbiggins007) ---
        pattern = score_pattern_quality(df)

        # --- Composite score ---
        q_score = _compute_qullamaggie_score(consolidation, rs, catalyst, breakout_level, weekly)
        composite = round(
            q_score * WEIGHT_QULLAMAGGIE
            + bull_flag_score * WEIGHT_BULL_FLAG
            + pattern["score"] * WEIGHT_PATTERN
        )
        composite = max(0, min(100, composite))

        # --- Quality gate (must pass or ranks last) ---
                        vol_ratio = round(float(df["Volume"].iloc[-1]) / float(df["Volume"].iloc[-20:].mean()), 2) if len(df) >= 20 else 0.0
      passes_gate = quality_gate(consolidation, rs, vol_ratio)

        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = round(float(last["Close"]), 2)
        change_pct = round((price - float(prev["Close"])) / float(prev["Close"]) * 100, 2)
        vol_ratio = round(float(last["Volume"]) / float(df["Volume"].iloc[-20:].mean()), 2)

        return {
            "ticker": ticker,
            "price": price,
            "change_pct": change_pct,
            "volume": int(last["Volume"]),
            "vol_ratio": vol_ratio,
            "composite_score": composite,
            "passes_gate": passes_gate,
            # Qullamaggie sub-scores
            "atr_compression": consolidation["atr_compression"],
            "ema_stack": consolidation["ema_stack"],
            "hh_hl_pct": consolidation["hh_hl_pct"],
            "candle_quality": consolidation["candle_quality"],
            "rs_percentile": rs["percentile"],
            "rs_direction": rs["direction"],
            "catalyst_tier": catalyst["tier"],
            "catalyst_freshness": catalyst["freshness"],
            "breakout_level": breakout_level,
            "weekly_confluence": weekly["confluence"],
            # Bull flag
            "bull_flag": flag_detected,
            "flag_tightness": flag_data.get("tightness") if flag_detected else None,
            "flag_vol_contraction": flag_data.get("vol_contraction") if flag_detected else None,
            "bull_flag_score": bull_flag_score,
            # Pattern quality
            "setup_type": pattern["setup_type"],
            "pattern_score": pattern["score"],
            "macd_curl": pattern["macd_curl"],
            "trend_alignment": pattern["trend_alignment"],
            # Status
            "status": _get_status(composite),
            "scanned_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return None


def _compute_qullamaggie_score(consolidation, rs, catalyst, breakout_level, weekly) -> float:
    """Reproduce the evidence-based ranking logic from Qullamaggie scanner v5."""
    score = 0.0

    # EMA stack (0-25)
    stack = consolidation["ema_stack"]
    if stack == "full":
        score += 25
    elif stack == "partial":
        score += 15
    elif stack == "weak":
        score += 7

    # HH/HL price structure — double-weighted (0-20)
    hh_hl = consolidation["hh_hl_pct"]
    if hh_hl >= 0.85:
        score += 20
    elif hh_hl >= 0.70:
        score += 13
    elif hh_hl >= 0.55:
        score += 7

    # ATR compression (0-15)
    atr = consolidation["atr_compression"]
    if atr <= 0.25:
        score += 15
    elif atr <= 0.35:
        score += 11
    elif atr <= 0.45:
        score += 7
    elif atr <= 0.55:
        score += 3

    # Relative strength (0-20)
    rs_pct = rs["percentile"]
    if rs_pct >= 90:
        score += 20
    elif rs_pct >= 80:
        score += 15
    elif rs_pct >= 70:
        score += 10
    elif rs_pct >= 50:
        score += 5

    # Breakout level (0-10)
    if breakout_level == "ATH":
        score += 10
    elif breakout_level == "multi-year":
        score += 8
    elif breakout_level == "52-week":
        score += 6
    elif breakout_level == "prior resistance":
        score += 3

    # Catalyst freshness (0-5)
    freshness = catalyst["freshness"]
    if freshness >= 0.8:
        score += 5
    elif freshness >= 0.5:
        score += 3
    elif freshness >= 0.2:
        score += 1

    # Weekly confluence (0-5)
    if weekly["confluence"]:
        score += 5

    return min(100.0, score)


def _get_status(score: int) -> str:
    if score >= 85:
        return "READY"
    if score >= 70:
        return "WATCH"
    if score >= 50:
        return "BUILDING"
    return "WEAK"


def run_scan(min_score: int = 50, nasdaq_only: bool = True) -> list[dict]:
    print("\n🔍 NASDAQ Momentum Screener — Starting scan...")
    print(f"   Filter: {'NASDAQ only' if nasdaq_only else 'NYSE + NASDAQ'} | Min score: {min_score}")

    # Step 1: Get universe
    print("\n[1/6] Fetching ticker universe...")
    tickers = get_nasdaq_universe(nasdaq_only=nasdaq_only)
    print(f"   → {len(tickers)} liquid stocks to scan")

    # Step 2: Download prices
    print("\n[2/6] Downloading price data (cached after first run)...")
    prices, benchmark = download_prices(tickers)
    print(f"   → Data ready for {len(prices)} tickers")

    # Step 3: Market regime check
    print("\n[3/6] Computing market regime...")
    regime = classify_market_regime(benchmark)
    print(f"   → Market regime: {regime['label']} ({regime['score']}/5 indicators favorable)")
    if regime["label"] == "Risk Off":
        print("   ⚠️  Risk-Off regime detected — scan suppressed. Wait for better conditions.")
        return []

    # Step 4: Analyze each stock
    print(f"\n[4/6] Analyzing {len(prices)} stocks across 8 factor categories...")
    results = []
    errors = 0
    for i, (ticker, df) in enumerate(prices.items()):
        if i % 200 == 0 and i > 0:
            print(f"   ... {i}/{len(prices)} processed ({len(results)} candidates so far)")
        result = analyze_stock(ticker, df, benchmark)
        if result:
            results.append(result)
        else:
            errors += 1

    print(f"   → {len(results)} stocks analyzed ({errors} skipped — insufficient data)")

    # Step 5: Rank
    print("\n[5/6] Ranking by composite score...")
    assign_rs_percentiles(results)
    ranked = rank_stocks(results)
    qualified = [r for r in ranked if r["composite_score"] >= min_score]
    print(f"   → {len(qualified)} stocks scored {min_score}+")
    ready = sum(1 for r in qualified if r["status"] == "READY")
    watch = sum(1 for r in qualified if r["status"] == "WATCH")
    print(f"   → READY: {ready} | WATCH: {watch}")

    # Step 6: Save results
    print("\n[6/6] Saving results...")
    SCANS_DIR.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    json_path = SCANS_DIR / f"scan_{date_str}.json"
    with open(json_path, "w") as f:
        json.dump({
            "scan_date": date_str,
            "regime": regime,
            "total_scanned": len(prices),
            "results": ranked
        }, f, indent=2, default=str)
    print(f"   → Saved to {json_path}")

    return ranked


def watch_mode(results: list[dict]):
    """Intraday monitor — polls every 5 minutes, alerts when a stock approaches breakout."""
    import yfinance as yf
    watchlist = [r["ticker"] for r in results if r["status"] in ("READY", "WATCH")]
    print(f"\n👁️  Watch mode active — monitoring {len(watchlist)} tickers every 5 min")
    print("   Press Ctrl+C to stop.\n")

    while True:
        try:
            batch = " ".join(watchlist)
            live = yf.download(batch, period="1d", interval="5m", progress=False)
            now = datetime.now().strftime("%H:%M")
            alerts = []

            for ticker in watchlist:
                result = next((r for r in results if r["ticker"] == ticker), None)
                if not result:
                    continue
                try:
                    closes = live["Close"][ticker].dropna()
                    if closes.empty:
                        continue
                    current = float(closes.iloc[-1])
                                                    # Alert if current price is within 1% above the scan-time price
                                              # (uses scan result price as breakout level proxy — more accurate than intraday high)
                                              scan_price = result.get("price", 0)
                                              if scan_price > 0:
                                                                                    dist = (current - scan_price) / scan_price
                                                                                    if -0.01 <= dist <= 0.02:  # within 1% below or 2% above scan price
                                                                                                                              alerts.append(f"  🚀 {ticker} — near breakout level at ${current:.2f} (scan: ${scan_price:.2f})")
                except Exception:
                    continue

            if alerts:
                print(f"\n[{now}] BREAKOUT ALERTS:")
                for a in alerts:
                    print(a)
                try:
                    import subprocess
                    for a in alerts:
                        ticker = a.split()[1]
                        subprocess.run(["osascript", "-e",
                            f'display notification "{a}" with title "Scanner Alert"'], check=False)
                except Exception:
                    pass
            else:
                print(f"[{now}] No alerts. {len(watchlist)} stocks monitored.", end="\r")

            time.sleep(300)
        except KeyboardInterrupt:
            print("\n\nWatch mode stopped.")
            break


def main():
    args = parse_args()
    nasdaq_only = not args.no_nasdaq_filter

    results = run_scan(min_score=args.min_score, nasdaq_only=nasdaq_only)

    if not results:
        print("\nNo results — check market regime or lower --min-score threshold.")
        return

    # Render HTML dashboard
    date_str = datetime.now().strftime("%Y-%m-%d")
    html_path = SCANS_DIR / f"scan_{date_str}.html"
    render_dashboard(results, html_path, date_str)
    print(f"\n✅ Dashboard: {html_path}")

    if not args.no_open:
        webbrowser.open(f"file://{html_path.resolve()}")

    if args.watch:
        watch_mode(results)


if __name__ == "__main__":
    main()
