"""Tipos de dominio del launcher.

Todo lo que se mueve entre capas pasa por aca. Las clases son dataclasses
simples y sin comportamiento pesado: las reglas viven en ``authz`` y en
``repository``, no en los modelos.

Nota sobre Python 3.7: se usa ``dataclasses`` (disponible desde 3.7) pero no
``field(kw_only=...)`` ni ``slots=True``, que son 3.10.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Identidad y credenciales
# ---------------------------------------------------------------------------

#: Un SID valido: letras, digitos, punto, guion y guion bajo. Se usa para
#: construir rutas dentro del share, asi que se valida con lista blanca para
#: que nunca pueda contener ".." ni separadores de ruta.
_SID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def normalize_sid(raw):
    # type: (Any) -> str
    """Normaliza un SID a minusculas y valida que sea seguro para rutas.

    Acepta las formas en que aparece un usuario en un entorno Windows
    (``DOMINIO\\usuario``, ``usuario@dominio``) y devuelve solo la parte de
    usuario, en minusculas, para que la comparacion contra ``members.json``
    sea insensible a mayusculas y al dominio.
    """
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    # Se rechaza antes de normalizar en vez de despues: si dejaramos que
    # "../../etc/passwd" colapse a "passwd" el resultado seria seguro pero
    # silencioso, y una entrada asi siempre significa que algo esta mal.
    if ".." in text:
        raise ValueError(f"SID invalido: {raw!r}")
    # Se separa el dominio solo si hay exactamente un separador: "CORP\ana"
    # es una forma legitima, "a\b\c" no lo es de ninguna manera.
    for sep in ("\\", "/"):
        if sep in text:
            parts = text.split(sep)
            if len(parts) != 2:
                raise ValueError(f"SID invalido: {raw!r}")
            text = parts[1]
    if "@" in text:            # usuario@dominio
        text = text.split("@", 1)[0]
    text = text.strip().lower()
    if not _SID_RE.match(text):
        raise ValueError(f"SID invalido: {raw!r}")
    return text


@dataclass
class Credentials:
    """Credenciales de red del usuario, vivas solo en memoria.

    Nunca se serializan ni se escriben a disco. ``__repr__`` esta sobrescrito
    a proposito: un ``print(creds)`` o un traceback que incluya el objeto no
    tiene que filtrar el password.
    """

    sid: str
    password: str
    domain: str = ""

    def __post_init__(self):
        # type: () -> None
        self.sid = normalize_sid(self.sid)

    def __repr__(self):
        # type: () -> str
        return f"Credentials(sid={self.sid!r}, domain={self.domain!r}, password=***)"

    __str__ = __repr__

    @property
    def qualified_user(self):
        # type: () -> str
        """El usuario en la forma que espera ``net use``: ``DOMINIO\\sid``."""
        if self.domain:
            return f"{self.domain}\\{self.sid}"
        return self.sid


# ---------------------------------------------------------------------------
# Roles y principal
# ---------------------------------------------------------------------------

ROLE_LEAD = "lead"
ROLE_MEMBER = "member"


@dataclass
class Principal:
    """Quien esta usando la app y con que rol en cada hub.

    ``roles`` mapea ``hub_id -> rol``. La ausencia de una clave significa que
    el principal no pertenece a ese hub: no hay estado intermedio.
    """

    sid: str
    display_name: str = ""
    roles: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        # type: () -> None
        self.sid = normalize_sid(self.sid)
        if not self.display_name:
            self.display_name = self.sid

    def role_in(self, hub_id):
        # type: (str) -> Optional[str]
        return self.roles.get(hub_id)

    def is_member_of(self, hub_id):
        # type: (str) -> bool
        return hub_id in self.roles

    def is_lead_of(self, hub_id):
        # type: (str) -> bool
        return self.roles.get(hub_id) == ROLE_LEAD

    @property
    def hub_ids(self):
        # type: () -> List[str]
        return sorted(self.roles)

    def __repr__(self):
        # type: () -> str
        return f"Principal(sid={self.sid!r}, roles={self.roles!r})"


# ---------------------------------------------------------------------------
# Hub y proceso
# ---------------------------------------------------------------------------

@dataclass
class Hub:
    """Un equipo y su espacio de automatizaciones dentro del share."""

    id: str
    name: str
    path: str
    description: str = ""

    @classmethod
    def from_dict(cls, data, hub_id=None):
        # type: (Dict[str, Any], Optional[str]) -> Hub
        ident = str(data.get("id") or hub_id or "").strip()
        if not ident:
            raise ValueError("el hub no tiene 'id'")
        return cls(
            id=ident,
            name=str(data.get("name") or ident),
            path=str(data.get("path") or ident),
            description=str(data.get("description") or ""),
        )


@dataclass
class Process:
    """Una automatizacion: un notebook que el launcher sabe correr.

    ``hub_id`` no es decorativo. Se revalida en el momento de ejecutar contra
    los permisos del principal, de modo que un click forjado en el navegador
    no pueda disparar el proceso de otro equipo.
    """

    id: str
    name: str
    notebook: str
    hub_id: str
    description: str = ""
    how_to_run: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 3600
    requires_confirmation: bool = False
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data, hub_id):
        # type: (Dict[str, Any], str) -> Process
        ident = str(data.get("id") or "").strip()
        if not ident:
            raise ValueError("el proceso no tiene 'id'")
        notebook = str(data.get("notebook") or "").strip()
        if not notebook:
            raise ValueError(f"el proceso {ident!r} no tiene 'notebook'")
        try:
            timeout = int(data.get("timeout_seconds", 3600))
        except (TypeError, ValueError):
            raise ValueError(f"el proceso {ident!r} tiene 'timeout_seconds' invalido") from None
        if timeout <= 0:
            raise ValueError(f"el proceso {ident!r} tiene 'timeout_seconds' <= 0")
        params = data.get("parameters") or {}
        if not isinstance(params, dict):
            raise ValueError(f"el proceso {ident!r} tiene 'parameters' que no es un dict")
        tags = data.get("tags") or []
        if not isinstance(tags, (list, tuple)):
            raise ValueError(f"el proceso {ident!r} tiene 'tags' que no es una lista")
        return cls(
            id=ident,
            name=str(data.get("name") or ident),
            notebook=notebook,
            hub_id=hub_id,
            description=str(data.get("description") or ""),
            how_to_run=str(data.get("how_to_run") or ""),
            parameters=dict(params),
            timeout_seconds=timeout,
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            tags=[str(t) for t in tags],
        )

    def matches(self, query):
        # type: (str) -> bool
        """Filtro del buscador: nombre, id, descripcion, notebook y tags."""
        if not query:
            return True
        needle = query.strip().lower()
        haystack = " ".join(
            [self.id, self.name, self.description, self.notebook] + list(self.tags)
        ).lower()
        return needle in haystack


# ---------------------------------------------------------------------------
# Corridas
# ---------------------------------------------------------------------------

class RunState:
    """Estados de una corrida.

    No es un ``enum.Enum`` a proposito: los valores se serializan a JSON en el
    historial y conviene que sean strings planos, sin ``.value`` en cada uso.
    """

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    WARN = "warn"
    ERROR = "error"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

    #: Estados en los que la corrida ya no avanza mas.
    TERMINAL = (DONE, WARN, ERROR, CANCELLED, TIMEOUT)

    #: Estados que cuentan como fracaso en las metricas.
    FAILED = (ERROR, TIMEOUT)


@dataclass
class RunRecord:
    """Una linea del historial: que se corrio, quien, cuando y como termino."""

    run_id: str
    hub_id: str
    process_id: str
    process_name: str
    sid: str
    state: str = RunState.PENDING
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: float = 0.0
    lines: int = 0
    warnings: int = 0
    errors: int = 0
    message: str = ""

    def to_dict(self):
        # type: () -> Dict[str, Any]
        return {
            "run_id": self.run_id,
            "hub_id": self.hub_id,
            "process_id": self.process_id,
            "process_name": self.process_name,
            "sid": self.sid,
            "state": self.state,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": round(self.duration_seconds, 3),
            "lines": self.lines,
            "warnings": self.warnings,
            "errors": self.errors,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data):
        # type: (Dict[str, Any]) -> RunRecord
        return cls(
            run_id=str(data.get("run_id") or ""),
            hub_id=str(data.get("hub_id") or ""),
            process_id=str(data.get("process_id") or ""),
            process_name=str(data.get("process_name") or ""),
            sid=str(data.get("sid") or ""),
            state=str(data.get("state") or RunState.PENDING),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            duration_seconds=float(data.get("duration_seconds") or 0.0),
            lines=int(data.get("lines") or 0),
            warnings=int(data.get("warnings") or 0),
            errors=int(data.get("errors") or 0),
            message=str(data.get("message") or ""),
        )

    @property
    def started_datetime(self):
        # type: () -> Optional[datetime]
        if not self.started_at:
            return None
        try:
            return datetime.strptime(self.started_at, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
