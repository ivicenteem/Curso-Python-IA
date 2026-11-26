"""Simulador de datos realistas y reproducibles de un gimnasio.

Genera socios, visitas y bajas con NumPy y una semilla fija: la misma semilla
produce siempre los mismos datos. Las reglas imitan lo que se ve en un
gimnasio real:

- Las tarifas sin permanencia, los socios nuevos y las subidas de cuota
  aumentan la probabilidad mensual de baja.
- Antes de darse de baja, el socio va cada vez menos y deja de venir unas
  semanas antes de irse.
- También se simulan las bajas de los meses siguientes a ``fin``: no se
  guardan, porque todavía no han ocurrido, pero su declive ya se ve en las
  visitas, igual que en un gimnasio real el día de hoy.
- Algunos socios fieles hacen una pausa (vacaciones, una lesión) y vuelven:
  son las falsas alarmas que cualquier modelo tiene que soportar.

``simular_acciones`` añade un histórico de acciones de retención: cada mes se
propone una acción a los socios en riesgo y su resultado sale de los propios
datos (perdido si el socio se dio de baja poco después, retenido si no).
"""

from dataclasses import replace
from datetime import date, timedelta

import numpy as np

from .excepciones import DatosNoValidos
from .modelos import TARIFAS, AccionRetencion, Gimnasio, Socio, Visita, primeros_de_mes
from .radar import Radar
from .retencion import GestorRetencion

SEMILLA = 42
N_SOCIOS = 300
MESES = 12
FECHA_FIN = date(2026, 10, 31)

PROPORCION_ANTIGUOS = 0.7          # socios que ya estaban antes del periodo simulado
ANTIGUEDAD_MAXIMA_DIAS = 1000
PROB_TARIFA = {"mensual": 0.5, "trimestral": 0.3, "anual": 0.2}
CUOTA_BASE = {"mensual": 45.0, "trimestral": 40.0, "anual": 35.0}

BAJA_MENSUAL = {"mensual": 0.035, "trimestral": 0.02, "anual": 0.01}
EXTRA_BAJA_NUEVO = 0.05            # durante los primeros DIAS_SOCIO_NUEVO días
DIAS_SOCIO_NUEVO = 90
EXTRA_BAJA_SUBIDA = 0.06           # durante los DIAS_EFECTO_SUBIDA días tras una subida
DIAS_EFECTO_SUBIDA = 90
DIAS_MINIMOS_ANTES_DE_BAJA = 14
MESES_FUTUROS = 2                  # meses tras el final con bajas que aún no han ocurrido

PROB_SUBIDA = 0.3
SUBIDA_MINIMA, SUBIDA_MAXIMA = 0.08, 0.25

VISITAS_MES_MEDIA = 8.0
VISITAS_MES_MINIMA = 3.0
DIAS_DECLIVE = 60                  # la asistencia empieza a caer estos días antes de la baja
SILENCIO_MINIMO, SILENCIO_MAXIMO = 7, 25
PROB_PAUSA = 0.15
PAUSA_MINIMA, PAUSA_MAXIMA = 10, 25

MESES_CON_ACCIONES = 5
DIAS_HASTA_CONTACTO = 3
DIAS_HASTA_RETENCION = 30          # sin baja en este plazo, el socio cuenta como retenido
DIAS_SEGUIMIENTO = 60              # una baja dentro de este plazo cuenta como perdido

NOMBRES = ("Lucía", "Hugo", "Martina", "Mateo", "Sofía", "Leo", "Julia", "Daniel", "Paula",
           "Álvaro", "Valeria", "Pablo", "Emma", "Manuel", "Carmen", "Javier", "Irene", "Diego",
           "Elena", "Adrián", "Nerea", "Iñaki", "Ainhoa", "Marcos", "Laura", "Sergio")
APELLIDOS = ("García", "Martínez", "López", "Sánchez", "Pérez", "Gómez", "Martín", "Ruiz",
             "Díaz", "Hernández", "Moreno", "Muñoz", "Álvarez", "Romero", "Navarro", "Torres",
             "Etxeberria", "Vidal", "Castro", "Ortega", "Rubio", "Molina", "Serrano", "Blanco")


