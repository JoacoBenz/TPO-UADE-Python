"""Verifica que el codigo se pueda parsear con la gramatica de Python 3.7.

El launcher corre sobre el kernel Athena, que es 3.7. Acá no hay un 3.7 para
ejecutar, pero ``ast.parse(..., feature_version=(3, 7))`` usa exactamente el
parser de esa version, asi que rechaza el operador morsa, los parametros
posicionales, ``match``, las f-strings anidadas y todo lo demas que entro
despues.

El chequeo de gramatica solo, sin embargo, no alcanza. Hay dos huecos:

* ``int | str`` parsea en cualquier version (es un ``BinOp``); solo falla al
  evaluarse. Como todos los modulos tienen ``from __future__ import
  annotations``, en anotaciones es inocuo, pero fuera de ellas no.
* Nada impide llamar a ``statistics.quantiles`` o ``functools.cached_property``,
  que existen recien desde 3.8 y explotarian en el kernel de produccion.

Por eso ademas se busca por nombre un conjunto de funciones y clases de la
biblioteca estandar que entraron despues de 3.7.

    python tools/check_py37.py
"""

from __future__ import annotations

import ast
import os
import sys

TARGET = (3, 7)
ROOTS = ("automation_launcher", "tools", "tests")
EXTRA = ("launcher_config.example.py", "demo/launcher_config.demo.py")


#: Nombres de la biblioteca estandar que NO existen en 3.7. Usarlos parsea
#: perfecto y revienta recien en produccion, que es el peor momento posible.
FORBIDDEN_NAMES = {
    "cached_property": "functools.cached_property es de 3.8",
    "quantiles": "statistics.quantiles es de 3.8 (usar core.metrics.percentile)",
    "prod": "math.prod es de 3.8",
    "Protocol": "typing.Protocol es de 3.8 (usar una clase base o duck typing)",
    "TypedDict": "typing.TypedDict es de 3.8",
    "Literal": "typing.Literal es de 3.8",
    "Final": "typing.Final es de 3.8",
    "AsyncMock": "unittest.mock.AsyncMock es de 3.8",
    "get_origin": "typing.get_origin es de 3.8",
    "get_args": "typing.get_args es de 3.8",
    "pairwise": "itertools.pairwise es de 3.10",
    "removeprefix": "str.removeprefix es de 3.9",
    "removesuffix": "str.removesuffix es de 3.9",
}


def find_forbidden(tree):
    """Devuelve (linea, motivo) por cada nombre de stdlib demasiado nuevo."""
    hits = []
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, ast.alias):
            name = node.name.rsplit(".", 1)[-1]
        elif isinstance(node, ast.Name):
            name = node.id
        if name in FORBIDDEN_NAMES:
            line = getattr(node, "lineno", 0)
            hits.append((line, FORBIDDEN_NAMES[name]))
    return hits


def iter_files():
    for root in ROOTS:
        for base, _dirs, names in os.walk(root):
            if "__pycache__" in base:
                continue
            for name in sorted(names):
                if name.endswith(".py"):
                    yield os.path.join(base, name)
    for path in EXTRA:
        if os.path.isfile(path):
            yield path


def main():
    failures = []
    checked = 0
    for path in iter_files():
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        try:
            tree = ast.parse(source, filename=path, feature_version=TARGET)
            checked += 1
        except SyntaxError as exc:
            failures.append((path, exc.lineno, exc.msg))
            continue
        for line, reason in find_forbidden(tree):
            failures.append((path, line, reason))

    version = "{}.{}".format(*TARGET)
    if failures:
        print(f"Incompatible con Python {version}:\n")
        for path, lineno, msg in failures:
            print(f"  {path}:{lineno}: {msg}")
        return 1
    print(f"{checked} archivos compatibles con Python {version} "
          "(gramatica + nombres de stdlib).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
