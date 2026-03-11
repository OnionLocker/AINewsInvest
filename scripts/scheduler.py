"""
scripts/scheduler.py - 定时推送调度器

推送时间（北京时间 UTC+8）：
  - A 股 / 港股 / 基金：每天 08:00
  - 美股夏令时（3月第2个周日 ~ 11月第1个周日）：每天 20:30（美东 08:30）
  - 美股冬令时：每天 21:30（美东 08:30）

用法：
  python scripts/scheduler.py          # 前台运行
  nohup python scripts/scheduler.py &  # 后台运行
"""
import os
import sys
import json
from datetime import datetime, date, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

BJT = timezone(timedelta(hours=8))


def is_us_dst() -> bool:
    """判断当前是否处于美国夏令时"""
    from zoneinfo import ZoneInfo
    eastern = ZoneInfo("America/New_York")
    now_et = datetime.now(eastern)
    return bool(now_et.dst())


def push_market_report(market: str):
    """生成指定市场的每日报告并推送给所有配置了 Telegram 的用户"""
    from app import app
    from models import db, User, DailyReport
    from utils.logger import app_logger
    from utils.notifier import make_notifier

    with app.app_context():
        today = date.today()
        existing = DailyReport.query.filter_by(market=market, report_date=today).first()

        if existing and existing.pushed:
            app_logger.info(f"[调度] {market} 今日报告已推送过，跳过")
            return

        # TODO: 接入真实 AI 分析引擎生成报告数据
        # 当前使用占位数据，后续替换为：
        #   1. 拉取新闻（news_fetcher）
        #   2. 拉取技术指标（market_data）
        #   3. AI 综合分析生成推荐
        report_data = {
            "metrics": {"count": 0, "bull": 0, "bear": 0, "sentiment": "待生成"},
            "items": [],
            "note": "AI 分析引擎尚未接入，报告将在接入后自动生成。"
        }

        if not existing:
            report = DailyReport(
                market=market,
                report_date=today,
                data=json.dumps(report_data, ensure_ascii=False),
                pushed=False,
            )
            db.session.add(report)
        else:
            report = existing
            report.data = json.dumps(report_data, ensure_ascii=False)
            report.generated_at = datetime.utcnow()

        db.session.commit()
        app_logger.info(f"[调度] {market} 报告已生成")

        # 推送给所有配置了 Telegram 的用户
        market_labels = {"a_share": "A股", "us_stock": "美股", "hk_stock": "港股", "fund": "基金"}
        market_name = market_labels.get(market, market)

        users = User.query.filter(
            User.tg_bot_token_enc != "",
            User.tg_chat_id_enc != "",
        ).all()

        pushed_count = 0
        for user in users:
            try:
                token, chat_id = user.get_tg_config()
                notify = make_notifier(token, chat_id)
                if notify:
                    items_text = ""
                    for item in report_data.get("items", []):
                        direction = item.get("dirLabel", "")
                        items_text += f"\n  {direction} {item['name']}({item['ticker']}) {item.get('price','')}"

                    if not items_text:
                        items_text = "\n  AI 分析引擎准备中，敬请期待"

                    msg = (
                        f"<b>Alpha Vault {market_name}日报</b>\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"日期：{today.isoformat()}\n"
                        f"推荐：{report_data['metrics']['count']} 只\n"
                        f"情绪：{report_data['metrics']['sentiment']}\n"
                        f"\n<b>推荐标的</b>{items_text}\n"
                        f"\n详情请登录 Alpha Vault 查看"
                    )
                    if notify(msg):
                        pushed_count += 1
            except Exception as e:
                app_logger.warning(f"[调度] 推送给 {user.username} 失败: {e}")

        report.pushed = True
        db.session.commit()
        app_logger.info(f"[调度] {market} 推送完成，成功 {pushed_count}/{len(users)} 人")


def job_cn_morning():
    """北京时间 08:00 - A股/港股/基金"""
    push_market_report("a_share")
    push_market_report("hk_stock")
    push_market_report("fund")


def job_us_premarket():
    """美股盘前 - 根据夏冬令时自动判断"""
    push_market_report("us_stock")


def main():
    from utils.logger import app_logger

    scheduler = BlockingScheduler(timezone="Asia/Shanghai")

    # A股/港股/基金：北京时间每天 08:00
    scheduler.add_job(
        job_cn_morning,
        CronTrigger(hour=8, minute=0, timezone="Asia/Shanghai"),
        id="cn_morning",
        name="A股/港股/基金 08:00 推送",
    )

    # 美股夏令时：北京时间 20:30（美东 08:30，开盘前1小时）
    scheduler.add_job(
        job_us_premarket,
        CronTrigger(hour=20, minute=30, timezone="Asia/Shanghai"),
        id="us_summer",
        name="美股夏令时 20:30 推送",
    )

    # 美股冬令时：北京时间 21:30（美东 08:30，开盘前1小时）
    scheduler.add_job(
        job_us_premarket,
        CronTrigger(hour=21, minute=30, timezone="Asia/Shanghai"),
        id="us_winter",
        name="美股冬令时 21:30 推送",
    )

    app_logger.info("定时推送调度器已启动")
    app_logger.info("  A股/港股/基金: 北京时间 08:00")
    app_logger.info("  美股夏令时:    北京时间 20:30")
    app_logger.info("  美股冬令时:    北京时间 21:30")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        app_logger.info("调度器已停止")


if __name__ == "__main__":
    main()
