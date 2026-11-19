"""Tests de la ampliación opcional de la práctica 1."""

import pytest

import m1_practica_conversor as conversor


def test_metros_a_pies():
    assert conversor.METROS_POR_PIE == 0.3048
    assert conversor.metros_a_pies(0.3048) == pytest.approx(1)
    assert conversor.metros_a_pies(100) == pytest.approx(328.0839895)


def test_main_convierte_metros_a_pies(monkeypatch, capsys):
    respuestas = iter(["7", "10"])
    monkeypatch.setattr("builtins.input", lambda *args: next(respuestas))
    conversor.main()
    assert "10.00 m = 32.81 ft" in capsys.readouterr().out


def test_main_repetido_hasta_elegir_cero(monkeypatch, capsys):
    respuestas = iter(["1", "100", "9", "3", "10", "0"])
    monkeypatch.setattr("builtins.input", lambda *args: next(respuestas))
    conversor.main_repetido()
    salida = capsys.readouterr().out
    assert "100.00 °C = 212.00 °F" in salida
    assert "Opción no válida" in salida
    assert "10.00 km = 6.21 mi" in salida
    assert "¡Hasta luego!" in salida
    assert salida.count("Conversor de unidades") == 4


def test_main_repetido_sale_directamente_con_cero(monkeypatch, capsys):
    respuestas = iter(["0"])
    monkeypatch.setattr("builtins.input", lambda *args: next(respuestas))
    conversor.main_repetido()
    assert "¡Hasta luego!" in capsys.readouterr().out
