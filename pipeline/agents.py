"""Layers 3-6: Dual LLM Agent pipeline with code-enforced risk control.

Layer 3: News Sentiment Agent + Tech Bypass mechanism
Layer 4: Technical Analysis Agent
Layer 5: Score synthesis (weighted merge, confidence filter, quality marking)
Layer 6: Code-enforced risk control (entry/SL/TP recalculation, R:R >= 1.5)

Adapted from astock-quant/pipeline/agents.py for US/HK markets.
LLM always participates - no separate rule-based path.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loguru import logger

from analysis.llm_client import agent_analyze
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
# Layer 3: News Sentiment Agent + Tech Bypass
# ---------------------------------------------------------------------------

def _build_news_payload(
    enriched: list[dict],
    market: str,
) -> dict[str, Any]:
    """Package enriched candidates with multi-source news for the News Agent.

    Each news item now includes credibility score and source tier,
    letting the LLM Agent weight information by trustworthiness.
    """
    from analysis.news_fetcher import fetch_market_news

    items = []
    for c in enriched:
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
            "price": _safe_float(c.get("price")),
            "change_pct": _safe_float(c.get("change_pct")),
            "market_cap": _safe_float(c.get("market_cap")),
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
            "themes": list(r.get("themes") or []),
        })
    logger.info(f"News Agent returned {len(normalized)} results")
    return normalized


def _check_tech_bypass(c: dict) -> bool:
    """Tech Bypass: allow candidate through even if news_score is low.

    Bypassed if ALL conditions are met:
    1. MA bullish alignment (ma5 >= ma10 >= ma20)
    2. Volume expansion (5d/20d ratio > 1.3)
    3. Not overbought (ma20 bias < 15%)
    4. No volume-price divergence
    """
    signals = c.get("signals", {})
    return (
        signals.get("ma_bullish_align", False)
        and signals.get("volume_expansion", False)
        and not signals.get("overbought_bias", False)
        and not signals.get("volume_price_divergence", False)
    )


def run_news_filter(
    enriched: list[dict],
    news_results: list[dict],
    top_n: int = 20,
) -> list[dict]:
    """Layer 3 filter: keep top news_score candidates + tech-bypassed ones.

    Returns the subset of enriched candidates that pass to Layer 4.
    """
    news_map = {r["ticker"]: r for r in news_results}

    scored = []
    for c in enriched:
        ticker = c["ticker"]
        nr = news_map.get(ticker)
        ns = nr["news_score"] if nr else 0
        scored.append((ns, c))

    scored.sort(key=lambda x: x[0], reverse=True)

    passed_tickers: set[str] = set()
    passed: list[dict] = []

    for ns, c in scored[:top_n]:
        passed_tickers.add(c["ticker"])
        passed.append(c)

    bypass_count = 0
    for ns, c in scored[top_n:]:
        if c["ticker"] not in passed_tickers and _check_tech_bypass(c):
            passed.append(c)
            passed_tickers.add(c["ticker"])
            bypass_count += 1

    if bypass_count:
        logger.info(f"Layer 3 Tech Bypass: {bypass_count} additional candidates passed")
    logger.info(f"Layer 3 news filter: {len(enriched)} -> {len(passed)} candidates")
    return passed


# ---------------------------------------------------------------------------
# Layer 4: Technical Analysis Agent
# ---------------------------------------------------------------------------

def _build_tech_payload(
    enriched: list[dict],
    market: str,
) -> dict[str, Any]:
    """Package enriched candidates with full technical data for Tech Agent.

    Uses pre-computed Layer 2 data instead of re-fetching.
    """
    items = []
    for c in enriched:
        items.append({
            "ticker": c["ticker"],
            "name": c.get("name", c["ticker"]),
            "market": c.get("market", market),
            "price": _safe_float(c.get("price")),
            "change_pct": _safe_float(c.get("change_pct")),
            "ma5": _safe_float(c.get("ma5")),
            "ma10": _safe_float(c.get("ma10")),
            "ma20": _safe_float(c.get("ma20")),
            "ma60": _safe_float(c.get("ma60")),
            "ma20_bias_pct": _safe_float(c.get("ma20_bias_pct")),
            "atr_20d": _safe_float(c.get("atr_20d")),
            "volatility_20d": _safe_float(c.get("volatility_20d")),
            "volatility_class": c.get("volatility_class", "medium"),
            "volume_ratio": _safe_float(c.get("volume_ratio")),
            "support_levels": c.get("support_levels", []),
            "resistance_levels": c.get("resistance_levels", []),
            "support_touch_count": c.get("support_touch_count", 0),
            "support_hold_strength": c.get("support_hold_strength", "untested"),
            "high_20d_volume_ratio": _safe_float(c.get("high_20d_volume_ratio")),
            "weekly_trend": c.get("weekly_trend", "neutral"),
            "signals": c.get("signals", {}),
            "kline_recent_part1": c.get("kline_recent_part1", []),
            "kline_recent_part2": c.get("kline_recent_part2", []),
        })
    return {
        "market": market,
        "candidate_count": len(items),
        "candidates": items,
    }


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
        })
    logger.info(f"Tech Agent returned {len(normalized)} results")
    return normalized


def fallback_technical_scores(enriched: list[dict]) -> list[dict]:
    """Deterministic fallback when Tech Agent fails.
    Uses pre-computed Layer 2 data for signal-based scoring.
    """
    cfg = get_config()
    fb = cfg.agent.fallback

    results = []
    for c in enriched:
        ticker = c["ticker"]
        price = _safe_float(c.get("price"))
        if price <= 0:
            continue

        signals = c.get("signals", {})
        score = fb.base_score

        if signals.get("ma_bullish_align"):
            score += fb.ma_bullish_bonus
        elif signals.get("ma_bearish_align"):
            score -= fb.ma_bearish_penalty

        vol_ratio = _safe_float(c.get("volume_ratio", 1.0))
        if vol_ratio >= fb.volume_ratio_strong:
            score += fb.volume_strong_bonus
        elif vol_ratio >= fb.volume_ratio_medium:
            score += fb.volume_medium_bonus

        if signals.get("overbought_bias"):
            score = min(score, 65)
        elif _safe_float(c.get("ma20_bias_pct")) > 10:
            score -= 5

        if signals.get("volume_price_divergence"):
            score -= 12

        if c.get("volatility_class") == "high":
            score -= 3

        weekly_trend = c.get("weekly_trend", "neutral")
        if weekly_trend == "bearish":
            score -= 8
        elif weekly_trend == "bullish":
            score += 3

        score = max(0, min(100, score))

        action = "buy" if score >= 60 else ("hold" if score >= 45 else "avoid")
        risk_note = ""
        if signals.get("overbought_bias"):
            action = "hold"
            risk_note = "MA20 bias over 15%, overbought risk"
        elif signals.get("volume_price_divergence"):
            risk_note = "Volume-price divergence at 20d high"

        results.append({
            "ticker": ticker,
            "technical_score": score,
            "action": action,
            "analysis": "Fallback rule-based technical scoring",
            "risk_flags": [],
            "risk_note": risk_note,
            "position_note": "",
        })

    return results


# ---------------------------------------------------------------------------
# Consistency check
# ---------------------------------------------------------------------------

_ACTION_SCORE_RANGES: dict[str, tuple[int, int]] = {
    "strong_buy": (70, 100),
    "buy": (60, 100),
    "hold": (35, 70),
    "avoid": (0, 45),
}


def _classify_action(action_str: str) -> str:
    a = (action_str or "").lower().strip()
    if any(k in a for k in ("strong", "aggressive")):
        return "strong_buy"
    if any(k in a for k in ("buy", "positive", "long", "bullish")):
        return "buy"
    if any(k in a for k in ("avoid", "negative", "bearish", "sell")):
        return "avoid"
    return "hold"


def check_agent_consistency(
    news_results: list[dict],
    tech_results: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Detect and penalise action-vs-score contradictions in agent outputs."""

    def _fix(results: list[dict], score_key: str) -> list[dict]:
        for r in results:
            action = str(r.get("action", ""))
            score = int(r.get(score_key, 0))
            bucket = _classify_action(action)
            lo, hi = _ACTION_SCORE_RANGES.get(bucket, (0, 100))
            if score < lo or score > hi:
                midpoint = (lo + hi) // 2
                adjusted = int(round(score * 0.6 + midpoint * 0.4))
                logger.debug(
                    f"Consistency fix {r.get('ticker')}: action='{action}' "
                    f"score {score}->{adjusted} (range [{lo},{hi}])"
                )
                r[score_key] = adjusted
                r["_consistency_adjusted"] = True
        return results

    news_results = _fix(news_results, "news_score")
    tech_results = _fix(tech_results, "technical_score")
    return news_results, tech_results


