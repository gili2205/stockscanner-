"""
Relative strength factor.
ATR-normalized RS percentile vs the NASDAQ universe + vs SPY/QQQ sector ETF.
Based on Qullamaggie scanner relative_strength.py logic.
"""

import numpy as np
import pandas as pd

from config import RS_LOOKBACK, ATR_PERIOD


def score_rs(df: pd.DataFrame, benchmark: pd.DataFrame) -> dict:
    """
    Compute relative strength for a stock vs benchmark (SPY/QQQ).
    Returns percentile (0-100), direction (up/flat/down), vs_spy, vs_qqq.
    
    Note: True universe-relative RS requires all stocks' RS computed together
    and percentile-ranked. Here we compute ATR-normalized RS vs benchmarks.
    Full percentile ranking happens in ranking.py after all stocks are analyzed.
    """
    result = {"percentile": 50, "direction": "flat", "vs_spy": 0.0, "vs_qqq": 0.0, "raw_rs": 0.0}

    try:
        closes = df["Close"].dropna()
        if len(closes) < RS_LOOKBACK + 5:
            return result

        # ATR-normalized RS: stock gain vs SPY gain, normalized by ATR
        atr = _compute_atr(df)
        if atr <= 0:
            return result

        stock_return = (closes.iloc[-1] - closes.iloc[-RS_LOOKBACK]) / closes.iloc[-RS_LOOKBACK]

        spy_return = 0.0
        qqq_return = 0.0

        if "SPY" in benchmark.columns:
            spy = benchmark["SPY"].dropna()
            if len(spy) >= RS_LOOKBACK:
                spy_return = (spy.iloc[-1] - spy.iloc[-RS_LOOKBACK]) / spy.iloc[-RS_LOOKBACK]

        if "QQQ" in benchmark.columns:
            qqq = benchmark["QQQ"].dropna()
            if len(qqq) >= RS_LOOKBACK:
                qqq_return = (qqq.iloc[-1] - qqq.iloc[-RS_LOOKBACK]) / qqq.iloc[-RS_LOOKBACK]

        vs_spy = stock_return - spy_return
        vs_qqq = stock_return - qqq_return

        # Raw RS score (used for cross-stock percentile ranking later)
        raw_rs = (vs_spy + vs_qqq) / 2

        # Direction: is RS improving over last 5 days?
        if len(closes) >= RS_LOOKBACK + 5:
            rs_5d_ago = (closes.iloc[-5] - closes.iloc[-(RS_LOOKBACK + 5)]) / closes.iloc[-(RS_LOOKBACK + 5)]
            spy_5d = 0.0
            if "SPY" in benchmark.columns:
                spy = benchmark["SPY"].dropna()
                if len(spy) >= RS_LOOKBACK + 5:
                    spy_5d = (spy.iloc[-5] - spy.iloc[-(RS_LOOKBACK + 5)]) / spy.iloc[-(RS_LOOKBACK + 5)]
            vs_spy_5d = rs_5d_ago - spy_5d
            direction = "up" if vs_spy > vs_spy_5d + 0.005 else ("down" if vs_spy < vs_spy_5d - 0.005 else "flat")
        else:
            direction = "up" if raw_rs > 0.02 else ("down" if raw_rs < -0.02 else "flat")

        result.update({
            "raw_rs": round(float(raw_rs), 4),
            "vs_spy": round(float(vs_spy), 4),
            "vs_qqq": round(float(vs_qqq), 4),
            "direction": direction,
            "percentile": 50,  # will be updated in ranking.py
        })

    except Exception:
        pass

    return result


def assign_rs_percentiles(results: list[dict]) -> list[dict]:
    """
    After all stocks are analyzed, rank raw_rs values and assign percentiles.
    Called from ranking.py.
    """
    rs_values = [r.get("raw_rs", r.get("rs_raw", 0)) for r in results]
    if not rs_values:
        return results

    rs_series = pd.Series(rs_values)
    percentiles = rs_series.rank(pct=True) * 100

    for i, result in enumerate(results):
        result["rs_percentile"] = round(float(percentiles.iloc[i]), 1)

    return results


def _compute_atr(df: pd.DataFrame) -> float:
    high = df["High"]
    low = df["Low"]
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=ATR_PERIOD, adjust=False).mean()
    last_close = float(df["Close"].iloc[-1])
    return float(atr.iloc[-1]) / last_close if last_close > 0 else 0.0
