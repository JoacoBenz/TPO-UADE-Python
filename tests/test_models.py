"""Modelos: normalizacion de SID, credenciales y validacion de procesos."""

from __future__ import annotations

import pytest

from automation_launcher.core.models import (
    Credentials,
    Principal,
    Process,
    RunRecord,
    RunState,
    normalize_sid,
)


@pytest.mark.parametrize("entrada,esperado", [
    ("CORP\\Joaquin.Benz", "joaquin.benz"),
    ("CORP/ana.g", "ana.g"),
    ("ana.g@corp.com", "ana.g"),
    ("  Carlos.M  ", "carlos.m"),
    ("", ""),
    (None, ""),
])
def test_normalize_sid_acepta_las_formas_de_windows(entrada, esperado):
    assert normalize_sid(entrada) == esperado


@pytest.mark.parametrize("entrada", [
    "../../etc/passwd",   # el SID se usa para armar rutas
    "a\\b\\c",
    "..",
    "ana g",
    "ana;rm -rf /",
    "a" * 65,
])
def test_normalize_sid_rechaza_lo_peligroso(entrada):
    with pytest.raises(ValueError):
        normalize_sid(entrada)


def test_credentials_no_filtra_el_password_en_repr():
    """Un print(creds) o un traceback que incluya el objeto no puede
    exponer la contrasena."""
    creds = Credentials(sid="ana.g", password="Tr3as*ry!2026", domain="CORP")
    for texto in (repr(creds), str(creds), f"{creds}"):
        assert "Tr3as*ry!2026" not in texto
        assert "***" in texto


def test_credentials_qualified_user():
    assert Credentials("ana.g", "x", "CORP").qualified_user == "CORP\\ana.g"
    assert Credentials("ana.g", "x").qualified_user == "ana.g"


def test_principal_roles():
    p = Principal("ana.g", roles={"treasury": "lead", "clo": "member"})
    assert p.is_lead_of("treasury")
    assert not p.is_lead_of("clo")
    assert p.is_member_of("clo")
    assert not p.is_member_of("otro")
    assert p.hub_ids == ["clo", "treasury"]


def test_process_from_dict_valida():
    proc = Process.from_dict(
        {"id": "x", "name": "X", "notebook": "a.ipynb", "tags": ["t"]}, "treasury")
    assert proc.hub_id == "treasury"
    assert proc.timeout_seconds == 3600

    for malo in (
        {"name": "sin id", "notebook": "a.ipynb"},
        {"id": "x", "notebook": ""},
        {"id": "x", "notebook": "a.ipynb", "timeout_seconds": 0},
        {"id": "x", "notebook": "a.ipynb", "timeout_seconds": "diez"},
        {"id": "x", "notebook": "a.ipynb", "parameters": "no soy dict"},
    ):
        with pytest.raises(ValueError):
            Process.from_dict(malo, "treasury")


def test_process_matches_busca_en_todo():
    proc = Process.from_dict(
        {"id": "dtc_up", "name": "DTC Upload", "notebook": "clo.ipynb",
         "description": "sube a DTC", "tags": ["settlement"]}, "h")
    for consulta in ("dtc", "DTC", "settlement", "clo.ipynb", "sube", ""):
        assert proc.matches(consulta)
    assert not proc.matches("nada que ver")


def test_runrecord_ida_y_vuelta():
    record = RunRecord(run_id="r1", hub_id="h", process_id="p", process_name="P",
                       sid="ana.g", state=RunState.DONE, duration_seconds=1.234)
    assert RunRecord.from_dict(record.to_dict()).to_dict() == record.to_dict()
