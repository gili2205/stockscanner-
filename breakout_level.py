"""Breakout level classification."""
import pandas as pd
from config import MULTI_YEAR_LOOKBACK_DAYS

def classify_breakout_level(df: pd.DataFrame) -> str:
    """
    Classify where the current price is relative to historical resistance.
    ATH > multi-year high > 52-week high > prior resistance
    """
    try:
        if len(df) < 50:
            return "prior resistance"
        last_close = float(df["Close"].iloc[-1])
        all_time_high = float(df["High"].max())
        high_52w = float(df["High"].tail(252).max())
        multi_year_high = float(df["High"].tail(min(MULTI_YEAR_LOOKBACK_DAYS, len(df))).max())

        tolerance = 0.02  # within 2% counts as "at" that level

        if last_close >= all_time_high * (1 - tolerance):
            return "ATH"
        if last_close >= multi_year_high * (1 - tolerance):
            return "multi-year"
        if last_close >= high_52w * (1 - tolerance):
            return "52-week"
        return "prior resistance"
    except Exception:
        return "prior resistance"
