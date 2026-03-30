"""Score-outcome correlation analyzer.

Analyzes historical win_rate_records to measure which score dimensions
(news_score, tech_score, fundamental_score) actually predict returns.

Requires the expanded win_rate_records schema (B1) with score columns.
"""

from __future__ import annotations

from typing import Any

from core.database import Database
from core.user import SYSTEM_DB_PATH


def analyze_score_effectiveness(min_records: int = 20) -> dict[str, Any]:
    """Analyze correlation between scores and outcomes.

    Returns effectiveness metrics for each score dimension.
    Requires at least `min_records` completed records to produce results.
    """
    db = Database(SYSTEM_DB_PATH)
    try:
        rows = _get_completed_records(db)
        if len(rows) < min_records:
            return {
                "status": "insufficient_data",
                "records_found": len(rows),
                "min_required": min_records,
                "message": f"Need at least {min_records} completed records, found {len(rows)}",
            }

        analysis = {
            "status": "ok",
            "total_records": len(rows),
            "overall": _compute_overall_stats(rows),
            "by_news_score": _analyze_dimension(rows, "news_score"),
            "by_tech_score": _analyze_dimension(rows, "tech_score"),
            "by_fundamental_score": _analyze_dimension(rows, "fundamental_score"),
            "by_combined_score": _analyze_dimension(rows, "combined_score"),
            "by_sector": _analyze_by_sector(rows),
            "by_direction": _analyze_by_direction(rows),
            "correlation_summary": {},
        }

        analysis["correlation_summary"] = _compute_correlations(rows)
        analysis["recommendations"] = _generate_recommendations(analysis)

        return analysis
    finally:
        db.close()


def _get_completed_records(db: Database) -> list[dict]:
    """Fetch completed win_rate_records with score columns."""
    cursor = db._conn.execute("""
        SELECT run_date, ticker, name, market, strategy, direction,
               entry_price, stop_loss, take_profit, holding_days,
               outcome, exit_price, return_pct,
               news_score, tech_score, fundamental_score,
               combined_score, confidence, sector
        FROM win_rate_records
        WHERE outcome IN ('win', 'loss', 'timeout')
        ORDER BY run_date DESC
    """)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _compute_overall_stats(rows: list[dict]) -> dict:
    """Compute overall win rate and return stats."""
    wins = sum(1 for r in rows if r["outcome"] == "win")
    losses = sum(1 for r in rows if r["outcome"] == "loss")
    timeouts = sum(1 for r in rows if r["outcome"] == "timeout")
    returns = [r["return_pct"] for r in rows if r.get("return_pct") is not None]

    return {
        "total": len(rows),
        "wins": wins,
        "losses": losses,
        "timeouts": timeouts,
        "win_rate_pct": round(wins / len(rows) * 100, 1) if rows else 0,
        "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0,
        "total_return_pct": round(sum(returns), 2) if returns else 0,
    }


def _analyze_dimension(rows: list[dict], score_key: str) -> dict:
    """Analyze a single score dimension by ranges."""
    ranges = {
        "0-30": (0, 30),
        "30-50": (30, 50),
        "50-70": (50, 70),
        "70-100": (70, 100),
    }

    result = {}
    for label, (lo, hi) in ranges.items():
        bucket = [r for r in rows if r.get(score_key) is not None and lo <= r[score_key] < hi]
        if not bucket:
            continue
        wins = sum(1 for r in bucket if r["outcome"] == "win")
        returns = [r["return_pct"] for r in bucket if r.get("return_pct") is not None]
        result[label] = {
            "count": len(bucket),
            "win_rate_pct": round(wins / len(bucket) * 100, 1),
            "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0,
        }

    has_data = any(r.get(score_key) is not None for r in rows)
    if has_data:
        scored = [r for r in rows if r.get(score_key) is not None]
        if len(scored) >= 10:
            high = [r for r in scored if r[score_key] >= 60]
            low = [r for r in scored if r[score_key] < 40]
            high_wr = sum(1 for r in high if r["outcome"] == "win") / len(high) * 100 if high else 0
            low_wr = sum(1 for r in low if r["outcome"] == "win") / len(low) * 100 if low else 0
            result["_predictive_spread"] = round(high_wr - low_wr, 1)
        else:
            result["_predictive_spread"] = None
    else:
        result["_predictive_spread"] = None

    return result


