# intentful

[![CI](https://github.com/intentful-dev/intentful/actions/workflows/ci.yml/badge.svg)](https://github.com/intentful-dev/intentful/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> AI agent that connects to any backend via OpenAPI — understand intent, not just requests.

`intentful` is a standalone AI agent that sits between your users and your backend API. It reads your OpenAPI spec, understands what each endpoint does, and lets users interact with your API using natural language — through a CLI, an API, or a drop-in frontend widget.

**Works with any backend** — Python, Node.js, Go, Java, Ruby, whatever serves an OpenAPI spec.

## What changed in v1.0

| v0.2 (library) | v1.0 (agent) |
| --- | --- |
| Python library imported inside FastAPI | Standalone agent, connects to any backend |
| Only FastAPI/Python backends | Any backend with OpenAPI/Swagger spec |
| `@intent` decorator required | Auto-discovery from OpenAPI spec |
| No frontend | Drop-in chat widget ("i" button) |
| `pip install` + code changes | `pip install` + one command to start |

The FastAPI integration (`intentful_auto`, `@intent`, `IntentRouter`) still works — v1.0 is backwards compatible.

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
  - [Option A: Standalone Agent (any backend)](#option-a-standalone-agent-any-backend)
  - [Option B: Frontend Widget](#option-b-frontend-widget)
  - [Option C: FastAPI Integration (legacy)](#option-c-fastapi-integration-legacy)
- [CLI Reference](#cli-reference)
- [Agent API Reference](#agent-api-reference)
- [Frontend Widget](#frontend-widget)
- [Prompt Modes](#prompt-modes)
- [Smart Validation](#smart-validation)
- [Two-Step Lookup Resolution](#two-step-lookup-resolution)
- [FastAPI Integration (legacy)](#fastapi-integration-legacy)
- [Features](#features)
- [Development](#development)

---

## Installation

```bash
pip install intentful
```

With LLM backends:

```bash
pip install intentful[anthropic]  # Claude (recommended)
pip install intentful[openai]     # GPT
pip install intentful[all]        # all backends
```

For local models (Ollama), no extra dependencies are needed — Ollama uses httpx which is already included.

---

## Quick Start

### Option A: Standalone Agent (any backend)

Your backend can be written in **any language**. The only requirement is that it serves an OpenAPI/Swagger spec.

**1. Scan your API to see what intentful discovers:**

```bash
intentful scan --openapi-url http://localhost:3000/openapi.json
```

Output:

```
         Endpoints descobertos (5)
┌────────┬──────────────┬──────────────────┬────────────┬─────────┐
│ Method │ Path         │ Description      │ Operations │ Payload │
├────────┼──────────────┼──────────────────┼────────────┼─────────┤
│ GET    │ /users       │ List all users   │ READ       │   —     │
│ POST   │ /users       │ Create a user    │ CREATE     │   ✓     │
│ GET    │ /users/{id}  │ Get user by ID   │ READ       │   —     │
│ PUT    │ /users/{id}  │ Update user      │ UPDATE     │   ✓     │
│ DELETE │ /users/{id}  │ Delete user      │ DELETE     │   —     │
└────────┴──────────────┴──────────────────┴────────────┴─────────┘
```

**2. Start the agent:**

```bash
export ANTHROPIC_API_KEY="sk-..."
intentful serve --openapi-url http://localhost:3000/openapi.json
```

```
Intentful Agent v1.0.0
  Target:  http://localhost:3000/openapi.json
  Backend: anthropic
  Server:  http://0.0.0.0:8100
  Widget:  http://0.0.0.0:8100/widget/intentful.js
```

**3. Send a prompt:**

```bash
curl -X POST http://localhost:8100/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "create a user called João with email joao@example.com"}'
```

Response:

```json
{
  "success": true,
  "resolution": {
    "endpoint": "/users",
    "method": "POST",
    "payload": {"name": "João", "email": "joao@example.com"},
    "confidence": 0.95
  },
  "result": {"id": 1, "name": "João", "email": "joao@example.com"}
}
```

**4. Or use the CLI directly (no server needed):**

```bash
intentful prompt "list all users" --openapi-url http://localhost:3000/openapi.json
```

### Option B: Frontend Widget

Add the chat widget to any frontend — one script tag, zero dependencies:

```html
<script src="http://localhost:8100/widget/intentful.js"></script>
<script>
  Intentful.init({
    serverUrl: "http://localhost:8100",
    position: "bottom-right",  // bottom-right | bottom-left | top-right | top-left
    theme: "light",            // light | dark
    language: "pt",
    title: "Intentful",
    placeholder: "Escreva o que pretende fazer..."
  });
</script>
```

This renders a floating "i" button. When clicked, it opens a chat where users can type natural language prompts that are resolved and executed against your backend.

**Widget API:**

```javascript
Intentful.open();          // Open the chat programmatically
Intentful.close();         // Close the chat
Intentful.resetSession();  // Clear conversation history
```

### Option C: FastAPI Integration (legacy)

If your backend is FastAPI and you want the library integrated directly (v0.2 approach):

```python
from fastapi import FastAPI
from intentful import intentful_auto

app = FastAPI()

# ... your routes ...

intentful_auto(app, backend="anthropic")
```

See [FastAPI Integration (legacy)](#fastapi-integration-legacy) for full details.

---

## CLI Reference

### `intentful serve`

Start the standalone agent server.

```bash
intentful serve --openapi-url <url> [options]
```

| Option | Default | Description |
| --- | --- | --- |
| `--openapi-url` | required | URL or local path to the OpenAPI spec |
| `--target-url` | inferred | Base URL of the target backend. Inferred from openapi-url if omitted |
| `--backend` | `anthropic` | LLM backend: `anthropic`, `openai`, `ollama` |
| `--port` | `8100` | Agent server port |
| `--host` | `0.0.0.0` | Agent server host |
| `--confidence` | `0.7` | Minimum confidence threshold (0-1) |
| `--language` | `pt` | Default language (ISO 639-1) |

### `intentful scan`

Scan an OpenAPI spec and show discovered endpoints (dry-run, no server started).

```bash
intentful scan --openapi-url <url> [--format table|json]
```

### `intentful prompt`

Send a one-shot prompt without starting the server.

```bash
intentful prompt "create an event" --openapi-url <url> [options]
```

| Option | Default | Description |
| --- | --- | --- |
| `--openapi-url` | required | URL or path to the OpenAPI spec |
| `--target-url` | inferred | Base URL of the target backend |
| `--backend` | `anthropic` | LLM backend |
| `--language` | `pt` | Prompt language |
| `--dry-run` | `false` | Simulate without executing |

---

## Agent API Reference

When running `intentful serve`, these endpoints are available:

### `POST /prompt`

Send a natural language prompt.

**Request:**

```json
{
  "prompt": "create a user called João",
  "language": "pt",
  "mode": "single",
  "dry_run": false,
  "session_id": null,
  "user_id": null,
  "confirmed": false
}
```

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `prompt` | `string` | required | Natural language prompt |
| `mode` | `string` | `"single"` | `"single"` or `"conversational"` |
| `language` | `string` | `"pt"` | Prompt language (ISO 639-1) |
| `dry_run` | `boolean` | `false` | Simulate without executing |
| `session_id` | `string?` | `null` | Session ID for continuing a conversation |
| `user_id` | `string?` | `null` | User ID for audit trail |
| `confirmed` | `boolean` | `false` | Confirm a pending operation |

**Response:**

```json
{
  "success": true,
  "message": null,
  "resolution": {
    "endpoint": "/users",
    "method": "POST",
    "payload": {"name": "João"},
    "confidence": 0.95,
    "reasoning": "User wants to create a new user"
  },
  "result": {"id": 1, "name": "João"},
  "error": null,
  "audit_id": "uuid-...",
  "validation_details": null,
  "confirmation_required": false,
  "confirmation_message": null,
  "conversation": null
}
```

**HTTP status codes:**

| Code | Meaning |
| --- | --- |
| `200` | Success |
| `422` | Low confidence or validation failed |
| `404` | Endpoint not found |
| `502` | Error contacting backend or LLM |
| `503` | No endpoints discovered |

### `GET /health`

Health check.

```json
{
  "status": "ok",
  "version": "1.0.0",
  "endpoints_discovered": 5,
  "target": "http://localhost:3000/openapi.json",
  "backend": "anthropic"
}
```

### `GET /endpoints`

List all discovered endpoints.

```json
[
  {
    "path": "/users",
    "method": "GET",
    "description": "List all users",
    "allowed_operations": ["READ"],
    "payload_schema": null
  }
]
```

### `GET /widget/intentful.js`

Serves the frontend widget JavaScript file.

---

## Frontend Widget

The widget is a single vanilla JavaScript file with zero dependencies. It renders a floating chat button ("i") that connects to the intentful agent.

### How to add it

**Option 1: From the agent server**

```html
<script src="http://localhost:8100/widget/intentful.js"></script>
<script>Intentful.init({ serverUrl: "http://localhost:8100" });</script>
```

**Option 2: Self-hosted**

Copy `intentful/widget/intentful.js` to your static assets and serve it directly.

### Configuration

```javascript
Intentful.init({
  serverUrl: "http://localhost:8100",  // Intentful agent URL
  position: "bottom-right",            // Button position
  theme: "light",                      // "light" or "dark"
  language: "pt",                      // Default language
  placeholder: "Escreva o que pretende fazer...",
  title: "Intentful",                  // Chat header title
  buttonSize: 56,                      // Button size in pixels
});
```

### Features

- Sends prompts to `POST /prompt` on the agent
- Displays responses inline in the chat
- Supports conversational mode (maintains session)
- Light and dark themes
- Configurable position (four corners)
- Works with any frontend framework or static HTML

---

## Prompt Modes

### Single Prompt (default)

Send a complete prompt and get an immediate result:

```bash
curl -X POST http://localhost:8100/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create event Python Workshop for 50 people"}'
```

Use `"dry_run": true` to simulate without executing.

### Conversational Mode

The system guides the user through each required field, step by step:

**Start a conversation:**

```bash
curl -X POST http://localhost:8100/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "create event", "mode": "conversational"}'
```

Response:

```json
{
  "success": true,
  "conversation": {
    "session_id": "a1b2c3d4-...",
    "status": "collecting",
    "question": "What's the event name?",
    "collected_fields": {},
    "pending_field": "name"
  }
}
```

**Continue the conversation:**

```bash
curl -X POST http://localhost:8100/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Python Workshop", "mode": "conversational", "session_id": "a1b2c3d4-..."}'
```

The system keeps asking until all required fields are collected, then executes automatically.

**Session states:**

| Status | Meaning |
| --- | --- |
| `resolving` | Identifying which endpoint the user wants |
| `collecting` | Collecting required fields one by one |
| `ready` | All fields collected, about to execute |
| `completed` | Endpoint executed, result available |
| `expired` | Session timed out (default: 5 minutes) |

---

## Smart Validation

When a prompt is incomplete or produces invalid data, intentful provides structured error details and user-friendly suggestions:

```json
{
  "success": false,
  "error": "Validacao falhou: ...",
  "validation_details": {
    "valid": false,
    "errors": ["Campo obrigatorio em falta: 'email'"],
    "missing_fields": ["email"],
    "invalid_fields": {},
    "suggestion": "Falta indicar o email do utilizador."
  }
}
```

**What smart validation checks:**

1. **Allowed operations** — is the HTTP method permitted?
2. **Missing required fields** — compares payload against the schema
3. **Invalid values** — type errors and constraint violations
4. **LLM-generated suggestion** — natural language explanation in the user's language

---

## Two-Step Lookup Resolution

REST endpoints use IDs (`DELETE /orders/abc-456`), but users say *"delete Joao's order"*. Intentful splits the process:

1. **LLM** picks the endpoint and extracts search hints (`customer_name: "Joao"`)
2. **Your resolver function** queries the real database and returns candidates
3. **Auto-resolve** (1 match), **ask user** (N matches), or **error** (0 matches)

This feature requires the `@intent` decorator with `LookupConfig` — see the FastAPI integration section.

---

## FastAPI Integration (legacy)

For FastAPI backends, you can still use the library directly without the standalone agent.

### Zero-Config

```python
from fastapi import FastAPI
from intentful import intentful_auto

app = FastAPI()

@app.post("/events")
async def create_event(payload: EventPayload):
    """Create a new event."""
    return {"id": 1, "event": payload.model_dump()}

intentful_auto(app, backend="anthropic")
```

### Manual Annotation

```python
from intentful import intent, IntentContext
from intentful.integrations.fastapi import IntentRouter, setup_intentful

app = FastAPI()
router = IntentRouter(ai_backend="anthropic", language="pt")

@router.post("/turmas/gerar")
@intent(
    description="Create classes for an academic year",
    context=IntentContext(
        rules=["Max 40 students per class"],
        allowed_operations=["CREATE"],
        requires_confirmation=True,
    ),
    path="/turmas/gerar",
)
async def gerar_turmas(payload: GeraTurmasSchema):
    return {"created": True}

setup_intentful(app, router)
```

### `intentful_auto()` parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `app` | `FastAPI` | required | The existing FastAPI application |
| `backend` | `str \| LLMBackend` | `"anthropic"` | LLM backend to use |
| `language` | `str \| list[str]` | `"pt"` | Language(s) for prompts |
| `confidence_threshold` | `float` | `0.7` | Minimum confidence (0-1) |
| `audit_trail` | `bool` | `True` | Enable audit logging |
| `exclude_paths` | `list[str]?` | `None` | Paths to exclude |
| `include_only` | `list[str]?` | `None` | Whitelist mode |
| `default_rules` | `list[str]?` | `None` | Business rules for all endpoints |

---

## Features

| Feature | Since | Description |
| --- | --- | --- |
| **Standalone agent** | v1.0.0 | Connects to any backend via OpenAPI — no code changes needed |
| **CLI** | v1.0.0 | `intentful serve`, `intentful scan`, `intentful prompt` |
| **Frontend widget** | v1.0.0 | Drop-in chat button ("i") for any frontend |
| **OpenAPI scanner** | v1.0.0 | Auto-discovers endpoints from OpenAPI/Swagger specs |
| **HTTP executor** | v1.0.0 | Executes calls to the target backend via HTTP |
| `intentful_auto()` | v0.2.0 | Zero-config FastAPI integration |
| Conversational mode | v0.2.0 | Guided multi-step field collection |
| Smart validation | v0.2.0 | Missing field detection + LLM-generated suggestions |
| `@intent` decorator | v0.1.0 | Annotate endpoints with semantic context |
| Two-step lookup | v0.1.0 | Resolve natural language references to real IDs |
| Confirmation flow | v0.1.0 | Require user confirmation for high-impact operations |
| Dry-run mode | v0.1.0 | Simulate operations without executing |
| Audit trail | v0.1.0 | Log every intent-based operation |
| Multi-backend | v0.1.0 | Anthropic (Claude), OpenAI (GPT), Ollama (local) |
| Multilingual | v0.1.0 | Accepts prompts in any language |

---

## Architecture

```
Frontend (any)                 Intentful Agent (Python)          Backend (any)
┌──────────────┐              ┌───────────────────────┐         ┌──────────────┐
│  Widget "i"  │──prompt────→ │  intentful serve      │         │              │
│  (chat       │              │  ┌─────────────────┐  │──HTTP─→ │  Express     │
│   flutuante) │←─response─── │  │ OpenAPI Scanner │  │         │  FastAPI     │
│              │              │  │ LLM Resolver    │  │         │  Go / Spring │
│  Any frontend│              │  │ HTTP Executor   │  │         │  Rails / etc │
└──────────────┘              │  │ Conversation    │  │         └──────────────┘
                              │  │ Smart Validation│  │
                              │  └─────────────────┘  │
                              └───────────────────────┘
```

**How it works:**

1. On startup, the agent fetches the OpenAPI spec from the target backend
2. It parses all endpoints, extracts descriptions, schemas, and parameters
3. When a prompt arrives, the LLM resolves it to the best matching endpoint
4. The payload is validated against the endpoint's schema
5. The agent executes the HTTP call to the real backend
6. The result is returned to the user

---

## Development

```bash
git clone https://github.com/intentful-dev/intentful.git
cd intentful
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,all]"
pytest tests/ -v
```

### Project structure

```
intentful/
  __init__.py                      # Public API and exports
  core/                            # Registry, schemas, context (framework-agnostic)
    context.py                     # IntentContext model
    decorator.py                   # @intent decorator
    registry.py                    # IntentRegistry singleton
    schemas.py                     # Request/Response schemas
  scanner/                         # OpenAPI auto-discovery (v1.0)
    openapi.py                     # OpenAPI 3.x parser
    registry_builder.py            # Spec → IntentRegistry
  server/                          # Standalone agent server (v1.0)
    app.py                         # FastAPI app for the agent
    routes.py                      # /prompt, /health, /endpoints
    executor.py                    # HTTP calls to target backend
  cli/                             # CLI entry point (v1.0)
    main.py                        # intentful serve|scan|prompt
  widget/                          # Frontend widget (v1.0)
    intentful.js                   # Vanilla JS chat widget
  routing/                         # LLM resolution pipeline
    resolver.py                    # LLMResolver (prompt → endpoint)
    validator.py                   # Basic validation
    smart_validation.py            # Smart validation + LLM suggestions
    middleware.py                  # IntentMiddleware (FastAPI)
    lookup.py                      # Two-step lookup resolution
  conversation/                    # Conversational mode
    session.py                     # ConversationSession, FieldSpec
    store.py                       # Session storage
    fields.py                      # Pydantic field extraction
    resolver.py                    # ConversationalResolver
  integrations/                    # Framework-specific (legacy)
    fastapi.py                     # IntentRouter, setup_intentful
    auto.py                        # intentful_auto() zero-config
  backends/                        # LLM backends
    anthropic.py                   # Claude
    openai.py                      # GPT
    local.py                       # Ollama
  execution/                       # Audit and confirmation
    auditor.py                     # Audit trail
    confirmer.py                   # Confirmation flow
tests/
  test_scanner.py                  # OpenAPI scanner tests
  test_executor.py                 # HTTP executor tests
  test_server.py                   # Standalone server tests
  test_cli.py                      # CLI tests
  test_core.py                     # Core tests
  test_resolver.py                 # LLM resolver tests
  test_conversation.py             # Conversational mode tests
  test_smart_validation.py         # Smart validation tests
  test_integration.py              # End-to-end tests
  ...
```

---

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

## License

[MIT](LICENSE)
