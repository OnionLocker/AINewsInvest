"""Fundamental scoring for US/HK equities from yfinance-backed financial data."""
from __future__ import annotations

from typing import Any

from loguru import logger

from core.data_source import get_financial_data


def _to_pct_margin_roe(val: float | None) -> float | None:
    if val is None:
        return None
    v = float(val)
    if abs(v) <= 1.5:
        return v * 100.0
    return v


def _to_pct_growth(val: float | None) -> float | None:
    if val is None:
        return None
    v = float(val)
    if abs(v) < 10:
        return v * 100.0
    return v


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _score_roe_pct(roe: float | None) -> float:
    if roe is None:
        return 0.0
    if roe < 0:
        return 0.0
    return 10.0 * _clamp(roe / 25.0, 0.0, 1.0)


def _score_margin_pct(m: float | None, weight: float, excellent: float) -> float:
    if m is None:
        return 0.0
    if m < 0:
        return 0.0
    return weight * _clamp(m / excellent, 0.0, 1.0)


def _score_profitability(
    roe: float | None,
    gross: float | None,
    net: float | None,
    op: float | None,
) -> float:
    s = _score_roe_pct(roe)
    s += _score_margin_pct(gross, 7.0, 45.0)
    s += _score_margin_pct(net, 7.0, 25.0)
    s += _score_margin_pct(op, 6.0, 30.0)
    return _clamp(s, 0.0, 30.0)


def _score_safety(
    debt_to_equity: float | None,
    current_ratio: float | None,
    debt_trend_up: bool,
) -> float:
    s = 0.0
    if debt_to_equity is not None:
        de = float(debt_to_equity)
        if de <= 30:
            s += 12.0
        elif de <= 80:
            s += 12.0 * (1.0 - (de - 30) / 50.0 * 0.5)
        elif de <= 200:
            s += 6.0 * (1.0 - (de - 80) / 120.0)
        else:
            s += 0.0
    else:
        s += 6.0
    if current_ratio is not None:
        cr = float(current_ratio)
        if cr >= 2.0:
            s += 12.0
        elif cr >= 1.5:
            s += 10.0
        elif cr >= 1.0:
            s += 7.0
        elif cr > 0:
            s += 4.0 * _clamp(cr, 0.0, 1.0)
    else:
        s += 6.0
    if debt_trend_up:
        s -= 4.0
    return _clamp(s, 0.0, 30.0)


def _score_growth(rev: float | None, earn: float | None) -> float:
    def g(v: float | None) -> float:
        if v is None:
            return 5.0
        x = float(v)
        if x >= 15:
            return 10.0
        if x >= 5:
            return 7.0 + 3.0 * (x - 5) / 10.0
        if x >= 0:
            return 4.0 + 3.0 * (x / 5.0)
        if x >= -10:
            return 4.0 * (1.0 + x / 10.0)
        return 0.0

    return _clamp(g(rev) + g(earn), 0.0, 20.0)


def _estimate_net_income(data: dict[str, Any]) -> float | None:
    rev = data.get("total_revenue")
    pm = data.get("profit_margins")
    if rev is None or pm is None:
        return None
    try:
        r, p = float(rev), float(pm)
        if r <= 0:
            return None
        if abs(p) <= 1.5:
            return r * p
        return r * (p / 100.0)
    except (TypeError, ValueError):
        return None


def _score_earnings_quality(fcf: float | None, ni: float | None) -> float:
    if fcf is None or ni is None or ni == 0:
        return 10.0
    ratio = float(fcf) / float(ni)
    if ratio >= 1.0:
        return 20.0
    if ratio >= 0.7:
        return 16.0 + 4.0 * (ratio - 0.7) / 0.3
    if ratio >= 0.4:
        return 10.0 + 6.0 * (ratio - 0.4) / 0.3
    if ratio >= 0:
        return 10.0 * (ratio / 0.4)
    return 0.0


def _debt_trend(indicators: list[dict[str, Any]] | None) -> tuple[bool, float | None]:
    if not indicators:
        return False, None
    pairs = [(e.get("year"), e.get("debt_ratio")) for e in indicators if e.get("debt_ratio") is not None]
    if len(pairs) < 2:
        return False, pairs[-1][1] if pairs else None
    pairs.sort(key=lambda x: x[0] or 0)
    ratios = [float(p[1]) for p in pairs]
    latest = ratios[-1]
    older = sum(ratios[:-1]) / (len(ratios) - 1)
    return latest > older + 2.0, latest


