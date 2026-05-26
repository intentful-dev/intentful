# tests/test_smart_validation.py — Testes para a validacao inteligente
import pytest
from pydantic import BaseModel, Field

from intentful.core.context import IntentContext
from intentful.core.registry import IntentEntry
from intentful.core.schemas import IntentResolution
from intentful.routing.smart_validation import smart_validate


class EventPayload(BaseModel):
    name: str = Field(..., description="Nome do evento")
    description: str = Field(..., description="Descricao do evento")
    max_participants: int = Field(..., description="Numero maximo de participantes")
    location: str = Field(default="Online", description="Local do evento")


def _make_entry(
    *,
    payload_model=EventPayload,
    allowed_operations=None,
    rules=None,
) -> IntentEntry:
    async def handler(payload: EventPayload):
        pass

    return IntentEntry(
        endpoint_path="/eventos/criar",
        method="POST",
        description="Criar um evento",
        context=IntentContext(
            allowed_operations=allowed_operations or ["CREATE"],
            rules=rules or [],
        ),
        handler=handler,
        payload_schema=payload_model.model_json_schema() if payload_model else None,
        payload_model=payload_model,
    )


def _make_resolution(payload: dict, **kwargs) -> IntentResolution:
    return IntentResolution(
        endpoint="/eventos/criar",
        method="POST",
        payload=payload,
        confidence=0.95,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_valid_payload_passes():
    entry = _make_entry()
    resolution = _make_resolution({
        "name": "Workshop Python",
        "description": "Intro ao Python",
        "max_participants": 50,
    })
    result = await smart_validate(resolution, entry)
    assert result.valid is True
    assert result.errors == []
    assert result.missing_fields == []
    assert result.invalid_fields == {}
    assert result.suggestion is None


@pytest.mark.asyncio
async def test_detects_missing_required_fields():
    entry = _make_entry()
    resolution = _make_resolution({"name": "Workshop Python"})
    result = await smart_validate(resolution, entry)
    assert result.valid is False
    assert "description" in result.missing_fields
    assert "max_participants" in result.missing_fields
    assert "location" not in result.missing_fields  # tem default
    assert len(result.errors) >= 2


@pytest.mark.asyncio
async def test_detects_invalid_field_types():
    entry = _make_entry()
    resolution = _make_resolution({
        "name": "Workshop",
        "description": "Intro",
        "max_participants": "nao_e_numero",
    })
    result = await smart_validate(resolution, entry)
    assert result.valid is False
    assert len(result.invalid_fields) > 0


@pytest.mark.asyncio
async def test_disallowed_operation():
    entry = IntentEntry(
        endpoint_path="/eventos/apagar",
        method="DELETE",
        description="Apagar evento",
        context=IntentContext(allowed_operations=["READ"]),
        handler=lambda: None,
        payload_schema=None,
        payload_model=None,
    )
    resolution = IntentResolution(
        endpoint="/eventos/apagar", method="DELETE",
        payload={}, confidence=0.9,
    )
    result = await smart_validate(resolution, entry)
    assert result.valid is False
    assert any("operação" in e.lower() or "permitid" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_empty_payload_lists_all_required():
    entry = _make_entry()
    resolution = _make_resolution({})
    result = await smart_validate(resolution, entry)
    assert result.valid is False
    assert "name" in result.missing_fields
    assert "description" in result.missing_fields
    assert "max_participants" in result.missing_fields


@pytest.mark.asyncio
async def test_no_payload_model_skips_field_validation():
    entry = IntentEntry(
        endpoint_path="/health",
        method="GET",
        description="Health check",
        context=IntentContext(allowed_operations=["READ"]),
        handler=lambda: {"status": "ok"},
        payload_schema=None,
        payload_model=None,
    )
    resolution = IntentResolution(
        endpoint="/health", method="GET", payload={}, confidence=0.9,
    )
    result = await smart_validate(resolution, entry)
    assert result.valid is True


@pytest.mark.asyncio
async def test_suggestion_generated_with_backend():
    class FakeBackend:
        async def complete(self, system: str, prompt: str) -> str:
            return "Falta indicar a descricao e o numero de participantes."

    entry = _make_entry()
    resolution = _make_resolution({"name": "Workshop"})
    result = await smart_validate(resolution, entry, backend=FakeBackend(), language="pt")
    assert result.valid is False
    assert result.suggestion is not None
    assert "descricao" in result.suggestion.lower() or "participantes" in result.suggestion.lower()


@pytest.mark.asyncio
async def test_suggestion_none_without_backend():
    entry = _make_entry()
    resolution = _make_resolution({"name": "Workshop"})
    result = await smart_validate(resolution, entry, backend=None)
    assert result.valid is False
    assert result.suggestion is None


@pytest.mark.asyncio
async def test_suggestion_none_on_backend_error():
    class BrokenBackend:
        async def complete(self, system: str, prompt: str) -> str:
            raise RuntimeError("API down")

    entry = _make_entry()
    resolution = _make_resolution({"name": "Workshop"})
    result = await smart_validate(resolution, entry, backend=BrokenBackend(), language="pt")
    assert result.valid is False
    assert result.suggestion is None  # falha silenciosa, sem crash


@pytest.mark.asyncio
async def test_valid_with_optional_field_included():
    entry = _make_entry()
    resolution = _make_resolution({
        "name": "Workshop",
        "description": "Intro",
        "max_participants": 50,
        "location": "Sala 101",
    })
    result = await smart_validate(resolution, entry)
    assert result.valid is True


@pytest.mark.asyncio
async def test_rules_passed_to_suggestion():
    prompts_received = []

    class SpyBackend:
        async def complete(self, system: str, prompt: str) -> str:
            prompts_received.append(prompt)
            return "Corrija os erros."

    entry = _make_entry(rules=["Maximo 100 participantes", "Nome deve ser unico"])
    resolution = _make_resolution({"name": "Workshop"})
    await smart_validate(resolution, entry, backend=SpyBackend(), language="pt")
    assert len(prompts_received) == 1
    assert "Maximo 100 participantes" in prompts_received[0]
    assert "Nome deve ser unico" in prompts_received[0]
