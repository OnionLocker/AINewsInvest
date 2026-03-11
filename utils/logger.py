"""
utils/logger.py - 日志系统

借鉴 QuantProject：双输出（控制台 + 文件）、按天轮转保留 30 天。
全局 app_logger 供 Flask 路由和工具函数使用。
"""
import logging
import logging.handlers
import os

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_log_dir = os.path.join(_project_root, "logs")
os.makedirs(_log_dir, exist_ok=True)

# ── 全局 App Logger ─────────────────────────────────────────────

app_logger = logging.getLogger("AINews")
app_logger.setLevel(logging.INFO)

if not app_logger.handlers:
    _fmt = logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    _console = logging.StreamHandler()
    _console.setFormatter(_fmt)
    app_logger.addHandler(_console)

    _file = logging.handlers.TimedRotatingFileHandler(
        os.path.join(_log_dir, "app.log"),
        when="midnight", interval=1, backupCount=30, encoding="utf-8",
    )
    _file.suffix = "%Y%m%d"
    _file.setFormatter(_fmt)
    app_logger.addHandler(_file)


def get_user_logger(username: str) -> logging.Logger:
    """为单个用户创建独立日志，写入 logs/{username}.log，按天轮转"""
    logger = logging.getLogger(f"AINews.{username}")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter(f"[%(asctime)s][{username}] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.handlers.TimedRotatingFileHandler(
        os.path.join(_log_dir, f"{username}.log"),
        when="midnight", interval=1, backupCount=30, encoding="utf-8",
    )
    fh.suffix = "%Y%m%d"
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
