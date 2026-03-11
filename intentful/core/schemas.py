# intentful/core/schemas.py — Schemas partilhados para requests e responses de intent
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
    payload: dict[str, Any] = Field(default_factory=dict, description="Payload gerado pelo LLM")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança na resolução (0-1)")
    estimated_impact: str | None = Field(
        default=None, description="Estimativa do impacto da operação"
    )
    reasoning: str | None = Field(
        default=None, description="Raciocínio do LLM ao resolver o intent"
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
