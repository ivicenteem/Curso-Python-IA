"""Guardar y cargar los datos en una carpeta con tres CSV: socios, visitas y acciones.

También convierte los datos a texto CSV y los lee desde texto, para descargarlos
y subirlos desde la web.

Si un fichero no existe se considera vacío: es la primera ejecución. Si una
fila no vale, la carga se detiene con ``ErrorDeAlmacen`` indicando el fichero
y la línea, porque no se puede trabajar con la mitad de los datos.
"""

import csv
import io
import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TextIO

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
    return _crear_gimnasio(socios, visitas, str(carpeta)), acciones


def cargar_textos(socios: str, visitas: str, acciones: str = "") -> tuple[Gimnasio,
                                                                       list[AccionRetencion]]:
    """Lee los datos a partir del contenido de los tres CSV, por ejemplo subidos desde la web.

    Los socios son obligatorios; las visitas y las acciones pueden estar vacías.
    Los errores indican el fichero y la línea, igual que ``cargar``.
    """
    if not socios.strip():
        raise ErrorDeAlmacen(f"Falta el fichero de socios ({FICHERO_SOCIOS})")
    lista_socios = _leer_texto(socios, FICHERO_SOCIOS, CAMPOS_SOCIO, Socio.desde_fila)
    lista_visitas = _leer_texto(visitas, FICHERO_VISITAS, CAMPOS_VISITA, Visita.desde_fila)
    lista_acciones = _leer_texto(acciones, FICHERO_ACCIONES, CAMPOS_ACCION,
                                 AccionRetencion.desde_fila)
    return _crear_gimnasio(lista_socios, lista_visitas, "los ficheros subidos"), lista_acciones


def textos_csv(gimnasio: Gimnasio, acciones: Iterable[AccionRetencion]) -> dict[str, str]:
    """Contenido CSV de cada fichero de datos, por nombre de fichero."""
    contenidos = {
        FICHERO_SOCIOS: (CAMPOS_SOCIO, gimnasio.socios.values()),
        FICHERO_VISITAS: (CAMPOS_VISITA, gimnasio.visitas),
        FICHERO_ACCIONES: (CAMPOS_ACCION, acciones),
    }
    return {nombre: _a_texto(campos, registros)
            for nombre, (campos, registros) in contenidos.items()}


def _crear_gimnasio(socios: list[Socio], visitas: list[Visita], origen: str) -> Gimnasio:
    """Crea el gimnasio; si los datos no son coherentes, lanza ``ErrorDeAlmacen``."""
    try:
        return Gimnasio.desde_listas(socios, visitas)
    except DatosNoValidos as error:
        raise ErrorDeAlmacen(f"Los datos de {origen} no son coherentes: {error}") from error


def _escribir(ruta: Path, campos: list[str], registros: Iterable[Registro]) -> None:
    """Escribe los registros en un CSV con la cabecera ``campos``."""
    try:
        fichero = ruta.open("w", encoding="utf-8", newline="")
    except OSError as error:
        raise ErrorDeAlmacen(f"No se puede escribir {ruta}: {error}") from error
    with fichero:
        _escribir_en(fichero, campos, registros)


def _a_texto(campos: list[str], registros: Iterable[Registro]) -> str:
    """Los registros como texto CSV con la cabecera ``campos``."""
    salida = io.StringIO(newline="")
    _escribir_en(salida, campos, registros)
    return salida.getvalue()


def _escribir_en(fichero: TextIO, campos: list[str], registros: Iterable[Registro]) -> None:
    """Escribe la cabecera y las filas de los registros en un fichero de texto abierto."""
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
        return _leer_de(fichero, ruta.name, campos, convertir)


def _leer_texto[T](texto: str, nombre: str, campos: list[str],
                   convertir: Callable[[dict[str, str]], T]) -> list[T]:
    """Lee un CSV a partir de su contenido. Un texto vacío es una lista vacía."""
    if not texto.strip():
        return []
    return _leer_de(io.StringIO(texto, newline=""), nombre, campos, convertir)


def _leer_de[T](fichero: TextIO, nombre: str, campos: list[str],
                convertir: Callable[[dict[str, str]], T]) -> list[T]:
    """Lee un CSV abierto y convierte cada fila; comprueba antes que estén las columnas."""
    lector = csv.DictReader(fichero)
    faltan = set(campos) - set(lector.fieldnames or [])
    if faltan:
        raise ErrorDeAlmacen(f"{nombre}: faltan las columnas {', '.join(sorted(faltan))}")
    return [_convertir_fila(convertir, fila, nombre, lector.line_num) for fila in lector]


def _convertir_fila[T](convertir: Callable[[dict[str, str]], T], fila: dict[str, str],
                       nombre: str, linea: int) -> T:
    """Convierte una fila; si no vale, lanza ``ErrorDeAlmacen`` con el fichero y la línea."""
    try:
        return convertir(fila)
    except DatosNoValidos as error:
        raise ErrorDeAlmacen(f"{nombre}, línea {linea}: {error}") from error
