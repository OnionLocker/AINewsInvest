"""Multi-source financial news fetchers.

Each source class returns a standardized list of news dicts:
  {
    "title": str,
    "publisher": str,
    "link": str,
    "published": int (unix timestamp) or str,
    "summary": str,
    "source_tier": "official" | "analyst" | "media" | "aggregator" | "social",
    "credibility": float (0.0 - 1.0),
    "origin": str (source name for dedup tracking),
  }

Design philosophy (from a trading P&L perspective):
  - Official filings/announcements are MOST actionable (earnings, 8-K, HKEX)
  - Analyst upgrades/downgrades directly move prices
  - Top-tier media (Bloomberg, Reuters, WSJ) break news fastest
  - Aggregators/social have noise but catch breadth
  - Every item tagged with credibility so LLM Agent can weight accordingly
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote_plus

import httpx
from loguru import logger


# ---------------------------------------------------------------------------
# Publisher credibility database
# ---------------------------------------------------------------------------

_TIER_OFFICIAL = {
    "sec.gov", "sec filing", "edgar", "hkexnews", "hkex",
    "federal reserve", "treasury", "pboc",
}
_TIER_ANALYST = {
    "goldman sachs", "morgan stanley", "jpmorgan", "jp morgan",
    "citigroup", "bank of america", "ubs", "hsbc", "barclays",
    "credit suisse", "deutsche bank", "nomura", "clsa",
    "bernstein", "jefferies", "raymond james", "piper sandler",
    "moody", "s&p global", "fitch",
}
_TIER_TOP_MEDIA = {
    "bloomberg", "reuters", "wsj", "wall street journal",
    "financial times", "ft.com", "barron", "cnbc",
    "south china morning post", "scmp", "hkej",
    "caixin", "nikkei", "the economist",
}
_TIER_MEDIA = {
    "marketwatch", "yahoo finance", "seeking alpha", "motley fool",
    "investopedia", "benzinga", "thestreet", "investor",
    "business insider", "fortune", "forbes",
    "aastocks", "etnet", "sina finance", "east money",
    "10jqka", "cls.cn", "yicai", "wallstreetcn",
}


def classify_publisher(publisher: str) -> tuple[str, float]:
    """Classify publisher into tier and credibility score."""
    p = (publisher or "").lower().strip()
    if not p:
        return "aggregator", 0.5

    for kw in _TIER_OFFICIAL:
        if kw in p:
            return "official", 1.0
    for kw in _TIER_ANALYST:
        if kw in p:
            return "analyst", 0.85
    for kw in _TIER_TOP_MEDIA:
        if kw in p:
            return "media", 0.80
    for kw in _TIER_MEDIA:
        if kw in p:
            return "media", 0.70
    return "aggregator", 0.55


def _tag_item(item: dict, origin: str) -> dict:
    """Add credibility metadata to a news item."""
    tier, cred = classify_publisher(item.get("publisher", ""))
    item["source_tier"] = tier
    item["credibility"] = cred
    item["origin"] = origin
    return item


# ---------------------------------------------------------------------------
# Source 1: Yahoo Finance (via yfinance)
# ---------------------------------------------------------------------------

class YFinanceNews:
    """Yahoo Finance news via yfinance library.
    Pros: No API key, decent US coverage, some HK
    Cons: Limited HK mid-cap coverage, no sentiment
    """

    def fetch(self, ticker: str, market: str, limit: int = 10) -> list[dict]:
        import yfinance as yf
        from core.data_source import to_yf_ticker

        symbol = to_yf_ticker(ticker, market)
        try:
            t = yf.Ticker(symbol)
            raw = t.news or []
            items = []
            for n in raw[:limit]:
                item = {
                    "title": n.get("title", ""),
                    "publisher": n.get("publisher", ""),
                    "link": n.get("link", ""),
                    "published": n.get("providerPublishTime", ""),
                    "summary": "",
                }
                items.append(_tag_item(item, "yahoo_finance"))
            return items
        except Exception as e:
            logger.debug(f"YFinance news failed {symbol}: {e}")
            return []


# ---------------------------------------------------------------------------
# Source 2: Finnhub (best free API for trading)
# ---------------------------------------------------------------------------

class FinnhubNews:
    """Finnhub company news API.
    Pros: Aggregates Bloomberg/Reuters/WSJ, 60 calls/min free, 1yr history
    Cons: Needs free API key, HK coverage varies
    Why it matters for P&L: Fastest aggregator of top-tier sources,
    catches earnings surprises and analyst actions early.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://finnhub.io/api/v1"

    def _to_finnhub_symbol(self, ticker: str, market: str) -> str:
        if market == "hk_stock":
            t = ticker.replace(".HK", "")
            return f"{t}.HK"
        return ticker

    def fetch(self, ticker: str, market: str, limit: int = 15) -> list[dict]:
        if not self.api_key:
            # Caller (_get_sources in news_fetcher) already logs the warning
            return []

        symbol = self._to_finnhub_symbol(ticker, market)
        today = datetime.now()
        from_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")

        url = f"{self.base_url}/company-news"
        params = {
            "symbol": symbol,
            "from": from_date,
            "to": to_date,
            "token": self.api_key,
        }

        try:
            with httpx.Client(timeout=10) as client:
                r = client.get(url, params=params)
                r.raise_for_status()
                data = r.json()

            if not isinstance(data, list):
                return []

            items = []
            for n in data[:limit]:
                pub = n.get("source", "")
                item = {
                    "title": n.get("headline", ""),
                    "publisher": pub,
                    "link": n.get("url", ""),
                    "published": n.get("datetime", 0),
                    "summary": (n.get("summary") or "")[:300],
                }
                items.append(_tag_item(item, "finnhub"))
            return items

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("Finnhub rate limited, waiting 5s and retrying once")
                time.sleep(5)
                try:
                    with httpx.Client(timeout=10) as client2:
                        r2 = client2.get(url, params=params)
                        r2.raise_for_status()
                        data2 = r2.json()
                    if isinstance(data2, list):
                        items2 = []
                        for n in data2[:limit]:
                            item2 = {
                                "title": n.get("headline", ""),
                                "publisher": n.get("source", ""),
                                "link": n.get("url", ""),
                                "published": n.get("datetime", 0),
                                "summary": (n.get("summary") or "")[:300],
                            }
                            items2.append(_tag_item(item2, "finnhub"))
                        return items2
                except Exception:
                    pass
                return []
            else:
                logger.debug(f"Finnhub news failed {symbol}: {e}")
            return []
        except Exception as e:
            logger.debug(f"Finnhub news failed {symbol}: {e}")
            return []

    def fetch_market_news(self, category: str = "general", limit: int = 20) -> list[dict]:
        """Fetch general market-level news (macro, Fed, etc.)."""
        if not self.api_key:
            return []

        url = f"{self.base_url}/news"
        params = {"category": category, "token": self.api_key}

        try:
            with httpx.Client(timeout=10) as client:
                r = client.get(url, params=params)
                r.raise_for_status()
                data = r.json()

            items = []
            for n in data[:limit]:
                item = {
                    "title": n.get("headline", ""),
                    "publisher": n.get("source", ""),
                    "link": n.get("url", ""),
                    "published": n.get("datetime", 0),
                    "summary": (n.get("summary") or "")[:300],
                }
                items.append(_tag_item(item, "finnhub_market"))
            return items
        except Exception as e:
            logger.debug(f"Finnhub market news failed: {e}")
            return []


