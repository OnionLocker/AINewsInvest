"""
analysis/stock_screener.py - 动态股票池筛选器

筛选模式:
  - technical:    技术面异动 (量能/均线/RSI/MACD)
  - fundamental:  基本面价值筛选 (PE/PB/ROE/股息率/财务质量)
  - combined:     技术面 + 基本面综合

技术面维度:
  1. 成交量异动（近5日均量 > 20日均量 × 倍数）
  2. 均线突破（股价站上 MA20 / MA60）
  3. RSI 极端值（超卖反弹 / 超买警示）
  4. 日涨跌幅异常（>3%）

基本面维度 (参考龟龟框架 screener_core.py):
  Tier 1: PE/PB/股息率加权排名
  Tier 2: ROE/负债率/现金流质量检查 + 硬否决
"""
import json
import os

import numpy as np
import pandas as pd

from utils.logger import app_logger
from utils.config_loader import get_config

_SYMBOLS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "symbols.json")


# ══════════════════════════════════════════════════════════════
# 公开接口
# ══════════════════════════════════════════════════════════════

def screen_market(market: str, mode: str = "technical") -> list[tuple[str, str, str]]:
    """
    筛选指定市场的标的。

    参数:
        market: a_share / us_stock / hk_stock
        mode:   "technical" | "fundamental" | "combined"

    返回: [(ticker, name, reason), ...]
    """
    if mode == "fundamental":
        return _screen_fundamental(market)
    elif mode == "combined":
        tech = _screen_technical(market)
        fund = _screen_fundamental(market)
        return _merge_results(tech, fund)
    else:
        return _screen_technical(market)


# ══════════════════════════════════════════════════════════════
# 技术面筛选 (原有逻辑, 改为从 config 读取参数)
# ══════════════════════════════════════════════════════════════

def _screen_technical(market: str) -> list[tuple[str, str, str]]:
    from analysis.technical import fetch_kline, compute_indicators

    cfg = _get_screener_cfg()
    symbols = _load_market_symbols(market)
    if not symbols:
        return []

    app_logger.info(f"[筛选-技术] 扫描 {market}，共 {len(symbols)} 只")
    hits = []
    max_n = cfg["max_screened"]

    for sym in symbols:
        ticker, name = sym["ticker"], sym["name"]
        try:
            reasons = _check_technical(
                ticker, market, fetch_kline, compute_indicators, cfg)
            if reasons:
                hits.append((ticker, name, " | ".join(reasons)))
        except Exception:
            continue
        if len(hits) >= max_n:
            break

    app_logger.info(f"[筛选-技术] {market} 命中 {len(hits)} 只")
    return hits


def _check_technical(ticker, market, fetch_kline_fn, compute_fn, cfg) -> list[str]:
    """技术面单标的筛检"""
    df = fetch_kline_fn(ticker, market)
    if df is None or len(df) < 30:
        return []

    df = compute_fn(df)
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    reasons = []

    close = float(last["close"])
    prev_close = float(prev["close"])
    change_pct = (close - prev_close) / prev_close * 100 if prev_close else 0

    if abs(change_pct) >= cfg["price_change_threshold"]:
        direction = "涨" if change_pct > 0 else "跌"
        reasons.append(f"日{direction}{abs(change_pct):.1f}%")

    vol_ma5 = last.get("vol_ma5")
    vol_ma20 = last.get("vol_ma20")
    if pd.notna(vol_ma5) and pd.notna(vol_ma20) and vol_ma20 > 0:
        if vol_ma5 > vol_ma20 * cfg["vol_multiplier"]:
            reasons.append(f"量能放大{vol_ma5 / vol_ma20:.1f}倍")

    ma20 = last.get("ma20")
    ma60 = last.get("ma60")
    prev_ma20 = prev.get("ma20") if "ma20" in prev.index else None
    prev_ma60 = prev.get("ma60") if "ma60" in prev.index else None

    if pd.notna(ma20) and pd.notna(prev_ma20):
        if prev_close < prev_ma20 and close > ma20:
            reasons.append("突破MA20")
    if pd.notna(ma60) and pd.notna(prev_ma60):
        if prev_close < prev_ma60 and close > ma60:
            reasons.append("突破MA60")

    rsi = last.get("rsi")
    if pd.notna(rsi):
        if rsi < 25:
            reasons.append(f"RSI超卖({rsi:.0f})")
        elif rsi > 75:
            reasons.append(f"RSI超买({rsi:.0f})")

    if pd.notna(last.get("dif")) and pd.notna(last.get("dea")):
        if pd.notna(prev.get("dif")) and pd.notna(prev.get("dea")):
            if prev["dif"] <= prev["dea"] and last["dif"] > last["dea"]:
                reasons.append("MACD金叉")
            elif prev["dif"] >= prev["dea"] and last["dif"] < last["dea"]:
                reasons.append("MACD死叉")

    return reasons


# ══════════════════════════════════════════════════════════════
# 基本面筛选 (新增)
# ══════════════════════════════════════════════════════════════

