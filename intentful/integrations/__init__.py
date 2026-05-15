# intentful/integrations/__init__.py — Integrações com frameworks
from intentful.integrations.fastapi import IntentRouter, setup_intentful

__all__ = [
    "IntentRouter",
    "setup_intentful",
]
