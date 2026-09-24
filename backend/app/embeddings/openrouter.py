"""OpenRouter embedding provider.

Nemotron 3 Embed 1B returns a fixed 2048-d vector. The stored index is the
Gemini width (768 by default). This provider refuses before any HTTP call
when those widths differ, so a misconfigured switch cannot write or query
the wrong space.
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.errors import ProviderError, ProviderRateLimited
from app.core.logging import get_logger
from app.embeddings.base import EmbeddingProvider

logger = get_logger(__name__)


class OpenRouterEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.openrouter_api_key
        self._model = model or settings.openrouter_embedding_model
        self._dimensions = (
            dimensions if dimensions is not None else settings.openrouter_embedding_dimensions
        )
        self._timeout = timeout

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_id(self) -> str:
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_index_compatible()
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        self._ensure_index_compatible()
        return self._embed([text])[0]

    def _ensure_index_compatible(self) -> None:
        stored = settings.gemini_embedding_dimensions
        if self._dimensions != stored:
            raise ProviderError(
                f"OpenRouter embeddings are {self._dimensions}-d; this database stores "
                f"{stored}-d vectors. Migrate the embedding column and re-embed every chunk "
                "before setting EMBEDDING_PROVIDER=openrouter."
            )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not self._api_key:
            raise ProviderError("OPENROUTER_API_KEY is not set")
        response = httpx.post(
            f"{settings.openrouter_api_base.rstrip('/')}/embeddings",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self._model, "input": texts},
            timeout=self._timeout,
        )
        if response.status_code == 429 or response.status_code >= 500:
            logger.warning("OpenRouter embedding error %s", response.status_code)
            raise ProviderRateLimited(f"OpenRouter embedding error {response.status_code}")
        if response.status_code >= 400:
            raise ProviderError(
                f"OpenRouter embedding error {response.status_code}: {response.text[:400]}"
            )
        rows = sorted((response.json().get("data") or []), key=lambda row: row.get("index", 0))
        vectors = [list(row.get("embedding") or []) for row in rows]
        if len(vectors) != len(texts):
            raise ProviderError(
                f"OpenRouter returned {len(vectors)} embeddings for {len(texts)} inputs"
            )
        for vector in vectors:
            if len(vector) != self._dimensions:
                raise ProviderError(
                    f"OpenRouter returned a {len(vector)}-d vector; expected {self._dimensions}"
                )
        return vectors
