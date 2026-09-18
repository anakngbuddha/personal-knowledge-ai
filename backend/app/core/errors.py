class AppError(Exception):
    """Base application error."""


class UnsupportedFileType(AppError):
    pass


class ExtractionError(AppError):
    pass


class StorageError(AppError):
    pass


class ProviderError(AppError):
    """External inference provider failed (network, 5xx, bad payload)."""


class ProviderRateLimited(ProviderError):
    """Provider returned 429. Tracked separately from retrieval failures."""
