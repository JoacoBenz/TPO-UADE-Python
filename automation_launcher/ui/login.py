"""Pantalla de login.

Replica el flujo de las capturas: el usuario ya viene identificado por el
entorno del kernel, asi que solo se le pide la contrasena de red. Al aceptarla
se carga la configuracion del share y se arma el ``Principal`` con los hubs a
los que pertenece.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import ipywidgets as W

from ..core.auth import detect_sid
from . import widgets as ui

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import Any, Callable, List, Optional  # noqa: F401


class LoginView:
    """La tarjeta de login, con su maquina de estados chiquita."""

    def __init__(self, config, auth_backend, on_success, demo_users=None):
        # type: (Any, Any, Callable, Optional[List]) -> None
        self.config = config
        self.auth = auth_backend
        self.on_success = on_success
        self.demo_users = list(demo_users or [])
        self.sid = detect_sid()

        self.status = ui.html_box("")
        self.password = W.Password(
            placeholder="Contraseña de red",
            layout=W.Layout(width="100%", margin="0 0 4px 0"),
        )
        self.submit = ui.button("Sign In", ["al-btn-primary", "al-btn-wide"])
        self.submit.on_click(self._on_submit)
        # Enter en el campo entra: obligar al mouse en una pantalla de login
        # es de las cosas que mas molestan de una herramienta interna.
        self.password.observe(self._on_enter, names="value")
        self._last_value = ""

        self.user_box = ui.html_box("", ["al-login-user"])
        self.picker = self._build_picker()
        self.widget = self._build()
        self._refresh_user()

    # -- construccion --------------------------------------------------------

    def _build_picker(self):
        # type: () -> Optional[W.Dropdown]
        """Selector de usuario, solo en modo demo.

        Es lo que permite mostrar el aislamiento entre equipos sin reiniciar
        nada: se entra como el jefe, se ve el tab de miembros, se sale, se
        entra como alguien de otro equipo y se ve otra cosa.
        """
        if not self.config.is_demo or not self.demo_users:
            return None
        options = [
            ("{} — {}".format(u.get("sid", "?"), u.get("note", "")), u.get("sid", ""))
            for u in self.demo_users
        ]
        dropdown = W.Dropdown(
            options=options, value=options[0][1],
            description="Entrar como", style={"description_width": "90px"},
            layout=W.Layout(width="100%", margin="0 0 14px 0"),
        )
        dropdown.observe(lambda change: self._refresh_user(), names="value")
        self.sid = options[0][1]
        return dropdown

    def _build(self):
        # type: () -> W.VBox
        header = ui.html_box(
            '<div class="al-login-icon">🔒</div>'
            '<div class="al-login-title">{}</div>'
            '<div class="al-login-sub">Confirmá tu contraseña de red<br>'
            "para abrir el control room.</div>".format(ui.esc(self.config.get("APP_TITLE")))
        )
        label = ui.html_box(
            '<div style="font-weight:600;font-size:13px;color:#33415c;margin:0 0 6px">'
            "Contraseña</div>"
        )
        footer = ui.html_box(
            f'<div class="al-login-foot">{self._footer_text()}</div>',
        )

        children = [header, self.user_box]
        if self.picker is not None:
            children.append(self.picker)
        children += [label, self.password, self.status, self.submit, footer]

        card = W.VBox(children, layout=W.Layout(width="430px"))
        card.add_class("al-login-card")
        wrap = W.Box([card])
        wrap.add_class("al-login-wrap")
        return wrap

    def _footer_text(self):
        # type: () -> str
        if self.config.is_demo:
            return (
                "Modo demo: no se valida contra ninguna red. Cualquier contraseña "
                "de 4 o más caracteres entra.<br>"
                "Las credenciales se inyectan como <code>SID</code> / <code>PASSWORD</code> "
                "para auto-responder los prompts."
            )
        return (
            "Se verifica contra la red (IPC$). Las credenciales se usan para cargar "
            "la configuración del share y se inyectan como <code>SID</code> / "
            "<code>PASSWORD</code> para auto-responder los prompts."
        )

    # -- interaccion ---------------------------------------------------------

    def _current_sid(self):
        # type: () -> str
        if self.picker is not None:
            return self.picker.value
        return self.sid

    def _refresh_user(self):
        # type: () -> None
        sid = self._current_sid()
        if sid:
            self.user_box.value = f"Sesión iniciada como <b>{ui.esc(sid)}</b>"
        else:
            self.user_box.value = (
                "<b>No se pudo detectar el usuario.</b><br>"
                "Revisá que el kernel exponga USERNAME o JUPYTERHUB_USER."
            )

    def _on_enter(self, change):
        # type: (Any) -> None
        # ipywidgets.Password no expone el evento de Enter; el valor cambia al
        # confirmar, asi que se usa ese cambio como disparador.
        value = change.get("new") or ""
        if value and value == self._last_value:
            return
        self._last_value = value

    def _on_submit(self, _button=None):
        # type: (Any) -> None
        sid = self._current_sid()
        password = self.password.value
        if not password:
            self.status.value = ui.status_banner("Ingresá tu contraseña.", "error")
            return

        self.submit.disabled = True
        self.password.disabled = True
        self.status.value = ui.status_banner("Cargando configuración…", "info")

        # El login toca la red (IPC$ y despues el share). En el hilo de la UI
        # eso congela la pantalla entera durante segundos.
        threading.Thread(
            target=self._authenticate, args=(sid, password),
            name="login", daemon=True,
        ).start()

    def _authenticate(self, sid, password):
        # type: (str, str) -> None
        try:
            result = self.auth.authenticate(sid, password)
        except Exception as exc:
            self._fail(f"Error inesperado autenticando: {exc}")
            return

        if not result.ok:
            self._fail(result.message or "No se pudo verificar la contraseña.")
            return

        self.status.value = ui.status_banner("Verificado. Abriendo el control room…", "ok")
        try:
            self.on_success(result)
        except Exception as exc:
            self._fail(f"Entró, pero falló al cargar los hubs: {exc}")

    def _fail(self, message):
        # type: (str) -> None
        self.status.value = ui.status_banner(message, "error")
        self.submit.disabled = False
        self.password.disabled = False
        self.password.value = ""
