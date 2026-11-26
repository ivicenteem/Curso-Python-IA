"""Rutas de la web de Radar de Bajas (FastAPI y plantillas Jinja2).

Es una capa de presentación, igual que ``radar_app.py``: recoge lo que pide el
usuario, llama al paquete ``radar`` y pinta el resultado. Los errores de la
aplicación (``ErrorRadar``) se muestran como avisos en la página.

Para arrancarla, desde la raíz del repositorio:

    python modulo_08_proyecto/radar_bajas/web
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import pandas as pd
from fastapi import APIRouter, FastAPI, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from radar import almacen, analisis, informes
from radar.excepciones import DatosNoValidos, ErrorRadar
from radar.modelos import ESTADOS_ACCION, TARIFAS, AccionRetencion, Gimnasio
from radar.radar import UMBRAL_RIESGO, Evaluacion, Radar, comprobar_fecha, rango_de_fechas
from radar.retencion import GestorRetencion
from radar.simulador import SEMILLA, simular, simular_acciones
from radar.validacion import (CORTES_MAXIMO, CORTES_MINIMO, HORIZONTE_DIAS, HORIZONTES_DIAS,
                              NUMERO_CORTES, validar)

CARPETA_WEB = Path(__file__).parent
CARPETA_DATOS = CARPETA_WEB.parent / "datos"
UMBRAL_MINIMO, UMBRAL_MAXIMO = 20, 80
CODIFICACION_CSV = "utf-8-sig"      # acepta también los CSV con BOM que guarda Excel

# Nombres legibles de las señales y de los tipos de acción
ETIQUETAS = {
    "dias_sin_venir": "Días sin venir", "caida_asistencia": "Caída de asistencia",
    "antiguedad": "Antigüedad", "tarifa": "Tarifa", "subida_cuota": "Subida de cuota",
    "llamada": "Llamada", "descuento": "Descuento", "clase_gratis": "Clase gratis",
    "cambio_tarifa": "Cambio de tarifa",
}


def etiqueta(clave: str) -> str:
    """Nombre legible de una señal o un tipo de acción."""
    return ETIQUETAS.get(clave, clave)


def entero(numero: int) -> str:
    """Entero con punto de miles, por ejemplo "20.297"."""
    return f"{numero:,}".replace(",", ".")


plantillas = Jinja2Templates(directory=CARPETA_WEB / "templates")
plantillas.env.filters |= {"euros": informes.euros, "porcentaje": informes.porcentaje,
                           "tasa": informes.texto_tasa, "etiqueta": etiqueta, "entero": entero}
rutas = APIRouter()


@dataclass(frozen=True)
class Mensaje:
    """Aviso que se muestra una vez en la siguiente página."""

    tipo: str
    texto: str


@dataclass
class Sesion:
    """Estado de la web: los datos cargados, las acciones y los ajustes elegidos."""

    carpeta: Path
    gimnasio: Gimnasio
    retencion: GestorRetencion
    origen: str
    umbral: int = UMBRAL_RIESGO
    fecha: date | None = None
    mensajes: list[Mensaje] = field(default_factory=list)

    @property
    def radar(self) -> Radar:
        """Radar con las señales por defecto y el umbral elegido."""
        return Radar.por_defecto(self.umbral)

    @property
    def fecha_analisis(self) -> date:
        """Fecha elegida o, si no se ha elegido, la última de los datos."""
        return self.fecha or self.gimnasio.fecha_referencia

    def evaluaciones(self) -> list[Evaluacion]:
        """Riesgo de los socios activos en la fecha de análisis."""
        return self.radar.evaluar_todos(self.gimnasio, self.fecha_analisis)

    def cambiar_datos(self, gimnasio: Gimnasio, acciones: list[AccionRetencion],
                      origen: str) -> None:
        """Sustituye los datos y vuelve a analizar en la última fecha."""
        self.gimnasio, self.retencion, self.origen = gimnasio, GestorRetencion(acciones), origen
        self.fecha = None

    def avisar(self, texto: str, tipo: str = "ok") -> None:
        """Guarda un aviso para la siguiente página."""
        self.mensajes.append(Mensaje(tipo, texto))

    def recoger_mensajes(self) -> list[Mensaje]:
        """Devuelve los avisos pendientes y los olvida."""
        mensajes, self.mensajes = self.mensajes, []
        return mensajes


# --- Utilidades de presentación ----------------------------------------------

def sesion_de(request: Request) -> Sesion:
    """Sesión de la aplicación que atiende la petición."""
    return request.app.state.sesion


def barra_lateral(sesion: Sesion) -> dict[str, object]:
    """Datos de la barra lateral: umbral, fecha de análisis y su rango."""
    barra: dict[str, object] = {"umbral": sesion.umbral, "minimo": UMBRAL_MINIMO,
                                "maximo": UMBRAL_MAXIMO, "hay_datos": not sesion.gimnasio.vacio,
                                "origen": sesion.origen}
    if not sesion.gimnasio.vacio:
        primera, ultima = rango_de_fechas(sesion.gimnasio)
        barra |= {"fecha": sesion.fecha_analisis, "primera": primera, "ultima": ultima}
    return barra


def pagina(request: Request, plantilla: str, seccion: str, codigo: int = 200,
           **datos: object) -> HTMLResponse:
    """Pinta una plantilla con la barra lateral y los avisos pendientes."""
    sesion = sesion_de(request)
    contexto = {"seccion": seccion, "barra": barra_lateral(sesion),
                "mensajes": sesion.recoger_mensajes(), **datos}
    return plantillas.TemplateResponse(request, plantilla, contexto, status_code=codigo)


def grafico(etiquetas: list[str], *series: pd.Series, sufijo: str = "") -> dict[str, object]:
    """Datos de un gráfico para Chart.js; los valores ausentes van como ``None``."""
    return {
        "etiquetas": [str(etiqueta) for etiqueta in etiquetas],
        "series": [{"nombre": str(serie.name),
                    "valores": serie.astype(object).where(serie.notna(), None).tolist()}
                   for serie in series],
        "sufijo": sufijo,
    }


def volver_a(destino: str) -> RedirectResponse:
    """Redirige a una ruta interna de la web (nunca a otra web)."""
    partes = urlsplit(destino)
    interno = destino.startswith("/") and not destino.startswith("//") and not partes.netloc
    return RedirectResponse(destino if interno else "/", status_code=303)


def a_registros(tabla: pd.DataFrame) -> list[dict[str, object]]:
    """Filas de una tabla como diccionarios para la plantilla."""
    return tabla.reset_index().to_dict("records")


async def leer_subido(fichero: UploadFile | None) -> str:
    """Contenido de texto de un fichero subido; vacío si no se ha elegido ninguno."""
    if fichero is None:
        return ""
    return (await fichero.read()).decode(CODIFICACION_CSV, errors="replace")


# --- Errores -----------------------------------------------------------------

async def mostrar_error(request: Request, error: ErrorRadar) -> Response:
    """Muestra un error de la aplicación como aviso, nunca como traza.

    En una página, pinta el aviso con un código 400. En un formulario, vuelve
    a la página de la que venía el usuario con el aviso arriba.
    """
    sesion_de(request).avisar(str(error), "error")
    if request.method == "GET":
        return pagina(request, "aviso.html", seccion_de(request.url.path), codigo=400)
    origen = request.headers.get("referer", "")
    respaldo = request.url.path.rsplit("/", 1)[0] or "/"
    return volver_a(urlsplit(origen)._replace(scheme="", netloc="").geturl() or respaldo)


def seccion_de(ruta: str) -> str:
    """Sección de la barra lateral a la que pertenece una ruta."""
    primera = ruta.strip("/").split("/")[0]
    return primera if primera in {"socios", "validacion", "retencion", "datos"} else "resumen"


# --- Ajustes -----------------------------------------------------------------

@rutas.post("/ajustes")
def ajustar(request: Request, umbral: Annotated[int, Form()], fecha: Annotated[date, Form()],
            volver: Annotated[str, Form()] = "/") -> RedirectResponse:
    """Cambia el umbral de riesgo y la fecha de análisis de todas las secciones."""
    sesion = sesion_de(request)
    sesion.umbral = Radar.por_defecto(umbral).umbral
    sesion.fecha = comprobar_fecha(sesion.gimnasio, fecha)
    return volver_a(volver)


# --- Resumen -----------------------------------------------------------------

@rutas.get("/", response_class=HTMLResponse)
def resumen(request: Request) -> HTMLResponse:
    """Resumen para la dirección a la fecha de análisis."""
    sesion = sesion_de(request)
    datos = analisis.resumen_direccion(sesion.gimnasio, sesion.evaluaciones(),
                                       sesion.retencion.acciones, sesion.fecha_analisis)
    evolucion = datos.evolucion
    graficos = {
        "bajas": grafico(evolucion.index.strftime("%m/%y").tolist(),
                         evolucion["bajas"].rename("Bajas")),
        "tarifa": grafico(datos.por_tarifa.index.tolist(),
                          datos.por_tarifa["riesgo_medio"].rename("Riesgo medio")),
        "eficacia": grafico(datos.eficacia.index.map(etiqueta).tolist(),
                            datos.eficacia["tasa_retencion"].rename("Retenidos"), sufijo=" %"),
    }
    return pagina(request, "resumen.html", "resumen", resumen=datos,
                  indicadores=datos.indicadores, graficos=graficos)


# --- Socios ------------------------------------------------------------------

@rutas.get("/socios", response_class=HTMLResponse)
def socios(request: Request, q: str = "",
           tarifa: Annotated[list[str] | None, Query()] = None,
           minimo: Annotated[int, Query(ge=0, le=100)] = 0) -> HTMLResponse:
    """Tabla de socios con buscador y filtros."""
    tarifas = tarifa or list(TARIFAS)
    riesgo = analisis.tabla_riesgo(sesion_de(request).evaluaciones())
    filtrada = analisis.filtrar_riesgo(riesgo, tarifas, minimo, q)
    return pagina(request, "socios.html", "socios", filas=filtrada.to_dict("records"),
                  total=len(riesgo), q=q, tarifas=tarifas, todas_tarifas=TARIFAS,
                  minimo=minimo)


@rutas.get("/socios/{id_socio}", response_class=HTMLResponse)
def ficha(request: Request, id_socio: int) -> HTMLResponse:
    """Ficha de un socio: su riesgo explicado, la acción que procede y sus visitas."""
    sesion = sesion_de(request)
    evaluacion = sesion.radar.evaluar_socio(sesion.gimnasio, id_socio, sesion.fecha_analisis)
    senales = analisis.tabla_senales(evaluacion)
    visitas = analisis.visitas_por_mes(sesion.gimnasio, id_socio, sesion.fecha_analisis)
    graficos = {
        "senales": grafico(senales.index.map(etiqueta).tolist(),
                           senales["puntos"].rename("Puntos")),
        "visitas": grafico(visitas.index.strftime("%m/%y").tolist(), visitas.rename("Visitas")),
    }
    accion = informes.accion_para(evaluacion, sesion.retencion.abierta_de(id_socio))
    return pagina(request, "socio.html", "socios", evaluacion=evaluacion,
                  senales=a_registros(senales), accion=accion, graficos=graficos)


# --- Validación --------------------------------------------------------------

@rutas.get("/validacion", response_class=HTMLResponse)
def validacion(request: Request,
               cortes: Annotated[int, Query(ge=CORTES_MINIMO, le=CORTES_MAXIMO)] = NUMERO_CORTES,
               horizonte: int = HORIZONTE_DIAS) -> HTMLResponse:
    """Backtesting del radar con los cortes y el horizonte elegidos."""
    sesion = sesion_de(request)
    resultado = validar(sesion.gimnasio, sesion.radar, horizonte, cortes, sesion.fecha_analisis)
    barrido = resultado.barrido
    grafico_barrido = grafico(barrido.index.tolist(),
                              (100 * barrido["precision"]).round(1).rename("Precisión"),
                              (100 * barrido["recall"]).round(1).rename("Recall"), sufijo=" %")
    return pagina(request, "validacion.html", "validacion", resultado=resultado,
                  matriz=a_registros(resultado.matriz), barrido=a_registros(barrido),
                  grafico_barrido=grafico_barrido, cortes=cortes, horizonte=horizonte,
                  opciones_cortes=range(CORTES_MINIMO, CORTES_MAXIMO + 1),
                  opciones_horizonte=HORIZONTES_DIAS)


# --- Retención ---------------------------------------------------------------

@rutas.get("/retencion", response_class=HTMLResponse)
def retencion(request: Request) -> HTMLResponse:
    """Acciones abiertas, formulario para avanzarlas y eficacia por tipo."""
    sesion = sesion_de(request)
    acciones = analisis.tabla_acciones(sesion.retencion.acciones)
    eficacia = analisis.eficacia_acciones(analisis.acciones_hasta(acciones,
                                                                  sesion.fecha_analisis))
    return pagina(request, "retencion.html", "retencion", abiertas=sesion.retencion.abiertas,
                  estados=ESTADOS_ACCION, eficacia=a_registros(eficacia),
                  en_riesgo=sum(evaluacion.en_riesgo for evaluacion in sesion.evaluaciones()))


@rutas.post("/retencion/proponer")
def proponer(request: Request) -> RedirectResponse:
    """Propone una acción a cada socio en riesgo que no tenga una abierta."""
    sesion = sesion_de(request)
    nuevas = sesion.retencion.proponer_en_riesgo(sesion.evaluaciones(), sesion.fecha_analisis)
    sesion.avisar(f"Acciones nuevas: {len(nuevas)}.")
    return volver_a("/retencion")


@rutas.post("/retencion/avanzar")
def avanzar(request: Request, id_accion: Annotated[int, Form()],
            estado: Annotated[str, Form()]) -> RedirectResponse:
    """Cambia el estado de una acción; el modelo valida la transición."""
    sesion = sesion_de(request)
    accion = sesion.retencion.avanzar(id_accion, estado, sesion.fecha_analisis)
    sesion.avisar(f"La acción {accion.id} queda en {accion.estado}.")
    return volver_a("/retencion")


# --- Datos -------------------------------------------------------------------

@rutas.get("/datos", response_class=HTMLResponse)
def datos(request: Request) -> HTMLResponse:
    """Origen de los datos, altas, visitas, bajas, descargas y guardado."""
    gimnasio = sesion_de(request).gimnasio
    return pagina(request, "datos.html", "datos", gimnasio=gimnasio, tarifas=TARIFAS,
                  semilla=SEMILLA, ficheros=[almacen.FICHERO_SOCIOS, almacen.FICHERO_VISITAS,
                                             almacen.FICHERO_ACCIONES])


@rutas.post("/datos/cargar")
def cargar(request: Request) -> RedirectResponse:
    """Carga los datos guardados en la carpeta datos/."""
    sesion = sesion_de(request)
    sesion.cambiar_datos(*almacen.cargar(sesion.carpeta), "datos guardados")
    sesion.avisar(f"Cargados {len(sesion.gimnasio.socios)} socios de {sesion.carpeta.name}/.")
    return volver_a("/datos")


@rutas.post("/datos/simular")
def simular_datos(request: Request, semilla: Annotated[int, Form(ge=0)]) -> RedirectResponse:
    """Sustituye los datos por otros simulados con la semilla elegida."""
    sesion = sesion_de(request)
    gimnasio = simular(semilla=semilla)
    sesion.cambiar_datos(gimnasio, simular_acciones(gimnasio, Radar.por_defecto()).acciones,
                         f"simulación con semilla {semilla}")
    sesion.avisar(f"Simulados {len(gimnasio.socios)} socios con la semilla {semilla}.")
    return volver_a("/datos")


@rutas.post("/datos/subir")
async def subir(request: Request, socios: UploadFile, visitas: UploadFile | None = None,
                acciones: UploadFile | None = None) -> RedirectResponse:
    """Carga los CSV que sube el usuario; el almacén los valida fila a fila."""
    sesion = sesion_de(request)
    textos = [await leer_subido(fichero) for fichero in (socios, visitas, acciones)]
    sesion.cambiar_datos(*almacen.cargar_textos(*textos), "ficheros subidos")
    sesion.avisar(f"Cargados {len(sesion.gimnasio.socios)} socios de los ficheros subidos.")
    return volver_a("/datos")


@rutas.post("/datos/socios")
def alta(request: Request, nombre: Annotated[str, Form()], fecha_alta: Annotated[date, Form()],
         tarifa: Annotated[str, Form()], cuota: Annotated[float, Form()]) -> RedirectResponse:
    """Da de alta un socio nuevo."""
    socio = sesion_de(request).gimnasio.dar_de_alta(nombre, fecha_alta, tarifa, cuota)
    sesion_de(request).avisar(f"Alta del socio {socio.id}: {socio.nombre}.")
    return volver_a("/datos")


@rutas.post("/datos/visitas")
def visita(request: Request, id_socio: Annotated[int, Form()],
           fecha: Annotated[date, Form()]) -> RedirectResponse:
    """Apunta una visita de un socio."""
    sesion_de(request).gimnasio.registrar_visita(id_socio, fecha)
    sesion_de(request).avisar(f"Visita del socio {id_socio} apuntada el {fecha.isoformat()}.")
    return volver_a("/datos")


@rutas.post("/datos/bajas")
def baja(request: Request, id_socio: Annotated[int, Form()],
         fecha: Annotated[date, Form()]) -> RedirectResponse:
    """Registra la baja de un socio."""
    sesion_de(request).gimnasio.registrar_baja(id_socio, fecha)
    sesion_de(request).avisar(f"Baja del socio {id_socio} registrada el {fecha.isoformat()}.")
    return volver_a("/datos")


@rutas.get("/datos/descargar/{nombre}")
def descargar(request: Request, nombre: str) -> Response:
    """Descarga uno de los CSV con los datos actuales."""
    sesion = sesion_de(request)
    textos = almacen.textos_csv(sesion.gimnasio, sesion.retencion.acciones)
    if nombre not in textos:
        raise HTTPException(status_code=404, detail="Fichero desconocido")
    return Response(textos[nombre], media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@rutas.post("/datos/guardar")
def guardar(request: Request, confirmar: Annotated[str, Form()] = "") -> RedirectResponse:
    """Guarda los datos actuales en datos/, sobrescribiendo lo que hubiera."""
    sesion = sesion_de(request)
    if confirmar != "si":
        raise DatosNoValidos("Marca la casilla de confirmación para sobrescribir datos/")
    almacen.guardar(sesion.carpeta, sesion.gimnasio, sesion.retencion.acciones)
    sesion.avisar(f"Datos guardados en {sesion.carpeta.name}/.")
    return volver_a("/datos")


# --- Aplicación --------------------------------------------------------------

def sesion_inicial(carpeta: Path) -> Sesion:
    """Sesión con los datos de ``carpeta``; si no se pueden leer, vacía y con el aviso."""
    try:
        gimnasio, acciones = almacen.cargar(carpeta)
    except ErrorRadar as error:
        sesion = Sesion(carpeta, Gimnasio(), GestorRetencion(), "sin datos")
        sesion.avisar(str(error), "error")
        return sesion
    return Sesion(carpeta, gimnasio, GestorRetencion(acciones), "datos guardados")


def crear_app(carpeta: Path = CARPETA_DATOS) -> FastAPI:
    """Crea la aplicación web con los datos de ``carpeta``."""
    app = FastAPI(title="Radar de Bajas", docs_url=None, redoc_url=None)
    app.state.sesion = sesion_inicial(Path(carpeta))
    app.mount("/static", StaticFiles(directory=CARPETA_WEB / "static"), name="static")
    app.include_router(rutas)
    app.add_exception_handler(ErrorRadar, mostrar_error)
    return app
