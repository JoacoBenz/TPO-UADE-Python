"""Lectura del share: registro de hubs, procesos e historial."""

from __future__ import annotations

import json
import os

from automation_launcher.core.repository import _clean_sids


def test_un_proceso_invalido_no_tumba_la_pantalla(share, make_repo):
    """Que una automatizacion mal cargada deje al equipo sin poder correr las
    otras nueve seria el peor resultado posible."""
    ruta = os.path.join(share, "_hubs", "treasury", "processes.json")
    with open(ruta, encoding="utf-8") as handle:
        data = json.load(handle)
    data["processes"].append({"name": "sin id ni notebook"})
    with open(ruta, "w", encoding="utf-8") as handle:
        json.dump(data, handle)

    eventos = []
    repo = make_repo("ana.g", audit=eventos.append)
    procesos = repo.list_processes("treasury")
    assert [p.id for p in procesos] == ["eod", "dtc"]
    assert any(e.get("event") == "process_invalid" for e in eventos)


def test_un_hub_sin_processes_json_devuelve_lista_vacia(share, make_repo):
    os.remove(os.path.join(share, "_hubs", "treasury", "processes.json"))
    assert make_repo("ana.g").list_processes("treasury") == []


def test_los_hubs_se_descubren_por_carpeta_sin_registry(share, make_repo):
    """El registry es una comodidad, no un requisito: se puede dar de alta un
    hub creando la carpeta."""
    os.remove(os.path.join(share, "_hubs", "registry.json"))
    assert [h.id for h in make_repo("carlos.m").list_hubs()] == ["clo_ops", "treasury"]


def test_un_members_json_roto_no_otorga_pertenencia(share, make_repo):
    """No se inventa una pertenencia que no se pudo verificar."""
    with open(os.path.join(share, "_hubs", "treasury", "members.json"), "w") as handle:
        handle.write("{ esto no es json")
    assert make_repo("ana.g").principal.roles == {}


def test_read_runs_saltea_lineas_corruptas(share, make_repo):
    ruta = os.path.join(share, "_hubs", "treasury", "runs")
    os.makedirs(ruta)
    with open(os.path.join(ruta, "2026-09-04.jsonl"), "w", encoding="utf-8") as handle:
        handle.write('{"run_id":"ok","state":"done"}\n')
        handle.write("linea corrupta que no es json\n")
        handle.write('{"run_id":"ok2","state":"error"}\n')
    registros = make_repo("ana.g").read_runs("treasury")
    assert [r["run_id"] for r in registros] == ["ok", "ok2"]


def test_read_runs_solo_lee_los_ultimos_dias(share, make_repo):
    """Con un anio de corridas, leer todo para dibujar un tab significaria
    bajar decenas de megas por SMB en cada visita."""
    ruta = os.path.join(share, "_hubs", "treasury", "runs")
    os.makedirs(ruta)
    for dia in range(1, 21):
        nombre = f"2026-09-{dia:02d}.jsonl"
        with open(os.path.join(ruta, nombre), "w", encoding="utf-8") as handle:
            handle.write(f'{{"run_id":"d{dia}","state":"done"}}\n')
    assert len(make_repo("ana.g").read_runs("treasury", days=5)) == 5


def test_clean_sids_normaliza_y_descarta_lo_invalido():
    """Estos archivos los editan personas: van a venir duplicados y mayusculas."""
    assert _clean_sids(["CORP\\Ana.G", "ana.g", "  Carlos.M ", "../malo", ""]) == [
        "ana.g", "carlos.m"]
    assert _clean_sids(None) == []


def test_el_jefe_no_se_duplica_en_miembros(make_repo):
    """El rol de jefe ya incluye lo de miembro."""
    resultado = make_repo("ana.g").save_membership(
        "treasury", ["ana.g"], ["ana.g", "joaquin.benz"])
    assert resultado.leads == ["ana.g"]
    assert resultado.members == ["joaquin.benz"]


def test_guardar_sube_la_revision_y_deja_rastro(make_repo):
    repo = make_repo("ana.g")
    antes = repo.get_membership("treasury")
    despues = repo.save_membership("treasury", ["ana.g"], ["nuevo"])
    assert despues.revision == antes.revision + 1
    assert despues.updated_by == "ana.g"
    assert despues.updated_at
