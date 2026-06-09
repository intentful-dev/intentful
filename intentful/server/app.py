# intentful/server/app.py — Standalone HTTP server do agente Intentful
# Path: intentful/server/app.py
from __future__ import annotations

from dataclasses import dataclass

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from intentful.backends import LLMBackend
from intentful.conversation.resolver import ConversationalResolver
from intentful.conversation.store import InMemorySessionStore
from intentful.core.registry import IntentRegistry
from intentful.execution.auditor import Auditor
from intentful.routing.resolver import LLMResolver
from intentful.scanner.openapi import OpenAPIScanner
from intentful.scanner.registry_builder import build_registry_from_spec
from intentful.server.executor import HTTPExecutor


@dataclass
class AgentConfig:
    """Configuração do agente Intentful standalone."""

    openapi_url: str
    target_base_url: str | None = None
    backend_name: str = "anthropic"
    port: int = 8100
    host: str = "0.0.0.0"
    confidence_threshold: float = 0.7
    language: str = "pt"
    cors_origins: list[str] | None = None
    auth_headers: dict[str, str] | None = None
    exclude_paths: list[str] | None = None
    include_only: list[str] | None = None
    default_rules: list[str] | None = None


def create_agent_app(config: AgentConfig) -> FastAPI:
    """Cria a app FastAPI do agente Intentful standalone.

    Esta app:
    1. No startup, escaneia a spec OpenAPI do backend target
    2. Popula o IntentRegistry com os endpoints descobertos
    3. Serve endpoints /prompt, /health, /endpoints, /widget/intentful.js
    """
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """No startup, escaneia a spec OpenAPI e popula o registry."""
        scanner = OpenAPIScanner(
            exclude_paths=config.exclude_paths,
            include_only=config.include_only,
            default_rules=config.default_rules,
        )
        entries = await scanner.scan(config.openapi_url)
        build_registry_from_spec(
            entries,
            registry=app.state.registry,
            clear_existing=True,
        )
        yield

    app = FastAPI(
        title="Intentful Agent",
        description="AI agent that connects to any backend via OpenAPI",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — aceitar requests do widget frontend
    origins = config.cors_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # State partilhado pela app
    app.state.config = config
    app.state.registry = IntentRegistry()
    app.state.auditor = Auditor()
    app.state.session_store = InMemorySessionStore()

    # Inferir base_url do target a partir da openapi_url se não fornecido
    target_base_url = config.target_base_url
    if not target_base_url:
        # http://localhost:3000/openapi.json -> http://localhost:3000
        from urllib.parse import urlparse
        parsed = urlparse(config.openapi_url)
        target_base_url = f"{parsed.scheme}://{parsed.netloc}"

    app.state.executor = HTTPExecutor(
        base_url=target_base_url,
        auth_headers=config.auth_headers,
    )

    # Backend LLM e resolvers
    backend = _create_backend(config.backend_name)
    app.state.backend = backend
    app.state.resolver = LLMResolver(backend)
    app.state.conversational_resolver = ConversationalResolver(backend)
    app.state.confidence_threshold = config.confidence_threshold

    # Registar rotas
    from intentful.server.routes import create_routes
    router = create_routes()
    app.include_router(router)

    # Servir o widget JS
    @app.get("/widget/intentful.js", include_in_schema=False)
    async def serve_widget() -> Response:
        """Serve o widget JS para integração no frontend."""
        import importlib.resources as pkg_resources
        widget_js = pkg_resources.files("intentful.widget").joinpath("intentful.js")
        content = widget_js.read_text(encoding="utf-8")
        return Response(content=content, media_type="application/javascript")

    return app


def _create_backend(name: str) -> LLMBackend:
    """Factory para criar backends LLM por nome."""
    if name == "anthropic":
        from intentful.backends.anthropic import AnthropicBackend
        return AnthropicBackend()
    elif name == "openai":
        from intentful.backends.openai import OpenAIBackend
        return OpenAIBackend()
    elif name == "ollama":
        from intentful.backends.local import OllamaBackend
        return OllamaBackend()
    else:
        raise ValueError(f"Backend desconhecido: '{name}'. Disponíveis: anthropic, openai, ollama")
