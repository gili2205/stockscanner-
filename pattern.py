"""
Pattern quality scoring system.
Based on slimbiggins007/breakout-scanner logic.
Scores 4 setup types: tight base, weekly base, trendline compression, undercut & rally.
Final score: 0-100 (40pts pattern, 30pts trend, 20pts momentum, 10pts sector bonus).
"""

import numpy as np
import pandas as pd

from config import (
    EMA_PERIODS, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    PATTERN_SCORE_QUALITY, PATTERN_SCORE_TREND,
    PATTERN_SCORE_MOMENTUM, PATTERN_SCORE_SECTOR,
    LEADING_SECTORS,
)


def score_pattern_quality(df: pd.DataFrame, sector: str = "") -> dict:
    """
    Score pattern quality for a stock.
    Returns: {score, setup_type, macd_curl, trend_alignment}
    """
    result = {"score": 0, "setup_type": "None", "macd_curl": False, "trend_alignment": False}

    try:
        if len(df) < 60:
            return result

        df = df.copy()
        _add_indicators(df)

        # Detect best setup type
        setups = {
            "Tight Base": _score_tight_base(df),
            "Weekly Base": _score_weekly_base(df),
            "Trendline": _score_trendline_compression(df),
            "Undercut Rally": _score_undercut_rally(df),
        }

        best_type = max(setups, key=lambda k: setups[k]["quality"])
        best = setups[best_type]

        # Trend alignment (30 pts)
        trend_score, trend_aligned = _score_trend(df)

        # Momentum (20 pts)
        momentum_score, macd_curl = _score_momentum(df)

        # Sector bonus (10 pts)
        sector_score = PATTERN_SCORE_SECTOR if sector in LEADING_SECTORS else 0

        total = (
            best["quality"]           # 0-40
            + trend_score             # 0-30
            + momentum_score          # 0-20
            + sector_score            # 0-10
        )

        result.update({
            "score": max(0, min(100, round(float(total)))),
            "setup_type": best_type,
            "setup_score": round(float(best["quality"])),
            "macd_curl": macd_curl,
            "trend_alignment": trend_aligned,
        })

    except Exception:
        pass

    return result


