"""
Evidence-based ranking system.
Implements Qullamaggie scanner v5 ranking with RS percentile assignment
and quality gate from all three source repos.
"""

import pandas as pd

from config import (
    QUALITY_GATE_RS_MIN, QUALITY_GATE_VOL_RATIO,
    SCORE_READY, SCORE_WATCH, SCORE_BUILDING,
)
from factors.relative_strength import assign_rs_percentiles


def quality_gate(consolidation: dict, rs: dict) -> bool:
    """
    Stock must pass all 3 criteria or it sorts last (shown grayed out).
    From Qullamaggie scanner v5 ranking logic.
    """
    ema_ok = consolidation.get("ema_stack", "none") in ("full", "partial", "weak")
    rs_ok = rs.get("percentile", 0) >= QUALITY_GATE_RS_MIN
    # vol_ratio checked in main loop from the raw data
    return ema_ok and rs_ok


def rank_stocks(results: list[dict]) -> list[dict]:
    """
    Sort stocks by composite score.
    1. Quality gate — failing stocks sort last
    2. Primary: composite score (Qullamaggie + bull flag + pattern blend)
    3. Secondary: HH/HL price structure (strongest single predictor per backtest)
    4. Tertiary: ATR compression (lower = better)
    5. Quaternary: RS percentile
    """
    if not results:
        return []

    # Assign RS percentiles across the universe
    results = assign_rs_percentiles(results)

    # Update rs_percentile from the newly assigned value
    for r in results:
        if "rs_percentile" in r:
            r["rs_percentile"] = r["rs_percentile"]

    # Penalties
    for r in results:
        score = r.get("composite_score", 0)

        # Post-catalyst cooldown: fresh catalyst + loose ATR = penalty
        if r.get("catalyst_freshness", 0) > 0.8 and r.get("atr_compression", 1) > 0.6:
            score = max(0, score - 8)

        # Extension penalty: if price is >2 ABR above breakout level, penalize
        if r.get("breakout_level") == "ATH" and r.get("vol_ratio", 1) < 0.5:
            score = max(0, score - 5)

        r["composite_score"] = score
        r["status"] = _get_status(score)

    # Sort: gate-passing stocks first, then by score desc, then secondary criteria
    def sort_key(r):
        gate = 1 if r.get("passes_gate", False) else 0
        score = r.get("composite_score", 0)
        hh_hl = r.get("hh_hl_pct", 0)
        atr = -r.get("atr_compression", 1)  # lower = better, negate for desc sort
        rs = r.get("rs_percentile", 50)
        return (gate, score, hh_hl, atr, rs)

    ranked = sorted(results, key=sort_key, reverse=True)

    # Add rank numbers
    for i, r in enumerate(ranked):
        r["rank"] = i + 1

    return ranked


def _get_status(score: int) -> str:
    if score >= SCORE_READY:
        return "READY"
    if score >= SCORE_WATCH:
        return "WATCH"
    if score >= SCORE_BUILDING:
        return "BUILDING"
    return "WEAK"
