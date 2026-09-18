from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class GroundedAnswer:
    text: str
    citations: list[dict]
    model_id: str


class LLMProvider(ABC):
    """Phase 3 lands here. The interface exists now so the RAG layer never imports a vendor SDK."""

    @property
    @abstractmethod
    def model_id(self) -> str: ...

    @abstractmethod
    def generate_grounded_answer(
        self,
        question: str,
        context_chunks: list[dict],
        history: list[dict] | None = None,
    ) -> GroundedAnswer: ...
