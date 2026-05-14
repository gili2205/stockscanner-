"""
Backtest Engine
===============
Reconstructs 30 days of scanner signals using historical price data.
Runs on GCP VM. Results stored in Firebase /scanner/history/YYYY-MM-DD.

Usage:
    python backtest.py                    # last 30 trading days
    python backtest.py --days 60          # last 60 trading days
    python backtest.py --date 2026-04-01  # specific date only

Strategy:
    For each historical trading day:
    1. Load OHLCV data up to that day (simulating what scanner would see)
    2. Apply full scoring logic (same as live scanner)
    3. Store top 200 picks with all signals
    4. Fetch forward returns at 1W/2W/1M/2M/3M for picks that have enough history
"""

import os, sys, time, json, logging, argparse
import concurrent.futures
from datetime import datetime, date, timedelta
from pathlib import Path
import pytz

# Load .env automatically so the script works from any shell without
# needing to manually source it first. Checks script dir, then /home/scanner/.
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
import pandas as pd
import numpy as np
import yfinance as yf
import firebase_admin
from firebase_admin import credentials, db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")
FIREBASE_URL  = os.environ["FIREBASE_URL"]
FIREBASE_CRED = os.environ["FIREBASE_CRED"]

cred = credentials.Certificate(FIREBASE_CRED)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})
hist_ref  = db.reference("/scanner/history")
first_ref = db.reference("/scanner/first_seen")

# ── Scoring version ────────────────────────────────────────────────────────────
# Bump this string whenever the scoring logic in score_stock_historical() changes.
# Format: "v{N}_{short_description}"
# Every pick stored in Firebase carries this tag so the optimizer can filter
# by version and experiments can be compared apples-to-apples.
SCORING_VERSION = "v2_base_setup"

# ── Universe ──────────────────────────────────────────────────────────────────
def get_universe():
    """Get NASDAQ tickers from SEC EDGAR."""
    import requests
    try:
        log.info("Fetching universe from SEC EDGAR...")
        r = requests.get(
            "https://efts.sec.gov/LATEST/search-index?q=%22%22&dateRange=custom"
            "&startdt=2024-01-01&forms=10-K&hits.hits._source=period_of_report,entity_name",
            headers={"User-Agent": "scanner analytics@scanner.com"},
            timeout=30
        )
        # Fallback: use yfinance NASDAQ screener
    except Exception:
        pass

    # Use a curated liquid NASDAQ list as fallback
    try:
        log.info("Fetching from NASDAQ API...")
        r = requests.get(
            "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=5000&exchange=NASDAQ",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30
        )
        data = r.json()
        rows = data.get("data", {}).get("table", {}).get("rows", [])
        tickers = [row["symbol"] for row in rows if row.get("symbol")]
        log.info(f"Got {len(tickers)} tickers from NASDAQ API")
        return tickers
    except Exception as e:
        log.warning(f"NASDAQ API failed: {e}")

    # Final fallback: use current Firebase all_stocks
    log.info("Using current scanner universe from Firebase...")
    try:
        current = db.reference("/scanner/all_stocks").get() or {}
        tickers = list(current.keys())
        log.info(f"Got {len(tickers)} tickers from Firebase")
        return tickers
    except Exception as e:
        log.error(f"Firebase fallback failed: {e}")
        return []


# ── Price download ─────────────────────────────────────────────────────────────
def _download_one_batch(batch, start_str, end_str):
    """Run yf.download for one batch — called inside a thread so we can time it out."""
    return yf.download(
        batch, start=start_str, end=end_str,
        auto_adjust=True, progress=False, threads=True
    )


