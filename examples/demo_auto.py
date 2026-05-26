# examples/demo_auto.py — Exemplo de auto-integracao zero-config
# Path: examples/demo_auto.py
#
# Este exemplo mostra como integrar o intentful numa app FastAPI existente
# sem alterar nenhuma rota — basta uma linha: intentful_auto(app)
#
# Uso:
#   pip install intentful[anthropic]
#   export ANTHROPIC_API_KEY="sk-..."
#   uvicorn examples.demo_auto:app --reload

from fastapi import FastAPI
from pydantic import BaseModel, Field

from intentful import intentful_auto

app = FastAPI(title="Demo Auto-Integration")


# --- Modelos ---

class EventPayload(BaseModel):
    name: str = Field(..., description="Nome do evento")
    description: str = Field(..., description="Descricao do evento")
    max_participants: int = Field(..., description="Numero maximo de participantes")
    location: str = Field(default="Online", description="Local do evento")


class UserPayload(BaseModel):
    username: str = Field(..., description="Nome de utilizador")
    email: str = Field(..., description="Email do utilizador")


# --- Rotas normais (sem @intent, sem IntentRouter) ---

@app.post("/eventos")
async def criar_evento(payload: EventPayload):
    """Criar um novo evento no sistema."""
    return {"id": 1, "evento": payload.model_dump(), "status": "criado"}


@app.get("/eventos")
async def listar_eventos():
    """Listar todos os eventos disponiveis."""
    return [
        {"id": 1, "name": "Workshop Python", "max_participants": 50},
        {"id": 2, "name": "Hackathon IA", "max_participants": 100},
    ]


@app.delete("/eventos/{evento_id}")
async def apagar_evento(evento_id: int):
    """Apagar um evento pelo seu ID."""
    return {"deleted": evento_id}


@app.post("/utilizadores")
async def criar_utilizador(payload: UserPayload):
    """Registar um novo utilizador."""
    return {"id": 42, "user": payload.model_dump()}


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Uma unica linha para activar o intentful ---
intentful_auto(
    app,
    backend="anthropic",
    language="pt",
    exclude_paths=["/health"],
    default_rules=["Maximo 200 participantes por evento"],
)

# Agora pode usar:
#   POST /intent {"prompt": "criar um evento Workshop de Python para 50 pessoas"}
#   POST /intent {"prompt": "listar eventos", "dry_run": true}
#   POST /intent {"prompt": "apagar o evento 1"}
