# Plano `intentful` — Da Ideia à Biblioteca Open Source

---

## 1. Visão e Posicionamento

**Tagline:** *"Build APIs that understand intent, not just requests."*

**Definição em uma frase:**
> `intentful` é uma biblioteca Python que permite ao programador de backend anotar endpoints FastAPI com contexto semântico durante o desenvolvimento, tornando cada fluxo naturalmente accionável por linguagem natural — sem chatbots, sem agentes externos, sem perda de controlo.

**Filosofia central — dois princípios:**

- **Backend-first**: o programador define as fronteiras, o LLM opera dentro delas
- **Progressive enhancement**: o mesmo endpoint funciona com payload estruturado tradicional OU com prompt em linguagem natural — sem quebrar nada existente

---

## 2. Arquitectura Técnica

```
intentful/
├── core/
│   ├── decorator.py       # @intent — o coração da biblioteca
│   ├── context.py         # IntentContext — fronteiras semânticas
│   └── registry.py        # regista todos os endpoints anotados
├── routing/
│   ├── middleware.py      # intercepta requests com campo "prompt"
│   ├── resolver.py        # LLM mapeia prompt → endpoint + payload
│   └── validator.py       # valida payload gerado contra as regras
├── execution/
│   ├── confirmer.py       # lógica de confirmação para operações massivas
│   ├── auditor.py         # audit trail de todas as operações via prompt
│   └── rollback.py        # suporte a operações reversíveis
├── backends/
│   ├── anthropic.py       # Claude como motor de resolução
│   ├── openai.py          # GPT como alternativa
│   └── local.py           # modelos locais (Ollama, etc.)
└── integrations/
    ├── fastapi.py         # IntentRouter — extensão do APIRouter
    ├── sqlalchemy.py      # hints automáticos de schema
    └── oracle.py          # suporte específico Oracle (relevante pro SIAA)
```

---

## 3. A API da Biblioteca — Como o Programador a Usa

### Nível 1 — Decorator básico
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
            "Períodos válidos: 1º Semestre, 2º Semestre, Anual"
        ],
        allowed_operations=["CREATE", "READ"],
        requires_confirmation=True
    )
)
async def gerar_turmas(payload: GeraTurmasSchema, db=Depends(get_db)):
    # lógica normal — não muda nada aqui
    ...
```

### Nível 2 — IntentRouter (substituição directa do APIRouter)
```python
from intentful.integrations.fastapi import IntentRouter

router = IntentRouter(
    ai_backend="anthropic",
    language="pt",  # português como língua dos prompts
    audit_trail=True
)

# @router.post funciona exactamente igual ao FastAPI normal
# mas todos os endpoints ficam automaticamente registados no registry
```

### Nível 3 — Como o utilizador final interage (no frontend React)
```javascript
// Forma tradicional — continua a funcionar
await api.post('/turmas/gerar', {
  ano_lectivo: '2025/26',
  curso_id: 5,
  semestre: 1
})

// Forma nova — mesmo endpoint, via prompt
await api.post('/turmas/gerar', {
  prompt: "Cria turmas para todos os cursos de Engenharia em 2025/26"
})

// Ou através de um endpoint universal de intent
await api.post('/intent', {
  prompt: "Cria turmas para todos os cursos de Engenharia em 2025/26"
})
// O middleware resolve automaticamente para /turmas/gerar
```

---

## 4. O Fluxo Interno — O Que Acontece Quando Chega um Prompt

```
1. Request chega com campo "prompt"
        ↓
2. IntentMiddleware intercepta (antes de chegar ao endpoint)
        ↓
3. Resolver consulta o IntentRegistry
   (lista de todos os endpoints anotados com @intent)
        ↓
4. LLM recebe:
   - O prompt do utilizador
   - A lista de endpoints disponíveis e os seus contextos
   - As regras de negócio de cada um
   - O schema Pydantic esperado
        ↓
5. LLM devolve JSON estruturado:
   {
     "endpoint": "/turmas/gerar",
     "payload": {"ano_lectivo": "2025/26", "curso_id": 5},
     "confidence": 0.97,
     "estimated_impact": "47 turmas serão criadas"
   }
        ↓
6. Validator verifica:
   - Payload válido contra o schema Pydantic?
   - Operações dentro das allowed_operations?
   - requires_confirmation? → pausa e pergunta ao utilizador
        ↓
