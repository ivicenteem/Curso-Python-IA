"""Radar de Bajas: interfaz web con Streamlit.

Igual que ``radar_app.py``, solo presenta: recoge lo que elige el usuario,
llama al paquete ``radar`` y muestra los resultados. Toda la lógica está en
el paquete.

Uso, desde la raíz del repositorio:

    streamlit run modulo_08_proyecto/radar_bajas/web_app.py
"""

import copy
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from radar import almacen, analisis, informes
from radar.excepciones import ErrorRadar
from radar.modelos import ESTADOS_ACCION, TARIFAS, AccionRetencion, Gimnasio
from radar.radar import UMBRAL_RIESGO, Evaluacion, Radar
from radar.retencion import GestorRetencion
from radar.simulador import SEMILLA, simular, simular_acciones
from radar.validacion import (HORIZONTE_DIAS, cortes_por_defecto, resultado_desde_tabla,
                              tabla_backtest)

CARPETA_DATOS = Path(__file__).parent / "datos"
ORIGEN_CARPETA = "Datos guardados (datos/)"
ORIGEN_SIMULADO = "Simular con una semilla"
UMBRAL_MINIMO, UMBRAL_MAXIMO = 20, 80

COLUMNAS_SOCIOS = {"id_socio": "Socio", "nombre": "Nombre", "tarifa": "Tarifa",
                   "cuota": "Cuota (€)", "riesgo": "Riesgo", "explicacion": "Motivos"}
COLUMNAS_ACCIONES = {"id": "Acción", "id_socio": "Socio", "tipo": "Tipo",
                     "fecha_propuesta": "Propuesta", "estado": "Estado"}


@dataclass(frozen=True)
class Opciones:
    """Lo que el usuario ha elegido en la barra lateral."""

    origen: str
    semilla: int
    umbral: int
    seccion: str


@dataclass
class Contexto:
    """Datos con los que se dibuja cualquier sección."""

    gimnasio: Gimnasio
    evaluaciones: list[Evaluacion]
    retencion: GestorRetencion
    opciones: Opciones


# --- Datos con caché ---------------------------------------------------------

@st.cache_resource(show_spinner="Cargando los datos…")
def cargar_datos(origen: str, semilla: int) -> tuple[Gimnasio, list[AccionRetencion]]:
    """Gimnasio y acciones guardadas, o simulados con la semilla. Se calcula una vez."""
    if origen == ORIGEN_CARPETA:
        return almacen.cargar(CARPETA_DATOS)
    gimnasio = simular(semilla=semilla)
    return gimnasio, simular_acciones(gimnasio, Radar.por_defecto()).acciones


@st.cache_resource(show_spinner="Calculando el riesgo…")
def evaluar(origen: str, semilla: int, umbral: int) -> list[Evaluacion]:
    """Riesgo de los socios activos en la fecha de los datos con el umbral elegido."""
    gimnasio, _ = cargar_datos(origen, semilla)
    return Radar.por_defecto(umbral).evaluar_todos(gimnasio)


@st.cache_data(show_spinner="Validando con el histórico…")
def backtest(origen: str, semilla: int) -> tuple[pd.DataFrame, list[date]]:
    """Tabla de backtesting y sus fechas de corte. No depende del umbral."""
    gimnasio, _ = cargar_datos(origen, semilla)
    cortes = cortes_por_defecto(gimnasio)
    return tabla_backtest(gimnasio, Radar.por_defecto(), cortes), cortes


def retencion_de_sesion(opciones: Opciones,
                        acciones: list[AccionRetencion]) -> GestorRetencion:
    """Gestor de acciones de esta sesión; se rehace al cambiar el origen de los datos."""
    clave = (opciones.origen, opciones.semilla)
    if st.session_state.get("datos_de_la_sesion") != clave:
        st.session_state["datos_de_la_sesion"] = clave
        st.session_state["retencion"] = GestorRetencion(copy.deepcopy(acciones))
    return st.session_state["retencion"]


def con_errores[**P](funcion: Callable[P, None], *args: P.args, **kwargs: P.kwargs) -> None:
    """Ejecuta ``funcion`` y muestra los errores de la aplicación en lugar de una traza."""
    try:
        funcion(*args, **kwargs)
    except ErrorRadar as error:
        st.error(f"Error: {error}")


