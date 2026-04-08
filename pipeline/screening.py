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

from core.data_source import (
    get_financial_data,
    get_index_components,
    get_insider_trades,
    get_klines,
    get_options_signal,
    get_quote,
)
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


def _fetch_benchmark_return(market: str, days: int = 60) -> float:
    """Fetch benchmark index return over the lookback period.

    US → SPY, HK → ^HSI.  Returns 0.0 on failure (graceful degradation).
    """
    try:
        symbol = "SPY" if market == "us_stock" else "^HSI"
        kdf = get_klines(symbol, market, days=days + 5)
        if kdf is not None and not kdf.empty and len(kdf) >= 20:
            closes = kdf["close"].tolist()
            return (closes[-1] / closes[0]) - 1.0
    except Exception as e:
        logger.debug(f"Benchmark return fetch failed: {e}")
    return 0.0


def run_screening(market: str = "us_stock", top_n: int = 40) -> list[dict]:
    """Layer 1: Full stock pool -> ~top_n candidates via two-stage screening.

    v4 redesign for short-term trading:
    - Stage A: Hard filters (market cap, volume, daily change) + MA proximity pre-rank
    - Stage B: K-line fetch + quality gate (reject garbage, not score)
    - Multi-factor ranking:
      * Acceleration (30%): Is the stock gaining momentum? (10d vs 20d return ratio)
      * Volume Anomaly (25%): Recent volume surge vs 20-day average
      * Trend Setup (30%): MA structure + pullback quality (near MA20 in uptrend)
      * Volatility Fit (15%): Optimal daily vol range for short-term trading (1-3%)
    """
    cfg = get_config()
    sc = cfg.screening

    pool = _load_pool_file(market)
    if not pool:
        pool = _pool_from_indices(market)
    if not pool:
        logger.warning(f"No stock pool for {market}")
        return []

    # ------------------------------------------------------------------
    # Stage A: Fast quote-based hard filter + MA proximity pre-rank
    # ------------------------------------------------------------------

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

        # --- Hard gates ---
        if mc < sc.min_market_cap:
            continue
        if volume < sc.min_avg_volume:
            continue
        if abs(change_pct) > sc.max_daily_change_pct:
            continue
        # Note: PE hard filter REMOVED — high-growth stocks (NVDA, TSLA)
        # often have PE > 80. Quality gate in Stage B handles garbage.

        passed.append({**row, "quote": q, "financial": None})

    logger.info(f"Stage A hard filter: {len(pool)} -> {len(passed)} passed (market={market})")

    if not passed:
        return []

    # Pre-rank: prefer stocks near MA20 (pullback entry), not at 52-week highs.
    # We approximate with 52-week position: middle range (0.4-0.7) is ideal.
    for r in passed:
        q = r["quote"]
        price = float(q["price"])
        yh = float(q.get("year_high") or price)
        yl = float(q.get("year_low") or price)
        if yh > yl:
            pos = (price - yl) / (yh - yl)
            # Bell curve: peak at 0.55 (slightly above mid), penalize extremes
            # 0.0 = 52-week low (battered), 1.0 = 52-week high (chasing)
            r["_pre_rank"] = max(0, 1.0 - abs(pos - 0.55) * 2.0)
        else:
            r["_pre_rank"] = 0.5

    passed.sort(key=lambda x: x["_pre_rank"], reverse=True)

    _STAGE_B_SIZE = max(top_n * 3, 80)
    shortlist = passed[:_STAGE_B_SIZE]
    logger.info(f"Stage A pre-rank: top {len(shortlist)} of {len(passed)} sent to Stage B")

    # ------------------------------------------------------------------
    # Stage B: Financial data + K-line fetch + quality gate
    # ------------------------------------------------------------------

    fin_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(get_financial_data, r["ticker"], r["market"]): r for r in shortlist}
        for fut in as_completed(futs):
            r = futs[fut]
            try:
                fin = fut.result()
            except Exception:
                fin = None
            r["financial"] = fin
            fin_rows.append(r)

    # Quality gate: reject garbage (not a scoring factor)
    # - Negative earnings + negative FCF + negative revenue growth = likely dying company
    # - PB > 15 = extreme valuation risk
    # - PE is NOT a hard filter anymore; it's only a soft quality factor
    filtered: list[dict] = []
    for r in fin_rows:
        fin = r.get("financial")
        if fin:
            pb = _safe_float(fin.get("pb"))
            if pb > 0 and pb > sc.max_pb:
                continue
            # Garbage gate: reject if ALL three are bad simultaneously
            roe = fin.get("roe")
            fcf = fin.get("free_cashflow") or fin.get("free_cash_flow")
            rev_g = fin.get("revenue_growth")
            if (roe is not None and roe < -0.10
                    and fcf is not None and fcf < 0
                    and rev_g is not None and rev_g < -0.10):
                logger.debug(f"Quality gate reject {r['ticker']}: ROE={roe}, FCF<0, RevG={rev_g}")
                continue
        filtered.append(r)

    if not filtered:
        logger.info(f"No symbols passed quality gate for {market}")
        return []

    logger.info(f"Stage B quality gate: {len(shortlist)} -> {len(filtered)}")

    # Fetch 80-day K-lines
    kline_map = batch_fetch_klines(
        [{"ticker": r["ticker"], "market": r["market"]} for r in filtered],
        days=80,
    )
    global _layer1_kline_cache
    _layer1_kline_cache = kline_map

    bench_ret = _fetch_benchmark_return(market, days=60)
    logger.info(f"Benchmark 60d return: {bench_ret:+.2%}")

    # ------------------------------------------------------------------
    # Trend pre-filter: reject confirmed deep downtrends
    # (relaxed vs old: only reject if >10% below MA50, not 8%)
    # ------------------------------------------------------------------
    trend_filtered: list[dict] = []
    for r in filtered:
        kdf = kline_map.get(r["ticker"], pd.DataFrame())
        if kdf is not None and not kdf.empty and len(kdf) >= 20:
            closes = kdf["close"].tolist()
            price = float(r["quote"]["price"])
            ma20 = sum(closes[-20:]) / 20
            ma50 = sum(closes[-min(50, len(closes)):]) / min(50, len(closes))
            if price < ma20 < ma50 and price < ma50 * 0.90:
                logger.debug(
                    f"Trend reject {r['ticker']}: "
                    f"price={price:.2f} < MA20={ma20:.2f} < MA50={ma50:.2f} (>10% below)"
                )
                continue
        trend_filtered.append(r)

    logger.info(
        f"Trend filter: {len(filtered)} -> {len(trend_filtered)} "
        f"(rejected {len(filtered) - len(trend_filtered)} deep downtrends)"
    )
    if not trend_filtered:
        logger.warning("Trend filter removed all candidates, falling back")
        trend_filtered = filtered

    # ------------------------------------------------------------------
    # Multi-factor ranking (v4: short-term trading optimized)
    # ------------------------------------------------------------------
    # Factor 1: Acceleration (30%) — is momentum increasing?
    # Factor 2: Volume Anomaly (25%) — unusual volume surge
    # Factor 3: Trend Setup (30%) — MA structure + pullback quality
    # Factor 4: Volatility Fit (15%) — optimal vol range for trading
    # ------------------------------------------------------------------

    raw_accel: list[float] = []
    raw_volume: list[float] = []
    raw_setup: list[float] = []
    raw_volfit: list[float] = []
    raw_fundamental: list[float] = []
    raw_quality_bonus: list[float] = []

    for r in trend_filtered:
        q = r["quote"]
        price = float(q["price"])
        kdf = kline_map.get(r["ticker"], pd.DataFrame())
        fin = r.get("financial") or {}

        if kdf is not None and not kdf.empty and len(kdf) >= 10:
            closes = kdf["close"].tolist()
            volumes = kdf["volume"].tolist() if "volume" in kdf.columns else []
        else:
            closes = []
            volumes = []

        # --- Factor 1: Acceleration (beta-adjusted, not absolute momentum) ---
        if len(closes) >= 20:
            ret_5d = (price / closes[-5]) - 1.0 if closes[-5] > 0 else 0.0
            ret_20d = (price / closes[-20]) - 1.0 if closes[-20] > 0 else 0.0
            # Normalize to same time period: 5d rate * 4 ≈ 20d rate
            accel = (ret_5d * 4.0) - ret_20d  # positive = accelerating
            # Beta-adjusted benchmark: implied beta from 20d returns
            if abs(bench_ret) > 0.005:
                implied_beta = ret_20d / bench_ret
                implied_beta = max(0.5, min(2.5, implied_beta))
            else:
                implied_beta = 1.0
            accel -= implied_beta * bench_ret * (5 / 20)
            accel = max(-0.5, min(0.5, accel))
        elif len(closes) >= 5:
            ret_5d = (price / closes[-5]) - 1.0 if closes[-5] > 0 else 0.0
            accel = ret_5d - bench_ret * 0.1
            accel = max(-0.3, min(0.3, accel))
        else:
            accel = 0.0
        raw_accel.append(accel)

        # --- Factor 2: Volume Anomaly ---
        # How much is recent volume above the 20-day average?
        if len(volumes) >= 20:
            vol_5d_avg = sum(volumes[-5:]) / 5.0 if sum(volumes[-5:]) > 0 else 1.0
            vol_20d_avg = sum(volumes[-20:]) / 20.0 if sum(volumes[-20:]) > 0 else 1.0
            vol_ratio = vol_5d_avg / max(vol_20d_avg, 1.0)
            # Also check today's volume vs average
            today_vol = float(q.get("volume") or 0)
            today_ratio = today_vol / max(vol_20d_avg, 1.0) if today_vol > 0 else 1.0
            # Combine: 60% recent trend + 40% today spike
            vol_anomaly = 0.6 * min(vol_ratio, 4.0) + 0.4 * min(today_ratio, 5.0)
            # Normalize: 1.0 = normal, 2.0+ = interesting, 3.0+ = very unusual
            vol_anomaly = max(0.0, (vol_anomaly - 0.8) / 3.0)  # maps [0.8, 3.8] -> [0, 1]
        else:
            vol_anomaly = 0.3  # neutral
        raw_volume.append(vol_anomaly)

        # --- Factor 3: Trend Setup (structure + pullback quality) ---
        # Best setup: uptrend (MA aligned) + price pulled back to MA20 zone
        # This finds "ready to bounce" not "already bounced"
        if len(closes) >= 20:
            ma5 = sum(closes[-5:]) / 5
            ma10 = sum(closes[-10:]) / 10
            ma20 = sum(closes[-20:]) / 20
            ma50 = sum(closes[-min(50, len(closes)):]) / min(50, len(closes))

            setup = 0.0

            # MA alignment (structure, not direction scoring)
            if ma5 > ma10 > ma20:
                setup += 0.25  # bullish alignment
            elif ma5 > ma20:
                setup += 0.15  # partial alignment
            if ma20 > ma50:
                setup += 0.15  # longer-term uptrend intact

            # Pullback quality: how close is price to MA20?
            # Best: within 2% of MA20 in uptrend (entry opportunity)
            if ma20 > 0:
                bias = (price - ma20) / ma20
                if 0 <= bias <= 0.02:
                    setup += 0.30  # sitting right on MA20 support = ideal
                elif 0.02 < bias <= 0.05:
                    setup += 0.20  # slightly above, still good
                elif -0.03 <= bias < 0:
                    setup += 0.25  # just pulled back below MA20 = buying opp
                elif bias > 0.10:
                    setup += 0.0   # too far above = extended, no bonus
                elif bias < -0.05:
                    setup -= 0.10  # too far below = trend may be breaking

            # Support: price above MA50 = safety net
            if price > ma50:
                setup += 0.10

            # Recent consolidation: low range in last 5 days = coiled spring
            if len(closes) >= 5:
                recent = closes[-5:]
                hl_range = (max(recent) - min(recent)) / max(min(recent), 0.01)
                if hl_range < 0.03:
                    setup += 0.10  # tight consolidation = potential breakout

            setup = max(0.0, min(1.0, setup))
        else:
            setup = 0.3
        raw_setup.append(setup)

        # --- Factor 4: Volatility Fit ---
        # Short-term trading needs MODERATE volatility (1-3% daily).
        # Too low (<0.5%): can't reach 8% TP in 3 days
        # Too high (>4%): too likely to hit 5% SL
        # Optimal: 1.5-2.5% daily average
        if len(closes) >= 10:
            daily_rets = []
            for i in range(1, len(closes)):
                if closes[i - 1] > 0:
                    daily_rets.append(abs((closes[i] - closes[i - 1]) / closes[i - 1]))
            avg_vol = sum(daily_rets) / len(daily_rets) if daily_rets else 0.02

            # Bell curve: peak at blended optimal vol (short + swing)
            optimal_vol = (sc.optimal_vol_short + sc.optimal_vol_swing) / 2
            vol_width = sc.optimal_vol_width
            vol_distance = abs(avg_vol - optimal_vol)
            vol_fit = max(0.0, 1.0 - (vol_distance / vol_width))
        else:
            vol_fit = 0.5
        raw_volfit.append(vol_fit)

        # --- Factor 5: Fundamental quality ---
        fund_score = _compute_fundamental_score(r) / 100.0
        raw_fundamental.append(fund_score)

        # --- Absolute quality bonus/penalty (not normalized) ---
        quality_bonus = 0.0
        if accel > 0.05:
            quality_bonus += 5
        if vol_anomaly > 0.5:
            quality_bonus += 3
        if setup > 0.6:
            quality_bonus += 5
        if vol_fit > 0.7:
            quality_bonus += 2
        if accel < -0.05:
            quality_bonus -= 5
        if setup < 0.2:
            quality_bonus -= 5
        raw_quality_bonus.append(quality_bonus)
    n_accel = _norm_series(raw_accel, higher_is_better=True)
    n_volume = _norm_series(raw_volume, higher_is_better=True)
    n_setup = _norm_series(raw_setup, higher_is_better=True)
    n_volfit = _norm_series(raw_volfit, higher_is_better=True)
    n_fundamental = _norm_series(raw_fundamental, higher_is_better=True)

    w_accel = sc.weight_acceleration
    w_volume = sc.weight_volume_anomaly
    w_setup = sc.weight_trend_setup
    w_volfit = sc.weight_volatility_fit
    w_fund = sc.weight_fundamental

    results: list[dict] = []
    for i, r in enumerate(trend_filtered):
        q = r["quote"]
        fin = r.get("financial") or {}
        comp = (w_accel * n_accel[i] + w_volume * n_volume[i] +
                w_setup * n_setup[i] + w_volfit * n_volfit[i] +
                w_fund * n_fundamental[i]) * 100.0
        comp += raw_quality_bonus[i]  # absolute bonus, not normalized
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
            # Factor breakdown for transparency
            "factors": {
                "acceleration": round(n_accel[i], 3),
                "volume_anomaly": round(n_volume[i], 3),
                "trend_setup": round(n_setup[i], 3),
                "volatility_fit": round(n_volfit[i], 3),
                "fundamental": round(n_fundamental[i], 3),
                "quality_bonus": round(raw_quality_bonus[i], 1),
            },
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    # Absolute quality gate: reject candidates below minimum score
    # In weak markets, this means fewer or zero recommendations — by design
    pre_gate_count = len(results)
    results = [r for r in results if r["score"] >= sc.min_absolute_score]
    if pre_gate_count > len(results):
        logger.info(
            f"Absolute score gate: {pre_gate_count} -> {len(results)} "
            f"(rejected {pre_gate_count - len(results)} below {sc.min_absolute_score})"
        )

    # ------------------------------------------------------------------
    # Sector diversification — sector -> industry fallback
    # ------------------------------------------------------------------
    max_per_sector = max(top_n // 3, 5)
    sector_count: dict[str, int] = {}
    diversified: list[dict] = []
    overflow: list[dict] = []
    for r in results:
        fin_data = r.get("financial") or {}
        sec = fin_data.get("sector", "") or fin_data.get("industry", "") or ""
        sec = sec.strip()
        if not sec:
            sec = "_Unclassified"
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
        f"Layer 1 final: {len(trend_filtered)} -> {len(diversified)} candidates "
        f"(sectors: {len(sector_count)}, max/sector: {max_per_sector})"
    )
    return diversified


