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
        raise HTTPException(status_code=404, detail="未找到该股票数据")
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


@router.get("/market-sentiment/{market}")
async def market_sentiment(market: str, user: User = Depends(get_current_user)):
    """Aggregate market-level sentiment for US or HK."""
    if market not in ("us", "hk"):
        raise HTTPException(400, "市场参数必须为 us 或 hk")
    mkt = f"{market}_stock"

    def _work():
        from analysis.news_fetcher import fetch_market_news, analyze_sentiment
        from core.data_source import _get_market_breadth

        news = fetch_market_news(market=mkt, limit=25)
        sentiment = analyze_sentiment(news)

        breadth = _get_market_breadth(mkt)

        top_headlines = []
        for n in news[:6]:
            top_headlines.append({
                "title": n.get("title", ""),
                "publisher": n.get("publisher", ""),
                "link": n.get("link", ""),
                "credibility": n.get("credibility", 0.5),
            })

        fear_greed = _compute_fear_greed(sentiment, breadth)

        return {
            "market": mkt,
            "sentiment": sentiment,
            "breadth": breadth,
            "fear_greed": fear_greed,
            "headlines": top_headlines,
        }

    return await run_in_threadpool(_work)


def _compute_fear_greed(sentiment: dict, breadth: dict) -> dict:
    """Compute a simplified fear/greed index from sentiment + breadth."""
    s = sentiment.get("score", 0.0)
    adv = breadth.get("advance_pct", 50.0)

    raw = (s + 1) / 2 * 50 + adv / 100 * 50
    raw = max(0, min(100, raw))

    if raw >= 75:
        label = "极度贪婪"
    elif raw >= 60:
        label = "贪婪"
    elif raw >= 40:
        label = "中性"
    elif raw >= 25:
        label = "恐惧"
    else:
        label = "极度恐惧"

    return {"value": round(raw, 1), "label": label}


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