def _screen_fundamental(market: str) -> list[tuple[str, str, str]]:
    """
    基本面价值筛选:
    Tier 1 → 粗筛 (PE/PB/股息率排名)
    Tier 2 → 精筛 (ROE/负债率/现金流质量)
    """
    from data.financial import get_financial_data
    from analysis.fundamental import analyze as fund_analyze

    cfg = _get_screener_cfg()
    symbols = _load_market_symbols(market)
    if not symbols:
        return []

    app_logger.info(f"[筛选-基本面] 扫描 {market}，共 {len(symbols)} 只")

    # ── Tier 1: 获取财务数据, 粗筛 ──
    candidates = []
    for sym in symbols:
        ticker, name = sym["ticker"], sym["name"]
        try:
            fdata = get_financial_data(ticker, market)
            if not fdata or not fdata.get("indicators") or not fdata.get("market_info"):
                continue
            mi = fdata["market_info"]
            latest = fdata["indicators"][0]
            if not _pass_tier1(mi, latest, cfg):
                continue
            score = _tier1_score(mi, latest)
            candidates.append((ticker, name, fdata, score))
        except Exception:
            continue

    candidates.sort(key=lambda x: x[3], reverse=True)
    candidates = candidates[:cfg["max_screened"] * 2]

    # ── Tier 2: 深度检查 ──
    hits = []
    for ticker, name, fdata, t1_score in candidates:
        try:
            result = fund_analyze(ticker, market)
            if result is None:
                continue
            veto, veto_reason = _check_hard_veto(result)
            if veto:
                continue
            reasons = _build_fundamental_reason(result, mi=fdata["market_info"])
            hits.append((ticker, name, reasons))
        except Exception:
            continue
        if len(hits) >= cfg["max_screened"]:
            break

    app_logger.info(f"[筛选-基本面] {market} 命中 {len(hits)} 只")
    return hits


def _pass_tier1(market_info: dict, latest_ind: dict, cfg: dict) -> bool:
    """Tier 1 粗筛: 排除不符合基本条件的标的"""
    pe = market_info.get("pe_ttm")
    pb = market_info.get("pb")

    pe_range = cfg.get("pe_range", [3, 25])
    pb_range = cfg.get("pb_range", [0.3, 3.0])

    if pe is not None and (pe < pe_range[0] or pe > pe_range[1]):
        return False
    if pb is not None and (pb < pb_range[0] or pb > pb_range[1]):
        return False

    roe = latest_ind.get("roe")
    if roe is not None and roe < cfg.get("min_roe", 3):
        return False

    return True


def _tier1_score(market_info: dict, latest_ind: dict) -> float:
    """
    Tier 1 综合评分, 参考龟龟框架:
    composite = 0.4 × 股息率 + 0.3 × (1/PE) + 0.3 × (1/PB)
    """
    score = 0.0
    pe = market_info.get("pe_ttm")
    pb = market_info.get("pb")
    dy = market_info.get("dividend_yield_ttm")

    if dy and dy > 0:
        score += 0.4 * min(dy / 10, 1.0)
    if pe and pe > 0:
        score += 0.3 * min(1.0 / pe * 10, 1.0)
    if pb and pb > 0:
        score += 0.3 * min(1.0 / pb, 1.0)

    return round(score, 4)


def _check_hard_veto(fund_result: dict) -> tuple[bool, str]:
    """
    硬否决条件, 参考龟龟框架 _check_hard_vetoes:
    - 财务质量极差
    - 多个高风险标记同时出现
    """
    risks = fund_result.get("risk_flags", [])

    if "高负债" in risks and "经营现金流为负" in risks:
        return True, "高负债+现金流为负"
    if fund_result.get("quality_score", 0) < 20:
        return True, "财务质量极差"

    return False, ""


def _build_fundamental_reason(result: dict, mi: dict) -> str:
    """构建基本面筛选原因描述"""
    parts = []
    qs = result.get("quality_score", 0)
    ql = result.get("quality_label", "")
    parts.append(f"质量{ql}({qs}分)")

    prof = result.get("profitability", {})
    roe = prof.get("roe_latest")
    if roe is not None:
        parts.append(f"ROE{roe:.1f}%")

    pe = mi.get("pe_ttm")
    pb = mi.get("pb")
    if pe is not None:
        parts.append(f"PE{pe:.1f}")
    if pb is not None:
        parts.append(f"PB{pb:.1f}")

    return " | ".join(parts)


# ══════════════════════════════════════════════════════════════
# 合并筛选结果
# ══════════════════════════════════════════════════════════════

def _merge_results(tech: list, fund: list) -> list[tuple[str, str, str]]:
    """合并技术面和基本面筛选结果, 去重"""
    seen = set()
    merged = []
    for ticker, name, reason in tech:
        if ticker not in seen:
            seen.add(ticker)
            merged.append((ticker, name, f"[技术] {reason}"))
    for ticker, name, reason in fund:
        if ticker not in seen:
            seen.add(ticker)
            merged.append((ticker, name, f"[基本面] {reason}"))
        else:
            for i, (t, n, r) in enumerate(merged):
                if t == ticker:
                    merged[i] = (t, n, f"{r} + [基本面] {reason}")
                    break
    return merged


# ══════════════════════════════════════════════════════════════
# 配置与数据加载
# ══════════════════════════════════════════════════════════════

def _get_screener_cfg() -> dict:
    cfg = get_config().get("screener", {})
    return {
        "vol_multiplier": cfg.get("vol_multiplier", 2.0),
        "price_change_threshold": cfg.get("price_change_threshold", 3.0),
        "max_screened": cfg.get("max_screened_per_market", 10),
        "pe_range": cfg.get("pe_range", [3, 25]),
        "pb_range": cfg.get("pb_range", [0.3, 3.0]),
        "min_roe": cfg.get("min_roe", 5.0),
        "min_dividend_yield": cfg.get("min_dividend_yield", 2.0),
    }


def _load_market_symbols(market: str) -> list[dict]:
    if not os.path.exists(_SYMBOLS_PATH):
        return []
    try:
        with open(_SYMBOLS_PATH, "r", encoding="utf-8") as f:
            all_symbols = json.load(f)
        return [s for s in all_symbols if s.get("market") == market]
    except Exception:
        return []
