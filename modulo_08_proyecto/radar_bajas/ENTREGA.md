# Entrega del proyecto final: Radar de Bajas

- **Nombre y apellidos:** Iñaki Vicente Marchante
- **Fecha:** 26/11/2026

## Estado

- Tests superados: 248 de 248 (`pytest modulo_08_proyecto/radar_bajas`)
- Hitos terminados (1 a 7): todos
  1. Excepciones y modelos
  2. Señales y radar
  3. Simulador y almacén
  4. Validación y retención
  5. Análisis, gráficos e informes
  6. Menú
  7. README, datos de ejemplo y revisión final
- ¿La aplicación arranca y guarda los datos al salir? Sí. Arranca con los datos de `datos/` (o sin datos si la carpeta está vacía) y la opción 0 guarda socios, visitas y acciones en CSV. Las acciones propuestas o avanzadas en una ejecución aparecen en la siguiente.

## Decisiones de diseño

El menú es un diccionario que asocia cada opción con una función pequeña que recibe la `Sesion`, el estado de la aplicación. Solo hay un `try`/`except ErrorRadar`, alrededor de la ejecución de la opción elegida. Ninguna opción contiene reglas de negocio: por ejemplo, el socio dado de baja lo rechaza `Radar.evaluar_socio` y la transición no permitida la rechaza `AccionRetencion.avanzar`.

En el análisis, la operación de pandas más útil ha sido `pd.crosstab` con `reindex(fill_value=0)`. Da la matriz de confusión de la validación y la tabla de eficacia de las acciones, siempre con todas las filas y columnas aunque alguna combinación no tenga casos. También `groupby(pd.Grouper(freq="MS"))` para contar las bajas por mes.

El resto de las decisiones (índice explicable, polimorfismo en las señales, validación sin fugas del futuro) están en el README.

## Ampliaciones

- **Registro de operaciones:** cada acción propuesta o avanzada y cada guardado se anotan en `radar.log`.
- **Análisis en el menú y gráficos:** la opción 9 muestra el informe para la dirección y la opción 10 guarda tres gráficos PNG en `datos/graficos/`.
- **Validación del modelo:** la opción 5 hace el backtesting con seis fechas de corte y muestra la matriz de confusión, la precisión, el recall y un barrido de umbrales.
- **Simulador reproducible:** la opción 1 genera un gimnasio completo con la semilla que se indique.
- **Panel web propio (FastAPI, Jinja2, CSS y Chart.js):** resumen para la dirección, socios con buscador y ficha, validación con número de cortes y horizonte a elegir, acciones de retención y gestión de datos (cargar, simular, subir CSV, altas, visitas, bajas, descargar y guardar). El umbral y la fecha de análisis se aplican a todas las secciones. Se instala con `pip install -r modulo_08_proyecto/radar_bajas/requirements.txt` y se lanza desde la raíz con `python modulo_08_proyecto/radar_bajas/web`.

Para probarlas: `cd modulo_08_proyecto/radar_bajas`, `python radar_app.py` y las opciones 5, 9 y 10. Después de usar las opciones 6 y 7, el registro está en `radar.log`.

## Qué mejoraría con más tiempo

- Ajustar los pesos de las señales con una regresión logística y comparar su precisión con la del índice actual usando la misma validación.
- Medir el efecto real de las acciones con un grupo de control: en los datos simulados, el resultado de una acción depende de si el socio se fue, no de la acción.
- Una señal de "días sin venir" relativa al ritmo de cada socio: 10 días sin venir no significan lo mismo para quien viene a diario que para quien viene una vez por semana.

## Dificultades encontradas

- **Que los datos simulados fueran realistas.** Al principio el radar casi no detectaba a nadie en la fecha actual, porque el simulador solo generaba bajas hasta el último día. Lo arreglé simulando también las bajas de los dos meses siguientes, sin guardarlas, para que ya se notara que esos socios iban menos.
- **Que las métricas fueran fiables.** Validando con una sola fecha salían muy pocas bajas y los resultados cambiaban mucho según la semilla. Con seis fechas de corte (una por mes) los resultados se estabilizaron.
- **No hacer trampa en la validación.** Al evaluar una fecha pasada solo se puede usar lo que se sabía ese día: hay que ignorar las visitas y las subidas de cuota posteriores.
- **Hacer las tablas de texto sin recorrer el DataFrame fila a fila.** Alineé cada columna entera con `.str.rjust` y `.str.ljust` y luego las uní sumándolas.
