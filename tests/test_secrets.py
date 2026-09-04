"""El redactor: la garantia de que la contrasena no sale a ningun lado."""

from __future__ import annotations

import html
import urllib.parse

from automation_launcher.core.secrets import MASK, MIN_SECRET_LENGTH, Redactor


def test_tapa_el_valor_literal():
    r = Redactor()
    r.remember("Tr3as*ry!2026")
    assert "Tr3as*ry!2026" not in r.scrub("conectando con pass=Tr3as*ry!2026")
    assert MASK in r.scrub("pass=Tr3as*ry!2026")


def test_tapa_las_formas_codificadas():
    """Una contrasena llega a la salida despues de pasar por una URL o por el
    escapado de HTML tan seguido como en crudo."""
    secreto = "p@ss w/rd&x"
    r = Redactor()
    r.remember(secreto)
    for variante in (urllib.parse.quote(secreto, safe=""),
                     urllib.parse.quote_plus(secreto),
                     html.escape(secreto)):
        assert variante not in r.scrub("valor=" + variante)


def test_ignora_secretos_muy_cortos():
    """Un secreto de dos letras coincidiria en cualquier texto y volveria la
    consola ilegible: el riesgo de taparlo es peor que el de no hacerlo."""
    r = Redactor()
    r.remember("ab")
    assert r.scrub("ab abanico") == "ab abanico"
    assert len(r) == 0


def test_gana_la_coincidencia_mas_larga():
    r = Redactor()
    r.remember("clave", "clavelargasecreta")
    assert "clavelargasecreta" not in r.scrub("x clavelargasecreta y")


def test_scrub_acepta_cualquier_objeto():
    """Se lo llama sobre excepciones y tracebacks, no solo sobre strings."""
    r = Redactor()
    r.remember("secreto123")
    assert "secreto123" not in r.scrub(ValueError("fallo con secreto123"))
    assert r.scrub(None) == ""
    assert r.scrub(42) == "42"


def test_forget_borra_todo():
    r = Redactor()
    r.remember("secreto123")
    r.forget()
    assert r.scrub("secreto123") == "secreto123"
    assert len(r) == 0


def test_is_clean():
    r = Redactor()
    r.remember("secreto123")
    assert r.is_clean("texto normal")
    assert not r.is_clean("pass=secreto123")


def test_repr_no_filtra_secretos():
    r = Redactor()
    r.remember("secreto123")
    assert "secreto123" not in repr(r)


def test_min_length_es_coherente():
    r = Redactor()
    r.remember("a" * MIN_SECRET_LENGTH)
    assert len(r) >= 1
