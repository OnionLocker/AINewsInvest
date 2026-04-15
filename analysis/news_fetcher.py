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
import time
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


# ---------------------------------------------------------------------------
# Improved keyword sentiment — word-boundary matching + negation + weights
# ---------------------------------------------------------------------------

# Weighted keyword lists: (keyword, weight)
# Weight reflects how directly the keyword signals price direction.
# 3 = strong directional signal, 2 = moderate, 1 = weak/ambiguous
_POSITIVE_WEIGHTED = [
    # Strong (direct price action)
    ("surge", 3), ("soar", 3), ("beat", 3), ("rally", 3),
    ("breakout", 3), ("outperform", 3), ("record high", 3),
    # Moderate (likely positive for price)
    ("upgrade", 2), ("growth", 2), ("profit", 2), ("bullish", 2),
    ("gain", 2), ("buyback", 2), ("dividend", 2), ("approval", 2),
    ("strong", 2), ("beat expectations", 3), ("raised guidance", 3),
    ("exceeded", 2), ("accelerat", 2), ("momentum", 2),
    # Weak (context-dependent)
    ("buy", 1), ("partnership", 1), ("contract", 1),
    ("record", 1), ("positive", 1), ("optimis", 1),
]

_NEGATIVE_WEIGHTED = [
    # Strong (direct price action)
    ("crash", 3), ("plunge", 3), ("miss", 3), ("fraud", 3),
    ("bankruptcy", 3), ("default", 3), ("investigation", 3),
    ("recall", 3), ("missed expectations", 3), ("lowered guidance", 3),
    # Moderate (likely negative for price)
    ("downgrade", 2), ("loss", 2), ("bearish", 2), ("decline", 2),
    ("warning", 2), ("sell", 2), ("layoff", 2), ("lawsuit", 2),
    ("weak", 2), ("debt", 2), ("cut", 2), ("slump", 2),
    ("delay", 2), ("suspend", 2), ("probe", 2),
    # Weak (context-dependent)
    ("risk", 1), ("concern", 1), ("uncertain", 1),
    ("volatil", 1), ("pressure", 1),
]

# Negation words — if found within 3 words before a keyword, flip polarity
_NEGATION_WORDS = {
    "not", "no", "never", "neither", "nor", "none",
    "don't", "doesn't", "didn't", "won't", "wouldn't",
    "can't", "cannot", "isn't", "aren't", "wasn't", "weren't",
    "hasn't", "haven't", "hadn't", "without", "lack", "fail",
    "failed", "fails", "unlikely", "unable",
}


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
    else:
        logger.warning(
            "Finnhub API key not configured — "
            "Bloomberg/Reuters/WSJ aggregation disabled. "
            "Register free at https://finnhub.io/register"
        )

    if nc.marketaux_key:
        sources.append(("marketaux", MarketAuxNews(nc.marketaux_key)))
    else:
        logger.warning(
            "MarketAux API key not configured — "
            "HK/China news coverage and pre-computed sentiment disabled. "
            "Register free at https://www.marketaux.com/register"
        )

    sources.append(("google_news", GoogleNewsRSS()))
    sources.append(("sec_edgar", SECEdgarNews()))

    return sources


# Cache source warnings so they only fire once per session
_source_warned: set[str] = set()


def _warn_once(key: str, msg: str) -> None:
    if key not in _source_warned:
        logger.warning(msg)
        _source_warned.add(key)


