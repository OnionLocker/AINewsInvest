# -*- coding: utf-8 -*-
"""Tests for pipeline.skills.scorers — deterministic scoring functions.

All tests are self-contained; no LLM, no network, no database required.
"""
from __future__ import annotations

import pytest

from pipeline.skills.scorers import (
    NEWS_PARAMS,
    TECH_PARAMS,
    TECH_PARAMS_SHORT,
    TECH_PARAMS_SWING,
    score_news_output,
    score_tech_output,
)


# ===================================================================
# score_news_output
# ===================================================================

class TestScoreNewsOutput:
    """Tests for the news skill scorer."""

    # -- Baseline / empty inputs -----------------------------------------

    def test_empty_input_returns_base_score(self):
        """No catalysts, no risks, no flags → base_score (50.0)."""
        result = score_news_output({})
        assert result == 50.0

    def test_empty_catalysts_and_risks(self):
        result = score_news_output({"catalysts": [], "risks": [], "event_flags": {}})
        assert result == 50.0

    # -- Catalysts -------------------------------------------------------

    def test_positive_catalyst_increases_score(self):
        output = {
            "catalysts": [
                {
                    "impact": "positive",
                    "magnitude": "major",
                    "confidence": 1.0,
                    "time_horizon": "short_term",
                }
            ]
        }
        result = score_news_output(output)
        # contribution = 1.0 * 3.0 * 1.0 * 1.0 * 8.0 = 24.0
        assert result == 74.0

    def test_negative_catalyst_decreases_score(self):
        output = {
            "catalysts": [
                {
                    "impact": "negative",
                    "magnitude": "major",
                    "confidence": 1.0,
                    "time_horizon": "short_term",
                }
            ]
        }
        result = score_news_output(output)
        # contribution = -1.0 * 3.0 * 1.0 * 1.0 * 8.0 = -24.0
        assert result == 26.0

    def test_neutral_catalyst_has_no_effect(self):
        output = {
            "catalysts": [
                {
                    "impact": "neutral",
                    "magnitude": "moderate",
                    "confidence": 0.8,
                    "time_horizon": "short_term",
                }
            ]
        }
        result = score_news_output(output)
        assert result == 50.0  # impact_neutral = 0.0 → no change

    def test_medium_term_horizon_reduces_contribution(self):
        output = {
            "catalysts": [
                {
                    "impact": "positive",
                    "magnitude": "major",
                    "confidence": 1.0,
                    "time_horizon": "medium_term",
                }
            ]
        }
        result = score_news_output(output)
        # contribution = 1.0 * 3.0 * 1.0 * 0.4 * 8.0 = 9.6
        assert result == 59.6

    def test_confidence_clamped_to_0_1(self):
        output = {
            "catalysts": [
                {
                    "impact": "positive",
                    "magnitude": "minor",
                    "confidence": 5.0,  # exceeds 1.0 → clamped
                    "time_horizon": "short_term",
                }
            ]
        }
        result = score_news_output(output)
        # contribution = 1.0 * 1.0 * 1.0(clamped) * 1.0 * 8.0 = 8.0
        assert result == 58.0

    def test_multiple_catalysts_accumulate(self):
        output = {
            "catalysts": [
                {"impact": "positive", "magnitude": "minor", "confidence": 1.0, "time_horizon": "short_term"},
                {"impact": "positive", "magnitude": "minor", "confidence": 1.0, "time_horizon": "short_term"},
            ]
        }
        result = score_news_output(output)
        # 2 × 8.0 = 16.0
        assert result == 66.0

    # -- Risks -----------------------------------------------------------

    def test_single_risk_decreases_score(self):
        output = {
            "risks": [
                {"severity": "critical", "probability": "certain"}
            ]
        }
        result = score_news_output(output)
        # -15.0 * 1.0 = -15.0 → 50 - 15 = 35
        assert result == 35.0

    def test_minor_unlikely_risk_has_small_effect(self):
        output = {
            "risks": [
                {"severity": "minor", "probability": "unlikely"}
            ]
        }
        result = score_news_output(output)
        # -2.0 * 0.15 = -0.3 → 49.7
        assert result == 49.7

    def test_multiple_risks_accumulate(self):
        output = {
            "risks": [
                {"severity": "severe", "probability": "likely"},
                {"severity": "moderate", "probability": "possible"},
            ]
        }
        result = score_news_output(output)
        # -10 * 0.7 + -5 * 0.4 = -7.0 + -2.0 = -9.0 → 41.0
        assert result == 41.0

    # -- Event flags -----------------------------------------------------

    def test_guidance_raised_flag(self):
        output = {"event_flags": {"guidance_raised": True}}
        result = score_news_output(output)
        assert result == 58.0  # 50 + 8.0

    def test_guidance_lowered_flag(self):
        output = {"event_flags": {"guidance_lowered": True}}
        result = score_news_output(output)
        assert result == 42.0  # 50 - 8.0

    def test_false_flag_has_no_effect(self):
        output = {"event_flags": {"guidance_raised": False}}
        result = score_news_output(output)
        assert result == 50.0

    def test_litigation_risk_flag(self):
        output = {"event_flags": {"litigation_risk": True}}
        result = score_news_output(output)
        assert result == 44.0  # 50 - 6.0

    def test_fda_approval_flag(self):
        output = {"event_flags": {"fda_approval": True}}
        result = score_news_output(output)
        assert result == 60.0  # 50 + 10.0

    def test_unknown_flag_ignored(self):
        output = {"event_flags": {"unknown_flag": True}}
        result = score_news_output(output)
        assert result == 50.0

    # -- Sector sentiment ------------------------------------------------

    def test_positive_sector(self):
        output = {"sector_sentiment": "positive"}
        result = score_news_output(output)
        assert result == 53.0

    def test_negative_sector(self):
        output = {"sector_sentiment": "negative"}
        result = score_news_output(output)
        assert result == 47.0

    def test_neutral_sector_no_effect(self):
        output = {"sector_sentiment": "neutral"}
        result = score_news_output(output)
        assert result == 50.0

    # -- Market regime ---------------------------------------------------

    def test_risk_off_regime(self):
        result = score_news_output({}, market_regime="risk_off")
        assert result == 45.0  # 50 - 5

    def test_risk_on_regime(self):
        result = score_news_output({}, market_regime="risk_on")
        assert result == 52.0  # 50 + 2

    def test_neutral_regime_no_effect(self):
        result = score_news_output({}, market_regime="neutral")
        assert result == 50.0

    # -- Score clamping --------------------------------------------------

    def test_score_clamped_at_100(self):
        """Many strong positives should not exceed 100."""
        output = {
            "catalysts": [
                {"impact": "positive", "magnitude": "major", "confidence": 1.0, "time_horizon": "short_term"},
                {"impact": "positive", "magnitude": "major", "confidence": 1.0, "time_horizon": "short_term"},
                {"impact": "positive", "magnitude": "major", "confidence": 1.0, "time_horizon": "short_term"},
            ],
            "event_flags": {"fda_approval": True, "guidance_raised": True},
            "sector_sentiment": "positive",
        }
        result = score_news_output(output, market_regime="risk_on")
        assert result == 100.0

    def test_score_clamped_at_0(self):
        """Many severe negatives should not go below 0."""
        output = {
            "risks": [
                {"severity": "critical", "probability": "certain"},
                {"severity": "critical", "probability": "certain"},
                {"severity": "critical", "probability": "certain"},
                {"severity": "critical", "probability": "certain"},
            ],
            "event_flags": {"guidance_lowered": True, "litigation_risk": True},
            "sector_sentiment": "negative",
        }
        result = score_news_output(output, market_regime="risk_off")
        assert result == 0.0

    # -- Custom params override ------------------------------------------

    def test_custom_params_override(self):
        result = score_news_output({}, params={"base_score": 75.0})
        assert result == 75.0

    # -- Return type -----------------------------------------------------

    def test_return_type_is_float(self):
        assert isinstance(score_news_output({}), float)


