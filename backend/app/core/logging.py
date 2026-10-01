import logging

from app.core.config import settings
from app.security.privacy import redact_text


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact_text(super().format(record))



def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    for handler in logging.getLogger().handlers:
        handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
