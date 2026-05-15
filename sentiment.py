"""
Sentiment Tracker
=================
Fetches news sentiment for an expanded universe and pushes to Firebase.

Universe (merged, deduplicated):
  1. All current scanner picks  (/scanner/all_stocks)
  2. Recent IPOs                (Finnhub /calendar/ipo, last 30 days)
  3. Recent history picks       (/scanner/history, last 14 days)

What works on Finnhub free tier:
  - /company-news    : article list + headlines (confirmed working)
  - /calendar/ipo    : recent IPOs (confirmed working)

What does NOT work on free tier (removed):
  - /news-sentiment  : premium only
  - StockTwits       : Cloudflare bot protection blocks scripts
  - Reddit           : API requires OAuth, bot detection

Sentiment is derived by keyword analysis across all fetched headlines.
Buzz is derived from article volume (log-normalized to 0-100).

Firebase paths:
  /scanner/sentiment/{TICKER}   : sentiment record per ticker
  /scanner/sentiment/_updated   : last run timestamp

Usage:
    python sentiment.py                        # expanded universe (default)
    python sentiment.py --tickers AAPL,TSLA    # specific tickers
    python sentiment.py --limit 200            # cap universe size (default 200)
    python sentiment.py --ipo-days 30          # IPO lookback window (default 30)
    python sentiment.py --history-days 14      # history lookback (default 14)
"""

import os, time, math, logging, argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

import requests
import firebase_admin
from firebase_admin import credentials, db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FINNHUB_KEY   = os.environ.get("FINNHUB_KEY", "")
FIREBASE_URL  = os.environ["FIREBASE_URL"]
FIREBASE_CRED = os.environ["FIREBASE_CRED"]

cred = credentials.Certificate(FIREBASE_CRED)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})
sent_ref = db.reference("/scanner/sentiment")

# ── Sentiment keyword lists ────────────────────────────────────────────────────
BULLISH_WORDS = {
    "beat", "beats", "surge", "surges", "surging", "rally", "rallies", "record",
    "strong", "strength", "growth", "upgrade", "upgraded", "outperform", "buy",
    "profit", "profits", "gain", "gains", "soar", "soars", "soaring", "jump",
    "jumps", "rise", "rises", "rising", "bullish", "exceed", "exceeds", "positive",
    "boost", "boosted", "breakout", "momentum", "upside", "higher", "above",
    "opportunity", "optimistic", "recovery", "recovers", "expands", "expansion",
}

BEARISH_WORDS = {
    "miss", "misses", "missing", "decline", "declines", "declining", "drop",
    "drops", "dropping", "fall", "falls", "falling", "weak", "weakness",
    "downgrade", "downgraded", "underperform", "sell", "loss", "losses",
    "crash", "crashes", "concern", "concerns", "warning", "warns", "cut",
    "cuts", "reduce", "reduced", "below", "bearish", "disappoint", "disappoints",
    "disappointing", "plunge", "plunges", "trouble", "risk", "risks", "fear",
    "fears", "lawsuit", "investigation", "probe", "layoffs", "layoff", "debt",
}

# ── Source credibility weights ─────────────────────────────────────────────────
# SeekingAlpha/Benzinga are explicit buy-sell focused → higher weight
# General news (Yahoo, CNBC) is broader → lower weight
SOURCE_WEIGHTS = {
    "SeekingAlpha": 2.5,   # "Strong Buy", "Sell Now" — very explicit
    "Benzinga":     2.0,   # real-time, analyst-focused
    "ChartMill":    1.8,   # technical + fundamental ratings
    "CNBC":         1.3,   # credible but more neutral/macro
    "Yahoo":        1.0,   # broad aggregator
    "Finnhub":      1.0,   # default
}


# ── Finnhub news ───────────────────────────────────────────────────────────────
def fetch_finnhub_news(ticker, days=7):
    """Fetch all articles from Finnhub for the last N days. Returns list of dicts."""
    if not FINNHUB_KEY:
        return []
    try:
        today    = datetime.now().strftime("%Y-%m-%d")
        from_dt  = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        r = requests.get(
            "https://finnhub.io/api/v1/company-news",
            params={"symbol": ticker, "from": from_dt, "to": today, "token": FINNHUB_KEY},
            timeout=10
        )
        if r.status_code == 429:
            log.warning(f"  Finnhub rate limit — sleeping 15s")
            time.sleep(15)
            return []
        if r.status_code != 200:
            return []
        return r.json() or []
    except Exception as e:
        log.warning(f"  Finnhub news error for {ticker}: {e}")
        return []


