"""Tests del menú de consola: se simula a un usuario tecleando con ``monkeypatch``."""

from pathlib import Path

import pytest

import radar_app
from radar import almacen


@pytest.fixture
def usar_app(monkeypatch, capsys, tmp_path):
    """Ejecuta la aplicación con las respuestas dadas y devuelve el código y la salida."""
    def ejecutar(*respuestas: str, carpeta: Path = tmp_path) -> tuple[int, str]:
        entradas = iter(respuestas)

        def teclear(mensaje: str = "") -> str:
            """Como ``input``: al acabarse las respuestas lanza ``EOFError`` (Ctrl+D)."""
            try:
                return next(entradas)
            except StopIteration as error:
                raise EOFError from error

        monkeypatch.setattr("builtins.input", teclear)
        codigo = radar_app.main(carpeta)
        return codigo, capsys.readouterr().out
    return ejecutar


@pytest.fixture
def carpeta_con_datos(tmp_path, gimnasio) -> Path:
    """Carpeta con los datos simulados ya guardados y sin acciones."""
    carpeta = tmp_path / "datos"
    almacen.guardar(carpeta, gimnasio, [])
    return carpeta


def test_arranca_sin_datos_y_sale_guardando(usar_app, tmp_path):
    codigo, salida = usar_app("0")
    assert codigo == 0
    assert "No hay datos" in salida
    assert "RADAR DE BAJAS" in salida
    assert (tmp_path / almacen.FICHERO_SOCIOS).exists()


def test_generar_ver_top_y_guardar(usar_app, tmp_path):
    codigo, salida = usar_app("1", "", "3", "5", "0")
    assert codigo == 0
    assert "Generados 300 socios" in salida
    assert salida.count("!  ") >= 1
    gimnasio, acciones = almacen.cargar(tmp_path)
    assert len(gimnasio.socios) == 300
    assert acciones


def test_los_datos_se_conservan_entre_ejecuciones(usar_app, tmp_path):
    usar_app("1", "7", "6", "0")
    _, salida = usar_app("0")
    assert "300 socios" in salida
    _, acciones = almacen.cargar(tmp_path)
    assert any(accion.estado == "propuesta" for accion in acciones)


@pytest.mark.parametrize("respuestas, mensaje", [
    (("99",), "Opción no válida."),
    (("4", "doce"), "Error: No es un número entero: 'doce'"),
    (("4", "999"), "Error: No existe el socio 999"),
    (("3", "0"), "Error: El número de socios debe ser al menos 1"),
    (("7", "1", "retenido"), "Error: No se puede pasar de propuesta a retenido"),
    (("7", "500", "perdido"), "Error: No existe la acción 500"),
    (("7", "1", "olvidado"), "Error: Estado no válido: olvidado"),
])
def test_entradas_incorrectas_no_terminan_el_programa(usar_app, carpeta_con_datos, respuestas,
                                                      mensaje):
    codigo, salida = usar_app("6", *respuestas, "0", carpeta=carpeta_con_datos)
    assert mensaje in salida
    assert codigo == 0


def test_explicar_un_socio_dado_de_baja(usar_app, carpeta_con_datos, gimnasio):
    baja = next(socio.id for socio in gimnasio.socios.values() if not socio.activo)
    _, salida = usar_app("4", str(baja), "0", carpeta=carpeta_con_datos)
    assert f"Error: El socio {baja} no estaba dado de alta" in salida


def test_operaciones_sin_datos_dan_error_controlado(usar_app):
    _, salida = usar_app("3", "", "5", "6", "9", "0")
    assert salida.count("Error: No hay datos") == 4


def test_explicar_proponer_y_avanzar(usar_app, carpeta_con_datos, gimnasio):
    socio = next(iter(gimnasio.socios))
    _, salida = usar_app("4", str(socio), "6", "8", "7", "1", "contactado", "0",
                         carpeta=carpeta_con_datos)
    assert f"Socio {socio}:" in salida
    assert "Puntos por señal" in salida
    assert "La acción 1 queda en contactado." in salida
    _, acciones = almacen.cargar(carpeta_con_datos)
    assert acciones[0].estado == "contactado"


def test_informe_validacion_y_graficos(usar_app, carpeta_con_datos):
    _, salida = usar_app("5", "9", "10", "0", carpeta=carpeta_con_datos)
    assert "VALIDACIÓN DEL RADAR CON EL HISTÓRICO" in salida
    assert "INFORME PARA LA DIRECCIÓN" in salida
    assert len(list((carpeta_con_datos / radar_app.CARPETA_GRAFICOS).glob("*.png"))) == 3


def test_cargar_vuelve_a_leer_lo_guardado(usar_app, carpeta_con_datos):
    _, salida = usar_app("1", "3", "2", "0", carpeta=carpeta_con_datos)
    assert "Cargados de" in salida
    assert salida.count("300 socios") == 3


def test_fichero_corrupto_no_arranca(usar_app, tmp_path):
    (tmp_path / almacen.FICHERO_SOCIOS).write_text("id,nombre\n1,Ada\n", encoding="utf-8")
    codigo, salida = usar_app(carpeta=tmp_path)
    assert codigo == 1
    assert salida.startswith("Error:")


def test_fin_de_entrada_sale_sin_traza(usar_app):
    codigo, salida = usar_app("3")
    assert codigo == 1
    assert "Salida sin guardar." in salida


def test_pedir_entero_con_valor_por_defecto(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda mensaje="": "  ")
    assert radar_app.pedir_entero("¿Cuántos? ", 10) == 10
