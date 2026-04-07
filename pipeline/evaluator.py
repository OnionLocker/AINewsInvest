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


def evaluate_pending_records() -> dict[str, Any]:
    """Check all pending records against current prices.

    Called at the start of each pipeline run, or manually via API.
    """
    db = Database(SYSTEM_DB_PATH)
    try:
        pending = db.get_pending_evaluations()
        if not pending:
            return {"evaluated": 0, "still_pending": 0, "message": "No pending records"}

        results = {"win": 0, "loss": 0, "timeout": 0, "timeout_at_profit": 0, "timeout_at_loss": 0, "partial_win": 0, "still_pending": 0, "errors": 0}
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
            results["win"] + results["loss"] + results["timeout"]
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
        post_fill_rows = []

        for idx, (_, row) in enumerate(hist.iterrows()):
            high = float(row["High"])
            low = float(row["Low"])

            if not entry_filled:
                if is_short:
                    if high >= entry:
                        entry_filled = True
                        post_fill_rows = list(hist.iloc[idx:].iterrows())
                else:
                    if low <= entry:
                        entry_filled = True
                        post_fill_rows = list(hist.iloc[idx:].iterrows())

        if not entry_filled:
            if holding_expired:
                return {"outcome": "timeout", "exit_price": entry, "return_pct": 0.0}
            return None

        # --- Phase 2: evaluate TP / SL / trailing on post-fill bars ---
        if is_short:
            tp_distance = entry - tp1
            best_price = entry
        else:
            tp_distance = tp1 - entry
            best_price = entry

        for _, row in post_fill_rows:
            high = float(row["High"])
            low = float(row["Low"])

            if is_short:
                hit_sl = sl > 0 and high >= sl
                hit_tp = low <= tp1
                if hit_sl and hit_tp:
                    # Both hit same bar: judge by which level is closer
                    # (closer = more likely hit first)
                    tp_dist = abs(low - tp1)
                    sl_dist = abs(high - sl)
                    if tp_dist <= sl_dist:
                        ret_pct = round((entry - tp1) / entry * 100, 2)
                        return {"outcome": "win", "exit_price": tp1, "return_pct": ret_pct}
                    else:
                        ret_pct = round((entry - sl) / entry * 100, 2)
                        return {"outcome": "loss", "exit_price": sl, "return_pct": ret_pct}
                if hit_sl:
                    ret_pct = round((entry - sl) / entry * 100, 2)
                    return {"outcome": "loss", "exit_price": sl, "return_pct": ret_pct}
                if hit_tp:
                    ret_pct = round((entry - tp1) / entry * 100, 2)
                    return {"outcome": "win", "exit_price": tp1, "return_pct": ret_pct}

                best_price = min(best_price, low)
                gain = entry - best_price
                if tp_distance > 0 and gain > tp_distance * 0.5:
                    pullback = high - best_price
                    if pullback > gain * 0.5:
                        # Conservative simulated exit: 40% of gain from entry
                        exit_p = round(entry - gain * 0.4, 2)
                        ret_pct = round((entry - exit_p) / entry * 100, 2)
                        return {"outcome": "partial_win", "exit_price": exit_p, "return_pct": ret_pct}
            else:
                hit_sl = sl > 0 and low <= sl
                hit_tp = high >= tp1
                if hit_sl and hit_tp:
                    # Both hit same bar: judge by which level is closer
                    tp_dist = abs(high - tp1)
                    sl_dist = abs(low - sl)
                    if tp_dist <= sl_dist:
                        ret_pct = round((tp1 - entry) / entry * 100, 2)
                        return {"outcome": "win", "exit_price": tp1, "return_pct": ret_pct}
                    else:
                        ret_pct = round((sl - entry) / entry * 100, 2)
                        return {"outcome": "loss", "exit_price": sl, "return_pct": ret_pct}
                if hit_sl:
                    ret_pct = round((sl - entry) / entry * 100, 2)
                    return {"outcome": "loss", "exit_price": sl, "return_pct": ret_pct}
                if hit_tp:
                    ret_pct = round((tp1 - entry) / entry * 100, 2)
                    return {"outcome": "win", "exit_price": tp1, "return_pct": ret_pct}

                best_price = max(best_price, high)
                gain = best_price - entry
                if tp_distance > 0 and gain > tp_distance * 0.5:
                    pullback = best_price - low
                    if pullback > gain * 0.5:
                        # Conservative simulated exit: 40% of gain from entry
                        exit_p = round(entry + gain * 0.4, 2)
                        ret_pct = round((exit_p - entry) / entry * 100, 2)
                        return {"outcome": "partial_win", "exit_price": exit_p, "return_pct": ret_pct}

        if holding_expired:
            last_close = float(hist["Close"].iloc[-1])
            if is_short:
                ret_pct = round((entry - last_close) / entry * 100, 2)
            else:
                ret_pct = round((last_close - entry) / entry * 100, 2)

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
