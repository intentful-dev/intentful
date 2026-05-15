# intentful/execution/__init__.py — Execução, auditoria e confirmação
from intentful.execution.auditor import AuditEntry, Auditor
from intentful.execution.confirmer import build_confirmation_message, needs_confirmation

__all__ = [
    "AuditEntry",
    "Auditor",
    "build_confirmation_message",
    "needs_confirmation",
]
