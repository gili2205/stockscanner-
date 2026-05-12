# NASDAQ Momentum Scanner

A production stock scanner built on the Qullamaggie breakout methodology. Runs continuously on a GCP VM, stores results in Firebase, and serves a live web dashboard on Vercel.

---

## Architecture

```
GCP VM (scanner-prod / scanner-staging)
  ├── live_scanner.py   — runs every market day, scores all NASDAQ stocks, pushes to Firebase
  ├── backtest.py       — reconstructs historical signals + forward returns, stores in Firebase
  ├── optimizer.py      — factor analysis: which signals actually predict winning stocks
  └── smart_money.py    — fetches insider buys (Form 4) + hedge fund holdings (13F) from SEC EDGAR

Firebase Realtime Database
  ├── /scanner/all_stocks      — latest scan results (live dashboard)
  ├── /scanner/history         — historical picks with forward returns (analytics)
  ├── /scanner/first_seen      — when each ticker was first flagged
  ├── /scanner/smart_money     — insider + institutional data
  └── /scanner/optimization_reports — factor analysis results

Vercel (Flask app — app.py)
  ├── /            — live dashboard (latest scan results)
  ├── /analytics   — historical picks table with returns, sort, search
  └── /smart-money — insider buying + hedge fund holdings
```

Two environments — staging and production — with separate Firebase databases and GCP VMs. `FLASK_ENV=staging` switches the app to the staging Firebase config.

---

## Scoring Logic

### Qullamaggie Score (0–100)

Each stock is scored using these factors (same logic in both live scanner and backtest):

| Factor | Max pts | Logic |
|--------|---------|-------|
| EMA stack | 30 | `full` (price > EMA10 > EMA20 > EMA50) = 30, `partial` = 18, `weak` = 8 |
| HH/HL structure | 20 | % of last 20 bars with higher-high + higher-low: ≥85% = 20, ≥70% = 13, ≥55% = 7 |
| ATR compression | 15 | ATR/price: ≤0.25 = 15, ≤0.35 = 11, ≤0.45 = 7, ≤0.55 = 3 |
| Level | 10 | ATH = 10, multi-year high = 8, 52-week high = 6, prior resistance = 3 |
| Volume contraction | 10 | 5-day avg vs 20-day avg: ≤50% = 10, ≤70% = 6, ≤90% = 2 |
| Pre-breakout setup | 5 | ATR ≤ 3%, vol dry ≤ 70%, within 5% of level, EMA full/partial |
| Bull flag | 5 | ATR ≤ 2.5%, vol dry ≤ 65%, 1M momentum ≥ 8%, EMA full/partial |

### Status Labels
| Score | Status | Meaning |
|-------|--------|---------|
| ≥ 72 | READY | All criteria met — breakout imminent |
| 55–71 | WATCH | Pattern forming — wait for trigger |
| < 55 | BUILDING | Too early |

### Quality Gate (live scanner)
Stock must pass ALL to appear in results:
- Price ≥ $15
- Avg daily dollar volume ≥ $10M (price × avg volume)

---

## Files

### `live_scanner.py`
Runs on the GCP VM (via systemd). Every market day it:
1. Fetches ~4,000 NASDAQ tickers
2. Downloads OHLCV data via yfinance
3. Scores each stock with the Qullamaggie logic
4. Assigns RS percentiles across the universe
5. Pushes top results to Firebase `/scanner/all_stocks` using `ref.update()` (not `ref.set()` — critical: `set()` would wipe history)

### `backtest.py`
Reconstructs historical scanner signals using past price data. Run manually on the GCP VM.

```bash
# Last 30 trading days (default)
python backtest.py

# Last 180 trading days
python backtest.py --days 180

# Specific date only
python backtest.py --date 2026-04-01

# Fill in forward returns for existing picks (run after time passes)
python backtest.py --update-returns
```

Stores results in Firebase `/scanner/history/YYYY-MM-DD` — each day holds up to 200 top picks with all signals + forward returns (1W / 2W / 1M / 2M / 3M).

**Important**: Downloads price data in batches of 200 tickers using `ThreadPoolExecutor` with a 120-second timeout per batch. Batches that hang are retried up to 3 times then skipped.

### `optimizer.py`
Factor analysis engine. Reads all historical picks from Firebase and identifies which signals predict winning stocks.

```bash
# Analyze 1-month forward returns (default)
python optimizer.py

# Analyze all return windows
python optimizer.py --all-windows

# Specific window: 1w, 2w, 1m, 2m, 3m
python optimizer.py --window 2w
```

Output: overall win rate, performance by score band, factor analysis table sorted by win-rate lift. Saves to Firebase `/scanner/optimization_reports/<timestamp>` and `/tmp/optimizer_report.json`.

### `smart_money.py`
Fetches smart money signals from SEC EDGAR:
- **Insider buying** (Form 4): last 14 days, purchases > $100K
- **Hedge fund holdings** (13F): top 10 funds — Berkshire, Pershing Square, Duquesne, Appaloosa, Third Point, Tiger Global, Baupost, Viking, Point72, Renaissance

CUSIP → ticker mapping via OpenFIGI API. Pushes to Firebase `/scanner/smart_money`.

```bash
python smart_money.py
```

---

## Web Pages

### `/` — Live Dashboard
Shows the latest scan results from Firebase. Auto-refreshes. Cards show score, status, EMA stack, level, ATR, volume contraction, momentum, and setup flags.

### `/analytics` — Historical Picks
Shows all historical picks from Firebase `/scanner/history` with forward returns.
- **localStorage caching**: first load fetches all data, subsequent loads only fetch new dates (fast)
- **Sort**: by date, A–Z, score, 1W / 1M / 3M return
- **Search**: filter by ticker symbol

### `/smart-money` — Smart Money
Insider buying and hedge fund holdings in one tab. Updated by running `smart_money.py` on the VM.

---

## Environments

| | Production | Staging |
|---|---|---|
| VM | `scanner-prod` | `scanner-staging` |
| Firebase | `stockscanner-f9f81` | `stockscanner-staging` |
| Vercel | Production deployment | Preview deployment |
| Branch | `main` | `fix/scanner-bugs` |

`FLASK_ENV=staging` in the VM `.env` switches the app to the staging Firebase.

**Branch policy**: all changes go to `fix/scanner-bugs` first. Only merge to `main` after staging verification and explicit approval.

---

## Setup (new VM)

```bash
# Clone repo
git clone https://github.com/gili2205/stockscanner-.git /home/scanner
cd /home/scanner
git checkout fix/scanner-bugs   # or main for production

# Virtual environment
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# Environment variables
cp env_template.txt .env
# Edit .env: set FIREBASE_URL, FIREBASE_CRED, FLASK_ENV

# Run backtest to populate history
nohup venv/bin/python backtest.py --days 180 > /tmp/backtest.log 2>&1 &

# Then fill in forward returns
venv/bin/python backtest.py --update-returns

# Start live scanner (systemd service)
sudo systemctl start scanner
```

---

## Return Windows

| Label | Trading days |
|-------|-------------|
| 1W | 5 |
| 2W | 10 |
| 1M | 21 |
| 2M | 42 |
| 3M | 63 |
| 6M | 126 |
| 1Y | 252 |

---

## ⚠️ Disclaimer

This scanner identifies setups with historically positive expected value. It does NOT guarantee profits. Trading involves risk of loss. Always use stop losses. Past performance does not predict future results. This is not financial advice.
