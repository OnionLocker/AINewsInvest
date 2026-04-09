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

def get_klines(ticker: str, market: str, days: int = 120) -> pd.DataFrame:
    """Fetch daily OHLCV bars from yfinance.

    Returns a DataFrame with columns: date, open, high, low, close, volume.
    """
    symbol = to_yf_ticker(ticker, market)
    try:
        t = yf.Ticker(symbol)
        end = datetime.now()
        start = end - timedelta(days=days + 10)
        hist = t.history(start=start.strftime("%Y-%m-%d"),
                         end=(end + timedelta(days=1)).strftime("%Y-%m-%d"))
        if hist.empty:
            return pd.DataFrame()

        df = pd.DataFrame({
            "date": hist.index.tz_localize(None) if hist.index.tz else hist.index,
            "open": hist["Open"].values,
            "high": hist["High"].values,
            "low": hist["Low"].values,
            "close": hist["Close"].values,
            "volume": hist["Volume"].values,
        }).reset_index(drop=True)
        return df.tail(days)
    except Exception as e:
        logger.warning(f"K-line fetch failed {symbol}: {e}")
        return pd.DataFrame()


# -- Financials --

def get_financial_data(ticker: str, market: str) -> dict[str, Any] | None:
    """Fetch fundamental financial data from yfinance."""
    symbol = to_yf_ticker(ticker, market)
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
        if not info:
            return None

        def _get(key, default=None):
            v = info.get(key, default)
            return v

        pe_val = _get("trailingPE")
        pb_val = _get("priceToBook")

        result = {
            "roe": _get("returnOnEquity"),
            "gross_margins": _get("grossMargins"),
            "profit_margins": _get("profitMargins"),
            "operating_margins": _get("operatingMargins"),
            "debt_to_equity": _get("debtToEquity"),
            "current_ratio": _get("currentRatio"),
            "revenue_growth": _get("revenueGrowth"),
            "earnings_growth": _get("earningsGrowth"),
            "free_cashflow": _get("freeCashflow"),
            "total_revenue": _get("totalRevenue"),
            "net_income": _get("netIncomeToCommon"),
            "ebitda": _get("ebitda"),
            "total_debt": _get("totalDebt"),
            "total_cash": _get("totalCash"),
            "pe_trailing": pe_val,
            "pe_ttm": pe_val,
            "pe_forward": _get("forwardPE"),
            "peg_ratio": _get("pegRatio"),
            "price_to_book": pb_val,
            "pb": pb_val,
            "short_pct_of_float": _get("shortPercentOfFloat"),
            "held_pct_insiders": _get("heldPercentInsiders"),
            "held_pct_institutions": _get("heldPercentInstitutions"),
            "sector": _get("sector", ""),
            "industry": _get("industry", ""),
        }

        indicators = _build_financial_indicators(t, info)
        if indicators:
            result["indicators"] = indicators

        return result
    except Exception as e:
        logger.warning(f"Financial data failed {symbol}: {e}")
        return None


def _build_financial_indicators(t: Any, info: dict) -> list[dict] | None:
    """Build quarterly financial indicators for trend analysis."""
    try:
        bs = t.quarterly_balance_sheet
        if bs is None or bs.empty:
            return None

        indicators = []
        for col in bs.columns[:4]:
            total_assets = bs.at["Total Assets", col] if "Total Assets" in bs.index else None
            total_debt = bs.at["Total Debt", col] if "Total Debt" in bs.index else None

            debt_ratio = None
            if total_assets and total_debt and total_assets > 0:
                debt_ratio = round(float(total_debt / total_assets * 100), 2)

            indicators.append({
                "period": str(col.date()) if hasattr(col, "date") else str(col),
                "total_assets": float(total_assets) if total_assets else None,
                "total_debt": float(total_debt) if total_debt else None,
                "debt_ratio": debt_ratio,
            })
        return indicators
    except Exception:
        return None


# -- Insider trades --

