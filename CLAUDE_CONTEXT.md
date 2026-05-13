# NASDAQ Scanner — Full Context Document
**For continuing this project in a new Claude thread**

Last updated: 2026-05-13

---

## 1. What This App Is

A production stock scanner built on the **Qullamaggie breakout methodology**. It continuously scans ~4,000 NASDAQ stocks, scores them by setup quality, stores historical picks in Firebase, and serves a live web dashboard.

**Live URLs:**
- Production dashboard: deployed on Vercel (main branch)
- Staging dashboard: separate Vercel preview deployment (`fix/scanner-bugs` branch)

---

## 2. Full Architecture

```
┌─────────────────────────────────────┐
│         GCP VM (scanner-prod)       │
│  live_scanner.py  — runs daily      │
│  backtest.py      — run via cron    │
│  optimizer.py     — weekly cron     │
│  ai_optimizer.py  — 5-min cron poll │
│  smart_money.py   — run manually    │
└──────────────┬──────────────────────┘
               │ Firebase Admin SDK
               ▼
┌─────────────────────────────────────┐
│      Firebase Realtime Database     │
│  /scanner/all_stocks               │
│  /scanner/history                  │
│  /scanner/first_seen               │
│  /scanner/smart_money              │
│  /scanner/optimization_reports     │
│  /scanner/ai_recommendations       │
│  /scanner/approved_weights         │
│  /scanner/run_ai_requested         │
└──────────────┬──────────────────────┘
               │ Firebase JS SDK
               ▼
┌─────────────────────────────────────┐
│     Vercel — Flask app (app.py)     │
│  /             live dashboard       │
│  /analytics    historical picks     │
│  /smart-money  insider + funds      │
│  /optimizer    statistical + AI     │
└─────────────────────────────────────┘
```

### Two Environments — Always Separate

| | Production | Staging |
|---|---|---|
| GCP VM | `scanner-prod` | `scanner-staging` |
| Firebase DB | `stockscanner-f9f81-default-rtdb` | `stockscanner-staging-default-rtdb` |
| Vercel | Production deployment | Preview deployment |
| Git branch | `main` | `fix/scanner-bugs` |

`app.py` reads `FLASK_ENV` from the `.env` and switches Firebase config automatically. Never share databases between environments.

---

## 3. Files and What They Do

### `live_scanner.py`
Runs on GCP VM via systemd + watchdog cron. Every market day:
1. Fetches ~4,000 NASDAQ tickers
2. Downloads OHLCV via yfinance
3. Scores each stock (Qullamaggie logic, BREAKOUT track, 0–95 pts)
4. Assigns RS percentiles across the universe
5. Pushes top results to Firebase `/scanner/all_stocks`

**CRITICAL**: Uses `ref.update(payload)` NOT `ref.set(payload)`.
`set()` replaces the entire `/scanner` node and **wipes all history**. This was a catastrophic bug found early on.

**Scoring weights** are defined in `DEFAULT_WEIGHTS` dict at the top of the file. `ai_optimizer.py --apply` patches these values when approved changes are applied.

### `backtest.py`
Reconstructs historical scanner signals. Run via cron and manually.

```bash
python backtest.py --days 180        # 180 trading days of history
python backtest.py --days 14         # quick test run
python backtest.py --date 2026-04-01 # single specific date
python backtest.py --update-returns  # fill in forward returns for existing picks
```

Stores top 200 picks per day in Firebase `/scanner/history/YYYY-MM-DD` with all signals + forward returns (1W/2W/1M/2M/3M).

Downloads price data in batches of 200 tickers with a 120s `ThreadPoolExecutor` timeout per batch.

### `optimizer.py`
Statistical factor analysis. **Free — no AI involved.** Reads Firebase history, identifies which signals predict winning stocks.

```bash
python optimizer.py --window 1m      # analyze 1-month returns
python optimizer.py --all-windows    # all return windows
```

Output: overall win rate, score band breakdown, factor lift table. Saves to Firebase `/scanner/optimization_reports/<timestamp>`.

**Cron**: weekly, Sunday 4am.

### `ai_optimizer.py`
Claude AI analysis. **Costs ~$0.10/run.** Calls Claude claude-opus-4-5 to analyze backtest data, suggest weight changes, shadow-backtests the proposal on 180 days, saves recommendation to Firebase for human approval.

```bash
python ai_optimizer.py               # analyze 1m window
python ai_optimizer.py --apply       # apply latest APPROVED rec to live_scanner.py
python ai_optimizer.py --check-and-run  # cron mode: check flag, run if pending
```

**`--check-and-run` flow** (runs every 5 min via cron):
1. Reads `/scanner/run_ai_requested` from Firebase
2. If `status == pending`: sets status = `running`, calls `run_analysis()`, sets status = `done`
3. If not pending: exits silently

**`--apply` flow**:
1. Reads latest approved (not yet applied) rec from `/scanner/ai_recommendations`
2. Creates backup of `live_scanner.py`
3. Patches `DEFAULT_WEIGHTS` values using regex
4. Marks rec as `applied` in Firebase

