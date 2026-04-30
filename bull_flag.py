"""
Bull flag pattern detection.
Based on Ross Cameron's day trading methodology (saturn-amarbat/trade-ops).
Detects: pole (strong up move) + flag (tight consolidation, volume contraction).
"""

import numpy as np
import pandas as pd

from config import (
    POLE_MIN_GAIN, POLE_MIN_DAYS, POLE_MAX_DAYS, POLE_VOL_SPIKE,
    FLAG_MIN_DAYS, FLAG_MAX_DAYS, FLAG_MAX_RETRACE,
    FLAG_TIGHTNESS_IDEAL, FLAG_TIGHTNESS_OK, FLAG_VOL_CONTRACTION,
    FLAG_SCORE_TIGHTNESS, FLAG_SCORE_VOL_CONTRACT,
    FLAG_SCORE_RECENCY, FLAG_SCORE_POLE_STRENGTH,
)


def detect_bull_flag(df: pd.DataFrame) -> tuple[bool, dict]:
    """
    Detect if the stock is forming a bull flag pattern.
    Returns (flag_detected: bool, flag_data: dict)
    """
    empty = {"tightness": None, "vol_contraction": None, "pole_gain": None,
             "flag_days": None, "days_since_pole_end": None}

    try:
        if len(df) < 30:
            return False, empty

        closes = df["Close"].values
        highs = df["High"].values
        lows = df["Low"].values
        volumes = df["Volume"].values
        n = len(df)

        avg_vol_20 = float(df["Volume"].iloc[-40:-20].mean()) if n >= 40 else float(df["Volume"].mean())

        # Scan backward to find a pole
        best_flag = None
        best_score = 0

        for pole_end in range(n - FLAG_MIN_DAYS - 1, n - FLAG_MAX_DAYS - POLE_MAX_DAYS, -1):
            if pole_end < POLE_MIN_DAYS:
                break

            # Try different pole start points
            for pole_start in range(max(0, pole_end - POLE_MAX_DAYS), max(0, pole_end - POLE_MIN_DAYS)):
                pole_low = float(np.min(lows[pole_start:pole_end + 1]))
                pole_high = float(highs[pole_end])

                if pole_low <= 0:
                    continue

                pole_gain = (pole_high - pole_low) / pole_low
                if pole_gain < POLE_MIN_GAIN:
                    continue

                # Check pole volume was elevated
                pole_vol = float(np.mean(volumes[pole_start:pole_end + 1]))
                if pole_vol < avg_vol_20 * POLE_VOL_SPIKE:
                    continue

                # Now look for flag after pole
                flag_start = pole_end + 1
                flag_end = min(n - 1, flag_start + FLAG_MAX_DAYS - 1)

                if flag_start >= n:
                    continue

                flag_closes = closes[flag_start:flag_end + 1]
                flag_highs = highs[flag_start:flag_end + 1]
                flag_lows = lows[flag_start:flag_end + 1]
                flag_vols = volumes[flag_start:flag_end + 1]

                if len(flag_closes) < FLAG_MIN_DAYS:
                    continue

                # Flag retracement check (shouldn't retrace more than 50% of pole)
                flag_low = float(np.min(flag_lows))
                retrace = (pole_high - flag_low) / (pole_high - pole_low) if (pole_high - pole_low) > 0 else 1
                if retrace > FLAG_MAX_RETRACE:
                    continue

                # Flag tightness: average daily range as % of price
                daily_ranges = (flag_highs - flag_lows) / (flag_closes + 1e-9)
                tightness = float(np.mean(daily_ranges))

                # Volume contraction in flag vs pole
                flag_vol_avg = float(np.mean(flag_vols))
                vol_contraction = flag_vol_avg / pole_vol if pole_vol > 0 else 1.0

                if vol_contraction >= 1.0:  # flag volume must be lower than pole
                    continue

                # Compute flag score
                score = _score(tightness, vol_contraction, pole_gain,
                               n - 1 - flag_end)  # days_since_flag_end

                if score > best_score:
                    best_score = score
                    best_flag = {
                        "tightness": round(tightness, 4),
                        "vol_contraction": round(vol_contraction, 3),
                        "pole_gain": round(pole_gain, 3),
                        "flag_days": len(flag_closes),
                        "days_since_pole_end": n - 1 - pole_end,
                        "retrace_pct": round(retrace, 3),
                        "score": score,
                    }

        if best_flag and best_score >= 40:
            return True, best_flag

    except Exception:
        pass

    return False, empty


def score_bull_flag(flag_data: dict) -> float:
    """
    Score bull flag quality 0–100.
    Called only when flag_detected is True.
    """
    if not flag_data or flag_data.get("tightness") is None:
        return 0.0

    score = _score(
        flag_data["tightness"],
        flag_data["vol_contraction"],
        flag_data["pole_gain"],
        flag_data.get("days_since_pole_end", 10),
    )
    return min(100.0, float(score))


def _score(tightness: float, vol_contraction: float, pole_gain: float, days_since: int) -> float:
    score = 0.0

    # Tightness (40 pts)
    if tightness <= FLAG_TIGHTNESS_IDEAL:
        score += FLAG_SCORE_TIGHTNESS
    elif tightness <= FLAG_TIGHTNESS_OK:
        score += FLAG_SCORE_TIGHTNESS * 0.6
    elif tightness <= 0.08:
        score += FLAG_SCORE_TIGHTNESS * 0.3

    # Volume contraction (30 pts)
    if vol_contraction <= FLAG_VOL_CONTRACTION:
        score += FLAG_SCORE_VOL_CONTRACT
    elif vol_contraction <= 0.85:
        score += FLAG_SCORE_VOL_CONTRACT * 0.5

    # Recency bonus (20 pts) — fresher flags score higher
    if days_since <= 3:
        score += FLAG_SCORE_RECENCY
    elif days_since <= 7:
        score += FLAG_SCORE_RECENCY * 0.7
    elif days_since <= 15:
        score += FLAG_SCORE_RECENCY * 0.4

    # Pole strength (10 pts)
    if pole_gain >= 0.30:
        score += FLAG_SCORE_POLE_STRENGTH
    elif pole_gain >= 0.20:
        score += FLAG_SCORE_POLE_STRENGTH * 0.7
    elif pole_gain >= 0.10:
        score += FLAG_SCORE_POLE_STRENGTH * 0.4

    return score
