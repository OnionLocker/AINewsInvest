"""
analysis/news_fetcher.py - 新闻抓取 + 简单情绪分析

A股/港股：akshare 东方财富新闻
美股：yfinance news
情绪判定：关键词匹配（后续可接入 LLM 做深度分析）
"""
import akshare as ak
import yfinance as yf
from utils.logger import app_logger
from utils.data_fetcher import safe_fetch

# 情绪关键词表
_POSITIVE = {
    "增长", "上涨", "利好", "突破", "创新高", "超预期", "加速", "盈利",
    "回购", "分红", "净买入", "景气", "扩张", "量产", "获批", "中标",
    "签约", "合作", "升级", "涨停", "龙头", "强势", "放量", "新高",
    "surge", "beat", "growth", "upgrade", "bullish", "record", "profit",
    "buy", "outperform", "raise", "expand", "breakthrough",
}

_NEGATIVE = {
    "下跌", "利空", "跌破", "风险", "亏损", "下滑", "减持", "处罚",
    "违规", "退市", "暴雷", "暴跌", "裁员", "召回", "诉讼", "做空",
    "降级", "库存", "承压", "萎缩", "收缩", "跌停", "破位", "缩量",
    "decline", "miss", "loss", "downgrade", "bearish", "cut", "weak",
    "sell", "underperform", "risk", "layoff", "lawsuit", "short",
}


def fetch_news(ticker: str, market: str, limit: int = 10) -> list[dict]:
    """获取个股最近新闻，失败时降级为空列表。"""
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
        app_logger.warning(f"[新闻] 获取失败 [{market}:{ticker}]: {type(e).__name__}: {e}")
        return []


@safe_fetch("akshare_news", timeout=8, retries=0, fallback=list)
def _news_a_share(ticker: str, limit: int) -> list[dict]:
    df = ak.stock_news_em(symbol=ticker)
    if df is None or df.empty:
        return []
    items = []
    for _, row in df.head(limit).iterrows():
        items.append({
            "title": str(row.get("新闻标题", "")),
            "time": str(row.get("发布时间", "")),
            "source": str(row.get("文章来源", "")),
        })
    return items


@safe_fetch("akshare_news_hk", timeout=8, retries=0, fallback=list)
def _news_hk(ticker: str, limit: int) -> list[dict]:
    df = ak.stock_news_em(symbol=ticker)
    if df is None or df.empty:
        return []
    items = []
    for _, row in df.head(limit).iterrows():
        items.append({
            "title": str(row.get("新闻标题", "")),
            "time": str(row.get("发布时间", "")),
            "source": str(row.get("文章来源", "")),
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
    """基于关键词的简单情绪分析。"""
    if not news:
        return {"score": 0, "label": "中性", "positive": 0, "negative": 0, "summary": "暂无相关新闻。"}

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
        label = "偏多"
    elif score < -0.3:
        label = "偏空"
    else:
        label = "中性"

    summary_parts = []
    if key_titles:
        summary_parts.append(f"近期 {len(news)} 条新闻中，")
        if pos_count:
            summary_parts.append(f"{pos_count} 条偏正面")
        if pos_count and neg_count:
            summary_parts.append("，")
        if neg_count:
            summary_parts.append(f"{neg_count} 条偏负面")
        summary_parts.append("。")
        for t in key_titles[:2]:
            summary_parts.append(f"「{t[:40]}」")
    else:
        summary_parts.append(f"近期 {len(news)} 条新闻未检测到明显情绪倾向。")

    return {
        "score": score,
        "label": label,
        "positive": pos_count,
        "negative": neg_count,
        "summary": "".join(summary_parts),
    }
