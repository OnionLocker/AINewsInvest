"""
analysis/technical.py - \u6280\u672f\u9762\u5206\u6790\u5f15\u64ce

\u6d41\u7a0b\uff1a\u62c9\u53d6 K \u7ebf \u2192 \u8ba1\u7b97\u6307\u6807 \u2192 \u5224\u65ad\u8d8b\u52bf \u2192 \u7ed9\u51fa\u5165\u573a/\u6b62\u635f/\u6b62\u76c8\u70b9\u4f4d

\u6570\u636e\u6e90\u7b56\u7565\uff08\u7f8e\u56fd\u670d\u52a1\u5668\u4f18\u5316\uff09\uff1a
  - A\u80a1\uff1a\u4e3b yfinance (ticker.SS/SZ) \u2192 fallback akshare
  - \u6e2f\u80a1\uff1a\u4e3b yfinance (ticker.HK) \u2192 fallback akshare
  - \u7f8e\u80a1\uff1ayfinance
  - \u57fa\u91d1\uff1a\u4e3b yfinance (ticker.SS/SZ) \u2192 fallback akshare

\u8d85\u65f6\u63a7\u5236\u4f7f\u7528 ThreadPoolExecutor\uff0c\u517c\u5bb9 gunicorn gthread worker\u3002
"""
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

import numpy as np
import pandas as pd
import yfinance as yf
from utils.logger import app_logger

LOOKBACK_DAYS = 120
_KLINE_TIMEOUT_SECONDS = 20
_KLINE_CACHE_TTL_SECONDS = 1800
_kline_cache: dict[str, tuple[pd.DataFrame | None, float]] = {}

_MISSING = object()


def _cache_get(key: str) -> pd.DataFrame | None | object:
    item = _kline_cache.get(key)
    if not item:
        return _MISSING
    value, ts = item
    if time.time() - ts > _KLINE_CACHE_TTL_SECONDS:
        return _MISSING
    return value


def _cache_set(key: str, value: pd.DataFrame | None):
    _kline_cache[key] = (value, time.time())


# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
# Ticker \u8f6c\u6362\uff1a\u5c06\u56fd\u5185\u4ee3\u7801\u8f6c\u6362\u4e3a yfinance \u53ef\u8bc6\u522b\u7684\u683c\u5f0f
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def _to_yf_ticker_ashare(ticker: str) -> str:
    """A\u80a1\u4ee3\u7801 \u2192 yfinance: 6\u5f00\u5934=\u6caa(.SS), 0/3\u5f00\u5934=\u6df1(.SZ)"""
    t = ticker.strip()
    if t.startswith("6") or t.startswith("9"):
        return f"{t}.SS"
    else:
        return f"{t}.SZ"


def _to_yf_ticker_hk(ticker: str) -> str:
    """\u6e2f\u80a1\u4ee3\u7801 \u2192 yfinance: \u53bb\u6389\u524d\u5bfc0, \u52a0.HK"""
    t = ticker.strip().lstrip("0") or "0"
    return f"{t}.HK"


def _to_yf_ticker_fund(ticker: str) -> str:
    """\u57fa\u91d1/ETF\u4ee3\u7801 \u2192 yfinance: \u540c A\u80a1\u89c4\u5219"""
    return _to_yf_ticker_ashare(ticker)


# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
# yfinance \u7edf\u4e00 K \u7ebf\u83b7\u53d6
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def _yf_download(yf_ticker: str) -> pd.DataFrame | None:
    """yfinance \u83b7\u53d6\u65e5K\u7ebf\uff0c\u8fd4\u56de\u6807\u51c6\u5316 DataFrame"""
    t = yf.Ticker(yf_ticker)
    df = t.history(period="6mo")
    if df is None or df.empty:
        return None
    df = df.reset_index()
    df = df.rename(columns={
        "Date": "date", "Open": "open", "High": "high",
        "Low": "low", "Close": "close", "Volume": "volume",
    })
    cols = ["date", "open", "high", "low", "close", "volume"]
    for c in cols:
        if c not in df.columns:
            return None
    df = df[cols].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"])
    if df.empty:
        return None
    return df.tail(LOOKBACK_DAYS).reset_index(drop=True)


# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
# K \u7ebf\u6570\u636e\u83b7\u53d6\uff08\u7ebf\u7a0b\u5b89\u5168\u8d85\u65f6\uff09
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def fetch_kline(ticker: str, market: str) -> pd.DataFrame | None:
    """
    \u62c9\u53d6\u65e5K\u7ebf\uff0c\u8fd4\u56de\u6807\u51c6\u5316 DataFrame\u3002
    A\u80a1/\u6e2f\u80a1/\u57fa\u91d1\uff1a\u4e3b yfinance \u2192 fallback akshare
    \u7f8e\u80a1\uff1ayfinance
    """
    cache_key = f"{market}:{ticker}"
    cached = _cache_get(cache_key)
    if cached is not _MISSING:
        return cached

    def _load():
        if market == "a_share":
            return _kline_a_share(ticker)
        elif market == "hk_stock":
            return _kline_hk(ticker)
        elif market == "us_stock":
            return _kline_us(ticker)
        elif market == "fund":
            return _kline_fund(ticker)
        else:
            return None

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_load)
            df = future.result(timeout=_KLINE_TIMEOUT_SECONDS)
        _cache_set(cache_key, df)
        return df
    except FuturesTimeoutError:
        app_logger.warning(
            f"K\u7ebf\u83b7\u53d6\u8d85\u65f6 [{market}:{ticker}]\uff0c\u5df2\u8df3\u8fc7\uff08>{_KLINE_TIMEOUT_SECONDS}s\uff09"
        )
        _cache_set(cache_key, None)
        return None
    except Exception as e:
        app_logger.warning(f"K\u7ebf\u83b7\u53d6\u5931\u8d25 [{market}:{ticker}]: {type(e).__name__}: {e}")
        _cache_set(cache_key, None)
        return None


def _kline_a_share(ticker: str) -> pd.DataFrame | None:
    """A\u80a1: \u4e3b yfinance \u2192 fallback akshare"""
    yf_sym = _to_yf_ticker_ashare(ticker)
    df = _yf_download(yf_sym)
    if df is not None and len(df) >= 20:
        app_logger.info(f"A\u80a1 K\u7ebf [{ticker}] \u4f7f\u7528 yfinance({yf_sym}) \u6210\u529f")
        return df

    app_logger.info(f"A\u80a1 K\u7ebf [{ticker}] yfinance \u5931\u8d25\uff0c\u5c1d\u8bd5 akshare fallback")
    try:
        import akshare as ak
        df2 = ak.stock_zh_a_hist(symbol=ticker, period="daily", adjust="qfq")
        if df2 is not None and not df2.empty:
            df2 = df2.rename(columns={
                "\u65e5\u671f": "date", "\u5f00\u76d8": "open", "\u6700\u9ad8": "high",
                "\u6700\u4f4e": "low", "\u6536\u76d8": "close", "\u6210\u4ea4\u91cf": "volume",
            })
            df2 = df2[["date", "open", "high", "low", "close", "volume"]].copy()
            df2["date"] = pd.to_datetime(df2["date"])
            for c in ["open", "high", "low", "close", "volume"]:
                df2[c] = pd.to_numeric(df2[c], errors="coerce")
            app_logger.info(f"A\u80a1 K\u7ebf [{ticker}] akshare fallback \u6210\u529f")
            return df2.tail(LOOKBACK_DAYS).reset_index(drop=True)
    except Exception as e:
        app_logger.warning(f"A\u80a1 K\u7ebf [{ticker}] akshare fallback \u5931\u8d25: {type(e).__name__}: {e}")
    return None


