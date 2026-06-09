# intentful/cli/main.py — CLI entry point para o agente Intentful
# Path: intentful/cli/main.py
from __future__ import annotations

import asyncio
import json
import sys

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
@click.version_option(version="1.0.0", prog_name="intentful")
def cli() -> None:
    """Intentful — AI agent that connects to any backend via OpenAPI."""


@cli.command()
@click.option(
    "--openapi-url",
    required=True,
    help="URL ou path da spec OpenAPI do backend target (ex: http://localhost:3000/openapi.json)",
)
@click.option(
    "--target-url",
    default=None,
    help="Base URL do backend target. Inferido da openapi-url se omitido.",
)
@click.option(
    "--backend",
    default="anthropic",
    type=click.Choice(["anthropic", "openai", "ollama"]),
    help="Backend LLM a usar.",
)
@click.option("--port", default=8100, help="Porto do agente.")
@click.option("--host", default="0.0.0.0", help="Host do agente.")
@click.option(
    "--confidence",
    default=0.7,
    type=float,
    help="Limiar mínimo de confiança (0-1).",
)
@click.option("--language", default="pt", help="Língua padrão (ISO 639-1).")
def serve(
    openapi_url: str,
    target_url: str | None,
    backend: str,
    port: int,
    host: str,
    confidence: float,
    language: str,
) -> None:
    """Inicia o agente Intentful standalone.

    Escaneia a spec OpenAPI do backend target e serve um endpoint /prompt
    que aceita prompts em linguagem natural.

    Exemplo:
        intentful serve --openapi-url http://localhost:3000/openapi.json
    """
    from intentful.server.app import AgentConfig, create_agent_app

    config = AgentConfig(
        openapi_url=openapi_url,
        target_base_url=target_url,
        backend_name=backend,
        port=port,
        host=host,
        confidence_threshold=confidence,
        language=language,
    )

    app = create_agent_app(config)

    console.print("\n[bold green]Intentful Agent v1.0.0[/bold green]")
    console.print(f"  Target:  {openapi_url}")
    console.print(f"  Backend: {backend}")
    console.print(f"  Server:  http://{host}:{port}")
    console.print(f"  Widget:  http://{host}:{port}/widget/intentful.js\n")

    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


@cli.command()
@click.option(
    "--openapi-url",
    required=True,
    help="URL ou path da spec OpenAPI a escanear.",
)
@click.option("--format", "output_format", default="table", type=click.Choice(["table", "json"]))
def scan(openapi_url: str, output_format: str) -> None:
    """Escaneia uma spec OpenAPI e mostra os endpoints descobertos.

    Dry-run — não inicia o servidor, só mostra o que seria descoberto.

    Exemplo:
        intentful scan --openapi-url http://localhost:3000/openapi.json
    """
    from intentful.scanner.openapi import OpenAPIScanner

    async def _scan() -> None:
        scanner = OpenAPIScanner()
        try:
            entries = await scanner.scan(openapi_url)
        except Exception as e:
            console.print(f"[bold red]Erro ao escanear:[/bold red] {e}")
            sys.exit(1)

        if not entries:
            console.print("[yellow]Nenhum endpoint encontrado na spec.[/yellow]")
            return

        if output_format == "json":
            data = [
                {
                    "path": e.endpoint_path,
                    "method": e.method,
                    "description": e.description,
                    "operations": e.context.allowed_operations,
                    "has_payload": e.payload_schema is not None,
                }
                for e in entries
            ]
            console.print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            table = Table(title=f"Endpoints descobertos ({len(entries)})")
            table.add_column("Method", style="bold cyan", width=8)
            table.add_column("Path", style="green")
            table.add_column("Description")
            table.add_column("Operations", style="yellow")
            table.add_column("Payload", justify="center")

            for entry in entries:
                table.add_row(
                    entry.method,
                    entry.endpoint_path,
                    entry.description,
                    ", ".join(entry.context.allowed_operations),
                    "✓" if entry.payload_schema else "—",
                )

            console.print(table)

    asyncio.run(_scan())


@cli.command()
@click.argument("prompt_text")
@click.option(
    "--openapi-url",
    required=True,
    help="URL ou path da spec OpenAPI do backend target.",
)
@click.option(
    "--target-url",
    default=None,
    help="Base URL do backend target.",
)
@click.option(
    "--backend",
    default="anthropic",
    type=click.Choice(["anthropic", "openai", "ollama"]),
)
@click.option("--language", default="pt")
@click.option("--dry-run", is_flag=True, help="Simular sem executar.")
def prompt(
    prompt_text: str,
    openapi_url: str,
    target_url: str | None,
    backend: str,
    language: str,
    dry_run: bool,
) -> None:
    """Envia um prompt one-shot sem iniciar o servidor.

    Exemplo:
        intentful prompt "lista todos os utilizadores" --openapi-url http://localhost:3000/openapi.json
    """
    from intentful.core.schemas import IntentRequest
    from intentful.routing.resolver import LLMResolver
    from intentful.scanner.openapi import OpenAPIScanner
    from intentful.scanner.registry_builder import build_registry_from_spec
    from intentful.server.app import _create_backend
    from intentful.server.executor import HTTPExecutor

    async def _prompt() -> None:
        # 1. Scan
        scanner = OpenAPIScanner()
        try:
            entries = await scanner.scan(openapi_url)
        except Exception as e:
            console.print(f"[bold red]Erro ao escanear:[/bold red] {e}")
            sys.exit(1)

        if not entries:
            console.print("[yellow]Nenhum endpoint encontrado.[/yellow]")
            sys.exit(1)

        registry = build_registry_from_spec(entries)

        # 2. Resolve
        llm_backend = _create_backend(backend)
        resolver = LLMResolver(llm_backend)
        request = IntentRequest(prompt=prompt_text, language=language, dry_run=dry_run)

        console.print(f"[dim]Resolvendo: \"{prompt_text}\"...[/dim]")

        try:
            resolution = await resolver.resolve(request, registry)
        except RuntimeError as e:
            console.print(f"[bold red]Erro:[/bold red] {e}")
            sys.exit(1)

        console.print("\n[bold]Resolução:[/bold]")
        console.print(f"  Endpoint:   {resolution.method} {resolution.endpoint}")
        console.print(f"  Confiança:  {resolution.confidence:.0%}")
        console.print(f"  Raciocínio: {resolution.reasoning}")

        if resolution.payload:
            console.print(f"  Payload:    {json.dumps(resolution.payload, ensure_ascii=False)}")

        if dry_run:
            console.print("\n[yellow]Dry run — operação não executada.[/yellow]")
            return

        if resolution.confidence < 0.7:
            console.print("\n[red]Confiança insuficiente. Operação cancelada.[/red]")
            return

        # 3. Execute
        from urllib.parse import urlparse
        base = target_url
        if not base:
            parsed = urlparse(openapi_url)
            base = f"{parsed.scheme}://{parsed.netloc}"

        executor = HTTPExecutor(base_url=base)
        result = await executor.execute(
            method=resolution.method,
            path=resolution.endpoint,
            payload=resolution.payload,
        )

        if result.success:
            console.print(f"\n[bold green]Sucesso[/bold green] ({result.status_code}, {result.duration_ms}ms)")
            console.print(json.dumps(result.body, indent=2, ensure_ascii=False)
                          if isinstance(result.body, (dict, list)) else str(result.body))
        else:
            console.print(f"\n[bold red]Erro {result.status_code}[/bold red] ({result.duration_ms}ms)")
            console.print(str(result.body))

    asyncio.run(_prompt())


if __name__ == "__main__":
    cli()
