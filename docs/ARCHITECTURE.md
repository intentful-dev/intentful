# intentful — Documentacao Tecnica

<!-- Path: docs/ARCHITECTURE.md -->

> Build APIs that understand intent, not just requests.

`intentful` e uma biblioteca Python que permite anotar endpoints FastAPI com contexto semantico,
tornando cada endpoint naturalmente accionavel via linguagem natural — sem chatbots, agentes
externos, ou perda de controlo.

**Versao:** 0.1.0
**Licenca:** MIT
**Python:** >= 3.10
**Framework:** FastAPI

---

## Indice

1. [Visao Geral](#visao-geral)
2. [Arquitectura](#arquitectura)
3. [Modulos](#modulos)
   - [core — Nucleo da Biblioteca](#core)
   - [backends — Integracao com LLMs](#backends)
   - [routing — Resolucao de Intents](#routing)
   - [execution — Execucao e Auditoria](#execution)
   - [integrations — Integracoes com Frameworks](#integrations)
4. [Fluxo de Dados](#fluxo-de-dados)
5. [Schemas e Modelos](#schemas-e-modelos)
6. [Configuracao](#configuracao)

---

## Visao Geral

O `intentful` segue dois principios fundamentais:

- **Backend-first** — o developer define as fronteiras, o LLM opera dentro delas
- **Progressive enhancement** — o mesmo endpoint funciona com payloads estruturados
  ou linguagem natural, sem quebrar nada

A biblioteca transforma endpoints tradicionais em endpoints "inteligentes" atraves de:

1. Um **decorator** (`@intent`) que anota endpoints com contexto semantico
2. Um **registry** global que armazena todos os endpoints anotados
3. Um **resolver** que usa um LLM para mapear prompts em linguagem natural para endpoints + payloads
4. Um **validator** que verifica se o payload gerado respeita as regras do endpoint
5. Um **sistema de confirmacao** para operacoes de alto impacto
6. Um **auditor** que regista todas as operacoes

---

## Arquitectura

```
intentful/
├── __init__.py                    # API publica: intent, IntentContext, IntentRegistry
├── core/                          # Nucleo — decorators, schemas, registry
│   ├── __init__.py
│   ├── context.py                 # IntentContext — fronteiras semanticas
│   ├── decorator.py               # @intent — anotacao de endpoints
│   ├── registry.py                # IntentRegistry — registo global singleton
│   └── schemas.py                 # IntentRequest, IntentResolution, IntentResponse
├── backends/                      # Backends LLM
│   ├── __init__.py                # LLMBackend — classe base abstracta
│   ├── anthropic.py               # AnthropicBackend (Claude)
│   ├── openai.py                  # OpenAIBackend (GPT)
│   └── local.py                   # OllamaBackend (modelos locais)
├── routing/                       # Resolucao e validacao de intents
│   ├── __init__.py
│   ├── resolver.py                # LLMResolver — mapeia prompt -> endpoint + payload
│   ├── validator.py               # Valida payload contra regras do endpoint
│   └── middleware.py              # IntentMiddleware — intercepta requests com "prompt"
├── execution/                     # Execucao, auditoria, confirmacao
│   ├── __init__.py
│   ├── auditor.py                 # Auditor — audit trail em memoria
│   ├── confirmer.py               # Logica de confirmacao
│   └── rollback.py                # Placeholder para operacoes reversiveis
└── integrations/                  # Integracoes com frameworks
    ├── __init__.py
    ├── fastapi.py                 # IntentRouter + setup_intentful()
    ├── sqlalchemy.py              # Placeholder
    └── oracle.py                  # Placeholder
```

### Padroes de Design Utilizados

| Padrao | Onde | Descricao |
|--------|------|-----------|
| **Decorator** | `core/decorator.py` | `@intent` anota endpoints sem modificar a logica |
| **Singleton** | `core/registry.py` | Registry global unico para toda a aplicacao |
| **Strategy** | `backends/` | Interface abstracta `LLMBackend` com multiplas implementacoes |
| **Middleware** | `routing/middleware.py` | Interceta requests transparentemente |
| **Factory** | `integrations/fastapi.py` | `_create_backend()` cria backends por nome |

---

## Modulos

### core

O nucleo da biblioteca. Define os conceitos fundamentais.

#### `context.py` — IntentContext

Define as fronteiras semanticas de um endpoint. O `IntentContext` diz ao resolver
o que o endpoint pode fazer e quais regras se aplicam.

```python
class IntentContext(BaseModel):
    rules: list[str]                    # Regras de negocio para o LLM considerar
    allowed_operations: list[str]       # "CREATE", "READ", "UPDATE", "DELETE"
    requires_confirmation: bool         # Se True, pede confirmacao ao utilizador
    confirmation_template: str | None   # Template com {placeholders} do payload
    examples: list[str]                 # Exemplos de prompts que devem resolver aqui
    tags: list[str]                     # Tags para agrupar endpoints
```

**Tipos de operacao disponiveis:** `CREATE`, `READ`, `UPDATE`, `DELETE`

O valor por defeito de `allowed_operations` e `["READ"]` — endpoints sao read-only
por defeito, o que obriga o developer a autorizar explicitamente operacoes de escrita.

#### `decorator.py` — @intent

O decorator `@intent` e o ponto de entrada principal da biblioteca. Anota um endpoint
FastAPI com contexto semantico e regista-o automaticamente no `IntentRegistry`.

```python
def intent(
    description: str,              # Descricao do que o endpoint faz
    context: IntentContext | None,  # Contexto semantico (regras, permissoes)
    method: str = "POST",          # Metodo HTTP
    path: str | None = None,       # Path explicito (ou inferido do nome da funcao)
    tags: list[str] | None = None, # Tags de agrupamento
) -> Callable
```

**Funcionamento interno:**

1. Extrai o JSON Schema do modelo Pydantic do handler (primeiro parametro)
2. Cria um `IntentEntry` com toda a metadata
3. Regista a entry no `IntentRegistry` global
4. Devolve um wrapper que preserva o comportamento original do handler

**Extraccao automatica de schema:** A funcao `_extract_payload_info()` inspecciona
a assinatura do handler e, se encontrar um parametro com tipo `BaseModel`, extrai
o JSON Schema automaticamente. Funciona com `from __future__ import annotations`.

#### `registry.py` — IntentRegistry

Registo singleton que armazena todos os endpoints anotados com `@intent`.
E usado pelo resolver para saber quais endpoints estao disponiveis.

```python
class IntentRegistry:
    def register(entry: IntentEntry) -> None      # Regista um endpoint
    def get(method, path) -> IntentEntry | None    # Busca por metodo + path
    def all_entries() -> list[IntentEntry]          # Lista todos
    def filter_by_tags(tags) -> list[IntentEntry]   # Filtra por tags
    def to_prompt_context() -> list[dict]           # Serializa para enviar ao LLM
```

Cada entry e indexada pela chave `"METHOD:/path"` (ex: `"POST:/turmas/gerar"`).

O metodo `to_prompt_context()` serializa todas as entries para um formato que
o LLM consegue interpretar — inclui path, descricao, regras, operacoes permitidas
e o JSON Schema do payload esperado.

#### `schemas.py` — Modelos de Dados

Tres modelos Pydantic que definem a comunicacao entre componentes:

**IntentRequest** — o que o utilizador envia:

| Campo | Tipo | Default | Descricao |
|-------|------|---------|-----------|
| `prompt` | `str` | obrigatorio | Prompt em linguagem natural |
| `dry_run` | `bool` | `False` | Se True, simula sem executar |
| `language` | `str` | `"pt"` | Lingua do prompt (ISO 639-1) |
| `metadata` | `dict` | `{}` | Metadata adicional |

**IntentResolution** — o que o LLM devolve (apos parsing):

| Campo | Tipo | Default | Descricao |
|-------|------|---------|-----------|
| `endpoint` | `str` | obrigatorio | Path do endpoint resolvido |
| `method` | `str` | `"POST"` | Metodo HTTP |
| `payload` | `dict | None` | `{}` | Payload gerado pelo LLM |
| `confidence` | `float` | obrigatorio | Confianca na resolucao (0.0 a 1.0) |
| `estimated_impact` | `str | None` | `None` | Descricao do impacto |
| `reasoning` | `str | None` | `None` | Raciocinio do LLM |

**IntentResponse** — o que o sistema devolve ao utilizador:

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `success` | `bool` | Se a operacao foi bem sucedida |
| `resolution` | `IntentResolution | None` | A resolucao do LLM |
| `confirmation_required` | `bool` | Se precisa de confirmacao |
| `confirmation_message` | `str | None` | Mensagem de confirmacao |
| `result` | `Any` | Resultado da execucao do endpoint |
| `error` | `str | None` | Mensagem de erro |
| `audit_id` | `str | None` | ID do registo de auditoria |

---

### backends

Implementacoes de backends LLM. Todos implementam a interface `LLMBackend`.

#### `__init__.py` — LLMBackend (Interface Base)

```python
class LLMBackend(ABC):
    async def complete(self, system: str, prompt: str) -> str
```

Um unico metodo abstracto: recebe um system prompt e um user prompt, devolve
a resposta do LLM como string.

#### `anthropic.py` — AnthropicBackend

Usa a API da Anthropic (Claude) via o SDK oficial `anthropic`.

| Parametro | Default | Descricao |
|-----------|---------|-----------|
| `api_key` | `None` (usa env `ANTHROPIC_API_KEY`) | Chave da API |
| `model` | `"claude-sonnet-4-20250514"` | Modelo a usar |
| `max_tokens` | `1024` | Tokens maximos na resposta |

**Dependencia opcional:** `pip install intentful[anthropic]`

#### `openai.py` — OpenAIBackend

Usa a API da OpenAI (GPT) via o SDK oficial `openai`.

| Parametro | Default | Descricao |
|-----------|---------|-----------|
| `api_key` | `None` (usa env `OPENAI_API_KEY`) | Chave da API |
| `model` | `"gpt-4o"` | Modelo a usar |
| `max_tokens` | `1024` | Tokens maximos na resposta |

**Dependencia opcional:** `pip install intentful[openai]`

#### `local.py` — OllamaBackend

Usa modelos locais via Ollama. Nao requer chave de API.

| Parametro | Default | Descricao |
|-----------|---------|-----------|
| `model` | `"llama3"` | Nome do modelo Ollama |
| `base_url` | `"http://localhost:11434"` | URL do servidor Ollama |

Usa a API `/api/chat` do Ollama com `format: "json"` para forcar output JSON valido.
Timeout de 120 segundos para acomodar modelos mais lentos.

**Sem dependencias adicionais** — usa `httpx` (ja incluido no intentful).

**Nota:** Modelos pequenos (< 3B parametros) podem ter dificuldade em seguir o formato
JSON esperado. Recomenda-se pelo menos 7B parametros para resultados fiaveis.

---

### routing

Resolucao de intents: transforma prompts em chamadas estruturadas.

#### `resolver.py` — LLMResolver

O resolver e o componente central que converte linguagem natural em chamadas API.

**System Prompt enviado ao LLM:**

O resolver envia ao LLM:
- Um system prompt com regras (responder so em JSON, usar endpoints da lista, etc.)
- A lista de todos os endpoints registados com as suas descricoes, regras e schemas
- O prompt do utilizador com indicacao da lingua

**Formato esperado da resposta do LLM:**

```json
{
    "endpoint": "/path/to/endpoint",
    "method": "POST",
    "payload": {},
    "confidence": 0.95,
    "estimated_impact": "descricao do impacto",
    "reasoning": "porque este endpoint foi escolhido"
}
```

**Tratamento de erros:**

- Erro de conexao ao LLM: `RuntimeError` com mensagem descritiva
- Resposta vazia do LLM: `RuntimeError`
- JSON invalido: `RuntimeError` com os primeiros 200 caracteres da resposta
- `payload: null`: normalizado automaticamente para `{}`

#### `validator.py` — Validacao

Valida se a resolucao do LLM respeita as regras definidas no `IntentContext`.

**Verificacoes realizadas:**

1. **Operacoes permitidas** — verifica se pelo menos uma operacao implicita do metodo
   HTTP esta dentro das `allowed_operations` do endpoint
2. **Schema do payload** — se o endpoint tem um modelo Pydantic, valida o payload
   gerado contra esse modelo

**Mapeamento metodo HTTP -> operacoes:**

| Metodo | Operacoes Implicitas |
|--------|---------------------|
| GET | READ |
| POST | CREATE, READ |
| PUT | UPDATE |
| PATCH | UPDATE |
| DELETE | DELETE |

POST mapeia para CREATE e READ porque e comum usar POST para endpoints de leitura
que aceitam payloads de filtro (ex: `/alunos/listar`).

#### `middleware.py` — IntentMiddleware

Middleware Starlette/FastAPI que intercepta transparentemente qualquer request
que contenha um campo `"prompt"` no body.

**Comportamento:**

1. Se o request nao e POST/PUT/PATCH → passa normalmente
2. Se o path termina em `/intent` → passa normalmente (tratado pelo endpoint dedicado)
3. Se o body nao contem `"prompt"` → passa normalmente
4. Se contem `"prompt"`:
   - Resolve o intent via LLM
   - Verifica confianca (abaixo do threshold = 422)
   - Verifica se o endpoint existe no registry
   - Se `dry_run: true` → devolve a resolucao sem executar
   - Se `requires_confirmation` e nao `confirmed` → pede confirmacao
   - Caso contrario → reescreve o request (path + body) e passa adiante

Isto permite que **qualquer endpoint** aceite linguagem natural sem alteracoes de codigo.

---

### execution

Camada de execucao: auditoria, confirmacao, e rollback.

#### `auditor.py` — Audit Trail

Regista todas as operacoes executadas via intent para compliance e debug.

```python
class AuditEntry(BaseModel):
    id: str              # UUID gerado automaticamente
    timestamp: datetime  # UTC
    user_id: str | None  # Identificador do utilizador
    prompt: str          # Prompt original
    resolution: IntentResolution  # O que o LLM resolveu
    confirmed: bool      # Se foi confirmado
    executed: bool       # Se foi executado
    result: Any          # Resultado da execucao
    error: str | None    # Erro, se ocorreu
```

**Implementacao actual:** em memoria (lista Python). Adequada para desenvolvimento
e demos. Para producao, deve ser estendida com persistencia.

O `Auditor` suporta:
- `record(entry)` — regista e devolve o ID
- `get(audit_id)` — busca por ID
- `list_entries(user_id, limit)` — lista com filtro opcional por utilizador

#### `confirmer.py` — Confirmacao

Gera mensagens de confirmacao para operacoes de alto impacto.

Se o endpoint tem `confirmation_template`, usa-o com `str.format(**payload)`.
Caso contrario, gera uma mensagem generica com a descricao do endpoint e o impacto estimado.

#### `rollback.py` — Rollback (Placeholder)

Reservado para implementacao futura de operacoes reversiveis.

---

### integrations

Integracoes com frameworks web.

#### `fastapi.py` — IntentRouter + setup_intentful()

**IntentRouter** — extensao do `APIRouter` do FastAPI que adiciona:

1. Um endpoint universal `POST /intent` que recebe prompts e resolve automaticamente
2. Configuracao centralizada de backend, lingua, threshold e auditoria

```python
class IntentRouter(APIRouter):
    def __init__(
        self,
        ai_backend: str | LLMBackend,   # "anthropic", "openai", "ollama", ou instancia
        language: str | list[str],       # Lingua(s) aceites
        audit_trail: bool = True,        # Activar audit trail
        confidence_threshold: float = 0.7,  # Confianca minima (0.0 a 1.0)
    )
```

**Fluxo do endpoint `/intent`:**

1. Recebe `{"prompt": "...", "dry_run": false, "confirmed": false}`
2. Resolve via LLM
3. Valida confianca (< threshold → 422)
4. Valida endpoint existe no registry (nao → 404)
5. Valida payload contra regras (falha → 422)
6. Se `dry_run` → devolve resolucao sem executar
7. Se `requires_confirmation` e nao `confirmed` → devolve mensagem de confirmacao
8. Executa o handler, regista auditoria, devolve resultado

**setup_intentful()** — funcao de conveniencia que configura tudo:

```python
def setup_intentful(app: FastAPI, router: IntentRouter) -> None
```

Adiciona o `IntentMiddleware` e inclui o router na app. Deve ser chamada uma unica vez.

**Backends disponiveis por nome:**
- `"anthropic"` — AnthropicBackend (Claude)
- `"openai"` — OpenAIBackend (GPT)
- `"ollama"` — OllamaBackend (modelos locais)

---

## Fluxo de Dados

```
Utilizador envia prompt
        │
        ▼
┌─────────────────────────────┐
│  IntentMiddleware            │  Intercepta requests com campo "prompt"
│  OU endpoint POST /intent    │  Endpoint dedicado para resolucao
└──────────┬──────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  IntentRegistry               │  Lista de todos os endpoints @intent
│  .to_prompt_context()         │  Serializa para enviar ao LLM
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  LLMResolver                  │  Envia prompt + contexto ao backend
│  → LLMBackend.complete()      │  Anthropic / OpenAI / Ollama
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  JSON Response do LLM         │  { endpoint, payload, confidence, ... }
│  → json.loads() + validacao   │  Normaliza payload null → {}
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  Validator                    │  Verifica operacoes permitidas
│  validate_resolution()        │  Valida payload contra schema Pydantic
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  Confirmer (se necessario)    │  Pede confirmacao ao utilizador
│  build_confirmation_message() │  Usa template com placeholders
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  Handler Execution            │  Instancia Pydantic model e chama o handler
│  _call_handler()              │  Igual a uma chamada normal do FastAPI
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  Auditor                      │  Regista prompt, resolucao, resultado
│  AuditEntry                   │  UUID + timestamp + user_id
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  IntentResponse               │  Resposta final ao utilizador
│  { success, result, ... }     │  Inclui audit_id para rastreabilidade
└──────────────────────────────┘
```

---

## Configuracao

### Dependencias

**Obrigatorias:**
- `fastapi >= 0.100.0`
- `pydantic >= 2.0.0`
- `httpx >= 0.24.0`

**Opcionais (backends):**
- `anthropic >= 0.18.0` — para `AnthropicBackend`
- `openai >= 1.0.0` — para `OpenAIBackend`
- Ollama nao requer pacote adicional (usa `httpx`)

### Variaveis de Ambiente

| Variavel | Backend | Descricao |
|----------|---------|-----------|
| `ANTHROPIC_API_KEY` | Anthropic | Chave da API da Anthropic |
| `OPENAI_API_KEY` | OpenAI | Chave da API da OpenAI |
| `OLLAMA_URL` | Ollama | URL do servidor (default: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Ollama | Nome do modelo (default: `llama3`) |

### Instalacao

```bash
pip install intentful              # core
pip install intentful[anthropic]   # + Claude
pip install intentful[openai]      # + GPT
pip install intentful[all]         # todos os backends
pip install intentful[dev]         # + ferramentas de desenvolvimento
```
