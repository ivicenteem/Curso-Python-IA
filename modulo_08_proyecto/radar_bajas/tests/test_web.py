"""Tests de la web con el ``TestClient`` de FastAPI. Se saltan sin las dependencias de la web."""

import re
import shutil
from pathlib import Path

import pytest

from radar import almacen

pytest.importorskip("multipart")
TestClient = pytest.importorskip("fastapi.testclient").TestClient
crear_app = pytest.importorskip("web.app").crear_app

CARPETA_EJEMPLO = Path(__file__).parent.parent / "datos"
ULTIMA_FECHA = "2026-10-31"


@pytest.fixture
def carpeta(tmp_path) -> Path:
    """Copia de los datos de ejemplo (semilla 42) que los tests pueden sobrescribir."""
    destino = tmp_path / "datos"
    shutil.copytree(CARPETA_EJEMPLO, destino, ignore=shutil.ignore_patterns("graficos"))
    return destino


@pytest.fixture
def cliente(carpeta) -> TestClient:
    """Cliente de la web con la copia de los datos de ejemplo."""
    return TestClient(crear_app(carpeta))


def en_riesgo(html: str) -> int:
    """Número de la tarjeta «Socios en riesgo» del resumen."""
    return int(re.search(r'Socios en riesgo</span>\s*<span class="metrica-valor">(\d+)',
                         html).group(1))


def avisos(html: str, tipo: str) -> list[str]:
    """Textos de los avisos de un tipo ("ok" o "error") que muestra la página."""
    return [texto.strip() for texto in
            re.findall(rf'class="aviso aviso-{tipo}"[^>]*>(.*?)</div>', html, re.S)]


def ajustar(cliente: TestClient, umbral: int = 40, fecha: str = ULTIMA_FECHA,
            volver: str = "/") -> str:
    """Envía el formulario de la barra lateral y devuelve la página resultante."""
    return cliente.post("/ajustes", data={"umbral": umbral, "fecha": fecha,
                                          "volver": volver}).text


# --- Páginas -----------------------------------------------------------------

@pytest.mark.parametrize("ruta, texto", [
    ("/", "Resumen para la dirección"),
    ("/socios", "Lucía García"),
    ("/socios/110", "Riesgo 70: 38 días sin venir; asistencia -100 %; tarifa mensual"),
    ("/validacion", "Matriz de confusión"),
    ("/retencion", "Acciones de retención"),
    ("/datos", "Origen de los datos"),
])
def test_cada_pagina_responde(cliente, ruta, texto):
    respuesta = cliente.get(ruta)
    assert respuesta.status_code == 200
    assert texto in respuesta.text
    assert not avisos(respuesta.text, "error")


def test_recursos_estaticos_sin_internet(cliente):
    html = cliente.get("/").text
    assert 'src="/static/js/chart.umd.min.js"' in html
    assert "http://" not in html.split("<body>")[0] and "https://" not in html
    assert cliente.get("/static/js/chart.umd.min.js").status_code == 200
    assert cliente.get("/static/css/estilo.css").status_code == 200


def test_resumen_con_las_cifras_de_la_semilla_42(cliente):
    html = cliente.get("/").text
    assert en_riesgo(html) == 6
    assert "265,00 €" in html and "3.180,00 €" in html


# --- Umbral y fecha de análisis ----------------------------------------------

def test_cambiar_el_umbral_cambia_los_socios_en_riesgo(cliente):
    con_40 = en_riesgo(cliente.get("/").text)
    html = ajustar(cliente, umbral=30)
    assert en_riesgo(html) > con_40
    assert "Umbral 30" in html


def test_cambiar_la_fecha_cambia_los_socios_en_riesgo(cliente):
    con_ultima = en_riesgo(cliente.get("/").text)
    html = ajustar(cliente, fecha="2026-06-15")
    assert en_riesgo(html) != con_ultima
    assert "A fecha de 15/06/2026" in html


