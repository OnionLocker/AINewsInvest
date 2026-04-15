# -*- coding: utf-8 -*-
"""Shared pytest fixtures for AINewsInvest tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path so imports like `pipeline.skills.scorers` resolve.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Reusable news item factories
# ---------------------------------------------------------------------------

@pytest.fixture
def make_news_item():
    """Factory fixture that creates a news item dict with sensible defaults."""

    def _make(
        title: str = "Stock surges on strong earnings",
        publisher: str = "Reuters",
        credibility: float = 0.8,
        origin: str = "finnhub",
        summary: str = "",
        pre_sentiment: float | None = None,
    ) -> dict:
        item: dict = {
            "title": title,
            "publisher": publisher,
            "link": "https://example.com/news/1",
            "published": 1700000000,
            "summary": summary,
            "source_tier": "media",
            "credibility": credibility,
            "origin": origin,
        }
        if pre_sentiment is not None:
            item["pre_sentiment"] = pre_sentiment
        return item

    return _make
