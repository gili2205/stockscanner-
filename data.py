"""
Data download and universe management.
Fetches NASDAQ tickers from SEC EDGAR and price data from yfinance.
Implements disk caching with TTL to avoid re-downloading on every run.
"""

import json
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

from config import (
    CACHE_DIR, MIN_PRICE, MIN_AVG_VOLUME, VOLUME_AVG_PERIOD,
    PRICE_HISTORY_PERIOD, DOWNLOAD_CHUNK_SIZE,
    CACHE_PRICES_TTL_HOURS, CACHE_UNIVERSE_TTL_HOURS,
    BENCHMARK_TICKERS, NASDAQ_ONLY
)

warnings.filterwarnings("ignore", category=FutureWarning)


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

def get_nasdaq_universe(nasdaq_only: bool = True) -> list[str]:
    """
    Return liquid NASDAQ (and optionally NYSE) tickers from SEC EDGAR.
    Filters: price >= $5, 20-day avg volume >= 500K.
    Results are cached for 7 days.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / ("nasdaq_universe.json" if nasdaq_only else "full_universe.json")

    if _cache_valid(cache_file, CACHE_UNIVERSE_TTL_HOURS):
        with open(cache_file) as f:
            return json.load(f)

    print("   Fetching ticker list from SEC EDGAR...")
    tickers = _fetch_sec_tickers(nasdaq_only=nasdaq_only)
    print(f"   Filtering {len(tickers)} raw tickers for liquidity...")
    liquid = _filter_liquid(tickers)

    with open(cache_file, "w") as f:
        json.dump(liquid, f)

    return liquid


def _fetch_sec_tickers(nasdaq_only: bool) -> list[str]:
    """Pull all exchange-listed tickers from SEC EDGAR company_tickers_exchange.json."""
    url = "https://www.sec.gov/files/company_tickers_exchange.json"
    try:
        resp = requests.get(url, headers={"User-Agent": "nasdaq-scanner/1.0"}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        fields = data["fields"]   # ['cik', 'name', 'ticker', 'exchange']
        rows = data["data"]
        ticker_idx = fields.index("ticker")
        exchange_idx = fields.index("exchange")

        tickers = []
        for row in rows:
            exchange = str(row[exchange_idx]).upper()
            ticker = str(row[ticker_idx]).upper().strip()
            if not ticker or len(ticker) > 5:
                continue
            if nasdaq_only and exchange != "Nasdaq":
                continue
            if not nasdaq_only and exchange not in ("Nasdaq", "NYSE"):
                continue
            tickers.append(ticker)

        return list(set(tickers))
    except Exception as e:
        print(f"   ⚠️  SEC EDGAR fetch failed ({e}), using cached fallback...")
        return _fallback_tickers()


def _filter_liquid(tickers: list[str]) -> list[str]:
    """Download a quick snapshot and filter by price + volume."""
    liquid = []
    chunks = [tickers[i:i+500] for i in range(0, len(tickers), 500)]
    for chunk in chunks:
        try:
            batch = " ".join(chunk)
            df = yf.download(batch, period="1mo", interval="1d",
                             progress=False, auto_adjust=True)
            if df.empty:
                continue
            close = df["Close"] if "Close" in df.columns else df.get("Adj Close", pd.DataFrame())
            volume = df["Volume"] if "Volume" in df.columns else pd.DataFrame()

            if close.empty or volume.empty:
                continue

            for ticker in chunk:
                try:
                    if ticker not in close.columns:
                        continue
                    last_price = close[ticker].dropna().iloc[-1]
                    avg_vol = volume[ticker].dropna().iloc[-VOLUME_AVG_PERIOD:].mean()
                    if last_price >= MIN_PRICE and avg_vol >= MIN_AVG_VOLUME:
                        liquid.append(ticker)
                except Exception:
                    continue
        except Exception:
            continue
        time.sleep(0.5)  # be nice to Yahoo

    return liquid


def _fallback_tickers() -> list[str]:
    """Hardcoded fallback of ~100 liquid NASDAQ stocks if SEC EDGAR is unreachable."""
    return [
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO", "COST",
        "ASML", "NFLX", "AMD", "QCOM", "AMAT", "LRCX", "KLAC", "SNPS", "CDNS",
        "MRVL", "ADBE", "CRM", "PANW", "CRWD", "FTNT", "ZS", "OKTA", "NET",
        "DDOG", "SNOW", "MDB", "PLTR", "AXON", "SMCI", "ARM", "MSTR", "HIMS",
        "SOUN", "ASTS", "CELH", "DUOL", "CAVA", "RDDT", "UBER", "LYFT", "DASH",
        "ABNB", "BKNG", "EXPE", "PCTY", "PAYC", "GTLB", "HCP", "TMDX", "RXRX",
        "IREN", "CIFR", "BTDR", "MARA", "RIOT", "COIN", "HOOD", "SOFI", "AFRM",
        "UPST", "OPEN", "RDFN", "OPENDOOR", "SAMSARA", "IOT", "IONQ", "RGTI",
        "QUBT", "QBTS", "KULR", "SERV", "ACHR", "JOBY", "LILM", "EVTL",
        "ON", "WOLF", "ALGM", "MPWR", "OSIS", "AAON", "PAYSI", "GENI", "APP",
    ]


# ---------------------------------------------------------------------------
# Price data
# ---------------------------------------------------------------------------

def download_prices(tickers: list[str]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """
    Download 1 year of daily OHLCV for all tickers + benchmark tickers.
    Returns: (per-ticker DataFrames dict, benchmark DataFrame)
    Uses parquet cache with 16-hour TTL.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    all_tickers = list(set(tickers + BENCHMARK_TICKERS))

    cache_file = CACHE_DIR / "prices.parquet"
    if _cache_valid(cache_file, CACHE_PRICES_TTL_HOURS):
        print("   Using cached price data...")
        combined = pd.read_parquet(cache_file)
    else:
        combined = _download_all(all_tickers)
        combined.to_parquet(cache_file)

    # Split into per-ticker dict
    prices = {}
    for ticker in tickers:
        try:
            df = _extract_ticker(combined, ticker)
            if df is not None and len(df) >= 60:
                prices[ticker] = df
        except Exception:
            continue

    # Build benchmark df (Close columns for SPY, QQQ, ^VIX, etc.)
    benchmark = _build_benchmark(combined)

    return prices, benchmark


