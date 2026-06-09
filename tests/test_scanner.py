# tests/test_scanner.py — Testes do OpenAPI Scanner
# Path: tests/test_scanner.py
from __future__ import annotations


import pytest

from intentful.scanner.openapi import OpenAPIScanner
from intentful.scanner.registry_builder import build_registry_from_spec
from intentful.core.registry import IntentRegistry


# Spec OpenAPI de exemplo para testes
SAMPLE_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Test API", "version": "1.0.0"},
    "paths": {
        "/users": {
            "get": {
                "summary": "List all users",
                "operationId": "listUsers",
                "responses": {"200": {"description": "OK"}},
            },
            "post": {
                "summary": "Create a new user",
                "operationId": "createUser",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "email": {"type": "string", "format": "email"},
                                    "age": {"type": "integer"},
                                },
                                "required": ["name", "email"],
                            }
                        }
                    }
                },
                "responses": {"201": {"description": "Created"}},
            },
        },
        "/users/{id}": {
            "get": {
                "summary": "Get user by ID",
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"},
                    }
                ],
                "responses": {"200": {"description": "OK"}},
            },
            "put": {
                "summary": "Update user",
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"},
                    }
                ],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "email": {"type": "string"},
                                },
                            }
                        }
                    }
                },
                "responses": {"200": {"description": "OK"}},
            },
            "delete": {
                "summary": "Delete user",
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"},
                    }
                ],
                "responses": {"204": {"description": "Deleted"}},
            },
        },
        "/health": {
            "get": {
                "summary": "Health check",
                "responses": {"200": {"description": "OK"}},
            },
        },
    },
}

SPEC_WITH_REFS = {
    "openapi": "3.0.0",
    "info": {"title": "Ref Test", "version": "1.0.0"},
    "components": {
        "schemas": {
            "EventCreate": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "capacity": {"type": "integer"},
                },
                "required": ["name"],
            }
        }
    },
    "paths": {
        "/events": {
            "post": {
                "summary": "Create event",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/EventCreate"}
                        }
                    }
                },
                "responses": {"201": {"description": "Created"}},
            }
        }
    },
}


