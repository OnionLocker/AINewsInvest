"""
scripts/alert_checker.py - 告警规则检测引擎

遍历所有启用的告警规则，检测是否触发条件，
触发后推送 Telegram 通知并更新 last_triggered。
"""
from datetime import datetime, timedelta
from utils.logger import app_logger


def check_alerts(app):
    """在 Flask app context 内执行告警检测。"""
    from models import db, AlertRule, User
    from data.market_data import get_quote

    with app.app_context():
        rules = AlertRule.query.filter_by(enabled=True).all()
        if not rules:
            return

        app_logger.info(f"[告警检测] 开始检查 {len(rules)} 条规则")

        cooldown = timedelta(hours=4)

        for rule in rules:
            if rule.last_triggered and (datetime.utcnow() - rule.last_triggered) < cooldown:
                continue

            try:
                quote = get_quote(rule.ticker, rule.market)
                if not quote or quote.get("price") is None:
                    continue

                triggered = _evaluate(rule, quote)
                if triggered:
                    _send_alert(rule, quote)
                    rule.last_triggered = datetime.utcnow()
                    db.session.commit()
            except Exception as e:
                app_logger.warning(f"[告警检测] 规则 {rule.id} 检测失败: {e}")

        app_logger.info("[告警检测] 检查完毕")


def _evaluate(rule, quote) -> bool:
    """判断告警条件是否满足。"""
    price = quote.get("price")
    change_pct = quote.get("change_pct", 0) or 0
    threshold = rule.threshold

    if threshold is None:
        return False

    if rule.rule_type == "price_above":
        return price is not None and price >= threshold
    elif rule.rule_type == "price_below":
        return price is not None and price <= threshold
    elif rule.rule_type == "change_pct_above":
        return change_pct >= threshold
    elif rule.rule_type == "change_pct_below":
        return change_pct <= -abs(threshold)
    elif rule.rule_type == "volume_surge":
        return False  # TODO: need historical volume baseline

    return False


def _send_alert(rule, quote):
    """通过 Telegram 发送告警通知。"""
    from models import User

    user = User.query.get(rule.user_id)
    if not user or not user.tg_configured:
        app_logger.info(f"[告警推送] 用户 {rule.user_id} 未配置 Telegram，跳过")
        return

    token, chat_id = user.get_tg_config()
    if not token or not chat_id:
        return

    from models import AlertRule
    type_label = AlertRule.RULE_TYPES.get(rule.rule_type, rule.rule_type)
    price = quote.get("price", "N/A")
    change = quote.get("change_pct", 0) or 0
    sign = "+" if change > 0 else ""

    msg = (
        f"\U0001F6A8 *告警触发*\n\n"
        f"*{rule.name or rule.ticker}* ({rule.ticker})\n"
        f"规则: {type_label} {rule.threshold}\n"
        f"当前价: {price}  ({sign}{change:.2f}%)\n"
        f"时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )

    try:
        import requests
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "Markdown",
        }, timeout=10)
        app_logger.info(f"[告警推送] {rule.ticker} -> 用户 {rule.user_id} 已发送")
    except Exception as e:
        app_logger.warning(f"[告警推送] Telegram 发送失败: {e}")