# ---------------------------------------------------------------------------
# Layer 6: Code-enforced risk control
# ---------------------------------------------------------------------------

def _compute_trade_params(
    price: float,
    enriched: dict,
    action: str,
    strategy_type: str = "short",
) -> dict[str, Any]:
    """Compute entry/SL/TP purely from code. Never trust LLM prices.

    Uses enriched Layer 2 data (ATR, support levels, MA, volatility)
    to calculate risk-managed trade parameters.
    """
    cfg = get_config()
    strat = cfg.swing if strategy_type == "swing" else cfg.short_term

    if price <= 0:
        return {
            "entry_price": 0, "entry_2": 0,
            "stop_loss": 0, "take_profit": 0,
            "take_profit_2": 0, "take_profit_3": 0,
            "holding_days": strat.default_holding_days,
        }

    ma20 = _safe_float(enriched.get("ma20", price))
    atr_20d = _safe_float(enriched.get("atr_20d", 0))
    volatility_class = str(enriched.get("volatility_class", "medium"))
    support_levels = enriched.get("support_levels", [])
    resistance_levels = enriched.get("resistance_levels", [])
    support_1 = _safe_float(support_levels[0]) if support_levels else price * 0.97
    support_2 = _safe_float(support_levels[1]) if len(support_levels) > 1 else price * 0.94
    resist_1 = _safe_float(resistance_levels[0]) if resistance_levels else price * 1.05
    resist_2 = _safe_float(resistance_levels[1]) if len(resistance_levels) > 1 else price * 1.09
    support_hold_strength = str(enriched.get("support_hold_strength", "untested"))

    action_bucket = _classify_action(action)

    if action_bucket == "strong_buy":
        entry_price = round(price * 0.997, 2)
    elif action_bucket == "buy":
        if support_hold_strength in ("strong", "moderate") and support_1 < price:
            entry_price = round(support_1 * 1.01, 2)
            if entry_price < price * 0.95:
                entry_price = round(price * 0.97, 2)
        elif ma20 > 0 and ma20 < price:
            entry_price = round(ma20 * 1.005, 2)
            if entry_price < price * 0.95:
                entry_price = round(price * 0.97, 2)
        else:
            entry_price = round(price * 0.98, 2)
    elif action_bucket == "avoid":
        entry_price = round(price * 0.97, 2)
    else:
        entry_price = round(price * 0.95, 2)

    entry_price = min(entry_price, price)
    entry_price = max(entry_price, round(price * 0.92, 2))

    entry_2 = round(entry_price * 0.985, 2)
    entry_2 = max(entry_2, round(price * 0.90, 2))

    if volatility_class == "high":
        stop_buffer_pct = 0.025
        holding_days = 3
    elif volatility_class == "low":
        stop_buffer_pct = 0.012
        holding_days = strat.default_holding_days
    else:
        stop_buffer_pct = 0.018
        holding_days = strat.default_holding_days

    stop_from_support = round(support_1 - price * stop_buffer_pct, 2)
    stop_from_default = round(entry_price * strat.default_stop_loss_pct, 2)
    stop_loss = max(stop_from_support, stop_from_default)

    atr_pct = atr_20d / price if (atr_20d > 0 and price > 0) else 0
    if atr_pct > 0:
        sl_min_pct = max(0.015, atr_pct * 1.0)
        sl_max_pct = min(0.12, atr_pct * 3.0)
    else:
        sl_min_pct = 0.02
        sl_max_pct = 0.10
    stop_loss = max(stop_loss, round(entry_price * (1 - sl_max_pct), 2))
    stop_loss = min(stop_loss, round(entry_price * (1 - sl_min_pct), 2))
    stop_loss = round(stop_loss, 2)

    if strategy_type == "swing":
        tp_from_resist = max(resist_1, resist_2 * 0.98 if resist_2 > resist_1 else resist_1)
        tp_from_default = entry_price * strat.default_take_profit_pct
        take_profit = round(max(tp_from_resist, tp_from_default), 2)
        take_profit = max(take_profit, round(entry_price * 1.05, 2))
    else:
        take_profit = round(max(resist_1 * 0.98, entry_price * strat.default_take_profit_pct), 2)
    take_profit = max(take_profit, round(entry_price * 1.03, 2))

    # Bidirectional R:R ratio floor (1.5:1)
    MIN_RR = 1.5
    risk = entry_price - stop_loss
    reward = take_profit - entry_price
    if risk > 0 and reward / risk < MIN_RR:
        atr_floor = entry_price - max(atr_20d * 1.5, entry_price * 0.015)
        tighter_sl = max(atr_floor, entry_price - reward / MIN_RR)
        if tighter_sl > stop_loss and tighter_sl < entry_price * 0.995:
            stop_loss = round(tighter_sl, 2)
            risk = entry_price - stop_loss

        reward = take_profit - entry_price
        if risk > 0 and reward / risk < MIN_RR:
            needed_tp = entry_price + risk * MIN_RR
            resist_ceiling = resist_1 * 1.03
            take_profit = round(min(needed_tp, resist_ceiling), 2)

    take_profit = round(take_profit, 2)

    tp2_default = entry_price * strat.take_profit_2_pct
    if strategy_type == "swing":
        take_profit_2 = round(max(resist_2, tp2_default), 2)
        atr_ext = entry_price + atr_20d * 4 if atr_20d > 0 else round(tp2_default * 1.05, 2)
        take_profit_3 = round(max(atr_ext, tp2_default * 1.05), 2)
    else:
        take_profit_2 = round(max(resist_1 * 1.02, resist_2 * 0.98, tp2_default), 2)
        atr_ext = entry_price + atr_20d * 3 if atr_20d > 0 else round(tp2_default * 1.05, 2)
        take_profit_3 = round(max(atr_ext, resist_2 * 1.05, tp2_default * 1.05), 2)

    take_profit_2 = max(take_profit_2, round(take_profit * 1.03, 2))
    take_profit_3 = max(take_profit_3, round(take_profit_2 * 1.04, 2))

    if strategy_type == "swing" and volatility_class == "high":
        holding_days = min(10, strat.default_holding_days)

    return {
        "entry_price": entry_price,
        "entry_2": entry_2,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "take_profit_2": take_profit_2,
        "take_profit_3": take_profit_3,
        "holding_days": holding_days,
    }


