"""Multi-source news aggregator with credibility scoring and deduplication.

Fetches from up to 5 sources concurrently:
  1. Yahoo Finance (yfinance) - baseline, no key needed
  2. Finnhub - best free API, aggregates Bloomberg/Reuters/WSJ
  3. MarketAux - global coverage, built-in sentiment, good HK/China
  4. Google News RSS - free, no key, catches breaking news, Chinese for HK
  5. SEC EDGAR - official US filings (8-K, 10-Q, insider trades)

Each item is tagged with:
  - credibility: 0.0-1.0 based on publisher tier
  - source_tier: official/analyst/media/aggregator/social
  - origin: which API it came from

Deduplication removes near-duplicate titles across sources.
Results are sorted by credibility (highest first) so LLM Agent
gets the most trustworthy signals at the top.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from loguru import logger

from core.news_sources import (
    FinnhubNews,
    GoogleNewsRSS,
    MarketAuxNews,
    SECEdgarNews,
    YFinanceNews,
    classify_publisher,
)
from pipeline.config import get_config


_POSITIVE = [
    "surge", "soar", "beat", "upgrade", "growth", "profit", "bullish",
    "record", "strong", "outperform", "buy", "rally", "gain", "breakout",
    "dividend", "buyback", "partnership", "approval", "contract",
]
_NEGATIVE = [
    "crash", "plunge", "miss", "downgrade", "loss", "bearish", "weak",
    "decline", "sell", "cut", "warning", "debt", "risk", "fraud",
    "investigation", "lawsuit", "recall", "layoff", "default", "bankruptcy",
]


def _normalize_title(title: str) -> str:
    """Normalize title for dedup comparison."""
    t = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]", "", title.lower())
    return t[:80]


def _dedup_news(items: list[dict]) -> list[dict]:
    """Remove near-duplicate titles, keeping the highest-credibility version."""
    seen: dict[str, dict] = {}
    for item in items:
        key = _normalize_title(item.get("title", ""))
        if not key or len(key) < 10:
            continue
        existing = seen.get(key)
        if existing is None or item.get("credibility", 0) > existing.get("credibility", 0):
            seen[key] = item
    return list(seen.values())


def _get_sources() -> list[tuple[str, Any]]:
    """Build list of active news sources from config."""
    cfg = get_config()
    nc = cfg.news

    sources: list[tuple[str, Any]] = []

    sources.append(("yahoo_finance", YFinanceNews()))

    if nc.finnhub_key:
        sources.append(("finnhub", FinnhubNews(nc.finnhub_key)))

    if nc.marketaux_key:
        sources.append(("marketaux", MarketAuxNews(nc.marketaux_key)))

    sources.append(("google_news", GoogleNewsRSS()))
    sources.append(("sec_edgar", SECEdgarNews()))

    return sources


def fetch_news(ticker: str, market: str, limit: int = 15) -> list[dict]:
    """Fetch and aggregate news from all configured sources.

    Returns deduplicated, credibility-sorted list of news items.
    Each item has: title, publisher, link, published, summary,
    source_tier, credibility, origin.
    """
    sources = _get_sources()
    all_items: list[dict] = []

    with ThreadPoolExecutor(max_workers=len(sources)) as ex:
        futs = {}
        for name, src in sources:
            per_source = 10 if name in ("finnhub", "marketaux") else 8
            futs[ex.submit(src.fetch, ticker, market, per_source)] = name

        for fut in as_completed(futs):
            name = futs[fut]
            try:
                items = fut.result()
                if items:
                    all_items.extend(items)
                    logger.debug(f"News {name}: {len(items)} items for {ticker}")
            except Exception as e:
                logger.debug(f"News {name} failed {ticker}: {e}")

    if not all_items:
        return []

    deduped = _dedup_news(all_items)

    deduped.sort(key=lambda x: x.get("credibility", 0), reverse=True)

    return deduped[:limit]


def fetch_market_news(market: str = "us_stock", limit: int = 20) -> list[dict]:
    """Fetch general market-level news (macro, Fed, earnings season).

    Used to provide market context to the News Agent and sentiment API.
    """
    cfg = get_config()
    nc = cfg.news
    all_items: list[dict] = []

    if nc.finnhub_key:
        try:
            fh = FinnhubNews(nc.finnhub_key)
            cat = "general" if market == "us_stock" else "general"
            all_items.extend(fh.fetch_market_news(category=cat, limit=limit))
        except Exception as e:
            logger.debug(f"Finnhub market news failed: {e}")

    index_tickers = {
        "us_stock": ["^GSPC", "^IXIC", "^DJI"],
        "hk_stock": ["^HSI", "^HSTECH"],
    }
    tickers = index_tickers.get(market, index_tickers["us_stock"])

    try:
        gn = GoogleNewsRSS()
        for tk in tickers[:2]:
            try:
                items = gn.fetch(tk, market, 5)
                all_items.extend(items)
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"Google News market fetch failed: {e}")

    if nc.marketaux_key:
        try:
            mx = MarketAuxNews(nc.marketaux_key)
            search = "stock market" if market == "us_stock" else "hong kong stock"
            items = mx.fetch(tickers[0], market, 8)
            all_items.extend(items)
        except Exception as e:
            logger.debug(f"MarketAux market news failed: {e}")

    deduped = _dedup_news(all_items)
    deduped.sort(key=lambda x: x.get("credibility", 0), reverse=True)
    return deduped[:limit]


def analyze_sentiment(news_items: list[dict]) -> dict:
    """Quick keyword-based sentiment (used as fallback when LLM unavailable)."""
    if not news_items:
        return {
            "score": 0.0,
            "label": "neutral",
            "positive": 0,
            "negative": 0,
            "summary": "No news items",
        }

    text = " ".join(
        str(it.get("title", "")) + " " + str(it.get("publisher", ""))
        + " " + str(it.get("summary", ""))
        for it in news_items
    ).lower()

    pos = sum(text.count(kw) for kw in _POSITIVE)
    neg = sum(text.count(kw) for kw in _NEGATIVE)
    total = pos + neg
    if total == 0:
        score = 0.0
        label = "neutral"
    else:
        score = max(-1.0, min(1.0, (pos - neg) / total))
        if score > 0.15:
            label = "bullish"
        elif score < -0.15:
            label = "bearish"
        else:
            label = "neutral"

    summary = f"{pos} positive / {neg} negative across {len(news_items)} items"
    return {
        "score": round(score, 4),
        "label": label,
        "positive": pos,
        "negative": neg,
        "summary": summary,
    }
