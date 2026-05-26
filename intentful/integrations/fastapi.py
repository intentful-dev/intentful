# intentful/integrations/fastapi.py — IntentRouter: extensão do APIRouter
# Path: intentful/integrations/fastapi.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from pydantic import ValidationError

from intentful.backends import LLMBackend
from intentful.backends.anthropic import AnthropicBackend
from intentful.core.registry import IntentEntry, get_registry
from intentful.conversation.resolver import ConversationalResolver
from intentful.conversation.store import InMemorySessionStore
from intentful.core.schemas import ConversationResponse, IntentRequest, IntentResponse, ValidationDetail
from intentful.execution.auditor import AuditEntry, Auditor
from intentful.routing.middleware import IntentMiddleware
from intentful.routing.resolver import LLMResolver
from intentful.routing.lookup import LookupError, apply_resolved_params, needs_lookup, resolve_lookups
from intentful.routing.smart_validation import SmartValidationResult, smart_validate


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
        self.session_store = InMemorySessionStore()
        self.conversational_resolver = ConversationalResolver(self.backend)
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
                mode=body.get("mode", "single"),
                session_id=body.get("session_id"),
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

            # --- Modo conversacional ---
            if intent_request.mode == "conversational":
                return await self._handle_conversational(intent_request, body)

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

            # Validar o payload contra as regras do endpoint (smart validation)
            smart_result: SmartValidationResult = await smart_validate(
                resolution,
                entry,
                backend=self.backend,
                language=intent_request.language,
            )
            if not smart_result.valid:
                detail = ValidationDetail(
                    valid=False,
                    errors=smart_result.errors,
                    missing_fields=smart_result.missing_fields,
                    invalid_fields=smart_result.invalid_fields,
                    suggestion=smart_result.suggestion,
                )
                return JSONResponse(
                    status_code=422,
                    content=IntentResponse(
                        success=False,
                        resolution=resolution,
                        error="Validação falhou: " + "; ".join(smart_result.errors),
                        validation_details=detail,
                        suggestion=smart_result.suggestion,
                    ).model_dump(),
                )

            # --- Two-step lookup resolution ---
            if needs_lookup(resolution, entry):
                try:
                    lookup_results = await resolve_lookups(resolution, entry)
                except LookupError as e:
                    return JSONResponse(
                        status_code=502,
                        content=IntentResponse(
                            success=False,
                            resolution=resolution,
                            error=f"Erro ao resolver parâmetros: {e}",
                        ).model_dump(),
                    )

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
            except ValidationError as e:
                error_msg = "; ".join(
                    f"{' -> '.join(str(loc) for loc in err['loc'])}: {err['msg']}"
                    for err in e.errors()
                )
                if self.auditor and audit_id:
                    audit = self.auditor.get(audit_id)
                    if audit:
                        audit.error = error_msg

                return JSONResponse(
                    status_code=422,
                    content=IntentResponse(
                        success=False,
                        resolution=resolution,
                        error=f"Payload inválido: {error_msg}",
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


    async def _handle_conversational(
        self, intent_request: IntentRequest, body: dict
    ) -> JSONResponse:
        """Trata pedidos no modo conversacional (faseado)."""
        session_id = intent_request.session_id

        if session_id is not None:
            # Continuar sessao existente
            session = await self.session_store.get(session_id)
            if session is None:
                return JSONResponse(
                    status_code=404,
                    content=ConversationResponse(
                        session_id=session_id,
                        status="expired",
                        error="Sessao nao encontrada ou expirada.",
                        collected_fields={},
                    ).model_dump(),
                )

            session = await self.conversational_resolver.continue_session(
                session, intent_request.prompt
            )
        else:
            # Iniciar nova sessao
            session = await self.conversational_resolver.start_session(
                intent_request.prompt,
                language=intent_request.language,
            )

        await self.session_store.save(session)

        # Extrair a ultima mensagem do assistant como pergunta
        question = None
        for turn in reversed(session.history):
            if turn.role == "assistant":
                question = turn.content
                break

        current_field_name = None
        if session.current_field:
            current_field_name = session.current_field.name

        # Se pronto para executar, executar o handler
        result = None
        if session.status == "ready" and not intent_request.dry_run:
            entry = get_registry().get(session.method, session.endpoint_path)
            if entry is not None:
                try:
                    result = await _call_handler(entry, session.collected_fields)
                    session.status = "completed"
                    await self.session_store.save(session)
                except Exception as e:
                    return JSONResponse(
                        status_code=500,
                        content=ConversationResponse(
                            session_id=session.session_id,
                            status=session.status,
                            error=f"Erro ao executar: {e}",
                            collected_fields=session.collected_fields,
                        ).model_dump(),
                    )

        response = ConversationResponse(
            session_id=session.session_id,
            status=session.status,
            question=question,
            collected_fields=session.collected_fields,
            pending_field=current_field_name,
            result=result,
        )
        return JSONResponse(content=response.model_dump())


async def _call_handler(entry: IntentEntry, payload: dict) -> Any:
    """Chama o handler do endpoint, instanciando o schema Pydantic se necessário."""
    import inspect

    from pydantic import ValidationError

    try:
        if entry.payload_model is not None:
            model_instance = entry.payload_model(**payload)
            pass
        else:
            pass
    except ValidationError:
        raise  # Re-raise para o caller tratar com status 422

    handler = entry.handler
    if entry.payload_model is not None:
        result = handler(model_instance)
    else:
        result = handler(**payload)

    if inspect.isawaitable(result):
        return await result
    return result


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
