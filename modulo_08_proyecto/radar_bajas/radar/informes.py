"""Textos para mostrar al usuario. Las funciones devuelven cadenas; no imprimen nada."""

import operator
from collections.abc import Iterable
from functools import reduce

import pandas as pd

from .analisis import ResumenDireccion
from .excepciones import DatosNoValidos
from .modelos import AccionRetencion
from .radar import Evaluacion
from .retencion import recomendar
from .validacion import ALERTA, SIN_ALERTA, ResultadoValidacion

ANCHO = 78
SEPARADOR = "-" * ANCHO
MOTIVOS_EN_TABLA = 2


def _titulo(texto: str) -> list[str]:
    """Líneas de un título centrado entre dos líneas de signos igual."""
    return ["=" * ANCHO, texto.upper().center(ANCHO).rstrip(), "=" * ANCHO]


def _numero(valor: float, decimales: int = 1) -> str:
    """Número con coma decimal y punto de miles, al estilo español."""
    return f"{valor:,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def porcentaje(valor: float) -> str:
    """Porcentaje con un decimal, por ejemplo "12,5 %"."""
    return f"{_numero(valor)} %"


def euros(valor: float) -> str:
    """Importe en euros, por ejemplo "1.234,50 €"."""
    return f"{_numero(valor, 2)} €"


def _celda(valores: pd.Series | pd.Index, ancho: int, izquierda: bool = False) -> pd.Series:
    """Columna de texto alineada a ``ancho`` caracteres (a la derecha salvo que se pida)."""
    texto = pd.Series(valores).astype(str).reset_index(drop=True)
    return texto.str.ljust(ancho) if izquierda else texto.str.rjust(ancho)


def _lineas(*celdas: pd.Series) -> list[str]:
    """Une columnas de texto de la misma longitud en líneas sangradas con dos espacios."""
    return ("  " + reduce(operator.add, celdas)).tolist()


def _recortar(texto: str, ancho: int) -> str:
    """Recorta el texto a ``ancho`` caracteres, terminando en "…" si no cabe."""
    return texto if len(texto) <= ancho else texto[:ancho - 1] + "…"


def tabla_riesgo(evaluaciones: list[Evaluacion], cuantos: int) -> str:
    """Los ``cuantos`` socios con más riesgo con sus motivos principales."""
    if cuantos < 1:
        raise DatosNoValidos(f"El número de socios debe ser al menos 1: {cuantos}")
    cabecera = f"{'ID':>4}  {'RIESGO':>6}  {'NOMBRE':<16}{'TARIFA':<11}MOTIVOS"
    filas = [_fila_riesgo(evaluacion) for evaluacion in evaluaciones[:cuantos]]
    return "\n".join([cabecera, SEPARADOR, *(filas or ["(sin socios)"])])


def _fila_riesgo(evaluacion: Evaluacion) -> str:
    """Una línea de la tabla de riesgo."""
    socio = evaluacion.socio
    principales = evaluacion.senales_activas[:MOTIVOS_EN_TABLA]
    motivos = "; ".join(lectura.detalle for lectura in principales)
    alerta = "!" if evaluacion.en_riesgo else " "
    inicio = f"{socio.id:>4}  {evaluacion.riesgo:>5}{alerta}  {_recortar(socio.nombre, 15):<16}" \
             f"{socio.tarifa:<11}"
    return inicio + _recortar(motivos, ANCHO - len(inicio))


def ficha_socio(evaluacion: Evaluacion, accion_abierta: AccionRetencion | None) -> str:
    """Datos del socio, su riesgo explicado señal a señal y la acción que procede."""
    socio = evaluacion.socio
    lineas = [
        f"Socio {socio.id}: {socio.nombre}",
        f"Tarifa {socio.tarifa}, {euros(socio.cuota)} al mes, "
        f"alta el {socio.fecha_alta.isoformat()}",
        "",
        evaluacion.explicacion,
        "",
        "Puntos por señal",
        *[f"  {lectura.senal:<18}{_numero(lectura.puntos):>6}  {lectura.detalle}"
          for lectura in evaluacion.lecturas],
        "",
        accion_para(evaluacion, accion_abierta),
    ]
    return "\n".join(lineas)


def accion_para(evaluacion: Evaluacion, accion_abierta: AccionRetencion | None) -> str:
    """Línea con la acción abierta, la recomendada o el motivo de no proponer ninguna."""
    if accion_abierta:
        return (f"Acción en marcha: n.º {accion_abierta.id}, {accion_abierta.tipo} "
                f"({accion_abierta.estado})")
    if not evaluacion.en_riesgo:
        return f"Sin acción: el riesgo no llega al umbral ({evaluacion.umbral})"
    return f"Acción recomendada: {recomendar(evaluacion)}"


def listado_acciones(acciones: Iterable[AccionRetencion]) -> str:
    """Tabla de acciones de retención."""
    cabecera = f"{'ID':>4}  {'SOCIO':>5}  {'TIPO':<15}{'ESTADO':<12}{'PROPUESTA':<12}CIERRE"
    filas = [f"{accion.id:>4}  {accion.id_socio:>5}  {accion.tipo:<15}{accion.estado:<12}"
             f"{accion.fecha_propuesta.isoformat():<12}"
             f"{accion.fecha_cierre.isoformat() if accion.fecha_cierre else '-'}"
             for accion in acciones]
    return "\n".join([cabecera, SEPARADOR, *(filas or ["(sin acciones)"])])