# ── Finnhub IPO calendar ──────────────────────────────────────────────────────
def fetch_ipo_tickers(days=30):
    """Return set of ticker symbols from recent IPOs (Finnhub free tier)."""
    if not FINNHUB_KEY:
        return set()
    try:
        today   = datetime.now().strftime("%Y-%m-%d")
        from_dt = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        r = requests.get(
            "https://finnhub.io/api/v1/calendar/ipo",
            params={"from": from_dt, "to": today, "token": FINNHUB_KEY},
            timeout=10,
        )
        if r.status_code != 200:
            log.warning(f"  IPO calendar returned {r.status_code}")
            return set()
        data = r.json() or {}
        ipoCalendar = data.get("ipoCalendar", [])
        tickers = set()
        for item in ipoCalendar:
            sym = (item.get("symbol") or "").strip().upper()
            if not sym:
                continue
            exch = (item.get("exchange") or "").upper()
            # Finnhub returns "NASDAQ Global", "NASDAQ Capital", "NYSE MKT", etc.
            if exch.startswith("NASDAQ") or exch.startswith("NYSE") or exch == "":
                tickers.add(sym)
        log.info(f"  IPO calendar: {len(tickers)} tickers (last {days} days)")
        return tickers
    except Exception as e:
        log.warning(f"  IPO calendar error: {e}")
        return set()


# ── Firebase history picks ─────────────────────────────────────────────────────
def fetch_history_tickers(days=14):
    """Return set of tickers that appeared in /scanner/history in the last N days."""
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        snap = db.reference("/scanner/history").get()
        if not snap:
            return set()
        tickers = set()
        for date_key, day_data in snap.items():
            if date_key < cutoff:
                continue
            if isinstance(day_data, dict):
                tickers.update(day_data.keys())
        log.info(f"  History tickers (last {days} days): {len(tickers)}")
        return tickers
    except Exception as e:
        log.warning(f"  History tickers error: {e}")
        return set()


# ── Yahoo Finance trending + most-active tickers ──────────────────────────────
_YF_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; sentiment-tracker/1.0)"}

def fetch_yahoo_trending(count=50):
    """Trending tickers on Yahoo Finance right now (no auth required)."""
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v1/finance/trending/US",
            params={"count": count},
            headers=_YF_HEADERS,
            timeout=10,
        )
        if r.status_code != 200:
            log.warning(f"  Yahoo trending: HTTP {r.status_code}")
            return set()
        quotes = r.json().get("finance", {}).get("result", [{}])[0].get("quotes", [])
        tickers = {q["symbol"].strip().upper() for q in quotes if q.get("symbol")}
        log.info(f"  Yahoo trending: {len(tickers)} tickers")
        return tickers
    except Exception as e:
        log.warning(f"  Yahoo trending error: {e}")
        return set()

def fetch_yahoo_movers(count=50):
    """Top movers (most-actives + day gainers) from Yahoo Finance screener."""
    results = set()
    for scr_id in ("most_actives", "day_gainers", "day_losers"):
        try:
            r = requests.get(
                "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved",
                params={"scrIds": scr_id, "count": count},
                headers=_YF_HEADERS,
                timeout=10,
            )
            if r.status_code != 200:
                continue
            quotes = (
                r.json()
                .get("finance", {})
                .get("result", [{}])[0]
                .get("quotes", [])
            )
            for q in quotes:
                sym = (q.get("symbol") or "").strip().upper()
                if sym and "." not in sym:   # skip ADRs (BRK.A etc.)
                    results.add(sym)
        except Exception as e:
            log.warning(f"  Yahoo movers ({scr_id}) error: {e}")
    log.info(f"  Yahoo movers (actives+gainers+losers): {len(results)} tickers")
    return results


# ── Pinned tickers (user-managed via Sentiment page UI) ───────────────────────
def fetch_pinned_tickers():
    """Return set of tickers pinned by the user at /scanner/sentiment_universe/pinned."""
    try:
        snap = db.reference("/scanner/sentiment_universe/pinned").get() or {}
        tickers = {t.strip().upper() for t in snap.keys() if t and t != "_updated"}
        log.info(f"  Pinned tickers: {len(tickers)}")
        return tickers
    except Exception as e:
        log.warning(f"  Pinned tickers error: {e}")
        return set()


