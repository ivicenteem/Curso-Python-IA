"""Tests de la lógica añadida para la web: operaciones sobre los datos, fecha de análisis,
validación configurable y CSV como texto."""

import copy
from datetime import date

import pandas as pd
import pytest

from radar import almacen, analisis
from radar.excepciones import DatosNoValidos, ErrorDeAlmacen, SinDatos, SocioNoEncontrado
from radar.modelos import AccionRetencion, Gimnasio, Socio, Visita
from radar.radar import DIAS_HISTORIAL_MINIMO, Radar, comprobar_fecha, rango_de_fechas
from radar.validacion import cortes_por_defecto, validar

ALTA = date(2026, 1, 10)


@pytest.fixture
def pequeno() -> Gimnasio:
    """Gimnasio con dos socios y tres visitas, que cada test puede modificar."""
    socios = [Socio(1, "Ada", ALTA, "mensual", 45.0), Socio(2, "Bea", ALTA, "anual", 35.0)]
    visitas = [Visita(1, date(2026, 2, 1)), Visita(1, date(2026, 3, 1)),
               Visita(2, date(2026, 2, 5))]
    return Gimnasio.desde_listas(socios, visitas)


@pytest.fixture
def copia(gimnasio) -> Gimnasio:
    """Copia del gimnasio simulado que se puede modificar sin afectar a otros tests."""
    return copy.deepcopy(gimnasio)


# --- Altas, visitas y bajas --------------------------------------------------

def test_dar_de_alta_usa_el_siguiente_identificador(pequeno):
    socio = pequeno.dar_de_alta("  Cris ", date(2026, 3, 2), "trimestral", 40.0)
    assert (socio.id, socio.nombre) == (3, "Cris")
    assert pequeno.socio(3) is socio


def test_dar_de_alta_valida_los_datos(pequeno):
    with pytest.raises(DatosNoValidos):
        pequeno.dar_de_alta("Cris", date(2026, 3, 2), "semanal", 40.0)
    assert len(pequeno.socios) == 2


def test_registrar_visita_la_ordena_y_actualiza_la_agrupacion(pequeno):
    assert pequeno.visitas_por_socio[1] == [date(2026, 2, 1), date(2026, 3, 1)]
    pequeno.registrar_visita(1, date(2026, 2, 15))
    assert pequeno.visitas_por_socio[1] == [date(2026, 2, 1), date(2026, 2, 15), date(2026, 3, 1)]
    assert pequeno.visitas == sorted(pequeno.visitas)


@pytest.mark.parametrize("id_socio, fecha, mensaje", [
    (1, date(2026, 1, 5), "no estaba dado de alta"),
    (1, date(2026, 2, 1), "ya tiene una visita"),
])
def test_registrar_visita_no_valida(pequeno, id_socio, fecha, mensaje):
    with pytest.raises(DatosNoValidos, match=mensaje):
        pequeno.registrar_visita(id_socio, fecha)


def test_no_se_apuntan_visitas_de_un_socio_de_baja(pequeno):
    pequeno.registrar_baja(2, date(2026, 3, 1))
    with pytest.raises(DatosNoValidos, match="no estaba dado de alta"):
        pequeno.registrar_visita(2, date(2026, 3, 5))


def test_visita_de_socio_inexistente(pequeno):
    with pytest.raises(SocioNoEncontrado):
        pequeno.registrar_visita(9, date(2026, 3, 5))


def test_registrar_baja(pequeno):
    socio = pequeno.registrar_baja(1, date(2026, 3, 2))
    assert socio.fecha_baja == date(2026, 3, 2)
    assert not socio.activo


@pytest.mark.parametrize("fecha, mensaje", [
    (date(2026, 1, 1), "anterior al alta"),
    (date(2026, 3, 1), "tiene visitas"),
    (date(2026, 2, 20), "tiene visitas"),
])
def test_registrar_baja_no_valida(pequeno, fecha, mensaje):
    with pytest.raises(DatosNoValidos, match=mensaje):
        pequeno.registrar_baja(1, fecha)
    assert pequeno.socio(1).activo


