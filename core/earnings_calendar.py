# -*- coding: utf-8 -*-
"""Earnings calendar with per-ticker SQLite cache.

Wraps yfinance `Ticker.get_earnings_dates()` with a local cache so a pipeline
run does not trigger N network calls for every candidate. Also exposes an
``is_in_earnings_blackout`` helper used by the runner to drop short-term
candidates whose next earnings date falls inside a configurable T-2..T+1
window.

Design choices
--------------
- Cache lives in its own SQLite file (``~/.alpha_vault/earnings_cache.db``)
  so it does not interact with the main ``system.db`` migrations/backups.
- TTL defaults to 24 hours which is safe: earnings dates rarely move intraday.
- Failures are swallowed and logged; the helpers return a conservative default
  (``None`` for next date, ``False`` for blackout) so calendar outages never
  silently block all recommendations.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import yfinance as yf
from loguru import logger

from core.data_source import to_yf_ticker

_CACHE_DIR = Path.home() / ".alpha_vault"
_CACHE_PATH = _CACHE_DIR / "earnings_cache.db"
_TTL_SECONDS = 24 * 3600  # 24 hours
_DB_LOCK = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_CACHE_PATH, timeout=15)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS earnings_cache (
            ticker TEXT NOT NULL,
            market TEXT NOT NULL,
            next_earnings_date TEXT,   -- ISO date (YYYY-MM-DD) or NULL if unknown
            fetched_at INTEGER NOT NULL,
            PRIMARY KEY(ticker, market)
        )
        """
    )
    conn.commit()
    return conn


def _cache_get(ticker: str, market: str) -> Optional[tuple[Optional[str], int]]:
    """Return (next_date, fetched_at) if cached, else None."""
    with _DB_LOCK:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT next_earnings_date, fetched_at FROM earnings_cache "
                "WHERE ticker=? AND market=?",
                (ticker, market),
            ).fetchone()
            return (row[0], row[1]) if row else None
        finally:
            conn.close()


def _cache_put(ticker: str, market: str, next_date: Optional[str]) -> None:
    now_ts = int(datetime.now().timestamp())
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO earnings_cache "
                "(ticker, market, next_earnings_date, fetched_at) VALUES (?,?,?,?)",
                (ticker, market, next_date, now_ts),
            )
            conn.commit()
        finally:
            conn.close()


def _fetch_from_yfinance(ticker: str, market: str) -> Optional[str]:
    """Fetch next upcoming earnings date from yfinance.

    Returns ISO date string (YYYY-MM-DD) if a future earnings date exists,
    otherwise None. Returns None on any yfinance failure.
    """
    symbol = to_yf_ticker(ticker, market)
    try:
        t = yf.Ticker(symbol)
        df = t.get_earnings_dates(limit=8)
        if df is None or df.empty:
            return None
        # Index is the earnings datetime (timezone-aware). Keep only future dates.
        now = datetime.now()
        future_dates = []
        for idx in df.index:
            try:
                dt = idx.to_pydatetime()
                # Strip tz for straight date comparison
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                if dt >= now - timedelta(days=1):
                    # Include "today" earnings (same-day release) as still-pending
                    future_dates.append(dt)
            except Exception:
                continue
        if not future_dates:
            return None
        next_dt = min(future_dates)
        return next_dt.strftime("%Y-%m-%d")
    except Exception as e:
        logger.debug(f"earnings_calendar: yfinance fetch failed {symbol}: {e}")
        return None


def get_next_earnings_date(ticker: str, market: str = "us_stock") -> Optional[str]:
    """Return next upcoming earnings date (YYYY-MM-DD) or None.

    Uses a 24h cache; on cache miss queries yfinance.
    """
    cached = _cache_get(ticker, market)
    now_ts = int(datetime.now().timestamp())
    if cached is not None:
        next_date, fetched_at = cached
        if now_ts - fetched_at < _TTL_SECONDS:
            return next_date
    # Refresh
    next_date = _fetch_from_yfinance(ticker, market)
    _cache_put(ticker, market, next_date)
    return next_date


def is_in_earnings_blackout(
    ticker: str,
    market: str = "us_stock",
    ref_date: Optional[str] = None,
    days_before: int = 2,
    days_after: int = 1,
) -> bool:
    """Return True if ``ref_date`` falls within [T-days_before, T+days_after]
    of the ticker's next earnings date.

    ``ref_date`` is in YYYYMMDD format (matches runner convention). If None,
    uses today's date in the market's local sense (caller should pass the
    market ref_date).
    """
    if ref_date is None:
        ref_date = datetime.now().strftime("%Y%m%d")
    try:
        ref = datetime.strptime(ref_date, "%Y%m%d").date()
    except ValueError:
        logger.warning(f"earnings_calendar: invalid ref_date {ref_date}")
        return False

    next_iso = get_next_earnings_date(ticker, market)
    if not next_iso:
        return False
    try:
        earn = datetime.strptime(next_iso, "%Y-%m-%d").date()
    except ValueError:
        return False

    start = earn - timedelta(days=days_before)
    end = earn + timedelta(days=days_after)
    return start <= ref <= end


def days_until_earnings(ticker: str, market: str = "us_stock",
                        ref_date: Optional[str] = None) -> Optional[int]:
    """Return signed days from ref_date to next earnings (negative = past).

    Used by the runner to decide whether to warn / block / pass.
    Returns None if no earnings date is known.
    """
    if ref_date is None:
        ref_date = datetime.now().strftime("%Y%m%d")
    try:
        ref = datetime.strptime(ref_date, "%Y%m%d").date()
    except ValueError:
        return None
    next_iso = get_next_earnings_date(ticker, market)
    if not next_iso:
        return None
    try:
        earn = datetime.strptime(next_iso, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (earn - ref).days


def prefetch_earnings_dates(tickers: list[tuple[str, str]]) -> dict[str, Optional[str]]:
    """Warm the cache for a batch of (ticker, market) pairs.

    Returns a mapping keyed by ticker -> next earnings date (may be None).
    Network calls go one-by-one (yfinance has no bulk endpoint) but cached
    results are served without touching the network.
    """
    out: dict[str, Optional[str]] = {}
    for ticker, market in tickers:
        out[ticker] = get_next_earnings_date(ticker, market)
    return out
