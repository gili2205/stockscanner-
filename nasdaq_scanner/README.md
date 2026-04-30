# NASDAQ Momentum Screener

A combined Python scanner that merges the best logic from three open-source repos:

| Source | What was taken |
|--------|----------------|
| [VladPetrariu/Qullamaggie-breakout-scanner](https://github.com/VladPetrariu/Qullamaggie-breakout-scanner) | Core backbone — market regime gate, 6-factor analysis, evidence-based ranking (v5), backtested edge |
| [saturn-amarbat/trade-ops](https://github.com/saturn-amarbat/trade-ops) | Bull flag detector — pole + flag + volume contraction (Ross Cameron style) |
| [slimbiggins007/breakout-scanner](https://github.com/slimbiggins007/breakout-scanner) | Pattern quality scoring — 4 setup types, MACD curl, trend alignment, sector bonus |

All code is original implementation; no code was copied directly. MIT license.

---

## Setup

```bash
git clone <this-repo>
cd nasdaq_scanner
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```bash
# Full scan — opens HTML dashboard automatically (~4 min first run, ~12 sec cached)
python scanner.py

# NASDAQ + NYSE (default is NASDAQ only)
python scanner.py --no-nasdaq-filter

# Only show high-quality setups
python scanner.py --min-score 80

# Intraday watch mode — polls watchlist every 5 minutes, macOS alerts on breakout
python scanner.py --watch

# Don't auto-open browser
python scanner.py --no-open
```

## How scores are computed

### Final composite score (0–100)
```
composite = Qullamaggie_score × 0.45
          + Bull_flag_score   × 0.25
          + Pattern_score     × 0.30
```

### Qullamaggie score (0–100)
The most important layer — backtested 52.4% win rate (5-day) across 4,840 picks:

| Factor | Max pts | Description |
|--------|---------|-------------|
| EMA stack | 25 | EMA10 > EMA20 > EMA50, all rising |
| HH/HL structure | 20 | % of recent bars with higher-high/higher-low (double-weighted) |
| ATR compression | 15 | Recent ATR / base ATR (lower = tighter = better) |
| Relative strength | 20 | RS percentile vs NASDAQ universe |
| Breakout level | 10 | ATH > multi-year > 52wk > prior resistance |
| Catalyst freshness | 5 | Volume spike half-life decay |
| Weekly confluence | 5 | Weekly chart also coiling/breaking out |

### Bull flag score (0–100)
Ross Cameron style — pole + flag detection:
- 40pts: flag tightness (< 3% daily range = ideal)
- 30pts: volume contraction in flag vs pole
- 20pts: recency (fresher = higher)
- 10pts: pole strength (30%+ gain ideal)

### Pattern quality score (0–100)
Setup classification from slimbiggins007:
- 40pts: pattern quality (tight base / weekly base / trendline / undercut rally)
- 30pts: trend alignment (EMA order, all rising, price above EMAs)
- 20pts: momentum (MACD histogram curl, up-day volume > down-day volume)
- 10pts: sector bonus (semiconductors, AI, cybersecurity, etc.)

## Quality gate
Stock must pass ALL 3 criteria or ranks last:
1. EMA stack must be `full`, `partial`, or `weak` (not `none`)
2. RS percentile ≥ 20th percentile
3. Volume ratio ≥ 0.1x average

## Status labels
| Score | Status | Meaning |
|-------|--------|---------|
| 85–100 | READY | All criteria met, breakout imminent |
| 70–84 | WATCH | Most criteria met, waiting for trigger |
| 50–69 | BUILDING | Pattern forming, not yet mature |
| < 50 | WEAK | Below threshold |

## Market regime gate
The scan runs through 5 breadth indicators. If `Risk Off` is detected (VIX ≥ 32 or breadth severely deteriorated), output is suppressed — don't trade into headwinds.

## Backtested performance
From the Qullamaggie scanner backtest (Mar 2025–Mar 2026, 4,840 picks):

| Horizon | Win rate | Median return |
|---------|----------|---------------|
| 1 day | 50.6% | +0.04% |
| 3 day | 51.2% | +0.09% |
| 5 day | 52.4% | +0.21% |
| 10 day | 56.1% | +0.80% |

Edge is strongest in favorable/bull markets. In choppy regimes, reduce position size significantly.

## ⚠️ Disclaimer
This scanner identifies setups with a historically positive expected value. It does NOT guarantee profits. Trading involves risk of loss. Always use stop losses. Past performance does not predict future results. This is not financial advice.
