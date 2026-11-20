"""Módulo 2 - Práctica 2, parte B: calculadora de nómina.

Hecho con ayuda de IA.
"""

SEGURIDAD_SOCIAL = 6.35  # % de cotización del trabajador
PAGAS = 12

# (límite superior del tramo, tipo en %). El último tramo no tiene límite.
TRAMOS_IRPF = (
    (12450, 19),
    (20200, 24),
    (35200, 30),
    (60000, 37),
    (float("inf"), 45),
)

ANCHO_ETIQUETA = 20
ANCHO_IMPORTE = 12


def calcular_irpf(bruto_anual: float) -> float:
    """Calcula la retención anual de IRPF con una escala progresiva.

    Cada tramo se aplica solo a la parte del salario que cae dentro de él.

    >>> calcular_irpf(30000)
    7165.5
    """
    irpf = 0
    limite_inferior = 0
    for limite_superior, tipo in TRAMOS_IRPF:
        if bruto_anual <= limite_inferior:
            break
        gravado = min(bruto_anual, limite_superior) - limite_inferior
        irpf += gravado * tipo / 100
        limite_inferior = limite_superior
    return round(irpf, 2)


def calcular_seguridad_social(bruto_anual: float) -> float:
    """Calcula la cotización anual del trabajador a la Seguridad Social.

    >>> calcular_seguridad_social(30000)
    1905.0
    """
    return round(bruto_anual * SEGURIDAD_SOCIAL / 100, 2)


def calcular_neto_anual(bruto_anual: float) -> float:
    """Devuelve el salario neto anual: bruto menos IRPF y Seguridad Social.

    >>> calcular_neto_anual(30000)
    20929.5
    """
    irpf = calcular_irpf(bruto_anual)
    seguridad_social = calcular_seguridad_social(bruto_anual)
    return round(bruto_anual - irpf - seguridad_social, 2)


def tipo_efectivo(bruto_anual: float) -> float:
    """Devuelve el porcentaje de IRPF sobre el bruto, con dos decimales.

    Si el bruto es cero o negativo devuelve 0.0.

    >>> tipo_efectivo(30000)
    23.89
    """
    if bruto_anual <= 0:
        return 0.0
    return round(calcular_irpf(bruto_anual) / bruto_anual * 100, 2)


def formatear_nomina(bruto_anual: float) -> str:
    """Devuelve el resumen de la nómina en cinco líneas alineadas.

    >>> print(formatear_nomina(30000))
    Bruto anual            30,000.00
    IRPF (23.89 %)         -7,165.50
    Seguridad Social       -1,905.00
    Neto anual             20,929.50
    Neto mensual            1,744.12
    """
    neto_anual = calcular_neto_anual(bruto_anual)
    etiqueta_irpf = f"IRPF ({tipo_efectivo(bruto_anual):.2f} %)"
    filas = [
        ("Bruto anual", bruto_anual),
        (etiqueta_irpf, -calcular_irpf(bruto_anual)),
        ("Seguridad Social", -calcular_seguridad_social(bruto_anual)),
        ("Neto anual", neto_anual),
        ("Neto mensual", neto_anual / PAGAS),
    ]
    lineas = []
    for etiqueta, importe in filas:
        lineas.append(f"{etiqueta:<{ANCHO_ETIQUETA}}{importe:>{ANCHO_IMPORTE},.2f}")
    return "\n".join(lineas)


def main() -> None:
    """Pide el salario bruto anual y muestra la nómina."""
    texto = input("Salario bruto anual: ").strip()
    # Sin try/except (se ve en el módulo 6): solo cifras y como mucho un punto
    if not texto.replace(".", "", 1).isdecimal() or float(texto) <= 0:
        print("Importe no válido")
        return
    print(formatear_nomina(float(texto)))


if __name__ == "__main__":
    main()
