"""Daily pipeline runner - 6-layer architecture.

Layer 1: Quantitative screening (screening.run_screening)
Layer 2: Technical data enrichment (screening.build_enriched_candidates)
Layer 3-6: LLM Agent pipeline (agents.run_agent_pipeline)

Each call processes exactly ONE market (us_stock or hk_stock).
The ref_date is computed from the market's local timezone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from loguru import logger
from zoneinfo import ZoneInfo

import yfinance as yf

from core.database import Database
from core.user import SYSTEM_DB_PATH
from pipeline.config import get_config
from pipeline.screening import (
    run_screening, batch_fetch_klines, build_enriched_candidates,
    _layer1_kline_cache,
)

_MARKET_TZ = {
    "us_stock": "America/New_York",
    "hk_stock": "Asia/Hong_Kong",
}


def _check_market_regime(market: str) -> dict:
    """Check market-level conditions. Returns regime dict with level and flags.

    Levels: normal, cautious, bearish, crisis

    v6: Now includes macro yield curve data (US only) from core/macro_data.
    Yield curve inversion + elevated VIX -> escalate to bearish.
    """
    try:
        if market == "us_stock":
            spy = yf.Ticker("SPY").history(period="6d")
            vix_data = yf.Ticker("^VIX").history(period="1d")
        else:
            spy = yf.Ticker("^HSI").history(period="6d")
            vix_data = None

        if spy.empty or len(spy) < 2:
            return {"level": "normal", "flags": [], "details": {}}

        last_close = float(spy["Close"].iloc[-1])
        prev_close = float(spy["Close"].iloc[-2])
        daily_change = (last_close - prev_close) / prev_close * 100

        five_day_change = 0.0
        if len(spy) >= 5:
            five_ago = float(spy["Close"].iloc[-5])
            five_day_change = (last_close - five_ago) / five_ago * 100

        vix_val = 0.0
        if vix_data is not None and not vix_data.empty:
            vix_val = float(vix_data["Close"].iloc[-1])

        flags = []
        level = "normal"

        if daily_change < -3.0:
            flags.append("single_day_crash")
            level = "crisis"
        elif daily_change < -2.0:
            flags.append("large_daily_drop")
            level = max(level, "bearish", key=["normal", "cautious", "bearish", "crisis"].index)

        if five_day_change < -5.0:
            flags.append("sustained_decline")
            level = "crisis"
        elif five_day_change < -3.0:
            flags.append("weekly_weakness")
            level = max(level, "bearish", key=["normal", "cautious", "bearish", "crisis"].index)

        if vix_val > 35:
            flags.append("extreme_vix")
            level = max(level, "bearish", key=["normal", "cautious", "bearish", "crisis"].index)
        elif vix_val > 25:
            flags.append("elevated_vix")
            level = max(level, "cautious", key=["normal", "cautious", "bearish", "crisis"].index)

        # --- v6: Macro yield curve integration (US only) ---
        macro_data: dict = {}
        if market == "us_stock":
            try:
                from core.macro_data import get_macro_indicators
                macro_data = get_macro_indicators()
                if macro_data.get("_fetched"):
                    spread = macro_data.get("yield_spread_10y5y")
                    if spread is not None:
                        if spread < -0.5:
                            flags.append("deep_yield_inversion")
                            level = max(level, "bearish", key=["normal", "cautious", "bearish", "crisis"].index)
                        elif spread < -0.2:
                            flags.append("yield_curve_inversion")
                            level = max(level, "cautious", key=["normal", "cautious", "bearish", "crisis"].index)

                        # Inversion + elevated VIX = compounding risk
                        if spread < -0.3 and vix_val > 25:
                            flags.append("yield_inversion_plus_vix")
                            level = max(level, "bearish", key=["normal", "cautious", "bearish", "crisis"].index)
            except Exception as e:
                logger.debug(f"Macro indicators skipped: {e}")

        details = {
            "daily_change_pct": round(daily_change, 2),
            "five_day_change_pct": round(five_day_change, 2),
            "vix": round(vix_val, 1) if vix_val > 0 else None,
            # Macro fields (None if HK or fetch failed)
            "yield_10y": macro_data.get("yield_10y"),
            "yield_spread": macro_data.get("yield_spread_10y5y"),
            "macro_risk": macro_data.get("macro_risk_level"),
            "spread_trend": macro_data.get("spread_trend"),
        }

        # --- v11: Macro event calendar (FOMC/CPI/PCE/NFP, US only) ---
        # High-impact releases routinely cause 1-3% intraday swings that blow
        # through ATR-based stops. Day-of critical event -> escalate to
        # cautious; day-before critical -> flag so the runner can halve the
        # recommendation quota downstream.
        macro_events_today: list[dict] = []
        macro_events_tomorrow: list[dict] = []
        if market == "us_stock":
            try:
                from core.macro_calendar import (
                    get_macro_events_on, get_macro_events_tomorrow,
                    has_critical_event, has_critical_event_tomorrow,
                )
                today_ref = datetime.now(ZoneInfo(_MARKET_TZ[market])).strftime("%Y%m%d")
                macro_events_today = get_macro_events_on(today_ref)
                macro_events_tomorrow = get_macro_events_tomorrow(today_ref)

                if has_critical_event(today_ref):
                    flags.append("macro_event_today")
                    # Even normal markets become cautious on FOMC/CPI days
                    level = max(level, "cautious",
                                key=["normal", "cautious", "bearish", "crisis"].index)
                if has_critical_event_tomorrow(today_ref):
                    flags.append("macro_event_tomorrow")
                    # Do not escalate regime; runner will halve rec quota instead.
            except Exception as e:
                logger.debug(f"Macro calendar check failed: {e}")

        details["macro_events_today"] = macro_events_today
        details["macro_events_tomorrow"] = macro_events_tomorrow

        logger.info(
            f"Market regime {market}: {level} | "
            f"1d={daily_change:+.1f}% 5d={five_day_change:+.1f}% VIX={vix_val:.0f} "
            f"spread={macro_data.get('yield_spread_10y5y', 'N/A')} "
            f"macro_risk={macro_data.get('macro_risk_level', 'N/A')} "
            f"flags={flags}"
        )
        return {"level": level, "flags": flags, "details": details}

    except Exception as e:
        logger.warning(f"Market regime check failed: {e}")
        return {"level": "normal", "flags": ["check_failed"], "details": {}}


def _ref_date_for_market(market: str) -> str:
    tz_name = _MARKET_TZ.get(market, "America/New_York")
    return datetime.now(ZoneInfo(tz_name)).strftime("%Y%m%d")


def _apply_earnings_blackout(
    candidates: list[dict],
    ref_date: str,
    days_before: int = 2,
    days_after: int = 1,
) -> list[dict]:
    """Drop US candidates whose next earnings date falls in the blackout window.

    Blackout = [T - days_before, T + days_after] around the earnings release.
    Earnings weeks routinely produce 5-10% single-day moves which completely
    invalidate ATR-based stop-losses. Entering during this window is reckless
    regardless of how strong the signal looks on other dimensions.

    The cache in ``core.earnings_calendar`` keeps yfinance calls bounded.
    Any ticker whose earnings lookup fails falls back to "no blackout" so an
    intermittent data outage never silently blocks the full pipeline.
    """
    try:
        from core.earnings_calendar import is_in_earnings_blackout, days_until_earnings
    except Exception as e:
        logger.warning(f"earnings_calendar import failed, skipping blackout: {e}")
        return candidates

    kept: list[dict] = []
    dropped: list[tuple[str, int]] = []
    for c in candidates:
        ticker = c.get("ticker")
        if not ticker:
            continue
        try:
            blocked = is_in_earnings_blackout(
                ticker, market="us_stock", ref_date=ref_date,
                days_before=days_before, days_after=days_after,
            )
        except Exception as e:
            logger.debug(f"earnings lookup failed for {ticker}: {e}")
            blocked = False
        if blocked:
            try:
                du = days_until_earnings(ticker, "us_stock", ref_date)
            except Exception:
                du = None
            dropped.append((str(ticker), du if du is not None else 0))
            continue
        kept.append(c)

    if dropped:
        logger.warning(
            f"Earnings blackout: dropped {len(dropped)}/{len(candidates)} candidates "
            f"(window T-{days_before}..T+{days_after}); examples: {dropped[:5]}"
        )
    else:
        logger.info(
            f"Earnings blackout: 0 candidates dropped "
            f"(window T-{days_before}..T+{days_after})"
        )
    return kept


def _progress(
    cb: Callable[[dict], None] | None,
    pct: float,
    msg: str,
) -> None:
    if cb:
        try:
            cb({"progress": pct, "message": msg})
        except Exception as e:
            logger.warning(f"progress_cb error: {e}")


def _record_skill_outputs(db: "Database", ref_date: str, market: str, analyzed: list[dict]) -> int:
    """Record skill outputs from analyzed recommendations for backtesting."""
    count = 0
    for item in analyzed:
        ticker = item.get("ticker", "")
        if not ticker:
            continue

        # Record news skill output
        news_skill = item.get("_news_skill_output")
        if news_skill:
            try:
                db.save_skill_output(
                    run_date=ref_date,
                    market=market,
                    ticker=ticker,
                    skill_name="news_skill",
                    raw_output=news_skill,
                    scored_value=item.get("news_score"),
                )
                count += 1
            except Exception as e:
                logger.debug(f"Skill output save {ticker}/news: {e}")

        # Record tech skill output
        tech_skill = item.get("_tech_skill_output")
        if tech_skill:
            try:
                db.save_skill_output(
                    run_date=ref_date,
                    market=market,
                    ticker=ticker,
                    skill_name="tech_skill",
                    raw_output=tech_skill,
                    scored_value=item.get("tech_score"),
                )
                count += 1
            except Exception as e:
                logger.debug(f"Skill output save {ticker}/tech: {e}")

    if count:
        logger.info(f"Recorded {count} skill outputs for backtesting")
    return count


def run_daily_pipeline(
    market: str = "us_stock",
    strategy_mode: str = "dual",
    force: bool = False,
    trigger_source: str = "system_auto",
    trigger_note: str = "",
    progress_cb: Callable[[dict], None] | None = None,
) -> dict:
    """Execute the full 6-layer daily pipeline for a single market.

    1. Screen candidates (Layer 1)
    2. Enrich with technical data (Layer 2)
    3. Run Agent pipeline (Layers 3-6)
    4. Save and publish recommendations
    """
    cfg = get_config()
    ref_date = _ref_date_for_market(market)
    st = cfg.short_term

    _progress(progress_cb, 2.0, "Evaluating pending win-rate records")
    try:
        from pipeline.evaluator import evaluate_pending_records
        eval_result = evaluate_pending_records()
        logger.info(f"Pre-run evaluation: {eval_result}")
    except Exception as e:
        logger.warning(f"Pre-run evaluation failed: {e}")

    _progress(progress_cb, 4.0, "Checking market regime")
    regime = _check_market_regime(market)
    logger.info(f"Market regime: {regime}")

    db = Database(SYSTEM_DB_PATH)
    try:
        if not force:
            existing, items = db.get_daily_recommendations(ref_date, market=market)
            if existing:
                _progress(progress_cb, 100.0, f"Already ran today for {market}")
                return {
                    "ref_date": ref_date,
                    "market": market,
                    "skipped": True,
                    "reason": "daily run exists",
                    "published_count": len(items),
                }

        # Phase 1: Layer 1 - Screening
        _progress(progress_cb, 5.0, f"Layer 1: Screening {market}")
        _pool_type = "short_term" if strategy_mode == "short_term_only" else "default"
        screened = run_screening(market=market, top_n=cfg.max_candidates, pool_type=_pool_type)
        _progress(progress_cb, 15.0, f"Layer 1 screened {market}: {len(screened)} candidates")

        screened.sort(key=lambda x: x["score"], reverse=True)
        candidates = screened[:cfg.max_candidates]
        if not candidates:
            _progress(progress_cb, 100.0, "No candidates after screening")
            return {
                "ref_date": ref_date,
                "market": market,
                "candidate_count": 0,
                "published_count": 0,
                "items": [],
                "empty_reason": "no_candidates",
            }

        # v11: Earnings blackout filter (US only).
        # Drop any candidate whose next earnings date falls within T-2..T+1 of
        # ref_date. yfinance earnings_dates coverage for HK stocks is poor, so
        # we skip the filter for hk_stock to avoid false rejections.
        if market == "us_stock":
            candidates = _apply_earnings_blackout(candidates, ref_date)
            if not candidates:
                _progress(progress_cb, 100.0, "All candidates in earnings blackout")
                return {
                    "ref_date": ref_date,
                    "market": market,
                    "candidate_count": 0,
                    "published_count": 0,
                    "items": [],
                    "empty_reason": "earnings_blackout",
                }

        # Phase 2: Layer 2 - Technical enrichment
        # Reuse K-line data from Layer 1 if available, fetch missing ones
        _progress(progress_cb, 20.0, f"Layer 2: Enriching {len(candidates)} candidates")
        cached = _layer1_kline_cache or {}
        missing = [c for c in candidates if c["ticker"] not in cached]
        if missing:
            logger.info(f"Layer 2: {len(cached)} cached, fetching {len(missing)} missing K-lines")
            extra = batch_fetch_klines(missing, days=80)
            kline_map = {**cached, **extra}
        else:
            kline_map = cached
        enriched = build_enriched_candidates(candidates, kline_map)

        if not enriched:
            _progress(progress_cb, 100.0, "No candidates after enrichment")
            return {
                "ref_date": ref_date,
                "market": market,
                "candidate_count": len(candidates),
                "published_count": 0,
                "items": [],
                "empty_reason": "enrichment_failed",
            }

        # Phase 3: Layers 3-6 - Agent pipeline
        # v9 fix: dual mode returns short + swing (already cross-deduped and each
        # trimmed to its own top_n inside run_agent_pipeline); previously we
        # truncated the combined list back to cfg.max_recommendations=5, which
        # silently dropped half the recs and let duplicates (same ticker from
        # short + swing with equal conviction) survive. Compute the cap per-mode.
        if strategy_mode == "short_term_only":
            max_recs = cfg.max_recommendations
        else:  # dual
            max_recs = cfg.synthesis.top_n_normal + cfg.swing.top_n_normal
        if regime["level"] == "crisis":
            max_recs = 0
            logger.warning(f"Market CRISIS mode - skipping all long recs for {market}")
        # v7: bearish/cautious/normal handled by synthesis quality tier logic

        # v11: Halve recommendation quota the day before a critical macro release
        # (FOMC / CPI). Market often front-runs these events with fake breakouts.
        if "macro_event_tomorrow" in regime.get("flags", []) and max_recs > 0:
            max_recs = max(1, max_recs // 2)
            logger.warning(
                f"Critical macro event tomorrow - halving max_recs to {max_recs} "
                f"for {market}"
            )

        if regime["level"] == "crisis" and market == "hk_stock":
            _progress(progress_cb, 100.0, "Market crisis - no recommendations")
            return {
                "ref_date": ref_date,
                "market": market,
                "candidate_count": len(candidates),
                "published_count": 0,
                "regime": regime,
                "items": [],
                "empty_reason": "crisis_regime",
            }

        _progress(progress_cb, 30.0, f"Layers 3-6: Agent pipeline on {len(enriched)} candidates")
        from pipeline.agents import run_agent_pipeline
        _st_type = "short" if strategy_mode == "short_term_only" else "dual"
        analyzed = run_agent_pipeline(
            enriched,
            market=market,
            strategy_type=_st_type,
            progress_cb=progress_cb,
            regime=regime,
        )

        if not analyzed:
            _progress(progress_cb, 100.0, "No recommendations from agent pipeline")
            return {
                "ref_date": ref_date,
                "market": market,
                "candidate_count": len(candidates),
                "published_count": 0,
                "regime": regime,
                "items": [],
                "empty_reason": "no_signals",
            }

        top_items = analyzed[:max_recs]

        # Phase 4: Save and publish
        _progress(progress_cb, 80.0, f"Saving {len(top_items)} recommendations for {market}")

        run_id = db.save_daily_recommendation_run(
            ref_date,
            market,
            top_items,
            strategy="dual",
            source_count=len(screened),
            candidate_count=len(candidates),
            trigger_source=trigger_source,
            trigger_note=trigger_note,
        )

        admin_run, saved_items = db.get_daily_recommendations(ref_date, market=market)
        if not admin_run:
            admin_run = {
                "market": market,
                "strategy": "dual",
                "trigger_source": trigger_source,
                "trigger_note": trigger_note,
            }
        pub_id = db.publish_recommendations(ref_date, market, admin_run, saved_items)

        _wr_inserted = 0
        _wr_skipped_noparams = 0
        _wr_errors = 0
        for it in saved_items:
            try:
                # Skip records without valid trading params (is_quality=False)
                ep = it.get("entry_price")
                slp = it.get("stop_loss")
                tpp = it.get("take_profit")
                if not ep or not slp or not tpp:
                    _wr_skipped_noparams += 1
                    continue

                themes = it.get("themes", [])
                if isinstance(themes, str):
                    try:
                        themes = json.loads(themes) if themes.strip() else []
                    except Exception:
                        themes = []
                elif themes is None:
                    themes = []
                sector = themes[0] if themes else ""
                db.save_win_rate_record({
                    "run_date": ref_date,
                    "ticker": it["ticker"],
                    "name": it["name"],
                    "market": it["market"],
                    "strategy": it.get("strategy", "short_term"),
                    "direction": it.get("direction", "buy"),
                    "entry_price": float(it.get("entry_price") or 0),
                    "stop_loss": float(it.get("stop_loss") or 0),
                    "take_profit": float(it.get("take_profit") or 0),
                    "holding_days": int(it.get("holding_days") or st.default_holding_days),
                    "news_score": it.get("news_score", 0),
                    "tech_score": it.get("tech_score", 0),
                    "fundamental_score": it.get("fundamental_score", 0),
                    "combined_score": it.get("combined_score", 0),
                    "confidence": it.get("confidence", 0),
                    "sector": sector,
                })
                _wr_inserted += 1
            except Exception as e:
                _wr_errors += 1
                logger.warning(f"win_rate record {it.get('ticker')}: {e}")

        logger.info(
            f"win_rate insert: {_wr_inserted}/{len(saved_items)} inserted "
            f"(skipped_no_params={_wr_skipped_noparams}, errors={_wr_errors})"
        )

        # --- v3.x Cooldown: holding >5 days -> 30-day cooldown ---
        from datetime import timedelta as _td
        _cd_count = 0
        for it in saved_items:
            hd = int(it.get("holding_days") or 0)
            if hd > 5:
                _expire = (datetime.strptime(ref_date, "%Y%m%d") + _td(days=30)).strftime("%Y%m%d")
                try:
                    db.add_to_cooldown(
                        ticker=it["ticker"], market=market,
                        strategy_type=it.get("strategy", "short_term"),
                        direction=it.get("direction", "buy"),
                        added_date=ref_date, expire_date=_expire,
                    )
                    _cd_count += 1
                except Exception as e:
                    logger.debug(f"Cooldown write {it['ticker']}: {e}")
        if _cd_count:
            logger.info(f"Added {_cd_count} tickers to 30-day cooldown")

        _progress(progress_cb, 95.0, "Computing market sentiment cache")

        # Record skill outputs for backtesting
        try:
            _record_skill_outputs(db, ref_date, market, analyzed)
        except Exception as e:
            logger.warning(f"Skill output recording failed: {e}")

        try:
            _cache_market_sentiment(db, market)
        except Exception as e:
            logger.warning(f"Market sentiment cache failed: {e}")

        _progress(progress_cb, 100.0, f"Done - {market}")
        return {
            "ref_date": ref_date,
            "market": market,
            "run_id": run_id,
            "published_run_id": pub_id,
            "candidate_count": len(candidates),
            "published_count": len(saved_items),
            "regime": regime,
            "items": [dict(x) for x in saved_items],
        }
    finally:
        db.close()


def _cache_market_sentiment(db: Database, market: str):
    """Compute full market sentiment and store in DB for instant API reads."""
    from analysis.news_fetcher import fetch_market_news, analyze_sentiment
    from core.data_source import _get_market_breadth

    mkt_short = "us" if market == "us_stock" else "hk"

    news = fetch_market_news(market=market, limit=25)
    sentiment = analyze_sentiment(news)
    breadth = _get_market_breadth(market)

    top_headlines = []
    for n in news[:6]:
        top_headlines.append({
            "title": n.get("title", ""),
            "publisher": n.get("publisher", ""),
            "link": n.get("link", ""),
            "credibility": n.get("credibility", 0.5),
        })

    s = sentiment.get("score", 0.0)
    adv = breadth.get("advance_pct", 50.0)
    raw = (s + 1) / 2 * 50 + adv / 100 * 50
    raw = max(0, min(100, raw))
    if raw >= 75:
        label = "\u6781\u5ea6\u8d2a\u5a6a"
    elif raw >= 60:
        label = "\u8d2a\u5a6a"
    elif raw >= 40:
        label = "\u4e2d\u6027"
    elif raw >= 25:
        label = "\u6050\u60e7"
    else:
        label = "\u6781\u5ea6\u6050\u60e7"
    fear_greed = {"value": round(raw, 1), "label": label}

    total = breadth.get("total", 0)
    if mkt_short == "us":
        scope_label = f"\u6807\u666e500\u6210\u5206\u80a1({total}\u53ea)"
    else:
        scope_label = f"\u6052\u6307+\u6052\u751f\u79d1\u6280\u6210\u5206\u80a1({total}\u53ea)"

    result = {
        "market": market,
        "sentiment": sentiment,
        "breadth": breadth,
        "breadth_scope": scope_label,
        "fear_greed": fear_greed,
        "headlines": top_headlines,
        "vix": None,
    }

    # VIX (US only)
    if market == "us_stock":
        try:
            vix_data = yf.Ticker("^VIX").history(period="1d")
            if vix_data is not None and not vix_data.empty:
                result["vix"] = round(float(vix_data["Close"].iloc[-1]), 1)
        except Exception as e:
            logger.debug(f"VIX fetch for sentiment cache failed: {e}")

    db.save_market_sentiment(market, result)
    logger.info(f"Market sentiment cached for {market}: fg={fear_greed['value']}, breadth={total}")


# ---------------------------------------------------------------------------
# v11: Two-stage entry pricing
#
# Stage 1 (pre-market, e.g. 07:30 ET): initial pipeline run produces
# recommendations using pre-market / previous-close reference prices. Entry/
# SL/TP computed against that reference are an *approximation*.
#
# Stage 2 (post-open, e.g. 09:35 ET): recalibrate_trade_params pulls the real
# 09:35 price from yfinance intraday bars, recomputes entry/SL/TP against the
# true open, and either:
#   - Updates the recommendation in place (if gap-up/down is tolerable), OR
#   - Marks it "aborted" (entry/SL/TP zeroed + _rejected flag) if the stock
#     gapped more than the configured tolerance vs Stage 1 reference.
# ---------------------------------------------------------------------------

_GAP_ABORT_THRESHOLD = 0.03  # 3% gap vs stage-1 reference -> abort


def _fetch_open_price(ticker: str, market: str) -> float | None:
    """Return the 09:35 ET price (close of the first 5-minute bar).

    Falls back to regularMarketOpen / last_price if intraday bars are
    unavailable. Returns None on any failure.
    """
    from core.data_source import to_yf_ticker
    symbol = to_yf_ticker(ticker, market)
    try:
        t = yf.Ticker(symbol)
        # Try 5-minute bars first; yfinance returns OHLCV for the current
        # trading session when called intraday.
        intraday = t.history(period="1d", interval="5m")
        if intraday is not None and not intraday.empty:
            # Close of the first 5-min bar is the 09:35 ET price
            return float(intraday["Close"].iloc[0])
        # Fallback: regular market open from fast_info
        info = t.fast_info
        op = getattr(info, "open", None) or getattr(info, "last_price", None)
        return float(op) if op else None
    except Exception as e:
        logger.debug(f"open price fetch failed {symbol}: {e}")
        return None


def recalibrate_trade_params(
    market: str = "us_stock",
    ref_date: str | None = None,
    gap_abort_threshold: float = _GAP_ABORT_THRESHOLD,
) -> dict:
    """Stage 2 of the two-stage entry pricing.

    Re-prices every published recommendation for today using the real
    post-open price, then writes the new entry/SL/TP back into the DB and
    replaces the pending win_rate_records so win-rate tracking uses realistic
    targets.

    Returns a summary dict for logging / API consumption.
    """
    if market != "us_stock":
        logger.info(f"recalibrate: skipping non-US market {market}")
        return {"market": market, "skipped": "non_us"}

    if ref_date is None:
        ref_date = _ref_date_for_market(market)

    from pipeline.agents import _compute_trade_params, _compute_short_trade_params
    cfg = get_config()

    db = Database(SYSTEM_DB_PATH)
    try:
        # Read admin (daily) + published recommendations for today
        admin_run, admin_items = db.get_daily_recommendations(ref_date, market=market)
        pub_run, pub_items = db.get_published_recommendations(ref_date, market=market)

        if not admin_items and not pub_items:
            logger.info(f"recalibrate: no recommendations to recalibrate for {ref_date}/{market}")
            return {"market": market, "ref_date": ref_date, "recalibrated": 0,
                    "aborted": 0, "skipped": "no_items"}

        # Snapshot Stage-1 reference prices from the current rows so we can
        # detect gap abort. `price` column holds the Stage-1 quote.
        stage1_prices: dict[str, float] = {}
        for it in admin_items:
            try:
                stage1_prices[it["ticker"]] = float(it.get("price") or 0)
            except (TypeError, ValueError):
                pass

        stats = {"recalibrated": 0, "aborted_gap": 0, "aborted_price_fail": 0,
                 "unchanged": 0}
        updated_admin: list[dict] = []

        for it in admin_items:
            ticker = it["ticker"]
            item = dict(it)  # copy

            open_price = _fetch_open_price(ticker, market)
            stage1_price = stage1_prices.get(ticker, 0)

            # Price fetch failed entirely -> keep Stage-1 params but mark
            # with a warning flag so the UI can show "no recalibration"
            if open_price is None or open_price <= 0:
                item["_recalibrated"] = False
                item["_recalibration_status"] = "price_unavailable"
                stats["aborted_price_fail"] += 1
                updated_admin.append(item)
                continue

            # Gap check: if open deviated > threshold from Stage-1 reference,
            # abort. ATR-based targets are no longer reliable.
            if stage1_price > 0:
                gap = abs(open_price - stage1_price) / stage1_price
                if gap > gap_abort_threshold:
                    item["_recalibrated"] = False
                    item["_recalibration_status"] = "gap_abort"
                    item["_gap_pct"] = round(gap * 100, 2)
                    # Zero out trade params so evaluator / UI treat as
                    # rejected and do not track win-rate against stale numbers
                    item["entry_price"] = 0
                    item["entry_2"] = 0
                    item["stop_loss"] = 0
                    item["take_profit"] = 0
                    item["take_profit_2"] = 0
                    item["take_profit_3"] = 0
                    stats["aborted_gap"] += 1
                    updated_admin.append(item)
                    logger.warning(
                        f"recalibrate abort {ticker}: gap={gap*100:.2f}% "
                        f"(stage1={stage1_price:.2f} open={open_price:.2f})"
                    )
                    continue

            # Normal recalibration path
            strategy = str(item.get("strategy", "short_term"))
            strategy_type = "swing" if strategy == "swing" else "short"
            action = str(item.get("action", "buy"))
            direction = str(item.get("direction", "buy"))
            is_breakout = bool(item.get("is_breakout", False))
            regime_level = str(item.get("regime_level", "normal"))

            # Rebuild the minimal enriched dict _compute_trade_params needs.
            enriched = {
                "ma20": item.get("ma20"),
                "atr_20d": item.get("atr_20d"),
                "volatility_class": item.get("volatility_class", "medium"),
                "support_levels": _maybe_json_list(item.get("support_levels")),
                "resistance_levels": _maybe_json_list(item.get("resistance_levels")),
                "support_hold_strength": item.get("support_hold_strength", "untested"),
            }

            try:
                if direction == "short":
                    params = _compute_short_trade_params(
                        open_price, enriched,
                        strategy_type=strategy_type,
                        regime_level=regime_level,
                    )
                else:
                    params = _compute_trade_params(
                        open_price, enriched,
                        action=action,
                        strategy_type=strategy_type,
                        is_breakout=is_breakout,
                        regime_level=regime_level,
                    )
            except Exception as e:
                logger.warning(f"recalibrate compute failed {ticker}: {e}")
                item["_recalibrated"] = False
                item["_recalibration_status"] = "compute_failed"
                updated_admin.append(item)
                continue

            # Write new prices back; preserve everything else
            item["price"] = round(open_price, 4)
            item["entry_price"] = params.get("entry_price", 0)
            item["entry_2"] = params.get("entry_2", 0)
            item["stop_loss"] = params.get("stop_loss", 0)
            item["take_profit"] = params.get("take_profit", 0)
            item["take_profit_2"] = params.get("take_profit_2", 0)
            item["take_profit_3"] = params.get("take_profit_3", 0)
            item["holding_days"] = params.get(
                "holding_days", item.get("holding_days"))
            item["trailing_activation_price"] = params.get(
                "trailing_activation_price", item.get("trailing_activation_price"))
            item["trailing_distance_pct"] = params.get(
                "trailing_distance_pct", item.get("trailing_distance_pct"))
            item["_recalibrated"] = True
            item["_recalibration_status"] = "ok"
            if params.get("_rejected"):
                # Recalibrated but R:R no longer viable -> zero params
                item["entry_price"] = 0
                item["stop_loss"] = 0
                item["take_profit"] = 0
                item["_recalibration_status"] = "rr_rejected_post_open"
                stats["aborted_gap"] += 1  # accounted in aborted bucket
            else:
                stats["recalibrated"] += 1
            updated_admin.append(item)

        # Persist: overwrite both daily + published rows with refreshed items.
        # save_daily_recommendation_run already does DELETE+INSERT atomically.
        _meta = {
            "strategy": (admin_run or {}).get("strategy", "dual"),
            "source_count": (admin_run or {}).get("source_count", 0),
            "candidate_count": (admin_run or {}).get("candidate_count", 0),
            "trigger_source": "recalibration",
            "trigger_note": f"stage2_open_recalibration @ {datetime.now().isoformat()}",
        }
        db.save_daily_recommendation_run(ref_date, market, updated_admin, **_meta)

        # Re-publish with the new items
        _admin_run_refreshed, _admin_items_refreshed = db.get_daily_recommendations(
            ref_date, market=market)
        if _admin_run_refreshed:
            db.publish_recommendations(ref_date, market,
                                       _admin_run_refreshed, _admin_items_refreshed)

        # Reset pending win-rate records for today and re-insert with new numbers
        deleted = db.delete_pending_win_rate_records(ref_date, market)
        _wr_inserted = 0
        st = cfg.short_term
        for it in _admin_items_refreshed:
            ep = it.get("entry_price")
            slp = it.get("stop_loss")
            tpp = it.get("take_profit")
            if not ep or not slp or not tpp:
                continue
            try:
                themes = it.get("themes", [])
                if isinstance(themes, str):
                    try:
                        themes = json.loads(themes) if themes.strip() else []
                    except Exception:
                        themes = []
                elif themes is None:
                    themes = []
                sector = themes[0] if themes else ""
                db.save_win_rate_record({
                    "run_date": ref_date,
                    "ticker": it["ticker"],
                    "name": it["name"],
                    "market": it["market"],
                    "strategy": it.get("strategy", "short_term"),
                    "direction": it.get("direction", "buy"),
                    "entry_price": float(it.get("entry_price") or 0),
                    "stop_loss": float(it.get("stop_loss") or 0),
                    "take_profit": float(it.get("take_profit") or 0),
                    "holding_days": int(it.get("holding_days")
                                        or st.default_holding_days),
                    "news_score": it.get("news_score", 0),
                    "tech_score": it.get("tech_score", 0),
                    "fundamental_score": it.get("fundamental_score", 0),
                    "combined_score": it.get("combined_score", 0),
                    "confidence": it.get("confidence", 0),
                    "sector": sector,
                })
                _wr_inserted += 1
            except Exception as e:
                logger.warning(f"recalibrate win_rate reinsert {it.get('ticker')}: {e}")

        logger.info(
            f"Recalibration {ref_date}/{market}: "
            f"recalibrated={stats['recalibrated']}, "
            f"aborted_gap={stats['aborted_gap']}, "
            f"aborted_price_fail={stats['aborted_price_fail']}, "
            f"win_rate deleted_pending={deleted} reinserted={_wr_inserted}"
        )
        return {
            "market": market,
            "ref_date": ref_date,
            **stats,
            "win_rate_deleted": deleted,
            "win_rate_reinserted": _wr_inserted,
        }
    finally:
        db.close()


def _maybe_json_list(val) -> list:
    """Accept either list, JSON string, or None; return list."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []
