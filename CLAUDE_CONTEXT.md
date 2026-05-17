# NASDAQ Scanner — Full Context Document
**For continuing this project in a new Claude thread**

Last updated: 2026-05-16 — v4.0.0

---

## Version Tracking (ALWAYS follow these rules)

| Component | Version | Notes |
|-----------|---------|-------|
| `app.py` (Flask app) | **v4.3.0** | Optimizer: Accept button queues weight change to live_scanner.py |
| `backtest.py` | **v4_quality_setup** | `SCORING_VERSION` constant |
| `smart_money.py` | — | No version constant; track via git |
| Last updated | **2026-05-17** | v4.2.0 |

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
Reconstructs historical scanner signals. Experiment framework isolates runs.

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

### `smart_money.py`
- ARK holdings (ETF filings from ark-funds.com)
- Insider buys (Form 4 from SEC EDGAR — buys > $100K)
- Activist filings (13D/13G)
- 13F institutional holdings (major hedge funds)

### `app.py` (VERSION: v4.0.0)
Flask web app on Vercel. Key routes:
- `GET /` — live dashboard
- `GET /analytics` — historical picks (experiment-aware)
- `GET /sentiment` — news sentiment
- `GET /smart_money` — smart money

### `score_patch.py`
Patches scores in Firebase without full rescan.

### `sentiment.py`
- Finnhub `/company-news` (free tier)
- Buzz score: log-normalized article count 0–100
- Expanded universe: scanner picks + IPO calendar + history

### `config.py`
Shared constants (SCORE_READY=85, SCORE_WATCH=70, etc.)

---

## 5. Current Experiment: v4_quality_setup

- **Status**: Running as of 2026-05-16
- **Days**: 180 (2025-09-08 → 2026-05-15)
- **SCORING_VERSION**: `v4_quality_setup`
- **New fields stored**: `rsi`, `score_quality`, `score_setup`, `score_buy_now`
- **Firebase path**: `/scanner/experiments/v4_quality_setup/`
- **Purpose**: Validate new Quality/Setup/BuyNow scoring vs old blended score
- **What to check when done**: avg return by Buy Now bucket (≥65 vs 40-64 vs <40). If high Buy Now → high returns, scoring is validated.

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

---

## 7. Git Workflow — Strict Rules

**NEVER push directly to `main` without staging verification.**
**NEVER create new branches. Use `fix/scanner-bugs` for staging.**

All changes go to `fix/scanner-bugs` first:
```bash
git checkout fix/scanner-bugs
git add <specific files>
git commit -m "description"
git push origin fix/scanner-bugs
```

Merge to `main` only after explicit user approval.

**Vercel auto-deploys `app.py` changes — never tell the user to git pull for UI changes.**

---

## 8. VM Commands

```bash
# SSH
ssh gilih2205@scanner-staging

# Always cd first
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
# Watchdog
*/5 * * * * pgrep -f live_scanner.py > /dev/null || sudo bash /home/scanner/start.sh restart

# Backtest (nightly, market days)
0 22 * * 1-5 cd /home/scanner && /home/scanner/venv/bin/python3 backtest.py --days 2 >> /var/log/backtest.log 2>&1

# Update returns (nightly)
0 23 * * 1-5 cd /home/scanner && /home/scanner/venv/bin/python3 backtest.py --update-returns >> /var/log/backtest.log 2>&1

# Statistical optimizer (weekly)
0 4 * * 0 cd /home/scanner && /home/scanner/venv/bin/python optimizer.py --all-windows

# AI trigger poller (every 5 min)
*/5 * * * * cd /home/scanner && /home/scanner/venv/bin/python ai_optimizer.py --check-and-run
```

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

---

## 13. Pending / Future Work

- [ ] Wait for v4_quality_setup backtest to finish, then analyze results in Analytics
- [ ] If v4 validated → update Status labels (BUILDING/WATCH/READY) to use Buy Now thresholds
- [ ] If v4 validated → merge fix/scanner-bugs → main (promote to production)
- [ ] Congressional trading: consider paid API (Quiver Quantitative)
- [ ] Test "Approve" flow end-to-end: approve AI rec → run `--apply` → verify live_scanner.py patched
- [ ] Add Anthropic credits to enable AI analysis button
