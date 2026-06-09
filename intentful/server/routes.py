# intentful/server/routes.py — Endpoints do agente Intentful standalone
# Path: intentful/server/routes.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from pydantic import BaseModel, Field

from intentful.core.schemas import (
    ConversationResponse,
    IntentRequest,
    IntentResolution,
    ValidationDetail,
)
from intentful.execution.auditor import AuditEntry
from intentful.routing.smart_validation import smart_validate


class PromptRequest(BaseModel):
    """Request para o endpoint /prompt do agente."""

    prompt: str = Field(..., description="Prompt em linguagem natural")
    session_id: str | None = Field(default=None, description="ID da sessão conversacional")
    language: str = Field(default="pt", description="Língua do prompt (ISO 639-1)")
    dry_run: bool = Field(default=False, description="Se True, simula sem executar")
    mode: str = Field(default="single", description="Modo: 'single' ou 'conversational'")
    user_id: str | None = Field(default=None, description="ID do utilizador (para auditoria)")
    confirmed: bool = Field(default=False, description="Se True, confirma operação pendente")


class AgentResponse(BaseModel):
    """Response do agente Intentful."""

    success: bool
    message: str | None = None
    resolution: IntentResolution | None = None
    result: Any = None
    error: str | None = None
    audit_id: str | None = None
    validation_details: ValidationDetail | None = None
    confirmation_required: bool = False
    confirmation_message: str | None = None
    conversation: ConversationResponse | None = None


class EndpointInfo(BaseModel):
    """Informação sobre um endpoint descoberto."""

    path: str
    method: str
    description: str
    allowed_operations: list[str]
    payload_schema: dict[str, Any] | None = None


def create_routes() -> APIRouter:
    """Cria o router com os endpoints do agente."""
    router = APIRouter()

    @router.post("/prompt", response_model=AgentResponse)
    async def handle_prompt(body: PromptRequest, request: Request) -> JSONResponse:
        """Recebe um prompt em linguagem natural, resolve e executa no backend target.

        Flow:
        1. Resolve prompt → endpoint via LLM
        2. Valida payload
        3. Executa via HTTP no backend target
        4. Retorna resultado
        """
        state = request.app.state
        registry = state.registry
        resolver = state.resolver
        executor = state.executor
        auditor = state.auditor
        backend = state.backend
        confidence_threshold = state.confidence_threshold

        if len(registry) == 0:
            return JSONResponse(
                status_code=503,
                content=AgentResponse(
                    success=False,
                    error="Nenhum endpoint descoberto. Verifique a spec OpenAPI.",
                ).model_dump(),
            )

        # Modo conversacional
        if body.mode == "conversational":
            return await _handle_conversational(body, request)

        # Resolver prompt → endpoint
        intent_request = IntentRequest(
            prompt=body.prompt,
            dry_run=body.dry_run,
            language=body.language,
            mode="single",
        )

        try:
            resolution = await resolver.resolve(intent_request, registry)
        except RuntimeError as e:
            return JSONResponse(
                status_code=502,
                content=AgentResponse(
                    success=False,
                    error=f"Erro ao resolver prompt: {e}",
                ).model_dump(),
            )

        # Verificar confiança
        if resolution.confidence < confidence_threshold:
            return JSONResponse(
                status_code=422,
                content=AgentResponse(
                    success=False,
                    resolution=resolution,
                    error=(
                        f"Confiança insuficiente ({resolution.confidence:.0%}). "
                        "Reformule o prompt."
                    ),
                ).model_dump(),
            )

        # Verificar que o endpoint existe no registry
        entry = registry.get(resolution.method, resolution.endpoint)
        if entry is None:
            return JSONResponse(
                status_code=404,
                content=AgentResponse(
                    success=False,
                    resolution=resolution,
                    error=f"Endpoint {resolution.method} {resolution.endpoint} não encontrado.",
                ).model_dump(),
            )

        # Smart validation
        smart_result = await smart_validate(
            resolution,
            entry,
            backend=backend,
            language=body.language,
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
                content=AgentResponse(
                    success=False,
                    resolution=resolution,
                    error="Validação falhou: " + "; ".join(smart_result.errors),
                    validation_details=detail,
                ).model_dump(),
            )

        # Confirmação necessária?
        if entry.context.requires_confirmation and not body.confirmed:
            from intentful.execution.confirmer import build_confirmation_message

            return JSONResponse(
                content=AgentResponse(
                    success=True,
                    resolution=resolution,
                    confirmation_required=True,
                    confirmation_message=build_confirmation_message(entry, resolution),
                ).model_dump(),
            )

        # Dry run
        if body.dry_run:
            return JSONResponse(
                content=AgentResponse(
                    success=True,
                    resolution=resolution,
                    message="Dry run — operação não executada.",
                    confirmation_required=entry.context.requires_confirmation,
                ).model_dump(),
            )

        # Auditoria
        audit_id = None
        audit_entry = AuditEntry(
            user_id=body.user_id,
            prompt=body.prompt,
            resolution=resolution,
            confirmed=True,
        )
        audit_id = auditor.record(audit_entry)

        # Executar via HTTP no backend target
        try:
            exec_result = await executor.execute(
                method=resolution.method,
                path=resolution.endpoint,
                payload=resolution.payload,
            )

            # Actualizar auditoria
            audit = auditor.get(audit_id)
            if audit:
                audit.executed = True
                audit.result = exec_result.body

            if exec_result.success:
                return JSONResponse(
                    content=AgentResponse(
                        success=True,
                        resolution=resolution,
                        result=exec_result.body,
                        audit_id=audit_id,
                    ).model_dump(),
                )
            else:
                return JSONResponse(
                    status_code=exec_result.status_code,
                    content=AgentResponse(
                        success=False,
                        resolution=resolution,
                        error=f"Backend retornou {exec_result.status_code}",
                        result=exec_result.body,
                        audit_id=audit_id,
                    ).model_dump(),
                )

        except Exception as e:
            audit = auditor.get(audit_id)
            if audit:
                audit.error = str(e)

            return JSONResponse(
                status_code=502,
                content=AgentResponse(
                    success=False,
                    resolution=resolution,
                    error=f"Erro ao contactar backend: {e}",
                    audit_id=audit_id,
                ).model_dump(),
            )

    @router.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        """Healthcheck do agente."""
        registry = request.app.state.registry
        config = request.app.state.config
        return {
            "status": "ok",
            "version": "1.0.0",
            "endpoints_discovered": len(registry),
            "target": config.openapi_url,
            "backend": config.backend_name,
        }

    @router.get("/endpoints", response_model=list[EndpointInfo])
    async def list_endpoints(request: Request) -> list[dict[str, Any]]:
        """Lista todos os endpoints descobertos do backend target."""
        registry = request.app.state.registry
        return [
            EndpointInfo(
                path=entry.endpoint_path,
                method=entry.method,
                description=entry.description,
                allowed_operations=entry.context.allowed_operations,
                payload_schema=entry.payload_schema,
            ).model_dump()
            for entry in registry.all_entries()
        ]

    return router


