# intentful/conversation/store.py — Armazenamento de sessoes conversacionais
# Path: intentful/conversation/store.py
from __future__ import annotations

from abc import ABC, abstractmethod

from intentful.conversation.session import ConversationSession


class SessionStore(ABC):
    """Interface abstracta para armazenamento de sessoes."""

    @abstractmethod
    async def get(self, session_id: str) -> ConversationSession | None:
        """Obtem uma sessao pelo ID. Retorna None se nao existir ou expirada."""
        ...

    @abstractmethod
    async def save(self, session: ConversationSession) -> None:
        """Guarda ou actualiza uma sessao."""
        ...

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """Remove uma sessao."""
        ...


class InMemorySessionStore(SessionStore):
    """Armazenamento de sessoes em memoria com limpeza por TTL."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}

    async def get(self, session_id: str) -> ConversationSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired:
            session.status = "expired"
            del self._sessions[session_id]
            return None
        return session

    async def save(self, session: ConversationSession) -> None:
        self._sessions[session.session_id] = session

    async def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def clear(self) -> None:
        """Limpa todas as sessoes (util para testes)."""
        self._sessions.clear()

    def __len__(self) -> int:
        return len(self._sessions)