def _fetch_with_retry(src, name: str, ticker: str, market: str, limit: int, max_retries: int = 1) -> list[dict]:
    """Fetch news from a single source with retry on failure."""
    for attempt in range(1 + max_retries):
        try:
            items = src.fetch(ticker, market, limit)
            if items:
                return items
            return []
        except Exception as e:
            if attempt < max_retries:
                wait = 2 ** (attempt + 1)
                logger.debug(f"News {name} attempt {attempt + 1} failed for {ticker}: {e}, retrying in {wait}s")
                time.sleep(wait)
            else:
                logger.warning(f"News {name} all attempts failed for {ticker}: {e}")
    return []


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
            futs[ex.submit(_fetch_with_retry, src, name, ticker, market, per_source)] = name

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
            items = mx.fetch(tickers[0], market, 8)
            all_items.extend(items)
        except Exception as e:
            logger.debug(f"MarketAux market news failed: {e}")

    deduped = _dedup_news(all_items)
    deduped.sort(key=lambda x: x.get("credibility", 0), reverse=True)
    return deduped[:limit]


# ---------------------------------------------------------------------------
# News quality report — lets downstream know how much to trust the data
# ---------------------------------------------------------------------------

def news_quality_report(news_items: list[dict]) -> dict:
    """Assess the quality / completeness of fetched news.

    Returns a dict describing data source health so that downstream
    layers can adjust weights accordingly.

    Keys:
      - source_count: number of distinct origins
      - item_count: total items
      - has_premium: True if Finnhub or MarketAux provided data
      - has_pre_sentiment: True if any item has API-computed sentiment
      - avg_credibility: mean credibility across items
      - quality_tier: "good" | "fair" | "poor"
      - suggested_weight_factor: 0.3-1.0  (multiply against news_weight)
    """
    if not news_items:
        return {
            "source_count": 0,
            "item_count": 0,
            "has_premium": False,
            "has_pre_sentiment": False,
            "avg_credibility": 0.0,
            "quality_tier": "poor",
            "suggested_weight_factor": 0.3,
        }

    origins = {it.get("origin", "") for it in news_items}
    has_premium = bool(origins & {"finnhub", "marketaux", "finnhub_market"})
    has_pre_sent = any(it.get("pre_sentiment") is not None for it in news_items)
    avg_cred = sum(it.get("credibility", 0.5) for it in news_items) / len(news_items)

    # Quality tier logic
    n = len(news_items)
    src_n = len(origins)

    if has_premium and n >= 8 and src_n >= 3:
        tier = "good"
        factor = 1.0
    elif n >= 5 and src_n >= 2:
        tier = "fair"
        factor = 0.7
    elif n >= 2:
        tier = "fair"
        factor = 0.5
    else:
        tier = "poor"
        factor = 0.3

    # Boost slightly if pre-computed sentiment available
    if has_pre_sent:
        factor = min(1.0, factor + 0.1)

    return {
        "source_count": src_n,
        "item_count": n,
        "has_premium": has_premium,
        "has_pre_sentiment": has_pre_sent,
        "avg_credibility": round(avg_cred, 3),
        "quality_tier": tier,
        "suggested_weight_factor": round(factor, 2),
    }


# ---------------------------------------------------------------------------
# Improved sentiment analysis (fallback when LLM unavailable)
# ---------------------------------------------------------------------------

def _has_negation_before(words: list[str], idx: int, window: int = 3) -> bool:
    """Check if any negation word appears within `window` words before `idx`."""
    start = max(0, idx - window)
    for i in range(start, idx):
        if words[i] in _NEGATION_WORDS:
            return True
    return False


