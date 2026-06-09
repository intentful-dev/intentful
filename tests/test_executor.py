# tests/test_executor.py — Testes do HTTP Executor
# Path: tests/test_executor.py
from __future__ import annotations


import httpx
import pytest

from intentful.server.executor import ExecutionResult, HTTPExecutor


class TestExecutionResult:
    """Testes do modelo ExecutionResult."""

    def test_success_codes(self) -> None:
        assert ExecutionResult(status_code=200, body={}).success is True
        assert ExecutionResult(status_code=201, body={}).success is True
        assert ExecutionResult(status_code=204, body=None).success is True
        assert ExecutionResult(status_code=301, body=None).success is True

    def test_error_codes(self) -> None:
        assert ExecutionResult(status_code=400, body={}).success is False
        assert ExecutionResult(status_code=404, body={}).success is False
        assert ExecutionResult(status_code=500, body={}).success is False


class TestHTTPExecutor:
    """Testes do HTTPExecutor com httpx mock."""

    def test_init(self) -> None:
        executor = HTTPExecutor(
            base_url="http://localhost:3000",
            auth_headers={"Authorization": "Bearer token123"},
        )
        assert executor._base_url == "http://localhost:3000"
        assert executor._auth_headers == {"Authorization": "Bearer token123"}

    def test_init_strips_trailing_slash(self) -> None:
        executor = HTTPExecutor(base_url="http://localhost:3000/")
        assert executor._base_url == "http://localhost:3000"

    @pytest.mark.asyncio
    async def test_execute_get(self) -> None:
        """Deve fazer GET ao backend target."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"users": [{"id": 1, "name": "João"}]})
        )

        HTTPExecutor(base_url="http://localhost:3000")

        async def mock_execute(method, path, payload=None, **kwargs):
            async with httpx.AsyncClient(transport=transport) as client:
                response = await client.request(method, f"http://localhost:3000{path}")
                return ExecutionResult(
                    status_code=response.status_code,
                    body=response.json(),
                    duration_ms=1.0,
                )

        result = await mock_execute("GET", "/users")
        assert result.success is True
        assert result.body == {"users": [{"id": 1, "name": "João"}]}

    @pytest.mark.asyncio
    async def test_execute_post(self) -> None:
        """Deve fazer POST com payload JSON."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(201, json={"id": 1, "name": "Workshop"})
        )

        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.post(
                "http://localhost:3000/events",
                json={"name": "Workshop", "capacity": 50},
            )
            result = ExecutionResult(
                status_code=response.status_code,
                body=response.json(),
                duration_ms=5.0,
            )

        assert result.success is True
        assert result.body["name"] == "Workshop"

    def test_path_params_resolution(self) -> None:
        """Deve substituir path params no template."""
        # Testar substituição directa
        path = "/users/{id}"
        params = {"id": 42}
        resolved = path
        for name, value in params.items():
            resolved = resolved.replace(f"{{{name}}}", str(value))
        assert resolved == "/users/42"

        # Múltiplos params
        path = "/orgs/{org_id}/users/{user_id}"
        params = {"org_id": 1, "user_id": 99}
        resolved = path
        for name, value in params.items():
            resolved = resolved.replace(f"{{{name}}}", str(value))
        assert resolved == "/orgs/1/users/99"
