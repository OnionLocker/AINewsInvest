"""Recommendation routes -- today, history, screen, with market-scoped endpoints."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from api.deps import ScreenRequest, get_current_user
from core.user import User, SYSTEM_DB_PATH
from core.database import Database

router = APIRouter(prefix="/api", tags=["recommendations"])


def _get_user_db(user: User) -> Database:
    user.data_dir.mkdir(parents=True, exist_ok=True)
    return Database(user.db_path)


def _tz_for_market(market: str) -> str:
    return "Asia/Hong_Kong" if market == "hk_stock" else "America/New_York"


def _ref_date_for_market(market: str) -> str:
    from zoneinfo import ZoneInfo
    from datetime import datetime
    return datetime.now(ZoneInfo(_tz_for_market(market))).strftime("%Y%m%d")


@lru_cache(maxsize=1)
def _stock_pool_name_map() -> dict[tuple[str, str], str]:
    path = Path(__file__).resolve().parents[2] / "data" / "stock_pool.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    out: dict[tuple[str, str], str] = {}
    for row in raw:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker", "")).strip()
        market = str(row.get("market", "")).strip()
        name = str(row.get("name", "")).strip()
        if ticker and market and name:
            out[(ticker, market)] = name
    return out


def _normalize_item_names(items: list[dict]) -> list[dict]:
    name_map = _stock_pool_name_map()
    for item in items:
        ticker = str(item.get("ticker", "")).strip()
        market = str(item.get("market", "")).strip()
        clean_name = name_map.get((ticker, market))
        if clean_name:
            item["name"] = clean_name
    return items




# ---- Legacy (backward compat) ----

@router.get("/recommendations/today")
async def today_recommendations(user: User = Depends(get_current_user)):
    def _work():
        ref_date = _ref_date_for_market("us_stock")
        db = Database(SYSTEM_DB_PATH)
        try:
            run_info, items = db.get_published_recommendations(ref_date)
            if not run_info:
                last_run, last_items = db.get_latest_published()
                if last_run:
                    _normalize_item_names(last_items)
                    return {
                        "run": last_run, "items": last_items,
                        "display_message": f"\u663e\u793a\u6700\u8fd1\u4e00\u6b21\u63a8\u8350 ({last_run.get('ref_date', '?')})",
                    }
                return {"run": None, "items": [], "display_message": "\u6682\u65e0\u63a8\u8350\u6570\u636e"}
            _normalize_item_names(items)
            return {"run": run_info, "items": items}
        finally:
            db.close()
    return await run_in_threadpool(_work)


@router.get("/recommendations/history")
async def recommendation_history(
    limit: int = 20, user: User = Depends(get_current_user),
):
    db = Database(SYSTEM_DB_PATH)
    try:
        runs = db.list_published_runs(limit=limit)
        if runs.empty:
            return []
        return [
            {
                "id": int(row["id"]),
                "ref_date": row["ref_date"],
                "market": row.get("market", "us_stock"),
                "result_count": int(row["result_count"]),
                "published_count": int(row.get("published_count", row["result_count"])),
                "run_status": row.get("run_status", "published"),
                "created_at": row.get("created_at"),
                "published_at": row.get("published_at"),
            }
            for _, row in runs.iterrows()
        ]
    finally:
        db.close()


@router.get("/recommendations/{ref_date}")
async def recommendations_by_date(
    ref_date: str, user: User = Depends(get_current_user),
):
    db = Database(SYSTEM_DB_PATH)
    try:
        run_info, items = db.get_published_recommendations(ref_date)
        if not run_info:
            raise HTTPException(404, f"\u8be5\u65e5\u671f ({ref_date}) \u6682\u65e0\u63a8\u8350")
        _normalize_item_names(items)
        return {"run": run_info, "items": items}
    finally:
        db.close()


# ---- Market-scoped endpoints ----

@router.get("/recommendations/{market}/today")
async def market_today_recommendations(
    market: str, user: User = Depends(get_current_user),
):
    if market not in ("us", "hk"):
        raise HTTPException(400, "market \u53c2\u6570\u5fc5\u987b\u4e3a us \u6216 hk")
    mkt = f"{market}_stock"

    def _work():
        ref_date = _ref_date_for_market(mkt)
        db = Database(SYSTEM_DB_PATH)
        try:
            run_info, items = db.get_published_recommendations(ref_date, market=mkt)

            # Case A: today's run has not been executed yet -> show last published
            if not run_info:
                last_run, last_items = db.get_latest_published(market=mkt)
                if last_run:
                    _normalize_item_names(last_items)
                    return {
                        "run": last_run,
                        "items": last_items,
                        "empty_state": "pipeline_not_run_today",
                        "display_message": (
                            f"\u4eca\u65e5\u7ba1\u7ebf\u5c1a\u672a\u8fd0\u884c\uff0c"
                            f"\u663e\u793a\u6700\u8fd1\u4e00\u6b21\u63a8\u8350 "
                            f"({last_run.get('ref_date', '?')})"
                        ),
                    }
                return {
                    "run": None,
                    "items": [],
                    "empty_state": "no_data",
                    "display_message": "\u6682\u65e0\u63a8\u8350\u6570\u636e",
                }

            # Case B: today's run executed but returned no items
            if not items:
                return {
                    "run": run_info,
                    "items": [],
                    "empty_state": "no_signals_today",
                    "display_message": (
                        "\u4eca\u65e5\u7ba1\u7ebf\u5df2\u8fd0\u884c\uff0c"
                        "\u672a\u53d1\u73b0\u7b26\u5408\u6761\u4ef6\u7684\u6807\u7684"
                    ),
                }

            _normalize_item_names(items)

            user_db = _get_user_db(user)
            try:
                watchlist = user_db.list_watchlist()
            finally:
                user_db.close()

            watch_tickers = {(w["ticker"], w["market"]) for w in watchlist}
            for item in items:
                item["in_watchlist"] = (item["ticker"], item["market"]) in watch_tickers

            # v11: Attach today's macro-event advisory (US only; HK calendar
            # is not modeled yet). Computed on demand from the in-memory
            # schedule so we do not need to persist it per-run.
            macro_advisory = _compute_macro_advisory(mkt, ref_date)

            return {
                "run": run_info,
                "items": items,
                "empty_state": "ok",
                "macro_advisory": macro_advisory,
            }
        finally:
            db.close()

    return await run_in_threadpool(_work)


def _compute_macro_advisory(market: str, ref_date: str) -> dict:
    """Return today/tomorrow macro-event list + next upcoming for the UI."""
    if market != "us_stock":
        return {"market": market, "today": [], "tomorrow": [], "upcoming": None}
    try:
        from core.macro_calendar import (
            get_macro_events_on, get_macro_events_tomorrow, get_next_macro_event,
        )
        today = get_macro_events_on(ref_date)
        tomorrow = get_macro_events_tomorrow(ref_date)
        upcoming = get_next_macro_event(ref_date, horizon_days=10)
        return {
            "market": market,
            "today": today,
            "tomorrow": tomorrow,
            "upcoming": upcoming,
        }
    except Exception:
        return {"market": market, "today": [], "tomorrow": [], "upcoming": None}


@router.get("/recommendations/{market}/history")
async def market_recommendation_history(
    market: str, limit: int = 20, user: User = Depends(get_current_user),
):
    if market not in ("us", "hk"):
        raise HTTPException(400, "market \u53c2\u6570\u5fc5\u987b\u4e3a us \u6216 hk")
    mkt = f"{market}_stock"

    db = Database(SYSTEM_DB_PATH)
    try:
        runs = db.list_published_runs(limit=limit, market=mkt)
        if runs.empty:
            return []
        return [
            {
                "id": int(row["id"]),
                "ref_date": row["ref_date"],
                "market": row.get("market", mkt),
                "result_count": int(row["result_count"]),
                "published_count": int(row.get("published_count", row["result_count"])),
                "run_status": row.get("run_status", "published"),
                "created_at": row.get("created_at"),
                "published_at": row.get("published_at"),
            }
            for _, row in runs.iterrows()
        ]
    finally:
        db.close()


@router.get("/recommendations/{market}/{ref_date}")
async def market_recommendations_by_date(
    market: str, ref_date: str, user: User = Depends(get_current_user),
):
    if market not in ("us", "hk"):
        raise HTTPException(400, "market \u53c2\u6570\u5fc5\u987b\u4e3a us \u6216 hk")
    mkt = f"{market}_stock"

    db = Database(SYSTEM_DB_PATH)
    try:
        run_info, items = db.get_published_recommendations(ref_date, market=mkt)
        if not run_info:
            raise HTTPException(404, f"\u8be5\u65e5\u671f ({ref_date}) \u6682\u65e0{mkt}\u63a8\u8350")
        _normalize_item_names(items)
        return {"run": run_info, "items": items}
    finally:
        db.close()


# ---- Screening (unchanged) ----

@router.post("/screen")
async def run_screening(req: ScreenRequest, user: User = Depends(get_current_user)):
    def _work():
        from pipeline.screening import run_screening as _run
        results = _run(market=req.market, top_n=req.top_n)
        ref_date = req.ref_date
        if not ref_date:
            from datetime import datetime
            ref_date = datetime.now().strftime("%Y%m%d")

        db = _get_user_db(user)
        try:
            run_id = db.save_screening_run(req.market, ref_date, req.top_n, results)
        finally:
            db.close()

        return {
            "run_id": run_id, "ref_date": ref_date,
            "market": req.market, "top_n": req.top_n,
            "result_count": len(results), "results": results,
        }

    return await run_in_threadpool(_work)


@router.get("/screen/latest")
async def latest_screening(
    market: str = "us_stock", user: User = Depends(get_current_user),
):
    db = _get_user_db(user)
    try:
        run_info, results = db.get_latest_screening(market)
    finally:
        db.close()
    if run_info is None:
        return {"run": None, "results": []}
    return {"run": run_info, "results": results.to_dict("records") if not results.empty else []}


@router.get("/screen/history")
async def screening_history(
    limit: int = 20, user: User = Depends(get_current_user),
):
    db = _get_user_db(user)
    try:
        runs = db.get_screening_runs(limit=limit)
    finally:
        db.close()
    if runs.empty:
        return []
    return [
        {"id": int(r["id"]), "market": r.get("market", ""), "ref_date": r["ref_date"],
         "top_n": int(r["top_n"]), "result_count": int(r["result_count"]),
         "created_at": r["created_at"]}
        for _, r in runs.iterrows()
    ]
