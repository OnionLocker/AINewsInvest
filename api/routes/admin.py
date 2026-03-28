"""Admin routes -- user management, recommendation generation, publishing."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from loguru import logger

from api.deps import require_admin, AdminRecommendationRunRequest, get_user_manager
from core.user import User
from core.database import Database
from core.user import SYSTEM_DB_PATH

router = APIRouter(prefix="/api/admin", tags=["admin"])

_running_task: dict[str, Any] = {}


def _update_task_progress(info: dict):
    global _running_task
    _running_task.update(info)


@router.get("/users")
async def list_users(admin: User = Depends(require_admin)):
    um = get_user_manager()
    try:
        return um.list_users()
    finally:
        um.close()


@router.put("/users/{username}/active")
async def set_user_active(username: str, active: bool = True,
                          admin: User = Depends(require_admin)):
    um = get_user_manager()
    try:
        um.set_user_active(username, active)
        return {"msg": "updated"}
    finally:
        um.close()


@router.delete("/users/{username}")
async def delete_user(username: str, admin: User = Depends(require_admin)):
    if username == admin.username:
        raise HTTPException(400, "不能删除自己")
    um = get_user_manager()
    try:
        um.delete_user(username)
        return {"msg": "deleted"}
    finally:
        um.close()


@router.post("/recommendations/run")
async def run_recommendations(
    req: AdminRecommendationRunRequest,
    admin: User = Depends(require_admin),
):
    global _running_task
    if _running_task.get("status") == "running":
        raise HTTPException(409, "已有任务正在运行")

    if req.market not in ("us_stock", "hk_stock"):
        raise HTTPException(400, "market 参数必须为 us_stock 或 hk_stock")

    task_id = str(uuid.uuid4())
    _running_task = {
        "task_id": task_id, "status": "running",
        "market": req.market,
        "progress": 0, "message": "Starting...",
        "started_at": datetime.utcnow().isoformat(),
    }

    def _run():
        try:
            from pipeline.runner import run_daily_pipeline
            result = run_daily_pipeline(
                market=req.market, force=req.force,
                trigger_source="admin_manual",
                trigger_note=req.note or f"by {admin.username}",
                progress_cb=_update_task_progress,
            )
            _running_task.update({
                "status": "done", "progress": 100,
                "message": f"Done: {result.get('published_count', 0)} items",
                "result": result,
            })
        except Exception as e:
            logger.error(f"Recommendation run failed: {e}")
            _running_task.update({
                "status": "failed", "progress": 100,
                "message": str(e),
            })

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"task_id": task_id, "status": "running", "market": req.market}


@router.get("/recommendations/task-status")
async def task_status(admin: User = Depends(require_admin)):
    return _running_task or {"status": "idle"}


@router.post("/recommendations/publish")
async def publish_recommendations(
    ref_date: str | None = None,
    market: str = "us_stock",
    admin: User = Depends(require_admin),
):
    from zoneinfo import ZoneInfo
    if not ref_date:
        tz_name = "Asia/Hong_Kong" if market == "hk_stock" else "America/New_York"
        ref_date = datetime.now(ZoneInfo(tz_name)).strftime("%Y%m%d")

    db = Database(SYSTEM_DB_PATH)
    try:
        run_info, items = db.get_daily_recommendations(ref_date, market=market)
        if not run_info:
            raise HTTPException(404, f"该日期 ({ref_date}) 暂无 {market} 管理端推荐")
        pub_id = db.publish_recommendations(ref_date, market, run_info, items)
        return {"published_run_id": pub_id, "count": len(items), "market": market}
    finally:
        db.close()


@router.get("/recommendations/both-tables")
async def both_tables(ref_date: str | None = None,
                      market: str | None = None,
                      admin: User = Depends(require_admin)):
    from zoneinfo import ZoneInfo
    if not ref_date:
        ref_date = datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d")

    db = Database(SYSTEM_DB_PATH)
    try:
        admin_run, admin_items = db.get_daily_recommendations(ref_date, market=market)
        pub_run, pub_items = db.get_published_recommendations(ref_date, market=market)
        return {
            "admin": {"run": admin_run, "items": admin_items},
            "published": {"run": pub_run, "items": pub_items},
        }
    finally:
        db.close()
