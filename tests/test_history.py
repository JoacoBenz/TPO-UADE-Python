"""Historial de corridas y registro de auditoria."""

from __future__ import annotations

import json
import os
from datetime import datetime

from automation_launcher.core.contents import LocalContentsClient
from automation_launcher.core.history import MAX_LINES_PER_DAY, AuditLog, RunHistory
from automation_launcher.core.models import RunRecord, RunState
from automation_launcher.core.secrets import redactor


def record(run_id="r1", message=""):
    return RunRecord(run_id=run_id, hub_id="treasury", process_id="eod",
                     process_name="EOD", sid="ana.g", state=RunState.DONE,
                     started_at="2026-09-04T10:00:00", duration_seconds=1.5,
                     message=message)


def test_se_agrega_al_archivo_del_dia(tmp_path):
    client = LocalContentsClient(str(tmp_path))
    history = RunHistory(client, "_hubs")
    assert history.append("treasury", record("r1"))
    assert history.append("treasury", record("r2"))

    dia = datetime.now().strftime("%Y-%m-%d")
    texto = client.read_text(f"_hubs/treasury/runs/{dia}.jsonl")
    lineas = [json.loads(x) for x in texto.splitlines() if x.strip()]
    assert [x["run_id"] for x in lineas] == ["r1", "r2"]


def test_el_archivo_diario_tiene_tope(tmp_path):
    """Un bucle que dispare corridas no puede volver ilegible la carpeta."""
    client = LocalContentsClient(str(tmp_path))
    history = RunHistory(client, "_hubs")
    dia = datetime.now().strftime("%Y-%m-%d")
    ruta = f"_hubs/treasury/runs/{dia}.jsonl"
    client.write_text(ruta, "\n".join(['{"run_id":"viejo"}'] * (MAX_LINES_PER_DAY + 50)) + "\n")

    history.append("treasury", record("nuevo"))
    lineas = client.read_text(ruta).splitlines()
    assert len(lineas) == MAX_LINES_PER_DAY
    assert json.loads(lineas[-1])["run_id"] == "nuevo"


def test_un_share_caido_no_tumba_la_corrida(tmp_path):
    """La corrida ya paso: su resultado vale mas que la linea de historial."""
    class ClienteRoto:
        def read_text(self, path):
            raise OSError("share caido")

        def write_text(self, path, text):
            raise OSError("share caido")

    avisos = []
    history = RunHistory(ClienteRoto(), "_hubs", on_error=avisos.append)
    assert history.append("treasury", record()) is False
    assert avisos and "historial" in avisos[0]


def test_el_mensaje_se_redacta_antes_de_ir_a_disco(tmp_path):
    redactor.remember("Tr3as*ry!2026")
    client = LocalContentsClient(str(tmp_path))
    history = RunHistory(client, "_hubs")
    history.append("treasury", record(message="fallo con Tr3as*ry!2026"))

    dia = datetime.now().strftime("%Y-%m-%d")
    texto = client.read_text(f"_hubs/treasury/runs/{dia}.jsonl")
    assert "Tr3as*ry!2026" not in texto


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------

def test_el_audit_log_agrega_y_lee(tmp_path):
    log = AuditLog(str(tmp_path / "sub" / "audit.jsonl"))
    log({"event": "authz", "sid": "ana.g", "allowed": True, "hub_id": "treasury"})
    log({"event": "authz", "sid": "intruso", "allowed": False, "hub_id": "treasury"})

    entradas = log.tail(10)
    assert len(entradas) == 2
    assert entradas[0]["sid"] == "intruso"      # el mas nuevo primero
    assert all("at" in e for e in entradas)


def test_el_audit_log_redacta_los_motivos(tmp_path):
    """Un motivo de rechazo puede citar texto de entrada."""
    redactor.remember("Tr3as*ry!2026")
    ruta = str(tmp_path / "audit.jsonl")
    AuditLog(ruta)({"reason": "rechazado con Tr3as*ry!2026"})
    with open(ruta, encoding="utf-8") as handle:
        assert "Tr3as*ry!2026" not in handle.read()


def test_no_poder_auditar_no_frena_la_operacion(tmp_path):
    """Fallar cerrado dejaria la app inutilizable por un disco lleno."""
    log = AuditLog(os.path.join(str(tmp_path), "no", "existe", "\0malo"))
    log({"event": "authz"})     # no debe levantar
    assert log.tail() == []


def test_el_audit_log_se_puede_apagar(tmp_path):
    ruta = str(tmp_path / "audit.jsonl")
    log = AuditLog(ruta, enabled=False)
    log({"event": "authz"})
    assert not os.path.exists(ruta)
