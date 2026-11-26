"""Tests de las excepciones y del modelo de dominio."""

from datetime import date

import pytest

from radar.excepciones import (AccionNoEncontrada, DatosNoValidos, ErrorDeAlmacen, ErrorRadar,
                               SinDatos, SocioNoEncontrado, TransicionNoValida)
from radar.modelos import AccionRetencion, Gimnasio, Socio, Visita


def crear_socio(**cambios) -> Socio:
    """Socio válido con los cambios indicados."""
    datos = {"id": 1, "nombre": "Ada", "fecha_alta": date(2026, 1, 10),
             "tarifa": "mensual", "cuota": 45.0}
    return Socio(**(datos | cambios))


def crear_accion(**cambios) -> AccionRetencion:
    """Acción válida con los cambios indicados."""
    datos = {"id": 1, "id_socio": 1, "tipo": "llamada", "fecha_propuesta": date(2026, 6, 1)}
    return AccionRetencion(**(datos | cambios))


# --- Excepciones -------------------------------------------------------------

@pytest.mark.parametrize("clase", [DatosNoValidos, SinDatos, SocioNoEncontrado,
                                   AccionNoEncontrada, TransicionNoValida, ErrorDeAlmacen])
def test_todas_las_excepciones_heredan_de_error_radar(clase):
    assert issubclass(clase, ErrorRadar)


def test_socio_no_encontrado_guarda_el_identificador():
    error = SocioNoEncontrado(7)
    assert error.id_socio == 7
    assert str(error) == "No existe el socio 7"


def test_transicion_no_valida_guarda_los_estados():
    error = TransicionNoValida("retenido", "propuesta")
    assert (error.actual, error.nuevo) == ("retenido", "propuesta")
    assert str(error) == "No se puede pasar de retenido a propuesta"


# --- Socio -------------------------------------------------------------------

def test_socio_limpia_el_nombre_y_copia_la_cuota_anterior():
    socio = crear_socio(nombre="  Ada  ")
    assert socio.nombre == "Ada"
    assert socio.cuota_anterior == 45.0
    assert socio.subida_cuota == 0.0


@pytest.mark.parametrize("cambios, mensaje", [
    ({"nombre": "   "}, "nombre"),
    ({"tarifa": "semanal"}, "Tarifa"),
    ({"cuota": 0}, "cuota"),
    ({"cuota_anterior": -5.0}, "cuota anterior"),
    ({"id": 0}, "identificador"),
    ({"fecha_baja": date(2026, 1, 1)}, "baja"),
    ({"fecha_cambio_cuota": date(2025, 12, 1)}, "cuota"),
])
def test_socio_no_valido(cambios, mensaje):
    with pytest.raises(DatosNoValidos, match=mensaje):
        crear_socio(**cambios)


def test_subida_cuota_en_porcentaje():
    socio = crear_socio(cuota=54.0, cuota_anterior=45.0, fecha_cambio_cuota=date(2026, 5, 1))
    assert socio.subida_cuota == 20.0


@pytest.mark.parametrize("fecha, esperado", [
    (date(2026, 1, 9), False),
    (date(2026, 1, 10), True),
    (date(2026, 3, 31), True),
    (date(2026, 4, 1), False),
])
def test_activo_en(fecha, esperado):
    socio = crear_socio(fecha_baja=date(2026, 4, 1))
    assert socio.activo_en(fecha) is esperado
    assert socio.activo is False


def test_antiguedad_dias():
    assert crear_socio().antiguedad_dias(date(2026, 2, 9)) == 30


def test_socio_ida_y_vuelta_por_fila():
    socio = crear_socio(cuota=50.0, cuota_anterior=45.0, fecha_cambio_cuota=date(2026, 3, 1),
                        fecha_baja=date(2026, 6, 15))
    fila = socio.a_fila()
    assert all(isinstance(valor, str) for valor in fila.values())
    assert Socio.desde_fila(fila) == socio


@pytest.mark.parametrize("cambios", [{"id": "uno"}, {"fecha_alta": "10/01/2026"}, {"cuota": ""}])
def test_socio_desde_fila_no_valida_encadena_el_error(cambios):
    fila = crear_socio().a_fila() | cambios
    with pytest.raises(DatosNoValidos) as info:
        Socio.desde_fila(fila)
    assert isinstance(info.value.__cause__, ValueError)


def test_socio_desde_fila_sin_columna():
    fila = crear_socio().a_fila()
    del fila["tarifa"]
    with pytest.raises(DatosNoValidos):
        Socio.desde_fila(fila)


# --- Visita ------------------------------------------------------------------

