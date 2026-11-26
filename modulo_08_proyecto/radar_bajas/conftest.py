"""Configuración de los tests de Radar de Bajas.

Añade esta carpeta a ``sys.path`` para que los tests importen el paquete
``radar`` y la aplicación ``radar_app``, y define las fixtures comunes.
"""

import sys
from pathlib import Path

CARPETA_PROYECTO = Path(__file__).parent
sys.path.insert(0, str(CARPETA_PROYECTO))
