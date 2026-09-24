from functools import lru_cache

from app.core.config import settings
from app.embeddings.base import EmbeddingProvider


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    provider = settings.embedding_provider.lower()
    if provider == "fake":
        from app.embeddings.fake import FakeEmbeddingProvider

        return FakeEmbeddingProvider()
    if provider == "openrouter":
        from app.embeddings.openrouter import OpenRouterEmbeddingProvider

        return OpenRouterEmbeddingProvider()
    from app.embeddings.gemini import GeminiEmbeddingProvider

    return GeminiEmbeddingProvider()
