"""Configuracion del Automation Launcher — plantilla.

Copiala como ``launcher_config.py`` y ajustala para tu entorno. Ese archivo
NO se versiona (esta en .gitignore) porque es especifico de cada deploy.

Toda clave que falte usa el valor por defecto que esta definido en el codigo
(``automation_launcher/core/config.py``), asi que este archivo puede tener
solo lo que cambia. Un valor invalido se descarta con una advertencia visible
en la consola en lugar de tumbar la aplicacion.
"""

# =============================================================================
#  Donde viven las automatizaciones
# =============================================================================

# Raiz dentro de la Contents API de Jupyter. Si el share SMB esta montado con
# jupyterfs, esta es la ruta tal como se ve en el file browser de JupyterLab.
CONTENTS_DIR = "jupyter/notebooks/automations"

# Subcarpeta con la metadata de los hubs. Adentro va un registry.json y una
# carpeta por equipo. Ver docs/permissions.md por las ACLs que necesita.
HUBS_DIR = "_hubs"


# =============================================================================
#  Acceso a la Contents API
# =============================================================================

# Vacio => se autodetecta de las variables del kernel (JUPYTER_SERVER_URL y
# compania). Completalo solo si la deteccion falla.
JUPYTER_URL = ""

# Variables de entorno donde buscar el token, en orden. El launcher prueba
# ambas y se queda con la que funcione.
TOKEN_ENV = "ATHENA_IDA_TOKEN"
FALLBACK_TOKEN_ENV = "HYDRA_ID_ANYWHERE_TOKEN"

# El servidor interno usa certificado propio.
VERIFY_TLS = False

REQUEST_TIMEOUT = 30      # segundos por llamada HTTP
CACHE_TTL_SECONDS = 30    # cuanto se cachea una lectura del share


# =============================================================================
#  Autenticacion
# =============================================================================

# "smb"  -> valida la contrasena contra IPC$ en un host del dominio
# "mock" -> acepta cualquier contrasena (solo para desarrollo local)
AUTH_BACKEND = "smb"

# Host SMB contra el que autenticar. Sin barras invertidas al principio.
AUTH_HOST = "corp-fs01"

# Dominio de Windows. Vacio si los usuarios se loguean sin prefijo.
AUTH_DOMAIN = "CORP"

AUTH_TIMEOUT = 20


# =============================================================================
#  Ejecucion
# =============================================================================

# "inprocess" -> las corridas van en hilos de este proceso. Es lo que permite
#                auto-responder getpass()/input() y heredar el entorno del
#                kernel. Es el modo probado en produccion.
# "subprocess" -> aisla cada corrida en su propio proceso. El Stop corta
#                siempre, a costa de no compartir el estado del kernel.
RUNNER = "inprocess"

MAX_CONCURRENT_RUNS = 3
DEFAULT_TIMEOUT_SECONDS = 3600
CONSOLE_MAX_LINES = 5000

# Cada cuanto se repinta la consola, en milisegundos. Subilo si la interfaz
# se siente pesada con notebooks muy charlatanes.
CONSOLE_REFRESH_MS = 200


# =============================================================================
#  Interfaz
# =============================================================================

APP_TITLE = "Automation Launcher"
APP_SUBTITLE = "Automation Control Room"

# Texto de la barra negra superior. Vacio para dejarla sin marca.
ORG_NAME = ""

# Mostrar el selector de hub cuando alguien pertenece a mas de un equipo.
SHOW_HUB_PICKER = True


# =============================================================================
#  Auditoria
# =============================================================================

# Archivo local del servidor con las decisiones de autorizacion. Va local y no
# al share para que un rechazo quede registrado aunque la persona rechazada no
# tenga permiso de escritura en ninguna carpeta.
AUDIT_LOG_PATH = "runs/audit.jsonl"
AUDIT_ENABLED = True


# =============================================================================
#  Modo demo (desarrollo local)
# =============================================================================

# Solo tiene efecto con AUTH_BACKEND = "mock". Ver demo/launcher_config.demo.py
# para un ejemplo completo.
DEMO_MODE = False
DEMO_USERS = []

# Si se completa, se lee el share desde esta carpeta local en lugar de la
# Contents API. Es el interruptor que permite correr todo sin Jupyter ni SMB.
LOCAL_SHARE_ROOT = ""
