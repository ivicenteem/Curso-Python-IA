"""Modelo de dominio: socios, visitas, acciones de retención y el gimnasio que los reúne.

Cada objeto valida sus datos al crearse, así que nunca existe en un estado
incorrecto. Las conversiones ``a_fila`` y ``desde_fila`` son inversas y son
lo que se escribe y se lee de los CSV.
"""

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property

from .excepciones import DatosNoValidos, SinDatos, SocioNoEncontrado, TransicionNoValida

TARIFAS = ("mensual", "trimestral", "anual")

TIPOS_ACCION = ("llamada", "descuento", "clase_gratis", "cambio_tarifa")
ESTADOS_ACCION = ("propuesta", "contactado", "retenido", "perdido")
ESTADOS_FINALES = ("retenido", "perdido")

# Desde cada estado de una acción, a cuáles se puede pasar
TRANSICIONES_ACCION = {
    "propuesta": ("contactado", "perdido"),
    "contactado": ("retenido", "perdido"),
    "retenido": (),
    "perdido": (),
}

CAMPOS_SOCIO = ["id", "nombre", "fecha_alta", "tarifa", "cuota", "cuota_anterior",
                "fecha_cambio_cuota", "fecha_baja"]
CAMPOS_VISITA = ["id_socio", "fecha"]
CAMPOS_ACCION = ["id", "id_socio", "tipo", "fecha_propuesta", "estado", "fecha_cierre"]


