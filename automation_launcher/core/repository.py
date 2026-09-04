"""Acceso a los datos del share, siempre acotado a un principal.

Este modulo es el unico camino por el que la app lee hubs, procesos y
miembros. Y la firma es deliberada::

    repo = HubRepository(principal, client, config)

El principal se fija al construir, no se pasa en cada llamada. No existe una
forma de pedirle a este objeto un hub al que el usuario no pertenece: no es
que filtre los resultados despues de traerlos, es que no los va a buscar.

Esa diferencia importa. Un filtro posterior se puede olvidar en una rama
nueva del codigo; un constructor no se puede saltear.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from . import authz, contents
from .models import ROLE_LEAD, ROLE_MEMBER, Hub, Principal, Process, normalize_sid

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import (  # noqa: F401  (los usan los comentarios `# type:`)
        Any,
        Callable,
        Dict,
        List,
        Optional,
    )

#: Nombres de archivo dentro de la carpeta de cada hub.
REGISTRY_FILE = "registry.json"
HUB_FILE = "hub.json"
MEMBERS_FILE = "members.json"
PROCESSES_FILE = "processes.json"
RUNS_DIR = "runs"


class ConflictError(Exception):
    """Otro jefe modifico los miembros mientras vos editabas.

    Sin esto, dos jefes editando a la vez producen una escritura que pisa la
    otra en silencio y saca a alguien del equipo sin que nadie entienda por
    que. Con esto, el segundo en guardar recibe un error claro y vuelve a
    intentar sobre el estado nuevo.
    """


class Membership:
    """El contenido de ``members.json`` de un hub."""

    __slots__ = ("hub_id", "leads", "members", "revision", "updated_at", "updated_by")

    def __init__(self, hub_id, leads=None, members=None, revision=0,
                 updated_at="", updated_by=""):
        # type: (str, Optional[List[str]], Optional[List[str]], int, str, str) -> None
        self.hub_id = hub_id
        self.leads = _clean_sids(leads)
        self.members = _clean_sids(members)
        self.revision = int(revision or 0)
        self.updated_at = updated_at
        self.updated_by = updated_by

    @classmethod
    def from_dict(cls, hub_id, data):
        # type: (str, Dict[str, Any]) -> Membership
        if not isinstance(data, dict):
            raise contents.ContentsError(f"members.json de {hub_id!r} no es un objeto")
        return cls(
            hub_id=hub_id,
            leads=data.get("leads"),
            members=data.get("members"),
            revision=data.get("revision") or 0,
            updated_at=str(data.get("updated_at") or ""),
            updated_by=str(data.get("updated_by") or ""),
        )

    def to_dict(self):
        # type: () -> Dict[str, Any]
        return {
            "leads": list(self.leads),
            "members": list(self.members),
            "revision": self.revision,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
        }

    def role_of(self, sid):
        # type: (str) -> Optional[str]
        """El rol de ``sid``, o None si no pertenece.

        Un jefe es tambien miembro: figurar en ``leads`` alcanza para tener
        todo lo que tiene un miembro, sin necesidad de repetirlo en la otra
        lista.
        """
        sid = normalize_sid(sid)
        if sid in self.leads:
            return ROLE_LEAD
        if sid in self.members:
            return ROLE_MEMBER
        return None

    @property
    def everyone(self):
        # type: () -> List[str]
        return sorted(set(self.leads) | set(self.members))

    def __repr__(self):
        # type: () -> str
        return f"Membership({self.hub_id!r}, leads={len(self.leads)}, members={len(self.members)}, rev={self.revision})"


def _clean_sids(values):
    # type: (Any) -> List[str]
    """Normaliza una lista de SIDs, descartando lo que no sea valido.

    Los archivos del share los editan personas: van a aparecer duplicados,
    mayusculas y espacios. Se limpian en vez de fallar, pero una entrada con
    forma imposible se descarta en lugar de arrastrarse.
    """
    if not values:
        return []
    out = []    # type: List[str]
    for raw in values:
        try:
            sid = normalize_sid(raw)
        except ValueError:
            continue
        if sid and sid not in out:
            out.append(sid)
    return sorted(out)


# ---------------------------------------------------------------------------
# Construccion del principal
# ---------------------------------------------------------------------------

def build_principal(sid, client, config, display_name="", audit=None):
    # type: (str, Any, Any, str, Optional[Callable]) -> Principal
    """Arma el ``Principal`` leyendo la pertenencia real desde el share.

    Los roles no se los pasa nadie: se derivan de los ``members.json``. Eso
    significa que el jefe agrega a alguien y en el proximo login ya esta,
    sin redeploy ni reinicio.

    Un hub que no se puede leer (403 por ACL, o JSON roto) simplemente no
    aporta rol. Es el comportamiento correcto en las dos lecturas: si la ACL
    te tapa el hub, no sos miembro; si el archivo esta roto, no se inventa
    una pertenencia que no se pudo verificar.
    """
    sid = normalize_sid(sid)
    principal = Principal(sid=sid, display_name=display_name or sid)
    if not sid:
        return principal

    hubs_root = contents.join(config.get("CONTENTS_DIR"), config.get("HUBS_DIR"))
    for hub in _read_registry(client, hubs_root, audit):
        try:
            membership = _read_membership(client, hubs_root, hub)
        except contents.AccessDenied:
            # La ACL hizo su trabajo. No es un error: es un "no sos de aca".
            continue
        except contents.ContentsError:
            _audit(audit, "hub_unreadable", sid, hub.id, "no se pudo leer members.json")
            continue
        role = membership.role_of(sid)
        if role is not None:
            principal.roles[hub.id] = role
    return principal


def _read_registry(client, hubs_root, audit=None):
    # type: (Any, str, Optional[Callable]) -> List[Hub]
    """Lee ``registry.json``; si no esta, descubre los hubs por carpeta.

    El registry es una comodidad (permite nombres lindos y orden), no un
    requisito: un hub nuevo se puede dar de alta creando la carpeta y el
    launcher lo va a encontrar igual.
    """
    hubs = []       # type: List[Hub]
    seen = set()    # type: set

    registry_path = contents.join(hubs_root, REGISTRY_FILE)
    try:
        data = client.read_json(registry_path)
        raw_hubs = data.get("hubs") if isinstance(data, dict) else data
        for item in raw_hubs or []:
            try:
                hub = Hub.from_dict(item)
            except ValueError:
                continue
            if hub.id not in seen:
                seen.add(hub.id)
                hubs.append(hub)
    except contents.ContentsError:
        _audit(audit, "registry_missing", "", None, f"no hay registry.json en {hubs_root}")

    try:
        for entry in client.list_dir(hubs_root):
            if entry.is_dir and entry.name not in seen:
                seen.add(entry.name)
                hubs.append(Hub(id=entry.name, name=entry.name, path=entry.name))
    except contents.ContentsError:
        pass

    return hubs


def _read_membership(client, hubs_root, hub):
    # type: (Any, str, Hub) -> Membership
    path = contents.join(hubs_root, hub.path, MEMBERS_FILE)
    data = client.read_json(path)
    return Membership.from_dict(hub.id, data)


def _audit(audit, event, sid, hub_id, detail):
    # type: (Optional[Callable], str, str, Optional[str], str) -> None
    if audit is None:
        return
    try:
        audit({"event": event, "sid": sid, "hub_id": hub_id, "detail": detail})
    except Exception:
        # La auditoria nunca puede tumbar la operacion que estaba auditando.
        pass


# ---------------------------------------------------------------------------
# Repositorio
# ---------------------------------------------------------------------------

class HubRepository:
    """Lectura y escritura del share, acotada al principal de la sesion."""

    def __init__(self, principal, client, config, policy=None, audit=None):
        # type: (Principal, Any, Any, Optional[authz.Policy], Optional[Callable]) -> None
        self.principal = principal
        self.client = client
        self.config = config
        self.policy = policy or authz.policy
        self._audit = audit
        self.hubs_root = contents.join(config.get("CONTENTS_DIR"), config.get("HUBS_DIR"))
        self._hub_cache = None      # type: Optional[Dict[str, Hub]]

    # -- autorizacion --------------------------------------------------------

    def _authorize(self, action, hub_id, process=None):
        # type: (str, str, Optional[Process]) -> authz.Decision
        """Consulta la politica, deja rastro y corta si no alcanza.

        Se registran tambien las decisiones permitidas: un audit log que solo
        guarda los rechazos no sirve para responder "quien corrio esto".
        """
        decision = self.policy.check(self.principal, action, hub_id, process)
        if self._audit is not None:
            payload = decision.to_dict()
            payload["event"] = "authz"
            if process is not None:
                payload["process_id"] = process.id
            _audit_raw(self._audit, payload)
        return decision.raise_if_denied()

    # -- hubs ----------------------------------------------------------------

    def _all_hubs(self):
        # type: () -> Dict[str, Hub]
        if self._hub_cache is None:
            self._hub_cache = {
                hub.id: hub for hub in _read_registry(self.client, self.hubs_root, self._audit)
            }
        return self._hub_cache

    def list_hubs(self):
        # type: () -> List[Hub]
        """Los hubs del principal. Nunca aparece uno ajeno en esta lista."""
        allowed = set(self.policy.visible_hub_ids(self.principal))
        catalog = self._all_hubs()
        return [catalog[hub_id] for hub_id in sorted(allowed) if hub_id in catalog]

    def get_hub(self, hub_id):
        # type: (str) -> Hub
        self._authorize(authz.VIEW_HUB, hub_id)
        hub = self._all_hubs().get(hub_id)
        if hub is None:
            raise contents.NotFound(f"no existe el hub {hub_id!r}")
        return hub

    # -- procesos ------------------------------------------------------------

    def list_processes(self, hub_id):
        # type: (str) -> List[Process]
        """Las automatizaciones del hub, ya autorizadas.

        Un proceso con datos invalidos se saltea y se audita en lugar de
        tumbar la pantalla entera: que una automatizacion mal cargada deje al
        equipo sin poder correr las otras nueve seria el peor resultado.
        """
        hub = self.get_hub(hub_id)
        path = contents.join(self.hubs_root, hub.path, PROCESSES_FILE)
        try:
            data = self.client.read_json(path)
        except contents.NotFound:
            return []
        raw_list = data.get("processes") if isinstance(data, dict) else data
        processes = []      # type: List[Process]
        for item in raw_list or []:
            try:
                processes.append(Process.from_dict(item, hub_id))
            except ValueError as exc:
                _audit(self._audit, "process_invalid", self.principal.sid, hub_id, str(exc))
        return processes

    def get_process(self, hub_id, process_id):
        # type: (str, str) -> Process
        for process in self.list_processes(hub_id):
            if process.id == process_id:
                return process
        raise contents.NotFound(
            f"no existe el proceso {process_id!r} en el hub {hub_id!r}"
        )

    def authorize_run(self, hub_id, process):
        # type: (str, Process) -> authz.Decision
        """Ultima verificacion antes de ejecutar.

        Se llama desde el motor, no desde la UI, para que ninguna ruta de
        ejecucion pueda saltearla.
        """
        return self._authorize(authz.RUN_PROCESS, hub_id, process)

    # -- miembros ------------------------------------------------------------

    def get_membership(self, hub_id):
        # type: (str) -> Membership
        """Lee la pertenencia. Ser miembro alcanza: el equipo se ve entre si."""
        hub = self.get_hub(hub_id)
        try:
            return _read_membership(self.client, self.hubs_root, hub)
        except contents.NotFound:
            return Membership(hub_id)

    def save_membership(self, hub_id, leads, members, expected_revision=None):
        # type: (str, List[str], List[str], Optional[int]) -> Membership
        """Reescribe ``members.json``. Solo el jefe del hub puede.

        Dos protecciones que no son opcionales en algo que se edita a mano
        desde una UI compartida:

        * **Control de concurrencia.** Si ``expected_revision`` no coincide
          con lo que hay en el share, otro jefe guardo mientras editabas y se
          levanta ``ConflictError`` en lugar de pisarlo.

        * **El hub no se queda sin jefe.** Un hub sin nadie en ``leads`` no lo
          puede volver a administrar nadie; habria que arreglarlo editando el
          JSON a mano en el share. Se rechaza antes de que pase.
        """
        self._authorize(authz.MANAGE_MEMBERS, hub_id)
        hub = self.get_hub(hub_id)

        clean_leads = _clean_sids(leads)
        clean_members = _clean_sids(members)
        if not clean_leads:
            raise ValueError(
                f"el hub {hub_id!r} quedaria sin jefe: tiene que haber al menos uno"
            )

        # Un jefe no se repite en la lista de miembros: el rol ya lo incluye.
        clean_members = [sid for sid in clean_members if sid not in clean_leads]

        current = self.get_membership(hub_id)
        if expected_revision is not None and current.revision != expected_revision:
            raise ConflictError(
                f"otro jefe modifico los miembros de {hub_id!r} (revision {current.revision} != {expected_revision}). "
                "Refresca y volve a aplicar tus cambios."
            )

        updated = Membership(
            hub_id=hub_id,
            leads=clean_leads,
            members=clean_members,
            revision=current.revision + 1,
            updated_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            updated_by=self.principal.sid,
        )
        path = contents.join(self.hubs_root, hub.path, MEMBERS_FILE)
        self.client.write_json(path, updated.to_dict())

        _audit(
            self._audit, "members_changed", self.principal.sid, hub_id,
            f"leads={len(updated.leads)} members={len(updated.members)} rev={updated.revision}",
        )
        return updated

    # -- historial -----------------------------------------------------------

    def runs_dir(self, hub_id):
        # type: (str) -> str
        hub = self.get_hub(hub_id)
        return contents.join(self.hubs_root, hub.path, RUNS_DIR)

    def read_runs(self, hub_id, days=30):
        # type: (str, int) -> List[Dict[str, Any]]
        """Lee el historial del hub, de lo mas nuevo a lo mas viejo.

        El historial esta partido en un archivo por dia. Se leen solo los
        ultimos ``days`` archivos: con un anio de corridas, cargar todo para
        dibujar un tab de metricas significaria bajar decenas de megas por
        SMB cada vez que alguien abre la pantalla.
        """
        self._authorize(authz.VIEW_HISTORY, hub_id)
        directory = self.runs_dir(hub_id)
        try:
            entries = self.client.list_dir(directory)
        except contents.ContentsError:
            return []
        files = sorted(
            (e for e in entries if e.name.endswith(".jsonl")),
            key=lambda e: e.name, reverse=True,
        )[:max(1, days)]

        records = []    # type: List[Dict[str, Any]]
        for entry in files:
            try:
                text = self.client.read_text(entry.path)
            except contents.ContentsError:
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue    # una linea corrupta no invalida el resto
        return records

    def refresh(self):
        # type: () -> None
        """Tira la cache. Es lo que hace el boton Refresh."""
        self._hub_cache = None
        self.client.clear_cache()


def _audit_raw(audit, payload):
    # type: (Callable, Dict[str, Any]) -> None
    try:
        audit(payload)
    except Exception:
        pass
