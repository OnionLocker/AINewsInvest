# -*- coding: utf-8 -*-
"""Deterministic scoring functions for Skill outputs.

These functions convert structured LLM outputs (catalysts, patterns, etc.)
into numeric scores using pure code. The scores are 100% reproducible
and backtestable — given the same Skill output, the score is always identical.

Two scoring functions:
  - score_news_output(): NewsSkillOutput → float [0, 100]
  - score_tech_output(): TechSkillOutput + indicators → float [0, 100]
"""
from __future__ import annotations

from typing import Any

from loguru import logger


# ---------------------------------------------------------------------------
# NewsSkill Scorer
# ---------------------------------------------------------------------------

# Tunable parameters — these can be optimized via backtesting
NEWS_PARAMS = {
    # Catalyst magnitude multipliers
    "magnitude_major": 3.0,
    "magnitude_moderate": 2.0,
    "magnitude_minor": 1.0,

    # Impact direction
    "impact_positive": 1.0,
    "impact_negative": -1.0,
    "impact_neutral": 0.0,

    # Time horizon weights (short-term trading focus)
    "horizon_short_term": 1.0,
    "horizon_medium_term": 0.4,
    "horizon_long_term": 0.1,

    # Per-catalyst score contribution scale
    "catalyst_scale": 8.0,

    # Risk severity penalties
    "severity_critical": -15.0,
    "severity_severe": -10.0,
    "severity_moderate": -5.0,
    "severity_minor": -2.0,

    # Risk probability multipliers
    "prob_certain": 1.0,
    "prob_likely": 0.7,
    "prob_possible": 0.4,
    "prob_unlikely": 0.15,

    # Event flag adjustments
    "flag_earnings_just_reported": 3.0,
    "flag_guidance_raised": 8.0,
    "flag_guidance_lowered": -8.0,
    "flag_litigation_risk": -6.0,
    "flag_insider_selling": -4.0,
    "flag_short_squeeze_potential": 5.0,
    "flag_fda_approval": 10.0,

    # Sector sentiment bonus
    "sector_positive": 3.0,
    "sector_neutral_to_positive": 1.5,
    "sector_neutral": 0.0,
    "sector_neutral_to_negative": -1.5,
    "sector_negative": -3.0,

    # Market regime adjustments
    "regime_risk_off_penalty": -5.0,
    "regime_risk_on_bonus": 2.0,

    # Base score
    "base_score": 50.0,
}


def score_news_output(
    skill_output: dict[str, Any],
    market_regime: str = "neutral",
    params: dict[str, float] | None = None,
) -> float:
    """Score a NewsSkillOutput using deterministic rules.

    Args:
        skill_output: dict from NewsSkillOutput.model_dump()
        market_regime: "risk_on" | "risk_off" | "neutral"
        params: optional override for scoring parameters (for optimization)

    Returns:
        Score in [0, 100]
    """
    p = {**NEWS_PARAMS, **(params or {})}
    score = p["base_score"]

    # --- Catalysts ---
    for c in skill_output.get("catalysts", []):
        magnitude = p.get(f"magnitude_{c.get('magnitude', 'minor')}", 1.0)
        impact = p.get(f"impact_{c.get('impact', 'neutral')}", 0.0)
        confidence = max(0.0, min(1.0, float(c.get("confidence", 0.5))))
        horizon = p.get(f"horizon_{c.get('time_horizon', 'short_term')}", 0.5)

        contribution = impact * magnitude * confidence * horizon * p["catalyst_scale"]
        score += contribution

    # --- Risks ---
    for r in skill_output.get("risks", []):
        severity = p.get(f"severity_{r.get('severity', 'minor')}", -2.0)
        probability = p.get(f"prob_{r.get('probability', 'possible')}", 0.4)
        score += severity * probability

    # --- Event Flags ---
    flags = skill_output.get("event_flags", {})
    for flag_name, flag_value in flags.items():
        if flag_value:
            key = f"flag_{flag_name}"
            if key in p:
                score += p[key]

    # --- Sector Sentiment ---
    sector = skill_output.get("sector_sentiment", "neutral")
    sector_key = f"sector_{sector}"
    score += p.get(sector_key, 0.0)

    # --- Market Regime ---
    if market_regime == "risk_off":
        score += p["regime_risk_off_penalty"]
    elif market_regime == "risk_on":
        score += p["regime_risk_on_bonus"]

    return max(0.0, min(100.0, round(score, 1)))


