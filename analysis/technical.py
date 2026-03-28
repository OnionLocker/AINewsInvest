"""Technical analysis engine: indicators, S/R, trend, signal, trade levels."""
from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from core.data_source import get_klines

_SUPPORTED_MARKETS = frozenset({"us_stock", "hk_stock"})
_KLINE_CACHE: dict[tuple[str, str, int], tuple[float, pd.DataFrame]] = {}
_KLINE_TTL_SEC = 300
_KLINE_MAX_CACHE = 128
_KLINES_DAYS = 150
_MIN_BARS = 70


def _prune_kline_cache() -> None:
    if len(_KLINE_CACHE) <= _KLINE_MAX_CACHE:
        return
    oldest = sorted(_KLINE_CACHE.items(), key=lambda x: x[1][0])[: len(_KLINE_CACHE) - _KLINE_MAX_CACHE + 32]
    for k, _ in oldest:
        _KLINE_CACHE.pop(k, None)


def _get_klines_cached(ticker: str, market: str, days: int) -> pd.DataFrame:
    now = time.monotonic()
    key = (ticker, market, days)
    if key in _KLINE_CACHE:
        ts, df = _KLINE_CACHE[key]
        if now - ts < _KLINE_TTL_SEC:
            return df.copy()
    df = get_klines(ticker, market, days=days)
    _KLINE_CACHE[key] = (now, df.copy())
    _prune_kline_cache()
    return df.copy()


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_g = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_l = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_g / (avg_l + 1e-12)
    return 100.0 - (100.0 / (1.0 + rs))


def _atr_wilder(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_c = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_c).abs(),
            (low - prev_c).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    dif = ema12 - ema26
    dea = _ema(dif, 9)
    hist = dif - dea
    return dif, dea, hist


def _kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9, m1: int = 3, m2: int = 3):
    low_n = low.rolling(n).min()
    high_n = high.rolling(n).max()
    span = (high_n - low_n).replace(0, np.nan)
    rsv = (close - low_n) / span * 100.0
    rsv = rsv.fillna(50.0)
    k = rsv.rolling(m1).mean()
    d = k.rolling(m2).mean()
    j = 3.0 * k - 2.0 * d
    return k, d, j


def _bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0):
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    bw = (upper - lower) / (mid.abs() + 1e-12)
    return upper, mid, lower, bw


def _num(x: Any, nd: int = 4) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if np.isnan(v) or np.isinf(v):
        return None
    return round(v, nd)


