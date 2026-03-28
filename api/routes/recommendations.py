"""Recommendation routes -- today, history, screen."""
from __future__ import annotations

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


@router.get("/recommendations/today")
async def today_recommendations(user: User = Depends(get_current_user)):
    def _work():
        from zoneinfo import ZoneInfo
        from datetime import datetime
        ref_date = datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d")

        db = Database(SYSTEM_DB_PATH)
        try:
            run_info, items = db.get_published_recommendations(ref_date)
            if not run_info:
                last_run, last_items = db.get_latest_published()
                if last_run:
                    return {
                        "run": last_run, "items": last_items,
                        "display_message": f"显示最近一次推荐 ({last_run.get('ref_date', '?')})",
                    }
                return {"run": None, "items": [], "display_message": "暂无推荐数据"}

            user_db = _get_user_db(user)
            try:
                watchlist = user_db.list_watchlist()
            finally:
                user_db.close()

            watch_tickers = {(w["ticker"], w["market"]) for w in watchlist}
            for item in items:
                item["in_watchlist"] = (item["ticker"], item["market"]) in watch_tickers

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
                "market": row.get("market", "all"),
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
            raise HTTPException(404, f"该日期 ({ref_date}) 暂无推荐")
        return {"run": run_info, "items": items}
    finally:
        db.close()


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
