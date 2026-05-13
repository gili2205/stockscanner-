# NASDAQ Scanner — Architecture & Technical Design
**Version: v3.2.0 | Last updated: 2026-05-13**

---

## 1. System Overview

The scanner is a fully automated stock analysis pipeline. It continuously monitors ~4,000 NASDAQ stocks, scores each one using a quantitative breakout methodology, stores historical data in Firebase, and presents results through a live web dashboard. An optimizer layer (statistical + AI-powered) analyzes historical performance and proposes scoring improvements over time.

```
┌─────────────────────────────────────────────────────────────────┐
│                        GCP Compute Engine                       │
│                                                                 │
│   live_scanner.py ──► score all NASDAQ stocks daily            │
│   backtest.py     ──► reconstruct + store historical signals   │
│   optimizer.py    ──► statistical factor analysis (weekly)     │
│   ai_optimizer.py ──► Claude AI weight suggestions (on-demand) │
│   smart_money.py  ──► SEC EDGAR insider + fund data            │
│                                                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Firebase Admin SDK (Python)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Firebase Realtime Database                     │
│                                                                 │
│   /scanner/all_stocks             live scan results            │
│   /scanner/history/YYYY-MM-DD     historical picks + returns   │
│   /scanner/first_seen             ticker first-flagged dates   │
│   /scanner/smart_money            insider + hedge fund data    │
│   /scanner/optimization_reports   statistical analysis         │
│   /scanner/ai_recommendations     Claude suggestions           │
│   /scanner/approved_weights       pending weight changes       │
│   /scanner/run_ai_requested       UI → VM trigger flag         │
│                                                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Firebase JS SDK (browser)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Vercel — Flask (app.py)                        │
│                                                                 │
│   /              Live Dashboard                                 │
│   /analytics     Historical Picks + Returns                    │
│   /smart-money   Insider Buying + Hedge Funds                  │
│   /optimizer     Statistical + AI Optimizer                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Infrastructure

### 2.1 GCP Compute Engine VMs

Two identical VMs — one per environment:

| | Production | Staging |
|---|---|---|
| Instance name | `scanner-prod` | `scanner-staging` |
| OS | Debian/Ubuntu |  Debian/Ubuntu |
| Python | 3.12 (venv at `/home/scanner/venv`) | Same |
| Working dir | `/home/scanner/` | `/home/scanner/` |
| Git branch | `main` | `fix/scanner-bugs` |
| Firebase | Production DB | Staging DB |

**Process management:**
- `live_scanner.py` runs as a **systemd service** (`scanner.service`)
- A **watchdog cron** (`*/5 * * * *`) checks if `live_scanner.py` is running and restarts it via `start.sh` if not
- All other scripts run via cron or manual invocation

**Virtual environment:**
```
/home/scanner/venv/bin/python   ← always use this, not python3
/home/scanner/venv/bin/pip
```

**Environment variables** (loaded from `/home/scanner/.env`):
```
FIREBASE_URL=https://<project>-default-rtdb.firebaseio.com
FIREBASE_CRED=/home/scanner/firebase-credentials.json
FLASK_ENV=production   # or staging
ANTHROPIC_API_KEY=sk-ant-...
```

### 2.2 Firebase Realtime Database

Two separate databases — one per environment:

| | Production | Staging |
|---|---|---|
| Project | `stockscanner-f9f81` | `stockscanner-staging` |
| URL | `stockscanner-f9f81-default-rtdb.firebaseio.com` | `stockscanner-staging-default-rtdb.firebaseio.com` |

**Access:**
- VM scripts use **Firebase Admin SDK** (Python) with a service account credentials JSON
- Browser uses **Firebase JS SDK** (v9 compat) with a public `FIREBASE_CONFIG` object injected by Flask at page load

### 2.3 Vercel (Flask app)

- `app.py` is deployed as a serverless Flask app on Vercel
- **Auto-deploys** from `main` branch on every push
- `fix/scanner-bugs` branch gets a **preview deployment** automatically (separate URL, useful for staging)
- No server-side state — all dynamic data comes from Firebase via the browser's JS SDK
- Flask only serves HTML pages and a small set of API endpoints

---

## 3. Data Flow

### 3.1 Live Scan (daily)

```
live_scanner.py
    │
    ├─ 1. Fetch NASDAQ tickers (~4,000) from exchange listing
    │
    ├─ 2. Download OHLCV via yfinance (batches of 200, ThreadPoolExecutor, 120s timeout)
    │
    ├─ 3. Score each stock → BREAKOUT track score (0–95)
    │       • Momentum 1M          (28 pts max)
    │       • EMA stack            (22 pts full / 12 pts partial)
    │       • Distance to level    (18 pts max)
    │       • ATR compression      (12 pts max)
    │       • HH/HL structure      (6 pts max)
    │       • Volume contraction   (8 pts max)
    │       • Liquidity            (7 pts max)
    │       • Penalties            (-18 weak EMA, -12 far dist, -12 neg mom, -8 high vol)
    │
    ├─ 4. Assign RS percentiles across full universe
    │
    ├─ 5. Filter: price ≥ $15, avg dollar vol ≥ $10M
    │
    └─ 6. Push to Firebase /scanner/all_stocks via ref.update()
             (NEVER ref.set() — set() wipes the entire /scanner node)
