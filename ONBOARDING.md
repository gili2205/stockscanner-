# Stock Scanner — Claude Context & Project Reference

> **Always read this file at the start of every session.**
> **Always update this file and bump the version when making any meaningful change.**

---

## Version

| Component | Version | Notes |
|-----------|---------|-------|
| `app.py` (Flask app) | **v4.0.0** | Three-score system, ATR-derived stops |
| `backtest.py` | **v4_quality_setup** | `SCORING_VERSION` constant |
| `smart_money.py` | — | No version constant; track via git |
| Last updated | **2026-05-16** | — |

### Version bump rules (ALWAYS follow these)
- **Patch** (v4.0.**x**): bug fix, UI tweak, copy change
- **Minor** (v4.**x**.0): new feature, new score component, new data source
- **Major** (**vX**.0.0): scoring system redesign, architecture change
- Update `VERSION` in `app.py` AND this file on every meaningful commit.
- `SCORING_VERSION` in `backtest.py` must be bumped any time `score_stock_historical()` changes — format: `"vN_short_description"`.

---

## Architecture

```
GitHub (fix/scanner-bugs branch)
    │
    ├── Vercel (auto-deploys on push to fix/scanner-bugs → staging)
    │       Flask app (app.py) — serves dashboard, analytics, sentiment, smart money
    │       Python 3.12 — stricter UTF-8 than local dev (no surrogate chars)
    │
    ├── GCP VM  (scanner-staging, user: gilih2205)
    │       /home/scanner/  — working directory
    │       /home/scanner/venv/bin/python — always use this Python
    │       /home/scanner/.env — Firebase creds, API keys
    │       /home/scanner/.price_cache.pkl — yfinance batch download cache
    │       Runs: live_scanner.py, backtest.py, sentiment.py, smart_money.py
    │
    └── Firebase Realtime DB
            /scanner/all_stocks/{TICKER}     — live scanner picks
            /scanner/history/{DATE}/{TICKER} — production backtest history
            /scanner/first_seen/{TICKER}     — first time each ticker was flagged
            /scanner/sentiment/{TICKER}      — sentiment + buzz scores
            /scanner/smart_money/            — ARK, insider, activist, 13F data
            /scanner/experiments/{NAME}/     — experiment backtests (isolated)
```

### Branch rules
- `fix/scanner-bugs` → **staging** (Vercel auto-deploys)
- `main` → **production** (only merge when staging is verified)

---

## Scoring System (v4)

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
> Note: Status still uses the old 3-layer blended score (tech/fund/catalyst). Not yet updated to use Buy Now score. BUILDING does NOT mean bad — it means the old score is < 55.

### Stop loss calculation
```javascript
stopDist = clamp(0.02 / ATR, 3%, 9%)
```
- Low ATR (stable) → wide stop up to 9% (give it room)
- High ATR (volatile) → tight stop down to 3% (cut fast)
- **Inverse logic: high risk = tight stop, low risk = wide stop**

---

## Backtest System

