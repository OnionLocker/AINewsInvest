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
from analysis.news_fetcher import fetch_news, news_quality_report
from pipeline.config import get_config
from pipeline.skills.news_skill import (
    build_news_skill_input, call_news_skill, skill_output_to_legacy as news_to_legacy,
)
from pipeline.skills.tech_skill import (
    build_tech_skill_input, call_tech_skill, skill_output_to_legacy as tech_to_legacy,
)
from pipeline.skills.scorers import score_news_output, score_tech_output


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
    _news_quality_samples: list[dict] = []  # collect quality reports per ticker
    for c in enriched:
        ticker = c["ticker"]
        mkt = c.get("market", market)
        news_items = fetch_news(ticker, mkt, limit=12)
        _news_quality_samples.append(news_quality_report(news_items))
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

    # Aggregate news quality across all candidates
    _agg_quality = {
        "avg_items": round(sum(q["item_count"] for q in _news_quality_samples) / max(1, len(_news_quality_samples)), 1),
        "avg_sources": round(sum(q["source_count"] for q in _news_quality_samples) / max(1, len(_news_quality_samples)), 1),
        "has_premium_pct": round(sum(1 for q in _news_quality_samples if q["has_premium"]) / max(1, len(_news_quality_samples)) * 100),
        "overall_tier": "good" if all(q["quality_tier"] == "good" for q in _news_quality_samples)
                        else "poor" if all(q["quality_tier"] == "poor" for q in _news_quality_samples)
                        else "fair",
        "suggested_weight_factor": round(sum(q["suggested_weight_factor"] for q in _news_quality_samples) / max(1, len(_news_quality_samples)), 2),
    }

    return {
        "market": market,
        "candidate_count": len(items),
        "market_context": market_headlines,
        "candidates": items,
        "news_quality": _agg_quality,
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
    MAX_BYPASS = 5  # Cap to prevent runaway candidate lists
    for ns, c in scored[top_n:]:
        if bypass_count >= MAX_BYPASS:
            break
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
    """Relative Strength Index — Wilder's EMA smoothing.

    Uses the same algorithm as technical.py (_rsi_wilder) to avoid
    inconsistencies between fallback scoring and indicator computation.
    """
    if len(closes) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    # Wilder's smoothing: first average is SMA, then EMA with alpha = 1/period
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

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


def _continuous_tech_score(value: float, breakpoints: list[float], scores: list[float]) -> float:
    """Piecewise linear interpolation for continuous tech scoring.

    Given breakpoints [b0, b1, ..., bn] and scores [s0, s1, ..., sn],
    linearly interpolates between adjacent pairs. Values outside the
    range clamp to the nearest endpoint score.
    """
    if value <= breakpoints[0]:
        return scores[0]
    if value >= breakpoints[-1]:
        return scores[-1]
    for i in range(len(breakpoints) - 1):
        if breakpoints[i] <= value <= breakpoints[i + 1]:
            t = (value - breakpoints[i]) / (breakpoints[i + 1] - breakpoints[i])
            return scores[i] + t * (scores[i + 1] - scores[i])
    return 0.0


def fallback_technical_scores(
    enriched: list[dict],
    regime: dict | None = None,
) -> list[dict]:
    """Deterministic fallback when Tech Agent fails — v2 continuous scoring.

    v2 changes over v1:
    - Continuous scoring for RSI, Bollinger, MACD (no more step functions)
    - Market regime awareness (crisis/bearish reduces bullish bonuses)
    - Fixed overbought double-penalty (single continuous penalty, no cap)
    - Volatility penalty proportional to severity
    - Daily/weekly trend conflict detection
    """
    cfg = get_config()
    fb = cfg.agent.fallback

    # Regime multiplier: in crisis, bullish signals less trustworthy
    regime_level = (regime or {}).get("level", "normal")
    regime_bull_mult = {
        "normal": 1.0, "cautious": 0.85, "bearish": 0.65, "crisis": 0.40,
    }.get(regime_level, 1.0)
    regime_bear_mult = {
        "normal": 1.0, "cautious": 1.1, "bearish": 1.25, "crisis": 1.4,
    }.get(regime_level, 1.0)

    results = []
    for c in enriched:
        ticker = c["ticker"]
        price = _safe_float(c.get("price"))
        if price <= 0:
            continue

        signals = c.get("signals", {})
        score = float(fb.base_score)
        risk_flags: list[str] = []

        # --- MA alignment ---
        if signals.get("ma_bullish_align"):
            score += fb.ma_bullish_bonus * regime_bull_mult
            if signals.get("ma_short_golden_cross"):
                score += fb.ma_short_golden_bonus * regime_bull_mult
        elif signals.get("ma_bearish_align"):
            score -= fb.ma_bearish_penalty * regime_bear_mult

        # --- Volume ratio (continuous) ---
        vol_ratio = _safe_float(c.get("volume_ratio", 1.0))
        vol_score = _continuous_tech_score(
            vol_ratio,
            [0.5, 0.7, 1.0, 1.3, 1.5, 2.0, 3.0],
            [-4.0, -2.0, 0.0, 4.0, 8.0, 10.0, 10.0],
        )
        score += vol_score * regime_bull_mult if vol_score > 0 else vol_score

        # --- Overbought / MA20 bias (continuous, replaces old cap+penalty) ---
        ma20_bias = _safe_float(c.get("ma20_bias_pct"))
        if ma20_bias > 5:
            overbought_penalty = _continuous_tech_score(
                ma20_bias,
                [5.0, 10.0, 15.0, 20.0, 30.0],
                [0.0, -4.0, -10.0, -16.0, -20.0],
            )
            score += overbought_penalty * regime_bear_mult
            if ma20_bias > 15:
                risk_flags.append("\u8d85\u4e70\u504f\u79bb")

        # --- Volume-price divergence ---
        if signals.get("volume_price_divergence"):
            score -= 12.0 * regime_bear_mult
            risk_flags.append("\u91cf\u4ef7\u80cc\u79bb")

        # --- Volatility (proportional, not just -3) ---
        vol_20d = _safe_float(c.get("volatility_20d", 0.02))
        vol_penalty = _continuous_tech_score(
            vol_20d,
            [0.01, 0.02, 0.03, 0.04, 0.06],
            [2.0, 0.0, -3.0, -6.0, -10.0],
        )
        score += vol_penalty
        if c.get("volatility_class") == "high":
            risk_flags.append("\u9ad8\u6ce2\u52a8")

        # --- Weekly trend + conflict detection ---
        weekly_trend = c.get("weekly_trend", "neutral")
        daily_bullish = signals.get("ma_bullish_align", False)
        daily_bearish = signals.get("ma_bearish_align", False)

        if weekly_trend == "bearish":
            score -= 8.0 * regime_bear_mult
        elif weekly_trend == "bullish":
            score += 3.0 * regime_bull_mult

        if daily_bullish and weekly_trend == "bearish":
            score -= 4.0
            risk_flags.append("\u65e5\u5468\u8d8b\u52bf\u77db\u76fe")
        elif daily_bearish and weekly_trend == "bullish":
            score += 2.0

        rsi_val = None
        macd_hist_val = None
        bb_pos_val = None
        obv_trend_val = None

        klines_1 = c.get("kline_recent_part1") or []
        klines_2 = c.get("kline_recent_part2") or []
        all_klines = klines_1 + klines_2
        if len(all_klines) >= 14:
            kl_closes = [float(k.get("close", 0)) for k in all_klines if k.get("close")]
            kl_volumes = [float(k.get("volume", 0)) for k in all_klines if k.get("volume")]

            if len(kl_closes) >= 14:
                rsi = _compute_rsi(kl_closes)
                rsi_val = rsi
                # Continuous RSI:
                # 15→+10, 25→+6, 30→+3, 40→+1, 50→0, 60→-1, 70→-4, 75→-8, 85→-12
                rsi_score = _continuous_tech_score(
                    rsi,
                    [15.0, 25.0, 30.0, 40.0, 50.0, 60.0, 70.0, 75.0, 85.0],
                    [10.0, 6.0, 3.0, 1.0, 0.0, -1.0, -4.0, -8.0, -12.0],
                )
                score += rsi_score

            if len(kl_closes) >= 20:
                bb_pos = _compute_bollinger_position(kl_closes)
                bb_pos_val = bb_pos
                # Continuous BB:
                # 0.0→+6, 0.05→+4, 0.20→+1, 0.50→0, 0.80→-1, 0.95→-5, 1.0→-7
                bb_score = _continuous_tech_score(
                    bb_pos,
                    [0.0, 0.05, 0.20, 0.50, 0.80, 0.95, 1.0],
                    [6.0, 4.0, 1.0, 0.0, -1.0, -5.0, -7.0],
                )
                score += bb_score

                macd_val, signal_val, macd_hist = _compute_macd(kl_closes)
                macd_hist_val = macd_hist
                # MACD: normalize by price for cross-stock comparability
                macd_norm = macd_hist / max(kl_closes[-1], 1.0) * 100
                macd_score = _continuous_tech_score(
                    macd_norm,
                    [-0.5, -0.2, 0.0, 0.2, 0.5],
                    [-5.0, -3.0, 0.0, 3.0, 5.0],
                )
                score += macd_score

            if len(kl_closes) >= 14 and len(kl_volumes) >= 14:
                obv_trend = _compute_obv_trend(kl_closes, kl_volumes)
                obv_trend_val = obv_trend
                if obv_trend == "bullish":
                    score += 3.0 * regime_bull_mult
                elif obv_trend == "bearish":
                    score -= 3.0 * regime_bear_mult

        score = max(0, min(100, int(round(score))))

        # Action thresholds (regime-adjusted)
        buy_threshold = 60 if regime_level in ("normal", "cautious") else 65
        hold_threshold = 45 if regime_level in ("normal", "cautious") else 50

        action = "buy" if score >= buy_threshold else ("hold" if score >= hold_threshold else "avoid")
        risk_note = ""
        if "\u8d85\u4e70\u504f\u79bb" in risk_flags:
            if score >= buy_threshold:
                action = "hold"
            risk_note = "MA20\u504f\u79bb\u8d85\u8fc715%\uff0c\u6709\u8d85\u4e70\u98ce\u9669"
        elif "\u91cf\u4ef7\u80cc\u79bb" in risk_flags:
            risk_note = "20\u65e5\u9ad8\u70b9\u91cf\u4ef7\u80cc\u79bb"

        results.append({
            "ticker": ticker,
            "technical_score": score,
            "action": action,
            "analysis": "\u57fa\u4e8e\u89c4\u5219\u7684\u6280\u672f\u9762\u8bc4\u5206(v2: \u8fde\u7eed\u51fd\u6570+\u4f53\u5236\u611f\u77e5)",
            "risk_flags": risk_flags,
            "risk_note": risk_note,
            "position_note": "",
            "rsi": rsi_val,
            "macd_histogram": macd_hist_val,
            "bollinger_position": bb_pos_val,
            "obv_trend": obv_trend_val,
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
    is_breakout: bool = False,
) -> dict[str, Any]:
    """Compute entry/SL/TP purely from code. Never trust LLM prices.

    v4 changes:
    - Breakout entry: entry AT or slightly above current price (chase breakout)
    - Pullback entry: entry below current price (wait for dip)
    - R:R < 1.5 → reject trade (return _rejected=True), don't force-adjust
    """
    cfg = get_config()
    strat = cfg.swing if strategy_type == "swing" else cfg.short_term

    _rejected_result = {
        "entry_price": 0, "entry_2": 0,
        "stop_loss": 0, "take_profit": 0,
        "take_profit_2": 0, "take_profit_3": 0,
        "holding_days": strat.default_holding_days,
        "trailing_activation_price": 0,
        "trailing_distance_pct": 0,
        "_rejected": True,
    }

    if price <= 0:
        return _rejected_result

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

    # --- FIX 4: Breakout vs Pullback entry ---
    if is_breakout:
        # Breakout entry: buy at or near current price (don't wait for pullback)
        # The stock just broke resistance with volume — waiting = missing the move
        entry_price = round(price * 1.002, 2)  # tiny premium (market order simulation)
        entry_2 = round(price * 0.99, 2)       # partial fill on minor pullback
    else:
        # Pullback entry: limit order below current price
        if strategy_type == "swing":
            max_discount = 0.04
            secondary_discount = 0.06
        else:
            max_discount = 0.02
            secondary_discount = 0.035

        if action_bucket == "strong_buy":
            entry_price = round(price * 0.997, 2)
        elif action_bucket == "buy":
            if support_hold_strength in ("strong", "moderate") and support_1 < price:
                entry_price = round(support_1 * 1.01, 2)
                if entry_price < price * (1 - max_discount):
                    entry_price = round(price * (1 - max_discount * 0.7), 2)
            elif ma20 > 0 and ma20 < price:
                entry_price = round(ma20 * 1.005, 2)
                if entry_price < price * (1 - max_discount):
                    entry_price = round(price * (1 - max_discount * 0.7), 2)
            else:
                entry_price = round(price * (1 - max_discount * 0.5), 2)
        else:
            entry_price = round(price * (1 - max_discount), 2)

        entry_price = min(entry_price, price)
        entry_price = max(entry_price, round(price * (1 - max_discount), 2))
        entry_2 = round(entry_price * 0.985, 2)
        entry_2 = max(entry_2, round(price * (1 - secondary_discount), 2))

    # Volatility-based holding days
    if volatility_class == "high":
        stop_buffer_pct = 0.025
        holding_days = 3
    elif volatility_class == "low":
        stop_buffer_pct = 0.012
        holding_days = strat.default_holding_days
    else:
        stop_buffer_pct = 0.018
        holding_days = strat.default_holding_days

    # --- Stop Loss: ATR-based, tighter for breakout ---
    atr_pct = atr_20d / price if (atr_20d > 0 and price > 0) else 0

    if atr_20d > 0:
        if is_breakout:
            # Breakout SL: tighter — if it falls back below breakout level, thesis is wrong
            # Use 1.0 × ATR (tighter than normal 1.5×)
            sl_atr = entry_price - atr_20d * (strat.atr_sl_multiplier * 0.67)
            # Also: don't let SL go below the old resistance (now support)
            old_resist = resist_1 if resist_1 < entry_price else support_1
            sl_atr = max(sl_atr, old_resist * 0.99)
        else:
            # Pullback SL: standard 1.5 × ATR
            sl_atr = entry_price - atr_20d * strat.atr_sl_multiplier
            sl_support = support_1 - price * stop_buffer_pct if support_1 < entry_price else sl_atr
            sl_atr = max(sl_atr, sl_support)
        # Bound: 1.5% to 6% from entry
        stop_loss = max(sl_atr, round(entry_price * (1 - strat.sl_max_pct), 2))
        stop_loss = min(stop_loss, round(entry_price * (1 - strat.sl_min_pct), 2))
    else:
        stop_from_support = round(support_1 - price * stop_buffer_pct, 2)
        stop_from_default = round(entry_price * strat.default_stop_loss_pct, 2)
        stop_loss = max(stop_from_support, stop_from_default)
    stop_loss = round(stop_loss, 2)

    # --- Take Profit: ATR-based primary, resistance as reference ---
    if atr_20d > 0:
        tp_atr = entry_price + atr_20d * strat.atr_tp_multiplier
        if is_breakout:
            # Breakout: resistance already broken, use full ATR target
            # Old resistance is now support — upside is open
            take_profit = round(tp_atr, 2)
        else:
            # Pullback: use ATR target unless a strong resistance is
            # reachable and far enough to yield good R:R
            dist_to_resist = resist_1 - entry_price
            if dist_to_resist > atr_20d * 1.5:
                # Resistance is far — use it as a natural TP
                take_profit = round(resist_1 * 0.99, 2)
            else:
                # Resistance is close (< 1.5 ATR) — expect breakout, use ATR TP
                take_profit = round(tp_atr, 2)
        take_profit = max(take_profit, round(entry_price * 1.025, 2))
    else:
        take_profit = round(max(resist_1 * 0.98, entry_price * strat.default_take_profit_pct), 2)
        take_profit = max(take_profit, round(entry_price * 1.025, 2))

    # --- FIX 5: R:R reject — don't force-adjust, just reject ---
    MIN_RR = 1.5
    risk = entry_price - stop_loss
    reward = take_profit - entry_price
    if risk <= 0 or reward <= 0:
        return _rejected_result
    rr_ratio = reward / risk
    if rr_ratio < MIN_RR:
        logger.debug(
            f"R:R reject: entry={entry_price} sl={stop_loss} tp={take_profit} "
            f"risk={risk:.2f} reward={reward:.2f} R:R={rr_ratio:.2f} < {MIN_RR}"
        )
        return _rejected_result

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
        "trailing_activation_price": round(
            entry_price + (take_profit - entry_price) * strat.trailing_activation_pct, 2
        ),
        "trailing_distance_pct": strat.trailing_distance_pct,
        "_rejected": False,
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
            "trailing_activation_price": 0,
            "trailing_distance_pct": 0,
            "_rejected": True,
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

    # R:R reject for short trades
    reward_short = entry_price - take_profit
    if risk <= 0 or reward_short <= 0 or reward_short / risk < min_rr:
        return {
            "entry_price": 0, "entry_2": 0,
            "stop_loss": 0, "take_profit": 0,
            "take_profit_2": 0, "take_profit_3": 0,
            "holding_days": strat.default_holding_days,
            "trailing_activation_price": 0,
            "trailing_distance_pct": 0,
            "_rejected": True,
        }

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
        "trailing_activation_price": round(
            entry_price - (entry_price - take_profit) * strat.trailing_activation_pct, 2
        ),
        "trailing_distance_pct": strat.trailing_distance_pct,
        "_rejected": False,
    }


# ---------------------------------------------------------------------------
# Layer 5: Score synthesis
# ---------------------------------------------------------------------------

def _compute_confidence(
    ns: int, ts: int, news: dict, tech: dict,
    fundamental_score: int = 50,
) -> int:
    """Compute confidence — how much agreement and conviction across signals.

    v6: Multi-dimensional confidence with continuous adjustments.

    Dimensions:
    1. Direction agreement (news vs tech action)
    2. Score convergence (gap between news & tech scores)
    3. Fundamental alignment (does fundamental score agree?)
    4. Risk flag penalty (more flags = less confident)
    5. Signal source quality (LLM-backed vs fallback)

    Returns: confidence in [10, 95]
    """
    confidence = 50.0  # baseline

    # --- 1. Direction agreement (most important, ~30pt swing) ---
    news_action = _classify_action(str(news.get("action", "hold")))
    tech_action = _classify_action(str(tech.get("action", "hold")))

    bull_actions = ("buy", "strong_buy")
    bear_actions = ("avoid", "short")

    if news_action in bull_actions and tech_action in bull_actions:
        # Both bullish — high agreement
        bonus = 20.0
        if news_action == "strong_buy" and tech_action == "strong_buy":
            bonus = 28.0  # extra conviction for both strong_buy
        elif news_action == "strong_buy" or tech_action == "strong_buy":
            bonus = 24.0
        confidence += bonus
    elif news_action in bear_actions and tech_action in bear_actions:
        confidence += 18.0  # bearish agreement (slightly lower — shorts are harder)
    elif (news_action in bull_actions and tech_action in bear_actions) or \
         (tech_action in bull_actions and news_action in bear_actions):
        confidence -= 28.0  # direct contradiction — very bad
    elif news_action == "hold" and tech_action == "hold":
        confidence -= 5.0  # both uncertain
    elif news_action == "hold" or tech_action == "hold":
        confidence += 3.0  # one directional, one neutral — mild

    # --- 2. Score convergence (continuous, ~20pt swing) ---
    score_gap = abs(ns - ts)
    # Gap: 0→+15, 10→+10, 20→+3, 30→-5, 40→-12, 50+→-18
    gap_adj = _continuous_tech_score(
        float(score_gap),
        [0.0, 10.0, 20.0, 30.0, 40.0, 50.0],
        [15.0, 10.0, 3.0, -5.0, -12.0, -18.0],
    )
    confidence += gap_adj

    # --- 3. Fundamental alignment (~8pt swing) ---
    # If news+tech say buy but fundamentals are terrible, lower confidence
    avg_signal = (ns + ts) / 2
    if avg_signal >= 60 and fundamental_score >= 55:
        confidence += 5.0  # signals + fundamentals agree
    elif avg_signal >= 60 and fundamental_score < 35:
        confidence -= 8.0  # bullish signals but terrible fundamentals
    elif avg_signal <= 40 and fundamental_score <= 35:
        confidence += 4.0  # bearish agreement with weak fundamentals

    # --- 4. Both scores strong in same direction ---
    if ns >= 70 and ts >= 70:
        confidence += 8.0  # double strong bullish
    elif ns <= 30 and ts <= 30:
        confidence += 6.0  # double strong bearish

    # --- 5. Risk flag penalty (continuous) ---
    n_risks = len(news.get("risk_flags") or []) + len(tech.get("risk_flags") or [])
    if n_risks > 0:
        # 1 flag → -2, 3 flags → -6, 5 flags → -12, 8+ → -18
        risk_penalty = _continuous_tech_score(
            float(n_risks),
            [0.0, 1.0, 3.0, 5.0, 8.0],
            [0.0, -2.0, -6.0, -12.0, -18.0],
        )
        confidence += risk_penalty

    # --- 6. Signal source quality ---
    # If tech analysis is from LLM (has structured skill output), it's more reliable
    if tech.get("_skill_output"):
        confidence += 3.0  # LLM-validated tech score
    # If analysis text is the fallback boilerplate, slightly less confident
    if "v2:" in str(tech.get("analysis", "")) or not tech.get("analysis"):
        confidence -= 2.0  # fallback-only scoring

    return max(10, min(95, int(round(confidence))))


def synthesize_agent_results(
    enriched: list[dict],
    news_results: list[dict],
    tech_results: list[dict],
    strategy_type: str = "short",
    max_count: int | None = None,
    regime: dict | None = None,
) -> list[dict]:
    """Combine news + tech scores into ranked recommendations.

    v4 changes:
    - Real confidence (agent agreement, not just score)
    - Filter out hold/contradictory signals
    - No sector_bonus inflation
    - Breakout vs pullback entry routing
    - R:R reject (not force-adjust)
    v5 changes:
    - News quality aware: auto-reduce news_weight when data is degraded
    """
    cfg = get_config()
    syn = cfg.synthesis
    regime_level = (regime or {}).get("level", "normal")

    if strategy_type == "swing":
        news_weight = cfg.swing.news_weight
        tech_weight = cfg.swing.tech_weight
    else:
        news_weight = syn.news_weight
        tech_weight = syn.tech_weight

    # --- v5: News data quality check ---
    # Compute aggregate news quality from what sources actually provided
    nc_cfg = cfg.news
    has_premium_sources = bool(nc_cfg.finnhub_key) or bool(nc_cfg.marketaux_key)
    if not has_premium_sources:
        # No premium news APIs configured — significantly reduce news influence
        news_quality_factor = 0.5
        logger.info(
            f"News quality: no premium sources (Finnhub/MarketAux keys empty). "
            f"Reducing news_weight by {1 - news_quality_factor:.0%}"
        )
        news_weight *= news_quality_factor
        # Re-normalize weights
        total_w = news_weight + tech_weight + syn.fundamental_weight
        news_weight /= total_w
        tech_weight /= total_w
        logger.info(
            f"Adjusted weights: news={news_weight:.3f} tech={tech_weight:.3f} "
            f"fundamental={syn.fundamental_weight / total_w:.3f}"
        )

    # Adaptive weight adjustment based on historical win-rate data
    # v6: Disabled in crisis/bearish — historical correlations unreliable during regime shifts
    if regime_level in ("normal", "cautious"):
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
    else:
        logger.info(f"Adaptive weights disabled in {regime_level} regime")

    min_score = syn.min_confidence  # v6: renamed semantically — this is a score threshold
    quality_threshold = max(syn.quality_threshold, 55)  # v6: safety floor — never show trades for <55

    regime_level = (regime or {}).get("level", "normal")
    if regime_level == "bearish":
        min_score = min(95, min_score + 10)
        quality_threshold = min(90, quality_threshold + 5)
        logger.info(f"Bearish regime: min_score raised to {min_score}")
    elif regime_level == "crisis":
        min_score = min(95, min_score + 20)
        quality_threshold = min(90, quality_threshold + 10)
        logger.info(f"Crisis regime: min_score raised to {min_score}")

    if max_count is None:
        max_count = cfg.max_recommendations

    news_map = {r["ticker"]: r for r in news_results}
    tech_map = {r["ticker"]: r for r in tech_results}

    NEUTRAL = 50
    BLEND = syn.cross_fill_factor

    all_scored: list[dict] = []
    skipped_hold = 0
    skipped_contradiction = 0
    skipped_rr = 0

    for c in enriched:
        ticker = c["ticker"]
        news = news_map.get(ticker, {})
        tech = tech_map.get(ticker, {})

        if not news and not tech:
            continue

        ns = _safe_int(news.get("news_score", 0))
        ts = _safe_int(tech.get("technical_score", 0))

        # v6: Cross-fill with source penalty — if one signal is missing,
        # we fill a diluted estimate AND penalize confidence later
        _has_news = bool(news)
        _has_tech = bool(tech)
        if not _has_news and _has_tech:
            ns = int(NEUTRAL + (ts - NEUTRAL) * BLEND)
        elif _has_news and not _has_tech:
            ts = int(NEUTRAL + (ns - NEUTRAL) * BLEND)

        # --- FIX 1: Real confidence (agent agreement + fundamentals) ---
        fs = _safe_int(c.get("fundamental_score", 50))
        confidence = _compute_confidence(ns, ts, news, tech, fundamental_score=fs)

        # v6: Penalize confidence when one signal source is missing/synthetic
        if not _has_news:
            confidence = max(10, confidence - 12)
        if not _has_tech:
            confidence = max(10, confidence - 15)  # tech missing is worse

        # --- FIX 2: Filter contradictory signals ---
        news_action = _classify_action(str(news.get("action", "hold")))
        tech_action = _classify_action(str(tech.get("action", "hold")))

        # Skip if both agents say "hold" — no conviction either way
        if news_action == "hold" and tech_action == "hold":
            skipped_hold += 1
            continue

        # Skip if agents directly contradict (one buy, one avoid/short)
        buy_actions = ("buy", "strong_buy")
        bear_actions = ("avoid", "short")
        if (news_action in buy_actions and tech_action in bear_actions) or \
           (tech_action in buy_actions and news_action in bear_actions):
            skipped_contradiction += 1
            logger.debug(
                f"Signal contradiction {ticker}: news={news_action} tech={tech_action}, skipping"
            )
            continue

        # --- Combined score (no sector_bonus inflation) ---
        # fs already computed above for confidence calculation
        fw = syn.fundamental_weight
        if fw > 0:
            total_w = news_weight + tech_weight + fw
            combined = int(round(
                (ns * news_weight + ts * tech_weight + fs * fw) / total_w
            ))
        else:
            combined = int(round(ns * news_weight + ts * tech_weight))
        combined = max(0, min(100, combined))
        # FIX 3: sector_bonus REMOVED — was inflating scores unreliably

        price = _safe_float(c.get("price"))
        if price <= 0:
            continue

        action_str = str(tech.get("action", news.get("action", "hold")))
        action_bucket = _classify_action(action_str)
        market_str = c.get("market", "")

        # FIX 2b: Skip direction="hold" — don't recommend stocks without conviction
        if action_bucket == "hold":
            skipped_hold += 1
            continue

        is_short = (
            action_bucket == "short"
            and market_str == "us_stock"
        )

        # --- FIX 4: Route to breakout vs pullback entry ---
        signals = c.get("signals", {})
        is_breakout = (
            signals.get("broke_20d_high", False)
            and signals.get("volume_expansion", False)
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
                is_breakout=is_breakout,
            )
            direction = "buy"

        # --- FIX 5: R:R reject — if trade params are invalid, skip ---
        if trade.get("_rejected"):
            logger.warning(
                f"R:R reject {ticker}: insufficient reward-to-risk, skipping recommendation"
            )
            skipped_rr += 1
            continue

        is_quality = combined >= quality_threshold and confidence >= 50

        all_risk_flags = list(set(
            list(news.get("risk_flags") or []) +
            list(tech.get("risk_flags") or [])
        ))

        holding_days_final = trade["holding_days"]
        earnings_imminent = c.get("earnings_imminent", False)
        earnings_days = c.get("earnings_days_away")
        if earnings_imminent and earnings_days is not None and earnings_days >= 0:
            all_risk_flags.append("\u4e34\u8fd1\u8d22\u62a5")
            if earnings_days < holding_days_final:
                holding_days_final = max(1, earnings_days - 1)

        news_analysis = str(news.get("analysis", ""))
        tech_analysis = str(tech.get("analysis", ""))

        fin = c.get("financial") or {}
        sector = fin.get("sector", "") or ""
        insider_trades_data = c.get("insider_trades")
        insider_signal = ""
        if insider_trades_data and isinstance(insider_trades_data, dict):
            insider_signal = insider_trades_data.get("signal_strength", "")

        # --- Compute R:R for position sizing ---
        _entry = trade.get("entry_price", 0) or 0
        _sl = trade.get("stop_loss", 0) or 0
        _tp = trade.get("take_profit", 0) or 0
        if direction == "short":
            _risk = _sl - _entry if (_sl and _entry) else 1
            _reward = _entry - _tp if (_entry and _tp) else 0
        else:
            _risk = _entry - _sl if (_entry and _sl) else 1
            _reward = _tp - _entry if (_tp and _entry) else 0
        _rr_ratio = _reward / _risk if _risk > 0 else 0.0

        _pos_pct, _pos_rationale = _suggest_position_pct(
            score=combined,
            regime_level=regime_level,
            confidence=confidence,
            volatility_class=str(c.get("volatility_class", "medium")),
            risk_flag_count=len(all_risk_flags),
            rr_ratio=_rr_ratio,
            strategy_type=strategy_type,
        )

        all_scored.append({
            "ticker": ticker,
            "name": c.get("name", ticker),
            "market": market_str,
            "strategy": "swing" if strategy_type == "swing" else "short_term",
            "direction": direction,
            "score": round(combined, 2),
            "confidence": confidence,
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
            "trailing_activation_price": trade.get("trailing_activation_price", 0) if is_quality else 0,
            "trailing_distance_pct": trade.get("trailing_distance_pct", 0) if is_quality else 0,
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
            "position_pct": _pos_pct,
            "position_rationale": _pos_rationale,
            "earnings_days_away": c.get("earnings_days_away"),
            "earnings_date_str": c.get("earnings_date_str"),
            "position_note": str(tech.get("position_note", "")),
            "themes": news.get("themes", []) if isinstance(news.get("themes"), list) else [],
            "price": price,
            "change_pct": _safe_float(c.get("change_pct")),
            "sector": sector,
            "rsi": tech.get("rsi"),
            "macd_histogram": tech.get("macd_histogram"),
            "bollinger_position": tech.get("bollinger_position"),
            "obv_trend": tech.get("obv_trend"),
            "options_signal": c.get("options_signal", ""),
            "options_pc_ratio": c.get("options_pc_ratio"),
            "options_unusual_activity": bool(c.get("options_unusual_activity")),
            "insider_signal": insider_signal,
            # Skill structured outputs (for recording/backtesting)
            "_news_skill_output": news.get("_skill_output"),
            "_tech_skill_output": tech.get("_skill_output"),
        })

    if skipped_hold or skipped_contradiction or skipped_rr:
        logger.info(
            f"Synthesis filter: skipped {skipped_hold} hold + "
            f"{skipped_contradiction} contradictions + {skipped_rr} R:R rejects"
        )

    # v6: conviction_score = score × (confidence/100)^0.7
    # The exponent 0.7 means confidence matters but doesn't dominate.
    # A 75-score / 80-confidence stock beats a 70-score / 90-confidence stock.
    for s in all_scored:
        s["conviction_score"] = round(
            s["combined_score"] * (s["confidence"] / 100.0) ** 0.7, 2
        )

    all_scored.sort(key=lambda x: x["conviction_score"], reverse=True)

    # v6: Dual filter — score AND confidence must pass thresholds
    min_conf_threshold = 50  # absolute confidence floor
    filtered = [
        s for s in all_scored
        if s["combined_score"] >= min_score and s["confidence"] >= min_conf_threshold
    ]

    if not filtered:
        top_score = all_scored[0]["combined_score"] if all_scored else 0
        top_conf = all_scored[0]["confidence"] if all_scored else 0
        logger.info(
            f"No stocks passed min_score={min_score} & min_conf={min_conf_threshold} "
            f"(top: score={top_score}, conf={top_conf}). Sit out today."
        )
        return []

    filtered = _limit_sector_concentration(filtered, max_ratio=0.4)
    filtered = _check_pairwise_correlation(filtered)
    return filtered[:max_count]


def _suggest_position_pct(
    score: int,
    regime_level: str = "normal",
    confidence: int = 60,
    volatility_class: str = "medium",
    risk_flag_count: int = 0,
    rr_ratio: float = 2.0,
    strategy_type: str = "short_term",
) -> tuple[int, str]:
    """Suggest position size as % of portfolio with rationale.

    v4.1: Multi-factor model — score, confidence, volatility, risk flags,
    R:R, strategy, regime.  Returns (pct, rationale_chinese).
    """
    # 1) Base from score
    if score >= 85:
        base = 8
    elif score >= 75:
        base = 6
    elif score >= 65:
        base = 4
    else:
        base = 3

    pct = float(base)
    reasons: list[str] = [f"基础仓位{base}%(评分{score:.0f})"]

    # 2) Confidence multiplier
    if confidence >= 80:
        pct *= 1.20
        reasons.append(f"高置信度{confidence}%↑")
    elif confidence < 60:
        pct *= 0.70
        reasons.append(f"低置信度{confidence}%↓")

    # 3) Volatility
    if volatility_class == "high":
        pct *= 0.70
        reasons.append("高波动↓")
    elif volatility_class == "low":
        pct *= 1.10
        reasons.append("低波动↑")

    # 4) Risk flags
    if risk_flag_count >= 5:
        pct *= 0.60
        reasons.append(f"{risk_flag_count}个风险标记↓↓")
    elif risk_flag_count >= 3:
        pct *= 0.80
        reasons.append(f"{risk_flag_count}个风险标记↓")

    # 5) R:R ratio
    if rr_ratio >= 2.5:
        pct *= 1.15
        reasons.append(f"R:R={rr_ratio:.1f}↑")
    elif rr_ratio < 1.8:
        pct *= 0.85
        reasons.append(f"R:R={rr_ratio:.1f}↓")

    # 6) Strategy type
    if strategy_type == "swing":
        pct *= 0.90
        reasons.append("波段策略↓")

    # 7) Regime
    if regime_level == "cautious":
        pct *= 0.70
        reasons.append("谨慎市况↓")
    elif regime_level in ("bearish", "crisis"):
        pct *= 0.50
        reasons.append("熊市/危机↓↓")

    final_pct = max(2, min(10, round(pct)))
    rationale = "，".join(reasons) + f" → {final_pct}%"

    return final_pct, rationale


def _limit_sector_concentration(
    items: list[dict], max_ratio: float = 0.4,
) -> list[dict]:
    """Ensure no single sector exceeds max_ratio of the final list.

    v6: Uses real sector field (from yfinance financials) instead of themes[0].
    """
    if not items or len(items) <= 2:
        return items
    max_per = max(1, int(len(items) * max_ratio))
    counts: dict[str, int] = {}
    selected: list[dict] = []
    for item in items:
        # v6: Prefer real sector, fall back to themes, then _other
        sector = item.get("sector", "")
        if not sector:
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
    """Call NewsSkill in small batches, then score with deterministic scorer.

    New Skill-based flow:
    1. Build structured input for each batch
    2. Call NewsSkill LLM → get structured catalysts/risks
    3. Score each output with score_news_output() (deterministic)
    4. Return results in legacy format for downstream compatibility
    """
    all_results: list[dict] = []
    total = len(candidates)
    market_regime = "neutral"

    for i in range(0, total, LLM_BATCH_SIZE):
        batch = candidates[i : i + LLM_BATCH_SIZE]
        batch_num = i // LLM_BATCH_SIZE + 1
        total_batches = (total + LLM_BATCH_SIZE - 1) // LLM_BATCH_SIZE
        logger.info(f"NewsSkill batch {batch_num}/{total_batches}: {len(batch)} stocks")

        skill_input = build_news_skill_input(batch, market)
        response = call_news_skill(skill_input, max_retries=max_retries)

        if response.market_regime != "neutral":
            market_regime = response.market_regime

        if response.results:
            for so in response.results:
                legacy = news_to_legacy(so)
                # Deterministic scoring
                score = score_news_output(
                    so.model_dump(),
                    market_regime=market_regime,
                )
                legacy["news_score"] = max(0, min(100, int(round(score))))
                all_results.append(legacy)
            logger.info(f"NewsSkill batch {batch_num}: {len(response.results)} results scored")
        else:
            # Fallback: give neutral scores to batch
            for c in batch:
                all_results.append({
                    "ticker": c["ticker"],
                    "news_score": 50,
                    "sentiment": "neutral",
                    "action": "hold",
                    "analysis": "新闻数据不足，中性评估",
                    "risk_flags": ["信号不足"],
                    "risk_note": "",
                    "sector_bonus": 0,
                    "themes": [],
                    "_skill_output": None,
                })
            logger.warning(f"NewsSkill batch {batch_num}: no results, using neutral fallback")

    logger.info(f"NewsSkill total: {len(all_results)} results from {total} candidates")
    return all_results


def _batched_tech_agent(
    candidates: list[dict],
    market: str,
    max_retries: int,
    progress_cb: Callable[[dict], None] | None = None,
    regime: dict | None = None,
    strategy_type: str = "short",
) -> list[dict]:
    """Hybrid scoring: deterministic primary + TechSkill LLM for borderline.

    New Skill-based flow:
    1. ALL candidates get deterministic fallback scores (hard indicators)
    2. Find borderline cases (score 45-60)
    3. Call TechSkill LLM for borderline → structured patterns/trend/setup
    4. Score LLM output with score_tech_output() (60% hard + 40% soft)
    5. Blend: for borderline cases, replace deterministic with hybrid score
    """
    det_results = fallback_technical_scores(candidates, regime=regime)
    det_map = {r["ticker"]: r for r in det_results}

    # Build enriched lookup for indicators
    enriched_map = {c["ticker"]: c for c in candidates}

    # v2: Expanded LLM verification scope
    # - Borderline (40-65): uncertain zone, LLM decides
    # - High score (>70): verify against false positives
    # Only truly clear scores (65-70 or <40) skip LLM
    llm_candidates = []
    for c in candidates:
        det_score = det_map.get(c["ticker"], {}).get("technical_score", 0)
        if 40 <= det_score <= 65 or det_score > 70:
            llm_candidates.append(c)

    if not llm_candidates:
        logger.info(f"TechSkill: {len(det_results)} deterministic, 0 need LLM -> skip")
        return det_results

    logger.info(f"TechSkill: {len(det_results)} deterministic, {len(llm_candidates)} -> LLM verification")
    skill_outputs: dict[str, dict] = {}

    total = len(llm_candidates)
    for i in range(0, total, LLM_BATCH_SIZE):
        batch = llm_candidates[i : i + LLM_BATCH_SIZE]
        skill_input = build_tech_skill_input(batch, market)
        response = call_tech_skill(skill_input, max_retries=max_retries)

        for so in response.results:
            skill_outputs[so.ticker] = so

    if skill_outputs:
        for ticker, det in det_map.items():
            so = skill_outputs.get(ticker)
            if so is None:
                continue

            # Build indicators dict for scorer
            c = enriched_map.get(ticker, {})
            indicators = {
                "ma5": _safe_float(c.get("ma5")),
                "ma10": _safe_float(c.get("ma10")),
                "ma20": _safe_float(c.get("ma20")),
                "ma60": _safe_float(c.get("ma60")),
                "rsi": det.get("rsi"),
                "macd_histogram": det.get("macd_histogram"),
                "bollinger_position": det.get("bollinger_position"),
                "volume_ratio_5d_20d": _safe_float(c.get("volume_ratio")),
                "weekly_trend": c.get("weekly_trend", "neutral"),
            }
            signals = c.get("signals", {})

            # Hybrid score via scorer (strategy-aware hard/soft weights)
            hybrid_score = score_tech_output(
                so.model_dump(),
                indicators=indicators,
                signals=signals,
                strategy_type=strategy_type,
            )
            final_sc = max(0, min(100, int(round(hybrid_score))))

            det["technical_score"] = final_sc
            det["action"] = "buy" if final_sc >= 60 else ("hold" if final_sc >= 45 else "avoid")

            # Enrich with LLM analysis
            legacy = tech_to_legacy(so)
            det["analysis"] = legacy.get("analysis", det.get("analysis", ""))
            det["risk_flags"] = list(set(det.get("risk_flags", []) + legacy.get("risk_flags", [])))
            if legacy.get("risk_note"):
                det["risk_note"] = legacy["risk_note"]
            det["position_note"] = legacy.get("position_note", "")
            det["_skill_output"] = so.model_dump()

    logger.info(f"TechSkill total: {len(det_results)} results ({len(skill_outputs)} LLM-enhanced)")
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

    # Layer 3: NewsSkill (batched)
    _progress(35.0, f"Layer 3: NewsSkill analyzing {len(candidates)} candidates")
    news_results = _batched_news_agent(candidates, market, max_retries, progress_cb)

    if not news_results:
        logger.warning("NewsSkill returned no results, sending all to TechSkill")
        tech_candidates = candidates
    else:
        tech_candidates = run_news_filter(candidates, news_results, top_n=batch_size // 2)

    # Layer 4: TechSkill (batched, hybrid deterministic + LLM)
    _progress(55.0, f"Layer 4: TechSkill analyzing {len(tech_candidates)} candidates")
    tech_results = _batched_tech_agent(
        tech_candidates, market, max_retries, progress_cb,
        regime=regime, strategy_type=strategy_type,
    )

    if not tech_results:
        logger.warning("TechSkill returned no results, using fallback scoring")
        tech_results = fallback_technical_scores(tech_candidates, regime=regime)

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