# ===================================================================
# score_tech_output
# ===================================================================

class TestScoreTechOutput:
    """Tests for the tech skill scorer."""

    # -- Baseline / empty inputs -----------------------------------------

    def test_empty_input_returns_base_blend(self):
        """Empty output + empty indicators → hard_base * hw + soft_base * sw."""
        result = score_tech_output({}, {})
        # short strategy: 0.65 * 50 + 0.35 * 50 = 50.0
        assert result == 50.0

    def test_empty_input_swing(self):
        result = score_tech_output({}, {}, strategy_type="swing")
        # swing: 0.50 * 50 + 0.50 * 50 = 50.0
        assert result == 50.0

    # -- Hard indicators: RSI -------------------------------------------

    def test_rsi_oversold_deep(self):
        result = score_tech_output({}, {"rsi": 20})
        # hard = 50 + 8 = 58, soft = 50 → 0.65*58 + 0.35*50 = 37.7 + 17.5 = 55.2
        assert result == 55.2

    def test_rsi_oversold_moderate(self):
        result = score_tech_output({}, {"rsi": 35})
        # hard = 50 + 4 = 54 → 0.65*54 + 0.35*50 = 35.1 + 17.5 = 52.6
        assert result == 52.6

    def test_rsi_overbought(self):
        result = score_tech_output({}, {"rsi": 75})
        # hard = 50 - 8 = 42 → 0.65*42 + 0.35*50 = 27.3 + 17.5 = 44.8
        assert result == 44.8

    def test_rsi_slightly_high(self):
        result = score_tech_output({}, {"rsi": 65})
        # hard = 50 - 2 = 48 → 0.65*48 + 0.35*50 = 31.2 + 17.5 = 48.7
        assert result == 48.7

    def test_rsi_normal_range_no_effect(self):
        """RSI between 40 and 60 → no bonus/penalty."""
        result = score_tech_output({}, {"rsi": 50})
        assert result == 50.0

    # -- Hard indicators: MACD ------------------------------------------

    def test_macd_positive(self):
        result = score_tech_output({}, {"macd_histogram": 0.5})
        # hard = 50 + 5 = 55 → 0.65*55 + 0.35*50 = 35.75 + 17.5 = 53.25 → 53.2
        assert result == 53.2  # rounded

    def test_macd_negative(self):
        result = score_tech_output({}, {"macd_histogram": -0.5})
        # hard = 50 - 5 = 45 → 0.65*45 + 0.35*50 = 29.25 + 17.5 = 46.75 → 46.8
        assert result == 46.8

    # -- Hard indicators: Volume ----------------------------------------

    def test_volume_expansion(self):
        result = score_tech_output({}, {"volume_ratio_5d_20d": 1.5})
        # hard = 50 + 8 = 58 → 0.65*58 + 0.35*50 = 55.2
        assert result == 55.2

    def test_volume_contraction(self):
        result = score_tech_output({}, {"volume_ratio_5d_20d": 0.5})
        # hard = 50 - 5 = 45 → 0.65*45 + 0.35*50 = 46.75 → 46.8
        assert result == 46.8

    # -- Hard indicators: MA alignment via signals ----------------------

    def test_ma_bullish_alignment(self):
        result = score_tech_output({}, {}, signals={"ma_bullish_align": True})
        # hard = 50 + 12 = 62 → 0.65*62 + 0.35*50 = 40.3 + 17.5 = 57.8
        assert result == 57.8

    def test_ma_bearish_alignment(self):
        result = score_tech_output({}, {}, signals={"ma_bearish_align": True})
        # hard = 50 - 10 = 40 → 0.65*40 + 0.35*50 = 26 + 17.5 = 43.5
        assert result == 43.5

    # -- Hard indicators: Bollinger -------------------------------------

    def test_bollinger_oversold(self):
        result = score_tech_output({}, {"bollinger_position": 0.1})
        # hard = 50 + 6 = 56 → 0.65*56 + 0.35*50 = 36.4 + 17.5 = 53.9
        assert result == 53.9

    def test_bollinger_overbought(self):
        result = score_tech_output({}, {"bollinger_position": 0.9})
        # hard = 50 - 6 = 44 → 0.65*44 + 0.35*50 = 28.6 + 17.5 = 46.1
        assert result == 46.1

    # -- Hard indicators: Weekly trend ----------------------------------

    def test_weekly_bullish(self):
        result = score_tech_output({}, {"weekly_trend": "bullish"})
        # hard = 50 + 3 = 53 → 0.65*53 + 0.35*50 = 34.45 + 17.5 = 51.95 → 52.0
        assert result == 52.0

    def test_weekly_bearish(self):
        result = score_tech_output({}, {"weekly_trend": "bearish"})
        # hard = 50 - 8 = 42 → 0.65*42 + 0.35*50 = 27.3 + 17.5 = 44.8
        assert result == 44.8

    # -- Soft indicators: Patterns --------------------------------------

    def test_bullish_high_reliability_pattern(self):
        output = {
            "patterns": [{"name": "cup_and_handle", "reliability": "high", "bullish_or_bearish": "bullish"}]
        }
        result = score_tech_output(output, {})
        # soft = 50 + 8 = 58 → 0.65*50 + 0.35*58 = 32.5 + 20.3 = 52.8
        assert result == 52.8

    def test_bearish_pattern_flips_score(self):
        output = {
            "patterns": [{"name": "head_shoulders", "reliability": "high", "bullish_or_bearish": "bearish"}]
        }
        result = score_tech_output(output, {})
        # rel_score = 8.0 * (-1.0) = -8.0 → soft = 50 - 8 = 42
        # 0.65*50 + 0.35*42 = 32.5 + 14.7 = 47.2
        assert result == 47.2

    # -- Soft indicators: Trend assessment ------------------------------

    def test_bullish_strong_trend(self):
        output = {
            "trend_assessment": {"primary_trend": "bullish", "trend_strength": "strong"}
        }
        result = score_tech_output(output, {})
        # soft = 50 + 10 * 1.5 = 65 → 0.65*50 + 0.35*65 = 32.5 + 22.75 = 55.25 → 55.2
        assert result == 55.2  # rounded

    def test_bearish_moderate_trend(self):
        output = {
            "trend_assessment": {"primary_trend": "bearish", "trend_strength": "moderate"}
        }
        result = score_tech_output(output, {})
        # soft = 50 + (-10 * 1.0) = 40 → 0.65*50 + 0.35*40 = 32.5 + 14 = 46.5
        assert result == 46.5

    # -- Soft indicators: Volume signal ---------------------------------

    def test_accumulation_volume_signal(self):
        output = {"volume_analysis": {"signal": "accumulation"}}
        result = score_tech_output(output, {})
        # soft = 50 + 10 = 60 → 0.65*50 + 0.35*60 = 32.5 + 21 = 53.5
        assert result == 53.5

    def test_distribution_volume_signal(self):
        output = {"volume_analysis": {"signal": "distribution"}}
        result = score_tech_output(output, {})
        # soft = 50 - 10 = 40 → 0.65*50 + 0.35*40 = 32.5 + 14 = 46.5
        assert result == 46.5

    # -- Soft indicators: Setup quality ---------------------------------

    def test_excellent_setup(self):
        output = {"setup_quality": "excellent"}
        result = score_tech_output(output, {})
        # soft = 50 + 12 = 62 → 0.65*50 + 0.35*62 = 54.2
        # But consistency clamp: excellent floors at 55
        assert result == 55.0

    def test_poor_setup(self):
        output = {"setup_quality": "poor"}
        result = score_tech_output(output, {})
        # soft = 50 - 8 = 42 → 0.65*50 + 0.35*42 = 32.5 + 14.7 = 47.2
        assert result == 47.2

    # -- Soft indicators: Risk factors ----------------------------------

    def test_risk_factors_reduce_soft(self):
        output = {"risk_factors": ["gap risk", "earnings soon"]}
        result = score_tech_output(output, {})
        # soft = 50 + 2 * (-3.5) = 43 → 0.65*50 + 0.35*43 = 32.5 + 15.05 = 47.55 → round(47.55, 1) = 47.5
        assert result == 47.5

    # -- Consistency clamp -----------------------------------------------

    def test_avoid_quality_caps_at_45(self):
        """setup_quality='avoid' → final capped at 45 even if indicators are good."""
        output = {"setup_quality": "avoid"}
        # With bullish everything, hard would push score above 45
        indicators = {"rsi": 20, "macd_histogram": 1.0, "volume_ratio_5d_20d": 2.0}
        signals = {"ma_bullish_align": True}
        result = score_tech_output(output, indicators, signals=signals)
        assert result <= 45.0

    def test_poor_quality_caps_at_55(self):
        """setup_quality='poor' → final capped at 55."""
        output = {"setup_quality": "poor"}
        indicators = {"rsi": 20, "macd_histogram": 1.0, "volume_ratio_5d_20d": 2.0}
        signals = {"ma_bullish_align": True}
        result = score_tech_output(output, indicators, signals=signals)
        assert result <= 55.0

    def test_excellent_quality_floors_at_55(self):
        """setup_quality='excellent' → final floored at 55 even if indicators are bad."""
        output = {"setup_quality": "excellent"}
        indicators = {"rsi": 75, "macd_histogram": -1.0, "volume_ratio_5d_20d": 0.4}
        signals = {"ma_bearish_align": True}
        result = score_tech_output(output, indicators, signals=signals)
        assert result >= 55.0

    # -- Strategy type differences ---------------------------------------

    def test_short_vs_swing_weights_differ(self):
        """Short-term uses 65/35, swing uses 50/50."""
        # Push hard score high, soft low
        output = {"setup_quality": "avoid"}  # avoid → soft penalty (-15)
        indicators = {"rsi": 20}  # oversold → hard bonus (+8)
        signals = {"ma_bullish_align": True}  # hard bonus (+12)
        # But both will be clamped by "avoid" to 45, so pick non-clamping scenario
        output2 = {}
        indicators2 = {"rsi": 20}  # hard = 58, soft = 50
        short_result = score_tech_output(output2, indicators2, strategy_type="short")
        swing_result = score_tech_output(output2, indicators2, strategy_type="swing")
        # short: 0.65*58 + 0.35*50 = 37.7 + 17.5 = 55.2
        # swing: 0.50*58 + 0.50*50 = 29 + 25 = 54.0
        assert short_result == 55.2
        assert swing_result == 54.0
        assert short_result != swing_result

    # -- Score clamping --------------------------------------------------

    def test_tech_score_clamped_at_100(self):
        """Extreme bullish inputs should not exceed 100."""
        output = {
            "patterns": [
                {"name": "bull_flag", "reliability": "high", "bullish_or_bearish": "bullish"},
                {"name": "ascending_triangle", "reliability": "high", "bullish_or_bearish": "bullish"},
                {"name": "cup_handle", "reliability": "high", "bullish_or_bearish": "bullish"},
            ],
            "trend_assessment": {"primary_trend": "bullish", "trend_strength": "strong"},
            "volume_analysis": {"signal": "accumulation"},
            "setup_quality": "excellent",
        }
        indicators = {"rsi": 20, "macd_histogram": 1.0, "volume_ratio_5d_20d": 2.0, "bollinger_position": 0.1, "weekly_trend": "bullish"}
        signals = {"ma_bullish_align": True, "broke_20d_high": True, "volume_expansion": True}
        result = score_tech_output(output, indicators, signals=signals)
        assert 0.0 <= result <= 100.0

    def test_tech_score_clamped_at_0(self):
        """Extreme bearish inputs should not go below 0."""
        output = {
            "patterns": [
                {"name": "head_shoulders", "reliability": "high", "bullish_or_bearish": "bearish"},
                {"name": "double_top", "reliability": "high", "bullish_or_bearish": "bearish"},
            ],
            "trend_assessment": {"primary_trend": "bearish", "trend_strength": "strong"},
            "volume_analysis": {"signal": "distribution"},
            "setup_quality": "avoid",
            "risk_factors": ["gap", "earnings", "macro", "sector"],
        }
        indicators = {"rsi": 80, "macd_histogram": -1.0, "volume_ratio_5d_20d": 0.3, "bollinger_position": 0.95, "weekly_trend": "bearish"}
        signals = {"ma_bearish_align": True, "overbought_bias": True, "volume_price_divergence": True, "near_resistance": True}
        result = score_tech_output(output, indicators, signals=signals)
        assert 0.0 <= result <= 100.0

    # -- Return type -----------------------------------------------------

    def test_return_type_is_float(self):
        assert isinstance(score_tech_output({}, {}), float)

    # -- Custom params ---------------------------------------------------

    def test_custom_params_override_tech(self):
        result = score_tech_output({}, {}, params={"hard_base": 70.0, "soft_base": 70.0})
        # 0.65*70 + 0.35*70 = 70.0
        assert result == 70.0
