"""Backtesting engine - historical replay without LLM costs.

Replays the screening + technical scoring + risk control pipeline on
historical data to validate parameters and measure expected performance.

Key principle: NO look-ahead bias. For each simulated trading day,
only data available up to that day is used.
"""

from __future__ import annotations

import math
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from loguru import logger

from core.data_source import to_yf_ticker, get_index_components
from pipeline.config import get_config
from pipeline.screening import (
    _safe_float, _norm_series, _compute_fundamental_score,
    compute_atr, compute_volatility_pct, classify_volatility,
    compute_volume_profile_support, compute_support_strength,
    compute_volume_at_high, compute_weekly_trend,
)


def _fetch_extended_klines(ticker: str, market: str, total_days: int = 200) -> pd.DataFrame:
    """Fetch extended historical K-lines for backtesting (enough for lookback + forward)."""
    symbol = to_yf_ticker(ticker, market)
    try:
        t = yf.Ticker(symbol)
        end = datetime.now()
        start = end - timedelta(days=total_days + 30)
        df = t.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
        if df.empty:
            return pd.DataFrame()
        df = df.reset_index().rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        return df[["date", "open", "high", "low", "close", "volume"]]
    except Exception as e:
        logger.warning(f"Backtest kline fetch failed {symbol}: {e}")
        return pd.DataFrame()


