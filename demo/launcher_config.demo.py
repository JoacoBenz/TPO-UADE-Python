"""Configuracion de demo: corre el launcher entero sin red, sin SMB y sin Jupyter.

Es la que usan ``run_local.sh`` y ``run_local.bat``.

Lo que cambia respecto de produccion son tres claves:

  LOCAL_SHARE_ROOT  -> lee el "share" de una carpeta del repo
  AUTH_BACKEND      -> no valida contra ninguna red
  DEMO_MODE         -> habilita el selector de usuario del login

Todo lo demas es identico al deploy real, incluido el codigo que corre.
"""

import os

_HERE = os.path.dirname(os.path.abspath(__file__))

# --- lo que hace que ande local ---------------------------------------------
LOCAL_SHARE_ROOT = os.path.join(_HERE, "share")
CONTENTS_DIR = ""          # la raiz del share falso ya es demo/share
HUBS_DIR = "_hubs"

AUTH_BACKEND = "mock"
DEMO_MODE = True

# --- usuarios de prueba ------------------------------------------------------
# Cada uno muestra una cara distinta del modelo de permisos. Entra con
# cualquier contrasena de 4 caracteres o mas.
DEMO_USERS = [
    {"sid": "ana.g",
     "note": "jefa de Treasury — ve los tabs de Miembros y Métricas"},
    {"sid": "joaquin.benz",
     "note": "miembro de Treasury y CLO — dos hubs, sin tabs de jefe"},
    {"sid": "carlos.m",
     "note": "jefe de CLO y miembro de Treasury — jefe en uno solo"},
    {"sid": "lucia.r",
     "note": "miembro de Treasury únicamente — entra directo, sin selector"},
    {"sid": "intruso",
     "note": "sin ningún hub — muestra el rechazo y su registro de auditoría"},
]

# --- resto de la configuracion ------------------------------------------------
APP_TITLE = "Automation Launcher"
APP_SUBTITLE = "Automation Control Room"
ORG_NAME = "Demo Corp"

MAX_CONCURRENT_RUNS = 3
CONSOLE_MAX_LINES = 3000
CONSOLE_REFRESH_MS = 200
DEFAULT_TIMEOUT_SECONDS = 600

AUDIT_LOG_PATH = os.path.join(_HERE, "..", "runs", "audit.jsonl")
