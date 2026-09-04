"""Redaccion de secretos en todo texto que sale del launcher.

Los notebooks que corre esta herramienta hacen ``print`` de cosas
imprevisibles: respuestas de APIs, cadenas de conexion, tracebacks que
incluyen argumentos. Cualquiera de esas puede arrastrar el password de red
del usuario hasta la consola, el historial o un notebook de salida.

Por eso hay un unico punto por el que pasa *todo* texto antes de mostrarse o
persistirse. No es una capa opcional de higiene: es la que hace que la
inyeccion de ``SID``/``PASSWORD`` en los procesos sea aceptable.

Uso::

    redactor.remember(password)     # al hacer login
    redactor.scrub(linea)           # antes de mostrar o guardar
    redactor.forget()               # al hacer sign out
"""

from __future__ import annotations

import html
import re
import threading
import urllib.parse
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import Iterable, List, Set  # noqa: F401  (los usan los comentarios `# type:`)

#: Con que se reemplaza un secreto encontrado.
MASK = "•" * 8

#: Secretos mas cortos que esto no se enmascaran. Un password de dos
#: caracteres generaria coincidencias en cualquier texto y volveria la
#: consola ilegible; el riesgo de no taparlo es menor que el de romper todo.
MIN_SECRET_LENGTH = 4


class Redactor:
    """Guarda secretos y los tapa en cualquier texto.

    Es seguro de usar desde varios hilos: los runs corren en workers y todos
    escriben a la misma consola.
    """

    def __init__(self):
        # type: () -> None
        self._lock = threading.RLock()
        self._secrets = set()      # type: Set[str]
        self._pattern = None       # type: ignore[var-annotated]

    # -- gestion de secretos ------------------------------------------------

    def remember(self, *secrets):
        # type: (*str) -> None
        """Agrega secretos a tapar.

        Ademas del valor literal registra sus variantes codificadas, porque
        un password llega a la salida despues de pasar por una URL o por el
        escapado de HTML tan seguido como en crudo.
        """
        with self._lock:
            for secret in secrets:
                if not secret or len(secret) < MIN_SECRET_LENGTH:
                    continue
                for variant in self._variants(secret):
                    self._secrets.add(variant)
            self._rebuild()

    def forget(self):
        # type: () -> None
        """Olvida todos los secretos. Se llama en Sign Out."""
        with self._lock:
            self._secrets.clear()
            self._pattern = None

    @staticmethod
    def _variants(secret):
        # type: (str) -> Iterable[str]
        """Las formas en que un mismo secreto puede aparecer en la salida."""
        out = [
            secret,
            urllib.parse.quote(secret, safe=""),
            urllib.parse.quote_plus(secret),
            html.escape(secret),
        ]
        seen = []      # type: List[str]
        for value in out:
            if value and len(value) >= MIN_SECRET_LENGTH and value not in seen:
                seen.append(value)
        return seen

    def _rebuild(self):
        # type: () -> None
        """Recompila el patron unico que busca todos los secretos a la vez.

        Se ordena por longitud descendente para que, cuando un secreto es
        prefijo de otro, gane siempre la coincidencia mas larga.
        """
        if not self._secrets:
            self._pattern = None
            return
        ordered = sorted(self._secrets, key=len, reverse=True)
        self._pattern = re.compile("|".join(re.escape(s) for s in ordered))

    # -- uso ----------------------------------------------------------------

    def scrub(self, text):
        # type: (object) -> str
        """Devuelve ``text`` con todos los secretos reemplazados por la mascara.

        Acepta cualquier objeto y lo convierte a texto: esto se llama sobre
        tracebacks, excepciones y valores sueltos, no solo sobre strings.
        """
        if text is None:
            return ""
        if not isinstance(text, str):
            text = str(text)
        with self._lock:
            pattern = self._pattern
        if pattern is None or not text:
            return text
        return pattern.sub(MASK, text)

    def scrub_lines(self, lines):
        # type: (Iterable[object]) -> List[str]
        return [self.scrub(line) for line in lines]

    def is_clean(self, text):
        # type: (object) -> bool
        """True si ``text`` no contiene ningun secreto conocido.

        Existe para que los tests puedan afirmar la propiedad que importa
        ("el password no aparece en esta salida") sin duplicar la logica.
        """
        if text is None:
            return True
        if not isinstance(text, str):
            text = str(text)
        with self._lock:
            secrets = set(self._secrets)
        for secret in secrets:
            if secret in text:
                return False
        return True

    def __len__(self):
        # type: () -> int
        with self._lock:
            return len(self._secrets)

    def __repr__(self):
        # type: () -> str
        # Nunca se listan los secretos, ni siquiera parcialmente.
        return f"Redactor(secrets={len(self)})"


#: Instancia compartida. La consola, el historial y el motor la usan;
#: tener una sola evita que una capa quede sin proteger por olvido.
redactor = Redactor()
