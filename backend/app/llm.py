"""Thin client for NVIDIA's OpenAI-compatible API (build.nvidia.com). Every call fails safe (returns None)."""

import logging
import re

import httpx

from . import config

log = logging.getLogger(__name__)


def enabled() -> bool:
    return bool(config.NVIDIA_API_KEY)


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.NVIDIA_API_KEY}", "Accept": "application/json"}


async def chat(system: str, user: str, *, max_tokens: int = 900, temperature: float = 0.2,
               model: str | None = None, thinking: bool = False) -> str | None:
    if not enabled():
        return None
    payload = {
        "model": model or config.NVIDIA_CHAT_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "stream": False,
    }
    # We want the answer only, not a long hidden reasoning trace (reasoning models otherwise spend the
    # whole token budget thinking). Models that don't support the switch are retried without it.
    payload["chat_template_kwargs"] = {"enable_thinking": thinking}
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(f"{config.NVIDIA_BASE_URL}/chat/completions", json=payload, headers=_headers())
            if r.status_code in (400, 422):
                payload.pop("chat_template_kwargs")
                r = await client.post(f"{config.NVIDIA_BASE_URL}/chat/completions", json=payload, headers=_headers())
        if r.status_code != 200:
            log.warning("NVIDIA chat HTTP %s: %s", r.status_code, r.text[:300])
            return None
        content = r.json()["choices"][0]["message"].get("content") or ""
    except Exception as exc:
        log.warning("NVIDIA chat failed: %s", exc)
        return None
    # Reasoning models may emit their thinking inline; keep only the final answer.
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
    content = content.split("</think>")[-1]
    return content.strip() or None
