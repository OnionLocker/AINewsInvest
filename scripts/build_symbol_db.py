"""
scripts/build_symbol_db.py - 构建股票/基金符号数据库

从 akshare 拉取 A股、港股、基金列表，从 yfinance 常用美股列表构建，
写入 data/symbols.json 供搜索 API 使用。

用法: python scripts/build_symbol_db.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
OUTPUT = os.path.join(DATA_DIR, "symbols.json")


def build_a_share() -> list[dict]:
    """A 股全量股票列表"""
    import akshare as ak
    print("[..] 拉取 A 股列表...")
    df = ak.stock_zh_a_spot_em()
    items = []
    for _, row in df.iterrows():
        items.append({
            "ticker": str(row["代码"]),
            "name": str(row["名称"]),
            "market": "a_share",
        })
    print(f"[OK] A 股: {len(items)} 只")
    return items


def build_hk_stock() -> list[dict]:
    """港股主板列表"""
    import akshare as ak
    print("[..] 拉取港股列表...")
    df = ak.stock_hk_spot_em()
    items = []
    for _, row in df.iterrows():
        items.append({
            "ticker": str(row["代码"]),
            "name": str(row["名称"]),
            "market": "hk_stock",
        })
    print(f"[OK] 港股: {len(items)} 只")
    return items


def build_fund() -> list[dict]:
    """公募基金列表"""
    import akshare as ak
    print("[..] 拉取基金列表...")
    df = ak.fund_name_em()
    items = []
    for _, row in df.iterrows():
        items.append({
            "ticker": str(row["基金代码"]),
            "name": str(row["基金简称"]),
            "market": "fund",
        })
    print(f"[OK] 基金: {len(items)} 只")
    return items


def build_us_stock() -> list[dict]:
    """美股常用标的（S&P 500 + 热门中概股）"""
    import akshare as ak
    print("[..] 拉取美股列表...")
    items = []
    try:
        df = ak.stock_us_spot_em()
        for _, row in df.iterrows():
            name = str(row.get("名称", ""))
            ticker = str(row.get("代码", ""))
            # akshare 美股代码格式可能带前缀，清理一下
            ticker_clean = ticker.split(".")[-1] if "." in ticker else ticker
            items.append({
                "ticker": ticker_clean,
                "name": name,
                "market": "us_stock",
            })
    except Exception as e:
        print(f"[!] akshare 美股拉取失败: {e}")
        print("[..] 使用内置常用美股列表...")
        fallback = [
            ("AAPL", "苹果"), ("MSFT", "微软"), ("GOOGL", "谷歌A"), ("AMZN", "亚马逊"),
            ("NVDA", "英伟达"), ("META", "Meta"), ("TSLA", "特斯拉"), ("BRK.B", "伯克希尔B"),
            ("JPM", "摩根大通"), ("V", "Visa"), ("UNH", "联合健康"), ("MA", "万事达"),
            ("HD", "家得宝"), ("PG", "宝洁"), ("JNJ", "强生"), ("ABBV", "艾伯维"),
            ("MRK", "默沙东"), ("AVGO", "博通"), ("COST", "好市多"), ("PEP", "百事"),
            ("KO", "可口可乐"), ("TMO", "赛默飞"), ("ADBE", "Adobe"), ("CRM", "Salesforce"),
            ("AMD", "AMD"), ("INTC", "英特尔"), ("NFLX", "奈飞"), ("QCOM", "高通"),
            ("BABA", "阿里巴巴"), ("PDD", "拼多多"), ("JD", "京东"), ("BIDU", "百度"),
            ("NIO", "蔚来"), ("LI", "理想汽车"), ("XPEV", "小鹏汽车"), ("BILI", "哔哩哔哩"),
            ("TME", "腾讯音乐"), ("ZTO", "中通快递"), ("VNET", "世纪互联"), ("IQ", "爱奇艺"),
            ("COIN", "Coinbase"), ("PLTR", "Palantir"), ("SNOW", "Snowflake"),
            ("SQ", "Block"), ("SHOP", "Shopify"), ("UBER", "Uber"), ("ABNB", "Airbnb"),
            ("ARM", "ARM"), ("SMCI", "超微电脑"), ("MU", "美光"), ("MRVL", "Marvell"),
            ("PANW", "Palo Alto"), ("CRWD", "CrowdStrike"), ("DDOG", "Datadog"),
            ("NET", "Cloudflare"), ("ZS", "Zscaler"), ("OKTA", "Okta"),
            ("SPY", "标普500ETF"), ("QQQ", "纳指100ETF"), ("DIA", "道琼斯ETF"),
            ("IWM", "罗素2000ETF"), ("GLD", "黄金ETF"), ("TLT", "20年美债ETF"),
        ]
        items = [{"ticker": t, "name": n, "market": "us_stock"} for t, n in fallback]

    print(f"[OK] 美股: {len(items)} 只")
    return items


def main():
    all_symbols = []
    all_symbols.extend(build_a_share())
    all_symbols.extend(build_us_stock())
    all_symbols.extend(build_hk_stock())
    all_symbols.extend(build_fund())

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_symbols, f, ensure_ascii=False)

    print(f"\n[OK] 共 {len(all_symbols)} 条符号数据 → {OUTPUT}")


if __name__ == "__main__":
    main()
