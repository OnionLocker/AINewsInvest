"""
data/financial.py - 财务数据获取层

职责: 获取并缓存上市公司财务数据, 对外提供统一格式接口。
     本模块只负责数据采集与标准化, 不做任何分析判断。

公开接口:
    get_financial_data(ticker, market, years=5) -> dict | None

数据源:
    A股: akshare (stock_financial_analysis_indicator + stock_individual_info_em)
    美股: yfinance
    港股: yfinance (.HK 后缀)

缓存: JSON 文件, data/cache/ 目录, TTL 可通过 config.yaml 配置
"""
import json
import os
import time

import numpy as np
import pandas as pd

from utils.logger import app_logger
from utils.config_loader import get_config

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
_DEFAULT_TTL = 86400


# ══════════════════════════════════════════════════════════════
# 公开接口
# ══════════════════════════════════════════════════════════════

def get_financial_data(ticker: str, market: str, years: int = 5) -> dict | None:
    """
    获取指定标的近 N 年财务数据。

    返回标准化 dict (所有市场统一格式):
    {
        "ticker", "market", "currency",
        "market_info": { "pe_ttm", "pb", "market_cap_yi", "total_shares_yi", "dividend_yield_ttm" },
        "indicators": [                         # 按年倒序
            { "year", "roe", "gross_margin", "net_margin", "debt_ratio", "current_ratio",
              "revenue", "net_profit", "total_assets", "net_assets", "current_assets",
              "total_debt", "bvps", "eps", "ocf_per_share", "ocf_to_profit",
              "revenue_growth", "profit_growth" },
        ],
        "dividends": [ { "year", "dps", "payout_ratio" }, ... ],
    }
    失败返回 None。基金(fund)不支持, 返回 None。
    """
    if market == "fund":
        return None

    cfg = get_config().get("fundamental", {})
    if not cfg.get("enabled", True):
        return None

    cached = _cache_get(ticker, market)
    if cached is not None:
        return cached

    try:
        if market == "a_share":
            data = _fetch_a_share(ticker, years)
        elif market == "us_stock":
            data = _fetch_us(ticker, years)
        elif market == "hk_stock":
            data = _fetch_hk(ticker, years)
        else:
            return None

        if data and data.get("indicators"):
            _cache_set(ticker, market, data)
        return data
    except Exception as e:
        app_logger.warning(f"[财务数据] 获取失败 {market}:{ticker}: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# A 股数据获取
# ══════════════════════════════════════════════════════════════

def _fetch_a_share(ticker: str, years: int) -> dict | None:
    import akshare as ak

    # ── 财务指标 ──
    try:
        df = ak.stock_financial_analysis_indicator(symbol=ticker)
    except Exception as e:
        app_logger.warning(f"[财务数据] A股指标获取失败 {ticker}: {e}")
        return None
    if df is None or df.empty:
        return None

    date_col = _find_col(df.columns, "日期")
    if date_col is None:
        return None
    df[date_col] = df[date_col].astype(str)
    annual = df[df[date_col].str.endswith("-12-31")].head(years).copy()
    if annual.empty:
        return None

    cols = df.columns.tolist()
    indicators = []
    for _, row in annual.iterrows():
        year = int(str(row[date_col])[:4])
        ocf_pct = _extract(row, cols, "经营现金净流量与净利润", [])
        indicators.append({
            "year": year,
            "roe": _extract(row, cols, "净资产收益率", ["加权", "扣除"]),
            "gross_margin": _extract(row, cols, "销售毛利率", []),
            "net_margin": _extract(row, cols, "销售净利率", []),
            "debt_ratio": _extract(row, cols, "资产负债", ["股东"]),
            "current_ratio": _extract(row, cols, "流动比率", []),
            "revenue": _extract(row, cols, "主营业务收入", ["增长率", "利润"]),
            "net_profit": _extract(row, cols, "净利润", ["增长率", "扣除", "经营", "对"]),
            "total_assets": _extract(row, cols, "总资产", ["利润", "增长", "净利"]),
            "net_assets": _extract(row, cols, "股东权益合计", []),
            "current_assets": _extract(row, cols, "流动资产", []),
            "total_debt": _extract(row, cols, "总负债", []),
            "bvps": _extract(row, cols, "每股净资产", []),
            "eps": _extract(row, cols, "摊薄每股收益", []),
            "ocf_per_share": _extract(row, cols, "每股经营性现金流", []),
            "ocf_to_profit": round(ocf_pct / 100, 2) if ocf_pct is not None else None,
            "revenue_growth": _extract(row, cols, "主营业务收入增长率", []),
            "profit_growth": _extract(row, cols, "净利润增长率", []),
        })

    # ── 市场数据 ──
    market_info = _a_share_market_info(ticker)

    # ── 分红 ──
    dividends = _a_share_dividends(ticker, years, cols, annual, date_col)

    return {
        "ticker": ticker,
        "market": "a_share",
        "currency": "CNY",
        "market_info": market_info,
        "indicators": indicators,
        "dividends": dividends,
    }


def _a_share_market_info(ticker: str) -> dict:
    import akshare as ak
    empty = {"pe_ttm": None, "pb": None, "market_cap_yi": None,
             "total_shares_yi": None, "dividend_yield_ttm": None}
    try:
        df = ak.stock_individual_info_em(symbol=ticker)
        if df is None or df.empty:
            return empty
        lookup = {}
        for _, r in df.iterrows():
            lookup[str(r.iloc[0]).strip()] = r.iloc[1]

        mc_raw = _safe_float(lookup.get("总市值"))
        ts_raw = _safe_float(lookup.get("总股本"))
        return {
            "pe_ttm": _safe_float(lookup.get("市盈率(动态)")),
            "pb": _safe_float(lookup.get("市净率")),
            "market_cap_yi": round(mc_raw / 1e8, 2) if mc_raw and mc_raw > 1e6 else mc_raw,
            "total_shares_yi": round(ts_raw / 1e8, 4) if ts_raw and ts_raw > 1e6 else ts_raw,
            "dividend_yield_ttm": None,
        }
    except Exception as e:
        app_logger.warning(f"[财务数据] A股市场数据失败 {ticker}: {e}")
        return empty


def _a_share_dividends(ticker: str, years: int,
                       cols: list, annual: pd.DataFrame, date_col: str) -> list[dict]:
    """从财务指标表提取股息发放率, 结合 EPS 估算每股股利"""
    dividends = []
    for _, row in annual.iterrows():
        year = int(str(row[date_col])[:4])
        payout = _extract(row, cols, "股息发放率", [])
        eps = _extract(row, cols, "摊薄每股收益", [])
        dps = round(eps * payout / 100, 4) if eps and payout and payout > 0 else 0.0
        dividends.append({
            "year": year,
            "dps": dps,
            "payout_ratio": payout,
        })
    return dividends


# ══════════════════════════════════════════════════════════════
# 美股数据获取
# ══════════════════════════════════════════════════════════════

def _fetch_us(ticker: str, years: int) -> dict | None:
    import yfinance as yf

    t = yf.Ticker(ticker)
    info = t.info or {}
    financials = t.financials
    balance = t.balance_sheet
    cashflow = t.cashflow

    if financials is None or financials.empty:
        return None

    shares = info.get("sharesOutstanding")

    # ── 市场数据 ──
    market_info = {
        "pe_ttm": _safe_float(info.get("trailingPE")),
        "pb": _safe_float(info.get("priceToBook")),
        "market_cap_yi": round(info["marketCap"] / 1e8, 2) if info.get("marketCap") else None,
        "total_shares_yi": round(shares / 1e8, 4) if shares else None,
        "dividend_yield_ttm": _safe_float(info.get("dividendYield")) and round(
            info["dividendYield"] * 100, 2),
    }

    # ── 逐年指标 ──
    indicators = []
    period_cols = list(financials.columns)[:years]
    for col in period_cols:
        year = col.year if hasattr(col, "year") else int(str(col)[:4])

        revenue = _yf_item(financials, col, "Total Revenue")
        net_income = _yf_item(financials, col, "Net Income")
        gross_profit = _yf_item(financials, col, "Gross Profit")
        total_assets = _yf_item(balance, col, "Total Assets") if balance is not None else None
        equity = _yf_item(balance, col, "Stockholders Equity", "Total Equity") if balance is not None else None
        cur_assets = _yf_item(balance, col, "Current Assets") if balance is not None else None
        cur_liab = _yf_item(balance, col, "Current Liabilities") if balance is not None else None
        total_debt = _yf_item(balance, col, "Total Debt") if balance is not None else None
        op_cf = _yf_item(cashflow, col, "Operating Cash Flow",
                         "Cash Flow From Continuing Operating") if cashflow is not None else None

        roe = _ratio(net_income, equity, pct=True)
        gross_m = _ratio(gross_profit, revenue, pct=True)
        net_m = _ratio(net_income, revenue, pct=True)
        debt_r = _ratio(_sub(total_assets, equity), total_assets, pct=True) if total_assets and equity else None
        cur_r = _ratio(cur_assets, cur_liab)
        ocf_p = _ratio(op_cf, net_income)

        indicators.append({
            "year": year,
            "roe": roe,
            "gross_margin": gross_m,
            "net_margin": net_m,
            "debt_ratio": debt_r,
            "current_ratio": cur_r,
            "revenue": _to_wan(revenue),
            "net_profit": _to_wan(net_income),
            "total_assets": _to_wan(total_assets),
            "net_assets": _to_wan(equity),
            "current_assets": _to_wan(cur_assets),
            "total_debt": _to_wan(total_debt),
            "bvps": round(equity / shares, 2) if equity and shares else None,
            "eps": _safe_float(info.get("trailingEps")),
            "ocf_per_share": round(op_cf / shares, 2) if op_cf and shares else None,
            "ocf_to_profit": ocf_p,
            "revenue_growth": None,
            "profit_growth": None,
        })

    _fill_growth_rates(indicators)

    # ── 分红 ──
    dividends = _yf_dividends(t, years)

    return {
        "ticker": ticker,
        "market": "us_stock",
        "currency": "USD",
        "market_info": market_info,
        "indicators": indicators,
        "dividends": dividends,
    }


# ══════════════════════════════════════════════════════════════
# 港股数据获取
# ══════════════════════════════════════════════════════════════

def _fetch_hk(ticker: str, years: int) -> dict | None:
    import yfinance as yf

    yf_ticker = f"{ticker}.HK"
    t = yf.Ticker(yf_ticker)
    info = t.info or {}

    if not info.get("marketCap"):
        return None

    financials = t.financials
    balance = t.balance_sheet
    cashflow = t.cashflow

    if financials is None or financials.empty:
        return None

    shares = info.get("sharesOutstanding")

    market_info = {
        "pe_ttm": _safe_float(info.get("trailingPE")),
        "pb": _safe_float(info.get("priceToBook")),
        "market_cap_yi": round(info["marketCap"] / 1e8, 2) if info.get("marketCap") else None,
        "total_shares_yi": round(shares / 1e8, 4) if shares else None,
        "dividend_yield_ttm": _safe_float(info.get("dividendYield")) and round(
            info["dividendYield"] * 100, 2),
    }

    indicators = []
    period_cols = list(financials.columns)[:years]
    for col in period_cols:
        year = col.year if hasattr(col, "year") else int(str(col)[:4])

        revenue = _yf_item(financials, col, "Total Revenue")
        net_income = _yf_item(financials, col, "Net Income")
        gross_profit = _yf_item(financials, col, "Gross Profit")
        total_assets = _yf_item(balance, col, "Total Assets") if balance is not None else None
        equity = _yf_item(balance, col, "Stockholders Equity", "Total Equity") if balance is not None else None
        cur_assets = _yf_item(balance, col, "Current Assets") if balance is not None else None
        cur_liab = _yf_item(balance, col, "Current Liabilities") if balance is not None else None
        total_debt = _yf_item(balance, col, "Total Debt") if balance is not None else None
        op_cf = _yf_item(cashflow, col, "Operating Cash Flow",
                         "Cash Flow From Continuing Operating") if cashflow is not None else None

        roe = _ratio(net_income, equity, pct=True)
        gross_m = _ratio(gross_profit, revenue, pct=True)
        net_m = _ratio(net_income, revenue, pct=True)
        debt_r = _ratio(_sub(total_assets, equity), total_assets, pct=True) if total_assets and equity else None
        cur_r = _ratio(cur_assets, cur_liab)
        ocf_p = _ratio(op_cf, net_income)

        indicators.append({
            "year": year,
            "roe": roe,
            "gross_margin": gross_m,
            "net_margin": net_m,
            "debt_ratio": debt_r,
            "current_ratio": cur_r,
            "revenue": _to_wan(revenue),
            "net_profit": _to_wan(net_income),
            "total_assets": _to_wan(total_assets),
            "net_assets": _to_wan(equity),
            "current_assets": _to_wan(cur_assets),
            "total_debt": _to_wan(total_debt),
            "bvps": round(equity / shares, 2) if equity and shares else None,
            "eps": _safe_float(info.get("trailingEps")),
            "ocf_per_share": round(op_cf / shares, 2) if op_cf and shares else None,
            "ocf_to_profit": ocf_p,
            "revenue_growth": None,
            "profit_growth": None,
        })

    _fill_growth_rates(indicators)
    dividends = _yf_dividends(t, years)

    return {
        "ticker": ticker,
        "market": "hk_stock",
        "currency": "HKD",
        "market_info": market_info,
        "indicators": indicators,
        "dividends": dividends,
    }


# ══════════════════════════════════════════════════════════════
# yfinance 辅助
# ══════════════════════════════════════════════════════════════

def _yf_item(df: pd.DataFrame, col, *names: str) -> float | None:
    """从 yfinance 财务报表取值, 按名称优先级查找"""
    if df is None or df.empty or col not in df.columns:
        return None
    for name in names:
        if name in df.index:
            val = df.at[name, col]
            return float(val) if pd.notna(val) else None
        for idx in df.index:
            if name.lower() in str(idx).lower():
                val = df.at[idx, col]
                return float(val) if pd.notna(val) else None
    return None


def _yf_dividends(ticker_obj, years: int) -> list[dict]:
    try:
        div = ticker_obj.dividends
        if div is None or div.empty:
            return []
        by_year = div.groupby(div.index.year).sum()
        result = []
        for yr in sorted(by_year.index, reverse=True)[:years]:
            result.append({
                "year": int(yr),
                "dps": round(float(by_year[yr]), 4),
                "payout_ratio": None,
            })
        return result
    except Exception:
        return []


def _fill_growth_rates(indicators: list[dict]):
    """根据相邻年度的 revenue/net_profit 计算增长率 (就地修改)"""
    for i in range(len(indicators) - 1):
        curr = indicators[i]
        prev = indicators[i + 1]
        if curr["revenue"] and prev["revenue"] and prev["revenue"] != 0:
            curr["revenue_growth"] = round(
                (curr["revenue"] - prev["revenue"]) / abs(prev["revenue"]) * 100, 2)
        if curr["net_profit"] and prev["net_profit"] and prev["net_profit"] != 0:
            curr["profit_growth"] = round(
                (curr["net_profit"] - prev["net_profit"]) / abs(prev["net_profit"]) * 100, 2)


# ══════════════════════════════════════════════════════════════
# A 股列名匹配辅助
# ══════════════════════════════════════════════════════════════

def _find_col(columns, keyword: str, exclude: list[str] | None = None) -> str | None:
    """从列名列表中找到包含 keyword 但不含 exclude 中任何词的第一个列名"""
    exclude = exclude or []
    for col in columns:
        if keyword in str(col):
            if not any(ex in str(col) for ex in exclude):
                return col
    return None


def _extract(row, columns: list, keyword: str, exclude: list[str]) -> float | None:
    """从一行数据中, 按关键词找到对应列并提取 float 值"""
    col = _find_col(columns, keyword, exclude)
    if col is None:
        return None
    return _safe_float(row.get(col))


# ══════════════════════════════════════════════════════════════
# 通用辅助
# ══════════════════════════════════════════════════════════════

def _safe_float(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
        return None
    try:
        result = float(val)
        if np.isnan(result) or np.isinf(result):
            return None
        return round(result, 4)
    except (ValueError, TypeError):
        return None


def _ratio(a, b, pct: bool = False) -> float | None:
    if a is None or b is None or b == 0:
        return None
    r = a / b
    return round(r * 100, 2) if pct else round(r, 2)


def _sub(a, b) -> float | None:
    if a is None or b is None:
        return None
    return a - b


def _to_wan(val) -> float | None:
    """将原始货币值转为 '万' 单位"""
    if val is None:
        return None
    return round(val / 1e4, 2)


# ══════════════════════════════════════════════════════════════
# JSON 文件缓存
# ══════════════════════════════════════════════════════════════

def _get_ttl() -> int:
    cfg = get_config().get("fundamental", {})
    return cfg.get("cache_ttl", _DEFAULT_TTL)


def _cache_get(ticker: str, market: str) -> dict | None:
    path = os.path.join(_CACHE_DIR, f"{market}_{ticker}.json")
    if not os.path.exists(path):
        return None
    try:
        if time.time() - os.path.getmtime(path) > _get_ttl():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _cache_set(ticker: str, market: str, data: dict):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, f"{market}_{ticker}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        app_logger.warning(f"[财务数据] 缓存写入失败 {path}: {e}")
