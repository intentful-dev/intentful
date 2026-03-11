# tests/test_validator.py — Testes para o validator
from pydantic import BaseModel

from intentful.core.context import IntentContext
from intentful.core.registry import IntentEntry
from intentful.core.schemas import IntentResolution
from intentful.routing.validator import validate_resolution


class TurmaPayload(BaseModel):
    ano_lectivo: str
    curso_id: int


def test_validate_allowed_operations():
    entry = IntentEntry(
        endpoint_path="/turmas/gerar",
        method="POST",
        description="Criar turmas",
        context=IntentContext(allowed_operations=["CREATE", "READ"]),
        handler=lambda payload: None,
    )
    resolution = IntentResolution(
        endpoint="/turmas/gerar", method="POST",
        payload={"ano_lectivo": "2025/26", "curso_id": 5},
        confidence=0.95,
    )
    result = validate_resolution(resolution, entry)
    assert result.valid is True


def test_validate_disallowed_operation():
    entry = IntentEntry(
        endpoint_path="/turmas",
        method="DELETE",
        description="Apagar turmas",
        context=IntentContext(allowed_operations=["READ"]),
        handler=lambda: None,
    )
    resolution = IntentResolution(
        endpoint="/turmas", method="DELETE",
        payload={}, confidence=0.9,
    )
    result = validate_resolution(resolution, entry)
    assert result.valid is False
    assert len(result.errors) > 0


def test_validate_payload_against_schema():
    async def handler(payload: TurmaPayload):
        pass

    entry = IntentEntry(
        endpoint_path="/turmas/gerar",
        method="POST",
        description="Criar turmas",
        context=IntentContext(allowed_operations=["CREATE"]),
        handler=handler,
        payload_schema=TurmaPayload.model_json_schema(),
    )

    # Payload válido
    good = IntentResolution(
        endpoint="/turmas/gerar", method="POST",
        payload={"ano_lectivo": "2025/26", "curso_id": 5},
        confidence=0.95,
    )
    assert validate_resolution(good, entry).valid is True

    # Payload inválido (curso_id deveria ser int)
    bad = IntentResolution(
        endpoint="/turmas/gerar", method="POST",
        payload={"ano_lectivo": "2025/26", "curso_id": "abc"},
        confidence=0.95,
    )
    result = validate_resolution(bad, entry)
    assert result.valid is False
