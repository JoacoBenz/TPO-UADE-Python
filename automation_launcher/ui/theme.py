"""Estilos de la interfaz.

Todo el CSS del launcher vive aca, en un solo string. La alternativa -- ir
poniendo estilos inline en cada widget -- termina en una interfaz donde cada
pantalla se ve un poco distinta y cambiar un color implica buscarlo en seis
archivos.

Los colores estan definidos como variables CSS al principio: para cambiar la
identidad visual entera alcanza con tocar ese bloque.
"""

from __future__ import annotations

#: Paleta y medidas. Un solo lugar para ajustar la marca.
TOKENS = """
:root {
  --al-bg-from:      #f7f9fc;
  --al-bg-to:        #eaf0fa;
  --al-surface:      #ffffff;
  --al-surface-alt:  #f4f7fd;
  --al-border:       #e4e9f2;
  --al-text:         #16203a;
  --al-text-soft:    #6b7a99;
  --al-text-faint:   #9aa7bf;

  --al-primary:      #2f6fed;
  --al-primary-dark: #1f56c9;
  --al-primary-soft: #eaf1ff;

  --al-ok:           #16a34a;
  --al-warn:         #d97706;
  --al-error:        #dc2626;
  --al-error-soft:   #fdecec;

  --al-console-bg:   #0f1520;
  --al-console-bar:  #1b2434;
  --al-console-text: #cbd5e1;
  --al-console-dim:  #64748b;

  --al-radius:       14px;
  --al-radius-sm:    10px;
  --al-shadow:       0 1px 2px rgba(16,32,64,.04), 0 8px 24px rgba(16,32,64,.06);
  --al-shadow-lg:    0 10px 40px rgba(16,32,64,.10);
  --al-font:         -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                     "Helvetica Neue", Arial, sans-serif;
  --al-mono:         "SF Mono", ui-monospace, "Cascadia Mono", Menlo, Consolas,
                     "Liberation Mono", monospace;
}
"""

BASE = """
/* Voila deja margenes y fondos propios: se neutralizan para que la app ocupe
   toda la pantalla como una aplicacion y no como un notebook renderizado. */
body, .jp-Notebook, #rendered_cells {
  background: linear-gradient(160deg, var(--al-bg-from) 0%, var(--al-bg-to) 100%) !important;
  font-family: var(--al-font) !important;
  color: var(--al-text);
}
#rendered_cells, .jp-Cell, .jp-Notebook { padding: 0 !important; margin: 0 !important; }
.jp-OutputArea-output { padding: 0 !important; background: transparent !important; }
.jp-RenderedHTMLCommon { font-size: 14px; }
.jp-RenderedHTMLCommon p { margin: 0; }

.al-app { max-width: 1500px; margin: 0 auto; padding: 0 22px 40px; }

/* --- barra institucional superior ------------------------------------- */
.al-topbar {
  background: #101317; color: #fff; height: 52px; display: flex;
  align-items: center; padding: 0 24px; gap: 14px;
  margin: 0 -22px 26px; font-size: 15px;
}
.al-topbar .al-org { font-weight: 600; letter-spacing: .2px; font-size: 17px; }
.al-topbar .al-spacer { flex: 1; }
.al-topbar .al-badge {
  width: 26px; height: 26px; border-radius: 50%; background: #2b3542;
  display: flex; align-items: center; justify-content: center; font-size: 13px;
}

/* --- tarjetas ---------------------------------------------------------- */
.al-card {
  background: var(--al-surface); border: 1px solid var(--al-border);
  border-radius: var(--al-radius); box-shadow: var(--al-shadow);
}
.al-section-title {
  font-size: 11px; font-weight: 700; letter-spacing: .09em; text-transform: uppercase;
  color: var(--al-text-faint); margin: 4px 0 10px;
}

/* --- botones ----------------------------------------------------------- */
.widget-button.al-btn {
  border-radius: 999px !important; border: 1px solid var(--al-border) !important;
  background: var(--al-surface) !important; color: var(--al-text) !important;
  font-family: var(--al-font) !important; font-weight: 600 !important;
  font-size: 13px !important; box-shadow: none !important; height: 36px !important;
  transition: background .12s, border-color .12s, transform .06s;
}
.widget-button.al-btn:hover:enabled {
  background: var(--al-surface-alt) !important; border-color: #cfd9ea !important;
}
.widget-button.al-btn:active:enabled { transform: translateY(1px); }
.widget-button.al-btn-primary {
  background: var(--al-primary) !important; border-color: var(--al-primary) !important;
  color: #fff !important;
}
.widget-button.al-btn-primary:hover:enabled {
  background: var(--al-primary-dark) !important; border-color: var(--al-primary-dark) !important;
}
.widget-button.al-btn-danger { color: var(--al-error) !important; }
.widget-button.al-btn-danger:hover:enabled {
  background: var(--al-error-soft) !important; border-color: #f3c9c9 !important;
}
.widget-button.al-btn:disabled { opacity: .45 !important; cursor: not-allowed !important; }
.widget-button.al-btn-run { min-width: 96px !important; }
.widget-button.al-btn-icon {
  width: 34px !important; min-width: 34px !important; height: 34px !important;
  border-radius: 50% !important; font-size: 13px !important; padding: 0 !important;
}
.widget-button.al-btn-wide { width: 100% !important; height: 44px !important; font-size: 15px !important; }

/* --- campos de texto --------------------------------------------------- */
.widget-text input, .widget-password input {
  border-radius: var(--al-radius-sm) !important; border: 1px solid var(--al-border) !important;
  padding: 9px 13px !important; font-family: var(--al-font) !important; font-size: 14px !important;
  color: var(--al-text) !important; box-shadow: none !important;
}
.widget-text input:focus, .widget-password input:focus {
  border-color: var(--al-primary) !important;
  box-shadow: 0 0 0 3px rgba(47,111,237,.14) !important; outline: none !important;
}
.widget-label { font-family: var(--al-font) !important; color: var(--al-text-soft) !important; }

.widget-dropdown select {
  border-radius: var(--al-radius-sm) !important; border: 1px solid var(--al-border) !important;
  padding: 8px 12px !important; font-family: var(--al-font) !important;
  font-size: 13.5px !important; color: var(--al-text) !important;
  background: var(--al-surface) !important; box-shadow: none !important; height: 38px !important;
}
.widget-dropdown select:focus {
  border-color: var(--al-primary) !important;
  box-shadow: 0 0 0 3px rgba(47,111,237,.14) !important; outline: none !important;
}
"""