def download_prices(tickers: list, start: date, end: date) -> dict:
    """Download OHLCV for all tickers. Returns {ticker: DataFrame}."""
    log.info(f"Downloading price data for {len(tickers)} tickers: {start} to {end}...")

    start_str = str(start - timedelta(days=90))
    end_str   = str(end   + timedelta(days=5))

    # Download in batches of 200 to avoid yfinance memory/timeout issues.
    # Each batch runs in its own thread with a hard 120-second wall-clock timeout
    # so a frozen batch never stalls the whole run.
    result = {}
    batch_size = 200
    batches = [tickers[i:i+batch_size] for i in range(0, len(tickers), batch_size)]

    for i, batch in enumerate(batches):
        log.info(f"  Batch {i+1}/{len(batches)} ({len(batch)} tickers)...")
        raw = None
        for attempt in range(1, 4):          # up to 3 attempts per batch
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(_download_one_batch, batch, start_str, end_str)
                    raw = future.result(timeout=120)   # hard 120-second deadline
                break                                  # success → stop retrying
            except concurrent.futures.TimeoutError:
                log.warning(f"  Batch {i+1} attempt {attempt} timed out, retrying…")
            except Exception as e:
                log.warning(f"  Batch {i+1} attempt {attempt} error: {e}, retrying…")
            time.sleep(3)

        if raw is None or (hasattr(raw, 'empty') and raw.empty):
            log.warning(f"  Batch {i+1} gave no data after 3 attempts, skipping")
            time.sleep(2)
            continue

        if isinstance(raw.columns, pd.MultiIndex):
            for ticker in batch:
                try:
                    df = raw.xs(ticker, level=1, axis=1).dropna(how="all")
                    if len(df) >= 30:
                        result[ticker] = df
                except Exception:
                    pass
        else:
            # Single ticker returned
            if len(raw) >= 30:
                result[batch[0]] = raw

        time.sleep(1)  # polite rate-limit between batches

    log.info(f"Downloaded {len(result)} tickers with sufficient history")
    return result


# ── Scoring logic (mirrors live_scanner.py) ────────────────────────────────────
def compute_ema(series: pd.Series, period: int) -> float:
    return float(series.ewm(span=period, adjust=False).mean().iloc[-1])


