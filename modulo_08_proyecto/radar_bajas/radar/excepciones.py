"""Excepciones propias de Radar de Bajas.

Jerarquía:

    ErrorRadar (Exception)          base de todos los errores de la aplicación
    ├── DatosNoValidos              un dato no cumple las reglas del dominio
    ├── SinDatos                    no hay datos cargados para la operación pedida
    ├── SocioNoEncontrado           no existe un socio con ese identificador
    ├── AccionNoEncontrada          no existe una acción con ese identificador
    ├── TransicionNoValida          el cambio de estado de una acción no está permitido
    └── ErrorDeAlmacen              un fichero no se puede leer o escribir

Que todas hereden de ``ErrorRadar`` permite al menú capturarlas con un solo
``except``.
"""


class ErrorRadar(Exception):
    """Base de todos los errores de la aplicación."""


class DatosNoValidos(ErrorRadar):
    """Un dato no cumple las reglas del dominio."""


class SinDatos(ErrorRadar):
    """No hay datos con los que hacer la operación pedida."""


class SocioNoEncontrado(ErrorRadar):
    """No existe un socio con el identificador indicado."""

    def __init__(self, id_socio: int) -> None:
        super().__init__(f"No existe el socio {id_socio}")
        self.id_socio = id_socio


class AccionNoEncontrada(ErrorRadar):
    """No existe una acción de retención con el identificador indicado."""

    def __init__(self, id_accion: int) -> None:
        super().__init__(f"No existe la acción {id_accion}")
        self.id_accion = id_accion


class TransicionNoValida(ErrorRadar):
    """El flujo de estados de una acción no permite el cambio pedido."""

    def __init__(self, actual: str, nuevo: str) -> None:
        super().__init__(f"No se puede pasar de {actual} a {nuevo}")
        self.actual = actual
        self.nuevo = nuevo


class ErrorDeAlmacen(ErrorRadar):
    """Un fichero de datos no se puede leer o escribir."""
