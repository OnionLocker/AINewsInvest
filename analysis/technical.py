"""
analysis/technical.py - 技术面分析引擎

流程：拉取 K 线 → 计算指标 → 判断趋势 → 给出入场/止损/止盈点位

支持市场：A股(akshare) / 美股(yfinance) / 港股(akshare)
"""
import numpy as np
import pandas as pd
import akshare as ak
import yfinance as yf
from utils.logger import app_logger

LOOKBACK_DAYS = 120  # 回看交易日数


# ══════════════════════════════════════════════════════════════
# K 线数据获取
# ══════════════════════════════════════════════════════════════

def fetch_kline(ticker: str, market: str) -> pd.DataFrame | None:
    """
    拉取日K线，返回标准化 DataFrame:
    columns = [date, open, high, low, close, volume]
    """
    try:
        if market == "a_share":
            return _kline_a_share(ticker)
        elif market == "hk_stock":
            return _kline_hk(ticker)
        elif market == "us_stock":
            return _kline_us(ticker)
        else:
            return None
    except Exception as e:
        app_logger.warning(f"K线获取失败 [{market}:{ticker}]: {e}")
        return None


def _kline_a_share(ticker: str) -> pd.DataFrame | None:
    df = ak.stock_zh_a_hist(
        symbol=ticker, period="daily", adjust="qfq",
    )
    if df is None or df.empty:
        return None
    df = df.rename(columns={
        "日期": "date", "开盘": "open", "最高": "high",
        "最低": "low", "收盘": "close", "成交量": "volume",
    })
    df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.tail(LOOKBACK_DAYS).reset_index(drop=True)


def _kline_hk(ticker: str) -> pd.DataFrame | None:
    df = ak.stock_hk_hist(symbol=ticker, period="daily", adjust="qfq")
    if df is None or df.empty:
        return None
    df = df.rename(columns={
        "日期": "date", "开盘": "open", "最高": "high",
        "最低": "low", "收盘": "close", "成交量": "volume",
    })
    df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.tail(LOOKBACK_DAYS).reset_index(drop=True)


def _kline_us(ticker: str) -> pd.DataFrame | None:
    t = yf.Ticker(ticker)
    df = t.history(period="6mo")
    if df is None or df.empty:
        return None
    df = df.reset_index()
    df = df.rename(columns={
        "Date": "date", "Open": "open", "High": "high",
        "Low": "low", "Close": "close", "Volume": "volume",
    })
    df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    return df.tail(LOOKBACK_DAYS).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════
