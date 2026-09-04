"""La capa de acceso al share y su defensa contra rutas maliciosas."""

from __future__ import annotations

import os

import pytest

from automation_launcher.core.contents import (
    AccessDenied,
    ContentsError,
    LocalContentsClient,
    NotFound,
    join,
)


@pytest.mark.parametrize("partes,esperado", [
    (("a", "b", "c"), "a/b/c"),
    (("a/", "/b/"), "a/b"),
    (("a", "", "b"), "a/b"),
    ((r"a\b", "c"), "a/b/c"),
    (("", ""), ""),
    (("a", ".", "b"), "a/b"),
])
def test_join_normaliza(partes, esperado):
    assert join(*partes) == esperado


@pytest.mark.parametrize("ruta", ["..", "a/../../b", "../etc", "a/..", r"a\..\..\b"])
def test_join_rechaza_traversal(ruta):
    """Los ids de hub y de proceso vienen de JSON en el share: se los trata
    como entrada no confiable aunque hoy los escriban personas de confianza."""
    with pytest.raises(ValueError):
        join(ruta)


def test_local_client_no_sale_de_la_raiz(tmp_path):
    (tmp_path / "adentro").mkdir()
    (tmp_path / "afuera.txt").write_text("secreto")
    client = LocalContentsClient(str(tmp_path / "adentro"))
    with pytest.raises((ValueError, ContentsError, NotFound)):
        client.read_text("../afuera.txt")


def test_local_client_lee_y_escribe(tmp_path):
    client = LocalContentsClient(str(tmp_path))
    client.write_json("sub/dato.json", {"b": 2, "a": 1})
    assert client.read_json("sub/dato.json") == {"a": 1, "b": 2}
    assert client.exists("sub/dato.json")
    assert not client.exists("no/existe.json")


def test_local_client_write_text_para_jsonl(tmp_path):
    client = LocalContentsClient(str(tmp_path))
    client.write_text("runs/2026-09-04.jsonl", '{"a":1}\n{"b":2}\n')
    assert client.read_text("runs/2026-09-04.jsonl").count("\n") == 2


def test_local_client_lista_directorios(tmp_path):
    client = LocalContentsClient(str(tmp_path))
    (tmp_path / "sub").mkdir()
    (tmp_path / "n.ipynb").write_text("{}")
    (tmp_path / ".oculto").write_text("x")
    tipos = {e.name: e.type for e in client.list_dir("")}
    assert tipos == {"sub": "directory", "n.ipynb": "notebook"}


def test_json_invalido_da_un_error_claro(tmp_path):
    client = LocalContentsClient(str(tmp_path))
    (tmp_path / "roto.json").write_text("{no json")
    with pytest.raises(ContentsError) as error:
        client.read_json("roto.json")
    assert "roto.json" in str(error.value)


def test_faltante_es_notfound(tmp_path):
    client = LocalContentsClient(str(tmp_path))
    with pytest.raises(NotFound):
        client.read_text("nada.json")


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignora los permisos del filesystem")
def test_sin_permiso_es_accessdenied(tmp_path):
    """Es como se manifiesta una ACL: 403 en la Contents API, EACCES en local.

    Distinguirlo de NotFound importa: el repositorio trata AccessDenied como
    'este hub no es tuyo' en lugar de como una falla del sistema.
    """
    protegido = tmp_path / "privado.json"
    protegido.write_text("{}")
    protegido.chmod(0o000)
    client = LocalContentsClient(str(tmp_path))
    with pytest.raises(AccessDenied):
        client.read_text("privado.json")
    protegido.chmod(0o644)


def test_escritura_atomica_no_deja_temporales(tmp_path):
    client = LocalContentsClient(str(tmp_path))
    client.write_json("x.json", {"a": 1})
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]
