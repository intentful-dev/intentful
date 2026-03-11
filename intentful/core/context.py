# intentful/core/context.py — IntentContext: fronteiras semânticas para endpoints
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


OperationType = Literal["CREATE", "READ", "UPDATE", "DELETE"]


class IntentContext(BaseModel):
    """Define as fronteiras semânticas de um endpoint anotado com @intent.

    O IntentContext diz ao resolver quais regras de negócio se aplicam,
    que operações são permitidas e se é necessário confirmar antes de executar.
    """

    rules: list[str] = Field(
        default_factory=list,
        description="Regras de negócio que o LLM deve considerar ao resolver o intent",
    )
    allowed_operations: list[OperationType] = Field(
        default_factory=lambda: ["READ"],
        description="Tipos de operação que este endpoint pode executar",
    )
    requires_confirmation: bool = Field(
        default=False,
        description="Se True, operações via prompt pedem confirmação antes de executar",
    )
    confirmation_template: str | None = Field(
        default=None,
        description="Template da mensagem de confirmação (suporta {placeholders})",
    )
    examples: list[str] = Field(
        default_factory=list,
        description="Exemplos de prompts que devem resolver para este endpoint",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags para agrupar e filtrar endpoints no registry",
    )
