# -*- coding: utf-8 -*-
"""NewsSkill: structured LLM call for news sentiment analysis.

Wraps the news_sentiment_agent skill with Pydantic models for
type-safe input/output and deterministic post-processing.
"""
from __future__ import annotations

import json
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from analysis.llm_client import agent_analyze
from analysis.news_fetcher import fetch_news, fetch_market_news


class NewsCatalyst(BaseModel):
    type: str = ""
    description: str = ""
    magnitude: str = "minor"
    impact: str = "neutral"
    confidence: float = 0.5
    time_horizon: str = "short_term"


class NewsRisk(BaseModel):
    type: str = ""
    description: str = ""
    severity: str = "minor"
    probability: str = "possible"


class NewsSkillStockOutput(BaseModel):
    ticker: str
    news_score: int = 50
    sentiment: str = "neutral"
    action: str = "hold"
    analysis: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    risk_note: str = ""
    sector_bonus: int = 0
    themes: list[str] = Field(default_factory=list)
    catalysts: list[NewsCatalyst] = Field(default_factory=list)
    risks: list[NewsRisk] = Field(default_factory=list)
    event_flags: dict[str, bool] = Field(default_factory=dict)
    sector_sentiment: str = "neutral"


class NewsSkillResponse(BaseModel):
    agent_version: str = "news-edge-v3.0"
    market_regime: str = "neutral"
    market_summary: str = ""
    hot_sectors: list[str] = Field(default_factory=list)
    results: list[NewsSkillStockOutput] = Field(default_factory=list)


def build_news_skill_input(
    candidates: list[dict],
    market: str,
) -> dict[str, Any]:
    """Build structured payload for the NewsSkill LLM call."""
    items = []
    for c in candidates:
        ticker = c["ticker"]
        mkt = c.get("market", market)
        news_items = fetch_news(ticker, mkt, limit=12)
        news_summaries = []
        for n in news_items[:12]:
            entry: dict[str, Any] = {
                "title": n.get("title", ""),
                "publisher": n.get("publisher", ""),
                "credibility": n.get("credibility", 0.5),
                "source_tier": n.get("source_tier", "aggregator"),
            }
            summary = n.get("summary", "")
            if summary:
                entry["summary"] = summary[:200]
            pre_sent = n.get("pre_sentiment")
            if pre_sent is not None:
                entry["pre_sentiment"] = pre_sent
            news_summaries.append(entry)

        items.append({
            "ticker": ticker,
            "name": c.get("name", ticker),
            "market": mkt,
            "price": float(c.get("price") or 0),
            "change_pct": float(c.get("change_pct") or 0),
            "market_cap": float(c.get("market_cap") or 0),
            "pe_ttm": c.get("pe_ttm"),
            "ma_bullish_align": c.get("signals", {}).get("ma_bullish_align", False),
            "volume_expansion": c.get("signals", {}).get("volume_expansion", False),
            "weekly_trend": c.get("weekly_trend", "neutral"),
            "news": news_summaries,
        })

    market_context = fetch_market_news(limit=10)
    market_headlines = [
        {"title": m.get("title", ""), "publisher": m.get("publisher", ""),
         "credibility": m.get("credibility", 0.5)}
        for m in market_context[:10]
    ]

    return {
        "market": market,
        "candidate_count": len(items),
        "market_context": market_headlines,
        "candidates": items,
    }


def call_news_skill(
    payload: dict[str, Any],
    max_retries: int = 1,
) -> NewsSkillResponse:
    """Invoke LLM with news_sentiment_agent skill and parse into typed response."""
    response = agent_analyze("news_sentiment_agent", payload, max_retries=max_retries)

    if response is None:
        logger.warning("NewsSkill: LLM returned None")
        return NewsSkillResponse()

    try:
        parsed = NewsSkillResponse.model_validate(response)
        logger.info(f"NewsSkill: {len(parsed.results)} results, regime={parsed.market_regime}")
        return parsed
    except Exception as e:
        logger.warning(f"NewsSkill: parse error: {e}, falling back to legacy format")
        results = []
        for r in response.get("results", []):
            try:
                results.append(NewsSkillStockOutput.model_validate(r))
            except Exception:
                pass
        return NewsSkillResponse(
            market_regime=response.get("market_regime", "neutral"),
            results=results,
        )


def skill_output_to_legacy(so: NewsSkillStockOutput) -> dict[str, Any]:
    """Convert typed NewsSkillStockOutput to legacy dict format for downstream."""
    return {
        "ticker": so.ticker,
        "news_score": so.news_score,
        "sentiment": so.sentiment,
        "action": so.action,
        "analysis": so.analysis,
        "risk_flags": so.risk_flags,
        "risk_note": so.risk_note,
        "sector_bonus": so.sector_bonus,
        "themes": so.themes,
        "_skill_output": so.model_dump(),
    }
