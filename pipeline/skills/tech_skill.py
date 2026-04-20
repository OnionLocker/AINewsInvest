# -*- coding: utf-8 -*-
"""TechSkill: structured LLM call for technical analysis.

Wraps the technical_agent skill with Pydantic models for
type-safe input/output and deterministic post-processing.
"""
from __future__ import annotations

import json
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from analysis.llm_client import agent_analyze


class TechPattern(BaseModel):
    name: str = ""
    reliability: str = "moderate"
    bullish_or_bearish: str = "neutral"
    description: str = ""


class TrendAssessment(BaseModel):
    primary_trend: str = "neutral"
    trend_strength: str = "moderate"
    trend_stage: str = ""
    notes: str = ""


class VolumeAnalysis(BaseModel):
    signal: str = "neutral"
    notes: str = ""


class TechSkillStockOutput(BaseModel):
    ticker: str
    technical_score: int = 50
    action: str = "hold"
    analysis: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    risk_note: str = ""
    position_note: str = ""
    patterns: list[TechPattern] = Field(default_factory=list)
    trend_assessment: TrendAssessment = Field(default_factory=TrendAssessment)
    volume_analysis: VolumeAnalysis = Field(default_factory=VolumeAnalysis)
    setup_quality: str = "fair"
    risk_factors: list[str] = Field(default_factory=list)


class TechSkillResponse(BaseModel):
    agent_version: str = "technical-v2"
    results: list[TechSkillStockOutput] = Field(default_factory=list)


def build_tech_skill_input(
    candidates: list[dict],
    market: str,
) -> dict[str, Any]:
    """Build structured payload for the TechSkill LLM call."""
    items = []
    for c in candidates:
        item: dict[str, Any] = {
            "ticker": c["ticker"],
            "name": c.get("name", c["ticker"]),
            "market": c.get("market", market),
            "price": float(c.get("price") or 0),
            "change_pct": float(c.get("change_pct") or 0),
        }

        for key in (
            "ma5", "ma10", "ma20", "ma60", "ma20_bias_pct",
            "atr_20d", "volatility_20d", "volatility_class",
            "volume_ratio", "high_20d_volume_ratio",
            "support_levels", "resistance_levels",
            "support_touch_count", "support_hold_strength",
            "weekly_trend",
            "kline_recent_part1", "kline_recent_part2",
        ):
            val = c.get(key)
            if val is not None:
                item[key] = val

        signals = c.get("signals", {})
        if signals:
            item["signals"] = {
                k: v for k, v in signals.items()
                if isinstance(v, bool)
            }

        items.append(item)

    return {
        "market": market,
        "candidate_count": len(items),
        "candidates": items,
    }


def call_tech_skill(
    payload: dict[str, Any],
    max_retries: int = 1,
) -> TechSkillResponse:
    """Invoke LLM with technical_agent skill and parse into typed response."""
    response = agent_analyze("technical_agent", payload, max_retries=max_retries)

    if response is None:
        logger.warning("TechSkill: LLM returned None")
        return TechSkillResponse()

    try:
        parsed = TechSkillResponse.model_validate(response)
        logger.info(f"TechSkill: {len(parsed.results)} results")
        return parsed
    except Exception as e:
        logger.warning(f"TechSkill: bulk validation failed ({e}), trying per-result parse")
        results = []
        raw_results = response.get("results", []) or []
        dropped: list[tuple[str, str]] = []
        for r in raw_results:
            ticker = (r or {}).get("ticker", "?") if isinstance(r, dict) else "?"
            try:
                results.append(TechSkillStockOutput.model_validate(r))
            except Exception as ve:
                # v10.1: log dropped records so ops can see which tickers silently failed
                dropped.append((str(ticker), str(ve)[:160]))
        if dropped:
            logger.warning(
                f"TechSkill: dropped {len(dropped)}/{len(raw_results)} records due to schema mismatch; "
                f"examples: {dropped[:3]}"
            )
        return TechSkillResponse(results=results)


def skill_output_to_legacy(so: TechSkillStockOutput) -> dict[str, Any]:
    """Convert typed TechSkillStockOutput to legacy dict format for downstream."""
    return {
        "ticker": so.ticker,
        "technical_score": so.technical_score,
        "action": so.action,
        "analysis": so.analysis,
        "risk_flags": so.risk_flags,
        "risk_note": so.risk_note,
        "position_note": so.position_note,
        "_skill_output": so.model_dump(),
    }
