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

import pandas as pd
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


def _normalize_news_results(results: list[dict]) -> list[dict]:
    """Normalize raw news agent results."""
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
    return normalized


def _call_news_agent(payload: dict[str, Any], max_retries: int = 1) -> list[dict]:
    """Invoke the News Sentiment Agent and normalize results."""
    response = agent_analyze("news_sentiment_agent", payload, max_retries=max_retries)
    if response is None:
        return []

    results = response.get("results", [])
    normalized = _normalize_news_results(results)
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
        ns = nr["news_score"] if nr else 50
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


def _normalize_tech_results(results: list[dict]) -> list[dict]:
    """Normalize raw tech agent results."""
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
    return normalized


def _call_tech_agent(payload: dict[str, Any], max_retries: int = 1) -> list[dict]:
    """Invoke the Technical Analysis Agent and normalize results."""
    response = agent_analyze("technical_agent", payload, max_retries=max_retries)
    if response is None:
        return []

    results = response.get("results", [])
    normalized = _normalize_tech_results(results)
    logger.info(f"Tech Agent returned {len(normalized)} results")
    return normalized


def _compute_rsi(closes: list[float], period: int = 14) -> float:
    """Relative Strength Index."""
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    gains = gains[-(period):]
    losses = losses[-(period):]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _compute_macd(closes: list[float]) -> tuple[float, float, float]:
    """MACD line, signal line, histogram. Returns (macd, signal, hist)."""
    if len(closes) < 26:
        return 0.0, 0.0, 0.0

    def _ema(data, period):
        mult = 2 / (period + 1)
        ema = [data[0]]
        for val in data[1:]:
            ema.append(val * mult + ema[-1] * (1 - mult))
        return ema

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = [a - b for a, b in zip(ema12, ema26)]
    signal = _ema(macd_line[-9:], 9) if len(macd_line) >= 9 else [0]
    hist = macd_line[-1] - signal[-1]
    return round(macd_line[-1], 4), round(signal[-1], 4), round(hist, 4)


def _compute_bollinger_position(closes: list[float], period: int = 20) -> float:
    """Position within Bollinger Bands. 0=lower band, 0.5=middle, 1=upper band."""
    if len(closes) < period:
        return 0.5
    recent = closes[-period:]
    sma = sum(recent) / period
    std = (sum((x - sma) ** 2 for x in recent) / period) ** 0.5
    if std == 0:
        return 0.5
    upper = sma + 2 * std
    lower = sma - 2 * std
    if upper == lower:
        return 0.5
    pos = (closes[-1] - lower) / (upper - lower)
    return round(max(0.0, min(1.0, pos)), 3)


