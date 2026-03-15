# intentful

[![CI](https://github.com/intentful-dev/intentful/actions/workflows/ci.yml/badge.svg)](https://github.com/intentful-dev/intentful/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-compatible-009688.svg)](https://fastapi.tiangolo.com)

> Build APIs that understand intent, not just requests.

`intentful` is a Python library that lets backend developers annotate FastAPI endpoints with semantic context, making each endpoint naturally actionable via natural language — without chatbots, external agents, or losing control.

## Key Principles

- **Backend-first** — the developer defines the boundaries, the LLM operates within them
- **Progressive enhancement** — the same endpoint works with structured payloads or natural language, without breaking anything

## Installation

```bash
pip install intentful
```

With LLM backends:

```bash
pip install intentful[anthropic]  # Claude
pip install intentful[openai]     # GPT
pip install intentful[all]        # all backends
```

## Quick Start

### 1. Annotate your endpoints

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
    # your normal logic here
    ...

setup_intentful(app, router)
```

### 2. Use it both ways

```bash
# Traditional structured payload
curl -X POST http://localhost:8000/turmas/gerar \
  -H "Content-Type: application/json" \
  -d '{"ano_lectivo": "2025/26", "curso_id": 5}'

# Natural language via /intent
curl -X POST http://localhost:8000/intent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create classes for Engineering in 2025/26"}'

# Dry-run mode (simulate without executing)
curl -X POST http://localhost:8000/intent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create classes for Engineering in 2025/26", "dry_run": true}'
```

## Two-Step Lookup Resolution

### The problem

REST endpoints use identifiers (IDs) in paths — `DELETE /orders/abc-456`. But natural language prompts use descriptions — *"delete João's order from yesterday"*. The LLM doesn't have access to your database and can't know the real ID. If it tries, it hallucinates.

### The solution

Instead of trying to resolve everything in one step, intentful splits the process:

1. **Step 1 — Identify intent**: The LLM picks the right endpoint and extracts search hints from the prompt (e.g. `customer_name: "João"`, `created_at: "2026-03-14"`) — but never invents an ID.
2. **Step 2 — Resolve references**: The system uses your actual models/database to look up candidates matching those hints, then either auto-resolves (1 match), asks the user to choose (N matches), or returns an error (0 matches).

```text
User: "delete João's order from yesterday"
        │
        ▼
   ┌─────────┐
   │ Step 1  │  LLM → identifies endpoint + extracts search hints
   └────┬────┘
        │  endpoint: DELETE /orders/{order_id}
        │  lookup_hints: {customer_name: "João", created_at: "2026-03-14"}
        ▼
   ┌─────────┐
   │ Step 2  │  System → queries your DB/model with the hints
   └────┬────┘
        │  found: order_id = "abc-456"
        ▼
   ┌─────────┐
   │ Confirm │  "Delete order abc-456 (João, €45)?"
   └────┬────┘
        │  user confirms
        ▼
   DELETE /orders/abc-456
```

### Usage

Define a `resolver_fn` that queries your data source and pass it via `LookupConfig`:

```python
from intentful import intent, IntentContext, LookupConfig

# Your lookup function — queries the real database
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

The `LookupConfig` parameters:

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

## How It Works

```text
1. Request arrives with "prompt" field
        ↓
2. IntentMiddleware intercepts (or /intent endpoint receives)
        ↓
3. Resolver queries the IntentRegistry
   (all endpoints annotated with @intent)
        ↓
4. LLM receives: prompt + available endpoints + business rules + schemas
        ↓
5. LLM returns: { endpoint, payload, confidence, lookup_hints }
        ↓
6. Lookup Resolver: resolves hints against real data (if needed)
        ↓
7. Validator checks: valid schema? allowed operations? needs confirmation?
        ↓
8. If confirmed → executes the endpoint normally
        ↓
9. Auditor logs: original prompt, generated payload, user, timestamp, result
```

## Features

- **`@intent` decorator** — annotate any FastAPI endpoint with semantic context
- **`IntentRouter`** — drop-in replacement for `APIRouter` with intent support
- **Two-step lookup resolution** — resolve natural language references to real IDs via your models
- **Dual-mode endpoints** — structured payloads and natural language on the same route
- **Confirmation flow** — require user confirmation for high-impact operations
- **Dry-run mode** — simulate operations without executing
- **Audit trail** — log every intent-based operation
- **Multi-backend** — Anthropic (Claude), OpenAI (GPT), Ollama (local models)
- **Multilingual** — accepts prompts in any language

## Example

See [`examples/demo_app.py`](examples/demo_app.py) for a complete working example.

```bash
pip install intentful[anthropic]
export ANTHROPIC_API_KEY="sk-..."
uvicorn examples.demo_app:app --reload
```

## Development

```bash
git clone https://github.com/intentful-dev/intentful.git
cd intentful
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

## License

[MIT](LICENSE)
