# NASDAQ Momentum Scanner

## Changelog

### v3.2.0 — 2026-05-13
- **New: `/optimizer` tab** — two-section optimizer page
  - Section 1: Statistical Optimizer (reads `optimizer.py` factor analysis from Firebase, free, runs weekly via cron)
  - Section 2: AI Analysis (Claude claude-opus-4-5, on-demand via button, ~$0.10/run)
- **New: `ai_optimizer.py`** — calls Claude to suggest scoring weight changes, shadow-backtests on 180 days, saves recommendation for human approval
- **New: `--check-and-run` mode** in `ai_optimizer.py` — 5-min cron polls Firebase flag, runs analysis when UI button is clicked
- **New: approval workflow** — Approve/Reject buttons in UI → `ai_optimizer.py --apply` patches `live_scanner.py` with approved weights (creates backup)
- **Fix: READY card missing green border** — card class logic now correctly uses status field
- **Fix: WATCH + pre_breakout showing green** — status takes priority over setup flags in card styling
- **Fix: 3M/6M performance data missing** — off-by-one in `pct()` function fixed
- **Fix: header height jumping between tabs** — unified CSS with `min-height:56px` and `position:sticky` across all pages

### v3.1.1 — 2026-05-12
- Added `optimizer.py` — statistical factor analysis engine
- Added `smart_money.py` — SEC EDGAR insider buys (Form 4) + hedge fund holdings (13F)
- Added `/smart-money` page
- Added staging Firebase environment support
- Analytics localStorage caching (only fetch new dates on reload)
- Analytics sort buttons + ticker search

### v3.0.0 — 2026-04-xx
- Added `/analytics` page with historical picks and forward returns
- Added `backtest.py` — reconstructs historical signals, fills forward returns
- Firebase history structure (`/scanner/history/YYYY-MM-DD`)

### v2.0.0 — 2026-03-xx
- Live dashboard rewrite with card-based UI
- RS percentile scoring
- Pre-breakout and bull flag detection

### v1.0.0 — 2026-02-xx
- Initial scanner — EMA stack, ATR, volume contraction scoring
- Basic Firebase integration
- Simple Vercel Flask app

---

A production stock scanner built on the Qullamaggie breakout methodology. Runs continuously on a GCP VM, stores results in Firebase, and serves a live web dashboard on Vercel.

---

## Architecture

```
GCP VM (scanner-prod / scanner-staging)
  ├── live_scanner.py   — runs every market day, scores all NASDAQ stocks, pushes to Firebase
  ├── backtest.py       — reconstructs historical signals + forward returns, stores in Firebase
  ├── optimizer.py      — factor analysis: which signals actually predict winning stocks (free, weekly cron)
  ├── ai_optimizer.py   — Claude AI analysis: suggests weight changes, shadow-backtested on 180 days
  └── smart_money.py    — fetches insider buys (Form 4) + hedge fund holdings (13F) from SEC EDGAR

Firebase Realtime Database
  ├── /scanner/all_stocks             — latest scan results (live dashboard)
  ├── /scanner/history                — historical picks with forward returns (analytics)
  ├── /scanner/first_seen             — when each ticker was first flagged
  ├── /scanner/smart_money            — insider + institutional data
  ├── /scanner/optimization_reports   — statistical factor analysis results (optimizer.py)
  ├── /scanner/ai_recommendations     — Claude AI weight suggestions (ai_optimizer.py)
  ├── /scanner/approved_weights       — approved weight changes awaiting apply
  └── /scanner/run_ai_requested       — UI trigger flag for on-demand AI analysis

Vercel (Flask app — app.py)
  ├── /            — live dashboard (latest scan results)
  ├── /analytics   — historical picks table with returns, sort, search
  ├── /smart-money — insider buying + hedge fund holdings
  └── /optimizer   — statistical + AI optimizer with approve/reject workflow
```

Two environments — staging and production — with separate Firebase databases and GCP VMs.

---

## Scoring Logic

### Qullamaggie Score (0–95, capped)

Each stock is scored on a BREAKOUT track using these factors:

