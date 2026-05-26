# tests/test_conversation.py — Testes para o modo conversacional/faseado
import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from intentful import intent, IntentContext
from intentful.backends import LLMBackend
from intentful.conversation.fields import extract_field_specs, identify_missing_fields
from intentful.conversation.resolver import ConversationalResolver
from intentful.conversation.session import ConversationSession, FieldSpec
from intentful.conversation.store import InMemorySessionStore
from intentful.core.registry import IntentEntry, get_registry
from intentful.integrations.fastapi import IntentRouter, setup_intentful


# --- Modelos de teste ---

class EventPayload(BaseModel):
    name: str = Field(..., description="Nome do evento")
    description: str = Field(..., description="Descricao do evento")
    max_participants: int = Field(..., description="Numero maximo de participantes")
    location: str = Field(default="Online", description="Local do evento")


# --- Testes de extract_field_specs ---

def test_extract_field_specs_required_first():
    specs = extract_field_specs(EventPayload)
    names = [s.name for s in specs]
    # Obrigatorios primeiro, opcionais depois
    assert names == ["name", "description", "max_participants", "location"]
    assert specs[0].required is True
    assert specs[1].required is True
    assert specs[2].required is True
    assert specs[3].required is False


def test_extract_field_specs_descriptions():
    specs = extract_field_specs(EventPayload)
    name_spec = next(s for s in specs if s.name == "name")
    assert name_spec.description == "Nome do evento"
    assert name_spec.type_str == "str"


def test_extract_field_specs_default():
    specs = extract_field_specs(EventPayload)
    loc_spec = next(s for s in specs if s.name == "location")
    assert loc_spec.required is False
    assert loc_spec.default == "Online"


# --- Testes de identify_missing_fields ---

def test_identify_missing_all():
    specs = extract_field_specs(EventPayload)
    missing = identify_missing_fields(specs, {})
    names = [s.name for s in missing]
    assert "name" in names
    assert "description" in names
    assert "max_participants" in names
    assert "location" not in names  # opcional


def test_identify_missing_partial():
    specs = extract_field_specs(EventPayload)
    missing = identify_missing_fields(specs, {"name": "Workshop"})
    names = [s.name for s in missing]
    assert "name" not in names
    assert "description" in names


def test_identify_missing_none():
    specs = extract_field_specs(EventPayload)
    missing = identify_missing_fields(specs, {
        "name": "W", "description": "D", "max_participants": 10
    })
    assert missing == []


# --- Testes de InMemorySessionStore ---

@pytest.mark.asyncio
async def test_store_save_and_get():
    store = InMemorySessionStore()
    session = ConversationSession()
    await store.save(session)
    retrieved = await store.get(session.session_id)
    assert retrieved is not None
    assert retrieved.session_id == session.session_id


@pytest.mark.asyncio
async def test_store_get_nonexistent():
    store = InMemorySessionStore()
    assert await store.get("nao-existe") is None


@pytest.mark.asyncio
async def test_store_delete():
    store = InMemorySessionStore()
    session = ConversationSession()
    await store.save(session)
    await store.delete(session.session_id)
    assert await store.get(session.session_id) is None


@pytest.mark.asyncio
async def test_store_expired_session():
    store = InMemorySessionStore()
    session = ConversationSession(ttl_seconds=0)  # expira imediatamente
    await store.save(session)
    # Apos TTL, a sessao deve ser removida
    retrieved = await store.get(session.session_id)
    assert retrieved is None


# --- Testes de ConversationSession ---

def test_session_current_field():
    session = ConversationSession()
    session.pending_fields = [
        FieldSpec(name="name", type_str="str", description="Nome", required=True, default=None),
        FieldSpec(name="desc", type_str="str", description="Desc", required=True, default=None),
    ]
    assert session.current_field.name == "name"
    session.advance_field()
    assert session.current_field.name == "desc"
    session.advance_field()
    assert session.current_field is None
    assert session.status == "ready"