def _analyze_by_sector(rows: list[dict]) -> dict:
    """Win rate breakdown by sector."""
    sectors: dict[str, list] = {}
    for r in rows:
        sec = r.get("sector") or "Unknown"
        sectors.setdefault(sec, []).append(r)

    result = {}
    for sec, recs in sectors.items():
        if len(recs) < 3:
            continue
        wins = sum(1 for r in recs if r["outcome"] == "win")
        returns = [r["return_pct"] for r in recs if r.get("return_pct") is not None]
        result[sec] = {
            "count": len(recs),
            "win_rate_pct": round(wins / len(recs) * 100, 1),
            "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0,
        }
    return result


def _analyze_by_direction(rows: list[dict]) -> dict:
    """Win rate breakdown by direction (buy/short)."""
    result = {}
    for direction in ("buy", "short", "hold"):
        bucket = [r for r in rows if r.get("direction") == direction]
        if not bucket:
            continue
        wins = sum(1 for r in bucket if r["outcome"] == "win")
        returns = [r["return_pct"] for r in bucket if r.get("return_pct") is not None]
        result[direction] = {
            "count": len(bucket),
            "win_rate_pct": round(wins / len(bucket) * 100, 1),
            "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0,
        }
    return result


def _compute_correlations(rows: list[dict]) -> dict:
    """Compute simple correlation between each score and return_pct."""
    result = {}
    for key in ("news_score", "tech_score", "fundamental_score", "combined_score"):
        pairs = [(r[key], r["return_pct"]) for r in rows
                 if r.get(key) is not None and r.get("return_pct") is not None]
        if len(pairs) < 10:
            result[key] = {"correlation": None, "sample_size": len(pairs)}
            continue

        scores = [p[0] for p in pairs]
        returns = [p[1] for p in pairs]
        n = len(pairs)
        mean_s = sum(scores) / n
        mean_r = sum(returns) / n
        cov = sum((s - mean_s) * (r - mean_r) for s, r in pairs) / n
        std_s = (sum((s - mean_s) ** 2 for s in scores) / n) ** 0.5
        std_r = (sum((r - mean_r) ** 2 for r in returns) / n) ** 0.5

        if std_s > 0 and std_r > 0:
            corr = round(cov / (std_s * std_r), 3)
        else:
            corr = 0.0

        result[key] = {
            "correlation": corr,
            "sample_size": n,
            "interpretation": (
                "strong_positive" if corr > 0.3 else
                "moderate_positive" if corr > 0.1 else
                "weak" if corr > -0.1 else
                "moderate_negative" if corr > -0.3 else
                "strong_negative"
            ),
        }
    return result


def _generate_recommendations(analysis: dict) -> list[str]:
    """Generate actionable recommendations based on analysis."""
    recs = []
    corrs = analysis.get("correlation_summary", {})

    news_corr = (corrs.get("news_score") or {}).get("correlation")
    tech_corr = (corrs.get("tech_score") or {}).get("correlation")
    fund_corr = (corrs.get("fundamental_score") or {}).get("correlation")

    if news_corr is not None and news_corr < 0.05:
        recs.append("NEWS_WEIGHT_REDUCE: news_score shows near-zero correlation with returns. Consider reducing news_weight further or removing news layer.")

    if tech_corr is not None and tech_corr > 0.15:
        recs.append(f"TECH_WEIGHT_INCREASE: tech_score shows positive correlation ({tech_corr:.3f}). Consider increasing tech_weight.")

    if fund_corr is not None and fund_corr > 0.15:
        recs.append(f"FUNDAMENTAL_WEIGHT_INCREASE: fundamental_score shows positive correlation ({fund_corr:.3f}). Consider increasing fundamental_weight.")

    overall = analysis.get("overall", {})
    wr = overall.get("win_rate_pct", 0)
    if wr < 40:
        recs.append(f"LOW_WIN_RATE: Overall win rate is {wr}%. Consider raising min_confidence threshold.")
    elif wr > 65:
        recs.append(f"HIGH_WIN_RATE: Overall win rate is {wr}%. System is performing well; consider slightly more aggressive position sizing.")

    by_dir = analysis.get("by_direction", {})
    short_stats = by_dir.get("short", {})
    if short_stats and short_stats.get("win_rate_pct", 0) < 30:
        recs.append(f"SHORT_UNDERPERFORM: Short trades win rate is {short_stats['win_rate_pct']}%. Consider disabling short recommendations.")

    return recs
