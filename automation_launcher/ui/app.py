"""Punto de entrada de la interfaz: arma el contexto y enruta las pantallas.

Flujo: login → (selector de hub, si pertenece a varios) → control room, con
los tabs de miembros y métricas apareciendo solo si el usuario es jefe de ese
hub.

Este modulo es todo lo que ejecuta ``app.ipynb``. El notebook queda de cinco
lineas, que es el punto: la logica vive en archivos ``.py`` que git puede
comparar, pytest puede probar y una persona puede revisar en un pull request.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import ipywidgets as W
from IPython.display import HTML, display

from ..core import authz, contents
from ..core.auth import build_auth
from ..core.config import load_config
from ..core.console import ConsoleBuffer
from ..core.engine import RunManager
from ..core.history import AuditLog, RunHistory
from ..core.repository import HubRepository, build_principal
from . import theme
from . import widgets as ui
from .dashboard import DashboardView
from .login import LoginView
from .members import MembersView
from .metrics_tab import MetricsView

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import Any, List, Optional  # noqa: F401


class AppContext:
    """El estado compartido de la sesion.

    Se pasa a las vistas en lugar de una decena de parametros sueltos, y es el
    unico lugar donde vive la credencial del usuario.
    """

    def __init__(self, config):
        # type: (Any) -> None
        self.config = config
        self.policy = authz.policy
        self.client = contents.build_client(config)
        self.audit = AuditLog(
            config.get("AUDIT_LOG_PATH") or os.path.join("runs", "audit.jsonl")
        )
        self.buffer = ConsoleBuffer(config.get("CONSOLE_MAX_LINES"))
        self.manager = RunManager(
            config, buffer=self.buffer, on_finished=self._record_run
        )
        self.hubs_root = contents.join(config.get("CONTENTS_DIR"), config.get("HUBS_DIR"))
        self.history = RunHistory(
            self.client, self.hubs_root,
            on_error=lambda msg: self.buffer.append(msg, level="warn"),
        )
        self.principal = None       # type: Optional[Any]
        self.credentials = None     # type: Optional[Any]
        self.repo = None            # type: Optional[Any]

    # -- sesion --------------------------------------------------------------

    def sign_in(self, credentials):
        # type: (Any) -> Any
        self.credentials = credentials
        self.refresh_principal()
        return self.principal

    def refresh_principal(self):
        # type: () -> None
        """Relee la pertenencia desde el share y rearma el repositorio."""
        sid = self.credentials.sid if self.credentials else ""
        self.client.clear_cache()
        self.principal = build_principal(sid, self.client, self.config, audit=self.audit)
        self.repo = HubRepository(
            self.principal, self.client, self.config,
            policy=self.policy, audit=self.audit,
        )

    def sign_out(self):
        # type: () -> None
        """Cierra la sesion y borra el secreto de memoria.

        El ``redactor.forget()`` importa: si quedara recordando la contrasena
        de quien se fue, la proxima sesion enmascararia texto por un secreto
        que ya no es de nadie.
        """
        from ..core.secrets import redactor

        self.manager.stop_all()
        self.credentials = None
        self.principal = None
        self.repo = None
        redactor.forget()
        self.buffer.clear()

    # -- lectura de notebooks -------------------------------------------------

    def read_notebook(self, hub, process):
        # type: (Any, Any) -> str
        """Lee el notebook de un proceso desde el share.

        Una ruta relativa se resuelve dentro de la carpeta del hub; una que
        empiece con "/" se toma como absoluta dentro del share. ``contents.join``
        rechaza cualquier ".." en el camino, asi que un ``processes.json``
        editado a mano no puede apuntar fuera del share.
        """
        notebook = process.notebook
        if notebook.startswith("/"):
            path = contents.join(notebook)
        else:
            path = contents.join(self.hubs_root, hub.path, notebook)
        return self.client.read_text(path)

    # -- historial ------------------------------------------------------------

    def _record_run(self, handle):
        # type: (Any) -> None
        if self.repo is None:
            return
        try:
            hub = self.repo.get_hub(handle.hub_id)
        except Exception:
            return
        self.history.append(hub.path, handle.to_record())


class LauncherApp:
    """Arma la aplicacion y controla que pantalla se ve."""

    def __init__(self, config_path=None, overrides=None):
        # type: (Optional[str], Optional[dict]) -> None
        self.config = load_config(config_path)
        if overrides:
            merged = self.config.as_dict()
            merged.update(overrides)
            from ..core.config import LauncherConfig, validate

            values, problems = validate(merged)
            self.config = LauncherConfig(
                values, source=self.config.source or "<overrides>",
                problems=self.config.problems + problems,
            )
        self.ctx = AppContext(self.config)
        self.auth = build_auth(self.config)
        self.root = W.VBox(layout=W.Layout(width="100%"))
        self.container = W.VBox(layout=W.Layout(width="100%"))
        self.container.add_class("al-app")
        self._dashboard = None      # type: Optional[DashboardView]

    # -- ciclo ----------------------------------------------------------------

    def start(self):
        # type: () -> W.VBox
        display(HTML(theme.css()))
        self.ctx.buffer.append(
            f"Consola lista. {self.config.status_line()}", level="system"
        )
        for problem in self.config.problems:
            self.ctx.buffer.append(f"Config: {problem}", level="warn")
        self.root.children = [ui.topbar(self.config.get("ORG_NAME")), self.container]
        self._show_login()
        return self.root

    def _show_login(self):
        # type: () -> None
        self._close_dashboard()
        view = LoginView(
            self.config, self.auth, self._on_login,
            demo_users=self.config.get("DEMO_USERS"),
        )
        self.container.children = [view.widget]

    def _on_login(self, result):
        # type: (Any) -> None
        principal = self.ctx.sign_in(result.credentials)
        hubs = self.ctx.repo.list_hubs()
        if not hubs:
            self._show_no_hubs(principal)
        elif len(hubs) == 1 or not self.config.get("SHOW_HUB_PICKER"):
            self._show_hub(hubs[0], allow_switch=len(hubs) > 1)
        else:
            self._show_hub_picker(hubs)

    def _show_no_hubs(self, principal):
        # type: (Any) -> None
        """Cuando alguien entra pero no pertenece a ningun hub.

        Se explica que hacer en vez de mostrar una pantalla vacia: el usuario
        no tiene forma de saber que la solucion es pedirle acceso a un jefe.
        """
        back = ui.button("Volver", ["al-btn-primary"])
        back.on_click(lambda _b: self._sign_out())
        self.container.children = [
            W.VBox(
                [
                    ui.html_box(
                        '<div class="al-empty" style="max-width:560px;margin:60px auto 16px">'
                        "<div style='font-size:34px;margin-bottom:10px'>🔑</div>"
                        f"<b>{ui.esc(principal.sid)}</b> no pertenece a ningún hub todavía.<br><br>"
                        "Los equipos se administran desde el propio launcher: pedile al "
                        "jefe de tu equipo que te agregue y volvé a entrar."
                        "</div>"
                    ),
                    W.Box([back], layout=W.Layout(justify_content="center")),
                ]
            )
        ]

    def _show_hub_picker(self, hubs):
        # type: (List[Any]) -> None
        cards = []      # type: List[Any]
        for hub in hubs:
            role = self.ctx.principal.role_in(hub.id) or ""
            # El wrapper flex es necesario: este HTML entra como un solo hijo
            # del HBox, asi que sin el la etiqueta de rol caeria debajo del
            # nombre en vez de quedar a su derecha.
            label = ui.html_box(
                '<div style="display:flex;align-items:center;gap:12px;width:100%">'
                '<div style="flex:1"><div class="al-proc-name">{name}</div>'
                '<div style="color:#6b7a99;font-size:12.5px;margin-top:3px">{desc}</div></div>'
                '<span class="al-role-tag al-role-{role}">{role}</span>'
                "</div>".format(
                    name=ui.esc(hub.name),
                    desc=ui.esc(hub.description or hub.id),
                    role=ui.esc(role),
                )
            )
            enter = ui.button("Entrar", ["al-btn-primary"])
            enter.on_click(lambda _b, h=hub: self._show_hub(h, allow_switch=True))
            row = W.HBox([label, enter], layout=W.Layout(align_items="center", width="100%"))
            row.add_class("al-proc")
            cards.append(row)

        signout = ui.button("Sign Out")
        signout.on_click(lambda _b: self._sign_out())
        self.container.children = [
            W.VBox(
                [
                    W.HBox(
                        [
                            ui.html_box(
                                '<div><div class="al-header-title">Tus hubs</div>'
                                f'<div class="al-header-sub">Pertenecés a {len(hubs)} equipos. '
                                "Elegí con cuál trabajar.</div></div>"
                            ),
                            W.Box(layout=W.Layout(flex="1")),
                            signout,
                        ],
                        layout=W.Layout(align_items="center", width="100%"),
                    )
                ]
                + cards,
                layout=W.Layout(max_width="700px", margin="40px auto"),
            )
        ]

    def _show_hub(self, hub, allow_switch=False):
        # type: (Any, bool) -> None
        self._close_dashboard()
        hubs = self.ctx.repo.list_hubs()
        switcher = (lambda: self._show_hub_picker(hubs)) if allow_switch else None
        dashboard = DashboardView(self.ctx, hub, self._sign_out, switcher)
        self._dashboard = dashboard

        # Los tabs de jefe se construyen solo si la politica lo autoriza. No
        # es solo cosmetica: si no se construyen, no existen widgets que un
        # navegador manipulado pueda accionar.
        tabs = [("Procesos", dashboard.widget)]
        if self.ctx.policy.can_manage_members(self.ctx.principal, hub.id):
            tabs.append(("Miembros", MembersView(self.ctx, hub).widget))
        if self.ctx.policy.can_view_metrics(self.ctx.principal, hub.id):
            tabs.append(("Métricas", MetricsView(self.ctx, hub).widget))

        if len(tabs) == 1:
            self.container.children = [dashboard.widget]
            return
        tab_widget = W.Tab([child for _title, child in tabs])
        for index, (title, _child) in enumerate(tabs):
            tab_widget.set_title(index, title)
        tab_widget.add_class("al-tabs")
        self.container.children = [tab_widget]

    def _sign_out(self):
        # type: () -> None
        self._close_dashboard()
        self.ctx.sign_out()
        self._show_login()

    def _close_dashboard(self):
        # type: () -> None
        if self._dashboard is not None:
            self._dashboard.close()
            self._dashboard = None


def run(config_path=None, **overrides):
    # type: (Optional[str], **Any) -> None
    """Construye y muestra la aplicacion. Es lo que llama ``app.ipynb``.

    Devuelve ``None`` a proposito. Jupyter muestra automaticamente el valor de
    la ultima expresion de una celda: si esto devolviera el widget, la celda
    ``run()`` lo dibujaria una segunda vez y la pagina saldria duplicada.
    """
    if config_path is None:
        for candidate in ("launcher_config.py", os.path.join("..", "launcher_config.py")):
            if os.path.isfile(candidate):
                config_path = candidate
                break
    app = LauncherApp(config_path, overrides or None)
    display(app.start())
