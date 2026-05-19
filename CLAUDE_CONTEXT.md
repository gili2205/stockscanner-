# NASDAQ Scanner — Full Context Document
**For continuing this project in a new Claude thread**

Last updated: 2026-05-19 — v4.4.6

---

## Version Tracking (ALWAYS follow these rules)

| Component | Version | Notes |
|-----------|---------|-------|
| `app.py` (Flask app) | **v4.4.6** | Stat optimizer rows UI; bottom-line impact card; negative sim suppression |
| `backtest.py` | **v5_ema_gate_only** | EMA removed from Setup/Technical scoring (gate only); experiment branch |
| `optimizer.py` | — | Deduplicates to first-seen ticker (matches analytics dashboard) |
| `ai_optimizer.py` | — | Full auto-apply: approved AI recs + stat suggestions via cron; marks stat_recommendations batch applied |
| `smart_money.py` | — | No version constant; track via git |
| Last updated | **2026-05-19** | v4.4.6 |

### Version bump rules
- **Patch** (v4.0.**x**): bug fix, UI tweak, copy change
- **Minor** (v4.**x**.0): new feature, new score component, new data source
- **Major** (**vX**.0.0): scoring system redesign, architecture change
- **Always** update `VERSION` in `app.py` AND this file on every meaningful commit
- `SCORING_VERSION` in `backtest.py` must be bumped any time `score_stock_historical()` changes — format: `"vN_short_description"`

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
│         GCP VM (scanner-staging)    │
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
│  /scanner/sentiment                │
│  /scanner/smart_money              │
│  /scanner/experiments/{NAME}/      │
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
│  /sentiment    news sentiment       │
│  /smart_money  insider + funds      │
└─────────────────────────────────────┘
```

### Two Environments — Always Separate

| | Production | Staging |
|---|---|---|
| GCP VM | `scanner-prod` | `scanner-staging` (user: gilih2205) |
| Firebase DB | `stockscanner-f9f81-default-rtdb` | `stockscanner-staging-default-rtdb` |
| Vercel | Production deployment | Preview deployment |
| Git branch | `main` | `fix/scanner-bugs` |

`app.py` reads `FLASK_ENV` from the `.env` and switches Firebase config automatically. Never share databases between environments.

### Branch rules
- `fix/scanner-bugs` → **staging** (Vercel auto-deploys)
- `main` → **production** (only merge when staging is verified)

---

## 3. Scoring System (v4)

### Three scores shown on every card

| Score | What it measures | Max | Color |
|-------|-----------------|-----|-------|
| **Score (Buy Now)** | Geometric mean of Quality × Setup. Requires BOTH to be good. Primary ranking metric. | 100 | Green ≥65 / Amber 40-64 / Red <40 |
| **Quality** | How strong is this stock? RS percentile, EMA trend, 1M+3M momentum, HH/HL structure, fundamentals, liquidity | 100 | Blue |
| **Setup** | Is the entry timing good right now? EMA alignment, ATR coil, vol contraction, distance to level, HH/HL into base, RSI, vol ratio, pattern bonus, earnings penalty | 100 | Orange |

**Formula:** `Buy Now = √(Quality × Setup)`
- If Quality=80, Setup=80 → Buy Now=80 ✓
- If Quality=80, Setup=10 → Buy Now=28 (don't enter yet)
- If Quality=10, Setup=90 → Buy Now=30 (great setup, bad stock)

### Quality Score components (max 100)
| Factor | Points | Signal |
|--------|--------|--------|
| RS Percentile | 0–30 | ≥90=30, ≥80=22, ≥70=14, ≥60=7 |
| EMA Stack | 0–12 | full=12, partial=7, weak=2 |
| Momentum 1M | 0–13 | ≥20%=13, ≥10%=10, ≥5%=6, ≥0%=2 |
| Momentum 3M | 0–13 | ≥40%=13, ≥20%=9, ≥8%=5, ≥0%=1 |
| HH/HL structure | 0–10 | ≥0.85=10, ≥0.70=7, ≥0.55=4 |
| Fundamentals | 0–12 | score_fundamental × 0.12 |
| Liquidity | 0–10 | ≥$200M=10, ≥$50M=7, ≥$20M=4, else=2 |

### Setup Score components (max 100)
| Factor | Points | Signal |
|--------|--------|--------|
| EMA Stack | 0–20 | full=20, partial=10, weak=2 — trend must align for entry |
| ATR Coil | 0–20 | ≤0.15=20, ≤0.25=15, ≤0.35=10, ≤0.50=3 |
| Vol Contraction | 0–18 | ≤50%=18, ≤65%=12, ≤80%=6 |
| Distance to Level | 0–14 | ≤1%=14, ≤2%=10, ≤3.5%=6, ≤6%=2 |
| HH/HL into base | 0–8 | ≥0.85=8, ≥0.70=5, ≥0.55=2 |
| RSI | 0–8 | ≤55=8, ≤65=6, ≤75=3 |
| Vol Ratio | 0–7 | ≥3x=7, ≥2x=4, ≥1.5x=2 |
| Pattern bonus | 0–5 | pre_breakout=5, bull_flag=4 |
| **Earnings penalty** | −20/−10 | ≤7 days=−20, ≤14 days=−10 |

### Status labels (from live_scanner.py — based on OLD blended score)
```python
status = "READY" if score >= 72 else "WATCH" if score >= 55 else "BUILDING"
```
> Status still uses old 3-layer blended score thresholds. BUILDING does NOT mean bad — it means old score < 55. Not yet updated to use Buy Now score.

### Stop loss calculation
```javascript
stopDist = clamp(0.02 / ATR, 3%, 9%)
```
- Low ATR (stable) → wide stop up to 9% (give it room)
- High ATR (volatile) → tight stop down to 3% (cut fast)
- **Inverse logic: high risk = tight stop, low risk = wide stop**

### Important: separate script scopes in app.py
Dashboard and analytics are separate Flask routes with their own `<script>` blocks. Functions defined in one are NOT available in the other. `computeQualityScore`, `computeSetupScore`, and `computeBuyNow` must be duplicated verbatim in both script blocks.

---

## 4. Files and What They Do

### `live_scanner.py`
Runs on GCP VM. Every market day:
1. Fetches ~4,000 NASDAQ tickers
2. Downloads OHLCV via yfinance
3. Scores each stock (Qullamaggie logic, 0–95 pts)
4. Assigns RS percentiles across the universe
5. Pushes top results to Firebase `/scanner/all_stocks`

**CRITICAL**: Uses `ref.update(payload)` NOT `ref.set(payload)`.
`set()` replaces the entire `/scanner` node and **wipes all history**.

### `backtest.py` (SCORING_VERSION: v4_quality_setup)
Reconstructs historical scanner signals. Experiment framework isolates runs. Atomic cache writes: writes to `.price_cache.tmp` then renames to `.price_cache.pkl` (atomic on Linux/macOS, prevents corruption on kill). ThreadPoolExecutor fix: uses manual executor + `shutdown(wait=False)` to abandon hung yfinance threads immediately instead of blocking on exit. Batch size 25 tickers, 90s timeout.

```bash
# Production
/home/scanner/venv/bin/python /home/scanner/backtest.py --days 30

