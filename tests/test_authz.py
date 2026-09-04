"""La bateria de autorizacion.

Es el archivo mas importante del proyecto. Todo lo demas, si se rompe, causa
una molestia; si esto se rompe, un equipo ve los datos de otro.

Los tests estan escritos como afirmaciones sobre el comportamiento observable
("un miembro no puede administrar miembros"), no sobre la implementacion, para
que sigan valiendo si manana el modelo de roles se reescribe por dentro.
"""

from __future__ import annotations

import pytest

from automation_launcher.core import authz
from automation_launcher.core.authz import PermissionDenied, Policy
from automation_launcher.core.contents import NotFound
from automation_launcher.core.models import ROLE_LEAD, ROLE_MEMBER, Principal, Process

policy = Policy()

LEAD = Principal("ana.g", roles={"treasury": ROLE_LEAD})
MEMBER = Principal("joaquin.benz", roles={"treasury": ROLE_MEMBER})
CROSS = Principal("carlos.m", roles={"treasury": ROLE_MEMBER, "clo_ops": ROLE_LEAD})
OUTSIDER = Principal("intruso", roles={})


# ---------------------------------------------------------------------------
# La politica en si
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action", authz.ALL_ACTIONS)
def test_sin_sesion_todo_denegado(action):
    """Sin principal no hay accion posible, ni siquiera la mas inocua."""
    decision = policy.check(None, action, "treasury")
    assert not decision
    assert "sesion" in decision.reason


@pytest.mark.parametrize("action", authz.ALL_ACTIONS)
def test_ajeno_al_hub_todo_denegado(action):
    """Quien no pertenece al hub no puede hacer nada sobre el hub."""
    assert not policy.check(OUTSIDER, action, "treasury")
    assert not policy.check(MEMBER, action, "clo_ops")


@pytest.mark.parametrize("action", [authz.VIEW_HUB, authz.RUN_PROCESS, authz.VIEW_HISTORY])
def test_miembro_puede_lo_operativo(action):
    assert policy.check(MEMBER, action, "treasury")


@pytest.mark.parametrize("action", authz.LEAD_ONLY_ACTIONS)
def test_solo_el_jefe_administra(action):
    """Métricas y miembros son del jefe. Un miembro no los ve."""
    assert policy.check(LEAD, action, "treasury")
    assert not policy.check(MEMBER, action, "treasury")


def test_el_rol_es_por_hub_no_por_persona():
    """Ser jefe en un hub no da jefatura en otro.

    Este es el error clasico de un modelo multi-tenant: guardar "es jefe" en
    la persona en vez de en el par (persona, hub).
    """
    assert policy.check(CROSS, authz.MANAGE_MEMBERS, "clo_ops")
    assert not policy.check(CROSS, authz.MANAGE_MEMBERS, "treasury")
    assert policy.check(CROSS, authz.RUN_PROCESS, "treasury")


def test_accion_desconocida_se_deniega():
    """Ante una accion que no existe se cierra, no se abre."""
    assert not policy.check(LEAD, "borrar_todo", "treasury")


def test_sin_hub_se_deniega():
    assert not policy.check(LEAD, authz.VIEW_HUB, None)
    assert not policy.check(LEAD, authz.VIEW_HUB, "")


def test_proceso_de_otro_hub_se_deniega():
    """Un proceso ajeno no se puede correr aunque el hub propio este bien.

    Cubre el click forjado: mandar el id de un proceso de otro equipo junto
    con el hub al que uno si pertenece.
    """
    ajeno = Process(id="clo_upload", name="X", notebook="a.ipynb", hub_id="clo_ops")
    decision = policy.check(MEMBER, authz.RUN_PROCESS, "treasury", ajeno)
    assert not decision
    assert "clo_ops" in decision.reason


def test_visible_hub_ids_no_filtra_de_mas_ni_de_menos():
    assert policy.visible_hub_ids(CROSS) == ["clo_ops", "treasury"]
    assert policy.visible_hub_ids(OUTSIDER) == []
    assert policy.visible_hub_ids(None) == []


def test_la_decision_explica_el_motivo():
    """Un rechazo sin motivo genera un ticket; con motivo, no."""
    decision = policy.check(MEMBER, authz.MANAGE_MEMBERS, "treasury")
    assert "jefe" in decision.reason
    assert decision.to_dict()["allowed"] is False


def test_raise_if_denied():
    with pytest.raises(PermissionDenied):
        policy.check(OUTSIDER, authz.VIEW_HUB, "treasury").raise_if_denied()
    assert policy.check(LEAD, authz.VIEW_HUB, "treasury").raise_if_denied()


# ---------------------------------------------------------------------------
# El repositorio: la politica aplicada sobre datos reales
# ---------------------------------------------------------------------------

