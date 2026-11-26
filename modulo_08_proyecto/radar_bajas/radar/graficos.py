"""Gráficos para la dirección con matplotlib.

Cada función devuelve la figura sin mostrarla; ``exportar`` las guarda en PNG.
Se usa el backend "Agg", que dibuja en memoria y no abre ventanas.
"""

from pathlib import Path

import matplotlib
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from .almacen import crear_carpeta
from .analisis import ResumenDireccion
from .excepciones import ErrorDeAlmacen

matplotlib.use("Agg")

COLOR_BARRA = "#2a78d6"
COLOR_TEXTO = "#0b0b0b"
COLOR_SECUNDARIO = "#52514e"
COLOR_REJILLA = "#e4e3df"
COLOR_FONDO = "#fcfcfb"
TAMANO = (8, 4.5)
ANCHO_BARRA = 0.45


def _barras(titulo: str, etiquetas: list[str], valores: pd.Series, eje_y: str,
            textos: list[str]) -> Figure:
    """Figura de barras verticales de una serie con el valor escrito sobre cada barra."""
    figura = Figure(figsize=TAMANO, facecolor=COLOR_FONDO, layout="constrained")
    ejes: Axes = figura.subplots()
    ejes.set_facecolor(COLOR_FONDO)
    barras = ejes.bar(etiquetas, valores.fillna(0), width=ANCHO_BARRA, color=COLOR_BARRA)
    ejes.bar_label(barras, labels=textos, padding=3, color=COLOR_TEXTO, fontsize=9)
    ejes.set_title(titulo, loc="left", color=COLOR_TEXTO, fontsize=13, pad=12)
    ejes.set_ylabel(eje_y, color=COLOR_SECUNDARIO)
    ejes.tick_params(colors=COLOR_SECUNDARIO, length=0)
    ejes.grid(axis="y", color=COLOR_REJILLA, linewidth=0.8)
    ejes.set_axisbelow(True)
    ejes.spines[["top", "right", "left"]].set_visible(False)
    ejes.spines["bottom"].set_color(COLOR_SECUNDARIO)
    ejes.margins(y=0.15)
    return figura


def grafico_bajas(evolucion: pd.DataFrame) -> Figure:
    """Bajas de cada mes, a partir de ``analisis.evolucion_mensual``."""
    etiquetas = evolucion.index.strftime("%m/%y").tolist()
    textos = evolucion["bajas"].astype(str).tolist()
    return _barras("Bajas por mes", etiquetas, evolucion["bajas"], "Socios que se dan de baja",
                   textos)


def grafico_riesgo_tarifa(por_tarifa: pd.DataFrame) -> Figure:
    """Riesgo medio de cada tarifa, a partir de ``analisis.riesgo_por_tarifa``."""
    textos = por_tarifa["riesgo_medio"].map("{:.1f}".format).str.replace(".", ",").tolist()
    return _barras("Riesgo medio por tarifa", por_tarifa.index.tolist(),
                   por_tarifa["riesgo_medio"], "Riesgo medio (0 a 100)", textos)


def grafico_eficacia(eficacia: pd.DataFrame) -> Figure:
    """Tasa de retención de cada tipo de acción, a partir de ``analisis.eficacia_acciones``.

    Cada barra indica cuántas acciones cerradas hay detrás del porcentaje.
    """
    tasa = eficacia["tasa_retencion"]
    textos = (tasa.round().astype("Int64").astype(str) + " % (n="
              + eficacia["cerradas"].astype(str) + ")").where(tasa.notna(), "sin datos").tolist()
    etiquetas = eficacia.index.str.replace("_", " ").tolist()
    return _barras("Socios retenidos por tipo de acción", etiquetas, eficacia["tasa_retencion"],
                   "Retenidos (% de las acciones cerradas)", textos)


def guardar(figura: Figure, ruta: Path) -> Path:
    """Guarda la figura en PNG y devuelve la ruta."""
    try:
        figura.savefig(ruta, dpi=120)
    except OSError as error:
        raise ErrorDeAlmacen(f"No se puede guardar el gráfico {ruta}: {error}") from error
    return ruta


def exportar(carpeta: Path, resumen: ResumenDireccion) -> list[Path]:
    """Guarda los tres gráficos del resumen en ``carpeta`` y devuelve sus rutas."""
    carpeta = crear_carpeta(carpeta)
    figuras = {
        "evolucion_bajas.png": grafico_bajas(resumen.evolucion),
        "riesgo_por_tarifa.png": grafico_riesgo_tarifa(resumen.por_tarifa),
        "eficacia_acciones.png": grafico_eficacia(resumen.eficacia),
    }
    return [guardar(figura, carpeta / nombre) for nombre, figura in figuras.items()]