def test_no_se_puede_dar_de_baja_dos_veces(pequeno):
    pequeno.registrar_baja(2, date(2026, 3, 1))
    with pytest.raises(DatosNoValidos, match="ya está dado de baja"):
        pequeno.registrar_baja(2, date(2026, 4, 1))


# --- Fecha de análisis -------------------------------------------------------

def test_fecha_inicio(pequeno, gimnasio):
    assert pequeno.fecha_inicio == date(2026, 2, 1)
    assert Gimnasio.desde_listas([Socio(1, "Ada", ALTA, "mensual", 45.0)], []).fecha_inicio == ALTA
    with pytest.raises(SinDatos):
        Gimnasio().fecha_inicio
    assert gimnasio.fecha_inicio == date(2025, 11, 1)


def test_rango_de_fechas(gimnasio, pequeno):
    assert rango_de_fechas(gimnasio) == (date(2025, 12, 31), date(2026, 10, 31))
    assert DIAS_HISTORIAL_MINIMO == 60
    assert rango_de_fechas(pequeno) == (date(2026, 3, 1), date(2026, 3, 1))


@pytest.mark.parametrize("fecha, valida", [
    (date(2025, 12, 30), False),
    (date(2025, 12, 31), True),
    (date(2026, 6, 15), True),
    (date(2026, 11, 1), False),
])
def test_comprobar_fecha(gimnasio, fecha, valida):
    if valida:
        assert comprobar_fecha(gimnasio, fecha) == fecha
    else:
        with pytest.raises(DatosNoValidos, match="entre el 2025-12-31 y el 2026-10-31"):
            comprobar_fecha(gimnasio, fecha)


def test_evaluar_en_otra_fecha_cambia_los_socios_en_riesgo(gimnasio):
    radar = Radar.por_defecto()
    hoy = sum(e.en_riesgo for e in radar.evaluar_todos(gimnasio))
    antes = sum(e.en_riesgo for e in radar.evaluar_todos(gimnasio, date(2026, 6, 15)))
    assert hoy != antes


# --- Validación configurable -------------------------------------------------

@pytest.mark.parametrize("horizonte, numero, ultimo", [
    (15, 3, date(2026, 10, 1)),
    (30, 3, date(2026, 10, 1)),
    (60, 3, date(2026, 9, 1)),
])
def test_cortes_segun_horizonte(gimnasio, horizonte, numero, ultimo):
    cortes = cortes_por_defecto(gimnasio, horizonte, numero)
    assert len(cortes) == numero
    assert cortes[-1] == ultimo


def test_cortes_con_fecha_de_analisis(gimnasio):
    cortes = cortes_por_defecto(gimnasio, 30, 3, date(2026, 6, 15))
    assert cortes == [date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1)]


def test_cortes_sin_historial_suficiente(gimnasio):
    assert len(cortes_por_defecto(gimnasio, 30, 10)) == 10
    with pytest.raises(DatosNoValidos, match="No hay historial para 10 cortes"):
        cortes_por_defecto(gimnasio, 60, 10)


def test_validar_con_cortes_horizonte_y_fecha(gimnasio):
    radar = Radar.por_defecto()
    corto = validar(gimnasio, radar, horizonte_dias=15, numero_cortes=4)
    largo = validar(gimnasio, radar, horizonte_dias=60, numero_cortes=4)
    assert corto.horizonte_dias == 15 and len(corto.cortes) == 4
    assert largo.metricas.bajas > corto.metricas.bajas
    pasado = validar(gimnasio, radar, fecha=date(2026, 7, 1))
    assert pasado.cortes[-1] == date(2026, 6, 1)


# --- Análisis a una fecha ----------------------------------------------------

def test_evolucion_no_cuenta_nada_posterior_a_la_fecha(gimnasio):
    evolucion = analisis.evolucion_mensual(gimnasio, fecha=date(2026, 6, 15))
    assert evolucion.index[-1] == pd.Timestamp(2026, 6, 1)
    bajas = sum(socio.fecha_baja is not None and date(2026, 6, 1) <= socio.fecha_baja
                <= date(2026, 6, 15) for socio in gimnasio.socios.values())
    assert evolucion["bajas"].iloc[-1] == bajas
    visitas = sum(date(2026, 6, 1) <= visita.fecha <= date(2026, 6, 15)
                  for visita in gimnasio.visitas)
    assert evolucion["visitas"].iloc[-1] == visitas


