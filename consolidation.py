"""
Consolidation factor analysis.
Computes: ATR compression, EMA stack quality, HH/HL price structure,
candle quality, pole+flag detection prep.

Core logic from Qullamaggie scanner (VladPetrariu), MIT license.
"""

import numpy as np
import pandas as pd

from config import (
    EMA_PERIODS, ATR_PERIOD, ABR_PERIOD,
    CONSOLIDATION_MIN_DAYS, CONSOLIDATION_MAX_DAYS,
    CANDLE_QUALITY_IDEAL, CANDLE_QUALITY_OK, CANDLE_QUALITY_BARCODE,
    ATR_COMP_EXCELLENT, ATR_COMP_GOOD, ATR_COMP_OK, ATR_COMP_FLOOR,
)


def score_consolidation(df: pd.DataFrame) -> dict:
    """
    Analyze consolidation quality for a stock.
    Returns dict with atr_compression, ema_stack, hh_hl_pct, candle_quality, etc.
    """
    df = df.copy()
    df = _compute_indicators(df)

    atr_comp = _atr_compression(df)
    ema_stack = _ema_stack(df)
    hh_hl_pct = _hh_hl_structure(df)
    candle_qual = _candle_quality(df)
    pole_flag = _detect_pole(df)

    return {
        "atr_compression": atr_comp,
        "ema_stack": ema_stack,         # "full" | "partial" | "weak" | "none"
        "hh_hl_pct": hh_hl_pct,        # 0.0 - 1.0
        "candle_quality": candle_qual,  # "ideal" | "ok" | "barcode" | "poor"
        "has_pole": pole_flag["has_pole"],
        "pole_gain": pole_flag["gain"],
        "consolidation_days": _count_consolidation_days(df),
    }


def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add EMAs and ATR to df in place."""
    for p in EMA_PERIODS:
        df[f"ema{p}"] = df["Close"].ewm(span=p, adjust=False).mean()

    # ATR
    high = df["High"]
    low = df["Low"]
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(span=ATR_PERIOD, adjust=False).mean()

    # Average Body Range (ABR) — average true range of last 21 days
    df["abr"] = df["atr"].rolling(ABR_PERIOD).mean()

    return df


def _atr_compression(df: pd.DataFrame, lookback: int = 20) -> float:
    """
    ATR compression: recent ATR / ATR 50 days ago.
    Lower = tighter = better setup.
    Floored at ATR_COMP_FLOOR to prevent stagnant stocks.
    """
    if len(df) < 70:
        return 1.0
    recent_atr = df["atr"].iloc[-lookback:].mean()
    base_atr = df["atr"].iloc[-70:-50].mean()
    if base_atr <= 0:
        return 1.0
    compression = recent_atr / base_atr
    return max(ATR_COMP_FLOOR, round(float(compression), 3))


def _ema_stack(df: pd.DataFrame) -> str:
    """
    Check EMA stack alignment: EMA10 > EMA20 > EMA50 and all pointing up.
    Returns "full" | "partial" | "weak" | "none"
    """
    try:
        last = df.iloc[-1]
        e10, e20, e50 = last["ema10"], last["ema20"], last["ema50"]
        price = last["Close"]

        stacked = e10 > e20 > e50
        price_above_all = price > e10

        # Check EMAs are rising (positive slope over last 5 bars)
        slope10 = df["ema10"].iloc[-1] > df["ema10"].iloc[-5]
        slope20 = df["ema20"].iloc[-1] > df["ema20"].iloc[-5]
        slope50 = df["ema50"].iloc[-1] > df["ema50"].iloc[-10]

        if stacked and price_above_all and slope10 and slope20 and slope50:
            return "full"
        if stacked and price_above_all and slope10:
            return "partial"
        if e10 > e20 and price > e20:
            return "weak"
        return "none"
    except Exception:
        return "none"


def _hh_hl_structure(df: pd.DataFrame, lookback: int = 20) -> float:
    """
    Percentage of recent bars that show higher-high and higher-low vs prior bar.
    Perfect uptrend = 1.0. Strongest predictor in combo analysis per Qullamaggie scanner v5.
    """
    recent = df.tail(lookback)
    if len(recent) < 5:
        return 0.0
    hh = (recent["High"] > recent["High"].shift(1)).sum()
    hl = (recent["Low"] > recent["Low"].shift(1)).sum()
    total = len(recent) - 1
    if total <= 0:
        return 0.0
    return round(float((hh + hl) / (2 * total)), 3)


def _candle_quality(df: pd.DataFrame, lookback: int = 10) -> str:
    """
    Body/range ratio over recent candles.
    High ratio = clean trending candles. Low ratio = doji/barcode.
    """
    recent = df.tail(lookback)
    body = (recent["Close"] - recent["Open"]).abs()
    range_ = (recent["High"] - recent["Low"]).replace(0, np.nan)
    ratio = (body / range_).mean()

    if ratio >= CANDLE_QUALITY_IDEAL:
        return "ideal"
    if ratio >= CANDLE_QUALITY_OK:
        return "ok"
    if ratio >= CANDLE_QUALITY_BARCODE:
        return "barcode"
    return "poor"


def _detect_pole(df: pd.DataFrame, lookback: int = 40) -> dict:
    """
    Detect if there was a strong up-move (pole) in the recent past.
    Returns pole gain and whether one was detected.
    """
    if len(df) < lookback:
        return {"has_pole": False, "gain": 0.0}

    closes = df["Close"].iloc[-lookback:]
    rolling_min = closes.rolling(5).min()
    max_gain = 0.0

    for i in range(5, len(closes)):
        low = rolling_min.iloc[i - 5]
        high = closes.iloc[i]
        if low > 0:
            gain = (high - low) / low
            max_gain = max(max_gain, gain)

    has_pole = max_gain >= 0.15  # at least 15% move
    return {"has_pole": has_pole, "gain": round(float(max_gain), 3)}


def _count_consolidation_days(df: pd.DataFrame, lookback: int = 60) -> int:
    """
    Count how many days the stock has been in a tight range (consolidation).
    """
    recent = df.tail(lookback)
    if len(recent) < CONSOLIDATION_MIN_DAYS:
        return 0

    highs = recent["High"]
    lows = recent["Low"]

    # Find the start of the most recent consolidation (range < 15% of price)
    last_price = float(recent["Close"].iloc[-1])
    threshold = last_price * 0.15

    count = 0
    for i in range(len(recent) - 1, -1, -1):
        window = recent.iloc[i:]
        rng = float(window["High"].max() - window["Low"].min())
        if rng <= threshold:
            count = len(window)
        else:
            break

    return max(0, min(count, CONSOLIDATION_MAX_DAYS))