| Factor | Max pts | Logic |
|--------|---------|-------|
| Momentum 1M | 28 | ≥25%=28, ≥15%=22, ≥8%=15, ≥3%=9, ≥0%=4 |
| EMA stack (full) | 22 | price > EMA10 > EMA20 > EMA50 |
| EMA stack (partial) | 12 | EMA10 > EMA20 only |
| Distance to level | 18 | ≤1%=18, ≤2%=14, ≤3.5%=9, ≤6%=4, ≤10%=1 |
| ATR compression | 12 | ≤0.20=12, ≤0.25=9, ≤0.30=6, ≤0.40=2 |
| HH/HL structure | 6 | ≥0.85 ratio=6, ≥0.70=3 |
| Volume contraction | 8 | ≤50%=8, ≤65%=5, ≤80%=2 |
| Liquidity | 7 | ≥$200M/day=7, ≥$50M=5, ≥$20M=3, else=1 |
| **Penalty: weak EMA** | -18 | Subtracted when ema_stack = "weak" |
| **Penalty: far dist** | -12 | Subtracted when dist_to_level > 15% |
| **Penalty: neg momentum** | -12 | Subtracted when momentum_1m < -5% |
| **Penalty: high vol/ATR** | -8 | Subtracted when ATR > 0.7 AND momentum < 10% |

### Status Labels
| Score | Status | Meaning |
|-------|--------|---------|
| ≥ 72 | READY | All criteria met — breakout imminent |
| 55–71 | WATCH | Pattern forming — wait for trigger |
| < 55 | BUILDING | Too early — not surfaced |

### Quality Gate (live scanner)
Stock must pass ALL to appear in results:
- Price ≥ $15
- Avg daily dollar volume ≥ $10M

---

## Files

### `live_scanner.py`
Runs on the GCP VM (via systemd + watchdog cron). Every market day it:
1. Fetches ~4,000 NASDAQ tickers
2. Downloads OHLCV data via yfinance
3. Scores each stock with the Qullamaggie logic
4. Assigns RS percentiles across the universe
5. Pushes top results to Firebase `/scanner/all_stocks` using `ref.update()` (**not** `ref.set()` — `set()` wipes all history)

### `backtest.py`
Reconstructs historical scanner signals using past price data. Run manually on the GCP VM.

```bash
python backtest.py                    # last 30 trading days
python backtest.py --days 180         # last 180 trading days
python backtest.py --date 2026-04-01  # specific date only
python backtest.py --update-returns   # fill forward returns for existing picks
```

Stores results in Firebase `/scanner/history/YYYY-MM-DD` — each day holds up to 200 top picks with all signals + forward returns (1W/2W/1M/2M/3M).

### `optimizer.py`
Statistical factor analysis. Reads all historical picks from Firebase and identifies which signals predict winning stocks. **Free — no AI involved.**

```bash
python optimizer.py                   # analyze 1-month returns
python optimizer.py --all-windows     # all return windows (1w/2w/1m/2m/3m)
python optimizer.py --window 2w       # specific window
```

Output: overall win rate, score band breakdown, factor lift table. Saves to Firebase `/scanner/optimization_reports/<timestamp>`.

**Cron**: runs automatically every Sunday at 4am.
```
0 4 * * 0 cd /home/scanner && /home/scanner/venv/bin/python optimizer.py --all-windows >> /tmp/optimizer_cron.log 2>&1
```

### `ai_optimizer.py`
Claude AI analysis. Calls Claude claude-opus-4-5 to analyze backtest data, suggest scoring weight changes, and shadow-backtests the proposal on 180 days of history before saving to Firebase for human approval. **Costs ~$0.10 per run.**

```bash
python ai_optimizer.py                # analyze 1m window, generate recommendation
python ai_optimizer.py --window 2w    # different return window
python ai_optimizer.py --all-windows  # run for every window, pick best improvement
python ai_optimizer.py --apply        # apply latest APPROVED recommendation to live_scanner.py
python ai_optimizer.py --check-and-run  # check Firebase flag, run if requested (cron mode)
```

**Cron**: polls Firebase every 5 minutes for on-demand requests from the UI.
```
*/5 * * * * cd /home/scanner && /home/scanner/venv/bin/python ai_optimizer.py --check-and-run >> /tmp/ai_check.log 2>&1
```

**Approval flow**:
1. Click "Run AI Analysis" in `/optimizer` tab → sets `/scanner/run_ai_requested = pending`
2. VM picks it up within 5 min → sets status = `running` → calls Claude → saves recommendation
3. UI shows result automatically via Firebase listener
4. Click "Approve" in UI → sets `/scanner/ai_recommendations/<id>/status = approved`
5. On VM: `python ai_optimizer.py --apply` → patches `live_scanner.py` (creates backup first)