def score_stock_historical(ticker: str, df: pd.DataFrame, as_of: date) -> dict | None:
    """Score a stock using only data available up to as_of date."""
    try:
        # Slice to as_of date
        df = df[df.index.date <= as_of].copy()
        if len(df) < 30:
            return None

        close  = df["Close"]
        high   = df["High"]
        low    = df["Low"]
        volume = df["Volume"]
        price  = float(close.iloc[-1])

        # Quality gate
        if price < 15:
            return None
        avg_vol = float(volume.iloc[-20:].mean())
        if avg_vol * price < 10_000_000:
            return None

        # EMAs
        e10  = compute_ema(close, 10)
        e20  = compute_ema(close, 20)
        e50  = compute_ema(close, 50)
        e200 = compute_ema(close, 200) if len(df) >= 200 else None

        ema_stack = "none"
        if price > e10 > e20 > e50:
            ema_stack = "full"
        elif price > e20 > e50:
            ema_stack = "partial"
        elif price > e50:
            ema_stack = "weak"

        # True Range + ATR EMA series
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        atr_ema = tr.ewm(span=14, adjust=False).mean()
        atr14   = float(atr_ema.iloc[-1])

        # ATR as % of price — used only for flag threshold checks
        atr_pct = round(atr14 / price, 4) if price > 0 else 1.0

        # ATR compression ratio: recent (last 5 bars) vs prior (bars -25..-10)
        # Values <1.0 mean the stock is coiling; lower = tighter base
        if len(atr_ema) >= 25:
            atr_recent = float(atr_ema.iloc[-5:].mean())
            atr_hist   = float(atr_ema.iloc[-25:-10].mean())
            atr_c = round(atr_recent / atr_hist, 2) if atr_hist > 0 else 1.0
        else:
            atr_c = 1.0  # not enough history — treat as no compression
        # Expose atr_c clamped for storage
        atr_c = min(atr_c, 2.0)

        # Volume contraction: last 8 bars vs prior 17 (bars -25..-8)
        avg8  = float(volume.iloc[-8:].mean())
        avg25_ref = float(volume.iloc[-25:-8].mean()) if len(volume) >= 25 else float(volume.mean())
        vol_c = round(avg8 / avg25_ref, 2) if avg25_ref > 0 else 1.0

        # Volume ratio (today vs 20-day avg — kept for display)
        avg20 = float(volume.iloc[-20:].mean())
        vol_ratio = round(float(volume.iloc[-1]) / avg20, 2) if avg20 > 0 else 1.0

        # Distance to 52-week high (proximity to key level)
        h52  = float(high.iloc[-252:].max()) if len(high) >= 252 else float(high.max())
        dist = round((h52 - price) / price * 100, 2) if h52 > 0 else 0.0
        if   dist <= 1:   level = "ATH"
        elif dist <= 5:   level = "multi-year high"
        elif dist <= 15:  level = "52-week high"
        else:             level = "prior resistance"

        # HH/HL structure (last 20 bars)
        bars = min(20, len(df))
        hh_count = sum(
            1 for i in range(1, bars)
            if float(high.iloc[-bars+i]) > float(high.iloc[-bars+i-1])
            and float(low.iloc[-bars+i]) > float(low.iloc[-bars+i-1])
        )
        hh_hl = round(hh_count / (bars - 1), 2) if bars > 1 else 0.0

        # Momentum
        mom1m = round((price - float(close.iloc[-21])) / float(close.iloc[-21]) * 100, 1) \
                if len(close) >= 21 else 0.0
        mom3m = round((price - float(close.iloc[-63])) / float(close.iloc[-63]) * 100, 1) \
                if len(close) >= 63 else 0.0

        # Pre-breakout / bull flag (use atr_pct for absolute tightness check)
        pre_breakout = (atr_pct <= 0.03 and vol_c <= 0.7 and dist <= 5
                        and ema_stack in ("full", "partial"))
        bull_flag    = (atr_pct <= 0.025 and vol_c <= 0.65 and mom1m >= 8
                        and ema_stack in ("full", "partial"))

        # ── v2_base_setup scoring ─────────────────────────────────────────────
        # Designed to surface stocks in a tight base near a key level
        # after a prior move — the Qullamaggie "buyable" pattern.
        #
        # Component breakdown (max = 95):
        #   EMA structure      18   (trend direction / table stakes)
        #   HH/HL structure    10   (orderly consolidation structure)
        #   ATR compression    20   (tight coiling — key signal)
        #   Distance to level  18   (near a pivot = low-risk entry)
        #   Volume contraction 12   (institutions quietly accumulating)
        #   3M prior momentum  10   (prior move before base)
        #   Pre-breakout flag   4   (all-of-the-above tightness bonus)
        #   Bull-flag flag      3   (momentum + tight base combo)
        #                    ----
        #                      95
        # ─────────────────────────────────────────────────────────────────────
        score = 0

        # EMA structure (18 pts)
        if   ema_stack == "full":    score += 18
        elif ema_stack == "partial": score += 11
        elif ema_stack == "weak":    score += 5

        # HH/HL structure (10 pts)
        if   hh_hl >= 0.85: score += 10
        elif hh_hl >= 0.70: score += 7
        elif hh_hl >= 0.55: score += 3

        # ATR compression ratio (20 pts) — lower ratio = tighter coil
        if   atr_c <= 0.65: score += 20
        elif atr_c <= 0.75: score += 15
        elif atr_c <= 0.85: score += 9
        elif atr_c <= 0.95: score += 4

        # Distance to 52-week high / key level (18 pts)
        if   dist <= 1:  score += 18
        elif dist <= 3:  score += 14
        elif dist <= 6:  score += 9
        elif dist <= 10: score += 4
        elif dist <= 15: score += 1

        # Volume contraction (12 pts)
        if   vol_c <= 0.50: score += 12
        elif vol_c <= 0.65: score += 8
        elif vol_c <= 0.80: score += 4

        # 3-month prior momentum (10 pts) — prior move before base
        if   mom3m >= 30: score += 10
        elif mom3m >= 15: score += 7
        elif mom3m >= 5:  score += 3
        elif mom3m < -5:  score -= 5   # downtrend penalty

        # Setup flags (4 + 3 pts)
        if pre_breakout: score += 4
        if bull_flag:    score += 3

        score = min(score, 95)  # hard cap

        status = "READY" if score >= 72 else "WATCH" if score >= 55 else "BUILDING"

        return {
            "ticker":           ticker,
            "scan_date":        as_of.isoformat(),
            "price_at_scan":    round(price, 2),
            "score":            score,
            "status":           status,
            "track":            "BREAKOUT",
            "scoring_version":  SCORING_VERSION,
            "ema_stack":        ema_stack,
            "atr":              atr_c,        # compression ratio (v2: <1 = tight)
            "atr_pct":          atr_pct,      # ATR as % of price (for reference)
            "vol_contraction":  vol_c,
            "vol_ratio":        vol_ratio,
            "level":            level,
            "dist_to_level":    dist,
            "hh_hl":            hh_hl,
            "momentum_1m":      mom1m,
            "momentum_3m":      mom3m,
            "pre_breakout":     pre_breakout,
            "bull_flag":        bull_flag,
            "rs_percentile":    None,
            "returns":          {}
        }
    except Exception as e:
        return None