def test_acciones_hasta_deja_fuera_lo_que_aun_no_se_sabia():
    acciones = analisis.tabla_acciones([
        AccionRetencion(1, 1, "llamada", date(2026, 5, 1), "retenido", date(2026, 5, 20)),
        AccionRetencion(2, 2, "llamada", date(2026, 5, 1), "perdido", date(2026, 7, 1)),
        AccionRetencion(3, 3, "descuento", date(2026, 5, 10)),
        AccionRetencion(4, 4, "descuento", date(2026, 8, 1)),
    ])
    assert analisis.acciones_hasta(acciones, date(2026, 6, 1))["id"].tolist() == [1, 3]


def test_resumen_a_una_fecha_pasada(gimnasio):
    fecha = date(2026, 6, 15)
    evaluaciones = Radar.por_defecto().evaluar_todos(gimnasio, fecha)
    resumen = analisis.resumen_direccion(gimnasio, evaluaciones, [], fecha)
    assert resumen.fecha == fecha
    assert resumen.indicadores["socios_activos"] == len(gimnasio.activos_en(fecha))


@pytest.mark.parametrize("texto, esperados", [("lucía garcía", None), ("110", [110]),
                                              ("nadie así", [])])
def test_filtrar_riesgo_por_texto(gimnasio, texto, esperados):
    riesgo = analisis.tabla_riesgo(Radar.por_defecto().evaluar_todos(gimnasio))
    filtrada = analisis.filtrar_riesgo(riesgo, ["mensual", "trimestral", "anual"], 0, texto)
    if esperados is None:
        assert len(filtrada) > 0
        assert filtrada["nombre"].str.lower().eq(texto).all()
    else:
        assert filtrada["id_socio"].tolist() == esperados


def test_visitas_por_mes(gimnasio, pequeno):
    serie = analisis.visitas_por_mes(gimnasio, 110, date(2026, 10, 31))
    assert len(serie) == 12
    assert serie.sum() == len(gimnasio.visitas_hasta(110, date(2026, 10, 31)))
    assert serie.iloc[-1] == 0
    nuevo = pequeno.dar_de_alta("Cris", date(2026, 3, 1), "mensual", 45.0)
    assert analisis.visitas_por_mes(pequeno, nuevo.id, date(2026, 3, 1), 3).tolist() == [0, 0, 0]


# --- CSV como texto ----------------------------------------------------------

def test_textos_csv_ida_y_vuelta(gimnasio):
    acciones = [AccionRetencion(1, 5, "llamada", date(2026, 9, 1))]
    textos = almacen.textos_csv(gimnasio, acciones)
    assert list(textos) == [almacen.FICHERO_SOCIOS, almacen.FICHERO_VISITAS,
                            almacen.FICHERO_ACCIONES]
    cargado, acciones_cargadas = almacen.cargar_textos(*textos.values())
    assert cargado == gimnasio
    assert acciones_cargadas == acciones


def test_cargar_textos_sin_visitas_ni_acciones(pequeno):
    socios = almacen.textos_csv(pequeno, [])[almacen.FICHERO_SOCIOS]
    cargado, acciones = almacen.cargar_textos(socios, "")
    assert len(cargado.socios) == 2 and not cargado.visitas and acciones == []


@pytest.mark.parametrize("socios, visitas, mensaje", [
    ("", "", "Falta el fichero de socios"),
    ("id,nombre\n1,Ada\n", "", "socios.csv: faltan las columnas"),
    (None, "id_socio,fecha\n1,2026-02-01\n1,ayer\n", "visitas.csv, línea 3"),
    (None, "id_socio,fecha\n7,2026-02-01\n", "no son coherentes"),
])
def test_cargar_textos_con_errores(pequeno, socios, visitas, mensaje):
    socios = almacen.textos_csv(pequeno, [])[almacen.FICHERO_SOCIOS] if socios is None else socios
    with pytest.raises(ErrorDeAlmacen, match=mensaje):
        almacen.cargar_textos(socios, visitas)
