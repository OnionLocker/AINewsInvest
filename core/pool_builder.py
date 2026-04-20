"""Build tiered US stock pool from public index sources.

Merges S&P 500, Nasdaq-100 and S&P MidCap 400 into one pool, then fetches
market cap via yfinance to assign each stock a tier (large/mid/small).

Output schema (JSON list)::

    [
      {"ticker": "AAPL", "name": "Apple", "market": "us_stock",
       "tier": "large", "market_cap": 3500000000000.0,
       "sources": ["sp500", "ndx"]},
      ...
    ]

Usage::

    python -m core.pool_builder          # rebuild pool file in place
    python -m core.pool_builder --dry    # print stats, don't write
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import yfinance as yf
from loguru import logger

from core.data_source import (
    _clean_us_ticker,
    _get_nasdaq100_components,
    _get_sp500_components,
    _read_html_wiki,
)

_POOL_FILE = Path(__file__).resolve().parent.parent / "data" / "stock_pool.json"

# Tier boundaries (USD). Picked from empirical market-cap distribution of
# SP500 U NDX U SP400 = ~917 symbols (median $17B, 33rd pctl $11B).
# Keep in sync with config.yaml::pipeline.tiers.
#
# v1 (this release): sources are all mid+large-cap indices, so "small" here is
# really "smallest end of our universe" (~$2B-$10B). When we add Russell 2000
# (iShares IWM holdings) in a future release, we'll drop TIER_SMALL_MIN to
# $500M and add a true "micro" tier for $500M-$2B.
TIER_LARGE_MIN = 5.0e10   # $50B+
TIER_MID_MIN = 1.0e10     # $10B - $50B
TIER_SMALL_MIN = 2.0e9    # $2B - $10B


def _get_sp400_components() -> list[dict]:
    """Fetch S&P MidCap 400 components from Wikipedia."""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
        tables = _read_html_wiki(url)
        for table in tables:
            cols_lower = {str(c).lower(): c for c in table.columns}
            ticker_col = None
            name_col = None
            for lc, orig in cols_lower.items():
                if "symbol" in lc or "ticker" in lc:
                    ticker_col = orig
                if "security" in lc or "company" in lc or "name" in lc:
                    name_col = orig
            if ticker_col is None:
                continue
            results = []
            for _, row in table.iterrows():
                ticker = _clean_us_ticker(row.get(ticker_col, ""))
                if not ticker:
                    continue
                name = str(row.get(name_col, "")).strip() if name_col else ticker
                results.append({
                    "ticker": ticker, "market": "us_stock", "name": name,
                })
            if results:
                logger.info(f"SP400: fetched {len(results)} components")
                return results
        logger.warning("SP400: no suitable table found")
        return []
    except Exception as e:
        logger.warning(f"SP400 fetch failed: {e}")
        return []


def _classify_tier(market_cap: float) -> str | None:
    """Return tier name for a market cap in USD. None = below floor (reject)."""
    if market_cap >= TIER_LARGE_MIN:
        return "large"
    if market_cap >= TIER_MID_MIN:
        return "mid"
    if market_cap >= TIER_SMALL_MIN:
        return "small"
    return None


def _fetch_market_cap(symbol: str) -> float | None:
    """Fetch market cap via yfinance. Returns None on failure."""
    try:
        t = yf.Ticker(symbol)
        info = t.fast_info
        mc = getattr(info, "market_cap", None)
        if mc and mc > 0:
            return float(mc)
    except Exception:
        pass
    return None


def build_pool(dry_run: bool = False, fetch_workers: int = 16) -> dict:
    """Merge SP500 + NDX + SP400 and assign tiers.

    Returns stats dict. Writes ``data/stock_pool.json`` unless dry_run.
    """
    sp500 = _get_sp500_components()
    ndx = _get_nasdaq100_components()
    sp400 = _get_sp400_components()

    # Merge with source tracking
    merged: dict[str, dict] = {}
    for src_name, rows in (("sp500", sp500), ("ndx", ndx), ("sp400", sp400)):
        for r in rows:
            t = r["ticker"]
            if t in merged:
                merged[t]["sources"].append(src_name)
            else:
                merged[t] = {**r, "sources": [src_name]}
    logger.info(
        f"Merged: sp500={len(sp500)} ndx={len(ndx)} sp400={len(sp400)} "
        f"-> unique={len(merged)}"
    )

    # Fetch market caps in parallel
    tickers = list(merged.keys())
    start = time.time()
    caps: dict[str, float | None] = {}
    with ThreadPoolExecutor(max_workers=fetch_workers) as ex:
        futs = {ex.submit(_fetch_market_cap, t): t for t in tickers}
        done = 0
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                caps[t] = fut.result()
            except Exception:
                caps[t] = None
            done += 1
            if done % 100 == 0:
                logger.info(f"  market_cap fetched {done}/{len(tickers)}")
    elapsed = time.time() - start
    logger.info(f"Market cap fetch complete in {elapsed:.1f}s")

    # Classify & assemble
    out: list[dict] = []
    tier_counts = {"large": 0, "mid": 0, "small": 0, "rejected": 0, "unknown": 0}
    for t, rec in merged.items():
        mc = caps.get(t)
        if mc is None:
            tier_counts["unknown"] += 1
            # Keep without tier so humans can debug. Will be filtered out by
            # screening's hard market-cap gate anyway.
            out.append({**rec, "market_cap": 0.0, "tier": "unknown"})
            continue
        tier = _classify_tier(mc)
        if tier is None:
            tier_counts["rejected"] += 1
            continue
        tier_counts[tier] += 1
        out.append({**rec, "market_cap": round(mc, 2), "tier": tier})

    # Sort: tier then market_cap desc for determinism / human readability
    _tier_order = {"large": 0, "mid": 1, "small": 2, "unknown": 3}
    out.sort(key=lambda r: (_tier_order.get(r["tier"], 9), -r["market_cap"]))

    stats = {
        "total": len(out),
        "tiers": tier_counts,
        "sources": {
            "sp500": len(sp500),
            "ndx": len(ndx),
            "sp400": len(sp400),
        },
    }
    logger.info(f"Final pool: {stats}")

    if not dry_run:
        # Also preserve HK entries from existing pool (we only rebuild US)
        hk_entries: list[dict] = []
        if _POOL_FILE.is_file():
            try:
                existing = json.loads(_POOL_FILE.read_text(encoding="utf-8"))
                hk_entries = [r for r in existing if r.get("market") == "hk_stock"]
            except Exception as e:
                logger.warning(f"Could not read existing pool for HK merge: {e}")
        final = out + hk_entries
        _POOL_FILE.write_text(
            json.dumps(final, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info(f"Wrote {len(final)} entries ({len(hk_entries)} HK preserved) -> {_POOL_FILE}")

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry", action="store_true", help="Don't write file")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args(argv)

    stats = build_pool(dry_run=args.dry, fetch_workers=args.workers)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
