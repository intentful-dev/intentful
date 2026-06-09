# tests/test_cli.py — Testes da CLI
# Path: tests/test_cli.py
from __future__ import annotations

import json
from unittest.mock import patch

from click.testing import CliRunner

from intentful.cli.main import cli


class TestCLICommands:
    """Testes dos comandos CLI."""

    def test_version(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "1.0.0" in result.output

    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "intentful" in result.output.lower()

    def test_serve_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--openapi-url" in result.output
        assert "--backend" in result.output
        assert "--port" in result.output

    def test_scan_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", "--help"])
        assert result.exit_code == 0
        assert "--openapi-url" in result.output
        assert "--format" in result.output

    def test_prompt_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["prompt", "--help"])
        assert result.exit_code == 0
        assert "--openapi-url" in result.output
        assert "--dry-run" in result.output

    def test_scan_missing_url(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["scan"])
        assert result.exit_code != 0
        assert "openapi-url" in result.output.lower() or "required" in result.output.lower()

    @patch("intentful.scanner.openapi.OpenAPIScanner.scan")
    def test_scan_json_format(self, mock_scan) -> None:
        """Deve listar endpoints em formato JSON."""
        from intentful.core.context import IntentContext
        from intentful.core.registry import IntentEntry
        from intentful.scanner.openapi import _noop_handler

        mock_scan.return_value = [
            IntentEntry(
                endpoint_path="/users",
                method="GET",
                description="List users",
                context=IntentContext(allowed_operations=["READ"]),
                handler=_noop_handler,
            ),
        ]

        runner = CliRunner()
        result = runner.invoke(cli, [
            "scan",
            "--openapi-url", "http://localhost:3000/openapi.json",
            "--format", "json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["path"] == "/users"
        assert data[0]["method"] == "GET"

    @patch("intentful.scanner.openapi.OpenAPIScanner.scan")
    def test_scan_table_format(self, mock_scan) -> None:
        """Deve listar endpoints em formato tabela."""
        from intentful.core.context import IntentContext
        from intentful.core.registry import IntentEntry
        from intentful.scanner.openapi import _noop_handler

        mock_scan.return_value = [
            IntentEntry(
                endpoint_path="/events",
                method="POST",
                description="Create event",
                context=IntentContext(allowed_operations=["CREATE"]),
                handler=_noop_handler,
                payload_schema={"type": "object"},
            ),
        ]

        runner = CliRunner()
        result = runner.invoke(cli, [
            "scan",
            "--openapi-url", "http://localhost:3000/openapi.json",
        ])
        assert result.exit_code == 0
        assert "POST" in result.output
        assert "/events" in result.output
        assert "Create event" in result.output
