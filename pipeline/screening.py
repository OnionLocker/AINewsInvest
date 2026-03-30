"""Layer 1 & 2: Quantitative pre-screening + Technical data enrichment.

Layer 1 filters the full stock pool down to ~40 candidates using hard
quantitative thresholds (market cap, volume, PE/PB).

Layer 2 enriches each candidate with technical signals: ATR, MA alignment,
volume-profile support, volume-price divergence, support touch strength,
weekly trend. This enriched data feeds into the LLM Agents.

Adapted from astock-quant/pipeline/screening.py for US/HK markets.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from core.data_source import get_financial_data, get_index_components, get_klines, get_quote
from pipeline.config import get_config


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Stock pool loading
# ---------------------------------------------------------------------------

def _load_pool_file(market: str) -> list[dict] | None:
    candidates = [
        _package_root() / "data" / "stock_pool.json",
        Path.cwd() / "data" / "stock_pool.json",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                pool = [x for x in raw if isinstance(x, dict) and x.get("market") == market]
                logger.info(f"Loaded {len(pool)} {market} symbols from {path}")
                return pool
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read stock pool {path}: {e}")
    return None


def _pool_from_indices(market: str) -> list[dict]:
    cfg = get_config()
    key = "us_stock" if market == "us_stock" else "hk_stock"
    entries = cfg.stock_pool.get(key, [])
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for ent in entries:
        if not ent.index:
            continue
        logger.info(f"Fetching index components {ent.name} ({ent.index})")
        for row in get_index_components(ent.index):
            if row.get("market") != market:
                continue
            k = (str(row["ticker"]), market)
            if k not in seen:
                seen.add(k)
                out.append(row)
    return out


# ---------------------------------------------------------------------------
# Layer 1: Hard quantitative screening
# ---------------------------------------------------------------------------

def _norm_series(values: list[float | None], higher_is_better: bool) -> list[float]:
    arr = np.array([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    if arr.size == 0:
        return [0.5] * len(values)
    lo, hi = float(arr.min()), float(arr.max())
    out: list[float] = []
    for v in values:
        if v is None or not np.isfinite(v):
            out.append(0.5)
            continue
        if hi <= lo:
            x = 0.5
        else:
            x = (float(v) - lo) / (hi - lo)
        if not higher_is_better:
            x = 1.0 - x
        out.append(max(0.0, min(1.0, x)))
    return out


def run_screening(market: str = "us_stock", top_n: int = 40) -> list[dict]:
    """Layer 1: Full stock pool -> ~top_n candidates via hard filters + ranking."""
    cfg = get_config()
    sc = cfg.screening

    pool = _load_pool_file(market)
    if not pool:
        pool = _pool_from_indices(market)
    if not pool:
        logger.warning(f"No stock pool for {market}")
        return []

    import time as _time
    _BATCH = 5

    quotes: dict[tuple[str, str], dict | None] = {}
    for bi in range(0, len(pool), _BATCH):
        batch = pool[bi:bi + _BATCH]
        with ThreadPoolExecutor(max_workers=_BATCH) as ex:
            futs = {ex.submit(get_quote, row["ticker"], row["market"]): row for row in batch}
            for fut in as_completed(futs):
                row = futs[fut]
                t, m = row["ticker"], row["market"]
                try:
                    quotes[(t, m)] = fut.result()
                except Exception as e:
                    logger.warning(f"Quote error {m}:{t}: {e}")
                    quotes[(t, m)] = None
        if bi + _BATCH < len(pool):
            _time.sleep(0.5)

    passed: list[dict] = []
    for row in pool:
        t, m = row["ticker"], row["market"]
        q = quotes.get((t, m))
        if not q or not q.get("price"):
            continue
        price = float(q["price"])
        mc = float(q.get("market_cap") or 0)
        change_pct = float(q.get("change_pct") or 0)
        volume = float(q.get("volume") or 0)

        if mc < sc.min_market_cap:
            continue
        if volume < sc.min_avg_volume:
            continue
        if abs(change_pct) > 20:
            continue

        pe = None
        pb = None
        fin = None
        passed.append({**row, "quote": q, "financial": fin})

    logger.info(f"Layer 1 hard filter: {len(pool)} -> {len(passed)} passed (market={market})")

    if not passed:
        return []

    fin_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(get_financial_data, r["ticker"], r["market"]): r for r in passed}
        for fut in as_completed(futs):
            r = futs[fut]
            try:
                fin = fut.result()
            except Exception:
                fin = None
            r["financial"] = fin
            fin_rows.append(r)

    filtered: list[dict] = []
    for r in fin_rows:
        fin = r.get("financial")
        pe = _safe_float(fin.get("pe_ttm")) if fin else None
        pb = _safe_float(fin.get("pb")) if fin else None

        if pe is not None and (pe < sc.min_pe or pe > sc.max_pe):
            continue
        if pb is not None and pb > sc.max_pb:
            continue
        filtered.append(r)

    if not filtered:
        logger.info(f"No symbols passed financial filters for {market}")
        return []

    vols = [float(r["quote"].get("volume", 0)) for r in filtered]
    moms: list[float] = []
    mcs: list[float] = []
    changes: list[float] = []
    for r in filtered:
        q = r["quote"]
        price = float(q["price"])
        yh = float(q.get("year_high") or price)
        yl = float(q.get("year_low") or price)
        if yh > yl:
            rel_pos = (price - yl) / (yh - yl)
            if rel_pos > 0.85:
                mom = 0.6 - (rel_pos - 0.85) * 2.0
            elif rel_pos >= 0.35:
                mom = 0.4 + (rel_pos - 0.35) * 0.4
            else:
                mom = rel_pos * 1.14
            moms.append(max(0.0, min(1.0, mom)))
        else:
            moms.append(0.5)
        mcs.append(max(np.log10(max(q.get("market_cap") or 1, 1)), 0))
        chg = abs(float(q.get("change_pct") or 0))
        if chg <= 3.0:
            changes.append(chg / 3.0)
        else:
            changes.append(max(0.0, 1.0 - (chg - 3.0) / 5.0))

    nv = _norm_series(vols, higher_is_better=True)
    nm = _norm_series(moms, higher_is_better=True)
    nc = _norm_series(mcs, higher_is_better=True)
    nchg = _norm_series(changes, higher_is_better=True)

    wv, wm, wc, wchg = sc.weight_volume, sc.weight_momentum, sc.weight_market_cap, sc.weight_volatility

    results: list[dict] = []
    for i, r in enumerate(filtered):
        q = r["quote"]
        fin = r.get("financial") or {}
        comp = (wv * nv[i] + wm * nm[i] + wc * nc[i] + wchg * nchg[i]) * 100.0
        results.append({
            "ticker": r["ticker"],
            "name": r.get("name", r["ticker"]),
            "market": r["market"],
            "score": round(comp, 2),
            "price": q.get("price", 0),
            "change_pct": q.get("change_pct", 0),
            "volume": q.get("volume", 0),
            "market_cap": q.get("market_cap", 0),
            "pe_ttm": fin.get("pe_ttm"),
            "pb": fin.get("pb"),
            "year_high": q.get("year_high"),
            "year_low": q.get("year_low"),
            "financial": fin,
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    max_per_sector = max(top_n // 3, 5)
    sector_count: dict[str, int] = {}
    diversified: list[dict] = []
    overflow: list[dict] = []
    for r in results:
        sec = (r.get("financial") or {}).get("sector", "") or "Unknown"
        if sector_count.get(sec, 0) < max_per_sector:
            diversified.append(r)
            sector_count[sec] = sector_count.get(sec, 0) + 1
        else:
            overflow.append(r)
        if len(diversified) >= top_n:
            break
    if len(diversified) < top_n:
        for r in overflow:
            diversified.append(r)
            if len(diversified) >= top_n:
                break

    logger.info(
        f"Layer 1 ranking: {len(filtered)} -> {len(diversified)} candidates "
        f"(sectors: {len(sector_count)}, max/sector: {max_per_sector})"
    )
    return diversified


# ---------------------------------------------------------------------------
# Layer 2: Technical data enrichment
# ---------------------------------------------------------------------------

def compute_atr(kdf: pd.DataFrame, period: int = 20) -> float:
    """Average True Range over last `period` bars."""
    if kdf.empty or len(kdf) < 2:
        return 0.0
    df = kdf.tail(period + 1).reset_index(drop=True)
    if len(df) < 2:
        return 0.0
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    closes = df["close"].tolist()
    tr_list: list[float] = []
    for i in range(1, len(df)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr_list.append(max(hl, hc, lc))
    if not tr_list:
        return 0.0
    return round(sum(tr_list[-period:]) / len(tr_list[-period:]), 4)


def compute_volatility_pct(kdf: pd.DataFrame, period: int = 20) -> float:
    """Average daily volatility % = mean(|pct_change|) over last `period` bars."""
    if kdf.empty or len(kdf) < 2:
        return 0.0
    closes = kdf["close"].tail(period + 1).tolist()
    if len(closes) < 2:
        return 0.0
    changes = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            changes.append(abs((closes[i] - closes[i - 1]) / closes[i - 1] * 100))
    return round(sum(changes) / len(changes), 2) if changes else 0.0


def classify_volatility(vol_pct: float) -> str:
    if vol_pct > 4.0:
        return "high"
    elif vol_pct > 2.0:
        return "medium"
    return "low"


def compute_volume_profile_support(kdf: pd.DataFrame, close: float, bins: int = 20) -> list[float]:
    """Find support levels from volume-weighted price distribution (60-day)."""
    recent = kdf.tail(60)
    if recent.empty or len(recent) < 10:
        return [round(close * 0.97, 2), round(close * 0.94, 2)]

    price_min = float(recent["low"].min())
    price_max = float(recent["high"].max())
    bin_size = (price_max - price_min) / bins
    if bin_size <= 0:
        return [round(close * 0.97, 2), round(close * 0.94, 2)]

    volume_bins = [0.0] * bins
    for _, row in recent.iterrows():
        bar_low, bar_high = float(row["low"]), float(row["high"])
        bar_vol = _safe_float(row.get("volume", 0))
        bar_range = max(bar_high - bar_low, 0.01)
        for i in range(bins):
            bl = price_min + i * bin_size
            bh = bl + bin_size
            overlap = max(0.0, min(bar_high, bh) - max(bar_low, bl))
            volume_bins[i] += bar_vol * (overlap / bar_range)

    supports = []
    for i in range(bins):
        bin_mid = price_min + (i + 0.5) * bin_size
        if bin_mid < close:
            supports.append((volume_bins[i], round(bin_mid, 2)))
    supports.sort(reverse=True)

    if len(supports) >= 2:
        return [supports[0][1], supports[1][1]]
    elif supports:
        return [supports[0][1], round(supports[0][1] * 0.97, 2)]
    return [round(close * 0.97, 2), round(close * 0.94, 2)]


def compute_support_strength(
    kdf: pd.DataFrame, support_level: float, tolerance_pct: float = 0.02,
) -> tuple[int, str]:
    """Count how many times support was tested and whether it held."""
    if kdf.empty or support_level <= 0:
        return 0, "untested"
    recent = kdf.tail(20)
    if recent.empty:
        return 0, "untested"

    touch_zone = support_level * (1 + tolerance_pct)
    touch_count = 0
    all_held = True
    for _, bar in recent.iterrows():
        low = _safe_float(bar.get("low", 0))
        close_val = _safe_float(bar.get("close", 0))
        if low <= touch_zone and low >= support_level * 0.97:
            touch_count += 1
            if close_val < support_level * 0.99:
                all_held = False

    if touch_count >= 3 and all_held:
        return touch_count, "strong"
    elif touch_count >= 2:
        return touch_count, "moderate"
    elif touch_count == 1:
        return touch_count, "weak"
    return 0, "untested"


def compute_volume_at_high(kdf: pd.DataFrame) -> float:
    """Ratio of volume when 20d high was made vs current volume.
    > 1.0 means high was made with MORE volume (divergence risk).
    """
    if kdf.empty or len(kdf) < 3:
        return 1.0
    recent = kdf.tail(20)
    if "high" not in recent.columns or "volume" not in recent.columns:
        return 1.0
    high_idx = recent["high"].idxmax()
    vol_at_high = _safe_float(recent.loc[high_idx, "volume"])
    current_vol = recent["volume"].tail(3).mean()
    if current_vol <= 0:
        return 1.0
    return round(float(vol_at_high / max(current_vol, 1)), 2)


def compute_weekly_trend(kdf: pd.DataFrame, close: float) -> str:
    """Derive weekly trend from daily K-lines (4-week MA direction)."""
    if kdf.empty or len(kdf) < 20:
        return "neutral"
    try:
        df = kdf.tail(60).sort_values("date").reset_index(drop=True)
        closes = df["close"].tolist()
        week_closes: list[float] = []
        for i in range(0, len(closes), 5):
            chunk = closes[i:i + 5]
            if chunk:
                week_closes.append(chunk[-1])
        if len(week_closes) < 4:
            return "neutral"
        ma4w = sum(week_closes[-4:]) / 4
        ma8w = sum(week_closes[-min(8, len(week_closes)):]) / min(8, len(week_closes))
        if close > ma4w and ma4w > ma8w:
            return "bullish"
        elif close < ma4w and ma4w < ma8w:
            return "bearish"
        return "neutral"
    except Exception:
        return "neutral"


def batch_fetch_klines(
    candidates: list[dict], days: int = 80,
) -> dict[str, pd.DataFrame]:
    """Fetch K-line data for all candidates concurrently."""
    results: dict[str, pd.DataFrame] = {}
    max_workers = min(8, max(3, len(candidates) // 3))

    def _fetch(ticker: str, market: str):
        return get_klines(ticker, market, days=days)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {
            ex.submit(_fetch, c["ticker"], c["market"]): c["ticker"]
            for c in candidates
        }
        for fut in as_completed(futs):
            ticker = futs[fut]
            try:
                df = fut.result()
                results[ticker] = df if df is not None and not df.empty else pd.DataFrame()
            except Exception:
                results[ticker] = pd.DataFrame()

    ok = sum(1 for v in results.values() if not v.empty)
    logger.info(f"Layer 2 K-line fetch: {ok}/{len(candidates)} stocks with data")
    return results


def _check_earnings_proximity(ticker: str, market: str) -> dict:
    """Check if earnings are within the next 5 trading days."""
    try:
        from core.data_source import to_yf_ticker
        from datetime import datetime, timedelta
        import yfinance as yf

        symbol = to_yf_ticker(ticker, market)
        t = yf.Ticker(symbol)
        cal = t.calendar
        if cal is None or (hasattr(cal, 'empty') and cal.empty):
            return {"days_away": None, "date_str": None, "imminent": False}

        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if isinstance(ed, list) and ed:
                ed = ed[0]
        elif hasattr(cal, 'iloc'):
            ed = cal.iloc[0, 0] if cal.shape[1] > 0 else None
        else:
            ed = None

        if ed is None:
            return {"days_away": None, "date_str": None, "imminent": False}

        if hasattr(ed, 'date'):
            ed_date = ed.date()
        elif isinstance(ed, str):
            ed_date = datetime.strptime(ed[:10], "%Y-%m-%d").date()
        else:
            return {"days_away": None, "date_str": None, "imminent": False}

        today = datetime.now().date()
        days_away = (ed_date - today).days

        return {
            "days_away": days_away,
            "date_str": ed_date.strftime("%Y-%m-%d"),
            "imminent": 0 <= days_away <= 5,
        }
    except Exception:
        return {"days_away": None, "date_str": None, "imminent": False}


def _compute_fundamental_score(candidate: dict) -> float:
    """Lightweight fundamental scoring from available financial data.

    Returns 0-100 score. 50 = neutral baseline.
    """
    score = 50.0
    fin = candidate.get("financial") or {}

    roe = fin.get("roe")
    if roe is not None:
        if roe > 0.20:
            score += 12
        elif roe > 0.15:
            score += 8
        elif roe > 0.08:
            score += 3
        elif roe < 0:
            score -= 15

    rev_growth = fin.get("revenue_growth")
    if rev_growth is not None:
        if rev_growth > 0.20:
            score += 10
        elif rev_growth > 0.10:
            score += 6
        elif rev_growth > 0:
            score += 2
        elif rev_growth < -0.10:
            score -= 10

    de = fin.get("debt_to_equity")
    if de is not None:
        if de > 3.0:
            score -= 12
        elif de > 2.0:
            score -= 6
        elif de < 0.5:
            score += 5

    cr = fin.get("current_ratio")
    if cr is not None:
        if cr > 2.0:
            score += 5
        elif cr > 1.5:
            score += 3
        elif cr < 1.0:
            score -= 8

    margin = fin.get("profit_margins") or fin.get("profit_margin")
    if margin is not None:
        if margin > 0.20:
            score += 8
        elif margin > 0.10:
            score += 4
        elif margin < 0:
            score -= 10

    fcf = fin.get("free_cash_flow") or fin.get("free_cashflow")
    if fcf is not None:
        if fcf > 0:
            score += 5
        else:
            score -= 8

    short_pct = fin.get("short_pct_of_float")
    if short_pct is not None:
        if short_pct > 0.20:
            score -= 5
        elif short_pct > 0.10:
            score -= 2

    insider_pct = fin.get("held_pct_insiders")
    if insider_pct is not None:
        if insider_pct > 0.30:
            score += 5
        elif insider_pct > 0.10:
            score += 3

    inst_pct = fin.get("held_pct_institutions")
    if inst_pct is not None:
        if inst_pct > 0.80:
            score += 3
        elif inst_pct < 0.30:
            score -= 3

    return max(0, min(100, score))


def build_enriched_candidates(
    candidates: list[dict],
    kline_map: dict[str, pd.DataFrame],
) -> list[dict]:
    """Layer 2: Enrich each candidate with technical signals and K-line features.

    Output is the unified data payload that feeds into both LLM Agents.
    """
    earnings_map: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(6, max(2, len(candidates) // 4))) as ex:
        futs = {
            ex.submit(_check_earnings_proximity, c["ticker"], c.get("market", "us_stock")): c["ticker"]
            for c in candidates
        }
        for fut in as_completed(futs):
            ticker = futs[fut]
            try:
                earnings_map[ticker] = fut.result()
            except Exception:
                earnings_map[ticker] = {"days_away": None, "date_str": None, "imminent": False}

    enriched: list[dict] = []

    for c in candidates:
        ticker = c["ticker"]
        market = c.get("market", "us_stock")
        price = _safe_float(c.get("price"))
        if price <= 0:
            continue

        kdf = kline_map.get(ticker, pd.DataFrame())

        if kdf.empty or len(kdf) < 5:
            ma5 = ma10 = ma20 = ma60 = price
            support_levels = [round(price * 0.97, 2), round(price * 0.94, 2)]
            resistance_levels = [round(price * 1.05, 2), round(price * 1.09, 2)]
            volume_ratio = 1.0
            atr_20d = 0.0
            volatility_20d = 0.0
            volatility_class = "medium"
            ma20_bias_pct = 0.0
            support_touch_count = 0
            support_hold_strength = "untested"
            high_20d_volume_ratio = 1.0
            kline_part1: list[dict] = []
            kline_part2: list[dict] = []
        else:
            kdf = kdf.sort_values("date").reset_index(drop=True)
            closes = kdf["close"].tolist()
            n = len(closes)
            ma5 = round(sum(closes[-min(5, n):]) / min(5, n), 2)
            ma10 = round(sum(closes[-min(10, n):]) / min(10, n), 2)
            ma20 = round(sum(closes[-min(20, n):]) / min(20, n), 2)
            ma60 = round(sum(closes[-min(60, n):]) / min(60, n), 2) if n >= 30 else ma20

            recent = kdf.tail(20)
            high_20 = float(recent["high"].max()) if "high" in recent.columns else price * 1.05
            resistance_levels = [round(high_20, 2), round(high_20 * 1.03, 2)]

            support_levels = compute_volume_profile_support(kdf, price)

            avg_vol_5 = kdf["volume"].tail(5).mean() if "volume" in kdf.columns else 1
            avg_vol_20 = kdf["volume"].tail(20).mean() if "volume" in kdf.columns else 1
            volume_ratio = round(float(avg_vol_5 / max(avg_vol_20, 1)), 2)

            ma20_bias_pct = round(abs(price - ma20) / max(ma20, 0.01) * 100, 2)
            atr_20d = compute_atr(kdf, period=20)
            volatility_20d = compute_volatility_pct(kdf, period=20)
            volatility_class = classify_volatility(volatility_20d)

            support_touch_count, support_hold_strength = compute_support_strength(
                kdf, support_levels[0] if support_levels else 0,
            )
            high_20d_volume_ratio = compute_volume_at_high(kdf)

            recent_20 = kdf.tail(20)
            n_recent = len(recent_20)
            split_point = max(n_recent - 10, 0)
            part1_df = recent_20.iloc[:split_point]
            part2_df = recent_20.iloc[split_point:]

            def _kline_to_dict(kr):
                return {
                    "date": str(kr.get("date", "")),
                    "open": round(_safe_float(kr.get("open")), 2),
                    "high": round(_safe_float(kr.get("high")), 2),
                    "low": round(_safe_float(kr.get("low")), 2),
                    "close": round(_safe_float(kr.get("close")), 2),
                    "volume": int(_safe_float(kr.get("volume"))),
                }

            kline_part1 = [_kline_to_dict(kr) for _, kr in part1_df.iterrows()]
            kline_part2 = [_kline_to_dict(kr) for _, kr in part2_df.iterrows()]

        weekly_trend = compute_weekly_trend(kdf, price)

        ma_bullish = (ma5 >= ma10 >= ma20) and (ma5 > ma20)
        ma_bearish = (ma5 <= ma10 <= ma20) and (ma5 < ma20)
        above_ma20 = price > ma20 if ma20 > 0 else False
        volume_expansion = volume_ratio > 1.3
        near_support = price <= support_levels[0] * 1.02 if support_levels else False
        near_resistance = price >= resistance_levels[0] * 0.98 if resistance_levels else False
        broke_20d_high = price >= resistance_levels[0] if resistance_levels else False

        overbought_bias = ma20_bias_pct > 15.0
        volume_price_divergence = (
            broke_20d_high
            and high_20d_volume_ratio > 1.3
            and not volume_expansion
        )

        fundamental_score = _compute_fundamental_score(c)
        earnings_info = earnings_map.get(ticker, {"days_away": None, "date_str": None, "imminent": False})

        enriched.append({
            "ticker": ticker,
            "name": c.get("name", ticker),
            "market": market,
            "price": price,
            "fundamental_score": fundamental_score,
            "change_pct": _safe_float(c.get("change_pct")),
            "volume": _safe_float(c.get("volume")),
            "market_cap": _safe_float(c.get("market_cap")),
            "pe_ttm": c.get("pe_ttm"),
            "pb": c.get("pb"),
            "score": _safe_float(c.get("score")),
            "financial": c.get("financial"),
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "ma60": ma60,
            "ma20_bias_pct": ma20_bias_pct,
            "atr_20d": atr_20d,
            "volatility_20d": volatility_20d,
            "volatility_class": volatility_class,
            "volume_ratio": volume_ratio,
            "support_levels": support_levels,
            "resistance_levels": resistance_levels,
            "support_touch_count": support_touch_count,
            "support_hold_strength": support_hold_strength,
            "high_20d_volume_ratio": high_20d_volume_ratio,
            "weekly_trend": weekly_trend,
            "signals": {
                "ma_bullish_align": ma_bullish,
                "ma_bearish_align": ma_bearish,
                "above_ma20": above_ma20,
                "volume_expansion": volume_expansion,
                "near_support": near_support,
                "near_resistance": near_resistance,
                "broke_20d_high": broke_20d_high,
                "overbought_bias": overbought_bias,
                "volume_price_divergence": volume_price_divergence,
                "weekly_bearish": weekly_trend == "bearish",
            },
            "kline_recent_part1": kline_part1,
            "kline_recent_part2": kline_part2,
            "earnings_days_away": earnings_info.get("days_away"),
            "earnings_date_str": earnings_info.get("date_str"),
            "earnings_imminent": earnings_info.get("imminent", False),
        })

    logger.info(f"Layer 2 enrichment: {len(enriched)} candidates with technical data")
    return enriched
