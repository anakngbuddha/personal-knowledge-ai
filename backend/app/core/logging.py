import logging

from app.core.config import settings
from app.security.privacy import redact_text


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact_text(super().format(record))


class HealthCheckFilter(logging.Filter):
    """Filter out frequent health check probes from uvicorn access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "GET /health " not in msg and "GET /health HTTP" not in msg


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    for handler in logging.getLogger().handlers:
        handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