def simular(n_socios: int = N_SOCIOS, *, fin: date = FECHA_FIN, meses: int = MESES,
            semilla: int = SEMILLA) -> Gimnasio:
    """Genera un gimnasio con ``n_socios`` socios y ``meses`` meses de actividad hasta ``fin``."""
    if n_socios <= 0 or meses <= 0:
        raise DatosNoValidos("El número de socios y de meses debe ser positivo")
    generador = np.random.default_rng(semilla)
    meses_simulados = primeros_de_mes(fin, meses)
    meses_siguientes = primeros_de_mes(date(fin.year + 1, fin.month, 1), 12)
    meses_bajas = meses_simulados + meses_siguientes[:MESES_FUTUROS]
    fin_bajas = meses_siguientes[MESES_FUTUROS] - _dias(1)
    socios, visitas = [], []
    for id_socio in range(1, n_socios + 1):
        socio = _simular_socio(generador, id_socio, meses_simulados[0], fin)
        baja = _simular_baja(generador, socio, meses_bajas, fin_bajas)
        visitas += _simular_visitas(generador, socio, baja, meses_simulados[0], fin)
        socios.append(replace(socio, fecha_baja=baja if baja and baja <= fin else None))
    return Gimnasio.desde_listas(socios, visitas)


def _dias(numero: int | np.integer) -> timedelta:
    """``timedelta`` de ``numero`` días; acepta enteros de NumPy."""
    return timedelta(days=int(numero))


def _fecha_entre(generador: np.random.Generator, desde: date, hasta: date) -> date:
    """Fecha al azar entre ``desde`` y ``hasta``, ambas incluidas."""
    return desde + _dias(generador.integers(0, (hasta - desde).days + 1))


def _simular_socio(generador: np.random.Generator, id_socio: int, inicio: date,
                   fin: date) -> Socio:
    """Genera un socio, todavía sin baja, con su alta, tarifa y posible subida de cuota."""
    tarifa = str(generador.choice(TARIFAS, p=[PROB_TARIFA[tarifa] for tarifa in TARIFAS]))
    if generador.random() < PROPORCION_ANTIGUOS:
        alta = _fecha_entre(generador, inicio - _dias(ANTIGUEDAD_MAXIMA_DIAS), inicio - _dias(1))
    else:
        alta = _fecha_entre(generador, inicio, fin - _dias(30))
    cuota_base = CUOTA_BASE[tarifa]
    cambio = _simular_subida(generador, alta, inicio, fin)
    cuota = round(cuota_base * (1 + generador.uniform(SUBIDA_MINIMA, SUBIDA_MAXIMA)), 2) \
        if cambio else cuota_base
    nombre = f"{generador.choice(NOMBRES)} {generador.choice(APELLIDOS)}"
    return Socio(id_socio, nombre, alta, tarifa, cuota, cuota_base, cambio)


def _simular_subida(generador: np.random.Generator, alta: date, inicio: date,
                    fin: date) -> date | None:
    """Fecha de una subida de cuota dentro del periodo, o ``None`` si no hay subida."""
    desde, hasta = max(inicio, alta + _dias(60)), fin - _dias(15)
    if generador.random() >= PROB_SUBIDA or desde > hasta:
        return None
    return _fecha_entre(generador, desde, hasta)


def _probabilidad_baja(socio: Socio, mes: date) -> float:
    """Probabilidad de que el socio se dé de baja en el mes que empieza en ``mes``."""
    probabilidad = BAJA_MENSUAL[socio.tarifa]
    if socio.antiguedad_dias(mes) < DIAS_SOCIO_NUEVO:
        probabilidad += EXTRA_BAJA_NUEVO
    cambio = socio.fecha_cambio_cuota
    if cambio and -30 < (mes - cambio).days < DIAS_EFECTO_SUBIDA:
        probabilidad += EXTRA_BAJA_SUBIDA
    return probabilidad


