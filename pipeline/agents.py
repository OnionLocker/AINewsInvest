"""LLM Agent orchestration, score synthesis, and fallback logic.

Adapted from astock-quant/pipeline/agents.py for US/HK markets.
Architecture: Python pre-processing -> LLM Agent calls -> Python synthesis.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

import numpy as np
from loguru import logger

from analysis.llm_client import agent_analyze
from core.data_source import get_klines, get_news
from analysis.technical import analyze as technical_analyze
from analysis.news_fetcher import fetch_news
from pipeline.config import get_config


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------

def _build_news_payload(
    candidates: list[dict],
    market: str,
) -> dict[str, Any]:
    """Package candidate stocks with their news data for the News Agent."""
    items = []
    for c in candidates:
        ticker = c["ticker"]
        mkt = c.get("market", market)
        news_items = fetch_news(ticker, mkt, limit=8)
        news_summaries = [
            {
                "title": n.get("title", ""),
                "publisher": n.get("publisher", ""),
                "link": n.get("link", ""),
            }
            for n in news_items[:8]
        ]
        items.append({
            "ticker": ticker,
            "name": c.get("name", ticker),
            "market": mkt,
            "price": _safe_float(c.get("price")),
            "change_pct": _safe_float(c.get("change_pct")),
            "market_cap": _safe_float(c.get("market_cap")),
            "pe_ttm": c.get("pe_ttm"),
            "news": news_summaries,
        })
    return {
        "market": market,
        "candidate_count": len(items),
        "candidates": items,
    }


def _build_tech_payload(
    candidates: list[dict],
    market: str,
) -> dict[str, Any]:
    """Package candidate stocks with technical data for the Technical Agent."""
    items = []
    for c in candidates:
        ticker = c["ticker"]
        mkt = c.get("market", market)

        tech = None
        try:
            tech = technical_analyze(ticker, mkt)
        except Exception as e:
            logger.debug(f"Tech analyze {mkt}:{ticker}: {e}")

        klines = get_klines(ticker, mkt, days=25)
        kline_data = []
        if klines is not None and not klines.empty:
            recent = klines.tail(20)
            kline_data = [
                {
                    "date": str(row.get("date", "")),
                    "open": round(_safe_float(row.get("open")), 2),
                    "high": round(_safe_float(row.get("high")), 2),
                    "low": round(_safe_float(row.get("low")), 2),
                    "close": round(_safe_float(row.get("close")), 2),
                    "volume": int(_safe_float(row.get("volume"))),
                }
                for _, row in recent.iterrows()
            ]

        signals = {}
        if tech:
            signals = {
                "trend": tech.get("trend", ""),
                "signal": tech.get("signal", ""),
                "composite_score": _safe_float(tech.get("composite_score")),
                "ma5": _safe_float(tech.get("ma5")),
                "ma10": _safe_float(tech.get("ma10")),
                "ma20": _safe_float(tech.get("ma20")),
                "ma60": _safe_float(tech.get("ma60")),
                "rsi": _safe_float(tech.get("rsi")),
                "macd": _safe_float(tech.get("macd")),
                "macd_signal": _safe_float(tech.get("macd_signal")),
                "support": _safe_float(tech.get("support")),
                "resistance": _safe_float(tech.get("resistance")),
                "atr": _safe_float(tech.get("atr")),
            }
            levels = tech.get("levels") or {}
            if levels:
                signals["levels"] = levels

        items.append({
            "ticker": ticker,
            "name": c.get("name", ticker),
            "market": mkt,
            "price": _safe_float(c.get("price")),
            "change_pct": _safe_float(c.get("change_pct")),
            "signals": signals,
            "kline_recent": kline_data,
        })

    return {
        "market": market,
        "candidate_count": len(items),
        "candidates": items,
    }


# ---------------------------------------------------------------------------
# Agent callers
# ---------------------------------------------------------------------------

def _call_news_agent(payload: dict[str, Any], max_retries: int = 1) -> list[dict]:
    """Invoke the News Sentiment Agent and normalize results."""
    response = agent_analyze("news_sentiment_agent", payload, max_retries=max_retries)
    if response is None:
        return []

    results = response.get("results", [])
    normalized = []
    for r in results:
        ticker = r.get("ticker") or r.get("code", "")
        if not ticker:
            continue
        normalized.append({
            "ticker": str(ticker),
            "news_score": max(0, min(100, _safe_int(r.get("news_score", 50)))),
            "sentiment": str(r.get("sentiment", "neutral")),
            "action": str(r.get("action", "hold")),
            "analysis": str(r.get("analysis", ""))[:500],
            "risk_flags": list(r.get("risk_flags") or []),
            "risk_note": str(r.get("risk_note", ""))[:200],
            "sector_bonus": _safe_int(r.get("sector_bonus", 0)),
        })
    logger.info(f"News Agent returned {len(normalized)} results")
    return normalized


def _call_tech_agent(payload: dict[str, Any], max_retries: int = 1) -> list[dict]:
    """Invoke the Technical Analysis Agent and normalize results."""
    response = agent_analyze("technical_agent", payload, max_retries=max_retries)
    if response is None:
        return []

    results = response.get("results", [])
    normalized = []
    for r in results:
        ticker = r.get("ticker") or r.get("code", "")
        if not ticker:
            continue
        normalized.append({
            "ticker": str(ticker),
            "technical_score": max(0, min(100, _safe_int(r.get("technical_score", 50)))),
            "action": str(r.get("action", "hold")),
            "analysis": str(r.get("analysis", ""))[:500],
            "risk_flags": list(r.get("risk_flags") or []),
            "risk_note": str(r.get("risk_note", ""))[:200],
            "position_note": str(r.get("position_note", ""))[:100],
            "entry_price": _safe_float(r.get("entry_price")),
            "stop_loss": _safe_float(r.get("stop_loss")),
            "take_profit": _safe_float(r.get("take_profit")),
            "take_profit_2": _safe_float(r.get("take_profit_2")),
            "holding_days": _safe_int(r.get("holding_days", 5)),
        })
    logger.info(f"Tech Agent returned {len(normalized)} results")
    return normalized


# ---------------------------------------------------------------------------
# Fallback scoring (deterministic, no LLM)
# ---------------------------------------------------------------------------

def fallback_technical_scores(candidates: list[dict]) -> list[dict]:
    """Generate deterministic technical scores when LLM is unavailable.

    Uses pre-computed technical analysis signals and simple heuristics.
    """
    cfg = get_config()
    fb = cfg.agent.fallback
    st = cfg.short_term

    results = []
    for c in candidates:
        ticker = c["ticker"]
        market = c.get("market", "us_stock")
        price = _safe_float(c.get("price"))
        if price <= 0:
            continue

        tech = None
        try:
            tech = technical_analyze(ticker, market)
        except Exception:
            pass

        score = fb.base_score

        if tech:
            trend = str(tech.get("trend", "")).lower()
            if "bullish" in trend or "up" in trend:
                score += fb.ma_bullish_bonus
            elif "bearish" in trend or "down" in trend:
                score -= fb.ma_bearish_penalty

            signal = str(tech.get("signal", "")).lower()
            if "golden" in signal:
                score += fb.ma_short_golden_bonus

            vol_ratio = _safe_float(tech.get("volume_ratio", 1.0))
            if vol_ratio >= fb.volume_ratio_strong:
                score += fb.volume_strong_bonus
            elif vol_ratio >= fb.volume_ratio_medium:
                score += fb.volume_medium_bonus

        score = max(0, min(100, score))

        entry = round(price * fb.entry_discount, 4)
        results.append({
            "ticker": ticker,
            "technical_score": score,
            "action": "buy" if score >= 60 else "hold" if score >= 45 else "avoid",
            "analysis": "",
            "risk_flags": [],
            "risk_note": "",
            "entry_price": entry,
            "stop_loss": round(price * fb.stop_loss_pct, 4),
            "take_profit": round(price * fb.take_profit_pct, 4),
            "take_profit_2": round(price * st.take_profit_2_pct, 4),
            "holding_days": fb.holding_days,
        })

    return results


# ---------------------------------------------------------------------------
# Consistency check
# ---------------------------------------------------------------------------

def check_agent_consistency(
    news_results: list[dict],
    tech_results: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Dampen scores when news and tech agents strongly disagree.

    If one agent scores very high (>75) while the other scores low (<35),
    the high score is dampened toward neutral.
    """
    news_map = {r["ticker"]: r for r in news_results}
    tech_map = {r["ticker"]: r for r in tech_results}

    for ticker in set(news_map) & set(tech_map):
        ns = news_map[ticker]["news_score"]
        ts = tech_map[ticker]["technical_score"]

        if ns > 75 and ts < 35:
            dampened = int(ns * 0.7 + 50 * 0.3)
            logger.info(f"Consistency dampen {ticker}: news {ns}->{dampened} (tech={ts})")
            news_map[ticker]["news_score"] = dampened
            news_map[ticker].setdefault("risk_flags", []).append("agent_disagreement")

        elif ts > 75 and ns < 35:
            dampened = int(ts * 0.7 + 50 * 0.3)
            logger.info(f"Consistency dampen {ticker}: tech {ts}->{dampened} (news={ns})")
            tech_map[ticker]["technical_score"] = dampened
            tech_map[ticker].setdefault("risk_flags", []).append("agent_disagreement")

    return list(news_map.values()), list(tech_map.values())


