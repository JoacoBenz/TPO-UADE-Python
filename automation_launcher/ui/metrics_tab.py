"""Tab de metricas del hub. Solo lo ve el jefe del equipo.

Todo se dibuja con HTML y CSS, sin matplotlib. Un grafico de barras de catorce
dias no justifica importar una libreria de graficos adentro del proceso que
sirve la interfaz: la importacion sola tarda mas que dibujar la pantalla
entera, y cada figura hay que renderizarla a imagen y mandarla por el
websocket.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import ipywidgets as W

from ..core.authz import PermissionDenied
from ..core.metrics import HubMetrics
from . import widgets as ui

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import Any, List  # noqa: F401


def _bar(percentage, tone=""):
    # type: (float, str) -> str
    width = max(0.0, min(100.0, percentage))
    return f'<div class="al-bar {tone}"><span style="width:{width:.0f}%"></span></div>'


def _tone_for(rate):
    # type: (float) -> str
    if rate >= 90:
        return ""
    if rate >= 70:
        return "al-bar-warn"
    return "al-bar-error"


class MetricsView:
    """Resumen, tabla por proceso, actividad diaria y ultimas fallas."""

    def __init__(self, context, hub, days=30):
        # type: (Any, Any, int) -> None
        self.ctx = context
        self.hub = hub
        self.days = days

        self.body = ui.html_box("")
        self.reload_button = ui.button("Recargar", icon="refresh")
        self.reload_button.on_click(lambda _b: self.reload())
        self.widget = W.VBox(
            [
                W.HBox(
                    [
                        ui.html_box(
                            '<div class="al-admin-note" style="margin:0">Actividad de '
                            f"<b>{ui.esc(hub.name)}</b> en los últimos {days} días. Sale del historial de "
                            "corridas que el launcher guarda en la carpeta del hub.</div>"
                        ),
                        self.reload_button,
                    ],
                    layout=W.Layout(align_items="center", width="100%"),
                ),
                self.body,
            ],
            layout=W.Layout(width="100%"),
        )
        self.reload()

    def reload(self):
        # type: () -> None
        self.ctx.repo.refresh()
        try:
            records = self.ctx.repo.read_runs(self.hub.id, days=self.days)
        except PermissionDenied as exc:
            self.body.value = ui.empty_state(str(exc))
            return
        except Exception as exc:
            self.body.value = ui.empty_state(f"No se pudo leer el historial: {exc}")
            return

        metrics = HubMetrics(self.hub.id, records)
        if not metrics.total:
            self.body.value = ui.empty_state(
                "Todavía no hay corridas registradas para este hub."
            )
            return
        self.body.value = "".join(
            [
                self._summary(metrics),
                self._daily(metrics),
                self._by_process(metrics),
                self._failures(metrics),
                self._users(metrics),
            ]
        )

    # -- bloques -------------------------------------------------------------

    def _summary(self, m):
        # type: (HubMetrics) -> str
        hours = m.total_seconds / 3600.0
        return '<div class="al-metric-grid">{}{}{}{}{}</div>'.format(
            ui.stat_card(m.total, "Corridas", "primary"),
            ui.stat_card(f"{m.success_rate:.0f}%", "Tasa de éxito",
                         "ok" if m.success_rate >= 90 else "warn"),
            ui.stat_card(m.failed, "Fallidas", "error" if m.failed else ""),
            ui.stat_card(m.warn, "Con avisos", "warn" if m.warn else ""),
            ui.stat_card(f"{hours:.1f} h", "Tiempo de cómputo", "primary", mono=True),
        )

    def _daily(self, m):
        # type: (HubMetrics) -> str
        series = m.daily_series(14)
        if not series:
            return ""
        peak = max(d["total"] for d in series) or 1
        columns = []    # type: List[str]
        for day in series:
            height = 52.0 * day["total"] / peak
            failed_height = height * (day["failed"] / day["total"]) if day["total"] else 0
            ok_height = max(2.0, height - failed_height)
            bars = ""
            if failed_height > 0:
                bars += f'<div class="al-spark-fail" style="height:{failed_height:.0f}px"></div>'
            bars += f'<div class="al-spark-ok" style="height:{ok_height:.0f}px"></div>'
            columns.append(
                '<div class="al-spark-col" title="{day}: {total} corridas, {failed} fallidas">'
                '{bars}<div class="al-spark-day">{short}</div></div>'.format(
                    day=day["day"], total=day["total"], failed=day["failed"],
                    bars=bars, short=day["day"][5:],
                )
            )
        return (
            '<div class="al-card" style="padding:16px 20px;margin-bottom:18px">'
            '<div class="al-section-title">Actividad diaria</div>'
            '<div class="al-spark">{}</div></div>'
        ).format("".join(columns))

    def _by_process(self, m):
        # type: (HubMetrics) -> str
        rows = []   # type: List[str]
        for stats in m.by_process.values():
            rows.append(
                "<tr><td><b>{name}</b><div style='color:#9aa7bf;font-size:11px'>{pid}</div></td>"
                '<td class="al-num">{total}</td>'
                '<td class="al-num">{failed}</td>'
                "<td style='min-width:120px'>{bar}"
                "<div style='font-size:11px;color:#6b7a99;margin-top:3px'>{rate:.0f}%</div></td>"
                '<td class="al-num">{p50:.0f}s</td>'
                '<td class="al-num">{p95:.0f}s</td>'
                "<td style='font-size:11.5px;color:#6b7a99'>{last}</td></tr>".format(
                    name=ui.esc(stats.name), pid=ui.esc(stats.process_id),
                    total=stats.total, failed=stats.failed,
                    bar=_bar(stats.success_rate, _tone_for(stats.success_rate)),
                    rate=stats.success_rate, p50=stats.p50, p95=stats.p95,
                    last=ui.esc((stats.last_run or "—").replace("T", " ")),
                )
            )
        return (
            '<div class="al-card" style="padding:8px 12px 4px;margin-bottom:18px">'
            '<div class="al-section-title" style="padding:8px 12px 0">Por proceso</div>'
            '<table class="al-table"><tr>'
            "<th>Proceso</th><th style='text-align:right'>Corridas</th>"
            "<th style='text-align:right'>Fallas</th><th>Éxito</th>"
            "<th style='text-align:right'>p50</th><th style='text-align:right'>p95</th>"
            "<th>Última</th></tr>{}</table></div>"
        ).format("".join(rows))

    def _failures(self, m):
        # type: (HubMetrics) -> str
        failures = m.recent_failures(5)
        if not failures:
            return (
                '<div class="al-card" style="padding:16px 20px;margin-bottom:18px">'
                '<div class="al-section-title">Últimas fallas</div>'
                "<div style='color:#16a34a;font-size:13px'>Sin fallas en el período. 🎉</div>"
                "</div>"
            )
        rows = "".join(
            "<tr><td><b>{name}</b></td><td>{sid}</td>"
            "<td style='font-size:11.5px;color:#6b7a99'>{when}</td>"
            "<td style='color:#dc2626;font-size:12px'>{msg}</td></tr>".format(
                name=ui.esc(record.get("process_name") or record.get("process_id")),
                sid=ui.esc(record.get("sid")),
                when=ui.esc(str(record.get("started_at") or "").replace("T", " ")),
                msg=ui.esc(record.get("message") or "—"),
            )
            for record in failures
        )
        return (
            '<div class="al-card" style="padding:8px 12px 4px;margin-bottom:18px">'
            '<div class="al-section-title" style="padding:8px 12px 0">Últimas fallas</div>'
            '<table class="al-table"><tr><th>Proceso</th><th>Usuario</th>'
            f"<th>Cuándo</th><th>Detalle</th></tr>{rows}</table></div>"
        )

    def _users(self, m):
        # type: (HubMetrics) -> str
        users = m.top_users(6)
        if not users:
            return ""
        peak = users[0][1] or 1
        rows = "".join(
            f"<tr><td><b>{ui.esc(sid)}</b></td><td class='al-num'>{count}</td>"
            f"<td style='min-width:140px'>{_bar(100.0 * count / peak)}</td></tr>"
            for sid, count in users
        )
        return (
            '<div class="al-card" style="padding:8px 12px 4px">'
            '<div class="al-section-title" style="padding:8px 12px 0">Quién corre qué</div>'
            '<table class="al-table"><tr><th>Usuario</th>'
            f"<th style='text-align:right'>Corridas</th><th></th></tr>{rows}</table></div>"
        )
