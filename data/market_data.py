"""
data/market_data.py - \u7edf\u4e00\u884c\u60c5\u6570\u636e\u5c42

\u6570\u636e\u6e90\u7b56\u7565\uff08\u7f8e\u56fd\u670d\u52a1\u5668\u4f18\u5316\uff09\uff1a
  - A\u80a1/\u6e2f\u80a1/\u57fa\u91d1\uff1a\u4e3b yfinance \u2192 fallback akshare
  - \u7f8e\u80a1\uff1ayfinance
"""
import time
import yfinance as yf
from utils.logger import app_logger
from utils.data_fetcher import safe_fetch

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


def _to_yf_ashare(ticker: str) -> str:
    t = ticker.strip()
    if t.startswith("6") or t.startswith("9"):
        return f"{t}.SS"
    return f"{t}.SZ"


def _to_yf_hk(ticker: str) -> str:
    t = ticker.strip().lstrip("0") or "0"
    return f"{t}.HK"


def get_quote(ticker: str, market: str) -> dict | None:
    """\u83b7\u53d6\u5355\u53ea\u6807\u7684\u5b9e\u65f6\u884c\u60c5"""
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
        app_logger.warning(f"\u884c\u60c5\u83b7\u53d6\u5931\u8d25 [{market}:{ticker}]: {type(e).__name__}: {e}")
        return None


def get_quotes_batch(items: list[dict]) -> list[dict]:
    """\u6279\u91cf\u83b7\u53d6\u884c\u60c5"""
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


# ============================================================
# A\u80a1\u884c\u60c5\uff1a\u4e3b yfinance \u2192 fallback akshare
# ============================================================

@safe_fetch("yf_a_quote", timeout=15, retries=1, fallback=None)
def _quote_a_share(ticker: str) -> dict | None:
    yf_sym = _to_yf_ashare(ticker)
    result = _yf_quote(yf_sym, ticker, "a_share")
    if result:
        return result

    app_logger.info(f"A\u80a1\u884c\u60c5 [{ticker}] yfinance \u5931\u8d25\uff0c\u5c1d\u8bd5 akshare fallback")
    return _akshare_quote_a(ticker)


def _akshare_quote_a(ticker: str) -> dict | None:
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        row = df[df["\u4ee3\u7801"] == ticker]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            "ticker": ticker,
            "name": str(r.get("\u540d\u79f0", "")),
            "market": "a_share",
            "price": float(r["\u6700\u65b0\u4ef7"]) if r.get("\u6700\u65b0\u4ef7") else None,
            "change": float(r["\u6da8\u8dcc\u989d"]) if r.get("\u6da8\u8dcc\u989d") else None,
            "change_pct": float(r["\u6da8\u8dcc\u5e45"]) if r.get("\u6da8\u8dcc\u5e45") else None,
        }
    except Exception as e:
        app_logger.warning(f"A\u80a1 akshare fallback [{ticker}] \u5931\u8d25: {type(e).__name__}: {e}")
        return None


# ============================================================
# \u6e2f\u80a1\u884c\u60c5\uff1a\u4e3b yfinance \u2192 fallback akshare
# ============================================================

@safe_fetch("yf_hk_quote", timeout=15, retries=1, fallback=None)
def _quote_hk(ticker: str) -> dict | None:
    yf_sym = _to_yf_hk(ticker)
    result = _yf_quote(yf_sym, ticker, "hk_stock")
    if result:
        return result

    app_logger.info(f"\u6e2f\u80a1\u884c\u60c5 [{ticker}] yfinance \u5931\u8d25\uff0c\u5c1d\u8bd5 akshare fallback")
    return _akshare_quote_hk(ticker)


def _akshare_quote_hk(ticker: str) -> dict | None:
    try:
        import akshare as ak
        df = ak.stock_hk_spot_em()
        row = df[df["\u4ee3\u7801"] == ticker]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            "ticker": ticker,
            "name": str(r.get("\u540d\u79f0", "")),
            "market": "hk_stock",
            "price": float(r["\u6700\u65b0\u4ef7"]) if r.get("\u6700\u65b0\u4ef7") else None,
            "change": float(r["\u6da8\u8dcc\u989d"]) if r.get("\u6da8\u8dcc\u989d") else None,
            "change_pct": float(r["\u6da8\u8dcc\u5e45"]) if r.get("\u6da8\u8dcc\u5e45") else None,
        }
    except Exception as e:
        app_logger.warning(f"\u6e2f\u80a1 akshare fallback [{ticker}] \u5931\u8d25: {type(e).__name__}: {e}")
        return None


# ============================================================
# \u7f8e\u80a1\u884c\u60c5\uff1ayfinance
# ============================================================

@safe_fetch("yfinance_us_quote", timeout=10, retries=1, fallback=None)
def _quote_us(ticker: str) -> dict | None:
    return _yf_quote(ticker, ticker, "us_stock")


