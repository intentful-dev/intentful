# intentful/backends/anthropic.py — Claude como motor de resolução
from __future__ import annotations

from intentful.backends import LLMBackend


class AnthropicBackend(LLMBackend):
    """Backend que usa a API da Anthropic (Claude) para resolução de intents."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 1024,
    ) -> None:
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "O pacote 'anthropic' é necessário para usar o AnthropicBackend. "
                "Instale com: pip install intentful[anthropic]"
            )

        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    async def complete(self, system: str, prompt: str) -> str:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
