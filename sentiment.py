"""
Sentiment Tracker
=================
Fetches social + news sentiment for scanner picks and pushes to Firebase.

Sources:
  - StockTwits  : bullish/bearish ratio + message volume (no auth needed)
  - Finnhub     : news sentiment + buzz score (API key required)
  - Reddit      : mention count across r/wallstreetbets, r/stocks, r/investing

Firebase paths:
  /scanner/sentiment/{TICKER}   : sentiment record per ticker
  /scanner/sentiment/_updated   : last run timestamp

Usage:
    python sentiment.py                        # all top scanner picks
    python sentiment.py --tickers AAPL,TSLA    # specific tickers
    python sentiment.py --limit 50             # top N picks (default 100)
"""

import os, time, logging, argparse
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

REDDIT_HEADERS = {"User-Agent": "StockSentimentBot/1.0"}
SUBREDDITS     = ["wallstreetbets", "stocks", "investing"]


# ── StockTwits ─────────────────────────────────────────────────────────────────
def fetch_stocktwits(ticker):
    try:
        r = requests.get(
            f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json",
            timeout=10
        )
        if r.status_code == 429:
            log.warning(f"  StockTwits rate limit — sleeping 10s")
            time.sleep(10)
            return None
        if r.status_code != 200:
            return None
        messages = r.json().get("messages", [])
        bullish = sum(
            1 for m in messages
            if (m.get("entities") or {}).get("sentiment", {}) and
               m["entities"]["sentiment"].get("basic") == "Bullish"
        )
        bearish = sum(
            1 for m in messages
            if (m.get("entities") or {}).get("sentiment", {}) and
               m["entities"]["sentiment"].get("basic") == "Bearish"
        )
        total = bullish + bearish
        return {
            "message_count": len(messages),
            "bullish_count": bullish,
            "bearish_count": bearish,
            "bullish_pct":   round(bullish / total * 100) if total > 0 else 50,
            "bearish_pct":   round(bearish / total * 100) if total > 0 else 50,
        }
    except Exception as e:
        log.warning(f"  StockTwits error for {ticker}: {e}")
        return None


# ── Finnhub ────────────────────────────────────────────────────────────────────
def fetch_finnhub_news(ticker):
    if not FINNHUB_KEY:
        return None
    try:
        today    = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        r = requests.get(
            f"https://finnhub.io/api/v1/company-news",
            params={"symbol": ticker, "from": week_ago, "to": today, "token": FINNHUB_KEY},
            timeout=10
        )
        if r.status_code != 200:
            return None
        articles = r.json()
        latest = articles[0] if articles else {}
        return {
            "article_count_7d": len(articles),
            "latest_headline":  latest.get("headline", ""),
            "latest_url":       latest.get("url", ""),
            "latest_source":    latest.get("source", ""),
            "latest_ts":        latest.get("datetime", 0),
        }
    except Exception as e:
        log.warning(f"  Finnhub news error for {ticker}: {e}")
        return None


def fetch_finnhub_sentiment(ticker):
    if not FINNHUB_KEY:
        return None
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/news-sentiment",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=10
        )
        if r.status_code != 200:
            return None
        data = r.json()
        buzz = data.get("buzz", {})
        sent = data.get("sentiment", {})
        return {
            "buzz_score":      round(buzz.get("buzz", 0), 3),
            "articles_weekly": round(buzz.get("weeklyAverage", 0), 1),
            "news_sentiment":  round(sent.get("bearerSentiment", 0), 3),
            "positive_pct":    round((sent.get("positiveScore", 0)) * 100),
            "negative_pct":    round((sent.get("negativeScore", 0)) * 100),
        }
    except Exception as e:
        log.warning(f"  Finnhub sentiment error for {ticker}: {e}")
        return None


