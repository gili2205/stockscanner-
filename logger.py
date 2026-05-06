"""
Scanner History Logger
======================
Called by live_scanner.py after each push_results().
Logs daily snapshot of top picks with full signal data to Firebase:
  /scanner/history/YYYY-MM-DD/{ticker}: { signals, score, price, ... }

Only writes once per trading day per ticker.
Also tracks first-seen date per ticker for analytics.
"""

import logging
from datetime import datetime, date
import pytz
from firebase_admin import db

log = logging.getLogger(__name__)
ET  = pytz.timezone("America/New_York")

_logged_today = set()
_log_date     = None


def log_scan_results(results: list, session: str):
    """
    Call after push_results(). Writes daily history to Firebase.
    Only logs once per ticker per day.
    """
    global _logged_today, _log_date

    today = date.today()
    if _log_date != today:
        _logged_today = set()
        _log_date = today

    if session not in ("Market Open", "Pre-Market"):
        return

    now_et   = datetime.now(ET)
    date_str = today.isoformat()
    hist_ref = db.reference(f"/scanner/history/{date_str}")
    first_ref= db.reference("/scanner/first_seen")

    new_entries = {}
    new_first   = {}

    for r in results[:200]:
        ticker = r.get("ticker")
        if not ticker or ticker in _logged_today:
            continue

        entry = {
            "ticker":          ticker,
            "scan_date":       date_str,
            "scan_ts":         now_et.isoformat(),
            "price_at_scan":   r.get("price"),
            "rank":            r.get("rank"),
            "status":          r.get("status"),
            "track":           r.get("track", "BREAKOUT"),
            "score":           r.get("score"),
            "breakout_score":  r.get("breakout_score"),
            "catalyst_score":  r.get("catalyst_score"),
            "rs_percentile":   r.get("rs_percentile"),
            "vol_contraction": r.get("vol_contraction"),
            "vol_ratio":       r.get("vol_ratio"),
            "atr":             r.get("atr"),
            "ema_stack":       r.get("ema_stack"),
            "level":           r.get("level"),
            "dist_to_level":   r.get("dist_to_level"),
            "hh_hl":           r.get("hh_hl"),
            "momentum_1m":     r.get("momentum_1m"),
            "momentum_3m":     r.get("momentum_3m"),
            "pre_breakout":    bool(r.get("pre_breakout", False)),
            "bull_flag":       bool(r.get("bull_flag", False)),
            "days_to_earnings":r.get("days_to_earnings"),
            "earnings_soon":   bool(r.get("earnings_soon", False)),
            "analyst_upside":  r.get("analyst_upside"),
            "analyst_buy_pct": r.get("analyst_buy_pct"),
            "num_analysts":    r.get("num_analysts"),
            "recommendation":  r.get("recommendation", ""),
            "pe_ratio":        r.get("pe_ratio"),
            "analyst_target":  r.get("analyst_target"),
            "timeframe":       r.get("timeframe", "mid"),
            "returns":         {}
        }

        new_entries[ticker] = entry
        _logged_today.add(ticker)
        new_first[ticker] = {
            "date":  date_str,
            "price": r.get("price"),
            "score": r.get("score"),
        }

    if not new_entries:
        return

    try:
        hist_ref.update(new_entries)
        existing  = first_ref.get() or {}
        truly_new = {k: v for k, v in new_first.items() if k not in existing}
        if truly_new:
            first_ref.update(truly_new)
        log.info(f"History logged: {len(new_entries)} tickers for {date_str} "
                 f"({len(truly_new)} new first-seen)")
    except Exception as e:
        log.error(f"History log failed: {e}")