def primeros_de_mes(fin: date, meses: int) -> list[date]:
    """Primer día de cada uno de los ``meses`` meses que terminan en el mes de ``fin``."""
    indice_fin = fin.year * 12 + fin.month - 1
    return [date(indice // 12, indice % 12 + 1, 1)
            for indice in range(indice_fin - meses + 1, indice_fin + 1)]


def _a_texto(fecha: date | None) -> str:
    """Convierte una fecha opcional en texto ISO; ``None`` es la cadena vacía."""
    return fecha.isoformat() if fecha else ""


def _a_fecha(texto: str) -> date | None:
    """Convierte un texto ISO en fecha; la cadena vacía es ``None``.

    Lanza ``ValueError`` si el texto no es una fecha ISO.
    """
    return date.fromisoformat(texto) if texto.strip() else None


def _comprobar_positivo(valor: float, nombre: str) -> None:
    """Lanza ``DatosNoValidos`` si ``valor`` no es mayor que cero."""
    if valor <= 0:
        raise DatosNoValidos(f"{nombre} debe ser mayor que cero: {valor}")


def _error_de_fila(clase: str, error: Exception) -> DatosNoValidos:
    """Construye el error que se lanza cuando una fila del CSV no se puede convertir."""
    return DatosNoValidos(f"Fila de {clase} no válida: {error!r}")


@dataclass
class Socio:
    """Un socio del gimnasio.

    ``cuota`` es lo que paga al mes ahora. Si la cuota cambió, ``cuota_anterior``
    es la de antes y ``fecha_cambio_cuota`` el día del cambio; si no, la cuota
    anterior es igual a la actual y la fecha es ``None``.
    """

    id: int
    nombre: str
    fecha_alta: date
    tarifa: str
    cuota: float
    cuota_anterior: float | None = None
    fecha_cambio_cuota: date | None = None
    fecha_baja: date | None = None

    def __post_init__(self) -> None:
        """Limpia y valida los datos del socio."""
        self.nombre = self.nombre.strip()
        if self.cuota_anterior is None:
            self.cuota_anterior = self.cuota
        _comprobar_positivo(self.id, "El identificador")
        if not self.nombre:
            raise DatosNoValidos("El nombre es obligatorio")
        if self.tarifa not in TARIFAS:
            raise DatosNoValidos(f"Tarifa no válida: {self.tarifa}")
        _comprobar_positivo(self.cuota, "La cuota")
        _comprobar_positivo(self.cuota_anterior, "La cuota anterior")
        if self.fecha_cambio_cuota and self.fecha_cambio_cuota < self.fecha_alta:
            raise DatosNoValidos("La cuota no puede cambiar antes del alta")
        if self.fecha_baja and self.fecha_baja < self.fecha_alta:
            raise DatosNoValidos("La baja no puede ser anterior al alta")

    @property
    def activo(self) -> bool:
        """Indica si el socio sigue dado de alta."""
        return self.fecha_baja is None

    @property
    def subida_cuota(self) -> float:
        """Variación de la cuota respecto a la anterior, en porcentaje (negativa si bajó)."""
        return round((self.cuota / self.cuota_anterior - 1) * 100, 1)

    def activo_en(self, fecha: date) -> bool:
        """Indica si el socio estaba dado de alta el día ``fecha``."""
        return self.fecha_alta <= fecha and (self.fecha_baja is None or self.fecha_baja > fecha)

    def antiguedad_dias(self, fecha: date) -> int:
        """Días transcurridos desde el alta hasta ``fecha``."""
        return (fecha - self.fecha_alta).days

    def a_fila(self) -> dict[str, str]:
        """Devuelve el socio como diccionario de cadenas con las claves de ``CAMPOS_SOCIO``."""
        return {
            "id": str(self.id),
            "nombre": self.nombre,
            "fecha_alta": _a_texto(self.fecha_alta),
            "tarifa": self.tarifa,
            "cuota": f"{self.cuota:.2f}",
            "cuota_anterior": f"{self.cuota_anterior:.2f}",
            "fecha_cambio_cuota": _a_texto(self.fecha_cambio_cuota),
            "fecha_baja": _a_texto(self.fecha_baja),
        }

    @classmethod
    def desde_fila(cls, fila: dict[str, str]) -> "Socio":
        """Crea un socio a partir de una fila como la de ``a_fila``.

        Lanza ``DatosNoValidos`` si falta una columna o un número o una fecha
        no se pueden convertir.
        """
        try:
            datos = {
                "id": int(fila["id"]),
                "nombre": fila["nombre"],
                "fecha_alta": date.fromisoformat(fila["fecha_alta"]),
                "tarifa": fila["tarifa"],
                "cuota": float(fila["cuota"]),
                "cuota_anterior": float(fila["cuota_anterior"]),
                "fecha_cambio_cuota": _a_fecha(fila["fecha_cambio_cuota"]),
                "fecha_baja": _a_fecha(fila["fecha_baja"]),
            }
        except (KeyError, ValueError, TypeError) as error:
            raise _error_de_fila("socio", error) from error
        return cls(**datos)


@dataclass(frozen=True, order=True)
class Visita:
    """Una visita de un socio al gimnasio. Es inmutable."""

    id_socio: int
    fecha: date

    def __post_init__(self) -> None:
        """Valida el identificador del socio."""
        _comprobar_positivo(self.id_socio, "El identificador del socio")

    def a_fila(self) -> dict[str, str]:
        """Devuelve la visita como diccionario de cadenas con las claves de ``CAMPOS_VISITA``."""
        return {"id_socio": str(self.id_socio), "fecha": self.fecha.isoformat()}

    @classmethod
    def desde_fila(cls, fila: dict[str, str]) -> "Visita":
        """Crea una visita a partir de una fila como la de ``a_fila``."""
        try:
            datos = {"id_socio": int(fila["id_socio"]),
                     "fecha": date.fromisoformat(fila["fecha"])}
        except (KeyError, ValueError, TypeError) as error:
            raise _error_de_fila("visita", error) from error
        return cls(**datos)


@dataclass
class AccionRetencion:
    """Una acción para retener a un socio en riesgo.

    Sigue el flujo propuesta → contactado → retenido / perdido, definido en
    ``TRANSICIONES_ACCION``. Al llegar a un estado final se anota la fecha de
    cierre.
    """

    id: int
    id_socio: int
    tipo: str
    fecha_propuesta: date
    estado: str = "propuesta"
    fecha_cierre: date | None = None

    def __post_init__(self) -> None:
        """Valida que la acción sea coherente."""
        _comprobar_positivo(self.id, "El identificador")
        _comprobar_positivo(self.id_socio, "El identificador del socio")
        if self.tipo not in TIPOS_ACCION:
            raise DatosNoValidos(f"Tipo de acción no válido: {self.tipo}")
        _comprobar_estado(self.estado)
        if self.cerrada != (self.fecha_cierre is not None):
            raise DatosNoValidos("Solo las acciones cerradas tienen fecha de cierre")
        if self.fecha_cierre and self.fecha_cierre < self.fecha_propuesta:
            raise DatosNoValidos("El cierre no puede ser anterior a la propuesta")

    @property
    def cerrada(self) -> bool:
        """Indica si la acción ha llegado a un estado final."""
        return self.estado in ESTADOS_FINALES

    def avanzar(self, nuevo: str, hoy: date) -> None:
        """Pasa la acción al estado ``nuevo`` si el flujo lo permite.

        Lanza ``DatosNoValidos`` si el estado no existe o ``hoy`` es anterior
        a la propuesta, y ``TransicionNoValida`` si el cambio no está permitido.
        """
        _comprobar_estado(nuevo)
        if nuevo not in TRANSICIONES_ACCION[self.estado]:
            raise TransicionNoValida(self.estado, nuevo)
        if hoy < self.fecha_propuesta:
            raise DatosNoValidos("La fecha es anterior a la propuesta")
        self.estado = nuevo
        if self.cerrada:
            self.fecha_cierre = hoy

    def a_fila(self) -> dict[str, str]:
        """Devuelve la acción como diccionario de cadenas con las claves de ``CAMPOS_ACCION``."""
        return {
            "id": str(self.id),
            "id_socio": str(self.id_socio),
            "tipo": self.tipo,
            "fecha_propuesta": self.fecha_propuesta.isoformat(),
            "estado": self.estado,
            "fecha_cierre": _a_texto(self.fecha_cierre),
        }

    @classmethod
    def desde_fila(cls, fila: dict[str, str]) -> "AccionRetencion":
        """Crea una acción a partir de una fila como la de ``a_fila``."""
        try:
            datos = {
                "id": int(fila["id"]),
                "id_socio": int(fila["id_socio"]),
                "tipo": fila["tipo"],
                "fecha_propuesta": date.fromisoformat(fila["fecha_propuesta"]),
                "estado": fila["estado"],
                "fecha_cierre": _a_fecha(fila["fecha_cierre"]),
            }
        except (KeyError, ValueError, TypeError) as error:
            raise _error_de_fila("acción", error) from error
        return cls(**datos)


def _comprobar_estado(estado: str) -> None:
    """Lanza ``DatosNoValidos`` si ``estado`` no es un estado de acción."""
    if estado not in ESTADOS_ACCION:
        raise DatosNoValidos(f"Estado no válido: {estado}")


@dataclass
class Gimnasio:
    """Los socios del gimnasio y sus visitas.

    Se crea con ``desde_listas``, que comprueba que los datos sean coherentes.
    """

    socios: dict[int, Socio] = field(default_factory=dict)
    visitas: list[Visita] = field(default_factory=list)

    @classmethod
    def desde_listas(cls, socios: list[Socio], visitas: list[Visita]) -> "Gimnasio":
        """Crea el gimnasio comprobando que no haya socios repetidos ni visitas huérfanas."""
        por_id = {socio.id: socio for socio in sorted(socios, key=lambda socio: socio.id)}
        if len(por_id) != len(socios):
            raise DatosNoValidos("Hay socios con el identificador repetido")
        huerfanas = {visita.id_socio for visita in visitas} - por_id.keys()
        if huerfanas:
            raise DatosNoValidos(f"Hay visitas de socios que no existen: {sorted(huerfanas)}")
        return cls(por_id, sorted(visitas))

    @property
    def vacio(self) -> bool:
        """Indica si no hay ningún socio."""
        return not self.socios

    @cached_property
    def visitas_por_socio(self) -> dict[int, list[date]]:
        """Fechas de visita de cada socio, ordenadas. Los socios sin visitas no aparecen."""
        agrupadas: dict[int, list[date]] = {}
        for visita in self.visitas:
            agrupadas.setdefault(visita.id_socio, []).append(visita.fecha)
        return agrupadas

    @property
    def fecha_referencia(self) -> date:
        """Último día con datos: la visita o la baja más reciente.

        Es el «hoy» con el que se analizan los datos. Lanza ``SinDatos`` si el
        gimnasio está vacío.
        """
        if self.vacio:
            raise SinDatos("No hay datos: genera datos simulados o carga una carpeta")
        fechas_socios = {fecha for socio in self.socios.values()
                         for fecha in (socio.fecha_alta, socio.fecha_baja) if fecha}
        return max(fechas_socios | {visita.fecha for visita in self.visitas})

    def socio(self, id_socio: int) -> Socio:
        """Devuelve el socio con ese identificador o lanza ``SocioNoEncontrado``."""
        try:
            return self.socios[id_socio]
        except KeyError as error:
            raise SocioNoEncontrado(id_socio) from error

    def visitas_hasta(self, id_socio: int, fecha: date) -> list[date]:
        """Fechas de visita del socio hasta ``fecha`` incluida, ordenadas."""
        fechas = self.visitas_por_socio.get(id_socio, [])
        return fechas[:bisect_right(fechas, fecha)]

    def activos_en(self, fecha: date) -> list[Socio]:
        """Socios dados de alta el día ``fecha``, por identificador."""
        return [socio for socio in self.socios.values() if socio.activo_en(fecha)]
