# tests/test_core.py — Testes para o core: decorator, context, registry
from pydantic import BaseModel

from intentful.core.context import IntentContext
from intentful.core.decorator import intent
from intentful.core.registry import IntentEntry, IntentRegistry, get_registry


class DummyPayload(BaseModel):
    ano_lectivo: str
    curso_id: int


def test_intent_context_defaults():
    ctx = IntentContext()
    assert ctx.rules == []
    assert ctx.allowed_operations == ["READ"]
    assert ctx.requires_confirmation is False
    assert ctx.confirmation_template is None


def test_intent_context_custom():
    ctx = IntentContext(
        rules=["Máximo 40 alunos por turma"],
        allowed_operations=["CREATE", "READ"],
        requires_confirmation=True,
        confirmation_template="Vais criar {count} turmas. Confirmas?",
    )
    assert len(ctx.rules) == 1
    assert "CREATE" in ctx.allowed_operations
    assert ctx.requires_confirmation is True


def test_registry_register_and_get():
    registry = IntentRegistry()
    entry = IntentEntry(
        endpoint_path="/turmas/gerar",
        method="POST",
        description="Criar turmas",
        context=IntentContext(),
        handler=lambda: None,
    )
    registry.register(entry)
    assert len(registry) == 1
    assert registry.get("POST", "/turmas/gerar") is not None
    assert registry.get("GET", "/turmas/gerar") is None


def test_registry_to_prompt_context():
    registry = IntentRegistry()
    entry = IntentEntry(
        endpoint_path="/turmas/gerar",
        method="POST",
        description="Criar turmas",
        context=IntentContext(rules=["Regra 1"]),
        handler=lambda: None,
        payload_schema={"type": "object"},
    )
    registry.register(entry)
    ctx = registry.to_prompt_context()
    assert len(ctx) == 1
    assert ctx[0]["endpoint"] == "/turmas/gerar"
    assert ctx[0]["rules"] == ["Regra 1"]


def test_intent_decorator_registers_handler():
    # Limpar registry global antes do teste
    get_registry().clear()

    @intent(
        description="Criar turmas para um ano lectivo",
        context=IntentContext(
            rules=["Capacidade máxima 40 alunos"],
            allowed_operations=["CREATE", "READ"],
            requires_confirmation=True,
        ),
        path="/turmas/gerar",
    )
    async def gerar_turmas(payload: DummyPayload):
        return {"ok": True}

    registry = get_registry()
    assert len(registry) == 1
    entry = registry.get("POST", "/turmas/gerar")
    assert entry is not None
    assert entry.description == "Criar turmas para um ano lectivo"
    assert entry.context.requires_confirmation is True
    assert entry.payload_schema is not None
    assert "properties" in entry.payload_schema


def test_intent_decorator_extracts_schema():
    get_registry().clear()

    @intent(description="Test", path="/test")
    async def test_handler(payload: DummyPayload):
        pass

    entry = get_registry().get("POST", "/test")
    assert entry is not None
    schema = entry.payload_schema
    assert schema is not None
    assert "ano_lectivo" in schema.get("properties", {})
    assert "curso_id" in schema.get("properties", {})


def test_registry_filter_by_tags():
    registry = IntentRegistry()
    registry.register(IntentEntry(
        endpoint_path="/a", method="POST", description="A",
        context=IntentContext(), handler=lambda: None, tags=["turmas"],
    ))
    registry.register(IntentEntry(
        endpoint_path="/b", method="POST", description="B",
        context=IntentContext(), handler=lambda: None, tags=["matriculas"],
    ))
    assert len(registry.filter_by_tags(["turmas"])) == 1
    assert len(registry.filter_by_tags(["turmas", "matriculas"])) == 2
