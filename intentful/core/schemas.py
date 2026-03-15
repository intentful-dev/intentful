# intentful/core/schemas.py — Schemas partilhados para requests e responses de intent
from __future__ import annotations

from typing import Any, Callable, Awaitable

from pydantic import BaseModel, Field


class LookupConfig(BaseModel):
    """Configuração de lookup para resolver path params a partir de models.

    Uso no @intent:
        lookups={
            "order_id": LookupConfig(
                search_fields=["customer__name", "created_at"],
                resolver_fn=search_orders,
                id_field="id",
                display_fields=["customer__name", "total"],
            )
        }
    """

    search_fields: list[str] = Field(
        ..., description="Campos do model que o LLM pode usar como hints de busca"
    )
    resolver_fn: Callable[..., Awaitable[list[dict[str, Any]]]] = Field(
        ..., description="Função async que recebe hints e devolve lista de candidatos"
    )
    id_field: str = Field(
        default="id", description="Campo do resultado que contém o ID a usar"
    )
    display_fields: list[str] = Field(
        default_factory=list,
        description="Campos a mostrar ao utilizador para confirmação",
    )

    model_config = {"arbitrary_types_allowed": True}


class LookupHint(BaseModel):
    """Hint gerada pelo LLM para resolver um parâmetro não resolvido."""

    param_name: str = Field(..., description="Nome do path param a resolver")
    search_values: dict[str, Any] = Field(
        ..., description="Mapa de search_field -> valor extraído do prompt"
    )


class LookupCandidate(BaseModel):
    """Um candidato devolvido pelo lookup."""

    id_value: Any = Field(..., description="Valor do ID resolvido")
    display: dict[str, Any] = Field(
        default_factory=dict, description="Campos para mostrar ao utilizador"
    )


class IntentRequest(BaseModel):
    """Request enviado ao endpoint /intent ou como campo prompt num endpoint normal."""

    prompt: str = Field(..., description="O prompt em linguagem natural do utilizador")
    dry_run: bool = Field(default=False, description="Se True, simula sem executar")
    language: str = Field(default="pt", description="Língua do prompt (ISO 639-1)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata adicional")


class IntentResolution(BaseModel):
    """Resultado da resolução de um prompt pelo LLM."""

    endpoint: str = Field(..., description="Path do endpoint resolvido")
    method: str = Field(default="POST", description="Método HTTP")
    payload: dict[str, Any] | None = Field(default_factory=dict, description="Payload gerado pelo LLM")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança na resolução (0-1)")
    estimated_impact: str | None = Field(
        default=None, description="Estimativa do impacto da operação"
    )
    reasoning: str | None = Field(
        default=None, description="Raciocínio do LLM ao resolver o intent"
    )
    lookup_hints: list[LookupHint] = Field(
        default_factory=list,
        description="Hints para resolver parâmetros que o LLM não conseguiu preencher directamente",
    )


class IntentResponse(BaseModel):
    """Response devolvido ao utilizador após uma operação via intent."""

    success: bool
    resolution: IntentResolution | None = None
    confirmation_required: bool = False
    confirmation_message: str | None = None
    result: Any = None
    error: str | None = None
    audit_id: str | None = None
    lookup_results: dict[str, list[LookupCandidate]] | None = None