# ---------------------------------------------------------------------------
# Source 3: MarketAux (global coverage, built-in sentiment)
# ---------------------------------------------------------------------------

class MarketAuxNews:
    """MarketAux news API.
    Pros: 5000+ sources, 80+ markets, built-in sentiment, good HK/China coverage
    Cons: Free tier has daily limit
    Why it matters for P&L: Best coverage for HK/China stocks among free APIs,
    pre-computed sentiment saves LLM tokens.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.marketaux.com/v1/news/all"

    def fetch(self, ticker: str, market: str, limit: int = 10) -> list[dict]:
        if not self.api_key:
            return []

        symbols = ticker
        if market == "hk_stock":
            t = ticker.replace(".HK", "")
            symbols = f"{t}.HK"

        params: dict[str, Any] = {
            "symbols": symbols,
            "filter_entities": "true",
            "limit": min(limit, 10),
            "api_token": self.api_key,
        }
        if market == "hk_stock":
            params["countries"] = "hk,cn"

        try:
            with httpx.Client(timeout=10) as client:
                r = client.get(self.base_url, params=params)
                r.raise_for_status()
                data = r.json()

            articles = data.get("data") or []
            items = []
            for a in articles[:limit]:
                pub = a.get("source", "")
                sentiment_score = None
                entities = a.get("entities") or []
                for ent in entities:
                    if ent.get("symbol", "").upper() == ticker.upper():
                        sentiment_score = ent.get("sentiment_score")
                        break

                item = {
                    "title": a.get("title", ""),
                    "publisher": pub,
                    "link": a.get("url", ""),
                    "published": a.get("published_at", ""),
                    "summary": (a.get("description") or "")[:300],
                }
                if sentiment_score is not None:
                    item["pre_sentiment"] = round(float(sentiment_score), 3)

                items.append(_tag_item(item, "marketaux"))
            return items

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("MarketAux rate limited, waiting 3s and retrying once")
                time.sleep(3)
                try:
                    with httpx.Client(timeout=10) as client2:
                        r2 = client2.get(self.base_url, params=params)
                        r2.raise_for_status()
                        data2 = r2.json()
                    articles2 = data2.get("data") or []
                    items2 = []
                    for a in articles2[:limit]:
                        item2 = {
                            "title": a.get("title", ""),
                            "publisher": a.get("source", ""),
                            "link": a.get("url", ""),
                            "published": a.get("published_at", ""),
                            "summary": (a.get("description") or "")[:300],
                        }
                        items2.append(_tag_item(item2, "marketaux"))
                    return items2
                except Exception:
                    pass
                return []
            elif e.response.status_code == 402:
                logger.debug("MarketAux free quota exhausted")
            else:
                logger.debug(f"MarketAux failed {ticker}: {e}")
            return []
        except Exception as e:
            logger.debug(f"MarketAux failed {ticker}: {e}")
            return []


# ---------------------------------------------------------------------------
# Source 4: Google News RSS (free, no key, global, supports Chinese)
# ---------------------------------------------------------------------------

class GoogleNewsRSS:
    """Google News RSS feed.
    Pros: Free, no API key, no rate limit, supports Chinese for HK stocks
    Cons: XML parsing, lower signal-to-noise, no sentiment
    Why it matters for P&L: Catches breaking news from ANY source globally,
    good for detecting regime changes and unexpected events.
    For HK stocks, fetches Chinese-language news that other APIs miss.
    """

    def _build_url(self, ticker: str, market: str) -> str:
        if market == "hk_stock":
            t = ticker.replace(".HK", "")
            query = f"{t}.HK stock"
            return (
                f"https://news.google.com/rss/search?"
                f"q={quote_plus(query)}&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
            )
        else:
            query = f"{ticker} stock"
            return (
                f"https://news.google.com/rss/search?"
                f"q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
            )

    def _parse_rss(self, xml_text: str) -> list[dict]:
        items = []
        try:
            root = ET.fromstring(xml_text)
            for item_el in root.findall(".//item"):
                title = (item_el.findtext("title") or "").strip()
                link = (item_el.findtext("link") or "").strip()
                pub_date = (item_el.findtext("pubDate") or "").strip()
                source = (item_el.findtext("source") or "").strip()

                if not title:
                    continue

                if " - " in title and not source:
                    parts = title.rsplit(" - ", 1)
                    if len(parts) == 2:
                        title = parts[0].strip()
                        source = parts[1].strip()

                items.append({
                    "title": title,
                    "publisher": source,
                    "link": link,
                    "published": pub_date,
                    "summary": "",
                })
        except ET.ParseError as e:
            logger.debug(f"Google News RSS parse error: {e}")
        return items

    def fetch(self, ticker: str, market: str, limit: int = 10) -> list[dict]:
        url = self._build_url(ticker, market)
        try:
            with httpx.Client(timeout=8, follow_redirects=True) as client:
                r = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
                raw_items = self._parse_rss(r.text)

            items = []
            for item in raw_items[:limit]:
                items.append(_tag_item(item, "google_news"))
            return items

        except Exception as e:
            logger.debug(f"Google News RSS failed {ticker}: {e}")
            return []


# ---------------------------------------------------------------------------
# Source 5: SEC EDGAR full-text search (US official filings)
# ---------------------------------------------------------------------------

class SECEdgarNews:
    """SEC EDGAR full-text search API.
    Pros: Official filings (8-K, earnings, insider trades), credibility=1.0
    Cons: US only, filings not real-time, needs parsing
    Why it matters for P&L: 8-K filings contain material events that
    MUST be disclosed. Catching these before the market prices them in
    is one of the highest-edge signals in US equities.
    """

    EFTS_URL = "https://efts.sec.gov/LATEST/search-index"

    def _cik_search_url(self, ticker: str) -> str:
        return (
            f"https://efts.sec.gov/LATEST/search-index?"
            f"q=%22{quote_plus(ticker)}%22"
            f"&dateRange=custom"
            f"&startdt={(datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')}"
            f"&enddt={datetime.now().strftime('%Y-%m-%d')}"
            f"&forms=8-K,10-Q,10-K,4"
        )

    def fetch(self, ticker: str, market: str, limit: int = 5) -> list[dict]:
        if market != "us_stock":
            return []

        url = (
            f"https://efts.sec.gov/LATEST/search-index?"
            f"q=%22{quote_plus(ticker)}%22"
            f"&forms=8-K,10-Q,10-K,4"
            f"&dateRange=custom"
            f"&startdt={(datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')}"
            f"&enddt={datetime.now().strftime('%Y-%m-%d')}"
        )

        try:
            headers = {
                "User-Agent": "AlphaVault/1.0 research@example.com",
                "Accept": "application/json",
            }
            with httpx.Client(timeout=10, follow_redirects=True) as client:
                r = client.get(url, headers=headers)
                r.raise_for_status()
                data = r.json()

            hits = data.get("hits", {}).get("hits", [])
            items = []
            for h in hits[:limit]:
                src = h.get("_source", {})
                form_type = src.get("form_type", "")
                entity = src.get("entity_name", "")
                filed = src.get("file_date", "")
                title = f"SEC {form_type}: {entity}"
                link = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={quote_plus(ticker)}&type={form_type}"

                item = {
                    "title": title,
                    "publisher": "SEC EDGAR",
                    "link": link,
                    "published": filed,
                    "summary": f"Form {form_type} filed by {entity} on {filed}",
                    "source_tier": "official",
                    "credibility": 1.0,
                    "origin": "sec_edgar",
                }
                items.append(item)
            return items

        except Exception as e:
            logger.debug(f"SEC EDGAR search failed {ticker}: {e}")
            return []


# ---------------------------------------------------------------------------
# Source 6: Seeking Alpha RSS (analyst/community stock analysis)
# ---------------------------------------------------------------------------

class SeekingAlphaRSS:
    """Seeking Alpha per-ticker RSS feed.
    Pros: Free, no API key, analyst-grade commentary, earnings transcripts,
          bullish/bearish thesis per stock. Largest US stock analysis platform.
    Cons: Some delay (not breaking news), editorial slant
    Why it matters for P&L: Analyst buy/sell thesis directly influences
    retail and small-fund positioning. Catching a negative SA article early
    can front-run the retail sell pressure.
    """

    _BASE = "https://seekingalpha.com/api/sa/combined/{ticker}.xml"
    _MARKET_CURRENTS = "https://seekingalpha.com/market_currents.xml"

    def _parse_rss(self, xml_text: str) -> list[dict]:
        items = []
        try:
            root = ET.fromstring(xml_text)
            for item_el in root.findall(".//item"):
                title = (item_el.findtext("title") or "").strip()
                link = (item_el.findtext("link") or "").strip()
                pub_date = (item_el.findtext("pubDate") or "").strip()
                desc = (item_el.findtext("description") or "").strip()

                if not title:
                    continue

                # SA titles sometimes include author: "AAPL: Buy thesis (Author Name)"
                publisher = "Seeking Alpha"
                items.append({
                    "title": title,
                    "publisher": publisher,
                    "link": link,
                    "published": pub_date,
                    "summary": re.sub(r"<[^>]+>", "", desc)[:300] if desc else "",
                })
        except ET.ParseError as e:
            logger.debug(f"Seeking Alpha RSS parse error: {e}")
        return items

    def fetch(self, ticker: str, market: str, limit: int = 8) -> list[dict]:
        # Seeking Alpha only covers US stocks
        if market != "us_stock":
            return []

        url = self._BASE.format(ticker=ticker)
        try:
            with httpx.Client(timeout=8, follow_redirects=True) as client:
                r = client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/131.0.0.0 Safari/537.36",
                })
                if r.status_code == 403:
                    # SA occasionally blocks scraping; graceful degradation
                    logger.debug(f"Seeking Alpha RSS blocked for {ticker}")
                    return []
                r.raise_for_status()
                raw_items = self._parse_rss(r.text)

            items = []
            for item in raw_items[:limit]:
                items.append(_tag_item(item, "seeking_alpha"))
            return items
        except Exception as e:
            logger.debug(f"Seeking Alpha RSS failed {ticker}: {e}")
            return []

    def fetch_market_currents(self, limit: int = 10) -> list[dict]:
        """Fetch Seeking Alpha Market Currents (broad market news)."""
        try:
            with httpx.Client(timeout=8, follow_redirects=True) as client:
                r = client.get(self._MARKET_CURRENTS, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/131.0.0.0 Safari/537.36",
                })
                if r.status_code == 403:
                    return []
                r.raise_for_status()
                raw_items = self._parse_rss(r.text)

            items = []
            for item in raw_items[:limit]:
                items.append(_tag_item(item, "seeking_alpha_market"))
            return items
        except Exception as e:
            logger.debug(f"Seeking Alpha market currents failed: {e}")
            return []


# ---------------------------------------------------------------------------
# Source 7: CNBC RSS (mainstream financial news, fast breaking)
# ---------------------------------------------------------------------------

class CNBCRSS:
    """CNBC RSS feeds for market-moving news.
    Pros: Free, no API key, fast breaking news, institutional credibility,
          multiple category feeds (markets, earnings, economy)
    Cons: No per-ticker feed, broad market news only
    Why it matters for P&L: CNBC is the most-watched financial news source
    during US trading hours. Breaking CNBC headlines move prices in seconds.
    Best used for market-level context, not per-stock signals.
    """

    # Category RSS feed URLs
    _FEEDS = {
        "top_news": "https://search.cnbc.com/rs/search/combinedcms/view.xml"
                    "?partnerId=wrss01&id=100003114",
        "markets": "https://search.cnbc.com/rs/search/combinedcms/view.xml"
                   "?partnerId=wrss01&id=20910258",
        "earnings": "https://search.cnbc.com/rs/search/combinedcms/view.xml"
                    "?partnerId=wrss01&id=15839135",
        "economy": "https://search.cnbc.com/rs/search/combinedcms/view.xml"
                   "?partnerId=wrss01&id=20910258",
        "investing": "https://search.cnbc.com/rs/search/combinedcms/view.xml"
                     "?partnerId=wrss01&id=15839069",
    }

    def _parse_rss(self, xml_text: str) -> list[dict]:
        items = []
        try:
            root = ET.fromstring(xml_text)
            for item_el in root.findall(".//item"):
                title = (item_el.findtext("title") or "").strip()
                link = (item_el.findtext("link") or "").strip()
                pub_date = (item_el.findtext("pubDate") or "").strip()
                desc = (item_el.findtext("description") or "").strip()

                if not title:
                    continue

                items.append({
                    "title": title,
                    "publisher": "CNBC",
                    "link": link,
                    "published": pub_date,
                    "summary": re.sub(r"<[^>]+>", "", desc)[:300] if desc else "",
                })
        except ET.ParseError as e:
            logger.debug(f"CNBC RSS parse error: {e}")
        return items

    def fetch(self, ticker: str, market: str, limit: int = 6) -> list[dict]:
        """Fetch CNBC news relevant to a specific ticker.

        CNBC RSS doesn't have per-ticker feeds, so we search title/description
        for the ticker symbol to filter relevant items.
        """
        if market != "us_stock":
            return []

        # Fetch from markets + earnings feeds (most relevant for individual stocks)
        all_items: list[dict] = []
        for cat in ("markets", "earnings"):
            url = self._FEEDS.get(cat)
            if not url:
                continue
            try:
                with httpx.Client(timeout=8, follow_redirects=True) as client:
                    r = client.get(url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                                      "Chrome/131.0.0.0 Safari/537.36",
                    })
                    r.raise_for_status()
                    all_items.extend(self._parse_rss(r.text))
            except Exception as e:
                logger.debug(f"CNBC RSS {cat} failed: {e}")

        # Filter items that mention the ticker or company name
        ticker_upper = ticker.upper().replace("-", ".").replace("-", " ")
        relevant = []
        for item in all_items:
            text = f"{item.get('title', '')} {item.get('summary', '')}".upper()
            if ticker_upper in text:
                relevant.append(_tag_item(item, "cnbc"))

        return relevant[:limit]

    def fetch_market_news(self, limit: int = 10) -> list[dict]:
        """Fetch broad market news from CNBC (for market context)."""
        all_items: list[dict] = []
        for cat in ("top_news", "markets", "economy"):
            url = self._FEEDS.get(cat)
            if not url:
                continue
            try:
                with httpx.Client(timeout=8, follow_redirects=True) as client:
                    r = client.get(url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                                      "Chrome/131.0.0.0 Safari/537.36",
                    })
                    r.raise_for_status()
                    raw = self._parse_rss(r.text)
                    for item in raw:
                        all_items.append(_tag_item(item, "cnbc_market"))
            except Exception as e:
                logger.debug(f"CNBC RSS {cat} market news failed: {e}")

        return all_items[:limit]