def informe_validacion(resultado: ResultadoValidacion) -> str:
    """Resultado del backtesting: matriz de confusión, métricas y barrido de umbrales."""
    metricas, matriz, barrido = resultado.metricas, resultado.matriz, resultado.barrido
    cortes = f"{resultado.cortes[0].isoformat()} a {resultado.cortes[-1].isoformat()}"
    lineas = [
        *_titulo("Validación del radar con el histórico"),
        f"Cortes: {len(resultado.cortes)}, de {cortes}",
        f"Acierto: el socio avisado se da de baja en los {resultado.horizonte_dias} "
        "días siguientes",
        f"Umbral de alerta: {resultado.umbral}",
        "",
        f"  {'':<14}{SIN_ALERTA:>12}{ALERTA:>12}",
        *_lineas(_celda(matriz.index, 14, izquierda=True), _celda(matriz[SIN_ALERTA], 12),
                 _celda(matriz[ALERTA], 12)),
        "",
        f"Casos (socio y fecha de corte): {metricas.casos}",
        f"Precisión: {porcentaje(100 * metricas.precision)} de las alertas acabaron en baja",
        f"Recall: {porcentaje(100 * metricas.recall)} de las bajas tuvieron alerta",
        f"Tasa base: {porcentaje(100 * metricas.tasa_base)} "
        f"(avisar al azar); la alerta es {_numero(metricas.mejora)} veces más precisa",
        "",
        f"  {'UMBRAL':>6}{'ALERTAS':>10}{'ACIERTOS':>10}{'PRECISIÓN':>12}{'RECALL':>10}",
        *_lineas(_celda(barrido.index, 6), _celda(barrido["alertas"], 10),
                 _celda(barrido["aciertos"], 10),
                 _celda((100 * barrido["precision"]).map(porcentaje), 12),
                 _celda((100 * barrido["recall"]).map(porcentaje), 10)),
        "=" * ANCHO,
    ]
    return "\n".join(lineas)


def informe_direccion(resumen: ResumenDireccion) -> str:
    """Informe para la dirección: indicadores, evolución, riesgo por tarifa y acciones."""
    datos = resumen.indicadores
    evolucion, por_tarifa, eficacia = resumen.evolucion, resumen.por_tarifa, resumen.eficacia
    lineas = [
        *_titulo("Radar de bajas: informe para la dirección"),
        f"Datos a {resumen.fecha.isoformat()}",
        f"Socios activos: {datos['socios_activos']}",
        f"Socios en riesgo: {datos['en_riesgo']} ({porcentaje(datos['porcentaje_en_riesgo'])})",
        f"Ingresos en juego: {euros(datos['ingresos_en_juego'])} al mes "
        f"({euros(12 * datos['ingresos_en_juego'])} al año)",
        f"Tasa de abandono mensual media: {porcentaje(datos['tasa_abandono_media'])}",
        f"Acción que más retiene: {_texto_accion(datos['mejor_accion'])}",
        "",
        "Evolución mensual",
        f"  {'MES':<9}{'ACTIVOS':>8}{'BAJAS':>7}{'ABANDONO':>10}{'VISITAS':>9}",
        *_lineas(_celda(evolucion.index.strftime("%Y-%m"), 9, izquierda=True),
                 _celda(evolucion["activos"], 8), _celda(evolucion["bajas"], 7),
                 _celda(evolucion["tasa_abandono"].map(porcentaje), 10),
                 _celda(evolucion["visitas"], 9)),
        "",
        "Riesgo por tarifa",
        f"  {'TARIFA':<12}{'SOCIOS':>7}{'RIESGO MEDIO':>14}{'EN RIESGO':>11}",
        *_lineas(_celda(por_tarifa.index, 12, izquierda=True), _celda(por_tarifa["socios"], 7),
                 _celda(por_tarifa["riesgo_medio"].map(_numero), 14),
                 _celda(por_tarifa["en_riesgo"], 11)),
        "",
        "Causa principal de los socios en riesgo",
        *(_lineas(_celda(resumen.causas.index, 18, izquierda=True), _celda(resumen.causas, 4))
          or ["  (ningún socio en riesgo)"]),
        "",
        "Eficacia de las acciones de retención",
        f"  {'TIPO':<15}{'CERRADAS':>9}{'RETENIDOS':>11}{'TASA':>10}",
        *_lineas(_celda(eficacia.index, 15, izquierda=True), _celda(eficacia["cerradas"], 9),
                 _celda(eficacia["retenido"], 11),
                 _celda(eficacia["tasa_retencion"].map(texto_tasa), 10)),
        "=" * ANCHO,
    ]
    return "\n".join(lineas)


def _texto_accion(tipo: str | None) -> str:
    """Nombre de la acción o aviso de que aún no hay acciones cerradas suficientes."""
    return tipo or "faltan acciones cerradas para comparar"


def texto_tasa(tasa: float) -> str:
    """Tasa en porcentaje o un guion si no hay acciones cerradas (NaN)."""
    return "-" if pd.isna(tasa) else porcentaje(tasa)
