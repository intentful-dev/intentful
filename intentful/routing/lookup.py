# intentful/routing/lookup.py — Resolve parâmetros não resolvidos via lookup nos models
# Path: intentful/routing/lookup.py
from __future__ import annotations

import logging
from typing import Any

from intentful.core.registry import IntentEntry
from intentful.core.schemas import (
    IntentResolution,
    LookupCandidate,
    LookupConfig,
    LookupHint,
)

logger = logging.getLogger("intentful.lookup")


async def resolve_lookups(
    resolution: IntentResolution,
    entry: IntentEntry,
) -> dict[str, list[LookupCandidate]]:
    """Resolve todos os lookup_hints usando as configurações do endpoint.

    Retorna um dicionário {param_name: [candidatos]}.
    """
    results: dict[str, list[LookupCandidate]] = {}

    for hint in resolution.lookup_hints:
        config = entry.lookups.get(hint.param_name)
        if config is None:
            logger.warning(
                "LLM pediu lookup para '%s' mas não há config registada",
                hint.param_name,
            )
            continue

        # Filtrar search_values para usar apenas campos válidos
        valid_values = {
            k: v
            for k, v in hint.search_values.items()
            if k in config.search_fields
        }

        if not valid_values:
            logger.warning(
                "Nenhum search_value válido para '%s'. Valores: %s, Campos: %s",
                hint.param_name,
                list(hint.search_values.keys()),
                config.search_fields,
            )
            continue

        candidates = await _execute_lookup(config, valid_values)
        results[hint.param_name] = candidates

    return results


class LookupError(Exception):
    """Erro ao executar lookup de parâmetros."""


async def _execute_lookup(
    config: LookupConfig,
    search_values: dict[str, Any],
) -> list[LookupCandidate]:
    """Executa o resolver_fn e converte resultados em LookupCandidate."""
    try:
        raw_results = await config.resolver_fn(search_values)
    except Exception as e:
        logger.error("Erro ao executar lookup: %s", e)
        raise LookupError(f"Erro ao executar lookup: {e}") from e

    candidates: list[LookupCandidate] = []
    for row in raw_results:
        id_value = row.get(config.id_field)
        if id_value is None:
            continue

        display = {
            field: row[field]
            for field in config.display_fields
            if field in row
        }
        candidates.append(LookupCandidate(id_value=id_value, display=display))

    return candidates


def apply_resolved_params(
    resolution: IntentResolution,
    resolved: dict[str, Any],
) -> IntentResolution:
    """Aplica os parâmetros resolvidos ao endpoint path e payload."""
    endpoint = resolution.endpoint
    payload = dict(resolution.payload or {})

    for param_name, value in resolved.items():
        # Substituir no path: /orders/{order_id} -> /orders/123
        endpoint = endpoint.replace(f"{{{param_name}}}", str(value))
        # Adicionar ao payload
        payload[param_name] = value

    return resolution.model_copy(
        update={"endpoint": endpoint, "payload": payload, "lookup_hints": []}
    )


def needs_lookup(resolution: IntentResolution, entry: IntentEntry) -> bool:
    """Verifica se a resolução tem parâmetros que precisam de lookup."""
    return bool(resolution.lookup_hints) and bool(entry.lookups)