def _score_text_sentiment(text: str, credibility: float = 0.7) -> tuple[float, float]:
    """Score a single text blob.

    Returns (positive_score, negative_score) where each is a weighted sum.
    Uses word-boundary matching + negation detection + credibility weighting.
    """
    text_lower = text.lower()
    # Tokenize for negation detection (simple whitespace split)
    words = re.split(r"\s+", text_lower)
    words_str = " ".join(words)  # rejoin for phrase matching

    pos_total = 0.0
    neg_total = 0.0

    # Score positive keywords
    for kw, weight in _POSITIVE_WEIGHTED:
        # Use word boundary for single words, substring for phrases
        if " " in kw:
            count = words_str.count(kw)
        else:
            count = len(re.findall(r"\b" + re.escape(kw) + r"\w*\b", text_lower))

        if count == 0:
            continue

        # Check negation — for each occurrence, see if negated
        # For simplicity, check if negation appears near keyword in text
        negated = 0
        for m in re.finditer(r"\b" + re.escape(kw), text_lower):
            pos_in_words = text_lower[:m.start()].count(" ")
            if _has_negation_before(words, pos_in_words):
                negated += 1

        affirmed = max(0, count - negated)
        flipped = negated  # negated positives become negative

        pos_total += affirmed * weight * credibility
        neg_total += flipped * weight * credibility * 0.7  # flipped weaker than direct

    # Score negative keywords
    for kw, weight in _NEGATIVE_WEIGHTED:
        if " " in kw:
            count = words_str.count(kw)
        else:
            count = len(re.findall(r"\b" + re.escape(kw) + r"\w*\b", text_lower))

        if count == 0:
            continue

        negated = 0
        for m in re.finditer(r"\b" + re.escape(kw), text_lower):
            pos_in_words = text_lower[:m.start()].count(" ")
            if _has_negation_before(words, pos_in_words):
                negated += 1

        affirmed = max(0, count - negated)
        flipped = negated

        neg_total += affirmed * weight * credibility
        pos_total += flipped * weight * credibility * 0.7

    return pos_total, neg_total


def analyze_sentiment(news_items: list[dict]) -> dict:
    """Credibility-weighted, negation-aware keyword sentiment analysis.

    Improvements over v1:
      1. Word-boundary matching (no more "downgrader" matching "upgrade")
      2. Negation detection ("not beat earnings" → negative, not positive)
      3. Weighted keywords (strong signals count more than ambiguous ones)
      4. Per-item credibility weighting (Reuters counts more than random blog)
      5. Pre-computed sentiment from MarketAux is included when available

    This is still a FALLBACK — the LLM News Agent does the real analysis.
    """
    if not news_items:
        return {
            "score": 0.0,
            "label": "neutral",
            "positive": 0.0,
            "negative": 0.0,
            "summary": "No news items",
            "quality": news_quality_report([]),
        }

    total_pos = 0.0
    total_neg = 0.0
    pre_sentiment_scores: list[float] = []

    for it in news_items:
        cred = it.get("credibility", 0.5)
        text = " ".join(filter(None, [
            str(it.get("title", "")),
            str(it.get("summary", "")),
        ]))
        p, n = _score_text_sentiment(text, cred)
        total_pos += p
        total_neg += n

        # Incorporate pre-computed sentiment (e.g., from MarketAux)
        pre = it.get("pre_sentiment")
        if pre is not None:
            try:
                pre_sentiment_scores.append(float(pre))
            except (TypeError, ValueError):
                pass

    # Combine keyword sentiment with pre-computed sentiment
    total = total_pos + total_neg
    if total > 0:
        keyword_score = (total_pos - total_neg) / total  # [-1, 1]
    else:
        keyword_score = 0.0

    # Blend with pre-computed if available (pre-computed is generally better)
    if pre_sentiment_scores:
        pre_avg = sum(pre_sentiment_scores) / len(pre_sentiment_scores)
        # Weighted blend: 60% pre-computed, 40% keyword
        score = 0.6 * pre_avg + 0.4 * keyword_score
    else:
        score = keyword_score

    score = max(-1.0, min(1.0, score))

    # Thresholds — use 0.12 instead of hardcoded 0.15 for better sensitivity
    if score > 0.12:
        label = "bullish"
    elif score < -0.12:
        label = "bearish"
    else:
        label = "neutral"

    quality = news_quality_report(news_items)
    summary = (
        f"pos={total_pos:.1f} neg={total_neg:.1f} across {len(news_items)} items"
        f" ({quality['source_count']} sources, quality={quality['quality_tier']})"
    )

    return {
        "score": round(score, 4),
        "label": label,
        "positive": round(total_pos, 2),
        "negative": round(total_neg, 2),
        "summary": summary,
        "quality": quality,
    }