def test_los_roles_salen_del_share(make_repo):
    """Nadie le pasa los roles al principal: se leen de members.json."""
    assert make_repo("ana.g").principal.roles == {"treasury": ROLE_LEAD}
    assert make_repo("carlos.m").principal.roles == {
        "treasury": ROLE_MEMBER, "clo_ops": ROLE_LEAD}
    assert make_repo("intruso").principal.roles == {}


def test_list_hubs_solo_devuelve_los_propios(make_repo):
    assert [h.id for h in make_repo("ana.g").list_hubs()] == ["treasury"]
    assert [h.id for h in make_repo("carlos.m").list_hubs()] == ["clo_ops", "treasury"]
    assert make_repo("intruso").list_hubs() == []


def test_no_se_puede_pedir_un_hub_ajeno(make_repo):
    """La propiedad central: el repositorio ni siquiera lo busca."""
    repo = make_repo("ana.g")
    with pytest.raises(PermissionDenied):
        repo.get_hub("clo_ops")
    with pytest.raises(PermissionDenied):
        repo.list_processes("clo_ops")
    with pytest.raises(PermissionDenied):
        repo.read_runs("clo_ops")


def test_un_hub_inexistente_no_se_confunde_con_uno_prohibido(make_repo):
    """Distinguirlos importa: son problemas distintos con soluciones distintas."""
    repo = make_repo("ana.g")
    repo.principal.roles["fantasma"] = ROLE_MEMBER   # pertenece a algo que no existe
    with pytest.raises(NotFound):
        repo.get_hub("fantasma")


def test_solo_el_jefe_guarda_miembros(make_repo):
    with pytest.raises(PermissionDenied):
        make_repo("joaquin.benz").save_membership("treasury", ["joaquin.benz"], [])
    resultado = make_repo("ana.g").save_membership("treasury", ["ana.g"], ["nuevo.user"])
    assert "nuevo.user" in resultado.members


def test_un_jefe_de_otro_hub_no_puede_tocar_este(make_repo):
    """carlos.m es jefe de clo_ops; en treasury es solo miembro."""
    repo = make_repo("carlos.m")
    assert repo.save_membership("clo_ops", ["carlos.m"], ["joaquin.benz"])
    with pytest.raises(PermissionDenied):
        repo.save_membership("treasury", ["carlos.m"], [])


def test_el_hub_no_puede_quedarse_sin_jefe(make_repo):
    """Sin jefe, el hub no lo puede administrar nadie nunca mas."""
    repo = make_repo("ana.g")
    with pytest.raises(ValueError) as error:
        repo.save_membership("treasury", [], ["joaquin.benz"])
    assert "sin jefe" in str(error.value)


def test_edicion_concurrente_no_pisa_en_silencio(make_repo):
    """Dos jefes editando a la vez: el segundo recibe un error, no un borrado.

    Sin esto, el segundo guardado revierte el primero y alguien desaparece
    del equipo sin que quede rastro de por que.
    """
    from automation_launcher.core.repository import ConflictError

    primero = make_repo("ana.g")
    segundo = make_repo("ana.g")
    revision_vieja = primero.get_membership("treasury").revision

    segundo.save_membership("treasury", ["ana.g"], ["otra.persona"])
    with pytest.raises(ConflictError):
        primero.save_membership(
            "treasury", ["ana.g"], ["joaquin.benz"], expected_revision=revision_vieja
        )


def test_el_jefe_tambien_es_miembro(make_repo):
    """Figurar en `leads` alcanza para tener todo lo de un miembro."""
    repo = make_repo("ana.g")
    assert repo.list_processes("treasury")
    assert repo.policy.can_run(repo.principal, "treasury")


def test_authorize_run_revalida_el_hub_del_proceso(make_repo):
    repo = make_repo("joaquin.benz")
    propio = repo.get_process("treasury", "eod")
    assert repo.authorize_run("treasury", propio)

    ajeno = repo.get_process("clo_ops", "clo_upload")
    with pytest.raises(PermissionDenied):
        repo.authorize_run("treasury", ajeno)


def test_toda_decision_queda_auditada(make_repo):
    """Se registran los permisos y los rechazos: un log solo de rechazos no
    responde 'quien corrio esto'."""
    eventos = []
    repo = make_repo("joaquin.benz", audit=eventos.append)
    repo.list_processes("treasury")
    try:
        repo.list_processes("hg_settlement")
    except PermissionDenied:
        pass

    decisiones = [e for e in eventos if e.get("event") == "authz"]
    assert any(e["allowed"] for e in decisiones)
    assert any(not e["allowed"] for e in decisiones)
    rechazo = next(e for e in decisiones if not e["allowed"])
    assert rechazo["sid"] == "joaquin.benz"
    assert rechazo["hub_id"] == "hg_settlement"
