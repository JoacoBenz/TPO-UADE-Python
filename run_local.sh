#!/usr/bin/env bash
# Levanta el Automation Launcher en modo demo.
#
# No hace falta red de la empresa, ni el share SMB, ni credenciales reales:
# lee un share falso de demo/share y acepta cualquier contrasena de 4+
# caracteres. El codigo que corre es exactamente el mismo que va a produccion.
#
#   ./run_local.sh              -> http://localhost:8866
#   ./run_local.sh 9000         -> otro puerto
set -euo pipefail

PORT="${1:-8866}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

VENV="$HERE/.venv"
if [ ! -d "$VENV" ]; then
    echo "==> Creando entorno virtual en .venv"
    python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "==> Instalando dependencias"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

# Instalar el paquete ipykernel no alcanza: Voila necesita el kernelspec
# registrado aparte, o responde 500 con "No Jupyter kernel for language
# 'python' found". Se registra dentro del venv, autocontenido, y --sys-prefix
# hace que quede scopeado a este venv en vez de ensuciar el perfil del usuario.
echo "==> Registrando el kernel de Python para Jupyter"
python -m ipykernel install --sys-prefix --name python3 --display-name "Python 3" >/dev/null

# El launcher busca ./launcher_config.py. En modo demo se apunta al de demo/
# con un enlace, para no tener que tocar el codigo ni pasar parametros.
if [ ! -e launcher_config.py ]; then
    echo "==> Enlazando launcher_config.py -> demo/launcher_config.demo.py"
    ln -s demo/launcher_config.demo.py launcher_config.py
fi

cat <<'BANNER'

  ┌──────────────────────────────────────────────────────────────┐
  │  Automation Launcher — modo demo                             │
  │                                                              │
  │  Entra con cualquier contrasena de 4 o mas caracteres.        │
  │  El selector del login te deja probar distintos roles:        │
  │                                                              │
  │    ana.g         jefa de Treasury  (ve Miembros y Metricas)   │
  │    joaquin.benz  miembro de 2 hubs (sin tabs de jefe)         │
  │    carlos.m      jefe de CLO       (jefe en uno solo)         │
  │    lucia.r       un solo hub       (entra directo)            │
  │    intruso       sin hubs          (muestra el rechazo)       │
  └──────────────────────────────────────────────────────────────┘

BANNER

echo "==> Abriendo http://localhost:${PORT}"
exec voila app.ipynb --port="${PORT}" --no-browser --Voila.ip=0.0.0.0
