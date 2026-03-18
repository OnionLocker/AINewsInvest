"""
analysis/news_fetcher.py - \u65b0\u95fb\u6293\u53d6 + \u7b80\u5355\u60c5\u7eea\u5206\u6790

A\u80a1/\u6e2f\u80a1\uff1aakshare \u4e1c\u65b9\u8d22\u5bcc\u65b0\u95fb
\u7f8e\u80a1\uff1ayfinance news
\u60c5\u7eea\u5224\u5b9a\uff1a\u5173\u952e\u8bcd\u5339\u914d\uff08\u540e\u7eed\u53ef\u63a5\u5165 LLM \u505a\u6df1\u5ea6\u5206\u6790\uff09
"""
import akshare as ak
import yfinance as yf
from utils.logger import app_logger
from utils.data_fetcher import safe_fetch

_POSITIVE = {
    "\u589e\u957f", "\u4e0a\u6da8", "\u5229\u597d", "\u7a81\u7834", "\u521b\u65b0\u9ad8", "\u8d85\u9884\u671f", "\u52a0\u901f", "\u76c8\u5229",
    "\u56de\u8d2d", "\u5206\u7ea2", "\u51c0\u4e70\u5165", "\u666f\u6c14", "\u6269\u5f20", "\u91cf\u4ea7", "\u83b7\u6279", "\u4e2d\u6807",
    "\u7b7e\u7ea6", "\u5408\u4f5c", "\u5347\u7ea7", "\u6da8\u505c", "\u9f99\u5934", "\u5f3a\u52bf", "\u653e\u91cf", "\u65b0\u9ad8",
    "surge", "beat", "growth", "upgrade", "bullish", "record", "profit",
    "buy", "outperform", "raise", "expand", "breakthrough",
}

_NEGATIVE = {
    "\u4e0b\u8dcc", "\u5229\u7a7a", "\u8dcc\u7834", "\u98ce\u9669", "\u4e8f\u635f", "\u4e0b\u6ed1", "\u51cf\u6301", "\u5904\u7f5a",
    "\u8fdd\u89c4", "\u9000\u5e02", "\u66b4\u96f7", "\u66b4\u8dcc", "\u88c1\u5458", "\u53ec\u56de", "\u8bc9\u8bbc", "\u505a\u7a7a",
    "\u964d\u7ea7", "\u5e93\u5b58", "\u627f\u538b", "\u840e\u7f29", "\u6536\u7f29", "\u8dcc\u505c", "\u7834\u4f4d", "\u7f29\u91cf",
    "decline", "miss", "loss", "downgrade", "bearish", "cut", "weak",
    "sell", "underperform", "risk", "layoff", "lawsuit", "short",
}


def fetch_news(ticker: str, market: str, limit: int = 10) -> list[dict]:
    """\u83b7\u53d6\u4e2a\u80a1\u6700\u8fd1\u65b0\u95fb\uff0c\u5931\u8d25\u65f6\u964d\u7ea7\u4e3a\u7a7a\u5217\u8868\u3002"""
    try:
        if market == "a_share":
            return _news_a_share(ticker, limit)
        elif market == "hk_stock":
            return _news_hk(ticker, limit)
        elif market == "us_stock":
            return _news_us(ticker, limit)
        else:
            return []
    except Exception as e:
        app_logger.warning(f"[\u65b0\u95fb] \u83b7\u53d6\u5931\u8d25 [{market}:{ticker}]: {type(e).__name__}: {e}")
        return []


@safe_fetch("akshare_news", timeout=15, retries=1, fallback=list)
def _news_a_share(ticker: str, limit: int) -> list[dict]:
    df = ak.stock_news_em(symbol=ticker)
    if df is None or df.empty:
        return []
    items = []
    for _, row in df.head(limit).iterrows():
        items.append({
            "title": str(row.get("\u65b0\u95fb\u6807\u9898", "")),
            "time": str(row.get("\u53d1\u5e03\u65f6\u95f4", "")),
            "source": str(row.get("\u6587\u7ae0\u6765\u6e90", "")),
        })
    return items


@safe_fetch("akshare_news_hk", timeout=15, retries=1, fallback=list)
def _news_hk(ticker: str, limit: int) -> list[dict]:
    df = ak.stock_news_em(symbol=ticker)
    if df is None or df.empty:
        return []
    items = []
    for _, row in df.head(limit).iterrows():
        items.append({
            "title": str(row.get("\u65b0\u95fb\u6807\u9898", "")),
            "time": str(row.get("\u53d1\u5e03\u65f6\u95f4", "")),
            "source": str(row.get("\u6587\u7ae0\u6765\u6e90", "")),
        })
    return items


@safe_fetch("yfinance_news", timeout=8, retries=0, fallback=list)
def _news_us(ticker: str, limit: int) -> list[dict]:
    t = yf.Ticker(ticker)
    news_list = t.news or []
    items = []
    for n in news_list[:limit]:
        items.append({
            "title": n.get("title", ""),
            "time": "",
            "source": n.get("publisher", ""),
        })
    return items


def analyze_sentiment(news: list[dict]) -> dict:
    """\u57fa\u4e8e\u5173\u952e\u8bcd\u7684\u7b80\u5355\u60c5\u7eea\u5206\u6790\u3002"""
    if not news:
        return {"score": 0, "label": "\u4e2d\u6027", "positive": 0, "negative": 0, "summary": "\u6682\u65e0\u76f8\u5173\u65b0\u95fb\u3002"}

    pos_count = 0
    neg_count = 0
    key_titles = []

    for item in news:
        title = item.get("title", "").lower()
        title_zh = item.get("title", "")
        is_pos = any(kw in title or kw in title_zh for kw in _POSITIVE)
        is_neg = any(kw in title or kw in title_zh for kw in _NEGATIVE)
        if is_pos:
            pos_count += 1
        if is_neg:
            neg_count += 1
        if is_pos or is_neg:
            key_titles.append(title_zh)

    total = pos_count + neg_count
    if total == 0:
        score = 0
    else:
        score = round((pos_count - neg_count) / total, 2)

    if score > 0.3:
        label = "\u504f\u591a"
    elif score < -0.3:
        label = "\u504f\u7a7a"
    else:
        label = "\u4e2d\u6027"

    summary_parts = []
    if key_titles:
        summary_parts.append(f"\u8fd1\u671f {len(news)} \u6761\u65b0\u95fb\u4e2d\uff0c")
        if pos_count:
            summary_parts.append(f"{pos_count} \u6761\u504f\u6b63\u9762")
        if pos_count and neg_count:
            summary_parts.append("\uff0c")
        if neg_count:
            summary_parts.append(f"{neg_count} \u6761\u504f\u8d1f\u9762")
        summary_parts.append("\u3002")
        for t in key_titles[:2]:
            summary_parts.append(f"\u300c{t[:40]}\u300d")
    else:
        summary_parts.append(f"\u8fd1\u671f {len(news)} \u6761\u65b0\u95fb\u672a\u68c0\u6d4b\u5230\u660e\u663e\u60c5\u7eea\u503e\u5411\u3002")

    return {
        "score": score,
        "label": label,
        "positive": pos_count,
        "negative": neg_count,
        "summary": "".join(summary_parts),
    }
