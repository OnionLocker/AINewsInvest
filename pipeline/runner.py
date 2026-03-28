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

from core.database import Database
from core.user import SYSTEM_DB_PATH
from pipeline.config import get_config
from pipeline.screening import run_screening, batch_fetch_klines, build_enriched_candidates

_MARKET_TZ = {
    "us_stock": "America/New_York",
    "hk_stock": "Asia/Hong_Kong",
}


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
        _progress(progress_cb, 30.0, f"Layers 3-6: Agent pipeline on {len(enriched)} candidates")
        from pipeline.agents import run_agent_pipeline
        analyzed = run_agent_pipeline(
            enriched,
            market=market,
            strategy_type="short",
            progress_cb=progress_cb,
        )

        if not analyzed:
            _progress(progress_cb, 100.0, "No recommendations from agent pipeline")
            return {
                "ref_date": ref_date,
                "market": market,
                "candidate_count": len(candidates),
                "published_count": 0,
                "items": [],
            }

        top_items = analyzed[:cfg.max_recommendations]

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

        _progress(progress_cb, 100.0, f"Done - {market}")
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
