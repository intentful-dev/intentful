# tests/conftest.py — Fixtures partilhadas entre todos os testes
import pytest

from intentful.core.registry import get_registry


@pytest.fixture(autouse=True)
def _clean_registry():
    """Limpa o registry global antes e depois de cada teste."""
    get_registry().clear()
    yield
    get_registry().clear()
