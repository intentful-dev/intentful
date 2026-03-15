# intentful/integrations/fastapi.py — IntentRouter: extensão do APIRouter
# Path: intentful/integrations/fastapi.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from pydantic import BaseModel

from intentful.backends import LLMBackend
from intentful.backends.anthropic import AnthropicBackend
from intentful.core.registry import IntentEntry, get_registry
from intentful.core.schemas import IntentRequest, IntentResponse
from intentful.execution.auditor import AuditEntry, Auditor
from intentful.routing.middleware import IntentMiddleware
from intentful.routing.resolver import LLMResolver
from intentful.routing.lookup import apply_resolved_params, needs_lookup, resolve_lookups
from intentful.routing.validator import validate_resolution


class IntentRouter(APIRouter):
    """APIRouter do FastAPI estendido com suporte a intents.

    Drop-in replacement para o APIRouter — todos os endpoints ficam
    automaticamente registados no IntentRegistry.

    Uso:
        router = IntentRouter(ai_backend="anthropic", language="pt")

        @router.post("/turmas/gerar")
        @intent(description="Criar turmas", context=IntentContext(...))
        async def gerar_turmas(...):
            ...
    """

    def __init__(
        self,
        *,
        ai_backend: str | LLMBackend = "anthropic",
        language: str | list[str] = "pt",
        audit_trail: bool = True,
        confidence_threshold: float = 0.7,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.language = language if isinstance(language, list) else [language]
        self.audit_trail = audit_trail
        self.confidence_threshold = confidence_threshold
        self.auditor = Auditor() if audit_trail else None

        if isinstance(ai_backend, str):
            self.backend = _create_backend(ai_backend)
        else:
            self.backend = ai_backend

        self.resolver = LLMResolver(self.backend)
        self._add_intent_endpoint()

    def _add_intent_endpoint(self) -> None:
        """Adiciona o endpoint universal /intent ao router."""

        @self.post("/intent", response_model=IntentResponse)
        async def resolve_intent(request: Request) -> JSONResponse:
            """Endpoint universal para resolver prompts em linguagem natural.

            Recebe um prompt e resolve para o endpoint + payload correcto.
            """
            body = await request.json()
            intent_request = IntentRequest(
                prompt=body["prompt"],
                dry_run=body.get("dry_run", False),
                language=body.get("language", self.language[0]),
                metadata=body.get("metadata", {}),
            )

            registry = get_registry()
            if len(registry) == 0:
                return JSONResponse(
                    status_code=400,
                    content=IntentResponse(
                        success=False,
                        error="Nenhum endpoint registado com @intent.",
                    ).model_dump(),
                )

            resolution = await self.resolver.resolve(intent_request, registry)

            if resolution.confidence < self.confidence_threshold:
                return JSONResponse(
                    status_code=422,
                    content=IntentResponse(
                        success=False,
                        resolution=resolution,
                        error=(
                            f"Confiança insuficiente ({resolution.confidence:.0%}). "
                            "Reformule o prompt ou use o endpoint directamente."
                        ),
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

            # Validar o payload contra as regras do endpoint
            validation = validate_resolution(resolution, entry)
            if not validation.valid:
                return JSONResponse(
                    status_code=422,
                    content=IntentResponse(
                        success=False,
                        resolution=resolution,
                        error="Validação falhou: " + "; ".join(validation.errors),
                    ).model_dump(),
                )

            # --- Two-step lookup resolution ---
            if needs_lookup(resolution, entry):
                lookup_results = await resolve_lookups(resolution, entry)

                # Verificar se há candidatos ambíguos ou vazios
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
                        # Múltiplos candidatos — devolver para o utilizador escolher
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

                # Exactamente 1 candidato por param — resolver automaticamente
                resolved_params = {
                    param_name: candidates[0].id_value
                    for param_name, candidates in lookup_results.items()
                }
                resolution = apply_resolved_params(resolution, resolved_params)

            # Modo dry_run — só mostra o que faria
            if intent_request.dry_run:
                return JSONResponse(
                    content=IntentResponse(
                        success=True,
                        resolution=resolution,
                        confirmation_required=entry.context.requires_confirmation,
                        confirmation_message=entry.context.confirmation_template,
                    ).model_dump(),
                )

            # Confirmação necessária?
            if entry.context.requires_confirmation and not body.get("confirmed", False):
                from intentful.execution.confirmer import build_confirmation_message

                return JSONResponse(
                    content=IntentResponse(
                        success=True,
                        resolution=resolution,
                        confirmation_required=True,
                        confirmation_message=build_confirmation_message(entry, resolution),
                    ).model_dump(),
                )

            # Executar o handler directamente
            audit_id = None
            if self.auditor:
                audit_entry = AuditEntry(
                    user_id=body.get("user_id"),
                    prompt=intent_request.prompt,
                    resolution=resolution,
                    confirmed=True,
                )
                audit_id = self.auditor.record(audit_entry)

            try:
                result = await _call_handler(entry, resolution.payload)

                if self.auditor and audit_id:
                    audit = self.auditor.get(audit_id)
                    if audit:
                        audit.executed = True
                        audit.result = result

                return JSONResponse(
                    content=IntentResponse(
                        success=True,
                        resolution=resolution,
                        result=result,
                        audit_id=audit_id,
                    ).model_dump(),
                )
            except Exception as e:
                if self.auditor and audit_id:
                    audit = self.auditor.get(audit_id)
                    if audit:
                        audit.error = str(e)

                return JSONResponse(
                    status_code=500,
                    content=IntentResponse(
                        success=False,
                        resolution=resolution,
                        error=f"Erro ao executar: {e}",
                        audit_id=audit_id,
                    ).model_dump(),
                )


async def _call_handler(entry: IntentEntry, payload: dict) -> Any:
    """Chama o handler do endpoint, instanciando o schema Pydantic se necessário."""
    if entry.payload_model is not None:
        model_instance = entry.payload_model(**payload)
        return await entry.handler(model_instance)
    return await entry.handler(**payload)


def _create_backend(name: str) -> LLMBackend:
    """Factory para criar backends LLM por nome."""
    backends = {
        "anthropic": lambda: AnthropicBackend(),
        "openai": lambda: _import_openai(),
        "ollama": lambda: _import_ollama(),
    }
    factory = backends.get(name)
    if factory is None:
        raise ValueError(f"Backend desconhecido: '{name}'. Disponíveis: {list(backends.keys())}")
    return factory()


def _import_openai() -> LLMBackend:
    from intentful.backends.openai import OpenAIBackend

    return OpenAIBackend()


def _import_ollama() -> LLMBackend:
    from intentful.backends.local import OllamaBackend

    return OllamaBackend()


def setup_intentful(app: FastAPI, router: IntentRouter) -> None:
    """Configura o middleware de intent na app FastAPI.

    Uso:
        app = FastAPI()
        router = IntentRouter(ai_backend="anthropic")
        setup_intentful(app, router)
    """
    app.add_middleware(
        IntentMiddleware,
        resolver=router.resolver,
        confidence_threshold=router.confidence_threshold,
    )
    app.include_router(router)
