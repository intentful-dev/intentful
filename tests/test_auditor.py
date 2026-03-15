# tests/test_auditor.py — Testes para o audit trail
from __future__ import annotations

from intentful.core.schemas import IntentResolution
from intentful.execution.auditor import AuditEntry, Auditor


def _make_resolution(**overrides) -> IntentResolution:
    defaults = {
        "endpoint": "/turmas/gerar",
        "method": "POST",
        "payload": {"ano_lectivo": "2025/26"},
        "confidence": 0.95,
    }
    defaults.update(overrides)
    return IntentResolution(**defaults)


def _make_audit_entry(**overrides) -> AuditEntry:
    defaults = {
        "prompt": "Cria turmas para Engenharia",
        "resolution": _make_resolution(),
    }
    defaults.update(overrides)
    return AuditEntry(**defaults)


def test_audit_entry_defaults():
    entry = _make_audit_entry()
    assert entry.id is not None
    assert entry.timestamp is not None
    assert entry.user_id is None
    assert entry.confirmed is False
    assert entry.executed is False
    assert entry.result is None
    assert entry.error is None


def test_audit_entry_with_user():
    entry = _make_audit_entry(user_id="user-123", confirmed=True)
    assert entry.user_id == "user-123"
    assert entry.confirmed is True


def test_auditor_record_and_get():
    auditor = Auditor()
    entry = _make_audit_entry()
    audit_id = auditor.record(entry)

    assert audit_id == entry.id
    retrieved = auditor.get(audit_id)
    assert retrieved is not None
    assert retrieved.prompt == "Cria turmas para Engenharia"


def test_auditor_get_nonexistent():
    auditor = Auditor()
    assert auditor.get("nonexistent-id") is None


def test_auditor_list_entries():
    auditor = Auditor()
    for i in range(5):
        auditor.record(_make_audit_entry(prompt=f"Prompt {i}"))

    entries = auditor.list_entries()
    assert len(entries) == 5


def test_auditor_list_entries_with_limit():
    auditor = Auditor()
    for i in range(10):
        auditor.record(_make_audit_entry(prompt=f"Prompt {i}"))

    entries = auditor.list_entries(limit=3)
    assert len(entries) == 3
    # Deve devolver os últimos 3
    assert entries[0].prompt == "Prompt 7"
    assert entries[2].prompt == "Prompt 9"


def test_auditor_list_entries_filter_by_user():
    auditor = Auditor()
    auditor.record(_make_audit_entry(user_id="alice"))
    auditor.record(_make_audit_entry(user_id="bob"))
    auditor.record(_make_audit_entry(user_id="alice"))
    auditor.record(_make_audit_entry(user_id=None))

    alice_entries = auditor.list_entries(user_id="alice")
    assert len(alice_entries) == 2

    bob_entries = auditor.list_entries(user_id="bob")
    assert len(bob_entries) == 1


def test_auditor_clear():
    auditor = Auditor()
    auditor.record(_make_audit_entry())
    auditor.record(_make_audit_entry())
    assert len(auditor.list_entries()) == 2

    auditor.clear()
    assert len(auditor.list_entries()) == 0


def test_auditor_entry_mutation():
    """Verificar que se pode actualizar o estado de uma entry após registo."""
    auditor = Auditor()
    entry = _make_audit_entry()
    audit_id = auditor.record(entry)

    retrieved = auditor.get(audit_id)
    assert retrieved is not None
    retrieved.executed = True
    retrieved.result = {"turmas_criadas": 3}

    # Re-obter e verificar que a mutação persistiu (referência partilhada)
    again = auditor.get(audit_id)
    assert again is not None
    assert again.executed is True
    assert again.result == {"turmas_criadas": 3}


def test_audit_entry_unique_ids():
    """Cada entry deve ter um ID único."""
    entries = [_make_audit_entry() for _ in range(10)]
    ids = {e.id for e in entries}
    assert len(ids) == 10