# ── Build full sentiment universe ──────────────────────────────────────────────
def build_universe(limit, ipo_days, history_days):
    """
    Merge six sources into an ordered list of tickers:
      1. Pinned tickers (user-managed) — always included, never dropped
      2. Yahoo Finance trending tickers (right now)
      3. Yahoo Finance most-actives / day gainers / day losers
      4. All scanner picks (sorted by score desc)
      5. Recent IPOs from Finnhub calendar
      6. Recent history picks (appeared in last history_days)
    Deduplicates while preserving insertion order, then caps at limit.
    """
    ordered = []
    seen    = set()

    def _add(tickers):
        for t in sorted(tickers):
            if t not in seen:
                ordered.append(t)
                seen.add(t)

    # 1. Pinned tickers (always included, regardless of limit)
    pinned = fetch_pinned_tickers()
    _add(pinned)

    # 2. Yahoo Finance trending
    _add(fetch_yahoo_trending())

    # 3. Yahoo Finance movers (most-actives + gainers + losers)
    _add(fetch_yahoo_movers())

    # 4. Scanner picks
    try:
        snap = db.reference("/scanner/all_stocks").get() or {}
        scanner_tickers = sorted(
            snap.keys(),
            key=lambda t: (snap[t] or {}).get("score", 0),
            reverse=True,
        )
        _add(scanner_tickers)
        log.info(f"  Scanner picks: {len(scanner_tickers)}")
    except Exception as e:
        log.warning(f"  Scanner picks error: {e}")

    # 5. IPO calendar
    ipo_tickers = fetch_ipo_tickers(days=ipo_days)
    time.sleep(1.1)  # rate limit
    _add(ipo_tickers)

    # 6. History tickers
    _add(fetch_history_tickers(days=history_days))

    # Pinned tickers are always included even beyond the limit
    non_pinned = [t for t in ordered if t not in pinned]
    universe   = list(pinned) + non_pinned[:max(0, limit - len(pinned))]
    log.info(f"  Universe: {len(universe)} tickers ({len(pinned)} pinned, cap={limit})")
    return universe


# ── Sentiment from headlines ───────────────────────────────────────────────────
def analyze_sentiment(articles):
    """
    Keyword analysis across all article headlines, weighted by source credibility.
    SeekingAlpha/Benzinga signals count 2-2.5x more than generic news.
    Returns: 'bullish' | 'bearish' | 'neutral', plus weighted pos/neg scores.
    """
    pos = 0.0
    neg = 0.0
    for a in articles:
        weight = SOURCE_WEIGHTS.get(a.get("source", ""), 1.0)
        words  = set((a.get("headline", "") + " " + a.get("summary", "")).lower().split())
        pos   += len(words & BULLISH_WORDS) * weight
        neg   += len(words & BEARISH_WORDS) * weight
    total = pos + neg
    if total == 0:
        sentiment = "neutral"
    elif pos / total >= 0.60:
        sentiment = "bullish"
    elif neg / total >= 0.60:
        sentiment = "bearish"
    else:
        sentiment = "neutral"
    return sentiment, round(pos, 1), round(neg, 1)


# ── Buzz score from article volume (log scale, 0–100) ─────────────────────────
def compute_buzz(article_count):
    """
    Log-normalized buzz score:
      0 articles  →  0
      5 articles  → 27
     10 articles  → 36
     20 articles  → 46
     50 articles  → 60
    100 articles  → 72
    244 articles  → 90
    300+ articles → 100
    """
    if article_count <= 0:
        return 0
    return min(100, round(math.log(article_count + 1) / math.log(301) * 100))


# ── Main ───────────────────────────────────────────────────────────────────────
def run(tickers):
    log.info(f"Fetching sentiment for {len(tickers)} tickers...")
    for i, ticker in enumerate(tickers):
        log.info(f"[{i+1}/{len(tickers)}] {ticker}")

        articles = fetch_finnhub_news(ticker)
        time.sleep(1.1)   # Finnhub free: 60 req/min

        count   = len(articles)
        buzz    = compute_buzz(count)
        sentiment, pos_count, neg_count = analyze_sentiment(articles)

        # Store top 3 headlines
        headlines = [
            {
                "headline": a.get("headline", ""),
                "url":      a.get("url", ""),
                "source":   a.get("source", ""),
                "ts":       a.get("datetime", 0),
            }
            for a in articles[:3]
        ]

        record = {
            "ticker":            ticker,
            "updated_at":        datetime.now().isoformat(),
            "buzz_score":        buzz,
            "overall_sentiment": sentiment,
            "article_count_7d":  count,
            "positive_signals":  pos_count,
            "negative_signals":  neg_count,
            "headlines":         headlines,
            # Latest headline (kept for backwards compat with dashboard badge)
            "finnhub": {
                "article_count_7d": count,
                "latest_headline":  headlines[0]["headline"] if headlines else "",
                "latest_url":       headlines[0]["url"]      if headlines else "",
                "latest_source":    headlines[0]["source"]   if headlines else "",
            }
        }

        sent_ref.child(ticker).set(record)
        log.info(f"  → buzz={buzz}  sentiment={sentiment}  "
                 f"articles={count}  pos={pos_count}  neg={neg_count}")

    sent_ref.child("_updated").set(datetime.now().isoformat())
    log.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers",      help="Comma-separated tickers (overrides auto universe)")
    parser.add_argument("--limit",        type=int, default=200, help="Max tickers in universe (default 200)")
    parser.add_argument("--ipo-days",     type=int, default=30,  help="IPO calendar lookback days (default 30)")
    parser.add_argument("--history-days", type=int, default=14,  help="History lookback days (default 14)")
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = build_universe(
            limit        = args.limit,
            ipo_days     = args.ipo_days,
            history_days = args.history_days,
        )

    if not tickers:
        log.error("No tickers to process.")
        exit(1)

    run(tickers)
