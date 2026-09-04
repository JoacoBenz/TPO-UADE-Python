"""Empaqueta el launcher entero en un unico .ipynb autocontenido.

Para que existe: en un entorno controlado a veces solo se puede mover un
archivo al servidor de Jupyter. Este script arma un notebook que trae el
paquete completo adentro y no depende de nada mas.

La idea es que **no cambie como se desarrolla**. Se sigue trabajando en
archivos .py que git compara y pytest prueba; esto es solo el formato de
entrega. El notebook generado no se edita a mano nunca: se regenera.

Como funciona: cada modulo se escribe en una celda que lo registra en
``sys.modules`` antes de que nadie lo importe. Asi los ``from .core import x``
del propio paquete siguen funcionando tal cual, sin reescribir imports.

El notebook NO trae la configuracion adentro: busca un ``launcher_config.py``
a su lado, igual que el deploy normal. Embeberla obligaria a rehacer el build
para cambiar un timeout, y la configuracion es lo que mas cambia entre
entornos.

    python tools/build_single_notebook.py
    python tools/build_single_notebook.py --output dist/launcher.ipynb
"""

from __future__ import annotations

import argparse
import json
import os
import sys

PACKAGE = "automation_launcher"

#: Orden de carga: cada modulo tiene que estar registrado antes de que otro lo
#: importe. Es el orden de dependencias del paquete, de abajo hacia arriba.
MODULE_ORDER = [
    "core.models",
    "core.secrets",
    "core.config",
    "core.contents",
    "core.authz",
    "core.repository",
    "core.auth",
    "core.console",
    "core.engine",
    "core.history",
    "core.metrics",
    "ui.theme",
    "ui.widgets",
    "ui.login",
    "ui.dashboard",
    "ui.members",
    "ui.metrics_tab",
    "ui.app",
]

HEADER = '''"""Automation Launcher — build autocontenido.

GENERADO AUTOMATICAMENTE. No editar a mano: los cambios se pierden en el
proximo build y no quedan en git.

  Fuente:  {package}/
  Rehacer: python tools/build_single_notebook.py

Este notebook trae el paquete completo adentro. Para servirlo:

    voila <este archivo>.ipynb
"""
import sys, types

_MODULES = {{}}


def _register(name, source):
    """Registra un modulo del paquete en sys.modules sin tocarlo en disco."""
    full = "{package}." + name if name else "{package}"
    module = types.ModuleType(full)
    module.__file__ = "<empaquetado:" + full + ">"
    if name.count(".") == 0 and name:
        module.__package__ = "{package}"
    else:
        module.__package__ = full.rsplit(".", 1)[0]
    if not name or name in ("core", "ui"):
        module.__path__ = []          # es un paquete, no un modulo suelto
    sys.modules[full] = module
    _MODULES[full] = (module, source)
    # Sin return: Jupyter muestra el valor de la ultima expresion de cada
    # celda, y devolver el modulo llenaria la pagina con sus reprs.


def _exec_all():
    """Ejecuta las fuentes ya registradas, en el orden en que se agregaron."""
    for full, (module, source) in _MODULES.items():
        if source is not None:
            exec(compile(source, module.__file__, "exec"), module.__dict__)
'''


def read_module(name):
    path = os.path.join(PACKAGE, *(name.split("."))) + ".py"
    if not os.path.isfile(path):
        raise SystemExit(f"no se encontro {path}")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def code_cell(source):
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": source}


def build(output):
    cells = [code_cell(HEADER.format(package=PACKAGE))]

    # Los paquetes contenedores primero, para que los submodulos tengan donde
    # colgar cuando se registren.
    cells.append(code_cell(
        "# Paquetes contenedores\n"
        '_register("", None)\n'
        '_register("core", None)\n'
        '_register("ui", None)\n'
    ))

    for name in MODULE_ORDER:
        source = read_module(name)
        cells.append(code_cell(
            f"# \u2500\u2500 {PACKAGE}.{name} \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            + f"_register({name!r}, {source!r})\n"
        ))

    cells.append(code_cell("_exec_all()\n"))
    cells.append(code_cell(
        "from automation_launcher.ui.app import run\n\n"
        "run()   # busca launcher_config.py junto al notebook\n"
    ))

    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python",
                           "name": "python3"},
            "language_info": {"name": "python", "version": "3.7.0"},
            "voila": {"theme": "light"},
        },
        "nbformat": 4, "nbformat_minor": 5,
    }

    directory = os.path.dirname(output)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(notebook, handle, indent=1, ensure_ascii=False)
        handle.write("\n")

    size = os.path.getsize(output)
    print(f"{output} \u2014 {len(cells)} celdas, {size / 1024.0:.0f} KB")
    print("Copiar junto a un launcher_config.py y servir con:")
    print(f"  voila {os.path.basename(output)}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", default="dist/automation_launcher_standalone.ipynb")
    args = parser.parse_args(argv)
    return build(args.output)


if __name__ == "__main__":
    sys.exit(main())
