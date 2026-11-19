"""Módulo 1 - Ejercicio 3: código con estilo.

La función de abajo funciona, pero ignora PEP 8. Reescríbela siguiendo las
indicaciones del enunciado sin cambiar su comportamiento.
"""

IVA_GENERAL = 21


def precio_final(precio, iva=IVA_GENERAL, descuento=0):
    """Calcula el precio final de un producto.

    Primero aplica el ``descuento`` (en %) sobre ``precio`` y después suma
    el ``iva`` (en %) al importe rebajado. Devuelve el resultado redondeado
    a dos decimales.

    >>> precio_final(100)
    121.0
    >>> precio_final(200, descuento=50)
    121.0
    """
    precio_rebajado = precio - precio * descuento / 100
    precio_con_iva = precio_rebajado + precio_rebajado * iva / 100
    return round(precio_con_iva, 2)
