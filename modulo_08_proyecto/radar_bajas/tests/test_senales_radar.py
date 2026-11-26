"""Tests de las señales de riesgo y del radar que las combina."""

from datetime import date, timedelta

import pytest

from radar.excepciones import DatosNoValidos, SocioNoEncontrado
from radar.modelos import Gimnasio, Socio, Visita
from radar.radar import PESOS, Radar
from radar.senales import (AntiguedadBaja, CaidaAsistencia, DiasSinVenir, Senal, SubidaCuota,
                           TipoTarifa, escalar)

HOY = date(2026, 6, 30)


def socio(**cambios) -> Socio:
    """Socio con un año de antigüedad y tarifa anual, salvo cambios."""
    datos = {"id": 1, "nombre": "Ada", "fecha_alta": date(2025, 6, 1),
             "tarifa": "anual", "cuota": 35.0}
    return Socio(**(datos | cambios))


def cada(dias: int, desde: date, hasta: date) -> list[date]:
    """Fechas de visita cada ``dias`` días entre ``desde`` y ``hasta``."""
    return [desde + timedelta(days=d) for d in range(0, (hasta - desde).days + 1, dias)]


# Socio constante: viene cada tres días hasta hoy
VISITAS_REGULARES = cada(3, date(2026, 1, 1), HOY)
# Socio que se apaga: venía cada dos días y lleva 25 días sin venir
VISITAS_QUE_CAEN = cada(2, date(2026, 1, 1), HOY - timedelta(days=25))


@pytest.mark.parametrize("valor, esperado", [(0, 0.0), (7, 0.0), (18.5, 0.5), (30, 1.0), (90, 1.0)])
def test_escalar(valor, esperado):
    assert escalar(valor, 7, 30) == esperado


def test_senal_es_abstracta_y_exige_peso_positivo():
    with pytest.raises(TypeError):
        Senal(10)
    with pytest.raises(DatosNoValidos):
        DiasSinVenir(0)


@pytest.mark.parametrize("visitas, dias, intensidad", [
    ([HOY - timedelta(days=3)], 3, 0.0),
    ([HOY - timedelta(days=30)], 30, 1.0),
    ([], (HOY - date(2025, 6, 1)).days, 1.0),
])
def test_dias_sin_venir(visitas, dias, intensidad):
    medida, detalle = DiasSinVenir(35).medir(socio(), visitas, HOY)
    assert medida == intensidad
    assert detalle == f"{dias} días sin venir"


def test_caida_asistencia_estable_no_puntua():
    intensidad, _ = CaidaAsistencia(25).medir(socio(), VISITAS_REGULARES, HOY)
    assert intensidad == 0.0


def test_caida_asistencia_detecta_el_bajon():
    intensidad, detalle = CaidaAsistencia(25).medir(socio(), VISITAS_QUE_CAEN, HOY)
    assert intensidad > 0.8
    assert detalle.startswith("asistencia -")
    assert detalle.endswith(" %")


def test_caida_asistencia_sin_historico():
    nuevo = socio(fecha_alta=HOY - timedelta(days=40))
    intensidad, detalle = CaidaAsistencia(25).medir(nuevo, [HOY - timedelta(days=1)], HOY)
    assert intensidad == 0.0
    assert detalle == "sin histórico de asistencia"


@pytest.mark.parametrize("dias, intensidad", [(10, 1.0), (105, 0.5), (400, 0.0)])
def test_antiguedad(dias, intensidad):
    medida, detalle = AntiguedadBaja(15).medir(socio(fecha_alta=HOY - timedelta(days=dias)), [], HOY)
    assert medida == intensidad
    assert detalle == f"socio desde hace {dias} días"


@pytest.mark.parametrize("tarifa, intensidad", [("mensual", 1.0), ("trimestral", 0.5), ("anual", 0.1)])
def test_tipo_tarifa(tarifa, intensidad):
    assert TipoTarifa(10).medir(socio(tarifa=tarifa), [], HOY) == (intensidad, f"tarifa {tarifa}")


@pytest.mark.parametrize("dias_desde_cambio, cuota, intensidad", [
    (10, 42.0, 1.0),     # +20 % hace poco: alarma
    (10, 38.5, 0.5),     # +10 %
    (120, 42.0, 0.0),    # demasiado antigua
    (-5, 42.0, 0.0),     # todavía no ha ocurrido en esa fecha
    (10, 31.5, 0.0),     # bajada de cuota
])
def test_subida_cuota(dias_desde_cambio, cuota, intensidad):
    cambiado = socio(cuota=cuota, cuota_anterior=35.0,
                     fecha_cambio_cuota=HOY - timedelta(days=dias_desde_cambio))
    medida, _ = SubidaCuota(15).medir(cambiado, [], HOY)
    assert medida == intensidad