async def _handle_conversational(body: PromptRequest, request: Request) -> JSONResponse:
    """Trata pedidos no modo conversacional."""
    state = request.app.state
    session_store = state.session_store
    conversational_resolver = state.conversational_resolver
    session_id = body.session_id

    if session_id is not None:
        session = await session_store.get(session_id)
        if session is None:
            return JSONResponse(
                status_code=404,
                content=AgentResponse(
                    success=False,
                    error="Sessão não encontrada ou expirada.",
                    conversation=ConversationResponse(
                        session_id=session_id,
                        status="expired",
                        collected_fields={},
                    ),
                ).model_dump(),
            )

        session = await conversational_resolver.continue_session(session, body.prompt)
    else:
        session = await conversational_resolver.start_session(
            body.prompt,
            language=body.language,
        )

    await session_store.save(session)

    # Extrair última pergunta do assistant
    question = None
    for turn in reversed(session.history):
        if turn.role == "assistant":
            question = turn.content
            break

    current_field_name = None
    if session.current_field:
        current_field_name = session.current_field.name

    # Se pronto para executar
    result = None
    if session.status == "ready" and not body.dry_run:
        executor = state.executor
        entry = state.registry.get(session.method, session.endpoint_path)
        if entry is not None:
            try:
                exec_result = await executor.execute(
                    method=session.method,
                    path=session.endpoint_path,
                    payload=session.collected_fields,
                )
                result = exec_result.body
                session.status = "completed"
                await session_store.save(session)
            except Exception as e:
                return JSONResponse(
                    status_code=502,
                    content=AgentResponse(
                        success=False,
                        error=f"Erro ao executar: {e}",
                        conversation=ConversationResponse(
                            session_id=session.session_id,
                            status=session.status,
                            collected_fields=session.collected_fields,
                        ),
                    ).model_dump(),
                )

    conversation = ConversationResponse(
        session_id=session.session_id,
        status=session.status,
        question=question,
        collected_fields=session.collected_fields,
        pending_field=current_field_name,
        result=result,
    )

    return JSONResponse(
        content=AgentResponse(
            success=True,
            conversation=conversation,
        ).model_dump(),
    )
