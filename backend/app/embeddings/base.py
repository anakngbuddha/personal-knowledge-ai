from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """The RAG layer talks to this, never to a vendor SDK directly."""

    @property
    @abstractmethod
    def dimensions(self) -> int: ...

    @property
    @abstractmethod
    def model_id(self) -> str: ...

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed chunk text for indexing."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a user question for retrieval."""
