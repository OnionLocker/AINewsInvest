"""US/HK stock floor valuation helpers."""
from __future__ import annotations

from typing import Any

from loguru import logger

_DDM_REQUIRED_RETURN = 0.10
_FCF_CAP_RATE = 0.12
_PENETRATION_A = 12.0
_PENETRATION_B = 6.0


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _floor_bvps(fin: dict) -> float | None:
    bv = _f(fin.get("book_value"))
    if bv is None or bv <= 0:
        return None
    return bv


def _floor_ddm(fin: dict, current_price: float) -> float | None:
    y = _f(fin.get("dividend_yield"))
    if y is None or y <= 0 or current_price <= 0:
        return None
    dps = current_price * y
    return dps / _DDM_REQUIRED_RETURN


def _floor_fcf_cap(fin: dict) -> float | None:
    fcf = _f(fin.get("free_cashflow"))
    sh = _f(fin.get("shares_outstanding"))
    if fcf is None or sh is None or sh <= 0 or fcf <= 0:
        return None
    fcf_ps = fcf / sh
    return fcf_ps / _FCF_CAP_RATE


def _penetration_grade(pct: float) -> str:
    if pct >= _PENETRATION_A:
        return "A"
    if pct >= _PENETRATION_B:
        return "B"
    return "C"


def _pe_pb_summary(pe: float | None, pb: float | None) -> str:
    parts: list[str] = []
    if pe is not None and pe > 0:
        if pe < 12:
            parts.append(f"PE(TTM)≈{pe:.1f} 相对偏低")
        elif pe > 28:
            parts.append(f"PE(TTM)≈{pe:.1f} 相对偏高")
        else:
            parts.append(f"PE(TTM)≈{pe:.1f} 处于常见区间")
    else:
        parts.append("PE(TTM)缺失或为负，不宜直接横向比较")
    if pb is not None and pb > 0:
        if pb < 1.0:
            parts.append(f"PB≈{pb:.2f} 低于账面折价区间")
        elif pb > 3.0:
        parts.append(f"PB={pb:.2f} 高于常规价值区间")
        else:
            parts.append(f"PB≈{pb:.2f} 处于常见区间")
    else:
        parts.append("PB缺失，需结合资产质量判断")
        return "; ".join(parts)


def valuate(financial_data: dict, current_price: float) -> dict | None:
    if not financial_data:
        return None
    price = _f(current_price)
    if price is None or price <= 0:
        logger.debug("valuate: invalid current_price")
        return None

    floors: list[float] = []
    b = _floor_bvps(financial_data)
    if b is not None:
        floors.append(b)
    d = _floor_ddm(financial_data, price)
    if d is not None:
        floors.append(d)
    fcfp = _floor_fcf_cap(financial_data)
    if fcfp is not None:
        floors.append(fcfp)

    if not floors:
        logger.debug("valuate: no floor components")
        return None

    floor_price = sum(floors) / len(floors)
    safety_margin = (floor_price - price) / price * 100.0

    fcf = _f(financial_data.get("free_cashflow"))
    sh = _f(financial_data.get("shares_outstanding"))
    oe_ps: float | None = None
    if fcf is not None and sh is not None and sh > 0:
        oe_ps = fcf / sh
    pen_pct: float | None = None
    pen_grade: str | None = None
    if oe_ps is not None and oe_ps > 0:
        pen_pct = oe_ps / price * 100.0
        pen_grade = _penetration_grade(pen_pct)

    pe_ttm = _f(financial_data.get("pe_ttm"))
    pb = _f(financial_data.get("pb"))

    return {
        "floor_price": round(floor_price, 4),
        "safety_margin": round(safety_margin, 2),
        "penetration_return": {
            "return_pct": round(pen_pct, 2) if pen_pct is not None else None,
            "grade": pen_grade,
        },
        "pe_ttm": pe_ttm,
        "pb": pb,
        "valuation_summary": _pe_pb_summary(pe_ttm, pb),
    }