# ── Forward returns ────────────────────────────────────────────────────────────
RETURN_WINDOWS = {
    "1w":  5,
    "2w":  10,
    "1m":  21,
    "2m":  42,
    "3m":  63,
    "6m":  126,
    "1y":  252,
}

def compute_returns(price_at_scan: float, ticker: str,
                    df: pd.DataFrame, scan_date: date) -> dict:
    """Compute forward returns from scan_date for all windows."""
    returns = {}
    future_df = df[df.index.date > scan_date]
    
    for label, n_days in RETURN_WINDOWS.items():
        if len(future_df) >= n_days:
            future_price = float(future_df["Close"].iloc[n_days - 1])
            ret = round((future_price - price_at_scan) / price_at_scan * 100, 2)
            returns[label] = ret
        # else: not enough future data yet, leave blank

    return returns


# ── Main backtest runner ───────────────────────────────────────────────────────
def run_backtest(n_days: int = 30, specific_date: date = None, experiment: str = None):
    """
    Run the historical backtest.

    experiment : str | None
        If provided, results are written to
          /scanner/experiments/{experiment}/history/{date}/{ticker}
        instead of /scanner/history. Experiment metadata (scoring version,
        date range, status) is saved to /scanner/experiments/{experiment}/meta.
        first_seen is NOT updated during experiment runs — only production
        runs touch that path.
        Use this to test scoring logic changes before promoting to production.
    """
    if experiment:
        write_ref = db.reference(f"/scanner/experiments/{experiment}/history")
        meta_ref  = db.reference(f"/scanner/experiments/{experiment}/meta")
        meta_ref.set({
            "created_at":      datetime.now().isoformat(),
            "scoring_version": SCORING_VERSION,
            "n_days":          n_days,
            "specific_date":   specific_date.isoformat() if specific_date else None,
            "status":          "running",
        })
        log.info(f"=== EXPERIMENT BACKTEST: {experiment} (scoring={SCORING_VERSION}) ===")
    else:
        write_ref = hist_ref
        log.info(f"=== BACKTEST START: {n_days} trading days (scoring={SCORING_VERSION}) ===")

    t_total = time.time()

    # Get trading dates (skip weekends)
    end_date   = date.today()
    all_dates  = []
    d = end_date - timedelta(days=1)
    while len(all_dates) < n_days:
        if d.weekday() < 5:  # Mon-Fri
            all_dates.append(d)
        d -= timedelta(days=1)
    all_dates.reverse()

    if specific_date:
        all_dates = [specific_date]

    log.info(f"Backtest dates: {all_dates[0]} to {all_dates[-1]} ({len(all_dates)} days)")

    # Get universe
    tickers = get_universe()
    if not tickers:
        log.error("No tickers — aborting")
        return

    # Download all price history at once (more efficient than per-day)
    earliest = all_dates[0] - timedelta(days=300)  # need 252 days of history
    latest   = date.today()
    prices   = download_prices(tickers, earliest, latest)

    log.info(f"Price data ready for {len(prices)} tickers")

    # Get existing first_seen data
    existing_first = first_ref.get() or {}

    # Process each day
    for day in all_dates:
        log.info(f"\n--- Processing {day} ---")
        day_t = time.time()

        # Check if already done (skip for experiments — always re-run)
        if not experiment:
            existing = hist_ref.child(day.isoformat()).get()
            if existing and len(existing) > 50:
                log.info(f"  Already have {len(existing)} records for {day}, skipping")
                continue

        # Score all stocks as of this day
        results = []
        for ticker, df in prices.items():
            r = score_stock_historical(ticker, df, day)
            if r:
                results.append(r)

        if not results:
            log.warning(f"  No results for {day}")
            continue

        # Assign RS percentiles
        scores = [r["score"] for r in results]
        for r in results:
            r["rs_percentile"] = round(
                sum(1 for s in scores if s < r["score"]) / len(scores) * 100, 1
            )

        # Sort and take top 200
        results.sort(key=lambda x: x["score"], reverse=True)
        top200 = results[:200]

        # Compute forward returns for each pick
        for r in top200:
            ticker = r["ticker"]
            if ticker in prices:
                r["returns"] = compute_returns(
                    r["price_at_scan"], ticker, prices[ticker], day
                )

        # Write to Firebase (experiment path or production)
        day_str = day.isoformat()
        write_ref.child(day_str).set({r["ticker"]: r for r in top200})

        # Update first_seen — production only
        new_first = {}
        if not experiment:
            for r in top200:
                t = r["ticker"]
                if t not in existing_first:
                    new_first[t] = {
                        "date":  day_str,
                        "price": r["price_at_scan"],
                        "score": r["score"],
                    }
                    existing_first[t] = new_first[t]
            if new_first:
                first_ref.update(new_first)

        elapsed = round(time.time() - day_t, 1)
        seen_msg = f", {len(new_first)} new first-seen" if not experiment else ""
        log.info(f"  {day}: {len(top200)} picks stored{seen_msg} | {elapsed}s")

    total_elapsed = round((time.time() - t_total) / 60, 1)

    if experiment:
        meta_ref.update({"status": "complete", "completed_at": datetime.now().isoformat()})
        log.info(f"\n=== EXPERIMENT COMPLETE in {total_elapsed} min ===")
        log.info(f"Analyze results:  python optimizer.py --experiment {experiment}")
        log.info(f"Compare vs prod:  python optimizer.py --compare {experiment}")
    else:
        log.info(f"\n=== BACKTEST COMPLETE in {total_elapsed} min ===")
        log.info("Now run: python backtest.py --update-returns  (to fill in forward returns)")


