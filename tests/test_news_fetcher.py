# -*- coding: utf-8 -*-
"""Tests for analysis.news_fetcher and core.news_sources.

Tests cover:
  - Title normalization and deduplication
  - News quality report computation
  - Keyword sentiment analysis (positive, negative, neutral, negation)
  - Publisher credibility classification

All tests are self-contained; no network or external APIs required.
"""
from __future__ import annotations

import pytest

from analysis.news_fetcher import (
    _dedup_news,
    _normalize_title,
    analyze_sentiment,
    news_quality_report,
)
from core.news_sources import classify_publisher


# ===================================================================
# _normalize_title
# ===================================================================

class TestNormalizeTitle:

    def test_lowercase_and_strip_punctuation(self):
        result = _normalize_title("AAPL Surges 10% on Earnings!")
        assert result == "aaplsurges10onearnings"

    def test_keeps_chinese_characters(self):
        result = _normalize_title("恒生指数大涨3%")
        assert result == "恒生指数大涨3"

    def test_truncates_to_80_chars(self):
        long_title = "A" * 200
        result = _normalize_title(long_title)
        assert len(result) == 80

    def test_empty_string(self):
        assert _normalize_title("") == ""

    def test_only_punctuation(self):
        assert _normalize_title("!@#$%^&*()") == ""

    def test_mixed_language(self):
        result = _normalize_title("Tesla (TSLA) 股价暴涨 - 10%")
        assert result == "teslatsla股价暴涨10"


# ===================================================================
# _dedup_news
# ===================================================================

class TestDedupNews:

    def test_removes_exact_duplicate_titles(self):
        items = [
            {"title": "Apple beats earnings expectations", "credibility": 0.7, "origin": "a"},
            {"title": "Apple beats earnings expectations", "credibility": 0.9, "origin": "b"},
        ]
        result = _dedup_news(items)
        assert len(result) == 1
        assert result[0]["credibility"] == 0.9  # keeps higher credibility

    def test_keeps_unique_titles(self):
        items = [
            {"title": "Apple beats earnings expectations nicely", "credibility": 0.7, "origin": "a"},
            {"title": "Tesla recalls 500k vehicles worldwide", "credibility": 0.8, "origin": "b"},
        ]
        result = _dedup_news(items)
        assert len(result) == 2

    def test_filters_short_titles(self):
        """Titles shorter than 10 chars after normalization are dropped."""
        items = [
            {"title": "Short", "credibility": 0.5, "origin": "a"},
            {"title": "This is a much longer headline about stocks", "credibility": 0.7, "origin": "b"},
        ]
        result = _dedup_news(items)
        assert len(result) == 1
        assert "longer" in result[0]["title"].lower()

    def test_empty_list(self):
        assert _dedup_news([]) == []

    def test_case_insensitive_dedup(self):
        """Normalization lowercases, so 'APPLE' and 'apple' should dedup."""
        items = [
            {"title": "APPLE Stock Surges Higher Today", "credibility": 0.5, "origin": "a"},
            {"title": "Apple stock surges higher today", "credibility": 0.9, "origin": "b"},
        ]
        result = _dedup_news(items)
        assert len(result) == 1
        assert result[0]["credibility"] == 0.9


# ===================================================================
# news_quality_report
# ===================================================================

class TestNewsQualityReport:

    def test_empty_items_returns_poor(self):
        report = news_quality_report([])
        assert report["quality_tier"] == "poor"
        assert report["item_count"] == 0
        assert report["source_count"] == 0
        assert report["suggested_weight_factor"] == 0.3

    def test_good_quality_with_premium(self):
        """Premium source + >=8 items + >=3 origins → good."""
        items = [
            {"origin": "finnhub", "credibility": 0.8},
            {"origin": "finnhub", "credibility": 0.8},
            {"origin": "google_news", "credibility": 0.55},
            {"origin": "google_news", "credibility": 0.55},
            {"origin": "yahoo_finance", "credibility": 0.7},
            {"origin": "yahoo_finance", "credibility": 0.7},
            {"origin": "yahoo_finance", "credibility": 0.7},
            {"origin": "yahoo_finance", "credibility": 0.7},
        ]
        report = news_quality_report(items)
        assert report["quality_tier"] == "good"
        assert report["suggested_weight_factor"] == 1.0
        assert report["has_premium"] is True

    def test_fair_quality_medium(self):
        """>=5 items, >=2 origins, no premium → fair/0.7."""
        items = [
            {"origin": "google_news", "credibility": 0.55},
            {"origin": "google_news", "credibility": 0.55},
            {"origin": "google_news", "credibility": 0.55},
            {"origin": "yahoo_finance", "credibility": 0.7},
            {"origin": "yahoo_finance", "credibility": 0.7},
        ]
        report = news_quality_report(items)
        assert report["quality_tier"] == "fair"
        assert report["suggested_weight_factor"] == 0.7

    def test_fair_quality_low(self):
        """2-4 items, 1 origin → fair/0.5."""
        items = [
            {"origin": "google_news", "credibility": 0.55},
            {"origin": "google_news", "credibility": 0.55},
        ]
        report = news_quality_report(items)
        assert report["quality_tier"] == "fair"
        assert report["suggested_weight_factor"] == 0.5

    def test_poor_quality_single_item(self):
        items = [{"origin": "yahoo_finance", "credibility": 0.7}]
        report = news_quality_report(items)
        assert report["quality_tier"] == "poor"
        assert report["suggested_weight_factor"] == 0.3

    def test_pre_sentiment_boosts_factor(self):
        """Having pre-computed sentiment adds 0.1 to factor."""
        items = [
            {"origin": "marketaux", "credibility": 0.8, "pre_sentiment": 0.5},
            {"origin": "marketaux", "credibility": 0.8},
        ]
        report = news_quality_report(items)
        assert report["has_pre_sentiment"] is True
        # 2 items, 1 origin → fair/0.5 + 0.1 = 0.6
        assert report["suggested_weight_factor"] == 0.6

    def test_has_premium_detects_marketaux(self):
        items = [{"origin": "marketaux", "credibility": 0.8}]
        report = news_quality_report(items)
        assert report["has_premium"] is True

    def test_has_premium_detects_finnhub_market(self):
        items = [{"origin": "finnhub_market", "credibility": 0.8}]
        report = news_quality_report(items)
        assert report["has_premium"] is True

    def test_avg_credibility(self):
        items = [
            {"origin": "a", "credibility": 0.8},
            {"origin": "b", "credibility": 0.6},
        ]
        report = news_quality_report(items)
        assert report["avg_credibility"] == 0.7


