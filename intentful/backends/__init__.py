# intentful/backends/__init__.py — Interface e backends LLM
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMBackend(ABC):
    """Interface base para backends LLM."""

    @abstractmethod
    async def complete(self, system: str, prompt: str) -> str:
        """Envia prompt ao LLM e devolve a resposta como string."""
        ...


__all__ = [
    "LLMBackend",
]