# --- Barra lateral -----------------------------------------------------------

def barra_lateral() -> Opciones:
    """Origen de los datos, umbral de riesgo y sección que mostrar."""
    st.sidebar.title("Radar de Bajas")
    origen = st.sidebar.radio("Origen de los datos", [ORIGEN_CARPETA, ORIGEN_SIMULADO],
                              key="origen")
    semilla = 0
    if origen == ORIGEN_SIMULADO:
        semilla = int(st.sidebar.number_input("Semilla", min_value=0, value=SEMILLA, step=1,
                                              key="semilla"))
    umbral = st.sidebar.slider(
        "Umbral de riesgo", UMBRAL_MINIMO, UMBRAL_MAXIMO, UMBRAL_RIESGO, key="umbral",
        help="Un socio está en riesgo cuando su índice llega a este valor.")
    seccion = st.sidebar.radio("Sección", list(SECCIONES), key="seccion")
    return Opciones(origen, semilla, umbral, seccion)


# --- Secciones ---------------------------------------------------------------

def seccion_resumen(contexto: Contexto) -> None:
    """Cifras principales y gráficos para la dirección."""
    st.header("Resumen para la dirección")
    st.write("Cuántos socios hay ahora mismo en riesgo de darse de baja, cuánto dinero "
             "suponen sus cuotas y cómo ha evolucionado el abandono en el último año.")
    retencion = contexto.retencion
    resumen = analisis.resumen_direccion(contexto.gimnasio, contexto.evaluaciones,
                                         retencion.acciones)
    datos = resumen.indicadores
    columnas = st.columns(5)
    columnas[0].metric("Socios activos", datos["socios_activos"])
    columnas[1].metric("Socios en riesgo", datos["en_riesgo"],
                       informes.porcentaje(datos["porcentaje_en_riesgo"]), delta_color="off")
    columnas[2].metric("Ingresos en juego al mes", informes.euros(datos["ingresos_en_juego"]))
    columnas[3].metric("Ingresos en juego al año",
                       informes.euros(12 * datos["ingresos_en_juego"]))
    columnas[4].metric("Abandono mensual medio",
                       informes.porcentaje(datos["tasa_abandono_media"]))
    st.subheader("Bajas por mes")
    evolucion = resumen.evolucion.set_index(resumen.evolucion.index.strftime("%Y-%m"))
    st.bar_chart(evolucion["bajas"], x_label="Mes", y_label="Bajas")
    izquierda, derecha = st.columns(2)
    izquierda.subheader("Riesgo medio por tarifa")
    izquierda.bar_chart(resumen.por_tarifa["riesgo_medio"], x_label="Tarifa",
                        y_label="Riesgo medio")
    derecha.subheader("Socios retenidos por tipo de acción (%)")
    derecha.bar_chart(resumen.eficacia["tasa_retencion"], x_label="Acción",
                      y_label="Retenidos (%)")


def seccion_socios(contexto: Contexto) -> None:
    """Tabla filtrable de socios y ficha del socio elegido."""
    st.header("Socios en riesgo")
    st.write("Cada socio tiene un índice de 0 a 100 que suma señales de alerta. La tabla se "
             "puede ordenar pulsando en las columnas.")
    fecha = contexto.gimnasio.fecha_referencia.isoformat()
    st.caption(f"Los «días sin venir» se cuentan hasta la fecha de los datos ({fecha}).")
    filtro_tarifa, filtro_riesgo = st.columns(2)
    tarifas = filtro_tarifa.multiselect("Tarifas", TARIFAS, default=list(TARIFAS),
                                        key="tarifas")
    minimo = filtro_riesgo.slider("Riesgo mínimo", 0, 100, 0, key="riesgo_minimo")
    filtrada = analisis.filtrar_riesgo(analisis.tabla_riesgo(contexto.evaluaciones), tarifas,
                                       minimo)
    st.dataframe(filtrada[list(COLUMNAS_SOCIOS)].rename(columns=COLUMNAS_SOCIOS),
                 hide_index=True)
    if filtrada.empty:
        st.info("Ningún socio cumple los filtros.")
        return
    ficha_socio(contexto, filtrada["id_socio"].tolist())


