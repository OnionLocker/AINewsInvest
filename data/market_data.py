"""
data/market_data.py - 閻炴稑鏈崕蹇涘极閻楀牆绁﹂柤鎯у槻瑜板洨浠﹂敓锟�

缂備胶鍠嶇粩瀵镐焊娴ｇ瓔妫� akshare闁挎稑婀忛柤璇ф嫹/婵炴搩鍨甸崑锟�/闁糕晜妞介崳楣冩晬婢跺﹥瀚� yfinance闁挎稑鐗忕欢銊╂嚃閳藉懐绀嗛柣銊ュ閺嗙喖骞戦鍨闁告瑦鐗槐锟�
闁圭鍋撻柡鍫濐槸椤﹀鏌堥妸銊ф闁烩偓鍔庣划鈩冩交閿燂拷 safe_fetch 缂備胶鍠嶇粩瀵告惥閸涱喗顦�/闂佹彃绉烽惁锟�/闁绘梹姊归弻鍥ㄧ┍濠靛洤袘闁靛棴鎷�
"""
import time
import akshare as ak
import yfinance as yf
from utils.logger import app_logger
from utils.data_fetcher import safe_fetch

# 闁告劕鎳庨悺銊х磽閹惧磭鎽�
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
    """闁兼儳鍢茶ぐ鍥础閺囨岸鍤嬮柡宥呮川濞堟垿寮甸埀顒勫棘閹峰矈鏀介柟顖氭嫅缁辨繄鏁敂鍓у閻庢稒菧閳ь剨鎷�"""
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
        app_logger.warning(f"[閻炴稑鏈崕寤� 闁兼儳鍢茶ぐ鍥ㄥ緞鏉堫偉袝 [{market}:{ticker}]: {type(e).__name__}: {e}")
        return None


def get_quotes_batch(items: list[dict]) -> list[dict]:
    """闁归潧缍婇崳娲嚔瀹勬澘绲块悶娑樻湰閸庡繘濡撮崒姘闁告瑯浜滈妵鎴犳嫻閵夈倗鐟濋梻鍐嚙椤綁宕楅張鐢甸搨闁靛棴鎷�"""
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


# 闁冲厜鍋撻柍鍏夊亾 A 闁肩寽銈庢斀闁诡垽鎷� 闁冲厜鍋撻柍鍏夊亾

@safe_fetch("akshare_a_quote", timeout=25, retries=2, fallback=None)
def _quote_a_share(ticker: str) -> dict | None:
    df = ak.stock_zh_a_spot_em()
    row = df[df["濞寸媴绲块悥锟�"] == ticker]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "ticker": ticker,
        "name": str(r["闁告艾绉惰ⅷ"]),
        "market": "a_share",
        "price": float(r["闁哄牃鍋撻柡鍌烆暒閻滐拷"]) if r["闁哄牃鍋撻柡鍌烆暒閻滐拷"] else None,
        "change": float(r["婵炴垯鍔忕粚鍏硷紣閿燂拷"]) if r["婵炴垯鍔忕粚鍏硷紣閿燂拷"] else None,
        "change_pct": float(r["婵炴垯鍔忕粚濂哥嵁閿燂拷"]) if r["婵炴垯鍔忕粚濂哥嵁閿燂拷"] else None,
    }


# 闁冲厜鍋撻柍鍏夊亾 婵炴搩鍨甸崑鍌滄偘鐏炴儳鍓� 闁冲厜鍋撻柍鍏夊亾

@safe_fetch("akshare_hk_quote", timeout=25, retries=2, fallback=None)
def _quote_hk(ticker: str) -> dict | None:
    df = ak.stock_hk_spot_em()
    row = df[df["濞寸媴绲块悥锟�"] == ticker]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "ticker": ticker,
        "name": str(r["闁告艾绉惰ⅷ"]),
        "market": "hk_stock",
        "price": float(r["闁哄牃鍋撻柡鍌烆暒閻滐拷"]) if r["闁哄牃鍋撻柡鍌烆暒閻滐拷"] else None,
        "change": float(r["婵炴垯鍔忕粚鍏硷紣閿燂拷"]) if r["婵炴垯鍔忕粚鍏硷紣閿燂拷"] else None,
        "change_pct": float(r["婵炴垯鍔忕粚濂哥嵁閿燂拷"]) if r["婵炴垯鍔忕粚濂哥嵁閿燂拷"] else None,
    }


# 闁冲厜鍋撻柍鍏夊亾 缂傚洤姘﹂崑鍌滄偘鐏炴儳鍓� 闁冲厜鍋撻柍鍏夊亾

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


# 闁冲厜鍋撻柍鍏夊亾 闁糕晜妞介崳楣冨礄閳ь剟宕愰敓锟� 闁冲厜鍋撻柍鍏夊亾

@safe_fetch("akshare_fund_quote", timeout=25, retries=1, fallback=None)
def _quote_fund(ticker: str) -> dict | None:
    df = ak.fund_open_fund_info_em(symbol=ticker, indicator="闁告娲戠紞鍛村礄閳ь剟宕愰懝鎷屾巢闁告棑鎷�")
    if df.empty:
        return None
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else None
    price = float(latest["闁告娲戠紞鍛村礄閳ь剟宕愰敓锟�"])
    change = round(price - float(prev["闁告娲戠紞鍛村礄閳ь剟宕愰敓锟�"]), 4) if prev is not None else None
    change_pct = round((change / float(prev["闁告娲戠紞鍛村礄閳ь剟宕愰敓锟�"])) * 100, 2) if prev is not None and change else None
    return {
        "ticker": ticker, "name": "", "market": "fund",
        "price": price, "change": change, "change_pct": change_pct,
    }


# 闁冲厜鍋撻柍鍏夊亾 閺夆晜鍨跺﹢鈩冪闁垮澹� 闁冲厜鍋撻柍鍏夊亾

@safe_fetch("akshare_recent_prices", timeout=25, retries=1, fallback=list)
def get_recent_prices(ticker: str, market: str, days: int = 20) -> list:
    """闁兼儳鍢茶ぐ鍥ㄦ交閿燂拷 N 闁哄啨鍎查弫褰掓儎濡湱骞嗛柨娑樻降ldest first闁挎稑顦埀顒婃嫹"""
    if market == "a_share":
        df = ak.stock_zh_a_hist(symbol=ticker, period="daily", adjust="qfq")
        if df is not None and not df.empty:
            return df["闁衡偓閸撲焦纾�"].tail(days).tolist()
    elif market == "hk_stock":
        df = ak.stock_hk_hist(symbol=ticker, period="daily", adjust="qfq")
        if df is not None and not df.empty:
            col = "闁衡偓閸撲焦纾�" if "闁衡偓閸撲焦纾�" in df.columns else "Close"
            return df[col].tail(days).tolist()
    elif market == "us_stock":
        t = yf.Ticker(ticker)
        hist = t.history(period="1mo")
        if hist is not None and not hist.empty:
            return hist["Close"].tail(days).tolist()
    elif market == "fund":
        df = ak.fund_open_fund_info_em(symbol=ticker, indicator="闁告娲戠紞鍛村礄閳ь剟宕愰懝鎷屾巢闁告棑鎷�")
        if df is not None and not df.empty:
            return df["闁告娲戠紞鍛村礄閳ь剟宕愰敓锟�"].tail(days).astype(float).tolist()
    return []
