"""Administracion de miembros del hub. Solo la ve el jefe del equipo.

Esta pantalla es la que hace que el modelo sea autoservicio: el jefe agrega o
saca gente sin abrir un ticket ni esperar a nadie. El siguiente login de esa
persona ya toma el cambio, porque los roles se derivan del ``members.json``
en cada arranque.

La escritura pasa por ``HubRepository.save_membership``, que vuelve a validar
el permiso, controla la concurrencia entre dos jefes editando a la vez, y no
deja que el hub se quede sin ningun jefe.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import ipywidgets as W

from ..core.authz import PermissionDenied
from ..core.models import ROLE_LEAD, normalize_sid
from ..core.repository import ConflictError
from . import widgets as ui

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import Any, List, Optional  # noqa: F401


class MembersView:
    """Lista de miembros con altas, bajas y cambio de rol."""

    def __init__(self, context, hub):
        # type: (Any, Any) -> None
        self.ctx = context
        self.hub = hub
        self.membership = None      # type: Optional[Any]

        self.status = ui.html_box("")
        self.list_box = W.VBox(layout=W.Layout(width="100%"))
        self.new_sid = W.Text(
            placeholder="usuario.nuevo",
            layout=W.Layout(width="220px", margin="0 8px 0 0"),
        )
        self.new_role = W.Dropdown(
            options=[("Miembro", "member"), ("Jefe", ROLE_LEAD)], value="member",
            layout=W.Layout(width="130px", margin="0 8px 0 0"),
        )
        self.add_button = ui.button("Agregar", ["al-btn-primary"], icon="plus")
        self.add_button.on_click(self._on_add)
        self.reload_button = ui.button("Recargar", icon="refresh")
        self.reload_button.on_click(lambda _b: self.reload())

        self.widget = W.VBox(
            [
                ui.html_box(
                    f'<div class="al-admin-note">Sos <b>jefe</b> de {ui.esc(self.hub.name)}. Lo que cambies acá se '
                    "guarda en <code>members.json</code> dentro de la carpeta del hub, y "
                    "aplica en el próximo ingreso de cada persona.<br>"
                    "El hub no puede quedarse sin jefe.</div>"
                ),
                W.HBox(
                    [self.new_sid, self.new_role, self.add_button, self.reload_button],
                    layout=W.Layout(align_items="center", margin="0 0 14px 0"),
                ),
                self.status,
                self.list_box,
            ],
            layout=W.Layout(width="100%", max_width="640px"),
        )
        self.reload()

    # -- datos ---------------------------------------------------------------

    def reload(self):
        # type: () -> None
        self.ctx.repo.refresh()
        try:
            self.membership = self.ctx.repo.get_membership(self.hub.id)
        except PermissionDenied as exc:
            self._say(str(exc), "error")
            return
        except Exception as exc:
            self._say(f"No se pudo leer members.json: {exc}", "error")
            return
        self._render()

    def _render(self):
        # type: () -> None
        membership = self.membership
        if membership is None:
            return
        rows = []   # type: List[Any]
        entries = (
            [(sid, ROLE_LEAD) for sid in membership.leads]
            + [(sid, "member") for sid in membership.members]
        )
        for sid, role in entries:
            rows.append(self._row(sid, role))
        if not rows:
            rows = [ui.html_box(ui.empty_state("El hub no tiene miembros cargados."))]
        rows.append(
            ui.html_box(
                '<div style="font-size:12px;color:#9aa7bf;margin-top:10px">'
                "revisión {} · última edición {} por {}</div>".format(
                    membership.revision,
                    ui.esc(membership.updated_at or "—"),
                    ui.esc(membership.updated_by or "—"),
                )
            )
        )
        self.list_box.children = rows

    def _row(self, sid, role):
        # type: (str, str) -> W.HBox
        is_lead = role == ROLE_LEAD
        is_self = sid == self.ctx.principal.sid
        # El wrapper con display:flex es necesario: este HTML entra como UN
        # hijo del HBox, asi que el flex del contenedor no alcanza a sus divs
        # internos y el avatar quedaria encima del nombre en vez de al lado.
        label = ui.html_box(
            '<div style="display:flex;align-items:center;gap:11px;width:100%">'
            '<div class="al-member-avatar">{initials}</div>'
            '<div style="flex:1"><span class="al-member-sid">{sid}</span>'
            '{you} <span class="al-role-tag al-role-{role}">{role}</span></div>'
            "</div>".format(
                initials=ui.esc(sid[:2].upper()), sid=ui.esc(sid),
                you=' <span style="color:#9aa7bf;font-size:12px">(vos)</span>' if is_self else "",
                role=ui.esc(role),
            )
        )
        toggle = ui.button(
            "Quitar jefatura" if is_lead else "Hacer jefe",
            tooltip=f"Cambiar el rol de {sid}",
        )
        toggle.on_click(lambda _b, s=sid, lead=is_lead: self._set_role(s, not lead))

        remove = ui.button("Sacar", ["al-btn-danger"], icon="times")
        remove.on_click(lambda _b, s=sid: self._remove(s))

        row = W.HBox(
            [label, W.Box(layout=W.Layout(flex="1")), toggle, remove],
            layout=W.Layout(align_items="center", width="100%"),
        )
        row.add_class("al-member")
        return row

    # -- acciones ------------------------------------------------------------

    def _on_add(self, _button=None):
        # type: (Any) -> None
        raw = self.new_sid.value.strip()
        if not raw:
            self._say("Escribí un usuario para agregar.", "error")
            return
        try:
            sid = normalize_sid(raw)
        except ValueError:
            self._say(f"“{raw}” no es un usuario válido.", "error")
            return
        membership = self.membership
        if membership is None:
            return
        if sid in membership.everyone:
            self._say(f"{sid} ya está en el hub.", "error")
            return

        leads = list(membership.leads)
        members = list(membership.members)
        (leads if self.new_role.value == ROLE_LEAD else members).append(sid)
        if self._save(leads, members, f"Se agregó {sid}."):
            self.new_sid.value = ""

    def _set_role(self, sid, make_lead):
        # type: (str, bool) -> None
        membership = self.membership
        if membership is None:
            return
        leads = [s for s in membership.leads if s != sid]
        members = [s for s in membership.members if s != sid]
        if make_lead:
            leads.append(sid)
        else:
            members.append(sid)
        self._save(
            leads, members,
            "{} ahora es {}.".format(sid, "jefe" if make_lead else "miembro"),
        )

    def _remove(self, sid):
        # type: (str) -> None
        membership = self.membership
        if membership is None:
            return
        leads = [s for s in membership.leads if s != sid]
        members = [s for s in membership.members if s != sid]
        self._save(leads, members, f"Se sacó a {sid} del hub.")

    def _save(self, leads, members, success_message):
        # type: (List[str], List[str], str) -> bool
        membership = self.membership
        expected = membership.revision if membership else None
        try:
            self.membership = self.ctx.repo.save_membership(
                self.hub.id, leads, members, expected_revision=expected
            )
        except ValueError as exc:
            # El caso tipico: sacar al ultimo jefe. Vale la pena que el
            # mensaje explique por que, no solo que no se pudo.
            self._say(str(exc), "error")
            return False
        except ConflictError as exc:
            self._say(str(exc), "error")
            self.reload()
            return False
        except PermissionDenied as exc:
            self._say(str(exc), "error")
            return False
        except Exception as exc:
            self._say(f"No se pudo guardar: {exc}", "error")
            return False

        self._say(success_message, "ok")
        self._render()
        # Si el jefe se cambio el rol a si mismo, la sesion actual quedo
        # desactualizada y hay que reflejarlo sin obligar a volver a entrar.
        self.ctx.refresh_principal()
        return True

    def _say(self, message, tone):
        # type: (str, str) -> None
        self.status.value = ui.status_banner(message, tone)