# Experiment (isolated, writes to /scanner/experiments/{NAME})
nohup /home/scanner/venv/bin/python /home/scanner/backtest.py \
  --experiment v4_quality_setup --days 180 \
  > /home/scanner/backtest_v4.log 2>&1 &

# Monitor
tail -f /home/scanner/backtest_v4.log

# Delete an experiment
/home/scanner/venv/bin/python /home/scanner/backtest.py \
  --delete-experiment v3_three_layer
```

Crash protection (v4):
- Firebase writes retry 4× with exponential backoff
- Per-day `try/except`: one bad day → logged, continues
- Per-ticker `try/except`: one bad stock → skipped
- KeyboardInterrupt: clean exit, re-run resumes from last unwritten day
- 10 consecutive day failures → aborts with clear error
- **Always use `nohup`** to protect against SSH disconnect

Scoring differences vs live:
| Factor | Live scanner | Backtest |
|--------|-------------|----------|
| RS percentile | Cross-stock comparison | Proxy from 3M momentum bucket |
| Fundamentals | yfinance real-time | 0 (no per-date data) |
| Earnings penalty | days_to_earnings from yfinance | Not applied |
| RSI | From API | Computed from OHLCV |

### `optimizer.py`
Statistical factor analysis. Free — no AI involved.

```bash
python optimizer.py --window 1m
python optimizer.py --all-windows
```

### `ai_optimizer.py`
Claude AI analysis. ~$0.10/run.

```bash
python ai_optimizer.py --check-and-run   # cron mode
python ai_optimizer.py --apply           # apply approved rec
```

`--check-and-run` now: (0) auto-applies any approved AI recommendations from Firebase `/scanner/ai_recommendations`, (1) auto-applies any pending stat suggestions from Firebase `/scanner/optimizer_suggestions`, (2) restarts `live_scanner.py` via watchdog if anything was applied, (3) THEN checks for new AI analysis requests. Both `apply_approved_recommendation()` and `apply_stat_suggestions()` return True/False. `PATCH_PATTERNS` use `ta+=` to match actual `live_scanner.py` variable names. User never needs to run `--apply` manually — cron handles everything within 5 min.

### `smart_money.py`
- ARK holdings (ETF filings from ark-funds.com)
- Insider buys (Form 4 from SEC EDGAR — buys > $100K)
- Activist filings (13D/13G)
- 13F institutional holdings (major hedge funds)

### `app.py` (VERSION: v4.3.1)
Flask web app on Vercel. Key routes:
- `GET /` — live dashboard
- `GET /analytics` — historical picks (experiment-aware)
- `GET /sentiment` — news sentiment
- `GET /smart_money` — smart money
- `GET /optimizer` — optimizer tab with full auto-apply flow

Optimizer tab: single consolidated suggestion card with one Accept button. Writes suggestions directly via Firebase JS SDK (`fdb.ref('/scanner/optimizer_suggestions/').set()`). localStorage tracks "queued" state across refreshes. Shows Accept / Queued / Applied states based on localStorage and Firebase.

### `score_patch.py`
Patches scores in Firebase without full rescan.

### `sentiment.py`
- Finnhub `/company-news` (free tier)
- Buzz score: log-normalized article count 0–100
- Expanded universe: scanner picks + IPO calendar + history

### `config.py`
Shared constants (SCORE_READY=85, SCORE_WATCH=70, etc.)

---

## 5. Experiments

### v5_ema_gate_only (current — staging only)
- **Status**: Ready to run as of 2026-05-19
- **SCORING_VERSION**: `v5_ema_gate_only`
- **Firebase path**: `/scanner/experiments/v5_ema_gate_only/`
- **Change**: EMA full/partial no longer awards points in Technical (ta) or Setup (t) scores. EMA kept in Quality (q) score only. Weak EMA penalty kept.
- **Rationale**: Optimizer data shows ~97% of picks have full EMA in a bull market → not a discriminating signal. EMA full shows −15% WR lift at 1m window. ATR compression and distance-to-level are better entry timing signals.
- **Run command**:
  ```bash
  nohup /home/scanner/venv/bin/python backtest.py --days 60 --experiment v5_ema_gate_only > /tmp/exp_v5.log 2>&1 &
  ```
- **Compare command** (after forward returns fill in):
  ```bash
  /home/scanner/venv/bin/python optimizer.py --compare v5_ema_gate_only
  ```
- **Promote if**: WR and avg return improve vs production baseline

### v4_quality_setup (completed)
- **Status**: Complete
- **SCORING_VERSION**: `v4_quality_setup`
- **Firebase path**: `/scanner/experiments/v4_quality_setup/`
- **Purpose**: Validate Quality/Setup/BuyNow scoring vs old blended score

---

## 6. Pages & Features

### Dashboard (/)
- Live scanner picks from Firebase `/scanner/all_stocks`
- Cards show: Score (top right), Quality + Setup bars (inside card)
- Sort: 🎯 Score | 💎 Quality | 🎣 Setup | 📅 Date | 🔤 A-Z
- Filter chips: Risk, Setup, Momentum, Sector, Streak
- Score Focus chips: Score / Quality / Setup

### Analytics (/analytics)
- History from Firebase `/scanner/history` or experiment path
- Table columns: Score (green) | Quality (blue) | Setup (orange) | returns
- KPI cards: win rate, avg return, expectancy

### Sentiment (/sentiment)
- Buzz score + bullish/bearish/neutral from keyword analysis

### Smart Money (/smart_money)
- ARK + insider + activist + 13F
- Top Conviction: tickers in multiple smart money sources

### Optimizer (/optimizer)
- Statistical factor analysis showing which signals predict winners
- Generates a consolidated "Recommended Scoring Changes" card with one Accept button
- Accepting suggestions writes directly to Firebase `/scanner/optimizer_suggestions` via JS SDK (avoids 401 auth issues with Flask REST API)
- VM cron (`ai_optimizer.py --check-and-run`, every 5 min) auto-applies pending suggestions, patches `live_scanner.py`, and restarts the scanner
- localStorage tracks accepted state across page refreshes; clears when Firebase confirms `applied=true`

---

## 7. Git Workflow — Strict Rules

**NEVER push directly to `main` without staging verification.**
**NEVER create new branches. Use `fix/scanner-bugs` for staging.**
**NEVER merge to `main` without explicit user approval. Always wait for the user to say "merge to main" or "promote to production".**

All changes go to `fix/scanner-bugs` first:
```bash
git checkout fix/scanner-bugs
git add <specific files>
git commit -m "description"
git push origin fix/scanner-bugs
```

Merge to `main` only after explicit user approval.

**Vercel auto-deploys `app.py` changes — never tell the user to git pull for UI changes.**

### Promoting to production — FULL CHECKLIST

**Go through every item below. Do NOT skip steps even if they seem unnecessary.**

#### 1. Git
```bash
git checkout main
git merge fix/scanner-bugs
git push origin main
git checkout fix/scanner-bugs   # always return to staging branch
```

#### 2. Vercel (automatic)
- Production Vercel auto-deploys when `main` is pushed — no action needed
- Verify deployment succeeded at vercel.com dashboard

#### 3. Production VM
```bash
# SSH in (use GCP console if needed)
cd /home/scanner
git pull origin main