def test_la_fecha_se_aplica_a_todas_las_secciones(cliente):
    ajustar(cliente, fecha="2026-06-15")
    assert "(15/06/2026)" in cliente.get("/socios").text
    assert "01/05/2026" in cliente.get("/validacion?cortes=3").text


def test_fecha_fuera_de_rango_muestra_el_error(cliente):
    html = ajustar(cliente, fecha="2027-01-01")
    assert any("La fecha de análisis debe estar entre" in aviso for aviso in avisos(html, "error"))


def test_ajustes_no_redirigen_fuera_de_la_web(cliente):
    respuesta = cliente.post("/ajustes", data={"umbral": 40, "fecha": ULTIMA_FECHA,
                                               "volver": "https://ejemplo.com/"},
                             follow_redirects=False)
    assert respuesta.headers["location"] == "/"


# --- Socios ------------------------------------------------------------------

@pytest.mark.parametrize("consulta, esperado, ausente", [
    ("q=lucía", "Lucía García", "Paula Castro"),
    ("q=110", "Lucía García", "Paula Castro"),
    ("tarifa=anual", "anual", "Lucía García"),
    ("minimo=60", "Pablo García", "Javier Ruiz"),
])
def test_buscador_y_filtros(cliente, consulta, esperado, ausente):
    html = cliente.get(f"/socios?{consulta}").text
    assert esperado in html
    assert ausente not in html


def test_ficha_de_socio_dado_de_baja_muestra_aviso_sin_traza(cliente, carpeta):
    gimnasio, _ = almacen.cargar(carpeta)
    baja = next(socio.id for socio in gimnasio.socios.values() if not socio.activo)
    respuesta = cliente.get(f"/socios/{baja}")
    assert respuesta.status_code == 400
    assert f"El socio {baja} no estaba dado de alta" in avisos(respuesta.text, "error")[0]
    assert "Traceback" not in respuesta.text


# --- Validación --------------------------------------------------------------

@pytest.mark.parametrize("cortes, horizonte", [(3, 15), (6, 30), (8, 60)])
def test_validacion_responde_a_cortes_y_horizonte(cliente, cortes, horizonte):
    html = cliente.get(f"/validacion?cortes={cortes}&horizonte={horizonte}").text
    assert html.count('class="chip"') == cortes
    assert f"en los\n    {horizonte} días siguientes" in html


def test_validacion_sin_historial_suficiente(cliente):
    respuesta = cliente.get("/validacion?cortes=10&horizonte=60")
    assert respuesta.status_code == 400
    assert "No hay historial para 10 cortes" in avisos(respuesta.text, "error")[0]


def test_validacion_reacciona_al_umbral(cliente):
    assert "30,8 %" in cliente.get("/validacion").text
    assert "46,3 %" in ajustar(cliente, umbral=50, volver="/validacion")


# --- Retención ---------------------------------------------------------------

def test_proponer_y_transicion_no_permitida(cliente):
    html = cliente.post("/retencion/proponer").text
    assert "Acciones nuevas: 6." in avisos(html, "ok")
    html = cliente.post("/retencion/avanzar", data={"id_accion": 54, "estado": "retenido"}).text
    assert "No se puede pasar de propuesta a retenido" in avisos(html, "error")[0]
    html = cliente.post("/retencion/avanzar", data={"id_accion": 54, "estado": "contactado"}).text
    assert "La acción 54 queda en contactado." in avisos(html, "ok")


def test_avanzar_accion_inexistente(cliente):
    html = cliente.post("/retencion/avanzar", data={"id_accion": 999, "estado": "perdido"}).text
    assert avisos(html, "error") == ["No existe la acción 999"]


# --- Datos -------------------------------------------------------------------