def _get_pool_tickers(market: str) -> list[dict]:
    """Get the stock pool for backtesting."""
    import json
    from pathlib import Path

    pkg_root = Path(__file__).resolve().parent.parent
    pool_path = pkg_root / "data" / "stock_pool.json"
    if pool_path.is_file():
        try:
            with open(pool_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                pool = [x for x in raw if isinstance(x, dict) and x.get("market") == market]
                if pool:
                    return pool
        except Exception:
            pass

    return get_index_components("^GSPC" if market == "us_stock" else "^HSI")


def _deterministic_score(kdf: pd.DataFrame, sim_date: pd.Timestamp, lookback: int = 80) -> dict:
    """Compute deterministic technical score from K-line data up to sim_date.
    
    Returns a dict with score, action, and enrichment data needed for trade params.
    """
    mask = kdf["date"] <= sim_date
    hist = kdf.loc[mask].tail(lookback).copy()
    
    if hist.empty or len(hist) < 10:
        return None
    
    hist = hist.sort_values("date").reset_index(drop=True)
    price = float(hist["close"].iloc[-1])
    if price <= 0:
        return None
    
    closes = hist["close"].tolist()
    n = len(closes)
    
    ma5 = sum(closes[-min(5, n):]) / min(5, n)
    ma10 = sum(closes[-min(10, n):]) / min(10, n)
    ma20 = sum(closes[-min(20, n):]) / min(20, n)
    ma60 = sum(closes[-min(60, n):]) / min(60, n) if n >= 30 else ma20
    
    atr_20d = compute_atr(hist, period=20)
    volatility_20d = compute_volatility_pct(hist, period=20)
    volatility_class = classify_volatility(volatility_20d)
    
    support_levels = compute_volume_profile_support(hist, price)
    support_touch_count, support_hold_strength = compute_support_strength(
        hist, support_levels[0] if support_levels else 0,
    )
    
    recent = hist.tail(20)
    high_20 = float(recent["high"].max()) if "high" in recent.columns else price * 1.05
    resistance_levels = [round(high_20, 2), round(high_20 * 1.03, 2)]
    
    avg_vol_5 = hist["volume"].tail(5).mean() if "volume" in hist.columns else 1
    avg_vol_20 = hist["volume"].tail(20).mean() if "volume" in hist.columns else 1
    volume_ratio = round(float(avg_vol_5 / max(avg_vol_20, 1)), 2)
    
    ma20_bias_pct = round(abs(price - ma20) / max(ma20, 0.01) * 100, 2)
    high_20d_volume_ratio = compute_volume_at_high(hist)
    weekly_trend = compute_weekly_trend(hist, price)
    
    ma_bullish = (ma5 >= ma10 >= ma20) and (ma5 > ma20)
    ma_bearish = (ma5 <= ma10 <= ma20) and (ma5 < ma20)
    above_ma20 = price > ma20
    volume_expansion = volume_ratio > 1.3
    near_support = price <= support_levels[0] * 1.02 if support_levels else False
    broke_20d_high = price >= resistance_levels[0] if resistance_levels else False
    overbought_bias = ma20_bias_pct > 15.0
    volume_price_divergence = broke_20d_high and high_20d_volume_ratio > 1.3 and not volume_expansion
    
    # Deterministic scoring (same logic as fallback_technical_scores)
    cfg = get_config()
    fb = cfg.agent.fallback
    score = fb.base_score
    
    if ma_bullish:
        score += fb.ma_bullish_bonus
    elif ma_bearish:
        score -= fb.ma_bearish_penalty
    
    if volume_ratio >= fb.volume_ratio_strong:
        score += fb.volume_strong_bonus
    elif volume_ratio >= fb.volume_ratio_medium:
        score += fb.volume_medium_bonus
    
    if overbought_bias:
        score = min(score, 65)
    elif ma20_bias_pct > 10:
        score -= 5
    
    if volume_price_divergence:
        score -= 12
    
    if volatility_class == "high":
        score -= 3
    
    if weekly_trend == "bearish":
        score -= 8
    elif weekly_trend == "bullish":
        score += 3
    
    if near_support and support_hold_strength in ("strong", "moderate"):
        score += 5
    
    score = max(0, min(100, score))
    action = "buy" if score >= 60 else ("hold" if score >= 45 else "avoid")
    
    if overbought_bias:
        action = "hold"
    
    volume = float(hist["volume"].iloc[-1]) if "volume" in hist.columns else 0
    market_cap_proxy = price * 1e9
    
    return {
        "price": price,
        "score": score,
        "action": action,
        "ma5": round(ma5, 2),
        "ma10": round(ma10, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
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
        "volume": volume,
        "signals": {
            "ma_bullish_align": ma_bullish,
            "ma_bearish_align": ma_bearish,
            "above_ma20": above_ma20,
            "volume_expansion": volume_expansion,
            "near_support": near_support,
            "near_resistance": price >= resistance_levels[0] * 0.98 if resistance_levels else False,
            "broke_20d_high": broke_20d_high,
            "overbought_bias": overbought_bias,
            "volume_price_divergence": volume_price_divergence,
            "weekly_bearish": weekly_trend == "bearish",
        },
    }


def _simulate_trade(
    kdf: pd.DataFrame,
    sim_date: pd.Timestamp,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    holding_days: int,
    direction: str = "buy",
) -> dict:
    """Simulate a trade outcome using future K-line data after sim_date."""
    future = kdf[kdf["date"] > sim_date].head(holding_days + 3)
    
    if future.empty:
        return {"outcome": "no_data", "return_pct": 0.0, "exit_price": entry_price, "days_held": 0}
    
    is_short = direction == "short"
    entry_filled = False
    
    for day_idx, (_, row) in enumerate(future.iterrows()):
        high = float(row["high"])
        low = float(row["low"])
        close_val = float(row["close"])
        
        if not entry_filled:
            if is_short:
                if high >= entry_price:
                    entry_filled = True
                else:
                    continue
            else:
                if low <= entry_price:
                    entry_filled = True
                else:
                    if day_idx == 0 and close_val > 0:
                        entry_price = float(row["open"])
                        entry_filled = True
                    else:
                        continue
        
        if is_short:
            if stop_loss > 0 and high >= stop_loss:
                ret = round((entry_price - stop_loss) / entry_price * 100, 2)
                return {"outcome": "loss", "return_pct": ret, "exit_price": stop_loss, "days_held": day_idx + 1}
            if low <= take_profit:
                ret = round((entry_price - take_profit) / entry_price * 100, 2)
                return {"outcome": "win", "return_pct": ret, "exit_price": take_profit, "days_held": day_idx + 1}
        else:
            if stop_loss > 0 and low <= stop_loss:
                ret = round((stop_loss - entry_price) / entry_price * 100, 2)
                return {"outcome": "loss", "return_pct": ret, "exit_price": stop_loss, "days_held": day_idx + 1}
            if high >= take_profit:
                ret = round((take_profit - entry_price) / entry_price * 100, 2)
                return {"outcome": "win", "return_pct": ret, "exit_price": take_profit, "days_held": day_idx + 1}
    
    if not entry_filled:
        return {"outcome": "no_fill", "return_pct": 0.0, "exit_price": entry_price, "days_held": 0}
    
    last_close = float(future["close"].iloc[-1])
    if is_short:
        ret = round((entry_price - last_close) / entry_price * 100, 2)
    else:
        ret = round((last_close - entry_price) / entry_price * 100, 2)
    return {"outcome": "timeout", "return_pct": ret, "exit_price": last_close, "days_held": len(future)}


def run_backtest(
    market: str = "us_stock",
    lookback_days: int = 60,
    top_n: int = 20,
    max_stocks: int = 80,
    min_score: int = 55,
    progress_cb=None,
) -> dict[str, Any]:
    """Run historical backtest for a market.
    
    Args:
        market: "us_stock" or "hk_stock"
        lookback_days: how many trading days to simulate
        top_n: how many top stocks to pick per day
        max_stocks: max stocks from pool to test (limits API calls)
        min_score: minimum tech score to generate a trade
        progress_cb: optional callback for progress updates
    
    Returns:
        Comprehensive backtest statistics dict
    """
    from pipeline.agents import _compute_trade_params, _classify_action
    
    logger.info(f"Backtest starting: market={market}, days={lookback_days}, top_n={top_n}")
    
    pool = _get_pool_tickers(market)
    if not pool:
        return {"error": "No stock pool"}
    
    pool = pool[:max_stocks]
    logger.info(f"Backtest pool: {len(pool)} stocks")
    
    if progress_cb:
        progress_cb({"progress": 5, "message": f"Fetching K-lines for {len(pool)} stocks..."})
    
    kline_cache: dict[str, pd.DataFrame] = {}
    total_hist_days = lookback_days + 100
    
    workers = min(6, max(2, len(pool) // 5))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(_fetch_extended_klines, s["ticker"], s["market"], total_hist_days): s
            for s in pool
        }
        done = 0
        for fut in as_completed(futs):
            s = futs[fut]
            done += 1
            try:
                df = fut.result()
                if not df.empty and len(df) >= 30:
                    kline_cache[s["ticker"]] = df
            except Exception:
                pass
            if progress_cb and done % 10 == 0:
                pct = 5 + (done / len(pool)) * 30
                progress_cb({"progress": pct, "message": f"Fetched {done}/{len(pool)} K-lines"})
    
    logger.info(f"Backtest K-line cache: {len(kline_cache)} stocks with data")
    
    if len(kline_cache) < 5:
        return {"error": "Not enough K-line data for backtest"}
    
    ref_ticker = list(kline_cache.keys())[0]
    ref_dates = kline_cache[ref_ticker]["date"].sort_values().tolist()
    
    if len(ref_dates) < lookback_days + 20:
        lookback_days = max(10, len(ref_dates) - 20)
    
    sim_dates = ref_dates[-(lookback_days + 10):-10]
    
    all_trades: list[dict] = []
    daily_returns: list[float] = []
    
    for day_idx, sim_date in enumerate(sim_dates):
        if progress_cb:
            pct = 35 + (day_idx / len(sim_dates)) * 55
            progress_cb({"progress": pct, "message": f"Simulating day {day_idx+1}/{len(sim_dates)}"})
        
        day_candidates = []
        for ticker, kdf in kline_cache.items():
            result = _deterministic_score(kdf, sim_date)
            if result is None:
                continue
            result["ticker"] = ticker
            result["market"] = market
            day_candidates.append(result)
        
        day_candidates.sort(key=lambda x: x["score"], reverse=True)
        top_picks = [c for c in day_candidates[:top_n] if c["score"] >= min_score]
        
        day_return = 0.0
        for pick in top_picks:
            action = pick["action"]
            action_bucket = _classify_action(action)
            
            trade = _compute_trade_params(
                price=pick["price"],
                enriched=pick,
                action=action,
                strategy_type="short",
            )
            
            kdf = kline_cache[pick["ticker"]]
            outcome = _simulate_trade(
                kdf, sim_date,
                entry_price=trade["entry_price"],
                stop_loss=trade["stop_loss"],
                take_profit=trade["take_profit"],
                holding_days=trade["holding_days"],
                direction="buy",
            )
            
            if outcome["outcome"] in ("no_data", "no_fill"):
                continue
            
            trade_record = {
                "date": str(sim_date.date()) if hasattr(sim_date, 'date') else str(sim_date)[:10],
                "ticker": pick["ticker"],
                "score": pick["score"],
                "action": action,
                "entry_price": trade["entry_price"],
                "stop_loss": trade["stop_loss"],
                "take_profit": trade["take_profit"],
                "holding_days": trade["holding_days"],
                **outcome,
            }
            all_trades.append(trade_record)
            day_return += outcome["return_pct"]
        
        if top_picks:
            daily_returns.append(day_return / len(top_picks))
    
    if progress_cb:
        progress_cb({"progress": 92, "message": "Computing statistics..."})
    
    stats = _compute_stats(all_trades, daily_returns)
    stats["market"] = market
    stats["lookback_days"] = lookback_days
    stats["pool_size"] = len(kline_cache)
    stats["sim_days"] = len(sim_dates)
    stats["top_n"] = top_n
    stats["min_score"] = min_score
    
    if progress_cb:
        progress_cb({"progress": 100, "message": "Backtest complete"})
    
    logger.info(
        f"Backtest complete: {stats['total_trades']} trades, "
        f"win_rate={stats['win_rate_pct']:.1f}%, "
        f"avg_return={stats['avg_return_pct']:.2f}%, "
        f"sharpe={stats['sharpe_ratio']:.2f}"
    )
    return stats


def _compute_stats(trades: list[dict], daily_returns: list[float]) -> dict[str, Any]:
    """Compute comprehensive backtest statistics."""
    if not trades:
        return {
            "total_trades": 0, "wins": 0, "losses": 0, "timeouts": 0,
            "win_rate_pct": 0, "avg_return_pct": 0, "total_return_pct": 0,
            "sharpe_ratio": 0, "max_drawdown_pct": 0, "profit_factor": 0,
            "avg_win_pct": 0, "avg_loss_pct": 0, "best_trade_pct": 0,
            "worst_trade_pct": 0, "avg_days_held": 0,
            "by_score_range": {}, "by_action": {}, "monthly": {},
        }
    
    returns = [t["return_pct"] for t in trades]
    wins = [t for t in trades if t["outcome"] == "win"]
    losses = [t for t in trades if t["outcome"] == "loss"]
    timeouts = [t for t in trades if t["outcome"] == "timeout"]
    
    win_returns = [t["return_pct"] for t in wins]
    loss_returns = [t["return_pct"] for t in losses]
    
    gross_profit = sum(r for r in returns if r > 0)
    gross_loss = abs(sum(r for r in returns if r < 0))
    
    # Sharpe ratio (annualized, assuming daily returns)
    if daily_returns and len(daily_returns) > 1:
        dr = np.array(daily_returns)
        mean_r = float(np.mean(dr))
        std_r = float(np.std(dr, ddof=1))
        sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0
    else:
        sharpe = 0.0
    
    # Max drawdown from cumulative daily returns
    max_dd = 0.0
    if daily_returns:
        cum = np.cumsum(daily_returns)
        peak = np.maximum.accumulate(cum)
        dd = cum - peak
        max_dd = float(np.min(dd)) if len(dd) > 0 else 0.0
    
    # Breakdown by score range
    score_ranges = {"50-60": [], "60-70": [], "70-80": [], "80+": []}
    for t in trades:
        s = t.get("score", 0)
        if s >= 80:
            score_ranges["80+"].append(t)
        elif s >= 70:
            score_ranges["70-80"].append(t)
        elif s >= 60:
            score_ranges["60-70"].append(t)
        else:
            score_ranges["50-60"].append(t)
    
    by_score = {}
    for rng, tlist in score_ranges.items():
        if tlist:
            w = sum(1 for t in tlist if t["outcome"] == "win")
            by_score[rng] = {
                "trades": len(tlist),
                "win_rate_pct": round(w / len(tlist) * 100, 1),
                "avg_return_pct": round(sum(t["return_pct"] for t in tlist) / len(tlist), 2),
            }
    
    # Breakdown by action
    by_action = {}
    for action in ("buy", "hold", "avoid"):
        atrades = [t for t in trades if t.get("action") == action]
        if atrades:
            w = sum(1 for t in atrades if t["outcome"] == "win")
            by_action[action] = {
                "trades": len(atrades),
                "win_rate_pct": round(w / len(atrades) * 100, 1),
                "avg_return_pct": round(sum(t["return_pct"] for t in atrades) / len(atrades), 2),
            }
    
    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "timeouts": len(timeouts),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1),
        "avg_return_pct": round(sum(returns) / len(returns), 2),
        "total_return_pct": round(sum(returns), 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "avg_win_pct": round(sum(win_returns) / len(win_returns), 2) if win_returns else 0,
        "avg_loss_pct": round(sum(loss_returns) / len(loss_returns), 2) if loss_returns else 0,
        "best_trade_pct": round(max(returns), 2),
        "worst_trade_pct": round(min(returns), 2),
        "avg_days_held": round(sum(t["days_held"] for t in trades) / len(trades), 1),
        "by_score_range": by_score,
        "by_action": by_action,
        "trades": trades,
    }