def update_all_returns():
    """
    Update forward returns for all historical picks.
    Run this daily — it fills in returns as time passes.
    """
    log.info("Updating forward returns for all historical picks...")
    history = hist_ref.get() or {}
    
    # Download current prices for all tickers we've ever seen
    all_tickers = set()
    for day_data in history.values():
        if isinstance(day_data, dict):
            all_tickers.update(day_data.keys())
    
    log.info(f"Fetching current prices for {len(all_tickers)} tickers...")
    prices = download_prices(list(all_tickers), 
                             date.today() - timedelta(days=400), 
                             date.today())

    updates = 0
    for day_str, day_data in history.items():
        if not isinstance(day_data, dict):
            continue
        scan_date = date.fromisoformat(day_str)
        
        for ticker, pick in day_data.items():
            if not isinstance(pick, dict):
                continue
            if ticker not in prices:
                continue
            
            price_at_scan = pick.get("price_at_scan")
            if not price_at_scan:
                continue
            
            new_returns = compute_returns(
                price_at_scan, ticker, prices[ticker], scan_date
            )
            
            # Only update if we have new windows
            existing = pick.get("returns", {})
            added = {k: v for k, v in new_returns.items() if k not in existing}
            if added:
                hist_ref.child(day_str).child(ticker).child("returns").update(added)
                updates += 1

    log.info(f"Updated returns for {updates} picks")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scanner backtest engine")
    parser.add_argument("--days",       type=int, default=30,
                        help="Number of trading days to backtest (default: 30)")
    parser.add_argument("--date",       type=str, default=None,
                        help="Backtest a single specific date (YYYY-MM-DD)")
    parser.add_argument("--update-returns", action="store_true",
                        help="Only update forward returns, don't rerun backtest")
    parser.add_argument("--experiment", type=str, default=None,
                        help=(
                            "Run as an experiment — results go to "
                            "/scanner/experiments/{NAME}/history instead of production. "
                            "Use this to test scoring changes before promoting to main. "
                            "Example: --experiment v2_momentum_reweight"
                        ))
    args = parser.parse_args()

    if args.update_returns:
        update_all_returns()
    else:
        specific = date.fromisoformat(args.date) if args.date else None
        run_backtest(n_days=args.days, specific_date=specific, experiment=args.experiment)
