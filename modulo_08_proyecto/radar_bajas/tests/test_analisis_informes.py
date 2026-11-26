"""Tests del análisis con pandas, de los gráficos y de los informes de texto."""

from datetime import date

import pandas as pd
import pytest
from matplotlib.figure import Figure

from radar import analisis, graficos, informes
from radar.excepciones import DatosNoValidos, ErrorDeAlmacen, SinDatos
from radar.modelos import TARIFAS, TIPOS_ACCION, AccionRetencion, Gimnasio, Socio
from radar.radar import Evaluacion, Radar
from radar.senales import Lectura
from radar.simulador import simular_acciones
from radar.validacion import validar

HOY = date(2026, 10, 31)


@pytest.fixture(scope="module")
def evaluaciones(gimnasio):
    """Evaluaciones de todos los socios activos en la fecha de los datos."""
    return Radar.por_defecto().evaluar_todos(gimnasio)


@pytest.fixture(scope="module")
def acciones(gimnasio):
    """Histórico simulado de acciones de retención."""
    return simular_acciones(gimnasio, Radar.por_defecto()).acciones


@pytest.fixture(scope="module")
def resumen(gimnasio, evaluaciones, acciones):
    """Resumen para la dirección con los datos simulados."""
    return analisis.resumen_direccion(gimnasio, evaluaciones, acciones)


def accion(id_accion: int, tipo: str, estado: str) -> AccionRetencion:
    """Acción en el estado indicado (cerrada el día después si es final)."""
    cierre = date(2026, 9, 2) if estado in ("retenido", "perdido") else None
    return AccionRetencion(id_accion, id_accion, tipo, date(2026, 9, 1), estado, cierre)


# --- Tablas ------------------------------------------------------------------

def test_tabla_socios_tipos(gimnasio):
    tabla = analisis.tabla_socios(gimnasio)
    assert len(tabla) == len(gimnasio.socios)
    assert pd.api.types.is_integer_dtype(tabla["id"])
    assert pd.api.types.is_float_dtype(tabla["cuota"])
    for columna in ("fecha_alta", "fecha_cambio_cuota", "fecha_baja"):
        assert pd.api.types.is_datetime64_any_dtype(tabla[columna])
    bajas = sum(not socio.activo for socio in gimnasio.socios.values())
    assert tabla["fecha_baja"].notna().sum() == bajas


def test_tabla_visitas_tipos(gimnasio):
    tabla = analisis.tabla_visitas(gimnasio)
    assert len(tabla) == len(gimnasio.visitas)
    assert pd.api.types.is_integer_dtype(tabla["id_socio"])
    assert pd.api.types.is_datetime64_any_dtype(tabla["fecha"])


def test_tablas_vacias_mantienen_las_columnas():
    assert list(analisis.tabla_riesgo([]).columns) == analisis.COLUMNAS_RIESGO
    assert analisis.tabla_acciones([]).empty


# --- Evolución y riesgo ------------------------------------------------------

def test_evolucion_mensual(gimnasio):
    evolucion = analisis.evolucion_mensual(gimnasio)
    assert len(evolucion) == 12
    assert evolucion.index[0] == pd.Timestamp(2025, 11, 1)
    assert evolucion["bajas"].sum() == sum(not socio.activo for socio in gimnasio.socios.values())
    assert evolucion["visitas"].sum() == len(gimnasio.visitas)
    assert evolucion.dtypes["activos"] == "int64"
    esperada = (100 * evolucion["bajas"] / evolucion["activos"]).round(1)
    pd.testing.assert_series_equal(evolucion["tasa_abandono"], esperada, check_names=False)


def test_evolucion_cuenta_activos_al_empezar_el_mes():
    socios = [Socio(1, "Ada", date(2026, 1, 15), "mensual", 45.0, fecha_baja=date(2026, 3, 1)),
              Socio(2, "Bea", date(2025, 6, 1), "anual", 35.0)]
    evolucion = analisis.evolucion_mensual(Gimnasio.desde_listas(socios, []), meses=4)
    assert evolucion.index[0] == pd.Timestamp(2025, 12, 1)   # cuatro meses hasta la baja
    assert evolucion["activos"].tolist() == [1, 1, 2, 1]
    assert evolucion["bajas"].tolist() == [0, 0, 0, 1]


def test_evolucion_sin_datos():
    with pytest.raises(SinDatos):
        analisis.evolucion_mensual(Gimnasio())


