# intentful/execution/confirmer.py — Lógica de confirmação para operações de alto impacto
from __future__ import annotations

from intentful.core.registry import IntentEntry
from intentful.core.schemas import IntentResolution


def needs_confirmation(entry: IntentEntry) -> bool:
    """Verifica se o endpoint requer confirmação."""
    return entry.context.requires_confirmation


def build_confirmation_message(
    entry: IntentEntry, resolution: IntentResolution
) -> str:
    """Gera a mensagem de confirmação usando o template do endpoint."""
    template = entry.context.confirmation_template
    if template is None:
        return (
            f"Vai executar '{entry.description}' no endpoint {resolution.endpoint}. "
            f"Impacto estimado: {resolution.estimated_impact or 'não calculado'}. "
            "Confirma?"
        )
    try:
        return template.format(**resolution.payload)
    except KeyError:
        return template
