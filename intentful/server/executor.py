# intentful/server/executor.py — Executa chamadas HTTP ao backend target
# Path: intentful/server/executor.py
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ExecutionResult:
    """Resultado de uma chamada HTTP ao backend target."""

    status_code: int
    body: Any
    headers: dict[str, str] = field(default_factory=dict)
    duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        return 200 <= self.status_code < 400


class HTTPExecutor:
    """Executa chamadas HTTP ao backend target em nome do agente.

    Recebe o endpoint resolvido pelo LLM e faz a chamada real via httpx.

    Uso:
        executor = HTTPExecutor(base_url="http://localhost:3000")
        result = await executor.execute("POST", "/events", {"name": "Workshop"})
    """

    def __init__(
        self,
        base_url: str,
        *,
        auth_headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth_headers = auth_headers or {}
        self._timeout = timeout

    async def execute(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        extra_headers: dict[str, str] | None = None,
        path_params: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Executa uma chamada HTTP ao backend target.

        Args:
            method: Método HTTP (GET, POST, PUT, PATCH, DELETE).
            path: Path do endpoint (ex: /events/{id}).
            payload: Payload JSON a enviar no body (POST/PUT/PATCH).
            extra_headers: Headers adicionais para esta chamada.
            path_params: Parâmetros para substituir no path template.

        Returns:
            ExecutionResult com status, body e duração.
        """
        # Substituir path params (ex: /events/{id} -> /events/123)
        resolved_path = path
        if path_params:
            for param_name, param_value in path_params.items():
                resolved_path = resolved_path.replace(
                    f"{{{param_name}}}", str(param_value)
                )

        url = f"{self._base_url}{resolved_path}"

        headers = {**self._auth_headers}
        if extra_headers:
            headers.update(extra_headers)

        start = time.monotonic()

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            if method.upper() in ("GET", "DELETE", "HEAD", "OPTIONS"):
                # Para GET/DELETE, payload vai como query params
                response = await client.request(
                    method.upper(),
                    url,
                    params=payload if method.upper() == "GET" and payload else None,
                    headers=headers,
                )
            else:
                # POST/PUT/PATCH — payload vai no body como JSON
                response = await client.request(
                    method.upper(),
                    url,
                    json=payload,
                    headers=headers,
                )

        duration_ms = (time.monotonic() - start) * 1000

        # Tentar parsear response como JSON, fallback para text
        try:
            body = response.json()
        except (ValueError, TypeError):
            body = response.text

        return ExecutionResult(
            status_code=response.status_code,
            body=body,
            headers=dict(response.headers),
            duration_ms=round(duration_ms, 2),
        )