**Requires**: `ANTHROPIC_API_KEY` in `/home/scanner/.env`

### `smart_money.py`
Fetches smart money signals from SEC EDGAR:
- **Form 4**: insider purchases > $100K in last 14 days
- **13F**: holdings from 10 major hedge funds

CUSIP → ticker via OpenFIGI API. Pushes to Firebase `/scanner/smart_money`.

### `app.py`
Flask web app deployed on Vercel. Auto-deploys from `main` branch.

Key Flask routes:
- `GET /` — live dashboard
- `GET /analytics` — historical picks
- `GET /smart-money` — smart money
- `GET /optimizer` (also `/ai`) — optimizer tab
- `POST /api/run-ai-analysis` — sets Firebase flag to trigger AI run
- `POST /api/recommendations/<id>/approve` — approves an AI recommendation
- `POST /api/recommendations/<id>/reject` — rejects an AI recommendation
- `POST /api/optimizer-suggestions/approve` — approves statistical optimizer suggestions

Current version: `v3.1.1`

---

## 4. Scoring Logic (Current Weights)

### DEFAULT_WEIGHTS (in both `live_scanner.py` and `ai_optimizer.py` — keep in sync!)

```python
DEFAULT_WEIGHTS = {
    "breakout_momentum_max":   28,
    "breakout_ema_full":       22,
    "breakout_ema_partial":    12,
    "breakout_hh_hl_strong":    6,
    "breakout_hh_hl_ok":        3,
    "breakout_atr_max":        12,
    "breakout_vol_max":         8,
    "breakout_dist_max":       18,
    "breakout_liquidity_max":   7,
    "penalty_weak_ema":        18,
    "penalty_far_dist":        12,
    "penalty_neg_mom":         12,
    "penalty_high_vol_atr":     8,
    "threshold_ready":         72,
    "threshold_watch":         55,
}
```

### Status Labels
| Score | Status |
|-------|--------|
| ≥ 72 | READY |
| 55–71 | WATCH |
| < 55 | BUILDING (not surfaced) |

### Quality Gate
- Price ≥ $15
- Avg daily dollar volume ≥ $10M

---

## 5. Optimizer Tab — How It Works

### Section 1: Statistical Optimizer (free, automatic)
- Data comes from `optimizer.py` saving to `/scanner/optimization_reports/<timestamp>`
- UI reads reports via Firebase listener on page load
- Shows: overall stats, factor lift table, auto-generated suggestions
- Suggestions: factors with >+5% WR lift → increase weight 15-25%; <-5% lift → decrease 20-30%
- "Approve Suggestions" → POST `/api/optimizer-suggestions/approve` → saves to `/scanner/approved_weights`
- Then run `python ai_optimizer.py --apply` on VM to patch `live_scanner.py`

### Section 2: AI Analysis (manual, ~$0.10/run)
- "Run AI Analysis" button → POST `/api/run-ai-analysis` → sets Firebase `/scanner/run_ai_requested = {status: pending}`
- Button state driven by Firebase listener: pending → running → done (auto-updates)
- VM polls every 5 min, picks up `pending`, runs `ai_optimizer.py`, sets `done`
- Result appears in UI automatically
- "Approve" → status = `approved` in Firebase
- Then run `python ai_optimizer.py --apply` on VM

---

## 6. Git Workflow — Strict Rules

**NEVER push directly to `main` without staging verification.**

All changes go to `fix/scanner-bugs` first:
```bash
git checkout fix/scanner-bugs
# make changes, test on staging
git add <specific files>
git commit -m "description"
git push origin fix/scanner-bugs
```

Merge to `main` only after:
1. Changes tested on staging
2. Explicit user approval: "yes, merge it" or "push to main"

On staging VM: `git pull origin fix/scanner-bugs`
On prod VM: `git pull origin main`

**Always explain what you're going to change and where before making any changes. Wait for go-ahead.**

---

## 7. Cron Jobs (both VMs)

```
# Watchdog
*/5 * * * * pgrep -f live_scanner.py > /dev/null || sudo bash /home/scanner/start.sh restart >> /var/log/scanner_watchdog.log 2>&1

# Backtest (nightly, market days)
0 22 * * 1-5 cd /home/scanner && /bin/bash -c 'set -a; source /home/scanner/.env; set +a; /home/scanner/venv/bin/python3 backtest.py --days 2' >> /var/log/backtest.log 2>&1

# Update returns (nightly)
0 23 * * 1-5 cd /home/scanner && /bin/bash -c 'set -a; source /home/scanner/.env; set +a; /home/scanner/venv/bin/python3 backtest.py --update-returns' >> /var/log/backtest.log 2>&1

# Statistical optimizer (weekly)
0 4 * * 0 cd /home/scanner && /home/scanner/venv/bin/python optimizer.py --all-windows >> /tmp/optimizer_cron.log 2>&1

# AI trigger poller (every 5 min)
*/5 * * * * cd /home/scanner && /home/scanner/venv/bin/python ai_optimizer.py --check-and-run >> /tmp/ai_check.log 2>&1
```

---

## 8. Environment Variables (.env)

