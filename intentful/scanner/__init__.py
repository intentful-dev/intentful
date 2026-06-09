# intentful/scanner/__init__.py — OpenAPI/Swagger scanner para discovery de endpoints
# Path: intentful/scanner/__init__.py
from intentful.scanner.openapi import OpenAPIScanner
from intentful.scanner.registry_builder import build_registry_from_spec

__all__ = ["OpenAPIScanner", "build_registry_from_spec"]
