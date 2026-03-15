# intentful/routing/resolver.py — LLM mapeia prompt -> endpoint + payload
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("intentful.resolver")

from intentful.core.registry import IntentRegistry
from intentful.core.schemas import IntentRequest, IntentResolution, LookupHint


RESOLVER_SYSTEM_PROMPT = """You are an intent resolver for a backend API system.
Given a user's natural language prompt and a list of available API endpoints with their contexts,
you must determine which endpoint best matches the user's intent and generate the appropriate payload.

RULES:
- Only resolve to endpoints in the provided list
- Generate payloads that match the endpoint's expected schema
- Set confidence based on how well the prompt matches the endpoint
- If no endpoint matches well, set confidence below 0.5
- Consider the business rules defined in each endpoint's context
- Respond ONLY with valid JSON, no other text

PARAMETER RESOLUTION:
- Some endpoints have "resolvable_params" — these are path parameters (like IDs) that cannot be guessed from the prompt alone.
- When an endpoint has resolvable_params, do NOT invent or guess IDs. Instead, provide "lookup_hints" with the search values extracted from the user's prompt, using ONLY the search_fields listed for that parameter.
- If the endpoint has NO resolvable_params, do NOT include lookup_hints.

RESPONSE FORMAT:
{{
    "endpoint": "/path/to/endpoint",
    "method": "POST",
    "payload": {{}},
    "confidence": 0.95,
    "estimated_impact": "description of what will happen",
    "reasoning": "why this endpoint was chosen",
    "lookup_hints": [
        {{
            "param_name": "order_id",
            "search_values": {{"customer_name": "João", "created_at": "2026-03-14"}}
        }}
    ]
}}

If there are no parameters to resolve, omit lookup_hints or set it to [].
"""


def build_resolution_prompt(request: IntentRequest, registry: IntentRegistry) -> str:
    """Constrói o prompt completo para enviar ao LLM."""
    endpoints_context = json.dumps(registry.to_prompt_context(), indent=2, ensure_ascii=False)
    return (
        f"Available endpoints:\n{endpoints_context}\n\n"
        f"User prompt (language: {request.language}):\n{request.prompt}"
    )


class Resolver(ABC):
    """Interface base para resolvers de intent."""

    @abstractmethod
    async def resolve(
        self, request: IntentRequest, registry: IntentRegistry
    ) -> IntentResolution: ...


class LLMResolver(Resolver):
    """Resolver que usa um backend LLM para mapear prompts a endpoints."""

    def __init__(self, backend: Any) -> None:
        self.backend = backend

    async def resolve(
        self, request: IntentRequest, registry: IntentRegistry
    ) -> IntentResolution:
        prompt = build_resolution_prompt(request, registry)
        try:
            raw_response = await self.backend.complete(
                system=RESOLVER_SYSTEM_PROMPT,
                prompt=prompt,
            )
        except Exception as e:
            logger.error("LLM backend error: %s", e)
            raise RuntimeError(f"Erro ao contactar o LLM: {e}") from e

        if not raw_response or not raw_response.strip():
            raise RuntimeError("LLM devolveu resposta vazia.")

        try:
            data = json.loads(raw_response)
        except json.JSONDecodeError as e:
            logger.error("LLM returned invalid JSON: %s", raw_response[:200])
            raise RuntimeError(f"LLM devolveu JSON inválido: {e}") from e

        if data.get("payload") is None:
            data["payload"] = {}
        if "lookup_hints" in data and data["lookup_hints"]:
            data["lookup_hints"] = [
                LookupHint(**h) if isinstance(h, dict) else h
                for h in data["lookup_hints"]
            ]
        else:
            data["lookup_hints"] = []
        return IntentResolution(**data)
