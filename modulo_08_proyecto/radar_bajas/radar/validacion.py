"""Validación del radar con el histórico (backtesting).

Se calcula el riesgo en fechas de corte pasadas, usando solo lo que se sabía
ese día, y se compara con quién se dio de baja en los días siguientes. Se
repite en varias fechas de corte, una por mes, para tener casos suficientes.
"""

from dataclasses import asdict, dataclass
from datetime import date, timedelta

import pandas as pd

from .excepciones import DatosNoValidos, SinDatos
from .modelos import Gimnasio, primeros_de_mes
from .radar import Radar, rango_de_fechas

HORIZONTE_DIAS = 30          # se acierta si el socio avisado se va en estos días
NUMERO_CORTES = 6            # fechas de corte, una al principio de cada mes
UMBRALES_BARRIDO = (20, 30, 40, 50, 60, 70)
HORIZONTES_DIAS = (15, 30, 60)            # horizontes que se ofrecen para validar
CORTES_MINIMO, CORTES_MAXIMO = 3, 10      # número de fechas de corte que se ofrecen

SE_QUEDA, SE_VA = "se queda", "se va"
SIN_ALERTA, ALERTA = "sin alerta", "alerta"


@dataclass(frozen=True)
class Metricas:
    """Indicadores de acierto de las alertas frente a las bajas reales."""

    alertas: int
    aciertos: int
    bajas: int
    casos: int
    precision: float
    recall: float
    exactitud: float

    @property
    def tasa_base(self) -> float:
        """Proporción de casos que acabaron en baja: la precisión de avisar al azar."""
        return _proporcion(self.bajas, self.casos)

    @property
    def mejora(self) -> float:
        """Cuántas veces más precisa es la alerta que avisar al azar."""
        return _proporcion(self.precision, self.tasa_base)


@dataclass(frozen=True, eq=False)
class ResultadoValidacion:
    """Resultado del backtesting: matriz de confusión, métricas y barrido de umbrales."""

    cortes: list[date]
    horizonte_dias: int
    umbral: int
    matriz: pd.DataFrame
    metricas: Metricas
    barrido: pd.DataFrame


def _proporcion(parte: float, total: float) -> float:
    """``parte / total``, o 0 si el total es 0."""
    return parte / total if total else 0.0


def cortes_por_defecto(gimnasio: Gimnasio, horizonte_dias: int = HORIZONTE_DIAS,
                       numero: int = NUMERO_CORTES, fecha: date | None = None) -> list[date]:
    """Los ``numero`` primeros de mes más recientes cuyo horizonte termina antes de ``fecha``.

    Sin ``fecha``, se usa la fecha de referencia de los datos. Lanza
    ``DatosNoValidos`` si el primer corte cae antes de que haya historial suficiente.
    """
    fecha = fecha or gimnasio.fecha_referencia
    cortes = primeros_de_mes(fecha - timedelta(days=horizonte_dias), numero)
    primera_posible, _ = rango_de_fechas(gimnasio)
    if cortes[0] < primera_posible:
        raise DatosNoValidos(
            f"No hay historial para {numero} cortes con un horizonte de {horizonte_dias} días: "
            f"el primero sería el {cortes[0].isoformat()} y el historial permite empezar el "
            f"{primera_posible.isoformat()}")
    return cortes


def tabla_backtest(gimnasio: Gimnasio, radar: Radar, cortes: list[date],
                   horizonte_dias: int = HORIZONTE_DIAS) -> pd.DataFrame:
    """Una fila por socio activo en cada corte con su riesgo y si se fue dentro del horizonte.

    Columnas: ``id_socio``, ``corte`` y ``fecha_baja`` (fechas), ``riesgo`` (int) y
    ``se_va`` (bool).
    """
    filas = [{"id_socio": evaluacion.socio.id, "corte": corte, "riesgo": evaluacion.riesgo,
              "fecha_baja": evaluacion.socio.fecha_baja}
             for corte in cortes for evaluacion in radar.evaluar_todos(gimnasio, corte)]
    if not filas:
        raise SinDatos("No hay socios activos en las fechas de corte")
    tabla = pd.DataFrame(filas)
    tabla["corte"] = pd.to_datetime(tabla["corte"])
    tabla["fecha_baja"] = pd.to_datetime(tabla["fecha_baja"])
    limite = tabla["corte"] + pd.Timedelta(days=horizonte_dias)
    tabla["se_va"] = (tabla["fecha_baja"] > tabla["corte"]) & (tabla["fecha_baja"] <= limite)
    return tabla


def matriz_confusion(se_va: pd.Series, alerta: pd.Series) -> pd.DataFrame:
    """Tabla 2 × 2 de casos: filas, lo que pasó; columnas, lo que avisó el radar."""
    return (pd.crosstab(se_va, alerta)
            .reindex(index=[False, True], columns=[False, True], fill_value=0)
            .rename(index={False: SE_QUEDA, True: SE_VA},
                    columns={False: SIN_ALERTA, True: ALERTA})
            .rename_axis(index="real", columns="radar"))


def calcular_metricas(matriz: pd.DataFrame) -> Metricas:
    """Precisión, recall y exactitud a partir de una matriz de confusión."""
    aciertos = int(matriz.loc[SE_VA, ALERTA])
    alertas = int(matriz[ALERTA].sum())
    bajas = int(matriz.loc[SE_VA].sum())
    casos = int(matriz.to_numpy().sum())
    correctos = aciertos + int(matriz.loc[SE_QUEDA, SIN_ALERTA])
    return Metricas(alertas, aciertos, bajas, casos, _proporcion(aciertos, alertas),
                    _proporcion(aciertos, bajas), _proporcion(correctos, casos))


def barrido_umbrales(tabla: pd.DataFrame, umbrales: tuple[int, ...] = UMBRALES_BARRIDO
                     ) -> pd.DataFrame:
    """Métricas para cada umbral posible: ayuda a elegir el equilibrio entre precisión y recall."""
    filas = [{"umbral": umbral} | asdict(calcular_metricas(
        matriz_confusion(tabla["se_va"], tabla["riesgo"] >= umbral))) for umbral in umbrales]
    return pd.DataFrame(filas).set_index("umbral")


def validar(gimnasio: Gimnasio, radar: Radar, horizonte_dias: int = HORIZONTE_DIAS,
            numero_cortes: int = NUMERO_CORTES, fecha: date | None = None) -> ResultadoValidacion:
    """Hace el backtesting del radar con los datos del gimnasio hasta ``fecha``."""
    if horizonte_dias <= 0 or numero_cortes <= 0:
        raise DatosNoValidos("El horizonte y el número de cortes deben ser positivos")
    cortes = cortes_por_defecto(gimnasio, horizonte_dias, numero_cortes, fecha)
    tabla = tabla_backtest(gimnasio, radar, cortes, horizonte_dias)
    return resultado_desde_tabla(tabla, cortes, horizonte_dias, radar.umbral)


def resultado_desde_tabla(tabla: pd.DataFrame, cortes: list[date], horizonte_dias: int,
                          umbral: int) -> ResultadoValidacion:
    """Resultado de la validación para un umbral a partir de una tabla de backtesting.

    El riesgo de cada caso no depende del umbral, así que la misma tabla sirve
    para probar umbrales distintos sin volver a evaluar a los socios.
    """
    matriz = matriz_confusion(tabla["se_va"], tabla["riesgo"] >= umbral)
    return ResultadoValidacion(cortes, horizonte_dias, umbral, matriz,
                               calcular_metricas(matriz), barrido_umbrales(tabla))
