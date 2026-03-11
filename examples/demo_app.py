# examples/demo_app.py — Mini app FastAPI que demonstra o intentful
# Path: examples/demo_app.py
#
# Correr:
#   pip install intentful[anthropic]
#   export ANTHROPIC_API_KEY="sk-..."
#   uvicorn examples.demo_app:app --reload
#
# Testar:
#   # Payload estruturado (modo tradicional)
#   curl -X POST http://localhost:8000/turmas/gerar \
#     -H "Content-Type: application/json" \
#     -d '{"ano_lectivo": "2025/26", "curso_id": 5}'
#
#   # Linguagem natural via /intent
#   curl -X POST http://localhost:8000/intent \
#     -H "Content-Type: application/json" \
#     -d '{"prompt": "Cria turmas para Engenharia em 2025/26"}'
#
#   # Modo dry-run (simula sem executar)
#   curl -X POST http://localhost:8000/intent \
#     -H "Content-Type: application/json" \
#     -d '{"prompt": "Matricula os alunos transitados em 2025/26", "dry_run": true}'

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from intentful import IntentContext, intent
from intentful.integrations.fastapi import IntentRouter, setup_intentful

# --- App ---

app = FastAPI(
    title="intentful Demo",
    description="Demonstração da biblioteca intentful com endpoints académicos.",
    version="0.1.0",
)

router = IntentRouter(
    ai_backend="anthropic",
    language="pt",
    audit_trail=True,
    confidence_threshold=0.7,
)


# --- Schemas ---


class GeraTurmasSchema(BaseModel):
    ano_lectivo: str = Field(..., description="Ano lectivo (ex: 2025/26)")
    curso_id: int = Field(..., description="ID do curso")
    capacidade: int = Field(default=40, description="Capacidade máxima por turma")


class MatriculaSchema(BaseModel):
    ano_lectivo: str = Field(..., description="Ano lectivo")
    curso_id: int | None = Field(default=None, description="ID do curso (None = todos)")


class NotasSchema(BaseModel):
    disciplina_id: int = Field(..., description="ID da disciplina")
    ano_lectivo: str = Field(..., description="Ano lectivo")


# --- Endpoints ---


@router.post("/turmas/gerar")
@intent(
    description="Criar turmas para um ano lectivo académico",
    context=IntentContext(
        rules=[
            "Cada curso tem anos curriculares definidos no plano curricular",
            "Capacidade máxima padrão é 40 alunos por turma",
            "Períodos válidos: 1º Semestre, 2º Semestre, Anual",
        ],
        allowed_operations=["CREATE", "READ"],
        requires_confirmation=True,
        confirmation_template=(
            "Vou criar turmas para o curso {curso_id} no ano lectivo {ano_lectivo} "
            "com capacidade de {capacidade} alunos. Confirmas?"
        ),
    ),
    path="/turmas/gerar",
    tags=["turmas", "academico"],
)
async def gerar_turmas(payload: GeraTurmasSchema) -> dict:
    """Gera turmas para um curso num dado ano lectivo."""
    # Simulação — numa app real, isto interagiria com a base de dados
    turmas = [
        {"nome": f"T{i}", "curso_id": payload.curso_id, "capacidade": payload.capacidade}
        for i in range(1, 4)
    ]
    return {
        "turmas_criadas": len(turmas),
        "ano_lectivo": payload.ano_lectivo,
        "curso_id": payload.curso_id,
        "turmas": turmas,
    }


@router.post("/matriculas/auto")
@intent(
    description="Matricular automaticamente alunos transitados no novo ano lectivo",
    context=IntentContext(
        rules=[
            "Só alunos com aproveitamento podem ser matriculados automaticamente",
            "A matrícula automática respeita os pré-requisitos curriculares",
        ],
        allowed_operations=["CREATE"],
        requires_confirmation=True,
        confirmation_template=(
            "Vou matricular automaticamente os alunos transitados "
            "no ano lectivo {ano_lectivo}. Confirmas?"
        ),
    ),
    path="/matriculas/auto",
    tags=["matriculas", "academico"],
)
async def matricula_automatica(payload: MatriculaSchema) -> dict:
    """Matricula automaticamente alunos transitados."""
    return {
        "matriculados": 47,
        "ano_lectivo": payload.ano_lectivo,
        "curso_id": payload.curso_id or "todos",
    }


@router.get("/notas/pauta")
@intent(
    description="Consultar pauta de notas de uma disciplina",
    context=IntentContext(
        rules=["Apenas docentes da disciplina podem consultar a pauta completa"],
        allowed_operations=["READ"],
    ),
    method="GET",
    path="/notas/pauta",
    tags=["notas", "academico"],
)
async def consultar_pauta(payload: NotasSchema) -> dict:
    """Consulta a pauta de notas de uma disciplina."""
    return {
        "disciplina_id": payload.disciplina_id,
        "ano_lectivo": payload.ano_lectivo,
        "alunos": [
            {"nome": "Ana Silva", "nota": 16},
            {"nome": "João Santos", "nota": 14},
            {"nome": "Maria Costa", "nota": 18},
        ],
    }


# --- Setup ---

setup_intentful(app, router)


# --- Endpoint de saúde ---


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