def explain_news_score(
    skill_output: dict[str, Any],
    market_regime: str = "neutral",
    params: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Return itemized breakdown of how the news score was computed.

    Each item: {"source": str, "detail": str, "contribution": float}
    """
    p = {**NEWS_PARAMS, **(params or {})}
    items = [{"source": "base", "detail": "基准分", "contribution": p["base_score"]}]

    for c in skill_output.get("catalysts", []):
        magnitude = p.get(f"magnitude_{c.get('magnitude', 'minor')}", 1.0)
        impact = p.get(f"impact_{c.get('impact', 'neutral')}", 0.0)
        confidence = max(0.0, min(1.0, float(c.get("confidence", 0.5))))
        horizon = p.get(f"horizon_{c.get('time_horizon', 'short_term')}", 0.5)
        contrib = impact * magnitude * confidence * horizon * p["catalyst_scale"]
        items.append({
            "source": "catalyst",
            "detail": f"{c.get('type', '?')}: {c.get('description', '')[:60]}",
            "contribution": round(contrib, 2),
        })

    for r in skill_output.get("risks", []):
        severity = p.get(f"severity_{r.get('severity', 'minor')}", -2.0)
        probability = p.get(f"prob_{r.get('probability', 'possible')}", 0.4)
        contrib = severity * probability
        items.append({
            "source": "risk",
            "detail": f"{r.get('type', '?')}: {r.get('description', '')[:60]}",
            "contribution": round(contrib, 2),
        })

    flags = skill_output.get("event_flags", {})
    for flag_name, flag_value in flags.items():
        if flag_value and f"flag_{flag_name}" in p:
            items.append({
                "source": "event_flag",
                "detail": flag_name,
                "contribution": p[f"flag_{flag_name}"],
            })

    sector = skill_output.get("sector_sentiment", "neutral")
    sector_val = p.get(f"sector_{sector}", 0.0)
    if sector_val != 0:
        items.append({
            "source": "sector",
            "detail": f"行业情绪: {sector}",
            "contribution": sector_val,
        })

    if market_regime == "risk_off":
        items.append({"source": "regime", "detail": "风险回避市场", "contribution": p["regime_risk_off_penalty"]})
    elif market_regime == "risk_on":
        items.append({"source": "regime", "detail": "风险偏好市场", "contribution": p["regime_risk_on_bonus"]})

    return items


# ---------------------------------------------------------------------------
# TechSkill Scorer
# ---------------------------------------------------------------------------

TECH_PARAMS = {
    # Hard/soft blend weights — defaults, overridden per strategy below
    "hard_weight": 0.60,
    "soft_weight": 0.40,

    # --- Hard indicators ---
    "ma_bullish_align": 12.0,
    "ma_bearish_align": -10.0,
    "rsi_oversold_25": 8.0,   # RSI < 25
    "rsi_oversold_40": 4.0,   # RSI 25-40
    "rsi_overbought_70": -8.0, # RSI > 70
    "rsi_overbought_60": -2.0, # RSI 60-70
    "macd_positive": 5.0,
    "macd_negative": -5.0,
    "volume_expansion": 8.0,   # volume_ratio > 1.3
    "volume_contraction": -5.0, # volume_ratio < 0.7
    "bb_oversold": 6.0,        # bollinger position < 0.2
    "bb_overbought": -6.0,     # bollinger position > 0.85
    "near_support_strong": 5.0,
    "near_resistance_no_vol": -5.0,
    "breakout_confirmed": 8.0,
    "weekly_bullish": 3.0,
    "weekly_bearish": -8.0,
    "overbought_bias": -10.0,
    "volume_price_divergence": -12.0,

    # --- Soft (LLM) indicators ---
    "pattern_reliability_high": 8.0,
    "pattern_reliability_moderate": 5.0,
    "pattern_reliability_low": 2.0,
    "pattern_bearish_flip": -1.0,

    "trend_bullish": 10.0,
    "trend_bearish": -10.0,
    "trend_neutral": 0.0,
    "trend_strength_strong": 1.5,
    "trend_strength_moderate": 1.0,
    "trend_strength_weak": 0.5,

    "volume_signal_bullish_confirmation": 8.0,
    "volume_signal_accumulation": 10.0,
    "volume_signal_distribution": -10.0,
    "volume_signal_bearish_divergence": -8.0,
    "volume_signal_neutral": 0.0,

    "setup_excellent": 12.0,
    "setup_good": 6.0,
    "setup_fair": 0.0,
    "setup_poor": -8.0,
    "setup_avoid": -15.0,

    "risk_factor_penalty": -3.5,  # v2: raised from -2.0 (risks matter more)

    # Base scores
    "hard_base": 50.0,
    "soft_base": 50.0,
}

# Per-strategy overrides: swing relies more on patterns, short-term on hard signals
TECH_PARAMS_SHORT = {**TECH_PARAMS, "hard_weight": 0.65, "soft_weight": 0.35}
TECH_PARAMS_SWING = {**TECH_PARAMS, "hard_weight": 0.50, "soft_weight": 0.50}


def score_tech_output(
    skill_output: dict[str, Any],
    indicators: dict[str, Any],
    signals: dict[str, Any] | None = None,
    params: dict[str, float] | None = None,
    strategy_type: str = "short",
) -> float:
    """Score a TechSkillOutput using hybrid deterministic rules.

    v2: Strategy-aware hard/soft weights:
      - short_term: 65% hard / 35% soft (hard signals more important for fast trades)
      - swing: 50% hard / 50% soft (patterns & trend stage matter more for holds)

    60% from code-computed hard indicators (RSI, MACD, MA, volume, etc.)
    40% from LLM-assessed soft indicators (patterns, trend stage, setup quality)

    Args:
        skill_output: dict from TechSkillOutput.model_dump()
        indicators: dict with pre-computed values (ma5, ma10, ..., rsi, macd, etc.)
        signals: dict with boolean signals (ma_bullish_align, volume_expansion, etc.)
        params: optional override for scoring parameters
        strategy_type: "short" or "swing" — selects hard/soft weight balance

    Returns:
        Score in [0, 100]
    """
    # Select strategy-specific defaults, then apply user overrides
    base_params = TECH_PARAMS_SWING if strategy_type == "swing" else TECH_PARAMS_SHORT
    p = {**base_params, **(params or {})}
    signals = signals or {}

    # === Part A: Hard indicators (code-computed) ===
    hard = p["hard_base"]

    # MA alignment
    if signals.get("ma_bullish_align"):
        hard += p["ma_bullish_align"]
    elif signals.get("ma_bearish_align"):
        hard += p["ma_bearish_align"]

    # RSI (if available)
    rsi = indicators.get("rsi")
    if rsi is not None:
        if rsi < 25:
            hard += p["rsi_oversold_25"]
        elif rsi < 40:
            hard += p["rsi_oversold_40"]
        elif rsi > 70:
            hard += p["rsi_overbought_70"]
        elif rsi > 60:
            hard += p["rsi_overbought_60"]

    # MACD histogram
    macd_hist = indicators.get("macd_histogram")
    if macd_hist is not None:
        hard += p["macd_positive"] if macd_hist > 0 else p["macd_negative"]

    # Volume
    vol_ratio = indicators.get("volume_ratio_5d_20d") or indicators.get("volume_ratio")
    if vol_ratio is not None:
        if vol_ratio > 1.3:
            hard += p["volume_expansion"]
        elif vol_ratio < 0.7:
            hard += p["volume_contraction"]

    # Bollinger position
    bb_pos = indicators.get("bollinger_position")
    if bb_pos is not None:
        if bb_pos < 0.2:
            hard += p["bb_oversold"]
        elif bb_pos > 0.85:
            hard += p["bb_overbought"]

    # Support/resistance context
    if signals.get("near_support") and signals.get("support_hold_strength") in ("strong", "moderate"):
        hard += p["near_support_strong"]
    if signals.get("near_resistance") and not signals.get("volume_expansion"):
        hard += p["near_resistance_no_vol"]
    if signals.get("broke_20d_high") and signals.get("volume_expansion"):
        hard += p["breakout_confirmed"]

    # Weekly trend
    weekly = indicators.get("weekly_trend", "neutral")
    if weekly == "bullish":
        hard += p["weekly_bullish"]
    elif weekly == "bearish":
        hard += p["weekly_bearish"]

    # Overbought/divergence penalties
    if signals.get("overbought_bias"):
        hard += p["overbought_bias"]
    if signals.get("volume_price_divergence"):
        hard += p["volume_price_divergence"]

    hard = max(0.0, min(100.0, hard))

    # === Part B: Soft indicators (LLM-assessed) ===
    soft = p["soft_base"]

    # Patterns
    for pat in skill_output.get("patterns", []):
        rel_key = f"pattern_reliability_{pat.get('reliability', 'moderate')}"
        rel_score = p.get(rel_key, 5.0)
        if pat.get("bullish_or_bearish") == "bearish":
            rel_score *= p["pattern_bearish_flip"]
        soft += rel_score

    # Trend assessment
    trend = skill_output.get("trend_assessment", {})
    trend_dir = trend.get("primary_trend", "neutral")
    trend_str = trend.get("trend_strength", "moderate")
    trend_score = p.get(f"trend_{trend_dir}", 0.0)
    strength_mult = p.get(f"trend_strength_{trend_str}", 1.0)
    soft += trend_score * strength_mult

    # Volume analysis
    vol_signal = skill_output.get("volume_analysis", {}).get("signal", "neutral")
    soft += p.get(f"volume_signal_{vol_signal}", 0.0)

    # Setup quality
    quality = skill_output.get("setup_quality", "fair")
    soft += p.get(f"setup_{quality}", 0.0)

    # Risk factors
    n_risks = len(skill_output.get("risk_factors", []))
    soft += n_risks * p["risk_factor_penalty"]

    soft = max(0.0, min(100.0, soft))

    # === Blend ===
    final = p["hard_weight"] * hard + p["soft_weight"] * soft

    # === v2: Consistency clamp — setup quality must align with final score ===
    quality = skill_output.get("setup_quality", "fair")
    if quality == "avoid" and final > 45:
        logger.debug(f"Consistency clamp: setup=avoid but score={final:.1f}, capping at 45")
        final = min(final, 45.0)
    elif quality == "poor" and final > 55:
        logger.debug(f"Consistency clamp: setup=poor but score={final:.1f}, capping at 55")
        final = min(final, 55.0)
    elif quality == "excellent" and final < 55:
        logger.debug(f"Consistency clamp: setup=excellent but score={final:.1f}, flooring at 55")
        final = max(final, 55.0)

    return max(0.0, min(100.0, round(final, 1)))


def explain_tech_score(
    skill_output: dict[str, Any],
    indicators: dict[str, Any],
    signals: dict[str, Any] | None = None,
    params: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Return itemized breakdown of how the tech score was computed.

    Returns: {"hard_score": float, "soft_score": float, "final": float,
              "hard_items": [...], "soft_items": [...]}
    """
    p = {**TECH_PARAMS, **(params or {})}
    signals = signals or {}

    hard_items = [{"source": "base", "detail": "硬指标基准", "value": p["hard_base"]}]
    hard = p["hard_base"]

    def _add_hard(label: str, val: float) -> None:
        nonlocal hard
        if val != 0:
            hard += val
            hard_items.append({"source": "hard", "detail": label, "value": val})

    if signals.get("ma_bullish_align"):
        _add_hard("MA多头排列", p["ma_bullish_align"])
    elif signals.get("ma_bearish_align"):
        _add_hard("MA空头排列", p["ma_bearish_align"])

    rsi = indicators.get("rsi")
    if rsi is not None:
        if rsi < 25:
            _add_hard(f"RSI={rsi:.0f} 超卖", p["rsi_oversold_25"])
        elif rsi < 40:
            _add_hard(f"RSI={rsi:.0f} 偏低", p["rsi_oversold_40"])
        elif rsi > 70:
            _add_hard(f"RSI={rsi:.0f} 超买", p["rsi_overbought_70"])
        elif rsi > 60:
            _add_hard(f"RSI={rsi:.0f} 偏高", p["rsi_overbought_60"])

    macd_hist = indicators.get("macd_histogram")
    if macd_hist is not None:
        _add_hard(f"MACD柱状图{'正' if macd_hist > 0 else '负'}", p["macd_positive"] if macd_hist > 0 else p["macd_negative"])

    vol_ratio = indicators.get("volume_ratio_5d_20d") or indicators.get("volume_ratio")
    if vol_ratio is not None:
        if vol_ratio > 1.3:
            _add_hard(f"放量({vol_ratio:.1f}x)", p["volume_expansion"])
        elif vol_ratio < 0.7:
            _add_hard(f"缩量({vol_ratio:.1f}x)", p["volume_contraction"])

    if signals.get("overbought_bias"):
        _add_hard("超买偏离", p["overbought_bias"])
    if signals.get("volume_price_divergence"):
        _add_hard("量价背离", p["volume_price_divergence"])

    hard = max(0.0, min(100.0, hard))

    soft_items = [{"source": "base", "detail": "LLM判断基准", "value": p["soft_base"]}]
    soft = p["soft_base"]

    def _add_soft(label: str, val: float) -> None:
        nonlocal soft
        if val != 0:
            soft += val
            soft_items.append({"source": "soft", "detail": label, "value": round(val, 2)})

    for pat in skill_output.get("patterns", []):
        rel_key = f"pattern_reliability_{pat.get('reliability', 'moderate')}"
        rel_score = p.get(rel_key, 5.0)
        if pat.get("bullish_or_bearish") == "bearish":
            rel_score *= p["pattern_bearish_flip"]
        _add_soft(f"形态:{pat.get('name', '?')}", rel_score)

    trend = skill_output.get("trend_assessment", {})
    trend_dir = trend.get("primary_trend", "neutral")
    trend_str = trend.get("trend_strength", "moderate")
    trend_val = p.get(f"trend_{trend_dir}", 0.0) * p.get(f"trend_strength_{trend_str}", 1.0)
    _add_soft(f"趋势:{trend_dir}/{trend_str}", trend_val)

    vol_signal = skill_output.get("volume_analysis", {}).get("signal", "neutral")
    _add_soft(f"量价:{vol_signal}", p.get(f"volume_signal_{vol_signal}", 0.0))

    quality = skill_output.get("setup_quality", "fair")
    _add_soft(f"质量:{quality}", p.get(f"setup_{quality}", 0.0))

    n_risks = len(skill_output.get("risk_factors", []))
    if n_risks:
        _add_soft(f"风险因子×{n_risks}", n_risks * p["risk_factor_penalty"])

    soft = max(0.0, min(100.0, soft))
    final = p["hard_weight"] * hard + p["soft_weight"] * soft
    final = max(0.0, min(100.0, round(final, 1)))

    return {
        "hard_score": round(hard, 1),
        "soft_score": round(soft, 1),
        "hard_weight": p["hard_weight"],
        "soft_weight": p["soft_weight"],
        "final": final,
        "hard_items": hard_items,
        "soft_items": soft_items,
    }
