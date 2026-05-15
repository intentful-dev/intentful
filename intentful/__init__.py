# intentful — Build APIs that understand intent, not just requests.
# Package root: intentful/__init__.py

from intentful.core.context import IntentContext
from intentful.core.decorator import intent
from intentful.core.registry import IntentRegistry, get_registry
from intentful.core.schemas import (
    IntentRequest,
    IntentResolution,
    IntentResponse,
    LookupCandidate,
    LookupConfig,
    LookupHint,
)

__version__ = "0.1.0"

__all__ = [
    "IntentContext",
    "IntentRegistry",
    "IntentRequest",
    "IntentResolution",
    "IntentResponse",
    "LookupCandidate",
    "LookupConfig",
    "LookupHint",
    "get_registry",
    "intent",
]
