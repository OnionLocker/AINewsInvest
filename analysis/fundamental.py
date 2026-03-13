"""
analysis/fundamental.py - 基本面分析引擎

职责: 基于财务数据计算质量评分、成长性、盈利能力、安全性指标。
     本模块不获取数据, 数据通过 data.financial 提供。

公开接口:
    analyze(ticker, market) -> dict | None

依赖:
    data.financial.get_financial_data  (仅在 analyze() 入口处调用)
"""
from utils.logger import app_logger


# ══════════════════════════════════════════════════════════════
# 公开接口
# ══════════════════════════════════════════════════════════════

def analyze(ticker: str, market: str) -> dict | None:
    """
    基本面分析入口。

    返回:
    {
        "ticker", "market",
        "quality_score": int (0-100),
        "quality_label": str,
        "growth": { "revenue_cagr_3y", "profit_cagr_3y", "trend" },
        "profitability": { "roe_latest", "roe_avg_3y", "roe_trend", "gross_margin", "net_margin" },
        "safety": { "debt_ratio", "current_ratio", "ocf_healthy_years", "dividend_years" },
        "valuation_snapshot": { "pe_ttm", "pb", "dividend_yield" },
        "risk_flags": list[str],
        "fundamental_summary": str,
    }
    失败返回 None。
    """
    from data.financial import get_financial_data

    data = get_financial_data(ticker, market)
    if not data or not data.get("indicators"):
        return None

    try:
        return _analyze_data(data)
    except Exception as e:
        app_logger.warning(f"[基本面] 分析失败 {market}:{ticker}: {e}")
        return None


def analyze_from_data(data: dict) -> dict | None:
    """接受预获取的财务数据进行分析, 用于测试或高级场景。"""
    if not data or not data.get("indicators"):
        return None
    return _analyze_data(data)


# ══════════════════════════════════════════════════════════════
# 核心分析逻辑
# ══════════════════════════════════════════════════════════════

def _analyze_data(data: dict) -> dict:
    indicators = data["indicators"]
    dividends = data.get("dividends", [])
    market_info = data.get("market_info", {})

    prof_score, profitability = _score_profitability(indicators)
    grow_score, growth = _score_growth(indicators)
    safe_score, safety = _score_safety(indicators, dividends)
    qual_score, _ = _score_earnings_quality(indicators)

    total = prof_score + grow_score + safe_score + qual_score
    total = max(0, min(100, total))

    if total >= 80:
        label = "优秀"
    elif total >= 60:
        label = "良好"
    elif total >= 40:
        label = "一般"
    else:
        label = "较差"

    risk_flags = _detect_risks(indicators, market_info)

    valuation_snapshot = {
        "pe_ttm": market_info.get("pe_ttm"),
        "pb": market_info.get("pb"),
        "dividend_yield": market_info.get("dividend_yield_ttm"),
    }

    result = {
        "ticker": data["ticker"],
        "market": data["market"],
        "quality_score": total,
        "quality_label": label,
        "growth": growth,
        "profitability": profitability,
        "safety": safety,
        "valuation_snapshot": valuation_snapshot,
        "risk_flags": risk_flags,
        "fundamental_summary": "",
    }
    result["fundamental_summary"] = _build_summary(result)
    return result


# ══════════════════════════════════════════════════════════════
# 盈利能力评分 (满分 30)
# ══════════════════════════════════════════════════════════════

def _score_profitability(indicators: list[dict]) -> tuple[int, dict]:
    score = 0
    latest = indicators[0] if indicators else {}
    roe_latest = latest.get("roe")
    gm = latest.get("gross_margin")
    nm = latest.get("net_margin")

    # ROE 评分 (0-20)
    if roe_latest is not None:
        if roe_latest >= 20:
            score += 20
        elif roe_latest >= 15:
            score += 16
        elif roe_latest >= 10:
            score += 12
        elif roe_latest >= 5:
            score += 6

    # 毛利率评分 (0-5)
    if gm is not None:
        if gm >= 40:
            score += 5
        elif gm >= 25:
            score += 3
        elif gm >= 15:
            score += 1

    # 净利率评分 (0-5)
    if nm is not None:
        if nm >= 20:
            score += 5
        elif nm >= 10:
            score += 3
        elif nm >= 5:
            score += 1

    # ROE 趋势
    roe_vals = _get_series(indicators, "roe", 3)
    roe_avg = _avg(roe_vals)
    roe_trend = _calc_trend(roe_vals)

    return score, {
        "roe_latest": roe_latest,
        "roe_avg_3y": roe_avg,
        "roe_trend": roe_trend,
        "gross_margin": gm,
        "net_margin": nm,
    }


# ══════════════════════════════════════════════════════════════
# 成长性评分 (满分 20)
# ══════════════════════════════════════════════════════════════

