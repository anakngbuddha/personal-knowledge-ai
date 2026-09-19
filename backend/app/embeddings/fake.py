import hashlib
import math

from app.core.config import settings
from app.embeddings.base import EmbeddingProvider


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic hash-based vectors. For tests and offline development only."""

    def __init__(self, dimensions: int | None = None) -> None:
        self._dimensions = dimensions or settings.gemini_embedding_dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_id(self) -> str:
        return "fake-deterministic"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        values: list[float] = []
        counter = 0
        while len(values) < self._dimensions:
            digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
            values.extend(byte / 255.0 - 0.5 for byte in digest)
            counter += 1
        values = values[: self._dimensions]
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]
