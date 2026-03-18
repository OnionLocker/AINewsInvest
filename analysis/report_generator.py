"""
analysis/report_generator.py - \u6bcf\u65e5\u62a5\u544a\u751f\u6210\u5668

\u6d41\u7a0b\uff1a
  1. \u4ece stock_pool \u83b7\u53d6\u56fa\u5b9a\u6807\u7684 + stock_screener \u83b7\u53d6\u5f02\u52a8\u6807\u7684
  2. \u5bf9\u6bcf\u53ea\u6807\u7684\uff1a\u6280\u672f\u5206\u6790 \u2192 \u65b0\u95fb\u60c5\u7eea \u2192 \u57fa\u672c\u9762 \u2192 \u4f30\u503c \u2192 LLM
  3. \u7efc\u5408\u8bc4\u5206\u6392\u5e8f
  4. \u751f\u6210\u7ed3\u6784\u5316\u62a5\u544a\u6570\u636e
"""
import json
from datetime import date
from analysis.technical import analyze as tech_analyze
from analysis.news_fetcher import fetch_news, analyze_sentiment
from analysis.stock_pool import get_pool
from analysis.llm_client import llm_analyze_stock, _is_enabled as llm_enabled
from utils.logger import app_logger
from utils.config_loader import get_config


def generate_report(market: str, use_screener: bool = True, use_news: bool = True,
                    progress_cb=None) -> dict:
    """
    \u751f\u6210\u6307\u5b9a\u5e02\u573a\u7684\u6bcf\u65e5\u62a5\u544a\u3002
    progress_cb: \u53ef\u9009\u56de\u8c03 fn(dict) \u7528\u4e8e\u6c47\u62a5\u9010\u53ea\u6807\u7684\u5206\u6790\u8fdb\u5ea6\u3002
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
                app_logger.info(f"[\u62a5\u544a] \u7b5b\u9009\u5668\u8865\u5145 {len(screened)} \u53ea\u5f02\u52a8\u6807\u7684")
        except Exception as e:
            app_logger.warning(f"[\u62a5\u544a] \u7b5b\u9009\u5668\u5f02\u5e38: {e}")

    if not pool:
        return _empty_report(market, reason="\u6807\u7684\u6c60\u4e3a\u7a7a")

    total_tickers = len(pool)
    app_logger.info(f"[\u62a5\u544a] \u5f00\u59cb\u751f\u6210 {market} \u62a5\u544a\uff0c\u5171 {total_tickers} \u53ea\u6807\u7684")
    has_llm = llm_enabled()
    fund_enabled = _is_fundamental_enabled()

    if has_llm:
        app_logger.info("[\u62a5\u544a] LLM \u5df2\u542f\u7528")
    if fund_enabled:
        app_logger.info("[\u62a5\u544a] \u57fa\u672c\u9762\u5206\u6790\u5df2\u542f\u7528")

    items = []
    failed_tickers = []
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time as _time

    def _analyze_with_timeout(ticker, name):
        start = _time.time()
        try:
            item = _analyze_one(ticker, name, market, has_llm, fund_enabled, use_news)
            elapsed = _time.time() - start
            app_logger.info(f"[\u62a5\u544a] {ticker} \u5206\u6790\u5b8c\u6210 ({elapsed:.1f}s)")
            return item
        except Exception as e:
            elapsed = _time.time() - start
            app_logger.warning(f"[\u62a5\u544a] {ticker} \u5206\u6790\u5931\u8d25 ({elapsed:.1f}s): {type(e).__name__}: {e}")
            return None

    done_count = 0
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_ticker = {
                executor.submit(_analyze_with_timeout, ticker, name): (ticker, name)
                for ticker, name in pool
            }
            for future in as_completed(future_to_ticker, timeout=300):
                ticker, name = future_to_ticker[future]
                done_count += 1
                try:
                    item = future.result(timeout=60)
                    if item:
                        for si in screened_info:
                            if si["ticker"] == ticker:
                                item["screened"] = True
                                item["screenReason"] = si["reason"]
                                break
                        items.append(item)
                    else:
                        failed_tickers.append({"ticker": ticker, "name": name, "error": "analysis_returned_none"})
                except Exception as e:
                    app_logger.warning(f"[\u62a5\u544a] {ticker} \u8d85\u65f6\u6216\u5f02\u5e38: {e}")
                    failed_tickers.append({"ticker": ticker, "name": name, "error": str(e)})

                if progress_cb:
                    try:
                        progress_cb({
                            "ticker": ticker,
                            "name": name,
                            "completed": done_count,
                            "total": total_tickers,
                            "success_count": len(items),
                            "failed_count": len(failed_tickers),
                        })
                    except Exception:
                        pass
    except Exception as overall_err:
        app_logger.warning(f"[\u62a5\u544a] \u6574\u4f53\u8d85\u65f6\u6216\u5f02\u5e38\uff0c\u5df2\u5b8c\u6210 {done_count}/{total_tickers}: {overall_err}")
        for future, (ticker, name) in future_to_ticker.items():
            if not future.done():
                failed_tickers.append({"ticker": ticker, "name": name, "error": "overall_timeout"})
                future.cancel()

    items.sort(key=lambda x: x["confidence"], reverse=True)

    buy_count = sum(1 for i in items if i["direction"] == "buy")
    sell_count = sum(1 for i in items if i["direction"] == "sell")
    total = len(items)

    if total == 0:
        sentiment, sentiment_class = "\u65e0\u6570\u636e", ""
    elif buy_count > sell_count * 1.5:
        sentiment, sentiment_class = "\u504f\u591a", "text-success"
    elif sell_count > buy_count * 1.5:
        sentiment, sentiment_class = "\u504f\u7a7a", "text-danger"
    else:
        sentiment, sentiment_class = "\u4e2d\u6027", "text-warning"

    tech_failed_count = sum(1 for i in items if i.get("techFailed"))
    partial = tech_failed_count > 0 or len(failed_tickers) > 0

    empty_reason = ""
    if total == 0 and failed_tickers:
        errors = [f.get("error", "") for f in failed_tickers]
        if any("timeout" in e.lower() or "\u8d85\u65f6" in e for e in errors):
            empty_reason = "\u6240\u6709\u6807\u7684\u6570\u636e\u83b7\u53d6\u8d85\u65f6\uff0c\u6570\u636e\u6e90\u53ef\u80fd\u4e0d\u53ef\u7528\u6216\u7f51\u7edc\u5f02\u5e38"
        else:
            empty_reason = "\u6240\u6709\u6807\u7684\u5206\u6790\u5747\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u6570\u636e\u6e90\u53ef\u7528\u6027"

    return {
        "metrics": {
            "count": total, "bull": buy_count, "bear": sell_count,
            "sentiment": sentiment, "sentimentClass": sentiment_class,
        },
        "items": items,
        "generated_date": date.today().isoformat(),
        "llm_enabled": has_llm,
        "fundamental_enabled": fund_enabled,
        "partial_success": partial,
        "tech_failed_count": tech_failed_count,
        "total_tickers": total_tickers,
        "failed_tickers": failed_tickers,
        "empty_reason": empty_reason,
    }


def _analyze_one(ticker: str, name: str, market: str,
                 use_llm: bool = False, use_fundamental: bool = False,
                 use_news: bool = True) -> dict | None:
    """\u5206\u6790\u5355\u53ea\u6807\u7684\uff0c\u8fd4\u56de\u62a5\u544a\u5361\u7247\u6570\u636e"""
    app_logger.info(f"[\u62a5\u544a] \u5206\u6790 {name}({ticker})...")

    tech = None
    tech_failed = False
    try:
        tech = tech_analyze(ticker, market)
    except Exception as e:
        app_logger.warning(f"[\u62a5\u544a] \u6280\u672f\u5206\u6790\u5f02\u5e38 {ticker}: {type(e).__name__}: {e}")
    if not tech:
        tech_failed = True
        app_logger.warning(f"[\u62a5\u544a] {ticker} \u6280\u672f\u5206\u6790\u5931\u8d25\uff0c\u5c06\u8f93\u51fa\u964d\u7ea7\u7ed3\u679c")

    if market != "fund" and use_news:
        news = fetch_news(ticker, market, limit=8)
        sentiment = analyze_sentiment(news)
    else:
        news = []
        sentiment = {"score": 0, "label": "N/A", "positive": 0,
                     "negative": 0, "summary": "\u5df2\u8df3\u8fc7\u65b0\u95fb\u5206\u6790\u3002" if market != "fund" else "\u57fa\u91d1\u4e0d\u5206\u6790\u65b0\u95fb\u9762\u3002"}

    fund_data = None
    val_data = None
    current_price = tech["price"] if tech else None
    if use_fundamental and market != "fund" and current_price:
        fund_data, val_data = _get_fundamental_valuation(ticker, market, current_price)

    tech_conf = tech["confidence"] if tech else 30
    news_mod = sentiment["score"] * 10
    if tech and tech["signal"] == "sell":
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

    if tech and tech["signal"] == "buy":
        direction, dir_label = "buy", "\u770b\u591a"
    elif tech and tech["signal"] == "sell":
        direction, dir_label = "sell", "\u770b\u7a7a"
    else:
        direction = "buy" if sentiment["score"] > 0.2 else (
            "sell" if sentiment["score"] < -0.2 else "buy")
        dir_label = "\u89c2\u671b\u504f\u591a" if direction == "buy" else "\u89c2\u671b\u504f\u7a7a"

    if tech:
        price_str = _format_price(tech["price"], market)
        change_str = f"+{tech['change_pct']}%" if tech["change_pct"] >= 0 else f"{tech['change_pct']}%"
    else:
        price_str = "--"
        change_str = "--"

    item = {
        "ticker": ticker,
        "name": name,
        "direction": direction,
        "dirLabel": dir_label,
        "price": price_str,
        "price_raw": tech["price"] if tech else 0,
        "change": change_str,
        "change_pct": tech["change_pct"] if tech else 0,
        "confidence": combined_conf,
        "entry": tech["entry"] if tech else 0,
        "stop_loss": tech["stop_loss"] if tech else 0,
        "take_profit_1": tech["take_profit_1"] if tech else 0,
        "take_profit_2": tech["take_profit_2"] if tech else 0,
        "risk_reward": tech["risk_reward"] if tech else "N/A",
        "techReason": tech["tech_summary"] if tech else "\u6280\u672f\u5206\u6790\u6570\u636e\u83b7\u53d6\u5931\u8d25\uff0c\u672c\u6b21\u7ed3\u679c\u4ec5\u57fa\u4e8e\u65b0\u95fb/\u57fa\u672c\u9762\u3002",
        "newsReason": sentiment["summary"],
        "indicators": tech["indicators"] if tech else {},
        "screened": False,
        "screenReason": "",
        "llmReason": "",
        "techFailed": tech_failed,
        "fundamentalReason": fund_data["fundamental_summary"] if fund_data else "",
        "valuationReason": val_data["valuation_summary"] if val_data else "",
        "riskFlags": fund_data["risk_flags"] if fund_data else [],
        "qualityScore": fund_data["quality_score"] if fund_data else None,
        "safetyMargin": (val_data["safety_margin"]["margin_pct"]
                         if val_data and val_data.get("safety_margin") else None),
        "penetrationReturn": (val_data["penetration_return"]["rate"]
                              if val_data and val_data.get("penetration_return") else None),
    }

    if use_llm:
        try:
            llm_result = llm_analyze_stock(
                ticker, name, market, tech or {}, news,
                fundamental_data=fund_data,
                valuation_data=val_data,
            )
            if llm_result and llm_result.get("llm_summary"):
                item["llmReason"] = llm_result["llm_summary"]
                if (("\u770b\u591a" in item["llmReason"] or "\u4e70\u5165" in item["llmReason"])
                        and direction == "buy"):
                    item["confidence"] = min(95, item["confidence"] + 5)
                elif (("\u770b\u7a7a" in item["llmReason"] or "\u51cf\u4ed3" in item["llmReason"])
                      and direction == "sell"):
                    item["confidence"] = min(95, item["confidence"] + 5)
        except Exception as e:
            app_logger.warning(f"[\u62a5\u544a] LLM \u5206\u6790 {ticker} \u5931\u8d25: {e}")

    return item


def _get_fundamental_valuation(ticker: str, market: str,
                               price: float) -> tuple[dict | None, dict | None]:
    """\u83b7\u53d6\u57fa\u672c\u9762\u548c\u4f30\u503c\u6570\u636e, \u5931\u8d25\u8fd4\u56de (None, None)"""
    fund_data = None
    val_data = None
    try:
        from analysis.fundamental import analyze as fund_analyze
        fund_data = fund_analyze(ticker, market)
    except Exception as e:
        app_logger.warning(f"[\u62a5\u544a] \u57fa\u672c\u9762 {ticker}: {e}")

    if fund_data:
        try:
            from data.financial import get_financial_data
            from analysis.valuation import valuate
            fin = get_financial_data(ticker, market)
            if fin:
                val_data = valuate(fin, price)
        except Exception as e:
            app_logger.warning(f"[\u62a5\u544a] \u4f30\u503c {ticker}: {e}")

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


def _empty_report(market: str, reason: str = "") -> dict:
    return {
        "metrics": {"count": 0, "bull": 0, "bear": 0,
                    "sentiment": "\u65e0\u6570\u636e", "sentimentClass": ""},
        "items": [],
        "generated_date": date.today().isoformat(),
        "llm_enabled": False,
        "fundamental_enabled": False,
        "partial_success": False,
        "tech_failed_count": 0,
        "total_tickers": 0,
        "failed_tickers": [],
        "empty_reason": reason,
    }


def generate_weekly_report(market: str) -> dict:
    """
    \u751f\u6210\u672c\u5468\u590d\u76d8\u5468\u62a5\u3002

    \u6c47\u603b\u672c\u5468\u6bcf\u65e5\u62a5\u544a\u4e2d\u7684\u63a8\u8350\u7ed3\u679c\uff0c\u8ba1\u7b97\u80dc\u7387\u3001\u5e73\u5747\u6536\u76ca\u3001\u6bcf\u65e5\u60c5\u7eea\u53d8\u5316\u7b49\u3002
    \u8fd4\u56de dict: {market, week_start, week_end, content, stats}
    """
    from datetime import timedelta
    from models import db, DailyReport, RecommendationTrack

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = today

    reports = DailyReport.query.filter(
        DailyReport.market == market,
        DailyReport.report_date >= week_start,
        DailyReport.report_date <= week_end,
    ).all()

    if not reports:
        return {
            "market": market,
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "content": "\u672c\u5468\u65e0\u65e5\u62a5\u6570\u636e\u3002",
            "stats": {},
        }

    report_ids = [r.id for r in reports]
    tracks = RecommendationTrack.query.filter(
        RecommendationTrack.report_id.in_(report_ids)
    ).all()

    total = len(tracks)
    wins = sum(1 for t in tracks if t.outcome in ("win", "partial"))
    losses = sum(1 for t in tracks if t.outcome == "loss")
    pending = total - wins - losses
    decided = wins + losses
    win_rate = round(wins / decided * 100, 1) if decided > 0 else 0

    returns = []
    best_rec = None
    worst_rec = None
    best_ret = -999
    worst_ret = 999

    for t in tracks:
        final = t.price_after_5d or t.price_after_3d or t.price_after_1d
        if final and t.entry_price and t.entry_price > 0:
            ret = (final - t.entry_price) / t.entry_price * 100
            if t.direction == "sell":
                ret = -ret
            returns.append(ret)
            if ret > best_ret:
                best_ret = ret
                best_rec = t
            if ret < worst_ret:
                worst_ret = ret
                worst_rec = t

    avg_return = round(sum(returns) / len(returns), 2) if returns else 0

    daily_sentiments = []
    for r in sorted(reports, key=lambda x: x.report_date):
        try:
            import json as _json
            data = _json.loads(r.data)
            metrics = data.get("metrics", {})
            daily_sentiments.append({
                "date": r.report_date.isoformat(),
                "sentiment": metrics.get("sentiment", "N/A"),
                "count": metrics.get("count", 0),
                "bull": metrics.get("bull", 0),
                "bear": metrics.get("bear", 0),
            })
        except Exception:
            pass

    market_labels = {"a_share": "A\u80a1", "us_stock": "\u7f8e\u80a1", "hk_stock": "\u6e2f\u80a1", "fund": "\u57fa\u91d1"}
    ml = market_labels.get(market, market)

    lines = []
    lines.append(f"\u25a0 {ml} \u5468\u62a5\u590d\u76d8 ({week_start.isoformat()} ~ {week_end.isoformat()})")
    lines.append("")
    lines.append(f"\u2501 \u7edf\u8ba1\u6982\u89c8")
    lines.append(f"  \u603b\u63a8\u8350: {total} \u53ea | \u80dc\u7387: {win_rate}% | \u5e73\u5747\u6536\u76ca: {avg_return}%")
    lines.append(f"  \u76c8\u5229: {wins} | \u4e8f\u635f: {losses} | \u5f85\u5b9a: {pending}")

    if best_rec:
        lines.append(f"  \u6700\u4f73\u63a8\u8350: {best_rec.ticker} {best_rec.name} +{best_ret:.1f}%")
    if worst_rec:
        lines.append(f"  \u6700\u5dee\u63a8\u8350: {worst_rec.ticker} {worst_rec.name} {worst_ret:.1f}%")

    lines.append("")
    lines.append("\u2501 \u6bcf\u65e5\u60c5\u7eea\u53d8\u5316")
    for ds in daily_sentiments:
        lines.append(f"  {ds['date']}: {ds['sentiment']} (\u591a{ds['bull']} / \u7a7a{ds['bear']})")

    lines.append("")
    lines.append("\u2501 \u672c\u5468\u63a8\u8350\u660e\u7ec6")
    for t in sorted(tracks, key=lambda x: x.created_at or x.id):
        final = t.price_after_5d or t.price_after_3d or t.price_after_1d
        ret_str = "\u5f85\u5b9a"
        if final and t.entry_price and t.entry_price > 0:
            ret = (final - t.entry_price) / t.entry_price * 100
            if t.direction == "sell":
                ret = -ret
            sign = "+" if ret > 0 else ""
            ret_str = f"{sign}{ret:.1f}%"
        outcome_icon = "\u2705" if t.outcome in ("win", "partial") else "\u274c" if t.outcome == "loss" else "\u23f3"
        lines.append(f"  {outcome_icon} {t.ticker} {t.name} | {t.direction} {t.entry_price} -> {ret_str} | {t.outcome or 'pending'}")

    content_text = "\n".join(lines)

    app_logger.info(f"[\u5468\u62a5] {market} \u5468\u62a5\u751f\u6210\u5b8c\u6bd5\uff0c{total} \u6761\u63a8\u8350")

    return {
        "market": market,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "content": content_text,
        "stats": {
            "total": total, "wins": wins, "losses": losses, "pending": pending,
            "win_rate": win_rate, "avg_return": avg_return,
        },
    }
