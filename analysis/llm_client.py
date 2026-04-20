"""OpenAI-compatible LLM client driven by pipeline config."""
from __future__ import annotations

import json
import re
import time
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


# Retryable network / server errors
_RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
)


def chat_completion(messages: list[dict[str, Any]], **kwargs: Any) -> str | None:
    if not _is_enabled():
        logger.debug("chat_completion: LLM disabled or misconfigured")
        return None
    cfg = get_config()
    max_retries = int(kwargs.pop("max_retries", 2))
    body: dict[str, Any] = {
        "model": cfg.llm.model,
        "messages": messages,
        "temperature": kwargs.get("temperature", cfg.llm.temperature),
        "max_tokens": kwargs.get("max_tokens", cfg.llm.max_tokens),
    }
    for k in ("top_p", "frequency_penalty", "presence_penalty", "stream", "response_format"):
        if k in kwargs:
            body[k] = kwargs[k]

    for attempt in range(1 + max_retries):
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
            status = e.response.status_code
            # 5xx server errors and 429 rate-limit are retryable with backoff.
            # Other 4xx (400/401/403/404/422) are client-side and not retryable.
            if (500 <= status < 600 or status == 429) and attempt < max_retries:
                # 429: honor Retry-After header if provided, else exponential backoff with a floor
                if status == 429:
                    retry_after = e.response.headers.get("Retry-After")
                    try:
                        wait = max(int(retry_after), 2 ** (attempt + 1)) if retry_after else 2 ** (attempt + 2)
                    except (TypeError, ValueError):
                        wait = 2 ** (attempt + 2)
                else:
                    wait = 2 ** (attempt + 1)
                logger.warning(
                    f"LLM HTTP {status} (attempt {attempt + 1}/{1 + max_retries}), "
                    f"retrying in {wait}s: {e.response.text[:200]}"
                )
                time.sleep(wait)
                continue
            logger.warning(f"LLM HTTP {status}: {e.response.text[:500]}")
            # v10.1: if gateway rejects `response_format`, retry once without it
            if (
                status in (400, 422)
                and "response_format" in body
                and "response_format" in (e.response.text or "").lower()
            ):
                logger.info("LLM gateway rejected response_format; retrying without it")
                body.pop("response_format", None)
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
                    return str(content).strip() if content else None
                except Exception as retry_err:
                    logger.warning(f"LLM fallback-without-response_format also failed: {retry_err}")
                    return None
            return None
        except _RETRYABLE_EXCEPTIONS as e:
            if attempt < max_retries:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    f"LLM network error (attempt {attempt + 1}/{1 + max_retries}), "
                    f"retrying in {wait}s: {e}"
                )
                time.sleep(wait)
                continue
            logger.warning(f"LLM request failed after {1 + max_retries} attempts: {e}")
            return None
        except Exception as e:
            logger.warning(f"LLM request failed: {e}")
            return None
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
        f"Stock: {ticker} ({name or 'N/A'}) Market: {market}",
        "## Technical Analysis\n```json\n"
        + json.dumps(tech_data, ensure_ascii=False, default=str, indent=2)
        + "\n```",
        "## News\n```json\n"
        + json.dumps(news_items[:15], ensure_ascii=False, default=str, indent=2)
        + "\n```",
    ]
    if fundamental_data is not None:
        blocks.append(
            "## Fundamentals\n```json\n"
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
    """Extract JSON from LLM response, handling markdown fences and preamble.

    Many LLMs prepend natural-language analysis before the JSON object.
    Strategy: find the outermost balanced { ... } block via brace counting,
    which is more robust than simple find/rfind.
    """
    text = text.strip()
    # Try markdown code fence first
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try full text as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Brace-counting: find the first top-level { ... } block
    depth = 0
    start = -1
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = -1  # try next top-level block
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

    cfg_max_tokens = get_config().llm.max_tokens or 4096

    try:
        skill_prompt = _load_skill(role)
    except FileNotFoundError as e:
        logger.warning(str(e))
        return None

    data_text = json.dumps(payload, ensure_ascii=False, default=str)

    _json_reminder = (
        "\n\n---\nIMPORTANT: Respond with a SINGLE JSON object ONLY. "
        "Do NOT include any text, explanation, or markdown before or after the JSON. "
        "Start your response with { and end with }."
    )

    messages = [
        {"role": "system", "content": skill_prompt},
        {"role": "user", "content": data_text + _json_reminder},
    ]

    for attempt in range(1 + max_retries):
        raw = chat_completion(
            messages,
            temperature=0.2,
            max_tokens=cfg_max_tokens,
            response_format={"type": "json_object"},
        )
        if raw is None:
            logger.warning(f"agent_analyze({role}): LLM returned None (attempt {attempt + 1})")
            continue

        parsed = _extract_json(raw)
        if parsed is not None:
            logger.info(f"agent_analyze({role}): success, {len(parsed.get('results', []))} results")
            return parsed

        logger.warning(f"agent_analyze({role}): JSON parse failed (attempt {attempt + 1}), raw[:200]={raw[:200]}")

        # On retry, append the failed output and a stronger correction nudge
        if attempt < max_retries:
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content":
                "Your previous response was NOT valid JSON. "
                "Output ONLY the JSON object, starting with { and ending with }. "
                "No explanation, no markdown, no preamble."
            })

    logger.error(f"agent_analyze({role}): all attempts exhausted")
    return None
