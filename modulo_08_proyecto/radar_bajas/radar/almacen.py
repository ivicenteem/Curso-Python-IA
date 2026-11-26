"""Guardar y cargar los datos en una carpeta con tres CSV: socios, visitas y acciones.

Si un fichero no existe se considera vacío: es la primera ejecución. Si una
fila no vale, la carga se detiene con ``ErrorDeAlmacen`` indicando el fichero
y la línea, porque no se puede trabajar con la mitad de los datos.
"""

import csv
import logging
from collections.abc import Callable, Iterable
from pathlib import Path

from .excepciones import DatosNoValidos, ErrorDeAlmacen
from .modelos import (CAMPOS_ACCION, CAMPOS_SOCIO, CAMPOS_VISITA, AccionRetencion, Gimnasio, Socio,
                      Visita)

logger = logging.getLogger(__name__)

FICHERO_SOCIOS = "socios.csv"
FICHERO_VISITAS = "visitas.csv"
FICHERO_ACCIONES = "acciones.csv"

Registro = Socio | Visita | AccionRetencion


def guardar(carpeta: Path, gimnasio: Gimnasio, acciones: Iterable[AccionRetencion]) -> None:
    """Escribe los socios, las visitas y las acciones en ``carpeta``, creándola si hace falta."""
    carpeta = crear_carpeta(carpeta)
    _escribir(carpeta / FICHERO_SOCIOS, CAMPOS_SOCIO, gimnasio.socios.values())
    _escribir(carpeta / FICHERO_VISITAS, CAMPOS_VISITA, gimnasio.visitas)
    _escribir(carpeta / FICHERO_ACCIONES, CAMPOS_ACCION, acciones)
    logger.info("Datos guardados en %s", carpeta)


def crear_carpeta(carpeta: Path) -> Path:
    """Crea la carpeta si no existe y la devuelve como ``Path``."""
    carpeta = Path(carpeta)
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ErrorDeAlmacen(f"No se puede crear la carpeta {carpeta}: {error}") from error
    return carpeta


def cargar(carpeta: Path) -> tuple[Gimnasio, list[AccionRetencion]]:
    """Lee los datos de ``carpeta``. Sin ficheros, devuelve un gimnasio vacío y ninguna acción."""
    carpeta = Path(carpeta)
    socios = _leer(carpeta / FICHERO_SOCIOS, CAMPOS_SOCIO, Socio.desde_fila)
    visitas = _leer(carpeta / FICHERO_VISITAS, CAMPOS_VISITA, Visita.desde_fila)
    acciones = _leer(carpeta / FICHERO_ACCIONES, CAMPOS_ACCION, AccionRetencion.desde_fila)
    try:
        gimnasio = Gimnasio.desde_listas(socios, visitas)
    except DatosNoValidos as error:
        raise ErrorDeAlmacen(f"Los datos de {carpeta} no son coherentes: {error}") from error
    return gimnasio, acciones


def _escribir(ruta: Path, campos: list[str], registros: Iterable[Registro]) -> None:
    """Escribe los registros en un CSV con la cabecera ``campos``."""
    try:
        fichero = ruta.open("w", encoding="utf-8", newline="")
    except OSError as error:
        raise ErrorDeAlmacen(f"No se puede escribir {ruta}: {error}") from error
    with fichero:
        escritor = csv.DictWriter(fichero, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(registro.a_fila() for registro in registros)


def _leer[T](ruta: Path, campos: list[str], convertir: Callable[[dict[str, str]], T]) -> list[T]:
    """Lee un CSV y convierte cada fila con ``convertir``. Si no existe, lista vacía."""
    if not ruta.exists():
        return []
    try:
        fichero = ruta.open(encoding="utf-8", newline="")
    except OSError as error:
        raise ErrorDeAlmacen(f"No se puede leer {ruta}: {error}") from error
    with fichero:
        lector = csv.DictReader(fichero)
        faltan = set(campos) - set(lector.fieldnames or [])
        if faltan:
            raise ErrorDeAlmacen(f"{ruta.name}: faltan las columnas {', '.join(sorted(faltan))}")
        return [_convertir_fila(convertir, fila, ruta, lector.line_num) for fila in lector]


def _convertir_fila[T](convertir: Callable[[dict[str, str]], T], fila: dict[str, str],
                       ruta: Path, linea: int) -> T:
    """Convierte una fila; si no vale, lanza ``ErrorDeAlmacen`` con el fichero y la línea."""
    try:
        return convertir(fila)
    except DatosNoValidos as error:
        raise ErrorDeAlmacen(f"{ruta.name}, línea {linea}: {error}") from error
