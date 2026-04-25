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

import os
from dataclasses import dataclass


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str


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
        response = await self._client.chat.completions.create(
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
