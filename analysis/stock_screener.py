"""
analysis/stock_screener.py - 动态股票池筛选器

从全量标的中筛选出有异动/突破信号的标的，补充进每日分析列表。
筛选维度：
  1. 成交量异动（近5日均量 > 20日均量 × 倍数）
  2. 均线突破（股价站上 MA20 / MA60）
  3. RSI 极端值（超卖反弹 / 超买警示）
  4. 日涨跌幅异常（>3%）
"""
import json
import os
import pandas as pd
import numpy as np
from utils.logger import app_logger

_SYMBOLS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "symbols.json")

# 筛选参数
VOL_MULTIPLIER = 2.0     # 量能放大倍数阈值
PRICE_CHANGE_THRESHOLD = 3.0  # 日涨跌幅阈值 (%)
RSI_OVERSOLD = 25
RSI_OVERBOUGHT = 75
MAX_SCREENED = 10         # 每市场最多筛出


def screen_market(market: str) -> list[tuple[str, str, str]]:
    """
    筛选指定市场的异动标的。

    返回: [(ticker, name, reason), ...]
    reason 是筛选触发原因的简短描述
    """
    from analysis.technical import fetch_kline, compute_indicators

    symbols = _load_market_symbols(market)
    if not symbols:
        app_logger.info(f"[筛选] {market} 无可用标的库")
        return []

    app_logger.info(f"[筛选] 开始扫描 {market}，共 {len(symbols)} 只")
    hits = []

    for sym in symbols:
        ticker = sym["ticker"]
        name = sym["name"]
        try:
            reasons = _check_one(ticker, market, fetch_kline, compute_indicators)
            if reasons:
                hits.append((ticker, name, " | ".join(reasons)))
        except Exception:
            continue

        if len(hits) >= MAX_SCREENED:
            break

    app_logger.info(f"[筛选] {market} 扫描完成，命中 {len(hits)} 只")
    return hits


def _check_one(ticker, market, fetch_kline_fn, compute_fn) -> list[str]:
    """对单只标的做快速筛检，返回触发原因列表"""
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

    # 1) 涨跌幅异常
    if abs(change_pct) >= PRICE_CHANGE_THRESHOLD:
        direction = "涨" if change_pct > 0 else "跌"
        reasons.append(f"日{direction}{abs(change_pct):.1f}%")

    # 2) 成交量异动
    vol_ma5 = last.get("vol_ma5")
    vol_ma20 = last.get("vol_ma20")
    if pd.notna(vol_ma5) and pd.notna(vol_ma20) and vol_ma20 > 0:
        if vol_ma5 > vol_ma20 * VOL_MULTIPLIER:
            ratio = vol_ma5 / vol_ma20
            reasons.append(f"量能放大{ratio:.1f}倍")

    # 3) 均线突破
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

    # 4) RSI 极端
    rsi = last.get("rsi")
    if pd.notna(rsi):
        if rsi < RSI_OVERSOLD:
            reasons.append(f"RSI超卖({rsi:.0f})")
        elif rsi > RSI_OVERBOUGHT:
            reasons.append(f"RSI超买({rsi:.0f})")

    # 5) MACD 金叉
    if pd.notna(last.get("dif")) and pd.notna(last.get("dea")):
        if pd.notna(prev.get("dif")) and pd.notna(prev.get("dea")):
            if prev["dif"] <= prev["dea"] and last["dif"] > last["dea"]:
                reasons.append("MACD金叉")
            elif prev["dif"] >= prev["dea"] and last["dif"] < last["dea"]:
                reasons.append("MACD死叉")

    return reasons


def _load_market_symbols(market: str) -> list[dict]:
    """从 symbols.json 加载指定市场的标的列表"""
    if not os.path.exists(_SYMBOLS_PATH):
        return []
    try:
        with open(_SYMBOLS_PATH, "r", encoding="utf-8") as f:
            all_symbols = json.load(f)
        return [s for s in all_symbols if s.get("market") == market]
    except Exception:
        return []
