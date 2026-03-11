"""
utils/config_loader.py - YAML 配置热重载

借鉴 QuantProject：每次调用 get_config() 检测文件 mtime，
若有变化自动重新加载，线程安全。运行中修改 config.yaml 无需重启。
"""
import os
import threading
import yaml

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(_project_root, "config.yaml")

_lock = threading.Lock()
_cache: dict | None = None
_last_mtime = 0.0


def get_config() -> dict:
    """读取 config.yaml 并缓存，文件修改时自动重载（热更新）。线程安全。"""
    global _cache, _last_mtime
    try:
        mtime = os.path.getmtime(CONFIG_PATH)
    except OSError:
        mtime = 0.0

    with _lock:
        if _cache is None or mtime > _last_mtime:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                _cache = yaml.safe_load(f) or {}
            _last_mtime = mtime
        return _cache