def _add_indicators(df: pd.DataFrame):
    """Add EMA, MACD to df in-place."""
    for p in EMA_PERIODS:
        df[f"ema{p}"] = df["Close"].ewm(span=p, adjust=False).mean()

    df["ema9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["Close"].ewm(span=21, adjust=False).mean()

    ema_fast = df["Close"].ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = df["Close"].ewm(span=MACD_SLOW, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
    df["macd"] = macd_line
    df["macd_signal"] = signal_line
    df["macd_hist"] = macd_line - signal_line


def _score_tight_base(df: pd.DataFrame) -> dict:
    """3-7 day consolidation near highs, EMAs stacked, volume drying up."""
    quality = 0.0
    lookback = 10
    recent = df.tail(lookback)

    # Tightness: range of recent highs/lows
    high_range = (recent["High"].max() - recent["Low"].min()) / recent["Close"].mean()
    if high_range < 0.05:
        quality += 20
    elif high_range < 0.08:
        quality += 12
    elif high_range < 0.12:
        quality += 6

    # Near recent highs
    n52wk = df["High"].tail(252).max()
    curr = df["Close"].iloc[-1]
    if curr >= n52wk * 0.97:
        quality += 12
    elif curr >= n52wk * 0.93:
        quality += 7

    # Volume drying up in base
    base_vol = recent["Volume"].mean()
    prior_vol = df["Volume"].iloc[-40:-10].mean()
    if base_vol < prior_vol * 0.7:
        quality += 8
    elif base_vol < prior_vol * 0.85:
        quality += 4

    return {"quality": min(40, quality)}


def _score_weekly_base(df: pd.DataFrame) -> dict:
    """Multi-week base under horizontal resistance, EMAs crossing."""
    quality = 0.0
    lookback = 20

    if len(df) < lookback + 10:
        return {"quality": 0}

    recent = df.tail(lookback)

    # Horizontal resistance: highs clustered within 5%
    high_range = recent["High"].max() / recent["High"].min()
    if high_range < 1.05:
        quality += 20
    elif high_range < 1.08:
        quality += 12

    # Duration appropriate (3-8 weeks)
    quality += 10  # credit for being in this window

    # EMAs converging
    e10 = float(df["ema10"].iloc[-1])
    e20 = float(df["ema20"].iloc[-1])
    e50 = float(df["ema50"].iloc[-1])
    spread = (e10 - e50) / e50 if e50 > 0 else 1
    if spread < 0.03:
        quality += 10  # EMAs tightly converged

    return {"quality": min(40, quality)}


def _score_trendline_compression(df: pd.DataFrame) -> dict:
    """Descending highs + horizontal support converging into a wedge."""
    quality = 0.0

    if len(df) < 25:
        return {"quality": 0}

    recent = df.tail(20)
    highs = recent["High"].values
    lows = recent["Low"].values

    # Descending highs (resistance line declining)
    high_slope = np.polyfit(range(len(highs)), highs, 1)[0]
    low_slope = np.polyfit(range(len(lows)), lows, 1)[0]

    if high_slope < 0 and low_slope >= 0:
        quality += 25  # converging wedge
    elif high_slope < 0:
        quality += 12

    # Compression: recent range < historical range
    recent_range = highs[-5:].max() - lows[-5:].min()
    prior_range = highs[:10].max() - lows[:10].min()
    if prior_range > 0 and recent_range / prior_range < 0.5:
        quality += 15
    elif prior_range > 0 and recent_range / prior_range < 0.7:
        quality += 8

    return {"quality": min(40, quality)}


def _score_undercut_rally(df: pd.DataFrame) -> dict:
    """False breakdown below support then recovery back above on volume."""
    quality = 0.0

    if len(df) < 20:
        return {"quality": 0}

    # Look for: recent low that undercut a prior support, then rallied back
    recent = df.tail(15)
    prior = df.iloc[-30:-15]

    if prior.empty:
        return {"quality": 0}

    support_level = float(prior["Low"].mean())
    recent_low = float(recent["Low"].min())
    current_close = float(df["Close"].iloc[-1])

    # Did price dip below support and recover?
    undercut = recent_low < support_level * 0.98
    recovered = current_close > support_level

    if undercut and recovered:
        quality += 25

        # Volume check: recovery volume > undercut volume
        undercut_idx = recent["Low"].idxmin()
        if undercut_idx in df.index:
            undercut_vol = float(df.loc[undercut_idx, "Volume"])
            recovery_vol = float(df["Volume"].iloc[-3:].mean())
            if recovery_vol > undercut_vol:
                quality += 15
        else:
            quality += 8

    return {"quality": min(40, quality)}


def _score_trend(df: pd.DataFrame) -> tuple[float, bool]:
    """Trend alignment: EMA order, rising, price above EMAs."""
    score = 0.0
    last = df.iloc[-1]

    try:
        e9, e21, e50 = last.get("ema9", 0), last.get("ema21", 0), last.get("ema50", 0)
        price = last["Close"]

        # EMA order (10 pts)
        if e9 > e21 > e50:
            score += 10

        # All EMAs rising (10 pts)
        slope9 = df["ema9"].iloc[-1] > df["ema9"].iloc[-5] if "ema9" in df.columns else False
        slope21 = df["ema21"].iloc[-1] > df["ema21"].iloc[-5] if "ema21" in df.columns else False
        slope50 = df["ema50"].iloc[-1] > df["ema50"].iloc[-10]
        if slope9 and slope21 and slope50:
            score += 10

        # Price above EMAs (10 pts)
        if price > e9 > e21:
            score += 10

        aligned = score >= 20
    except Exception:
        aligned = False

    return min(30.0, score), aligned


def _score_momentum(df: pd.DataFrame) -> tuple[float, bool]:
    """MACD histogram curl + volume pattern."""
    score = 0.0
    macd_curl = False

    try:
        hist = df["macd_hist"].dropna()
        if len(hist) >= 5:
            # MACD curl: histogram turning from negative to less negative (or positive)
            recent_hist = hist.iloc[-5:].values
            if recent_hist[-1] > recent_hist[-2] > recent_hist[-3]:
                macd_curl = True
                if recent_hist[-1] > 0:
                    score += 15  # MACD crossed zero
                else:
                    score += 10  # Still negative but improving

        # Volume pattern: recent volume expanding on up days
        recent = df.tail(10)
        up_days = recent[recent["Close"] > recent["Open"]]
        dn_days = recent[recent["Close"] <= recent["Open"]]
        if not up_days.empty and not dn_days.empty:
            up_vol = up_days["Volume"].mean()
            dn_vol = dn_days["Volume"].mean()
            if up_vol > dn_vol * 1.2:
                score += 5

    except Exception:
        pass

    return min(20.0, score), macd_curl