# ============================================================
# \u57fa\u91d1\u884c\u60c5\uff1a\u4e3b yfinance \u2192 fallback akshare
# ============================================================

@safe_fetch("yf_fund_quote", timeout=15, retries=1, fallback=None)
def _quote_fund(ticker: str) -> dict | None:
    yf_sym = _to_yf_ashare(ticker)
    result = _yf_quote(yf_sym, ticker, "fund")
    if result:
        return result

    app_logger.info(f"\u57fa\u91d1\u884c\u60c5 [{ticker}] yfinance \u5931\u8d25\uff0c\u5c1d\u8bd5 akshare fallback")
    return _akshare_quote_fund(ticker)


def _akshare_quote_fund(ticker: str) -> dict | None:
    try:
        import akshare as ak
        df = ak.fund_open_fund_info_em(symbol=ticker, indicator="\u5355\u4f4d\u51c0\u503c\u8d70\u52bf")
        if df is None or df.empty:
            return None
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else None
        price = float(latest["\u5355\u4f4d\u51c0\u503c"])
        change = round(price - float(prev["\u5355\u4f4d\u51c0\u503c"]), 4) if prev is not None else None
        change_pct = round((change / float(prev["\u5355\u4f4d\u51c0\u503c"])) * 100, 2) if prev is not None and change else None
        return {
            "ticker": ticker, "name": "", "market": "fund",
            "price": price, "change": change, "change_pct": change_pct,
        }
    except Exception as e:
        app_logger.warning(f"\u57fa\u91d1 akshare fallback [{ticker}] \u5931\u8d25: {type(e).__name__}: {e}")
        return None


# ============================================================
# yfinance \u7edf\u4e00\u884c\u60c5\u83b7\u53d6
# ============================================================

def _yf_quote(yf_sym: str, orig_ticker: str, market: str) -> dict | None:
    """yfinance \u83b7\u53d6\u5355\u53ea\u6807\u7684\u884c\u60c5"""
    try:
        t = yf.Ticker(yf_sym)
        info = t.fast_info
        price = getattr(info, "last_price", None)
        prev_close = getattr(info, "previous_close", None)
        if price is None:
            return None
        change = round(price - prev_close, 4) if prev_close else None
        change_pct = round((change / prev_close) * 100, 2) if prev_close and change else None
        return {
            "ticker": orig_ticker,
            "name": orig_ticker,
            "market": market,
            "price": round(price, 4),
            "change": change,
            "change_pct": change_pct,
        }
    except Exception:
        return None


# ============================================================
# \u8fd1\u671f\u4ef7\u683c\u5e8f\u5217\uff1a\u4e3b yfinance \u2192 fallback akshare
# ============================================================

@safe_fetch("recent_prices", timeout=15, retries=1, fallback=list)
def get_recent_prices(ticker: str, market: str, days: int = 20) -> list:
    """\u83b7\u53d6\u8fd1 N \u65e5\u6536\u76d8\u4ef7\u5e8f\u5217"""
    if market == "a_share":
        yf_sym = _to_yf_ashare(ticker)
    elif market == "hk_stock":
        yf_sym = _to_yf_hk(ticker)
    elif market == "us_stock":
        yf_sym = ticker
    elif market == "fund":
        yf_sym = _to_yf_ashare(ticker)
    else:
        return []

    try:
        t = yf.Ticker(yf_sym)
        hist = t.history(period="1mo")
        if hist is not None and not hist.empty:
            return hist["Close"].tail(days).tolist()
    except Exception:
        pass

    if market in ("a_share", "hk_stock", "fund"):
        return _recent_prices_akshare_fallback(ticker, market, days)

    return []


def _recent_prices_akshare_fallback(ticker: str, market: str, days: int) -> list:
    try:
        import akshare as ak
        if market == "a_share":
            df = ak.stock_zh_a_hist(symbol=ticker, period="daily", adjust="qfq")
            if df is not None and not df.empty:
                return df["\u6536\u76d8"].tail(days).tolist()
        elif market == "hk_stock":
            df = ak.stock_hk_hist(symbol=ticker, period="daily", adjust="qfq")
            if df is not None and not df.empty:
                col = "\u6536\u76d8" if "\u6536\u76d8" in df.columns else "Close"
                return df[col].tail(days).tolist()
        elif market == "fund":
            df = ak.fund_open_fund_info_em(symbol=ticker, indicator="\u5355\u4f4d\u51c0\u503c\u8d70\u52bf")
            if df is not None and not df.empty:
                return df["\u5355\u4f4d\u51c0\u503c"].tail(days).astype(float).tolist()
    except Exception as e:
        app_logger.warning(f"akshare fallback \u8fd1\u671f\u4ef7\u683c [{market}:{ticker}] \u5931\u8d25: {e}")
    return []