```

### 3.2 Historical Backtest

```
backtest.py --days 180
    │
    ├─ For each of the last N trading days:
    │   ├─ Download price data for that date
    │   ├─ Score all stocks as if it were that date
    │   └─ Store top 200 picks in /scanner/history/YYYY-MM-DD
    │
    └─ Each pick stored with:
         ticker, score, status, ema_stack, atr, vol_contraction,
         dist_to_level, momentum_1m, hh_hl, level, rs_percentile,
         pre_breakout, bull_flag, returns: {1w, 2w, 1m, 2m, 3m}

backtest.py --update-returns
    │
    └─ For each pick in /scanner/history:
         ├─ Check current price
         └─ Compute % change for each return window (1w=5 days, 1m=21 days, etc.)
              stored in pick.returns.{1w, 2w, 1m, 2m, 3m}
```

### 3.3 Optimizer Pipeline

```
optimizer.py --all-windows   (runs weekly via cron, Sunday 4am)
    │
    ├─ Load all picks from /scanner/history that have return data
    ├─ Compute: overall win rate, avg return, best/worst pick
    ├─ Score band breakdown (by score decile 0-9, 10-19, ... 90-99)
    ├─ Factor analysis: for each signal, compare WR "with" vs "without"
    │     WR lift = win_rate_with_signal − win_rate_without_signal
    └─ Save to /scanner/optimization_reports/<timestamp>

Browser → /optimizer tab
    │
    └─ Firebase listener reads /scanner/optimization_reports
         └─ Renders factor table, score bands, auto-suggestions
```

### 3.4 AI Analysis Pipeline

```
User clicks "Run AI Analysis"
    │
    ├─ Browser → POST /api/run-ai-analysis
    │             Flask sets /scanner/run_ai_requested = {status: pending}
    │
    ├─ Firebase listener updates button: "⏳ Queued..."
    │
    ├─ VM cron (every 5 min): ai_optimizer.py --check-and-run
    │   ├─ Reads /scanner/run_ai_requested
    │   ├─ If pending: set status = running
    │   ├─ load_picks() — last 180 days with return data
    │   ├─ factor_analysis() — WR lift per signal
    │   ├─ score_band_breakdown() — perf by score decile
    │   ├─ shadow_backtest(picks, DEFAULT_WEIGHTS) — current baseline
    │   ├─ call_claude() — send data to Claude claude-opus-4-5
    │   │     → returns JSON: reasoning, summary, confidence, changes[]
    │   ├─ shadow_backtest(picks, proposed_weights) — projected improvement
    │   ├─ Save full recommendation to /scanner/ai_recommendations/<timestamp>
    │   └─ Set /scanner/run_ai_requested = {status: done}
    │
    ├─ Firebase listener shows result, button → "✓ Done — Run Again"
    │
    └─ User clicks Approve
         ├─ POST /api/recommendations/<id>/approve
         │   Flask sets /scanner/ai_recommendations/<id>/status = approved
         └─ On VM: python ai_optimizer.py --apply
              ├─ Read latest approved (not yet applied) rec
              ├─ Backup live_scanner.py → live_scanner.py.bak_YYYYMMDD_HHMMSS
              ├─ Patch DEFAULT_WEIGHTS values in live_scanner.py via regex
              └─ Mark rec as applied in Firebase
