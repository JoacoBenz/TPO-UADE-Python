"""Politica de autorizacion: el unico lugar donde se decide quien puede que.

Toda la app pregunta aca. No hay chequeos de permisos desparramados por la
interfaz -- si un boton se muestra o no, si una corrida arranca o no, y si un
JSON se puede escribir o no, sale siempre de ``Policy.check``.

Tener un solo punto de decision es lo que hace auditable el modelo: se puede
leer entero en una pantalla, se puede testear exhaustivamente, y cada
decision (permitida o denegada) se puede registrar sin instrumentar cien
lugares distintos.

Sobre el alcance real de esta capa
----------------------------------
Estos chequeos son **defensa en profundidad y experiencia de usuario**, no la
barrera dura. La barrera dura es la ACL de NTFS/DFS sobre la carpeta de cada
hub: si el share deja leer a cualquiera, alguien abre el file browser de
JupyterLab y lee el hub ajeno sin pasar nunca por este codigo.

Las dos capas coinciden por diseno: con las ACLs puestas, la Contents API
devuelve 403 en los hubs ajenos y el repositorio llega al mismo resultado que
esta politica. Ver ``docs/permissions.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import ROLE_LEAD

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import Any, List, Optional  # noqa: F401  (los usan los comentarios `# type:`)

# ---------------------------------------------------------------------------
# Acciones
# ---------------------------------------------------------------------------

#: Ver un hub y sus automatizaciones.
VIEW_HUB = "view_hub"
#: Ejecutar una automatizacion del hub.
RUN_PROCESS = "run_process"
#: Ver el historial de corridas del hub.
VIEW_HISTORY = "view_history"
#: Ver el tab de metricas (solo jefes).
VIEW_METRICS = "view_metrics"
#: Agregar o sacar gente del hub (solo jefes).
MANAGE_MEMBERS = "manage_members"

ALL_ACTIONS = (VIEW_HUB, RUN_PROCESS, VIEW_HISTORY, VIEW_METRICS, MANAGE_MEMBERS)

#: Acciones reservadas al jefe del hub. El resto le alcanza con ser miembro.
LEAD_ONLY_ACTIONS = (VIEW_METRICS, MANAGE_MEMBERS)


class PermissionDenied(Exception):
    """Se intento una accion que la politica no permite."""

    def __init__(self, decision):
        # type: (Decision) -> None
        super().__init__(decision.reason)
        self.decision = decision


class Decision:
    """El resultado de una consulta a la politica, con su motivo.

    El motivo no es decorativo: es lo que se escribe en el audit log y lo que
    se le muestra al usuario cuando algo no aparece. "No tenes permiso" sin
    explicacion genera un ticket; con explicacion, no.
    """

    __slots__ = ("allowed", "action", "sid", "hub_id", "reason")

    def __init__(self, allowed, action, sid, hub_id, reason):
        # type: (bool, str, str, Optional[str], str) -> None
        self.allowed = allowed
        self.action = action
        self.sid = sid
        self.hub_id = hub_id
        self.reason = reason

    def __bool__(self):
        # type: () -> bool
        return self.allowed

    def raise_if_denied(self):
        # type: () -> Decision
        if not self.allowed:
            raise PermissionDenied(self)
        return self

    def to_dict(self):
        # type: () -> dict
        return {
            "allowed": self.allowed,
            "action": self.action,
            "sid": self.sid,
            "hub_id": self.hub_id,
            "reason": self.reason,
        }

    def __repr__(self):
        # type: () -> str
        return "Decision({}, {!r}, sid={!r}, hub={!r})".format(
            "allow" if self.allowed else "DENY", self.action, self.sid, self.hub_id
        )


class Policy:
    """Las reglas. Se leen enteras de una sentada, y esa es la idea."""

    def check(self, principal, action, hub_id=None, process=None):
        # type: (Optional[Principal], str, Optional[str], Optional[Any]) -> Decision
        """Decide si ``principal`` puede hacer ``action`` sobre ``hub_id``."""
        sid = principal.sid if principal is not None else ""

        def deny(reason):
            # type: (str) -> Decision
            return Decision(False, action, sid, hub_id, reason)

        def allow(reason):
            # type: (str) -> Decision
            return Decision(True, action, sid, hub_id, reason)

        # -- 1. Tiene que haber alguien identificado -------------------------
        if principal is None or not principal.sid:
            return deny("no hay sesion iniciada")

        # -- 2. La accion tiene que existir ----------------------------------
        if action not in ALL_ACTIONS:
            return deny(f"accion desconocida: {action!r}")

        # -- 3. Toda accion es sobre un hub ----------------------------------
        if not hub_id:
            return deny(f"la accion {action!r} requiere un hub")

        # -- 4. Pertenencia --------------------------------------------------
        role = principal.role_in(hub_id)
        if role is None:
            return deny(f"{principal.sid} no pertenece al hub {hub_id!r}")

        # -- 5. Acciones reservadas al jefe ----------------------------------
        if action in LEAD_ONLY_ACTIONS and role != ROLE_LEAD:
            return deny(
                f"{principal.sid} es {role!r} en {hub_id!r}: {action} es solo para el jefe del equipo"
            )

        # -- 6. Coherencia del proceso con el hub ----------------------------
        # Se revalida aca, no solo en la UI: un click forjado en el navegador
        # podria mandar el id de un proceso de otro equipo junto al hub propio.
        if process is not None:
            process_hub = getattr(process, "hub_id", None)
            if process_hub != hub_id:
                return deny(
                    "el proceso {!r} pertenece al hub {!r}, no a {!r}".format(
                        getattr(process, "id", "?"), process_hub, hub_id
                    )
                )

        return allow(f"{principal.sid} es {role!r} en {hub_id!r}")

    # -- atajos de lectura, para que la UI se lea bien -----------------------

    def can_view_hub(self, principal, hub_id):
        # type: (Optional[Principal], str) -> bool
        return bool(self.check(principal, VIEW_HUB, hub_id))

    def can_run(self, principal, hub_id, process=None):
        # type: (Optional[Principal], str, Optional[Any]) -> bool
        return bool(self.check(principal, RUN_PROCESS, hub_id, process))

    def can_manage_members(self, principal, hub_id):
        # type: (Optional[Principal], str) -> bool
        return bool(self.check(principal, MANAGE_MEMBERS, hub_id))

    def can_view_metrics(self, principal, hub_id):
        # type: (Optional[Principal], str) -> bool
        return bool(self.check(principal, VIEW_METRICS, hub_id))

    def visible_hub_ids(self, principal):
        # type: (Optional[Principal]) -> List[str]
        """Los hubs que ``principal`` puede ver, en orden estable."""
        if principal is None:
            return []
        return [h for h in principal.hub_ids if self.can_view_hub(principal, h)]


#: Politica compartida. Es sin estado, asi que una sola instancia alcanza.
policy = Policy()
