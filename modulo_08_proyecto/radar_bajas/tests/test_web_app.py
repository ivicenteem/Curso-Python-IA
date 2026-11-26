"""Tests de la interfaz web con ``streamlit.testing``. Se saltan si Streamlit no está instalado."""

from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

RUTA_WEB = Path(__file__).parent.parent / "web_app.py"
SECCIONES = ["Resumen para la dirección", "Socios en riesgo", "Validación del modelo",
             "Acciones de retención"]


@pytest.fixture
def web() -> AppTest:
    """La web arrancada con los datos guardados de ejemplo."""
    app = AppTest.from_file(str(RUTA_WEB), default_timeout=120)
    return app.run()


def metrica(app: AppTest, etiqueta: str) -> str:
    """Valor de la métrica con esa etiqueta."""
    return next(elemento.value for elemento in app.metric if elemento.label == etiqueta)


def test_arranca_sin_excepciones(web):
    assert not web.exception
    assert not web.error
    assert web.header[0].value == SECCIONES[0]


@pytest.mark.parametrize("seccion", SECCIONES)
def test_cada_seccion_se_dibuja(web, seccion):
    web.sidebar.radio(key="seccion").set_value(seccion).run()
    assert not web.exception
    assert not web.error
    assert web.header[0].value == seccion


def test_el_umbral_cambia_los_socios_en_riesgo(web):
    con_umbral_40 = int(metrica(web, "Socios en riesgo"))
    web.sidebar.slider(key="umbral").set_value(20).run()
    assert int(metrica(web, "Socios en riesgo")) > con_umbral_40


def test_la_validacion_reacciona_al_umbral(web):
    web.sidebar.radio(key="seccion").set_value("Validación del modelo").run()
    precision_40 = metrica(web, "Precisión")
    web.sidebar.slider(key="umbral").set_value(60).run()
    assert metrica(web, "Precisión") != precision_40


def test_transicion_no_permitida_muestra_un_error(web):
    web.sidebar.radio(key="seccion").set_value("Acciones de retención").run()
    web.button(key="proponer").click().run()
    assert "Acciones nuevas:" in web.success[0].value
    web.selectbox(key="estado_nuevo").set_value("retenido")
    next(boton for boton in web.button if boton.label == "Cambiar estado").click().run()
    assert not web.exception
    assert "No se puede pasar de propuesta a retenido" in web.error[0].value


def test_transicion_permitida(web):
    web.sidebar.radio(key="seccion").set_value("Acciones de retención").run()
    web.button(key="proponer").click().run()
    web.selectbox(key="estado_nuevo").set_value("contactado")
    next(boton for boton in web.button if boton.label == "Cambiar estado").click().run()
    assert any("queda en contactado" in mensaje.value for mensaje in web.success)


def test_simular_con_otra_semilla(web):
    web.sidebar.radio(key="origen").set_value("Simular con una semilla").run()
    web.sidebar.number_input(key="semilla").set_value(7).run()
    assert not web.exception
    assert int(metrica(web, "Socios activos")) > 0
