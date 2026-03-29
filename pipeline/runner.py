"""Daily pipeline runner - 6-layer architecture.

Layer 1: Quantitative screening (screening.run_screening)
Layer 2: Technical data enrichment (screening.build_enriched_candidates)
Layer 3-6: LLM Agent pipeline (agents.run_agent_pipeline)

Each call processes exactly ONE market (us_stock or hk_stock).
The ref_date is computed from the market's local timezone.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from loguru import logger
from zoneinfo import ZoneInfo

import yfinance as yf

from core.database import Database
from core.user import SYSTEM_DB_PATH
from pipeline.config import get_config
from pipeline.screening import run_screening, batch_fetch_klines, build_enriched_candidates

_MARKET_TZ = {
    "us_stock": "America/New_York",
    "hk_stock": "Asia/Hong_Kong",
}


def _check_market_regime(market: str) -> dict:
    """Check market-level conditions. Returns regime dict with level and flags.

    Levels: normal, cautious, bearish, crisis
    """
    try:
        if market == "us_stock":
            spy = yf.Ticker("SPY").history(period="6d")
            vix_data = yf.Ticker("^VIX").history(period="1d")
        else:
            spy = yf.Ticker("^HSI").history(period="6d")
            vix_data = None

        if spy.empty or len(spy) < 2:
            return {"level": "normal", "flags": [], "details": {}}

        last_close = float(spy["Close"].iloc[-1])
        prev_close = float(spy["Close"].iloc[-2])
        daily_change = (last_close - prev_close) / prev_close * 100

        five_day_change = 0.0
        if len(spy) >= 5:
            five_ago = float(spy["Close"].iloc[-5])
            five_day_change = (last_close - five_ago) / five_ago * 100

        vix_val = 0.0
        if vix_data is not None and not vix_data.empty:
            vix_val = float(vix_data["Close"].iloc[-1])

        flags = []
        level = "normal"

        if daily_change < -3.0:
            flags.append("single_day_crash")
            level = "crisis"
        elif daily_change < -2.0:
            flags.append("large_daily_drop")
            level = max(level, "bearish", key=["normal", "cautious", "bearish", "crisis"].index)

        if five_day_change < -5.0:
            flags.append("sustained_decline")
            level = "crisis"
        elif five_day_change < -3.0:
            flags.append("weekly_weakness")
            level = max(level, "bearish", key=["normal", "cautious", "bearish", "crisis"].index)

        if vix_val > 35:
            flags.append("extreme_vix")
            level = max(level, "bearish", key=["normal", "cautious", "bearish", "crisis"].index)
        elif vix_val > 25:
            flags.append("elevated_vix")
            level = max(level, "cautious", key=["normal", "cautious", "bearish", "crisis"].index)

        details = {
            "daily_change_pct": round(daily_change, 2),
            "five_day_change_pct": round(five_day_change, 2),
            "vix": round(vix_val, 1) if vix_val > 0 else None,
        }

        logger.info(
            f"Market regime {market}: {level} | "
            f"1d={daily_change:+.1f}% 5d={five_day_change:+.1f}% VIX={vix_val:.0f} "
            f"flags={flags}"
        )
        return {"level": level, "flags": flags, "details": details}

    except Exception as e:
        logger.warning(f"Market regime check failed: {e}")
        return {"level": "normal", "flags": ["check_failed"], "details": {}}


def _ref_date_for_market(market: str) -> str:
    tz_name = _MARKET_TZ.get(market, "America/New_York")
    return datetime.now(ZoneInfo(tz_name)).strftime("%Y%m%d")


def _progress(
    cb: Callable[[dict], None] | None,
    pct: float,
    msg: str,
) -> None:
    if cb:
        try:
            cb({"progress": pct, "message": msg})
        except Exception as e:
            logger.warning(f"progress_cb error: {e}")


def run_daily_pipeline(
    market: str = "us_stock",
    force: bool = False,
    trigger_source: str = "system_auto",
    trigger_note: str = "",
    progress_cb: Callable[[dict], None] | None = None,
) -> dict:
    """Execute the full 6-layer daily pipeline for a single market.

    1. Screen candidates (Layer 1)
    2. Enrich with technical data (Layer 2)
    3. Run Agent pipeline (Layers 3-6)
    4. Save and publish recommendations
    """
    cfg = get_config()
    ref_date = _ref_date_for_market(market)
    st = cfg.short_term

    _progress(progress_cb, 2.0, "Evaluating pending win-rate records")
    try:
        from pipeline.evaluator import evaluate_pending_records
        eval_result = evaluate_pending_records()
        logger.info(f"Pre-run evaluation: {eval_result}")
    except Exception as e:
        logger.warning(f"Pre-run evaluation failed: {e}")

    _progress(progress_cb, 4.0, "Checking market regime")
    regime = _check_market_regime(market)
    logger.info(f"Market regime: {regime}")

    db = Database(SYSTEM_DB_PATH)
    try:
        if not force:
            existing, items = db.get_daily_recommendations(ref_date, market=market)
            if existing:
                _progress(progress_cb, 100.0, f"Already ran today for {market}")
                return {
                    "ref_date": ref_date,
                    "market": market,
                    "skipped": True,
                    "reason": "daily run exists",
                    "published_count": len(items),
                }

        # Phase 1: Layer 1 - Screening
        _progress(progress_cb, 5.0, f"Layer 1: Screening {market}")
        screened = run_screening(market=market, top_n=cfg.max_candidates)
        _progress(progress_cb, 15.0, f"Layer 1 screened {market}: {len(screened)} candidates")

        screened.sort(key=lambda x: x["score"], reverse=True)
        candidates = screened[:cfg.max_candidates]
        if not candidates:
            _progress(progress_cb, 100.0, "No candidates after screening")
            return {
                "ref_date": ref_date,
                "market": market,
                "candidate_count": 0,
                "published_count": 0,
                "items": [],
            }

        # Phase 2: Layer 2 - Technical enrichment
        _progress(progress_cb, 20.0, f"Layer 2: Enriching {len(candidates)} candidates")
        kline_map = batch_fetch_klines(candidates, days=80)
        enriched = build_enriched_candidates(candidates, kline_map)

        if not enriched:
            _progress(progress_cb, 100.0, "No candidates after enrichment")
            return {
                "ref_date": ref_date,
                "market": market,
                "candidate_count": len(candidates),
                "published_count": 0,
                "items": [],
            }

        # Phase 3: Layers 3-6 - Agent pipeline
        max_recs = cfg.max_recommendations
        if regime["level"] == "crisis":
            max_recs = 0
            logger.warning(f"Market CRISIS mode - skipping all long recs for {market}")
        elif regime["level"] == "bearish":
            max_recs = max(3, max_recs // 2)
            logger.info(f"Market bearish - reducing max_recs to {max_recs}")

        if regime["level"] == "crisis" and market == "hk_stock":
            _progress(progress_cb, 100.0, "Market crisis - no recommendations")
            return {
                "ref_date": ref_date,
                "market": market,
                "candidate_count": len(candidates),
                "published_count": 0,
                "regime": regime,
                "items": [],
            }

        _progress(progress_cb, 30.0, f"Layers 3-6: Agent pipeline on {len(enriched)} candidates")
        from pipeline.agents import run_agent_pipeline
        analyzed = run_agent_pipeline(
            enriched,
            market=market,
            strategy_type="short",
            progress_cb=progress_cb,
            regime=regime,
        )

        if not analyzed:
            _progress(progress_cb, 100.0, "No recommendations from agent pipeline")
            return {
                "ref_date": ref_date,
                "market": market,
                "candidate_count": len(candidates),
                "published_count": 0,
                "regime": regime,
                "items": [],
            }

        top_items = analyzed[:max_recs]

        # Phase 4: Save and publish
        _progress(progress_cb, 80.0, f"Saving {len(top_items)} recommendations for {market}")

        run_id = db.save_daily_recommendation_run(
            ref_date,
            market,
            top_items,
            strategy="dual",
            source_count=len(screened),
            candidate_count=len(candidates),
            trigger_source=trigger_source,
            trigger_note=trigger_note,
        )

        admin_run, saved_items = db.get_daily_recommendations(ref_date, market=market)
        if not admin_run:
            admin_run = {
                "market": market,
                "strategy": "dual",
                "trigger_source": trigger_source,
                "trigger_note": trigger_note,
            }
        pub_id = db.publish_recommendations(ref_date, market, admin_run, saved_items)

        for it in saved_items:
            try:
                db.save_win_rate_record({
                    "run_date": ref_date,
                    "ticker": it["ticker"],
                    "name": it["name"],
                    "market": it["market"],
                    "strategy": it.get("strategy", "short_term"),
                    "direction": it.get("direction", "buy"),
                    "entry_price": float(it.get("entry_price") or 0),
                    "stop_loss": float(it.get("stop_loss") or 0),
                    "take_profit": float(it.get("take_profit") or 0),
                    "holding_days": int(it.get("holding_days") or st.default_holding_days),
                })
            except Exception as e:
                logger.warning(f"win_rate record {it.get('ticker')}: {e}")

        _progress(progress_cb, 95.0, "Computing market sentiment cache")
        try:
            _cache_market_sentiment(db, market)
        except Exception as e:
            logger.warning(f"Market sentiment cache failed: {e}")

        _progress(progress_cb, 100.0, f"Done - {market}")
        return {
            "ref_date": ref_date,
            "market": market,
            "run_id": run_id,
            "published_run_id": pub_id,
            "candidate_count": len(candidates),
            "published_count": len(saved_items),
            "regime": regime,
            "items": [dict(x) for x in saved_items],
        }
    finally:
        db.close()


def _cache_market_sentiment(db: Database, market: str):
    """Compute full market sentiment and store in DB for instant API reads."""
    from analysis.news_fetcher import fetch_market_news, analyze_sentiment
    from core.data_source import _get_market_breadth

    mkt_short = "us" if market == "us_stock" else "hk"

    news = fetch_market_news(market=market, limit=25)
    sentiment = analyze_sentiment(news)
    breadth = _get_market_breadth(market)

    top_headlines = []
    for n in news[:6]:
        top_headlines.append({
            "title": n.get("title", ""),
            "publisher": n.get("publisher", ""),
            "link": n.get("link", ""),
            "credibility": n.get("credibility", 0.5),
        })

    s = sentiment.get("score", 0.0)
    adv = breadth.get("advance_pct", 50.0)
    raw = (s + 1) / 2 * 50 + adv / 100 * 50
    raw = max(0, min(100, raw))
    if raw >= 75:
        label = "\u6781\u5ea6\u8d2a\u5a6a"
    elif raw >= 60:
        label = "\u8d2a\u5a6a"
    elif raw >= 40:
        label = "\u4e2d\u6027"
    elif raw >= 25:
        label = "\u6050\u60e7"
    else:
        label = "\u6781\u5ea6\u6050\u60e7"
    fear_greed = {"value": round(raw, 1), "label": label}

    total = breadth.get("total", 0)
    if mkt_short == "us":
        scope_label = f"\u6807\u666e500\u6210\u5206\u80a1({total}\u53ea)"
    else:
        scope_label = f"\u6052\u6307+\u6052\u751f\u79d1\u6280\u6210\u5206\u80a1({total}\u53ea)"

    result = {
        "market": market,
        "sentiment": sentiment,
        "breadth": breadth,
        "breadth_scope": scope_label,
        "fear_greed": fear_greed,
        "headlines": top_headlines,
    }

    db.save_market_sentiment(market, result)
    logger.info(f"Market sentiment cached for {market}: fg={fear_greed['value']}, breadth={total}")
