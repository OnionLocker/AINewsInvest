"""Macro economic indicators via yfinance — no FRED API key needed.

Fetches US Treasury yields through Yahoo Finance ticker proxies:
  ^TNX  → 10-Year Treasury Yield (%)
  ^FVX  → 5-Year Treasury Yield (%)
  ^IRX  → 13-Week Treasury Bill Rate (%)

The 10Y-5Y spread is used as a proxy for the classic 10Y-2Y yield
curve indicator. A negative spread signals recession risk.

All data is cached for 4 hours to avoid redundant API calls within
a single pipeline run.
"""

from __future__ import annotations

import time
from typing import Any

import yfinance as yf
from loguru import logger


# ---------------------------------------------------------------------------
# Module-level cache (4-hour TTL)
# ---------------------------------------------------------------------------

_cache: dict[str, Any] = {}
_cache_ts: float = 0.0
_CACHE_TTL = 4 * 3600  # 4 hours


def _is_cache_valid() -> bool:
    return bool(_cache) and (time.time() - _cache_ts < _CACHE_TTL)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_macro_indicators() -> dict[str, Any]:
    """Fetch key macro indicators for regime detection.

    Returns:
        {
            "yield_10y": float | None,      # 10-Year Treasury Yield (%)
            "yield_5y": float | None,       # 5-Year Treasury Yield (%)
            "yield_3m": float | None,       # 13-Week T-Bill Rate (%)
            "yield_spread_10y5y": float | None,  # 10Y - 5Y spread
            "yield_spread_10y3m": float | None,  # 10Y - 3M spread (broader inversion)
            "spread_trend": "steepening" | "flattening" | "stable" | "unknown",
            "macro_risk_level": "low" | "moderate" | "elevated" | "high",
            "flags": list[str],
            "_fetched": bool,
        }
    """
    global _cache, _cache_ts

    if _is_cache_valid():
        return _cache

    result = _fetch_yields()
    _cache = result
    _cache_ts = time.time()
    return result


def _fetch_yields() -> dict[str, Any]:
    """Internal: fetch yield data from yfinance."""
    empty = {
        "yield_10y": None, "yield_5y": None, "yield_3m": None,
        "yield_spread_10y5y": None, "yield_spread_10y3m": None,
        "spread_trend": "unknown", "macro_risk_level": "moderate",
        "flags": ["macro_data_unavailable"], "_fetched": False,
    }

    try:
        # Fetch 6 days to compute trend
        tickers = yf.download(
            "^TNX ^FVX ^IRX",
            period="6d",
            progress=False,
            threads=True,
        )

        if tickers.empty:
            logger.warning("Macro indicators: yfinance returned empty data")
            return empty

        closes = tickers["Close"] if "Close" in tickers.columns.get_level_values(0) else tickers

        # Extract latest values
        yield_10y = _last_valid(closes, "^TNX")
        yield_5y = _last_valid(closes, "^FVX")
        yield_3m = _last_valid(closes, "^IRX")

        # Compute spreads
        spread_10y5y = round(yield_10y - yield_5y, 3) if yield_10y is not None and yield_5y is not None else None
        spread_10y3m = round(yield_10y - yield_3m, 3) if yield_10y is not None and yield_3m is not None else None

        # Spread trend: compare today vs 5 days ago
        spread_trend = _compute_spread_trend(closes, "^TNX", "^FVX")

        # Macro risk assessment
        flags: list[str] = []
        risk_level = "low"

        if spread_10y5y is not None:
            if spread_10y5y < -0.5:
                flags.append("deep_yield_inversion")
                risk_level = "high"
            elif spread_10y5y < -0.2:
                flags.append("yield_curve_inversion")
                risk_level = _max_risk(risk_level, "elevated")
            elif spread_10y5y < 0.1:
                flags.append("yield_curve_flat")
                risk_level = _max_risk(risk_level, "moderate")

        if spread_10y3m is not None and spread_10y3m < -0.3:
            flags.append("broad_inversion_10y3m")
            risk_level = _max_risk(risk_level, "elevated")

        if spread_trend == "flattening":
            risk_level = _max_risk(risk_level, "moderate")
        elif spread_trend == "steepening" and spread_10y5y is not None and spread_10y5y > 0:
            # Steepening from positive = healthy
            pass

        # Rapid rate rise (10Y > 5% is historically tight)
        if yield_10y is not None and yield_10y > 5.0:
            flags.append("high_rates")
            risk_level = _max_risk(risk_level, "moderate")

        result = {
            "yield_10y": yield_10y,
            "yield_5y": yield_5y,
            "yield_3m": yield_3m,
            "yield_spread_10y5y": spread_10y5y,
            "yield_spread_10y3m": spread_10y3m,
            "spread_trend": spread_trend,
            "macro_risk_level": risk_level,
            "flags": flags,
            "_fetched": True,
        }

        logger.info(
            f"Macro indicators: 10Y={yield_10y}% 5Y={yield_5y}% 3M={yield_3m}% "
            f"spread={spread_10y5y} trend={spread_trend} risk={risk_level} "
            f"flags={flags}"
        )
        return result

    except Exception as e:
        logger.warning(f"Macro indicators fetch failed: {e}")
        return empty


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _last_valid(df, col: str) -> float | None:
    """Get last non-NaN value for a column."""
    try:
        if col in df.columns:
            s = df[col].dropna()
            if not s.empty:
                return round(float(s.iloc[-1]), 3)
    except Exception:
        pass
    return None


def _compute_spread_trend(df, long_col: str, short_col: str) -> str:
    """Compare spread today vs 5 days ago to determine trend."""
    try:
        if long_col not in df.columns or short_col not in df.columns:
            return "unknown"

        spread = (df[long_col] - df[short_col]).dropna()
        if len(spread) < 3:
            return "unknown"

        current = float(spread.iloc[-1])
        oldest = float(spread.iloc[0])
        delta = current - oldest

        if delta > 0.15:
            return "steepening"
        elif delta < -0.15:
            return "flattening"
        return "stable"
    except Exception:
        return "unknown"


_RISK_ORDER = ["low", "moderate", "elevated", "high"]


def _max_risk(current: str, new: str) -> str:
    """Return the higher risk level."""
    ci = _RISK_ORDER.index(current) if current in _RISK_ORDER else 0
    ni = _RISK_ORDER.index(new) if new in _RISK_ORDER else 0
    return _RISK_ORDER[max(ci, ni)]
