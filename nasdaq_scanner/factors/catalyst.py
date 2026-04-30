"""
Catalyst detection factor.
Volume spike detection with half-life freshness scoring.
From Qullamaggie scanner catalyst.py logic.
"""

import math
import numpy as np
import pandas as pd

from config import (
    VOLUME_SPIKE_THRESHOLD, CATALYST_HALFLIFE,
    FRESHNESS_AGE_WEIGHT, FRESHNESS_EXT_WEIGHT,
    EARNINGS_LOOKBACK_DAYS,
)


def score_catalyst(df: pd.DataFrame) -> dict:
    """
    Detect the most recent volume spike catalyst and score its freshness.
    Returns: {tier, days_ago, freshness, spike_ratio}
    """
    result = {"tier": None, "days_ago": None, "freshness": 0.0, "spike_ratio": 0.0, "has_catalyst": False}

    try:
        if len(df) < 25:
            return result

        vol = df["Volume"].copy()
        avg_vol = vol.rolling(20).mean().shift(1)  # avoid lookahead
        spike_ratio = vol / avg_vol

        # Find the most recent significant volume spike
        recent = df.tail(EARNINGS_LOOKBACK_DAYS).copy()
        recent_ratio = spike_ratio.tail(EARNINGS_LOOKBACK_DAYS)

        spikes = recent_ratio[recent_ratio >= VOLUME_SPIKE_THRESHOLD]
        if spikes.empty:
            return result

        # Get most recent spike
        last_spike_idx = spikes.index[-1]
        days_ago = len(df) - df.index.get_loc(last_spike_idx) - 1
        spike_val = float(spikes.iloc[-1])

        # Classify tier by spike magnitude
        if spike_val >= 10:
            tier = "tier1"
        elif spike_val >= 5:
            tier = "tier2"
        else:
            tier = "tier3"

        halflife = CATALYST_HALFLIFE[tier]

        # Age freshness: exponential decay
        age_freshness = math.exp(-math.log(2) * days_ago / halflife)

        # Extension freshness: how far has the stock moved from the catalyst bar?
        catalyst_close = float(df.loc[last_spike_idx, "Close"]) if last_spike_idx in df.index else float(df["Close"].iloc[-1])
        current_close = float(df["Close"].iloc[-1])
        extension = abs(current_close - catalyst_close) / catalyst_close if catalyst_close > 0 else 0
        ext_freshness = max(0.0, 1.0 - extension * 3)  # penalize if >33% extended

        freshness = FRESHNESS_AGE_WEIGHT * age_freshness + FRESHNESS_EXT_WEIGHT * ext_freshness

        result.update({
            "tier": tier,
            "days_ago": days_ago,
            "freshness": round(float(freshness), 3),
            "spike_ratio": round(spike_val, 2),
            "has_catalyst": True,
        })

    except Exception:
        pass

    return result