def _compute_obv_trend(closes: list[float], volumes: list[float], period: int = 20) -> str:
    """On-Balance Volume trend over last `period` bars."""
    if len(closes) < period + 1 or len(volumes) < period + 1:
        return "neutral"
    obv = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    recent_obv = obv[-period:]
    if len(recent_obv) < 5:
        return "neutral"
    first_half = sum(recent_obv[:len(recent_obv)//2]) / (len(recent_obv)//2)
    second_half = sum(recent_obv[len(recent_obv)//2:]) / (len(recent_obv) - len(recent_obv)//2)
    diff_pct = (second_half - first_half) / max(abs(first_half), 1) * 100
    if diff_pct > 10:
        return "bullish"
    elif diff_pct < -10:
        return "bearish"
    return "neutral"


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

        # Enhanced indicators from K-line data
        klines_1 = c.get("kline_recent_part1") or []
        klines_2 = c.get("kline_recent_part2") or []
        all_klines = klines_1 + klines_2
        if len(all_klines) >= 14:
            kl_closes = [float(k.get("close", 0)) for k in all_klines if k.get("close")]
            kl_volumes = [float(k.get("volume", 0)) for k in all_klines if k.get("volume")]

            if len(kl_closes) >= 14:
                rsi = _compute_rsi(kl_closes)
                if rsi > 75:
                    score -= 8
                elif rsi > 70:
                    score -= 4
                elif rsi < 25:
                    score += 6
                elif rsi < 30:
                    score += 3

            if len(kl_closes) >= 20:
                bb_pos = _compute_bollinger_position(kl_closes)
                if bb_pos > 0.95:
                    score -= 5
                elif bb_pos < 0.05:
                    score += 4

                macd_val, signal_val, macd_hist = _compute_macd(kl_closes)
                if macd_hist > 0 and macd_val > signal_val:
                    score += 3
                elif macd_hist < 0 and macd_val < signal_val:
                    score -= 3

            if len(kl_closes) >= 14 and len(kl_volumes) >= 14:
                obv_trend = _compute_obv_trend(kl_closes, kl_volumes)
                if obv_trend == "bullish":
                    score += 3
                elif obv_trend == "bearish":
                    score -= 3

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
    "short": (0, 35),
}


def _classify_action(action_str: str) -> str:
    a = (action_str or "").lower().strip()
    if any(k in a for k in ("short", "sell_short")):
        return "short"
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


def _compute_short_trade_params(
    price: float,
    enriched: dict,
    strategy_type: str = "short",
) -> dict[str, Any]:
    """Compute SHORT (sell) trade parameters. TP below price, SL above price."""
    cfg = get_config()
    strat = cfg.swing if strategy_type == "swing" else cfg.short_term

    if price <= 0:
        return {
            "entry_price": 0, "entry_2": 0,
            "stop_loss": 0, "take_profit": 0,
            "take_profit_2": 0, "take_profit_3": 0,
            "holding_days": strat.default_holding_days,
        }

    atr_20d = _safe_float(enriched.get("atr_20d", 0))
    volatility_class = str(enriched.get("volatility_class", "medium"))
    support_levels = enriched.get("support_levels", [])
    resistance_levels = enriched.get("resistance_levels", [])
    support_1 = _safe_float(support_levels[0]) if support_levels else price * 0.95
    support_2 = _safe_float(support_levels[1]) if len(support_levels) > 1 else price * 0.91
    resist_1 = _safe_float(resistance_levels[0]) if resistance_levels else price * 1.03

    entry_price = round(price * 1.003, 2)
    entry_price = max(entry_price, price)
    entry_2 = round(entry_price * 1.015, 2)

    if volatility_class == "high":
        sl_buffer_pct = 0.025
        holding_days = 3
    elif volatility_class == "low":
        sl_buffer_pct = 0.012
        holding_days = strat.default_holding_days
    else:
        sl_buffer_pct = 0.018
        holding_days = strat.default_holding_days

    stop_loss = round(max(resist_1 * 1.01, entry_price * (1 + sl_buffer_pct)), 2)

    atr_pct = atr_20d / price if (atr_20d > 0 and price > 0) else 0
    if atr_pct > 0:
        sl_max_pct = min(0.10, atr_pct * 2.5)
    else:
        sl_max_pct = 0.08
    stop_loss = min(stop_loss, round(entry_price * (1 + sl_max_pct), 2))
    stop_loss = max(stop_loss, round(entry_price * 1.015, 2))

    risk = stop_loss - entry_price
    min_rr = 1.5
    take_profit = round(min(support_1, entry_price * (1 - strat.default_stop_loss_pct + 1)), 2)
    take_profit = round(min(take_profit, entry_price - risk * min_rr), 2)
    take_profit = min(take_profit, round(entry_price * 0.97, 2))

    take_profit_2 = round(min(support_2, take_profit * 0.97), 2)
    take_profit_3 = round(take_profit_2 * 0.96, 2)

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
    regime: dict | None = None,
) -> list[dict]:
    """Combine news + tech scores into ranked recommendations.

    Implements:
    - Weighted merge (short: news 0.35, tech 0.65)
    - Confidence filter (strict: below threshold = no recommendation)
    - Market regime adjustment (bearish = higher bar)
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

    # Adaptive weight adjustment based on historical win-rate data
    try:
        from pipeline.analyzer import analyze_score_effectiveness
        effectiveness = analyze_score_effectiveness(min_records=50)
        if effectiveness.get("status") == "ok":
            corrs = effectiveness.get("correlation_summary", {})
            nc = (corrs.get("news_score") or {}).get("correlation")
            tc = (corrs.get("tech_score") or {}).get("correlation")
            if nc is not None and tc is not None:
                prior_blend = 0.7
                if nc < 0.05:
                    adj_news = max(0.05, news_weight * 0.5)
                elif nc > 0.2:
                    adj_news = min(0.35, news_weight * 1.3)
                else:
                    adj_news = news_weight
                if tc > 0.2:
                    adj_tech = min(0.70, tech_weight * 1.2)
                elif tc < 0.05:
                    adj_tech = max(0.30, tech_weight * 0.8)
                else:
                    adj_tech = tech_weight
                news_weight = news_weight * prior_blend + adj_news * (1 - prior_blend)
                tech_weight = tech_weight * prior_blend + adj_tech * (1 - prior_blend)
                total = news_weight + tech_weight + syn.fundamental_weight
                news_weight /= total
                tech_weight /= total
                logger.info(f"Adaptive weights: news={news_weight:.2f} tech={tech_weight:.2f} (nc={nc:.3f} tc={tc:.3f})")
    except Exception as e:
        logger.debug(f"Adaptive weights skipped: {e}")

    min_confidence = syn.min_confidence
    quality_threshold = syn.quality_threshold
    low_score_both = 40

    regime_level = (regime or {}).get("level", "normal")
    if regime_level == "bearish":
        min_confidence = min(95, min_confidence + 10)
        logger.info(f"Bearish regime: min_confidence raised to {min_confidence}")
    elif regime_level == "crisis":
        min_confidence = min(95, min_confidence + 20)
        logger.info(f"Crisis regime: min_confidence raised to {min_confidence}")

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

        fs = _safe_int(c.get("fundamental_score", 50))
        fw = syn.fundamental_weight
        if fw > 0:
            total_w = news_weight + tech_weight + fw
            combined = int(round(
                (ns * news_weight + ts * tech_weight + fs * fw) / total_w
            ))
        else:
            combined = int(round(ns * news_weight + ts * tech_weight))
        combined = max(0, min(100, combined))

        sector_bonus = _safe_int(news.get("sector_bonus", 0))
        combined = min(100, combined + sector_bonus)

        price = _safe_float(c.get("price"))
        if price <= 0:
            continue

        action_str = str(tech.get("action", news.get("action", "hold")))
        action_bucket = _classify_action(action_str)
        market_str = c.get("market", "")

        is_short = (
            action_bucket == "short"
            and market_str == "us_stock"
        )

        if is_short:
            trade = _compute_short_trade_params(
                price=price,
                enriched=c,
                strategy_type=strategy_type,
            )
            direction = "short"
        else:
            trade = _compute_trade_params(
                price=price,
                enriched=c,
                action=action_str,
                strategy_type=strategy_type,
            )
            direction = "buy" if action_bucket in ("buy", "strong_buy") else "hold"

        is_quality = combined >= quality_threshold and not (
            ns < low_score_both and ts < low_score_both
        )
        if is_short:
            is_quality = ns <= 35 and ts <= 40

        all_risk_flags = list(set(
            list(news.get("risk_flags") or []) +
            list(tech.get("risk_flags") or [])
        ))

        holding_days_final = trade["holding_days"]
        earnings_imminent = c.get("earnings_imminent", False)
        earnings_days = c.get("earnings_days_away")
        if earnings_imminent and earnings_days is not None and earnings_days >= 0:
            all_risk_flags.append("earnings_imminent")
            if earnings_days < holding_days_final:
                holding_days_final = max(1, earnings_days - 1)

        news_analysis = str(news.get("analysis", ""))
        tech_analysis = str(tech.get("analysis", ""))

        all_scored.append({
            "ticker": ticker,
            "name": c.get("name", ticker),
            "market": market_str,
            "strategy": "swing" if strategy_type == "swing" else "short_term",
            "direction": direction,
            "score": round(combined, 2),
            "confidence": combined,
            "tech_score": ts,
            "news_score": ns,
            "fundamental_score": fs,
            "combined_score": combined,
            "action": action_str,
            "entry_price": trade["entry_price"] if is_quality else None,
            "entry_2": trade["entry_2"] if is_quality else None,
            "stop_loss": trade["stop_loss"] if is_quality else None,
            "take_profit": trade["take_profit"] if is_quality else None,
            "take_profit_2": trade["take_profit_2"] if is_quality else None,
            "take_profit_3": trade["take_profit_3"] if is_quality else None,
            "show_trading_params": is_quality,
            "holding_days": holding_days_final,
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
            "position_pct": _suggest_position_pct(combined, regime_level),
            "earnings_days_away": c.get("earnings_days_away"),
            "earnings_date_str": c.get("earnings_date_str"),
            "position_note": str(tech.get("position_note", "")),
            "themes": news.get("themes", []) if isinstance(news.get("themes"), list) else [],
            "price": price,
            "change_pct": _safe_float(c.get("change_pct")),
        })

    all_scored.sort(key=lambda x: x["combined_score"], reverse=True)

    filtered = [s for s in all_scored if s["combined_score"] >= min_confidence]

    if not filtered:
        top_score = all_scored[0]["combined_score"] if all_scored else 0
        logger.info(
            f"No stocks passed min_confidence={min_confidence} "
            f"(top_score={top_score}). Returning empty - sit out today."
        )
        return []

    filtered = _limit_sector_concentration(filtered, max_ratio=0.4)
    filtered = _check_pairwise_correlation(filtered)
    return filtered[:max_count]


def _suggest_position_pct(score: int, regime_level: str = "normal") -> int:
    """Suggest position size as % of portfolio based on score and regime."""
    if score >= 85:
        pct = 10
    elif score >= 75:
        pct = 8
    elif score >= 65:
        pct = 5
    else:
        pct = 3

    if regime_level == "cautious":
        pct = max(2, pct - 2)
    elif regime_level in ("bearish", "crisis"):
        pct = max(2, pct // 2)

    return pct


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


def _check_pairwise_correlation(items: list[dict], max_corr: float = 0.7) -> list[dict]:
    """Remove highly correlated picks from the recommendation list.

    Uses recent price change similarity as a correlation proxy.
    """
    if not items or len(items) <= 2:
        return items

    tickers = [it["ticker"] for it in items]
    try:
        import yfinance as yf
        from datetime import datetime, timedelta
        end = datetime.now()
        start = end - timedelta(days=30)
        data = yf.download(
            tickers, start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"), progress=False,
        )
        if data.empty or "Close" not in data.columns.get_level_values(0):
            return items

        closes = data["Close"]
        if isinstance(closes, pd.Series):
            return items

        returns = closes.pct_change().dropna()
        if returns.empty or len(returns) < 5:
            return items

        corr_matrix = returns.corr()

        removed: set[str] = set()
        score_map = {it["ticker"]: it.get("combined_score", 0) for it in items}

        for i, t1 in enumerate(tickers):
            if t1 in removed:
                continue
            for t2 in tickers[i+1:]:
                if t2 in removed:
                    continue
                if t1 in corr_matrix.columns and t2 in corr_matrix.columns:
                    c = corr_matrix.loc[t1, t2]
                    if abs(c) > max_corr:
                        drop = t2 if score_map.get(t1, 0) >= score_map.get(t2, 0) else t1
                        removed.add(drop)
                        logger.info(f"Correlation filter: dropping {drop} (corr with {t1 if drop == t2 else t2}={c:.2f})")

        if removed:
            filtered = [it for it in items if it["ticker"] not in removed]
            logger.info(f"Correlation filter: {len(items)} -> {len(filtered)} items")
            return filtered
    except Exception as e:
        logger.debug(f"Correlation check skipped: {e}")

    return items


# ---------------------------------------------------------------------------
# Main agent pipeline entry point
# ---------------------------------------------------------------------------

LLM_BATCH_SIZE = 10


def _batched_news_agent(
    candidates: list[dict],
    market: str,
    max_retries: int,
    progress_cb: Callable[[dict], None] | None = None,
) -> list[dict]:
    """Call News Agent in small batches to avoid LLM timeout."""
    all_results: list[dict] = []
    total = len(candidates)
    for i in range(0, total, LLM_BATCH_SIZE):
        batch = candidates[i : i + LLM_BATCH_SIZE]
        batch_num = i // LLM_BATCH_SIZE + 1
        total_batches = (total + LLM_BATCH_SIZE - 1) // LLM_BATCH_SIZE
        logger.info(f"News Agent batch {batch_num}/{total_batches}: {len(batch)} stocks")

        payload = _build_news_payload(batch, market)
        results = _call_news_agent(payload, max_retries=max_retries)
        if results:
            all_results.extend(results)
            logger.info(f"News Agent batch {batch_num}: got {len(results)} results")
        else:
            logger.warning(f"News Agent batch {batch_num}: no results")

    logger.info(f"News Agent total: {len(all_results)} results from {total} candidates")
    return all_results


def _batched_tech_agent(
    candidates: list[dict],
    market: str,
    max_retries: int,
    progress_cb: Callable[[dict], None] | None = None,
) -> list[dict]:
    """Deterministic scoring as primary, LLM as secondary for borderline cases."""
    det_results = fallback_technical_scores(candidates)
    det_map = {r["ticker"]: r for r in det_results}

    borderline = [c for c in candidates if 45 <= det_map.get(c["ticker"], {}).get("technical_score", 0) <= 60]

    if not borderline:
        logger.info(f"Tech scoring: {len(det_results)} deterministic, 0 borderline -> skip LLM")
        return det_results

    logger.info(f"Tech scoring: {len(det_results)} deterministic, {len(borderline)} borderline -> LLM")
    llm_results: list[dict] = []
    total = len(borderline)
    for i in range(0, total, LLM_BATCH_SIZE):
        batch = borderline[i : i + LLM_BATCH_SIZE]
        payload = _build_tech_payload(batch, market)
        results = _call_tech_agent(payload, max_retries=max_retries)
        if results:
            llm_results.extend(results)

    if llm_results:
        llm_map = {r["ticker"]: r for r in llm_results}
        for ticker, det in det_map.items():
            llm = llm_map.get(ticker)
            if llm:
                blended = int(round(det["technical_score"] * 0.6 + llm["technical_score"] * 0.4))
                final_sc = max(0, min(100, blended))
                det["technical_score"] = final_sc
                det["action"] = "buy" if final_sc >= 60 else ("hold" if final_sc >= 45 else "avoid")
                det["analysis"] = llm.get("analysis", det.get("analysis", ""))
                det["risk_flags"] = list(set(det.get("risk_flags", []) + llm.get("risk_flags", [])))
                if llm.get("risk_note"):
                    det["risk_note"] = llm["risk_note"]

    logger.info(f"Tech Agent total: {len(det_results)} results ({len(llm_results)} LLM-enhanced)")
    return det_results


def run_agent_pipeline(
    enriched: list[dict],
    market: str = "all",
    strategy_type: str = "short",
    progress_cb: Callable[[dict], None] | None = None,
    regime: dict | None = None,
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

    # Layer 3: News Agent (batched)
    _progress(35.0, f"Layer 3: News Agent analyzing {len(candidates)} candidates")
    news_results = _batched_news_agent(candidates, market, max_retries, progress_cb)

    if not news_results:
        logger.warning("News Agent returned no results, sending all to Tech Agent")
        tech_candidates = candidates
    else:
        tech_candidates = run_news_filter(candidates, news_results, top_n=batch_size // 2)

    # Layer 4: Technical Agent (batched)
    _progress(55.0, f"Layer 4: Tech Agent analyzing {len(tech_candidates)} candidates")
    tech_results = _batched_tech_agent(tech_candidates, market, max_retries, progress_cb)

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
        regime=regime,
    )

    _progress(78.0, f"Pipeline complete: {len(recommendations)} recommendations")
    return recommendations
