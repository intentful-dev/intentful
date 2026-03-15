# intentful/backends/local.py — Modelos locais via Ollama (placeholder para Fase 2)
from __future__ import annotations

from intentful.backends import LLMBackend


class OllamaBackend(LLMBackend):
    """Backend que usa modelos locais via Ollama."""

    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
    ) -> None:
        import httpx

        self.model = model
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=120.0)

    async def complete(self, system: str, prompt: str) -> str:
        response = await self.client.post(
            "/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
