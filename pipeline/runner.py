from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from loguru import logger
from zoneinfo import ZoneInfo

from analysis.fundamental import analyze as fundamental_analyze
from analysis.news_fetcher import analyze_sentiment, fetch_news
from analysis.technical import analyze as technical_analyze
from core.data_source import get_quote
from core.database import Database
from core.user import SYSTEM_DB_PATH
from pipeline.config import get_config
from pipeline.screening import run_screening


def _ref_date_ny() -> str:
    return datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d")


def _pct_01(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    if hi <= lo:
        return 50.0
    t = (max(lo, min(hi, x)) - lo) / (hi - lo)
    return t * 100.0


def _news_to_score(sentiment: dict) -> int:
    return int(round(_pct_01(float(sentiment.get("score", 0.0)), -1.0, 1.0)))


def _tech_to_score(tech: dict | None) -> int:
    if not tech:
        return 50
    return int(round(_pct_01(float(tech.get("composite_score", 0.0)), -1.0, 1.0)))


def _fund_to_score(fund: dict | None) -> int:
    if not fund:
        return 50
    q = fund.get("quality_score")
    if q is None:
        return 50
    return int(max(0, min(100, round(float(q)))))


def _levels_from_tech(
    tech: dict | None,
    price: float,
    st,
) -> tuple[float, float, float, float]:
    if tech and tech.get("levels"):
        lv = tech["levels"]
        e = float(lv.get("entry") or price)
        sl = float(lv.get("stop_loss") or price * st.default_stop_loss_pct)
        tp = float(lv.get("take_profit_1") or price * st.default_take_profit_pct)
        tp2 = float(lv.get("take_profit_2") or price * st.take_profit_2_pct)
        return e, sl, tp, tp2
    e = round(price, 4)
    return (
        e,
        round(price * st.default_stop_loss_pct, 4),
        round(price * st.default_take_profit_pct, 4),
        round(price * st.take_profit_2_pct, 4),
    )


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


# ---------------------------------------------------------------------------
# Rule-based analysis (fallback when LLM Agent is disabled)
# ---------------------------------------------------------------------------

def _run_rule_based_analysis(
    candidates: list[dict],
    progress_cb: Callable[[dict], None] | None = None,
) -> list[dict]:
    """Per-stock analysis using rule-based scoring (no LLM)."""
    cfg = get_config()
    syn = cfg.synthesis
    st = cfg.short_term

    analyzed: list[dict] = []
    n_c = len(candidates)
    base = 35.0
    span = 40.0

    for idx, row in enumerate(candidates):
        t, m = row["ticker"], row["market"]
        name = row.get("name", t)
        tech = None
        fund = None
        try:
            tech = technical_analyze(t, m)
        except Exception as e:
            logger.warning(f"Technical {m}:{t}: {e}")
        try:
            fund = fundamental_analyze(t, m)
        except Exception as e:
            logger.warning(f"Fundamental {m}:{t}: {e}")
        news_items = fetch_news(t, m, limit=10)
        sentiment = analyze_sentiment(news_items)

        price = float(tech["price"]) if tech and tech.get("price") else float(row.get("price") or 0)
        if price <= 0:
            q = get_quote(t, m)
            if q and q.get("price"):
                price = float(q["price"])
        if price <= 0:
            logger.warning(f"Skip {m}:{t} - no price")
            continue

        ts = _tech_to_score(tech)
        ns = _news_to_score(sentiment)
        fs = _fund_to_score(fund)
        combined = (
            syn.tech_weight * ts
            + syn.news_weight * ns
            + syn.fundamental_weight * fs
        )
        conf = int(max(0, min(100, round(combined))))

        entry, stop_loss, take_profit, take_profit_2 = _levels_from_tech(tech, price, st)
        chg = float(row.get("change_pct") or 0)

        tech_reason = ""
        if tech:
            tech_reason = f"{tech.get('trend', '')} / {tech.get('signal', '')} (norm {tech.get('composite_score')})"
        news_reason = sentiment.get("summary", "")
        fund_reason = (fund or {}).get("fundamental_summary", "")[:500]

        analyzed.append({
            "ticker": t,
            "name": name,
            "market": m,
            "strategy": "short_term",
            "direction": "buy",
            "score": round(combined, 2),
            "confidence": conf,
            "tech_score": ts,
            "news_score": ns,
            "fundamental_score": fs,
            "combined_score": conf,
            "entry_price": entry,
            "entry_2": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "take_profit_2": take_profit_2,
            "holding_days": st.default_holding_days,
            "tech_reason": tech_reason,
            "news_reason": news_reason,
            "fundamental_reason": fund_reason,
            "llm_reason": "",
            "recommendation_reason": news_reason or tech_reason,
            "valuation_summary": (fund or {}).get("fundamental_summary", "")[:800],
            "quality_score": (fund or {}).get("quality_score"),
            "safety_margin": None,
            "risk_flags": list((fund or {}).get("risk_flags") or []),
            "price": price,
            "change_pct": chg,
        })
        p = base + span * (idx + 1) / max(n_c, 1)
        _progress(progress_cb, min(p, 75.0), f"Analyzed {t}")

    return analyzed


# ---------------------------------------------------------------------------
# Main daily pipeline
# ---------------------------------------------------------------------------

def run_daily_pipeline(
    market: str = "all",
    force: bool = False,
    trigger_source: str = "system_auto",
    trigger_note: str = "",
    progress_cb: Callable[[dict], None] | None = None,
) -> dict:
    cfg = get_config()
    ref_date = _ref_date_ny()
    syn = cfg.synthesis
    st = cfg.short_term

    db = Database(SYSTEM_DB_PATH)
    try:
        if not force:
            existing, items = db.get_daily_recommendations(ref_date)
            if existing:
                _progress(progress_cb, 100.0, "Already ran today")
                return {
                    "ref_date": ref_date,
                    "skipped": True,
                    "reason": "daily run exists",
                    "published_count": len(items),
                }

        # Phase 1: Screening
        markets = ["us_stock", "hk_stock"] if market == "all" else [market]
        screened: list[dict] = []
        n_m = len(markets)
        for i, mkt in enumerate(markets):
            part = run_screening(market=mkt, top_n=cfg.max_candidates)
            screened.extend(part)
            p = 10.0 + 20.0 * (i + 1) / max(n_m, 1)
            _progress(progress_cb, p, f"Screened {mkt}: {len(part)} candidates")

        screened.sort(key=lambda x: x["score"], reverse=True)
        candidates = screened[: cfg.max_candidates]
        if not candidates:
            _progress(progress_cb, 100.0, "No candidates")
            return {
                "ref_date": ref_date,
                "market": market,
                "candidate_count": 0,
                "published_count": 0,
                "items": [],
            }

        # Phase 2: Analysis (Agent or Rule-based)
        use_agent = cfg.agent.enabled and cfg.llm.enabled
        if use_agent:
            logger.info("Using LLM Agent pipeline for analysis")
            from pipeline.agents import run_agent_pipeline
            analyzed = run_agent_pipeline(
                candidates,
                market=market,
                progress_cb=progress_cb,
            )
        else:
            logger.info("Using rule-based pipeline for analysis (Agent disabled)")
            analyzed = _run_rule_based_analysis(candidates, progress_cb=progress_cb)

        if not analyzed:
            _progress(progress_cb, 100.0, "No analyzable candidates")
            return {
                "ref_date": ref_date,
                "market": market,
                "candidate_count": len(candidates),
                "published_count": 0,
                "items": [],
            }

        # Phase 3: Filter and select top items
        if not use_agent:
            analyzed.sort(key=lambda x: x.get("combined_score", x.get("score", 0)), reverse=True)
            min_conf = syn.min_confidence
            quality_th = syn.quality_threshold
            filtered = [
                a for a in analyzed
                if a.get("confidence", 0) >= min_conf
                and (a.get("quality_score") is None or float(a["quality_score"]) >= quality_th)
            ]
            if len(filtered) < len(analyzed):
                logger.info(
                    f"Filtered {len(analyzed) - len(filtered)} below confidence/quality "
                    f"(min_conf={min_conf}, quality>={quality_th})"
                )
            if not filtered:
                filtered = analyzed[: cfg.max_recommendations]
            top_items = filtered[: cfg.max_recommendations]
        else:
            top_items = analyzed

        if not top_items:
            _progress(progress_cb, 100.0, "Nothing to publish after filters")
            return {
                "ref_date": ref_date,
                "market": market,
                "candidate_count": len(candidates),
                "published_count": 0,
                "items": [],
            }

        # Phase 4: Save and publish
        _progress(progress_cb, 78.0, f"Saving {len(top_items)} recommendations")

        run_market = "all" if market == "all" else market
        run_id = db.save_daily_recommendation_run(
            ref_date,
            run_market,
            top_items,
            strategy="dual",
            source_count=len(screened),
            candidate_count=len(candidates),
            trigger_source=trigger_source,
            trigger_note=trigger_note,
        )

        admin_run, saved_items = db.get_daily_recommendations(ref_date)
        if not admin_run:
            admin_run = {
                "market": run_market,
                "strategy": "dual",
                "trigger_source": trigger_source,
                "trigger_note": trigger_note,
            }
        pub_id = db.publish_recommendations(ref_date, admin_run, saved_items)

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

        _progress(progress_cb, 100.0, "Done")
        return {
            "ref_date": ref_date,
            "market": market,
            "run_id": run_id,
            "published_run_id": pub_id,
            "candidate_count": len(candidates),
            "published_count": len(saved_items),
            "items": [dict(x) for x in saved_items],
        }
    finally:
        db.close()