# ---------------------------------------------------------------------------
# Score synthesis
# ---------------------------------------------------------------------------

def _compute_trade_params(
    price: float,
    tech: dict,
    cfg_st: Any,
) -> dict[str, Any]:
    """Recalculate trade parameters from real price data.
    Never trust LLM-provided price numbers directly.
    """
    entry = round(price * 0.995, 4)
    stop_loss = round(price * cfg_st.default_stop_loss_pct, 4)
    take_profit = round(price * cfg_st.default_take_profit_pct, 4)
    take_profit_2 = round(price * cfg_st.take_profit_2_pct, 4)
    holding_days = cfg_st.default_holding_days

    if tech.get("entry_price") and tech["entry_price"] > 0:
        agent_entry = _safe_float(tech["entry_price"])
        if 0.9 * price < agent_entry < 1.1 * price:
            entry = round(agent_entry, 4)

    if tech.get("holding_days") and 1 <= tech["holding_days"] <= cfg_st.max_holding_days:
        holding_days = tech["holding_days"]

    return {
        "entry_price": entry,
        "entry_2": round(price * 0.99, 4),
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "take_profit_2": take_profit_2,
        "holding_days": holding_days,
    }


def synthesize_agent_results(
    candidates: list[dict],
    news_results: list[dict],
    tech_results: list[dict],
    fundamental_data: dict[str, dict] | None = None,
    max_count: int | None = None,
) -> list[dict]:
    """Combine per-stock scores from both agents into a ranked recommendation list.

    Implements adaptive threshold lowering from astock-quant when all scores
    fall below min_confidence (e.g. weak market).
    """
    cfg = get_config()
    syn = cfg.synthesis
    st = cfg.short_term

    if max_count is None:
        max_count = cfg.max_recommendations

    news_weight = syn.news_weight
    tech_weight = syn.tech_weight
    fund_weight = syn.fundamental_weight
    min_confidence = syn.min_confidence
    quality_threshold = syn.quality_threshold

    news_map = {r["ticker"]: r for r in news_results}
    tech_map = {r["ticker"]: r for r in tech_results}
    fund_map = fundamental_data or {}

    NEUTRAL = 50
    BLEND = syn.cross_fill_factor

    all_scored: list[dict] = []
    for c in candidates:
        ticker = c["ticker"]
        news = news_map.get(ticker, {})
        tech = tech_map.get(ticker, {})

        if not news and not tech:
            continue

        ns = _safe_int(news.get("news_score", 0))
        ts = _safe_int(tech.get("technical_score", 0))

        if not news and tech:
            ns = int(NEUTRAL + (ts - NEUTRAL) * BLEND)
        elif news and not tech:
            ts = int(NEUTRAL + (ns - NEUTRAL) * BLEND)

        fs = 50
        fund = fund_map.get(ticker)
        if fund:
            qs = fund.get("quality_score")
            if qs is not None:
                fs = max(0, min(100, int(round(float(qs)))))

        combined = int(round(ns * news_weight + ts * tech_weight + fs * fund_weight))
        combined = max(0, min(100, combined))

        sector_bonus = _safe_int(news.get("sector_bonus", 0))
        combined = min(100, combined + sector_bonus)

        price = _safe_float(c.get("price"))
        if price <= 0:
            continue

        trade = _compute_trade_params(price, tech, st)

        all_risk_flags = list(set(
            list(news.get("risk_flags") or []) +
            list(tech.get("risk_flags") or [])
        ))

        news_reason = news.get("analysis", "")
        tech_reason = tech.get("analysis", "")
        if not tech_reason and tech:
            tech_reason = f"{tech.get('action', '')} (score={ts})"

        fund_reason = ""
        if fund:
            fund_reason = str(fund.get("fundamental_summary", ""))[:500]

        action = tech.get("action") or news.get("action", "hold")
        direction = "buy" if action == "buy" else "hold"

        all_scored.append({
            "ticker": ticker,
            "name": c.get("name", ticker),
            "market": c.get("market", ""),
            "strategy": "short_term",
            "direction": direction,
            "score": round(combined, 2),
            "confidence": combined,
            "tech_score": ts,
            "news_score": ns,
            "fundamental_score": fs,
            "combined_score": combined,
            "entry_price": trade["entry_price"],
            "entry_2": trade["entry_2"],
            "stop_loss": trade["stop_loss"],
            "take_profit": trade["take_profit"],
            "take_profit_2": trade["take_profit_2"],
            "holding_days": trade["holding_days"],
            "tech_reason": tech_reason,
            "news_reason": news_reason,
            "fundamental_reason": fund_reason,
            "llm_reason": "",
            "recommendation_reason": news_reason or tech_reason,
            "valuation_summary": fund_reason,
            "quality_score": fs if fund else None,
            "safety_margin": None,
            "risk_flags": all_risk_flags,
            "price": price,
            "change_pct": _safe_float(c.get("change_pct")),
        })

    if not all_scored:
        return []

    all_scored.sort(key=lambda x: x["combined_score"], reverse=True)

    filtered = [
        a for a in all_scored
        if a["confidence"] >= min_confidence
        and (a.get("quality_score") is None or a["quality_score"] >= quality_threshold)
    ]

    if not filtered and all_scored:
        drop = syn.adaptive_threshold_drop
        floor = syn.adaptive_threshold_floor
        lowered = max(floor, min_confidence - drop)
        filtered = [a for a in all_scored if a["confidence"] >= lowered]
        if filtered:
            logger.info(
                f"Adaptive threshold: {min_confidence} -> {lowered}, "
                f"recovered {len(filtered)} candidates"
            )
        else:
            filtered = all_scored[:max_count]
            logger.info(f"All below threshold, taking top {len(filtered)}")

    return filtered[:max_count]


