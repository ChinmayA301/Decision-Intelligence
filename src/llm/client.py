"""
LLM provider abstraction.

Set LLM_PROVIDER in .env:
  anthropic   — Anthropic API (paid, requires ANTHROPIC_API_KEY)
  groq        — Groq free tier (free, requires GROQ_API_KEY from console.groq.com)
  ollama      — Local Ollama (free, requires `ollama serve` running)

All expose the same async interface:
  await client.complete(system, messages, max_tokens) -> str
"""
from __future__ import annotations

import asyncio
import os
import random
import re
from dataclasses import dataclass

_MAX_ATTEMPTS = 5
_RETRY_AFTER_HINT = re.compile(r"try again in (\d+(?:\.\d+)?)s")


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str


async def _call_with_rate_limit_retry(fn, *args, **kwargs):
    """Retry transient 429s. Free-tier Groq allows ~12k tokens/min and one brief
    uses most of that, so a second brief inside the same minute would otherwise
    fail. Honors the provider's 'try again in Ns' hint when present."""
    from openai import RateLimitError

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return await fn(*args, **kwargs)
        except RateLimitError as exc:
            if attempt == _MAX_ATTEMPTS:
                raise
            hint = _RETRY_AFTER_HINT.search(str(exc))
            delay = float(hint.group(1)) + 1.0 if hint else 2.0 * (2 ** (attempt - 1))
            await asyncio.sleep(min(delay, 30.0) + random.uniform(0, 0.5))


class LLMClient:
    """Single interface for all LLM calls in the pipeline."""

    async def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = 1024,
    ) -> str:
        raise NotImplementedError


# ─── Anthropic provider ───────────────────────────────────────────────────────

class AnthropicClient(LLMClient):
    def __init__(self, model: str | None = None) -> None:
        import anthropic
        self._client = anthropic.AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"]
        )
        self._model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    async def complete(self, system: str, messages: list[Message], max_tokens: int = 1024) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        return response.content[0].text


# ─── Groq provider ───────────────────────────────────────────────────────────

class GroqClient(LLMClient):
    """
    Groq free tier — sign up at console.groq.com (no credit card needed).
    Default model: llama-3.3-70b-versatile (very capable, free).
    Free limits: ~14,400 tokens/min, 500k tokens/day — plenty for dev/testing.
    Uses OpenAI-compatible API so no extra SDK needed.
    """
    def __init__(self, model: str | None = None) -> None:
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ["GROQ_API_KEY"],
        )
        self._model = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    async def complete(self, system: str, messages: list[Message], max_tokens: int = 1024) -> str:
        all_messages = [{"role": "system", "content": system}]
        all_messages += [{"role": m.role, "content": m.content} for m in messages]
        response = await _call_with_rate_limit_retry(
            self._client.chat.completions.create,
            model=self._model,
            messages=all_messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""


# ─── Ollama provider ──────────────────────────────────────────────────────────

class OllamaClient(LLMClient):
    """
    Uses Ollama's OpenAI-compatible API (http://localhost:11434/v1).
    Recommended free models: llama3.1:8b, mistral:7b, gemma3:4b
    Pull with: ollama pull llama3.1:8b
    """
    def __init__(self, model: str | None = None) -> None:
        from openai import AsyncOpenAI
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self._client = AsyncOpenAI(base_url=base_url, api_key="ollama")
        self._model = model or os.environ.get("OLLAMA_MODEL", "llama3.1:8b")

    async def complete(self, system: str, messages: list[Message], max_tokens: int = 1024) -> str:
        all_messages = [{"role": "system", "content": system}]
        all_messages += [{"role": m.role, "content": m.content} for m in messages]
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=all_messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""


# ─── Factory ──────────────────────────────────────────────────────────────────

def get_llm_client() -> LLMClient:
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider == "anthropic":
        return AnthropicClient()
    elif provider == "groq":
        return GroqClient()
    elif provider == "ollama":
        return OllamaClient()
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: {provider!r}. Choose 'anthropic', 'groq', or 'ollama'."
        )
