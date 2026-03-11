"""
scripts/scheduler.py - 定时推送调度器

推送时间（北京时间 UTC+8）：
  - A 股 / 港股 / 基金：每天 08:00
  - 美股夏令时：每天 20:30（美东 08:30，开盘前1小时）
  - 美股冬令时：每天 21:30（美东 08:30，开盘前1小时）

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


def push_market_report(market: str):
    """生成指定市场的每日报告并推送给所有配置了 Telegram 的用户"""
    from app import app
    from models import db, User, DailyReport
    from utils.logger import app_logger
    from utils.notifier import make_notifier
    from analysis.report_generator import generate_report

    with app.app_context():
        today = date.today()
        existing = DailyReport.query.filter_by(market=market, report_date=today).first()

        if existing and existing.pushed:
            app_logger.info(f"[调度] {market} 今日报告已推送过，跳过")
            return

        # 生成报告
        app_logger.info(f"[调度] 开始生成 {market} 报告...")
        report_data = generate_report(market)

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
                if not notify:
                    continue

                # 构造推送消息
                items = report_data.get("items", [])
                metrics = report_data.get("metrics", {})

                msg_parts = [
                    f"<b>Alpha Vault {market_name}日报</b>",
                    f"━━━━━━━━━━━━━━",
                    f"日期：{today.isoformat()}",
                    f"推荐：{metrics.get('count', 0)} 只 | 情绪：{metrics.get('sentiment', 'N/A')}",
                    "",
                ]

                # 只取前 5 只推送（避免消息太长）
                for item in items[:5]:
                    emoji = "🟢" if item["direction"] == "buy" else "🔴"
                    msg_parts.append(
                        f"{emoji} <b>{item['name']}</b>({item['ticker']}) {item['dirLabel']}"
                    )
                    msg_parts.append(
                        f"   价格 {item['price']} {item['change']}"
                    )
                    msg_parts.append(
                        f"   入场 {item['entry']} | 止损 {item['stop_loss']} | 止盈 {item['take_profit_1']}"
                    )
                    msg_parts.append(f"   置信度 {item['confidence']}% | 风险回报 {item['risk_reward']}")
                    msg_parts.append("")

                if not items:
                    msg_parts.append("暂无推荐标的")

                msg_parts.append("详情请登录 Alpha Vault 查看完整分析")
                msg = "\n".join(msg_parts)

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
    """美股盘前"""
    push_market_report("us_stock")


def main():
    from utils.logger import app_logger

    scheduler = BlockingScheduler(timezone="Asia/Shanghai")

    scheduler.add_job(
        job_cn_morning,
        CronTrigger(hour=8, minute=0, timezone="Asia/Shanghai"),
        id="cn_morning",
        name="A股/港股/基金 08:00 推送",
    )

    scheduler.add_job(
        job_us_premarket,
        CronTrigger(hour=20, minute=30, timezone="Asia/Shanghai"),
        id="us_summer",
        name="美股夏令时 20:30 推送",
    )

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
