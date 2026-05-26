# intentful/conversation/fields.py — Extracao de campos de modelos Pydantic
# Path: intentful/conversation/fields.py
from __future__ import annotations

from typing import Any, get_args, get_origin

from pydantic import BaseModel

from intentful.conversation.session import FieldSpec


def extract_field_specs(model: type[BaseModel]) -> list[FieldSpec]:
    """Extrai especificacoes de todos os campos de um modelo Pydantic.

    Retorna campos obrigatorios primeiro, depois opcionais.
    """
    required: list[FieldSpec] = []
    optional: list[FieldSpec] = []

    for field_name, field_info in model.model_fields.items():
        type_str = _type_to_str(field_info.annotation)
        spec = FieldSpec(
            name=field_name,
            type_str=type_str,
            description=field_info.description,
            required=field_info.is_required(),
            default=field_info.default if not field_info.is_required() else None,
        )
        if spec.required:
            required.append(spec)
        else:
            optional.append(spec)

    return required + optional


def identify_missing_fields(
    specs: list[FieldSpec],
    collected: dict[str, Any],
) -> list[FieldSpec]:
    """Retorna campos obrigatorios que ainda nao foram recolhidos."""
    return [s for s in specs if s.required and s.name not in collected]


def _type_to_str(annotation: Any) -> str:
    """Converte uma anotacao de tipo para string legivel."""
    if annotation is None:
        return "any"

    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        args_str = ", ".join(_type_to_str(a) for a in args) if args else ""
        origin_name = getattr(origin, "__name__", str(origin))
        return f"{origin_name}[{args_str}]" if args_str else origin_name

    if isinstance(annotation, type):
        return annotation.__name__

    return str(annotation)
