# intentful/integrations/auto.py — Auto-integracao zero-config para apps FastAPI existentes
# Path: intentful/integrations/auto.py
from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI
from starlette.routing import Route

from intentful.backends import LLMBackend
from intentful.core.context import IntentContext
from intentful.core.decorator import _extract_payload_info
from intentful.core.registry import IntentEntry, get_registry
from intentful.integrations.fastapi import IntentRouter, setup_intentful
from intentful.routing.validator import _method_to_operations


# Paths internos do FastAPI que devem ser ignorados por defeito
_DEFAULT_EXCLUDE = {"/docs", "/redoc", "/openapi.json", "/intent"}


def intentful_auto(
    app: FastAPI,
    *,
    backend: str | LLMBackend = "anthropic",
    language: str | list[str] = "pt",
    confidence_threshold: float = 0.7,
    audit_trail: bool = True,
    exclude_paths: list[str] | None = None,
    include_only: list[str] | None = None,
    default_rules: list[str] | None = None,
) -> IntentRouter:
    """Integra o intentful automaticamente numa app FastAPI existente.

    Escaneia todas as rotas da app, regista-as no IntentRegistry com
    descricoes inferidas, e adiciona o endpoint /intent e o middleware.

    Uso:
        app = FastAPI()
        # ... todas as rotas normais ...
        intentful_auto(app, backend="anthropic")

    Args:
        app: A aplicacao FastAPI existente.
        backend: Backend LLM a usar ("anthropic", "openai", "ollama" ou instancia LLMBackend).
        language: Lingua(s) para prompts.
        confidence_threshold: Limiar minimo de confianca (0-1).
        audit_trail: Se True, activa o registo de auditoria.
        exclude_paths: Paths a excluir do scan (alem dos defaults internos).
        include_only: Se definido, so estas paths sao incluidas (modo whitelist).
        default_rules: Regras de negocio aplicadas a todas as entries.

    Returns:
        O IntentRouter criado, para customizacao adicional se necessario.
    """
    excluded = _DEFAULT_EXCLUDE | set(exclude_paths or [])
    rules = default_rules or []
    registry = get_registry()

    for route_info in _scan_routes(app, excluded, include_only):
        entry = _build_entry(route_info, rules)
        registry.register(entry)

    router = IntentRouter(
        ai_backend=backend,
        language=language,
        confidence_threshold=confidence_threshold,
        audit_trail=audit_trail,
    )
    setup_intentful(app, router)
    return router


def _scan_routes(
    app: FastAPI,
    excluded: set[str],
    include_only: list[str] | None,
) -> list[_RouteInfo]:
    """Escaneia as rotas da app e devolve informacao estruturada."""
    results: list[_RouteInfo] = []

    for route in app.routes:
        if not isinstance(route, Route):
            continue

        path = route.path
        if path in excluded:
            continue
        if include_only is not None and path not in include_only:
            continue

        # Saltar rotas ja decoradas com @intent
        endpoint = route.endpoint
        if hasattr(endpoint, "_intent_entry"):
            continue

        methods = getattr(route, "methods", None) or {"GET"}
        for method in methods:
            results.append(
                _RouteInfo(
                    path=path,
                    method=method.upper(),
                    endpoint=endpoint,
                    name=route.name or endpoint.__name__,
                    summary=getattr(route, "summary", None),
                    description_attr=getattr(route, "description", None),
                )
            )

    return results


def _build_entry(route_info: _RouteInfo, default_rules: list[str]) -> IntentEntry:
    """Constroi um IntentEntry a partir de informacao de rota."""
    description = _infer_description(route_info)
    operations = _method_to_operations(route_info.method)
    payload_schema, payload_model = _extract_payload_info(route_info.endpoint)

    context = IntentContext(
        allowed_operations=operations,
        rules=list(default_rules),
    )

    return IntentEntry(
        endpoint_path=route_info.path,
        method=route_info.method,
        description=description,
        context=context,
        handler=route_info.endpoint,
        payload_schema=payload_schema,
        payload_model=payload_model,
    )


def _infer_description(route_info: _RouteInfo) -> str:
    """Infere a descricao de um endpoint por ordem de prioridade."""
    # 1. Docstring do handler
    doc = route_info.endpoint.__doc__
    if doc:
        first_line = doc.strip().split("\n")[0].strip()
        if first_line:
            return first_line

    # 2. summary ou description do route (FastAPI kwargs)
    if route_info.summary:
        return route_info.summary
    if route_info.description_attr:
        first_line = route_info.description_attr.strip().split("\n")[0].strip()
        if first_line:
            return first_line

    # 3. Nome da funcao humanizado
    return _humanize_name(route_info.name)


def _humanize_name(name: str) -> str:
    """Converte nome de funcao em descricao legivel.

    Exemplos:
        create_event -> "Create event"
        get_user_by_id -> "Get user by id"
        listarTurmas -> "Listar turmas"
    """
    # camelCase -> snake_case
    name = re.sub(r"([a-z])([A-Z])", r"\1_\2", name)
    # snake_case -> palavras
    words = name.replace("_", " ").strip().lower()
    if words:
        return words[0].upper() + words[1:]
    return name


class _RouteInfo:
    """Informacao extraida de uma rota FastAPI."""

    __slots__ = ("path", "method", "endpoint", "name", "summary", "description_attr")

    def __init__(
        self,
        *,
        path: str,
        method: str,
        endpoint: Any,
        name: str,
        summary: str | None,
        description_attr: str | None,
    ) -> None:
        self.path = path
        self.method = method
        self.endpoint = endpoint
        self.name = name
        self.summary = summary
        self.description_attr = description_attr
