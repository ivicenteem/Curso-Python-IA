"""Configuración de los tests de Radar de Bajas.

Añade esta carpeta a ``sys.path`` para que los tests importen el paquete
``radar`` y la aplicación ``radar_app``. Las fixtures están en
``tests/conftest.py``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
