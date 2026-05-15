# tests/test_lookup.py — Testes para o two-step lookup resolution
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from intentful.backends import LLMBackend
from intentful.core.context import IntentContext
from intentful.core.decorator import intent
from intentful.core.registry import IntentEntry, IntentRegistry, get_registry
from intentful.core.schemas import (
    IntentResolution,
    LookupCandidate,
    LookupConfig,
    LookupHint,
)
from intentful.integrations.fastapi import IntentRouter, setup_intentful
from intentful.routing.lookup import (
    apply_resolved_params,
    needs_lookup,
    resolve_lookups,
)


# --- Helpers ---


async def fake_search_orders(hints: dict) -> list[dict]:
    """Simula uma busca de encomendas."""
    orders = [
        {"id": "abc-456", "customer_name": "João", "created_at": "2026-03-14", "total": 45.00},
        {"id": "def-789", "customer_name": "João", "created_at": "2026-03-10", "total": 120.00},
        {"id": "ghi-012", "customer_name": "Maria", "created_at": "2026-03-14", "total": 30.00},
    ]
    results = []
    for order in orders:
        match = True
        for field, value in hints.items():
            if field in order and str(order[field]).lower() != str(value).lower():
                match = False
                break
        if match:
            results.append(order)
    return results


async def fake_search_empty(hints: dict) -> list[dict]:
    """Simula uma busca que não devolve resultados."""
    return []


async def fake_search_error(hints: dict) -> list[dict]:
    """Simula um erro na busca."""
    raise RuntimeError("Database connection failed")


# --- Testes unitários: needs_lookup ---


def test_needs_lookup_true():
    resolution = IntentResolution(
        endpoint="/orders/{order_id}",
        method="DELETE",
        payload={},
        confidence=0.9,
        lookup_hints=[LookupHint(param_name="order_id", search_values={"customer_name": "João"})],
    )
    entry = IntentEntry(
        endpoint_path="/orders/{order_id}",
        method="DELETE",
        description="Apagar encomenda",
        context=IntentContext(),
        handler=lambda: None,
        lookups={
            "order_id": LookupConfig(
                search_fields=["customer_name"],
                resolver_fn=fake_search_orders,
            )
        },
    )
    assert needs_lookup(resolution, entry) is True


def test_needs_lookup_false_no_hints():
    resolution = IntentResolution(
        endpoint="/turmas/gerar",
        method="POST",
        payload={"ano": "2025/26"},
        confidence=0.9,
    )
    entry = IntentEntry(
        endpoint_path="/turmas/gerar",
        method="POST",
        description="Criar turmas",
        context=IntentContext(),
        handler=lambda: None,
    )
    assert needs_lookup(resolution, entry) is False


def test_needs_lookup_false_no_config():
    resolution = IntentResolution(
        endpoint="/orders/{order_id}",
        method="DELETE",
        payload={},
        confidence=0.9,
        lookup_hints=[LookupHint(param_name="order_id", search_values={"customer_name": "João"})],
    )
    entry = IntentEntry(
        endpoint_path="/orders/{order_id}",
        method="DELETE",
        description="Apagar encomenda",
        context=IntentContext(),
        handler=lambda: None,
    )
    assert needs_lookup(resolution, entry) is False


# --- Testes unitários: resolve_lookups ---


@pytest.mark.asyncio
async def test_resolve_lookups_single_match():
    config = LookupConfig(
        search_fields=["customer_name", "created_at"],
        resolver_fn=fake_search_orders,
        id_field="id",
        display_fields=["customer_name", "total"],
    )
    resolution = IntentResolution(
        endpoint="/orders/{order_id}",
        method="DELETE",
        payload={},
        confidence=0.9,
        lookup_hints=[
            LookupHint(param_name="order_id", search_values={"customer_name": "Maria", "created_at": "2026-03-14"})
        ],
    )
    entry = IntentEntry(
        endpoint_path="/orders/{order_id}",
        method="DELETE",
        description="Apagar encomenda",
        context=IntentContext(),
        handler=lambda: None,
        lookups={"order_id": config},
    )

    results = await resolve_lookups(resolution, entry)

    assert "order_id" in results
    assert len(results["order_id"]) == 1
    assert results["order_id"][0].id_value == "ghi-012"
    assert results["order_id"][0].display == {"customer_name": "Maria", "total": 30.00}


@pytest.mark.asyncio
async def test_resolve_lookups_multiple_matches():
    config = LookupConfig(
        search_fields=["customer_name"],
        resolver_fn=fake_search_orders,
        id_field="id",
        display_fields=["customer_name", "total"],
    )
    resolution = IntentResolution(
        endpoint="/orders/{order_id}",
        method="DELETE",
        payload={},
        confidence=0.9,
        lookup_hints=[
            LookupHint(param_name="order_id", search_values={"customer_name": "João"})
        ],
    )
    entry = IntentEntry(
        endpoint_path="/orders/{order_id}",
        method="DELETE",
        description="Apagar encomenda",
        context=IntentContext(),
        handler=lambda: None,
        lookups={"order_id": config},
    )

    results = await resolve_lookups(resolution, entry)

    assert len(results["order_id"]) == 2
    ids = [c.id_value for c in results["order_id"]]
    assert "abc-456" in ids
    assert "def-789" in ids


