"""
fundamentals.py — Overnight fundamentals enrichment for NASDAQ Scanner v1.5
Fetches earnings dates, analyst ratings, revenue growth, and short interest
for all stocks in the history cache. Saves to fundamentals_cache.json.

Run once per day, ideally at 6 AM ET before market open.
Usage: /home/scanner/venv/bin/python /home/scanner/fundamentals.py
"""

import json
import os
import pickle
import time
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import yfinance as yf
import firebase_admin
from firebase_admin import credentials, db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("/var/log/scanner.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

CACHE_FILE       = "/home/scanner/history_cache.pkl"
FUND_CACHE_FILE  = "/home/scanner/fundamentals_cache.json"
FIREBASE_URL     = os.environ["FIREBASE_URL"]
FIREBASE_CRED    = os.environ["FIREBASE_CRED"]

# How many stocks to fetch per batch (yfinance is slow — 1-2s per ticker)
BATCH_SIZE = 1
# Max stocks to enrich (do top N by dollar volume to save time)
MAX_STOCKS = 800

def load_universe():
    """Load tickers from history cache."""
    if not Path(CACHE_FILE).exists():
        log.error("No history cache found — run live_scanner.py first")
        return []
    with open(CACHE_FILE, "rb") as f:
        cache = pickle.load(f)
    history = cache.get("data", {})
    log.info(f"Loaded {len(history)} tickers from history cache")
    return list(history.keys())

def load_existing_fundamentals():
    """Load existing fundamentals cache to skip already-fetched tickers."""
    if not Path(FUND_CACHE_FILE).exists():
        return {}
    try:
        with open(FUND_CACHE_FILE) as f:
            data = json.load(f)
        # Only keep if fetched today
        today = str(date.today())
        if data.get("_date") == today:
            log.info(f"Loaded existing fundamentals for {len(data)-1} tickers")
            return data
    except Exception:
        pass
    return {}

def fetch_fundamentals(ticker: str) -> dict:
    """
    Fetch fundamentals for a single ticker using yfinance.
    Returns a dict with all relevant fundamental data.
    """
    result = {
        "ticker":              ticker,
        "earnings_date":       None,   # Next earnings date (string)
        "days_to_earnings":    None,   # Days until next earnings
        "earnings_surprise":   None,   # Average EPS surprise % last 4Q
        "beat_count":          0,      # How many of last 4Q beat estimates
        "analyst_buy_pct":     None,   # % of analysts with Buy/Strong Buy
        "analyst_target":      None,   # Consensus price target
        "revenue_growth_yoy":  None,   # Revenue growth year-over-year %
        "eps_growth_yoy":      None,   # EPS growth year-over-year %
        "short_interest_pct":  None,   # Short interest as % of float
        "market_cap_b":        None,   # Market cap in billions
        "sector":              None,   # Sector
        "industry":            None,   # Industry
    }

    try:
        t = yf.Ticker(ticker)
        info = t.info

        # ── Market cap & sector ───────────────────────────────────────
        mc = info.get("marketCap")
        if mc:
            result["market_cap_b"] = round(mc / 1e9, 2)
        result["sector"]   = info.get("sector", "")
        result["industry"] = info.get("industry", "")

        # ── Analyst target & ratings ──────────────────────────────────
        target = info.get("targetMeanPrice")
        if target:
            result["analyst_target"] = round(float(target), 2)

        # Analyst recommendation: strongBuy, buy, hold, sell, strongSell
        sb  = info.get("numberOfAnalystOpinions", 0) or 0
        rec = info.get("recommendationKey", "")
        # recommendationMean: 1=Strong Buy, 2=Buy, 3=Hold, 4=Sell, 5=Strong Sell
        rec_mean = info.get("recommendationMean")
        if rec_mean:
            # Convert to buy percentage (1.0=100% buy, 3.0=0% buy)
            buy_pct = max(0, min(100, round((3.0 - rec_mean) / 2.0 * 100)))
            result["analyst_buy_pct"] = buy_pct

        # ── Revenue & EPS growth ──────────────────────────────────────
        rev_growth = info.get("revenueGrowth")
        if rev_growth:
            result["revenue_growth_yoy"] = round(float(rev_growth) * 100, 1)

        eps_growth = info.get("earningsGrowth")
        if eps_growth:
            result["eps_growth_yoy"] = round(float(eps_growth) * 100, 1)

        # ── Short interest ────────────────────────────────────────────
        short_pct = info.get("shortPercentOfFloat")
        if short_pct:
            result["short_interest_pct"] = round(float(short_pct) * 100, 1)

        # ── Next earnings date ────────────────────────────────────────
        try:
            cal = t.calendar
            if cal is not None and not cal.empty:
                # Calendar is a DataFrame with dates as columns
                cols = list(cal.columns)
                if cols:
                    earn_date = cols[0]
                    if hasattr(earn_date, 'date'):
                        earn_date = earn_date.date()
                    elif isinstance(earn_date, str):
                        earn_date = datetime.strptime(earn_date[:10], "%Y-%m-%d").date()
                    result["earnings_date"] = str(earn_date)
                    days = (earn_date - date.today()).days
                    result["days_to_earnings"] = days
        except Exception:
            pass

        # ── Earnings surprise history ─────────────────────────────────
        try:
            hist = t.earnings_history
            if hist is not None and not hist.empty:
                surprises = []
                beats = 0
                for _, row in hist.tail(4).iterrows():
                    surprise_pct = row.get("surprisePercent")
                    if surprise_pct is not None and not pd.isna(surprise_pct):
                        surprises.append(float(surprise_pct) * 100)
                        if float(surprise_pct) > 0:
                            beats += 1
                if surprises:
                    result["earnings_surprise"] = round(sum(surprises)/len(surprises), 1)
                    result["beat_count"] = beats
        except Exception:
            pass

    except Exception as e:
        log.debug(f"  {ticker}: {e}")

    return result

def push_to_firebase(fund_data: dict):
    """Push summary statistics to Firebase for dashboard display."""
    try:
        # Count stocks with upcoming earnings (next 7 days)
        upcoming = [
            t for t, v in fund_data.items()
            if t != "_date" and isinstance(v, dict)
            and v.get("days_to_earnings") is not None
            and 0 <= v["days_to_earnings"] <= 7
        ]
        ref = db.reference("/fundamentals_meta")
        ref.set({
            "last_updated": datetime.now().isoformat(),
            "stocks_enriched": len(fund_data) - 1,
            "earnings_this_week": len(upcoming),
            "earnings_tickers": upcoming[:20],
        })
        log.info(f"Pushed fundamentals meta to Firebase: {len(upcoming)} earnings this week")
    except Exception as e:
        log.warning(f"Firebase push failed: {e}")

def main():
    import pandas as pd

    log.info("=== FUNDAMENTALS ENRICHMENT starting ===")

    # Initialize Firebase
    try:
        cred = credentials.Certificate(FIREBASE_CRED)
        firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})
    except Exception as e:
        log.warning(f"Firebase init: {e}")

    # Load tickers
    tickers = load_universe()
    if not tickers:
        return

    # Load existing cache
    fund_data = load_existing_fundamentals()
    today = str(date.today())
    fund_data["_date"] = today

    # Limit to MAX_STOCKS — prioritize by alphabet for now
    # (in future: prioritize by dollar volume)
    to_fetch = [t for t in tickers if t not in fund_data][:MAX_STOCKS]
    log.info(f"Fetching fundamentals for {len(to_fetch)} tickers (skipping {len(fund_data)-1} already cached)")

    for i, ticker in enumerate(to_fetch):
        result = fetch_fundamentals(ticker)
        fund_data[ticker] = result

        if (i+1) % 50 == 0 or (i+1) == len(to_fetch):
            pct = round((i+1)/len(to_fetch)*100)
            log.info(f"  Fundamentals progress: {i+1}/{len(to_fetch)} ({pct}%)")
            # Save intermediate results
            with open(FUND_CACHE_FILE, "w") as f:
                json.dump(fund_data, f)

        time.sleep(0.3)  # Be respectful to Yahoo Finance

    # Final save
    with open(FUND_CACHE_FILE, "w") as f:
        json.dump(fund_data, f)

    log.info(f"=== FUNDAMENTALS COMPLETE: {len(fund_data)-1} stocks enriched ===")

    # Push summary to Firebase
    push_to_firebase(fund_data)

    # Print summary of what we found
    upcoming_earnings = [
        (t, v["days_to_earnings"], v.get("analyst_target"))
        for t, v in fund_data.items()
        if t != "_date" and isinstance(v, dict)
        and v.get("days_to_earnings") is not None
        and 0 <= v["days_to_earnings"] <= 7
    ]
    upcoming_earnings.sort(key=lambda x: x[1])
    if upcoming_earnings:
        log.info(f"\n📅 EARNINGS THIS WEEK ({len(upcoming_earnings)} stocks):")
        for ticker, days, target in upcoming_earnings[:20]:
            log.info(f"   {ticker}: in {days} days | target: ${target}")

if __name__ == "__main__":
    import pandas as pd
    main()
