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
# v12: Sector rotation detection
# ---------------------------------------------------------------------------

_SECTOR_ETF_MAP = {
    "XLK": "Technology",
    "XLF": "Financial Services",
    "XLE": "Energy",
    "XLV": "Healthcare",
    "XLI": "Industrials",
    "XLY": "Consumer Cyclical",
    "XLP": "Consumer Defensive",
    "XLC": "Communication Services",
    "XLRE": "Real Estate",
    "XLB": "Basic Materials",
    "XLU": "Utilities",
}

_sector_rotation_cache: dict[str, float] | None = None


def _compute_sector_rotation(lookback_days: int = 5) -> dict[str, float]:
    """Compute sector relative strength vs SPY over the lookback window.

    Returns dict mapping sector name to excess return (e.g., +0.023 = 2.3% above SPY).
    Cached per screening run.
    """
    global _sector_rotation_cache
    if _sector_rotation_cache is not None:
        return _sector_rotation_cache

    import yfinance as yf

    result: dict[str, float] = {}
    try:
        tickers = list(_SECTOR_ETF_MAP.keys()) + ["SPY"]
        data = yf.download(tickers, period=f"{lookback_days + 5}d", progress=False)
        if data.empty or "Close" not in data.columns.get_level_values(0):
            logger.debug("Sector rotation: download failed or empty")
            _sector_rotation_cache = {}
            return {}

        closes = data["Close"]
        if isinstance(closes, pd.Series):
            _sector_rotation_cache = {}
            return {}

        spy_ret = 0.0
        if "SPY" in closes.columns and len(closes) >= 2:
            spy_first = closes["SPY"].dropna().iloc[0]
            spy_last = closes["SPY"].dropna().iloc[-1]
            spy_ret = (spy_last - spy_first) / spy_first if spy_first > 0 else 0.0

        for etf, sector in _SECTOR_ETF_MAP.items():
            if etf in closes.columns:
                col = closes[etf].dropna()
                if len(col) >= 2:
                    first = col.iloc[0]
                    last = col.iloc[-1]
                    ret = (last - first) / first if first > 0 else 0.0
                    result[sector] = round(ret - spy_ret, 4)

        logger.info(
            f"Sector rotation ({lookback_days}d): "
            f"top={max(result, key=result.get) if result else 'N/A'} "
            f"bottom={min(result, key=result.get) if result else 'N/A'}"
        )
    except Exception as e:
        logger.warning(f"Sector rotation computation failed: {e}")

    _sector_rotation_cache = result
    return result


# ---------------------------------------------------------------------------
# Stock pool loading
# ---------------------------------------------------------------------------

def _load_pool_file(market: str, pool_type: str = "default") -> list[dict] | None:
    if pool_type == "short_term":
        candidates = [
            _package_root() / "data" / "short_term_pool.json",
            Path.cwd() / "data" / "short_term_pool.json",
        ]
    else:
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

    US -> SPY, HK -> ^HSI.  Returns 0.0 on failure (graceful degradation).
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


