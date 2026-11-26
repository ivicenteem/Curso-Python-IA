"""Radar de Bajas: aplicación de consola.

Es la única parte del proyecto que habla con el usuario: usa ``input`` y
``print``, captura los errores de la aplicación y decide cuándo se guarda.
Toda la lógica está en el paquete ``radar``.

Uso: python radar_app.py [carpeta_de_datos]
"""

import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from radar import almacen, analisis, graficos, informes
from radar.excepciones import DatosNoValidos, ErrorDeAlmacen, ErrorRadar
from radar.modelos import ESTADOS_ACCION, Gimnasio
from radar.radar import Evaluacion, Radar
from radar.retencion import GestorRetencion
from radar.simulador import SEMILLA, simular, simular_acciones
from radar.validacion import validar

CARPETA_PROYECTO = Path(__file__).parent
CARPETA_DATOS = CARPETA_PROYECTO / "datos"
RUTA_LOG = CARPETA_PROYECTO / "radar.log"
CARPETA_GRAFICOS = "graficos"
TOP_POR_DEFECTO = 10

MENU = """
RADAR DE BAJAS
1. Generar datos simulados
2. Cargar los datos guardados
3. Socios con más riesgo
4. Explicar el riesgo de un socio
5. Validar el modelo con el histórico
6. Proponer acciones a los socios en riesgo
7. Avanzar el estado de una acción
8. Ver las acciones abiertas
9. Informe para la dirección
10. Exportar gráficos
0. Guardar y salir
"""


@dataclass
class Sesion:
    """Estado de la aplicación mientras está abierta."""

    carpeta: Path
    gimnasio: Gimnasio
    retencion: GestorRetencion
    radar: Radar = field(default_factory=Radar.por_defecto)
    terminada: bool = False

    def evaluaciones(self) -> list[Evaluacion]:
        """Riesgo de todos los socios activos en la fecha de los datos."""
        return self.radar.evaluar_todos(self.gimnasio)

    def resumen(self) -> analisis.ResumenDireccion:
        """Tablas e indicadores para la dirección con los datos actuales."""
        return analisis.resumen_direccion(self.gimnasio, self.evaluaciones(),
                                          self.retencion.acciones)


def pedir_entero(mensaje: str, por_defecto: int | None = None) -> int:
    """Pide un entero. Vacío devuelve ``por_defecto`` si lo hay; si no es un número, error."""
    texto = input(mensaje).strip()
    if not texto and por_defecto is not None:
        return por_defecto
    try:
        return int(texto)
    except ValueError as error:
        raise DatosNoValidos(f"No es un número entero: '{texto}'") from error


def describir_datos(sesion: Sesion) -> str:
    """Una línea con lo que hay cargado."""
    if sesion.gimnasio.vacio:
        return "No hay datos: genera datos simulados (1) o carga los guardados (2)."
    gimnasio = sesion.gimnasio
    return (f"{len(gimnasio.socios)} socios, {len(gimnasio.visitas)} visitas y "
            f"{len(sesion.retencion)} acciones; "
            f"datos hasta {gimnasio.fecha_referencia.isoformat()}.")


def generar(sesion: Sesion) -> None:
    """Opción 1: sustituye los datos por otros simulados con la semilla elegida."""
    semilla = pedir_entero(f"Semilla [{SEMILLA}]: ", SEMILLA)
    sesion.gimnasio = simular(semilla=semilla)
    sesion.retencion = simular_acciones(sesion.gimnasio, sesion.radar)
    print(f"Generados {describir_datos(sesion)}")


def cargar(sesion: Sesion) -> None:
    """Opción 2: vuelve a leer los datos guardados en la carpeta."""
    sesion.gimnasio, acciones = almacen.cargar(sesion.carpeta)
    sesion.retencion = GestorRetencion(acciones)
    print(f"Cargados de {sesion.carpeta}: {describir_datos(sesion)}")


def ver_top(sesion: Sesion) -> None:
    """Opción 3: los socios con más riesgo."""
    cuantos = pedir_entero(f"¿Cuántos socios? [{TOP_POR_DEFECTO}]: ", TOP_POR_DEFECTO)
    print(informes.tabla_riesgo(sesion.evaluaciones(), cuantos))


