from abc import ABC, abstractmethod


class ObjectStorage(ABC):
    """Original uploaded files live here. PostgreSQL only stores the key."""

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str | None = None) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...
