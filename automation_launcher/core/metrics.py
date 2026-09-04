"""Agregaciones sobre el historial, para el tab de metricas del jefe.

Todo se calcula con la libreria estandar: sin pandas ni numpy. No es
minimalismo por deporte -- este codigo corre adentro del proceso de Voila que
sirve la interfaz, y una importacion pesada por cada vez que alguien abre una
pestana se nota. Con unos miles de corridas, listas y diccionarios sobran.

``statistics.quantiles`` seria comodo pero es de Python 3.8, y el kernel es
3.7, asi que el percentil va calculado a mano.
"""

from __future__ import annotations

from collections import Counter, OrderedDict
from typing import TYPE_CHECKING

from .models import RunState

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import Any, Dict, List, Optional  # noqa: F401


def percentile(values, fraction):
    # type: (List[float], float) -> float
    """Percentil por interpolacion lineal, al estilo de ``numpy.percentile``.

    Se implementa aca porque ``statistics.quantiles`` no existe en 3.7.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * max(0.0, min(1.0, fraction))
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


class ProcessStats:
    """Resumen de un proceso dentro del periodo analizado."""

    __slots__ = ("process_id", "name", "total", "ok", "warn", "failed",
                 "cancelled", "durations", "last_run", "last_state")

    def __init__(self, process_id, name=""):
        # type: (str, str) -> None
        self.process_id = process_id
        self.name = name or process_id
        self.total = 0
        self.ok = 0
        self.warn = 0
        self.failed = 0
        self.cancelled = 0
        self.durations = []     # type: List[float]
        self.last_run = ""
        self.last_state = ""

    @property
    def success_rate(self):
        # type: () -> float
        """Porcentaje de exito sobre las corridas que llegaron a un desenlace.

        Las canceladas quedan afuera del denominador: el usuario aborto, no
        es una falla del proceso, y contarlas castigaria injustamente a un
        proceso largo que la gente corta seguido.
        """
        decided = self.total - self.cancelled
        if decided <= 0:
            return 0.0
        return 100.0 * (self.ok + self.warn) / decided

    @property
    def p50(self):
        # type: () -> float
        return percentile(self.durations, 0.50)

    @property
    def p95(self):
        # type: () -> float
        return percentile(self.durations, 0.95)

    @property
    def avg(self):
        # type: () -> float
        return sum(self.durations) / len(self.durations) if self.durations else 0.0

    def to_dict(self):
        # type: () -> Dict[str, Any]
        return {
            "process_id": self.process_id, "name": self.name, "total": self.total,
            "ok": self.ok, "warn": self.warn, "failed": self.failed,
            "cancelled": self.cancelled, "success_rate": round(self.success_rate, 1),
            "p50": round(self.p50, 1), "p95": round(self.p95, 1),
            "avg": round(self.avg, 1), "last_run": self.last_run,
            "last_state": self.last_state,
        }


class HubMetrics:
    """Todo lo que muestra el tab de metricas, ya calculado."""

    def __init__(self, hub_id, records):
        # type: (str, List[Dict[str, Any]]) -> None
        self.hub_id = hub_id
        self.records = records or []
        self.by_process = OrderedDict()     # type: OrderedDict
        self.by_user = Counter()
        self.by_day = OrderedDict()         # type: OrderedDict
        self.total = 0
        self.ok = 0
        self.warn = 0
        self.failed = 0
        self.cancelled = 0
        self.failures = []                  # type: List[Dict[str, Any]]
        self._compute()

    def _compute(self):
        # type: () -> None
        for record in self.records:
            state = str(record.get("state") or "")
            process_id = str(record.get("process_id") or "?")
            stats = self.by_process.get(process_id)
            if stats is None:
                stats = ProcessStats(process_id, str(record.get("process_name") or ""))
                self.by_process[process_id] = stats

            self.total += 1
            stats.total += 1
            if state == RunState.DONE:
                self.ok += 1
                stats.ok += 1
            elif state == RunState.WARN:
                self.warn += 1
                stats.warn += 1
            elif state == RunState.CANCELLED:
                self.cancelled += 1
                stats.cancelled += 1
            elif state in RunState.FAILED:
                self.failed += 1
                stats.failed += 1
                self.failures.append(record)

            try:
                duration = float(record.get("duration_seconds") or 0.0)
            except (TypeError, ValueError):
                duration = 0.0
            if duration > 0:
                stats.durations.append(duration)

            started = str(record.get("started_at") or "")
            if started > stats.last_run:
                stats.last_run = started
                stats.last_state = state

            sid = str(record.get("sid") or "?")
            self.by_user[sid] += 1

            day = started[:10]
            if day:
                bucket = self.by_day.setdefault(day, {"total": 0, "failed": 0})
                bucket["total"] += 1
                if state in RunState.FAILED:
                    bucket["failed"] += 1

        # Lo mas usado primero: es el orden en que un jefe quiere leer esto.
        self.by_process = OrderedDict(
            sorted(self.by_process.items(), key=lambda kv: kv[1].total, reverse=True)
        )
        self.by_day = OrderedDict(sorted(self.by_day.items()))
        self.failures.sort(key=lambda r: str(r.get("started_at") or ""), reverse=True)

    @property
    def success_rate(self):
        # type: () -> float
        decided = self.total - self.cancelled
        if decided <= 0:
            return 0.0
        return 100.0 * (self.ok + self.warn) / decided

    @property
    def total_seconds(self):
        # type: () -> float
        return sum(sum(s.durations) for s in self.by_process.values())

    def daily_series(self, days=14):
        # type: (int) -> List[Dict[str, Any]]
        """Los ultimos N dias con actividad, para el grafico de barras."""
        items = list(self.by_day.items())[-days:]
        return [
            {"day": day, "total": values["total"], "failed": values["failed"]}
            for day, values in items
        ]

    def top_users(self, limit=5):
        # type: (int) -> List[Any]
        return self.by_user.most_common(limit)

    def recent_failures(self, limit=5):
        # type: (int) -> List[Dict[str, Any]]
        return self.failures[:limit]

    def slowest(self, limit=5):
        # type: (int) -> List[ProcessStats]
        return sorted(self.by_process.values(), key=lambda s: s.p95, reverse=True)[:limit]

    def most_fragile(self, limit=5, min_runs=3):
        # type: (int, int) -> List[ProcessStats]
        """Los procesos que mas fallan, entre los que corrieron lo suficiente.

        El minimo de corridas evita que un proceso nuevo que fallo una sola
        vez encabece la lista con 0% de exito y desvie la atencion del que
        viene fallando de verdad hace dos semanas.
        """
        candidates = [
            s for s in self.by_process.values()
            if (s.total - s.cancelled) >= min_runs and s.failed > 0
        ]
        return sorted(candidates, key=lambda s: s.success_rate)[:limit]

    def to_dict(self):
        # type: () -> Dict[str, Any]
        return {
            "hub_id": self.hub_id, "total": self.total, "ok": self.ok,
            "warn": self.warn, "failed": self.failed, "cancelled": self.cancelled,
            "success_rate": round(self.success_rate, 1),
            "total_seconds": round(self.total_seconds, 1),
            "by_process": [s.to_dict() for s in self.by_process.values()],
            "top_users": self.top_users(),
            "daily": self.daily_series(),
        }

    def __repr__(self):
        # type: () -> str
        return f"HubMetrics({self.hub_id!r}, total={self.total}, exito={self.success_rate:.0f}%)"
