# tests/test_schemas.py — Testes para os schemas de request/response
from intentful.core.schemas import IntentRequest, IntentResolution, IntentResponse


def test_intent_request_defaults():
    req = IntentRequest(prompt="Cria turmas para Engenharia")
    assert req.prompt == "Cria turmas para Engenharia"
    assert req.dry_run is False
    assert req.language == "pt"


def test_intent_resolution():
    res = IntentResolution(
        endpoint="/turmas/gerar",
        payload={"ano_lectivo": "2025/26", "curso_id": 5},
        confidence=0.95,
        estimated_impact="47 turmas serão criadas",
    )
    assert res.confidence == 0.95
    assert res.payload["curso_id"] == 5


def test_intent_response_success():
    res = IntentResponse(success=True, result={"created": 47})
    assert res.success is True
    assert res.confirmation_required is False


def test_intent_response_confirmation():
    res = IntentResponse(
        success=True,
        confirmation_required=True,
        confirmation_message="Confirmas?",
    )
    assert res.confirmation_required is True
