from functools import lru_cache

from app.core.config import settings
from app.storage.base import ObjectStorage


@lru_cache
def get_storage() -> ObjectStorage:
    if settings.storage_backend == "local":
        from app.storage.local import LocalStorage

        return LocalStorage()
    from app.storage.r2 import R2Storage

    return R2Storage()
