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

        results = {"win": 0, "loss": 0, "timeout": 0, "still_pending": 0, "errors": 0}
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

        results["evaluated"] = results["win"] + results["loss"] + results["timeout"]
        logger.info(
            f"Evaluation: {results['evaluated']} done "
            f"({results['win']}W/{results['loss']}L/{results['timeout']}T), "
            f"{results['still_pending']} still pending, {results['errors']} errors"
        )
        return results
    finally:
        db.close()


def _evaluate_single(rec: dict, today: datetime) -> dict[str, Any] | None:
    """Evaluate one pending record. Supports both long and short directions."""
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

        for _, row in hist.iterrows():
            high = float(row["High"])
            low = float(row["Low"])

            if is_short:
                hit_sl = sl > 0 and high >= sl
                hit_tp = low <= tp1
                if hit_sl and hit_tp:
                    ret_pct = round((entry - sl) / entry * 100, 2)
                    return {"outcome": "loss", "exit_price": sl, "return_pct": ret_pct}
                if hit_sl:
                    ret_pct = round((entry - sl) / entry * 100, 2)
                    return {"outcome": "loss", "exit_price": sl, "return_pct": ret_pct}
                if hit_tp:
                    ret_pct = round((entry - tp1) / entry * 100, 2)
                    return {"outcome": "win", "exit_price": tp1, "return_pct": ret_pct}
            else:
                hit_sl = sl > 0 and low <= sl
                hit_tp = high >= tp1
                if hit_sl and hit_tp:
                    ret_pct = round((sl - entry) / entry * 100, 2)
                    return {"outcome": "loss", "exit_price": sl, "return_pct": ret_pct}
                if hit_sl:
                    ret_pct = round((sl - entry) / entry * 100, 2)
                    return {"outcome": "loss", "exit_price": sl, "return_pct": ret_pct}
                if hit_tp:
                    ret_pct = round((tp1 - entry) / entry * 100, 2)
                    return {"outcome": "win", "exit_price": tp1, "return_pct": ret_pct}

        if holding_expired:
            last_close = float(hist["Close"].iloc[-1])
            if is_short:
                ret_pct = round((entry - last_close) / entry * 100, 2)
            else:
                ret_pct = round((last_close - entry) / entry * 100, 2)

            if is_short:
                if last_close <= tp1:
                    return {"outcome": "win", "exit_price": last_close, "return_pct": ret_pct}
                elif sl > 0 and last_close >= sl:
                    return {"outcome": "loss", "exit_price": last_close, "return_pct": ret_pct}
                else:
                    return {"outcome": "timeout", "exit_price": last_close, "return_pct": ret_pct}
            else:
                if last_close >= tp1:
                    return {"outcome": "win", "exit_price": last_close, "return_pct": ret_pct}
                elif sl > 0 and last_close <= sl:
                    return {"outcome": "loss", "exit_price": last_close, "return_pct": ret_pct}
                else:
                    return {"outcome": "timeout", "exit_price": last_close, "return_pct": ret_pct}

        return None

    except Exception as e:
        logger.warning(f"Price fetch failed for {symbol}: {e}")
        if holding_expired:
            return {"outcome": "timeout", "exit_price": entry, "return_pct": 0.0}
        return None