### `smart_money.py`
Fetches smart money signals from SEC EDGAR:
- **Insider buying** (Form 4): last 14 days, purchases > $100K
- **Hedge fund holdings** (13F): top 10 funds — Berkshire, Pershing Square, Duquesne, Appaloosa, Third Point, Tiger Global, Baupost, Viking, Point72, Renaissance

CUSIP → ticker mapping via OpenFIGI API. Pushes to Firebase `/scanner/smart_money`.

```bash
python smart_money.py
```

### `app.py`
Flask web app deployed on Vercel. Auto-deploys from `main` branch.

---

## Web Pages

### `/` — Live Dashboard
Latest scan results from Firebase. Auto-refreshes. Cards show score, status, EMA stack, level, ATR, volume contraction, momentum, setup flags.

### `/analytics` — Historical Picks
All historical picks from Firebase `/scanner/history` with forward returns.
- **localStorage caching**: first load fetches all data, subsequent loads only fetch new dates
- **Sort**: by date, A–Z, score, 1W / 1M / 3M return
- **Search**: filter by ticker symbol

### `/smart-money` — Smart Money
Insider buying and hedge fund holdings. Updated by running `smart_money.py` on the VM.

### `/optimizer` — Optimizer
Two sections:

**Section 1 — Statistical Optimizer** (free, auto-runs weekly)
- Reads `optimizer.py` reports from Firebase
- Shows overall win rate, score band breakdown, factor lift table
- Auto-generates weight change suggestions for factors with >±5% win-rate lift
- Approve button saves to Firebase `/scanner/approved_weights`

**Section 2 — AI Analysis** (manual, ~$0.10/run)
- "Run AI Analysis" button triggers on-demand Claude analysis
- Live status: Queued → Running → Done (via Firebase listener)
- Shows Claude's reasoning, proposed weight changes, and projected win-rate improvement
- Approve / Reject buttons
- Approved → run `python ai_optimizer.py --apply` on VM to patch `live_scanner.py`

---

## Environments

| | Production | Staging |
|---|---|---|
| VM | `scanner-prod` | `scanner-staging` |
| Firebase | `stockscanner-f9f81` | `stockscanner-staging` |
| Vercel | Production deployment | Preview deployment |
| Branch | `main` | `fix/scanner-bugs` |

**Branch policy**: all changes go to `fix/scanner-bugs` first. Test on staging. Merge to `main` only with explicit approval.

---

## Cron Jobs (both VMs)

```bash
crontab -l
```

Should contain:
```
# Watchdog — restart scanner if it dies
*/5 * * * * pgrep -f live_scanner.py > /dev/null || sudo bash /home/scanner/start.sh restart >> /var/log/scanner_watchdog.log 2>&1

# Backtest — nightly (market days only)
0 22 * * 1-5 cd /home/scanner && /bin/bash -c 'set -a; source /home/scanner/.env; set +a; /home/scanner/venv/bin/python3 backtest.py --days 2' >> /var/log/backtest.log 2>&1

# Update returns — nightly
0 23 * * 1-5 cd /home/scanner && /bin/bash -c 'set -a; source /home/scanner/.env; set +a; /home/scanner/venv/bin/python3 backtest.py --update-returns' >> /var/log/backtest.log 2>&1

# Statistical optimizer — weekly (Sunday 4am)
0 4 * * 0 cd /home/scanner && /home/scanner/venv/bin/python optimizer.py --all-windows >> /tmp/optimizer_cron.log 2>&1

# AI trigger poller — every 5 minutes
*/5 * * * * cd /home/scanner && /home/scanner/venv/bin/python ai_optimizer.py --check-and-run >> /tmp/ai_check.log 2>&1
```

---

## Setup (new VM)

```bash
# Clone repo
git clone https://github.com/gili2205/stockscanner-.git /home/scanner
cd /home/scanner
git checkout main   # or fix/scanner-bugs for staging

# Virtual environment
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# Environment variables
cp env_template.txt .env
# Edit .env: FIREBASE_URL, FIREBASE_CRED, FLASK_ENV, ANTHROPIC_API_KEY

# Populate history
nohup venv/bin/python backtest.py --days 180 > /tmp/backtest.log 2>&1 &
venv/bin/python backtest.py --update-returns

# Run optimizer once to populate Optimizer tab
venv/bin/python optimizer.py --all-windows

# Set up cron jobs
crontab -e
# (add lines from Cron Jobs section above)

# Start live scanner
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
