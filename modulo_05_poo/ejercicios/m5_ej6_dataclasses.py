"""Módulo 5 - Ejercicio 6: dataclasses y composición.

En este ejercicio las clases se escriben enteras: no hay plantilla. El
enunciado está en ejercicios/README.md.
"""

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Punto:
    """Un punto inmutable en el plano."""

    x: float = 0.0
    y: float = 0.0

    def distancia(self, otro: "Punto") -> float:
        """Devuelve la distancia hasta otro punto, con dos decimales.

        >>> Punto(0, 0).distancia(Punto(3, 4))
        5.0
        """
        return round(math.hypot(self.x - otro.x, self.y - otro.y), 2)


@dataclass
class LineaPedido:
    """Una línea de un pedido: producto, unidades y precio unitario."""

    producto: str
    unidades: int
    precio: float

    def __post_init__(self):
        if self.unidades <= 0:
            raise ValueError("Las unidades tienen que ser positivas")

    @property
    def importe(self) -> float:
        """Unidades por precio, con dos decimales. Solo lectura."""
        return round(self.unidades * self.precio, 2)


@dataclass
class Pedido:
    """Un pedido de un cliente, compuesto por varias líneas."""

    numero: int
    cliente: str
    lineas: list[LineaPedido] = field(default_factory=list)

    def anadir(self, producto: str, unidades: int, precio: float) -> LineaPedido:
        """Crea una línea, la añade al pedido y la devuelve."""
        linea = LineaPedido(producto, unidades, precio)
        self.lineas.append(linea)
        return linea

    @property
    def total(self) -> float:
        """Suma de los importes de las líneas, con dos decimales. Solo lectura."""
        return round(sum(linea.importe for linea in self.lineas), 2)

    def __len__(self) -> int:
        return len(self.lineas)

    def productos(self) -> list[str]:
        """Nombres de los productos, sin repetir y en orden alfabético."""
        return sorted({linea.producto for linea in self.lineas})
