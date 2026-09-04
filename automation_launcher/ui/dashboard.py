"""El control room: procesos a la izquierda, consola en vivo a la derecha.

Todo lo que se muestra pasa por el repositorio, que ya viene acotado al
principal de la sesion. Esta capa no filtra por permisos: si algo llego hasta
aca, es porque la politica lo autorizo. Los unicos chequeos que hace son para
decidir que botones dibujar, y aun asi el motor vuelve a validar antes de
ejecutar.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import ipywidgets as W

from ..core.authz import PermissionDenied
from ..core.contents import ContentsError
from . import widgets as ui

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import Any, Callable, Dict, List, Optional  # noqa: F401


class ProcessCard:
    """Una fila de la lista: descripcion, boton ⓘ y boton Run."""

    def __init__(self, process, on_run, on_toggle_info, can_run=True):
        # type: (Any, Callable, Callable, bool) -> None
        self.process = process
        self.on_run = on_run
        self.expanded = False
        self.state = None       # type: Optional[str]
        self.running = False

        self.text = ui.html_box("")
        self.info_button = ui.button("", ["al-btn-icon"], icon="info", tooltip="Qué hace y cómo se corre")
        self.info_button.on_click(lambda _b: on_toggle_info(self))
        #: Si la politica permite ejecutar. Se guarda porque `disabled` cambia
        #: mientras corre, y sin este dato no se sabria si volver a habilitar
        #: el boton al terminar o dejarlo bloqueado por falta de permiso.
        self.can_run = can_run
        self.run_button = ui.button("Run", ["al-btn-primary", "al-btn-run"], icon="play")
        self.run_button.on_click(self._clicked)
        self.run_button.disabled = not can_run

        self.info_panel = ui.html_box("")
        self.info_panel.layout.display = "none"

        row = W.HBox(
            [
                ui.html_box('<div class="al-proc-play">▶</div>'),
                W.Box([self.text], layout=W.Layout(flex="1", overflow="hidden")),
                self.info_button,
                self.run_button,
            ],
            layout=W.Layout(align_items="center", width="100%"),
        )
        self.widget = W.VBox([row, self.info_panel], layout=W.Layout(width="100%"))
        self.widget.add_class("al-proc")
        self.refresh()

    def _clicked(self, _button=None):
        # type: (Any) -> None
        self.on_run(self.process)

    def toggle_info(self):
        # type: () -> None
        self.expanded = not self.expanded
        if self.expanded:
            self.info_panel.value = ui.process_info(self.process)
            self.info_panel.layout.display = "block"
        else:
            self.info_panel.layout.display = "none"

    def set_state(self, state, running):
        # type: (Optional[str], bool) -> None
        if state == self.state and running == self.running:
            return
        self.state = state
        self.running = running
        self.refresh()

    def refresh(self):
        # type: () -> None
        self.text.value = ui.process_row(self.process, self.state, self.running)
        if self.can_run:
            self.run_button.description = "Corriendo" if self.running else "Run"
            self.run_button.disabled = self.running


class DashboardView:
    """La pantalla principal de un hub."""

    def __init__(self, context, hub, on_sign_out, on_switch_hub=None):
        # type: (Any, Any, Callable, Optional[Callable]) -> None
        self.ctx = context
        self.hub = hub
        self.on_sign_out = on_sign_out
        self.on_switch_hub = on_switch_hub
        self.processes = []     # type: List[Any]
        self.cards = {}         # type: Dict[str, ProcessCard]
        self._pending_confirm = None    # type: Optional[Any]

        self.console = ui.ConsoleView(
            context.buffer,
            refresh_ms=int(context.config.get("CONSOLE_REFRESH_MS") or 200),
        )
        self.stats_box = ui.html_box("")
        self.list_box = W.VBox(layout=W.Layout(width="100%"))
        self.hint = ui.html_box(
            '<div class="al-console-hint">Tocá el ⓘ de un proceso para ver qué hace '
            "y cómo se corre (tocalo de nuevo para ocultarlo).</div>"
        )
        self.confirm_box = W.VBox(layout=W.Layout(display="none", width="100%"))
        self.search = W.Text(
            placeholder="Buscar…",
            layout=W.Layout(width="220px", margin="0 8px 0 0"),
        )
        self.search.observe(lambda _c: self._render_list(), names="value")

        self.refresh_button = ui.button("Refresh", tooltip="Volver a leer el share")
        self.clear_button = ui.button("Clear", tooltip="Limpiar la consola")
        self.stop_button = ui.button("Stop", ["al-btn-danger"], tooltip="Cortar lo que esté corriendo")
        self.signout_button = ui.button("Sign Out")
        self.refresh_button.on_click(lambda _b: self.reload())
        self.clear_button.on_click(lambda _b: self._clear_console())
        self.stop_button.on_click(lambda _b: self._stop_all())
        self.signout_button.on_click(lambda _b: self.on_sign_out())

        self.widget = self._build()
        self.console.start()
        self._start_ticker()
        self.reload()

    # -- construccion --------------------------------------------------------

    def _build(self):
        # type: () -> W.VBox
        principal = self.ctx.principal
        role = principal.role_in(self.hub.id) or ""
        pill = ui.html_box(
            f'<div class="al-user-pill"><span class="al-live"></span>{ui.esc(principal.display_name)}'
            f'<span class="al-user-role">{ui.esc(role)}</span></div>'
        )
        header_left = W.HBox(
            [
                ui.html_box('<div class="al-header-icon">⌘</div>'),
                ui.html_box(
                    '<div><div class="al-header-title">{}</div>'
                    '<div class="al-header-sub">{}</div></div>'.format(
                        ui.esc(self.ctx.config.get("APP_TITLE")),
                        ui.esc(self.hub.name))
                ),
            ],
            layout=W.Layout(align_items="center"),
        )
        controls = [pill, self.search, self.refresh_button, self.clear_button,
                    self.stop_button, self.signout_button]
        if self.on_switch_hub is not None:
            switch = ui.button("Cambiar hub", tooltip="Ir a otro equipo")
            switch.on_click(lambda _b: self.on_switch_hub())
            controls.insert(1, switch)

        header = W.HBox(
            [header_left, W.Box(layout=W.Layout(flex="1")),
             W.HBox(controls, layout=W.Layout(align_items="center"))],
            layout=W.Layout(align_items="center", width="100%"),
        )
        header.add_class("al-header")

        left = W.VBox(
            [ui.html_box('<div class="al-section-title">Procesos</div>'),
             self.confirm_box, self.list_box],
            layout=W.Layout(width="38%", min_width="330px", margin="0 20px 0 0"),
        )
        right = W.VBox(
            [ui.html_box('<div class="al-section-title">Consola en vivo</div>'),
             self.hint, self.console.widget],
            layout=W.Layout(flex="1"),
        )
        body = W.HBox([left, right], layout=W.Layout(width="100%", align_items="flex-start"))
        return W.VBox([header, self.stats_box, body], layout=W.Layout(width="100%"))

    # -- datos ---------------------------------------------------------------

    def reload(self):
        # type: () -> None
        """Relee el share. Es lo que hace el boton Refresh."""
        self.ctx.repo.refresh()
        try:
            self.processes = self.ctx.repo.list_processes(self.hub.id)
        except PermissionDenied as exc:
            self.processes = []
            self.ctx.buffer.append(f"Acceso denegado: {exc}", level="error")
        except ContentsError as exc:
            self.processes = []
            self.ctx.buffer.append(f"No se pudo leer el share: {exc}", level="error")
        self.cards = {}
        self._render_list()
        self._render_stats()

    def _render_list(self):
        # type: () -> None
        query = self.search.value.strip()
        visible = [p for p in self.processes if p.matches(query)]
        if not visible:
            message = (
                f"Ningún proceso coincide con “{query}”." if query
                else "Este hub todavía no tiene automatizaciones cargadas."
            )
            self.list_box.children = [ui.html_box(ui.empty_state(message))]
            return

        can_run = self.ctx.policy.can_run(self.ctx.principal, self.hub.id)
        children = []   # type: List[Any]
        for process in visible:
            card = self.cards.get(process.id)
            if card is None:
                card = ProcessCard(process, self._request_run, self._toggle_info, can_run)
                self.cards[process.id] = card
            children.append(card.widget)
        self.list_box.children = children

    def _render_stats(self):
        # type: () -> None
        counts = self.ctx.manager.stats(self.hub.id)
        active = self.ctx.manager.active_runs(self.hub.id)
        elapsed = max((r.elapsed for r in active), default=0.0)
        if not active:
            finished = [r for r in self.ctx.manager.runs(self.hub.id) if not r.is_active]
            elapsed = finished[0].elapsed if finished else 0.0
        self.stats_box.value = (
            '<div class="al-stats">{}{}{}{}{}</div>'.format(
                ui.stat_card(len(self.processes), "Procesos", "primary"),
                ui.stat_card(counts["running"], "Corriendo", "warn"),
                ui.stat_card(counts["completed"], "Completados", "ok"),
                ui.stat_card(counts["failed"], "Fallados", "error"),
                ui.stat_card(ui.format_duration(elapsed), "Última / en vivo", "primary", mono=True),
            )
        )
        self.stop_button.disabled = not active
        self.console.set_live(bool(active), active[-1].started_at if active else 0.0)

    # -- acciones ------------------------------------------------------------

    def _toggle_info(self, card):
        # type: (ProcessCard) -> None
        card.toggle_info()

    def _request_run(self, process):
        # type: (Any) -> None
        """Corre el proceso, pidiendo confirmacion si el proceso lo exige.

        La confirmacion no es un adorno: estos procesos suben instrucciones de
        settlement a sistemas reales, y un Run apretado sin querer cuesta caro.
        """
        if process.requires_confirmation:
            self._show_confirm(process)
        else:
            self._launch(process)

    def _show_confirm(self, process):
        # type: (Any) -> None
        message = ui.html_box(
            f'<div class="al-admin-note"><b>{ui.esc(process.name)}</b> requiere confirmación porque '
            "escribe en sistemas de producción.<br>¿Lo corrés igual?</div>"
        )
        yes = ui.button("Sí, correr", ["al-btn-primary"])
        no = ui.button("Cancelar")

        def accept(_b=None):
            self.confirm_box.layout.display = "none"
            self._launch(process)

        def reject(_b=None):
            self.confirm_box.layout.display = "none"

        yes.on_click(accept)
        no.on_click(reject)
        self.confirm_box.children = [message, W.HBox([yes, no])]
        self.confirm_box.layout.display = "block"

    def _launch(self, process):
        # type: (Any) -> None
        try:
            # Ultima validacion antes de ejecutar. La UI ya decidio mostrar el
            # boton, pero esa decision no es la que manda.
            self.ctx.repo.authorize_run(self.hub.id, process)
        except PermissionDenied as exc:
            self.ctx.buffer.append(f"Denegado: {exc}", level="error", source=process.id)
            return

        try:
            source = self.ctx.read_notebook(self.hub, process)
        except ContentsError as exc:
            self.ctx.buffer.append(
                f"No se pudo leer el notebook {process.notebook}: {exc}",
                level="error", source=process.id,
            )
            return

        self.ctx.manager.start(
            process, self.hub.id, self.ctx.principal.sid, source, self.ctx.credentials
        )
        self._render_stats()

    def _stop_all(self):
        # type: () -> None
        stopped = self.ctx.manager.stop_all(self.hub.id)
        if not stopped:
            self.ctx.buffer.append("No hay nada corriendo.", level="system")

    def _clear_console(self):
        # type: () -> None
        self.ctx.buffer.clear()
        self.ctx.buffer.append(
            f"Consola lista. {self.ctx.config.status_line()}", level="system"
        )

    # -- refresco periodico ---------------------------------------------------

    def _start_ticker(self):
        # type: () -> None
        """Mantiene vivos los contadores y el estado de cada tarjeta.

        Un solo hilo para toda la pantalla, a un ritmo fijo: si cada tarjeta
        tuviera el suyo, veinte procesos serian veinte hilos peleando por
        actualizar la misma interfaz.
        """
        def loop():
            while not self._stop_ticker.is_set():
                time.sleep(0.5)
                try:
                    self._tick()
                except Exception:
                    pass

        self._stop_ticker = threading.Event()
        threading.Thread(target=loop, name="dashboard-ticker", daemon=True).start()

    def _tick(self):
        # type: () -> None
        by_process = {}     # type: Dict[str, Any]
        for run in self.ctx.manager.runs(self.hub.id):
            if run.process.id not in by_process:
                by_process[run.process.id] = run
        for process_id, card in self.cards.items():
            run = by_process.get(process_id)
            card.set_state(run.state if run else None, bool(run and run.is_active))
        self._render_stats()

    def close(self):
        # type: () -> None
        self.console.stop()
        stopper = getattr(self, "_stop_ticker", None)
        if stopper is not None:
            stopper.set()