def test_session_add_turn():
    session = ConversationSession()
    session.add_turn("user", "ola")
    session.add_turn("assistant", "como posso ajudar?")
    assert len(session.history) == 2
    assert session.history[0].role == "user"
    assert session.history[1].role == "assistant"


# --- Testes de ConversationalResolver ---

class FakeConversationalBackend(LLMBackend):
    """Backend fake que responde de forma deterministica para testes conversacionais."""

    def __init__(self):
        self.call_count = 0
        self.calls = []

    async def complete(self, system: str, prompt: str) -> str:
        self.call_count += 1
        self.calls.append({"system": system, "prompt": prompt})
        combined = system + " " + prompt

        # Resolver endpoint
        if "Available endpoints" in prompt:
            return json.dumps({
                "endpoint": "/eventos/criar",
                "method": "POST",
                "payload": {},
                "confidence": 0.95,
                "reasoning": "User wants to create an event",
            })

        # Extracao de valor de campo (verificar ANTES de "extract" generico)
        if "user_answer" in prompt:
            answer = prompt.replace("<user_answer>", "").replace("</user_answer>", "").strip()
            # Tentar converter para int se o campo for numerico
            # Verificar "Type: int" no system prompt (mais especifico que "int" generico)
            if "Type: int" in system or "max_participants" in system:
                try:
                    val = int(answer)
                    return json.dumps({"value": val, "valid": True})
                except ValueError:
                    return json.dumps({"value": None, "valid": False, "error": "Deve ser um numero"})
            return json.dumps({"value": answer, "valid": True})

        # Extracao de campos iniciais
        if "Extract any field values" in combined:
            if "Workshop de Python" in combined:
                return json.dumps({"name": "Workshop de Python"})
            return json.dumps({})

        # Geracao de pergunta
        if "question" in combined.lower() or "friendly" in combined.lower():
            if "name" in combined.lower() and "field" in combined.lower():
                return "Qual o nome do evento?"
            if "description" in combined.lower() or "descricao" in combined.lower():
                return "Qual a descricao do evento?"
            if "max_participants" in combined.lower() or "participantes" in combined.lower():
                return "Quantas pessoas podem participar?"
            return "Por favor, indique o valor."

        return json.dumps({})


def _register_event_entry():
    """Regista um endpoint de teste no registry."""
    async def criar_evento(payload: EventPayload):
        return {"id": 1, "evento": payload.model_dump()}

    entry = IntentEntry(
        endpoint_path="/eventos/criar",
        method="POST",
        description="Criar um novo evento",
        context=IntentContext(allowed_operations=["CREATE"]),
        handler=criar_evento,
        payload_schema=EventPayload.model_json_schema(),
        payload_model=EventPayload,
    )
    get_registry().register(entry)
    return entry


@pytest.mark.asyncio
async def test_start_session_no_initial_fields():
    _register_event_entry()
    backend = FakeConversationalBackend()
    resolver = ConversationalResolver(backend, get_registry())

    session = await resolver.start_session("criar evento", language="pt")

    assert session.status == "collecting"
    assert session.endpoint_path == "/eventos/criar"
    assert session.method == "POST"
    assert len(session.pending_fields) > 0
    assert len(session.history) >= 2  # user + assistant
    assert session.history[-1].role == "assistant"


@pytest.mark.asyncio
async def test_start_session_with_initial_fields():
    _register_event_entry()

    class BackendWithInitial(FakeConversationalBackend):
        async def complete(self, system: str, prompt: str) -> str:
            if "Available endpoints" in prompt:
                return json.dumps({
                    "endpoint": "/eventos/criar",
                    "method": "POST",
                    "payload": {},
                    "confidence": 0.95,
                })
            if "Extract any field values" in system or "extract" in system.lower():
                return json.dumps({
                    "name": "Workshop Python",
                    "description": "Intro ao Python",
                    "max_participants": 50,
                })
            return await super().complete(system, prompt)

    resolver = ConversationalResolver(BackendWithInitial(), get_registry())
    session = await resolver.start_session(
        "criar evento Workshop Python, Intro ao Python, 50 pessoas"
    )

    assert session.status == "ready"
    assert session.collected_fields["name"] == "Workshop Python"


