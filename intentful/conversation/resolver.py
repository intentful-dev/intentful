# intentful/conversation/resolver.py — Resolver conversacional multi-turno
# Path: intentful/conversation/resolver.py
from __future__ import annotations

import json
import logging
from typing import Any

from intentful.backends import LLMBackend
from intentful.conversation.fields import extract_field_specs, identify_missing_fields
from intentful.conversation.session import ConversationSession, FieldSpec
from intentful.core.registry import IntentRegistry, get_registry
from intentful.core.schemas import IntentRequest, IntentResolution
from intentful.routing.resolver import LLMResolver

logger = logging.getLogger("intentful.conversation")


FIELD_EXTRACTION_PROMPT = """You are a data extraction assistant.
The user is filling in a form field by field via conversation.

Current field to extract:
- Name: {field_name}
- Type: {field_type}
- Description: {field_description}

The user's answer is inside <user_answer> tags. Extract the value for this field.
If the answer is invalid or unclear, set "valid" to false and explain in "error".

Respond ONLY with valid JSON:
{{"value": <extracted_value>, "valid": true}}
or
{{"value": null, "valid": false, "error": "explanation"}}
"""


QUESTION_GENERATION_PROMPT = """You are a friendly assistant helping a user fill in form fields.
Generate a short, natural question in {language} to ask for the following field:

- Field name: {field_name}
- Type: {field_type}
- Description: {field_description}

Context: The user wants to {endpoint_description}.
Fields already collected: {collected_fields}

Respond with ONLY the question text, no JSON, no formatting.
"""


INITIAL_EXTRACTION_PROMPT = """You are a data extraction assistant.
The user sent a prompt to trigger the endpoint: {endpoint_description}

Available fields to extract:
{fields_json}

The user's prompt is inside <user_prompt> tags. Extract any field values already present in the prompt.
Only extract values you are confident about. Do NOT guess or fabricate values.

Respond ONLY with valid JSON — a dict of field_name: value for fields found in the prompt.
If no fields can be extracted, respond with {{}}.

<user_prompt>{user_prompt}</user_prompt>
"""


class ConversationalResolver:
    """Resolver que guia o utilizador campo a campo num fluxo conversacional."""

    def __init__(
        self,
        backend: LLMBackend,
        registry: IntentRegistry | None = None,
    ) -> None:
        self.backend = backend
        self.registry = registry or get_registry()
        self._llm_resolver = LLMResolver(backend)

    async def start_session(
        self,
        prompt: str,
        language: str = "pt",
    ) -> ConversationSession:
        """Primeiro turno: resolve endpoint, extrai campos iniciais, identifica pendentes."""
        session = ConversationSession(language=language)
        session.add_turn("user", prompt)

        # 1. Resolver endpoint via LLMResolver existente
        request = IntentRequest(prompt=prompt, language=language)
        resolution: IntentResolution = await self._llm_resolver.resolve(
            request, self.registry
        )

        entry = self.registry.get(resolution.method, resolution.endpoint)
        if entry is None or resolution.confidence < 0.5:
            session.status = "expired"
            session.add_turn(
                "assistant",
                "Nao foi possivel identificar a operacao pretendida. Tente reformular.",
            )
            return session

        session.endpoint_path = resolution.endpoint
        session.method = resolution.method

        # 2. Extrair campos do modelo Pydantic
        if entry.payload_model is not None:
            all_specs = extract_field_specs(entry.payload_model)

            # 3. Extrair campos ja presentes no prompt inicial
            initial_values = await self._extract_initial_fields(
                prompt, entry.description, all_specs
            )
            session.collected_fields.update(initial_values)

            # 4. Identificar campos pendentes (obrigatorios nao preenchidos)
            missing = identify_missing_fields(all_specs, session.collected_fields)
            session.pending_fields = missing

            if not missing:
                session.status = "ready"
                session.add_turn("assistant", "Todos os campos foram preenchidos.")
            else:
                session.status = "collecting"
                question = await self._generate_question(
                    missing[0], entry.description, session
                )
                session.add_turn("assistant", question)
        else:
            # Sem modelo Pydantic — nada a recolher
            session.status = "ready"
            session.collected_fields = resolution.payload or {}

        return session

    async def continue_session(
        self,
        session: ConversationSession,
        user_input: str,
    ) -> ConversationSession:
        """Turnos seguintes: extrai valor do campo actual e avanca."""
        if session.is_expired:
            session.status = "expired"
            return session

        if session.status != "collecting":
            return session

        session.add_turn("user", user_input)
        current = session.current_field
        if current is None:
            session.status = "ready"
            return session

        # Extrair valor do input do utilizador
        extracted = await self._extract_field_value(current, user_input)

        if extracted is not None and extracted.get("valid", False):
            session.collected_fields[current.name] = extracted["value"]
            session.advance_field()

            if session.status == "ready":
                session.add_turn("assistant", "Todos os campos foram preenchidos.")
            else:
                next_field = session.current_field
                if next_field:
                    entry = self.registry.get(session.method, session.endpoint_path)
                    desc = entry.description if entry else ""
                    question = await self._generate_question(next_field, desc, session)
                    session.add_turn("assistant", question)
        else:
            # Valor invalido — pedir novamente
            error_msg = (extracted or {}).get("error", "Valor nao reconhecido.")
            desc = current.description or current.name
            retry_msg = f"{error_msg} Por favor, indique novamente: {desc}"
            session.add_turn("assistant", retry_msg)

        return session

    async def _extract_initial_fields(
        self,
        prompt: str,
        endpoint_description: str,
        specs: list[FieldSpec],
    ) -> dict[str, Any]:
        """Extrai campos ja presentes no prompt inicial."""
        fields_info = [
            {"name": s.name, "type": s.type_str, "description": s.description}
            for s in specs
            if s.required
        ]
        system_prompt = INITIAL_EXTRACTION_PROMPT.format(
            endpoint_description=endpoint_description,
            fields_json=json.dumps(fields_info, ensure_ascii=False),
            user_prompt=prompt,
        )

        try:
            raw = await self.backend.complete("You are a data extraction assistant.", system_prompt)
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            logger.warning("Falha ao extrair campos iniciais do prompt")

        return {}

    async def _extract_field_value(
        self,
        field: FieldSpec,
        user_input: str,
    ) -> dict[str, Any] | None:
        """Usa o LLM para extrair e validar o valor de um campo."""
        system = FIELD_EXTRACTION_PROMPT.format(
            field_name=field.name,
            field_type=field.type_str,
            field_description=field.description or field.name,
        )
        prompt = f"<user_answer>{user_input}</user_answer>"

        try:
            raw = await self.backend.complete(system, prompt)
            return json.loads(raw)
        except Exception:
            logger.warning("Falha ao extrair valor para campo '%s'", field.name)
            return None

    async def _generate_question(
        self,
        field: FieldSpec,
        endpoint_description: str,
        session: ConversationSession,
    ) -> str:
        """Gera uma pergunta natural para recolher um campo."""
        system = QUESTION_GENERATION_PROMPT.format(
            language=session.language,
            field_name=field.name,
            field_type=field.type_str,
            field_description=field.description or field.name,
            endpoint_description=endpoint_description,
            collected_fields=json.dumps(session.collected_fields, ensure_ascii=False),
        )

        try:
            return await self.backend.complete(
                "You are a friendly assistant.", system
            )
        except Exception:
            # Fallback: pergunta simples
            desc = field.description or field.name
            return f"Qual o valor para '{desc}'?"
