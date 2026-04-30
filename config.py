"""
All constants, thresholds, and blend weights for the combined NASDAQ scanner.
Based on VladPetrariu/Qullamaggie-breakout-scanner config.py (MIT license)
with additions for bull flag and pattern scoring layers.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_DIR    = PROJECT_ROOT / "cache"
SCANS_DIR    = PROJECT_ROOT / "scans"

# ---------------------------------------------------------------------------
# Universe filters
# ---------------------------------------------------------------------------
MIN_PRICE        = 5.0
MIN_AVG_VOLUME   = 500_000      # 20-day average volume
VOLUME_AVG_PERIOD = 20
NASDAQ_ONLY      = True         # Set False to include NYSE

# ---------------------------------------------------------------------------
# Data download
# ---------------------------------------------------------------------------
PRICE_HISTORY_PERIOD    = "1y"   # yfinance period string
DOWNLOAD_CHUNK_SIZE     = 500    # tickers per yfinance batch
CACHE_PRICES_TTL_HOURS  = 16
CACHE_UNIVERSE_TTL_HOURS = 7 * 24

# ---------------------------------------------------------------------------
# Technical indicator periods
# ---------------------------------------------------------------------------
EMA_PERIODS  = (10, 20, 50)
ATR_PERIOD   = 14
RS_LOOKBACK  = 20    # days for RS computation vs universe
ABR_PERIOD   = 21    # average body range lookback
MACD_FAST    = 12
MACD_SLOW    = 26
MACD_SIGNAL  = 9

# ---------------------------------------------------------------------------
# Market context thresholds (5 indicators → regime gate)
# Regime labels: Favorable | Mixed | Caution | Risk Off
# ---------------------------------------------------------------------------
MARKET_CONTEXT_THRESHOLDS = {
    "pct_above_50ma": {"favorable": 60, "mixed": 45, "caution": 30},
    "pct_above_20ma": {"favorable": 55, "mixed": 40, "caution": 25},
    "highs_lows_ratio": {"favorable": 2.0, "mixed": 1.0, "caution": 0.5},
    "vix_level": {"favorable": 18, "caution": 25, "risk_off": 32},
}

# ---------------------------------------------------------------------------
# Catalyst detection (Qullamaggie layer)
# ---------------------------------------------------------------------------
EARNINGS_LOOKBACK_DAYS  = 30
VOLUME_SPIKE_THRESHOLD  = 3.0   # x of 20-day avg

CATALYST_HALFLIFE = {
    "tier1": 4,   # shock events
    "tier2": 10,  # IPO / policy
    "tier3": 18,  # thematic / gradual
}

FRESHNESS_AGE_WEIGHT = 0.40
FRESHNESS_EXT_WEIGHT = 0.60

# ---------------------------------------------------------------------------
# Consolidation (Qullamaggie layer)
# ---------------------------------------------------------------------------
CONSOLIDATION_MIN_DAYS  = 3
CONSOLIDATION_MAX_DAYS  = 90
CANDLE_QUALITY_IDEAL    = 0.52  # body/range — top ~10%
CANDLE_QUALITY_OK       = 0.44  # above median
CANDLE_QUALITY_BARCODE  = 0.38  # bottom ~10%

# ATR compression thresholds
ATR_COMP_EXCELLENT = 0.25
ATR_COMP_GOOD      = 0.35
ATR_COMP_OK        = 0.45
ATR_COMP_FLOOR     = 0.30   # floor to prevent stagnant stocks ranking first

# Quality gate thresholds (stock must pass all 3 or sorts last)
QUALITY_GATE_RS_MIN    = 20   # RS percentile
QUALITY_GATE_VOL_RATIO = 0.1  # volume ratio vs avg

# ---------------------------------------------------------------------------
# Breakout level lookbacks
# ---------------------------------------------------------------------------
MULTI_YEAR_LOOKBACK_DAYS = 5 * 252

# ---------------------------------------------------------------------------
# Bull flag parameters (Ross Cameron / saturn-amarbat layer)
# ---------------------------------------------------------------------------
# Pole: strong up move before the flag
POLE_MIN_GAIN        = 0.10   # minimum 10% gain in pole
POLE_MIN_DAYS        = 3
POLE_MAX_DAYS        = 20
POLE_VOL_SPIKE       = 1.5    # pole volume vs avg

# Flag: tight consolidation after pole
FLAG_MIN_DAYS        = 3
FLAG_MAX_DAYS        = 20
FLAG_MAX_RETRACE     = 0.50   # flag retraces at most 50% of pole
FLAG_TIGHTNESS_IDEAL = 0.03   # < 3% daily range in flag = ideal
FLAG_TIGHTNESS_OK    = 0.05   # < 5% = acceptable
FLAG_VOL_CONTRACTION = 0.7    # flag volume < 70% of pole volume = good

# Bull flag scoring weights
FLAG_SCORE_TIGHTNESS    = 40
FLAG_SCORE_VOL_CONTRACT = 30
FLAG_SCORE_RECENCY      = 20
FLAG_SCORE_POLE_STRENGTH = 10

# ---------------------------------------------------------------------------
# Pattern quality scoring (slimbiggins007 layer)
# ---------------------------------------------------------------------------
# Setup type weights (must sum to 100)
PATTERN_SCORE_QUALITY   = 40  # tightness, consolidation length, cleanliness
PATTERN_SCORE_TREND     = 30  # EMA stack order, all rising, price above EMAs
PATTERN_SCORE_MOMENTUM  = 20  # MACD histogram curl, volume pattern
PATTERN_SCORE_SECTOR    = 10  # leading sector bonus

LEADING_SECTORS = {
    "Semiconductors", "Technology", "AI Infrastructure",
    "Cybersecurity", "Biotechnology", "Space Tech",
}

# Score thresholds → status labels
SCORE_READY    = 85
SCORE_WATCH    = 70
SCORE_BUILDING = 50

MIN_SCORE_DEFAULT = 50

# ---------------------------------------------------------------------------
# Blending weights (must sum to 1.0)
# Qullamaggie: proven backtested edge — highest weight
# Bull flag: high-momentum day-trading setups
# Pattern: quality filter and setup classification
# ---------------------------------------------------------------------------
WEIGHT_QULLAMAGGIE = 0.45
WEIGHT_BULL_FLAG   = 0.25
WEIGHT_PATTERN     = 0.30

# ---------------------------------------------------------------------------
# Sector ETF mapping (for RS vs sector)
# ---------------------------------------------------------------------------
SECTOR_ETFS = {
    "Technology":            "XLK",
    "Healthcare":            "XLV",
    "Financial Services":    "XLF",
    "Consumer Cyclical":     "XLY",
    "Consumer Defensive":    "XLP",
    "Energy":                "XLE",
    "Utilities":             "XLU",
    "Industrials":           "XLI",
    "Basic Materials":       "XLB",
    "Real Estate":           "XLRE",
    "Communication Services":"XLC",
}

BENCHMARK_TICKERS = ["SPY", "QQQ", "^VIX", "^IXIC"] + list(SECTOR_ETFS.values())