def get_insider_trades(ticker: str, market: str) -> dict[str, Any] | None:
    """Fetch recent insider trading activity from yfinance.

    v6: Added executive role detection and net flow calculation.
    """
    if market != "us_stock":
        return None
    symbol = to_yf_ticker(ticker, market)
    try:
        t = yf.Ticker(symbol)
        insiders = t.insider_transactions
        if insiders is None or insiders.empty:
            return None

        recent = insiders.head(30)  # v6: expanded from 20 to 30
        buys = 0
        sells = 0
        buy_value = 0.0
        sell_value = 0.0
        executive_buys = 0
        executive_buy_value = 0.0

        _EXEC_TITLES = ("ceo", "cfo", "coo", "cto", "president", "chief",
                        "director", "officer", "vp", "evp", "svp")

        for _, row in recent.iterrows():
            text = str(row.get("Text", "")).lower()
            shares = abs(float(row.get("Shares", 0) or 0))
            value = abs(float(row.get("Value", 0) or 0))

            # v6: Detect executive role
            insider_name = str(row.get("Insider Trading", "") or row.get("Insider", "")).lower()
            is_exec = any(t in insider_name for t in _EXEC_TITLES)

            if "purchase" in text or "buy" in text:
                buys += 1
                buy_value += value
                if is_exec:
                    executive_buys += 1
                    executive_buy_value += value
            elif "sale" in text or "sell" in text:
                sells += 1
                sell_value += value

        total = buys + sells
        if total == 0:
            return {"signal_strength": "neutral", "buys": 0, "sells": 0,
                    "buy_value": 0, "sell_value": 0, "transactions": total,
                    "has_executive_buying": False, "executive_buy_value": 0,
                    "net_insider_flow": 0}

        buy_ratio = buys / total
        if buy_ratio >= 0.7 and buy_value > 100_000:
            signal = "strong_buy"
        elif buy_ratio >= 0.5:
            signal = "moderate_buy"
        elif buy_ratio <= 0.2 and sell_value > 500_000:
            signal = "strong_sell"
        elif buy_ratio <= 0.35:
            signal = "moderate_sell"
        else:
            signal = "neutral"

        return {
            "signal_strength": signal,
            "buys": buys, "sells": sells,
            "buy_value": round(buy_value, 2),
            "sell_value": round(sell_value, 2),
            "transactions": total,
            # v6: Executive role + net flow
            "has_executive_buying": executive_buys > 0,
            "executive_buy_value": round(executive_buy_value, 2),
            "net_insider_flow": round(buy_value - sell_value, 2),
        }
    except Exception as e:
        logger.warning(f"Insider trades failed {symbol}: {e}")
        return None


# -- Options signal --

def get_options_signal(ticker: str, market: str) -> dict[str, Any] | None:
    """Derive a bullish/bearish signal from options data."""
    if market != "us_stock":
        return None
    symbol = to_yf_ticker(ticker, market)
    try:
        t = yf.Ticker(symbol)
        expirations = t.options
        if not expirations:
            return None

        nearest = expirations[0]
        chain = t.option_chain(nearest)
        calls = chain.calls
        puts = chain.puts

        if calls.empty and puts.empty:
            return None

        call_oi = int(calls["openInterest"].sum()) if "openInterest" in calls.columns else 0
        put_oi = int(puts["openInterest"].sum()) if "openInterest" in puts.columns else 0
        call_vol = int(calls["volume"].fillna(0).sum()) if "volume" in calls.columns else 0
        put_vol = int(puts["volume"].fillna(0).sum()) if "volume" in puts.columns else 0

        total_oi = call_oi + put_oi
        pc_ratio = round(put_oi / max(call_oi, 1), 2)
        vol_pc_ratio = round(put_vol / max(call_vol, 1), 2)

        # v6: Unusual activity detection — vol/OI ratio as proxy
        call_vol_ratio = round(call_vol / max(call_oi, 1), 2)
        put_vol_ratio = round(put_vol / max(put_oi, 1), 2)
        unusual_call = call_vol_ratio > 0.5   # Day vol > 50% of open interest
        unusual_put = put_vol_ratio > 0.5

        if pc_ratio < 0.5:
            signal = "bullish"
        elif pc_ratio > 1.5:
            signal = "bearish"
        else:
            signal = "neutral"

        return {
            "signal": signal,
            "put_call_ratio": pc_ratio,
            "vol_put_call_ratio": vol_pc_ratio,
            "call_oi": call_oi,
            "put_oi": put_oi,
            "total_oi": total_oi,
            "expiration": nearest,
            # v6: Unusual activity fields
            "unusual_call_activity": unusual_call,
            "unusual_put_activity": unusual_put,
            "call_vol_ratio": call_vol_ratio,
            "put_vol_ratio": put_vol_ratio,
        }
    except Exception as e:
        logger.warning(f"Options signal failed {symbol}: {e}")
        return None


# -- Index components --

def get_index_components(index_symbol: str) -> list[dict]:
    """Return list of component stocks for a given index.

    Each item has keys: ticker, market, name.
    """
    try:
        if index_symbol == "^GSPC":
            return _get_sp500_components()
        elif index_symbol == "^HSI":
            return _get_hsi_components()
        elif index_symbol == "^HSTECH":
            return _get_hstech_components()
        else:
            logger.warning(f"Unknown index: {index_symbol}")
            return []
    except Exception as e:
        logger.warning(f"Index components failed {index_symbol}: {e}")
        return []


