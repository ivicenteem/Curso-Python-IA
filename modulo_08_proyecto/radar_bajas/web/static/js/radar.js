/* Radar de Bajas: gráficos con Chart.js, tablas ordenables y ajustes de la barra lateral. */
"use strict";

/** Valor de una variable CSS del tema actual (claro u oscuro). */
function colorDe(variable) {
  return getComputedStyle(document.documentElement).getPropertyValue(variable).trim();
}

/** Número con coma decimal, al estilo español. */
function formatear(valor, sufijo) {
  if (valor === null || valor === undefined) return "sin datos";
  return valor.toLocaleString("es-ES", { maximumFractionDigits: 1 }) + (sufijo || "");
}

/** Configuración de Chart.js para un gráfico de barras o de líneas. */
function configuracion(tipo, datos) {
  const colores = [colorDe("--serie-1"), colorDe("--serie-2")];
  const horizontal = tipo === "barras-horizontales";
  const lineas = tipo === "lineas";
  const ejeValor = {
    beginAtZero: true,
    grid: { color: colorDe("--rejilla") },
    border: { display: false },
    ticks: { color: colorDe("--texto-2"), callback: (v) => formatear(v, datos.sufijo) },
  };
  const ejeCategoria = {
    grid: { display: false },
    border: { color: colorDe("--borde") },
    ticks: { color: colorDe("--texto-2") },
  };
  return {
    type: lineas ? "line" : "bar",
    data: {
      labels: datos.etiquetas,
      datasets: datos.series.map((serie, i) => ({
        label: serie.nombre,
        data: serie.valores,
        backgroundColor: colores[i],
        borderColor: colores[i],
        borderWidth: lineas ? 2 : 0,
        borderRadius: lineas ? 0 : 4,
        maxBarThickness: 28,
        pointRadius: lineas ? 4 : 0,
        pointHoverRadius: 6,
        tension: 0.25,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: horizontal ? "y" : "x",
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          display: datos.series.length > 1,
          labels: { color: colorDe("--texto-2"), usePointStyle: true },
        },
        tooltip: {
          callbacks: { label: (c) => ` ${c.dataset.label}: ${formatear(c.raw, datos.sufijo)}` },
        },
      },
      scales: horizontal ? { x: ejeValor, y: ejeCategoria } : { x: ejeCategoria, y: ejeValor },
    },
  };
}

/** Dibuja todos los gráficos de la página a partir de sus datos JSON. */
function dibujarGraficos() {
  if (typeof Chart === "undefined") return;
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  document.querySelectorAll("canvas[data-grafico]").forEach((lienzo) => {
    const datos = JSON.parse(document.getElementById(lienzo.dataset.grafico).textContent);
    new Chart(lienzo, configuracion(lienzo.dataset.tipo, datos));
  });
}

/** Ordena una tabla por la columna pulsada; un segundo clic invierte el orden. */
function ordenarTabla(tabla, cabecera) {
  const columna = [...cabecera.parentNode.children].indexOf(cabecera);
  const ascendente = cabecera.getAttribute("aria-sort") !== "ascending";
  const numerica = cabecera.dataset.tipo === "numero";
  const valor = (fila) => {
    const celda = fila.children[columna];
    const texto = celda.dataset.valor ?? celda.textContent.trim();
    return numerica ? parseFloat(texto) : texto.toLocaleLowerCase("es");
  };
  const cuerpo = tabla.tBodies[0];
  const filas = [...cuerpo.rows].sort((a, b) => {
    const [x, y] = [valor(a), valor(b)];
    const orden = numerica ? x - y : x.localeCompare(y, "es");
    return ascendente ? orden : -orden;
  });
  tabla.querySelectorAll("th").forEach((th) => th.removeAttribute("aria-sort"));
  cabecera.setAttribute("aria-sort", ascendente ? "ascending" : "descending");
  cuerpo.append(...filas);
}

/** Activa las tablas ordenables y las filas que llevan a una ficha. */
function prepararTablas() {
  document.querySelectorAll("table[data-ordenable]").forEach((tabla) => {
    tabla.querySelectorAll("thead th").forEach((th) => {
      th.addEventListener("click", () => ordenarTabla(tabla, th));
    });
  });
  document.querySelectorAll("tr[data-href]").forEach((fila) => {
    fila.addEventListener("click", (evento) => {
      if (!evento.target.closest("a")) window.location = fila.dataset.href;
    });
  });
}

/** Muestra el umbral mientras se mueve y aplica los ajustes al soltarlo o cambiar la fecha. */
function prepararAjustes() {
  document.querySelectorAll("form[data-autoenvio]").forEach((formulario) => {
    formulario.querySelectorAll("input[data-muestra]").forEach((entrada) => {
      const salida = formulario.querySelector(`output[data-salida="${entrada.dataset.muestra}"]`);
      entrada.addEventListener("input", () => { salida.value = entrada.value; });
    });
    formulario.querySelectorAll("input").forEach((entrada) => {
      entrada.addEventListener("change", () => {
        if (formulario.reportValidity()) formulario.submit();
      });
    });
  });
}

/** Pide confirmación antes de enviar los formularios que la necesitan. */
function prepararConfirmaciones() {
  document.querySelectorAll("form[data-confirmar]").forEach((formulario) => {
    formulario.addEventListener("submit", (evento) => {
      if (!window.confirm(formulario.dataset.confirmar)) evento.preventDefault();
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  dibujarGraficos();
  prepararTablas();
  prepararAjustes();
  prepararConfirmaciones();
});
