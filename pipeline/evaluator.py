"""Win rate evaluator - checks pending recommendations against actual prices.

Called automatically at the start of each pipeline run.

Logic (long/buy):
- If intraday high >= TP1: WIN
- If intraday low <= SL (before TP1): LOSS

Logic (short/sell):
- If intraday low <= TP1: WIN (price dropped to target)
- If intraday high >= SL (before TP1): LOSS (price rose past stop)

- If holding period expired without either: TIMEOUT
- If still within holding period: stay pending
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import yfinance as yf
from loguru import logger

from core.database import Database
from core.data_source import to_yf_ticker
from core.user import SYSTEM_DB_PATH
from pipeline.config import get_config


# v11: Per-trade round-trip cost model.
# 0.3% total = 0.15% on entry (paying ask + slippage) + 0.15% on exit
# (hitting bid + slippage). This covers a realistic zero-commission US-retail
# account where bid-ask spread + market impact is the true cost. Applied only
# to return_pct calculation so win/loss determination still uses raw prices
# (the broker sees the raw TP/SL orders, not the cost-adjusted ones).
_TRADE_COST_ONE_WAY = 0.0015  # 0.15% per fill
_TRADE_COST_ROUND_TRIP = 2 * _TRADE_COST_ONE_WAY  # 0.30%


def _apply_trade_cost(raw_return_pct: float) -> float:
    """Deduct round-trip cost from a raw % return.

    Works for both long and short since cost is symmetric.
    """
    return round(raw_return_pct - _TRADE_COST_ROUND_TRIP * 100, 2)


def evaluate_pending_records() -> dict[str, Any]:
    """Check all pending records against current prices.

    Called at the start of each pipeline run, or manually via API.
    """
    db = Database(SYSTEM_DB_PATH)
    try:
        pending = db.get_pending_evaluations()
        if not pending:
            return {"evaluated": 0, "still_pending": 0, "message": "No pending records"}

        results = {"win": 0, "loss": 0, "trailing_stop": 0, "timeout": 0, "timeout_at_profit": 0, "timeout_at_loss": 0, "partial_win": 0, "still_pending": 0, "errors": 0}
        today = datetime.now()

        for rec in pending:
            try:
                outcome = _evaluate_single(rec, today)
                if outcome is None:
                    results["still_pending"] += 1
                    continue

                db.update_win_rate(
                    rec["id"],
                    outcome["outcome"],
                    outcome["exit_price"],
                    outcome["return_pct"],
                )
                results[outcome["outcome"]] = results.get(outcome["outcome"], 0) + 1
            except Exception as e:
                logger.warning(f"Eval error {rec.get('ticker')}: {e}")
                results["errors"] += 1

        results["evaluated"] = (
            results["win"] + results["loss"] + results["trailing_stop"]
            + results["timeout"]
            + results["timeout_at_profit"] + results["timeout_at_loss"]
            + results["partial_win"]
        )
        logger.info(
            f"Evaluation: {results['evaluated']} done "
            f"({results['win']}W/{results['loss']}L/{results['timeout']}T), "
            f"{results['still_pending']} still pending, {results['errors']} errors"
        )
        return results
    finally:
        db.close()


def _evaluate_single(rec: dict, today: datetime) -> dict[str, Any] | None:
    """Evaluate one pending record. Supports both long and short directions.

    Phase 1 – Entry fill: iterate daily bars to see if the limit-order
    entry_price was actually reached (low <= entry for long, high >= entry
    for short).  Only bars *after* the fill date are eligible for TP/SL.

    Phase 2 – TP / SL / trailing-stop / timeout evaluation on post-fill bars.
    """
    run_date = datetime.strptime(rec["run_date"], "%Y%m%d")
    entry = float(rec["entry_price"])
    tp1 = float(rec["take_profit"])
    sl = float(rec["stop_loss"])
    holding_days = int(rec["holding_days"])
    direction = str(rec.get("direction", "buy"))
    is_short = direction == "short"

    if entry <= 0 or tp1 <= 0:
        return {"outcome": "timeout", "exit_price": entry, "return_pct": 0.0}

    trade_start = run_date + timedelta(days=1)

    if today <= trade_start:
        return None

    calendar_buffer = holding_days + (holding_days // 5) * 2 + 3
    expiry_date = trade_start + timedelta(days=calendar_buffer)
    holding_expired = today >= expiry_date

    symbol = to_yf_ticker(rec["ticker"], rec["market"])

    try:
        start_str = trade_start.strftime("%Y-%m-%d")
        end_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")

        hist = yf.Ticker(symbol).history(start=start_str, end=end_str)
        if hist.empty:
            if holding_expired:
                return {"outcome": "timeout", "exit_price": entry, "return_pct": 0.0}
            return None

        # --- Phase 1: check if the limit-order entry was filled ---
        entry_filled = False
        fill_idx = -1

        for idx, (_, row) in enumerate(hist.iterrows()):
            high = float(row["High"])
            low = float(row["Low"])
            rng = max(high - low, 1e-9)

            if is_short:
                # Short: limit near/above market (high>=entry) or stop when price drops (low<=entry)
                filled = (high >= entry) or (low <= entry)
            else:
                # Long: strict intraday touch; buy-stop / breakout (high>=entry); limit buy when
                # session low is at/below limit (low<=entry) with guard so absurd entry above
                # the bar (data error) does not auto-fill via low<=entry alone.
                touched = low <= entry <= high
                buy_stop = high >= entry
                limit_buy = (low <= entry) and (
                    entry <= high
                    or (
                        entry > high
                        and (entry - high) <= rng
                    )
                )
                filled = touched or buy_stop or limit_buy

            if filled:
                entry_filled = True
                fill_idx = idx
                break

        if not entry_filled:
            if holding_expired:
                return {"outcome": "timeout", "exit_price": entry, "return_pct": 0.0}
            return None

        # Bars from the fill day onward (including fill bar) — needed so TP/SL can
        # resolve when the only fill happens on the latest daily bar; "next bar only"
        # would otherwise leave those trades stuck in pending forever.
        post_fill_rows = list(hist.iloc[fill_idx:].iterrows())
        if not post_fill_rows:
            return None

        # --- Phase 2: evaluate TP / SL / trailing on post-fill bars ---
        # Derive trailing stop parameters from config
        cfg = get_config()
        strategy = str(rec.get("strategy", "short_term"))
        strat_cfg = cfg.swing if strategy == "swing" else cfg.short_term
        trailing_activation_pct = strat_cfg.trailing_activation_pct
        trailing_distance_pct = strat_cfg.trailing_distance_pct

        if is_short:
            tp_distance = entry - tp1
            best_price = entry
            trailing_activation_price = entry - tp_distance * trailing_activation_pct
        else:
            tp_distance = tp1 - entry
            best_price = entry
            trailing_activation_price = entry + tp_distance * trailing_activation_pct

        trailing_active = False
        effective_sl = sl

        for _, row in post_fill_rows:
            high = float(row["High"])
            low = float(row["Low"])

            if is_short:
                # Update best (lowest) price
                best_price = min(best_price, low)

                # Check trailing activation
                if not trailing_active and tp_distance > 0 and best_price <= trailing_activation_price:
                    trailing_active = True
                if trailing_active and trailing_distance_pct > 0:
                    trailing_sl = round(best_price * (1 + trailing_distance_pct), 2)
                    effective_sl = min(sl, trailing_sl)  # tighter (lower) for shorts

                hit_sl = effective_sl > 0 and high >= effective_sl
                hit_tp = low <= tp1

                if hit_sl and hit_tp:
                    tp_dist = abs(low - tp1)
                    sl_dist = abs(high - effective_sl)
                    if tp_dist <= sl_dist:
                        ret_pct = _apply_trade_cost((entry - tp1) / entry * 100)
                        return {"outcome": "win", "exit_price": tp1, "return_pct": ret_pct}
                    else:
                        ret_pct = _apply_trade_cost((entry - effective_sl) / entry * 100)
                        outcome_str = "trailing_stop" if trailing_active else "loss"
                        return {"outcome": outcome_str, "exit_price": effective_sl, "return_pct": ret_pct}
                if hit_sl:
                    ret_pct = _apply_trade_cost((entry - effective_sl) / entry * 100)
                    outcome_str = "trailing_stop" if trailing_active else "loss"
                    return {"outcome": outcome_str, "exit_price": effective_sl, "return_pct": ret_pct}
                if hit_tp:
                    ret_pct = _apply_trade_cost((entry - tp1) / entry * 100)
                    return {"outcome": "win", "exit_price": tp1, "return_pct": ret_pct}

                # Partial win detection
                gain = entry - best_price
                if tp_distance > 0 and gain > tp_distance * 0.5:
                    pullback = high - best_price
                    if pullback > gain * 0.5:
                        exit_p = round(entry - gain * 0.4, 2)
                        ret_pct = _apply_trade_cost((entry - exit_p) / entry * 100)
                        return {"outcome": "partial_win", "exit_price": exit_p, "return_pct": ret_pct}

            else:  # LONG
                # Update best (highest) price
                best_price = max(best_price, high)

                # Check trailing activation
                if not trailing_active and tp_distance > 0 and best_price >= trailing_activation_price:
                    trailing_active = True
                if trailing_active and trailing_distance_pct > 0:
                    trailing_sl = round(best_price * (1 - trailing_distance_pct), 2)
                    effective_sl = max(sl, trailing_sl)  # tighter (higher) for longs

                hit_sl = effective_sl > 0 and low <= effective_sl
                hit_tp = high >= tp1

                if hit_sl and hit_tp:
                    tp_dist = abs(high - tp1)
                    sl_dist = abs(low - effective_sl)
                    if tp_dist <= sl_dist:
                        ret_pct = _apply_trade_cost((tp1 - entry) / entry * 100)
                        return {"outcome": "win", "exit_price": tp1, "return_pct": ret_pct}
                    else:
                        ret_pct = _apply_trade_cost((effective_sl - entry) / entry * 100)
                        outcome_str = "trailing_stop" if trailing_active else "loss"
                        return {"outcome": outcome_str, "exit_price": effective_sl, "return_pct": ret_pct}
                if hit_sl:
                    ret_pct = _apply_trade_cost((effective_sl - entry) / entry * 100)
                    outcome_str = "trailing_stop" if trailing_active else "loss"
                    return {"outcome": outcome_str, "exit_price": effective_sl, "return_pct": ret_pct}
                if hit_tp:
                    ret_pct = _apply_trade_cost((tp1 - entry) / entry * 100)
                    return {"outcome": "win", "exit_price": tp1, "return_pct": ret_pct}

                # Partial win detection
                gain = best_price - entry
                if tp_distance > 0 and gain > tp_distance * 0.5:
                    pullback = best_price - low
                    if pullback > gain * 0.5:
                        exit_p = round(entry + gain * 0.4, 2)
                        ret_pct = _apply_trade_cost((exit_p - entry) / entry * 100)
                        return {"outcome": "partial_win", "exit_price": exit_p, "return_pct": ret_pct}

        if holding_expired:
            last_close = float(hist["Close"].iloc[-1])
            if is_short:
                ret_pct = _apply_trade_cost((entry - last_close) / entry * 100)
            else:
                ret_pct = _apply_trade_cost((last_close - entry) / entry * 100)

            if is_short:
                if last_close <= tp1:
                    return {"outcome": "timeout_at_profit", "exit_price": last_close, "return_pct": ret_pct}
                elif sl > 0 and last_close >= sl:
                    return {"outcome": "timeout_at_loss", "exit_price": last_close, "return_pct": ret_pct}
                else:
                    return {"outcome": "timeout", "exit_price": last_close, "return_pct": ret_pct}
            else:
                if last_close >= tp1:
                    return {"outcome": "timeout_at_profit", "exit_price": last_close, "return_pct": ret_pct}
                elif sl > 0 and last_close <= sl:
                    return {"outcome": "timeout_at_loss", "exit_price": last_close, "return_pct": ret_pct}
                else:
                    return {"outcome": "timeout", "exit_price": last_close, "return_pct": ret_pct}

        return None

    except Exception as e:
        logger.warning(f"Price fetch failed for {symbol}: {e}")
        if holding_expired:
            return {"outcome": "timeout", "exit_price": entry, "return_pct": 0.0}
        return None


def get_underperforming_sectors(
    days: int = 30,
    min_samples: int = 8,
    max_win_rate: float = 0.35,
) -> list[str]:
    """Return sector names with poor recent win rates.

    Only flags sectors with >= min_samples completed trades to avoid
    small-sample noise. Used by synthesize_agent_results for confidence penalty.
    """
    db = Database(SYSTEM_DB_PATH)
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        rows = db._conn.execute("""
            SELECT sector, COUNT(*) as cnt,
                   SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins
            FROM win_rate_records
            WHERE outcome IN ('win', 'loss')
              AND run_date >= ?
              AND sector IS NOT NULL AND sector != ''
            GROUP BY sector
            HAVING cnt >= ?
        """, (cutoff, min_samples)).fetchall()

        bad_sectors = []
        for sector, cnt, wins in rows:
            wr = wins / cnt
            if wr < max_win_rate:
                bad_sectors.append(sector)
                logger.info(
                    f"Sector penalty candidate: {sector} "
                    f"win_rate={wr:.1%} ({wins}/{cnt} in last {days}d)"
                )
        return bad_sectors
    except Exception as e:
        logger.warning(f"Sector analysis failed: {e}")
        return []
    finally:
        db.close()


def compute_dimensional_win_rates(lookback_days: int = 60) -> dict[str, dict]:
    """Compute win rates grouped by (tier, strategy, regime_level).

    Returns dict like:
      {"large|short_term|normal": {"win_rate": 0.55, "count": 20}, ...}

    Only includes groups with completed trades (win/loss).
    """
    db = Database(SYSTEM_DB_PATH)
    try:
        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y%m%d")
        # Check if tier and regime_level columns exist
        cols = [c[1] for c in db._conn.execute("PRAGMA table_info(win_rate_records)").fetchall()]
        has_tier = "tier" in cols
        has_regime = "regime_level" in cols

        if not has_tier or not has_regime:
            logger.debug("dimensional win-rates: tier/regime_level columns not yet in DB")
            return {}

        rows = db._conn.execute("""
            SELECT tier, strategy, regime_level,
                   COUNT(*) as cnt,
                   SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins
            FROM win_rate_records
            WHERE outcome IN ('win', 'loss')
              AND run_date >= ?
              AND tier IS NOT NULL
              AND regime_level IS NOT NULL
            GROUP BY tier, strategy, regime_level
        """, (cutoff,)).fetchall()

        result: dict[str, dict] = {}
        for tier, strategy, regime, cnt, wins in rows:
            key = f"{tier}|{strategy}|{regime}"
            result[key] = {
                "win_rate": round(wins / cnt, 3) if cnt > 0 else 0.0,
                "count": cnt,
                "wins": wins,
            }

        if result:
            logger.info(f"Dimensional win-rates: {len(result)} groups over {lookback_days}d")
        return result
    except Exception as e:
        logger.debug(f"Dimensional win-rates failed: {e}")
        return {}
    finally:
        db.close()


def check_parameter_drift(lookback_days: int = 30, threshold_pp: float = 10.0) -> dict:
    """Compare recent win-rate vs prior period to detect performance drift.

    Checks the last `lookback_days` vs the preceding `lookback_days`.
    If overall or any dimensional win-rate drops by more than `threshold_pp`
    percentage points, returns drifted=True with details.
    """
    db = Database(SYSTEM_DB_PATH)
    try:
        now = datetime.now()
        recent_start = (now - timedelta(days=lookback_days)).strftime("%Y%m%d")
        prior_start = (now - timedelta(days=lookback_days * 2)).strftime("%Y%m%d")

        def _win_rate_in_range(start: str, end: str) -> tuple[int, int]:
            row = db._conn.execute("""
                SELECT COUNT(*) as cnt,
                       SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins
                FROM win_rate_records
                WHERE outcome IN ('win', 'loss')
                  AND run_date >= ? AND run_date < ?
            """, (start, end)).fetchone()
            return (row[0] or 0, row[1] or 0)

        recent_cnt, recent_wins = _win_rate_in_range(recent_start, now.strftime("%Y%m%d"))
        prior_cnt, prior_wins = _win_rate_in_range(prior_start, recent_start)

        if recent_cnt < 5 or prior_cnt < 5:
            return {"drifted": False, "reason": "insufficient_data",
                    "recent_count": recent_cnt, "prior_count": prior_cnt}

        recent_wr = recent_wins / recent_cnt * 100
        prior_wr = prior_wins / prior_cnt * 100
        drop = prior_wr - recent_wr

        drifted = drop > threshold_pp
        details = {
            "recent_win_rate": round(recent_wr, 1),
            "prior_win_rate": round(prior_wr, 1),
            "drop_pp": round(drop, 1),
            "recent_count": recent_cnt,
            "prior_count": prior_cnt,
        }

        # Also check by strategy
        drifted_dimensions: list[str] = []
        for strategy in ("short_term", "swing"):
            def _wr_strat(start, end, strat):
                r = db._conn.execute("""
                    SELECT COUNT(*), SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END)
                    FROM win_rate_records
                    WHERE outcome IN ('win','loss') AND run_date >= ? AND run_date < ?
                      AND strategy = ?
                """, (start, end, strat)).fetchone()
                return (r[0] or 0, r[1] or 0)

            rc, rw = _wr_strat(recent_start, now.strftime("%Y%m%d"), strategy)
            pc, pw = _wr_strat(prior_start, recent_start, strategy)
            if rc >= 3 and pc >= 3:
                r_wr = rw / rc * 100
                p_wr = pw / pc * 100
                strat_drop = p_wr - r_wr
                if strat_drop > threshold_pp:
                    drifted_dimensions.append(f"{strategy}: {p_wr:.0f}% -> {r_wr:.0f}%")
                    drifted = True

        if drifted:
            logger.warning(
                f"Parameter drift detected: overall {prior_wr:.0f}% -> {recent_wr:.0f}% "
                f"(drop {drop:.1f}pp). Dimensions: {drifted_dimensions or ['overall']}"
            )
        else:
            logger.info(
                f"Drift check OK: {prior_wr:.0f}% -> {recent_wr:.0f}% "
                f"(delta {drop:+.1f}pp, threshold {threshold_pp}pp)"
            )

        return {
            "drifted": drifted,
            "dimensions": drifted_dimensions,
            "details": details,
        }
    except Exception as e:
        logger.debug(f"Parameter drift check failed: {e}")
        return {"drifted": False, "error": str(e)}
    finally:
        db.close()
