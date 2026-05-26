# intentful/routing/smart_validation.py — Validacao inteligente com detecao de campos e sugestoes LLM
# Path: intentful/routing/smart_validation.py
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from intentful.backends import LLMBackend
from intentful.core.registry import IntentEntry
from intentful.core.schemas import IntentResolution
from intentful.routing.validator import ValidationResult, validate_resolution


VALIDATION_SYSTEM_PROMPT = (
    "You are a validation assistant for an API. "
    "Given validation errors for an API call, generate a friendly, helpful message "
    "in {language} telling the user what's missing or wrong. "
    "Be concise. List missing fields naturally. If a value is invalid, explain why. "
    "If there are business rules that were violated, mention them. "
    "Respond with plain text only, no JSON, no markdown."
)


@dataclass
class SmartValidationResult:
    """Resultado detalhado de validacao com campos em falta, erros por campo, e sugestao."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    invalid_fields: dict[str, str] = field(default_factory=dict)
    suggestion: str | None = None


async def smart_validate(
    resolution: IntentResolution,
    entry: IntentEntry,
    backend: LLMBackend | None = None,
    language: str = "pt",
) -> SmartValidationResult:
    """Validacao inteligente que detecta campos em falta e gera sugestoes via LLM."""
    errors: list[str] = []
    missing_fields: list[str] = []
    invalid_fields: dict[str, str] = {}

    # 1. Validacao base (operacoes permitidas)
    base_result: ValidationResult = validate_resolution(resolution, entry)
    errors.extend(base_result.errors)

    # 2. Validacao detalhada contra o modelo Pydantic
    if entry.payload_model is not None:
        model_cls: type[BaseModel] = entry.payload_model
        payload = resolution.payload or {}

        # Detectar campos obrigatorios em falta
        for field_name, field_info in model_cls.model_fields.items():
            if field_info.is_required() and field_name not in payload:
                missing_fields.append(field_name)
                desc = field_info.description or field_name
                errors.append(f"Campo obrigatorio em falta: '{field_name}' ({desc})")

        # Validacao completa com Pydantic (tipos, constraints)
        if not missing_fields:
            try:
                model_cls.model_validate(payload)
            except ValidationError as e:
                for err in e.errors():
                    loc = " -> ".join(str(part) for part in err["loc"])
                    msg = err["msg"]
                    invalid_fields[loc] = msg
                    errors.append(f"Valor invalido em '{loc}': {msg}")

    valid = len(errors) == 0

    result = SmartValidationResult(
        valid=valid,
        errors=errors,
        missing_fields=missing_fields,
        invalid_fields=invalid_fields,
    )

    # 3. Gerar sugestao amigavel via LLM (apenas se houver erros e backend disponivel)
    if not valid and backend is not None:
        result.suggestion = await _generate_suggestion(
            errors=errors,
            missing_fields=missing_fields,
            invalid_fields=invalid_fields,
            rules=entry.context.rules,
            backend=backend,
            language=language,
        )

    return result


async def _generate_suggestion(
    *,
    errors: list[str],
    missing_fields: list[str],
    invalid_fields: dict[str, str],
    rules: list[str],
    backend: LLMBackend,
    language: str,
) -> str | None:
    """Pede ao LLM para gerar uma mensagem amigavel a partir dos erros de validacao."""
    parts = []
    if missing_fields:
        parts.append(f"Missing required fields: {', '.join(missing_fields)}")
    if invalid_fields:
        parts.append(
            "Invalid values: "
            + "; ".join(f"{k}: {v}" for k, v in invalid_fields.items())
        )
    if rules:
        parts.append(f"Business rules: {'; '.join(rules)}")

    prompt = "\n".join(parts)
    system = VALIDATION_SYSTEM_PROMPT.format(language=language)

    try:
        return await backend.complete(system, prompt)
    except Exception:
        return None
