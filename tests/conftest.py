"""Fixtures compartidas.

La idea que guia estos tests: **el nucleo se prueba sin Jupyter, sin SMB y sin
red**. Cada test arma un share falso en un directorio temporal y habla con el
mismo ``LocalContentsClient`` que usa el modo demo, asi que se ejercita el
codigo real y no un doble.
"""

from __future__ import annotations

import json
import os

import pytest

from automation_launcher.core.config import LauncherConfig
from automation_launcher.core.contents import LocalContentsClient
from automation_launcher.core.repository import HubRepository, build_principal
from automation_launcher.core.secrets import redactor


@pytest.fixture(autouse=True)
def clean_redactor():
    """Cada test arranca sin secretos recordados.

    El redactor es un singleton compartido; sin esto, la contrasena de un test
    enmascararia texto en el siguiente y los fallos serian incomprensibles.
    """
    redactor.forget()
    yield
    redactor.forget()


def write_json(path, data):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


@pytest.fixture
def share(tmp_path):
    """Un share con tres hubs y roles cruzados.

      treasury       ana.g es jefa;  joaquin.benz y carlos.m son miembros
      clo_ops        carlos.m es jefe;  joaquin.benz es miembro
      hg_settlement  diego.f es jefe;  nadie mas

    El cruce importa: carlos.m es jefe en un hub y miembro en otro, que es el
    caso donde un chequeo de permisos mal escrito (por usuario en vez de por
    usuario y hub) se rompe.
    """
    root = str(tmp_path / "share")
    hubs = os.path.join(root, "_hubs")

    write_json(os.path.join(hubs, "registry.json"), {"hubs": [
        {"id": "treasury", "name": "Treasury Ops", "path": "treasury"},
        {"id": "clo_ops", "name": "CLO Operations", "path": "clo_ops"},
        {"id": "hg_settlement", "name": "HG Settlement", "path": "hg_settlement"},
    ]})

    memberships = {
        "treasury": {"leads": ["ana.g"], "members": ["joaquin.benz", "carlos.m"]},
        "clo_ops": {"leads": ["carlos.m"], "members": ["joaquin.benz"]},
        "hg_settlement": {"leads": ["diego.f"], "members": []},
    }
    for hub_id, data in memberships.items():
        write_json(os.path.join(hubs, hub_id, "members.json"), dict(data, revision=1))

    processes = {
        "treasury": [
            {"id": "eod", "name": "EOD Positions", "notebook": "/nb/ok.ipynb"},
            {"id": "dtc", "name": "DTC Upload", "notebook": "/nb/ok.ipynb",
             "requires_confirmation": True, "tags": ["dtc"]},
        ],
        "clo_ops": [{"id": "clo_upload", "name": "CLO Upload", "notebook": "/nb/ok.ipynb"}],
        "hg_settlement": [{"id": "hg_is", "name": "HG IS", "notebook": "/nb/ok.ipynb"}],
    }
    for hub_id, items in processes.items():
        write_json(os.path.join(hubs, hub_id, "processes.json"), {"processes": items})

    return root


@pytest.fixture
def config(share):
    return LauncherConfig({"CONTENTS_DIR": "", "HUBS_DIR": "_hubs",
                           "LOCAL_SHARE_ROOT": share, "AUDIT_ENABLED": False})


@pytest.fixture
def client(share):
    return LocalContentsClient(share)


@pytest.fixture
def make_repo(client, config):
    """Devuelve una funcion que arma el repositorio para un SID dado."""
    def factory(sid, audit=None):
        principal = build_principal(sid, client, config, audit=audit)
        return HubRepository(principal, client, config, audit=audit)
    return factory
