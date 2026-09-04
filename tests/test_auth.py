"""Autenticacion: modo demo y el backend SMB con subprocess simulado."""

from __future__ import annotations

import subprocess

from automation_launcher.core.auth import MockAuth, SmbAuth
from automation_launcher.core.config import LauncherConfig
from automation_launcher.core.secrets import redactor


def smb_config():
    return LauncherConfig({"AUTH_BACKEND": "smb", "AUTH_HOST": "corp-fs01",
                           "AUTH_DOMAIN": "CORP"})


def test_mock_acepta_una_contrasena_razonable():
    resultado = MockAuth().authenticate("CORP\\Ana.G", "demo1234")
    assert resultado.ok
    assert resultado.sid == "ana.g"


def test_mock_rechaza_lo_muy_corto():
    assert not MockAuth().authenticate("ana.g", "ab").ok
    assert not MockAuth().authenticate("ana.g", "").ok


def test_mock_rechaza_un_sid_invalido():
    assert not MockAuth().authenticate("../../etc/passwd", "demo1234").ok


def test_smb_arma_bien_la_llamada():
    """El share administrativo y el usuario con dominio, como espera net use."""
    llamadas = []

    def fake(share, user, password):
        llamadas.append((share, user, password))
        return (0, "")

    resultado = SmbAuth(smb_config(), runner=fake).authenticate("joaquin.benz", "clave")
    assert resultado.ok
    assert llamadas[0][0] == r"\\corp-fs01\IPC$"
    assert llamadas[0][1] == "CORP\\joaquin.benz"


def test_smb_traduce_los_codigos_de_windows():
    """Un codigo de Windows crudo genera un ticket de soporte por cada intento
    fallido; un mensaje en castellano, no."""
    casos = [
        ("System error 1326: The user name or password is incorrect.", "incorrect"),
        ("System error 1909 has occurred. The account is locked out.", "bloquead"),
        ("System error 1907: password must be changed", "expir"),
        ("System error 1219: Multiple connections to a server", "conexion"),
    ]
    for salida, fragmento in casos:
        auth = SmbAuth(smb_config(), runner=lambda s, u, p, o=salida: (2, o))
        resultado = auth.authenticate("ana.g", "mala")
        assert not resultado.ok
        assert fragmento.lower() in resultado.message.lower(), resultado.message


def test_smb_sin_host_no_intenta_nada():
    config = LauncherConfig({"AUTH_BACKEND": "smb", "AUTH_HOST": ""})
    resultado = SmbAuth(config, runner=lambda *a: (0, "")).authenticate("ana.g", "x")
    assert not resultado.ok
    assert "AUTH_HOST" in resultado.message


def test_smb_maneja_la_falta_de_net():
    def fake(*_args):
        raise FileNotFoundError("net")
    resultado = SmbAuth(smb_config(), runner=fake).authenticate("ana.g", "x")
    assert not resultado.ok
    assert "Windows" in resultado.message


def test_smb_maneja_el_timeout():
    def fake(*_args):
        raise subprocess.TimeoutExpired("net", 20)
    resultado = SmbAuth(smb_config(), runner=fake).authenticate("ana.g", "x")
    assert not resultado.ok
    assert "Timeout" in resultado.message


def test_el_password_se_recuerda_antes_de_correr_nada():
    """Si el subproceso falla y su mensaje arrastra la contrasena, ya esta
    cubierta: por eso se registra antes y no despues."""
    def fake(_share, _user, password):
        return (2, f"error raro: la clave {password} no sirve")

    resultado = SmbAuth(smb_config(), runner=fake).authenticate("ana.g", "Tr3as*ry!2026")
    assert not resultado.ok
    assert "Tr3as*ry!2026" not in resultado.message
    assert redactor.is_clean(resultado.message)
