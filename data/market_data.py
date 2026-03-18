"""
data/market_data.py - 行情数据获取层

统一封装 akshare（A股/港股/基金）和 yfinance（美股）的数据获取，
所有外部调用经过 safe_fetch 统一超时/重试/熔断保护。
"""
import time
import akshare as ak
import yfinance as yf
from utils.logger import app_logger
from utils.data_fetcher import safe_fetch

# 内存缓存
_cache: dict = {}
_CACHE_TTL = 120


def _cached(key: str):
    if key in _cache:
        data, ts = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return data
    return None


def _set_cache(key: str, data: dict):
    _cache[key] = (data, time.time())


def get_quote(ticker: str, market: str) -> dict | None:
    """获取单个标的最新行情，带缓存。"""
    cache_key = f"quote:{market}:{ticker}"
    cached = _cached(cache_key)
    if cached:
        return cached

    try:
        if market == "a_share":
            result = _quote_a_share(ticker)
        elif market == "hk_stock":
            result = _quote_hk(ticker)
        elif market == "us_stock":
            result = _quote_us(ticker)
        elif market == "fund":
            result = _quote_fund(ticker)
        else:
            return None

        if result:
            _set_cache(cache_key, result)
        return result
    except Exception as e:
        app_logger.warning(f"[行情] 获取失败 [{market}:{ticker}]: {type(e).__name__}: {e}")
        return None


def get_quotes_batch(items: list[dict]) -> list[dict]:
    """批量获取行情。单只失败不阻塞其他。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _fetch_one(item):
        try:
            quote = get_quote(item["ticker"], item["market"])
            if quote:
                return quote
        except Exception:
            pass
        return {
            "ticker": item["ticker"],
            "name": item.get("name", ""),
            "market": item["market"],
            "price": None, "change": None, "change_pct": None,
        }

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_one, item): item for item in items}
        for future in as_completed(futures, timeout=30):
            try:
                results.append(future.result())
            except Exception:
                item = futures[future]
                results.append({
                    "ticker": item["ticker"], "name": item.get("name", ""),
                    "market": item["market"],
                    "price": None, "change": None, "change_pct": None,
                })
    return results


# ── A 股行情 ──

@safe_fetch("akshare_a_quote", timeout=10, retries=1, fallback=None)
def _quote_a_share(ticker: str) -> dict | None:
    df = ak.stock_zh_a_spot_em()
    row = df[df["代码"] == ticker]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "ticker": ticker,
        "name": str(r["名称"]),
        "market": "a_share",
        "price": float(r["最新价"]) if r["最新价"] else None,
        "change": float(r["涨跌额"]) if r["涨跌额"] else None,
        "change_pct": float(r["涨跌幅"]) if r["涨跌幅"] else None,
    }


# ── 港股行情 ──

@safe_fetch("akshare_hk_quote", timeout=10, retries=1, fallback=None)
def _quote_hk(ticker: str) -> dict | None:
    df = ak.stock_hk_spot_em()
    row = df[df["代码"] == ticker]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "ticker": ticker,
        "name": str(r["名称"]),
        "market": "hk_stock",
        "price": float(r["最新价"]) if r["最新价"] else None,
        "change": float(r["涨跌额"]) if r["涨跌额"] else None,
        "change_pct": float(r["涨跌幅"]) if r["涨跌幅"] else None,
    }


# ── 美股行情 ──

@safe_fetch("yfinance_us_quote", timeout=10, retries=1, fallback=None)
def _quote_us(ticker: str) -> dict | None:
    t = yf.Ticker(ticker)
    info = t.fast_info
    price = getattr(info, "last_price", None)
    prev = getattr(info, "previous_close", None)
    if price is None:
        return None
    change = round(price - prev, 2) if prev else None
    change_pct = round((change / prev) * 100, 2) if prev and change else None
    return {
        "ticker": ticker,
        "name": ticker,
        "market": "us_stock",
        "price": round(price, 2),
        "change": change,
        "change_pct": change_pct,
    }


# ── 基金净值 ──

@safe_fetch("akshare_fund_quote", timeout=10, retries=0, fallback=None)
def _quote_fund(ticker: str) -> dict | None:
    df = ak.fund_open_fund_info_em(symbol=ticker, indicator="单位净值走势")
    if df.empty:
        return None
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else None
    price = float(latest["单位净值"])
    change = round(price - float(prev["单位净值"]), 4) if prev is not None else None
    change_pct = round((change / float(prev["单位净值"])) * 100, 2) if prev is not None and change else None
    return {
        "ticker": ticker, "name": "", "market": "fund",
        "price": price, "change": change, "change_pct": change_pct,
    }


# ── 近期价格 ──

@safe_fetch("akshare_recent_prices", timeout=10, retries=0, fallback=list)
def get_recent_prices(ticker: str, market: str, days: int = 20) -> list:
    """获取近 N 日收盘价（oldest first）。"""
    if market == "a_share":
        df = ak.stock_zh_a_hist(symbol=ticker, period="daily", adjust="qfq")
        if df is not None and not df.empty:
            return df["收盘"].tail(days).tolist()
    elif market == "hk_stock":
        df = ak.stock_hk_hist(symbol=ticker, period="daily", adjust="qfq")
        if df is not None and not df.empty:
            col = "收盘" if "收盘" in df.columns else "Close"
            return df[col].tail(days).tolist()
    elif market == "us_stock":
        t = yf.Ticker(ticker)
        hist = t.history(period="1mo")
        if hist is not None and not hist.empty:
            return hist["Close"].tail(days).tolist()
    elif market == "fund":
        df = ak.fund_open_fund_info_em(symbol=ticker, indicator="单位净值走势")
        if df is not None and not df.empty:
            return df["单位净值"].tail(days).astype(float).tolist()
    return []
