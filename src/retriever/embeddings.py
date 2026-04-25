"""Embedding provider abstraction — Voyage (preferred) or OpenAI fallback."""
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


def get_embedder() -> EmbeddingProvider:
    provider = os.environ.get("EMBEDDING_PROVIDER", "voyage").lower()
    if provider == "voyage":
        return VoyageEmbedder()
    elif provider == "openai":
        return OpenAIEmbedder()
    else:
        raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider!r}")
