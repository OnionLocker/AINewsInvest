"""Unified yfinance data source for US and HK stocks.

Provides: quotes, K-lines, financials, news, index components.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import yfinance as yf
from loguru import logger


def to_yf_ticker(ticker: str, market: str) -> str:
    if market == "hk_stock":
        t = ticker.replace(".HK", "")
        return f"{t}.HK"
    return ticker


# -- Quotes --

def get_quote(ticker: str, market: str) -> dict[str, Any] | None:
    symbol = to_yf_ticker(ticker, market)
    try:
        t = yf.Ticker(symbol)
        info = t.fast_info
        price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
        prev = getattr(info, "previous_close", None)
        if price is None:
            return None
        change_pct = round((price - prev) / prev * 100, 2) if prev and prev > 0 else 0.0
        return {
            "ticker": ticker, "market": market,
            "price": round(float(price), 4), "change_pct": change_pct,
            "volume": int(getattr(info, "last_volume", 0) or 0),
            "market_cap": float(getattr(info, "market_cap", 0) or 0),
            "day_high": float(getattr(info, "day_high", 0) or 0),
            "day_low": float(getattr(info, "day_low", 0) or 0),
            "year_high": float(getattr(info, "year_high", 0) or 0),
            "year_low": float(getattr(info, "year_low", 0) or 0),
        }
    except Exception as e:
        logger.warning(f"Quote failed {symbol}: {e}")
        return None


def get_quotes_batch(items: list[dict]) -> list[dict]:
    results = []
    for item in items:
        q = get_quote(item["ticker"], item["market"])
        if q:
            q["name"] = item.get("name", "")
        else:
            q = {"ticker": item["ticker"], "market": item["market"],
                 "name": item.get("name", ""), "price": None, "change_pct": None}
        results.append(q)
    return results


# -- K-lines --

def get_klines(ticker: str, market: str, days: int = 60) -> pd.DataFrame:
    symbol = to_yf_ticker(ticker, market)
    try:
        t = yf.Ticker(symbol)
        end = datetime.now()
        start = end - timedelta(days=days + 15)
        df = t.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
        if df.empty:
            return pd.DataFrame()
        df = df.reset_index().rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        return df[["date", "open", "high", "low", "close", "volume"]].tail(days)
    except Exception as e:
        logger.warning(f"Kline failed {symbol}: {e}")
        return pd.DataFrame()


# -- Financials --

def get_financial_data(ticker: str, market: str) -> dict[str, Any] | None:
    symbol = to_yf_ticker(ticker, market)
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
        if not info.get("symbol"):
            return None
        indicators = _extract_multi_year(t.balance_sheet, t.financials, t.cashflow)
        return {
            "ticker": ticker, "market": market,
            "name": info.get("shortName", ""),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "pe_ttm": info.get("trailingPE"),
            "pb": info.get("priceToBook"),
            "market_cap": info.get("marketCap", 0),
            "dividend_yield": info.get("dividendYield"),
            "roe": info.get("returnOnEquity"),
            "current_ratio": info.get("currentRatio"),
            "debt_to_equity": info.get("debtToEquity"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "gross_margins": info.get("grossMargins"),
            "operating_margins": info.get("operatingMargins"),
            "profit_margins": info.get("profitMargins"),
            "total_revenue": info.get("totalRevenue"),
            "total_debt": info.get("totalDebt"),
            "total_cash": info.get("totalCash"),
            "free_cashflow": info.get("freeCashflow"),
            "book_value": info.get("bookValue"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "indicators": indicators,
        }
    except Exception as e:
        logger.warning(f"Financial data failed {symbol}: {e}")
        return None


def _extract_multi_year(bs, fin, cf) -> list[dict]:
    indicators: list[dict] = []
    if fin is None or fin.empty:
        return indicators
    for col in fin.columns:
        year = col.year if hasattr(col, "year") else str(col)[:4]
        entry: dict[str, Any] = {"year": int(year)}
        revenue = _safe_val(fin, "Total Revenue", col)
        net_income = _safe_val(fin, "Net Income", col)
        gross_profit = _safe_val(fin, "Gross Profit", col)
        if revenue and revenue > 0:
            if gross_profit:
                entry["gross_margin"] = round(gross_profit / revenue * 100, 2)
            if net_income:
                entry["net_margin"] = round(net_income / revenue * 100, 2)
        if bs is not None and col in bs.columns:
            equity = _safe_val(bs, "Stockholders Equity", col)
            total_assets = _safe_val(bs, "Total Assets", col)
            debt = _safe_val(bs, "Total Debt", col) or _safe_val(bs, "Long Term Debt", col)
            ca = _safe_val(bs, "Current Assets", col)
            cl = _safe_val(bs, "Current Liabilities", col)
            if equity and equity > 0 and net_income:
                entry["roe"] = round(net_income / equity * 100, 2)
            if total_assets and total_assets > 0 and debt:
                entry["debt_ratio"] = round(debt / total_assets * 100, 2)
            if cl and cl > 0 and ca:
                entry["current_ratio"] = round(ca / cl, 2)
        indicators.append(entry)
    indicators.sort(key=lambda x: x.get("year", 0))
    return indicators


def _safe_val(df, label: str, col) -> float | None:
    if df is None or df.empty:
        return None
    for idx in df.index:
        if label.lower() in str(idx).lower():
            try:
                val = df.loc[idx, col]
                if pd.notna(val):
                    return float(val)
            except (KeyError, TypeError, ValueError):
                pass
    return None


# -- News --

def get_news(ticker: str, market: str, limit: int = 10) -> list[dict]:
    symbol = to_yf_ticker(ticker, market)
    try:
        t = yf.Ticker(symbol)
        raw = t.news or []
        return [{"title": n.get("title", ""), "publisher": n.get("publisher", ""),
                 "link": n.get("link", ""), "published": n.get("providerPublishTime", "")}
                for n in raw[:limit]]
    except Exception as e:
        logger.warning(f"News failed {symbol}: {e}")
        return []


# -- Index components --

def get_index_components(index_symbol: str) -> list[dict]:
    try:
        if index_symbol in ("^GSPC", "^SPX"):
            return _sp500_components()
        if index_symbol in ("^NDX", "^IXIC"):
            return _nasdaq100_components()
        if index_symbol == "^HSI":
            return _hsi_components()
        if index_symbol == "^HSTECH":
            return _hstech_components()
        return []
    except Exception as e:
        logger.error(f"Index components failed {index_symbol}: {e}")
        return []


def _sp500_components() -> list[dict]:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    df = pd.read_html(url)[0]
    return [{"ticker": str(r.get("Symbol", "")).strip().replace(".", "-"),
             "name": str(r.get("Security", "")).strip(), "market": "us_stock"}
            for _, r in df.iterrows() if str(r.get("Symbol", "")).strip()]


def _nasdaq100_components() -> list[dict]:
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    for tbl in pd.read_html(url):
        col = "Ticker" if "Ticker" in tbl.columns else ("Symbol" if "Symbol" in tbl.columns else None)
        if col:
            nc = "Company" if "Company" in tbl.columns else "Security"
            return [{"ticker": str(r.get(col, "")).strip(),
                     "name": str(r.get(nc, "")).strip(), "market": "us_stock"}
                    for _, r in tbl.iterrows() if str(r.get(col, "")).strip()]
    return []


def _hsi_components() -> list[dict]:
    url = "https://en.wikipedia.org/wiki/Hang_Seng_Index"
    for tbl in pd.read_html(url):
        cols_lower = [str(c).lower() for c in tbl.columns]
        if any("ticker" in c or "stock code" in c for c in cols_lower):
            results = []
            for _, row in tbl.iterrows():
                for c in tbl.columns:
                    if "ticker" in str(c).lower() or "stock code" in str(c).lower():
                        raw = str(row[c]).strip().replace(".0", "")
                        t = raw.zfill(4) if raw.isdigit() else raw
                        nc = [x for x in tbl.columns if "company" in str(x).lower() or "name" in str(x).lower()]
                        n = str(row[nc[0]]).strip() if nc else t
                        if t and t != "nan":
                            results.append({"ticker": t, "name": n, "market": "hk_stock"})
                        break
            if results:
                return results
    return []


def _hstech_components() -> list[dict]:
    return [{"ticker": t, "name": n, "market": "hk_stock"} for t, n in [
        ("9988", "Alibaba"), ("0700", "Tencent"), ("3690", "Meituan"),
        ("9999", "NetEase"), ("1810", "Xiaomi"), ("9618", "JD.com"),
        ("0981", "SMIC"), ("9888", "Baidu"), ("0285", "BYD Electronic"),
        ("6060", "ZhongAn"), ("1347", "Hua Hong Semi"), ("2382", "Sunny Optical"),
        ("0268", "Kingdee"), ("0241", "Ali Health"), ("0772", "China Literature"),
        ("1024", "Kuaishou"), ("2015", "Li Auto"),
        ("9866", "NIO"), ("9868", "XPeng"), ("6618", "JD Health"),
        ("9626", "Bilibili"),
    ]]


def _get_market_breadth(market: str) -> dict:
    """Get advance/decline breadth data for a market.

    Uses a sample of major index components to estimate market breadth.
    """
    try:
        if market == "us_stock":
            symbols = [
                "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA",
                "BRK-B", "JPM", "V", "JNJ", "UNH", "XOM", "PG", "MA",
                "HD", "CVX", "LLY", "ABBV", "MRK", "PEP", "KO", "COST",
                "AVGO", "TMO", "WMT", "MCD", "CRM", "CSCO", "ACN",
            ]
        else:
            symbols = [
                "0700.HK", "9988.HK", "3690.HK", "1810.HK", "0005.HK",
                "0388.HK", "0941.HK", "1299.HK", "0883.HK", "0002.HK",
                "0016.HK", "0003.HK", "0011.HK", "2318.HK", "0027.HK",
                "0001.HK", "0006.HK", "0012.HK", "1038.HK", "0017.HK",
            ]

        tickers_obj = yf.Tickers(" ".join(symbols))
        advance = 0
        decline = 0
        unchanged = 0

        for sym in symbols:
            try:
                info = tickers_obj.tickers[sym.replace("-", "-")].fast_info
                price = getattr(info, "last_price", None)
                prev = getattr(info, "previous_close", None)
                if price and prev and prev > 0:
                    pct = (price - prev) / prev * 100
                    if pct > 0.05:
                        advance += 1
                    elif pct < -0.05:
                        decline += 1
                    else:
                        unchanged += 1
            except Exception:
                continue

        total = advance + decline + unchanged
        if total == 0:
            return {"advance": 0, "decline": 0, "unchanged": 0, "advance_pct": 50.0}

        return {
            "advance": advance,
            "decline": decline,
            "unchanged": unchanged,
            "total": total,
            "advance_pct": round(advance / total * 100, 1),
        }
    except Exception as e:
        logger.warning(f"Market breadth failed: {e}")
        return {"advance": 0, "decline": 0, "unchanged": 0, "advance_pct": 50.0}


def get_market_indices() -> list[dict]:
    indices = [
        ("^GSPC", "标普500", "us_stock"), ("^IXIC", "纳斯达克", "us_stock"),
        ("^DJI", "道琼斯", "us_stock"),
        ("^HSI", "恒生指数", "hk_stock"), ("^HSTECH", "恒生科技", "hk_stock"),
    ]
    results = []
    for symbol, label, market in indices:
        try:
            t = yf.Ticker(symbol)
            info = t.fast_info
            price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
            prev = getattr(info, "previous_close", None)
            if price and prev and prev > 0:
                results.append({"name": label, "market": market,
                                "price": round(float(price), 2),
                                "change_pct": round((price - prev) / prev * 100, 2)})
        except Exception:
            pass
    return results
