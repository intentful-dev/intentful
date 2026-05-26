# intentful — Build APIs that understand intent, not just requests.
# Package root: intentful/__init__.py

from intentful.core.context import IntentContext
from intentful.core.decorator import intent
from intentful.core.registry import IntentRegistry, get_registry
from intentful.core.schemas import (
    ConversationResponse,
    IntentRequest,
    IntentResolution,
    IntentResponse,
    LookupCandidate,
    LookupConfig,
    LookupHint,
    ValidationDetail,
)
from intentful.integrations.auto import intentful_auto

__version__ = "0.2.0"

__all__ = [
    "ConversationResponse",
    "IntentContext",
    "IntentRegistry",
    "IntentRequest",
    "IntentResolution",
    "IntentResponse",
    "LookupCandidate",
    "LookupConfig",
    "LookupHint",
    "ValidationDetail",
    "get_registry",
    "intent",
    "intentful_auto",
]
