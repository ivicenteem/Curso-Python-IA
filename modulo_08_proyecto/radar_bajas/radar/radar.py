"""El radar: combina las señales en un índice de riesgo de 0 a 100 con su explicación."""

from dataclasses import dataclass
from datetime import date, timedelta

from .excepciones import DatosNoValidos
from .modelos import Gimnasio, Socio
from .senales import (HISTORICO_MINIMO_DIAS, VENTANA_RECIENTE_DIAS, AntiguedadBaja,
                      CaidaAsistencia, DiasSinVenir, Lectura, Senal, SubidaCuota, TipoTarifa)

# Puntos máximos de cada señal en el radar por defecto (suman 100)
PESOS = {
    DiasSinVenir: 35,
    CaidaAsistencia: 25,
    AntiguedadBaja: 15,
    SubidaCuota: 15,
    TipoTarifa: 10,
}

# A partir de este riesgo un socio se considera en riesgo de baja
UMBRAL_RIESGO = 40

# Días de datos necesarios antes de la primera fecha que se puede analizar:
# el último mes más un mes de historial con el que comparar la asistencia
DIAS_HISTORIAL_MINIMO = VENTANA_RECIENTE_DIAS + HISTORICO_MINIMO_DIAS


def rango_de_fechas(gimnasio: Gimnasio) -> tuple[date, date]:
    """Primera y última fecha en las que se puede analizar el gimnasio.

    La primera es la del primer dato más ``DIAS_HISTORIAL_MINIMO`` días (sin
    pasar de la última); la última es la fecha de referencia de los datos.
    """
    ultima = gimnasio.fecha_referencia
    primera = gimnasio.fecha_inicio + timedelta(days=DIAS_HISTORIAL_MINIMO)
    return min(primera, ultima), ultima


def comprobar_fecha(gimnasio: Gimnasio, fecha: date) -> date:
    """Devuelve ``fecha`` si está en el rango analizable; si no, lanza ``DatosNoValidos``."""
    primera, ultima = rango_de_fechas(gimnasio)
    if not primera <= fecha <= ultima:
        raise DatosNoValidos(f"La fecha de análisis debe estar entre el {primera.isoformat()} "
                             f"y el {ultima.isoformat()}")
    return fecha


@dataclass(frozen=True)
class Evaluacion:
    """El riesgo de un socio en una fecha, con las lecturas de cada señal de mayor a menor."""

    socio: Socio
    fecha: date
    riesgo: int
    lecturas: tuple[Lectura, ...]
    umbral: int = UMBRAL_RIESGO

    @property
    def en_riesgo(self) -> bool:
        """Indica si el riesgo alcanza el umbral."""
        return self.riesgo >= self.umbral

    @property
    def senales_activas(self) -> list[Lectura]:
        """Lecturas que suman algún punto, de mayor a menor."""
        return [lectura for lectura in self.lecturas if lectura.puntos > 0]

    @property
    def causa_principal(self) -> str | None:
        """Nombre de la señal que más puntos suma, o ``None`` si ninguna suma."""
        activas = self.senales_activas
        return activas[0].senal if activas else None

    @property
    def explicacion(self) -> str:
        """Texto corto del riesgo, por ejemplo "Riesgo 82: 19 días sin venir; asistencia -70 %"."""
        motivos = "; ".join(lectura.detalle for lectura in self.senales_activas)
        return f"Riesgo {self.riesgo}: {motivos or 'sin señales de alerta'}"


class Radar:
    """Calcula el riesgo de baja de los socios combinando un conjunto de señales."""

    def __init__(self, senales: list[Senal], umbral: int = UMBRAL_RIESGO) -> None:
        nombres = [senal.nombre for senal in senales]
        if not senales:
            raise DatosNoValidos("El radar necesita al menos una señal")
        if len(set(nombres)) != len(nombres):
            raise DatosNoValidos(f"Hay señales repetidas: {nombres}")
        if not 0 <= umbral <= 100:
            raise DatosNoValidos(f"El umbral debe estar entre 0 y 100: {umbral}")
        self.senales = list(senales)
        self.umbral = umbral

    @classmethod
    def por_defecto(cls, umbral: int = UMBRAL_RIESGO) -> "Radar":
        """Radar con las cinco señales y los pesos de ``PESOS``."""
        return cls([clase(peso) for clase, peso in PESOS.items()], umbral)

    @property
    def peso_total(self) -> float:
        """Suma de los pesos de las señales: los puntos que valen un riesgo de 100."""
        return sum(senal.peso for senal in self.senales)

    def evaluar(self, socio: Socio, visitas: list[date], fecha: date) -> Evaluacion:
        """Evalúa un socio en ``fecha`` a partir de sus visitas hasta ese día, ordenadas."""
        lecturas = sorted((senal.leer(socio, visitas, fecha) for senal in self.senales),
                          key=lambda lectura: lectura.puntos, reverse=True)
        puntos = sum(lectura.puntos for lectura in lecturas)
        riesgo = round(100 * puntos / self.peso_total)
        return Evaluacion(socio, fecha, riesgo, tuple(lecturas), self.umbral)

    def evaluar_socio(self, gimnasio: Gimnasio, id_socio: int,
                      fecha: date | None = None) -> Evaluacion:
        """Evalúa un socio del gimnasio. Sin ``fecha``, usa la fecha de referencia de los datos.

        Lanza ``SocioNoEncontrado`` si no existe y ``DatosNoValidos`` si no
        estaba dado de alta en esa fecha.
        """
        fecha = fecha or gimnasio.fecha_referencia
        socio = gimnasio.socio(id_socio)
        if not socio.activo_en(fecha):
            raise DatosNoValidos(
                f"El socio {id_socio} no estaba dado de alta el {fecha.isoformat()}")
        return self.evaluar(socio, gimnasio.visitas_hasta(id_socio, fecha), fecha)

    def evaluar_todos(self, gimnasio: Gimnasio, fecha: date | None = None) -> list[Evaluacion]:
        """Evalúa los socios activos en ``fecha``, de mayor a menor riesgo.

        Sin ``fecha``, usa la fecha de referencia de los datos. A igual riesgo
        van primero los de menor identificador.
        """
        fecha = fecha or gimnasio.fecha_referencia
        evaluaciones = [self.evaluar(socio, gimnasio.visitas_hasta(socio.id, fecha), fecha)
                        for socio in gimnasio.activos_en(fecha)]
        return sorted(evaluaciones,
                      key=lambda evaluacion: (-evaluacion.riesgo, evaluacion.socio.id))