```

### 3.5 Browser Data Loading

All pages use Firebase JS SDK with **real-time listeners** (`ref.on('value', ...)`):
- Data arrives as soon as the page loads — no polling needed
- Changes on Firebase (e.g. AI analysis completing) update the UI automatically
- No server round-trips after initial HTML load — Flask is only for page delivery

**Exception**: `/analytics` page uses **localStorage caching**:
```
First load:  fetch ALL /scanner/history → cache in localStorage
Subsequent:  only fetch dates not already in cache → merge
```

---

## 4. Scoring Logic — Technical Details

### 4.1 BREAKOUT Track Score (0–95, capped)

Implemented in `live_scanner.py → score_stock()` and mirrored in `ai_optimizer.py → compute_breakout_score()`.

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

**Momentum (1M)** — graduated tiers:
```
mom1m ≥ 25% → 28 pts
mom1m ≥ 15% → 22 pts
mom1m ≥  8% → 15 pts
mom1m ≥  3% →  9 pts
mom1m ≥  0% →  4 pts
```

**EMA Stack:**
```
full    (price > EMA10 > EMA20 > EMA50) → 22 pts
partial (EMA10 > EMA20 only)            → 12 pts
weak    (any other configuration)       → 0 pts + penalty
```

**ATR Compression** (ATR as % of price):
```
≤ 0.20 → 12 pts
≤ 0.25 →  9 pts
≤ 0.30 →  6 pts
≤ 0.40 →  2 pts
> 0.40 →  0 pts
```

**Volume Contraction** (5-day avg / 20-day avg):
```
≤ 0.50 → 8 pts
≤ 0.65 → 5 pts
≤ 0.80 → 2 pts
> 0.80 → 0 pts
```

**Distance to Level** (% below breakout level):
```
≤  1% → 18 pts
≤  2% → 14 pts
≤  3.5% → 9 pts
≤  6% →  4 pts
≤ 10% →  1 pt
> 10% →  0 pts
```

**Penalties** (subtracted after all positive points):
```
ema_stack == "weak"               → -18
dist_to_level > 15%               → -12
momentum_1m < -5%                 → -12
atr > 0.7 AND momentum_1m < 10%   →  -8
```

**Status assignment:**
```
score ≥ 72 → READY    (shown prominently, green border)
score ≥ 55 → WATCH    (yellow border)
score  < 55 → BUILDING (not surfaced in UI)
```

**Hard kill:** if 3M momentum < -30%, score = 0 (severe downtrend, skip entirely)

### 4.2 RS Percentile

After all stocks are scored, each stock's 6-month return is ranked against the full universe. RS percentile = `rank / total * 100`. Stored as `rs_percentile` in Firebase.

### 4.3 Forward Returns

`backtest.py --update-returns` computes forward returns using closing price data:

```python
def pct(n):
    if len(closes) >= n and n > 0:
        base = closes[-n]
        if base and base > 0:
            return round((price - base) / base * 100, 1)
    return None