7. Se confirmado → chama o endpoint normalmente
   (como se fosse um POST estruturado tradicional)
        ↓
8. Auditor regista:
   - prompt original
   - payload gerado
   - utilizador
   - timestamp
   - resultado
```

---

## 5. Funcionalidades Diferenciadoras

### Confirmação inteligente
```python
# A biblioteca detecta automaticamente operações de alto impacto
@intent(
    description="Matricular alunos transitados",
    context=IntentContext(
        requires_confirmation=True,
        confirmation_template=(
            "Vou matricular {count} alunos no ano lectivo {ano_lectivo}. "
            "Esta operação afecta {cursos} cursos. Confirmas?"
        )
    )
)
```

### Audit trail nativo
```python
# Cada operação via prompt fica registada automaticamente
# Quem fez, o quê, quando, e qual era o prompt original
# Integra com o sistema de auditoria existente (Oracle audit tables)
```

### Modo simulação
```python
# O utilizador pode testar sem executar
await api.post('/intent', {
  "prompt": "Cria turmas para todos os cursos",
  "dry_run": True  # só mostra o que faria, não executa
})
```

### Multilíngue nativo
```python
IntentRouter(language=["pt", "en"])
# Aceita prompts em português e inglês
# Relevante para Angola: português é obrigatório
```

---

## 6. Roadmap de Desenvolvimento

### Fase 0 — Fundação *(2 semanas)*
- Setup do repositório GitHub (`intentful-py`)
- Estrutura base da biblioteca
- Testes unitários básicos

### Fase 1 — MVP *(1 mês)*
- `@intent` decorator funcional
- `IntentMiddleware` básico
- Backend Anthropic (Claude) para resolução
- Integração com FastAPI
- Testado no SIAA com 3 endpoints reais

### Fase 2 — Robustez *(1 mês)*
- Sistema de confirmação
- Audit trail
- Modo dry_run
- Suporte multilíngue (pt/en)
- Backend OpenAI como alternativa

### Fase 3 — Ecossistema *(2 meses)*
- Documentação completa (MkDocs)
- Exemplos práticos com SIAA como caso de uso
- Publicação no PyPI (`pip install intentful`)
- Package no GitHub com licença MIT

### Fase 4 — Académico + Comunidade *(paralelo às fases anteriores)*
- Paper IEEE baseado nos resultados do SIAA
- Proposta à comunidade FastAPI
- Blog post técnico em inglês

---

## 7. O Paper Académico

**Título proposto:**
> *"intentful: An Annotated Endpoint Architecture for Intent-Driven Information Systems"*

**Estrutura:**
1. Introdução — o problema das tarefas administrativas complexas em SIs
2. Trabalho relacionado — MCP, Semantic Router, LangChain tools (e porque diferem)
3. Arquitectura proposta — `@intent`, IntentContext, dual-mode endpoints
4. Implementação — a biblioteca `intentful`
5. Caso de estudo — SIAA/SIGES na FEUAN, Luanda
6. Avaliação — tempo de execução de tarefas antes/depois, erros, satisfação dos utilizadores
7. Conclusão e trabalho futuro

**Venue alvo:** IEEE ACCESS, ou ICEIS (International Conference on Enterprise Information Systems)

---

## 8. Identidade do Projecto

```
Nome:        intentful
PyPI:        pip install intentful
GitHub:      github.com/[teu-username]/intentful
Licença:     MIT
Linguagem:   Python 3.10+
Dependências core: fastapi, pydantic, anthropic (opcional), httpx
Tagline:     "Build APIs that understand intent, not just requests."
```

**README badge stack:**
```
[PyPI version] [Python 3.10+] [License: MIT] [FastAPI] [Tests]
```

---

## 9. Próximos Passos Imediatos

A ordem de execução mais eficiente:

```
Esta semana:
├── Criar repositório GitHub
├── Definir os schemas Pydantic base (IntentContext, IntentResult)
└── Implementar o @intent decorator básico (só registo, sem LLM ainda)

Próxima semana:
├── IntentMiddleware que intercepta requests com "prompt"
├── Resolver simples com Claude API
└── Primeiro teste real: endpoint /turmas/gerar do SIAA

Mês 1:
└── MVP funcional com 5 endpoints reais do SIAA documentados
```

---

Queres começar pelo repositório e a estrutura base do código?