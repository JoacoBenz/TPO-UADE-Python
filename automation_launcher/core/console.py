"""Buffer de la consola en vivo.

Tres responsabilidades, y la tercera es la que decide si la app se siente
rapida o rota:

1. Guardar las lineas con su nivel y su marca de tiempo.
2. Llevar los contadores que se ven en la barra (lineas, warn, err).
3. **No crecer sin limite.** Un notebook charlatan emite decenas de miles de
   lineas; sin tope, el proceso de Voila se come la memoria y el navegador se
   traba con un DOM imposible. El buffer es circular: se queda con las
   ultimas N y descarta el resto.

Todo texto pasa por ``secrets.redactor`` al entrar, no al salir. Asi el
password no queda guardado ni siquiera en memoria dentro del buffer, y no hay
forma de olvidarse de limpiarlo en alguna de las salidas.
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from typing import TYPE_CHECKING

from .secrets import redactor

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import (  # noqa: F401  (los usan los comentarios `# type:`)
        Any,
        Callable,
        Dict,
        List,
        Optional,
    )

# Niveles, de menor a mayor severidad.
INFO = "info"
WARN = "warn"
ERROR = "error"
SUCCESS = "success"
SYSTEM = "system"

#: Senales inequivocas de fallo: nombres de excepcion en CamelCase y la
#: cabecera de un traceback. Van con mayusculas y minusculas exactas porque
#: "ValueError" es un tipo y "value error" es prosa.
_STRONG_ERROR = re.compile(
    r"Traceback \(most recent call last\)"
    r"|\b\w*(?:Error|Exception)\b\s*:"
    r"|^\s*\w*(?:Error|Exception)\b"
)

#: Frases que mencionan errores justamente para decir que no hubo ninguno.
#: Sin esta excepcion, un notebook que cierra con "0 errors" se pinta de rojo
#: y el tablero miente sobre el estado de la corrida.
_BENIGN = re.compile(
    r"\b(?:0|no|sin|zero)\s+(?:errors?|failures?|warnings?|fallos?|errores)\b",
    re.IGNORECASE,
)

#: Palabras que sugieren fallo cuando no hay una senal mas fuerte.
_ERROR_WORDS = re.compile(
    r"\b(?:errors?|errores?|failed|failure|fallo|fatal|critical)\b", re.IGNORECASE
)

#: Advertencias, incluidas las clases CamelCase del modulo ``warnings``.
_WARN_PATTERNS = re.compile(
    r"\w*Warning\b|\b(?:warn|warnings?|deprecated|deprecation|advertencia)\b",
    re.IGNORECASE,
)


def classify(text):
    # type: (str) -> str
    """Deduce el nivel de una linea por su contenido.

    Es una heuristica y se la trata como tal: la senal confiable de que una
    corrida fallo es la excepcion o la escritura a stderr, que el motor
    conoce con certeza. Esto solo colorea lo que sale por stdout.

    El orden de las reglas es el que evita los dos errores que importan:
    marcar de rojo un "0 errors" (falso positivo, el peor, porque hace
    desconfiar del tablero) y dejar en gris un ``DeprecationWarning``.
    """
    if not text or not text.strip():
        return INFO
    if _STRONG_ERROR.search(text):
        return ERROR
    if _BENIGN.search(text):
        return INFO
    if _ERROR_WORDS.search(text):
        return ERROR
    if _WARN_PATTERNS.search(text):
        return WARN
    return INFO


class ConsoleLine:
    """Una linea de la consola."""

    __slots__ = ("timestamp", "level", "text", "source")

    def __init__(self, text, level=INFO, source="", timestamp=None):
        # type: (str, str, str, Optional[float]) -> None
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.level = level
        self.text = text
        #: Que proceso la emitio. Con corridas en paralelo, sin esto la
        #: consola es una sopa donde no se sabe quien dijo que.
        self.source = source

    @property
    def clock(self):
        # type: () -> str
        return time.strftime("%H:%M:%S", time.localtime(self.timestamp))

    def to_dict(self):
        # type: () -> Dict[str, Any]
        return {
            "timestamp": self.timestamp, "clock": self.clock,
            "level": self.level, "text": self.text, "source": self.source,
        }

    def __repr__(self):
        # type: () -> str
        return f"ConsoleLine({self.level!r}, {self.text[:40]!r})"


class ConsoleBuffer:
    """Buffer circular con contadores, seguro para usar desde varios hilos."""

    def __init__(self, max_lines=5000):
        # type: (int) -> None
        self.max_lines = max(100, int(max_lines))
        self._lines = deque(maxlen=self.max_lines)   # type: deque
        self._lock = threading.RLock()
        self._listeners = []    # type: List[Callable[[], None]]
        # Los contadores son acumulados de la sesion, no del buffer: si se
        # descartan lineas viejas por el tope, igual queremos saber cuantos
        # errores hubo en total.
        self._total = 0
        self._warnings = 0
        self._errors = 0
        self._dropped = 0

    # -- escritura -----------------------------------------------------------

    def append(self, text, level=None, source=""):
        # type: (Any, Optional[str], str) -> ConsoleLine
        """Agrega una linea, ya redactada y clasificada."""
        clean = redactor.scrub(text)
        if level is None:
            level = classify(clean)
        line = ConsoleLine(clean, level=level, source=source)
        with self._lock:
            if len(self._lines) == self.max_lines:
                self._dropped += 1
            self._lines.append(line)
            self._total += 1
            if level == WARN:
                self._warnings += 1
            elif level == ERROR:
                self._errors += 1
        self._notify()
        return line

    def append_block(self, text, level=None, source=""):
        # type: (Any, Optional[str], str) -> None
        """Agrega un bloque multilinea, una linea del buffer por cada salto."""
        clean = redactor.scrub(text)
        if not clean:
            return
        for raw in clean.splitlines():
            self.append(raw, level=level, source=source)

    def clear(self):
        # type: () -> None
        """Vacia la pantalla. Los contadores se reinician con ella."""
        with self._lock:
            self._lines.clear()
            self._total = 0
            self._warnings = 0
            self._errors = 0
            self._dropped = 0
        self._notify()

    # -- lectura -------------------------------------------------------------

    def lines(self, source=None, limit=None):
        # type: (Optional[str], Optional[int]) -> List[ConsoleLine]
        with self._lock:
            items = list(self._lines)
        if source:
            items = [line for line in items if line.source == source]
        if limit:
            items = items[-limit:]
        return items

    def text(self, source=None):
        # type: (Optional[str]) -> str
        return "\n".join(line.text for line in self.lines(source=source))

    @property
    def stats(self):
        # type: () -> Dict[str, int]
        with self._lock:
            return {
                "lines": self._total, "warnings": self._warnings,
                "errors": self._errors, "dropped": self._dropped,
                "buffered": len(self._lines),
            }

    def sources(self):
        # type: () -> List[str]
        with self._lock:
            return sorted({line.source for line in self._lines if line.source})

    # -- notificacion --------------------------------------------------------

    def subscribe(self, callback):
        # type: (Callable[[], None]) -> None
        """Registra un observador que se avisa en cada cambio.

        La UI no repinta en cada aviso: los agrupa por tiempo. Ver
        ``ui.widgets.ConsoleView``.
        """
        with self._lock:
            self._listeners.append(callback)

    def _notify(self):
        # type: () -> None
        with self._lock:
            listeners = list(self._listeners)
        for callback in listeners:
            try:
                callback()
            except Exception:
                # Un observador roto no puede frenar la corrida que estaba
                # escribiendo en la consola.
                pass

    def __len__(self):
        # type: () -> int
        with self._lock:
            return len(self._lines)

    def __repr__(self):
        # type: () -> str
        stats = self.stats
        return "ConsoleBuffer(lines={lines}, warn={warnings}, err={errors})".format(**stats)
