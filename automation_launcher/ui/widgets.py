"""Componentes reutilizables de la interfaz.

Cada uno arma widgets de ipywidgets y les pega las clases CSS de ``theme``.
Nada de estilos inline: si un color se define en dos lugares, tarde o
temprano se van a desincronizar.
"""

from __future__ import annotations

import html
import threading
import time
from typing import TYPE_CHECKING

import ipywidgets as W

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import Any, Callable, Dict, List, Optional  # noqa: F401


def esc(text):
    # type: (Any) -> str
    """Escapa texto para insertarlo en HTML.

    Se usa en todo lo que viene del share (nombres de procesos, descripciones,
    SIDs). Esos archivos los editan personas y podrian traer ``<`` o ``&``;
    sin escapar, romperian el layout -- y con contenido malicioso, algo peor.
    """
    return html.escape("" if text is None else str(text))


def button(description, classes=(), icon="", tooltip="", disabled=False, width=None):
    # type: (str, Any, str, str, bool, Optional[str]) -> W.Button
    layout = W.Layout(height="36px")
    if width:
        layout.width = width
    control = W.Button(description=description, icon=icon, tooltip=tooltip,
                       disabled=disabled, layout=layout)
    control.add_class("al-btn")
    for name in classes:
        control.add_class(name)
    return control


def html_box(markup, classes=()):
    # type: (str, Any) -> W.HTML
    widget = W.HTML(markup)
    for name in classes:
        widget.add_class(name)
    return widget


def topbar(org_name):
    # type: (str) -> W.HTML
    """La barra institucional negra de arriba."""
    org = esc(org_name) if org_name else "&nbsp;"
    return html_box(
        '<div class="al-topbar">'
        f'<span class="al-org">{org}</span>'
        '<span class="al-spacer"></span>'
        '<span class="al-badge">i</span>'
        "</div>"
    )


def stat_card(value, label, tone="", mono=False):
    # type: (Any, str, str, bool) -> str
    """Una de las tarjetas de numeros del tablero.

    Todas ocupan una porcion igual del ancho del panel (ver ``.al-stat`` en
    theme.py): no hay una variante "angosta" ni "ancha", la distribucion
    pareja es lo que evita que las tarjetas se agrupen a la izquierda y
    dejen la mitad del panel como espacio vacio.
    """
    classes = ["al-stat-value"]
    if tone:
        classes.append("al-v-" + tone)
    if mono:
        classes.append("al-v-mono")
    return (
        '<div class="al-stat">'
        f'<div class="{" ".join(classes)}">{esc(value)}</div>'
        f'<div class="al-stat-label">{esc(label)}</div>'
        "</div>"
    )


def format_duration(seconds):
    # type: (float) -> str
    """Segundos a ``MM:SS``, que es como se lee el cronometro del tablero."""
    seconds = max(0, int(seconds or 0))
    if seconds >= 3600:
        return f"{seconds // 3600:d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class ConsoleView:
    """La consola oscura, con repintado agrupado por tiempo.

    El detalle que decide si esto se siente rapido: **no se repinta por cada
    linea**. Un notebook puede emitir cientos de lineas por segundo y cada
    repintado manda el HTML entero por el websocket de Voila; hacerlo por
    linea satura la conexion y traba el navegador.

    En cambio se marca "hay cambios" y un hilo pintor refresca como maximo
    cada ``refresh_ms``. El usuario percibe salida continua y el navegador
    recibe cinco actualizaciones por segundo en vez de quinientas.
    """

    def __init__(self, buffer, refresh_ms=200, max_render_lines=600):
        # type: (Any, int, int) -> None
        self.buffer = buffer
        self.refresh_seconds = max(0.05, refresh_ms / 1000.0)
        self.max_render_lines = max_render_lines
        self.source_filter = None   # type: Optional[str]

        self.body = html_box("", ["al-console-body"])
        self.bar = html_box("")
        self.widget = W.VBox([self.bar, self.body])
        self.widget.add_class("al-console")

        self._dirty = True
        self._stop = threading.Event()
        self._started = 0.0
        self._live = False
        self._painter = None    # type: Optional[threading.Thread]
        buffer.subscribe(self._mark_dirty)
        self.render()

    # -- ciclo de vida --------------------------------------------------------

    def start(self):
        # type: () -> None
        if self._painter is not None:
            return
        self._painter = threading.Thread(target=self._loop, name="console-painter", daemon=True)
        self._painter.start()

    def stop(self):
        # type: () -> None
        self._stop.set()

    def _loop(self):
        # type: () -> None
        while not self._stop.is_set():
            time.sleep(self.refresh_seconds)
            # El cronometro tiene que avanzar aunque no llegue salida nueva.
            if self._dirty or self._live:
                try:
                    self.render()
                except Exception:
                    pass

    def _mark_dirty(self):
        # type: () -> None
        self._dirty = True

    # -- estado ---------------------------------------------------------------

    def set_live(self, live, started_at=0.0):
        # type: (bool, float) -> None
        self._live = live
        self._started = started_at or (time.time() if live else 0.0)
        self._dirty = True

    def set_filter(self, source):
        # type: (Optional[str]) -> None
        self.source_filter = source or None
        self._dirty = True

    # -- dibujo ---------------------------------------------------------------

    def render(self):
        # type: () -> None
        self._dirty = False
        stats = self.buffer.stats
        elapsed = (time.time() - self._started) if (self._live and self._started) else 0.0

        chips = [
            '<span class="al-chip">{} lines</span>'.format(stats["lines"]),
            '<span class="al-chip{}">{} warn</span>'.format(
                " al-chip-warn" if stats["warnings"] else "", stats["warnings"]),
            '<span class="al-chip{}">{} err</span>'.format(
                " al-chip-error" if stats["errors"] else "", stats["errors"]),
            f'<span class="al-chip">⏱ {format_duration(elapsed)}</span>',
            '<span class="al-chip{}">{}</span>'.format(
                " al-chip-live" if self._live else "",
                "● running" if self._live else "● idle"),
        ]
        self.bar.value = (
            '<div class="al-console-bar">'
            '<span class="al-console-dot" style="background:#ff5f57"></span>'
            '<span class="al-console-dot" style="background:#febc2e"></span>'
            '<span class="al-console-dot" style="background:#28c840"></span>'
            '<span class="al-console-name">Console</span>'
            '<span class="al-console-chips">{}</span>'
            "</div>"
        ).format("".join(chips))

        lines = self.buffer.lines(source=self.source_filter, limit=self.max_render_lines)
        if not lines:
            self.body.value = (
                '<div class="al-line"><span class="al-line-text" style="color:#64748b">'
                "Console ready. Seleccioná un proceso y apretá Run."
                "</span></div>"
            )
            return

        rendered = []   # type: List[str]
        if stats["dropped"]:
            rendered.append(
                '<div class="al-line"><span class="al-line-text" style="color:#64748b">'
                "… se descartaron {} líneas antiguas (buffer lleno)</span></div>".format(
                    stats["dropped"])
            )
        for line in lines:
            rendered.append(
                '<div class="al-line al-lv-{level}">'
                '<span class="al-line-time">{clock}</span>'
                '<span class="al-line-src">{source}</span>'
                '<span class="al-line-text">{text}</span>'
                "</div>".format(
                    level=esc(line.level), clock=esc(line.clock),
                    source=esc(line.source or "—"), text=esc(line.text) or "&nbsp;",
                )
            )
        # El ancla del final es lo que mantiene la vista pegada abajo mientras
        # llega salida nueva, sin necesidad de JavaScript.
        self.body.value = "".join(rendered) + '<div id="al-console-end"></div>'


