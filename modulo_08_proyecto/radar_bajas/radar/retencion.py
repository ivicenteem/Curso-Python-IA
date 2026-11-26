"""Acciones de retención: recomendar una según la causa del riesgo y seguir su estado."""

import logging
from collections.abc import Iterable
from datetime import date

from .excepciones import AccionNoEncontrada, DatosNoValidos
from .modelos import AccionRetencion
from .radar import Evaluacion

logger = logging.getLogger(__name__)

# Acción que se propone según la señal que más pesa en el riesgo del socio
ACCION_POR_CAUSA = {
    "dias_sin_venir": "llamada",
    "caida_asistencia": "clase_gratis",
    "antiguedad": "clase_gratis",
    "subida_cuota": "descuento",
    "tarifa": "cambio_tarifa",
}


def recomendar(evaluacion: Evaluacion) -> str:
    """Tipo de acción adecuado para la causa principal del riesgo."""
    if evaluacion.causa_principal is None:
        raise DatosNoValidos(f"El socio {evaluacion.socio.id} no tiene señales de riesgo")
    return ACCION_POR_CAUSA[evaluacion.causa_principal]


class GestorRetencion:
    """Conjunto de acciones de retención, por identificador.

    El gestor crea las acciones y delega en cada una los cambios de estado.
    Un socio solo puede tener una acción abierta a la vez.
    """

    def __init__(self, acciones: Iterable[AccionRetencion] = ()) -> None:
        self._acciones = {accion.id: accion for accion in acciones}

    def __len__(self) -> int:
        return len(self._acciones)

    @property
    def acciones(self) -> list[AccionRetencion]:
        """Todas las acciones, por identificador."""
        return sorted(self._acciones.values(), key=lambda accion: accion.id)

    @property
    def abiertas(self) -> list[AccionRetencion]:
        """Acciones que todavía no han llegado a un estado final, por identificador."""
        return [accion for accion in self.acciones if not accion.cerrada]

    def accion(self, id_accion: int) -> AccionRetencion:
        """Devuelve la acción con ese identificador o lanza ``AccionNoEncontrada``."""
        try:
            return self._acciones[id_accion]
        except KeyError as error:
            raise AccionNoEncontrada(id_accion) from error

    def abierta_de(self, id_socio: int) -> AccionRetencion | None:
        """Acción abierta del socio, si la tiene."""
        return next((accion for accion in self.abiertas if accion.id_socio == id_socio), None)

    def proponer(self, evaluacion: Evaluacion, hoy: date) -> AccionRetencion:
        """Registra una acción para un socio en riesgo según su causa principal."""
        id_socio = evaluacion.socio.id
        if not evaluacion.en_riesgo:
            raise DatosNoValidos(
                f"El socio {id_socio} no está en riesgo (riesgo {evaluacion.riesgo})")
        if self.abierta_de(id_socio):
            raise DatosNoValidos(f"El socio {id_socio} ya tiene una acción abierta")
        accion = AccionRetencion(max(self._acciones, default=0) + 1, id_socio,
                                 recomendar(evaluacion), hoy)
        self._acciones[accion.id] = accion
        logger.info("Acción %d propuesta: %s para el socio %d", accion.id, accion.tipo, id_socio)
        return accion

    def proponer_en_riesgo(self, evaluaciones: Iterable[Evaluacion],
                           hoy: date) -> list[AccionRetencion]:
        """Propone una acción a cada socio en riesgo que no tenga ya una abierta."""
        return [self.proponer(evaluacion, hoy) for evaluacion in evaluaciones
                if evaluacion.en_riesgo and self.abierta_de(evaluacion.socio.id) is None]

    def avanzar(self, id_accion: int, nuevo: str, hoy: date) -> AccionRetencion:
        """Pasa una acción al estado ``nuevo``; la acción valida la transición."""
        accion = self.accion(id_accion)
        accion.avanzar(nuevo, hoy)
        logger.info("Acción %d pasa a %s", id_accion, nuevo)
        return accion