```

| Window | Trading days |
|--------|-------------|
| 1w | 5 |
| 2w | 10 |
| 1m | 21 |
| 2m | 42 |
| 3m | 63 |

---

## 5. Firebase Data Structures

### `/scanner/all_stocks`
```json
{
  "AAPL": {
    "ticker": "AAPL",
    "price": 195.50,
    "score": 78,
    "status": "READY",
    "ema_stack": "full",
    "atr": 0.22,
    "vol_contraction": 0.61,
    "dist_to_level": 1.2,
    "momentum_1m": 12.4,
    "momentum_3m": 18.1,
    "hh_hl": 0.88,
    "rs_percentile": 91,
    "level": "52-week high",
    "pre_breakout": true,
    "bull_flag": false,
    "market_cap": "Large",
    "last_scan_time": "2026-05-13 09:30"
  }
}
```

### `/scanner/history/YYYY-MM-DD`
```json
{
  "AAPL": {
    "ticker": "AAPL",
    "score": 76,
    "status": "READY",
    "ema_stack": "full",
    "atr": 0.23,
    "vol_contraction": 0.55,
    "dist_to_level": 0.8,
    "momentum_1m": 11.2,
    "hh_hl": 0.85,
    "rs_percentile": 89,
    "returns": {
      "1w": 3.2,
      "2w": 5.1,
      "1m": 8.7,
      "2m": null,
      "3m": null
    }
  }
}
```

### `/scanner/optimization_reports/<timestamp>`
```json
{
  "generated_at": "2026-05-13T09:50:55",
  "windows": ["1w", "2w", "1m", "2m", "3m"],
  "reports": {
    "1m": {
      "stats": {
        "total_picks": 842,
        "scan_days": 47,
        "date_range": "2026-01-15 → 2026-05-12",
        "win_rate": 54.2,
        "avg_return": 3.1,
        "med_return": 1.8,
        "best": 48.2,
        "worst": -22.1
      },
      "factors": [
        {
          "factor": "ATR ≤ 0.25",
          "n_with": 210,
          "wr_with": 68.1,
          "wr_without": 48.3,
          "wr_diff": 19.8,
          "avg_ret_with": 6.2,
          "avg_ret_wout": 2.1
        }
      ],
      "bands": [
        { "score_range": "70-79", "n_picks": 180, "win_rate": 61.1, "avg_return": 4.2, "med_return": 2.1 }
      ]
    }
  }
}
```

### `/scanner/ai_recommendations/<timestamp>`
```json
{
  "generated_at": "2026-05-13T10:15:00",
  "window": "1m",
  "n_picks": 842,
  "status": "pending",
  "applied": false,
  "claude_summary": "ATR compression is severely under-weighted relative to its predictive power",
  "claude_reasoning": "...",
  "claude_confidence": "HIGH",
  "current_stats": { "all": { "n": 842, "win_rate": 54.2, "avg_return": 3.1 } },
  "projected_stats": { "all": { "n": 798, "win_rate": 61.4, "avg_return": 4.8 } },
  "win_rate_delta": 7.2,
  "avg_return_delta": 1.7,
  "current_weights": { "breakout_atr_max": 12, "..." : "..." },
  "proposed_weights": { "breakout_atr_max": 18, "..." : "..." },
  "changes": [
    {
      "weight_key": "breakout_atr_max",
      "current_value": 12,
      "proposed_value": 18,
      "reason": "ATR ≤ 0.25 shows +54.8% win rate lift — most predictive single factor"
    }
  ]
}
```

### `/scanner/run_ai_requested`
```json
{ "status": "pending", "requested_at": "2026-05-13T10:10:00" }
{ "status": "running", "started_at": "2026-05-13T10:15:00" }
{ "status": "done",    "completed_at": "2026-05-13T10:17:30" }
{ "status": "error",   "error": "Not enough data", "completed_at": "..." }
```

---

## 6. API Endpoints (Flask)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Live dashboard HTML |
| GET | `/analytics` | Analytics page HTML |
| GET | `/smart-money` | Smart money page HTML |
| GET | `/optimizer` | Optimizer page HTML |
| GET | `/ai` | Alias for `/optimizer` |
| GET | `/pre-market` | Pre-market page HTML |
| GET | `/api/scan` | Latest scan results JSON |
| GET | `/api/history` | Historical picks JSON |
| GET | `/api/smart-money` | Smart money data JSON |
| POST | `/api/run-ai-analysis` | Set Firebase trigger flag |
| POST | `/api/recommendations/<id>/approve` | Approve AI recommendation |
| POST | `/api/recommendations/<id>/reject` | Reject AI recommendation |
| POST | `/api/optimizer-suggestions/approve` | Approve statistical suggestions |

---

## 7. Cron Schedule (both VMs)

| Schedule | Command | Purpose |
|----------|---------|---------|
| `*/5 * * * *` | watchdog via `start.sh` | Restart scanner if crashed |
| `0 22 * * 1-5` | `backtest.py --days 2` | Nightly — add latest trading day to history |
| `0 23 * * 1-5` | `backtest.py --update-returns` | Nightly — fill in new return windows |
| `0 4 * * 0` | `optimizer.py --all-windows` | Weekly — statistical factor analysis |
| `*/5 * * * *` | `ai_optimizer.py --check-and-run` | Every 5 min — AI trigger poller |

---

## 8. Deployment

### Web App (Vercel)
- Push to `main` → Vercel auto-builds and deploys (typically < 60 seconds)
- Push to `fix/scanner-bugs` → Vercel creates a preview deployment at a branch URL
- No build step — Flask app runs as serverless functions
- `vercel.json` defines routing

### VM Scripts
```bash
cd /home/scanner && git pull origin main
# No restart needed for Python scripts — they read from disk at each cron invocation
# live_scanner.py needs restart to pick up code changes:
sudo systemctl restart scanner
```

### Applying Weight Changes
```bash
# After approving a recommendation in the UI:
/home/scanner/venv/bin/python ai_optimizer.py --apply
sudo systemctl restart scanner
```

---

## 9. Security & Config

- Firebase credentials JSON stored at `/home/scanner/firebase-credentials.json` — not in git
- `ANTHROPIC_API_KEY` in `.env` — not in git
- `.env` file loaded by all Python scripts via `_load_dotenv()` helper
- `FIREBASE_CONFIG` (public JS SDK config) injected by Flask at page load via string replacement in HTML template — safe to expose (read-only Firebase rules)
- Firebase security rules: currently open read (public dashboard), restricted write (Admin SDK only)

---

## 10. Dependencies

```
flask>=2.0.0          — web framework (Vercel)
yfinance>=0.2.0       — OHLCV price data
anthropic>=0.25.0     — Claude API (ai_optimizer.py)
firebase-admin        — Firebase Admin SDK (VM scripts)
numpy                 — numerical operations (optimizer)
requests              — HTTP (smart_money.py)
```

---

## 11. Known Technical Debt

| Item | Risk | Notes |
|------|------|-------|
| `ai_optimizer.py --apply` patches `live_scanner.py` via regex | Medium | Regex patterns are fragile; may fail if code formatting changes |
| `DEFAULT_WEIGHTS` duplicated in `live_scanner.py` and `ai_optimizer.py` | Medium | Must be kept in sync manually; drift causes incorrect shadow backtest |
| yfinance rate limiting | Low | GCP IPs occasionally rate-limited; batching + retry mitigates |
| Firebase rules open for reading | Low | Dashboard data is not sensitive; acceptable trade-off for simplicity |
| `smart_money.py` Form 4 insider buys returning 0 | Medium | Known bug, deferred |
