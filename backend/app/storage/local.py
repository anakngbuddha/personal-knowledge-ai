from pathlib import Path

from app.core.config import settings
from app.core.errors import StorageError
from app.storage.base import ObjectStorage


class LocalStorage(ObjectStorage):
    """Development-only stand-in for R2. Never use on Render (ephemeral filesystem)."""

    def __init__(self) -> None:
        self._root = Path(settings.local_storage_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        self._path(key).write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise StorageError(f"local object missing: {key}")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()
