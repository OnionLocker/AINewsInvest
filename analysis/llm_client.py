"""
analysis/llm_client.py - LLM 接口抽象层

兼容 OpenAI API 协议（OpenClaw / vLLM / Ollama / ChatGPT 均适用）。
部署方只需在 config.yaml 配置 endpoint + model 即可接入。

用法:
    from analysis.llm_client import llm_analyze_stock, llm_summarize_news

    result = llm_analyze_stock(ticker, name, market, tech_data, news_items)
    result = llm_analyze_stock(ticker, name, market, tech_data, news_items,
                               fundamental_data=..., valuation_data=...)
"""
import requests
from utils.logger import app_logger
from utils.config_loader import get_config

_DEFAULT_TIMEOUT = 60


# ══════════════════════════════════════════════════════════════
# 底层通信
# ══════════════════════════════════════════════════════════════

def _get_llm_config() -> dict:
    cfg = get_config()
    return cfg.get("llm", {})


def _is_enabled() -> bool:
    cfg = _get_llm_config()
    return bool(cfg.get("enabled", False) and cfg.get("base_url"))


def chat_completion(messages: list[dict], **kwargs) -> str | None:
    """
    调用 OpenAI 兼容 /v1/chat/completions 接口。
    返回 assistant 回复文本，失败返回 None。
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
# Prompt 模板
# ══════════════════════════════════════════════════════════════

_PROMPT_V1 = """你是一位资深投资分析师。请根据以下数据，对该标的进行综合分析并给出操作建议。

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

_PROMPT_V2 = """你是 Alpha Vault 的 AI 投资分析引擎。请按照以下结构化框架进行分析。

## 标的信息
- 代码: {ticker}
- 名称: {name}
- 市场: {market}

## 技术面数据
{tech_data}

## 基本面数据
{fundamental_data}

## 估值数据
{valuation_data}

## 近期新闻
{news_data}

## 分析框架（严格按顺序）

### 一、快速定性
- 行业地位与护城河
- 是否存在价值陷阱信号（连续亏损/现金流枯竭/资产减值）

### 二、财务质量
- ROE 趋势（改善/稳定/恶化）
- 利润含金量（经营现金流/净利润 是否>0.8）
- 负债结构与偿债能力

### 三、估值判断
- 当前估值 vs 历史区间
- 穿透回报率是否有吸引力
- 安全边际是否充足

### 四、综合结论
- 方向: 看多/看空/中性
- 置信度: 0-100
- 主要逻辑（3句话）
- 关键风险点

## 要求
- 中文回答，简洁专业，500字以内
- 数据不足的维度注明"数据不足"，不要编造
"""

_NEWS_SUMMARY_PROMPT = """你是一位资深金融新闻分析师。请分析以下新闻标题，给出：
1. 整体情绪倾向（正面/负面/中性）
2. 对股价可能的短期影响
3. 关键信息摘要（3句话以内）

用中文回答。

新闻列表：
{news_list}
"""


# ══════════════════════════════════════════════════════════════
# 高层业务接口
# ══════════════════════════════════════════════════════════════

def llm_analyze_stock(
    ticker: str,
    name: str,
    market: str,
    tech_data: dict,
    news_items: list[dict],
    fundamental_data: dict | None = None,
    valuation_data: dict | None = None,
) -> dict | None:
    """
    用 LLM 对单只股票做深度综合分析。

    当传入 fundamental_data 或 valuation_data 时, 使用 V2 结构化 prompt;
    否则降级为 V1 prompt, 保持向后兼容。

    返回: {"llm_summary": str, "llm_available": True} 或 None
    """
    if not _is_enabled():
        return None

    market_labels = {
        "a_share": "A股", "us_stock": "美股",
        "hk_stock": "港股", "fund": "基金",
    }

    tech_text = _format_tech(tech_data)
    news_text = _format_news(news_items)
    has_extra = fundamental_data is not None or valuation_data is not None

    if has_extra:
        fund_text = _format_fundamental(fundamental_data)
        val_text = _format_valuation(valuation_data)
        prompt = _PROMPT_V2.format(
            ticker=ticker, name=name,
            market=market_labels.get(market, market),
            tech_data=tech_text, news_data=news_text,
            fundamental_data=fund_text, valuation_data=val_text,
        )
    else:
        prompt = _PROMPT_V1.format(
            ticker=ticker, name=name,
            market=market_labels.get(market, market),
            tech_data=tech_text, news_data=news_text,
        )

    max_tokens = 3072 if has_extra else 2048
    messages = [
        {"role": "system", "content": "你是 Alpha Vault 的 AI 投资分析引擎。"},
        {"role": "user", "content": prompt},
    ]

    reply = chat_completion(messages, max_tokens=max_tokens)
    if reply:
        return {"llm_summary": reply.strip(), "llm_available": True}
    return None


