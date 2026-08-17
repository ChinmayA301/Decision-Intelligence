"""Embedding provider abstraction for Voyage, Jina AI, or OpenAI."""
from __future__ import annotations

import os
from typing import Protocol


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_one(self, text: str) -> list[float]: ...


class VoyageEmbedder:
    def __init__(self, api_key: str | None = None, model: str = "voyage-3") -> None:
        import voyageai
        self._client = voyageai.AsyncClient(api_key=api_key or os.environ["VOYAGE_API_KEY"])
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        result = await self._client.embed(texts, model=self._model, input_type="document")
        return result.embeddings

    async def embed_one(self, text: str) -> list[float]:
        embeddings = await self.embed([text])
        return embeddings[0]


class OpenAIEmbedder:
    def __init__(self, api_key: str | None = None, model: str = "text-embedding-3-large") -> None:
        import openai
        self._client = openai.AsyncOpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in response.data]

    async def embed_one(self, text: str) -> list[float]:
        embeddings = await self.embed([text])
        return embeddings[0]


class JinaEmbedder:
    """
    Jina AI free embeddings — sign up at jina.ai.
    Default model emits 1024 dimensions, matching the current vector schema.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        import httpx

        self._client = httpx.AsyncClient(
            base_url="https://api.jina.ai/v1",
            headers={"Authorization": f"Bearer {api_key or os.environ['JINA_API_KEY']}"},
            timeout=30.0,
        )
        self._model = model or os.environ.get("JINA_MODEL", "jina-embeddings-v3")
        self._task = os.environ.get("JINA_TASK", "text-matching")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.post(
            "/embeddings",
            json={
                "model": self._model,
                "task": self._task,
                "dimensions": 1024,
                "embedding_type": "float",
                "input": texts,
            },
        )
        response.raise_for_status()
        data = response.json()["data"]
        return [item["embedding"] for item in data]

    async def embed_one(self, text: str) -> list[float]:
        embeddings = await self.embed([text])
        return embeddings[0]


_EMBEDDERS = {
    "jina": (JinaEmbedder, "JINA_API_KEY"),
    "voyage": (VoyageEmbedder, "VOYAGE_API_KEY"),
    "openai": (OpenAIEmbedder, "OPENAI_API_KEY"),
}


def get_embedder() -> EmbeddingProvider:
    """Build the configured embedding provider.

    Defaults to Jina because the bundled ``data/case_store.json`` is embedded
    with jina-embeddings-v3. Query vectors must come from the same model as the
    stored ones — a different provider produces vectors in an unrelated space,
    so similarity scores would be meaningless even when the dimensions happen to
    match. Rebuild the store with ``scripts/build_local_store.py`` if you change
    this.
    """
    provider = os.environ.get("EMBEDDING_PROVIDER", "jina").lower().strip()
    entry = _EMBEDDERS.get(provider)
    if entry is None:
        raise ValueError(
            f"Unknown EMBEDDING_PROVIDER: {provider!r}. Choose one of: "
            f"{', '.join(sorted(_EMBEDDERS))}."
        )
    cls, key_env = entry
    if not os.environ.get(key_env):
        raise RuntimeError(
            f"EMBEDDING_PROVIDER={provider} requires {key_env}. Retrieval embeds "
            "the user's decision text on every request, so this key is required "
            "even when callers bring their own LLM key."
        )
    return cls()