LOGIN = """
.al-login-wrap { display: flex; justify-content: center; padding: 60px 0 90px; }
.al-login-card {
  width: 430px; background: var(--al-surface); border-radius: 18px;
  box-shadow: var(--al-shadow-lg); padding: 38px 40px 30px;
}
.al-login-icon {
  width: 62px; height: 62px; margin: 0 auto 18px; border-radius: 16px;
  background: linear-gradient(150deg, #5b8dff, #2f6fed);
  display: flex; align-items: center; justify-content: center; font-size: 27px;
  box-shadow: 0 6px 18px rgba(47,111,237,.32);
}
.al-login-title {
  font-size: 25px; font-weight: 700; text-align: center; margin-bottom: 8px;
  letter-spacing: -.4px;
}
.al-login-sub {
  text-align: center; color: var(--al-text-soft); font-size: 14px;
  line-height: 1.5; margin-bottom: 22px;
}
.al-login-user {
  background: var(--al-primary-soft); border-radius: var(--al-radius-sm);
  padding: 12px; text-align: center; font-size: 14px; color: #33415c; margin-bottom: 20px;
}
.al-login-user b { color: var(--al-text); }
.al-login-foot {
  margin-top: 20px; text-align: center; font-size: 11.5px; color: var(--al-text-faint);
  line-height: 1.7;
}
.al-login-foot code {
  background: var(--al-surface-alt); border: 1px solid var(--al-border);
  border-radius: 5px; padding: 1px 6px; font-family: var(--al-mono); font-size: 11px;
  color: var(--al-text-soft);
}
.al-status {
  border-radius: 999px; padding: 8px 16px; font-size: 13px; font-weight: 600;
  text-align: center; margin: 4px 0 2px;
}
.al-status-info  { background: #fff5e6; color: #a35b06; }
.al-status-error { background: var(--al-error-soft); color: var(--al-error); }
.al-status-ok    { background: #e9f9ef; color: #14803c; }
.al-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%;
          margin-right: 7px; vertical-align: middle; background: currentColor; }
"""

