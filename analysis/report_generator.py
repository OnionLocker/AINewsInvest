"""
analysis/report_generator.py - 每日报告生成器

流程：
  1. 从 stock_pool 获取固定标的 + stock_screener 获取异动标的
  2. 对每只标的：拉取 K 线 → 技术分析 → 拉取新闻 → 情绪分析
  3. 若 LLM 可用，调用 LLM 做深度综合分析
  4. 综合评分排序
  5. 生成结构化报告数据
"""
import json
from datetime import date
from analysis.technical import analyze as tech_analyze
from analysis.news_fetcher import fetch_news, analyze_sentiment
from analysis.stock_pool import get_pool
from analysis.llm_client import llm_analyze_stock, _is_enabled as llm_enabled
from utils.logger import app_logger


def generate_report(market: str, use_screener: bool = True) -> dict:
    """
    生成指定市场的每日报告。
    返回可直接 json.dumps 存入 DailyReport.data 的 dict。
    """
    pool = get_pool(market)
    pool_tickers = {t for t, _ in pool}

    # 动态筛选异动标的，合并到分析池
    screened_info = []
    if use_screener:
        try:
            from analysis.stock_screener import screen_market
            screened = screen_market(market)
            for ticker, name, reason in screened:
                if ticker not in pool_tickers:
                    pool.append((ticker, name))
                    pool_tickers.add(ticker)
                screened_info.append({"ticker": ticker, "name": name, "reason": reason})
            if screened:
                app_logger.info(f"[报告] 筛选器补充 {len(screened)} 只异动标的")
        except Exception as e:
            app_logger.warning(f"[报告] 筛选器异常: {e}")

    if not pool:
        return _empty_report(market)

    app_logger.info(f"[报告] 开始生成 {market} 报告，共 {len(pool)} 只标的")
    has_llm = llm_enabled()
    if has_llm:
        app_logger.info("[报告] LLM 已启用，将调用深度分析")

    items = []
    for ticker, name in pool:
        try:
            item = _analyze_one(ticker, name, market, has_llm)
            if item:
                # 标记是否为筛选器发现
                for si in screened_info:
                    if si["ticker"] == ticker:
                        item["screened"] = True
                        item["screenReason"] = si["reason"]
                        break
                items.append(item)
        except Exception as e:
            app_logger.warning(f"[报告] 分析 {market}:{ticker} 失败: {e}")

    items.sort(key=lambda x: x["confidence"], reverse=True)

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
        "generated_date": date.today().isoformat(),
        "llm_enabled": has_llm,
    }

    app_logger.info(f"[报告] {market} 完成: {total} 只，看多 {buy_count}，看空 {sell_count}")
    return report


def _analyze_one(ticker: str, name: str, market: str, use_llm: bool = False) -> dict | None:
    """分析单只标的，返回报告卡片数据"""
    app_logger.info(f"[报告] 分析 {name}({ticker})...")

    tech = tech_analyze(ticker, market)
    if not tech:
        return None

    if market != "fund":
        news = fetch_news(ticker, market, limit=8)
        sentiment = analyze_sentiment(news)
    else:
        news = []
        sentiment = {"score": 0, "label": "N/A", "positive": 0, "negative": 0, "summary": "基金不分析新闻面。"}

    tech_conf = tech["confidence"]
    news_modifier = sentiment["score"] * 15
    if tech["signal"] == "sell":
        news_modifier = -news_modifier
    combined_conf = min(95, max(20, int(tech_conf + news_modifier)))

    if tech["signal"] == "buy":
        direction = "buy"
        dir_label = "看多"
    elif tech["signal"] == "sell":
        direction = "sell"
        dir_label = "看空"
    else:
        direction = "buy" if sentiment["score"] > 0.2 else ("sell" if sentiment["score"] < -0.2 else "buy")
        dir_label = "观望偏多" if direction == "buy" else "观望偏空"

    price_str = _format_price(tech["price"], market)
    change_str = f"+{tech['change_pct']}%" if tech["change_pct"] >= 0 else f"{tech['change_pct']}%"

    item = {
        "ticker": ticker,
        "name": name,
        "direction": direction,
        "dirLabel": dir_label,
        "price": price_str,
        "price_raw": tech["price"],
        "change": change_str,
        "change_pct": tech["change_pct"],
        "confidence": combined_conf,
        "entry": tech["entry"],
        "stop_loss": tech["stop_loss"],
        "take_profit_1": tech["take_profit_1"],
        "take_profit_2": tech["take_profit_2"],
        "risk_reward": tech["risk_reward"],
        "techReason": tech["tech_summary"],
        "newsReason": sentiment["summary"],
        "indicators": tech["indicators"],
        "screened": False,
        "screenReason": "",
        "llmReason": "",
    }

    # LLM 深度分析
    if use_llm:
        try:
            llm_result = llm_analyze_stock(ticker, name, market, tech, news)
            if llm_result and llm_result.get("llm_summary"):
                item["llmReason"] = llm_result["llm_summary"]
                # LLM 置信度微调：如果 LLM 分析与技术面方向一致，加分
                if ("看多" in item["llmReason"] or "买入" in item["llmReason"]) and direction == "buy":
                    item["confidence"] = min(95, item["confidence"] + 5)
                elif ("看空" in item["llmReason"] or "减仓" in item["llmReason"]) and direction == "sell":
                    item["confidence"] = min(95, item["confidence"] + 5)
        except Exception as e:
            app_logger.warning(f"[报告] LLM 分析 {ticker} 失败: {e}")

    return item


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
        "generated_date": date.today().isoformat(),
        "llm_enabled": False,
    }
