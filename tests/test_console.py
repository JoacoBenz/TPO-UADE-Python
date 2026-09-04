"""Buffer de consola: clasificacion, tope de memoria y redaccion."""

from __future__ import annotations

import pytest

from automation_launcher.core.console import (
    ERROR,
    INFO,
    WARN,
    ConsoleBuffer,
    classify,
)
from automation_launcher.core.secrets import redactor


@pytest.mark.parametrize("texto,esperado", [
    ("cargando posiciones...", INFO),
    ("", INFO),
    ("  File 'x.py', line 3, in <module>", INFO),
    # El falso positivo que mas importa evitar: si el tablero pinta de rojo un
    # cierre exitoso, la gente deja de creerle a los colores.
    ("Procesados 1204 registros, 0 errors", INFO),
    ("Terminado sin errores", INFO),
    ("DeprecationWarning: usa la api nueva", WARN),
    ("/lib/x.py:12: FutureWarning: cambia en pandas 3", WARN),
    ("WARNING: el archivo llego tarde", WARN),
    ("ValueError: no se encontro el archivo", ERROR),
    ("Traceback (most recent call last)", ERROR),
    ("ConnectionError: timeout", ERROR),
    ("failed to upload batch 3", ERROR),
    ("CRITICAL: se corto la conexion", ERROR),
    ("2 errors encontrados", ERROR),
])
def test_classify(texto, esperado):
    assert classify(texto) == esperado


def test_el_buffer_no_crece_sin_limite():
    """Sin tope, un notebook charlatan se come la memoria de Voila."""
    buffer = ConsoleBuffer(max_lines=100)
    for i in range(250):
        buffer.append(f"linea {i}")
    stats = buffer.stats
    assert stats["buffered"] == 100
    assert stats["lines"] == 250      # el contador es de la sesion, no del buffer
    assert stats["dropped"] == 150
    assert buffer.lines()[0].text == "linea 150"


def test_los_contadores_siguen_los_niveles():
    buffer = ConsoleBuffer()
    buffer.append("todo bien")
    buffer.append("DeprecationWarning: ojo")
    buffer.append("ValueError: mal")
    stats = buffer.stats
    assert (stats["warnings"], stats["errors"]) == (1, 1)


def test_se_redacta_al_entrar_no_al_salir():
    """El secreto no queda ni siquiera guardado en memoria dentro del buffer."""
    redactor.remember("Tr3as*ry!2026")
    buffer = ConsoleBuffer()
    buffer.append("pass=Tr3as*ry!2026")
    assert "Tr3as*ry!2026" not in buffer.lines()[0].text
    assert "Tr3as*ry!2026" not in buffer.text()


def test_filtro_por_proceso():
    buffer = ConsoleBuffer()
    buffer.append("a", source="p1")
    buffer.append("b", source="p2")
    assert [x.text for x in buffer.lines(source="p1")] == ["a"]
    assert buffer.sources() == ["p1", "p2"]


def test_clear_reinicia_contadores():
    buffer = ConsoleBuffer()
    buffer.append("ValueError: x")
    buffer.clear()
    assert buffer.stats == {"lines": 0, "warnings": 0, "errors": 0,
                            "dropped": 0, "buffered": 0}


def test_un_observador_roto_no_frena_la_corrida():
    """La consola la escribe el hilo de una corrida: un listener que explota
    no puede matar el proceso que estaba registrando."""
    buffer = ConsoleBuffer()
    buffer.subscribe(lambda: 1 / 0)
    buffer.append("sigue andando")
    assert len(buffer) == 1


def test_append_block_parte_por_lineas():
    buffer = ConsoleBuffer()
    buffer.append_block("una\ndos\ntres")
    assert len(buffer) == 3
