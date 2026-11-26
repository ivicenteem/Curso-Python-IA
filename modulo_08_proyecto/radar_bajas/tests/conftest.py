"""Fixtures comunes de los tests: datos simulados con semilla fija."""

import pytest

from radar.modelos import Gimnasio
from radar.simulador import simular

SEMILLA_TESTS = 42


@pytest.fixture(scope="session")
def gimnasio() -> Gimnasio:
    """Gimnasio simulado con la semilla fija. Se comparte: los tests no deben modificarlo."""
    return simular(semilla=SEMILLA_TESTS)
