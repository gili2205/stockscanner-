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

import os, sys, time, json, logging, argparse, gc
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
SCORING_VERSION = "v5_ema_gate_only"

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
    """Run yf.download for one batch — called inside a thread so we can time it out.
    threads=False avoids yfinance spawning internal threads that can't be cleaned up."""
    return yf.download(
        batch, start=start_str, end=end_str,
        auto_adjust=True, progress=False, threads=False
    )


PRICE_CACHE_PATH = Path("/home/scanner/.price_cache.pkl")
PRICE_CACHE_MAX_AGE_HOURS = 12


def download_prices(tickers: list, start: date, end: date) -> dict:
    """
    Download OHLCV for all tickers. Returns {ticker: DataFrame}.
    Caches result to disk so VM restarts don't trigger a full re-download.

    Cache key uses ISO week (not exact date) so it stays stable across daily
    restarts within the same week.  The cache is written incrementally after
    every batch so a crash/restart can resume from where it left off rather
    than re-downloading from scratch.
    """
    import pickle, os as _os

    start_str = str(start - timedelta(days=90))
    # Key = ticker count + start date only. No week/date suffix — week rollover
    # was causing daily cache misses. Freshness is enforced by file mtime instead.
    cache_key = f"{len(tickers)}_{start_str}"

    batch_size = 25
    batches = [tickers[i:i+batch_size] for i in range(0, len(tickers), batch_size)]
    # end_str only needed for yfinance calls
    end_str = str(end + timedelta(days=5))

    # ── Try loading from disk cache (full or partial) ─────────────────────────
    result       = {}
    resume_from  = 0   # batch index to start/resume from

    if PRICE_CACHE_PATH.exists():
        # Expire cache if older than PRICE_CACHE_MAX_AGE_HOURS
        age_hours = (_os.path.getmtime(PRICE_CACHE_PATH) - 0) / 3600
        age_hours = (time.time() - _os.path.getmtime(PRICE_CACHE_PATH)) / 3600
        if age_hours > PRICE_CACHE_MAX_AGE_HOURS:
            log.info(f"Cache expired ({age_hours:.1f}h old) — starting fresh download")
            try: PRICE_CACHE_PATH.unlink()
            except Exception: pass
        else:
            try:
                with open(PRICE_CACHE_PATH, "rb") as f:
                    cached = pickle.load(f)
                if cached.get("key") == cache_key:
                    result = cached.get("data", {})
                    if cached.get("complete"):
                        log.info(f"Loaded {len(result)} tickers from complete disk cache ({age_hours:.1f}h old)")
                        return result
                    else:
                        resume_from = cached.get("batches_done", 0)
                        log.info(f"Resuming from batch {resume_from+1}/{len(batches)} "
                                 f"({len(result)} tickers already cached, {age_hours:.1f}h old)")
                else:
                    stored_key = cached.get("key", "?")
                    log.info(f"Cache key mismatch (stored={stored_key}, want={cache_key}) — starting fresh")
            except Exception as e:
                log.warning(f"Cache load failed ({e}) — deleting corrupt cache and starting fresh")
                try: PRICE_CACHE_PATH.unlink()
                except Exception: pass
                result = {}
                resume_from = 0

    # ── Download remaining batches ────────────────────────────────────────────
    if resume_from == 0:
        log.info(f"Downloading price data for {len(tickers)} tickers: {start} to {end}...")
    else:
        log.info(f"Continuing download: batches {resume_from+1}–{len(batches)}")

    for i, batch in enumerate(batches):
        if i < resume_from:
            continue   # already in cache

        log.info(f"  Batch {i+1}/{len(batches)} ({len(batch)} tickers)...")
        raw = None
        for attempt in range(1, 4):
            # NOTE: Do NOT use "with ThreadPoolExecutor() as ex" here.
            # The context manager calls shutdown(wait=True) on exit, which blocks
            # until the hung yfinance thread finishes — defeating the timeout.
            # Instead, we shut down with wait=False to abandon hung threads.
            ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                future = ex.submit(_download_one_batch, batch, start_str, end_str)
                raw = future.result(timeout=90)   # 90s per batch (25 tickers)
                ex.shutdown(wait=False)
                break
            except concurrent.futures.TimeoutError:
                ex.shutdown(wait=False)   # abandon hung thread, don't block
                log.warning(f"  Batch {i+1} attempt {attempt} timed out, retrying…")
            except Exception as e:
                ex.shutdown(wait=False)
                log.warning(f"  Batch {i+1} attempt {attempt} error: {e}, retrying…")
            time.sleep(5)

        if raw is None or (hasattr(raw, 'empty') and raw.empty):
            log.warning(f"  Batch {i+1} gave no data after 3 attempts, skipping")
            time.sleep(2)
        elif isinstance(raw.columns, pd.MultiIndex):
            for ticker in batch:
                try:
                    df = raw.xs(ticker, level=1, axis=1).dropna(how="all")
                    if len(df) >= 30:
                        result[ticker] = df
                except Exception:
                    pass
        else:
            if len(raw) >= 30:
                result[batch[0]] = raw

        # ── Incremental save after every batch (atomic write) ────────────────
        # Write to .tmp then rename — rename is atomic on Linux so a kill
        # mid-write never corrupts the cache file.
        is_last = (i == len(batches) - 1)
        tmp_path = PRICE_CACHE_PATH.with_suffix(".tmp")
        try:
            with open(tmp_path, "wb") as f:
                pickle.dump({
                    "key":          cache_key,
                    "complete":     is_last,
                    "batches_done": i + 1,
                    "data":         result,
                }, f)
            tmp_path.replace(PRICE_CACHE_PATH)   # atomic
        except Exception as e:
            log.warning(f"  Incremental cache save failed: {e}")
            try: tmp_path.unlink()
            except Exception: pass

        time.sleep(1)

    log.info(f"Downloaded {len(result)} tickers with sufficient history")
    return result


