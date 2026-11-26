"""Tests del simulador y del almacén CSV."""

from datetime import date

import pytest

from radar import almacen
from radar.excepciones import DatosNoValidos, ErrorDeAlmacen
from radar.modelos import CAMPOS_SOCIO, AccionRetencion, Gimnasio, primeros_de_mes
from radar.simulador import FECHA_FIN, N_SOCIOS, simular

# --- Simulador ---------------------------------------------------------------


def test_simulador_genera_los_socios_pedidos(gimnasio):
    assert len(gimnasio.socios) == N_SOCIOS
    assert list(gimnasio.socios) == list(range(1, N_SOCIOS + 1))
    assert gimnasio.fecha_referencia == FECHA_FIN


def test_simulador_es_reproducible_con_la_semilla():
    assert simular(40, semilla=3) == simular(40, semilla=3)
    assert simular(40, semilla=3) != simular(40, semilla=4)


def test_simulador_genera_datos_coherentes(gimnasio):
    inicio = primeros_de_mes(FECHA_FIN, 12)[0]
    for socio in gimnasio.socios.values():
        fechas = gimnasio.visitas_por_socio.get(socio.id, [])
        assert all(socio.activo_en(fecha) for fecha in fechas)
        assert all(inicio <= fecha <= FECHA_FIN for fecha in fechas)


def test_simulador_tiene_bajas_y_subidas_realistas(gimnasio):
    socios = gimnasio.socios.values()
    bajas = sum(not socio.activo for socio in socios)
    subidas = sum(socio.subida_cuota > 0 for socio in socios)
    assert 0.15 * N_SOCIOS < bajas < 0.45 * N_SOCIOS
    assert 0.1 * N_SOCIOS < subidas < 0.4 * N_SOCIOS
    assert {socio.tarifa for socio in socios} == {"mensual", "trimestral", "anual"}


def test_los_que_se_van_dejan_de_venir_antes(gimnasio):
    dias_sin_venir = [(socio.fecha_baja - gimnasio.visitas_por_socio[socio.id][-1]).days
                      for socio in gimnasio.socios.values()
                      if socio.fecha_baja and socio.id in gimnasio.visitas_por_socio]
    assert sum(dias_sin_venir) / len(dias_sin_venir) > 10


@pytest.mark.parametrize("n_socios, meses", [(0, 12), (10, 0)])
def test_simulador_rechaza_parametros_no_validos(n_socios, meses):
    with pytest.raises(DatosNoValidos):
        simular(n_socios, meses=meses)


@pytest.mark.parametrize("fin, meses, esperado", [
    (date(2026, 10, 31), 3, [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)]),
    (date(2026, 2, 14), 3, [date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]),
])
def test_primeros_de_mes(fin, meses, esperado):
    assert primeros_de_mes(fin, meses) == esperado


# --- Almacén -----------------------------------------------------------------

@pytest.fixture
def acciones() -> list[AccionRetencion]:
    """Dos acciones de ejemplo, una abierta y otra cerrada."""
    return [AccionRetencion(1, 5, "llamada", date(2026, 9, 1)),
            AccionRetencion(2, 8, "descuento", date(2026, 9, 1), "retenido", date(2026, 9, 20))]


def test_almacen_ida_y_vuelta(tmp_path, gimnasio, acciones):
    almacen.guardar(tmp_path / "datos", gimnasio, acciones)
    cargado, acciones_cargadas = almacen.cargar(tmp_path / "datos")
    assert cargado == gimnasio
    assert acciones_cargadas == acciones


def test_almacen_escribe_csv_legibles(tmp_path, gimnasio):
    almacen.guardar(tmp_path, gimnasio, [])
    lineas = (tmp_path / almacen.FICHERO_SOCIOS).read_text(encoding="utf-8").splitlines()
    assert lineas[0].split(",") == CAMPOS_SOCIO
    assert len(lineas) == N_SOCIOS + 1
    assert (tmp_path / almacen.FICHERO_ACCIONES).read_text(encoding="utf-8").count("\n") == 1


def test_almacen_sin_ficheros_es_la_primera_ejecucion(tmp_path):
    gimnasio, acciones = almacen.cargar(tmp_path / "no_existe")
    assert gimnasio == Gimnasio()
    assert acciones == []


def test_almacen_fila_no_valida_indica_la_linea(tmp_path, gimnasio):
    almacen.guardar(tmp_path, gimnasio, [])
    ruta = tmp_path / almacen.FICHERO_SOCIOS
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    lineas[3] = lineas[3].replace("mensual", "diaria").replace("trimestral", "diaria") \
        .replace("anual", "diaria")
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    with pytest.raises(ErrorDeAlmacen, match="socios.csv, línea 4") as info:
        almacen.cargar(tmp_path)
    assert isinstance(info.value.__cause__, DatosNoValidos)


def test_almacen_columnas_que_faltan(tmp_path):
    (tmp_path / almacen.FICHERO_VISITAS).write_text("socio,dia\n1,2026-01-01\n", encoding="utf-8")
    with pytest.raises(ErrorDeAlmacen, match="faltan las columnas fecha, id_socio"):
        almacen.cargar(tmp_path)


def test_almacen_datos_incoherentes(tmp_path):
    (tmp_path / almacen.FICHERO_VISITAS).write_text("id_socio,fecha\n9,2026-01-01\n",
                                                    encoding="utf-8")
    with pytest.raises(ErrorDeAlmacen, match="no son coherentes"):
        almacen.cargar(tmp_path)


def test_almacen_no_puede_escribir(tmp_path, gimnasio):
    bloqueo = tmp_path / "fichero"
    bloqueo.write_text("", encoding="utf-8")
    with pytest.raises(ErrorDeAlmacen):
        almacen.guardar(bloqueo / "datos", gimnasio, [])
