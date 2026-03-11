"""
analysis/report_generator.py - 每日报告生成器

流程：
  1. 从 stock_pool 获取待分析标的
  2. 对每只标的：拉取 K 线 → 技术分析 → 拉取新闻 → 情绪分析
  3. 综合评分排序
  4. 生成结构化报告数据
"""
import json
from datetime import date
from analysis.technical import analyze as tech_analyze
from analysis.news_fetcher import fetch_news, analyze_sentiment
from analysis.stock_pool import get_pool
from utils.logger import app_logger


def generate_report(market: str) -> dict:
    """
    生成指定市场的每日报告。
    返回可直接 json.dumps 存入 DailyReport.data 的 dict。
    """
    pool = get_pool(market)
    if not pool:
        return _empty_report(market)

    app_logger.info(f"[报告] 开始生成 {market} 报告，共 {len(pool)} 只标的")

    items = []
    for ticker, name in pool:
        try:
            item = _analyze_one(ticker, name, market)
            if item:
                items.append(item)
        except Exception as e:
            app_logger.warning(f"[报告] 分析 {market}:{ticker} 失败: {e}")

    # 按置信度排序，高置信度排前面
    items.sort(key=lambda x: x["confidence"], reverse=True)

    # 统计
    buy_count = sum(1 for i in items if i["direction"] == "buy")
    sell_count = sum(1 for i in items if i["direction"] == "sell")
    total = len(items)

    if buy_count > sell_count * 1.5:
        sentiment = "偏多"
        sentiment_class = "text-success"
    elif sell_count > buy_count * 1.5:
        sentiment = "偏空"
        sentiment_class = "text-danger"
    else:
        sentiment = "中性"
        sentiment_class = "text-warning"

    report = {
        "metrics": {
            "count": total,
            "bull": buy_count,
            "bear": sell_count,
            "sentiment": sentiment,
            "sentimentClass": sentiment_class,
        },
        "items": items,
    }

    app_logger.info(f"[报告] {market} 完成: {total} 只，看多 {buy_count}，看空 {sell_count}")
    return report


def _analyze_one(ticker: str, name: str, market: str) -> dict | None:
    """分析单只标的，返回报告卡片数据"""
    app_logger.info(f"[报告] 分析 {name}({ticker})...")

    # 技术面
    tech = tech_analyze(ticker, market)
    if not tech:
        return None

    # 新闻面（基金跳过新闻）
    if market != "fund":
        news = fetch_news(ticker, market, limit=8)
        sentiment = analyze_sentiment(news)
    else:
        news = []
        sentiment = {"score": 0, "label": "N/A", "positive": 0, "negative": 0, "summary": "基金不分析新闻面。"}

    # 综合置信度：技术面权重 70%，新闻面权重 30%
    tech_conf = tech["confidence"]
    news_modifier = sentiment["score"] * 15  # -15 ~ +15
    if tech["signal"] == "sell":
        news_modifier = -news_modifier
    combined_conf = min(95, max(20, int(tech_conf + news_modifier)))

    # 方向标签
    if tech["signal"] == "buy":
        direction = "buy"
        dir_label = "看多"
    elif tech["signal"] == "sell":
        direction = "sell"
        dir_label = "看空"
    else:
        direction = "buy" if sentiment["score"] > 0.2 else ("sell" if sentiment["score"] < -0.2 else "buy")
        dir_label = "观望偏多" if direction == "buy" else "观望偏空"

    # 价格和涨跌幅格式化
    price_str = _format_price(tech["price"], market)
    change_str = f"+{tech['change_pct']}%" if tech["change_pct"] >= 0 else f"{tech['change_pct']}%"

    return {
        "ticker": ticker,
        "name": name,
        "direction": direction,
        "dirLabel": dir_label,
        "price": price_str,
        "change": change_str,
        "confidence": combined_conf,
        # 技术面点位
        "entry": tech["entry"],
        "stop_loss": tech["stop_loss"],
        "take_profit_1": tech["take_profit_1"],
        "take_profit_2": tech["take_profit_2"],
        "risk_reward": tech["risk_reward"],
        # 分析理由
        "techReason": tech["tech_summary"],
        "newsReason": sentiment["summary"],
        # 原始指标（供前端可视化）
        "indicators": tech["indicators"],
    }


def _format_price(price: float, market: str) -> str:
    if market == "us_stock":
        return f"${price:,.2f}"
    elif market == "hk_stock":
        return f"HK${price:,.2f}"
    elif market == "fund":
        return f"{price:.4f}"
    else:
        return f"{price:,.2f}"


def _empty_report(market: str) -> dict:
    return {
        "metrics": {"count": 0, "bull": 0, "bear": 0, "sentiment": "无数据", "sentimentClass": ""},
        "items": [],
    }
