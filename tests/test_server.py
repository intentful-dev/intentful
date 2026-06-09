# tests/test_server.py — Testes do standalone server
# Path: tests/test_server.py
from __future__ import annotations


import pytest
from fastapi.testclient import TestClient

from intentful.core.context import IntentContext
from intentful.core.registry import IntentEntry
from intentful.server.app import AgentConfig, create_agent_app
from intentful.scanner.openapi import _noop_handler


SAMPLE_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Test API", "version": "1.0.0"},
    "paths": {
        "/users": {
            "get": {
                "summary": "List all users",
                "responses": {"200": {"description": "OK"}},
            },
            "post": {
                "summary": "Create a new user",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "email": {"type": "string"},
                                },
                                "required": ["name", "email"],
                            }
                        }
                    }
                },
                "responses": {"201": {"description": "Created"}},
            },
        },
    },
}


@pytest.fixture
def app_with_registry():
    """Cria app com registry pré-populado (sem scan real)."""
    config = AgentConfig(
        openapi_url="http://localhost:3000/openapi.json",
        target_base_url="http://localhost:3000",
        backend_name="anthropic",
    )
    app = create_agent_app(config)

    # Pré-popular registry manualmente
    registry = app.state.registry
    registry.register(
        IntentEntry(
            endpoint_path="/users",
            method="GET",
            description="List all users",
            context=IntentContext(allowed_operations=["READ"]),
            handler=_noop_handler,
        )
    )
    registry.register(
        IntentEntry(
            endpoint_path="/users",
            method="POST",
            description="Create a new user",
            context=IntentContext(allowed_operations=["CREATE"]),
            handler=_noop_handler,
            payload_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                },
                "required": ["name", "email"],
            },
        )
    )

    return app


class TestHealthEndpoint:
    """Testes do endpoint /health."""

    def test_health(self, app_with_registry) -> None:
        client = TestClient(app_with_registry, raise_server_exceptions=False)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
        assert data["endpoints_discovered"] == 2


class TestEndpointsListing:
    """Testes do endpoint /endpoints."""

    def test_list_endpoints(self, app_with_registry) -> None:
        client = TestClient(app_with_registry, raise_server_exceptions=False)
        response = client.get("/endpoints")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        methods = {e["method"] for e in data}
        assert "GET" in methods
        assert "POST" in methods


class TestWidgetServing:
    """Testes de servir o widget JS."""

    def test_serve_widget(self, app_with_registry) -> None:
        client = TestClient(app_with_registry, raise_server_exceptions=False)
        response = client.get("/widget/intentful.js")
        assert response.status_code == 200
        assert "application/javascript" in response.headers["content-type"]
        assert "Intentful" in response.text
        assert "init" in response.text


class TestPromptEndpoint:
    """Testes do endpoint /prompt."""

    def test_empty_registry_returns_503(self) -> None:
        """Se nenhum endpoint foi descoberto, deve retornar 503."""
        config = AgentConfig(
            openapi_url="http://localhost:3000/openapi.json",
            target_base_url="http://localhost:3000",
        )
        app = create_agent_app(config)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/prompt", json={"prompt": "lista utilizadores"})
        assert response.status_code == 503
