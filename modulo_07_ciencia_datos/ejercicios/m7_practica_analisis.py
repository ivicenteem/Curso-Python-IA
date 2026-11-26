"""Módulo 7 - Práctica 7: análisis de las ventas del año.

Un pequeño proceso de análisis completo: cargar, limpiar, calcular indicadores,
generar gráficos y exportar los resultados.

La limpieza, las agregaciones y los gráficos reutilizan los ejercicios 3, 4 y 5.

Uso:

    python m7_practica_analisis.py
"""

from pathlib import Path

import pandas as pd

from m7_ej3_limpieza import cargar_en_bruto, limpiar
from m7_ej4_agrupacion import con_objetivos, importe_mensual, importe_por, resumen_por_vendedor
from m7_ej5_graficos import grafico_barras, grafico_lineas, guardar

DATOS = Path(__file__).resolve().parent.parent / "datos"
SALIDA = Path(__file__).resolve().parent / "salida_practica_7"
COLUMNAS_RANKING = ["vendedor", "ventas", "importe", "objetivo", "cumplimiento", "cumplido"]


def cargar(ruta: str | Path) -> pd.DataFrame:
    """Lee el CSV de ventas con todas las columnas como texto."""
    return cargar_en_bruto(ruta)


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve las ventas limpias y con las columnas calculadas.

    1. Texto sin espacios sobrantes y con la inicial en mayúscula.
    2. Sin filas duplicadas.
    3. ``fecha`` como fecha (formato "AAAA-MM-DD"), ``unidades`` y ``precio``
       como números. ``precio`` admite coma decimal.
    4. Las regiones ausentes pasan a ser "Sin región".
    5. Se descartan las filas sin fecha, vendedor, unidades o precio válidos, y
       las que tienen unidades o precio menores o iguales que cero.
    6. ``unidades`` queda como entero.
    7. Columnas nuevas: ``importe`` (unidades por precio) y ``mes`` ("AAAA-MM").
    8. Filas ordenadas por fecha, con el índice renumerado desde 0. A igual
       fecha se conserva el orden original.

    No modifica el DataFrame recibido.
    """
    limpias = limpiar(df)
    ordenadas = limpias.sort_values("fecha", kind="stable").reset_index(drop=True)
    return ordenadas.assign(importe=ordenadas["unidades"] * ordenadas["precio"],
                            mes=ordenadas["fecha"].dt.strftime("%Y-%m"))


def indicadores(df: pd.DataFrame) -> dict:
    """Devuelve los indicadores principales de unas ventas preparadas.

    Claves:

    - "ventas": número de ventas (int).
    - "importe_total": float con dos decimales.
    - "ticket_medio": importe medio por venta, float con dos decimales.
    - "mejor_vendedor": el de mayor importe total.
    - "mejor_mes": el mes "AAAA-MM" de mayor importe total.
    - "producto_mas_vendido": el de más unidades.
    """
    return {
        "ventas": len(df),
        "importe_total": round(float(df["importe"].sum()), 2),
        "ticket_medio": round(float(df["importe"].mean()), 2),
        "mejor_vendedor": str(importe_por(df, "vendedor").idxmax()),
        "mejor_mes": str(importe_por(df, "mes").idxmax()),
        "producto_mas_vendido": str(df.groupby("producto")["unidades"].sum().idxmax()),
    }


def ranking_vendedores(df: pd.DataFrame, objetivos: pd.DataFrame) -> pd.DataFrame:
    """Devuelve una fila por vendedor, de mayor a menor importe.

    Columnas, en este orden: vendedor, ventas, importe, objetivo, cumplimiento
    y cumplido. ``importe`` va redondeado a dos decimales, ``cumplimiento`` es
    el porcentaje del objetivo alcanzado con un decimal y ``cumplido`` indica
    si el importe llega al objetivo. El índice va de 0 en adelante.

    ``objetivos`` tiene las columnas vendedor y objetivo.
    """
    ranking = con_objetivos(resumen_por_vendedor(df), objetivos).reset_index()
    return ranking[COLUMNAS_RANKING].assign(importe=ranking["importe"].round(2))


def evolucion_mensual(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve una fila por mes, en orden, con las columnas mes, importe y variacion.

    ``importe`` va redondeado a dos decimales. ``variacion`` es el cambio en
    porcentaje respecto al mes anterior, con un decimal; en el primer mes es
    un valor ausente. El índice va de 0 en adelante.
    """
    mensual = importe_mensual(df)
    return pd.DataFrame({
        "mes": mensual.index,
        "importe": mensual.round(2).to_numpy(),
        "variacion": (100 * mensual.pct_change()).round(1).to_numpy(),
    })


def generar_graficos(df: pd.DataFrame, carpeta: str | Path) -> list[Path]:
    """Guarda dos gráficos en ``carpeta`` y devuelve sus rutas, en este orden.

    1. ``importe_por_vendedor.png``: barras, de mayor a menor importe.
    2. ``evolucion_mensual.png``: líneas con el importe de cada mes.

    Crea la carpeta si no existe. Cada gráfico lleva título y etiqueta en el
    eje Y. Las figuras se cierran después de guardarlas.
    """
    carpeta = Path(carpeta)
    por_vendedor = grafico_barras(importe_por(df, "vendedor"), "Importe por vendedor")
    mensual = grafico_lineas(importe_mensual(df), "Evolución mensual del importe")
    return [guardar(por_vendedor, carpeta / "importe_por_vendedor.png"),
            guardar(mensual, carpeta / "evolucion_mensual.png")]


def exportar(tabla: pd.DataFrame, ruta: str | Path) -> None:
    """Escribe la tabla en un CSV en UTF-8, sin la columna del índice.

    Crea la carpeta de destino si no existe.
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(ruta, index=False, encoding="utf-8")


def main() -> None:
    """Ejecuta el análisis completo con los datos del módulo."""
    ventas = preparar(cargar(DATOS / "ventas_2026.csv"))
    objetivos = pd.read_csv(DATOS / "objetivos.csv")

    print("INDICADORES")
    for nombre, valor in indicadores(ventas).items():
        print(f"  {nombre:<22}{valor}")
    print()
    print("RANKING DE VENDEDORES")
    ranking = ranking_vendedores(ventas, objetivos)
    print(ranking.to_string(index=False))
    print()
    print("EVOLUCIÓN MENSUAL")
    print(evolucion_mensual(ventas).to_string(index=False))

    exportar(ranking, SALIDA / "ranking_vendedores.csv")
    exportar(evolucion_mensual(ventas), SALIDA / "evolucion_mensual.csv")
    for ruta in generar_graficos(ventas, SALIDA):
        print(f"Gráfico guardado en {ruta}")


if __name__ == "__main__":
    main()
