# intentful

> Build APIs that understand intent, not just requests.

`intentful` is a Python library that lets backend developers annotate FastAPI endpoints with semantic context, making each endpoint naturally actionable via natural language — without chatbots, external agents, or losing control.

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

```python
from intentful import intent, IntentContext
from fastapi import APIRouter

router = APIRouter()

@router.post("/turmas/gerar")
@intent(
    description="Criar turmas para um ano lectivo académico",
    context=IntentContext(
        rules=[
            "Cada curso tem anos curriculares definidos no plano curricular",
            "Capacidade máxima padrão é 40 alunos por turma",
        ],
        allowed_operations=["CREATE", "READ"],
        requires_confirmation=True,
    ),
)
async def gerar_turmas(payload: GeraTurmasSchema):
    ...
```

The same endpoint works with structured payloads or natural language:

```python
# Traditional
await api.post("/turmas/gerar", {"ano_lectivo": "2025/26", "curso_id": 5})

# Natural language
await api.post("/turmas/gerar", {"prompt": "Cria turmas para Engenharia em 2025/26"})
```

## License

MIT