def _score_growth(indicators: list[dict]) -> tuple[int, dict]:
    score = 0
    rev_cagr = _calc_cagr(indicators, "revenue", 3)
    prof_cagr = _calc_cagr(indicators, "net_profit", 3)

    # 营收 CAGR 评分 (0-10)
    if rev_cagr is not None:
        if rev_cagr >= 20:
            score += 10
        elif rev_cagr >= 10:
            score += 7
        elif rev_cagr >= 5:
            score += 4
        elif rev_cagr >= 0:
            score += 1

    # 利润 CAGR 评分 (0-10)
    if prof_cagr is not None:
        if prof_cagr >= 20:
            score += 10
        elif prof_cagr >= 10:
            score += 7
        elif prof_cagr >= 5:
            score += 4
        elif prof_cagr >= 0:
            score += 1

    # 趋势判断
    rev_growths = _get_series(indicators, "revenue_growth", 3)
    if rev_cagr is not None and len(rev_growths) >= 2:
        if all(g is not None and g > 0 for g in rev_growths):
            if rev_growths[0] is not None and rev_growths[-1] is not None and rev_growths[0] > rev_growths[-1]:
                trend = "加速增长"
            else:
                trend = "稳定增长"
        elif rev_cagr > 0:
            trend = "放缓"
        else:
            trend = "下滑"
    elif rev_cagr is not None:
        trend = "增长" if rev_cagr > 0 else "下滑"
    else:
        trend = "数据不足"

    return score, {
        "revenue_cagr_3y": rev_cagr,
        "profit_cagr_3y": prof_cagr,
        "trend": trend,
    }


# ══════════════════════════════════════════════════════════════
# 安全性评分 (满分 30)
# ══════════════════════════════════════════════════════════════

def _score_safety(indicators: list[dict], dividends: list[dict]) -> tuple[int, dict]:
    score = 0
    latest = indicators[0] if indicators else {}
    dr = latest.get("debt_ratio")
    cr = latest.get("current_ratio")

    # 负债率评分 (0-10)
    if dr is not None:
        if dr <= 30:
            score += 10
        elif dr <= 45:
            score += 8
        elif dr <= 60:
            score += 5
        elif dr <= 70:
            score += 2

    # 流动比率评分 (0-5)
    if cr is not None:
        if cr >= 2.0:
            score += 5
        elif cr >= 1.5:
            score += 3
        elif cr >= 1.0:
            score += 1

    # 经营现金流健康年数 (0-10)
    ocf_vals = _get_series(indicators, "ocf_to_profit", 5)
    ocf_healthy = sum(1 for v in ocf_vals if v is not None and v > 0.5)
    if ocf_healthy >= 4:
        score += 10
    elif ocf_healthy >= 3:
        score += 7
    elif ocf_healthy >= 2:
        score += 3

    # 分红持续性评分 (0-5)
    div_years = sum(1 for d in dividends if d.get("dps") and d["dps"] > 0)
    if div_years >= 4:
        score += 5
    elif div_years >= 3:
        score += 3
    elif div_years >= 1:
        score += 1

    return score, {
        "debt_ratio": dr,
        "current_ratio": cr,
        "ocf_healthy_years": ocf_healthy,
        "dividend_years": div_years,
    }


# ══════════════════════════════════════════════════════════════
# 盈余质量评分 (满分 20)
# ══════════════════════════════════════════════════════════════

def _score_earnings_quality(indicators: list[dict]) -> tuple[int, dict]:
    score = 0
    latest = indicators[0] if indicators else {}

    # 经营现金流/净利润 (0-10)
    ocf_p = latest.get("ocf_to_profit")
    if ocf_p is not None:
        if ocf_p >= 1.0:
            score += 10
        elif ocf_p >= 0.8:
            score += 7
        elif ocf_p >= 0.5:
            score += 4
        elif ocf_p > 0:
            score += 1

    # ROE 稳定性 (0-10): 近3年标准差越小越好
    roe_vals = [v for v in _get_series(indicators, "roe", 3) if v is not None]
    if len(roe_vals) >= 2:
        avg = sum(roe_vals) / len(roe_vals)
        if avg > 0:
            std = (sum((v - avg) ** 2 for v in roe_vals) / len(roe_vals)) ** 0.5
            cv = std / avg
            if cv <= 0.1:
                score += 10
            elif cv <= 0.2:
                score += 7
            elif cv <= 0.3:
                score += 4
            else:
                score += 1

    return score, {}


# ══════════════════════════════════════════════════════════════
# 风险检测
# ══════════════════════════════════════════════════════════════

