"""
utils/data_fetcher.py - 统一外部数据访问层

提供: timeout / retry / 熔断(circuit breaker) / 缓存 / 错误分类
所有外部数据源调用统一经过此层。
"""
import time
import threading
from functools import wraps
from utils.logger import app_logger


class DataSourceError(Exception):
    """数据源错误基类"""
    def __init__(self, message, error_type="unknown", source="unknown"):
        super().__init__(message)
        self.error_type = error_type
        self.source = source


class DataSourceTimeout(DataSourceError):
    def __init__(self, message="数据源请求超时", source="unknown"):
        super().__init__(message, "timeout", source)


class DataSourceConnectionError(DataSourceError):
    def __init__(self, message="数据源连接失败", source="unknown"):
        super().__init__(message, "connection", source)


class DataSourceEmpty(DataSourceError):
    def __init__(self, message="数据源返回空结果", source="unknown"):
        super().__init__(message, "empty", source)


# ── 熔断器 ──

class CircuitBreaker:
    """简单熔断器：连续失败 N 次后短路，冷却后自动恢复。"""

    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._last_failure_time = 0
        self._state = "closed"  # closed / open / half-open
        self._lock = threading.Lock()

    @property
    def is_open(self):
        with self._lock:
            if self._state == "open":
                if time.time() - self._last_failure_time > self.recovery_timeout:
                    self._state = "half-open"
                    return False
                return True
            return False

    def record_success(self):
        with self._lock:
            self._failures = 0
            self._state = "closed"

    def record_failure(self):
        with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()
            if self._failures >= self.failure_threshold:
                self._state = "open"

    @property
    def state(self):
        with self._lock:
            return self._state


_breakers: dict[str, CircuitBreaker] = {}
_breaker_lock = threading.Lock()


def _get_breaker(name: str) -> CircuitBreaker:
    with _breaker_lock:
        if name not in _breakers:
            _breakers[name] = CircuitBreaker()
        return _breakers[name]


# ── 缓存 ──

_cache: dict[str, tuple] = {}
_cache_lock = threading.Lock()
_DEFAULT_TTL = 300  # 5 minutes


def cache_get(key: str) -> object | None:
    with _cache_lock:
        if key in _cache:
            value, expire_at = _cache[key]
            if time.time() < expire_at:
                return value
            del _cache[key]
    return None


def cache_set(key: str, value: object, ttl: int = _DEFAULT_TTL):
    with _cache_lock:
        _cache[key] = (value, time.time() + ttl)


# ── 核心装饰器 ──

def safe_fetch(source: str, timeout: float = 15, retries: int = 1,
               cache_ttl: int = 0, fallback=None):
    """
    统一外部数据获取装饰器。

    source: 数据源名称（用于日志和熔断器）
    timeout: 单次调用超时（秒）
    retries: 重试次数（不含首次）
    cache_ttl: 缓存时间（秒），0 = 不缓存
    fallback: 失败时的默认返回值
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            breaker = _get_breaker(source)

            # 熔断检查
            if breaker.is_open:
                app_logger.warning(f"[数据源] {source} 熔断中，直接返回 fallback")
                return fallback() if callable(fallback) else fallback

            # 缓存检查
            cache_key = None
            if cache_ttl > 0:
                cache_key = f"{source}:{func.__name__}:{args}:{kwargs}"
                cached = cache_get(cache_key)
                if cached is not None:
                    return cached

            last_error = None
            for attempt in range(1 + retries):
                start = time.time()
                try:
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(func, *args, **kwargs)
                        result = future.result(timeout=timeout)

                    elapsed = time.time() - start
                    breaker.record_success()

                    if elapsed > 5:
                        app_logger.warning(
                            f"[数据源] {source}.{func.__name__} 慢调用: {elapsed:.1f}s")

                    # 缓存结果
                    if cache_key and result is not None:
                        cache_set(cache_key, result, cache_ttl)

                    return result

                except concurrent.futures.TimeoutError:
                    elapsed = time.time() - start
                    last_error = DataSourceTimeout(
                        f"{source}.{func.__name__} 超时 ({elapsed:.1f}s > {timeout}s)",
                        source=source)
                    breaker.record_failure()
                    app_logger.warning(f"[数据源] {last_error}")

                except (ConnectionError, OSError) as e:
                    elapsed = time.time() - start
                    last_error = DataSourceConnectionError(
                        f"{source}.{func.__name__} 连接失败: {e}", source=source)
                    breaker.record_failure()
                    app_logger.warning(f"[数据源] {last_error}")

                except Exception as e:
                    elapsed = time.time() - start
                    error_name = type(e).__name__
                    if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                        last_error = DataSourceTimeout(
                            f"{source}.{func.__name__}: {error_name}: {e}",
                            source=source)
                    elif "connect" in str(e).lower() or "remote" in str(e).lower():
                        last_error = DataSourceConnectionError(
                            f"{source}.{func.__name__}: {error_name}: {e}",
                            source=source)
                    else:
                        last_error = DataSourceError(
                            f"{source}.{func.__name__}: {error_name}: {e}",
                            error_type="unknown", source=source)
                    breaker.record_failure()
                    app_logger.warning(f"[数据源] {last_error}")

                if attempt < retries:
                    time.sleep(min(1 * (attempt + 1), 3))

            app_logger.error(
                f"[数据源] {source}.{func.__name__} 最终失败 (重试{retries}次): {last_error}")
            return fallback() if callable(fallback) else fallback

        return wrapper
    return decorator


# ── 错误分类映射（供前端使用）──

ERROR_MESSAGES = {
    "timeout": "数据源响应超时，请稍后重试",
    "connection": "数据源连接失败，请检查网络",
    "empty": "未获取到数据，可能该标的暂无相关信息",
    "llm_error": "AI 分析服务暂时不可用",
    "parameter": "请求参数有误",
    "auth": "请先登录",
    "unknown": "系统异常，请稍后重试",
}


def classify_error(e: Exception) -> dict:
    """将异常分类为前端可用的错误信息。"""
    if isinstance(e, DataSourceTimeout):
        return {"error_type": "timeout", "message": ERROR_MESSAGES["timeout"]}
    elif isinstance(e, DataSourceConnectionError):
        return {"error_type": "connection", "message": ERROR_MESSAGES["connection"]}
    elif isinstance(e, DataSourceEmpty):
        return {"error_type": "empty", "message": ERROR_MESSAGES["empty"]}
    elif isinstance(e, DataSourceError):
        return {"error_type": e.error_type, "message": ERROR_MESSAGES.get(e.error_type, str(e))}
    else:
        msg = str(e)
        if "timeout" in msg.lower() or "timed out" in msg.lower():
            return {"error_type": "timeout", "message": ERROR_MESSAGES["timeout"]}
        return {"error_type": "unknown", "message": ERROR_MESSAGES["unknown"]}
