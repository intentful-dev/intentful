# tests/test_resolver.py — Testes para o resolver e build_resolution_prompt
from __future__ import annotations

import json

import pytest

from intentful.backends import LLMBackend
from intentful.core.context import IntentContext
from intentful.core.registry import IntentEntry, IntentRegistry
from intentful.core.schemas import IntentRequest, IntentResolution, LookupConfig
from intentful.routing.resolver import LLMResolver, build_resolution_prompt


# --- Fake backends ---


class FakeBackend(LLMBackend):
    def __init__(self, response: str) -> None:
        self._response = response

    async def complete(self, system: str, prompt: str) -> str:
        return self._response


class ErrorBackend(LLMBackend):
    async def complete(self, system: str, prompt: str) -> str:
        raise ConnectionError("API unavailable")


class EmptyBackend(LLMBackend):
    async def complete(self, system: str, prompt: str) -> str:
        return ""


# --- Helpers ---


def _make_registry() -> IntentRegistry:
    registry = IntentRegistry()
    registry.register(IntentEntry(
        endpoint_path="/turmas/gerar",
        method="POST",
        description="Criar turmas",
        context=IntentContext(rules=["Capacidade máxima 40"]),
        handler=lambda: None,
        payload_schema={"type": "object"},
    ))
    return registry


# --- Testes: build_resolution_prompt ---


def test_build_resolution_prompt_includes_endpoints():
    registry = _make_registry()
    request = IntentRequest(prompt="Cria turmas", language="pt")
    prompt = build_resolution_prompt(request, registry)

    assert "/turmas/gerar" in prompt
    assert "Criar turmas" in prompt
    assert "Capacidade máxima 40" in prompt


def test_build_resolution_prompt_includes_language():
    registry = _make_registry()
    request = IntentRequest(prompt="Create classes", language="en")
    prompt = build_resolution_prompt(request, registry)

    assert "language: en" in prompt
    assert "Create classes" in prompt


def test_build_resolution_prompt_includes_resolvable_params():
    async def fake_fn(hints):
        return []

    registry = IntentRegistry()
    registry.register(IntentEntry(
        endpoint_path="/orders/{order_id}",
        method="DELETE",
        description="Apagar encomenda",
        context=IntentContext(),
        handler=lambda: None,
        lookups={
            "order_id": LookupConfig(
                search_fields=["customer_name", "created_at"],
                resolver_fn=fake_fn,
            )
        },
    ))
    request = IntentRequest(prompt="Apaga encomenda")
    prompt = build_resolution_prompt(request, registry)

    assert "resolvable_params" in prompt
    assert "customer_name" in prompt


# --- Testes: LLMResolver ---


@pytest.mark.asyncio
async def test_resolver_valid_response():
    response = json.dumps({
        "endpoint": "/turmas/gerar",
        "method": "POST",
        "payload": {"ano_lectivo": "2025/26", "curso_id": 5},
        "confidence": 0.95,
        "reasoning": "Match claro",
    })
    resolver = LLMResolver(FakeBackend(response))
    registry = _make_registry()
    request = IntentRequest(prompt="Cria turmas")

    result = await resolver.resolve(request, registry)

    assert isinstance(result, IntentResolution)
    assert result.endpoint == "/turmas/gerar"
    assert result.confidence == 0.95
    assert result.payload["curso_id"] == 5
    assert result.lookup_hints == []


@pytest.mark.asyncio
async def test_resolver_with_lookup_hints():
    response = json.dumps({
        "endpoint": "/orders/{order_id}",
        "method": "DELETE",
        "payload": {},
        "confidence": 0.9,
        "lookup_hints": [
            {"param_name": "order_id", "search_values": {"customer_name": "João"}}
        ],
    })
    resolver = LLMResolver(FakeBackend(response))
    registry = _make_registry()
    request = IntentRequest(prompt="Apaga encomenda do João")

    result = await resolver.resolve(request, registry)

    assert len(result.lookup_hints) == 1
    assert result.lookup_hints[0].param_name == "order_id"
    assert result.lookup_hints[0].search_values == {"customer_name": "João"}


@pytest.mark.asyncio
async def test_resolver_null_payload():
    """Payload null deve ser convertido para dict vazio."""
    response = json.dumps({
        "endpoint": "/turmas/gerar",
        "method": "POST",
        "payload": None,
        "confidence": 0.8,
    })
    resolver = LLMResolver(FakeBackend(response))
    result = await resolver.resolve(IntentRequest(prompt="test"), _make_registry())

    assert result.payload == {}


@pytest.mark.asyncio
async def test_resolver_backend_error():
    resolver = LLMResolver(ErrorBackend())
    with pytest.raises(RuntimeError, match="Erro ao contactar o LLM"):
        await resolver.resolve(IntentRequest(prompt="test"), _make_registry())


@pytest.mark.asyncio
async def test_resolver_empty_response():
    resolver = LLMResolver(EmptyBackend())
    with pytest.raises(RuntimeError, match="resposta vazia"):
        await resolver.resolve(IntentRequest(prompt="test"), _make_registry())


@pytest.mark.asyncio
async def test_resolver_invalid_json():
    resolver = LLMResolver(FakeBackend("this is not json"))
    with pytest.raises(RuntimeError, match="JSON inválido"):
        await resolver.resolve(IntentRequest(prompt="test"), _make_registry())
