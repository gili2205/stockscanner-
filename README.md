# NASDAQ Momentum Scanner

A production stock scanner built on the Qullamaggie breakout methodology. Runs continuously on a GCP VM, stores results in Firebase, and serves a live web dashboard on Vercel.

---

## Architecture

```
GCP VM (scanner-prod / scanner-staging)
  ├── live_scanner.py   — runs every market day, scores all NASDAQ stocks, pushes to Firebase
  ├── backtest.py       — reconstructs historical signals + forward returns, stores in Firebase
  ├── optimizer.py      — factor analysis: which signals actually predict winning stocks
  ├── ai_optimizer.py   — Claude-powered weight tuner: analyzes history, proposes changes, shadow-backtests
  └── smart_money.py    — fetches insider buys (Form 4) + hedge fund holdings (13F) from SEC EDGAR

Firebase Realtime Database
  ├── /scanner/all_stocks              — latest scan results (live dashboard)
  ├── /scanner/history                 — historical picks with forward returns (analytics)
  ├── /scanner/first_seen              — when each ticker was first flagged
  ├── /scanner/smart_money             — insider + institutional data
  ├── /scanner/optimization_reports    — weekly factor analysis results
  ├── /scanner/ai_recommendations      — Claude-suggested weight changes (pending / approved / applied)
  ├── /scanner/optimizer_suggestions   — stat optimizer accepted suggestions (pending / applied)
  ├── /scanner/run_ai_requested        — flag to trigger AI analysis from the UI
  └── /scanner/experiments/            — isolated experiment results (see Experiment Framework below)
        └── {experiment_name}/
              ├── meta     — scoring_version, created_at, status
              ├── history  — picks scored with experimental logic
              └── report   — optimizer output for this experiment

Vercel (Flask app — app.py)
  ├── /            — live dashboard (latest scan results)
  ├── /analytics   — historical picks table with returns, sort, search
  └── /smart-money — insider buying + hedge fund holdings
```

Two environments — staging and production — with separate Firebase databases and GCP VMs. `FLASK_ENV=staging` switches the app to the staging Firebase config.

---

## Scoring Logic

### Three scores (v4)

| Score | What it measures | Max | Color |
|-------|-----------------|-----|-------|
| **Buy Now** | √(Quality × Setup) — geometric mean. Primary ranking metric. | 100 | Green ≥65 / Amber 40-64 / Red <40 |
| **Quality** | How strong is the stock? RS percentile, EMA trend, momentum 1M+3M, HH/HL structure, fundamentals, liquidity | 100 | Blue |
| **Setup** | Is the entry timing good? EMA alignment, ATR coil, vol contraction, distance to level, RSI, vol ratio | 100 | Orange |

