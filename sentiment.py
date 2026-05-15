"""
Sentiment Tracker
=================
Fetches news sentiment for scanner picks from Finnhub and pushes to Firebase.

What works on Finnhub free tier:
  - /company-news  : article list + headlines (confirmed working)

What does NOT work on free tier (removed):
  - /news-sentiment : premium only
  - StockTwits      : Cloudflare bot protection blocks scripts
  - Reddit          : API requires OAuth, bot detection

Sentiment is derived by keyword analysis across all fetched headlines.
Buzz is derived from article volume (log-normalized to 0-100).

Firebase paths:
  /scanner/sentiment/{TICKER}   : sentiment record per ticker
  /scanner/sentiment/_updated   : last run timestamp

Usage:
    python sentiment.py                        # all top scanner picks
    python sentiment.py --tickers AAPL,TSLA    # specific tickers
    python sentiment.py --limit 50             # top N picks (default 100)
"""

import os, time, math, logging, argparse
from datetime import datetime, timedelta
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


# ── Sentiment from headlines ───────────────────────────────────────────────────
def analyze_sentiment(articles):
    """
    Count bullish / bearish keywords across all article headlines.
    Returns: 'bullish' | 'bearish' | 'neutral', plus positive_count, negative_count.
    """
    pos = 0
    neg = 0
    for a in articles:
        words = set((a.get("headline", "") + " " + a.get("summary", "")).lower().split())
        pos += len(words & BULLISH_WORDS)
        neg += len(words & BEARISH_WORDS)
    total = pos + neg
    if total == 0:
        sentiment = "neutral"
    elif pos / total >= 0.60:
        sentiment = "bullish"
    elif neg / total >= 0.60:
        sentiment = "bearish"
    else:
        sentiment = "neutral"
    return sentiment, pos, neg


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
    parser.add_argument("--tickers", help="Comma-separated tickers (default: top scanner picks)")
    parser.add_argument("--limit",   type=int, default=100, help="Max tickers to process (default 100)")
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        snap = db.reference("/scanner/all_stocks").get()
        if not snap:
            log.error("No scanner data found in Firebase. Run live_scanner.py first.")
            exit(1)
        tickers = sorted(
            snap.keys(),
            key=lambda t: (snap[t] or {}).get("score", 0),
            reverse=True
        )[:args.limit]

    if not tickers:
        log.error("No tickers to process.")
        exit(1)

    run(tickers)
