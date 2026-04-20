# -*- coding: utf-8 -*-
"""Options PCR history store and percentile-based signal scoring.

Persists a rolling 30-day window of put/call ratios per ticker in a small
SQLite file (``~/.alpha_vault/options_pcr_history.db``). The raw PCR reading
alone is too noisy to score on (mega-caps have structurally different PCR
levels than biotech), so instead we compute the *percentile* of today's PCR
within each ticker's own recent history.

Signal interpretation (contrarian):
- current PCR at 90th+ percentile = historic fear -> bullish reversal bias
- current PCR at 10th- percentile = historic greed -> bearish reversal bias
- middle band = no signal

This is only a *modifier* on technical score (±3 points) and a risk_flag; it
never drives a standalone recommendation.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger

_DB_DIR = Path.home() / ".alpha_vault"
_DB_PATH = _DB_DIR / "options_pcr_history.db"
_DB_LOCK = threading.Lock()

_HISTORY_DAYS = 30  # Rolling window
_MIN_SAMPLES_FOR_PERCENTILE = 10
_EXTREME_HIGH_PCT = 0.90
_EXTREME_LOW_PCT = 0.10


def _get_conn() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=15)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pcr_history (
            ticker TEXT NOT NULL,
            date   TEXT NOT NULL,
            pcr    REAL NOT NULL,
            PRIMARY KEY(ticker, date)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pcr_ticker ON pcr_history(ticker)")
    conn.commit()
    return conn


def record_pcr(ticker: str, pcr: float, date: Optional[str] = None) -> None:
    """Upsert today's PCR reading for a ticker. ``date`` defaults to today."""
    if pcr is None or pcr <= 0:
        return
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO pcr_history(ticker, date, pcr) VALUES (?,?,?)",
                (ticker, date, float(pcr)),
            )
            conn.commit()
        finally:
            conn.close()


def get_history(ticker: str, window_days: int = _HISTORY_DAYS) -> list[float]:
    """Return last N days of PCR values for this ticker (oldest first)."""
    cutoff = (datetime.now() - timedelta(days=window_days)).strftime("%Y-%m-%d")
    with _DB_LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT pcr FROM pcr_history WHERE ticker=? AND date >= ? "
                "ORDER BY date ASC",
                (ticker, cutoff),
            ).fetchall()
            return [float(r[0]) for r in rows]
        finally:
            conn.close()


def prune_old_entries(keep_days: int = _HISTORY_DAYS + 7) -> int:
    """Delete rows older than ``keep_days``. Returns number removed."""
    cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    with _DB_LOCK:
        conn = _get_conn()
        try:
            cur = conn.execute("DELETE FROM pcr_history WHERE date < ?", (cutoff,))
            conn.commit()
            return cur.rowcount or 0
        finally:
            conn.close()


def _percentile_rank(value: float, sorted_history: list[float]) -> float:
    """Return the fraction of history entries <= value (0.0-1.0)."""
    if not sorted_history:
        return 0.5
    # Simple empirical CDF; ties count as half (standard mid-rank convention)
    below = sum(1 for v in sorted_history if v < value)
    equal = sum(1 for v in sorted_history if v == value)
    return (below + 0.5 * equal) / len(sorted_history)


def compute_options_signal(
    ticker: str,
    options_data: dict | None,
) -> dict:
    """Compute PCR percentile signal for a ticker.

    Records today's reading as a side effect so the history grows over time.

    Returns a dict with:
    - ``pcr``: today's put/call ratio (float, 0 if unavailable)
    - ``percentile``: today's reading's rank in the 30-day window (0.0-1.0)
    - ``samples``: number of historical samples used
    - ``signal``: one of ``extreme_fear`` | ``extreme_greed`` | ``neutral``
                  | ``insufficient_data``
    - ``score_delta``: int in [-3, 3] to add to technical_score
    - ``risk_flag``: optional Chinese risk flag string (or empty)
    """
    out = {
        "pcr": 0.0,
        "percentile": 0.5,
        "samples": 0,
        "signal": "insufficient_data",
        "score_delta": 0,
        "risk_flag": "",
    }
    if not options_data or not isinstance(options_data, dict):
        return out

    pcr = options_data.get("put_call_ratio")
    if pcr is None:
        return out
    try:
        pcr_f = float(pcr)
    except (TypeError, ValueError):
        return out
    if pcr_f <= 0:
        return out

    # Record today's reading (before computing percentile, so it is excluded
    # from the history we compare against - otherwise today trivially ranks
    # mid-pack against itself on low-sample days)
    try:
        history = get_history(ticker, _HISTORY_DAYS)
    except Exception as e:
        logger.debug(f"options_history read failed {ticker}: {e}")
        history = []
    try:
        record_pcr(ticker, pcr_f)
    except Exception as e:
        logger.debug(f"options_history write failed {ticker}: {e}")

    out["pcr"] = round(pcr_f, 2)
    out["samples"] = len(history)

    if len(history) < _MIN_SAMPLES_FOR_PERCENTILE:
        out["signal"] = "insufficient_data"
        return out

    sorted_hist = sorted(history)
    pct = _percentile_rank(pcr_f, sorted_hist)
    out["percentile"] = round(pct, 3)

    if pct >= _EXTREME_HIGH_PCT:
        # Extreme fear (everyone buying puts) - contrarian bullish +3
        out["signal"] = "extreme_fear"
        out["score_delta"] = 3
        out["risk_flag"] = "\u671f\u6743\u6050\u614c\u6781\u7aef"  # 期权恐慌极端
    elif pct <= _EXTREME_LOW_PCT:
        # Extreme greed (everyone buying calls) - contrarian bearish -3
        out["signal"] = "extreme_greed"
        out["score_delta"] = -3
        out["risk_flag"] = "\u671f\u6743\u8d2a\u5a6a\u6781\u7aef"  # 期权贪婪极端
    else:
        out["signal"] = "neutral"

    return out