def run_screening(market: str = "us_stock", top_n: int = 40, pool_type: str = "default") -> list[dict]:
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

    # v12: Clear sector rotation cache at each run to avoid stale data
    global _sector_rotation_cache
    _sector_rotation_cache = None

    pool = _load_pool_file(market, pool_type=pool_type)
    if not pool:
        pool = _pool_from_indices(market)
    if not pool:
        logger.warning(f"No stock pool for {market}")
        return []

    # --- v3.x Cooldown filter: remove tickers still in cooldown ---
    try:
        from core.database import Database
        from core.user import SYSTEM_DB_PATH
        from datetime import datetime as _dt
        _today = _dt.now().strftime("%Y%m%d")
        _cd_db = Database(SYSTEM_DB_PATH)
        cooldown_set = _cd_db.get_active_cooldown_tickers(market, _today)
        _cd_db.close()
        if cooldown_set:
            _before = len(pool)
            pool = [r for r in pool if r["ticker"] not in cooldown_set]
            logger.info(f"Cooldown filter: {_before} -> {len(pool)} "
                        f"(removed {_before - len(pool)} in cooldown)")
    except Exception as e:
        logger.debug(f"Cooldown filter skipped: {e}")

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
    reversal_candidates: list[dict] = []   # v10: stocks down >= |reversal_trigger|%
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
        # v10 asymmetric daily-change filter:
        # - Reject if moved too far in EITHER direction (extreme volatility day)
        # - Reject if already up > max_upside_today_pct (chasing kills R:R)
        # - If down past reversal_trigger, flag for reversal branch instead
        if abs(change_pct) > sc.max_daily_change_pct:
            continue
        if change_pct > sc.max_upside_today_pct:
            logger.debug(f"Upside reject {t}: today +{change_pct:.1f}% > {sc.max_upside_today_pct:.1f}%")
            continue
        _is_reversal_candidate = change_pct <= sc.reversal_trigger_pct

        # --- Liquidity gates (avoid "dead money" large-caps like BEN) ---
        # Dollar volume: shares * price - filters low-price large-cap with no trading
        dollar_volume = volume * price
        if dollar_volume < sc.min_dollar_volume:
            logger.debug(
                f"Liquidity reject {t}: dollar_vol=${dollar_volume/1e6:.0f}M "
                f"< ${sc.min_dollar_volume/1e6:.0f}M (vol={volume:.0f}, price={price:.2f})"
            )
            continue
        # Turnover ratio: dollar_volume / market_cap - filters stale stocks
        # Tiered thresholds: mega-caps (>$500B) are exempt if dollar_volume
        # is sufficient, because their turnover is structurally low due to
        # enormous market cap, not lack of liquidity.
        if mc > 0:
            turnover = dollar_volume / mc
            if mc >= 5e11:
                _min_to = 0  # mega-cap: exempt, dollar_volume gate is enough
            elif mc >= 5e10:
                _min_to = sc.min_turnover_ratio * 0.33  # large-cap: ~0.1%
            else:
                _min_to = sc.min_turnover_ratio  # mid/small-cap: full 0.3%
            if _min_to > 0 and turnover < _min_to:
                logger.debug(
                    f"Turnover reject {t}: turnover={turnover:.4f} "
                    f"< {_min_to:.4f} (dv=${dollar_volume/1e6:.0f}M, mc=${mc/1e9:.1f}B)"
                )
                continue
        # Note: PE hard filter REMOVED - high-growth stocks (NVDA, TSLA)
        # often have PE > 80. Quality gate in Stage B handles garbage.

        # v10: resolve tier - prefer pool metadata (from pool_builder), else
        # compute from live market cap.
        tier = row.get("tier") if row.get("tier") in ("large", "mid", "small") else None
        if tier is None:
            if mc >= 5.0e10:
                tier = "large"
            elif mc >= 1.0e10:
                tier = "mid"
            else:
                tier = "small"

        entry = {
            **row, "quote": q, "financial": None,
            "dollar_volume": dollar_volume, "tier": tier,
            "_reversal": _is_reversal_candidate,
        }
        if _is_reversal_candidate:
            reversal_candidates.append(entry)
        passed.append(entry)

    logger.info(
        f"Stage A hard filter: {len(pool)} -> {len(passed)} passed (market={market}); "
        f"{len(reversal_candidates)} flagged as reversal candidates"
    )

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
    # 20-day average dollar volume filter (precise, uses K-line history)
    # Stage A used a snapshot; this uses 20-day average for stability.
    # ------------------------------------------------------------------
    liquidity_filtered: list[dict] = []
    for r in filtered:
        kdf = kline_map.get(r["ticker"], pd.DataFrame())
        if kdf is not None and not kdf.empty and len(kdf) >= 20 and "volume" in kdf.columns:
            avg_vol_20 = float(kdf["volume"].tail(20).mean())
            price = float(r["quote"]["price"])
            avg_dv_20 = avg_vol_20 * price
            if avg_dv_20 < sc.min_avg_dollar_volume_20d:
                logger.debug(
                    f"20d liquidity reject {r['ticker']}: "
                    f"avg_dv=${avg_dv_20/1e6:.0f}M < ${sc.min_avg_dollar_volume_20d/1e6:.0f}M"
                )
                continue
        liquidity_filtered.append(r)

    if len(liquidity_filtered) < len(filtered):
        logger.info(
            f"20d liquidity filter: {len(filtered)} -> {len(liquidity_filtered)} "
            f"(rejected {len(filtered) - len(liquidity_filtered)} illiquid stocks)"
        )
    filtered = liquidity_filtered

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
    # Factor 1: Acceleration (30%) - is momentum increasing?
    # Factor 2: Volume Anomaly (25%) - unusual volume surge
    # Factor 3: Trend Setup (30%) - MA structure + pullback quality
    # Factor 4: Volatility Fit (15%) - optimal vol range for trading
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

        # --- Factor 1: Relative Strength vs benchmark (v12) ---
        # Replaces absolute momentum with excess return over SPY/HSI.
        # _norm_series maps raw RS to percentile within peer group.
        if len(closes) >= 20:
            ret_20d = (price / closes[-5]) - 1.0 if closes[-5] > 0 else 0.0
            ret_20d_full = (price / closes[-20]) - 1.0 if closes[-20] > 0 else 0.0
            # Relative strength = excess return over benchmark
            rs_raw = ret_20d_full - bench_ret
            # Also factor in short-term acceleration
            ret_5d = (price / closes[-5]) - 1.0 if closes[-5] > 0 else 0.0
            short_accel = ret_5d * 4.0 - ret_20d_full  # 5d annualized vs 20d
            # Blend: 70% RS + 30% short-term acceleration
            accel = 0.7 * rs_raw + 0.3 * max(-0.3, min(0.3, short_accel))
            accel = max(-0.5, min(0.5, accel))
        elif len(closes) >= 5:
            ret_5d = (price / closes[-5]) - 1.0 if closes[-5] > 0 else 0.0
            accel = ret_5d - bench_ret * 0.25
            accel = max(-0.3, min(0.3, accel))
        else:
            accel = 0.0
        raw_accel.append(accel)

        # --- Factor 2: Directional Volume Anomaly (v12) ---
        # Distinguishes up-volume from down-volume. High volume on up days
        # is bullish; high volume on down days is bearish (distribution).
        if len(closes) >= 20 and len(volumes) >= 20:
            # Classify each day's volume as "up" or "down" based on close-to-close
            up_vol_5d = 0.0
            dn_vol_5d = 0.0
            for _vi in range(-5, 0):
                if closes[_vi] > closes[_vi - 1]:
                    up_vol_5d += volumes[_vi]
                else:
                    dn_vol_5d += volumes[_vi]

            up_vol_20d = 0.0
            dn_vol_20d = 0.0
            for _vi in range(-20, 0):
                if closes[_vi] > closes[_vi - 1]:
                    up_vol_20d += volumes[_vi]
                else:
                    dn_vol_20d += volumes[_vi]

            # Compute up-volume expansion ratio and down-volume expansion ratio
            up_avg_5 = up_vol_5d / 5.0 if up_vol_5d > 0 else 0
            up_avg_20 = up_vol_20d / 20.0 if up_vol_20d > 0 else 1
            dn_avg_5 = dn_vol_5d / 5.0 if dn_vol_5d > 0 else 0
            dn_avg_20 = dn_vol_20d / 20.0 if dn_vol_20d > 0 else 1

            up_ratio = up_avg_5 / max(up_avg_20, 1) if up_avg_20 > 0 else 1.0
            dn_ratio = dn_avg_5 / max(dn_avg_20, 1) if dn_avg_20 > 0 else 1.0

            # Net directional score: up-volume expansion good, down-volume bad
            # up_ratio=2.0 means up-days have 2x normal volume (accumulation)
            # dn_ratio=2.0 means down-days have 2x normal volume (distribution)
            vol_anomaly = max(0.0, min(1.0,
                (min(up_ratio, 4.0) - min(dn_ratio, 4.0) * 0.5 + 0.5) / 2.5
            ))
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
        # Short-term trading needs MODERATE volatility. Optimal range differs
        # by market-cap tier: mega-cap "exciting" move is 1.8%, small-cap is 4.5%.
        # v10: per-tier optimal_vol when tiers enabled, else legacy flat config.
        if len(closes) >= 10:
            daily_rets = []
            for i in range(1, len(closes)):
                if closes[i - 1] > 0:
                    daily_rets.append(abs((closes[i] - closes[i - 1]) / closes[i - 1]))
            avg_vol = sum(daily_rets) / len(daily_rets) if daily_rets else 0.02

            if cfg.tiers.enabled:
                tcfg = cfg.tiers.get(r.get("tier", "mid"))
                optimal_vol = (tcfg.optimal_vol_short + tcfg.optimal_vol_swing) / 2
            else:
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

    w_accel = sc.weight_acceleration
    w_volume = sc.weight_volume_anomaly
    w_setup = sc.weight_trend_setup
    w_volfit = sc.weight_volatility_fit
    w_fund = sc.weight_fundamental

    # v12: Sector rotation signal
    _sector_rot = _compute_sector_rotation() if cfg.raw.get("pipeline", {}).get("sector_rotation", {}).get("enabled", False) else {}
    _rot_bonus = float(cfg.raw.get("pipeline", {}).get("sector_rotation", {}).get("bonus_pct", 0.08)) * 100
    _rot_penalty = float(cfg.raw.get("pipeline", {}).get("sector_rotation", {}).get("penalty_pct", -0.05)) * 100

    def _score_group(indices: list[int]) -> list[dict]:
        """Normalize factor values within a group and build result dicts."""
        if not indices:
            return []
        s_a = _norm_series([raw_accel[i] for i in indices], higher_is_better=True)
        s_v = _norm_series([raw_volume[i] for i in indices], higher_is_better=True)
        s_s = _norm_series([raw_setup[i] for i in indices], higher_is_better=True)
        s_vf = _norm_series([raw_volfit[i] for i in indices], higher_is_better=True)
        s_fu = _norm_series([raw_fundamental[i] for i in indices], higher_is_better=True)
        out: list[dict] = []
        for local_i, global_i in enumerate(indices):
            r = trend_filtered[global_i]
            q = r["quote"]
            fin = r.get("financial") or {}
            comp = (w_accel * s_a[local_i] + w_volume * s_v[local_i] +
                    w_setup * s_s[local_i] + w_volfit * s_vf[local_i] +
                    w_fund * s_fu[local_i]) * 100.0
            comp += raw_quality_bonus[global_i]

            # v12: Sector rotation bonus/penalty
            _sr_adj = 0.0
            _stock_sector = (fin.get("sector") or "").strip()
            if _sector_rot and _stock_sector:
                _sr_val = _sector_rot.get(_stock_sector, 0.0)
                if _sr_val > 0.01:   # sector outperforming SPY by >1%
                    _sr_adj = _rot_bonus
                elif _sr_val < -0.01:  # sector underperforming SPY by >1%
                    _sr_adj = _rot_penalty
                comp += _sr_adj

            out.append({
                "ticker": r["ticker"],
                "name": r.get("name", r["ticker"]),
                "market": r["market"],
                "tier": r.get("tier", "mid"),
                "reversal_candidate": bool(r.get("_reversal", False)),
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
                "factors": {
                    "acceleration": round(s_a[local_i], 3),
                    "volume_anomaly": round(s_v[local_i], 3),
                    "trend_setup": round(s_s[local_i], 3),
                    "volatility_fit": round(s_vf[local_i], 3),
                    "fundamental": round(s_fu[local_i], 3),
                    "quality_bonus": round(raw_quality_bonus[global_i], 1),
                    "sector_rotation": round(_sr_adj, 1),
                },
                # v12: pass premarket data through
                "premarket_price": q.get("premarket_price"),
                "premarket_change_pct": q.get("premarket_change_pct", 0.0),
                "premarket_volume": q.get("premarket_volume", 0),
            })
        return out

    # v10: tier-aware path - normalize within each tier, apply per-tier quotas.
    if cfg.tiers.enabled:
        tier_idx: dict[str, list[int]] = {"large": [], "mid": [], "small": []}
        for i, r in enumerate(trend_filtered):
            t = r.get("tier")
            if t not in tier_idx:
                t = "mid"
            tier_idx[t].append(i)

        merged: list[dict] = []
        summary_parts: list[str] = []
        for tier_name in ("large", "mid", "small"):
            idx_list = tier_idx.get(tier_name, [])
            tier_results = _score_group(idx_list)
            tier_results.sort(key=lambda x: x["score"], reverse=True)
            pre_gate = len(tier_results)
            tier_results = [r for r in tier_results if r["score"] >= sc.min_absolute_score]

            tcfg = cfg.tiers.get(tier_name)
            quota = max(0, int(tcfg.candidate_quota))
            selected = tier_results[:quota]
            merged.extend(selected)
            summary_parts.append(
                f"{tier_name}={len(selected)}/{quota} "
                f"(gated {len(tier_results)}/{pre_gate} of {len(idx_list)})"
            )

        results = merged
        results.sort(key=lambda x: x["score"], reverse=True)
        logger.info("Tier-aware selection: " + ", ".join(summary_parts))
    else:
        # Legacy: single global normalization
        results = _score_group(list(range(len(trend_filtered))))
        results.sort(key=lambda x: x["score"], reverse=True)

    # v10: tier-aware path has already applied the absolute-score gate per
    # tier. Legacy path applies it globally here.
    if not cfg.tiers.enabled:
        pre_gate_count = len(results)
        results = [r for r in results if r["score"] >= sc.min_absolute_score]
        if pre_gate_count > len(results):
            logger.info(
                f"Absolute score gate: {pre_gate_count} -> {len(results)} "
                f"(rejected {pre_gate_count - len(results)} below {sc.min_absolute_score})"
            )

    # ------------------------------------------------------------------
    # Sector diversification: sector -> industry fallback.
    # When tiers are enabled and per-tier quotas already fit within top_n,
    # we skip the sector trim (each tier is small enough that concentration
    # risk is contained within that tier's 2-3 slots).
    # ------------------------------------------------------------------
    if cfg.tiers.enabled and len(results) <= max(top_n, 1):
        logger.info(
            f"Layer 1 final: {len(trend_filtered)} -> {len(results)} candidates "
            f"(tiers.enabled=True, top_n={top_n}, sector trim skipped)"
        )
        return results

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
        f"(sectors: {len(sector_count)}, max/sector: {max_per_sector}, "
        f"tiers.enabled={cfg.tiers.enabled})"
    )
    return diversified


