"""
analysis/llm_client.py - LLM 接口抽象层

兼容 OpenAI API 协议（OpenClaw / vLLM / Ollama / ChatGPT 均适用）。
部署方只需在 config.yaml 配置 endpoint + model 即可接入。

用法:
    from analysis.llm_client import llm_analyze_stock, llm_summarize_news

    # 对单只股票做深度分析（技术面+新闻面 → AI 总结）
    result = llm_analyze_stock(ticker, name, market, tech_data, news_items)

    # 对一组新闻做情绪摘要
    summary = llm_summarize_news(news_items)
"""
import json
import requests
from utils.logger import app_logger
from utils.config_loader import get_config

_DEFAULT_TIMEOUT = 60


# ══════════════════════════════════════════════════════════════
# 底层通信
# ══════════════════════════════════════════════════════════════

def _get_llm_config() -> dict:
    """从 config.yaml 读取 LLM 配置"""
    cfg = get_config()
    return cfg.get("llm", {})


def _is_enabled() -> bool:
    cfg = _get_llm_config()
    return bool(cfg.get("enabled", False) and cfg.get("base_url"))


def chat_completion(messages: list[dict], **kwargs) -> str | None:
    """
    调用 OpenAI 兼容 /v1/chat/completions 接口。

    参数:
        messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
        **kwargs: temperature, max_tokens 等，会覆盖 config.yaml 中的默认值

    返回:
        assistant 的回复文本，失败返回 None
    """
    cfg = _get_llm_config()
    if not cfg.get("base_url"):
        return None

    base_url = cfg["base_url"].rstrip("/")
    url = f"{base_url}/v1/chat/completions"
    model = kwargs.pop("model", None) or cfg.get("model", "default")
    api_key = cfg.get("api_key", "")
    timeout = cfg.get("timeout", _DEFAULT_TIMEOUT)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": kwargs.get("temperature", cfg.get("temperature", 0.3)),
        "max_tokens": kwargs.get("max_tokens", cfg.get("max_tokens", 2048)),
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        app_logger.warning(f"[LLM] 请求超时 ({timeout}s)")
        return None
    except requests.exceptions.ConnectionError:
        app_logger.warning(f"[LLM] 无法连接 {base_url}")
        return None
    except Exception as e:
        app_logger.warning(f"[LLM] 调用失败: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# 高层业务接口
# ══════════════════════════════════════════════════════════════

_STOCK_ANALYSIS_PROMPT = """你是一位资深投资分析师。请根据以下数据，对该标的进行综合分析并给出操作建议。

## 标的信息
- 代码: {ticker}
- 名称: {name}
- 市场: {market}

## 技术面数据
{tech_data}

## 近期新闻
{news_data}

## 要求
1. 先简述当前技术面形态（趋势、关键指标、量价关系）
2. 再分析新闻面对股价可能的影响
3. 给出综合判断：看多/看空/中性，置信度（0-100）
4. 给出具体操作建议：入场价位、止损价位、第一止盈、第二止盈
5. 用中文回答，简洁专业，控制在 300 字以内
"""

_NEWS_SUMMARY_PROMPT = """你是一位资深金融新闻分析师。请分析以下新闻标题，给出：
1. 整体情绪倾向（正面/负面/中性）
2. 对股价可能的短期影响
3. 关键信息摘要（3句话以内）

用中文回答。

新闻列表：
{news_list}
"""


def llm_analyze_stock(
    ticker: str,
    name: str,
    market: str,
    tech_data: dict,
    news_items: list[dict],
) -> dict | None:
    """
    用 LLM 对单只股票做深度综合分析。

    参数:
        ticker: 股票代码
        name: 股票名称
        market: 市场 (a_share/us_stock/hk_stock/fund)
        tech_data: technical.analyze() 的返回结果
        news_items: news_fetcher.fetch_news() 的返回列表

    返回:
        {
            "llm_summary": str,    # AI 深度分析文本
            "llm_available": True  # 标记 LLM 是否可用
        }
        如果 LLM 不可用返回 None
    """
    if not _is_enabled():
        return None

    market_labels = {"a_share": "A股", "us_stock": "美股", "hk_stock": "港股", "fund": "基金"}

    tech_text = _format_tech_for_prompt(tech_data)
    news_text = _format_news_for_prompt(news_items)

    prompt = _STOCK_ANALYSIS_PROMPT.format(
        ticker=ticker,
        name=name,
        market=market_labels.get(market, market),
        tech_data=tech_text,
        news_data=news_text,
    )

    messages = [
        {"role": "system", "content": "你是 Alpha Vault 的 AI 投资分析引擎。"},
        {"role": "user", "content": prompt},
    ]

    reply = chat_completion(messages)
    if reply:
        return {"llm_summary": reply.strip(), "llm_available": True}
    return None


def llm_summarize_news(news_items: list[dict]) -> str | None:
    """
    用 LLM 对新闻做情绪摘要。

    返回摘要文本，LLM 不可用时返回 None。
    """
    if not _is_enabled() or not news_items:
        return None

    news_text = _format_news_for_prompt(news_items)
    prompt = _NEWS_SUMMARY_PROMPT.format(news_list=news_text)

    messages = [
        {"role": "system", "content": "你是 Alpha Vault 的新闻分析助手。"},
        {"role": "user", "content": prompt},
    ]

    return chat_completion(messages)


def llm_health_check() -> dict:
    """
    检查 LLM 服务连通性。

    返回: {"available": bool, "model": str, "base_url": str, "error": str|None}
    """
    cfg = _get_llm_config()
    result = {
        "available": False,
        "model": cfg.get("model", ""),
        "base_url": cfg.get("base_url", ""),
        "error": None,
    }

    if not cfg.get("base_url"):
        result["error"] = "未配置 llm.base_url"
        return result

    try:
        reply = chat_completion(
            [{"role": "user", "content": "ping"}],
            max_tokens=16,
            temperature=0,
        )
        if reply:
            result["available"] = True
        else:
            result["error"] = "LLM 返回空响应"
    except Exception as e:
        result["error"] = str(e)

    return result


# ══════════════════════════════════════════════════════════════
# 内部工具函数
# ══════════════════════════════════════════════════════════════

def _format_tech_for_prompt(tech: dict) -> str:
    """把 tech_analyze 的结果转成 LLM 可读文本"""
    if not tech:
        return "无技术面数据"

    indicators = tech.get("indicators", {})
    lines = [
        f"最新价: {tech.get('price', 'N/A')}  涨跌幅: {tech.get('change_pct', 'N/A')}%",
        f"趋势判断: {tech.get('trend', 'N/A')}  信号: {tech.get('signal', 'N/A')}",
        f"置信度: {tech.get('confidence', 'N/A')}%",
        f"MA5={indicators.get('ma5')}  MA20={indicators.get('ma20')}  MA60={indicators.get('ma60')}",
        f"RSI={indicators.get('rsi')}  MACD DIF={indicators.get('macd_dif')}  DEA={indicators.get('macd_dea')}",
        f"布林上轨={indicators.get('boll_upper')}  布林下轨={indicators.get('boll_lower')}  ATR={indicators.get('atr')}",
        f"建议入场: {tech.get('entry')}  止损: {tech.get('stop_loss')}",
        f"止盈一: {tech.get('take_profit_1')}  止盈二: {tech.get('take_profit_2')}",
        f"风险回报: {tech.get('risk_reward')}",
    ]
    return "\n".join(lines)


def _format_news_for_prompt(news: list[dict]) -> str:
    """把新闻列表转成 LLM 可读文本"""
    if not news:
        return "暂无相关新闻"

    lines = []
    for i, item in enumerate(news[:8], 1):
        title = item.get("title", "")
        source = item.get("source", "")
        time_str = item.get("time", "")
        lines.append(f"{i}. [{source}] {title} ({time_str})")
    return "\n".join(lines)
