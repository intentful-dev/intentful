# intentful/conversation/session.py — Modelos de sessao conversacional
# Path: intentful/conversation/session.py
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


@dataclass
class FieldSpec:
    """Especificacao de um campo do payload Pydantic."""

    name: str
    type_str: str
    description: str | None
    required: bool
    default: Any | None


@dataclass
class ConversationTurn:
    """Um turno na conversa (pergunta ou resposta)."""

    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ConversationSession:
    """Estado de uma sessao conversacional em curso."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    endpoint_path: str | None = None
    method: str | None = None
    collected_fields: dict[str, Any] = field(default_factory=dict)
    pending_fields: list[FieldSpec] = field(default_factory=list)
    current_field_index: int = 0
    status: Literal["resolving", "collecting", "ready", "completed", "expired"] = "resolving"
    history: list[ConversationTurn] = field(default_factory=list)
    language: str = "pt"
    ttl_seconds: int = 300

    @property
    def current_field(self) -> FieldSpec | None:
        """Campo actualmente a ser recolhido."""
        if self.current_field_index < len(self.pending_fields):
            return self.pending_fields[self.current_field_index]
        return None

    @property
    def is_expired(self) -> bool:
        """Verifica se a sessao expirou."""
        elapsed = (datetime.now(timezone.utc) - self.updated_at).total_seconds()
        return elapsed > self.ttl_seconds

    def add_turn(self, role: Literal["user", "assistant"], content: str) -> None:
        """Adiciona um turno a historia."""
        self.history.append(ConversationTurn(role=role, content=content))
        self.updated_at = datetime.now(timezone.utc)

    def advance_field(self) -> None:
        """Avanca para o proximo campo pendente."""
        self.current_field_index += 1
        if self.current_field_index >= len(self.pending_fields):
            self.status = "ready"
