"""Arranca la web de Radar de Bajas en http://127.0.0.1:8000 y abre el navegador.

Uso, desde la raíz del repositorio:

    python modulo_08_proyecto/radar_bajas/web
    python modulo_08_proyecto/radar_bajas/web --sin-navegador

Solo escucha en 127.0.0.1, así que no es accesible desde otros equipos.
"""

import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

HOST = "127.0.0.1"
PUERTO = 8000
CARPETA_PROYECTO = Path(__file__).resolve().parent.parent
SEGUNDOS_ANTES_DE_ABRIR = 1.5


def main() -> None:
    """Abre el navegador (salvo con ``--sin-navegador``) y sirve la web hasta Ctrl+C."""
    if "--sin-navegador" not in sys.argv:
        url = f"http://{HOST}:{PUERTO}"
        threading.Timer(SEGUNDOS_ANTES_DE_ABRIR, webbrowser.open, args=[url]).start()
    uvicorn.run("web.app:crear_app", factory=True, host=HOST, port=PUERTO,
                app_dir=str(CARPETA_PROYECTO))


if __name__ == "__main__":
    main()