@pytest.mark.asyncio
async def test_continue_session_collects_field():
    _register_event_entry()
    backend = FakeConversationalBackend()
    resolver = ConversationalResolver(backend, get_registry())

    session = await resolver.start_session("criar evento")
    assert session.status == "collecting"

    # Responder ao primeiro campo (name)
    session = await resolver.continue_session(session, "Workshop de IA")
    assert "name" in session.collected_fields

    # Responder ao segundo campo (description)
    session = await resolver.continue_session(session, "Introducao a inteligencia artificial")
    assert "description" in session.collected_fields

    # Responder ao terceiro campo (max_participants)
    session = await resolver.continue_session(session, "30")
    assert "max_participants" in session.collected_fields
    assert session.status == "ready"


@pytest.mark.asyncio
async def test_continue_session_invalid_value_retries():
    _register_event_entry()
    backend = FakeConversationalBackend()
    resolver = ConversationalResolver(backend, get_registry())

    session = await resolver.start_session("criar evento")
    # Preencher name e description primeiro
    session = await resolver.continue_session(session, "Workshop")
    session = await resolver.continue_session(session, "Desc")

    # Agora estamos no max_participants (int) — enviar texto invalido
    session = await resolver.continue_session(session, "nao_e_numero")
    # Deve continuar em collecting, sem avancar
    assert session.status == "collecting"
    assert "max_participants" not in session.collected_fields


# --- Testes de integracao HTTP ---

def _create_test_app() -> tuple[FastAPI, FakeConversationalBackend]:
    """Cria uma app FastAPI de teste com modo conversacional."""
    backend = FakeConversationalBackend()
    app = FastAPI()
    router = IntentRouter(ai_backend=backend, language="pt")

    @router.post("/eventos/criar")
    @intent(
        description="Criar um novo evento",
        context=IntentContext(allowed_operations=["CREATE"]),
        path="/eventos/criar",
    )
    async def criar_evento(payload: EventPayload):
        return {"id": 1, "evento": payload.model_dump()}

    setup_intentful(app, router)
    return app, backend


@pytest.mark.asyncio
async def test_http_conversational_start():
    app, _ = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/intent", json={
            "prompt": "criar evento",
            "mode": "conversational",
        })

    data = resp.json()
    assert resp.status_code == 200
    assert "session_id" in data
    assert data["status"] == "collecting"
    assert data["question"] is not None


@pytest.mark.asyncio
async def test_http_conversational_continue():
    app, _ = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Iniciar
        resp1 = await client.post("/intent", json={
            "prompt": "criar evento",
            "mode": "conversational",
        })
        session_id = resp1.json()["session_id"]

        # Continuar — responder ao primeiro campo
        resp2 = await client.post("/intent", json={
            "prompt": "Workshop de IA",
            "mode": "conversational",
            "session_id": session_id,
        })

    data = resp2.json()
    assert resp2.status_code == 200
    assert data["session_id"] == session_id
    assert "Workshop de IA" in str(data["collected_fields"])


@pytest.mark.asyncio
async def test_http_conversational_expired_session():
    app, _ = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/intent", json={
            "prompt": "ola",
            "mode": "conversational",
            "session_id": "sessao-inexistente",
        })

    assert resp.status_code == 404
    data = resp.json()
    assert data["status"] == "expired"


@pytest.mark.asyncio
async def test_http_single_mode_unchanged():
    """Verificar que mode=single (default) continua a funcionar normalmente."""
    app, _ = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/intent", json={
            "prompt": "criar evento Workshop para 50 pessoas",
        })

    # O modo single usa o fluxo normal (IntentResponse, nao ConversationResponse)
    data = resp.json()
    assert "success" in data  # IntentResponse tem campo "success"
