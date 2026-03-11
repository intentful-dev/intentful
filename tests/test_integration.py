# tests/test_integration.py — Teste do fluxo completo: prompt → resolução → execução
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from intentful.backends import LLMBackend
from intentful.core.context import IntentContext
from intentful.core.decorator import intent
from intentful.core.registry import get_registry
from intentful.integrations.fastapi import IntentRouter, setup_intentful


# --- Fake LLM backend para testes (sem chamadas reais) ---


class FakeLLMBackend(LLMBackend):
    """Backend que devolve respostas pré-definidas sem chamar nenhum LLM."""

    def __init__(self, responses: list[tuple[str, dict]]) -> None:
        # Lista ordenada de (keyword, response) — primeira match ganha
        self._responses = responses

    async def complete(self, system: str, prompt: str) -> str:
        prompt_lower = prompt.lower()
        for keyword, response in self._responses:
            if keyword.lower() in prompt_lower:
                return json.dumps(response)
        return json.dumps({
            "endpoint": "/unknown",
            "method": "POST",
            "payload": {},
            "confidence": 0.1,
            "reasoning": "No matching endpoint found",
        })


# --- Schemas de teste ---


class GeraTurmasSchema(BaseModel):
    ano_lectivo: str = Field(..., description="Ano lectivo (ex: 2025/26)")
    curso_id: int = Field(..., description="ID do curso")


class MatriculaSchema(BaseModel):
    ano_lectivo: str
    count: int = 50


# --- Respostas do fake LLM ---


FAKE_RESPONSES = [
    ("matricula todos", {
        "endpoint": "/matriculas/auto",
        "method": "POST",
        "payload": {"ano_lectivo": "2025/26", "count": 120},
        "confidence": 0.92,
        "estimated_impact": "120 alunos serão matriculados",
        "reasoning": "O utilizador pediu matrícula automática",
    }),
    ("meteorologia", {
        "endpoint": "/unknown",
        "method": "POST",
        "payload": {},
        "confidence": 0.2,
        "reasoning": "Prompt não corresponde a nenhum endpoint disponível",
    }),
    ("turmas", {
        "endpoint": "/turmas/gerar",
        "method": "POST",
        "payload": {"ano_lectivo": "2025/26", "curso_id": 5},
        "confidence": 0.95,
        "estimated_impact": "3 turmas serão criadas",
        "reasoning": "O utilizador pediu para criar turmas para Engenharia",
    }),
]


# --- Estado partilhado para verificação ---

turmas_criadas: list[dict] = []


def _register_test_handlers() -> None:
    """Regista os handlers de teste no registry global."""
    registry = get_registry()
    registry.clear()
    turmas_criadas.clear()

    @intent(
        description="Criar turmas para um ano lectivo académico",
        context=IntentContext(
            rules=[
                "Cada curso tem anos curriculares definidos no plano curricular",
                "Capacidade máxima padrão é 40 alunos por turma",
            ],
            allowed_operations=["CREATE", "READ"],
            requires_confirmation=False,
        ),
        method="POST",
        path="/turmas/gerar",
        tags=["turmas", "academico"],
    )
    async def gerar_turmas(payload: GeraTurmasSchema) -> dict:
        result = {
            "turmas_criadas": 3,
            "ano_lectivo": payload.ano_lectivo,
            "curso_id": payload.curso_id,
        }
        turmas_criadas.append(result)
        return result

    @intent(
        description="Matricular alunos transitados no novo ano lectivo",
        context=IntentContext(
            rules=["Só alunos com aproveitamento podem ser matriculados"],
            allowed_operations=["CREATE"],
            requires_confirmation=True,
            confirmation_template="Vou matricular {count} alunos no ano lectivo {ano_lectivo}. Confirmas?",
        ),
        method="POST",
        path="/matriculas/auto",
        tags=["matriculas"],
    )
    async def matricular_alunos(payload: MatriculaSchema) -> dict:
        return {"matriculados": payload.count, "ano_lectivo": payload.ano_lectivo}


# --- Fixtures ---


@pytest.fixture
def app() -> FastAPI:
    """Cria uma app FastAPI com IntentRouter configurado."""
    _register_test_handlers()
    backend = FakeLLMBackend(FAKE_RESPONSES)
    app = FastAPI()
    router = IntentRouter(ai_backend=backend, language="pt", audit_trail=True)
    setup_intentful(app, router)
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- Testes do fluxo completo ---


async def test_resolve_and_execute_turmas(client: AsyncClient):
    """Fluxo completo: prompt → resolução → execução do handler."""
    response = await client.post("/intent", json={
        "prompt": "Cria turmas para o curso de Engenharia em 2025/26",
    })
    data = response.json()

    assert response.status_code == 200
    assert data["success"] is True
    assert data["resolution"]["endpoint"] == "/turmas/gerar"
    assert data["resolution"]["confidence"] == 0.95
    assert data["result"]["turmas_criadas"] == 3
    assert data["result"]["ano_lectivo"] == "2025/26"
    assert data["audit_id"] is not None


async def test_dry_run_does_not_execute(client: AsyncClient):
    """dry_run=True resolve mas não executa."""
    response = await client.post("/intent", json={
        "prompt": "Cria turmas para Engenharia 2025/26",
        "dry_run": True,
    })
    data = response.json()

    assert response.status_code == 200
    assert data["success"] is True
    assert data["resolution"]["endpoint"] == "/turmas/gerar"
    assert data["result"] is None
    assert len(turmas_criadas) == 0


async def test_low_confidence_rejected(client: AsyncClient):
    """Prompts com confiança baixa são rejeitados."""
    response = await client.post("/intent", json={
        "prompt": "Qual é a meteorologia de amanhã?",
    })
    data = response.json()

    assert response.status_code == 422
    assert data["success"] is False
    assert "Confiança insuficiente" in data["error"]


async def test_confirmation_required(client: AsyncClient):
    """Endpoint com requires_confirmation pede confirmação."""
    response = await client.post("/intent", json={
        "prompt": "Matricula todos os alunos transitados em 2025/26",
    })
    data = response.json()

    assert response.status_code == 200
    assert data["success"] is True
    assert data["confirmation_required"] is True
    assert data["confirmation_message"] is not None
    assert data["result"] is None


async def test_confirmation_confirmed_executes(client: AsyncClient):
    """Após confirmar, a operação é executada."""
    response = await client.post("/intent", json={
        "prompt": "Matricula todos os alunos transitados em 2025/26",
        "confirmed": True,
    })
    data = response.json()

    assert response.status_code == 200
    assert data["success"] is True
    assert data["result"]["matriculados"] == 120
    assert data["audit_id"] is not None


async def test_empty_registry_returns_error(client: AsyncClient):
    """Registry vazio devolve erro claro."""
    get_registry().clear()
    response = await client.post("/intent", json={
        "prompt": "Faz qualquer coisa",
    })
    data = response.json()

    assert response.status_code == 400
    assert data["success"] is False
    assert "Nenhum endpoint" in data["error"]