def _get_sp500_components() -> list[dict]:
    """Fetch S&P 500 components from Wikipedia."""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)
        df = tables[0]
        results = []
        for _, row in df.iterrows():
            ticker = str(row.get("Symbol", "")).strip()
            name = str(row.get("Security", "")).strip()
            if ticker:
                results.append({"ticker": ticker, "market": "us_stock", "name": name})
        return results
    except Exception as e:
        logger.warning(f"S&P 500 fetch failed: {e}")
        return []


def _get_hsi_components() -> list[dict]:
    """Fetch Hang Seng Index components."""
    try:
        url = "https://en.wikipedia.org/wiki/Hang_Seng_Index"
        tables = pd.read_html(url)
        results = []
        for table in tables:
            cols = [str(c).lower() for c in table.columns]
            ticker_col = None
            name_col = None
            for c in table.columns:
                cl = str(c).lower()
                if "ticker" in cl or "stock" in cl or "code" in cl:
                    ticker_col = c
                if "name" in cl or "company" in cl:
                    name_col = c
            if ticker_col is None:
                continue
            for _, row in table.iterrows():
                raw = str(row[ticker_col]).strip()
                digits = "".join(c for c in raw if c.isdigit())
                if not digits or len(digits) < 4:
                    continue
                ticker = digits.zfill(4)
                name = str(row[name_col]).strip() if name_col else ticker
                results.append({"ticker": ticker, "market": "hk_stock", "name": name})
            if results:
                break
        return results
    except Exception as e:
        logger.warning(f"HSI fetch failed: {e}")
        return []


def _get_hstech_components() -> list[dict]:
    """Fetch Hang Seng TECH Index components."""
    try:
        url = "https://en.wikipedia.org/wiki/Hang_Seng_TECH_Index"
        tables = pd.read_html(url)
        results = []
        for table in tables:
            ticker_col = None
            name_col = None
            for c in table.columns:
                cl = str(c).lower()
                if "ticker" in cl or "stock" in cl or "code" in cl:
                    ticker_col = c
                if "name" in cl or "company" in cl:
                    name_col = c
            if ticker_col is None:
                continue
            for _, row in table.iterrows():
                raw = str(row[ticker_col]).strip()
                digits = "".join(c for c in raw if c.isdigit())
                if not digits or len(digits) < 4:
                    continue
                ticker = digits.zfill(4)
                name = str(row[name_col]).strip() if name_col else ticker
                results.append({"ticker": ticker, "market": "hk_stock", "name": name})
            if results:
                break
        return results
    except Exception as e:
        logger.warning(f"HSTECH fetch failed: {e}")
        return []


# -- Market indices --

def get_market_indices() -> list[dict]:
    indices = [
        ("^GSPC", "\u6807\u666e500", "us_stock"),
        ("^IXIC", "\u7eb3\u65af\u8fbe\u514b", "us_stock"),
        ("^DJI", "\u9053\u743c\u65af", "us_stock"),
        ("^HSI", "\u6052\u751f\u6307\u6570", "hk_stock"),
        ("^HSTECH", "\u6052\u751f\u79d1\u6280", "hk_stock"),
    ]
    results = []
    for symbol, label, market in indices:
        try:
            t = yf.Ticker(symbol)
            info = t.fast_info
            price = getattr(info, "last_price", None)
            prev = getattr(info, "previous_close", None)
            if price and prev and prev > 0:
                results.append({"name": label, "market": market,
                                "price": round(float(price), 2),
                                "change_pct": round((price - prev) / prev * 100, 2)})
        except Exception:
            pass
    return results


# -- Market breadth --

def _get_market_breadth(market: str) -> dict[str, Any]:
    """Compute advance/decline breadth for the given market.

    Returns dict with advance, decline, unchanged counts and advance_pct.
    """
    try:
        if market == "us_stock":
            components = _get_sp500_components()
        else:
            components = _get_hsi_components() + _get_hstech_components()

        if not components:
            return {"advance": 0, "decline": 0, "unchanged": 0,
                    "total": 0, "advance_pct": 50.0}

        advance = 0
        decline = 0
        unchanged = 0

        batch = get_quotes_batch(components)
        for q in batch:
            chg = q.get("change_pct")
            if chg is None:
                continue
            if chg > 0:
                advance += 1
            elif chg < 0:
                decline += 1
            else:
                unchanged += 1

        total = advance + decline + unchanged
        advance_pct = round(advance / max(total, 1) * 100, 1)

        return {
            "advance": advance,
            "decline": decline,
            "unchanged": unchanged,
            "total": total,
            "advance_pct": advance_pct,
        }
    except Exception as e:
        logger.warning(f"Market breadth failed: {e}")
        return {"advance": 0, "decline": 0, "unchanged": 0,
                "total": 0, "advance_pct": 50.0}