DASHBOARD = """
/* --- encabezado de la aplicacion --------------------------------------- */
.al-header { display: flex; align-items: center; gap: 14px; padding: 6px 0 20px; }
.al-header-icon {
  width: 44px; height: 44px; border-radius: 12px;
  background: linear-gradient(150deg, #5b8dff, #2f6fed); color: #fff;
  display: flex; align-items: center; justify-content: center; font-size: 20px;
  box-shadow: 0 4px 12px rgba(47,111,237,.3);
}
.al-header-title { font-size: 19px; font-weight: 700; line-height: 1.25; }
.al-header-sub { font-size: 12.5px; color: var(--al-text-soft); }
.al-user-pill {
  display: inline-flex; align-items: center; gap: 8px; background: var(--al-surface);
  border: 1px solid var(--al-border); border-radius: 999px; padding: 8px 16px;
  font-size: 13px; font-weight: 600; white-space: nowrap;
}
.al-user-pill .al-live { width: 8px; height: 8px; border-radius: 50%; background: var(--al-ok); }
.al-user-role {
  font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  background: var(--al-primary-soft); color: var(--al-primary-dark);
  border-radius: 5px; padding: 2px 6px;
}

/* --- tarjetas de metricas superiores ------------------------------------ */
.al-stats { display: flex; gap: 14px; margin-bottom: 22px; flex-wrap: wrap; }
.al-stat {
  background: var(--al-surface); border: 1px solid var(--al-border);
  border-radius: var(--al-radius); box-shadow: var(--al-shadow);
  padding: 16px 20px; min-width: 108px;
}
.al-stat-value { font-size: 30px; font-weight: 700; line-height: 1.1; letter-spacing: -1px; }
.al-stat-label {
  font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase;
  color: var(--al-text-faint); margin-top: 5px;
}
.al-stat-wide { flex: 1; }
.al-v-primary { color: var(--al-primary); }
.al-v-warn    { color: var(--al-warn); }
.al-v-ok      { color: var(--al-ok); }
.al-v-error   { color: var(--al-error); }
.al-v-mono    { font-family: var(--al-mono); font-size: 25px; letter-spacing: 0; }

/* --- lista de procesos --------------------------------------------------- */
.al-proc {
  background: var(--al-surface); border: 1px solid var(--al-border);
  border-radius: var(--al-radius); box-shadow: var(--al-shadow);
  padding: 14px 16px; margin-bottom: 11px;
}
.al-proc-play {
  width: 30px; height: 30px; border-radius: 50%; border: 1px solid var(--al-border);
  color: var(--al-primary); display: flex; align-items: center; justify-content: center;
  font-size: 11px; flex-shrink: 0;
}
.al-proc-name { font-size: 14.5px; font-weight: 700; line-height: 1.3; }
.al-proc-file {
  font-size: 12px; color: var(--al-text-soft); font-family: var(--al-mono);
  margin-top: 3px; word-break: break-all;
}
.al-proc-tag {
  display: inline-block; font-size: 10px; font-weight: 600; background: var(--al-surface-alt);
  color: var(--al-text-soft); border-radius: 5px; padding: 2px 7px; margin: 5px 5px 0 0;
}
.al-proc-info {
  background: var(--al-surface-alt); border-left: 3px solid var(--al-primary);
  border-radius: 0 var(--al-radius-sm) var(--al-radius-sm) 0;
  padding: 12px 15px; margin-top: 11px; font-size: 13px; line-height: 1.6;
  color: #37455f;
}
.al-proc-info b { color: var(--al-text); }
.al-proc-state {
  font-size: 10px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
  border-radius: 5px; padding: 3px 8px;
}
.al-st-running   { background: #fff3e0; color: var(--al-warn); }
.al-st-done      { background: #e9f9ef; color: var(--al-ok); }
.al-st-warn      { background: #fff3e0; color: var(--al-warn); }
.al-st-error     { background: var(--al-error-soft); color: var(--al-error); }
.al-st-cancelled { background: var(--al-surface-alt); color: var(--al-text-soft); }

/* --- consola ------------------------------------------------------------ */
.al-console { border-radius: var(--al-radius); overflow: hidden; box-shadow: var(--al-shadow); }
.al-console-bar {
  background: var(--al-console-bar); padding: 10px 15px; display: flex;
  align-items: center; gap: 9px;
}
.al-console-dot { width: 11px; height: 11px; border-radius: 50%; }
.al-console-name { color: #e2e8f0; font-weight: 700; font-size: 13px; margin-left: 6px; }
.al-console-chips { margin-left: auto; display: flex; gap: 7px; }
.al-chip {
  background: #2a3546; color: #94a3b8; border-radius: 6px; padding: 3px 9px;
  font-size: 11px; font-family: var(--al-mono); font-weight: 600;
}
.al-chip-warn  { color: #fbbf24; }
.al-chip-error { color: #f87171; }
.al-chip-live  { color: #4ade80; }
.al-console-body {
  background: var(--al-console-bg); padding: 15px 18px; height: 430px; overflow-y: auto;
  font-family: var(--al-mono); font-size: 12.5px; line-height: 1.75;
}
.al-console-body::-webkit-scrollbar { width: 9px; }
.al-console-body::-webkit-scrollbar-thumb { background: #2f3b4d; border-radius: 5px; }
.al-line { display: flex; gap: 11px; white-space: pre-wrap; word-break: break-word; }
.al-line-time { color: #475569; flex-shrink: 0; }
.al-line-src {
  color: #7c8db5; flex-shrink: 0; min-width: 92px; max-width: 92px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.al-line-text { color: var(--al-console-text); flex: 1; }
.al-lv-warn    .al-line-text { color: #fbbf24; }
.al-lv-error   .al-line-text { color: #f87171; }
.al-lv-success .al-line-text { color: #4ade80; }
.al-lv-system  .al-line-text { color: #93b4f5; }
.al-console-hint {
  color: var(--al-text-soft); font-size: 13px; font-style: italic;
  padding: 15px 18px; background: var(--al-surface);
  border: 1px solid var(--al-border); border-radius: var(--al-radius);
  margin-bottom: 14px;
}
.al-empty {
  text-align: center; color: var(--al-text-soft); padding: 44px 20px; font-size: 14px;
  background: var(--al-surface); border: 1px dashed #d6deec; border-radius: var(--al-radius);
}
"""

