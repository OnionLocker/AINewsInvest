from __future__ import annotations

from loguru import logger

from core.data_source import get_news

_POSITIVE = [
    "surge", "soar", "beat", "upgrade", "growth", "profit", "bullish",
    "record", "strong", "outperform", "buy", "rally", "gain",
]
_NEGATIVE = [
    "crash", "plunge", "miss", "downgrade", "loss", "bearish", "weak",
    "decline", "sell", "cut", "warning", "debt", "risk",
]


def fetch_news(ticker: str, market: str, limit: int = 10) -> list[dict]:
    return get_news(ticker, market, limit=limit)


def analyze_sentiment(news_items: list[dict]) -> dict:
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

    summary = f"{pos} positive / {neg} negative keyword hits across {len(news_items)} items"
    logger.debug(f"Sentiment {label} score={score:.3f} ({summary})")
    return {
        "score": round(score, 4),
        "label": label,
        "positive": pos,
        "negative": neg,
        "summary": summary,
    }
