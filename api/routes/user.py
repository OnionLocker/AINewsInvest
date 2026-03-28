"""User routes - watchlist, stock query, market overview, config."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from api.deps import (
    get_current_user, WatchlistAddRequest, StockQueryRequest,
)
from core.user import User
from core.database import Database

router = APIRouter(prefix="/api", tags=["user"])


def _get_user_db(user: User) -> Database:
    user.data_dir.mkdir(parents=True, exist_ok=True)
    return Database(user.db_path)


@router.get("/market-overview")
async def market_overview(user: User = Depends(get_current_user)):
    from core.data_source import get_market_indices
    indices = await run_in_threadpool(get_market_indices)
    return indices


@router.post("/stock-query")
async def stock_query(req: StockQueryRequest, user: User = Depends(get_current_user)):
    from core.data_source import get_quote
    result = await run_in_threadpool(get_quote, req.ticker, req.market)
    if not result:
        raise HTTPException(status_code=404, detail="??????")
    return result


@router.post("/watchlist")
async def add_watchlist(req: WatchlistAddRequest, user: User = Depends(get_current_user)):
    db = _get_user_db(user)
    try:
        item_id = db.add_watchlist(
            req.ticker, req.name, req.market,
            rec_item_id=req.recommendation_item_id, note=req.note,
        )
        return {"id": item_id, "msg": "added"}
    finally:
        db.close()


@router.get("/watchlist")
async def list_watchlist(user: User = Depends(get_current_user)):
    db = _get_user_db(user)
    try:
        items = db.list_watchlist()
        return items
    finally:
        db.close()


@router.delete("/watchlist/{item_id}")
async def remove_watchlist(item_id: int, user: User = Depends(get_current_user)):
    db = _get_user_db(user)
    try:
        db.remove_watchlist(item_id)
        return {"msg": "removed"}
    finally:
        db.close()


@router.get("/watchlist/quotes")
async def watchlist_quotes(user: User = Depends(get_current_user)):
    from core.data_source import get_quotes_batch
    db = _get_user_db(user)
    try:
        items = db.list_watchlist()
    finally:
        db.close()
    if not items:
        return []
    batch = [{"ticker": i["ticker"], "market": i["market"], "name": i["name"]} for i in items]
    quotes = await run_in_threadpool(get_quotes_batch, batch)
    for q, item in zip(quotes, items):
        q["watchlist_id"] = item["id"]
    return quotes


@router.get("/performance/summary")
async def performance_summary(
    market: str = "all", user: User = Depends(get_current_user),
):
    from core.database import Database as SysDB
    from core.user import SYSTEM_DB_PATH
    db = SysDB(SYSTEM_DB_PATH)
    try:
        summary = db.get_win_rate_summary(market=market if market != "all" else None)
        return summary
    finally:
        db.close()