### Running a backtest
```bash
# Production (writes to /scanner/history)
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

### Current experiment: v4_quality_setup
- **Status**: Running as of 2026-05-16
- **Days**: 180 (2025-09-08 → 2026-05-15)
- **SCORING_VERSION**: `v4_quality_setup`
- **New fields stored**: `rsi`, `score_quality`, `score_setup`, `score_buy_now`
- **Firebase path**: `/scanner/experiments/v4_quality_setup/`
- **Purpose**: Validate new Quality/Setup/BuyNow scoring vs old blended score
- **What to check when done**: avg return by Buy Now score bucket (≥65 vs 40-64 vs <40). If high Buy Now → high returns, scoring is validated.

### Crash protection (v4)
- Firebase writes retry 4× with exponential backoff
- Per-day `try/except`: one bad day → logged, continues to next
- Per-ticker `try/except`: one bad stock → skipped, day continues
- KeyboardInterrupt: clean exit, re-running resumes from last unwritten day
- 10 consecutive day failures → aborts with clear error
- **Always use `nohup`** to protect against SSH disconnect

### Scoring in backtest vs live
| Factor | Live scanner | Backtest |
|--------|-------------|----------|
| RS percentile | Cross-stock comparison | Proxy from 3M momentum bucket |
| Fundamentals | yfinance real-time | 0 (no per-date fundamental data) |
| Earnings penalty | days_to_earnings from yfinance | Not applied (no calendar) |
| RSI | From API | Computed from OHLCV |

---

## Pages & Features

### Dashboard (/)
- Live scanner picks from Firebase `/scanner/all_stocks`
- Cards show: Buy Now score (top right), Quality + Setup bars (inside card, below Technical Factors)
- Sort: 🎯 Score | 💎 Quality | 🎣 Setup | 📅 Date | 🔤 A-Z
- Filter chips: Risk (Low/Med/High ATR), Setup, Momentum, Sector, Streak
- Score Focus chips: Score / Quality / Setup (sets sort key)
- Risk/Reward section: Risk (ATR-based stop), Reward (signal count), Setup label

### Analytics (/analytics)
- History from Firebase `/scanner/history` or experiment path
- Table columns: Score (Buy Now, green) | Quality (blue) | Setup (orange) | returns
- Sort by: Score / Quality / Setup / Date / A-Z / returns
- KPI cards: win rate, avg return, expectancy
- Score focus chips: Score (buy now) | Quality | Setup

### Sentiment (/sentiment)
- Fetches news from Finnhub for expanded universe
- Buzz score (log-normalized article count 0–100)
- Sentiment: bullish/bearish/neutral from keyword analysis
- Universe: pinned tickers + Yahoo trending + movers + scanner picks + IPOs + history

### Smart Money (/smart_money)
- ARK holdings (ETF filings from ark-funds.com)
- Insider buys (Form 4 from SEC EDGAR — buys > $100K)
- Activist filings (13D/13G — uses submissions JSON API for ticker, SGML header for filer)
- 13F institutional holdings (major hedge funds)
- Top Conviction: tickers appearing in multiple smart money sources
- Congressional trades: no working free data source (shows warning)

---

## Known Issues & Limitations

| Issue | Status |
|-------|--------|
| Congressional trading data | No free API. Quiver Quantitative requires paid plan. Shows warning in UI. |
| RS percentile in backtest | Proxied from momentum, not true cross-stock rank |
| Status (BUILDING/WATCH/READY) | Uses old blended score thresholds, not new Buy Now score |
| Insider scraper DNS failures | Transient GCP VM network issue. Retry logic exists but ~300 filing cap helps. |
| Fundamentals in backtest | Always 0 (no per-date yfinance fundamental data available) |

---

## Key Files

| File | Purpose |
|------|---------|
| `app.py` | Flask app, all HTML/JS for all pages, `/api/card-data`, `/lookup` routes |
| `backtest.py` | Historical backtest engine, experiment framework |
| `live_scanner.py` | Live scanner that writes to Firebase `/scanner/all_stocks` |
| `smart_money.py` | ARK + insider + activist + 13F scraper |
| `sentiment.py` | News sentiment tracker |
| `score_patch.py` | Patches scores in Firebase without full rescan |
| `optimizer.py` | Analyzes backtest results, compares experiments |
| `ai_optimizer.py` | AI-assisted weight optimization |
| `config.py` | Shared constants (SCORE_READY=85, SCORE_WATCH=70, etc.) |

---

## Common VM Commands

```bash
# SSH
ssh gilih2205@scanner-staging

# Always cd first
cd /home/scanner

# Pull latest
git pull origin fix/scanner-bugs

# Run scripts
/home/scanner/venv/bin/python /home/scanner/live_scanner.py
/home/scanner/venv/bin/python /home/scanner/smart_money.py --insiders
/home/scanner/venv/bin/python /home/scanner/sentiment.py

# Check running processes
ps aux | grep python

# View logs
tail -f /home/scanner/backtest_v4.log
```

---

## Important Lessons Learned

### Python 3.12 / Vercel
- Stricter UTF-8 encoding — lone surrogates (`\ud83d`) crash `.format()` on HTML templates
- Always use plain ASCII or proper Unicode in template strings (no copy-pasted emoji stored as surrogates)

### yfinance
- `closes[-1]` can be `NaN` for today's unsettled bar — always filter: `[c for c in closes if c and not math.isnan(c)]`
- Use `info['currentPrice']` for real-time price in upside calculations, not historical close

### EDGAR parsing
- form.idx column widths are NOT fixed — use regex, not slice positions
- Directory listings include nav links — use submissions JSON API instead (`data.sec.gov/submissions/CIK{padded}.json`)
- SGML header (first 8KB of .txt file) contains `FILED BY: COMPANY CONFORMED NAME:` for activist filer identity

### Scoring
- Quality and Setup are separate concerns — don't mix ATR coil (entry timing) into a "quality" score
- Earnings proximity is the biggest missing factor from any entry-timing score
- Geometric mean for combined score: forces both dimensions to be good (not just average of them)
- Stop loss is **inversely** related to risk: high ATR (risky) → tight stop; low ATR (conviction) → wide stop