def llm_summarize_news(news_items: list[dict]) -> str | None:
    """用 LLM 对新闻做情绪摘要。"""
    if not _is_enabled() or not news_items:
        return None

    news_text = _format_news(news_items)
    prompt = _NEWS_SUMMARY_PROMPT.format(news_list=news_text)
    messages = [
        {"role": "system", "content": "你是 Alpha Vault 的新闻分析助手。"},
        {"role": "user", "content": prompt},
    ]
    return chat_completion(messages)


def llm_health_check() -> dict:
    """检查 LLM 服务连通性。"""
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
            max_tokens=16, temperature=0,
        )
        if reply:
            result["available"] = True
        else:
            result["error"] = "LLM 返回空响应"
    except Exception as e:
        result["error"] = str(e)
    return result


# ══════════════════════════════════════════════════════════════
# 格式化工具函数
# ══════════════════════════════════════════════════════════════

def _format_tech(tech: dict) -> str:
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


def _format_news(news: list[dict]) -> str:
    if not news:
        return "暂无相关新闻"
    lines = []
    for i, item in enumerate(news[:8], 1):
        title = item.get("title", "")
        source = item.get("source", "")
        time_str = item.get("time", "")
        lines.append(f"{i}. [{source}] {title} ({time_str})")
    return "\n".join(lines)


def _format_fundamental(data: dict | None) -> str:
    if not data:
        return "基本面数据暂不可用"

    prof = data.get("profitability", {})
    grow = data.get("growth", {})
    safe = data.get("safety", {})

    lines = [
        f"财务质量: {data.get('quality_score', 'N/A')}/100 ({data.get('quality_label', '')})",
        f"ROE: {_fmt(prof.get('roe_latest'))}%  趋势: {prof.get('roe_trend', 'N/A')}",
        f"毛利率: {_fmt(prof.get('gross_margin'))}%  净利率: {_fmt(prof.get('net_margin'))}%",
        f"营收CAGR(3y): {_fmt(grow.get('revenue_cagr_3y'))}%  利润CAGR(3y): {_fmt(grow.get('profit_cagr_3y'))}%  趋势: {grow.get('trend', 'N/A')}",
        f"负债率: {_fmt(safe.get('debt_ratio'))}%  流动比率: {_fmt(safe.get('current_ratio'))}",
        f"现金流健康年数: {safe.get('ocf_healthy_years', 'N/A')}/5  连续分红: {safe.get('dividend_years', 'N/A')}年",
    ]
    risks = data.get("risk_flags", [])
    if risks:
        lines.append(f"风险标记: {', '.join(risks)}")
    return "\n".join(lines)


def _format_valuation(data: dict | None) -> str:
    if not data:
        return "估值数据暂不可用"

    fp = data.get("floor_price", {})
    pr = data.get("penetration_return", {})
    sm = data.get("safety_margin", {})
    ev = data.get("ev_ebitda", {})

    lines = [
        f"穿透回报率: {_fmt(pr.get('rate'))}% (评级 {pr.get('grade', 'N/A')})",
        f"地板价均值: {_fmt(fp.get('average'))}  当前价: {_fmt(sm.get('current_price'))}",
        f"安全边际: {_fmt(sm.get('margin_pct'))}% ({sm.get('verdict', 'N/A')})",
        f"EV/EBITDA: {_fmt(ev.get('value'))}",
        f"地板价明细: 净流动资产={_fmt(fp.get('net_current_asset'))}  BVPS={_fmt(fp.get('bvps'))}  股息折现={_fmt(fp.get('dividend_discount'))}  悲观FCF={_fmt(fp.get('pessimistic_fcf'))}",
    ]
    return "\n".join(lines)


def _fmt(val) -> str:
    if val is None:
        return "N/A"
    if isinstance(val, float):
        return f"{val:.2f}" if abs(val) < 1000 else f"{val:,.0f}"
    return str(val)