# ---------------------------------------------------------------------------
# Main agent pipeline entry point
# ---------------------------------------------------------------------------

def run_agent_pipeline(
    candidates: list[dict],
    market: str = "all",
    progress_cb: Callable[[dict], None] | None = None,
) -> list[dict]:
    """Run the dual-agent pipeline on pre-screened candidates.

    1. Build news & tech payloads
    2. Call News Agent
    3. Call Tech Agent (with optional news-based filtering)
    4. Consistency check
    5. Synthesize final scores

    Returns ranked list of recommendation dicts.
    """
    cfg = get_config()
    max_retries = cfg.agent.max_retries
    batch_size = cfg.agent.batch_size

    def _progress(pct: float, msg: str):
        if progress_cb:
            try:
                progress_cb({"progress": pct, "message": msg})
            except Exception:
                pass

    if not candidates:
        return []

    batched = candidates[:batch_size]
    _progress(40.0, f"News Agent: analyzing {len(batched)} candidates")

    news_payload = _build_news_payload(batched, market)
    news_results = _call_news_agent(news_payload, max_retries=max_retries)

    if not news_results:
        logger.warning("News Agent returned no results, proceeding with tech only")

    _progress(55.0, f"Tech Agent: analyzing {len(batched)} candidates")

    tech_payload = _build_tech_payload(batched, market)
    tech_results = _call_tech_agent(tech_payload, max_retries=max_retries)

    if not tech_results:
        logger.warning("Tech Agent returned no results, using fallback scoring")
        tech_results = fallback_technical_scores(batched)

    _progress(70.0, "Consistency check and synthesis")

    if news_results and tech_results:
        news_results, tech_results = check_agent_consistency(news_results, tech_results)

    fund_data: dict[str, dict] = {}
    for c in batched:
        ticker = c["ticker"]
        fund = c.get("financial") or {}
        if fund:
            fund_data[ticker] = fund

    recommendations = synthesize_agent_results(
        batched,
        news_results,
        tech_results,
        fundamental_data=fund_data,
    )

    _progress(78.0, f"Agent pipeline complete: {len(recommendations)} recommendations")
    return recommendations
