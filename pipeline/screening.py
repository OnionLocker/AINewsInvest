from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import pandas as pd
from loguru import logger

from core.data_source import get_financial_data, get_index_components, get_klines, get_quote
from pipeline.config import get_config


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent


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


def _avg_volume(ticker: str, market: str, days: int = 25) -> float | None:
    df = get_klines(ticker, market, days=days)
    if df is None or df.empty or "volume" not in df.columns:
        return None
    v = pd.to_numeric(df["volume"], errors="coerce").dropna()
    if v.empty:
        return None
    return float(v.tail(min(20, len(v))).mean())


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


def run_screening(market: str = "us_stock", top_n: int = 20) -> list[dict]:
    cfg = get_config()
    sc = cfg.screening

    pool = _load_pool_file(market)
    if not pool:
        pool = _pool_from_indices(market)
    if not pool:
        logger.warning(f"No stock pool for {market}")
        return []

    quotes: dict[tuple[str, str], dict | None] = {}
    max_workers = min(32, max(8, len(pool) // 4 or 8))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {
            ex.submit(get_quote, row["ticker"], row["market"]): row
            for row in pool
        }
        for fut in as_completed(futs):
            row = futs[fut]
            t, m = row["ticker"], row["market"]
            try:
                quotes[(t, m)] = fut.result()
            except Exception as e:
                logger.warning(f"Quote error {m}:{t}: {e}")
                quotes[(t, m)] = None

    passed: list[dict] = []
    for row in pool:
        t, m = row["ticker"], row["market"]
        q = quotes.get((t, m))
        if not q or not q.get("price"):
            continue
        mc = float(q.get("market_cap") or 0)
        if mc < sc.min_market_cap:
            continue
        passed.append({**row, "quote": q})

    vol_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_avg_volume, r["ticker"], r["market"]): r for r in passed}
        for fut in as_completed(futs):
            r = futs[fut]
            try:
                av = fut.result()
            except Exception as e:
                logger.debug(f"Avg volume {r['market']}:{r['ticker']}: {e}")
                av = None
            q = r["quote"]
            vol_use = av if av is not None else float(q.get("volume") or 0)
            if vol_use < sc.min_avg_volume:
                continue
            vol_rows.append({**r, "avg_volume": vol_use})

    fin_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {
            ex.submit(get_financial_data, r["ticker"], r["market"]): r
            for r in vol_rows
        }
        for fut in as_completed(futs):
            r = futs[fut]
            try:
                fin = fut.result()
            except Exception as e:
                logger.debug(f"Financials {r['market']}:{r['ticker']}: {e}")
                fin = None
            fin_rows.append({**r, "financial": fin})

    filtered: list[dict] = []
    for r in fin_rows:
        fin = r.get("financial")
        pe = fin.get("pe_ttm") if fin else None
        pb = fin.get("pb") if fin else None
        if pe is not None:
            try:
                pe = float(pe)
            except (TypeError, ValueError):
                pe = None
        if pb is not None:
            try:
                pb = float(pb)
            except (TypeError, ValueError):
                pb = None

        if sc.min_pe > 0 and pe is None:
            continue
        if pe is not None:
            if pe < sc.min_pe or pe > sc.max_pe:
                continue
        if pb is not None and pb > sc.max_pb:
            continue
        filtered.append(r)

    if not filtered:
        logger.info(f"No symbols passed filters for {market}")
        return []

    vols = [float(r["avg_volume"]) for r in filtered]
    moms: list[float] = []
    mcs: list[float] = []
    volatilities: list[float] = []
    for r in filtered:
        q = r["quote"]
        price = float(q["price"])
        yh = float(q.get("year_high") or price)
        yl = float(q.get("year_low") or price)
        band = (yh - yl) / max(price, 1e-9)
        volatilities.append(band)
        if yh > yl:
            moms.append((price - yl) / (yh - yl))
        else:
            moms.append(0.5)
        mcs.append(max(np.log10(max(q.get("market_cap") or 1, 1)), 0))

    nv = _norm_series(vols, higher_is_better=True)
    nm = _norm_series(moms, higher_is_better=True)
    nc = _norm_series(mcs, higher_is_better=True)
    nvol = _norm_series(volatilities, higher_is_better=False)

    results: list[dict] = []
    wv, wm, wc, wvol = sc.weight_volume, sc.weight_momentum, sc.weight_market_cap, sc.weight_volatility
    for i, r in enumerate(filtered):
        q = r["quote"]
        fin = r.get("financial") or {}
        comp = (
            wv * nv[i] + wm * nm[i] + wc * nc[i] + wvol * nvol[i]
        ) * 100.0
        factors = {
            "volume_rank": nv[i],
            "momentum_rank": nm[i],
            "market_cap_rank": nc[i],
            "volatility_rank": nvol[i],
            "avg_volume": r["avg_volume"],
        }
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
            "factors": factors,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]