ADMIN = """
/* --- tabs -------------------------------------------------------------- */
.al-tabs .p-TabBar-tab, .al-tabs .lm-TabBar-tab {
  font-family: var(--al-font) !important; font-weight: 600 !important; font-size: 13px !important;
}
.al-tabs > .widget-tab-contents { padding: 18px 0 0 !important; }

/* --- administracion de miembros ---------------------------------------- */
.al-admin-note {
  background: var(--al-primary-soft); border-radius: var(--al-radius-sm);
  padding: 13px 16px; font-size: 13px; line-height: 1.6; color: #33415c; margin-bottom: 16px;
}
.al-member {
  display: flex; align-items: center; gap: 11px; padding: 9px 13px;
  border: 1px solid var(--al-border); border-radius: var(--al-radius-sm);
  margin-bottom: 8px; background: var(--al-surface);
}
.al-member-avatar {
  width: 30px; height: 30px; border-radius: 50%; background: var(--al-primary-soft);
  color: var(--al-primary-dark); display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 12px; flex-shrink: 0;
}
.al-member-sid { font-weight: 600; font-size: 13.5px; }
.al-role-tag {
  font-size: 10px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
  border-radius: 5px; padding: 2px 7px;
}
.al-role-lead   { background: #fff0e0; color: #b45309; }
.al-role-member { background: var(--al-surface-alt); color: var(--al-text-soft); }

/* --- metricas ----------------------------------------------------------- */
.al-metric-grid { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 20px; }
.al-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.al-table th {
  text-align: left; font-size: 10px; font-weight: 700; letter-spacing: .08em;
  text-transform: uppercase; color: var(--al-text-faint);
  padding: 9px 12px; border-bottom: 1px solid var(--al-border);
}
.al-table td { padding: 11px 12px; border-bottom: 1px solid #f0f3f9; }
.al-table tr:last-child td { border-bottom: none; }
.al-table .al-num { text-align: right; font-family: var(--al-mono); font-size: 12.5px; }
.al-bar { background: var(--al-surface-alt); border-radius: 4px; height: 7px; overflow: hidden;
          min-width: 90px; }
.al-bar > span { display: block; height: 100%; border-radius: 4px; background: var(--al-ok); }
.al-bar-warn > span  { background: var(--al-warn); }
.al-bar-error > span { background: var(--al-error); }
.al-spark { display: flex; align-items: flex-end; gap: 4px; height: 62px; padding-top: 8px; }
.al-spark-col { flex: 1; display: flex; flex-direction: column; justify-content: flex-end;
                gap: 2px; min-width: 12px; }
.al-spark-ok   { background: var(--al-primary); border-radius: 3px 3px 0 0; min-height: 2px; }
.al-spark-fail { background: var(--al-error); border-radius: 3px 3px 0 0; }
.al-spark-day  { font-size: 9px; color: var(--al-text-faint); text-align: center;
                 margin-top: 5px; font-family: var(--al-mono); }
"""


def css():
    # type: () -> str
    """Devuelve la hoja de estilos completa, lista para inyectar."""
    return f"<style>{TOKENS + BASE + LOGIN + DASHBOARD + ADMIN}</style>"