def test_sin_subida_de_cuota():
    assert SubidaCuota(15).medir(socio(), [], HOY) == (0.0, "sin subida reciente")


def test_lectura_multiplica_peso_por_intensidad():
    lectura = TipoTarifa(10).leer(socio(tarifa="trimestral"), [], HOY)
    assert (lectura.senal, lectura.puntos, lectura.detalle) == ("tarifa", 5.0, "tarifa trimestral")


# --- Radar -------------------------------------------------------------------

def test_radar_por_defecto_suma_cien_puntos():
    radar = Radar.por_defecto()
    assert radar.peso_total == 100
    assert {type(senal) for senal in radar.senales} == set(PESOS)


@pytest.mark.parametrize("senales, umbral", [
    ([], 50),
    ([DiasSinVenir(10), DiasSinVenir(20)], 50),
    ([DiasSinVenir(10)], 120),
])
def test_radar_no_valido(senales, umbral):
    with pytest.raises(DatosNoValidos):
        Radar(senales, umbral)


def test_socio_fiel_tiene_riesgo_bajo():
    evaluacion = Radar.por_defecto().evaluar(socio(), VISITAS_REGULARES, HOY)
    assert evaluacion.riesgo == 1
    assert not evaluacion.en_riesgo
    assert evaluacion.causa_principal == "tarifa"


def test_socio_que_se_apaga_tiene_riesgo_alto_y_explicado():
    apagado = socio(tarifa="mensual", cuota=54.0, cuota_anterior=45.0,
                    fecha_cambio_cuota=HOY - timedelta(days=40))
    evaluacion = Radar.por_defecto().evaluar(apagado, VISITAS_QUE_CAEN, HOY)
    assert evaluacion.riesgo == 78  # 28,9 + 23,8 + 15 + 10
    assert evaluacion.en_riesgo
    assert evaluacion.causa_principal == "dias_sin_venir"
    assert evaluacion.explicacion == ("Riesgo 78: 26 días sin venir; asistencia -87 %; "
                                      "cuota +20 % hace 40 días; tarifa mensual")


def test_explicacion_sin_senales():
    radar = Radar([DiasSinVenir(10)])
    evaluacion = radar.evaluar(socio(), [HOY], HOY)
    assert evaluacion.riesgo == 0
    assert evaluacion.causa_principal is None
    assert evaluacion.explicacion == "Riesgo 0: sin señales de alerta"


def test_riesgo_se_normaliza_con_pesos_que_no_suman_cien():
    radar = Radar([DiasSinVenir(3), TipoTarifa(1)], umbral=60)
    evaluacion = radar.evaluar(socio(tarifa="mensual"), [], HOY)
    assert evaluacion.riesgo == 100
    assert evaluacion.umbral == 60


def test_radar_solo_usa_visitas_hasta_la_fecha():
    gimnasio = Gimnasio.desde_listas([socio()], [Visita(1, fecha) for fecha in VISITAS_REGULARES])
    radar = Radar.por_defecto()
    pasado = date(2026, 3, 1)
    assert radar.evaluar_socio(gimnasio, 1, pasado).lecturas == \
        radar.evaluar(socio(), [f for f in VISITAS_REGULARES if f <= pasado], pasado).lecturas


def test_evaluar_todos_ordena_por_riesgo_y_omite_bajas():
    socios = [socio(), socio(id=2, nombre="Bea", tarifa="mensual"),
              socio(id=3, nombre="Cas", fecha_baja=date(2026, 5, 1))]
    visitas = [Visita(1, fecha) for fecha in VISITAS_REGULARES] + \
              [Visita(2, fecha) for fecha in VISITAS_QUE_CAEN]
    evaluaciones = Radar.por_defecto().evaluar_todos(Gimnasio.desde_listas(socios, visitas))
    assert [evaluacion.socio.id for evaluacion in evaluaciones] == [2, 1]
    assert evaluaciones[0].fecha == HOY


def test_evaluar_socio_inexistente():
    gimnasio = Gimnasio.desde_listas([socio()], [Visita(1, HOY)])
    with pytest.raises(SocioNoEncontrado):
        Radar.por_defecto().evaluar_socio(gimnasio, 5)