def _quality_label(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Average"
    if score >= 35:
        return "Poor"
    return "Risky"


def _build_summary(
    label: str,
    score: int,
    profitability: dict[str, Any],
    safety: dict[str, Any],
    growth: dict[str, Any],
    flags: list[str],
) -> str:
    parts = [
        f"Fundamental score {score}/100; quality label: {label}. ",
    ]
    r = profitability.get("roe")
    g = profitability.get("gross_margin")
    n = profitability.get("net_margin")
    if r is not None or g is not None or n is not None:
        bits = []
        if r is not None:
            bits.append(f"ROE ~{r:.1f}%")
        if g is not None:
            bits.append(f"gross margin ~{g:.1f}%")
        if n is not None:
            bits.append(f"net margin ~{n:.1f}%")
        parts.append("Profitability: " + ", ".join(bits) + ". ")
    de = safety.get("debt_to_equity")
    cr = safety.get("current_ratio")
    if de is not None or cr is not None:
        sb = []
        if de is not None:
            sb.append(f"D/E ~{de:.1f}")
        if cr is not None:
            sb.append(f"current ratio ~{cr:.2f}")
        parts.append("Safety: " + ", ".join(sb) + ". ")
    rg = growth.get("revenue_growth")
    eg = growth.get("earnings_growth")
    if rg is not None or eg is not None:
        gb = []
        if rg is not None:
            gb.append(f"revenue growth ~{rg:+.1f}%")
        if eg is not None:
            gb.append(f"earnings growth ~{eg:+.1f}%")
        parts.append("Growth: " + ", ".join(gb) + ". ")
    if flags:
        parts.append("Risk flags: " + "; ".join(flags) + ". ")
    return "".join(parts)


def analyze(ticker: str, market: str) -> dict[str, Any] | None:
    data = get_financial_data(ticker, market)
    if not data:
        logger.warning(f"No financial data for {market}:{ticker}")
        return None

    roe = _to_pct_margin_roe(data.get("roe"))
    gross_margin = _to_pct_margin_roe(data.get("gross_margins"))
    net_margin = _to_pct_margin_roe(data.get("profit_margins"))
    operating_margin = _to_pct_margin_roe(data.get("operating_margins"))

    debt_to_equity = data.get("debt_to_equity")
    if debt_to_equity is not None:
        debt_to_equity = float(debt_to_equity)
    current_ratio = data.get("current_ratio")
    if current_ratio is not None:
        current_ratio = float(current_ratio)

    revenue_growth = _to_pct_growth(data.get("revenue_growth"))
    earnings_growth = _to_pct_growth(data.get("earnings_growth"))

    debt_trend_up, indicator_debt_ratio = _debt_trend(data.get("indicators"))

    fcf = data.get("free_cashflow")
    if fcf is not None:
        fcf = float(fcf)
    ni = _estimate_net_income(data)

    p_score = _score_profitability(roe, gross_margin, net_margin, operating_margin)
    s_score = _score_safety(debt_to_equity, current_ratio, debt_trend_up)
    g_score = _score_growth(revenue_growth, earnings_growth)
    q_score = _score_earnings_quality(fcf, ni)
    total = int(round(_clamp(p_score + s_score + g_score + q_score, 0.0, 100.0)))

    flags: list[str] = []
    if debt_to_equity is not None and debt_to_equity > 200:
        flags.append("High debt-to-equity")
    if indicator_debt_ratio is not None and indicator_debt_ratio > 60:
        flags.append("High debt-to-assets")
    if debt_trend_up:
        flags.append("Rising leverage trend")
    if current_ratio is not None and current_ratio < 1.0:
        flags.append("Low current ratio")
    if revenue_growth is not None and revenue_growth < 0:
        flags.append("Negative revenue growth")
    if earnings_growth is not None and earnings_growth < 0:
        flags.append("Negative earnings growth")
    if net_margin is not None and net_margin < 0:
        flags.append("Negative net margin")
    if roe is not None and roe < 0:
        flags.append("Negative ROE")
    if fcf is not None and ni is not None and ni > 0 and fcf < 0:
        flags.append("Negative free cash flow")
    if fcf is not None and ni is not None and ni > 0:
        if fcf / ni < 0.5:
            flags.append("Free cash flow well below net income")

    debt_ratio = indicator_debt_ratio

    label = _quality_label(total)
    profitability = {
        "roe": roe,
        "gross_margin": gross_margin,
        "net_margin": net_margin,
        "operating_margin": operating_margin,
    }
    safety = {"debt_to_equity": debt_to_equity, "current_ratio": current_ratio}
    growth = {"revenue_growth": revenue_growth, "earnings_growth": earnings_growth}
    summary = _build_summary(label, total, profitability, safety, growth, flags)

    logger.debug(f"Fundamental {market}:{ticker} score={total} label={label}")

    return {
        "ticker": ticker,
        "market": market,
        "quality_score": total,
        "quality_label": label,
        "profitability": profitability,
        "safety": safety,
        "growth": growth,
        "risk_flags": flags,
        "fundamental_summary": summary,
        "roe": roe,
        "gross_margin": gross_margin,
        "debt_ratio": debt_ratio,
        "revenue_growth": revenue_growth,
    }
