"""LLM provider factory.

Mirrors the embedding factory pattern: reads `LLM_PROVIDER` from settings and
returns the configured provider. The provider is cached for the process lifetime
(same as the embedding provider).
"""

from functools import lru_cache

from app.core.config import settings
from app.llm.base import LLMProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "fake":
        from app.llm.fake import FakeLLMProvider

        return FakeLLMProvider()
    if provider == "openrouter":
        from app.llm.openrouter import OpenRouterLLMProvider

        return OpenRouterLLMProvider()
    from app.llm.fallback import FallbackLLMProvider
    from app.llm.gemini import GeminiLLMProvider

    return FallbackLLMProvider(GeminiLLMProvider())