```
FIREBASE_URL=https://<project>-default-rtdb.firebaseio.com
FIREBASE_CRED=/home/scanner/firebase-credentials.json
FLASK_ENV=production   # or staging
ANTHROPIC_API_KEY=sk-ant-...   # required for ai_optimizer.py
```

Production Firebase: `stockscanner-f9f81-default-rtdb`
Staging Firebase: `stockscanner-staging-default-rtdb`

---

## 9. VM Operations

### Running scripts
```bash
cd /home/scanner

# Always use venv python
/home/scanner/venv/bin/python optimizer.py --all-windows
/home/scanner/venv/bin/python ai_optimizer.py --check-and-run

# Run in background
nohup /home/scanner/venv/bin/python backtest.py --days 180 > /tmp/backtest180.log 2>&1 &

# Check if running
ps aux | grep backtest

# Kill if stuck
pkill -f backtest.py
```

### Pulling latest code
```bash
cd /home/scanner && git pull origin fix/scanner-bugs   # staging
cd /home/scanner && git pull origin main               # production
```

If git pull fails due to permissions:
```bash
sudo chown -R $(whoami):$(whoami) /home/scanner/.git && git pull
```

If VM is on detached HEAD:
```bash
git checkout main && git pull origin main
```

### Checking Firebase connectivity
```bash
curl -s "$(grep FIREBASE_URL /home/scanner/.env | cut -d= -f2)/.json?shallow=true"
# Expected: {"scanner":true}
```

### Checking cron logs
```bash
tail -f /tmp/optimizer_cron.log
tail -f /tmp/ai_check.log
tail -f /var/log/backtest.log
```

### Installing new packages
```bash
/home/scanner/venv/bin/pip install <package>
```

---

## 10. Lessons Learned — What NOT To Do

### 10.1 The `ref.set()` vs `ref.update()` Disaster
`live_scanner.py` was using `ref.set(payload)` where `ref = db.reference("/scanner")`. Every scan wiped ALL of `/scanner` — history, first_seen, everything.

**Fix**: `ref.set()` → `ref.update()`. Always use `update()` unless you want to wipe a node.

### 10.2 `\'` Inside Python Triple-Quoted Strings
`\'` inside a `"""` string is just `'` — the backslash is consumed by Python. This broke JS strings in the Optimizer HTML.

**Fix**: Use `data-id` attributes instead of escaped quotes in onclick handlers. Or use `\\n` to get `\n` in JS regex (`/\\n/g` in Python source → `/\n/g` in output).

### 10.3 `\n` in Python Triple-Quoted Strings Used in JS
`\n` inside a Python `"""` string is a literal newline. If used in a JS regex like `/\n/g`, the rendered HTML has a newline inside the regex, causing `SyntaxError: Invalid regular expression: missing /`.

**Fix**: Use `\\n` in Python source to produce `\n` in JS output.

### 10.4 Don't Test on Production Before Staging
All VM operations (git pull, pip install, cron setup, script runs) must be done on staging first. Mistakes on production affect live users.

### 10.5 VM Network Issues
If the staging VM loses network (Firebase DNS fails), the running process hangs forever and can't be killed via SSH. Solution: stop and start the VM from GCP Console, verify network with `ping google.com` before running any scripts.

### 10.6 The Multiprocessing Overengineering
Replaced working `ThreadPoolExecutor` code with `multiprocessing`. Introduced deadlocks, queue overflows, and firebase double-init crashes. Always revert to what works in production.

### 10.7 Don't Test Firebase Reachability with `curl` When App Uses a Library
`curl` returning "Too Many Requests" doesn't mean yfinance is blocked — yfinance uses its own session and headers.

---

## 11. Pending / Future Work

- [ ] Add `smart_money.py` cron job (every 4 hours) on both VMs
- [ ] Fix insider buys (Form 4 returning 0 buys) in `smart_money.py`
- [ ] Test "Approve" flow end-to-end: approve AI rec → run `--apply` → verify live_scanner.py patched correctly
- [ ] Add Anthropic credits to enable AI analysis button (console.anthropic.com)
- [ ] Consider adding more return windows to optimizer (6M, 1Y) once enough history exists

---

## 12. Return Windows

| Label | Trading days | Notes |
|-------|-------------|-------|
| 1W | 5 | Available ~1 week after pick |
| 2W | 10 | |
| 1M | 21 | Best for optimizer analysis |
| 2M | 42 | |
| 3M | 63 | |
| 6M | 126 | |
| 1Y | 252 | Long-term |

Run `python backtest.py --update-returns` periodically to fill in new windows as time passes.

---

## 13. Current State (as of 2026-05-13)

- ✅ All code on `main` branch (fix/scanner-bugs merged)
- ✅ Vercel production auto-deployed
- ✅ Both VMs have cron jobs set up (optimizer weekly + AI poller 5-min)
- ✅ Staging optimizer ran → data in Firebase → Section 1 showing data
- ✅ Production optimizer ran → data in Firebase → Section 1 showing data
- ⏳ AI Analysis requires Anthropic credits before it can run
- ⏳ `smart_money.py` Form 4 insider buys returning 0 (known bug, deferred)
