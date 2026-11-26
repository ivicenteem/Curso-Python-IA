"""Señales de riesgo de baja.

Cada señal mira un aspecto del socio en una fecha y devuelve una intensidad
entre 0 (nada preocupante) y 1 (alarma máxima) y un texto que la explica. El
radar multiplica la intensidad por el peso de la señal para obtener puntos.

Todas las señales comparten la interfaz de ``Senal`` y el radar las trata
igual: añadir una señal nueva es escribir una subclase.
"""

from abc import ABC, abstractmethod
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date, timedelta

from .excepciones import DatosNoValidos
from .modelos import Socio

# Días sin venir: por debajo del primer valor es normal; desde el segundo, alarma
DIAS_SIN_VENIR_NORMAL = 7
DIAS_SIN_VENIR_ALARMA = 30

# Caída de asistencia: último mes frente a la media mensual de los meses anteriores
VENTANA_RECIENTE_DIAS = 30
VENTANA_HISTORICA_DIAS = 90
HISTORICO_MINIMO_DIAS = 30
CAIDA_NORMAL = 0.2
CAIDA_ALARMA = 0.9

# Antigüedad: un socio con menos días que el primer valor es nuevo del todo
ANTIGUEDAD_NUEVO_DIAS = 30
ANTIGUEDAD_CONSOLIDADO_DIAS = 180

# Intensidad de cada tarifa: la mensual se deja sin penalización
RIESGO_TARIFA = {"mensual": 1.0, "trimestral": 0.5, "anual": 0.1}

# Subida de cuota: cuenta durante unos días y una subida del 20 % es alarma
VENTANA_SUBIDA_DIAS = 90
SUBIDA_ALARMA = 20.0


def escalar(valor: float, normal: float, alarma: float) -> float:
    """Lleva ``valor`` a una intensidad lineal entre 0 (en ``normal``) y 1 (en ``alarma``)."""
    return min(max((valor - normal) / (alarma - normal), 0.0), 1.0)


@dataclass(frozen=True)
class Lectura:
    """Resultado de aplicar una señal a un socio: cuántos puntos suma y por qué."""

    senal: str
    puntos: float
    detalle: str


class Senal(ABC):
    """Una señal de riesgo con su peso, que son los puntos que suma con intensidad 1."""

    nombre: str = ""

    def __init__(self, peso: float) -> None:
        if peso <= 0:
            raise DatosNoValidos(f"El peso de la señal debe ser positivo: {peso}")
        self.peso = peso

    def __repr__(self) -> str:
        return f"{type(self).__name__}(peso={self.peso})"

    def leer(self, socio: Socio, visitas: list[date], fecha: date) -> Lectura:
        """Aplica la señal al socio en ``fecha`` con sus visitas hasta ese día, ordenadas."""
        intensidad, detalle = self.medir(socio, visitas, fecha)
        return Lectura(self.nombre, round(self.peso * intensidad, 1), detalle)

    @abstractmethod
    def medir(self, socio: Socio, visitas: list[date], fecha: date) -> tuple[float, str]:
        """Devuelve la intensidad, entre 0 y 1, y el texto que la explica."""


class DiasSinVenir(Senal):
    """Cuántos días lleva el socio sin venir. Sin visitas, cuenta desde el alta."""

    nombre = "dias_sin_venir"

    def medir(self, socio: Socio, visitas: list[date], fecha: date) -> tuple[float, str]:
        """Más días sin venir, más intensidad."""
        ultima = visitas[-1] if visitas else socio.fecha_alta
        dias = (fecha - ultima).days
        intensidad = escalar(dias, DIAS_SIN_VENIR_NORMAL, DIAS_SIN_VENIR_ALARMA)
        return intensidad, f"{dias} días sin venir"


class CaidaAsistencia(Senal):
    """Visitas del último mes frente a su media mensual de los meses anteriores."""

    nombre = "caida_asistencia"

    def medir(self, socio: Socio, visitas: list[date], fecha: date) -> tuple[float, str]:
        """Cuanto mayor es la caída, más intensidad. Sin histórico suficiente no puntúa."""
        inicio_reciente = fecha - timedelta(days=VENTANA_RECIENTE_DIAS)
        inicio_historico = max(socio.fecha_alta, fecha - timedelta(days=VENTANA_HISTORICA_DIAS))
        dias_historico = (inicio_reciente - inicio_historico).days
        corte_reciente = bisect_right(visitas, inicio_reciente)
        historicas = corte_reciente - bisect_left(visitas, inicio_historico)
        if dias_historico < HISTORICO_MINIMO_DIAS or historicas == 0:
            return 0.0, "sin histórico de asistencia"
        media = historicas * VENTANA_RECIENTE_DIAS / dias_historico
        caida = 1 - (len(visitas) - corte_reciente) / media
        return escalar(caida, CAIDA_NORMAL, CAIDA_ALARMA), f"asistencia {-caida * 100:+.0f} %"


class AntiguedadBaja(Senal):
    """Los socios recién llegados se van más: todavía no han cogido el hábito."""

    nombre = "antiguedad"

    def medir(self, socio: Socio, visitas: list[date], fecha: date) -> tuple[float, str]:
        """Intensidad máxima el primer mes, que baja hasta 0 al consolidarse."""
        dias = socio.antiguedad_dias(fecha)
        intensidad = 1 - escalar(dias, ANTIGUEDAD_NUEVO_DIAS, ANTIGUEDAD_CONSOLIDADO_DIAS)
        return intensidad, f"socio desde hace {dias} días"


class TipoTarifa(Senal):
    """Las tarifas sin permanencia facilitan irse."""

    nombre = "tarifa"

    def medir(self, socio: Socio, visitas: list[date], fecha: date) -> tuple[float, str]:
        """Intensidad fija según ``RIESGO_TARIFA``."""
        return RIESGO_TARIFA[socio.tarifa], f"tarifa {socio.tarifa}"


class SubidaCuota(Senal):
    """Una subida de cuota reciente empuja a replantearse la suscripción."""

    nombre = "subida_cuota"

    def medir(self, socio: Socio, visitas: list[date], fecha: date) -> tuple[float, str]:
        """Solo cuentan las subidas de los últimos ``VENTANA_SUBIDA_DIAS`` días hasta ``fecha``."""
        cambio = socio.fecha_cambio_cuota
        if cambio is None or not 0 <= (fecha - cambio).days <= VENTANA_SUBIDA_DIAS:
            return 0.0, "sin subida reciente"
        subida = socio.subida_cuota
        detalle = f"cuota {subida:+.0f} % hace {(fecha - cambio).days} días"
        return escalar(subida, 0, SUBIDA_ALARMA), detalle
