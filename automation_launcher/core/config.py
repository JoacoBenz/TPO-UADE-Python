"""Carga de ``launcher_config.py``, con defaults del lado del codigo.

Regla que gobierna este modulo: **una clave faltante o un share inalcanzable
nunca rompen la app**. Todo valor tiene un default definido aca; el archivo
de config lo pisa si existe y si es valido. Si no, el launcher arranca en
modo degradado y lo dice en pantalla ("config not loaded -- using defaults")
en lugar de tirar un traceback contra la cara del usuario.

El archivo se carga por ruta con ``importlib``, no con un ``import`` a
ciegas, para que el launcher pueda leer la config que vive en el share sin
depender de que ese directorio este en ``sys.path``.
"""

from __future__ import annotations

import importlib.util
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import (  # noqa: F401  (los usan los comentarios `# type:`)
        Any,
        Dict,
        List,
        Optional,
        Tuple,
    )

# ---------------------------------------------------------------------------
# Defaults del lado del codigo
# ---------------------------------------------------------------------------

DEFAULTS = {
    # -- Donde viven las automatizaciones -----------------------------------
    # Raiz dentro de la Contents API de Jupyter. jupyterfs monta el SMB aca.
    "CONTENTS_DIR": "jupyter/notebooks/automations",
    # Subcarpeta con la metadata de los hubs (registry, miembros, procesos).
    "HUBS_DIR": "_hubs",

    # -- Acceso a la Contents API -------------------------------------------
    "JUPYTER_URL": "",              # vacio => se autodetecta del entorno
    "TOKEN_ENV": "ATHENA_IDA_TOKEN",
    "FALLBACK_TOKEN_ENV": "HYDRA_ID_ANYWHERE_TOKEN",
    "VERIFY_TLS": False,
    "REQUEST_TIMEOUT": 30,
    "CACHE_TTL_SECONDS": 30,

    # -- Autenticacion -------------------------------------------------------
    # "smb"  -> valida contra IPC$ en un host SMB del dominio (produccion)
    # "mock" -> acepta cualquier password de largo suficiente (local/demo)
    "AUTH_BACKEND": "smb",
    "AUTH_HOST": "",
    "AUTH_DOMAIN": "",
    "AUTH_TIMEOUT": 20,

    # -- Ejecucion -----------------------------------------------------------
    "RUNNER": "inprocess",          # "inprocess" | "subprocess"
    "MAX_CONCURRENT_RUNS": 3,
    "DEFAULT_TIMEOUT_SECONDS": 3600,
    "CONSOLE_MAX_LINES": 5000,
    "CONSOLE_REFRESH_MS": 200,

    # -- Interfaz ------------------------------------------------------------
    "APP_TITLE": "Automation Launcher",
    "APP_SUBTITLE": "Automation Control Room",
    "ORG_NAME": "",
    "SHOW_HUB_PICKER": True,

    # -- Auditoria -----------------------------------------------------------
    # Archivo local del servidor donde se registran las decisiones de
    # autorizacion. Va local y no al share a proposito: un rechazo tiene que
    # quedar anotado aunque la persona rechazada no tenga permiso de escritura.
    "AUDIT_LOG_PATH": "runs/audit.jsonl",
    "AUDIT_ENABLED": True,

    # -- Modo demo -----------------------------------------------------------
    # Solo tiene efecto con AUTH_BACKEND="mock". Habilita el selector de
    # usuario para poder ver la app con los ojos de distintos roles.
    "DEMO_MODE": False,
    "DEMO_USERS": [],
    "LOCAL_SHARE_ROOT": "",         # si esta seteado se usa LocalContentsClient
}

#: Claves cuyo valor debe ser entero positivo. Se validan al cargar.
_POSITIVE_INT_KEYS = (
    "REQUEST_TIMEOUT",
    "CACHE_TTL_SECONDS",
    "AUTH_TIMEOUT",
    "MAX_CONCURRENT_RUNS",
    "DEFAULT_TIMEOUT_SECONDS",
    "CONSOLE_MAX_LINES",
    "CONSOLE_REFRESH_MS",
)

_VALID_AUTH_BACKENDS = ("smb", "mock")
_VALID_RUNNERS = ("inprocess", "subprocess")


class LauncherConfig:
    """Los valores de configuracion efectivos, ya resueltos.

    Se accede por atributo (``config.CONTENTS_DIR``) o por ``get``. Cualquier
    clave desconocida devuelve el default o ``None`` en vez de explotar.
    """

    def __init__(self, values=None, source=None, problems=None):
        # type: (Optional[Dict[str, Any]], Optional[str], Optional[List[str]]) -> None
        self._values = dict(DEFAULTS)
        if values:
            self._values.update(values)
        #: De donde salio la config, o None si se usaron solo los defaults.
        self.source = source
        #: Problemas no fatales encontrados al cargar, para mostrar en la UI.
        self.problems = list(problems or [])

    # -- acceso --------------------------------------------------------------

    def get(self, key, default=None):
        # type: (str, Any) -> Any
        if key in self._values:
            return self._values[key]
        return DEFAULTS.get(key, default)

    def __getattr__(self, key):
        # type: (str) -> Any
        # Solo se llama cuando el atributo no existe como atributo real.
        try:
            return self.__dict__["_values"][key]
        except KeyError:
            pass
        if key in DEFAULTS:
            return DEFAULTS[key]
        raise AttributeError(key)

    def __contains__(self, key):
        # type: (object) -> bool
        return key in self._values

    def as_dict(self):
        # type: () -> Dict[str, Any]
        return dict(self._values)

    # -- estado --------------------------------------------------------------

    @property
    def loaded(self):
        # type: () -> bool
        """True si se levanto un ``launcher_config.py`` de verdad."""
        return self.source is not None

    @property
    def is_demo(self):
        # type: () -> bool
        return bool(self.get("DEMO_MODE")) and self.get("AUTH_BACKEND") == "mock"

    def status_line(self):
        # type: () -> str
        """El texto que la consola muestra al arrancar."""
        if not self.loaded:
            return "config not loaded — using defaults"
        if self.problems:
            return f"config loaded from {self.source} ({len(self.problems)} advertencia(s))"
        return f"config loaded from {self.source}"

    def __repr__(self):
        # type: () -> str
        return f"LauncherConfig(source={self.source!r}, problems={len(self.problems)})"


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

