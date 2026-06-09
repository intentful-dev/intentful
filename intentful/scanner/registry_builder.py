# intentful/scanner/registry_builder.py — Converte resultados do scanner em IntentRegistry
# Path: intentful/scanner/registry_builder.py
from __future__ import annotations

from intentful.core.registry import IntentEntry, IntentRegistry, get_registry


def build_registry_from_spec(
    entries: list[IntentEntry],
    *,
    registry: IntentRegistry | None = None,
    clear_existing: bool = False,
) -> IntentRegistry:
    """Popula um IntentRegistry com entries geradas pelo OpenAPIScanner.

    Args:
        entries: Lista de IntentEntry gerados pelo scanner.
        registry: Registry a usar. Se None, usa o singleton global.
        clear_existing: Se True, limpa entries existentes antes de adicionar.

    Returns:
        O IntentRegistry populado.
    """
    if registry is None:
        registry = get_registry()

    if clear_existing:
        registry.clear()

    for entry in entries:
        registry.register(entry)

    return registry
