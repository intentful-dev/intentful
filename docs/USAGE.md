# intentful — Guia de Utilizacao

<!-- Path: docs/USAGE.md -->

Guia pratico para integrar o `intentful` numa aplicacao FastAPI.

---

## Indice

1. [Instalacao](#instalacao)
2. [Setup Basico](#setup-basico)
3. [Anotar Endpoints com @intent](#anotar-endpoints-com-intent)
4. [Configurar o Backend LLM](#configurar-o-backend-llm)
5. [Usar o Endpoint /intent](#usar-o-endpoint-intent)
6. [Modo Dual: Estruturado + Linguagem Natural](#modo-dual)
7. [Confirmacao de Operacoes](#confirmacao-de-operacoes)
8. [Dry-Run (Simulacao)](#dry-run)
9. [Audit Trail](#audit-trail)
10. [Exemplos Completos](#exemplos-completos)

---

## Instalacao

```bash
# Core (sem backend LLM)
pip install intentful

# Com backend especifico
pip install intentful[openai]      # GPT (recomendado para comecar)
pip install intentful[anthropic]   # Claude
pip install intentful[all]         # Todos os backends
```

Para usar Ollama (modelos locais), nao e necessario instalar extras:

```bash
pip install intentful
# Depois: ollama pull llama3.1:8b
```

---

## Setup Basico

Tres passos para adicionar intent a uma app FastAPI existente:

```python
from fastapi import FastAPI
from intentful import intent, IntentContext
from intentful.integrations.fastapi import IntentRouter, setup_intentful

# 1. Criar a app normalmente
app = FastAPI(title="Minha App")

# 2. Criar o IntentRouter (substitui o APIRouter)
router = IntentRouter(
    ai_backend="openai",       # "openai", "anthropic", ou "ollama"
    language="pt",             # Lingua dos prompts
    confidence_threshold=0.7,  # Confianca minima (0.0 a 1.0)
    audit_trail=True,          # Registar todas as operacoes
)

# 3. Configurar e arrancar
setup_intentful(app, router)
```

A funcao `setup_intentful()` faz duas coisas:
- Adiciona o `IntentMiddleware` (intercepta requests com campo `"prompt"`)
- Inclui o router com o endpoint `POST /intent`

---

## Anotar Endpoints com @intent

O decorator `@intent` anota um endpoint com contexto semantico. O endpoint
continua a funcionar normalmente — o decorator so adiciona metadata.

### Endpoint de leitura simples

```python
from pydantic import BaseModel, Field

class FiltroAlunos(BaseModel):
    curso_id: int | None = Field(default=None, description="Filtrar por curso")
    ano: int | None = Field(default=None, description="Filtrar por ano curricular")

@router.post("/alunos/listar")
@intent(
    description="Listar alunos com filtro opcional por curso ou ano",
    context=IntentContext(
        rules=["Sem filtros retorna todos os alunos activos"],
        allowed_operations=["READ"],
    ),
    path="/alunos/listar",
)
async def listar_alunos(payload: FiltroAlunos) -> dict:
    # logica normal...
    return {"alunos": [...]}
```

### Endpoint de escrita com confirmacao

```python
class CriaTurma(BaseModel):
    ano_lectivo: str = Field(..., description="Ano lectivo (ex: 2025/26)")
    curso_id: int = Field(..., description="ID do curso")
    capacidade: int = Field(default=40, description="Capacidade maxima")

@router.post("/turmas/gerar")
@intent(
    description="Gerar turmas automaticamente para um curso",
    context=IntentContext(
        rules=[
            "Cria uma turma por disciplina do curso",
            "Capacidade padrao e 40 alunos por turma",
            "Verifica duplicados antes de criar",
        ],
        allowed_operations=["CREATE", "READ"],
        requires_confirmation=True,
        confirmation_template="Criar turmas para curso {curso_id} em {ano_lectivo}. Confirmas?",
    ),
    path="/turmas/gerar",
)
async def gerar_turmas(payload: CriaTurma) -> dict:
    # logica de criacao...
    return {"turmas_criadas": 10}
```

### Parametros do @intent

| Parametro | Tipo | Obrigatorio | Descricao |
|-----------|------|-------------|-----------|
| `description` | `str` | Sim | Descricao clara do que o endpoint faz. O LLM usa isto para decidir qual endpoint usar |
| `context` | `IntentContext` | Nao | Regras de negocio, permissoes, confirmacao |
| `method` | `str` | Nao | Metodo HTTP (default: `"POST"`) |
| `path` | `str` | Nao | Path do endpoint (inferido do nome da funcao se omitido) |
| `tags` | `list[str]` | Nao | Tags para agrupar endpoints |

### Parametros do IntentContext

| Parametro | Tipo | Default | Descricao |
|-----------|------|---------|-----------|
| `rules` | `list[str]` | `[]` | Regras de negocio enviadas ao LLM |
| `allowed_operations` | `list[str]` | `["READ"]` | Operacoes permitidas: `CREATE`, `READ`, `UPDATE`, `DELETE` |
| `requires_confirmation` | `bool` | `False` | Se True, pede confirmacao antes de executar |
| `confirmation_template` | `str` | `None` | Template com `{placeholders}` do payload |
| `examples` | `list[str]` | `[]` | Exemplos de prompts que devem resolver para este endpoint |
| `tags` | `list[str]` | `[]` | Tags de agrupamento |

### Boas Praticas

**Descricoes claras:** A descricao e o que o LLM mais usa para decidir. Seja especifico:
- Mau: `"Gerir turmas"`
- Bom: `"Gerar turmas automaticamente para todas as disciplinas de um curso num ano lectivo"`

**Regras de negocio:** Adicione regras que o LLM deve considerar ao gerar o payload:
```python
rules=[
    "So matricula alunos activos",
    "Precisa que as turmas ja estejam criadas",
    "Capacidade maxima por turma: 40 alunos",
]
```

**Schemas Pydantic descritivos:** Use `Field(description=...)` em todos os campos.
O schema e enviado ao LLM — descricoes boas geram payloads melhores:
```python
class Schema(BaseModel):
    # Mau:
    id: int
    # Bom:
    curso_id: int = Field(..., description="ID do curso (ex: 1=Eng. Informatica, 2=Eng. Civil)")
```

**Exemplos de prompts:** Ajudam o LLM a fazer matching correcto:
```python
examples=[
    "mostra os alunos do 2 ano",
    "lista alunos de engenharia informatica",
    "quais alunos estao no 3 ano?",
]
```

---

## Configurar o Backend LLM

### OpenAI (GPT)

```bash
pip install intentful[openai]
export OPENAI_API_KEY="sk-..."
```

```python
# Por nome (usa defaults)
router = IntentRouter(ai_backend="openai")

# Com configuracao personalizada
from intentful.backends.openai import OpenAIBackend

backend = OpenAIBackend(
    model="gpt-4o-mini",  # Mais barato, suficiente para resolucao de intents
    max_tokens=1024,
)
router = IntentRouter(ai_backend=backend)
```

**Modelos recomendados:**
- `gpt-4o-mini` — barato, rapido, muito bom para intent resolution
- `gpt-4o` — mais capaz, para casos complexos

### Anthropic (Claude)

```bash
pip install intentful[anthropic]
export ANTHROPIC_API_KEY="sk-ant-..."
```

```python
# Por nome
router = IntentRouter(ai_backend="anthropic")

# Personalizado
from intentful.backends.anthropic import AnthropicBackend

backend = AnthropicBackend(model="claude-sonnet-4-20250514")
router = IntentRouter(ai_backend=backend)
```

### Ollama (Modelos Locais)

```bash
# Instalar e iniciar Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
ollama serve
```

```python
from intentful.backends.local import OllamaBackend

backend = OllamaBackend(
    model="llama3.1:8b",
    base_url="http://localhost:11434",
)
router = IntentRouter(ai_backend=backend)
```

**Modelos recomendados para Ollama:**
- `llama3.1:8b` — bom equilibrio custo/qualidade
- `qwen2.5:7b` — alternativa competitiva
- `llama3.2:1b` — **nao recomendado** (demasiado pequeno, gera JSON inconsistente)

### Backend Personalizado

Pode criar o seu proprio backend implementando a interface `LLMBackend`:

```python
from intentful.backends import LLMBackend

class MeuBackend(LLMBackend):
    async def complete(self, system: str, prompt: str) -> str:
        # A sua logica aqui
        # Deve devolver uma string JSON valida
        return '{"endpoint": "/...", "confidence": 0.9, ...}'

router = IntentRouter(ai_backend=MeuBackend())
```

---

## Usar o Endpoint /intent

O `IntentRouter` cria automaticamente um endpoint `POST /intent` que aceita
prompts em linguagem natural.

### Request basico

```bash
curl -X POST http://localhost:8000/intent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "mostra todos os cursos"}'
```

### Parametros do request

```json
{
    "prompt": "mostra todos os cursos",
    "language": "pt",
    "dry_run": false,
    "confirmed": false,
    "user_id": "user123",
    "metadata": {}
}
```

| Campo | Obrigatorio | Descricao |
|-------|-------------|-----------|
| `prompt` | Sim | O pedido em linguagem natural |
| `language` | Nao | Lingua do prompt (default: configurado no router) |
| `dry_run` | Nao | Se `true`, simula sem executar |
| `confirmed` | Nao | Se `true`, confirma operacoes que pedem confirmacao |
| `user_id` | Nao | ID do utilizador (para auditoria) |
| `metadata` | Nao | Dados adicionais |

### Exemplo de resposta (sucesso)

```json
{
    "success": true,
    "resolution": {
        "endpoint": "/cursos/listar",
        "method": "POST",
        "payload": {"nome": null},
        "confidence": 0.95,
        "estimated_impact": "Retorna a lista de todos os cursos disponiveis.",
        "reasoning": "O prompt pede para listar cursos."
    },
    "result": {
        "total": 3,
        "cursos": [
            {"id": 1, "nome": "Engenharia Informatica", "sigla": "EI"},
            {"id": 2, "nome": "Engenharia Civil", "sigla": "EC"}
        ]
    },
    "audit_id": "a1b2c3d4-..."
}
```

### Codigos de resposta

| Codigo | Significado |
|--------|-------------|
| 200 | Sucesso (ou confirmacao pendente) |
| 400 | Nenhum endpoint registado com @intent |
| 404 | LLM resolveu para um endpoint que nao existe |
| 422 | Confianca insuficiente ou validacao falhou |
| 500 | Erro ao executar o handler |

---

## Modo Dual

O mesmo endpoint funciona com payloads estruturados (chamadas tradicionais)
e com linguagem natural (via `/intent` ou middleware).

```python
# Rota com intent (resolve via LLM)
@router.post("/alunos/listar")
@intent(description="Listar alunos", path="/alunos/listar", ...)
async def listar_alunos(payload: FiltroAlunos) -> dict:
    ...

# Rota directa (sem LLM, chamada tradicional)
@app.post("/alunos/listar")
async def api_listar_alunos(payload: FiltroAlunos):
    return await listar_alunos(payload)
```

Agora o endpoint aceita ambos:

```bash
# Via linguagem natural
curl -X POST http://localhost:8000/intent \
  -d '{"prompt": "lista alunos do 2 ano de informatica"}'

# Via payload estruturado (tradicional)
curl -X POST http://localhost:8000/alunos/listar \
  -d '{"curso_id": 1, "ano_curricular": 2}'
```

### Middleware Transparente

O `IntentMiddleware` tambem intercepta requests a qualquer endpoint que contenham
um campo `"prompt"`. Isto significa que pode enviar:

```bash
# Isto tambem funciona — o middleware intercepta e resolve
curl -X POST http://localhost:8000/alunos/listar \
  -d '{"prompt": "alunos do 2 ano"}'
```

O middleware resolve o intent, reescreve o path e payload, e encaminha para o
endpoint correcto.

---

## Confirmacao de Operacoes

Endpoints com `requires_confirmation=True` nao executam imediatamente.
O fluxo e em dois passos:

### Passo 1: Enviar o prompt

```bash
curl -X POST http://localhost:8000/intent \
  -d '{"prompt": "gera turmas para informatica 2025/26"}'
```

Resposta (pede confirmacao):

```json
{
    "success": true,
    "resolution": {
        "endpoint": "/turmas/gerar",
        "payload": {"ano_lectivo": "2025/26", "curso_id": 1, "capacidade": 40},
        "confidence": 0.92
    },
    "confirmation_required": true,
    "confirmation_message": "Criar turmas para curso 1 em 2025/26. Confirmas?"
}
```

### Passo 2: Confirmar

```bash
curl -X POST http://localhost:8000/intent \
  -d '{"prompt": "gera turmas para informatica 2025/26", "confirmed": true}'
```

Agora sim, executa e devolve o resultado.

### Templates de Confirmacao

O `confirmation_template` suporta placeholders do payload:

```python
IntentContext(
    requires_confirmation=True,
    confirmation_template="Vou matricular alunos no ano {ano_lectivo} para o curso {curso_id}. Confirmas?",
)
```

Se nao definir template, o intentful gera uma mensagem generica com a descricao
do endpoint e o impacto estimado pelo LLM.

---

## Dry-Run

O modo dry-run simula a resolucao sem executar nada. Util para:
- Testar se o LLM resolve correctamente
- Mostrar ao utilizador o que vai acontecer antes de confirmar
- Debug

```bash
curl -X POST http://localhost:8000/intent \
  -d '{"prompt": "matricula todos os alunos em 2025/26", "dry_run": true}'
```

Resposta:

```json
{
    "success": true,
    "resolution": {
        "endpoint": "/matriculas/auto",
        "method": "POST",
        "payload": {"ano_lectivo": "2025/26", "curso_id": null},
        "confidence": 0.90,
        "estimated_impact": "Alunos activos serao matriculados automaticamente.",
        "reasoning": "O prompt pede matricula automatica de todos os alunos."
    },
    "confirmation_required": true,
    "confirmation_message": "Matricular alunos em 2025/26. Confirmas?",
    "result": null
}
```

O campo `result` e `null` porque nada foi executado.

---

## Audit Trail

Com `audit_trail=True` (default), todas as operacoes via intent sao registadas.

Cada resposta inclui um `audit_id`:

```json
{
    "success": true,
    "result": {...},
    "audit_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

### O que e registado

- ID unico (UUID)
- Timestamp (UTC)
- ID do utilizador (se fornecido)
- Prompt original
- Resolucao completa do LLM (endpoint, payload, confianca)
- Se foi confirmado
- Se foi executado
- Resultado ou erro

### Aceder ao Auditor programaticamente

```python
# O auditor esta disponivel no router
auditor = router.auditor

# Buscar por ID
entry = auditor.get("f47ac10b-...")

# Listar ultimas 50 operacoes de um utilizador
entries = auditor.list_entries(user_id="user123", limit=50)

# Limpar
auditor.clear()
```

**Nota:** A implementacao actual armazena em memoria. Os dados perdem-se ao reiniciar
o servidor. Para producao, implemente persistencia no `Auditor`.

---

## Exemplos Completos

### App Minima

```python
# app.py — App minima com intentful
# Path: app.py

from fastapi import FastAPI
from pydantic import BaseModel, Field

from intentful import intent, IntentContext
from intentful.integrations.fastapi import IntentRouter, setup_intentful

app = FastAPI()

router = IntentRouter(ai_backend="openai", language="pt")


class SaudacaoSchema(BaseModel):
    nome: str = Field(..., description="Nome da pessoa a cumprimentar")


@router.post("/saudacao")
@intent(
    description="Cumprimentar uma pessoa pelo nome",
    context=IntentContext(
        rules=["Usar saudacao formal em portugues"],
        allowed_operations=["READ"],
    ),
    path="/saudacao",
)
async def saudacao(payload: SaudacaoSchema) -> dict:
    return {"mensagem": f"Bom dia, {payload.nome}!"}


setup_intentful(app, router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
```

Testar:

```bash
# Linguagem natural
curl -X POST http://localhost:8000/intent \
  -d '{"prompt": "cumprimenta o Joao"}'

# Estruturado
curl -X POST http://localhost:8000/saudacao \
  -d '{"nome": "Joao"}'
```

### App com Ollama (Sem API Key)

```python
# app_local.py — App com modelo local via Ollama
# Path: app_local.py

from fastapi import FastAPI
from pydantic import BaseModel, Field

from intentful import intent, IntentContext
from intentful.backends.local import OllamaBackend
from intentful.integrations.fastapi import IntentRouter, setup_intentful

app = FastAPI()

backend = OllamaBackend(model="llama3.1:8b")
router = IntentRouter(ai_backend=backend, language="pt")


class ProdutoQuery(BaseModel):
    categoria: str | None = Field(default=None, description="Categoria do produto")
    preco_max: float | None = Field(default=None, description="Preco maximo")


@router.post("/produtos/listar")
@intent(
    description="Listar produtos com filtro por categoria ou preco",
    context=IntentContext(
        rules=["Sem filtros retorna todos os produtos"],
        allowed_operations=["READ"],
        examples=[
            "mostra produtos de electronica",
            "produtos abaixo de 50 euros",
        ],
    ),
    path="/produtos/listar",
)
async def listar_produtos(payload: ProdutoQuery) -> dict:
    return {"produtos": []}


setup_intentful(app, router)
```

### App com Multiplos Endpoints e Confirmacao

```python
# app_completa.py — App com CRUD completo
# Path: app_completa.py

from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from intentful import intent, IntentContext
from intentful.backends.openai import OpenAIBackend
from intentful.integrations.fastapi import IntentRouter, setup_intentful


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializar base de dados, etc.
    yield


app = FastAPI(lifespan=lifespan)

backend = OpenAIBackend(model="gpt-4o-mini")
router = IntentRouter(
    ai_backend=backend,
    language=["pt", "en"],
    confidence_threshold=0.6,
)


# --- READ ---

class FiltroClientes(BaseModel):
    nome: str | None = Field(default=None, description="Filtrar por nome")
    cidade: str | None = Field(default=None, description="Filtrar por cidade")


@router.post("/clientes/listar")
@intent(
    description="Listar clientes com filtro opcional por nome ou cidade",
    context=IntentContext(
        rules=["Retorna clientes activos ordenados por nome"],
        allowed_operations=["READ"],
        examples=["mostra clientes de Lisboa", "lista todos os clientes"],
    ),
    path="/clientes/listar",
    tags=["clientes"],
)
async def listar_clientes(payload: FiltroClientes) -> dict:
    return {"clientes": []}


# --- CREATE com confirmacao ---

class NovoCliente(BaseModel):
    nome: str = Field(..., description="Nome completo do cliente")
    email: str = Field(..., description="Email do cliente")
    cidade: str = Field(default="Lisboa", description="Cidade")


@router.post("/clientes/criar")
@intent(
    description="Registar um novo cliente no sistema",
    context=IntentContext(
        rules=[
            "Email deve ser unico no sistema",
            "Nome e obrigatorio",
        ],
        allowed_operations=["CREATE"],
        requires_confirmation=True,
        confirmation_template="Criar cliente {nome} ({email}) em {cidade}. Confirmas?",
        examples=["regista o cliente Maria com email maria@email.pt"],
    ),
    path="/clientes/criar",
    tags=["clientes"],
)
async def criar_cliente(payload: NovoCliente) -> dict:
    return {"mensagem": f"Cliente {payload.nome} criado"}


# --- DELETE com confirmacao ---

class RemoveCliente(BaseModel):
    cliente_id: int = Field(..., description="ID do cliente a remover")


@router.post("/clientes/remover")
@intent(
    description="Remover um cliente do sistema (soft delete)",
    context=IntentContext(
        rules=[
            "Nao remove fisicamente, marca como inactivo",
            "So remove se o cliente nao tiver dividas pendentes",
        ],
        allowed_operations=["DELETE"],
        requires_confirmation=True,
        confirmation_template="Remover cliente {cliente_id}. Esta accao marca o cliente como inactivo. Confirmas?",
    ),
    path="/clientes/remover",
    tags=["clientes"],
)
async def remover_cliente(payload: RemoveCliente) -> dict:
    return {"mensagem": f"Cliente {payload.cliente_id} marcado como inactivo"}


setup_intentful(app, router)
```

### Integrar com Frontend (JavaScript)

```javascript
// Enviar prompt via fetch
async function enviarPrompt(prompt) {
    const response = await fetch("/intent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            prompt: prompt,
            language: "pt",
        }),
    });

    const data = await response.json();

    if (data.confirmation_required) {
        // Mostrar mensagem de confirmacao ao utilizador
        const confirma = confirm(data.confirmation_message);
        if (confirma) {
            // Re-enviar com confirmed: true
            return enviarConfirmado(prompt);
        }
        return null;
    }

    return data.result;
}

async function enviarConfirmado(prompt) {
    const response = await fetch("/intent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            prompt: prompt,
            confirmed: true,
        }),
    });
    return (await response.json()).result;
}
```

---

## Resolucao de Problemas

### "Confianca insuficiente" (422)

O LLM nao conseguiu mapear o prompt com confianca suficiente.

**Solucoes:**
- Reformule o prompt de forma mais clara
- Reduza o `confidence_threshold` (ex: `0.5` em vez de `0.7`)
- Adicione `examples` ao `IntentContext` do endpoint
- Melhore a `description` do endpoint

### "Endpoint nao encontrado no registry" (404)

O LLM resolveu para um endpoint que nao esta registado.

**Solucoes:**
- Verifique se o `path` no `@intent` corresponde exactamente ao path do `@router.post()`
- Use `path="/meu/endpoint"` explicitamente no `@intent`

### JSON invalido do LLM

Modelos pequenos (< 3B parametros) podem gerar JSON invalido.

**Solucoes:**
- Use um modelo maior (`llama3.1:8b+`, `gpt-4o-mini`, Claude)
- O `OllamaBackend` ja usa `format: "json"` para forcar output JSON

### Payload com campos null

O LLM pode devolver `null` para campos opcionais.

**Solucoes:**
- Use `Field(default=None)` nos campos opcionais do schema Pydantic
- O resolver ja normaliza `payload: null` para `{}`

### Operacao nao permitida (422)

O validator rejeita porque a operacao implicita do metodo HTTP nao esta em `allowed_operations`.

**Solucoes:**
- Adicione a operacao correcta: `allowed_operations=["CREATE", "READ"]`
- Endpoints de listagem que usam POST precisam de `"READ"` nas operacoes permitidas