# Restart scanner ONLY if live_scanner.py changed in this release
sudo bash /home/scanner/start.sh restart
```

#### 4. Firebase Rules — ALWAYS CHECK
Go to **Firebase Console → stockscanner-f9f81-default-rtdb → Rules**
Compare staging rules (stockscanner-staging-default-rtdb) with production rules.
Any new path added to staging rules must also be added to production.

**Current required rules (both staging and production):**
```json
{
  "rules": {
    ".read": true,
    ".write": false,
    "scanner": {
      "watchlist":              { ".write": true },
      "sentiment_universe":    { "pinned": { ".write": true } },
      "optimizer_suggestions": { ".write": true },
      "run_ai_requested":      { ".write": true },
      "ai_recommendations":    { ".write": true },
      "approved_weights":      { ".write": true },
      "stat_recommendations":  { ".write": true }
    }
  }
}
```

#### 5. Cron Jobs — check if changed
```bash
crontab -l   # on production VM — compare with section 9 of this doc
# If cron changed on staging, apply same change to production crontab
```

#### 6. Environment Variables — check if changed
```bash
cat /home/scanner/.env   # verify all new env vars are present
```

#### 7. Tell the user what manual steps they need to do
Always explicitly list which of steps 4–6 require manual action before declaring "done".

---

## 8. VM Commands

**IMPORTANT: The repo root on the VM is `/home/scanner/` — NOT `/home/scanner/stockscanner` or any subdirectory.**
All scripts (`ai_optimizer.py`, `live_scanner.py`, etc.) live directly in `/home/scanner/`.

```bash
# SSH
ssh gilih2205@scanner-staging

