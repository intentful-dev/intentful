# intentful/scanner/openapi.py — Parser de specs OpenAPI 3.x para auto-discovery de endpoints
# Path: intentful/scanner/openapi.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import yaml

from intentful.core.context import IntentContext, OperationType
from intentful.core.registry import IntentEntry


# Paths tipicamente internos que devem ser ignorados
_DEFAULT_EXCLUDE = {"/docs", "/redoc", "/openapi.json", "/swagger.json", "/health", "/healthz"}

# Mapeamento de método HTTP para operações semânticas
_METHOD_OPERATIONS: dict[str, list[OperationType]] = {
    "GET": ["READ"],
    "POST": ["CREATE", "READ"],
    "PUT": ["UPDATE"],
    "PATCH": ["UPDATE"],
    "DELETE": ["DELETE"],
}


def _noop_handler(**kwargs: Any) -> None:
    """Placeholder handler — no standalone mode, o HTTPExecutor faz a chamada real."""


class OpenAPIScanner:
    """Lê uma spec OpenAPI 3.x e gera IntentEntry[] para cada endpoint.

    Suporta:
    - Fetch via HTTP (url)
    - Leitura de ficheiro local (JSON ou YAML)
    - Filtragem por paths (exclude/include_only)
    - Inferência de IntentContext a partir do método HTTP e descrição

    Uso:
        scanner = OpenAPIScanner()
        entries = await scanner.scan("http://localhost:3000/openapi.json")
    """

    def __init__(
        self,
        *,
        exclude_paths: list[str] | None = None,
        include_only: list[str] | None = None,
        default_rules: list[str] | None = None,
    ) -> None:
        self._exclude = _DEFAULT_EXCLUDE | set(exclude_paths or [])
        self._include_only = set(include_only) if include_only else None
        self._default_rules = default_rules or []

    async def scan(self, source: str) -> list[IntentEntry]:
        """Escaneia uma spec OpenAPI e devolve lista de IntentEntry.

        Args:
            source: URL (http/https) ou path de ficheiro local (.json/.yaml/.yml)

        Returns:
            Lista de IntentEntry prontos para registar no IntentRegistry.
        """
        spec = await self._load_spec(source)
        return self._parse_spec(spec)

    async def _load_spec(self, source: str) -> dict[str, Any]:
        """Carrega a spec de uma URL ou ficheiro local."""
        if source.startswith(("http://", "https://")):
            return await self._fetch_remote(source)
        return self._read_local(source)

    async def _fetch_remote(self, url: str) -> dict[str, Any]:
        """Busca spec via HTTP."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "yaml" in content_type or "yml" in content_type:
                return yaml.safe_load(response.text)
            return response.json()

    def _read_local(self, path: str) -> dict[str, Any]:
        """Lê spec de ficheiro local."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Spec file not found: {path}")

        content = file_path.read_text(encoding="utf-8")
        if file_path.suffix in (".yaml", ".yml"):
            return yaml.safe_load(content)
        return json.loads(content)

    def _parse_spec(self, spec: dict[str, Any]) -> list[IntentEntry]:
        """Extrai IntentEntry[] dos paths da spec OpenAPI."""
        entries: list[IntentEntry] = []
        paths = spec.get("paths", {})
        components_schemas = spec.get("components", {}).get("schemas", {})

        for path, path_item in paths.items():
            if path in self._exclude:
                continue
            if self._include_only and path not in self._include_only:
                continue

            for method in ("get", "post", "put", "patch", "delete"):
                operation = path_item.get(method)
                if not operation:
                    continue

                entry = self._build_entry(
                    path=path,
                    method=method.upper(),
                    operation=operation,
                    components_schemas=components_schemas,
                )
                entries.append(entry)

        return entries

    def _build_entry(
        self,
        *,
        path: str,
        method: str,
        operation: dict[str, Any],
        components_schemas: dict[str, Any],
    ) -> IntentEntry:
        """Constrói um IntentEntry a partir de uma operação OpenAPI."""
        description = self._extract_description(operation, path, method)
        payload_schema = self._extract_payload_schema(operation, components_schemas)
        operations = _METHOD_OPERATIONS.get(method, ["READ"])

        # Extrair parâmetros de path/query como parte do schema
        param_schema = self._extract_parameters_schema(operation)
        if param_schema and payload_schema:
            # Merge params into payload schema
            payload_schema["properties"] = {
                **param_schema.get("properties", {}),
                **payload_schema.get("properties", {}),
            }
            # Merge required fields
            existing_required = set(payload_schema.get("required", []))
            param_required = set(param_schema.get("required", []))
            merged = sorted(existing_required | param_required)
            if merged:
                payload_schema["required"] = merged
        elif param_schema:
            payload_schema = param_schema

        context = IntentContext(
            allowed_operations=operations,
            rules=list(self._default_rules),
        )

        return IntentEntry(
            endpoint_path=path,
            method=method,
            description=description,
            context=context,
            handler=_noop_handler,
            payload_schema=payload_schema,
        )

    def _extract_description(
        self, operation: dict[str, Any], path: str, method: str
    ) -> str:
        """Extrai descrição da operação, com fallbacks."""
        # 1. summary
        if summary := operation.get("summary"):
            return summary

        # 2. description (primeira linha)
        if desc := operation.get("description"):
            first_line = desc.strip().split("\n")[0].strip()
            if first_line:
                return first_line

        # 3. operationId humanizado
        if op_id := operation.get("operationId"):
            return self._humanize_name(op_id)

        # 4. Fallback: "METHOD /path"
        return f"{method} {path}"

    def _extract_payload_schema(
        self,
        operation: dict[str, Any],
        components_schemas: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Extrai JSON Schema do request body."""
        request_body = operation.get("requestBody")
        if not request_body:
            return None

        content = request_body.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema")
        if not schema:
            return None

        # Resolver $ref se necessário
        return self._resolve_refs(schema, components_schemas)

    def _extract_parameters_schema(
        self, operation: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Converte parâmetros OpenAPI (path/query) num JSON Schema."""
        parameters = operation.get("parameters", [])
        if not parameters:
            return None

        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in parameters:
            name = param.get("name", "")
            param_in = param.get("in", "")
            if param_in not in ("path", "query"):
                continue

            param_schema = param.get("schema", {"type": "string"})
            if description := param.get("description"):
                param_schema["description"] = description

            properties[name] = param_schema
            if param.get("required", param_in == "path"):
                required.append(name)

        if not properties:
            return None

        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    def _resolve_refs(
        self, schema: dict[str, Any], components_schemas: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolve $ref recursivamente nos schemas."""
        if "$ref" in schema:
            ref_path = schema["$ref"]
            # Ex: "#/components/schemas/EventCreate"
            parts = ref_path.split("/")
            if len(parts) >= 4 and parts[1] == "components" and parts[2] == "schemas":
                schema_name = parts[3]
                resolved = components_schemas.get(schema_name, {})
                return self._resolve_refs(dict(resolved), components_schemas)
            return schema

        # Resolver refs dentro de properties
        if "properties" in schema:
            for prop_name, prop_schema in schema["properties"].items():
                schema["properties"][prop_name] = self._resolve_refs(
                    dict(prop_schema), components_schemas
                )

        # Resolver refs em items (arrays)
        if "items" in schema:
            schema["items"] = self._resolve_refs(
                dict(schema["items"]), components_schemas
            )

        # Resolver refs em allOf/anyOf/oneOf
        for keyword in ("allOf", "anyOf", "oneOf"):
            if keyword in schema:
                schema[keyword] = [
                    self._resolve_refs(dict(s), components_schemas)
                    for s in schema[keyword]
                ]

        return schema

    @staticmethod
    def _humanize_name(name: str) -> str:
        """Converte operationId em descrição legível.

        Exemplos:
            createEvent -> "Create event"
            get_user_by_id -> "Get user by id"
            listUsers -> "List users"
        """
        import re

        # camelCase -> snake_case
        name = re.sub(r"([a-z])([A-Z])", r"\1_\2", name)
        # snake_case -> palavras
        words = name.replace("_", " ").replace("-", " ").strip().lower()
        if words:
            return words[0].upper() + words[1:]
        return name
