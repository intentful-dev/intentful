# intentful/core/registry.py — Registo global de todos os endpoints anotados com @intent
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from intentful.core.context import IntentContext
from intentful.core.schemas import LookupConfig


@dataclass
class IntentEntry:
    """Representa um endpoint registado no IntentRegistry."""

    endpoint_path: str
    method: str
    description: str
    context: IntentContext
    handler: Callable[..., Any]
    payload_schema: dict[str, Any] | None = None
    payload_model: Any | None = None
    tags: list[str] = field(default_factory=list)
    lookups: dict[str, LookupConfig] = field(default_factory=dict)

    def to_prompt_context(self) -> dict[str, Any]:
        """Serializa esta entry para ser enviada ao LLM como contexto."""
        ctx: dict[str, Any] = {
            "endpoint": self.endpoint_path,
            "method": self.method,
            "description": self.description,
            "rules": self.context.rules,
            "allowed_operations": self.context.allowed_operations,
            "requires_confirmation": self.context.requires_confirmation,
            "examples": self.context.examples,
            "payload_schema": self.payload_schema,
        }
        if self.lookups:
            ctx["resolvable_params"] = {
                param: {"search_fields": cfg.search_fields}
                for param, cfg in self.lookups.items()
            }
        return ctx


class IntentRegistry:
    """Registo singleton de todos os endpoints anotados com @intent."""

    def __init__(self) -> None:
        self._entries: dict[str, IntentEntry] = {}

    def register(self, entry: IntentEntry) -> None:
        key = f"{entry.method.upper()}:{entry.endpoint_path}"
        self._entries[key] = entry

    def get(self, method: str, path: str) -> IntentEntry | None:
        key = f"{method.upper()}:{path}"
        return self._entries.get(key)

    def all_entries(self) -> list[IntentEntry]:
        return list(self._entries.values())

    def filter_by_tags(self, tags: list[str]) -> list[IntentEntry]:
        return [e for e in self._entries.values() if any(t in e.tags for t in tags)]

    def to_prompt_context(self) -> list[dict[str, Any]]:
        """Gera a lista completa de contexto para enviar ao LLM."""
        return [entry.to_prompt_context() for entry in self._entries.values()]

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


# Singleton global
_registry = IntentRegistry()


def get_registry() -> IntentRegistry:
    return _registry
