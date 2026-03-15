# tests/test_confirmer.py — Testes para a lógica de confirmação
from __future__ import annotations

from intentful.core.context import IntentContext
from intentful.core.registry import IntentEntry
from intentful.core.schemas import IntentResolution
from intentful.execution.confirmer import build_confirmation_message, needs_confirmation


def _make_entry(**overrides) -> IntentEntry:
    defaults = {
        "endpoint_path": "/turmas/gerar",
        "method": "POST",
        "description": "Criar turmas",
        "context": IntentContext(),
        "handler": lambda: None,
    }
    defaults.update(overrides)
    return IntentEntry(**defaults)


def _make_resolution(**overrides) -> IntentResolution:
    defaults = {
        "endpoint": "/turmas/gerar",
        "method": "POST",
        "payload": {"ano_lectivo": "2025/26", "curso_id": 5},
        "confidence": 0.95,
    }
    defaults.update(overrides)
    return IntentResolution(**defaults)


def test_needs_confirmation_true():
    entry = _make_entry(context=IntentContext(requires_confirmation=True))
    assert needs_confirmation(entry) is True


def test_needs_confirmation_false():
    entry = _make_entry(context=IntentContext(requires_confirmation=False))
    assert needs_confirmation(entry) is False


def test_build_confirmation_message_with_template():
    entry = _make_entry(
        context=IntentContext(
            requires_confirmation=True,
            confirmation_template="Criar turmas para {curso_id} em {ano_lectivo}. Confirmas?",
        )
    )
    resolution = _make_resolution()
    msg = build_confirmation_message(entry, resolution)
    assert msg == "Criar turmas para 5 em 2025/26. Confirmas?"


def test_build_confirmation_message_without_template():
    entry = _make_entry(
        description="Criar turmas académicas",
        context=IntentContext(requires_confirmation=True),
    )
    resolution = _make_resolution(
        estimated_impact="3 turmas serão criadas",
    )
    msg = build_confirmation_message(entry, resolution)
    assert "Criar turmas académicas" in msg
    assert "/turmas/gerar" in msg
    assert "3 turmas serão criadas" in msg
    assert "Confirma?" in msg


def test_build_confirmation_message_without_template_no_impact():
    entry = _make_entry(context=IntentContext(requires_confirmation=True))
    resolution = _make_resolution(estimated_impact=None)
    msg = build_confirmation_message(entry, resolution)
    assert "não calculado" in msg


def test_build_confirmation_message_template_missing_key():
    """Template com placeholder que não existe no payload — devolve template raw."""
    entry = _make_entry(
        context=IntentContext(
            requires_confirmation=True,
            confirmation_template="Vou criar {turmas_count} turmas. Confirmas?",
        )
    )
    resolution = _make_resolution(payload={"ano_lectivo": "2025/26"})
    msg = build_confirmation_message(entry, resolution)
    # KeyError → devolve o template sem formatação
    assert msg == "Vou criar {turmas_count} turmas. Confirmas?"