@pytest.mark.asyncio
async def test_resolve_lookups_no_matches():
    config = LookupConfig(
        search_fields=["customer_name"],
        resolver_fn=fake_search_orders,
        id_field="id",
    )
    resolution = IntentResolution(
        endpoint="/orders/{order_id}",
        method="DELETE",
        payload={},
        confidence=0.9,
        lookup_hints=[
            LookupHint(param_name="order_id", search_values={"customer_name": "Carlos"})
        ],
    )
    entry = IntentEntry(
        endpoint_path="/orders/{order_id}",
        method="DELETE",
        description="Apagar encomenda",
        context=IntentContext(),
        handler=lambda: None,
        lookups={"order_id": config},
    )

    results = await resolve_lookups(resolution, entry)
    assert results["order_id"] == []


@pytest.mark.asyncio
async def test_resolve_lookups_filters_invalid_search_fields():
    """Valores de busca com campos não registados são ignorados."""
    config = LookupConfig(
        search_fields=["customer_name"],
        resolver_fn=fake_search_orders,
        id_field="id",
    )
    resolution = IntentResolution(
        endpoint="/orders/{order_id}",
        method="DELETE",
        payload={},
        confidence=0.9,
        lookup_hints=[
            LookupHint(param_name="order_id", search_values={"invalid_field": "xyz"})
        ],
    )
    entry = IntentEntry(
        endpoint_path="/orders/{order_id}",
        method="DELETE",
        description="Apagar encomenda",
        context=IntentContext(),
        handler=lambda: None,
        lookups={"order_id": config},
    )

    results = await resolve_lookups(resolution, entry)
    assert "order_id" not in results


@pytest.mark.asyncio
async def test_resolve_lookups_missing_config():
    """Hint para param sem config registada é ignorada."""
    resolution = IntentResolution(
        endpoint="/orders/{order_id}",
        method="DELETE",
        payload={},
        confidence=0.9,
        lookup_hints=[
            LookupHint(param_name="order_id", search_values={"customer_name": "João"})
        ],
    )
    entry = IntentEntry(
        endpoint_path="/orders/{order_id}",
        method="DELETE",
        description="Apagar encomenda",
        context=IntentContext(),
        handler=lambda: None,
        lookups={},
    )

    results = await resolve_lookups(resolution, entry)
    assert results == {}


@pytest.mark.asyncio
async def test_resolve_lookups_resolver_error():
    """Erro no resolver_fn propaga LookupError."""
    from intentful.routing.lookup import LookupError

    config = LookupConfig(
        search_fields=["customer_name"],
        resolver_fn=fake_search_error,
        id_field="id",
    )
    resolution = IntentResolution(
        endpoint="/orders/{order_id}",
        method="DELETE",
        payload={},
        confidence=0.9,
        lookup_hints=[
            LookupHint(param_name="order_id", search_values={"customer_name": "João"})
        ],
    )
    entry = IntentEntry(
        endpoint_path="/orders/{order_id}",
        method="DELETE",
        description="Apagar encomenda",
        context=IntentContext(),
        handler=lambda: None,
        lookups={"order_id": config},
    )

    with pytest.raises(LookupError, match="Database connection failed"):
        await resolve_lookups(resolution, entry)


# --- Testes unitários: apply_resolved_params ---


def test_apply_resolved_params():
    resolution = IntentResolution(
        endpoint="/orders/{order_id}",
        method="DELETE",
        payload={"extra": "data"},
        confidence=0.9,
        lookup_hints=[LookupHint(param_name="order_id", search_values={"customer_name": "João"})],
    )
    result = apply_resolved_params(resolution, {"order_id": "abc-456"})

    assert result.endpoint == "/orders/abc-456"
    assert result.payload["order_id"] == "abc-456"
    assert result.payload["extra"] == "data"
    assert result.lookup_hints == []


def test_apply_resolved_params_multiple():
    resolution = IntentResolution(
        endpoint="/courses/{course_id}/students/{student_id}",
        method="GET",
        payload={},
        confidence=0.9,
        lookup_hints=[
            LookupHint(param_name="course_id", search_values={"name": "Eng"}),
            LookupHint(param_name="student_id", search_values={"name": "João"}),
        ],
    )
    result = apply_resolved_params(resolution, {"course_id": 5, "student_id": 42})

    assert result.endpoint == "/courses/5/students/42"
    assert result.payload["course_id"] == 5
    assert result.payload["student_id"] == 42