# Always cd first — repo root IS /home/scanner
cd /home/scanner

# Pull latest
git pull origin fix/scanner-bugs

# Run scripts (always use venv python)
/home/scanner/venv/bin/python /home/scanner/live_scanner.py
/home/scanner/venv/bin/python /home/scanner/smart_money.py --insiders
/home/scanner/venv/bin/python /home/scanner/sentiment.py

# Check running processes
ps aux | grep python

# View logs
tail -f /home/scanner/backtest_v4.log
```

---

## 9. Cron Jobs (staging VM)

```
# Backtest (nightly, market days) — sources .env for Firebase creds
0 22 * * 1-5 cd /home/scanner && /bin/bash -c 'set -a; source /home/scanner/.env; set +a; /home/scanner/venv/bin/python backtest.py --days 2 >> /tmp/backtest_cron.log 2>&1'

# Update returns (nightly)
0 23 * * 1-5 cd /home/scanner && /bin/bash -c 'set -a; source /home/scanner/.env; set +a; /home/scanner/venv/bin/python backtest.py --update-returns >> /tmp/backtest_cron.log 2>&1'

# Statistical optimizer (weekly, Sunday 4am)
0 4 * * 0 cd /home/scanner && /home/scanner/venv/bin/python optimizer.py --all-windows >> /tmp/optimizer_cron.log 2>&1

# AI trigger poller (every 5 min) — flock prevents overlapping instances
*/5 * * * * flock -n /tmp/ai_check.lock bash -c 'cd /home/scanner && /home/scanner/venv/bin/python ai_optimizer.py --check-and-run >> /tmp/ai_check.log 2>&1'

# Watchdog — restart live_scanner if not running
*/5 * * * * pgrep -f live_scanner.py > /dev/null || sudo bash /home/scanner/start.sh restart >> /var/log/scanner.log 2>&1

