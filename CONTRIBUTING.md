# Contributing to intentful

Thanks for your interest in contributing! Here's how you can help.

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR-USERNAME/intentful.git
   cd intentful
   ```
3. Create a virtual environment and install dev dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```
4. Create a branch for your changes:
   ```bash
   git checkout -b feat/my-feature
   ```

## Development Workflow

### Running tests

```bash
pytest tests/ -v
```

### Linting

```bash
ruff check intentful/ tests/
```

### Before submitting

- Make sure all tests pass
- Add tests for new features
- Follow the existing code style
- Keep commits focused and descriptive

## Branch Naming

- `feat/` — new features
- `fix/` — bug fixes
- `docs/` — documentation changes
- `test/` — test additions or fixes
- `refactor/` — code refactoring

## Pull Requests

1. Open an issue first to discuss the change
2. Reference the issue in your PR
3. Keep PRs focused — one feature or fix per PR
4. Write a clear description of what changed and why

## Project Structure

```
intentful/
├── core/           # @intent decorator, IntentContext, registry, schemas
├── routing/        # middleware, LLM resolver, payload validator
├── execution/      # audit trail, confirmation, rollback (Phase 2)
├── backends/       # LLM backends (Anthropic, OpenAI, Ollama)
└── integrations/   # FastAPI integration (IntentRouter)
```

## Code of Conduct

Be respectful and constructive. We're building something together.