def process_status_dot(state, running):
    # type: (Optional[str], bool) -> str
    """El punto de color a la izquierda del nombre del proceso.

    Reemplaza al icono ▶ que habia antes ahi, que era puramente decorativo
    -- no representaba nada del estado real. Gris tenue si el proceso todavia
    no corrio en esta sesion, ambar pulsando mientras corre, y el color del
    resultado (verde/ambar/rojo/gris) una vez que termina. Con una lista
    larga de procesos, este punto es lo que se escanea de un vistazo antes
    de leer ningun texto.
    """
    if running:
        return '<span class="al-proc-dot al-dot-running" title="Corriendo"></span>'
    if not state:
        return '<span class="al-proc-dot al-dot-idle" title="Sin corridas en esta sesión"></span>'
    return f'<span class="al-proc-dot al-dot-{esc(state)}" title="{esc(state)}"></span>'


def process_row(process, state=None, running=False):
    # type: (Any, Optional[str], bool) -> str
    """El bloque de texto de una fila de proceso (sin los botones)."""
    tags = "".join(
        f'<span class="al-proc-tag">{esc(tag)}</span>' for tag in process.tags[:4]
    )
    badge = ""
    if state:
        badge = f'<span class="al-proc-state al-st-{esc(state)}">{esc(state)}</span>'
    lock = ' <span title="Pide confirmación">🔒</span>' if process.requires_confirmation else ""
    dot = process_status_dot(state, running)
    return (
        '<div style="display:flex;align-items:center;gap:10px">'
        f'{dot}<div class="al-proc-name">{esc(process.name)}{lock}</div>{badge}</div>'
        f'<div class="al-proc-file">{esc(process.notebook)}</div>'
        f"{tags}"
    )


def process_info(process):
    # type: (Any) -> str
    """El panel que se despliega con el botón ⓘ."""
    parts = []      # type: List[str]
    if process.description:
        parts.append(f"<b>Qué hace:</b> {esc(process.description)}")
    if process.how_to_run:
        parts.append(f"<b>Cómo se corre:</b> {esc(process.how_to_run)}")
    if process.parameters:
        params = ", ".join(
            f"<code>{esc(k)}={esc(v)}</code>"
            for k, v in sorted(process.parameters.items())
        )
        parts.append(f"<b>Parámetros:</b> {params}")
    parts.append(
        f"<b>Notebook:</b> <code>{esc(process.notebook)}</code> · <b>Timeout:</b> {format_duration(process.timeout_seconds)}"
    )
    if process.requires_confirmation:
        parts.append("<b>Requiere confirmación</b> antes de ejecutarse.")
    if not process.description and not process.how_to_run:
        parts.insert(0, "<i>Este proceso no tiene descripción cargada en processes.json.</i>")
    return '<div class="al-proc-info">{}</div>'.format("<br>".join(parts))


def status_banner(message, tone="info"):
    # type: (str, str) -> str
    return f'<div class="al-status al-status-{esc(tone)}"><span class="al-dot"></span>{esc(message)}</div>'


def empty_state(message):
    # type: (str) -> str
    return f'<div class="al-empty">{esc(message)}</div>'
