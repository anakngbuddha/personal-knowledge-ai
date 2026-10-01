from pathlib import Path

from app.core.config import settings
from app.core.errors import StorageError
from app.storage.base import ObjectStorage


class LocalStorage(ObjectStorage):
    """Development-only stand-in for R2. Never use on Render (ephemeral filesystem)."""

    def __init__(self) -> None:
        self._root = Path(settings.local_storage_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key or Path(key).is_absolute():
            raise StorageError("invalid object key")
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root) or path == self._root:
            raise StorageError("invalid object key")
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

    def list_page(self, prefix, cursor=None, limit=100):
        from itertools import islice
        from datetime import datetime, timezone
        base = (self._root / prefix).resolve()
        if not base.is_relative_to(self._root):
            raise StorageError("invalid inventory prefix")
        try:
            offset = int(cursor or "0")
        except ValueError as exc:
            raise StorageError("invalid inventory cursor") from exc
        if not 0 <= offset <= 100000 or not 1 <= limit <= 500:
            raise StorageError("inventory limit exceeded")
        paths = list(islice(base.rglob("*"), offset, offset + limit))
        rows = []
        for path in paths:
            resolved = path.resolve()
            if resolved.is_relative_to(base) and resolved.is_file():
                rows.append({"key": resolved.relative_to(self._root).as_posix(), "modified": datetime.fromtimestamp(resolved.stat().st_mtime, timezone.utc)})
        return rows, str(offset + len(paths)) if len(paths) == limit else None