# Module-level cache for Layer 1 K-line data (reused by Layer 2)
_layer1_kline_cache: dict[str, pd.DataFrame] = {}


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


def _continuous_score(value: float | None, breakpoints: list[float], scores: list[float]) -> float:
    """Piecewise linear interpolation for continuous scoring.

    Maps a value to a score using linear interpolation between breakpoints.
    Example: _continuous_score(0.18, [-0.10, 0, 0.15, 0.40], [-15, 0, 8, 18]) → ~9.6
    """
    if value is None:
        return 0.0
    if len(breakpoints) != len(scores) or len(breakpoints) < 2:
        return 0.0
    if value <= breakpoints[0]:
        return scores[0]
    if value >= breakpoints[-1]:
        return scores[-1]
    for i in range(len(breakpoints) - 1):
        if breakpoints[i] <= value <= breakpoints[i + 1]:
            t = (value - breakpoints[i]) / (breakpoints[i + 1] - breakpoints[i])
            return scores[i] + t * (scores[i + 1] - scores[i])
    return scores[-1]


def _compute_fundamental_score(candidate: dict) -> float:
    """Continuous fundamental scoring — magnitude-aware, not step functions.

    Returns 0-100 score. 50 = neutral baseline.
    Uses piecewise linear interpolation so ROE 40% scores higher than ROE 21%.
    """
    score = 50.0
    fin = candidate.get("financial") or {}

    # ROE: negative penalized, high rewarded proportionally
    roe = fin.get("roe")
    score += _continuous_score(roe,
        [-0.10, -0.02, 0, 0.08, 0.15, 0.20, 0.40],
        [-15,   -5,    0, 3,    8,    12,   18])

    # Revenue growth: contraction penalized, high growth rewarded
    rev_growth = fin.get("revenue_growth")
    score += _continuous_score(rev_growth,
        [-0.20, -0.10, 0, 0.10, 0.20, 0.50],
        [-12,   -8,    0, 4,    8,    14])

    # Debt to equity: high leverage penalized
    de = fin.get("debt_to_equity")
    score += _continuous_score(de,
        [0, 0.3, 0.5, 1.0, 2.0, 3.0, 5.0],
        [6, 5,   3,   0,   -4,  -8,  -14])

    # Current ratio: below 1.0 is dangerous
    cr = fin.get("current_ratio")
    score += _continuous_score(cr,
        [0.5, 1.0, 1.5, 2.0, 3.0],
        [-10, -4,  0,   4,   5])

    # Profit margin: negative = burning cash
    margin = fin.get("profit_margins") or fin.get("profit_margin")
    score += _continuous_score(margin,
        [-0.10, 0, 0.05, 0.10, 0.20, 0.35],
        [-12,   -3, 0,   3,    6,    10])

    # Free cash flow — binary signal but scaled by FCF yield
    fcf = fin.get("free_cash_flow") or fin.get("free_cashflow")
    market_cap_val = (candidate.get("quote") or {}).get("market_cap") or candidate.get("market_cap") or 0
    if fcf is not None and market_cap_val and market_cap_val > 0:
        fcf_yield = fcf / market_cap_val
        score += _continuous_score(fcf_yield,
            [-0.05, -0.02, 0, 0.02, 0.05, 0.08, 0.12],
            [-8,    -4,    0, 2,    5,    8,    10])
    elif fcf is not None:
        score += 4 if fcf > 0 else -6

    # PEG ratio
    pe_val = fin.get("pe_ttm")
    eg = fin.get("earnings_growth")
    if pe_val is not None and eg is not None and eg > 0:
        peg = pe_val / (eg * 100) if eg < 1 else pe_val / eg
        score += _continuous_score(peg,
            [0.5, 1.0, 1.5, 2.0, 3.0, 5.0],
            [10,  8,   4,   0,   -3,  -6])

    # Revenue acceleration: earnings growing faster than revenue = operating leverage
    earn_g = fin.get("earnings_growth")
    if rev_growth is not None and earn_g is not None:
        if rev_growth > 0.10 and earn_g > rev_growth:
            score += 6
        elif rev_growth > 0.10 and earn_g > 0:
            score += 3
        elif rev_growth < 0 and earn_g < 0:
            score -= 6

    # Short interest
    short_pct = fin.get("short_pct_of_float")
    score += _continuous_score(short_pct,
        [0, 0.05, 0.10, 0.20, 0.30],
        [0, 0,    -2,   -5,   -8])

    # Insider ownership (alignment of interests)
    insider_pct = fin.get("held_pct_insiders")
    score += _continuous_score(insider_pct,
        [0, 0.05, 0.10, 0.30, 0.50],
        [0, 1,    3,    5,    6])

    # Institutional ownership
    inst_pct = fin.get("held_pct_institutions")
    score += _continuous_score(inst_pct,
        [0.10, 0.30, 0.50, 0.80, 0.95],
        [-4,   -1,   1,    3,    2])

    # Insider trading activity signal
    insider_trades = candidate.get("insider_trades")
    if insider_trades and isinstance(insider_trades, dict):
        sig = insider_trades.get("signal_strength", "")
        if sig == "strong_buy":
            score += 10
        elif sig == "moderate_buy":
            score += 5
        elif sig == "strong_sell":
            score -= 8
        elif sig == "moderate_sell":
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
    insider_map: dict[str, dict | None] = {}
    options_map: dict[str, dict[str, Any] | None] = {}
    n = len(candidates)
    max_workers = min(12, max(4, (n * 3) // 4)) if n else 4
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs: dict[Any, tuple[str, str]] = {}
        for c in candidates:
            t = c["ticker"]
            m = c.get("market", "us_stock")
            futs[ex.submit(_check_earnings_proximity, t, m)] = ("earnings", t)
            futs[ex.submit(get_insider_trades, t, m)] = ("insider", t)
            futs[ex.submit(get_options_signal, t, m)] = ("options", t)
        for fut in as_completed(futs):
            kind, ticker = futs[fut]
            try:
                res = fut.result()
            except Exception:
                res = None
            if kind == "earnings":
                if res is None:
                    earnings_map[ticker] = {"days_away": None, "date_str": None, "imminent": False}
                else:
                    earnings_map[ticker] = res
            elif kind == "insider":
                insider_map[ticker] = res
            else:
                options_map[ticker] = res

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

        insider_trades = insider_map.get(ticker)
        c_for_fundamental = {**c, "insider_trades": insider_trades}
        fundamental_score = _compute_fundamental_score(c_for_fundamental)
        earnings_info = earnings_map.get(ticker, {"days_away": None, "date_str": None, "imminent": False})
        opt_info = options_map.get(ticker)
        if opt_info:
            options_signal_str = opt_info.get("signal", "unavailable")
            options_pc_ratio_val = opt_info.get("pc_ratio_volume")
            options_unusual = bool(
                opt_info.get("unusual_call_activity") or opt_info.get("unusual_put_activity")
            )
        else:
            options_signal_str = "unavailable"
            options_pc_ratio_val = None
            options_unusual = False

        enriched.append({
            "ticker": ticker,
            "name": c.get("name", ticker),
            "market": market,
            "price": price,
            "fundamental_score": fundamental_score,
            "insider_trades": insider_trades,
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
            "options_signal": options_signal_str,
            "options_pc_ratio": options_pc_ratio_val,
            "options_unusual_activity": options_unusual,
        })

    logger.info(f"Layer 2 enrichment: {len(enriched)} candidates with technical data")
    return enriched