# Sentiment (every 5 min on market days)
0 7,12,17,22 * * 1-5 cd /home/scanner && /home/scanner/venv/bin/python3 sentiment.py --limit 200 >> /tmp/sentiment.log 2>&1
```

**IMPORTANT:** `flock -n /tmp/ai_check.lock` on the AI poller prevents multiple instances from stacking up when AI analysis takes >5 min (e.g. calling Claude API). Without flock, each 5-min cron tick spawns a new process, causing OOM on the e2-micro.

---

## 10. Environment Variables (.env)

```
FIREBASE_URL=https://<project>-default-rtdb.firebaseio.com
FIREBASE_CRED=/home/scanner/firebase-credentials.json
FLASK_ENV=staging
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 11. Known Issues & Limitations

| Issue | Status |
|-------|--------|
| Congressional trading data | No free API. Shows warning in UI. |
| RS percentile in backtest | Proxied from momentum, not true cross-stock rank |
| Status (BUILDING/WATCH/READY) | ✅ Fixed v4.0.1 — now driven by BuyNow score (≥65=READY, ≥40=WATCH) |
| Insider scraper DNS failures | Transient GCP VM network issue. ~300 filing cap helps. |
| Fundamentals in backtest | Always 0 (no per-date yfinance fundamental data) |
| AI Analysis | Requires Anthropic credits before it can run |
| Firebase write auth (REST API) | ✅ Fixed — All browser writes use Firebase JS SDK. Rules updated on both staging and production to allow `.write: true` on: `optimizer_suggestions`, `run_ai_requested`, `ai_recommendations`, `approved_weights`. |
| AI cron overlapping instances | ✅ Fixed — `flock -n /tmp/ai_check.lock` on cron prevents stacking when AI analysis takes >5 min. Applied to both staging and production crontabs. |

---

## 12. Lessons Learned

### Python 3.12 / Vercel
- Stricter UTF-8 — lone surrogates crash `.format()` on HTML templates
- Use plain ASCII or proper Unicode in template strings

### yfinance
- `closes[-1]` can be `NaN` for today's unsettled bar — always filter
- Use `info['currentPrice']` for real-time price, not historical close

### Firebase
- Always `ref.update()` not `ref.set()` — `set()` wipes the entire node
- Retry writes 4× with exponential backoff for network blips

### EDGAR parsing
- form.idx column widths are NOT fixed — use regex, not slice positions
- Use submissions JSON API (`data.sec.gov/submissions/CIK{padded}.json`)

### Scoring
- Quality and Setup are separate concerns — don't mix ATR coil into quality
- Geometric mean for combined score: forces both dimensions to be good
- Stop loss is **inversely** related to ATR: high ATR → tight stop

### JS / Flask templating
- Each Flask route has its own `<script>` block — functions don't share scope
- Always duplicate score calculation functions in both dashboard and analytics

### ThreadPoolExecutor + timeout trap
- `with ThreadPoolExecutor() as ex:` calls `shutdown(wait=True)` on exit — defeats timeout logic
- Fix: manual executor + `shutdown(wait=False)` to abandon hung threads

### Atomic file writes
- Writing large pickles: process kill mid-write corrupts the file
- Fix: write to `.tmp` then `os.rename()` — atomic on Linux/macOS

### Firebase rules vs REST API
- Flask server REST API calls use no auth token → 401 on paths requiring auth
- Firebase JS SDK in browser handles auth automatically
- Solution: client-side writes via `fdb.ref().set()` for user-triggered actions
- Always add explicit `.write: true` rules for paths the web app needs to write to

---

## 13. Pending / Future Work

- [ ] Run v5_ema_gate_only experiment on staging VM (60 days), wait ~1 week for returns, then compare
- [ ] If v5 validated → apply EMA gate change to live_scanner.py and promote to production
- [ ] If v4 validated → update Status labels (BUILDING/WATCH/READY) to use Buy Now thresholds
- [ ] Congressional trading: consider paid API (Quiver Quantitative)
- [x] Test "Approve" flow end-to-end: approve AI rec → cron auto-applies → live_scanner.py patched ✅
- [x] AI optimizer full auto-apply flow working end-to-end ✅
- [x] flock on AI cron to prevent overlapping instances ✅
- [x] Stat optimizer redesigned as rows (Pending/Queued/Applied) matching AI rec UI ✅
- [x] Optimizer stats deduplicated to match analytics dashboard ✅
