"""
utils/notifier.py - 通知推送工具

借鉴 QuantProject 的工厂模式：
  - make_notifier(token, chat_id)  → 返回一个闭包函数，调用即发送
  - make_webhook_notifier(url)     → Webhook 通道
  - make_multi_notifier(...)       → 多通道组合，任一成功即成功
  - test_notify(token, chat_id)    → 测试连通性，返回 (bool, msg)
"""
import requests
from utils.logger import app_logger

_TIMEOUT = 10


def _do_send(token: str, chat_id: str, message: str) -> bool:
    """底层发送，不依赖任何全局状态"""
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=_TIMEOUT,
        )
        return resp.status_code == 200 and resp.json().get("ok")
    except Exception as e:
        app_logger.warning(f"Telegram 发送异常: {e}")
        return False


def make_notifier(token: str, chat_id: str):
    """
    工厂函数：闭包捕获 token/chat_id，返回可直接调用的发送函数。
    token 或 chat_id 为空时返回 None，调用方应先判断。

    用法:
        notify = make_notifier(user_token, user_chat_id)
        if notify:
            notify("消息内容")
    """
    if not token or not chat_id:
        return None

    def _send(message: str) -> bool:
        ok = _do_send(token, chat_id, message)
        if not ok:
            app_logger.warning(f"Telegram 发送失败 (chat_id={chat_id[:6]}...)")
        return ok

    return _send


def make_webhook_notifier(url: str, headers: dict = None):
    """Webhook 通道工厂：向指定 URL POST JSON 消息"""
    if not url:
        return None

    def _send(message: str) -> bool:
        try:
            resp = requests.post(
                url,
                json={"text": message, "content": message},
                headers=headers or {"Content-Type": "application/json"},
                timeout=_TIMEOUT,
            )
            return 200 <= resp.status_code < 300
        except Exception as e:
            app_logger.warning(f"Webhook 发送失败: {e}")
            return False

    return _send


def make_multi_notifier(*notifiers):
    """组合多个通知器，顺序发送，任一成功视为成功"""
    active = [n for n in notifiers if n is not None]
    if not active:
        return None

    def _send(message: str) -> bool:
        return any(n(message) for n in active)

    return _send


def test_notify(token: str, chat_id: str) -> tuple[bool, str]:
    """测试 Telegram 连通性，返回 (是否成功, 提示信息)"""
    if not token or not chat_id:
        return False, "Token 和 Chat ID 不能为空"
    ok = _do_send(token, chat_id, "<b>AI 投研系统</b>\n老板，投研系统大本营已连接成功！")
    if ok:
        return True, "测试消息发送成功，请检查 Telegram"
    return False, "发送失败，请检查 Token 和 Chat ID 是否正确"
