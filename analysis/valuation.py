"""
analysis/valuation.py - 估值引擎

职责: 基于财务数据和市场价格, 计算多维度估值指标与安全边际。
     本模块不获取数据, 所有数据通过参数传入。

公开接口:
    valuate(financial_data, current_price) -> dict | None

估值方法来源:
    - 地板价 5 种方法 (龟龟框架 screener_core.py)
    - 穿透回报率 / Owner Earnings (龟龟框架 Phase 3)
    - 安全边际计算
"""
from utils.logger import app_logger


# ══════════════════════════════════════════════════════════════
# 公开接口
# ══════════════════════════════════════════════════════════════

def valuate(financial_data: dict, current_price: float) -> dict | None:
    """
    对标的进行估值分析。

    参数:
        financial_data: data.financial.get_financial_data() 的返回值
        current_price:  当前股价 (本币)

    返回:
    {
        "ticker", "market",
        "floor_price": {
            "net_current_asset": float|None,   # 方法1: 净流动资产/股
            "bvps": float|None,                # 方法2: 每股净资产
            "dividend_discount": float|None,   # 方法3: 股息折现
            "pessimistic_fcf": float|None,     # 方法4: 悲观FCF资本化
            "average": float|None,             # 有效方法的平均
        },
        "penetration_return": {
            "owner_earnings_per_share": float|None,
            "rate": float|None,                # %
            "grade": str,                      # "A" / "B" / "C" / "N/A"
        },
        "ev_ebitda": {
            "value": float|None,
        },
        "safety_margin": {
            "current_price": float,
            "floor_price": float|None,
            "margin_pct": float|None,          # %
            "verdict": str,
        },
        "valuation_summary": str,
    }
    失败返回 None。
    """
    if not financial_data or not financial_data.get("indicators"):
        return None
    if not current_price or current_price <= 0:
        return None

    try:
        return _valuate_core(financial_data, current_price)
    except Exception as e:
        app_logger.warning(
            f"[估值] 分析失败 {financial_data.get('ticker')}: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# 核心估值逻辑
# ══════════════════════════════════════════════════════════════

def _valuate_core(data: dict, price: float) -> dict:
    indicators = data["indicators"]
    market_info = data.get("market_info", {})
    dividends = data.get("dividends", [])
    latest = indicators[0]

    total_shares_yi = market_info.get("total_shares_yi")
    total_shares = total_shares_yi * 1e8 if total_shares_yi else None

    floor = _calc_floor_price(indicators, dividends, total_shares)
    penetration = _calc_penetration_return(indicators, price, total_shares)
    ev_ebitda = _calc_ev_ebitda(market_info, latest)
    safety = _calc_safety_margin(price, floor.get("average"))

    result = {
        "ticker": data["ticker"],
        "market": data["market"],
        "floor_price": floor,
        "penetration_return": penetration,
        "ev_ebitda": ev_ebitda,
        "safety_margin": safety,
        "valuation_summary": "",
    }
    result["valuation_summary"] = _build_summary(result)
    return result


# ══════════════════════════════════════════════════════════════
# 地板价计算 (4 种方法)
# ══════════════════════════════════════════════════════════════

def _calc_floor_price(indicators: list[dict], dividends: list[dict],
                      total_shares: float | None) -> dict:
    result = {
        "net_current_asset": None,
        "bvps": None,
        "dividend_discount": None,
        "pessimistic_fcf": None,
        "average": None,
    }

    latest = indicators[0] if indicators else {}

    # 方法1: 净流动资产/股 = (流动资产 - 总负债) / 总股本
    ca = latest.get("current_assets")
    td = latest.get("total_debt")
    if ca is not None and td is not None and total_shares and total_shares > 0:
        nca = (ca - td) * 1e4 / total_shares
        result["net_current_asset"] = round(nca, 2) if nca > 0 else 0

    # 方法2: 每股净资产 (BVPS)
    bvps = latest.get("bvps")
    if bvps is not None and bvps > 0:
        result["bvps"] = round(bvps, 2)

    # 方法3: 股息折现 = 近3年平均每股股利 / 无风险利率
    RISK_FREE_RATE = 0.025
    recent_divs = [d["dps"] for d in dividends[:3] if d.get("dps") and d["dps"] > 0]
    if recent_divs:
        avg_dps = sum(recent_divs) / len(recent_divs)
        result["dividend_discount"] = round(avg_dps / RISK_FREE_RATE, 2)

    # 方法4: 悲观FCF资本化
    # FCF ≈ 净利润 × OCF/利润比 (简化, 未扣除 CapEx, 留待 Phase 2 增强)
    # 取近3年最低 FCF 近似值 / (无风险利率 + 风险溢价)
    DISCOUNT_RATE = RISK_FREE_RATE + 0.03
    fcf_estimates = []
    for ind in indicators[:3]:
        np_val = ind.get("net_profit")
        ocf_r = ind.get("ocf_to_profit")
        if np_val is not None and ocf_r is not None and ocf_r > 0:
            fcf_approx = np_val * min(ocf_r, 1.0)
            fcf_estimates.append(fcf_approx)
    if fcf_estimates and total_shares and total_shares > 0:
        min_fcf = min(fcf_estimates)
        if min_fcf > 0:
            result["pessimistic_fcf"] = round(
                min_fcf * 1e4 / total_shares / DISCOUNT_RATE, 2)

    # 平均地板价
    valid = [v for v in result.values() if isinstance(v, (int, float)) and v > 0]
    if valid:
        result["average"] = round(sum(valid) / len(valid), 2)

    return result


# ══════════════════════════════════════════════════════════════
# 穿透回报率
# ══════════════════════════════════════════════════════════════

def _calc_penetration_return(indicators: list[dict], price: float,
                             total_shares: float | None) -> dict:
    """
    穿透回报率 = Owner Earnings / 市值
    Owner Earnings ≈ 净利润 × min(OCF/利润比, 1.0)
    (简化版: 未单独扣除维护性 CapEx, 用 OCF/利润比作为近似)
    """
    empty = {"owner_earnings_per_share": None, "rate": None, "grade": "N/A"}

    if not total_shares or total_shares <= 0 or price <= 0:
        return empty

    latest = indicators[0] if indicators else {}
    np_val = latest.get("net_profit")
    ocf_r = latest.get("ocf_to_profit")

    if np_val is None:
        return empty

    ocf_factor = min(ocf_r, 1.2) if ocf_r is not None and ocf_r > 0 else 0.7
    owner_earnings = np_val * ocf_factor * 1e4
    oe_per_share = owner_earnings / total_shares
    market_cap = price * total_shares
    rate = (owner_earnings / market_cap) * 100 if market_cap > 0 else None

    if rate is None:
        grade = "N/A"
    elif rate >= 15:
        grade = "A"
    elif rate >= 8:
        grade = "B"
    else:
        grade = "C"

    return {
        "owner_earnings_per_share": round(oe_per_share, 2),
        "rate": round(rate, 2) if rate is not None else None,
        "grade": grade,
    }


# ══════════════════════════════════════════════════════════════
# EV/EBITDA (简化)
# ══════════════════════════════════════════════════════════════

def _calc_ev_ebitda(market_info: dict, latest_ind: dict) -> dict:
    """
    EV/EBITDA 简化计算
    EV = 市值 + 净负债
    EBITDA ≈ 净利润 / 净利率 × (1 + 折旧摊销估算)
    由于缺少精确折旧数据, 此处用 PE 的 0.7-0.85 倍做粗略估算
    """
    pe = market_info.get("pe_ttm")
    if pe is not None and pe > 0:
        ev_ebitda_approx = pe * 0.75
        return {"value": round(ev_ebitda_approx, 1)}
    return {"value": None}


# ══════════════════════════════════════════════════════════════
# 安全边际
# ══════════════════════════════════════════════════════════════

def _calc_safety_margin(current_price: float,
                        floor_price: float | None) -> dict:
    if floor_price is None or floor_price <= 0:
        return {
            "current_price": current_price,
            "floor_price": None,
            "margin_pct": None,
            "verdict": "数据不足",
        }

    margin = (floor_price - current_price) / current_price * 100

    if margin >= 30:
        verdict = "充足"
    elif margin >= 10:
        verdict = "适中"
    elif margin >= 0:
        verdict = "不足"
    else:
        verdict = "溢价"

    return {
        "current_price": round(current_price, 2),
        "floor_price": round(floor_price, 2),
        "margin_pct": round(margin, 1),
        "verdict": verdict,
    }


# ══════════════════════════════════════════════════════════════
# 文字总结
# ══════════════════════════════════════════════════════════════

def _build_summary(result: dict) -> str:
    parts = []
    pr = result["penetration_return"]
    sm = result["safety_margin"]
    fp = result["floor_price"]
    ev = result["ev_ebitda"]

    # 穿透回报率
    rate = pr.get("rate")
    grade = pr.get("grade", "N/A")
    if rate is not None:
        grade_zh = {"A": "极具吸引力", "B": "合理偏低估", "C": "一般"}.get(grade, "")
        parts.append(f"穿透回报率{rate:.1f}%（{grade_zh}）。")

    # 地板价
    avg_fp = fp.get("average")
    if avg_fp is not None:
        parts.append(f"综合地板价{avg_fp:.2f}，")

    # 安全边际
    margin = sm.get("margin_pct")
    verdict = sm.get("verdict", "")
    if margin is not None:
        if margin >= 0:
            parts.append(f"安全边际{margin:.0f}%（{verdict}）。")
        else:
            parts.append(f"当前溢价{abs(margin):.0f}%。")

    # EV/EBITDA
    ev_val = ev.get("value")
    if ev_val is not None:
        if ev_val < 8:
            parts.append(f"EV/EBITDA约{ev_val:.0f}倍，估值偏低。")
        elif ev_val < 15:
            parts.append(f"EV/EBITDA约{ev_val:.0f}倍，估值合理。")
        else:
            parts.append(f"EV/EBITDA约{ev_val:.0f}倍，估值偏高。")

    return "".join(parts) if parts else "估值数据不足，无法生成完整评估。"