# --- Testes unitários: registry com lookups ---


def test_registry_prompt_context_includes_resolvable_params():
    config = LookupConfig(
        search_fields=["customer_name", "created_at"],
        resolver_fn=fake_search_orders,
        id_field="id",
    )
    entry = IntentEntry(
        endpoint_path="/orders/{order_id}",
        method="DELETE",
        description="Apagar encomenda",
        context=IntentContext(),
        handler=lambda: None,
        lookups={"order_id": config},
    )
    ctx = entry.to_prompt_context()

    assert "resolvable_params" in ctx
    assert "order_id" in ctx["resolvable_params"]
    assert ctx["resolvable_params"]["order_id"]["search_fields"] == ["customer_name", "created_at"]


def test_registry_prompt_context_no_resolvable_params_without_lookups():
    entry = IntentEntry(
        endpoint_path="/turmas/gerar",
        method="POST",
        description="Criar turmas",
        context=IntentContext(),
        handler=lambda: None,
    )
    ctx = entry.to_prompt_context()
    assert "resolvable_params" not in ctx


# --- Testes de integração: fluxo completo com lookup ---


class FakeLLMBackend(LLMBackend):
    def __init__(self, responses: list[tuple[str, dict]]) -> None:
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
        })


LOOKUP_RESPONSES = [
    ("apaga a encomenda da maria", {
        "endpoint": "/orders/{order_id}",
        "method": "DELETE",
        "payload": {},
        "confidence": 0.9,
        "reasoning": "Utilizador quer apagar encomenda",
        "lookup_hints": [
            {"param_name": "order_id", "search_values": {"customer_name": "Maria", "created_at": "2026-03-14"}}
        ],
    }),
    ("apaga a encomenda do joão", {
        "endpoint": "/orders/{order_id}",
        "method": "DELETE",
        "payload": {},
        "confidence": 0.9,
        "reasoning": "Utilizador quer apagar encomenda do João",
        "lookup_hints": [
            {"param_name": "order_id", "search_values": {"customer_name": "João"}}
        ],
    }),
    ("apaga a encomenda do carlos", {
        "endpoint": "/orders/{order_id}",
        "method": "DELETE",
        "payload": {},
        "confidence": 0.9,
        "lookup_hints": [
            {"param_name": "order_id", "search_values": {"customer_name": "Carlos"}}
        ],
    }),
]

deleted_orders: list[str] = []


def _register_lookup_handlers() -> None:
    get_registry().clear()
    deleted_orders.clear()

    @intent(
        description="Apagar uma encomenda",
        context=IntentContext(allowed_operations=["DELETE"]),
        method="DELETE",
        path="/orders/{order_id}",
        lookups={
            "order_id": LookupConfig(
                search_fields=["customer_name", "created_at"],
                resolver_fn=fake_search_orders,
                id_field="id",
                display_fields=["customer_name", "total"],
            )
        },
    )
    async def delete_order(order_id: str) -> dict:
        deleted_orders.append(order_id)
        return {"deleted": order_id}


@pytest.fixture
def lookup_app() -> FastAPI:
    _register_lookup_handlers()
    backend = FakeLLMBackend(LOOKUP_RESPONSES)
    app = FastAPI()
    router = IntentRouter(ai_backend=backend, language="pt", audit_trail=False)
    setup_intentful(app, router)
    return app


@pytest.fixture
async def lookup_client(lookup_app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=lookup_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_integration_lookup_single_match(lookup_client: AsyncClient):
    """1 match → auto-resolve e executa."""
    response = await lookup_client.post("/intent", json={
        "prompt": "Apaga a encomenda da Maria de 14 de Março",
    })
    data = response.json()

    assert response.status_code == 200
    assert data["success"] is True
    assert data["resolution"]["endpoint"] == "/orders/ghi-012"
    assert data["result"]["deleted"] == "ghi-012"


@pytest.mark.asyncio
async def test_integration_lookup_multiple_matches(lookup_client: AsyncClient):
    """N matches → devolve candidatos para escolha."""
    response = await lookup_client.post("/intent", json={
        "prompt": "Apaga a encomenda do João",
    })
    data = response.json()

    assert response.status_code == 200
    assert data["success"] is True
    assert data["confirmation_required"] is True
    assert data["lookup_results"] is not None
    assert len(data["lookup_results"]["order_id"]) == 2
    assert data["result"] is None


@pytest.mark.asyncio
async def test_integration_lookup_no_matches(lookup_client: AsyncClient):
    """0 matches → erro 404."""
    response = await lookup_client.post("/intent", json={
        "prompt": "Apaga a encomenda do Carlos",
    })
    data = response.json()

    assert response.status_code == 404
    assert data["success"] is False
    assert "order_id" in data["error"]