def test_subir_csv_incorrecto_indica_fichero_y_linea(cliente, carpeta):
    socios = (carpeta / "socios.csv").read_text(encoding="utf-8").splitlines()
    socios[2] = socios[2].replace("trimestral", "semanal").replace("anual", "semanal")
    html = cliente.post("/datos/subir", files={
        "socios": ("socios.csv", "\n".join(socios).encode("utf-8"), "text/csv")}).text
    assert "socios.csv, línea 3" in avisos(html, "error")[0]


def test_subir_csv_correcto(cliente, carpeta):
    ficheros = {nombre: (f"{nombre}.csv", (carpeta / f"{nombre}.csv").read_bytes(), "text/csv")
                for nombre in ("socios", "visitas", "acciones")}
    html = cliente.post("/datos/subir", files=ficheros).text
    assert "Cargados 300 socios de los ficheros subidos." in avisos(html, "ok")


def test_simular_con_otra_semilla(cliente):
    html = cliente.post("/datos/simular", data={"semilla": 7}).text
    assert "Simulados 300 socios con la semilla 7." in avisos(html, "ok")
    assert "simulación con semilla 7" in html


def test_alta_visita_y_baja(cliente):
    html = cliente.post("/datos/socios", data={"nombre": "Nuevo Socio", "fecha_alta": "2026-10-01",
                                               "tarifa": "mensual", "cuota": 45}).text
    assert "Alta del socio 301: Nuevo Socio." in avisos(html, "ok")
    html = cliente.post("/datos/visitas", data={"id_socio": 301, "fecha": "2026-10-05"}).text
    assert "Visita del socio 301 apuntada el 2026-10-05." in avisos(html, "ok")
    html = cliente.post("/datos/bajas", data={"id_socio": 301, "fecha": "2026-10-20"}).text
    assert "Baja del socio 301 registrada el 2026-10-20." in avisos(html, "ok")
    html = cliente.post("/datos/visitas", data={"id_socio": 301, "fecha": "2026-10-25"}).text
    assert "no estaba dado de alta" in avisos(html, "error")[0]


@pytest.mark.parametrize("ruta, datos, mensaje", [
    ("/datos/bajas", {"id_socio": 110, "fecha": "2020-01-01"}, "anterior al alta"),
    ("/datos/socios", {"nombre": " ", "fecha_alta": ULTIMA_FECHA, "tarifa": "mensual",
                       "cuota": 45}, "El nombre es obligatorio"),
    ("/datos/visitas", {"id_socio": 999, "fecha": ULTIMA_FECHA}, "No existe el socio 999"),
])
def test_operaciones_de_datos_no_validas(cliente, ruta, datos, mensaje):
    html = cliente.post(ruta, data=datos).text
    assert mensaje in avisos(html, "error")[0]


def test_descargar_csv(cliente):
    respuesta = cliente.get("/datos/descargar/socios.csv")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/csv")
    assert respuesta.text.startswith("id,nombre,fecha_alta,tarifa")
    assert cliente.get("/datos/descargar/otro.csv").status_code == 404


def test_guardar_pide_confirmacion(cliente, carpeta):
    cliente.post("/retencion/proponer")
    html = cliente.post("/datos/guardar", data={}).text
    assert "Marca la casilla de confirmación" in avisos(html, "error")[0]
    html = cliente.post("/datos/guardar", data={"confirmar": "si"}).text
    assert "Datos guardados en datos/." in avisos(html, "ok")
    assert "propuesta" in (carpeta / "acciones.csv").read_text(encoding="utf-8")


def test_sin_datos(tmp_path):
    cliente = TestClient(crear_app(tmp_path / "vacia"))
    respuesta = cliente.get("/")
    assert respuesta.status_code == 400
    assert "No hay datos" in avisos(respuesta.text, "error")[0]
    assert cliente.get("/datos").status_code == 200


def test_datos_corruptos_al_arrancar(tmp_path):
    (tmp_path / "socios.csv").write_text("id,nombre\n1,Ada\n", encoding="utf-8")
    html = TestClient(crear_app(tmp_path)).get("/datos").text
    assert "faltan las columnas" in avisos(html, "error")[0]
