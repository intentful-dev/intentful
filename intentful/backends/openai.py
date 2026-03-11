# intentful/backends/openai.py — GPT como alternativa
from __future__ import annotations

from intentful.backends import LLMBackend


class OpenAIBackend(LLMBackend):
    """Backend que usa a API da OpenAI (GPT) para resolução de intents."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        max_tokens: int = 1024,
    ) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "O pacote 'openai' é necessário para usar o OpenAIBackend. "
                "Instale com: pip install intentful[openai]"
            )

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    async def complete(self, system: str, prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or ""
