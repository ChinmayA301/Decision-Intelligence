"""
LLM provider abstraction.

Two ways to supply a model:

1. **Server-configured** — set ``LLM_PROVIDER`` and the matching key in the
   environment. This is what a self-hosted or locally-run instance uses.

2. **Per-request (bring your own key)** — the caller passes provider, model and
   API key with a single request. The credentials are used to build a client for
   that request only: they are never written to disk, never logged, and never
   held past the response. This lets a public demo run on visitors' own quota
   instead of the operator's.

Security note: the base URL for each provider comes from ``PROVIDERS`` below and
is never taken from caller input. Accepting a caller-supplied URL would let an
attacker point the request at a host they control and harvest the API key, and
would turn the server into an SSRF pivot. ``ollama`` reads its URL from the
server's own environment, which is operator-controlled, not caller-controlled.
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


@dataclass(frozen=True)
class ProviderSpec:
    """Static description of a supported provider. Base URLs live here only."""

    name: str
    label: str
    kind: str  # "openai_compatible" | "anthropic"
    default_model: str
    key_env: str | None
    model_env: str | None
    base_url: str | None = None
    requires_key: bool = True
    key_hint: str = ""
    signup_url: str = ""


PROVIDERS: dict[str, ProviderSpec] = {
    "groq": ProviderSpec(
        name="groq",
        label="Groq",
        kind="openai_compatible",
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        key_env="GROQ_API_KEY",
        model_env="GROQ_MODEL",
        key_hint="gsk_…",
        signup_url="https://console.groq.com/keys",
    ),
    "anthropic": ProviderSpec(
        name="anthropic",
        label="Anthropic",
        kind="anthropic",
        default_model="claude-sonnet-5",
        key_env="ANTHROPIC_API_KEY",
        model_env="ANTHROPIC_MODEL",
        key_hint="sk-ant-…",
        signup_url="https://console.anthropic.com/settings/keys",
    ),
    "openai": ProviderSpec(
        name="openai",
        label="OpenAI",
        kind="openai_compatible",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        key_env="OPENAI_API_KEY",
        model_env="OPENAI_MODEL",
        key_hint="sk-…",
        signup_url="https://platform.openai.com/api-keys",
    ),
    "openrouter": ProviderSpec(
        name="openrouter",
        label="OpenRouter",
        kind="openai_compatible",
        base_url="https://openrouter.ai/api/v1",
        default_model="meta-llama/llama-3.3-70b-instruct",
        key_env="OPENROUTER_API_KEY",
        model_env="OPENROUTER_MODEL",
        key_hint="sk-or-…",
        signup_url="https://openrouter.ai/keys",
    ),
    "ollama": ProviderSpec(
        name="ollama",
        label="Ollama (local)",
        kind="openai_compatible",
        base_url=None,  # resolved from OLLAMA_BASE_URL at construction time
        default_model="llama3.1:8b",
        key_env=None,
        model_env="OLLAMA_MODEL",
        requires_key=False,
        key_hint="(no key needed)",
        signup_url="https://ollama.com/download",
    ),
}


class UnknownProviderError(ValueError):
    pass


class MissingCredentialError(ValueError):
    pass


async def _call_with_rate_limit_retry(fn, *args, **kwargs):
    """Retry transient 429s. Free tiers are tight — Groq's free tier allows about
    12k tokens/minute and one brief uses most of that — so a second brief inside
    the same minute would otherwise fail. Honors the provider's 'try again in Ns'
    hint when present. Daily caps are not retried past the attempt budget; those
    surface to the caller so the UI can say the quota is exhausted."""
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

    provider: str = "unknown"
    model: str = "unknown"

    async def complete(
        self,
        system: str,
        messages: list[Message],
        max_tokens: int = 1024,
    ) -> str:
        raise NotImplementedError


# ─── Anthropic provider ───────────────────────────────────────────────────────

class AnthropicClient(LLMClient):
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        import anthropic

        spec = PROVIDERS["anthropic"]
        key = api_key or os.environ.get(spec.key_env or "")
        if not key:
            raise MissingCredentialError("Anthropic requires an API key.")
        self._client = anthropic.AsyncAnthropic(api_key=key)
        self.provider = "anthropic"
        self.model = model or os.environ.get(spec.model_env or "", "") or spec.default_model

    async def complete(self, system: str, messages: list[Message], max_tokens: int = 1024) -> str:
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        return response.content[0].text


# ─── OpenAI-compatible providers (Groq, OpenAI, OpenRouter, Ollama) ───────────

class OpenAICompatibleClient(LLMClient):
    """One client for every provider that speaks the OpenAI chat API.

    ``base_url`` is taken from the provider registry, never from caller input.
    """

    def __init__(
        self,
        spec: ProviderSpec,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        from openai import AsyncOpenAI

        key = api_key or (os.environ.get(spec.key_env) if spec.key_env else None)
        if spec.requires_key and not key:
            raise MissingCredentialError(f"{spec.label} requires an API key.")

        base_url = spec.base_url
        if spec.name == "ollama":
            base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")

        self._client = AsyncOpenAI(base_url=base_url, api_key=key or "not-needed")
        self.provider = spec.name
        self.model = model or os.environ.get(spec.model_env or "", "") or spec.default_model

    async def complete(self, system: str, messages: list[Message], max_tokens: int = 1024) -> str:
        all_messages = [{"role": "system", "content": system}]
        all_messages += [{"role": m.role, "content": m.content} for m in messages]
        response = await _call_with_rate_limit_retry(
            self._client.chat.completions.create,
            model=self.model,
            messages=all_messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""


# ─── Factory ──────────────────────────────────────────────────────────────────

def build_llm_client(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> LLMClient:
    """Build a client for one provider.

    Passing ``api_key`` builds a request-scoped client that leaves no trace: the
    key is held only by the returned object and is never logged or persisted.
    Omitting it falls back to the server's own environment.
    """
    name = (provider or os.environ.get("LLM_PROVIDER", "groq")).lower().strip()
    spec = PROVIDERS.get(name)
    if spec is None:
        raise UnknownProviderError(
            f"Unknown provider {name!r}. Supported: {', '.join(sorted(PROVIDERS))}."
        )
    if spec.kind == "anthropic":
        return AnthropicClient(model=model, api_key=api_key)
    return OpenAICompatibleClient(spec, model=model, api_key=api_key)


def get_llm_client() -> LLMClient:
    """Server-configured client, built from environment variables only."""
    return build_llm_client()


def server_provider_configured() -> bool:
    """True when the server has its own usable credentials, i.e. a visitor can
    generate a brief without supplying a key. Drives the UI's 'key required'
    state — checked without ever constructing a client or touching a key value."""
    name = os.environ.get("LLM_PROVIDER", "groq").lower().strip()
    spec = PROVIDERS.get(name)
    if spec is None:
        return False
    if not spec.requires_key:
        return True
    return bool(spec.key_env and os.environ.get(spec.key_env))