# ---------------------------------------------------------------------------
# Layer 5: Score synthesis
# ---------------------------------------------------------------------------

def synthesize_agent_results(
    enriched: list[dict],
    news_results: list[dict],
    tech_results: list[dict],
    strategy_type: str = "short",
    max_count: int | None = None,
) -> list[dict]:
    """Combine news + tech scores into ranked recommendations.

    Implements:
    - Weighted merge (short: news 0.35, tech 0.65)
    - Confidence filter (< 55 removed, adaptive fallback)
    - Quality marking (< 50 hides trade params, both < 40 = low quality)
    - Code-enforced trade params (Layer 6)
    """
    cfg = get_config()
    syn = cfg.synthesis

    if strategy_type == "swing":
        news_weight = 0.40
        tech_weight = 0.60
    else:
        news_weight = syn.news_weight
        tech_weight = syn.tech_weight

    min_confidence = syn.min_confidence
    quality_threshold = syn.quality_threshold
    low_score_both = 40

    if max_count is None:
        max_count = cfg.max_recommendations

    news_map = {r["ticker"]: r for r in news_results}
    tech_map = {r["ticker"]: r for r in tech_results}

    NEUTRAL = 50
    BLEND = syn.cross_fill_factor

    all_scored: list[dict] = []
    for c in enriched:
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

        combined = int(round(ns * news_weight + ts * tech_weight))
        combined = max(0, min(100, combined))

        sector_bonus = _safe_int(news.get("sector_bonus", 0))
        combined = min(100, combined + sector_bonus)

        price = _safe_float(c.get("price"))
        if price <= 0:
            continue

        action_str = str(tech.get("action", news.get("action", "hold")))

        trade = _compute_trade_params(
            price=price,
            enriched=c,
            action=action_str,
            strategy_type=strategy_type,
        )

        is_quality = combined >= quality_threshold and not (
            ns < low_score_both and ts < low_score_both
        )

        all_risk_flags = list(set(
            list(news.get("risk_flags") or []) +
            list(tech.get("risk_flags") or [])
        ))

        news_analysis = str(news.get("analysis", ""))
        tech_analysis = str(tech.get("analysis", ""))

        all_scored.append({
            "ticker": ticker,
            "name": c.get("name", ticker),
            "market": c.get("market", ""),
            "strategy": "swing" if strategy_type == "swing" else "short_term",
            "direction": "buy" if _classify_action(action_str) in ("buy", "strong_buy") else "hold",
            "score": round(combined, 2),
            "confidence": combined,
            "tech_score": ts,
            "news_score": ns,
            "fundamental_score": 50,
            "combined_score": combined,
            "action": action_str,
            "entry_price": trade["entry_price"] if is_quality else None,
            "entry_2": trade["entry_2"] if is_quality else None,
            "stop_loss": trade["stop_loss"] if is_quality else None,
            "take_profit": trade["take_profit"] if is_quality else None,
            "take_profit_2": trade["take_profit_2"] if is_quality else None,
            "take_profit_3": trade["take_profit_3"] if is_quality else None,
            "show_trading_params": is_quality,
            "holding_days": trade["holding_days"],
            "tech_reason": tech_analysis,
            "news_reason": news_analysis,
            "fundamental_reason": "",
            "llm_reason": "",
            "recommendation_reason": news_analysis or tech_analysis,
            "valuation_summary": "",
            "quality_score": None,
            "safety_margin": None,
            "risk_flags": all_risk_flags,
            "risk_note": str(tech.get("risk_note", "")),
            "position_note": str(tech.get("position_note", "")),
            "themes": news.get("themes", []) if isinstance(news.get("themes"), list) else [],
            "price": price,
            "change_pct": _safe_float(c.get("change_pct")),
        })

    all_scored.sort(key=lambda x: x["combined_score"], reverse=True)

    filtered = [s for s in all_scored if s["combined_score"] >= min_confidence]

    if not filtered and all_scored:
        adaptive_min = max(
            syn.adaptive_threshold_floor,
            min_confidence - syn.adaptive_threshold_drop,
        )
        filtered = [s for s in all_scored if s["combined_score"] >= adaptive_min]
        if not filtered:
            filtered = all_scored[:max(1, len(all_scored) // 2)]
        logger.info(
            f"Adaptive threshold: {min_confidence}->{adaptive_min}, "
            f"keeping {len(filtered)} (top={all_scored[0]['combined_score']})"
        )

    filtered = _limit_sector_concentration(filtered, max_ratio=0.4)
    return filtered[:max_count]


def _limit_sector_concentration(
    items: list[dict], max_ratio: float = 0.4,
) -> list[dict]:
    """Ensure no single sector exceeds max_ratio of the final list."""
    if not items or len(items) <= 2:
        return items
    max_per = max(1, int(len(items) * max_ratio))
    counts: dict[str, int] = {}
    selected: list[dict] = []
    for item in items:
        themes = item.get("themes") or []
        sector = themes[0] if themes else "_other"
        cnt = counts.get(sector, 0)
        if cnt >= max_per:
            continue
        selected.append(item)
        counts[sector] = cnt + 1
    if selected and len(selected) < len(items):
        logger.info(f"Sector limiter: {len(items)}->{len(selected)}")
    return selected


# ---------------------------------------------------------------------------
# Main agent pipeline entry point
# ---------------------------------------------------------------------------

def run_agent_pipeline(
    enriched: list[dict],
    market: str = "all",
    strategy_type: str = "short",
    progress_cb: Callable[[dict], None] | None = None,
) -> list[dict]:
    """Run the full 6-layer agent pipeline on enriched candidates.

    Expects output from screening.build_enriched_candidates().

    Layer 3: News Agent + filter + Tech Bypass
    Layer 4: Technical Agent (fallback if LLM fails)
    Layer 5: Score synthesis
    Layer 6: Trade params are code-enforced inside synthesis

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

    if not enriched:
        return []

    candidates = enriched[:batch_size]

    # Layer 3: News Agent
    _progress(35.0, f"Layer 3: News Agent analyzing {len(candidates)} candidates")
    news_payload = _build_news_payload(candidates, market)
    news_results = _call_news_agent(news_payload, max_retries=max_retries)

    if not news_results:
        logger.warning("News Agent returned no results, sending all to Tech Agent")
        tech_candidates = candidates
    else:
        tech_candidates = run_news_filter(candidates, news_results, top_n=batch_size // 2)

    # Layer 4: Technical Agent
    _progress(55.0, f"Layer 4: Tech Agent analyzing {len(tech_candidates)} candidates")
    tech_payload = _build_tech_payload(tech_candidates, market)
    tech_results = _call_tech_agent(tech_payload, max_retries=max_retries)

    if not tech_results:
        logger.warning("Tech Agent returned no results, using fallback scoring")
        tech_results = fallback_technical_scores(tech_candidates)

    # Consistency check between agents
    if news_results and tech_results:
        news_results, tech_results = check_agent_consistency(news_results, tech_results)

    # Layer 5 + 6: Synthesis with code-enforced trade params
    _progress(70.0, "Layer 5-6: Synthesis and risk control")
    recommendations = synthesize_agent_results(
        tech_candidates,
        news_results,
        tech_results,
        strategy_type=strategy_type,
    )

    _progress(78.0, f"Pipeline complete: {len(recommendations)} recommendations")
    return recommendations
