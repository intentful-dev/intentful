# intentful/core/decorator.py — @intent: o coração da biblioteca
from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable

from pydantic import BaseModel

from intentful.core.context import IntentContext
from intentful.core.registry import IntentEntry, get_registry


def _extract_payload_schema(handler: Callable[..., Any]) -> dict[str, Any] | None:
    """Extrai o JSON Schema do primeiro parâmetro Pydantic do handler."""
    sig = inspect.signature(handler)
    for param in sig.parameters.values():
        annotation = param.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return annotation.model_json_schema()
    return None


def intent(
    description: str,
    context: IntentContext | None = None,
    *,
    method: str = "POST",
    path: str | None = None,
    tags: list[str] | None = None,
) -> Callable:
    """Decorator que anota um endpoint FastAPI com contexto semântico.

    Uso:
        @router.post("/turmas/gerar")
        @intent(
            description="Criar turmas para um ano lectivo",
            context=IntentContext(rules=[...], requires_confirmation=True)
        )
        async def gerar_turmas(payload: Schema, db=Depends(get_db)):
            ...
    """
    if context is None:
        context = IntentContext()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        payload_schema = _extract_payload_schema(func)

        entry = IntentEntry(
            endpoint_path=path or _infer_path(func),
            method=method.upper(),
            description=description,
            context=context,
            handler=func,
            payload_schema=payload_schema,
            tags=tags or context.tags,
        )

        get_registry().register(entry)

        # Guarda metadata no handler para acesso posterior
        func._intent_entry = entry  # type: ignore[attr-defined]

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs) if inspect.iscoroutinefunction(func) else func(*args, **kwargs)

        wrapper._intent_entry = entry  # type: ignore[attr-defined]
        return wrapper

    return decorator


def _infer_path(func: Callable[..., Any]) -> str:
    """Tenta inferir o path do endpoint a partir do nome da função."""
    return f"/{func.__name__.replace('_', '/')}"