def _simular_baja(generador: np.random.Generator, socio: Socio, meses: list[date],
                  fin: date) -> date | None:
    """Recorre los meses y decide si el socio se da de baja y qué día."""
    primera_posible = socio.fecha_alta + _dias(DIAS_MINIMOS_ANTES_DE_BAJA)
    for mes, siguiente in zip(meses, meses[1:] + [fin + _dias(1)]):
        ultimo_dia = siguiente - _dias(1)
        if ultimo_dia < primera_posible:
            continue
        if generador.random() < _probabilidad_baja(socio, mes):
            return _fecha_entre(generador, max(mes, primera_posible), ultimo_dia)
    return None


def _simular_visitas(generador: np.random.Generator, socio: Socio, baja: date | None,
                     inicio: date, fin: date) -> list[Visita]:
    """Genera las visitas del socio con su ritmo, su declive si se va o una pausa si no."""
    desde = max(socio.fecha_alta, inicio)
    hasta = min(baja - _dias(1), fin) if baja else fin
    numero_dias = (hasta - desde).days + 1
    if numero_dias <= 0:
        return []
    ritmo_diario = max(generador.gamma(4.0, VISITAS_MES_MEDIA / 4), VISITAS_MES_MINIMA) / 30
    if baja:
        factor = _factor_declive(generador, (baja - desde).days - np.arange(numero_dias))
    elif generador.random() < PROB_PAUSA:
        factor = _factor_pausa(generador, numero_dias)
    else:
        factor = np.ones(numero_dias)
    vienen = generador.random(numero_dias) < ritmo_diario * factor
    return [Visita(socio.id, desde + _dias(dia)) for dia in np.flatnonzero(vienen)]


def _factor_declive(generador: np.random.Generator, dias_hasta_baja: np.ndarray) -> np.ndarray:
    """Multiplicador del ritmo de visitas que cae hasta 0 en las semanas previas a la baja."""
    silencio = generador.integers(SILENCIO_MINIMO, SILENCIO_MAXIMO + 1)
    return np.clip((dias_hasta_baja - silencio) / (DIAS_DECLIVE - silencio), 0, 1)


def _factor_pausa(generador: np.random.Generator, numero_dias: int) -> np.ndarray:
    """Multiplicador del ritmo de visitas con un hueco de unas semanas sin venir."""
    duracion = int(generador.integers(PAUSA_MINIMA, PAUSA_MAXIMA + 1))
    comienzo = int(generador.integers(0, max(numero_dias - duracion, 1)))
    factor = np.ones(numero_dias)
    factor[comienzo:comienzo + duracion] = 0
    return factor


def simular_acciones(gimnasio: Gimnasio, radar: Radar,
                     meses: int = MESES_CON_ACCIONES) -> GestorRetencion:
    """Genera el histórico de acciones de retención de los últimos ``meses`` meses."""
    gestor = GestorRetencion()
    fin = gimnasio.fecha_referencia
    for corte in primeros_de_mes(fin - _dias(DIAS_HASTA_RETENCION), meses):
        for accion in gestor.proponer_en_riesgo(radar.evaluar_todos(gimnasio, corte), corte):
            _resolver(gestor, accion, gimnasio.socio(accion.id_socio))
    return gestor


def _resolver(gestor: GestorRetencion, accion: AccionRetencion, socio: Socio) -> None:
    """Lleva la acción a su estado final según lo que hizo el socio después."""
    propuesta = accion.fecha_propuesta
    baja = socio.fecha_baja
    perdido = baja is not None and baja <= propuesta + _dias(DIAS_SEGUIMIENTO)
    contacto = propuesta + _dias(DIAS_HASTA_CONTACTO)
    if not (perdido and baja <= contacto):
        gestor.avanzar(accion.id, "contactado", contacto)
    if perdido:
        gestor.avanzar(accion.id, "perdido", baja)
    else:
        gestor.avanzar(accion.id, "retenido", propuesta + _dias(DIAS_HASTA_RETENCION))
