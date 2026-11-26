"""Tests del backtesting y de las acciones de retención."""

from datetime import date

import pandas as pd
import pytest

from radar.excepciones import AccionNoEncontrada, DatosNoValidos, SinDatos, TransicionNoValida
from radar.modelos import ESTADOS_FINALES, Gimnasio, Socio
from radar.radar import Evaluacion, Radar
from radar.retencion import ACCION_POR_CAUSA, GestorRetencion, recomendar
from radar.senales import Lectura
from radar.simulador import simular_acciones
from radar.validacion import (ALERTA, SE_QUEDA, SE_VA, SIN_ALERTA, calcular_metricas,
                              cortes_por_defecto, matriz_confusion, tabla_backtest, validar)

HOY = date(2026, 10, 31)


@pytest.fixture(scope="module")
def resultado(gimnasio):
    """Backtesting del radar por defecto sobre el gimnasio simulado."""
    return validar(gimnasio, Radar.por_defecto())


def evaluacion(id_socio: int = 1, riesgo: int = 70, causa: str = "dias_sin_venir") -> Evaluacion:
    """Evaluación de prueba con una sola señal activa."""
    socio = Socio(id_socio, "Ada", date(2025, 1, 1), "mensual", 45.0)
    return Evaluacion(socio, HOY, riesgo, (Lectura(causa, riesgo, "motivo"),))


# --- Validación --------------------------------------------------------------

def test_cortes_por_defecto_dejan_sitio_al_horizonte(gimnasio):
    cortes = cortes_por_defecto(gimnasio, horizonte_dias=30, numero=3)
    assert cortes == [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)]


def test_tabla_backtest_tipos_y_etiquetas(gimnasio):
    tabla = tabla_backtest(gimnasio, Radar.por_defecto(), [date(2026, 9, 1)], 30)
    assert pd.api.types.is_datetime64_any_dtype(tabla["corte"])
    assert pd.api.types.is_integer_dtype(tabla["riesgo"])
    assert tabla["se_va"].dtype == bool
    se_van = tabla.loc[tabla["se_va"], "fecha_baja"]
    assert se_van.between(pd.Timestamp(2026, 9, 2), pd.Timestamp(2026, 10, 1)).all()


def test_tabla_backtest_sin_socios():
    with pytest.raises(SinDatos):
        tabla_backtest(Gimnasio(), Radar.por_defecto(), [HOY])


def test_matriz_confusion_completa_aunque_falten_casos():
    matriz = matriz_confusion(pd.Series([False, False, True]), pd.Series([False, False, False]))
    assert matriz.loc[SE_QUEDA, SIN_ALERTA] == 2
    assert matriz.loc[SE_VA, SIN_ALERTA] == 1
    assert matriz[ALERTA].tolist() == [0, 0]


def test_calcular_metricas():
    matriz = matriz_confusion(pd.Series([True, True, False, False, False]),
                              pd.Series([True, False, True, False, False]))
    metricas = calcular_metricas(matriz)
    assert (metricas.alertas, metricas.aciertos, metricas.bajas, metricas.casos) == (2, 1, 2, 5)
    assert metricas.precision == 0.5
    assert metricas.recall == 0.5
    assert metricas.exactitud == 0.6
    assert metricas.tasa_base == 0.4
    assert metricas.mejora == 1.25


def test_metricas_sin_alertas_no_dividen_por_cero():
    metricas = calcular_metricas(matriz_confusion(pd.Series([True]), pd.Series([False])))
    assert metricas.precision == 0.0


def test_validacion_suma_todos_los_casos(resultado):
    assert resultado.matriz.to_numpy().sum() == resultado.metricas.casos
    assert resultado.umbral == Radar.por_defecto().umbral
    assert len(resultado.cortes) == 6


def test_el_radar_es_mucho_mejor_que_el_azar(resultado):
    assert resultado.metricas.mejora > 5
    assert resultado.metricas.recall > 0.4


def test_barrido_umbral_mas_alto_menos_alertas_y_menos_recall(resultado):
    barrido = resultado.barrido
    assert barrido["alertas"].is_monotonic_decreasing
    assert barrido["recall"].is_monotonic_decreasing
    fila = barrido.loc[resultado.umbral]
    assert fila["precision"] == resultado.metricas.precision


@pytest.mark.parametrize("horizonte, cortes", [(0, 6), (30, 0)])
def test_validar_parametros_no_validos(gimnasio, horizonte, cortes):
    with pytest.raises(DatosNoValidos):
        validar(gimnasio, Radar.por_defecto(), horizonte, cortes)


# --- Retención ---------------------------------------------------------------

@pytest.mark.parametrize("causa, tipo", list(ACCION_POR_CAUSA.items()))
def test_recomendar_segun_la_causa(causa, tipo):
    assert recomendar(evaluacion(causa=causa)) == tipo


def test_recomendar_sin_causa():
    sin_senales = Evaluacion(evaluacion().socio, HOY, 0, ())
    with pytest.raises(DatosNoValidos):
        recomendar(sin_senales)


def test_proponer_y_avanzar():
    gestor = GestorRetencion()
    accion = gestor.proponer(evaluacion(causa="subida_cuota"), HOY)
    assert (accion.id, accion.tipo, accion.estado) == (1, "descuento", "propuesta")
    assert gestor.abierta_de(1) is accion
    gestor.avanzar(1, "contactado", HOY)
    gestor.avanzar(1, "retenido", HOY)
    assert gestor.abierta_de(1) is None
    assert gestor.abiertas == []


def test_proponer_rechaza_socio_sin_riesgo_o_con_accion_abierta():
    gestor = GestorRetencion()
    with pytest.raises(DatosNoValidos, match="no está en riesgo"):
        gestor.proponer(evaluacion(riesgo=10), HOY)
    gestor.proponer(evaluacion(), HOY)
    with pytest.raises(DatosNoValidos, match="ya tiene"):
        gestor.proponer(evaluacion(), HOY)


def test_proponer_en_riesgo_omite_sin_riesgo_y_con_accion_abierta():
    gestor = GestorRetencion()
    gestor.proponer(evaluacion(1), HOY)
    nuevas = gestor.proponer_en_riesgo([evaluacion(1), evaluacion(2), evaluacion(3, riesgo=5)], HOY)
    assert [accion.id_socio for accion in nuevas] == [2]
    assert [accion.id for accion in gestor.acciones] == [1, 2]


def test_gestor_delega_las_transiciones_en_la_accion():
    gestor = GestorRetencion()
    gestor.proponer(evaluacion(), HOY)
    with pytest.raises(TransicionNoValida):
        gestor.avanzar(1, "retenido", HOY)
    with pytest.raises(AccionNoEncontrada):
        gestor.avanzar(9, "contactado", HOY)


def test_simular_acciones_respeta_el_flujo(gimnasio):
    gestor = simular_acciones(gimnasio, Radar.por_defecto())
    acciones = gestor.acciones
    assert len(gestor) > 20
    assert all(accion.estado in ESTADOS_FINALES for accion in acciones)
    perdidas = [accion for accion in acciones if accion.estado == "perdido"]
    assert all(gimnasio.socio(accion.id_socio).fecha_baja == accion.fecha_cierre
               for accion in perdidas)
