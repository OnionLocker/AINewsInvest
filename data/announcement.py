"""
data/announcement.py - 公告/研报摘要采集

从东方财富获取个股公告标题列表。
"""
from utils.logger import app_logger


def fetch_announcements(ticker: str, market: str, days: int = 30) -> list[dict]:
    """
    获取指定标的近 N 天公告列表。

    返回: [{"title": "...", "date": "2026-03-10", "type": "公告"}, ...]
    """
    if market not in ("a_share",):
        return []

    try:
        import akshare as ak
        df = ak.stock_notice_report(symbol=ticker)
        if df is None or df.empty:
            return []

        results = []
        date_col = None
        for c in df.columns:
            if "日期" in str(c) or "date" in str(c).lower() or "时间" in str(c):
                date_col = c
                break

        title_col = None
        for c in df.columns:
            if "标题" in str(c) or "title" in str(c).lower() or "公告" in str(c):
                title_col = c
                break

        if title_col is None:
            title_col = df.columns[0] if len(df.columns) > 0 else None

        if title_col is None:
            return []

        from datetime import date as dt_date, timedelta
        cutoff = dt_date.today() - timedelta(days=days)

        for _, row in df.head(50).iterrows():
            title = str(row.get(title_col, ""))
            d = str(row.get(date_col, "")) if date_col else ""

            if d and len(d) >= 10:
                try:
                    row_date = dt_date.fromisoformat(d[:10])
                    if row_date < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass

            results.append({
                "title": title,
                "date": d[:10] if d else "",
                "type": "公告",
            })

        app_logger.info(f"[公告] {ticker} 获取 {len(results)} 条公告")
        return results[:20]

    except Exception as e:
        app_logger.warning(f"[公告] {ticker} 获取失败: {e}")
        return []


def format_for_llm(announcements: list[dict]) -> str:
    """将公告列表格式化为 LLM 输入。"""
    if not announcements:
        return ""

    lines = ["近期公告:"]
    for a in announcements[:10]:
        lines.append(f"  [{a['date']}] {a['title']}")
    return "\n".join(lines)
