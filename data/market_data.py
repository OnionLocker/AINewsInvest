"""
data/market_data.py - 行情数据获取层

统一封装 akshare（A股/港股/基金）和 yfinance（美股）的数据获取，
对外提供统一接口：get_quote(ticker, market) → dict
"""
import akshare as ak
import yfinance as yf
from utils.logger import app_logger

# 缓存 TTL（秒），避免短时间重复请求
_cache: dict = {}
_CACHE_TTL = 60

import time


def _cached(key: str):
    """检查缓存是否有效"""
    if key in _cache:
        data, ts = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return data
    return None


def _set_cache(key: str, data: dict):
    _cache[key] = (data, time.time())


def get_quote(ticker: str, market: str) -> dict | None:
    """
    获取单个标的最新行情。
    返回: {"ticker", "name", "price", "change", "change_pct", "volume"} 或 None
    """
    cache_key = f"{market}:{ticker}"
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
        app_logger.warning(f"行情获取失败 [{market}:{ticker}]: {e}")
        return None


def get_quotes_batch(items: list[dict]) -> list[dict]:
    """
    批量获取行情，items 格式: [{"ticker": "600519", "market": "a_share", "name": "贵州茅台"}, ...]
    返回带价格信息的列表
    """
    results = []
    for item in items:
        quote = get_quote(item["ticker"], item["market"])
        if quote:
            results.append(quote)
        else:
            results.append({
                "ticker": item["ticker"],
                "name": item.get("name", ""),
                "market": item["market"],
                "price": None,
                "change": None,
                "change_pct": None,
            })
    return results


# ── A 股行情 ──────────────────────────────────────────────────

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


# ── 港股行情 ──────────────────────────────────────────────────

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


# ── 美股行情（yfinance）───────────────────────────────────────

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
        "name": ticker,  # yfinance 不直接返回中文名，用 symbols.json 补充
        "market": "us_stock",
        "price": round(price, 2),
        "change": change,
        "change_pct": change_pct,
    }


# ── 基金净值 ──────────────────────────────────────────────────

def _quote_fund(ticker: str) -> dict | None:
    try:
        df = ak.fund_open_fund_info_em(symbol=ticker, indicator="单位净值走势")
        if df.empty:
            return None
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else None
        price = float(latest["单位净值"])
        change = round(price - float(prev["单位净值"]), 4) if prev is not None else None
        change_pct = round((change / float(prev["单位净值"])) * 100, 2) if prev is not None and change else None
        return {
            "ticker": ticker,
            "name": "",
            "market": "fund",
            "price": price,
            "change": change,
            "change_pct": change_pct,
        }
    except Exception:
        return None


def get_recent_prices(ticker: str, market: str, days: int = 20) -> list:
    """Return list of recent closing prices (oldest first)."""
    try:
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
    except Exception as e:
        app_logger.warning(f"近期价格获取失败 [{market}:{ticker}]: {e}")
    return []
