"""Built-in scheduler for independent US/HK pipeline execution.

Uses threading.Timer to trigger pipelines at configured times,
running Mon-Fri only. Each market has its own schedule tied to
its local timezone.

v11: US market also gets a Stage-2 "recalibration" timer triggered after the
daily pipeline completes. At ``us_recalibrate_time`` (default 09:35 ET, which
is 5 minutes after open) the scheduler re-runs entry/SL/TP computation
against the real open price. See ``pipeline.runner.recalibrate_trade_params``.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any

from loguru import logger
from zoneinfo import ZoneInfo

_MARKET_TZ = {
    "us_stock": "America/New_York",
    "hk_stock": "Asia/Hong_Kong",
}


class PipelineScheduler:
    """Timer-based scheduler that fires US and HK pipelines independently."""

    def __init__(
        self,
        us_time: str = "07:30",
        hk_time: str = "07:30",
        us_recalibrate_time: str = "09:35",
    ):
        self._us_time = us_time
        self._hk_time = hk_time
        self._us_recalibrate_time = us_recalibrate_time
        self._timers: dict[str, threading.Timer] = {}
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._running:
                logger.warning("Scheduler already running")
                return
            self._running = True

        logger.info(
            f"Pipeline scheduler started - "
            f"US: {self._us_time} ET (recalibrate {self._us_recalibrate_time} ET), "
            f"HK: {self._hk_time} HKT"
        )
        self._schedule_next("us_stock")
        self._schedule_next("hk_stock")
        self._schedule_recalibration_if_due()

    def stop(self) -> None:
        with self._lock:
            self._running = False
            for name, timer in self._timers.items():
                timer.cancel()
                logger.info(f"Cancelled timer for {name}")
            self._timers.clear()
        logger.info("Pipeline scheduler stopped")

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "us_time": f"{self._us_time} ET",
                "us_recalibrate_time": f"{self._us_recalibrate_time} ET",
                "hk_time": f"{self._hk_time} HKT",
                "active_timers": list(self._timers.keys()),
            }

    def _schedule_next(self, market: str) -> None:
        with self._lock:
            if not self._running:
                return

        target_time = self._hk_time if market == "hk_stock" else self._us_time
        if not target_time:
            logger.info(f"Scheduler: {market} disabled (no run_time configured)")
            return

        tz_name = _MARKET_TZ[market]
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)

        hour, minute = map(int, target_time.split(":"))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if target <= now:
            target += timedelta(days=1)

        while target.weekday() >= 5:
            target += timedelta(days=1)

        delay = (target - now).total_seconds()
        tz_label = "HKT" if market == "hk_stock" else "ET"
        logger.info(
            f"Next {market} pipeline: {target.strftime('%Y-%m-%d %H:%M')} {tz_label} "
            f"(in {delay/3600:.1f}h)"
        )

        timer = threading.Timer(delay, self._fire, args=(market,))
        timer.daemon = True
        timer.name = f"scheduler-{market}"

        with self._lock:
            old = self._timers.pop(market, None)
            if old:
                old.cancel()
            self._timers[market] = timer

        timer.start()

    def _fire(self, market: str) -> None:
        tz_name = _MARKET_TZ[market]
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)

        if now.weekday() >= 5:
            logger.info(f"Skipping {market} pipeline on weekend")
            self._schedule_next(market)
            return

        logger.info(f"Scheduler firing pipeline for {market}")
        try:
            from pipeline.runner import run_daily_pipeline
            result = run_daily_pipeline(
                market=market,
                force=False,
                trigger_source="scheduler",
            )
            count = result.get("published_count", 0)
            skipped = result.get("skipped", False)
            if skipped:
                logger.info(f"Scheduler: {market} pipeline skipped (already ran)")
            else:
                logger.info(f"Scheduler: {market} pipeline done, {count} recommendations")
        except Exception as e:
            logger.error(f"Scheduler: {market} pipeline failed: {e}")
        finally:
            # Always reschedule the next daily run
            self._schedule_next(market)
            # US-only: schedule Stage-2 recalibration at 09:35 ET
            if market == "us_stock" and self._us_recalibrate_time:
                self._schedule_recalibration_for_today()

    def _schedule_recalibration_for_today(self) -> None:
        """Schedule today's 09:35 ET recalibration, if still in the future."""
        with self._lock:
            if not self._running:
                return

        tz = ZoneInfo(_MARKET_TZ["us_stock"])
        now = datetime.now(tz)

        try:
            hour, minute = map(int, self._us_recalibrate_time.split(":"))
        except Exception:
            logger.warning(
                f"invalid us_recalibrate_time={self._us_recalibrate_time}, "
                f"skipping Stage-2 scheduling"
            )
            return

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            logger.info(
                f"Recalibration time {self._us_recalibrate_time} ET already passed "
                f"for today ({now.strftime('%H:%M')} ET); skipping"
            )
            return

        if target.weekday() >= 5:
            logger.info("Recalibration skipped: weekend")
            return

        delay = (target - now).total_seconds()
        logger.info(
            f"Next US recalibration: {target.strftime('%Y-%m-%d %H:%M')} ET "
            f"(in {delay/60:.1f}m)"
        )

        timer = threading.Timer(delay, self._fire_recalibration)
        timer.daemon = True
        timer.name = "scheduler-us_stock-recalibrate"

        with self._lock:
            old = self._timers.pop("us_stock_recalibrate", None)
            if old:
                old.cancel()
            self._timers["us_stock_recalibrate"] = timer

        timer.start()

    def _schedule_recalibration_if_due(self) -> None:
        """On startup, schedule today's recalibration if still in the future.

        Covers the case where the service is (re)started between 07:30 and
        09:35 ET: the daily pipeline may already have run, but Stage-2 has
        not. Without this, skipping that day's recalibration would silently
        leave Stage-1 prices in place.
        """
        if not self._us_time or not self._us_recalibrate_time:
            return
        tz = ZoneInfo(_MARKET_TZ["us_stock"])
        now = datetime.now(tz)
        if now.weekday() >= 5:
            return
        try:
            r_h, r_m = map(int, self._us_recalibrate_time.split(":"))
        except Exception:
            return
        target = now.replace(hour=r_h, minute=r_m, second=0, microsecond=0)
        if target > now:
            self._schedule_recalibration_for_today()

    def _fire_recalibration(self) -> None:
        """Execute the Stage-2 recalibration for US market."""
        tz = ZoneInfo(_MARKET_TZ["us_stock"])
        now = datetime.now(tz)
        if now.weekday() >= 5:
            logger.info("Skipping recalibration on weekend")
            return
        logger.info("Scheduler firing recalibration for us_stock")
        try:
            from pipeline.runner import recalibrate_trade_params
            result = recalibrate_trade_params(market="us_stock")
            logger.info(f"Scheduler: recalibration done, result={result}")
        except Exception as e:
            logger.error(f"Scheduler: recalibration failed: {e}")


_scheduler: PipelineScheduler | None = None


def start_scheduler(
    us_time: str = "07:30",
    hk_time: str = "07:30",
    us_recalibrate_time: str = "09:35",
) -> PipelineScheduler:
    global _scheduler
    if _scheduler:
        _scheduler.stop()
    _scheduler = PipelineScheduler(
        us_time=us_time,
        hk_time=hk_time,
        us_recalibrate_time=us_recalibrate_time,
    )
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.stop()
        _scheduler = None


def get_scheduler() -> PipelineScheduler | None:
    return _scheduler
