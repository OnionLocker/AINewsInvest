"""User routes - watchlist, stock query, market overview, win rate."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from api.deps import (
    get_current_user, WatchlistAddRequest, StockQueryRequest,
)
from core.user import User, SYSTEM_DB_PATH
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
        raise HTTPException(status_code=404, detail="\u672a\u627e\u5230\u8be5\u80a1\u7968\u6570\u636e")
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
    """Read market sentiment with smart cache.

    Cache strategy (US market, ET timezone):
    - Cache is valid until next trading day 07:30 ET.
    - First request after 07:30 ET triggers a live refresh.
    - Within the same trading window, all reads hit cache.
    HK market uses 07:30 HKT as boundary.
    """
    if market not in ("us", "hk"):
        raise HTTPException(400, "\u5e02\u573a\u53c2\u6570\u5fc5\u987b\u4e3a us \u6216 hk")
    mkt = f"{market}_stock"

    def _work():
        db = Database(SYSTEM_DB_PATH)
        try:
            cached = db.get_market_sentiment(mkt)
            if cached and not _sentiment_cache_expired(cached, market):
                cached.pop("_cached_at", None)
                return cached
        finally:
            db.close()

        # Cache missing or expired — compute live and save
        result = _compute_sentiment_live(market, mkt)
        db2 = Database(SYSTEM_DB_PATH)
        try:
            db2.save_market_sentiment(mkt, result)
        finally:
            db2.close()
        return result

    return await run_in_threadpool(_work)


def _sentiment_cache_expired(cached: dict, market: str) -> bool:
    """Check if sentiment cache has crossed the 07:30 local boundary."""
    from datetime import datetime, time as dtime
    try:
        import zoneinfo
    except ImportError:
        from backports import zoneinfo  # type: ignore[no-redef]

    cached_at_str = cached.get("_cached_at")
    if not cached_at_str:
        return True  # no timestamp → treat as expired

    try:
        # SQLite CURRENT_TIMESTAMP is UTC
        cached_utc = datetime.fromisoformat(str(cached_at_str).replace("Z", "+00:00"))
        if cached_utc.tzinfo is None:
            cached_utc = cached_utc.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
    except Exception:
        return True

    tz = zoneinfo.ZoneInfo("America/New_York" if market == "us" else "Asia/Hong_Kong")
    now_local = datetime.now(tz)
    cached_local = cached_utc.astimezone(tz)

    # Boundary: 07:30 local time today
    boundary = now_local.replace(hour=7, minute=30, second=0, microsecond=0)

    # If now is past today's 07:30 and cache is from before 07:30 → expired
    if now_local >= boundary and cached_local < boundary:
        return True

    # If cache is from a previous calendar day (local) → expired
    if cached_local.date() < now_local.date() and now_local >= boundary:
        return True

    return False


def _compute_sentiment_live(market: str, mkt: str) -> dict:
    """Compute market sentiment live (used when cache is missing or expired)."""
    from analysis.news_fetcher import fetch_market_news, analyze_sentiment
    from core.data_source import _get_market_breadth

    news = fetch_market_news(market=mkt, limit=15)
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

    # VIX (US only)
    vix = None
    if market == "us":
        try:
            import yfinance as yf
            vix_data = yf.Ticker("^VIX").history(period="1d")
            if vix_data is not None and not vix_data.empty:
                vix = round(float(vix_data["Close"].iloc[-1]), 1)
        except Exception:
            pass

    total = breadth.get("total", 0)
    if market == "us":
        scope_label = f"\u6807\u666e500\u6210\u5206\u80a1({total}\u53ea)"
    else:
        scope_label = f"\u6052\u6307+\u6052\u751f\u79d1\u6280\u6210\u5206\u80a1({total}\u53ea)"

    return {
        "market": mkt,
        "sentiment": sentiment,
        "breadth": breadth,
        "breadth_scope": scope_label,
        "fear_greed": fear_greed,
        "headlines": top_headlines,
        "vix": vix,
    }


# ---- Win Rate ----

@router.get("/win-rate/summary")
async def win_rate_summary(user: User = Depends(get_current_user)):
    def _work():
        db = Database(SYSTEM_DB_PATH)
        try:
            us_all = db.get_win_rate_summary(market="us_stock")
            us_7d = db.get_win_rate_summary(market="us_stock", days=7)
            us_30d = db.get_win_rate_summary(market="us_stock", days=30)
            hk_all = db.get_win_rate_summary(market="hk_stock")
            hk_7d = db.get_win_rate_summary(market="hk_stock", days=7)
            hk_30d = db.get_win_rate_summary(market="hk_stock", days=30)
            overall = db.get_win_rate_summary()

            # Dimension breakdowns
            us_by_strategy = db.get_win_rate_by_dimension("strategy", market="us_stock")
            us_by_direction = db.get_win_rate_by_dimension("direction", market="us_stock")
            hk_by_strategy = db.get_win_rate_by_dimension("strategy", market="hk_stock")
            hk_by_direction = db.get_win_rate_by_dimension("direction", market="hk_stock")

            return {
                "overall": overall,
                "us_stock": {
                    "all": us_all, "7d": us_7d, "30d": us_30d,
                    "by_strategy": us_by_strategy,
                    "by_direction": us_by_direction,
                },
                "hk_stock": {
                    "all": hk_all, "7d": hk_7d, "30d": hk_30d,
                    "by_strategy": hk_by_strategy,
                    "by_direction": hk_by_direction,
                },
            }
        finally:
            db.close()
    return await run_in_threadpool(_work)


@router.get("/win-rate/details")
async def win_rate_details(
    market: str = "all",
    strategy: str = "",
    direction: str = "",
    outcome: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 50,
    user: User = Depends(get_current_user),
):
    def _work():
        db = Database(SYSTEM_DB_PATH)
        try:
            mkt = market if market != "all" else None
            items = db.get_win_rate_details_filtered(
                market=mkt,
                strategy=strategy or None,
                direction=direction or None,
                outcome=outcome or None,
                start_date=start_date or None,
                end_date=end_date or None,
                limit=limit,
            )
            return items
        finally:
            db.close()
    return await run_in_threadpool(_work)


@router.get("/win-rate/by-date")
async def win_rate_by_date(
    market: str = "all",
    user: User = Depends(get_current_user),
):
    def _work():
        db = Database(SYSTEM_DB_PATH)
        try:
            mkt = market if market != "all" else None
            data = db.get_win_rate_by_date(market=mkt)
            return data
        finally:
            db.close()
    return await run_in_threadpool(_work)


@router.get("/win-rate/trend")
async def win_rate_trend(
    market: str = "all",
    user: User = Depends(get_current_user),
):
    """Return daily aggregated win rate data for trend chart."""
    def _work():
        db = Database(SYSTEM_DB_PATH)
        try:
            mkt = market if market != "all" else None
            data = db.get_win_rate_by_date(market=mkt)
            # Add cumulative return
            cumulative = 0.0
            for row in reversed(data):
                cumulative += row.get("avg_return", 0) * row.get("total", 0)
                row["cumulative_return"] = round(cumulative, 2)
            return data
        finally:
            db.close()
    return await run_in_threadpool(_work)


@router.post("/win-rate/evaluate")
async def trigger_evaluation(user: User = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(403, "\u9700\u8981\u7ba1\u7406\u5458\u6743\u9650")
    from pipeline.evaluator import evaluate_pending_records
    result = await run_in_threadpool(evaluate_pending_records)
    return result



@router.post("/win-rate/cleanup")
async def trigger_cleanup(user: User = Depends(get_current_user)):
    """Admin-only endpoint to trigger win-rate record cleanup based on retention policy."""
    if not user.is_admin:
        raise HTTPException(403, "需要管理员权限")
    
    db = Database(SYSTEM_DB_PATH)
    try:
        result = await run_in_threadpool(db.cleanup_old_records)
        return result
    finally:
        db.close()



@router.get("/performance/summary")
async def performance_summary(
    market: str = "all", user: User = Depends(get_current_user),
):
    db = Database(SYSTEM_DB_PATH)
    try:
        summary = db.get_win_rate_summary(market=market if market != "all" else None)
        return summary
    finally:
        db.close()