def test_riesgo_por_tarifa(evaluaciones):
    por_tarifa = analisis.riesgo_por_tarifa(analisis.tabla_riesgo(evaluaciones))
    assert por_tarifa.index.tolist() == list(TARIFAS)
    assert por_tarifa["socios"].sum() == len(evaluaciones)
    en_riesgo = sum(evaluacion.en_riesgo for evaluacion in evaluaciones)
    assert por_tarifa["en_riesgo"].sum() == en_riesgo
    assert por_tarifa.loc["mensual", "riesgo_medio"] > por_tarifa.loc["anual", "riesgo_medio"]


@pytest.mark.parametrize("tarifas, minimo", [(["mensual"], 0), (["anual", "trimestral"], 10),
                                             (list(TARIFAS), 40)])
def test_filtrar_riesgo(evaluaciones, tarifas, minimo):
    filtrada = analisis.filtrar_riesgo(analisis.tabla_riesgo(evaluaciones), tarifas, minimo)
    esperados = sum(evaluacion.socio.tarifa in tarifas and evaluacion.riesgo >= minimo
                    for evaluacion in evaluaciones)
    assert len(filtrada) == esperados
    assert filtrada["riesgo"].is_monotonic_decreasing


def test_tabla_riesgo_incluye_la_explicacion(evaluaciones):
    tabla = analisis.tabla_riesgo(evaluaciones)
    assert tabla.loc[0, "explicacion"] == evaluaciones[0].explicacion
    assert tabla.loc[0, "nombre"] == evaluaciones[0].socio.nombre


def test_tabla_senales(evaluaciones):
    evaluacion = evaluaciones[0]
    tabla = analisis.tabla_senales(evaluacion)
    assert tabla.index.tolist() == [lectura.senal for lectura in evaluacion.lecturas]
    assert tabla["puntos"].sum() == pytest.approx(sum(l.puntos for l in evaluacion.lecturas))


def test_causas_en_riesgo_solo_cuenta_los_que_estan_en_riesgo(evaluaciones):
    causas = analisis.causas_en_riesgo(analisis.tabla_riesgo(evaluaciones))
    assert causas.sum() == sum(evaluacion.en_riesgo for evaluacion in evaluaciones)


def test_eficacia_acciones():
    tabla = analisis.tabla_acciones([
        accion(1, "llamada", "retenido"), accion(2, "llamada", "perdido"),
        accion(3, "llamada", "retenido"), accion(4, "descuento", "propuesta"),
    ])
    eficacia = analisis.eficacia_acciones(tabla)
    assert eficacia.index.tolist() == list(TIPOS_ACCION)
    assert eficacia.loc["llamada", "cerradas"] == 3
    assert eficacia.loc["llamada", "tasa_retencion"] == 66.7
    assert eficacia.loc["descuento", "propuesta"] == 1
    assert pd.isna(eficacia.loc["descuento", "tasa_retencion"])
    assert eficacia.loc["cambio_tarifa", "retenido"] == 0


def test_indicadores_con_tipos_de_python(resumen, evaluaciones):
    datos = resumen.indicadores
    assert datos["socios_activos"] == len(evaluaciones)
    assert datos["en_riesgo"] == sum(evaluacion.en_riesgo for evaluacion in evaluaciones)
    en_juego = sum(evaluacion.socio.cuota for evaluacion in evaluaciones if evaluacion.en_riesgo)
    assert datos["ingresos_en_juego"] == round(en_juego, 2)
    assert all(type(valor) in (int, float, str) for valor in datos.values())


def test_mejor_accion_exige_un_minimo_de_cerradas():
    acciones = [accion(1, "descuento", "retenido")] + \
               [accion(n, "llamada", "retenido" if n % 2 else "perdido") for n in range(2, 8)]
    eficacia = analisis.eficacia_acciones(analisis.tabla_acciones(acciones))
    riesgo = analisis.tabla_riesgo([])
    evolucion = pd.DataFrame({"tasa_abandono": [2.0], "bajas": [1]})
    assert analisis.indicadores(evolucion, riesgo, eficacia)["mejor_accion"] == "llamada"


# --- Gráficos ----------------------------------------------------------------

