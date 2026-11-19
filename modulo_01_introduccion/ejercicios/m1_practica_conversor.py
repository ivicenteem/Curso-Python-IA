"""Módulo 1 - Práctica 1: conversor de unidades.

Lee el enunciado en PRACTICA_1.md.
"""

KM_POR_MILLA = 1.609344
KG_POR_LIBRA = 0.45359237


def celsius_a_fahrenheit(grados):
    """Convierte grados Celsius a Fahrenheit."""
    return grados * 9 / 5 + 32


def fahrenheit_a_celsius(grados):
    """Convierte grados Fahrenheit a Celsius."""
    return (grados - 32) * 5 / 9


def km_a_millas(km):
    """Convierte kilómetros a millas."""
    return km / KM_POR_MILLA


def millas_a_km(millas):
    """Convierte millas a kilómetros."""
    return millas * KM_POR_MILLA


def kg_a_libras(kg):
    """Convierte kilogramos a libras."""
    return kg / KG_POR_LIBRA


def libras_a_kg(libras):
    """Convierte libras a kilogramos."""
    return libras * KG_POR_LIBRA


def formatear(valor, unidad_origen, resultado, unidad_destino):
    """Devuelve el texto de la conversión con dos decimales.

    >>> formatear(100, "°C", 212.0, "°F")
    '100.00 °C = 212.00 °F'
    """
    return f"{valor:.2f} {unidad_origen} = {resultado:.2f} {unidad_destino}"


# Cada opción del menú: (texto, función, unidad de origen, unidad de destino)
OPCIONES = {
    "1": ("Celsius a Fahrenheit", celsius_a_fahrenheit, "°C", "°F"),
    "2": ("Fahrenheit a Celsius", fahrenheit_a_celsius, "°F", "°C"),
    "3": ("Kilómetros a millas", km_a_millas, "km", "mi"),
    "4": ("Millas a kilómetros", millas_a_km, "mi", "km"),
    "5": ("Kilogramos a libras", kg_a_libras, "kg", "lb"),
    "6": ("Libras a kilogramos", libras_a_kg, "lb", "kg"),
}


def main():
    """Muestra el menú, pide los datos e imprime el resultado."""
    print("Conversor de unidades")
    for clave, (texto, _, _, _) in OPCIONES.items():
        print(f"{clave}. {texto}")
    opcion = input("Elige una opción (1-6): ").strip()

    if opcion not in OPCIONES:
        print("Opción no válida")
        return

    _, convertir, origen, destino = OPCIONES[opcion]
    valor = float(input("Valor a convertir: "))
    print(formatear(valor, origen, convertir(valor), destino))


if __name__ == "__main__":
    main()
