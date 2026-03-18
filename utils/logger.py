"""
utils/logger.py - 日志系统

双输出（控制台 + 文件）、按天轮转保留 30 天。
支持结构化字段、请求追踪、阶段耗时。
"""
import logging
import logging.handlers
import os
import time
import uuid
import threading
from contextlib import contextmanager

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_log_dir = os.path.join(_project_root, "logs")
os.makedirs(_log_dir, exist_ok=True)

# ── 请求上下文 ──

_request_context = threading.local()


def set_request_id(request_id: str = None):
    _request_context.request_id = request_id or str(uuid.uuid4())[:8]


def get_request_id() -> str:
    return getattr(_request_context, "request_id", "-")


class StructuredFormatter(logging.Formatter):
    """包含 request_id 的结构化日志格式。"""
    def format(self, record):
        record.request_id = get_request_id()
        return super().format(record)


# ── 全局 App Logger ──

app_logger = logging.getLogger("AINews")
app_logger.setLevel(logging.INFO)

if not app_logger.handlers:
    _fmt = StructuredFormatter(
        "[%(asctime)s][%(levelname)s][%(request_id)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

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


# ── 阶段耗时计时器 ──

@contextmanager
def log_phase(phase_name: str, ticker: str = "", market: str = ""):
    """记录某个分析阶段的耗时。"""
    start = time.time()
    prefix = f"[{market}:{ticker}]" if ticker else ""
    app_logger.info(f"{prefix} ▶ {phase_name} 开始")
    error_occurred = False
    try:
        yield
    except Exception:
        error_occurred = True
        raise
    finally:
        elapsed = time.time() - start
        status = "✗ 失败" if error_occurred else "✓ 完成"
        level = logging.WARNING if elapsed > 10 else logging.INFO
        app_logger.log(level, f"{prefix} {status} {phase_name} ({elapsed:.1f}s)")


# ── Flask 请求日志中间件 ──

def init_request_logging(flask_app):
    """注册 Flask before/after_request 钩子，记录请求耗时。"""

    @flask_app.before_request
    def _before():
        from flask import request, g
        set_request_id()
        g.request_start = time.time()

    @flask_app.after_request
    def _after(response):
        from flask import request, g
        elapsed = time.time() - getattr(g, "request_start", time.time())
        status = response.status_code
        level = logging.WARNING if elapsed > 5 or status >= 500 else logging.INFO
        if not request.path.startswith("/static"):
            app_logger.log(
                level,
                f"{request.method} {request.path} → {status} ({elapsed:.1f}s)",
            )
        return response


def get_user_logger(username: str) -> logging.Logger:
    """为单个用户创建独立日志。"""
    logger = logging.getLogger(f"AINews.{username}")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = StructuredFormatter(
        f"[%(asctime)s][{username}][%(request_id)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

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