# Module-level cache for Layer 1 K-line data (reused by Layer 2)
_layer1_kline_cache: dict[str, pd.DataFrame] = {}


# ---------------------------------------------------------------------------
# Layer 2: Technical data enrichment
# ---------------------------------------------------------------------------

def _compute_adv_20d(kdf: pd.DataFrame) -> float:
    """Compute 20-day average daily dollar volume from K-line data."""
    if kdf is None or kdf.empty or len(kdf) < 5:
        return 0.0
    try:
        tail = kdf.tail(20)
        dollar_vols = tail["close"].values * tail["volume"].values
        return float(dollar_vols.mean())
    except Exception:
        return 0.0


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
    Example: _continuous_score(0.18, [-0.10, 0, 0.15, 0.40], [-15, 0, 8, 18]) -> ~9.6
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
    """Continuous fundamental scoring - magnitude-aware, not step functions.

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

    # Free cash flow - binary signal but scaled by FCF yield
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

            recent_klines = kdf.tail(60)
            n_recent = len(recent_klines)
            split_point = max(n_recent - 30, 0)
            part1_df = recent_klines.iloc[:split_point]
            part2_df = recent_klines.iloc[split_point:]

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
            options_pc_ratio_val = opt_info.get("vol_put_call_ratio")  # v6: fixed key mismatch
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
            "tier": c.get("tier", "mid"),
            "reversal_candidate": bool(c.get("reversal_candidate", False)),
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
            "options_data": opt_info,  # v6: full options dict for Layer 4 scoring
            # v12: Premarket data (passed through from quote)
            "premarket_price": c.get("premarket_price"),
            "premarket_change_pct": c.get("premarket_change_pct", 0.0),
            "premarket_volume": c.get("premarket_volume", 0),
            # v12: Average daily dollar volume for liquidity-aware position sizing
            "adv_20d": _compute_adv_20d(kdf),
        })

    logger.info(f"Layer 2 enrichment: {len(enriched)} candidates with technical data")
    return enriched
