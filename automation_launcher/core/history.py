"""Historial de corridas y registro de auditoria.

Son dos rastros distintos y viven en lugares distintos a proposito:

* **Historial de corridas** -- que se ejecuto, quien, cuando y como termino.
  Va en la carpeta del hub, dentro del share, porque le pertenece al equipo:
  es lo que alimenta el tab de metricas del jefe y lo que se mira cuando algo
  salio mal ayer a la noche. Esta partido en un archivo por dia.

* **Registro de auditoria** -- las decisiones de autorizacion. Va a un archivo
  local del servidor y no al share, por una razon practica: si el registro
  viviera adentro de la carpeta del hub, escribir en el exigiria permiso de
  escritura sobre esa carpeta a todo el que entre, incluido el que fue
  *rechazado*. Un rechazo tiene que quedar anotado aunque la persona no tenga
  permiso de escribir nada.

Ninguno de los dos puede tumbar la operacion que esta registrando: si el
share no responde, la corrida ya paso y el resultado del usuario vale mas que
la linea de historial. Los fallos de escritura se tragan y se avisan por la
consola.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import TYPE_CHECKING

from . import contents
from .secrets import redactor

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import Any, Dict, List, Optional  # noqa: F401

#: Cuantas lineas se conservan como maximo en el archivo de un dia. Un bucle
#: descontrolado que dispare corridas no puede hacer crecer el archivo hasta
#: volver ilegible la carpeta del hub.
MAX_LINES_PER_DAY = 5000


class RunHistory:
    """Escribe y lee las corridas de un hub sobre el share."""

    def __init__(self, client, hubs_root, on_error=None):
        # type: (Any, str, Optional[Any]) -> None
        self.client = client
        self.hubs_root = hubs_root
        self._on_error = on_error
        # La Contents API no sabe agregar al final de un archivo: hay que
        # leerlo, sumarle la linea y reescribirlo. Este lock evita que dos
        # corridas que terminan a la vez se pisen la escritura.
        self._lock = threading.RLock()

    def _path(self, hub_path, day=None):
        # type: (str, Optional[str]) -> str
        day = day or datetime.now().strftime("%Y-%m-%d")
        return contents.join(self.hubs_root, hub_path, "runs", day + ".jsonl")

    def append(self, hub_path, record):
        # type: (str, Any) -> bool
        """Suma una corrida al historial del dia. Nunca levanta excepcion."""
        payload = record.to_dict() if hasattr(record, "to_dict") else dict(record)
        # Doble red: el historial va a disco, asi que se redacta aunque el
        # campo `message` deberia venir limpio del motor.
        payload["message"] = redactor.scrub(payload.get("message", ""))
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        path = self._path(hub_path)
        with self._lock:
            try:
                existing = self._read_raw(path)
                existing.append(line)
                if len(existing) > MAX_LINES_PER_DAY:
                    existing = existing[-MAX_LINES_PER_DAY:]
                self._write_raw(path, existing)
                return True
            except Exception as exc:
                self._report(f"No se pudo guardar el historial: {redactor.scrub(exc)}")
                return False

    def _read_raw(self, path):
        # type: (str) -> List[str]
        try:
            text = self.client.read_text(path)
        except contents.ContentsError:
            return []
        return [line for line in text.splitlines() if line.strip()]

    def _write_raw(self, path, lines):
        # type: (str, List[str]) -> None
        # Se escribe con el mismo cliente que el resto del share. `write_json`
        # serializa a JSON, asi que para un .jsonl se usa la ruta de texto
        # cuando el cliente la ofrece.
        body = "\n".join(lines) + "\n"
        writer = getattr(self.client, "write_text", None)
        if writer is not None:
            writer(path, body)
        else:
            self.client.write_json(path, lines)

    def _report(self, message):
        # type: (str) -> None
        if self._on_error is not None:
            try:
                self._on_error(message)
            except Exception:
                pass


class AuditLog:
    """Registro local de decisiones de autorizacion y cambios de miembros.

    Es de solo agregar y va a un archivo del servidor. Responde las preguntas
    que llegan despues: quien corrio esto, a quien se le nego el acceso y
    cuando, quien saco a alguien del equipo.
    """

    def __init__(self, path, enabled=True):
        # type: (str, bool) -> None
        self.path = path
        self.enabled = bool(enabled and path)
        self._lock = threading.RLock()

    def __call__(self, event):
        # type: (Dict[str, Any]) -> None
        """Permite pasar el log directamente como callback de auditoria."""
        self.record(event)

    def record(self, event):
        # type: (Dict[str, Any]) -> None
        if not self.enabled:
            return
        payload = dict(event)
        payload.setdefault("event", "authz")
        payload["at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        # Una razon de rechazo puede citar texto de entrada: se redacta igual.
        if "reason" in payload:
            payload["reason"] = redactor.scrub(payload["reason"])
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self._lock:
            try:
                directory = os.path.dirname(self.path)
                if directory and not os.path.isdir(directory):
                    os.makedirs(directory)
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            except Exception:
                # Que no se pueda auditar no puede impedir la operacion. El
                # camino contrario -- fallar cerrado -- dejaria la app
                # inutilizable por un disco lleno.
                pass

    def tail(self, limit=100):
        # type: (int) -> List[Dict[str, Any]]
        """Las ultimas entradas, de la mas nueva a la mas vieja."""
        if not self.enabled or not os.path.isfile(self.path):
            return []
        try:
            with open(self.path, encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError:
            return []
        out = []    # type: List[Dict[str, Any]]
        for line in reversed(lines[-limit * 2:]):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
            if len(out) >= limit:
                break
        return out

    def __repr__(self):
        # type: () -> str
        return f"AuditLog({self.path!r}, enabled={self.enabled})"
