from abc import ABC, abstractmethod


class OcrProvider(ABC):
    """Optical character recognition for PDFs with no text layer."""

    name: str = "ocr"

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def image_to_text(self, image_bytes: bytes) -> str: ...