# ── Reddit ─────────────────────────────────────────────────────────────────────
def fetch_reddit(ticker):
    total_mentions = 0
    top_title  = ""
    top_score  = 0
    try:
        for sub in SUBREDDITS:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/search.json",
                params={"q": ticker, "sort": "relevance", "t": "week",
                        "limit": 10, "restrict_sr": 1},
                headers=REDDIT_HEADERS,
                timeout=10
            )
            if r.status_code == 200:
                posts = r.json().get("data", {}).get("children", [])
                total_mentions += len(posts)
                for post in posts:
                    d = post.get("data", {})
                    if d.get("score", 0) > top_score:
                        top_score = d["score"]
                        top_title = d.get("title", "")
            time.sleep(0.6)   # stay under Reddit rate limit
        return {
            "mentions_7d":    total_mentions,
            "top_post_title": top_title,
            "top_post_score": top_score,
        }
    except Exception as e:
        log.warning(f"  Reddit error for {ticker}: {e}")
        return None


# ── Composite buzz score (0–100) ───────────────────────────────────────────────
def compute_buzz(st, fh, rd):
    score = 0.0
    # StockTwits volume: up to 25 pts (30 msgs = max)
    if st:
        score += min(25, st.get("message_count", 0) * 25 / 30)
        # Sentiment skew: bullish > 60 → bonus, < 40 → penalty
        bull = st.get("bullish_pct", 50)
        score += max(-10, min(10, (bull - 50) * 0.4))
    # Finnhub buzz: 0-1 scale → up to 35 pts
    if fh:
        score += min(35, fh.get("buzz_score", 0) * 35)
        # News sentiment bonus: up to 10 pts
        score += max(-5, min(10, fh.get("news_sentiment", 0) * 20))
    # Reddit mentions: up to 20 pts (10 mentions = max)
    if rd:
        score += min(20, rd.get("mentions_7d", 0) * 2)
    return min(100, max(0, round(score)))


def overall_sentiment(st, fh):
    bull_pct   = (st or {}).get("bullish_pct", 50)
    news_score = (fh or {}).get("news_sentiment", 0)
    if bull_pct >= 60 and news_score >= 0.05:
        return "bullish"
    if bull_pct <= 40 or news_score <= -0.05:
        return "bearish"
    return "neutral"


# ── Main ───────────────────────────────────────────────────────────────────────
def run(tickers):
    log.info(f"Fetching sentiment for {len(tickers)} tickers...")
    for i, ticker in enumerate(tickers):
        log.info(f"[{i+1}/{len(tickers)}] {ticker}")

        st = fetch_stocktwits(ticker)
        time.sleep(0.3)

        fh_news = fetch_finnhub_news(ticker)
        time.sleep(1.1)          # Finnhub free tier: 60 req/min
        fh_sent = fetch_finnhub_sentiment(ticker)
        time.sleep(1.1)

        rd = fetch_reddit(ticker)

        fh = {}
        if fh_news: fh.update(fh_news)
        if fh_sent: fh.update(fh_sent)

        buzz = compute_buzz(st, fh or None, rd)
        sent = overall_sentiment(st, fh or None)

        record = {
            "ticker":             ticker,
            "updated_at":         datetime.now().isoformat(),
            "buzz_score":         buzz,
            "overall_sentiment":  sent,
            "stocktwits":         st or {},
            "finnhub":            fh or {},
            "reddit":             rd or {},
        }

        sent_ref.child(ticker).set(record)
        log.info(f"  → buzz={buzz}  sentiment={sent}  "
                 f"ST={st and st['message_count']}msgs  "
                 f"Reddit={rd and rd['mentions_7d']}mentions  "
                 f"News={fh and fh.get('article_count_7d')}articles")

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
        # Sort by score descending, take top N
        tickers = sorted(snap.keys(),
                         key=lambda t: (snap[t] or {}).get("score", 0),
                         reverse=True)[:args.limit]

    if not tickers:
        log.error("No tickers to process.")
        exit(1)

    run(tickers)