@pytest.mark.parametrize("funcion, atributo", [
    (graficos.grafico_bajas, "evolucion"),
    (graficos.grafico_riesgo_tarifa, "por_tarifa"),
    (graficos.grafico_eficacia, "eficacia"),
])
def test_graficos_devuelven_una_figura_con_barras(resumen, funcion, atributo):
    tabla = getattr(resumen, atributo)
    figura = funcion(tabla)
    assert isinstance(figura, Figure)
    assert len(figura.axes[0].patches) == len(tabla)


def test_exportar_graficos_png(tmp_path, resumen):
    rutas = graficos.exportar(tmp_path / "graficos", resumen)
    assert [ruta.name for ruta in rutas] == ["evolucion_bajas.png", "riesgo_por_tarifa.png",
                                             "eficacia_acciones.png"]
    assert all(ruta.read_bytes().startswith(b"\x89PNG") for ruta in rutas)


def test_exportar_en_carpeta_imposible(tmp_path, resumen):
    fichero = tmp_path / "fichero"
    fichero.write_text("", encoding="utf-8")
    with pytest.raises(ErrorDeAlmacen):
        graficos.exportar(fichero / "graficos", resumen)


# --- Informes ----------------------------------------------------------------

@pytest.mark.parametrize("valor, texto", [(1234.5, "1.234,50 €"), (0, "0,00 €")])
def test_euros(valor, texto):
    assert informes.euros(valor) == texto


def test_porcentaje():
    assert informes.porcentaje(12.345) == "12,3 %"


def test_tabla_riesgo(evaluaciones):
    texto = informes.tabla_riesgo(evaluaciones, 5)
    lineas = texto.splitlines()
    assert lineas[0].split() == ["ID", "RIESGO", "NOMBRE", "TARIFA", "MOTIVOS"]
    assert len(lineas) == 7
    assert all(len(linea) <= informes.ANCHO for linea in lineas)
    assert f"{evaluaciones[0].riesgo}!" in lineas[2]


def test_tabla_riesgo_cantidad_no_valida(evaluaciones):
    with pytest.raises(DatosNoValidos):
        informes.tabla_riesgo(evaluaciones, 0)


def test_ficha_socio_explica_cada_senal(evaluaciones):
    evaluacion = evaluaciones[0]
    texto = informes.ficha_socio(evaluacion, None)
    assert evaluacion.explicacion in texto
    assert all(lectura.senal in texto for lectura in evaluacion.lecturas)
    assert "Acción recomendada:" in texto


@pytest.mark.parametrize("riesgo, abierta, esperado", [
    (10, None, "Sin acción"),
    (80, None, "Acción recomendada: llamada"),
    (80, AccionRetencion(4, 1, "llamada", HOY, "contactado"), "Acción en marcha: n.º 4"),
])
def test_ficha_socio_accion(riesgo, abierta, esperado):
    socio = Socio(1, "Ada", date(2025, 1, 1), "mensual", 45.0)
    evaluacion = Evaluacion(socio, HOY, riesgo, (Lectura("dias_sin_venir", riesgo, "x"),))
    assert esperado in informes.ficha_socio(evaluacion, abierta)


def test_listado_acciones():
    texto = informes.listado_acciones([accion(1, "llamada", "retenido"),
                                       accion(2, "descuento", "propuesta")])
    lineas = texto.splitlines()
    assert lineas[2].split() == ["1", "1", "llamada", "retenido", "2026-09-01", "2026-09-02"]
    assert lineas[3].endswith("-")
    assert informes.listado_acciones([]).endswith("(sin acciones)")


def test_informe_validacion(gimnasio):
    resultado = validar(gimnasio, Radar.por_defecto())
    texto = informes.informe_validacion(resultado)
    assert "VALIDACIÓN DEL RADAR" in texto
    assert f"Casos (socio y fecha de corte): {resultado.metricas.casos}" in texto
    assert "Precisión:" in texto and "Recall:" in texto
    assert texto.count("\n  se va ") == 1


def test_informe_direccion(resumen):
    texto = informes.informe_direccion(resumen)
    lineas = texto.splitlines()
    assert lineas[1].strip() == "RADAR DE BAJAS: INFORME PARA LA DIRECCIÓN"
    assert "Datos a 2026-10-31" in texto
    assert informes.euros(resumen.indicadores["ingresos_en_juego"]) in texto
    assert all(len(linea) <= informes.ANCHO for linea in lineas)
    assert "  2025-11" in texto and "  2026-10" in texto
