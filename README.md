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

## How It Works

```
1. Request arrives with "prompt" field
        ↓
2. IntentMiddleware intercepts (or /intent endpoint receives)
        ↓
3. Resolver queries the IntentRegistry
   (all endpoints annotated with @intent)
        ↓
4. LLM receives: prompt + available endpoints + business rules + schemas
        ↓
5. LLM returns: { endpoint, payload, confidence, estimated_impact }
        ↓
6. Validator checks: valid schema? allowed operations? needs confirmation?
        ↓
7. If confirmed → executes the endpoint normally
        ↓
8. Auditor logs: original prompt, generated payload, user, timestamp, result
```

## Features

- **`@intent` decorator** — annotate any FastAPI endpoint with semantic context
- **`IntentRouter`** — drop-in replacement for `APIRouter` with intent support
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