def explicar(sesion: Sesion) -> None:
    """Opción 4: la ficha de riesgo de un socio."""
    id_socio = pedir_entero("Número de socio: ")
    evaluacion = sesion.radar.evaluar_socio(sesion.gimnasio, id_socio)
    print(informes.ficha_socio(evaluacion, sesion.retencion.abierta_de(id_socio)))


def validar_modelo(sesion: Sesion) -> None:
    """Opción 5: el backtesting del radar."""
    print(informes.informe_validacion(validar(sesion.gimnasio, sesion.radar)))


def proponer(sesion: Sesion) -> None:
    """Opción 6: registra una acción para cada socio en riesgo que no tenga una abierta."""
    nuevas = sesion.retencion.proponer_en_riesgo(sesion.evaluaciones(),
                                                 sesion.gimnasio.fecha_referencia)
    print(f"Acciones nuevas: {len(nuevas)}.")
    if nuevas:
        print(informes.listado_acciones(nuevas))


def avanzar(sesion: Sesion) -> None:
    """Opción 7: cambia el estado de una acción."""
    id_accion = pedir_entero("Número de acción: ")
    estado = input(f"Nuevo estado ({', '.join(ESTADOS_ACCION)}): ").strip()
    accion = sesion.retencion.avanzar(id_accion, estado, sesion.gimnasio.fecha_referencia)
    print(f"La acción {accion.id} queda en {accion.estado}.")


def ver_acciones(sesion: Sesion) -> None:
    """Opción 8: las acciones que siguen abiertas."""
    print(informes.listado_acciones(sesion.retencion.abiertas))


def informe(sesion: Sesion) -> None:
    """Opción 9: el informe para la dirección."""
    print(informes.informe_direccion(sesion.resumen()))


def exportar(sesion: Sesion) -> None:
    """Opción 10: guarda los gráficos en PNG."""
    for ruta in graficos.exportar(sesion.carpeta / CARPETA_GRAFICOS, sesion.resumen()):
        print(f"Guardado {ruta}")


def guardar_y_salir(sesion: Sesion) -> None:
    """Opción 0: guarda los datos y termina."""
    almacen.guardar(sesion.carpeta, sesion.gimnasio, sesion.retencion.acciones)
    sesion.terminada = True
    print(f"Datos guardados en {sesion.carpeta}. Hasta luego.")


OPCIONES: dict[str, Callable[[Sesion], None]] = {
    "1": generar,
    "2": cargar,
    "3": ver_top,
    "4": explicar,
    "5": validar_modelo,
    "6": proponer,
    "7": avanzar,
    "8": ver_acciones,
    "9": informe,
    "10": exportar,
    "0": guardar_y_salir,
}


def main(carpeta: Path = CARPETA_DATOS) -> int:
    """Ejecuta la aplicación. Devuelve 0 si termina guardando y 1 si no.

    Los errores de la aplicación se muestran como "Error: ..." y se vuelve al
    menú; el programa no termina por una entrada incorrecta.
    """
    try:
        gimnasio, acciones = almacen.cargar(carpeta)
    except ErrorDeAlmacen as error:
        print(f"Error: {error}")
        return 1
    sesion = Sesion(Path(carpeta), gimnasio, GestorRetencion(acciones))
    print(describir_datos(sesion))
    try:
        while not sesion.terminada:
            print(MENU)
            ejecutar(sesion, input("Opción: ").strip())
    except (EOFError, KeyboardInterrupt):
        print("\nSalida sin guardar.")
        return 1
    return 0


def ejecutar(sesion: Sesion, opcion: str) -> None:
    """Ejecuta una opción del menú y muestra cualquier error de la aplicación."""
    funcion = OPCIONES.get(opcion)
    if funcion is None:
        print("Opción no válida.")
        return
    try:
        funcion(sesion)
    except ErrorRadar as error:
        print(f"Error: {error}")


if __name__ == "__main__":
    logging.basicConfig(filename=RUTA_LOG, encoding="utf-8", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else CARPETA_DATOS))