def _collect_sr(
    close: float,
    high: pd.Series,
    low: pd.Series,
    ma5: float,
    ma10: float,
    ma20: float,
    ma60: float,
    bb_u: float,
    bb_m: float,
    bb_l: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    h10 = float(high.tail(10).max())
    l10 = float(low.tail(10).min())
    h20 = float(high.tail(20).max())
    l20 = float(low.tail(20).min())
    raw_sup = [
        (l10, "recent_low_10"),
        (l20, "recent_low_20"),
        (_num(bb_l), "bollinger_lower"),
        (_num(ma5), "ma5"),
        (_num(ma10), "ma10"),
        (_num(ma20), "ma20"),
        (_num(ma60), "ma60"),
    ]
    raw_res = [
        (h10, "recent_high_10"),
        (h20, "recent_high_20"),
        (_num(bb_u), "bollinger_upper"),
        (_num(bb_m), "bollinger_middle"),
        (_num(ma5), "ma5"),
        (_num(ma10), "ma10"),
        (_num(ma20), "ma20"),
        (_num(ma60), "ma60"),
    ]
    support: list[dict[str, Any]] = []
    seen_s: set[float] = set()
    for val, src in raw_sup:
        if val is None:
            continue
        if val < close and val not in seen_s:
            seen_s.add(val)
            support.append({"price": round(val, 4), "source": src})
    support.sort(key=lambda x: x["price"], reverse=True)

    resistance: list[dict[str, Any]] = []
    seen_r: set[float] = set()
    for val, src in raw_res:
        if val is None:
            continue
        if val > close and val not in seen_r:
            seen_r.add(val)
            resistance.append({"price": round(val, 4), "source": src})
    resistance.sort(key=lambda x: x["price"])
    return support, resistance


def _trend(
    c: float,
    ma5: float,
    ma10: float,
    ma20: float,
    ma60: float,
    dif: float,
    dea: float,
) -> str:
    bull_ma = c > ma20 > ma60
    bear_ma = c < ma20 < ma60
    bull_short = ma5 > ma10
    bear_short = ma5 < ma10
    if bull_ma and bull_short and dif >= dea:
        return "bullish"
    if bear_ma and bear_short and dif <= dea:
        return "bearish"
    return "ranging"


def _signal_from_score(score: int) -> str:
    if score >= 2:
        return "buy"
    if score <= -2:
        return "sell"
    return "neutral"


def _composite_score_int(
    c: float,
    ma20: float,
    ma60: float,
    dif: float,
    dea: float,
    hist: float,
    rsi: float,
    k: float,
    d: float,
    bb_u: float,
    bb_m: float,
    bb_l: float,
) -> tuple[int, float]:
    s = 0
    if c > ma20 > ma60:
        s += 1
    elif c < ma20 < ma60:
        s -= 1
    if dif > dea:
        s += 1
    elif dif < dea:
        s -= 1
    if hist > 0:
        s += 1
    elif hist < 0:
        s -= 1
    if rsi < 35:
        s += 1
    elif rsi > 65:
        s -= 1
    if k > d and k < 80:
        s += 1
    elif k < d and k > 20:
        s -= 1
    width = bb_u - bb_l
    if width > 1e-9:
        pos = (c - bb_l) / width
        if pos < 0.2:
            s += 1
        elif pos > 0.8:
            s -= 1
    norm = max(min(s / 6.0, 1.0), -1.0)
    return s, round(norm, 4)


def _trade_levels(
    signal: str,
    close: float,
    atr: float,
    support: list[dict[str, Any]],
    resistance: list[dict[str, Any]],
) -> dict[str, float | None]:
    atr = max(atr, close * 1e-6)
    nearest_sup = support[0]["price"] if support else None
    nearest_res = resistance[0]["price"] if resistance else None

    if signal == "buy":
        entry = round(close, 4)
        if nearest_sup is not None:
            sl = min(nearest_sup, close) - 1.5 * atr
        else:
            sl = close - 2.0 * atr
        tp1 = close + 1.5 * atr
        if nearest_res is not None:
            tp1 = min(tp1, nearest_res)
        tp2 = close + 3.0 * atr
        if nearest_res is not None:
            tp2 = max(tp2, nearest_res)
        if tp2 <= tp1:
            tp2 = tp1 + 1.5 * atr
        return {
            "entry": entry,
            "stop_loss": _num(sl, 4),
            "take_profit_1": _num(round(tp1, 4), 4),
            "take_profit_2": _num(round(tp2, 4), 4),
        }
    if signal == "sell":
        entry = round(close, 4)
        if nearest_res is not None:
            sl = max(nearest_res, close) + 1.5 * atr
        else:
            sl = close + 2.0 * atr
        tp1 = close - 1.5 * atr
        if nearest_sup is not None and nearest_sup < close:
            tp1 = max(tp1, nearest_sup + 0.25 * atr)
        tp2 = min(close - 3.0 * atr, tp1 - 1.5 * atr)
        if tp2 >= tp1:
            tp2 = tp1 - 1.0 * atr
        return {
            "entry": entry,
            "stop_loss": _num(sl, 4),
            "take_profit_1": _num(round(tp1, 4), 4),
            "take_profit_2": _num(round(tp2, 4), 4),
        }
    entry = round(close, 4)
    return {
        "entry": entry,
        "stop_loss": _num(close - 1.0 * atr, 4),
        "take_profit_1": _num(close + 1.0 * atr, 4),
        "take_profit_2": _num(close + 2.0 * atr, 4),
    }


def analyze(ticker: str, market: str) -> dict | None:
    if market not in _SUPPORTED_MARKETS:
        logger.warning(f"Technical analyze unsupported market: {market}")
        return None

    df = _get_klines_cached(ticker, market, _KLINES_DAYS)
    if df.empty or len(df) < _MIN_BARS:
        logger.warning(f"Insufficient klines {market}:{ticker} len={len(df)}")
        return None

    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["high", "low", "close"])
    if len(df) < _MIN_BARS:
        return None

    c = df["close"]
    h = df["high"]
    lo = df["low"]
    v = df["volume"]

    ma5 = c.rolling(5).mean()
    ma10 = c.rolling(10).mean()
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    vol_ma5 = v.rolling(5).mean()
    vol_ma20 = v.rolling(20).mean()

    dif, dea, hist = _macd(c)
    rsi = _rsi_wilder(c, 14)
    bb_u, bb_m, bb_l, bb_w = _bollinger(c, 20, 2.0)
    k_line, d_line, j_line = _kdj(h, lo, c, 9, 3, 3)
    atr = _atr_wilder(h, lo, c, 14)

    last = df.iloc[-1]
    c0 = float(last["close"])
    ma5v = float(ma5.iloc[-1])
    ma10v = float(ma10.iloc[-1])
    ma20v = float(ma20.iloc[-1])
    ma60v = float(ma60.iloc[-1])
    difv = float(dif.iloc[-1])
    deav = float(dea.iloc[-1])
    histv = float(hist.iloc[-1])
    rsiv = float(rsi.iloc[-1])
    kv = float(k_line.iloc[-1])
    dv = float(d_line.iloc[-1])
    jv = float(j_line.iloc[-1])
    atrv = float(atr.iloc[-1])
    bu = float(bb_u.iloc[-1])
    bm = float(bb_m.iloc[-1])
    bl = float(bb_l.iloc[-1])
    bwidth = float(bb_w.iloc[-1])

    support, resistance = _collect_sr(c0, h, lo, ma5v, ma10v, ma20v, ma60v, bu, bm, bl)
    trend = _trend(c0, ma5v, ma10v, ma20v, ma60v, difv, deav)
    score_i, score_norm = _composite_score_int(
        c0, ma20v, ma60v, difv, deav, histv, rsiv, kv, dv, bu, bm, bl
    )
    signal = _signal_from_score(score_i)
    levels = _trade_levels(signal, c0, atrv, support, resistance)

    as_of = last["date"]
    if hasattr(as_of, "isoformat"):
        as_of_s = as_of.isoformat()
    else:
        as_of_s = str(as_of)

    return {
        "ticker": ticker,
        "market": market,
        "price": round(c0, 4),
        "as_of": as_of_s,
        "trend": trend,
        "signal": signal,
        "composite_score": score_norm,
        "composite_score_raw": score_i,
        "indicators": {
            "ma": {
                "ma5": _num(ma5v),
                "ma10": _num(ma10v),
                "ma20": _num(ma20v),
                "ma60": _num(ma60v),
            },
            "macd": {
                "dif": _num(difv),
                "dea": _num(deav),
                "histogram": _num(histv),
            },
            "rsi14": _num(rsiv, 2),
            "bollinger": {
                "upper": _num(bu),
                "middle": _num(bm),
                "lower": _num(bl),
                "bandwidth": _num(bwidth, 6),
            },
            "kdj": {
                "k": _num(kv, 2),
                "d": _num(dv, 2),
                "j": _num(jv, 2),
            },
            "atr14": _num(atrv),
            "volume_ma": {
                "ma5": _num(float(vol_ma5.iloc[-1])),
                "ma20": _num(float(vol_ma20.iloc[-1])),
            },
            "volume": int(last["volume"]) if pd.notna(last["volume"]) else 0,
        },
        "support_resistance": {
            "support": support,
            "resistance": resistance,
        },
        "levels": levels,
    }