**Formula:** `Buy Now = √(Quality × Setup)`. Forces both dimensions to be good simultaneously.
- If Quality=80, Setup=80 → Buy Now=80 ✓
- If Quality=80, Setup=10 → Buy Now=28 (don't enter yet)
- If Quality=10, Setup=90 → Buy Now=30 (great setup, bad stock)

### Status Labels
| Buy Now | Status | Meaning |
|---------|--------|---------|
| ≥ 65 | READY | Strong stock in a good setup |
| ≥ 40 | WATCH | Pattern forming — wait for trigger |
| < 40 | BUILDING | Not yet ready |

Every pick stored by backtest.py carries a `scoring_version` field (e.g. `"v4_quality_setup"`). Bump `SCORING_VERSION` in backtest.py whenever the scoring logic changes.

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
3. Scores each stock with the two-track Qullamaggie logic
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

# Run as an experiment (does NOT touch production history)
python backtest.py --days 60 --experiment my_experiment_name
```

Stores results in Firebase `/scanner/history/YYYY-MM-DD` — each day holds up to 200 top picks with all signals + forward returns (1W / 2W / 1M / 2M / 3M).

**Important**: Downloads price data in batches of 25 tickers using a manual `ThreadPoolExecutor` with a 90-second timeout per batch. Uses `shutdown(wait=False)` to abandon hung yfinance threads immediately instead of blocking on exit. Cache writes are atomic: data is written to `.price_cache.tmp` first, then renamed to `.price_cache.pkl` — rename is atomic on Linux/macOS and prevents cache corruption if the process is killed mid-write.

### `optimizer.py`
Factor analysis engine. Reads all historical picks from Firebase and identifies which signals predict winning stocks.

```bash
# Analyze 1-month forward returns (default)
python optimizer.py

# Analyze all return windows
python optimizer.py --all-windows

# Specific window: 1w, 2w, 1m, 2m, 3m
python optimizer.py --window 2w

# Analyze an experiment instead of production data
python optimizer.py --experiment my_experiment_name

# Compare an experiment side-by-side with production (PROMOTE / REJECT verdict)
python optimizer.py --compare my_experiment_name
```

Output: overall win rate, performance by score band, factor analysis table sorted by win-rate lift. Saves to Firebase `/scanner/optimization_reports/<timestamp>` and `/tmp/optimizer_report.json`.

Runs automatically every **Sunday at 4 AM** via cron on both VMs.

### `ai_optimizer.py`
Claude-powered weight tuner. Reads historical performance, calls Claude to suggest scoring weight changes, runs a shadow backtest to project the impact, and saves the recommendation to Firebase for human approval.

```bash
# Analyze and generate a recommendation
python ai_optimizer.py

# Run for all return windows, pick the best improvement
python ai_optimizer.py --all-windows

# Apply latest APPROVED recommendation to live_scanner.py
python ai_optimizer.py --apply

# Check Firebase flag and run if requested (used by cron every 5 min)
python ai_optimizer.py --check-and-run
```

Flow:
1. Loads last 180 days of picks with return data
2. Runs factor analysis + score band breakdown
3. Calls Claude with the performance data → Claude suggests specific weight changes
4. Shadow-backtests the proposed weights against the same historical picks (fast estimate)
5. Saves recommendation to `/scanner/ai_recommendations/{timestamp}` with status `pending`
6. Human reviews in the Optimizer UI and clicks **Approve** → status set to `approved` via Firebase JS SDK
7. Cron (`--check-and-run`, every 5 min) detects the approved recommendation, patches `live_scanner.py`, restarts the scanner, and marks it `applied` — no manual VM step needed

Every recommendation is tagged with an `experiment_id` (e.g. `ai_2026-05-14_10-30-00`) that links to the experiment framework for real backtest verification.

`--check-and-run` (cron every 5 min, protected by `flock` to prevent overlapping instances) now runs in order:
1. **Apply approved AI recommendations** from `/scanner/ai_recommendations` (step 0 — highest priority)
2. **Apply stat suggestions** from `/scanner/optimizer_suggestions` (accepted in the Optimizer UI)
3. **Restart scanner** if anything was applied (kills live_scanner.py; watchdog restarts it within 5 min)
4. **Run AI analysis** if `/scanner/run_ai_requested` flag is set to `pending`

All browser-triggered writes use the Firebase JS SDK directly (not Flask REST API) to avoid auth token issues. Firebase security rules must allow `.write: true` on: `optimizer_suggestions`, `run_ai_requested`, `ai_recommendations`, `approved_weights`.

### `smart_money.py`
Fetches smart money signals from SEC EDGAR:
- **Insider buying** (Form 4): last 14 days, open-market purchases > $100K
- **Hedge fund holdings** (13F): top 10 funds — Berkshire, Pershing Square, Duquesne, Appaloosa, Third Point, Tiger Global, Baupost, Viking, Bridgewater, Renaissance

Uses EDGAR quarterly full-index to find Form 4 filings, tries `ownership.xml` directly (standard filename) before falling back to directory listing. CUSIP → ticker mapping via OpenFIGI API. Pushes to Firebase `/scanner/smart_money`.

```bash
python smart_money.py            # fetch both insiders + institutions
python smart_money.py --insiders      # insiders only
python smart_money.py --institutions  # institutions only
```

---

## Experiment Framework

Use this whenever you want to test a scoring logic change before it goes live. The framework isolates experiment data from production, runs a real backtest, and produces a quantitative PROMOTE / REJECT verdict.

### When to use it
- You want to rebalance scoring weights (e.g. reduce momentum, increase ATR compression)
- Claude's `ai_optimizer` has suggested changes and you want to verify with a real backtest
- You're adding a new signal and want to measure its impact before shipping

### Full workflow

```
1. BRANCH    git checkout fix/scanner-bugs
             (all experiments happen on staging first)

2. EDIT      Modify score_stock_historical() in backtest.py
             Bump SCORING_VERSION to the next version (e.g. "v2_momentum_reweight")

3. BACKTEST  python backtest.py --days 60 --experiment v2_momentum_reweight
             → writes to /scanner/experiments/v2_momentum_reweight/history
             → saves metadata to /scanner/experiments/v2_momentum_reweight/meta
             → does NOT touch /scanner/history or /scanner/first_seen

4. WAIT      Give the experiment picks ~1 week of forward returns before comparing
             (or use existing production history as baseline if it overlaps in time)

5. ANALYZE   python optimizer.py --experiment v2_momentum_reweight
             → factor analysis on experiment picks only

6. COMPARE   python optimizer.py --compare v2_momentum_reweight
             → side-by-side production vs experiment
             → prints PROMOTE / REJECT verdict with win rate and avg return delta

7. PROMOTE   If verdict is PROMOTE:
               a. Merge scoring change to live_scanner.py (for live picks)
               b. Bump SCORING_VERSION in backtest.py
               c. Merge fix/scanner-bugs → main
               d. Pull on prod VM + restart scanner
             If verdict is REJECT:
               Discard the experiment, try a different approach
```

### Firebase experiment paths

```
/scanner/experiments/{experiment_name}/
  meta/
    created_at      — ISO timestamp
    scoring_version — e.g. "v2_momentum_reweight"
    n_days          — days backtested
    status          — "running" | "complete"
  history/
    {YYYY-MM-DD}/
      {TICKER}: { score, ema_stack, atr, ... returns: {1w, 1m, ...} }
  report/
    (written by optimizer.py --experiment)
```

### AI optimizer experiments

When `ai_optimizer.py` runs an analysis, it generates an `experiment_id` (e.g. `ai_2026-05-14_10-30-00`). After approving and applying the recommendation:

```bash
# Verify the change with a real backtest
python backtest.py --days 60 --experiment ai_2026-05-14_10-30-00
python optimizer.py --compare ai_2026-05-14_10-30-00
```

The shadow backtest inside ai_optimizer is a fast estimate (re-scores existing picks). The real backtest above is the ground truth.

### Scoring version history

| Version | Description | File |
|---------|-------------|------|
| `v1_qullamaggie` | Original Qullamaggie formula (EMA+HH/HL+ATR+Level+Vol) | backtest.py (retired) |
| `v2_base_setup` | Rebalanced: ATR compression ratio + dist-to-level + 3M momentum + vol contraction | backtest.py (current) |
| `v2_two_track` | Two-track BREAKOUT+CATALYST scoring with fundamentals | live_scanner.py |

---

## Web Pages

### `/` — Live Dashboard
Shows the latest scan results from Firebase. Auto-refreshes. Cards show score, status, EMA stack, level, ATR, volume contraction, momentum, and setup flags. Filter chips: sector, size (market cap), risk, setup, momentum, streak (days on list).

### `/analytics` — Historical Picks
Shows all historical picks from Firebase `/scanner/history` with forward returns.
- **localStorage caching**: first load fetches all data, subsequent loads only fetch new dates (fast)
- **Sort**: by date, A–Z, score, 1W / 1M / 3M return
- **Search**: filter by ticker symbol

### `/smart-money` — Smart Money
Insider buying and hedge fund holdings in one tab. Updated by running `smart_money.py` on the VM.

### `/optimizer` — Optimizer
- **Statistical Optimizer**: factor analysis showing which signals predict winners. Generates a consolidated "Recommended Scoring Changes" card with one Accept button.
- **Accepting suggestions**: writes to Firebase `/scanner/optimizer_suggestions` via the Firebase JS SDK (client-side, avoids Flask REST API 401 auth issues). The VM cron (`ai_optimizer.py --check-and-run`, every 5 min) patches `live_scanner.py` and restarts the scanner automatically.
- **State tracking**: localStorage remembers accepted suggestions (key: `optimizer_queued_{sortedParams}`) so revisiting shows "Queued" state instead of the Accept button. Clears when Firebase confirms `applied=true`.
- **AI Analysis**: Claude-powered analysis (requires Anthropic credits). Run button sets `/scanner/run_ai_requested` flag in Firebase; cron picks it up.

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

## Firebase Security Rules

Both staging and production databases use these rules:

```json
{
  "rules": {
    ".read": true,
    ".write": false,
    "scanner": {
      "watchlist":              { ".write": true },
      "sentiment_universe":    { "pinned": { ".write": true } },
      "optimizer_suggestions": { ".write": true },
      "run_ai_requested":      { ".write": true }
    }
  }
}
```

The web app (Firebase JS SDK in browser) writes directly to these paths. Flask REST API calls on the server have no auth token and will receive 401 on write-protected paths — use client-side JS SDK writes for user-triggered actions instead.

---

## Cron Schedule (both VMs)

| Schedule | Command | Purpose |
|----------|---------|---------|
| Weeknights 10 PM | `backtest.py --days 2` | Fill in last 2 trading days |
| Weeknights 11 PM | `backtest.py --update-returns` | Fill forward returns |
| Sundays 4 AM | `optimizer.py --all-windows` | Weekly factor analysis |
| Every 5 min | `ai_optimizer.py --check-and-run` | AI analysis when requested |

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