def _download_all(tickers: list[str]) -> pd.DataFrame:
    """Download in chunks to respect yfinance rate limits."""
    chunks = [tickers[i:i+DOWNLOAD_CHUNK_SIZE] for i in range(0, len(tickers), DOWNLOAD_CHUNK_SIZE)]
    frames = []
    for i, chunk in enumerate(chunks):
        print(f"   Downloading chunk {i+1}/{len(chunks)} ({len(chunk)} tickers)...", end="\r")
        try:
            batch = " ".join(chunk)
            df = yf.download(batch, period=PRICE_HISTORY_PERIOD, interval="1d",
                             progress=False, auto_adjust=True, group_by="ticker")
            frames.append(df)
        except Exception as e:
            print(f"\n   ⚠️  Chunk {i+1} failed: {e}")
        time.sleep(1.0)

    print()
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1)


def _extract_ticker(combined: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    """Extract OHLCV for a single ticker from the combined multi-ticker DataFrame."""
    try:
        if ticker in combined.columns.get_level_values(0):
            df = combined[ticker].dropna(subset=["Close"])
        elif ("Close", ticker) in combined.columns:
            cols = ["Open", "High", "Low", "Close", "Volume"]
            df = pd.DataFrame({c: combined[(c, ticker)] for c in cols}).dropna(subset=["Close"])
        else:
            return None
        return df.reset_index().rename(columns={"index": "Date"}) if "Date" not in df.columns else df
    except Exception:
        return None


def _build_benchmark(combined: pd.DataFrame) -> pd.DataFrame:
    """Extract benchmark close prices for market context calculation."""
    bench_data = {}
    for ticker in BENCHMARK_TICKERS:
        try:
            df = _extract_ticker(combined, ticker)
            if df is not None and not df.empty:
                bench_data[ticker] = df.set_index("Date")["Close"] if "Date" in df.columns else df["Close"]
        except Exception:
            continue
    return pd.DataFrame(bench_data)


def _cache_valid(path: Path, ttl_hours: int) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return datetime.now() - mtime < timedelta(hours=ttl_hours)