# 技术指标计算
# ══════════════════════════════════════════════════════════════

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """在 DataFrame 上计算全套技术指标"""
    c = df["close"]
    h = df["high"]
    l = df["low"]

    # ── 均线 ──
    for period in [5, 10, 20, 60]:
        df[f"ma{period}"] = c.rolling(period).mean()

    # ── MACD (12, 26, 9) ──
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    df["dif"] = ema12 - ema26
    df["dea"] = df["dif"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = 2 * (df["dif"] - df["dea"])

    # ── RSI (14) ──
    delta = c.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ── 布林带 (20, 2) ──
    df["boll_mid"] = c.rolling(20).mean()
    boll_std = c.rolling(20).std()
    df["boll_upper"] = df["boll_mid"] + 2 * boll_std
    df["boll_lower"] = df["boll_mid"] - 2 * boll_std

    # ── KDJ (9, 3, 3) ──
    low9 = l.rolling(9).min()
    high9 = h.rolling(9).max()
    rsv = (c - low9) / (high9 - low9).replace(0, np.nan) * 100
    df["k"] = rsv.ewm(com=2, adjust=False).mean()
    df["d"] = df["k"].ewm(com=2, adjust=False).mean()
    df["j"] = 3 * df["k"] - 2 * df["d"]

    # ── ATR (14) ──
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()

    # ── 成交量均线 ──
    df["vol_ma5"] = df["volume"].rolling(5).mean()
    df["vol_ma20"] = df["volume"].rolling(20).mean()

    return df


# ══════════════════════════════════════════════════════════════
# 支撑/阻力位识别
# ══════════════════════════════════════════════════════════════

def find_support_resistance(df: pd.DataFrame, n: int = 20) -> dict:
    """基于近 N 日高低点和均线识别关键价位"""
    recent = df.tail(n)
    close = df["close"].iloc[-1]

    levels = set()
    # 近期高低点
    levels.add(round(recent["high"].max(), 2))
    levels.add(round(recent["low"].min(), 2))
    # 均线价位
    for ma in ["ma5", "ma10", "ma20", "ma60"]:
        if ma in df.columns and pd.notna(df[ma].iloc[-1]):
            levels.add(round(df[ma].iloc[-1], 2))
    # 布林带
    if pd.notna(df["boll_upper"].iloc[-1]):
        levels.add(round(df["boll_upper"].iloc[-1], 2))
        levels.add(round(df["boll_lower"].iloc[-1], 2))

    supports = sorted([lv for lv in levels if lv < close], reverse=True)
    resistances = sorted([lv for lv in levels if lv > close])

    return {
        "supports": supports[:3],
        "resistances": resistances[:3],
    }


# ══════════════════════════════════════════════════════════════
# 综合技术面分析（核心）
# ══════════════════════════════════════════════════════════════

def analyze(ticker: str, market: str) -> dict | None:
    """
    对单只标的做完整技术面分析，返回结构化结果：
    {
        "ticker", "market",
        "price", "change_pct",
        "trend",           # bullish / bearish / ranging
        "signal",          # buy / sell / neutral
        "confidence",      # 0-100
        "entry", "stop_loss", "take_profit_1", "take_profit_2",
        "risk_reward",
        "tech_summary",    # 人话总结
        "indicators": {...}
    }
    """
    df = fetch_kline(ticker, market)
    if df is None or len(df) < 60:
        return None

    df = compute_indicators(df)
    last = df.iloc[-1]
    prev = df.iloc[-2]

    close = round(float(last["close"]), 2)
    prev_close = float(prev["close"])
    change_pct = round((close - prev_close) / prev_close * 100, 2)
    atr = float(last["atr"]) if pd.notna(last["atr"]) else close * 0.02

    # ── 趋势判断 ──
    trend_score = 0  # 正=多头, 负=空头

    # 均线排列
    mas = {}
    for p in [5, 10, 20, 60]:
        val = last.get(f"ma{p}")
        if pd.notna(val):
            mas[p] = float(val)

    if mas.get(5) and mas.get(20) and mas.get(60):
        if mas[5] > mas[20] > mas[60]:
            trend_score += 2  # 完美多头排列
        elif mas[5] < mas[20] < mas[60]:
            trend_score -= 2  # 完美空头排列
        if close > mas[20]:
            trend_score += 1
        else:
            trend_score -= 1
        if close > mas[60]:
            trend_score += 1
        else:
            trend_score -= 1

    # MACD
    if pd.notna(last["dif"]) and pd.notna(last["dea"]):
        if last["dif"] > last["dea"]:
            trend_score += 1
            if prev["dif"] <= prev["dea"]:
                trend_score += 1  # 金叉加分
        else:
            trend_score -= 1
            if prev["dif"] >= prev["dea"]:
                trend_score -= 1  # 死叉减分
        if last["dif"] > 0:
            trend_score += 0.5
        else:
            trend_score -= 0.5

    # RSI
    rsi = float(last["rsi"]) if pd.notna(last["rsi"]) else 50
    if rsi > 60:
        trend_score += 1
    elif rsi < 40:
        trend_score -= 1
    if rsi > 80:
        trend_score -= 0.5  # 超买风险
    elif rsi < 20:
        trend_score += 0.5  # 超卖反弹机会

    # KDJ
    if pd.notna(last["k"]) and pd.notna(last["d"]):
        if last["k"] > last["d"]:
            trend_score += 0.5
        else:
            trend_score -= 0.5

    # 量价
    if pd.notna(last["vol_ma5"]) and pd.notna(last["vol_ma20"]):
        if last["vol_ma5"] > last["vol_ma20"] * 1.3:
            trend_score += 0.5 if change_pct > 0 else -0.5

    # ── 趋势结论 ──
    if trend_score >= 3:
        trend = "bullish"
        signal = "buy"
    elif trend_score <= -3:
        trend = "bearish"
        signal = "sell"
    else:
        trend = "ranging"
        signal = "neutral"

    # ── 置信度 ──
    confidence = min(95, max(30, int(50 + trend_score * 5)))

    # ── 关键价位 ──
    sr = find_support_resistance(df)

    # ── 入场/止损/止盈 ──
    if signal == "buy":
        entry = round(close, 2)
        # 止损：最近支撑位下方半个 ATR，或 entry 下方 1.5 ATR
        if sr["supports"]:
            stop_loss = round(sr["supports"][0] - atr * 0.5, 2)
        else:
            stop_loss = round(entry - atr * 1.5, 2)
        risk = entry - stop_loss
        take_profit_1 = round(entry + risk * 2, 2)   # 1:2 风险回报
        take_profit_2 = round(entry + risk * 3, 2)   # 1:3 风险回报
        # 如有阻力位，用阻力位做参考
        if sr["resistances"]:
            take_profit_1 = max(take_profit_1, round(sr["resistances"][0], 2))
            if len(sr["resistances"]) > 1:
                take_profit_2 = max(take_profit_2, round(sr["resistances"][1], 2))

    elif signal == "sell":
        entry = round(close, 2)
        if sr["resistances"]:
            stop_loss = round(sr["resistances"][0] + atr * 0.5, 2)
        else:
            stop_loss = round(entry + atr * 1.5, 2)
        risk = stop_loss - entry
        take_profit_1 = round(entry - risk * 2, 2)
        take_profit_2 = round(entry - risk * 3, 2)
        if sr["supports"]:
            take_profit_1 = min(take_profit_1, round(sr["supports"][0], 2))
            if len(sr["supports"]) > 1:
                take_profit_2 = min(take_profit_2, round(sr["supports"][1], 2))
    else:
        entry = round(close, 2)
        stop_loss = round(close - atr * 1.5, 2)
        take_profit_1 = round(close + atr * 2, 2)
        take_profit_2 = round(close + atr * 3, 2)

    # 风险回报比
    risk_amt = abs(entry - stop_loss)
    reward_amt = abs(take_profit_1 - entry)
    rr = f"1:{round(reward_amt / risk_amt, 1)}" if risk_amt > 0 else "N/A"

    # ── 生成人话总结 ──
    tech_summary = _build_summary(
        trend, signal, close, mas, last, prev, rsi, sr, atr, entry, stop_loss, take_profit_1, take_profit_2
    )

    return {
        "ticker": ticker,
        "market": market,
        "price": close,
        "change_pct": change_pct,
        "trend": trend,
        "signal": signal,
        "confidence": confidence,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "risk_reward": rr,
        "tech_summary": tech_summary,
        "indicators": {
            "ma5": round(mas.get(5, 0), 2),
            "ma20": round(mas.get(20, 0), 2),
            "ma60": round(mas.get(60, 0), 2),
            "rsi": round(rsi, 1),
            "macd_dif": round(float(last["dif"]), 3) if pd.notna(last["dif"]) else None,
            "macd_dea": round(float(last["dea"]), 3) if pd.notna(last["dea"]) else None,
            "atr": round(atr, 2),
            "boll_upper": round(float(last["boll_upper"]), 2) if pd.notna(last["boll_upper"]) else None,
            "boll_lower": round(float(last["boll_lower"]), 2) if pd.notna(last["boll_lower"]) else None,
        },
    }


def _build_summary(
    trend, signal, close, mas, last, prev, rsi, sr, atr, entry, sl, tp1, tp2
) -> str:
    """根据指标数据生成自然语言技术分析总结"""
    parts = []

    # 趋势描述
    trend_zh = {"bullish": "多头", "bearish": "空头", "ranging": "震荡"}
    parts.append(f"当前趋势 {trend_zh[trend]}。")

    # 均线
    if mas.get(5) and mas.get(20) and mas.get(60):
        if mas[5] > mas[20] > mas[60]:
            parts.append("均线多头排列（MA5>MA20>MA60），中期趋势向上。")
        elif mas[5] < mas[20] < mas[60]:
            parts.append("均线空头排列（MA5<MA20<MA60），中期趋势向下。")
        else:
            parts.append("均线交织，趋势不明朗。")

        if close > mas[20]:
            parts.append(f"股价站上20日均线（{mas[20]:.2f}）。")
        else:
            parts.append(f"股价运行在20日均线（{mas[20]:.2f}）下方。")

    # MACD
    if pd.notna(last["dif"]) and pd.notna(last["dea"]):
        if last["dif"] > last["dea"] and prev["dif"] <= prev["dea"]:
            parts.append("MACD 刚刚形成金叉，短期动能转强。")
        elif last["dif"] < last["dea"] and prev["dif"] >= prev["dea"]:
            parts.append("MACD 形成死叉，短期动能减弱。")
        elif last["dif"] > last["dea"]:
            parts.append("MACD 多头运行中。")
        else:
            parts.append("MACD 空头运行中。")

    # RSI
    if rsi > 75:
        parts.append(f"RSI({rsi:.0f}) 进入超买区域，注意回调风险。")
    elif rsi < 25:
        parts.append(f"RSI({rsi:.0f}) 进入超卖区域，可能存在反弹机会。")
    elif rsi > 55:
        parts.append(f"RSI({rsi:.0f}) 偏强。")
    elif rsi < 45:
        parts.append(f"RSI({rsi:.0f}) 偏弱。")

    # 支撑阻力
    if sr["supports"]:
        parts.append(f"下方支撑：{', '.join(str(s) for s in sr['supports'][:2])}。")
    if sr["resistances"]:
        parts.append(f"上方阻力：{', '.join(str(r) for r in sr['resistances'][:2])}。")

    # 操作建议
    if signal == "buy":
        parts.append(
            f"建议入场 {entry}，止损 {sl}（-{abs(entry-sl):.2f}），"
            f"第一止盈 {tp1}（+{abs(tp1-entry):.2f}），"
            f"第二止盈 {tp2}（+{abs(tp2-entry):.2f}）。"
        )
    elif signal == "sell":
        parts.append(
            f"建议做空/减仓入场 {entry}，止损 {sl}（+{abs(sl-entry):.2f}），"
            f"第一止盈 {tp1}（-{abs(entry-tp1):.2f}），"
            f"第二止盈 {tp2}（-{abs(entry-tp2):.2f}）。"
        )
    else:
        parts.append("目前无明确方向信号，建议观望等待突破。")

    return "".join(parts)
