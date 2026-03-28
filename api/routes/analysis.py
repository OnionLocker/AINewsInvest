"""Deep analysis routes -- single-stock deep analysis with SSE streaming."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from loguru import logger

from api.deps import DeepAnalysisRequest, get_current_user
from core.user import User, SYSTEM_DB_PATH
from core.database import Database

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/deep-analysis")
async def deep_analysis(req: DeepAnalysisRequest, user: User = Depends(get_current_user)):
    if req.market not in ("us_stock", "hk_stock"):
        raise HTTPException(400, "Only us_stock and hk_stock supported")

    db = Database(SYSTEM_DB_PATH)
    try:
        if not req.force:
            cached = db.get_deep_cache(req.ticker, req.market)
            if cached:
                logger.info(f"Deep analysis cache hit {req.market}:{req.ticker}")
                return cached
    finally:
        db.close()

    def _run():
        return _run_deep_analysis(req.ticker, req.market)

    result = await run_in_threadpool(_run)
    db = Database(SYSTEM_DB_PATH)
    try:
        db.save_deep_cache(req.ticker, req.market, result)
    finally:
        db.close()

    logger.info(f"Deep analysis {req.market}:{req.ticker} by {user.username}")
    return result


@router.post("/deep-analysis-stream")
async def deep_analysis_stream(req: DeepAnalysisRequest,
                                user: User = Depends(get_current_user)):
    if req.market not in ("us_stock", "hk_stock"):
        raise HTTPException(400, "Only us_stock and hk_stock supported")

    def generate():
        steps_total = 5

        yield _sse({"step": 1, "total": steps_total, "msg": "Fetching market data..."})
        from analysis.technical import analyze as tech_analyze
        tech = tech_analyze(req.ticker, req.market)

        yield _sse({"step": 2, "total": steps_total, "msg": "Analyzing news..."})
        from analysis.news_fetcher import fetch_news, analyze_sentiment
        news = fetch_news(req.ticker, req.market, limit=10)
        sentiment = analyze_sentiment(news)

        yield _sse({"step": 3, "total": steps_total, "msg": "Fundamental analysis..."})
        fund_data = None
        try:
            from analysis.fundamental import analyze as fund_analyze
            fund_data = fund_analyze(req.ticker, req.market)
        except Exception as e:
            logger.warning(f"Fundamental failed {req.ticker}: {e}")

        yield _sse({"step": 4, "total": steps_total, "msg": "Valuation analysis..."})
        val_data = None
        if fund_data and tech:
            try:
                from analysis.valuation import valuate
                from core.data_source import get_financial_data
                fin = get_financial_data(req.ticker, req.market)
                if fin:
                    val_data = valuate(fin, tech["price"])
            except Exception as e:
                logger.warning(f"Valuation failed {req.ticker}: {e}")

        yield _sse({"step": 5, "total": steps_total, "msg": "AI analysis..."})
        llm_result = None
        from analysis.llm_client import _is_enabled
        if _is_enabled():
            try:
                from analysis.llm_client import llm_analyze_stock
                llm_result = llm_analyze_stock(
                    req.ticker, "", req.market, tech or {}, news,
                    fundamental_data=fund_data, valuation_data=val_data,
                )
            except Exception as e:
                logger.warning(f"LLM failed {req.ticker}: {e}")

        result = {
            "ticker": req.ticker, "market": req.market,
            "technical": tech,
            "news": {"items": news, "sentiment": sentiment},
            "fundamental": fund_data,
            "valuation": val_data,
            "llm_analysis": llm_result,
            "generated_at": datetime.now().isoformat(),
        }

        db = Database(SYSTEM_DB_PATH)
        try:
            db.save_deep_cache(req.ticker, req.market, result)
        finally:
            db.close()

        yield _sse({"step": 5, "total": steps_total, "msg": "Done",
                     "done": True, "result": result})

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _run_deep_analysis(ticker: str, market: str) -> dict:
    from analysis.technical import analyze as tech_analyze
    from analysis.news_fetcher import fetch_news, analyze_sentiment
    from analysis.llm_client import _is_enabled

    tech = tech_analyze(ticker, market)
    news = fetch_news(ticker, market, limit=10)
    sentiment = analyze_sentiment(news)

    fund_data = None
    val_data = None
    try:
        from analysis.fundamental import analyze as fund_analyze
        fund_data = fund_analyze(ticker, market)
    except Exception as e:
        logger.warning(f"Fundamental failed {ticker}: {e}")

    if fund_data and tech:
        try:
            from analysis.valuation import valuate
            from core.data_source import get_financial_data
            fin = get_financial_data(ticker, market)
            if fin:
                val_data = valuate(fin, tech["price"])
        except Exception as e:
            logger.warning(f"Valuation failed {ticker}: {e}")

    llm_result = None
    if _is_enabled():
        try:
            from analysis.llm_client import llm_analyze_stock
            llm_result = llm_analyze_stock(
                ticker, "", market, tech or {}, news,
                fundamental_data=fund_data, valuation_data=val_data,
            )
        except Exception as e:
            logger.warning(f"LLM failed {ticker}: {e}")

    return {
        "ticker": ticker, "market": market,
        "technical": tech,
        "news": {"items": news, "sentiment": sentiment},
        "fundamental": fund_data,
        "valuation": val_data,
        "llm_analysis": llm_result,
        "generated_at": datetime.now().isoformat(),
    }