def ficha_socio(contexto: Contexto, ids: list[int]) -> None:
    """Explicación del riesgo del socio elegido, señal a señal, y acción que procede."""
    por_id = {evaluacion.socio.id: evaluacion for evaluacion in contexto.evaluaciones}
    id_socio = st.selectbox("Socio", ids, key="socio",
                            format_func=lambda id_: describir_socio(por_id[id_]))
    evaluacion = por_id[id_socio]
    socio = evaluacion.socio
    st.subheader(f"Socio {socio.id}: {socio.nombre}")
    st.write(f"Tarifa {socio.tarifa}, {informes.euros(socio.cuota)} al mes, "
             f"alta el {socio.fecha_alta.isoformat()}.")
    st.markdown(f"**{evaluacion.explicacion}**")
    senales = analisis.tabla_senales(evaluacion)
    st.bar_chart(senales["puntos"], horizontal=True, x_label="Puntos", y_label="Señal")
    st.dataframe(senales.rename(columns={"puntos": "Puntos", "detalle": "Detalle"}))
    st.info(informes.accion_para(evaluacion, contexto.retencion.abierta_de(socio.id)))


def describir_socio(evaluacion: Evaluacion) -> str:
    """Texto de un socio en el desplegable: número, nombre y riesgo."""
    return f"{evaluacion.socio.id} · {evaluacion.socio.nombre} (riesgo {evaluacion.riesgo})"


def seccion_validacion(contexto: Contexto) -> None:
    """Backtesting del radar con el umbral elegido."""
    st.header("Validación del modelo")
    st.write(f"Una **fecha de corte** es un día del pasado en el que calculamos el riesgo como "
             f"si fuera hoy, usando solo lo que se sabía ese día: nada de información del "
             f"futuro. Después comprobamos quién se dio de baja de verdad en los "
             f"{HORIZONTE_DIAS} días siguientes. Así se mide cuánto acierta el radar.")
    opciones = contexto.opciones
    tabla, cortes = backtest(opciones.origen, opciones.semilla)
    resultado = resultado_desde_tabla(tabla, cortes, HORIZONTE_DIAS, opciones.umbral)
    st.write("Fechas de corte: " + ", ".join(corte.isoformat() for corte in cortes))
    metricas = resultado.metricas
    columnas = st.columns(4)
    columnas[0].metric("Precisión", informes.porcentaje(100 * metricas.precision),
                       help="De los socios avisados, cuántos se fueron de verdad.")
    columnas[1].metric("Recall", informes.porcentaje(100 * metricas.recall),
                       help="De los socios que se fueron, a cuántos avisamos antes.")
    columnas[2].metric("Tasa base", informes.porcentaje(100 * metricas.tasa_base),
                       help="Lo que acertaríamos avisando al azar.")
    columnas[3].metric("Mejor que el azar", f"{metricas.mejora:.1f} veces".replace(".", ","))
    st.subheader(f"Matriz de confusión (umbral {opciones.umbral})")
    st.dataframe(resultado.matriz)
    st.subheader("Barrido de umbrales")
    st.write("Un umbral bajo avisa a más socios y detecta más bajas, pero con más falsas "
             "alarmas; uno alto acierta más pero se le escapan más bajas.")
    porcentajes = (100 * resultado.barrido[["precision", "recall"]]).round(1)
    st.line_chart(porcentajes.rename(columns={"precision": "Precisión", "recall": "Recall"}),
                  x_label="Umbral", y_label="%")
    st.dataframe(resultado.barrido.assign(precision=porcentajes["precision"],
                                          recall=porcentajes["recall"]))


