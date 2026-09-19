class AppError(Exception):
    """Base application error."""


class UnsupportedFileType(AppError):
    pass


class ExtractionError(AppError):
    pass


class ExtractionTimeout(ExtractionError):
    """Parsing exceeded its wall-clock budget. Tracked separately: it usually means a
    hostile or pathological file rather than a bad parser."""


class UnsafeFile(AppError):
    """The file tripped a pre-parse safety limit (zip bomb, entity expansion, traversal)."""


class MalwareDetected(UnsafeFile):
    pass


class ScannerUnavailable(AppError):
    """A malware scanner is configured but unreachable. Uploads fail closed."""


class StorageError(AppError):
    pass


class ProviderError(AppError):
    """External inference provider failed (network, 5xx, bad payload)."""


class ProviderRateLimited(ProviderError):
    """Provider returned 429. Tracked separately from retrieval failures."""


class SsrfBlocked(AppError):
    """A URL resolved to an address the fetcher refuses to touch."""


class DuplicateDocument(AppError):
    """Content hash already exists in this workspace."""

    def __init__(self, message: str, existing_id: object | None = None) -> None:
        super().__init__(message)
        self.existing_id = existing_id


class PermissionDenied(AppError):
    """The caller's grants do not cover the resource. Surfaced as 404, never 403,
    so the existence of another tenant's data is not confirmable."""


class PermissionFilterMissing(AppError):
    """A retrieval query was assembled without its permission predicates.

    This is a programming error, not a user error. It exists so that deleting the
    permission filter fails loudly instead of silently widening every search.
    """


class TokenBudgetExhausted(AppError):
    """The organization's token budget for this period has been reached."""


class GenerationRateLimited(AppError):
    """The user has exceeded their per-minute generation rate limit."""


class GenerationRefused(AppError):
    """The model refused to answer because context was insufficient.

    This is not an error per se — it is the correct behavior when the corpus
    does not contain the answer. Tracked separately from provider errors.
    """
