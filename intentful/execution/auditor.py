# intentful/execution/auditor.py — Audit trail de todas as operações via prompt
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from intentful.core.schemas import IntentResolution


class AuditEntry(BaseModel):
    """Registo de auditoria de uma operação via intent."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str | None = None
    prompt: str
    resolution: IntentResolution
    confirmed: bool = False
    executed: bool = False
    result: Any = None
    error: str | None = None


class Auditor:
    """Regista e armazena audit trail de operações via intent.

    Implementação base em memória. Pode ser estendida para persistir
    em base de dados (SQLAlchemy, Oracle, etc.).
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(self, entry: AuditEntry) -> str:
        self._entries.append(entry)
        return entry.id

    def get(self, audit_id: str) -> AuditEntry | None:
        for entry in self._entries:
            if entry.id == audit_id:
                return entry
        return None

    def list_entries(
        self, user_id: str | None = None, limit: int = 100
    ) -> list[AuditEntry]:
        entries = self._entries
        if user_id:
            entries = [e for e in entries if e.user_id == user_id]
        return entries[-limit:]

    def clear(self) -> None:
        self._entries.clear()
