import math

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.errors import ProviderError, ProviderRateLimited
from app.core.logging import get_logger
from app.embeddings.base import EmbeddingProvider

logger = get_logger(__name__)


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key or settings.gemini_api_key
        self._model = model or settings.gemini_embedding_model
        self._dimensions = dimensions or settings.gemini_embedding_dimensions
        self._timeout = timeout
        if not self._api_key:
            raise ProviderError("GEMINI_API_KEY is not set")

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_id(self) -> str:
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._batch_embed(texts, task_type="RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._batch_embed([text], task_type="RETRIEVAL_QUERY")[0]

    @retry(
        retry=retry_if_exception_type((ProviderRateLimited, httpx.TransportError)),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _batch_embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        url = f"{settings.gemini_api_base}/models/{self._model}:batchEmbedContents"
        payload = {
            "requests": [
                {
                    "model": f"models/{self._model}",
                    "content": {"parts": [{"text": text}]},
                    "taskType": task_type,
                    "outputDimensionality": self._dimensions,
                }
                for text in texts
            ]
        }
        try:
            response = httpx.post(
                url,
                params={"key": self._api_key},
                json=payload,
                timeout=self._timeout,
            )
        except httpx.TransportError:
            raise
        if response.status_code == 429:
            logger.warning("Gemini embedding rate limited (429)")
            raise ProviderRateLimited("Gemini embedding rate limit reached")
        if response.status_code >= 500:
            raise ProviderRateLimited(f"Gemini embedding transient error {response.status_code}")
        if response.status_code >= 400:
            raise ProviderError(f"Gemini embedding error {response.status_code}: {response.text[:400]}")

        data = response.json()
        embeddings = data.get("embeddings") or []
        if len(embeddings) != len(texts):
            raise ProviderError(
                f"Gemini returned {len(embeddings)} embeddings for {len(texts)} inputs"
            )
        return [_normalize(item.get("values") or []) for item in embeddings]


def _normalize(vector: list[float]) -> list[float]:
    """Reduced-dimension Gemini vectors are not unit length; normalize for cosine distance."""
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]
