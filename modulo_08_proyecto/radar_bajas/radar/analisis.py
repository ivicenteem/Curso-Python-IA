"""Indicadores para la dirección calculados con pandas.

Los objetos del dominio se convierten en tablas con ``a_fila`` y a partir de
ahí todo son operaciones de columna: sin bucles sobre las filas. Las fechas
son fechas, los enteros son enteros y las cifras que se devuelven sueltas son
tipos de Python, no de NumPy.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

import pandas as pd

from .modelos import (ESTADOS_ACCION, TARIFAS, TIPOS_ACCION, AccionRetencion, Gimnasio,
                      primeros_de_mes)
from .radar import Evaluacion

MESES_EVOLUCION = 12
COLUMNAS_RIESGO = ["id_socio", "nombre", "tarifa", "cuota", "riesgo", "en_riesgo", "causa",
                   "explicacion"]
MINIMO_CERRADAS = 5          # acciones cerradas necesarias para comparar un tipo


def tabla_socios(gimnasio: Gimnasio) -> pd.DataFrame:
    """Una fila por socio con las fechas como fechas y las cuotas como números."""
    tabla = pd.DataFrame([socio.a_fila() for socio in gimnasio.socios.values()])
    return tabla.astype({"id": int, "cuota": float, "cuota_anterior": float}).assign(
        fecha_alta=pd.to_datetime(tabla["fecha_alta"]),
        fecha_cambio_cuota=pd.to_datetime(tabla["fecha_cambio_cuota"]),
        fecha_baja=pd.to_datetime(tabla["fecha_baja"]),
    )


def tabla_visitas(gimnasio: Gimnasio) -> pd.DataFrame:
    """Una fila por visita: ``id_socio`` (int) y ``fecha`` (fecha)."""
    tabla = pd.DataFrame([visita.a_fila() for visita in gimnasio.visitas],
                         columns=["id_socio", "fecha"])
    return tabla.astype({"id_socio": int}).assign(fecha=pd.to_datetime(tabla["fecha"]))


def tabla_riesgo(evaluaciones: Iterable[Evaluacion]) -> pd.DataFrame:
    """Una fila por socio evaluado: riesgo, causa principal, cuota y explicación."""
    return pd.DataFrame(
        [{"id_socio": evaluacion.socio.id, "nombre": evaluacion.socio.nombre,
          "tarifa": evaluacion.socio.tarifa, "cuota": evaluacion.socio.cuota,
          "riesgo": evaluacion.riesgo, "en_riesgo": evaluacion.en_riesgo,
          "causa": evaluacion.causa_principal, "explicacion": evaluacion.explicacion}
         for evaluacion in evaluaciones],
        columns=COLUMNAS_RIESGO,
    ).astype({"id_socio": int, "cuota": float, "riesgo": int, "en_riesgo": bool})


def visitas_por_mes(gimnasio: Gimnasio, id_socio: int, fecha: date,
                    meses: int = MESES_EVOLUCION) -> pd.Series:
    """Visitas del socio en cada uno de los ``meses`` meses que terminan en ``fecha``."""
    inicio_meses = pd.DatetimeIndex(primeros_de_mes(fecha, meses), name="mes")
    fechas = pd.to_datetime(pd.Series(gimnasio.visitas_hasta(id_socio, fecha), dtype=object))
    return (pd.Series(1, index=fechas).resample("MS").sum()
            .reindex(inicio_meses, fill_value=0).astype(int).rename("visitas"))


def tabla_senales(evaluacion: Evaluacion) -> pd.DataFrame:
    """Puntos y detalle de cada señal de una evaluación, indexados por la señal."""
    return pd.DataFrame(
        [{"senal": lectura.senal, "puntos": lectura.puntos, "detalle": lectura.detalle}
         for lectura in evaluacion.lecturas],
        columns=["senal", "puntos", "detalle"],
    ).set_index("senal")


def filtrar_riesgo(riesgo: pd.DataFrame, tarifas: Iterable[str], riesgo_minimo: int = 0,
                   texto: str = "") -> pd.DataFrame:
    """Socios de las tarifas indicadas con al menos ``riesgo_minimo``, de mayor a menor riesgo.

    Si se da ``texto``, solo los socios cuyo nombre lo contiene (sin distinguir
    mayúsculas) o cuyo número es exactamente ese texto.
    """
    texto = texto.strip()
    coincide = (riesgo["nombre"].str.contains(texto, case=False, regex=False)
                | (riesgo["id_socio"].astype(str) == texto))
    mascara = (riesgo["tarifa"].isin(list(tarifas)) & (riesgo["riesgo"] >= riesgo_minimo)
               & coincide)
    return riesgo[mascara].sort_values(["riesgo", "id_socio"], ascending=[False, True])


def tabla_acciones(acciones: Iterable[AccionRetencion]) -> pd.DataFrame:
    """Una fila por acción de retención con las fechas como fechas."""
    tabla = pd.DataFrame([accion.a_fila() for accion in acciones],
                         columns=["id", "id_socio", "tipo", "fecha_propuesta", "estado",
                                  "fecha_cierre"])
    return tabla.astype({"id": int, "id_socio": int}).assign(
        fecha_propuesta=pd.to_datetime(tabla["fecha_propuesta"]),
        fecha_cierre=pd.to_datetime(tabla["fecha_cierre"]),
    )


def evolucion_mensual(gimnasio: Gimnasio, meses: int = MESES_EVOLUCION,
                      fecha: date | None = None) -> pd.DataFrame:
    """Socios activos al empezar cada mes, bajas, tasa de abandono (%) y visitas.

    Abarca los ``meses`` meses que terminan en ``fecha`` (por defecto, la fecha
    de referencia) y no cuenta nada posterior a ella. El índice es el primer
    día de cada mes. La tasa de abandono es el porcentaje de los activos al
    empezar el mes que se dieron de baja en él.
    """
    fecha = fecha or gimnasio.fecha_referencia
    inicio_meses = pd.DatetimeIndex(primeros_de_mes(fecha, meses), name="mes")
    socios = tabla_socios(gimnasio)
    socios = socios.assign(fecha_baja=socios["fecha_baja"].where(
        socios["fecha_baja"] <= pd.Timestamp(fecha)))
    visitas = tabla_visitas(gimnasio)
    altas = socios["fecha_alta"].to_numpy()[:, None]
    bajas = socios["fecha_baja"].to_numpy()[:, None]
    activos = ((altas < inicio_meses.to_numpy()) & ~(bajas <= inicio_meses.to_numpy())).sum(axis=0)
    bajas_por_mes = (socios.dropna(subset=["fecha_baja"])
                     .groupby(pd.Grouper(key="fecha_baja", freq="MS")).size()
                     .reindex(inicio_meses, fill_value=0))
    visitas_por_mes = (visitas[visitas["fecha"] <= pd.Timestamp(fecha)]
                       .set_index("fecha").resample("MS").size()
                       .reindex(inicio_meses, fill_value=0))
    evolucion = pd.DataFrame({"activos": activos, "bajas": bajas_por_mes,
                              "visitas": visitas_por_mes}, index=inicio_meses)
    evolucion["tasa_abandono"] = (100 * evolucion["bajas"] / evolucion["activos"]).round(1)
    return evolucion.astype({"activos": int, "bajas": int, "visitas": int})


def riesgo_por_tarifa(riesgo: pd.DataFrame) -> pd.DataFrame:
    """Socios, riesgo medio, socios en riesgo y su porcentaje para cada tarifa."""
    por_tarifa = (riesgo.groupby("tarifa")
                  .agg(socios=("id_socio", "size"), riesgo_medio=("riesgo", "mean"),
                       en_riesgo=("en_riesgo", "sum"))
                  .reindex(list(TARIFAS), fill_value=0))
    por_tarifa["porcentaje_en_riesgo"] = (100 * por_tarifa["en_riesgo"]
                                          / por_tarifa["socios"]).fillna(0).round(1)
    return por_tarifa.astype({"socios": int, "en_riesgo": int}).round({"riesgo_medio": 1})


def causas_en_riesgo(riesgo: pd.DataFrame) -> pd.Series:
    """Cuántos socios en riesgo tienen cada causa principal, de más a menos."""
    return riesgo.loc[riesgo["en_riesgo"], "causa"].value_counts()


def acciones_hasta(acciones: pd.DataFrame, fecha: date) -> pd.DataFrame:
    """Acciones tal como se conocían en ``fecha``: propuestas antes y sin cierres posteriores.

    Las acciones que se cerraron después de ``fecha`` se dejan fuera, porque ese
    día todavía no se sabía su resultado.
    """
    limite = pd.Timestamp(fecha)
    conocidas = (acciones["fecha_propuesta"] <= limite) & ~(acciones["fecha_cierre"] > limite)
    return acciones[conocidas]


def eficacia_acciones(acciones: pd.DataFrame) -> pd.DataFrame:
    """Acciones de cada tipo por estado y tasa de retención (%) de las cerradas.

    La tasa queda vacía (NaN) en los tipos sin acciones cerradas.
    """
    eficacia = (pd.crosstab(acciones["tipo"], acciones["estado"])
                .reindex(index=list(TIPOS_ACCION), columns=list(ESTADOS_ACCION), fill_value=0)
                .rename_axis(index="tipo", columns=None))
    cerradas = eficacia["retenido"] + eficacia["perdido"]
    eficacia["cerradas"] = cerradas
    tasa = 100 * eficacia["retenido"] / cerradas.where(cerradas > 0)
    eficacia["tasa_retencion"] = tasa.round(1)
    return eficacia


def indicadores(evolucion: pd.DataFrame, riesgo: pd.DataFrame,
                eficacia: pd.DataFrame) -> dict[str, int | float | str | None]:
    """Cifras principales para la dirección, con tipos de Python."""
    en_riesgo = riesgo["en_riesgo"]
    tasas = eficacia.loc[eficacia["cerradas"] >= MINIMO_CERRADAS, "tasa_retencion"]
    return {
        "socios_activos": int(len(riesgo)),
        "en_riesgo": int(en_riesgo.sum()),
        "porcentaje_en_riesgo": round(float(100 * en_riesgo.mean()), 1) if len(riesgo) else 0.0,
        "ingresos_en_juego": round(float(riesgo.loc[en_riesgo, "cuota"].sum()), 2),
        "tasa_abandono_media": round(float(evolucion["tasa_abandono"].mean()), 1),
        "bajas_ultimo_mes": int(evolucion["bajas"].iloc[-1]),
        "mejor_accion": str(tasas.idxmax()) if len(tasas) else None,
    }


@dataclass(frozen=True, eq=False)
class ResumenDireccion:
    """Todo lo que necesitan el informe y los gráficos para la dirección."""

    fecha: date
    indicadores: dict[str, int | float | str | None]
    evolucion: pd.DataFrame
    por_tarifa: pd.DataFrame
    causas: pd.Series
    eficacia: pd.DataFrame


def resumen_direccion(gimnasio: Gimnasio, evaluaciones: list[Evaluacion],
                      acciones: Iterable[AccionRetencion],
                      fecha: date | None = None) -> ResumenDireccion:
    """Calcula las tablas y los indicadores del informe para la dirección a ``fecha``.

    Sin ``fecha``, usa la fecha de referencia de los datos. Las evaluaciones
    deben estar hechas en esa misma fecha.
    """
    fecha = fecha or gimnasio.fecha_referencia
    evolucion = evolucion_mensual(gimnasio, fecha=fecha)
    riesgo = tabla_riesgo(evaluaciones)
    eficacia = eficacia_acciones(acciones_hasta(tabla_acciones(acciones), fecha))
    return ResumenDireccion(fecha, indicadores(evolucion, riesgo, eficacia),
                            evolucion, riesgo_por_tarifa(riesgo), causas_en_riesgo(riesgo),
                            eficacia)
