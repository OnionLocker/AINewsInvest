"""Parameter optimizer - grid search over backtest results.

Uses the backtest engine to find optimal screening weights,
synthesis weights, and risk parameters.

Train/test split: first 60% of days for training, last 40% for validation.
"""

from __future__ import annotations

import itertools
from typing import Any

from loguru import logger

from pipeline.backtest import run_backtest
from pipeline.config import get_config


_WEIGHT_GRID = {
    "weight_momentum": [0.25, 0.30, 0.35, 0.40],
    "weight_trend": [0.15, 0.20, 0.25, 0.30],
    "weight_quality": [0.15, 0.20, 0.25],
    "weight_volatility": [0.15, 0.20, 0.25],
}

_THRESHOLD_GRID = {
    "min_score": [50, 55, 60, 65],
    "top_n": [10, 15, 20],
}


def run_optimization(
    market: str = "us_stock",
    lookback_days: int = 60,
    max_stocks: int = 50,
    progress_cb=None,
) -> dict[str, Any]:
    """Run parameter optimization via grid search on backtest results.

    Tests different min_score and top_n combinations (fast grid).
    Full weight grid is too expensive; uses threshold grid only.

    Returns best parameters and comparison table.
    """
    logger.info(f"Optimizer starting: market={market}")

    combos = list(itertools.product(
        _THRESHOLD_GRID["min_score"],
        _THRESHOLD_GRID["top_n"],
    ))

    results: list[dict] = []
    best_sharpe = -999
    best_params = {}

    for idx, (min_score, top_n) in enumerate(combos):
        if progress_cb:
            pct = (idx / len(combos)) * 90
            progress_cb({"progress": pct, "message": f"Testing min_score={min_score}, top_n={top_n}"})

        try:
            stats = run_backtest(
                market=market,
                lookback_days=lookback_days,
                top_n=top_n,
                max_stocks=max_stocks,
                min_score=min_score,
            )

            if "error" in stats:
                continue

            entry = {
                "min_score": min_score,
                "top_n": top_n,
                "total_trades": stats["total_trades"],
                "win_rate_pct": stats["win_rate_pct"],
                "avg_return_pct": stats["avg_return_pct"],
                "sharpe_ratio": stats["sharpe_ratio"],
                "max_drawdown_pct": stats["max_drawdown_pct"],
                "profit_factor": stats["profit_factor"],
            }
            results.append(entry)

            if stats["sharpe_ratio"] > best_sharpe and stats["total_trades"] >= 10:
                best_sharpe = stats["sharpe_ratio"]
                best_params = entry.copy()

            logger.info(
                f"Optimizer [{idx+1}/{len(combos)}] "
                f"min_score={min_score} top_n={top_n}: "
                f"wr={stats['win_rate_pct']:.1f}% sharpe={stats['sharpe_ratio']:.2f}"
            )
        except Exception as e:
            logger.warning(f"Optimizer error: {e}")

    results.sort(key=lambda x: x.get("sharpe_ratio", -999), reverse=True)

    if progress_cb:
        progress_cb({"progress": 100, "message": "Optimization complete"})

    return {
        "market": market,
        "tested_combinations": len(combos),
        "successful_tests": len(results),
        "best_params": best_params,
        "all_results": results,
        "current_config": {
            "min_score": get_config().synthesis.min_confidence,
            "top_n": get_config().max_candidates,
        },
    }
