"""OpenAI-compatible LLM client driven by pipeline config."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from pipeline.config import get_config

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _is_enabled() -> bool:
    cfg = get_config()
    return bool(cfg.llm.enabled and cfg.llm.base_url and cfg.llm.model)


def _chat_url() -> str:
    base = get_config().llm.base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _headers() -> dict[str, str]:
    cfg = get_config()
    h = {"Content-Type": "application/json"}
    if cfg.llm.api_key:
        h["Authorization"] = f"Bearer {cfg.llm.api_key}"
    return h


def chat_completion(messages: list[dict[str, Any]], **kwargs: Any) -> str | None:
    if not _is_enabled():
        logger.debug("chat_completion: LLM disabled or misconfigured")
        return None
    cfg = get_config()
    body: dict[str, Any] = {
        "model": cfg.llm.model,
        "messages": messages,
        "temperature": kwargs.get("temperature", cfg.llm.temperature),
        "max_tokens": kwargs.get("max_tokens", cfg.llm.max_tokens),
    }
    for k in ("top_p", "frequency_penalty", "presence_penalty", "stream"):
        if k in kwargs:
            body[k] = kwargs[k]
    try:
        with httpx.Client(timeout=cfg.llm.timeout) as client:
            r = client.post(_chat_url(), headers=_headers(), json=body)
        r.raise_for_status()
        data = r.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if content is None:
            return None
        return str(content).strip() or None
    except httpx.HTTPStatusError as e:
        logger.warning(f"LLM HTTP {e.response.status_code}: {e.response.text[:500]}")
        return None
    except Exception as e:
        logger.warning(f"LLM request failed: {e}")
        return None


def llm_health_check() -> dict[str, Any]:
    cfg = get_config()
    if not cfg.llm.enabled:
        return {"ok": False, "error": "llm.disabled"}
    if not cfg.llm.base_url or not cfg.llm.model:
        return {"ok": False, "error": "llm.misconfigured"}
    text = chat_completion(
        [{"role": "user", "content": "ok"}],
        max_tokens=4,
        temperature=0,
    )
    ok = text is not None
    return {"ok": ok, "model": cfg.llm.model, "base_url": cfg.llm.base_url}


def llm_analyze_stock(
    ticker: str,
    name: str,
    market: str,
    tech_data: dict[str, Any],
    news_items: list[dict[str, Any]],
    fundamental_data: dict[str, Any] | None = None,
    valuation_data: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not _is_enabled():
        return None
    blocks = [
        f"閺嶅洨娈�: {ticker} ({name or 'N/A'}) 鐢倸婧€: {market}",
        "## Technical Analysis\n```json\n"
        + json.dumps(tech_data, ensure_ascii=False, default=str, indent=2)
        + "\n```",
        "## 閺備即妞圽n```json\n"
        + json.dumps(news_items[:15], ensure_ascii=False, default=str, indent=2)
        + "\n```",
    ]
    if fundamental_data is not None:
        blocks.append(
            "## 閸╃儤婀伴棃顣俷```json\n"
            + json.dumps(fundamental_data, ensure_ascii=False, default=str, indent=2)
            + "\n```"
        )
    if valuation_data is not None:
        blocks.append(
        "## Valuation\n```json\n"
            + json.dumps(valuation_data, ensure_ascii=False, default=str, indent=2)
            + "\n```"
        )
    blocks.append(
        "Based on the above data, provide a concise investment summary in Chinese covering: key insights, risks, valuation, "
        "and recommendation. Do not fabricate numbers not in the data. Keep under 400 characters."
    )
    prompt = "\n\n".join(blocks)
    summary = chat_completion(
        [{"role": "user", "content": prompt}],
    )
    if summary is None:
        return None
    return {"llm_summary": summary}


# ---------------------------------------------------------------------------
# Agent-oriented LLM calls (structured JSON output)
# ---------------------------------------------------------------------------

def _load_skill(skill_name: str) -> str:
    """Load a skill prompt from the skills directory.
    Extracts content between triple-backtick code fences.
    """
    path = _SKILLS_DIR / f"{skill_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Skill file not found: {path}")
    text = path.read_text(encoding="utf-8")
    match = re.search(r"```\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract JSON from LLM response, handling markdown code fences."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                pass
    return None


def agent_analyze(
    role: str,
    payload: dict[str, Any],
    max_retries: int = 1,
) -> dict[str, Any] | None:
    """Call an LLM agent with a skill prompt and structured data payload.

    Args:
        role: "news_sentiment_agent" or "technical_agent"
        payload: dict with candidate data to analyze
        max_retries: number of retries on parse failure

    Returns:
        Parsed JSON dict from agent, or None on failure.
    """
    if not _is_enabled():
        logger.debug(f"agent_analyze({role}): LLM disabled")
        return None

    try:
        skill_prompt = _load_skill(role)
    except FileNotFoundError as e:
        logger.warning(str(e))
        return None

    data_text = json.dumps(payload, ensure_ascii=False, default=str)

    messages = [
        {"role": "system", "content": skill_prompt},
        {"role": "user", "content": data_text},
    ]

    for attempt in range(1 + max_retries):
        raw = chat_completion(
            messages,
            temperature=0.2,
            max_tokens=4096,
        )
        if raw is None:
            logger.warning(f"agent_analyze({role}): LLM returned None (attempt {attempt + 1})")
            continue

        parsed = _extract_json(raw)
        if parsed is not None:
            logger.info(f"agent_analyze({role}): success, {len(parsed.get('results', []))} results")
            return parsed

        logger.warning(f"agent_analyze({role}): JSON parse failed (attempt {attempt + 1}), raw[:200]={raw[:200]}")

    logger.error(f"agent_analyze({role}): all attempts exhausted")
    return None