def _detect_risks(indicators: list[dict], market_info: dict) -> list[str]:
    flags = []
    if len(indicators) < 2:
        return flags

    # ROE 连续下滑
    roe_vals = _get_series(indicators, "roe", 3)
    if len(roe_vals) >= 3 and all(v is not None for v in roe_vals):
        if roe_vals[0] < roe_vals[1] < roe_vals[2]:
            flags.append("ROE连续下滑")

    # 高负债
    dr = indicators[0].get("debt_ratio")
    if dr is not None and dr > 70:
        flags.append("高负债")

    # 现金流告警
    ocf = indicators[0].get("ocf_to_profit")
    if ocf is not None and ocf < 0:
        flags.append("经营现金流为负")
    elif ocf is not None and ocf < 0.5:
        flags.append("现金流质量偏低")

    # 利润下滑
    pg = indicators[0].get("profit_growth")
    if pg is not None and pg < -20:
        flags.append("利润大幅下滑")

    # 营收下滑
    rg = indicators[0].get("revenue_growth")
    if rg is not None and rg < -10:
        flags.append("营收下滑")

    # 高估值警示
    pe = market_info.get("pe_ttm")
    if pe is not None and pe > 80:
        flags.append("PE偏高")
    pb = market_info.get("pb")
    if pb is not None and pb > 10:
        flags.append("PB偏高")

    return flags


# ══════════════════════════════════════════════════════════════
# 文字总结
# ══════════════════════════════════════════════════════════════

def _build_summary(result: dict) -> str:
    parts = []
    prof = result["profitability"]
    grow = result["growth"]
    safe = result["safety"]
    val = result["valuation_snapshot"]

    # 盈利能力
    roe = prof.get("roe_latest")
    if roe is not None:
        if roe >= 15:
            parts.append(f"盈利能力优秀，ROE {roe:.1f}%")
        elif roe >= 8:
            parts.append(f"盈利能力良好，ROE {roe:.1f}%")
        else:
            parts.append(f"盈利能力一般，ROE {roe:.1f}%")
        trend = prof.get("roe_trend", "")
        if trend == "改善":
            parts.append("且趋势改善")
        elif trend == "恶化":
            parts.append("且趋势走弱")
        parts.append("。")

    # 成长性
    trend = grow.get("trend", "")
    cagr = grow.get("revenue_cagr_3y")
    if cagr is not None and trend:
        parts.append(f"近3年营收复合增长{cagr:.1f}%，{trend}。")

    # 安全性
    dr = safe.get("debt_ratio")
    if dr is not None:
        if dr <= 45:
            parts.append(f"负债率{dr:.0f}%，财务稳健。")
        elif dr <= 65:
            parts.append(f"负债率{dr:.0f}%，处于合理水平。")
        else:
            parts.append(f"负债率{dr:.0f}%，偏高需关注。")

    ocf_y = safe.get("ocf_healthy_years", 0)
    if ocf_y >= 4:
        parts.append("经营现金流持续健康。")
    elif ocf_y <= 1:
        parts.append("经营现金流表现较弱。")

    # 估值
    pe = val.get("pe_ttm")
    pb = val.get("pb")
    if pe is not None and pb is not None:
        parts.append(f"当前PE {pe:.1f}倍，PB {pb:.1f}倍。")

    # 风险
    risks = result.get("risk_flags", [])
    if risks:
        parts.append(f"注意风险：{'、'.join(risks)}。")

    return "".join(parts) if parts else "基本面数据不足，无法生成完整总结。"


# ══════════════════════════════════════════════════════════════
# 计算辅助
# ══════════════════════════════════════════════════════════════

def _get_series(indicators: list[dict], key: str, n: int) -> list:
    """取近 n 年的某指标值列表 (按年倒序: 最新在前)"""
    return [ind.get(key) for ind in indicators[:n]]


def _avg(values: list) -> float | None:
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 2)


def _calc_trend(values: list) -> str:
    """判断趋势: 值按时间倒序 (最新在前)"""
    valid = [v for v in values if v is not None]
    if len(valid) < 2:
        return "数据不足"
    if valid[0] > valid[-1] * 1.05:
        return "改善"
    elif valid[0] < valid[-1] * 0.95:
        return "恶化"
    return "稳定"


def _calc_cagr(indicators: list[dict], key: str, years: int) -> float | None:
    """计算复合年增长率"""
    if len(indicators) < years + 1:
        vals = _get_series(indicators, key, len(indicators))
    else:
        vals = _get_series(indicators, key, years + 1)

    valid_start = None
    valid_end = None
    n = 0
    for i, v in enumerate(vals):
        if v is not None and v > 0:
            if valid_end is None:
                valid_end = v
            valid_start = v
            n = i

    if valid_start is None or valid_end is None or n == 0 or valid_start <= 0:
        return None

    cagr = ((valid_end / valid_start) ** (1 / n) - 1) * 100
    return round(cagr, 2)
