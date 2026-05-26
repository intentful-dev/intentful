# intentful

[![CI](https://github.com/intentful-dev/intentful/actions/workflows/ci.yml/badge.svg)](https://github.com/intentful-dev/intentful/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-compatible-009688.svg)](https://fastapi.tiangolo.com)

> Build APIs that understand intent, not just requests.

`intentful` is a Python library that lets backend developers add natural language support to FastAPI endpoints — without chatbots, external agents, or losing control. The developer defines the boundaries, the LLM operates within them.

## Key Principles

- **Backend-first** — the developer defines the boundaries, the LLM operates within them
- **Progressive enhancement** — the same endpoint works with structured payloads or natural language, without breaking anything
- **Zero-config possible** — plug into an existing app with one line, or fine-tune with decorators

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
  - [Option A: Zero-Config (v0.2.0)](#option-a-zero-config-v020)
  - [Option B: Manual Annotation](#option-b-manual-annotation)
- [Prompt Modes](#prompt-modes)
  - [Single Prompt (default)](#single-prompt-default)
  - [Conversational Mode (v0.2.0)](#conversational-mode-v020)
- [Smart Validation (v0.2.0)](#smart-validation-v020)
- [Two-Step Lookup Resolution](#two-step-lookup-resolution)
- [How It Works](#how-it-works)
- [API Reference](#api-reference)
  - [intentful_auto()](#intentful_auto)
  - [@intent decorator](#intent-decorator)
  - [IntentContext](#intentcontext)
  - [IntentRouter](#intentrouter)
  - [/intent endpoint](#intent-endpoint)
- [Features](#features)
- [Examples](#examples)
- [Development](#development)

---

## Installation

```bash
pip install intentful
```

With LLM backends:

```bash
pip install intentful[anthropic]  # Claude
pip install intentful[openai]     # GPT
pip install intentful[ollama]     # Ollama (local models)
pip install intentful[all]        # all backends
```

---

## Quick Start

### Option A: Zero-Config (v0.2.0)

Already have a FastAPI app? One line to add intent support — no route changes needed:

```python
from fastapi import FastAPI
from pydantic import BaseModel, Field
from intentful import intentful_auto

app = FastAPI()

class EventPayload(BaseModel):
    name: str = Field(..., description="Event name")
    description: str = Field(..., description="Event description")
    max_participants: int = Field(..., description="Maximum number of participants")

@app.post("/events")
async def create_event(payload: EventPayload):
    """Create a new event."""
    return {"id": 1, "event": payload.model_dump()}

@app.get("/events")
async def list_events():
    """List all available events."""
    return []

@app.delete("/events/{event_id}")
async def delete_event(event_id: int):
    """Delete an event by ID."""
    return {"deleted": event_id}

# One line — scans all routes and adds /intent endpoint
intentful_auto(app, backend="anthropic")
```

`intentful_auto()` scans the app's routes, infers descriptions from docstrings/function names, extracts Pydantic schemas, and registers everything. Now you can use:

```bash
# Natural language
curl -X POST http://localhost:8000/intent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "create an event called Python Workshop for 50 people"}'

# Traditional structured payload (still works)
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{"name": "Python Workshop", "description": "Intro", "max_participants": 50}'
```

See [`examples/demo_auto.py`](examples/demo_auto.py) for a complete example.

### Option B: Manual Annotation

For finer control, use the `@intent` decorator and `IntentRouter`:

```python
from fastapi import FastAPI
from pydantic import BaseModel, Field
from intentful import intent, IntentContext
from intentful.integrations.fastapi import IntentRouter, setup_intentful

app = FastAPI()
router = IntentRouter(ai_backend="anthropic", language="pt")

class GeraTurmasSchema(BaseModel):
    ano_lectivo: str = Field(..., description="Academic year (e.g. 2025/26)")
    curso_id: int = Field(..., description="Course ID")

@router.post("/turmas/gerar")
@intent(
    description="Create classes for an academic year",
    context=IntentContext(
        rules=[
            "Each course has curricular years defined in the study plan",
            "Default max capacity is 40 students per class",
        ],
        allowed_operations=["CREATE", "READ"],
        requires_confirmation=True,
    ),
    path="/turmas/gerar",
)
async def gerar_turmas(payload: GeraTurmasSchema):
    return {"created": True}

setup_intentful(app, router)
```

See [`examples/demo_app.py`](examples/demo_app.py) for a complete example.

---

## Prompt Modes

### Single Prompt (default)

Send a complete prompt and get an immediate result:

```bash
curl -X POST http://localhost:8000/intent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create event Python Workshop, intro to Python, 50 people"}'
```

Response:

```json
{
  "success": true,
  "resolution": {
    "endpoint": "/events",
    "method": "POST",
    "payload": {"name": "Python Workshop", "description": "intro to Python", "max_participants": 50},
    "confidence": 0.95
  },
  "result": {"id": 1, "event": {"name": "Python Workshop", "description": "intro to Python", "max_participants": 50}}
}
```

Use `"dry_run": true` to simulate without executing.

### Conversational Mode (v0.2.0)

The system guides the user through each required field, step by step. Useful when the user doesn't provide all information upfront.

**Start a conversation:**

```bash
curl -X POST http://localhost:8000/intent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "create event", "mode": "conversational"}'
```

Response:

```json
{
  "session_id": "a1b2c3d4-...",
  "status": "collecting",
  "question": "What's the event name?",
  "collected_fields": {},
  "pending_field": "name"
}
```

**Continue the conversation** (pass back the `session_id`):

```bash
curl -X POST http://localhost:8000/intent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Python Workshop", "mode": "conversational", "session_id": "a1b2c3d4-..."}'
```

Response:

```json
{
  "session_id": "a1b2c3d4-...",
  "status": "collecting",
  "question": "What's the description?",
  "collected_fields": {"name": "Python Workshop"},
  "pending_field": "description"
}
```

**Keep going** until all required fields are collected. When `status` becomes `"completed"`, the result is returned:

```json
{
  "session_id": "a1b2c3d4-...",
  "status": "completed",
  "collected_fields": {"name": "Python Workshop", "description": "Intro to Python", "max_participants": 50},
  "result": {"id": 1, "event": {"name": "Python Workshop", "description": "Intro to Python", "max_participants": 50}}
}
```

**How it works:**

1. The system resolves which endpoint the user wants
2. It analyses the Pydantic model and lists required fields
3. Any fields already present in the initial prompt are extracted automatically
4. The system asks only for what's missing, one field at a time
5. Invalid answers are rejected with a helpful message, asking the user to try again
6. Once all fields are collected, the endpoint is executed

**Session states:**

| Status | Meaning |
| --- | --- |
| `resolving` | Identifying which endpoint the user wants |
| `collecting` | Collecting required fields one by one |
| `ready` | All fields collected, about to execute |
| `completed` | Endpoint executed, result available |
| `expired` | Session timed out (default: 5 minutes) |

---

## Smart Validation (v0.2.0)

When a prompt is incomplete or produces invalid data, intentful now provides structured error details and user-friendly suggestions generated by the LLM:

```json
{
  "success": false,
  "error": "Validacao falhou: Campo obrigatorio em falta: 'description' (Event description); Campo obrigatorio em falta: 'max_participants' (Maximum number of participants)",
  "validation_details": {
    "valid": false,
    "errors": [
      "Campo obrigatorio em falta: 'description' (Event description)",
      "Campo obrigatorio em falta: 'max_participants' (Maximum number of participants)"
    ],
    "missing_fields": ["description", "max_participants"],
    "invalid_fields": {},
    "suggestion": "Falta indicar a descricao do evento e o numero maximo de participantes."
  },
  "suggestion": "Falta indicar a descricao do evento e o numero maximo de participantes."
}
```

**What smart validation checks:**

1. **Allowed operations** — is the HTTP method permitted by the endpoint's `allowed_operations`?
2. **Missing required fields** — compares payload against the Pydantic model's required fields
3. **Invalid values** — runs `model.model_validate()` and reports per-field errors
4. **LLM-generated suggestion** — if a backend is available, generates a natural language message explaining what's wrong and how to fix it, in the user's language

Smart validation is used automatically in both single and conversational modes.

---

## Two-Step Lookup Resolution

### The problem

REST endpoints use identifiers (IDs) in paths — `DELETE /orders/abc-456`. But natural language prompts use descriptions — *"delete Joao's order from yesterday"*. The LLM doesn't have access to your database and can't know the real ID.

### The solution

Instead of guessing, intentful splits the process:

1. **Step 1 — Identify intent**: The LLM picks the right endpoint and extracts search hints (e.g. `customer_name: "Joao"`, `created_at: "2026-03-14"`) — but never invents an ID.
2. **Step 2 — Resolve references**: The system uses your actual models/database to look up candidates, then either auto-resolves (1 match), asks the user to choose (N matches), or returns an error (0 matches).

```text
User: "delete Joao's order from yesterday"
        |
        v
   +----------+
   | Step 1   |  LLM -> identifies endpoint + extracts search hints
   +----+-----+
        |  endpoint: DELETE /orders/{order_id}
        |  lookup_hints: {customer_name: "Joao", created_at: "2026-03-14"}
        v
   +----------+
   | Step 2   |  System -> queries your DB/model with the hints
   +----+-----+
        |  found: order_id = "abc-456"
        v
   +----------+
   | Confirm  |  "Delete order abc-456 (Joao, 45EUR)?"
   +----+-----+
        |  user confirms
        v
   DELETE /orders/abc-456
```

### Usage

Define a `resolver_fn` that queries your data source and pass it via `LookupConfig`:

```python
from intentful import intent, IntentContext, LookupConfig

async def search_orders(hints: dict) -> list[dict]:
    query = db.query(Order)
    if "customer_name" in hints:
        query = query.filter(Order.customer_name.ilike(f"%{hints['customer_name']}%"))
    if "created_at" in hints:
        query = query.filter(Order.created_at == hints["created_at"])
    return [{"id": o.id, "customer_name": o.customer_name, "total": o.total}
            for o in await query.all()]

@router.delete("/orders/{order_id}")
@intent(
    description="Delete an order",
    context=IntentContext(
        allowed_operations=["DELETE"],
        requires_confirmation=True,
    ),
    method="DELETE",
    path="/orders/{order_id}",
    lookups={
        "order_id": LookupConfig(
            search_fields=["customer_name", "created_at", "description"],
            resolver_fn=search_orders,
            id_field="id",
            display_fields=["customer_name", "total"],
        )
    },
)
async def delete_order(order_id: str):
    ...
```

### LookupConfig parameters

| Parameter | Description |
| --- | --- |
| `search_fields` | Fields the LLM can use as search hints (shown in the prompt context) |
| `resolver_fn` | Async function that receives hints and returns a list of dicts |
| `id_field` | Which field in the result contains the ID (default: `"id"`) |
| `display_fields` | Fields to show the user when confirming or choosing between candidates |

### Resolution outcomes

| Result | Behaviour |
| --- | --- |
| **1 match** | Auto-resolves the parameter and continues to execution/confirmation |
| **N matches** | Returns candidates to the client with `lookup_results` for the user to choose |
| **0 matches** | Returns a 404 error explaining the parameter couldn't be resolved |

---

## How It Works

```text
1. Request arrives with "prompt" field
        |
2. IntentMiddleware intercepts (or /intent endpoint receives)
        |
3. Mode check: single or conversational?
        |
   [single]                          [conversational]
        |                                  |
4. LLM resolves: prompt +            4. Session management:
   endpoints + rules + schemas           start or continue
        |                                  |
5. LLM returns: endpoint,            5. Collect fields one
   payload, confidence,                  by one via LLM
   lookup_hints                          |
        |                             6. When ready, execute
6. Smart Validation: missing              |
   fields? invalid values?           [result]
   generates suggestion
        |
7. Lookup Resolution (if needed):
   resolves hints against real data
        |
8. Confirmation (if required):
   ask user before executing
        |
9. Execute endpoint normally
        |
10. Auditor logs: prompt, payload,
    user, timestamp, result
```

---

## API Reference

### `intentful_auto()`

```python
from intentful import intentful_auto

router = intentful_auto(
    app,                                    # FastAPI app
    backend="anthropic",                    # "anthropic" | "openai" | "ollama" | LLMBackend instance
    language="pt",                          # str or list[str]
    confidence_threshold=0.7,               # 0.0-1.0
    audit_trail=True,                       # enable audit logging
    exclude_paths=["/health", "/metrics"],  # paths to skip
    include_only=["/events", "/users"],     # whitelist mode (None = all)
    default_rules=["Max 200 participants"], # business rules for all endpoints
)
```

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `app` | `FastAPI` | required | The existing FastAPI application |
| `backend` | `str \| LLMBackend` | `"anthropic"` | LLM backend to use |
| `language` | `str \| list[str]` | `"pt"` | Language(s) for prompts |
| `confidence_threshold` | `float` | `0.7` | Minimum confidence to accept a resolution |
| `audit_trail` | `bool` | `True` | Enable audit logging |
| `exclude_paths` | `list[str] \| None` | `None` | Paths to exclude (in addition to `/docs`, `/redoc`, `/openapi.json`) |
| `include_only` | `list[str] \| None` | `None` | If set, only these paths are included |
| `default_rules` | `list[str] \| None` | `None` | Business rules applied to all auto-registered endpoints |

**Returns:** `IntentRouter` — the created router, for further customization if needed.

**Description inference priority:**
1. Handler docstring (first line)
2. Route `summary` attribute (from FastAPI decorator kwargs)
3. Function name humanized (`create_event` -> "Create event")

**Operation inference from HTTP method:**

| HTTP Method | Inferred Operations |
| --- | --- |
| `GET` | `["READ"]` |
| `POST` | `["CREATE", "READ"]` |
| `PUT`, `PATCH` | `["UPDATE"]` |
| `DELETE` | `["DELETE"]` |

Routes already decorated with `@intent` are skipped (not double-registered).

---

### `@intent` decorator

```python
from intentful import intent, IntentContext

@intent(
    description="Create classes for an academic year",
    context=IntentContext(...),
    method="POST",           # HTTP method (default: "POST")
    path="/turmas/gerar",    # explicit path (inferred from function name if omitted)
    tags=["turmas"],         # tags for filtering
    lookups={...},           # LookupConfig for parameter resolution
)
```

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `description` | `str` | required | Human-readable description sent to the LLM |
| `context` | `IntentContext \| None` | `IntentContext()` | Semantic boundaries and rules |
| `method` | `str` | `"POST"` | HTTP method |
| `path` | `str \| None` | inferred | Endpoint path |
| `tags` | `list[str] \| None` | from context | Tags for grouping/filtering |
| `lookups` | `dict[str, LookupConfig] \| None` | `None` | Parameter resolution configs |

---

### `IntentContext`

```python
from intentful import IntentContext

context = IntentContext(
    rules=["Max 40 students per class", "Only active courses"],
    allowed_operations=["CREATE", "READ"],
    requires_confirmation=True,
    confirmation_template="Create {count} classes for {course}. Confirm?",
    examples=["Create classes for Engineering 2025/26"],
    tags=["academic"],
)
```

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `rules` | `list[str]` | `[]` | Business rules the LLM must consider |
| `allowed_operations` | `list[OperationType]` | `["READ"]` | Permitted operations: `CREATE`, `READ`, `UPDATE`, `DELETE` |
| `requires_confirmation` | `bool` | `False` | Require user confirmation before execution |
| `confirmation_template` | `str \| None` | `None` | Custom confirmation message (supports `{placeholders}` from payload) |
| `examples` | `list[str]` | `[]` | Example prompts that should resolve to this endpoint |
| `tags` | `list[str]` | `[]` | Tags for grouping and filtering |

---

### `IntentRouter`

```python
from intentful.integrations.fastapi import IntentRouter, setup_intentful

router = IntentRouter(
    ai_backend="anthropic",      # "anthropic" | "openai" | "ollama" | LLMBackend instance
    language="pt",               # str or list[str]
    confidence_threshold=0.7,    # 0.0-1.0
    audit_trail=True,            # enable audit logging
)

setup_intentful(app, router)
```

`IntentRouter` extends FastAPI's `APIRouter`. All endpoints defined on it are automatically available via `/intent`.

---

### `/intent` endpoint

**POST** `/intent`

#### Request body

```json
{
  "prompt": "create an event called Python Workshop for 50 people",
  "mode": "single",
  "dry_run": false,
  "language": "pt",
  "session_id": null,
  "metadata": {}
}
```

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `prompt` | `string` | required | Natural language prompt |
| `mode` | `"single" \| "conversational"` | `"single"` | Prompt mode |
| `dry_run` | `boolean` | `false` | Simulate without executing |
| `language` | `string` | `"pt"` | Prompt language (ISO 639-1) |
| `session_id` | `string \| null` | `null` | Session ID for conversational mode continuation |
| `metadata` | `object` | `{}` | Additional metadata |

#### Response — Single mode (`IntentResponse`)

```json
{
  "success": true,
  "resolution": {
    "endpoint": "/events",
    "method": "POST",
    "payload": {"name": "Python Workshop", "description": "...", "max_participants": 50},
    "confidence": 0.95,
    "estimated_impact": "1 event will be created",
    "reasoning": "User wants to create an event"
  },
  "confirmation_required": false,
  "confirmation_message": null,
  "result": {"id": 1},
  "error": null,
  "audit_id": "uuid-...",
  "validation_details": null,
  "suggestion": null
}
```

#### Response — Conversational mode (`ConversationResponse`)

```json
{
  "session_id": "uuid-...",
  "status": "collecting",
  "question": "What's the event name?",
  "collected_fields": {},
  "pending_field": "name",
  "resolution": null,
  "result": null,
  "error": null
}
```

#### HTTP status codes

| Code | Meaning |
| --- | --- |
| `200` | Success (check `success` field and `confirmation_required`) |
| `400` | No endpoints registered |
| `404` | Endpoint not found, lookup resolved 0 results, or session expired |
| `422` | Low confidence, validation failed, or invalid payload |
| `500` | Handler execution error |
| `502` | Lookup resolver error |

---

## Features

| Feature | Since | Description |
| --- | --- | --- |
| `@intent` decorator | v0.1.0 | Annotate any FastAPI endpoint with semantic context |
| `IntentRouter` | v0.1.0 | Drop-in replacement for `APIRouter` with intent support |
| Two-step lookup | v0.1.0 | Resolve natural language references to real IDs via your models |
| Dual-mode endpoints | v0.1.0 | Structured payloads and natural language on the same route |
| Confirmation flow | v0.1.0 | Require user confirmation for high-impact operations |
| Dry-run mode | v0.1.0 | Simulate operations without executing |
| Audit trail | v0.1.0 | Log every intent-based operation |
| Multi-backend | v0.1.0 | Anthropic (Claude), OpenAI (GPT), Ollama (local models) |
| Multilingual | v0.1.0 | Accepts prompts in any language |
| `intentful_auto()` | v0.2.0 | Zero-config auto-integration for existing apps |
| Conversational mode | v0.2.0 | Guided multi-step field collection |
| Smart validation | v0.2.0 | Missing field detection + LLM-generated suggestions |

---

## Examples

| Example | Description |
| --- | --- |
| [`examples/demo_app.py`](examples/demo_app.py) | Manual integration with `@intent` and `IntentRouter` |
| [`examples/demo_auto.py`](examples/demo_auto.py) | Zero-config auto-integration with `intentful_auto()` |

```bash
pip install intentful[anthropic]
export ANTHROPIC_API_KEY="sk-..."
uvicorn examples.demo_auto:app --reload
```

---

## Development

```bash
git clone https://github.com/intentful-dev/intentful.git
cd intentful
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

### Project structure

```
intentful/
  __init__.py                      # Public API and exports
  core/
    context.py                     # IntentContext model
    decorator.py                   # @intent decorator
    registry.py                    # IntentRegistry singleton
    schemas.py                     # Request/Response/Conversation schemas
  routing/
    resolver.py                    # LLMResolver (prompt -> endpoint)
    validator.py                   # Basic operation/payload validation
    smart_validation.py            # Smart validation with LLM suggestions (v0.2.0)
    middleware.py                  # IntentMiddleware for transparent interception
    lookup.py                      # Two-step lookup resolution
  conversation/                    # Conversational mode (v0.2.0)
    session.py                     # ConversationSession, FieldSpec
    store.py                       # SessionStore ABC + InMemorySessionStore
    fields.py                      # Pydantic field extraction
    resolver.py                    # ConversationalResolver
  integrations/
    fastapi.py                     # IntentRouter, setup_intentful
    auto.py                        # intentful_auto() zero-config (v0.2.0)
    sqlalchemy.py                  # (planned) SQLAlchemy integration
    oracle.py                      # (planned) Oracle DB integration
  backends/
    __init__.py                    # LLMBackend ABC
    anthropic.py                   # Claude backend
    openai.py                      # GPT backend
    local.py                       # Ollama backend
  execution/
    auditor.py                     # Audit trail
    confirmer.py                   # Confirmation flow
    rollback.py                    # (planned) Rollback support
examples/
  demo_app.py                      # Manual integration example
  demo_auto.py                     # Zero-config example
tests/
  test_core.py                     # Core tests (context, registry, decorator)
  test_schemas.py                  # Schema validation tests
  test_resolver.py                 # LLM resolver tests
  test_validator.py                # Basic validation tests
  test_smart_validation.py         # Smart validation tests (v0.2.0)
  test_auto.py                     # Auto-integration tests (v0.2.0)
  test_conversation.py             # Conversational mode tests (v0.2.0)
  test_lookup.py                   # Lookup resolution tests
  test_middleware.py               # Middleware tests
  test_integration.py              # End-to-end integration tests
  test_auditor.py                  # Audit trail tests
  test_confirmer.py                # Confirmation flow tests
```

---

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

## License

[MIT](LICENSE)
