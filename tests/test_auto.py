# tests/test_auto.py — Testes para auto-integracao zero-config
from fastapi import FastAPI
from pydantic import BaseModel, Field

from intentful import intent, IntentContext
from intentful.backends import LLMBackend
from intentful.core.registry import get_registry
from intentful.integrations.auto import intentful_auto, _humanize_name, _infer_description, _RouteInfo


class FakeBackend(LLMBackend):
    async def complete(self, system: str, prompt: str) -> str:
        return '{"endpoint": "/test", "method": "GET", "payload": {}, "confidence": 0.9}'


# --- Modelos de teste ---

class EventPayload(BaseModel):
    name: str = Field(..., description="Nome do evento")
    max_participants: int = Field(..., description="Numero maximo de participantes")


class UserPayload(BaseModel):
    username: str
    email: str


# --- Testes de _humanize_name ---

def test_humanize_snake_case():
    assert _humanize_name("create_event") == "Create event"


def test_humanize_camel_case():
    assert _humanize_name("createEvent") == "Create event"


def test_humanize_single_word():
    assert _humanize_name("health") == "Health"


# --- Testes de _infer_description ---

def test_infer_description_from_docstring():
    def my_handler():
        """Create a new event for the system."""
        pass

    info = _RouteInfo(
        path="/events",
        method="POST",
        endpoint=my_handler,
        name="my_handler",
        summary=None,
        description_attr=None,
    )
    assert _infer_description(info) == "Create a new event for the system."


def test_infer_description_from_summary():
    def my_handler():
        pass

    info = _RouteInfo(
        path="/events",
        method="POST",
        endpoint=my_handler,
        name="my_handler",
        summary="Create an event",
        description_attr=None,
    )
    assert _infer_description(info) == "Create an event"


def test_infer_description_from_name():
    def create_event():
        pass

    info = _RouteInfo(
        path="/events",
        method="POST",
        endpoint=create_event,
        name="create_event",
        summary=None,
        description_attr=None,
    )
    assert _infer_description(info) == "Create event"


# --- Testes de intentful_auto ---

def test_auto_registers_all_routes():
    app = FastAPI()

    @app.post("/events")
    async def create_event(payload: EventPayload):
        return {"id": 1}

    @app.get("/events")
    async def list_events():
        return []

    @app.delete("/events/{event_id}")
    async def delete_event(event_id: int):
        return {"deleted": True}

    intentful_auto(app, backend=FakeBackend())

    registry = get_registry()
    assert registry.get("POST", "/events") is not None
    assert registry.get("GET", "/events") is not None
    assert registry.get("DELETE", "/events/{event_id}") is not None


def test_auto_extracts_pydantic_schema():
    app = FastAPI()

    @app.post("/events")
    async def create_event(payload: EventPayload):
        return {"id": 1}

    intentful_auto(app, backend=FakeBackend())

    entry = get_registry().get("POST", "/events")
    assert entry is not None
    assert entry.payload_model is EventPayload
    assert entry.payload_schema is not None


def test_auto_infers_operations_from_method():
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/items")
    async def create_item():
        pass

    @app.delete("/items/{id}")
    async def delete_item(id: int):
        pass

    intentful_auto(app, backend=FakeBackend())

    registry = get_registry()
    assert "READ" in registry.get("GET", "/health").context.allowed_operations
    assert "CREATE" in registry.get("POST", "/items").context.allowed_operations
    assert "DELETE" in registry.get("DELETE", "/items/{id}").context.allowed_operations


def test_auto_excludes_paths():
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/metrics")
    async def metrics():
        return {}

    @app.post("/events")
    async def create_event():
        pass

    intentful_auto(app, backend=FakeBackend(), exclude_paths=["/health", "/metrics"])

    registry = get_registry()
    assert registry.get("GET", "/health") is None
    assert registry.get("GET", "/metrics") is None
    assert registry.get("POST", "/events") is not None


def test_auto_include_only():
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/events")
    async def create_event():
        pass

    @app.get("/users")
    async def list_users():
        return []

    intentful_auto(app, backend=FakeBackend(), include_only=["/events"])

    registry = get_registry()
    assert registry.get("GET", "/health") is None
    assert registry.get("GET", "/users") is None
    assert registry.get("POST", "/events") is not None


def test_auto_skips_already_decorated_routes():
    app = FastAPI()

    @app.post("/events")
    @intent(description="Criar evento manualmente", context=IntentContext(allowed_operations=["CREATE"]), path="/events")
    async def create_event(payload: EventPayload):
        return {"id": 1}

    @app.get("/events")
    async def list_events():
        return []

    intentful_auto(app, backend=FakeBackend())

    registry = get_registry()
    # O @intent manual deve ter registado com a descricao manual
    manual_entry = registry.get("POST", "/events")
    assert manual_entry is not None
    assert manual_entry.description == "Criar evento manualmente"
    # O GET deve ter sido registado pelo auto
    assert registry.get("GET", "/events") is not None


def test_auto_applies_default_rules():
    app = FastAPI()

    @app.post("/events")
    async def create_event():
        pass

    intentful_auto(app, backend=FakeBackend(), default_rules=["Max 100 participantes"])

    entry = get_registry().get("POST", "/events")
    assert "Max 100 participantes" in entry.context.rules


def test_auto_returns_router():
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    router = intentful_auto(app, backend=FakeBackend(), confidence_threshold=0.8)
    assert router is not None
    assert router.confidence_threshold == 0.8


def test_auto_uses_docstring_as_description():
    app = FastAPI()

    @app.post("/events")
    async def create_event():
        """Criar um novo evento no sistema."""
        pass

    intentful_auto(app, backend=FakeBackend())

    entry = get_registry().get("POST", "/events")
    assert entry.description == "Criar um novo evento no sistema."


def test_auto_excludes_internal_fastapi_paths():
    """Paths como /docs, /redoc, /openapi.json devem ser ignorados por defeito."""
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    intentful_auto(app, backend=FakeBackend())

    registry = get_registry()
    assert registry.get("GET", "/docs") is None
    assert registry.get("GET", "/redoc") is None
    assert registry.get("GET", "/openapi.json") is None
