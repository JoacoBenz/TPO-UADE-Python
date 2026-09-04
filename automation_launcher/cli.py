"""Interfaz de linea de comandos.

Existe casi gratis: como el nucleo no depende de ipywidgets, las mismas
funciones que usa la interfaz se pueden manejar desde una terminal. Sirve
para tres cosas concretas:

  * ``doctor``  -- diagnostico cuando algo no anda en la maquina del trabajo.
                   Es lo primero que conviene correr.
  * ``whoami``  -- ver los permisos efectivos de un usuario sin abrir el
                   navegador. Responde "¿por que fulano no ve el hub?".
  * ``run``     -- ejecutar una automatizacion sin interfaz, que es lo que
                   hace falta para agendarla en un scheduler.

Uso::

    python -m automation_launcher doctor
    python -m automation_launcher whoami --sid ana.g
    python -m automation_launcher list --sid ana.g
    python -m automation_launcher run eod_positions --hub treasury --sid ana.g
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import time
from typing import TYPE_CHECKING

from .core import contents
from .core.auth import build_auth, detect_sid
from .core.config import load_config
from .core.console import ConsoleBuffer
from .core.engine import RunManager
from .core.history import AuditLog, RunHistory
from .core.models import Credentials, RunState
from .core.repository import HubRepository, build_principal
from .core.secrets import redactor

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import Any, List, Optional  # noqa: F401

DEFAULT_CONFIG = "launcher_config.py"


def _find_config(path=None):
    # type: (Optional[str]) -> Optional[str]
    for candidate in (path, DEFAULT_CONFIG, os.path.join("demo", "launcher_config.demo.py")):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _build(args):
    # type: (Any) -> tuple
    """Arma config, cliente y principal. Es el preambulo de casi todo comando."""
    config = load_config(_find_config(args.config))
    client = contents.build_client(config)
    sid = args.sid or detect_sid()
    audit = AuditLog(config.get("AUDIT_LOG_PATH"), config.get("AUDIT_ENABLED"))
    principal = build_principal(sid, client, config, audit=audit)
    repo = HubRepository(principal, client, config, audit=audit)
    return config, client, principal, repo


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def cmd_doctor(args):
    # type: (Any) -> int
    """Diagnostico del entorno: que anda y que no, con el motivo."""
    path = _find_config(args.config)
    config = load_config(path)
    problems = 0

    print("Automation Launcher — diagnóstico")
    print("=" * 62)

    print("\n[configuración]")
    print("  archivo : {}".format(path or "ninguno (se usan los defaults)"))
    print(f"  estado  : {config.status_line()}")
    for problem in config.problems:
        print(f"    ! {problem}")
        problems += 1

    print("\n[acceso al share]")
    client = contents.build_client(config)
    print(f"  backend : {client.describe()}")
    hubs_root = contents.join(config.get("CONTENTS_DIR"), config.get("HUBS_DIR"))
    print("  raíz    : {}".format(hubs_root or "(raíz del share)"))
    try:
        entries = client.list_dir(hubs_root)
        directories = [e for e in entries if e.is_dir]
        print(f"  lectura : OK — {len(directories)} carpeta(s) de hub")
    except Exception as exc:
        print(f"  lectura : FALLA — {exc}")
        print("            revisá CONTENTS_DIR/HUBS_DIR y que jupyterfs tenga montado el share")
        problems += 1
        directories = []

    print("\n[hubs]")
    for entry in directories:
        members_path = contents.join(hubs_root, entry.name, "members.json")
        try:
            data = client.read_json(members_path)
            leads = data.get("leads") or []
            members = data.get("members") or []
            note = "" if leads else "   ! sin jefe: nadie puede administrarlo"
            print(f"  {entry.name:<18} {len(leads)} jefe(s), {len(members)} miembro(s){note}")
            if not leads:
                problems += 1
        except contents.AccessDenied:
            print(f"  {entry.name:<18} sin acceso (403) — la ACL está haciendo su trabajo")
        except Exception as exc:
            print(f"  {entry.name:<18} ! members.json ilegible: {exc}")
            problems += 1

    print("\n[aislamiento entre equipos]")
    # Si todos los hubs se leen con la misma identidad, la separacion la
    # sostiene solo la app. Conviene decirlo, no descubrirlo en una auditoria.
    readable = 0
    for entry in directories:
        try:
            client.read_json(contents.join(hubs_root, entry.name, "members.json"))
            readable += 1
        except Exception:
            pass
    if len(directories) > 1 and readable == len(directories):
        print(f"  Este proceso puede leer los {readable} hubs.")
        print("  La separación la garantiza la aplicación, NO el sistema de archivos.")
        print("  Para que sea una barrera real hacen falta ACLs por carpeta:")
        print("  ver docs/permissions.md")
    elif directories:
        print(f"  Se leen {readable} de {len(directories)} hubs: hay ACLs activas.")

    print("\n[autenticación]")
    auth = build_auth(config)
    print(f"  backend : {auth.describe()}")
    if config.get("AUTH_BACKEND") == "smb" and not config.get("AUTH_HOST"):
        print("  ! AUTH_HOST vacío: no hay contra qué autenticar")
        problems += 1

    print("\n[ejecución]")
    print("  usuario detectado   : {}".format(detect_sid() or "(ninguno)"))
    print("  corridas simultáneas: {}".format(config.get("MAX_CONCURRENT_RUNS")))
    try:
        import IPython  # noqa: F401
        print("  magics de IPython   : disponibles")
    except ImportError:
        print("  magics de IPython   : no disponibles (se comentan al ejecutar)")

    print("\n" + "=" * 62)
    print("Sin problemas." if not problems else f"{problems} problema(s) para revisar.")
    return 1 if problems else 0


def cmd_whoami(args):
    # type: (Any) -> int
    """Los permisos efectivos de un usuario, tal como los ve la aplicación."""
    _config, _client, principal, repo = _build(args)
    print("SID: {}".format(principal.sid or "(no detectado)"))
    if not principal.roles:
        print("\nNo pertenece a ningún hub.")
        print("Un jefe de equipo tiene que agregarlo desde el tab Miembros.")
        return 0
    print("\n{:<20} {:<10} {}".format("HUB", "ROL", "PERMISOS"))
    print("-" * 62)
    from .core import authz
    for hub in repo.list_hubs():
        allowed = [
            name for name, action in (
                ("ver", authz.VIEW_HUB), ("correr", authz.RUN_PROCESS),
                ("historial", authz.VIEW_HISTORY), ("métricas", authz.VIEW_METRICS),
                ("miembros", authz.MANAGE_MEMBERS),
            )
            if repo.policy.check(principal, action, hub.id)
        ]
        print("{:<20} {:<10} {}".format(
            hub.id, principal.role_in(hub.id) or "", ", ".join(allowed)))
    return 0


def cmd_list(args):
    # type: (Any) -> int
    """Las automatizaciones visibles para el usuario."""
    _config, _client, principal, repo = _build(args)
    hubs = repo.list_hubs()
    if not hubs:
        print("{} no ve ningún hub.".format(principal.sid or "(sin usuario)"))
        return 0
    for hub in hubs:
        processes = repo.list_processes(hub.id)
        print(f"\n{hub.name} ({hub.id}) — {len(processes)} proceso(s)")
        print("-" * 62)
        for process in processes:
            mark = " [confirmación]" if process.requires_confirmation else ""
            print(f"  {process.id:<20} {process.name}{mark}")
            if process.description:
                print("  {:<20} {}".format("", process.description))
    return 0


def cmd_run(args):
    # type: (Any) -> int
    """Ejecuta una automatización sin interfaz."""
    config, _client, principal, repo = _build(args)

    hub_ids = [args.hub] if args.hub else principal.hub_ids
    target = None
    hub = None
    for hub_id in hub_ids:
        try:
            for process in repo.list_processes(hub_id):
                if process.id == args.process:
                    target, hub = process, repo.get_hub(hub_id)
                    break
        except Exception:
            continue
        if target:
            break

    if target is None:
        print(f"No se encontró el proceso {args.process!r} entre los hubs de {principal.sid}.")
        print(f"Probá: python -m automation_launcher list --sid {principal.sid}")
        return 2

    try:
        repo.authorize_run(hub.id, target)
    except Exception as exc:
        print(f"Denegado: {exc}")
        return 3

    # Solo se piden credenciales si el proceso las va a necesitar. Pedirlas
    # siempre haria imposible agendar esto en un scheduler.
    password = os.environ.get("PASSWORD") or ""
    if args.ask_password and not password:
        password = getpass.getpass(f"Contraseña de red para {principal.sid}: ")
    credentials = Credentials(sid=principal.sid, password=password) if password else None
    if password:
        redactor.remember(password)

    buffer = ConsoleBuffer(config.get("CONSOLE_MAX_LINES"))
    printed = [0]

    def drain():
        lines = buffer.lines()
        for line in lines[printed[0]:]:
            print(f"[{line.clock}] {line.text}")
        printed[0] = len(lines)

    history = RunHistory(repo.client, repo.hubs_root)
    manager = RunManager(config, buffer=buffer)
    source = _read_notebook(repo, hub, target)
    handle = manager.start(target, hub.id, principal.sid, source, credentials)

    while handle.is_active:
        drain()
        time.sleep(0.25)
    drain()

    history.append(hub.path, handle.to_record())
    print(f"\n{target.name} — {handle.state} en {handle.elapsed:.1f}s")
    return 0 if handle.state in (RunState.DONE, RunState.WARN) else 1


def _read_notebook(repo, hub, process):
    # type: (Any, Any, Any) -> str
    if process.notebook.startswith("/"):
        path = contents.join(process.notebook)
    else:
        path = contents.join(repo.hubs_root, hub.path, process.notebook)
    return repo.client.read_text(path)


# ---------------------------------------------------------------------------

def build_parser():
    # type: () -> argparse.ArgumentParser
    parser = argparse.ArgumentParser(
        prog="python -m automation_launcher",
        description="Automation Launcher desde la terminal.",
    )
    parser.add_argument("--config", help="ruta a launcher_config.py")
    parser.add_argument("--sid", help="usuario a suplantar (por defecto, el del entorno)")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("doctor", help="diagnostica el entorno")
    subparsers.add_parser("whoami", help="muestra los permisos efectivos")
    subparsers.add_parser("list", help="lista las automatizaciones visibles")

    run_parser = subparsers.add_parser("run", help="ejecuta una automatización")
    run_parser.add_argument("process", help="id del proceso")
    run_parser.add_argument("--hub", help="id del hub (si no, se busca en todos)")
    run_parser.add_argument(
        "--ask-password", action="store_true",
        help="pedir la contraseña de red por consola (si no, se toma de $PASSWORD)",
    )
    return parser


def main(argv=None):
    # type: (Optional[List[str]]) -> int
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    handlers = {
        "doctor": cmd_doctor, "whoami": cmd_whoami,
        "list": cmd_list, "run": cmd_run,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