# ===================================================================
# analyze_sentiment
# ===================================================================

class TestAnalyzeSentiment:

    def test_empty_returns_neutral(self):
        result = analyze_sentiment([])
        assert result["label"] == "neutral"
        assert result["score"] == 0.0

    def test_positive_news_bullish(self):
        items = [
            {"title": "Stock surges on strong earnings beat", "summary": "", "credibility": 0.8, "origin": "a"},
            {"title": "Company reports record profits and raises guidance", "summary": "", "credibility": 0.8, "origin": "a"},
        ]
        result = analyze_sentiment(items)
        assert result["label"] == "bullish"
        assert result["score"] > 0.12
        assert result["positive"] > 0

    def test_negative_news_bearish(self):
        items = [
            {"title": "Stock crashes after fraud investigation", "summary": "", "credibility": 0.8, "origin": "a"},
            {"title": "Company declares bankruptcy amid massive losses", "summary": "", "credibility": 0.8, "origin": "a"},
        ]
        result = analyze_sentiment(items)
        assert result["label"] == "bearish"
        assert result["score"] < -0.12
        assert result["negative"] > 0

    def test_neutral_news(self):
        items = [
            {"title": "Company holds annual meeting", "summary": "", "credibility": 0.5, "origin": "a"},
        ]
        result = analyze_sentiment(items)
        assert result["label"] == "neutral"

    def test_pre_sentiment_blended(self):
        """Items with pre_sentiment should influence the final score."""
        items = [
            {
                "title": "Normal headline without keywords",
                "summary": "",
                "credibility": 0.8,
                "origin": "marketaux",
                "pre_sentiment": 0.9,
            },
        ]
        result = analyze_sentiment(items)
        # pre_avg = 0.9, keyword_score = 0.0 → 0.6*0.9 + 0.4*0.0 = 0.54
        assert result["score"] > 0.12
        assert result["label"] == "bullish"

    def test_credibility_weights_sentiment(self):
        """Higher credibility → stronger signal."""
        low_cred = [{"title": "Stock surges", "summary": "", "credibility": 0.1, "origin": "a"}]
        high_cred = [{"title": "Stock surges", "summary": "", "credibility": 1.0, "origin": "a"}]
        low_result = analyze_sentiment(low_cred)
        high_result = analyze_sentiment(high_cred)
        assert high_result["positive"] > low_result["positive"]

    def test_result_contains_quality(self):
        items = [{"title": "Something happens in the market today", "summary": "", "credibility": 0.5, "origin": "a"}]
        result = analyze_sentiment(items)
        assert "quality" in result
        assert result["quality"]["item_count"] == 1

    def test_score_bounded(self):
        """Score should always be in [-1, 1]."""
        items = [
            {"title": "surge surge surge rally rally breakout record high", "summary": "", "credibility": 1.0, "origin": "a"},
        ]
        result = analyze_sentiment(items)
        assert -1.0 <= result["score"] <= 1.0


# ===================================================================
# classify_publisher
# ===================================================================

class TestClassifyPublisher:

    def test_official_sec(self):
        tier, cred = classify_publisher("SEC EDGAR Filing")
        assert tier == "official"
        assert cred == 1.0

    def test_official_hkex(self):
        tier, cred = classify_publisher("HKEX News")
        assert tier == "official"
        assert cred == 1.0

    def test_analyst_goldman(self):
        tier, cred = classify_publisher("Goldman Sachs Research")
        assert tier == "analyst"
        assert cred == 0.85

    def test_analyst_jpmorgan(self):
        tier, cred = classify_publisher("JPMorgan Chase & Co")
        assert tier == "analyst"
        assert cred == 0.85

    def test_top_media_bloomberg(self):
        tier, cred = classify_publisher("Bloomberg News")
        assert tier == "media"
        assert cred == 0.80

    def test_top_media_reuters(self):
        tier, cred = classify_publisher("Reuters")
        assert tier == "media"
        assert cred == 0.80

    def test_media_yahoo(self):
        tier, cred = classify_publisher("Yahoo Finance")
        assert tier == "media"
        assert cred == 0.70

    def test_media_benzinga(self):
        tier, cred = classify_publisher("Benzinga")
        assert tier == "media"
        assert cred == 0.70

    def test_unknown_publisher(self):
        tier, cred = classify_publisher("Random Blog XYZ")
        assert tier == "aggregator"
        assert cred == 0.55

    def test_empty_publisher(self):
        tier, cred = classify_publisher("")
        assert tier == "aggregator"
        assert cred == 0.5

    def test_none_publisher(self):
        tier, cred = classify_publisher(None)
        assert tier == "aggregator"
        assert cred == 0.5

    def test_case_insensitive(self):
        tier, cred = classify_publisher("BLOOMBERG")
        assert tier == "media"
        assert cred == 0.80
