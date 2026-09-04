"""Autenticacion del usuario contra la red.

En este entorno no hay un proveedor de identidad al que preguntarle quien es
el usuario: Jupyter corre adentro de una jaula y lo unico que se puede probar
es "esta persona sabe su password de red". Eso se verifica pidiendole al
sistema operativo que se conecte al share administrativo ``IPC$`` de un host
del dominio: si Windows acepta la conexion, las credenciales son buenas.

Es una forma indirecta de autenticar, pero es solida: la valida el controlador
de dominio, no esta app.

El password ademas se necesita despues, no solo para entrar: los notebooks lo
piden por ``getpass()`` y el launcher los responde por el usuario. Por eso se
retiene en memoria durante la sesion, y por eso ``secrets.Redactor`` existe.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

from .models import Credentials, normalize_sid
from .secrets import redactor

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import Any, Optional  # noqa: F401  (los usan los comentarios `# type:`)

#: Largo minimo aceptado en modo demo. En modo SMB no se valida largo: eso lo
#: decide la politica de contrasenas del dominio, no nosotros.
MIN_DEMO_PASSWORD = 4


class AuthResult:
    """Resultado de un intento de login."""

    __slots__ = ("ok", "sid", "display_name", "message", "credentials")

    def __init__(self, ok, sid="", display_name="", message="", credentials=None):
        # type: (bool, str, str, str, Optional[Credentials]) -> None
        self.ok = ok
        self.sid = sid
        self.display_name = display_name or sid
        self.message = message
        self.credentials = credentials

    def __bool__(self):
        # type: () -> bool
        return self.ok

    def __repr__(self):
        # type: () -> str
        return "AuthResult({}, sid={!r})".format("ok" if self.ok else "fail", self.sid)


def detect_sid():
    # type: () -> str
    """Deduce el usuario actual del entorno del kernel.

    El login no le pide el usuario a la persona -- ya esta logueada en la
    maquina y volver a tipearlo solo agrega errores. Se prueban las variables
    que usan Windows, Linux y JupyterHub, en ese orden.
    """
    for name in ("JUPYTERHUB_USER", "USERNAME", "USER", "LOGNAME"):
        value = os.environ.get(name)
        if not value:
            continue
        try:
            sid = normalize_sid(value)
        except ValueError:
            continue
        if sid:
            return sid
    try:
        import getpass
        return normalize_sid(getpass.getuser())
    except Exception:
        return ""


class MockAuth:
    """Backend de demo: acepta cualquier password razonable.

    Es lo que permite correr y mostrar la app completa fuera de la red de la
    empresa. No valida nada contra ningun lado y no pretende hacerlo.
    """

    name = "mock"

    def __init__(self, config=None):
        # type: (Any) -> None
        self.config = config

    def authenticate(self, sid, password):
        # type: (str, str) -> AuthResult
        try:
            sid = normalize_sid(sid)
        except ValueError:
            return AuthResult(False, message="El usuario tiene caracteres invalidos.")
        if not sid:
            return AuthResult(False, message="No se pudo determinar el usuario.")
        if not password or len(password) < MIN_DEMO_PASSWORD:
            return AuthResult(
                False, sid=sid,
                message=f"Modo demo: la contrasena necesita al menos {MIN_DEMO_PASSWORD} caracteres.",
            )
        credentials = Credentials(sid=sid, password=password)
        redactor.remember(password)
        return AuthResult(True, sid=sid, credentials=credentials, message="Modo demo")

    def describe(self):
        # type: () -> str
        return "mock (sin validacion real)"


class SmbAuth:
    """Backend de produccion: valida contra ``IPC$`` en un host SMB del dominio.

    Detalles que no son cosmeticos:

    * **El password va por stdin, no por argv.** ``net use \\\\host\\IPC$ *``
      lo pide de forma interactiva y se le escribe por la entrada estandar.
      Pasarlo como argumento lo dejaria visible en el Administrador de tareas
      para cualquiera que este en la misma maquina.

    * **La conexion se borra siempre.** El ``finally`` corre ``net use
      /delete`` para no dejar el share montado despues de validar. Si quedara
      montado, la siguiente persona que use esa maquina heredaria el acceso.
    """

    name = "smb"

    def __init__(self, config, runner=None):
        # type: (Any, Any) -> None
        self.config = config
        self.host = str(config.get("AUTH_HOST") or "").strip().strip("\\")
        self.domain = str(config.get("AUTH_DOMAIN") or "").strip()
        self.timeout = int(config.get("AUTH_TIMEOUT") or 20)
        #: Inyectable para poder testear sin un Windows con dominio detras.
        self._runner = runner or self._run_net_use

    @property
    def share(self):
        # type: () -> str
        return rf"\\{self.host}\IPC$"

    def authenticate(self, sid, password):
        # type: (str, str) -> AuthResult
        try:
            sid = normalize_sid(sid)
        except ValueError:
            return AuthResult(False, message="El usuario tiene caracteres invalidos.")
        if not sid:
            return AuthResult(False, message="No se pudo determinar el usuario.")
        if not password:
            return AuthResult(False, sid=sid, message="Ingresa tu contrasena de red.")
        if not self.host:
            return AuthResult(
                False, sid=sid,
                message="No hay AUTH_HOST configurado: no hay contra que autenticar.",
            )

        credentials = Credentials(sid=sid, password=password, domain=self.domain)
        # Se registra el secreto ANTES de correr nada: si el subproceso falla y
        # el mensaje de error arrastra la contrasena, ya esta cubierto.
        redactor.remember(password)

        try:
            code, output = self._runner(self.share, credentials.qualified_user, password)
        except FileNotFoundError:
            return AuthResult(
                False, sid=sid,
                message="No se encontro 'net': este backend necesita Windows.",
            )
        except subprocess.TimeoutExpired:
            return AuthResult(
                False, sid=sid,
                message=f"Timeout conectando a {self.share}.",
            )
        except Exception as exc:
            return AuthResult(
                False, sid=sid,
                message=f"Error autenticando: {redactor.scrub(exc)}",
            )

        if code == 0:
            return AuthResult(True, sid=sid, credentials=credentials,
                              message=f"Verificado contra {self.share}")
        return AuthResult(False, sid=sid, message=self._explain(code, output))

    def _run_net_use(self, share, user, password):
        # type: (str, str, str) -> tuple
        """Corre ``net use`` y garantiza que la conexion no quede montada."""
        try:
            process = subprocess.Popen(
                ["net", "use", share, "*", "/user:" + user],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            stdout, _ = process.communicate(
                input=(password + "\n").encode("utf-8", "replace"), timeout=self.timeout
            )
            return process.returncode, stdout.decode("utf-8", "replace")
        finally:
            # Siempre, incluso si lo de arriba levanto: no dejar el share montado.
            try:
                subprocess.run(
                    ["net", "use", share, "/delete", "/y"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=self.timeout,
                )
            except Exception:
                pass

    @staticmethod
    def _explain(code, output):
        # type: (int, str) -> str
        """Traduce el error de ``net use`` a algo que el usuario entienda.

        Los codigos de Windows por si solos generan un ticket de soporte por
        cada intento fallido; decir "la contrasena no coincide" no.
        """
        text = redactor.scrub(output or "").lower()
        if "1326" in text or "logon failure" in text or "user name or password" in text:
            return "Usuario o contrasena incorrectos."
        if "1909" in text or "locked out" in text:
            return "La cuenta esta bloqueada. Contactate con soporte."
        if "1907" in text or "password must be changed" in text:
            return "Tu contrasena expiro: cambiala en Windows y volve a intentar."
        if "53" in text and "network path" in text:
            return "No se encuentra el host en la red."
        if "1219" in text or "multiple connections" in text:
            return ("Ya hay una conexion abierta a ese servidor con otro usuario. "
                    "Cerra las sesiones con 'net use * /delete' y reintenta.")
        cleaned = " ".join((output or "").split())[:200]
        return f"Fallo la autenticacion (codigo {code}). {redactor.scrub(cleaned)}".strip()

    def describe(self):
        # type: () -> str
        return "SMB IPC$ en {}".format(self.host or "<sin host>")


def build_auth(config):
    # type: (Any) -> Any
    """Elige el backend segun ``AUTH_BACKEND``."""
    if config.get("AUTH_BACKEND") == "mock":
        return MockAuth(config)
    return SmbAuth(config)
