"""
analysis/report_generator.py - 每日报告生成器

流程：
  1. 从 stock_pool 获取固定标的 + stock_screener 获取异动标的
  2. 对每只标的：技术分析 → 新闻情绪 → 基本面 → 估值 → LLM
  3. 综合评分排序
  4. 生成结构化报告数据
"""
import json
from datetime import date
from analysis.technical import analyze as tech_analyze
from analysis.news_fetcher import fetch_news, analyze_sentiment
from analysis.stock_pool import get_pool
from analysis.llm_client import llm_analyze_stock, _is_enabled as llm_enabled
from utils.logger import app_logger
from utils.config_loader import get_config


def generate_report(market: str, use_screener: bool = True) -> dict:
    """
    生成指定市场的每日报告。
    返回可直接 json.dumps 存入 DailyReport.data 的 dict。
    """
    pool = get_pool(market)
    pool_tickers = {t for t, _ in pool}

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
    fund_enabled = _is_fundamental_enabled()

    if has_llm:
        app_logger.info("[报告] LLM 已启用")
    if fund_enabled:
        app_logger.info("[报告] 基本面分析已启用")

    items = []
    for ticker, name in pool:
        try:
            item = _analyze_one(ticker, name, market, has_llm, fund_enabled)
            if item:
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
        sentiment, sentiment_class = "偏多", "text-success"
    elif sell_count > buy_count * 1.5:
        sentiment, sentiment_class = "偏空", "text-danger"
    else:
        sentiment, sentiment_class = "中性", "text-warning"

    return {
        "metrics": {
            "count": total, "bull": buy_count, "bear": sell_count,
            "sentiment": sentiment, "sentimentClass": sentiment_class,
        },
        "items": items,
        "generated_date": date.today().isoformat(),
        "llm_enabled": has_llm,
        "fundamental_enabled": fund_enabled,
    }


def _analyze_one(ticker: str, name: str, market: str,
                 use_llm: bool = False, use_fundamental: bool = False) -> dict | None:
    """分析单只标的，返回报告卡片数据"""
    app_logger.info(f"[报告] 分析 {name}({ticker})...")

    # ── 技术面 (必须) ──
    tech = tech_analyze(ticker, market)
    if not tech:
        return None

    # ── 新闻面 ──
    if market != "fund":
        news = fetch_news(ticker, market, limit=8)
        sentiment = analyze_sentiment(news)
    else:
        news = []
        sentiment = {"score": 0, "label": "N/A", "positive": 0,
                     "negative": 0, "summary": "基金不分析新闻面。"}

    # ── 基本面 + 估值 (可选) ──
    fund_data = None
    val_data = None
    if use_fundamental and market != "fund":
        fund_data, val_data = _get_fundamental_valuation(ticker, market, tech["price"])

    # ── 综合置信度 ──
    tech_conf = tech["confidence"]
    news_mod = sentiment["score"] * 10
    if tech["signal"] == "sell":
        news_mod = -news_mod

    fund_mod = 0
    if fund_data:
        fund_mod = (fund_data.get("quality_score", 50) - 50) * 0.15
    val_mod = 0
    if val_data:
        margin = val_data.get("safety_margin", {}).get("margin_pct")
        if margin is not None:
            if margin >= 30:
                val_mod = 5
            elif margin < 0:
                val_mod = -5

    combined_conf = min(95, max(20, int(tech_conf + news_mod + fund_mod + val_mod)))

    # ── 方向判定 ──
    if tech["signal"] == "buy":
        direction, dir_label = "buy", "看多"
    elif tech["signal"] == "sell":
        direction, dir_label = "sell", "看空"
    else:
        direction = "buy" if sentiment["score"] > 0.2 else (
            "sell" if sentiment["score"] < -0.2 else "buy")
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
        # ── 新增字段 ──
        "fundamentalReason": fund_data["fundamental_summary"] if fund_data else "",
        "valuationReason": val_data["valuation_summary"] if val_data else "",
        "riskFlags": fund_data["risk_flags"] if fund_data else [],
        "qualityScore": fund_data["quality_score"] if fund_data else None,
        "safetyMargin": (val_data["safety_margin"]["margin_pct"]
                         if val_data and val_data.get("safety_margin") else None),
        "penetrationReturn": (val_data["penetration_return"]["rate"]
                              if val_data and val_data.get("penetration_return") else None),
    }

    # ── LLM 深度分析 ──
    if use_llm:
        try:
            llm_result = llm_analyze_stock(
                ticker, name, market, tech, news,
                fundamental_data=fund_data,
                valuation_data=val_data,
            )
            if llm_result and llm_result.get("llm_summary"):
                item["llmReason"] = llm_result["llm_summary"]
                if (("看多" in item["llmReason"] or "买入" in item["llmReason"])
                        and direction == "buy"):
                    item["confidence"] = min(95, item["confidence"] + 5)
                elif (("看空" in item["llmReason"] or "减仓" in item["llmReason"])
                      and direction == "sell"):
                    item["confidence"] = min(95, item["confidence"] + 5)
        except Exception as e:
            app_logger.warning(f"[报告] LLM 分析 {ticker} 失败: {e}")

    return item


def _get_fundamental_valuation(ticker: str, market: str,
                               price: float) -> tuple[dict | None, dict | None]:
    """获取基本面和估值数据, 失败返回 (None, None)"""
    fund_data = None
    val_data = None
    try:
        from analysis.fundamental import analyze as fund_analyze
        fund_data = fund_analyze(ticker, market)
    except Exception as e:
        app_logger.warning(f"[报告] 基本面 {ticker}: {e}")

    if fund_data:
        try:
            from data.financial import get_financial_data
            from analysis.valuation import valuate
            fin = get_financial_data(ticker, market)
            if fin:
                val_data = valuate(fin, price)
        except Exception as e:
            app_logger.warning(f"[报告] 估值 {ticker}: {e}")

    return fund_data, val_data


def _is_fundamental_enabled() -> bool:
    cfg = get_config().get("fundamental", {})
    return cfg.get("enabled", True)


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
        "metrics": {"count": 0, "bull": 0, "bear": 0,
                    "sentiment": "无数据", "sentimentClass": ""},
        "items": [],
        "generated_date": date.today().isoformat(),
        "llm_enabled": False,
        "fundamental_enabled": False,
    }
