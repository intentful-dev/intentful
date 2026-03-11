# intentful/routing/validator.py — Valida payload gerado contra as regras do endpoint
from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from intentful.core.registry import IntentEntry
from intentful.core.schemas import IntentResolution


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]


def validate_resolution(resolution: IntentResolution, entry: IntentEntry) -> ValidationResult:
    """Valida se a resolução do LLM respeita as regras do endpoint."""
    errors: list[str] = []

    # Verificar se o método é permitido
    if resolution.method.upper() not in _method_to_operations(resolution.method):
        pass  # O método HTTP é válido por si só

    # Verificar se as operações estão dentro das permitidas
    implied_ops = _method_to_operations(resolution.method)
    for op in implied_ops:
        if op not in entry.context.allowed_operations:
            errors.append(
                f"Operação '{op}' não permitida. "
                f"Permitidas: {entry.context.allowed_operations}"
            )

    # Validar payload contra o schema Pydantic se disponível
    if entry.payload_schema and resolution.payload:
        schema_errors = _validate_against_schema(resolution.payload, entry)
        errors.extend(schema_errors)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def _method_to_operations(method: str) -> list[str]:
    """Mapeia método HTTP para tipos de operação."""
    mapping = {
        "GET": ["READ"],
        "POST": ["CREATE"],
        "PUT": ["UPDATE"],
        "PATCH": ["UPDATE"],
        "DELETE": ["DELETE"],
    }
    return mapping.get(method.upper(), ["READ"])


def _validate_against_schema(payload: dict, entry: IntentEntry) -> list[str]:
    """Valida o payload contra o modelo Pydantic original do handler."""
    errors: list[str] = []
    # Buscar a classe Pydantic original do handler
    import inspect

    from pydantic import BaseModel

    sig = inspect.signature(entry.handler)
    for param in sig.parameters.values():
        annotation = param.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            try:
                annotation.model_validate(payload)
            except ValidationError as e:
                for err in e.errors():
                    loc = " -> ".join(str(l) for l in err["loc"])
                    errors.append(f"Validação falhou em '{loc}': {err['msg']}")
            break
    return errors
