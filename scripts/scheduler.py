"""
scripts/scheduler.py - 定时任务调度器

使用 APScheduler 管理所有定时任务：
- 告警检测（每 30 分钟）
- 推荐追踪回填（每日）
"""
from apscheduler.schedulers.background import BackgroundScheduler
from utils.logger import app_logger

_scheduler = None


def init_scheduler(app):
    """初始化并启动定时任务调度器。"""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(daemon=True)

    from scripts.alert_checker import check_alerts
    _scheduler.add_job(
        func=check_alerts,
        args=[app],
        trigger="interval",
        minutes=30,
        id="alert_checker",
        name="告警检测",
        replace_existing=True,
        misfire_grace_time=120,
    )

    
    def _weekly_report_job():
        from analysis.report_generator import generate_weekly_report
        with app.app_context():
            for market in ["a_share", "us_stock", "hk_stock"]:
                try:
                    report = generate_weekly_report(market)
                    app.config.setdefault("_weekly_cache", {})[f"weekly_{market}"] = report
                except Exception as e:
                    app_logger.warning(f"[\u5468\u62a5] {market} \u751f\u6210\u5931\u8d25: {e}")

    _scheduler.add_job(
        func=_weekly_report_job,
        trigger="cron",
        day_of_week="fri",
        hour=18,
        minute=0,
        id="weekly_report",
        name="\u5468\u62a5\u751f\u6210",
        replace_existing=True,
        misfire_grace_time=600,
    )

_scheduler.start()
    app_logger.info("[调度器] APScheduler 已启动，告警检测每 30 分钟执行")
    return _scheduler


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        app_logger.info("[调度器] APScheduler 已关闭")