def _kline_hk(ticker: str) -> pd.DataFrame | None:
    """\u6e2f\u80a1: \u4e3b yfinance \u2192 fallback akshare"""
    yf_sym = _to_yf_ticker_hk(ticker)
    df = _yf_download(yf_sym)
    if df is not None and len(df) >= 20:
        app_logger.info(f"\u6e2f\u80a1 K\u7ebf [{ticker}] \u4f7f\u7528 yfinance({yf_sym}) \u6210\u529f")
        return df

    app_logger.info(f"\u6e2f\u80a1 K\u7ebf [{ticker}] yfinance \u5931\u8d25\uff0c\u5c1d\u8bd5 akshare fallback")
    try:
        import akshare as ak
        df2 = ak.stock_hk_hist(symbol=ticker, period="daily", adjust="qfq")
        if df2 is not None and not df2.empty:
            df2 = df2.rename(columns={
                "\u65e5\u671f": "date", "\u5f00\u76d8": "open", "\u6700\u9ad8": "high",
                "\u6700\u4f4e": "low", "\u6536\u76d8": "close", "\u6210\u4ea4\u91cf": "volume",
            })
            df2 = df2[["date", "open", "high", "low", "close", "volume"]].copy()
            df2["date"] = pd.to_datetime(df2["date"])
            for c in ["open", "high", "low", "close", "volume"]:
                df2[c] = pd.to_numeric(df2[c], errors="coerce")
            app_logger.info(f"\u6e2f\u80a1 K\u7ebf [{ticker}] akshare fallback \u6210\u529f")
            return df2.tail(LOOKBACK_DAYS).reset_index(drop=True)
    except Exception as e:
        app_logger.warning(f"\u6e2f\u80a1 K\u7ebf [{ticker}] akshare fallback \u5931\u8d25: {type(e).__name__}: {e}")
    return None


def _kline_us(ticker: str) -> pd.DataFrame | None:
    """\u7f8e\u80a1: \u76f4\u63a5 yfinance"""
    return _yf_download(ticker)


def _kline_fund(ticker: str) -> pd.DataFrame | None:
    """\u57fa\u91d1/ETF: \u4e3b yfinance \u2192 fallback akshare \u51c0\u503c\u8d70\u52bf"""
    yf_sym = _to_yf_ticker_fund(ticker)
    df = _yf_download(yf_sym)
    if df is not None and len(df) >= 10:
        app_logger.info(f"\u57fa\u91d1 K\u7ebf [{ticker}] \u4f7f\u7528 yfinance({yf_sym}) \u6210\u529f")
        return df

    app_logger.info(f"\u57fa\u91d1 K\u7ebf [{ticker}] yfinance \u5931\u8d25\uff0c\u5c1d\u8bd5 akshare fallback")
    try:
        import akshare as ak
        df2 = ak.fund_open_fund_info_em(symbol=ticker, indicator="\u5355\u4f4d\u51c0\u503c\u8d70\u52bf")
        if df2 is not None and not df2.empty:
            df2 = df2.rename(columns={"\u51c0\u503c\u65e5\u671f": "date", "\u5355\u4f4d\u51c0\u503c": "close"})
            df2["date"] = pd.to_datetime(df2["date"])
            df2["close"] = pd.to_numeric(df2["close"], errors="coerce")
            df2["open"] = df2["close"]
            df2["high"] = df2["close"]
            df2["low"] = df2["close"]
            df2["volume"] = 0
            df2 = df2[["date", "open", "high", "low", "close", "volume"]].copy()
            app_logger.info(f"\u57fa\u91d1 K\u7ebf [{ticker}] akshare fallback \u6210\u529f")
            return df2.tail(LOOKBACK_DAYS).reset_index(drop=True)
    except Exception as e:
        app_logger.warning(f"\u57fa\u91d1 K\u7ebf [{ticker}] akshare fallback \u5931\u8d25: {type(e).__name__}: {e}")
    return None


# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
# \u6280\u672f\u6307\u6807\u8ba1\u7b97
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"]
    h = df["high"]
    l = df["low"]

    for period in [5, 10, 20, 60]:
        df[f"ma{period}"] = c.rolling(period).mean()

    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    df["dif"] = ema12 - ema26
    df["dea"] = df["dif"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = 2 * (df["dif"] - df["dea"])

    delta = c.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    df["boll_mid"] = c.rolling(20).mean()
    boll_std = c.rolling(20).std()
    df["boll_upper"] = df["boll_mid"] + 2 * boll_std
    df["boll_lower"] = df["boll_mid"] - 2 * boll_std

    low9 = l.rolling(9).min()
    high9 = h.rolling(9).max()
    rsv = (c - low9) / (high9 - low9).replace(0, np.nan) * 100
    df["k"] = rsv.ewm(com=2, adjust=False).mean()
    df["d"] = df["k"].ewm(com=2, adjust=False).mean()
    df["j"] = 3 * df["k"] - 2 * df["d"]

    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()

    df["vol_ma5"] = df["volume"].rolling(5).mean()
    df["vol_ma20"] = df["volume"].rolling(20).mean()

    return df


# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
# \u652f\u6491/\u963b\u529b\u4f4d\u8bc6\u522b
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def find_support_resistance(df: pd.DataFrame, n: int = 20) -> dict:
    recent = df.tail(n)
    close = df["close"].iloc[-1]

    levels = set()
    levels.add(round(recent["high"].max(), 2))
    levels.add(round(recent["low"].min(), 2))
    for ma in ["ma5", "ma10", "ma20", "ma60"]:
        if ma in df.columns and pd.notna(df[ma].iloc[-1]):
            levels.add(round(df[ma].iloc[-1], 2))
    if pd.notna(df["boll_upper"].iloc[-1]):
        levels.add(round(df["boll_upper"].iloc[-1], 2))
        levels.add(round(df["boll_lower"].iloc[-1], 2))

    supports = sorted([lv for lv in levels if lv < close], reverse=True)
    resistances = sorted([lv for lv in levels if lv > close])

    return {"supports": supports[:3], "resistances": resistances[:3]}


# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
# \u7efc\u5408\u6280\u672f\u9762\u5206\u6790\uff08\u6838\u5fc3\uff09
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def analyze(ticker: str, market: str) -> dict | None:
    df = fetch_kline(ticker, market)
    if df is None or len(df) < 20:
        return None

    df = compute_indicators(df)
    last = df.iloc[-1]
    prev = df.iloc[-2]

    close = round(float(last["close"]), 2)
    prev_close = float(prev["close"])
    if prev_close == 0:
        return None
    change_pct = round((close - prev_close) / prev_close * 100, 2)
    atr = float(last["atr"]) if pd.notna(last["atr"]) else close * 0.02

    trend_score = 0
    mas = {}
    for p in [5, 10, 20, 60]:
        val = last.get(f"ma{p}")
        if pd.notna(val):
            mas[p] = float(val)

    if mas.get(5) and mas.get(20) and mas.get(60):
        if mas[5] > mas[20] > mas[60]:
            trend_score += 2
        elif mas[5] < mas[20] < mas[60]:
            trend_score -= 2
        trend_score += 1 if close > mas[20] else -1
        trend_score += 1 if close > mas[60] else -1

    if pd.notna(last["dif"]) and pd.notna(last["dea"]):
        if last["dif"] > last["dea"]:
            trend_score += 1
            if prev["dif"] <= prev["dea"]:
                trend_score += 1
        else:
            trend_score -= 1
            if prev["dif"] >= prev["dea"]:
                trend_score -= 1
        trend_score += 0.5 if last["dif"] > 0 else -0.5

    rsi = float(last["rsi"]) if pd.notna(last["rsi"]) else 50
    if rsi > 60:
        trend_score += 1
    elif rsi < 40:
        trend_score -= 1
    if rsi > 80:
        trend_score -= 0.5
    elif rsi < 20:
        trend_score += 0.5

    if pd.notna(last["k"]) and pd.notna(last["d"]):
        trend_score += 0.5 if last["k"] > last["d"] else -0.5

    if pd.notna(last["vol_ma5"]) and pd.notna(last["vol_ma20"]):
        if last["vol_ma5"] > last["vol_ma20"] * 1.3:
            trend_score += 0.5 if change_pct > 0 else -0.5

    if trend_score >= 3:
        trend = "bullish"
        signal_dir = "buy"
    elif trend_score <= -3:
        trend = "bearish"
        signal_dir = "sell"
    else:
        trend = "ranging"
        signal_dir = "neutral"

    confidence = min(95, max(30, int(50 + trend_score * 5)))
    sr = find_support_resistance(df)

    if signal_dir == "buy":
        entry = round(close, 2)
        stop_loss = round(sr["supports"][0] - atr * 0.5, 2) if sr["supports"] else round(entry - atr * 1.5, 2)
        risk = entry - stop_loss
        take_profit_1 = round(entry + risk * 2, 2)
        take_profit_2 = round(entry + risk * 3, 2)
        if sr["resistances"]:
            take_profit_1 = max(take_profit_1, round(sr["resistances"][0], 2))
            if len(sr["resistances"]) > 1:
                take_profit_2 = max(take_profit_2, round(sr["resistances"][1], 2))
    elif signal_dir == "sell":
        entry = round(close, 2)
        stop_loss = round(sr["resistances"][0] + atr * 0.5, 2) if sr["resistances"] else round(entry + atr * 1.5, 2)
        risk = stop_loss - entry
        take_profit_1 = round(entry - risk * 2, 2)
        take_profit_2 = round(entry - risk * 3, 2)
        if sr["supports"]:
            take_profit_1 = min(take_profit_1, round(sr["supports"][0], 2))
            if len(sr["supports"]) > 1:
                take_profit_2 = min(take_profit_2, round(sr["supports"][1], 2))
    else:
        entry = round(close, 2)
        stop_loss = round(close - atr * 1.5, 2)
        take_profit_1 = round(close + atr * 2, 2)
        take_profit_2 = round(close + atr * 3, 2)

    risk_amt = abs(entry - stop_loss)
    reward_amt = abs(take_profit_1 - entry)
    rr = f"1:{round(reward_amt / risk_amt, 1)}" if risk_amt > 0 else "N/A"

    tech_summary = _build_summary(
        trend, signal_dir, close, mas, last, prev, rsi, sr, atr, entry, stop_loss, take_profit_1, take_profit_2
    )

    return {
        "ticker": ticker,
        "market": market,
        "price": close,
        "change_pct": change_pct,
        "trend": trend,
        "signal": signal_dir,
        "confidence": confidence,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "risk_reward": rr,
        "tech_summary": tech_summary,
        "indicators": {
            "ma5": round(mas.get(5, 0), 2),
            "ma20": round(mas.get(20, 0), 2),
            "ma60": round(mas.get(60, 0), 2),
            "rsi": round(rsi, 1),
            "macd_dif": round(float(last["dif"]), 3) if pd.notna(last["dif"]) else None,
            "macd_dea": round(float(last["dea"]), 3) if pd.notna(last["dea"]) else None,
            "atr": round(atr, 2),
            "boll_upper": round(float(last["boll_upper"]), 2) if pd.notna(last["boll_upper"]) else None,
            "boll_lower": round(float(last["boll_lower"]), 2) if pd.notna(last["boll_lower"]) else None,
        },
    }


def _build_summary(trend, signal_dir, close, mas, last, prev, rsi, sr, atr, entry, sl, tp1, tp2) -> str:
    parts = []
    trend_zh = {"bullish": "\u591a\u5934", "bearish": "\u7a7a\u5934", "ranging": "\u9707\u8361"}
    parts.append(f"\u5f53\u524d\u8d8b\u52bf {trend_zh[trend]}\u3002")

    if mas.get(5) and mas.get(20) and mas.get(60):
        if mas[5] > mas[20] > mas[60]:
            parts.append("\u5747\u7ebf\u591a\u5934\u6392\u5217\uff08MA5>MA20>MA60\uff09\uff0c\u4e2d\u671f\u8d8b\u52bf\u5411\u4e0a\u3002")
        elif mas[5] < mas[20] < mas[60]:
            parts.append("\u5747\u7ebf\u7a7a\u5934\u6392\u5217\uff08MA5<MA20<MA60\uff09\uff0c\u4e2d\u671f\u8d8b\u52bf\u5411\u4e0b\u3002")
        else:
            parts.append("\u5747\u7ebf\u4ea4\u7ec7\uff0c\u8d8b\u52bf\u4e0d\u660e\u6717\u3002")
        if close > mas[20]:
            parts.append(f"\u80a1\u4ef7\u7ad9\u4e0a20\u65e5\u5747\u7ebf\uff08{mas[20]:.2f}\uff09\u3002")
        else:
            parts.append(f"\u80a1\u4ef7\u8fd0\u884c\u572820\u65e5\u5747\u7ebf\uff08{mas[20]:.2f}\uff09\u4e0b\u65b9\u3002")

    if pd.notna(last["dif"]) and pd.notna(last["dea"]):
        if last["dif"] > last["dea"] and prev["dif"] <= prev["dea"]:
            parts.append("MACD \u521a\u521a\u5f62\u6210\u91d1\u53c9\uff0c\u77ed\u671f\u52a8\u80fd\u8f6c\u5f3a\u3002")
        elif last["dif"] < last["dea"] and prev["dif"] >= prev["dea"]:
            parts.append("MACD \u5f62\u6210\u6b7b\u53c9\uff0c\u77ed\u671f\u52a8\u80fd\u51cf\u5f31\u3002")
        elif last["dif"] > last["dea"]:
            parts.append("MACD \u591a\u5934\u8fd0\u884c\u4e2d\u3002")
        else:
            parts.append("MACD \u7a7a\u5934\u8fd0\u884c\u4e2d\u3002")

    if rsi > 75:
        parts.append(f"RSI({rsi:.0f}) \u8fdb\u5165\u8d85\u4e70\u533a\u57df\uff0c\u6ce8\u610f\u56de\u8c03\u98ce\u9669\u3002")
    elif rsi < 25:
        parts.append(f"RSI({rsi:.0f}) \u8fdb\u5165\u8d85\u5356\u533a\u57df\uff0c\u53ef\u80fd\u5b58\u5728\u53cd\u5f39\u673a\u4f1a\u3002")
    elif rsi > 55:
        parts.append(f"RSI({rsi:.0f}) \u504f\u5f3a\u3002")
    elif rsi < 45:
        parts.append(f"RSI({rsi:.0f}) \u504f\u5f31\u3002")

    if sr["supports"]:
        parts.append(f"\u4e0b\u65b9\u652f\u6491\uff1a{', '.join(str(s) for s in sr['supports'][:2])}\u3002")
    if sr["resistances"]:
        parts.append(f"\u4e0a\u65b9\u963b\u529b\uff1a{', '.join(str(r) for r in sr['resistances'][:2])}\u3002")

    if signal_dir == "buy":
        parts.append(f"\u5efa\u8bae\u5165\u573a {entry}\uff0c\u6b62\u635f {sl}\uff08-{abs(entry-sl):.2f}\uff09\uff0c\u7b2c\u4e00\u6b62\u76c8 {tp1}\uff08+{abs(tp1-entry):.2f}\uff09\uff0c\u7b2c\u4e8c\u6b62\u76c8 {tp2}\uff08+{abs(tp2-entry):.2f}\uff09\u3002")
    elif signal_dir == "sell":
        parts.append(f"\u5efa\u8bae\u505a\u7a7a/\u51cf\u4ed3\u5165\u573a {entry}\uff0c\u6b62\u635f {sl}\uff08+{abs(sl-entry):.2f}\uff09\uff0c\u7b2c\u4e00\u6b62\u76c8 {tp1}\uff08+{abs(entry-tp1):.2f}\uff09\uff0c\u7b2c\u4e8c\u6b62\u76c8 {tp2}\uff08+{abs(entry-tp2):.2f}\uff09\u3002")
    else:
        parts.append(f"\u5f53\u524d\u66f4\u9002\u5408\u89c2\u671b\uff0c\u82e5\u8bd5\u63a2\u6027\u53c2\u4e0e\uff0c\u53ef\u53c2\u8003\u5165\u573a {entry}\uff0c\u6b62\u635f {sl}\uff0c\u6b62\u76c8 {tp1}/{tp2}\u3002")

    return "".join(parts)