def read_config_source(source, filename="launcher_config.py"):
    # type: (str, str) -> Dict[str, Any]
    """Ejecuta codigo de configuracion y devuelve sus constantes en mayusculas.

    Se toman solo los nombres en MAYUSCULAS de nivel de modulo: asi el archivo
    puede tener imports y helpers sin que se cuelen como configuracion.
    """
    spec = importlib.util.spec_from_loader(filename, loader=None)
    if spec is None:                                    # pragma: no cover
        raise RuntimeError("no se pudo preparar el modulo de config")
    module = importlib.util.module_from_spec(spec)
    # __file__ absoluto y con los enlaces simbolicos resueltos. Los archivos
    # de configuracion calculan rutas relativas a si mismos
    # (os.path.dirname(os.path.abspath(__file__))); con una ruta relativa o
    # un enlace sin resolver, esas rutas apuntan al lugar equivocado segun
    # desde donde se haya arrancado el proceso.
    module.__file__ = os.path.realpath(filename) if os.path.exists(filename) else filename
    exec(compile(source, filename, "exec"), module.__dict__)   # noqa: S102
    return {
        key: value
        for key, value in vars(module).items()
        if key.isupper() and not key.startswith("_")
    }


def validate(values):
    # type: (Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]
    """Filtra los valores invalidos y explica cada descarte.

    No aborta: un valor malo se descarta y se usa el default, porque dejar la
    app arriba vale mas que ser estricto con una clave suelta. Lo que no se
    hace es descartar en silencio -- todo problema vuelve en la lista.
    """
    clean = {}       # type: Dict[str, Any]
    problems = []    # type: List[str]

    for key, value in values.items():
        if key in _POSITIVE_INT_KEYS:
            try:
                number = int(value)
            except (TypeError, ValueError):
                problems.append(f"{key}: se esperaba un entero, llego {value!r}")
                continue
            if number <= 0:
                problems.append(f"{key}: debe ser mayor que cero, llego {value!r}")
                continue
            clean[key] = number
            continue

        if key == "AUTH_BACKEND":
            if value not in _VALID_AUTH_BACKENDS:
                problems.append(
                    f"AUTH_BACKEND: debe ser uno de {_VALID_AUTH_BACKENDS}, llego {value!r}"
                )
                continue

        if key == "RUNNER":
            if value not in _VALID_RUNNERS:
                problems.append(
                    f"RUNNER: debe ser uno de {_VALID_RUNNERS}, llego {value!r}"
                )
                continue

        if key == "DEMO_USERS" and not isinstance(value, (list, tuple)):
            problems.append(f"DEMO_USERS: se esperaba una lista, llego {type(value)!r}")
            continue

        clean[key] = value

    # Coherencia entre claves: un valor puede ser valido y aun asi no tener
    # sentido junto a otro.
    if clean.get("AUTH_BACKEND") == "smb" and not clean.get("AUTH_HOST", DEFAULTS["AUTH_HOST"]):
        problems.append(
            "AUTH_BACKEND es 'smb' pero AUTH_HOST esta vacio: "
            "no hay contra que autenticar"
        )
    if clean.get("DEMO_MODE") and clean.get("AUTH_BACKEND", DEFAULTS["AUTH_BACKEND"]) != "mock":
        problems.append(
            "DEMO_MODE solo tiene efecto con AUTH_BACKEND='mock'; se ignora el selector de usuario"
        )

    return clean, problems


def load_config(path=None, source_text=None, source_name=None):
    # type: (Optional[str], Optional[str], Optional[str]) -> LauncherConfig
    """Carga la configuracion desde un archivo o desde texto.

    Nunca levanta excepcion: si algo falla devuelve una config con los
    defaults y el motivo dentro de ``problems``, que la UI muestra.
    """
    if source_text is not None:
        name = source_name or "<memoria>"
        try:
            raw = read_config_source(source_text, name)
        except Exception as exc:
            return LauncherConfig(problems=[f"no se pudo leer la config: {exc}"])
        values, problems = validate(raw)
        return LauncherConfig(values, source=name, problems=problems)

    if not path:
        return LauncherConfig(problems=["no se indico ruta de config"])
    if not os.path.isfile(path):
        return LauncherConfig(problems=[f"no existe el archivo de config: {path}"])

    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        raw = read_config_source(text, path)
    except Exception as exc:
        return LauncherConfig(problems=[f"no se pudo leer {path}: {exc}"])

    values, problems = validate(raw)
    return LauncherConfig(values, source=path, problems=problems)