# ── Scoring logic (mirrors live_scanner.py) ────────────────────────────────────
def compute_ema(series: pd.Series, period: int) -> float:
    return float(series.ewm(span=period, adjust=False).mean().iloc[-1])

def compute_rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(span=period, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(span=period, adjust=False).mean()
    rs    = gain.iloc[-1] / max(float(loss.iloc[-1]), 1e-10)
    return round(100 - 100 / (1 + rs), 1)


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

        # ── Base signals ──────────────────────────────────────────────
        e10 = compute_ema(close, 10)
        e20 = compute_ema(close, 20)
        e50 = compute_ema(close, 50)
        ema_stack = ("full"    if price > e10 > e20 > e50 else
                     "partial" if e10 > e20             else "weak")

        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        atr_ema = tr.ewm(span=14, adjust=False).mean()
        atr14   = float(atr_ema.iloc[-1])
        atr_pct = round(atr14 / price, 4) if price > 0 else 1.0

        # ATR compression ratio (recent vs historical)
        if len(atr_ema) >= 25:
            atr_c = round(float(atr_ema.iloc[-5:].mean()) /
                          float(atr_ema.iloc[-25:-10].mean()), 2)
        else:
            atr_c = 1.0
        atr_c = min(atr_c, 2.0)

        # Volume contraction (8-day vs prior 17-day reference)
        avg8      = float(volume.iloc[-8:].mean())
        avg25_ref = float(volume.iloc[-25:-8].mean()) if len(volume) >= 25 else float(volume.mean())
        vol_c     = round(avg8 / avg25_ref, 2) if avg25_ref > 0 else 1.0
        avg20     = float(volume.iloc[-20:].mean())
        vol_ratio = round(float(volume.iloc[-1]) / avg20, 2) if avg20 > 0 else 1.0

        # Distance to 52-week high
        h52  = float(high.iloc[-252:].max()) if len(high) >= 252 else float(high.max())
        dist = round((h52 - price) / price * 100, 2) if h52 > 0 else 0.0
        level = ("ATH"            if dist <= 1  else
                 "multi-year high" if dist <= 5  else
                 "52-week high"    if dist <= 15 else "prior resistance")

        # HH/HL (last 20 bars)
        bars     = min(20, len(df))
        hh_count = sum(1 for i in range(1, bars)
                       if float(high.iloc[-bars+i]) > float(high.iloc[-bars+i-1])
                       and float(low.iloc[-bars+i])  > float(low.iloc[-bars+i-1]))
        hh_hl = round(hh_count / (bars - 1), 2) if bars > 1 else 0.0

        # Momentum
        mom1m = round((price / float(close.iloc[-21]) - 1) * 100, 1) if len(close) >= 21 else 0.0
        mom3m = round((price / float(close.iloc[-63]) - 1) * 100, 1) if len(close) >= 63 else mom1m

        # RSI (14)
        rsi14 = compute_rsi(close)

        # Flags
        pre_breakout = (atr_pct <= 0.03 and vol_c <= 0.7 and dist <= 5
                        and ema_stack in ("full", "partial"))
        bull_flag    = (atr_pct <= 0.025 and vol_c <= 0.65 and mom1m >= 8
                        and ema_stack in ("full", "partial"))

        avg_dollar_vol = avg_vol * price

        # ════════════════════════════════════════════════════════════════
        # LAYER 1 — TECHNICAL (0-100)
        # ════════════════════════════════════════════════════════════════
        ta = 0
        if   ema_stack == "full":    ta += 25
        elif ema_stack == "partial": ta += 15
        elif ema_stack == "weak":    ta += 5

        if   hh_hl >= 0.85: ta += 12
        elif hh_hl >= 0.70: ta += 8
        elif hh_hl >= 0.55: ta += 4

        if   atr_c <= 0.20: ta += 20
        elif atr_c <= 0.25: ta += 15
        elif atr_c <= 0.30: ta += 10
        elif atr_c <= 0.40: ta += 5

        if   vol_c <= 0.50: ta += 15
        elif vol_c <= 0.65: ta += 10
        elif vol_c <= 0.80: ta += 5

        if   dist <= 1.0: ta += 20
        elif dist <= 2.0: ta += 16
        elif dist <= 3.5: ta += 11
        elif dist <= 6.0: ta += 5
        elif dist <= 10:  ta += 1

        if   avg_dollar_vol >= 200_000_000: ta += 8
        elif avg_dollar_vol >= 50_000_000:  ta += 6
        elif avg_dollar_vol >= 20_000_000:  ta += 4
        else:                               ta += 2

        if ema_stack == "weak":         ta = max(0, ta - 18)
        if dist > 15:                   ta = max(0, ta - 12)
        if mom1m < -5:                  ta = max(0, ta - 10)
        if atr_c > 0.7 and mom1m < 10: ta = max(0, ta - 8)

        score_technical = min(100, ta)

        # ════════════════════════════════════════════════════════════════
        # LAYER 2 — FUNDAMENTAL (0-100)
        # NOTE: backtest has no fundamental data from yfinance per-date,
        # so this layer is estimated from price-derived signals only.
        # It will be 0 for most stocks — the live scanner fills it in.
        # ════════════════════════════════════════════════════════════════
        score_fundamental = 0   # no per-date fundamental data in backtest

        # ════════════════════════════════════════════════════════════════
        # LAYER 3 — CATALYST (0-100)
        # ════════════════════════════════════════════════════════════════
        ca = 0
        if   mom1m >= 30: ca += 25
        elif mom1m >= 15: ca += 18
        elif mom1m >= 8:  ca += 10
        elif mom1m >= 3:  ca += 5

        if   vol_ratio >= 5.0: ca += 15
        elif vol_ratio >= 3.0: ca += 10
        elif vol_ratio >= 2.0: ca += 5

        if mom3m < -30: ca = max(0, ca - 20)

        score_catalyst = min(100, ca)

        # ── Default blend (50% tech / 30% fund / 20% catalyst) ───────
        score  = round(0.50 * score_technical + 0.30 * score_fundamental + 0.20 * score_catalyst)
        track  = "CATALYST" if score_catalyst > score_technical else "BREAKOUT"
        status = "READY" if score >= 72 else "WATCH" if score >= 55 else "BUILDING"

        # ════════════════════════════════════════════════════════════════
        # NEW: Quality / Setup / Buy-Now scores
        # RS percentile not available per-date in backtest (requires
        # cross-stock comparison). Proxied from 3M momentum bucket.
        # ════════════════════════════════════════════════════════════════
        rs_proxy = 85 if mom3m >= 40 else 70 if mom3m >= 20 else 55 if mom3m >= 5 else 35

        q = 0
        q += 30 if rs_proxy >= 90 else 22 if rs_proxy >= 80 else 14 if rs_proxy >= 70 else 7 if rs_proxy >= 60 else 0
        q += 12 if ema_stack == "full" else 7 if ema_stack == "partial" else 2 if ema_stack == "weak" else 0
        q += 13 if mom1m >= 20 else 10 if mom1m >= 10 else 6 if mom1m >= 5 else 2 if mom1m >= 0 else 0
        q += 13 if mom3m >= 40 else 9 if mom3m >= 20 else 5 if mom3m >= 8 else 1 if mom3m >= 0 else 0
        q += 10 if hh_hl >= 0.85 else 7 if hh_hl >= 0.70 else 4 if hh_hl >= 0.55 else 0
        # score_fundamental = 0 in backtest; no per-date fundamental data
        q += 10 if avg_dollar_vol >= 200e6 else 7 if avg_dollar_vol >= 50e6 else 4 if avg_dollar_vol >= 20e6 else 2
        score_quality = min(100, q)

        t = 0
        t += 20 if atr_c <= 0.15 else 15 if atr_c <= 0.25 else 10 if atr_c <= 0.35 else 3 if atr_c <= 0.50 else 0
        t += 18 if vol_c <= 0.50 else 12 if vol_c <= 0.65 else 6 if vol_c <= 0.80 else 0
        t += 14 if dist <= 1.0 else 10 if dist <= 2.0 else 6 if dist <= 3.5 else 2 if dist <= 6.0 else 0
        t += 8  if hh_hl >= 0.85 else 5 if hh_hl >= 0.70 else 2 if hh_hl >= 0.55 else 0
        t += 8  if rsi14 <= 55 else 6 if rsi14 <= 65 else 3 if rsi14 <= 75 else 0
        t += 7  if vol_ratio >= 3.0 else 4 if vol_ratio >= 2.0 else 2 if vol_ratio >= 1.5 else 0
        t += 5  if pre_breakout else 4 if bull_flag else 0
        # days_to_earnings not available in backtest — no earnings penalty
        score_setup    = min(100, max(0, t))
        score_buy_now  = round((score_quality * score_setup) ** 0.5)

        if score < 25:
            return None

        return {
            "ticker":            ticker,
            "scan_date":         as_of.isoformat(),
            "price_at_scan":     round(price, 2),
            "score":             score,
            "score_technical":   score_technical,
            "score_fundamental": score_fundamental,
            "score_catalyst":    score_catalyst,
            "status":            status,
            "track":             track,
            "scoring_version":   SCORING_VERSION,
            "ema_stack":         ema_stack,
            "atr":               atr_c,
            "atr_pct":           atr_pct,
            "vol_contraction":   vol_c,
            "vol_ratio":         vol_ratio,
            "level":             level,
            "dist_to_level":     dist,
            "hh_hl":             hh_hl,
            "momentum_1m":       mom1m,
            "momentum_3m":       mom3m,
            "pre_breakout":      pre_breakout,
            "bull_flag":         bull_flag,
            "rs_percentile":     None,
            "rsi":               rsi14,
            "score_quality":     score_quality,
            "score_setup":       score_setup,
            "score_buy_now":     score_buy_now,
            "returns":           {}
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
def run_backtest(n_days: int = None, specific_date: date = None, experiment: str = None):
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

        When experiment is set and n_days is None (the default), the backtest
        automatically reads all dates present in production /scanner/history
        and scores those exact same dates — so the comparison is always
        apples-to-apples against v1 production data.
    """
    if experiment:
        write_ref = db.reference(f"/scanner/experiments/{experiment}/history")
        meta_ref  = db.reference(f"/scanner/experiments/{experiment}/meta")
        log.info(f"=== EXPERIMENT BACKTEST: {experiment} (scoring={SCORING_VERSION}) ===")
    else:
        write_ref = hist_ref
        log.info(f"=== BACKTEST START: {n_days or 30} trading days (scoring={SCORING_VERSION}) ===")

    t_total = time.time()

    # Determine which dates to process
    if specific_date:
        all_dates = [specific_date]
    elif experiment and n_days is None:
        # Mirror production history dates exactly
        log.info("Experiment mode: reading production history dates from Firebase...")
        prod_history = hist_ref.get() or {}
        all_dates = sorted(
            date.fromisoformat(d) for d in prod_history.keys()
            if isinstance(prod_history[d], dict) and len(prod_history[d]) > 0
        )
        if not all_dates:
            log.error("No production history dates found — run backtest.py without --experiment first")
            return
        log.info(f"Found {len(all_dates)} dates in production history "
                 f"({all_dates[0]} → {all_dates[-1]})")
    else:
        # Standard n_days rolling window
        days = n_days or 30
        end_date  = date.today()
        all_dates = []
        d = end_date - timedelta(days=1)
        while len(all_dates) < days:
            if d.weekday() < 5:
                all_dates.append(d)
            d -= timedelta(days=1)
        all_dates.reverse()

    if experiment:
        meta_ref.set({
            "created_at":      datetime.now().isoformat(),
            "scoring_version": SCORING_VERSION,
            "n_days":          len(all_dates),
            "specific_date":   specific_date.isoformat() if specific_date else None,
            "mirrored_prod":   (n_days is None and specific_date is None),
            "status":          "running",
        })

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

    def fb_write(ref, data, retries=4, label="Firebase write"):
        """Write to Firebase with retries — network blips won't crash the run."""
        for attempt in range(1, retries + 1):
            try:
                ref.set(data)
                return True
            except Exception as e:
                log.warning(f"  {label} attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    time.sleep(5 * attempt)
        log.error(f"  {label} failed after {retries} attempts — skipping")
        return False

    # Process each day
    days_done = 0
    days_failed = 0
    for day in all_dates:
        log.info(f"\n--- Processing {day} ({days_done+1}/{len(all_dates)}) ---")
        day_t = time.time()

        try:
            # Skip dates already processed (works for both production and experiments)
            day_str  = day.isoformat()
            check_ref = write_ref.child(day_str)
            try:
                existing = check_ref.get()
            except Exception as e:
                log.warning(f"  Could not check existing data: {e} — processing anyway")
                existing = None
            if existing and len(existing) > 50:
                log.info(f"  Already have {len(existing)} records for {day}, skipping")
                days_done += 1
                continue

            # Score all stocks as of this day
            results = []
            for ticker, df in prices.items():
                try:
                    r = score_stock_historical(ticker, df, day)
                    if r:
                        results.append(r)
                except Exception as e:
                    log.debug(f"  score_stock_historical({ticker}) failed: {e}")

            if not results:
                log.warning(f"  No results for {day}")
                days_done += 1
                continue

            # Assign RS percentiles (cross-sectional rank on this day)
            scores = [r["score"] for r in results]
            n = len(scores)
            for r in results:
                r["rs_percentile"] = round(
                    sum(1 for s in scores if s < r["score"]) / n * 100, 1
                )

            # Sort and take top 200
            results.sort(key=lambda x: x["score"], reverse=True)
            top200 = results[:200]

            # Compute forward returns for each pick
            for r in top200:
                ticker = r["ticker"]
                if ticker in prices:
                    try:
                        r["returns"] = compute_returns(
                            r["price_at_scan"], ticker, prices[ticker], day
                        )
                    except Exception:
                        r["returns"] = {}

            # Write to Firebase — with retry so a blip doesn't kill the run
            fb_write(check_ref, {r["ticker"]: r for r in top200},
                     label=f"day {day_str}")

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
                    try:
                        first_ref.update(new_first)
                    except Exception as e:
                        log.warning(f"  first_seen update failed: {e}")

            days_done += 1
            elapsed = round(time.time() - day_t, 1)
            seen_msg = f", {len(new_first)} new first-seen" if not experiment else ""
            log.info(f"  {day}: {len(top200)} picks stored{seen_msg} | {elapsed}s "
                     f"[{days_done}/{len(all_dates)} done]")

            # Free day-local objects to keep memory flat across days
            del results, top200, scores
            gc.collect()

            # Periodic meta update so we can see progress in Firebase
            if experiment and days_done % 10 == 0:
                try:
                    meta_ref.update({"days_done": days_done,
                                     "last_date": day_str,
                                     "updated_at": datetime.now().isoformat()})
                except Exception:
                    pass

        except KeyboardInterrupt:
            log.info(f"\nInterrupted after {days_done} days. "
                     f"Re-run same command to resume — already-written days are skipped.")
            if experiment:
                try:
                    meta_ref.update({"status": "interrupted", "days_done": days_done,
                                     "last_date": day.isoformat()})
                except Exception:
                    pass
            raise

        except Exception as e:
            days_failed += 1
            log.error(f"  Day {day} failed unexpectedly: {e} — continuing to next day")
            if days_failed >= 10:
                log.error("10 consecutive-ish day failures — aborting run")
                break
            continue

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
    parser.add_argument("--days",       type=int, default=None,
                        help="Number of trading days to backtest (default: 30, or mirrors "
                             "production history when --experiment is used without --days)")
    parser.add_argument("--date",       type=str, default=None,
                        help="Backtest a single specific date (YYYY-MM-DD)")
    parser.add_argument("--update-returns", action="store_true",
                        help="Only update forward returns, don't rerun backtest")
    parser.add_argument("--experiment", type=str, default=None,
                        help=(
                            "Run as an experiment — results go to "
                            "/scanner/experiments/{NAME}/history instead of production. "
                            "Use this to test scoring changes before promoting to main. "
                            "Example: --experiment v4_quality_setup"
                        ))
    parser.add_argument("--delete-experiment", type=str, default=None, metavar="NAME",
                        help="Delete all Firebase data for an experiment and exit. "
                             "Example: --delete-experiment v3_three_layer")
    args = parser.parse_args()

    if args.delete_experiment:
        name = args.delete_experiment
        log.info(f"Deleting experiment '{name}' from Firebase...")
        ref = db.reference(f"/scanner/experiments/{name}")
        existing = ref.get()
        if existing is None:
            log.warning(f"Experiment '{name}' not found in Firebase — nothing to delete.")
        else:
            ref.delete()
            log.info(f"Deleted /scanner/experiments/{name} ✓")
    elif args.update_returns:
        update_all_returns()
    else:
        specific = date.fromisoformat(args.date) if args.date else None
        n = args.days if args.days else (30 if not args.experiment else None)
        run_backtest(n_days=n, specific_date=specific, experiment=args.experiment)
