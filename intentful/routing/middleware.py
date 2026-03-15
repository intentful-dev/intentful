# intentful/routing/middleware.py — Intercepta requests com campo "prompt"
from __future__ import annotations

import json
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from intentful.core.registry import get_registry
from intentful.core.schemas import IntentRequest, IntentResponse
from intentful.routing.lookup import apply_resolved_params, needs_lookup, resolve_lookups
from intentful.routing.resolver import Resolver


class IntentMiddleware(BaseHTTPMiddleware):
    """Middleware que detecta requests com campo 'prompt' e resolve via LLM.

    Se o body contém um campo "prompt", o middleware intercepta, resolve
    o intent e redireciona para o endpoint correcto com o payload gerado.
    Se não contém "prompt", passa normalmente.
    """

    def __init__(self, app: Any, resolver: Resolver, confidence_threshold: float = 0.7) -> None:
        super().__init__(app)
        self.resolver = resolver
        self.confidence_threshold = confidence_threshold

    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        # O endpoint /intent já trata resolução internamente
        if request.url.path.rstrip("/").endswith("/intent"):
            return await call_next(request)

        try:
            body = await request.body()
            if not body:
                return await call_next(request)

            data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return await call_next(request)

        if "prompt" not in data:
            return await call_next(request)

        intent_request = IntentRequest(
            prompt=data["prompt"],
            dry_run=data.get("dry_run", False),
            language=data.get("language", "pt"),
            metadata=data.get("metadata", {}),
        )

        registry = get_registry()
        resolution = await self.resolver.resolve(intent_request, registry)

        if resolution.confidence < self.confidence_threshold:
            return JSONResponse(
                status_code=422,
                content=IntentResponse(
                    success=False,
                    resolution=resolution,
                    error=f"Confiança insuficiente ({resolution.confidence:.0%}). "
                    "Reformule o prompt ou use o endpoint directamente.",
                ).model_dump(),
            )

        entry = registry.get(resolution.method, resolution.endpoint)
        if entry is None:
            return JSONResponse(
                status_code=404,
                content=IntentResponse(
                    success=False,
                    resolution=resolution,
                    error=f"Endpoint {resolution.endpoint} não encontrado no registry.",
                ).model_dump(),
            )

        if intent_request.dry_run:
            return JSONResponse(
                content=IntentResponse(
                    success=True,
                    resolution=resolution,
                    confirmation_required=entry.context.requires_confirmation,
                    confirmation_message=entry.context.confirmation_template,
                ).model_dump(),
            )

        # --- Two-step lookup resolution ---
        if needs_lookup(resolution, entry):
            lookup_results = await resolve_lookups(resolution, entry)

            for param_name, candidates in lookup_results.items():
                if len(candidates) == 0:
                    return JSONResponse(
                        status_code=404,
                        content=IntentResponse(
                            success=False,
                            resolution=resolution,
                            error=f"Não foi possível resolver '{param_name}': nenhum resultado encontrado.",
                            lookup_results=lookup_results,
                        ).model_dump(),
                    )

                if len(candidates) > 1:
                    return JSONResponse(
                        content=IntentResponse(
                            success=True,
                            resolution=resolution,
                            confirmation_required=True,
                            confirmation_message=(
                                f"Foram encontrados {len(candidates)} resultados "
                                f"para '{param_name}'. Selecione o correcto."
                            ),
                            lookup_results=lookup_results,
                        ).model_dump(),
                    )

            resolved_params = {
                param_name: candidates[0].id_value
                for param_name, candidates in lookup_results.items()
            }
            resolution = apply_resolved_params(resolution, resolved_params)

        if entry.context.requires_confirmation and not data.get("confirmed", False):
            return JSONResponse(
                content=IntentResponse(
                    success=True,
                    resolution=resolution,
                    confirmation_required=True,
                    confirmation_message=entry.context.confirmation_template,
                ).model_dump(),
            )

        # Reescrever o request com o payload estruturado resolvido
        request.state.intent_resolution = resolution
        request._body = json.dumps(resolution.payload).encode()
        scope = request.scope
        scope["path"] = resolution.endpoint

        return await call_next(request)
