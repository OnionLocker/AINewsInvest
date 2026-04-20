# -*- coding: utf-8 -*-
"""Macro-event calendar (FOMC / CPI / PCE / NFP).

Hardcoded schedule of high-impact US macro releases. These events routinely
cause 1-3% single-day moves in SPY and can blow through ATR-based stop losses
that were set assuming normal volatility. The runner uses this calendar to:

1. Escalate market regime to ``cautious`` on the day of a major release.
2. Halve the recommendation quota the day before a major release.
3. Expose ``macro_events`` in the regime details so the UI can warn users.

Schedule source (verified 2026-04):
- FOMC dates are from the Fed's published 2026 calendar.
- CPI/PCE/NFP dates follow BLS/BEA release schedules.
- Refresh this file each quarter when new data is published.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from loguru import logger


# ---------------------------------------------------------------------------
# 2026 US macro-event schedule.
# Each entry: (ISO date, event code, severity)
#   severity: "critical" (FOMC rate decision, CPI) or "major" (PCE, NFP)
# ---------------------------------------------------------------------------
# Fed FOMC meetings (dates are the FOMC decision / press conference day)
_FOMC_2026 = [
    "2026-01-28",
    "2026-03-18",
    "2026-04-29",
    "2026-06-17",
    "2026-07-29",
    "2026-09-16",
    "2026-10-28",
    "2026-12-09",
]

# CPI releases (typically 2nd Tuesday of the month for the prior month's data)
_CPI_2026 = [
    "2026-01-13",
    "2026-02-11",
    "2026-03-11",
    "2026-04-14",
    "2026-05-13",
    "2026-06-11",
    "2026-07-15",
    "2026-08-12",
    "2026-09-10",
    "2026-10-15",
    "2026-11-13",
    "2026-12-10",
]

# PCE releases (last Friday of the month, approximate)
_PCE_2026 = [
    "2026-01-30",
    "2026-02-27",
    "2026-03-27",
    "2026-04-30",
    "2026-05-29",
    "2026-06-26",
    "2026-07-31",
    "2026-08-28",
    "2026-09-25",
    "2026-10-30",
    "2026-11-25",
    "2026-12-23",
]

# Non-Farm Payrolls (1st Friday of the month, with occasional shifts)
_NFP_2026 = [
    "2026-01-02",
    "2026-02-06",
    "2026-03-06",
    "2026-04-03",
    "2026-05-01",
    "2026-06-05",
    "2026-07-02",
    "2026-08-07",
    "2026-09-04",
    "2026-10-02",
    "2026-11-06",
    "2026-12-04",
]


def _build_event_map() -> dict[date, list[dict]]:
    """Build date->events index from the hardcoded lists."""
    events: dict[date, list[dict]] = {}

    def _add(iso: str, code: str, severity: str) -> None:
        try:
            d = datetime.strptime(iso, "%Y-%m-%d").date()
        except ValueError:
            return
        events.setdefault(d, []).append({"code": code, "severity": severity})

    for iso in _FOMC_2026:
        _add(iso, "FOMC", "critical")
    for iso in _CPI_2026:
        _add(iso, "CPI", "critical")
    for iso in _PCE_2026:
        _add(iso, "PCE", "major")
    for iso in _NFP_2026:
        _add(iso, "NFP", "major")

    return events


_EVENT_MAP = _build_event_map()


def _parse_ref_date(ref_date: Optional[str]) -> date:
    if ref_date is None:
        return datetime.now().date()
    # Accept YYYYMMDD (runner convention) or YYYY-MM-DD
    s = ref_date.strip()
    try:
        if "-" in s:
            return datetime.strptime(s, "%Y-%m-%d").date()
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        logger.warning(f"macro_calendar: invalid ref_date {ref_date!r}")
        return datetime.now().date()


def get_macro_events_on(ref_date: Optional[str] = None) -> list[dict]:
    """Return list of macro events scheduled on ``ref_date``.

    Each dict has ``{code, severity}``. Returns ``[]`` if no events.
    """
    d = _parse_ref_date(ref_date)
    return list(_EVENT_MAP.get(d, []))


def get_macro_events_tomorrow(ref_date: Optional[str] = None) -> list[dict]:
    """Return events on the next calendar day after ``ref_date``."""
    d = _parse_ref_date(ref_date) + timedelta(days=1)
    return list(_EVENT_MAP.get(d, []))


def get_next_macro_event(ref_date: Optional[str] = None,
                         horizon_days: int = 10) -> Optional[dict]:
    """Return the soonest upcoming event within ``horizon_days``, or None.

    Default horizon = 10 days so a run on Monday can see next week's FOMC.

    Dict has ``{date, code, severity, days_until}``. Today's event (if any)
    is included with ``days_until=0``.
    """
    d = _parse_ref_date(ref_date)
    for offset in range(horizon_days + 1):
        probe = d + timedelta(days=offset)
        evs = _EVENT_MAP.get(probe)
        if evs:
            # Prefer the first critical event on that day
            evs_sorted = sorted(evs, key=lambda e: 0 if e["severity"] == "critical" else 1)
            first = evs_sorted[0]
            return {
                "date": probe.strftime("%Y-%m-%d"),
                "code": first["code"],
                "severity": first["severity"],
                "days_until": offset,
            }
    return None


def has_critical_event(ref_date: Optional[str] = None) -> bool:
    """True if ``ref_date`` has at least one critical event (FOMC/CPI)."""
    return any(e["severity"] == "critical"
               for e in get_macro_events_on(ref_date))


def has_critical_event_tomorrow(ref_date: Optional[str] = None) -> bool:
    """True if next calendar day has at least one critical event."""
    return any(e["severity"] == "critical"
               for e in get_macro_events_tomorrow(ref_date))
