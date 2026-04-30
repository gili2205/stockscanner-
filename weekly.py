"""Weekly timeframe confluence scoring."""
import pandas as pd
from config import EMA_PERIODS

def score_weekly_confluence(df: pd.DataFrame) -> dict:
    """
    Resample daily data to weekly and check if weekly chart also shows
    a coiling/breakout setup. When daily + weekly align, moves tend to be bigger.
    """
    result = {"confluence": False, "weekly_ema_stack": False, "weekly_coiling": False}
    try:
        if len(df) < 60:
            return result

        # Resample to weekly OHLCV
        df_idx = df.set_index("Date") if "Date" in df.columns else df
        weekly = df_idx.resample("W").agg({
            "Open": "first", "High": "max", "Low": "min",
            "Close": "last", "Volume": "sum"
        }).dropna()

        if len(weekly) < 20:
            return result

        # Weekly EMA stack
        w_ema10 = weekly["Close"].ewm(span=10, adjust=False).mean()
        w_ema20 = weekly["Close"].ewm(span=20, adjust=False).mean()
        w_ema40 = weekly["Close"].ewm(span=40, adjust=False).mean()
        stack = (w_ema10.iloc[-1] > w_ema20.iloc[-1] > w_ema40.iloc[-1]
                 and weekly["Close"].iloc[-1] > w_ema10.iloc[-1])

        # Weekly coiling: ATR compression on weekly
        w_atr = (weekly["High"] - weekly["Low"]).rolling(14).mean()
        recent_w_atr = w_atr.iloc[-4:].mean()
        base_w_atr = w_atr.iloc[-20:-12].mean()
        coiling = (recent_w_atr / base_w_atr < 0.8) if base_w_atr > 0 else False

        confluence = stack and coiling
        result.update({
            "confluence": bool(confluence),
            "weekly_ema_stack": bool(stack),
            "weekly_coiling": bool(coiling),
        })
    except Exception:
        pass
    return result