def seccion_acciones(contexto: Contexto) -> None:
    """Proponer, avanzar y guardar acciones de retención; eficacia de cada tipo."""
    st.header("Acciones de retención")
    st.write("A cada socio en riesgo se le propone la acción que corresponde a su causa "
             "principal: una llamada si ha dejado de venir, una clase gratis si va menos o es "
             "nuevo, un descuento si le subió la cuota y un cambio de tarifa si no tiene "
             "permanencia. No se avisa a todos los socios porque cada acción cuesta tiempo o "
             "dinero: el umbral concentra el esfuerzo en quien más probablemente se iría.")
    if st.button("Proponer acciones a los socios en riesgo", key="proponer"):
        con_errores(proponer, contexto)
    formulario_avanzar(contexto)
    st.subheader("Acciones abiertas")
    abiertas = analisis.tabla_acciones(contexto.retencion.abiertas)
    st.dataframe(abiertas[list(COLUMNAS_ACCIONES)].rename(columns=COLUMNAS_ACCIONES),
                 hide_index=True)
    st.subheader("Eficacia por tipo de acción")
    eficacia = analisis.eficacia_acciones(analisis.tabla_acciones(contexto.retencion.acciones))
    st.dataframe(eficacia)
    st.caption("Guardar escribe los socios, las visitas y las acciones en la carpeta datos/.")
    if st.button("Guardar en datos/", key="guardar"):
        con_errores(guardar, contexto)


def proponer(contexto: Contexto) -> None:
    """Registra una acción para cada socio en riesgo sin acción abierta."""
    nuevas = contexto.retencion.proponer_en_riesgo(contexto.evaluaciones,
                                                   contexto.gimnasio.fecha_referencia)
    st.success(f"Acciones nuevas: {len(nuevas)}.")


def formulario_avanzar(contexto: Contexto) -> None:
    """Formulario para pasar una acción abierta a otro estado."""
    abiertas = {accion.id: accion for accion in contexto.retencion.abiertas}
    if not abiertas:
        st.info("No hay acciones abiertas: pulsa «Proponer acciones» para crearlas.")
        return
    with st.form("avanzar"):
        st.subheader("Avanzar una acción")
        id_accion = st.selectbox(
            "Acción", list(abiertas), key="accion",
            format_func=lambda id_: f"{id_} · socio {abiertas[id_].id_socio}, "
                                    f"{abiertas[id_].tipo} ({abiertas[id_].estado})")
        estado = st.selectbox("Nuevo estado", ESTADOS_ACCION, key="estado_nuevo")
        enviado = st.form_submit_button("Cambiar estado")
    if enviado:
        con_errores(avanzar, contexto, id_accion, estado)


def avanzar(contexto: Contexto, id_accion: int, estado: str) -> None:
    """Cambia el estado de la acción; el modelo valida la transición."""
    accion = contexto.retencion.avanzar(id_accion, estado, contexto.gimnasio.fecha_referencia)
    st.success(f"La acción {accion.id} queda en {accion.estado}.")


def guardar(contexto: Contexto) -> None:
    """Guarda los datos y las acciones de la sesión en la carpeta de datos."""
    almacen.guardar(CARPETA_DATOS, contexto.gimnasio, contexto.retencion.acciones)
    cargar_datos.clear()
    st.success(f"Datos guardados en {CARPETA_DATOS}.")


SECCIONES: dict[str, Callable[[Contexto], None]] = {
    "Resumen para la dirección": seccion_resumen,
    "Socios en riesgo": seccion_socios,
    "Validación del modelo": seccion_validacion,
    "Acciones de retención": seccion_acciones,
}


# --- Página ------------------------------------------------------------------

def mostrar(opciones: Opciones) -> None:
    """Carga los datos y dibuja la sección elegida."""
    gimnasio, acciones = cargar_datos(opciones.origen, opciones.semilla)
    contexto = Contexto(gimnasio, evaluar(opciones.origen, opciones.semilla, opciones.umbral),
                        retencion_de_sesion(opciones, acciones), opciones)
    st.caption(f"Datos hasta {gimnasio.fecha_referencia.isoformat()} · "
               f"{len(gimnasio.socios)} socios · umbral de riesgo {opciones.umbral}")
    SECCIONES[opciones.seccion](contexto)


def main() -> None:
    """Dibuja la página completa."""
    st.set_page_config(page_title="Radar de Bajas", page_icon="📉", layout="wide")
    con_errores(mostrar, barra_lateral())


if __name__ == "__main__":
    main()