class TestOpenAPIScanner:
    """Testes do parser de specs OpenAPI."""

    @pytest.fixture
    def scanner(self) -> OpenAPIScanner:
        return OpenAPIScanner()

    def test_parse_spec_basic(self, scanner: OpenAPIScanner) -> None:
        """Deve extrair todos os endpoints (excepto /health que é excluído)."""
        entries = scanner._parse_spec(SAMPLE_SPEC)
        paths = [(e.method, e.endpoint_path) for e in entries]

        assert ("GET", "/users") in paths
        assert ("POST", "/users") in paths
        assert ("GET", "/users/{id}") in paths
        assert ("PUT", "/users/{id}") in paths
        assert ("DELETE", "/users/{id}") in paths
        # /health deve ser excluído por defeito
        assert ("GET", "/health") not in paths

    def test_descriptions_extracted(self, scanner: OpenAPIScanner) -> None:
        """Deve extrair summary como descrição."""
        entries = scanner._parse_spec(SAMPLE_SPEC)
        get_users = next(e for e in entries if e.method == "GET" and e.endpoint_path == "/users")
        assert get_users.description == "List all users"

    def test_payload_schema_extracted(self, scanner: OpenAPIScanner) -> None:
        """Deve extrair JSON Schema do request body."""
        entries = scanner._parse_spec(SAMPLE_SPEC)
        post_users = next(e for e in entries if e.method == "POST" and e.endpoint_path == "/users")
        assert post_users.payload_schema is not None
        assert "name" in post_users.payload_schema["properties"]
        assert "email" in post_users.payload_schema["properties"]
        assert "name" in post_users.payload_schema["required"]

    def test_operations_inferred(self, scanner: OpenAPIScanner) -> None:
        """Deve inferir operações correctas do método HTTP."""
        entries = scanner._parse_spec(SAMPLE_SPEC)

        get_users = next(e for e in entries if e.method == "GET" and e.endpoint_path == "/users")
        assert get_users.context.allowed_operations == ["READ"]

        post_users = next(e for e in entries if e.method == "POST" and e.endpoint_path == "/users")
        assert "CREATE" in post_users.context.allowed_operations

        put_user = next(e for e in entries if e.method == "PUT")
        assert put_user.context.allowed_operations == ["UPDATE"]

        delete_user = next(e for e in entries if e.method == "DELETE")
        assert delete_user.context.allowed_operations == ["DELETE"]

    def test_path_parameters_extracted(self, scanner: OpenAPIScanner) -> None:
        """Deve converter path parameters para o schema."""
        entries = scanner._parse_spec(SAMPLE_SPEC)
        get_user = next(e for e in entries if e.method == "GET" and e.endpoint_path == "/users/{id}")
        assert get_user.payload_schema is not None
        assert "id" in get_user.payload_schema["properties"]

    def test_exclude_paths(self) -> None:
        """Deve respeitar exclude_paths customizados."""
        scanner = OpenAPIScanner(exclude_paths=["/users"])
        entries = scanner._parse_spec(SAMPLE_SPEC)
        paths = [e.endpoint_path for e in entries]
        assert "/users" not in paths

    def test_include_only(self) -> None:
        """Deve respeitar include_only como whitelist."""
        scanner = OpenAPIScanner(include_only=["/users"])
        entries = scanner._parse_spec(SAMPLE_SPEC)
        paths = set(e.endpoint_path for e in entries)
        assert paths == {"/users"}

    def test_default_rules_applied(self) -> None:
        """Deve aplicar regras default a todas as entries."""
        scanner = OpenAPIScanner(default_rules=["Só admins podem usar"])
        entries = scanner._parse_spec(SAMPLE_SPEC)
        for entry in entries:
            assert "Só admins podem usar" in entry.context.rules

    def test_ref_resolution(self, scanner: OpenAPIScanner) -> None:
        """Deve resolver $ref para schemas em components."""
        entries = scanner._parse_spec(SPEC_WITH_REFS)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.payload_schema is not None
        assert "name" in entry.payload_schema["properties"]
        assert "capacity" in entry.payload_schema["properties"]

    def test_humanize_name(self) -> None:
        """Deve converter operationId em descrição legível."""
        assert OpenAPIScanner._humanize_name("createEvent") == "Create event"
        assert OpenAPIScanner._humanize_name("get_user_by_id") == "Get user by id"
        assert OpenAPIScanner._humanize_name("listUsers") == "List users"

    def test_description_fallback_to_operation_id(self, scanner: OpenAPIScanner) -> None:
        """Deve usar operationId humanizado quando não há summary."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/items": {
                    "get": {
                        "operationId": "getAllItems",
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
        entries = scanner._parse_spec(spec)
        assert entries[0].description == "Get all items"

    def test_description_fallback_to_method_path(self, scanner: OpenAPIScanner) -> None:
        """Deve usar 'METHOD /path' como último fallback."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/items": {
                    "get": {
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
        entries = scanner._parse_spec(spec)
        assert entries[0].description == "GET /items"


class TestRegistryBuilder:
    """Testes do registry builder."""

    def test_build_registry(self) -> None:
        """Deve popular o registry com entries do scanner."""
        scanner = OpenAPIScanner()
        entries = scanner._parse_spec(SAMPLE_SPEC)
        registry = build_registry_from_spec(entries, registry=IntentRegistry())

        assert len(registry) == len(entries)
        assert registry.get("GET", "/users") is not None
        assert registry.get("POST", "/users") is not None

    def test_clear_existing(self) -> None:
        """Deve limpar entries existentes se clear_existing=True."""
        registry = IntentRegistry()
        scanner = OpenAPIScanner()
        entries = scanner._parse_spec(SAMPLE_SPEC)

        build_registry_from_spec(entries, registry=registry)
        initial_count = len(registry)

        # Rebuild com clear
        build_registry_from_spec(entries[:1], registry=registry, clear_existing=True)
        assert len(registry) == 1
        assert len(registry) < initial_count

    def test_to_prompt_context(self) -> None:
        """Deve gerar contexto para o LLM."""
        scanner = OpenAPIScanner()
        entries = scanner._parse_spec(SAMPLE_SPEC)
        registry = build_registry_from_spec(entries, registry=IntentRegistry())

        context = registry.to_prompt_context()
        assert len(context) == len(entries)
        assert all("endpoint" in c for c in context)
        assert all("method" in c for c in context)
        assert all("description" in c for c in context)
