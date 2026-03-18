"""
scripts/build_symbol_db.py - 构建股票/基金符号数据库

从 akshare 拉取 A股、港股、基金列表，从 yfinance 常用美股列表构建，
写入 data/symbols.json 供搜索 API 使用。

特点：
- 单个市场拉取失败不会导致整个脚本退出
- 内置了各市场的最小 fallback 数据，保证 symbols.json 至少可用
- 会去重并按 market+ticker 排序输出

用法: python scripts/build_symbol_db.py
"""
import json
import os
import sys
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
OUTPUT = os.path.join(DATA_DIR, "symbols.json")


def _safe_build(label: str, builder: Callable[[], list[dict]], fallback: list[dict]) -> list[dict]:
    """执行构建，失败时回退到内置最小数据集。"""
    try:
        items = builder()
        if items:
            return items
        print(f"[!] {label} 返回空结果，使用 fallback ...")
    except Exception as e:
        print(f"[!] {label} 拉取失败: {e}")
        print(f"[..] {label} 使用 fallback ...")
    return fallback.copy()


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
    """美股常用标的（优先 akshare，全失败则由外层 fallback 兜底）"""
    import akshare as ak
    print("[..] 拉取美股列表...")
    items = []
    df = ak.stock_us_spot_em()
    for _, row in df.iterrows():
        name = str(row.get("名称", ""))
        ticker = str(row.get("代码", ""))
        ticker_clean = ticker.split(".")[-1] if "." in ticker else ticker
        items.append({
            "ticker": ticker_clean,
            "name": name,
            "market": "us_stock",
        })
    print(f"[OK] 美股: {len(items)} 只")
    return items


A_SHARE_FALLBACK = [
    {"ticker": "600519", "name": "贵州茅台", "market": "a_share"},
    {"ticker": "000858", "name": "五粮液", "market": "a_share"},
    {"ticker": "300750", "name": "宁德时代", "market": "a_share"},
    {"ticker": "000333", "name": "美的集团", "market": "a_share"},
    {"ticker": "601318", "name": "中国平安", "market": "a_share"},
    {"ticker": "600036", "name": "招商银行", "market": "a_share"},
    {"ticker": "600900", "name": "长江电力", "market": "a_share"},
    {"ticker": "002594", "name": "比亚迪", "market": "a_share"},
]

HK_STOCK_FALLBACK = [
    {"ticker": "00700", "name": "腾讯控股", "market": "hk_stock"},
    {"ticker": "09988", "name": "阿里巴巴-W", "market": "hk_stock"},
    {"ticker": "03690", "name": "美团-W", "market": "hk_stock"},
    {"ticker": "01810", "name": "小米集团-W", "market": "hk_stock"},
    {"ticker": "00941", "name": "中国移动", "market": "hk_stock"},
    {"ticker": "01299", "name": "友邦保险", "market": "hk_stock"},
]

FUND_FALLBACK = [
    {"ticker": "510300", "name": "沪深300ETF", "market": "fund"},
    {"ticker": "510500", "name": "中证500ETF", "market": "fund"},
    {"ticker": "159919", "name": "沪深300ETF", "market": "fund"},
    {"ticker": "513100", "name": "纳指ETF", "market": "fund"},
    {"ticker": "518880", "name": "黄金ETF", "market": "fund"},
]

US_STOCK_FALLBACK = [
    {"ticker": "AAPL", "name": "苹果", "market": "us_stock"},
    {"ticker": "MSFT", "name": "微软", "market": "us_stock"},
    {"ticker": "GOOGL", "name": "谷歌A", "market": "us_stock"},
    {"ticker": "AMZN", "name": "亚马逊", "market": "us_stock"},
    {"ticker": "NVDA", "name": "英伟达", "market": "us_stock"},
    {"ticker": "META", "name": "Meta", "market": "us_stock"},
    {"ticker": "TSLA", "name": "特斯拉", "market": "us_stock"},
    {"ticker": "BABA", "name": "阿里巴巴", "market": "us_stock"},
    {"ticker": "PDD", "name": "拼多多", "market": "us_stock"},
    {"ticker": "JD", "name": "京东", "market": "us_stock"},
    {"ticker": "SPY", "name": "标普500ETF", "market": "us_stock"},
    {"ticker": "QQQ", "name": "纳指100ETF", "market": "us_stock"},
]


def _dedupe(items: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for item in items:
        ticker = str(item.get("ticker", "")).strip()
        name = str(item.get("name", "")).strip()
        market = str(item.get("market", "")).strip()
        if not ticker or not name or not market:
            continue
        key = (market, ticker)
        if key in seen:
            continue
        seen.add(key)
        result.append({"ticker": ticker, "name": name, "market": market})
    result.sort(key=lambda x: (x["market"], x["ticker"]))
    return result


def main(markets=None):
    """
    构建符号数据库。
    markets: 指定要更新的市场列表，None = 全部。
             例如 ["a_share"] 只更新 A 股，其他市场保留旧数据。
    """
    import shutil

    builders = {
        "a_share": ("A 股", build_a_share, A_SHARE_FALLBACK),
        "us_stock": ("美股", build_us_stock, US_STOCK_FALLBACK),
        "hk_stock": ("港股", build_hk_stock, HK_STOCK_FALLBACK),
        "fund": ("基金", build_fund, FUND_FALLBACK),
    }

    if markets is None:
        markets = list(builders.keys())

    old_symbols = []
    if os.path.exists(OUTPUT):
        try:
            with open(OUTPUT, "r", encoding="utf-8") as f:
                old_symbols = json.load(f)
            shutil.copy2(OUTPUT, OUTPUT + ".bak")
            print(f"[..] 已备份旧符号库 ({len(old_symbols)} 条)")
        except Exception as e:
            print(f"[!] 读取旧符号库失败: {e}")

    keep = [s for s in old_symbols if s.get("market") not in markets]
    new_symbols = list(keep)

    for market_key in markets:
        if market_key not in builders:
            print(f"[!] 未知市场: {market_key}")
            continue
        label, builder, fallback = builders[market_key]
        new_symbols.extend(_safe_build(label, builder, fallback))

    new_symbols = _dedupe(new_symbols)

    if len(new_symbols) < 10:
        print("[!] 新构建结果太少，保留旧文件")
        return

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(new_symbols, f, ensure_ascii=False)

    print(f"\n[OK] 共 {len(new_symbols)} 条符号数据 → {OUTPUT}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="构建符号数据库")
    parser.add_argument("--market", nargs="*", help="指定市场: a_share us_stock hk_stock fund")
    args = parser.parse_args()
    main(args.market)