def test_visita_es_inmutable_y_ordenable():
    primera, segunda = Visita(2, date(2026, 1, 1)), Visita(1, date(2026, 1, 2))
    assert sorted([segunda, primera])[0] == segunda
    with pytest.raises(AttributeError):
        primera.fecha = date(2026, 2, 1)


def test_visita_ida_y_vuelta_y_errores():
    visita = Visita(3, date(2026, 5, 4))
    assert Visita.desde_fila(visita.a_fila()) == visita
    with pytest.raises(DatosNoValidos):
        Visita.desde_fila({"id_socio": "3", "fecha": "ayer"})
    with pytest.raises(DatosNoValidos):
        Visita(0, date(2026, 5, 4))


# --- Acción de retención -----------------------------------------------------

@pytest.mark.parametrize("cambios", [
    {"tipo": "regalo"},
    {"estado": "pendiente"},
    {"estado": "retenido"},
    {"fecha_cierre": date(2026, 6, 2)},
    {"estado": "perdido", "fecha_cierre": date(2026, 5, 1)},
])
def test_accion_no_valida(cambios):
    with pytest.raises(DatosNoValidos):
        crear_accion(**cambios)


@pytest.mark.parametrize("camino, final", [
    (["contactado", "retenido"], "retenido"),
    (["contactado", "perdido"], "perdido"),
    (["perdido"], "perdido"),
])
def test_accion_flujo_valido(camino, final):
    accion = crear_accion()
    for estado in camino:
        accion.avanzar(estado, date(2026, 6, 10))
    assert accion.estado == final
    assert accion.cerrada
    assert accion.fecha_cierre == date(2026, 6, 10)


@pytest.mark.parametrize("inicial, nuevo", [
    ("propuesta", "retenido"),
    ("propuesta", "propuesta"),
    ("contactado", "propuesta"),
])
def test_accion_transicion_no_valida(inicial, nuevo):
    accion = crear_accion(estado=inicial)
    with pytest.raises(TransicionNoValida):
        accion.avanzar(nuevo, date(2026, 6, 10))
    assert accion.estado == inicial


def test_accion_cerrada_no_cambia():
    accion = crear_accion(estado="retenido", fecha_cierre=date(2026, 6, 5))
    with pytest.raises(TransicionNoValida):
        accion.avanzar("perdido", date(2026, 6, 10))


def test_accion_avanzar_con_estado_inexistente_o_fecha_anterior():
    accion = crear_accion()
    with pytest.raises(DatosNoValidos):
        accion.avanzar("olvidado", date(2026, 6, 10))
    with pytest.raises(DatosNoValidos):
        accion.avanzar("contactado", date(2026, 5, 1))
    assert accion.estado == "propuesta"


def test_accion_ida_y_vuelta_por_fila():
    accion = crear_accion(estado="perdido", fecha_cierre=date(2026, 6, 20))
    assert AccionRetencion.desde_fila(accion.a_fila()) == accion


# --- Gimnasio ----------------------------------------------------------------

def test_gimnasio_ordena_y_agrupa_visitas():
    socios = [crear_socio(id=2, nombre="Bea"), crear_socio()]
    visitas = [Visita(1, date(2026, 2, 3)), Visita(2, date(2026, 2, 1)),
               Visita(1, date(2026, 2, 1))]
    gimnasio = Gimnasio.desde_listas(socios, visitas)
    assert list(gimnasio.socios) == [1, 2]
    assert gimnasio.visitas_por_socio[1] == [date(2026, 2, 1), date(2026, 2, 3)]
    assert gimnasio.visitas_hasta(1, date(2026, 2, 2)) == [date(2026, 2, 1)]
    assert gimnasio.visitas_hasta(3, date(2026, 2, 2)) == []
    assert gimnasio.fecha_referencia == date(2026, 2, 3)


def test_gimnasio_rechaza_datos_incoherentes():
    with pytest.raises(DatosNoValidos, match="repetido"):
        Gimnasio.desde_listas([crear_socio(), crear_socio()], [])
    with pytest.raises(DatosNoValidos, match="no existen"):
        Gimnasio.desde_listas([crear_socio()], [Visita(9, date(2026, 2, 1))])


def test_gimnasio_socio_y_activos():
    gimnasio = Gimnasio.desde_listas(
        [crear_socio(), crear_socio(id=2, nombre="Bea", fecha_baja=date(2026, 2, 1))], [])
    assert gimnasio.socio(2).nombre == "Bea"
    assert [socio.id for socio in gimnasio.activos_en(date(2026, 3, 1))] == [1]
    with pytest.raises(SocioNoEncontrado):
        gimnasio.socio(99)


def test_gimnasio_vacio_no_tiene_fecha_de_referencia():
    gimnasio = Gimnasio()
    assert gimnasio.vacio
    with pytest.raises(SinDatos):
        gimnasio.fecha_referencia
