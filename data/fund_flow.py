"""
data/fund_flow.py - 资金流向数据

获取个股主力/散户资金流向。
"""
from utils.logger import app_logger


def get_fund_flow(ticker: str, market: str) -> dict | None:
    """
    获取个股资金流向数据。

    返回:
    {
        "ticker": str,
        "main_net_inflow": float,      # 主力净流入(万)
        "main_net_inflow_pct": float,   # 主力净流入占比(%)
        "retail_net_inflow": float,     # 散户净流入(万)
        "super_large_net": float,       # 超大单净额(万)
        "large_net": float,             # 大单净额(万)
        "medium_net": float,            # 中单净额(万)
        "small_net": float,             # 小单净额(万)
        "recent_days": list[dict],      # 近5日主力净流入
    }
    """
    if market != "a_share":
        return None

    try:
        import akshare as ak

        df = ak.stock_individual_fund_flow(stock=ticker, market="sh" if ticker.startswith("6") else "sz")
        if df is None or df.empty:
            return None

        latest = df.iloc[0]
        cols = df.columns.tolist()

        def _find_val(keywords):
            for c in cols:
                for kw in keywords:
                    if kw in str(c):
                        try:
                            return float(latest[c])
                        except (ValueError, TypeError):
                            pass
            return 0

        result = {
            "ticker": ticker,
            "main_net_inflow": _find_val(["主力净流入", "主力净额"]),
            "main_net_inflow_pct": _find_val(["主力净占比", "主力净流入占比"]),
            "retail_net_inflow": _find_val(["散户净流入", "散户净额", "小单净额"]),
            "super_large_net": _find_val(["超大单净额", "超大单净流入"]),
            "large_net": _find_val(["大单净额", "大单净流入"]),
            "medium_net": _find_val(["中单净额", "中单净流入"]),
            "small_net": _find_val(["小单净额", "小单净流入"]),
        }

        recent = []
        for i, row in df.head(5).iterrows():
            date_col = None
            for c in cols:
                if "日期" in str(c) or "date" in str(c).lower():
                    date_col = c
                    break
            d = str(row.get(date_col, "")) if date_col else str(i)
            main_val = 0
            for c in cols:
                if "主力净流入" in str(c) or "主力净额" in str(c):
                    try:
                        main_val = float(row[c])
                    except (ValueError, TypeError):
                        pass
                    break
            recent.append({"date": d[:10], "main_net": main_val})
        result["recent_days"] = recent

        app_logger.info(f"[资金流向] {ticker} 主力净流入: {result['main_net_inflow']:.0f}万")
        return result

    except Exception as e:
        app_logger.warning(f"[资金流向] {ticker} 获取失败: {e}")
        return None


def format_for_llm(flow: dict | None) -> str:
    """将资金流向格式化为 LLM 输入。"""
    if not flow:
        return ""

    lines = ["资金流向:"]
    lines.append(f"  主力净流入: {flow.get('main_net_inflow', 0):.0f}万 ({flow.get('main_net_inflow_pct', 0):.1f}%)")
    lines.append(f"  超大单: {flow.get('super_large_net', 0):.0f}万 | 大单: {flow.get('large_net', 0):.0f}万")
    lines.append(f"  中单: {flow.get('medium_net', 0):.0f}万 | 小单: {flow.get('small_net', 0):.0f}万")

    recent = flow.get("recent_days", [])
    if recent:
        lines.append("  近5日主力净流入:")
        for r in recent:
            lines.append(f"    {r['date']}: {r['main_net']:.0f}万")

    return "\n".join(lines)
