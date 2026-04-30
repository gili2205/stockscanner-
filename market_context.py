"""
Market regime classification — gates the entire scan.
If market is Risk-Off, all output is suppressed.
Based on Qullamaggie scanner market_context.py logic.
Added QQQ breadth for NASDAQ-specific focus.
"""

import numpy as np
import pandas as pd

from config import MARKET_CONTEXT_THRESHOLDS


def classify_market_regime(benchmark: pd.DataFrame) -> dict:
    """
    Classify the current market regime using 5 breadth indicators.
    Returns: {label, score, indicators}
    """
    indicators = {}
    score = 0  # 0-5, each indicator contributes 1 point if favorable

    # 1. % of stocks above 50-day MA (proxy via SPY vs its 50-MA)
    try:
        spy = benchmark["SPY"].dropna()
        ma50 = spy.rolling(50).mean()
        above_50 = (spy > ma50).iloc[-20:].mean() * 100
        indicators["pct_above_50ma"] = round(float(above_50), 1)
        th = MARKET_CONTEXT_THRESHOLDS["pct_above_50ma"]
        if above_50 >= th["favorable"]:
            score += 1
    except Exception:
        indicators["pct_above_50ma"] = None

    # 2. % of stocks above 20-day MA (proxy via QQQ)
    try:
        qqq = benchmark.get("QQQ", benchmark.get("SPY")).dropna()
        ma20 = qqq.rolling(20).mean()
        above_20 = (qqq > ma20).iloc[-10:].mean() * 100
        indicators["pct_above_20ma"] = round(float(above_20), 1)
        th = MARKET_CONTEXT_THRESHOLDS["pct_above_20ma"]
        if above_20 >= th["favorable"]:
            score += 1
    except Exception:
        indicators["pct_above_20ma"] = None

    # 3. 52-week highs vs lows ratio (proxy via QQQ recent 52wk high)
    try:
        qqq = benchmark.get("QQQ", benchmark.get("SPY")).dropna()
        high_52 = qqq.rolling(252).max().iloc[-1]
        low_52 = qqq.rolling(252).min().iloc[-1]
        curr = qqq.iloc[-1]
        # Simplified: how far from 52wk high vs low
        pct_from_high = (high_52 - curr) / (high_52 - low_52 + 1e-9)
        ratio = (1 - pct_from_high) * 4  # scale to ~2 for favorable
        indicators["highs_lows_ratio"] = round(float(ratio), 2)
        th = MARKET_CONTEXT_THRESHOLDS["highs_lows_ratio"]
        if ratio >= th["favorable"]:
            score += 1
    except Exception:
        indicators["highs_lows_ratio"] = None

    # 4. VIX level
    try:
        vix_col = None
        for col in ["^VIX", "VIX"]:
            if col in benchmark.columns:
                vix_col = col
                break
        vix = float(benchmark[vix_col].dropna().iloc[-1]) if vix_col else 18.0
        indicators["vix"] = round(vix, 1)
        th = MARKET_CONTEXT_THRESHOLDS["vix_level"]
        if vix >= th["risk_off"]:
            return {
                "label": "Risk Off",
                "score": 0,
                "indicators": indicators,
                "vix": vix,
            }
        if vix <= th["favorable"]:
            score += 1
    except Exception:
        indicators["vix"] = None

    # 5. NASDAQ trend — QQQ above its 50-MA
    try:
        qqq = benchmark.get("QQQ", benchmark.get("SPY")).dropna()
        qqq_ma50 = qqq.rolling(50).mean().iloc[-1]
        qqq_curr = qqq.iloc[-1]
        indicators["qqq_above_50ma"] = qqq_curr > qqq_ma50
        if qqq_curr > qqq_ma50:
            score += 1
    except Exception:
        indicators["qqq_above_50ma"] = None

    # Classify
    if score >= 4:
        label = "Favorable"
    elif score == 3:
        label = "Mixed"
    elif score == 2:
        label = "Caution"
    else:
        label = "Risk Off"

    return {"label": label, "score": score, "indicators": indicators}
