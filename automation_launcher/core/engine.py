"""Ejecucion de notebooks.

Las corridas pasan en hilos del mismo proceso, no en subprocesos. No es por
comodidad: es la unica forma de responder por el usuario cuando un notebook
llama a ``getpass()`` o a ``input()``, porque para eso hay que reemplazar esas
funciones en el interprete que ejecuta el codigo. Ademas hereda el entorno del
kernel (Athena, tokens, librerias internas) sin tener que reconstruirlo.

El problema que eso trae, y como se resuelve
--------------------------------------------
``sys.stdout``, ``getpass.getpass`` y ``builtins.input`` son globales del
proceso. Con dos corridas en paralelo, la version ingenua -- parchear al
empezar y restaurar al terminar -- hace que la salida de un proceso aparezca
en la consola del otro, y que la restauracion del primero en terminar deje al
segundo sin parche.

Aca se parchea **una sola vez**, y el parche es un enrutador: mira que hilo
esta escribiendo y manda la linea al contexto de esa corrida. Los hilos que no
son corridas (la UI, el kernel) siguen viendo el stdout real. Asi las corridas
concurrentes no se mezclan y no hay restauracion que se pueda perder.

Sobre el Stop
-------------
Cancelar un hilo en Python se hace con ``PyThreadState_SetAsyncExc``, que
inyecta una excepcion en el hilo. Tiene un limite que conviene conocer: la
excepcion solo se entrega cuando el hilo esta ejecutando bytecode de Python.
Si el notebook esta bloqueado dentro de una llamada de red o de una extension
en C, el corte no ocurre hasta que esa llamada vuelve. El launcher marca la
corrida como cancelada igual y libera el lugar en la cola, pero el trabajo de
fondo puede seguir un rato. Cuando eso no alcanza, la salida es correr con
``RUNNER="subprocess"``.
"""

from __future__ import annotations

import ctypes
import io
import json
import os
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from . import console as console_mod
from .models import RunRecord, RunState
from .secrets import redactor

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import (  # noqa: F401  (los usan los comentarios `# type:`)
        Any,
        Callable,
        Dict,
        List,
        Optional,
    )


class RunCancelled(BaseException):
    """Se inyecta en el hilo de una corrida para cortarla.

    Hereda de ``BaseException`` y no de ``Exception`` a proposito: los
    notebooks estan llenos de ``except Exception:`` y con uno de esos se
    tragarian la cancelacion y seguirian corriendo.
    """


# ---------------------------------------------------------------------------
# Enrutado por hilo de la salida y de los prompts
# ---------------------------------------------------------------------------

class _RunContext:
    """Lo que necesita saber una corrida mientras se ejecuta."""

    __slots__ = ("run_id", "process", "buffer", "answers", "saw_stderr", "cancelled")

    def __init__(self, run_id, process, buffer, answers):
        # type: (str, Process, Any, Dict[str, str]) -> None
        self.run_id = run_id
        self.process = process
        self.buffer = buffer
        self.answers = answers
        #: Si el notebook escribio algo a stderr. Es un dato de diagnostico,
        #: no el criterio de resultado: warnings y logging usan stderr sin
        #: que eso signifique que la corrida fallo.
        self.saw_stderr = False
        self.cancelled = False


#: Contexto de la corrida asociado a cada hilo trabajador.
_contexts = {}      # type: Dict[int, _RunContext]
_contexts_lock = threading.RLock()


def _current_context():
    # type: () -> Optional[_RunContext]
    with _contexts_lock:
        return _contexts.get(threading.get_ident())


def _register_context(context):
    # type: (_RunContext) -> None
    with _contexts_lock:
        _contexts[threading.get_ident()] = context


def _unregister_context():
    # type: () -> None
    with _contexts_lock:
        _contexts.pop(threading.get_ident(), None)


class _StreamRouter(io.TextIOBase):
    """Reemplaza ``sys.stdout``/``sys.stderr`` y rutea segun el hilo.

    Escribe en la consola del launcher si quien escribe es una corrida, y en
    el stream original si es cualquier otro hilo. Nunca se lo desinstala, asi
    que no hay carrera entre corridas que terminan.
    """

    def __init__(self, original, is_stderr=False):
        # type: (Any, bool) -> None
        super().__init__()
        self._original = original
        self._is_stderr = is_stderr
        self._partial = {}      # type: Dict[int, str]
        self._lock = threading.RLock()

    def write(self, text):
        # type: (str) -> int
        context = _current_context()
        if context is None:
            return self._original.write(text)
        if not text:
            return 0
        if self._is_stderr and text.strip():
            context.saw_stderr = True

        # Los notebooks escriben sin salto de linea todo el tiempo (barras de
        # progreso, print(..., end="")). Se acumula por hilo y se emite recien
        # cuando hay una linea entera, para no partir el texto en la consola.
        thread_id = threading.get_ident()
        with self._lock:
            pending = self._partial.get(thread_id, "") + text
            *complete, remainder = pending.split("\n")
            self._partial[thread_id] = remainder
        for line in complete:
            context.buffer.append(line, level=self._level_for(line), source=context.process.id)
        return len(text)

    def _level_for(self, line):
        # type: (str) -> Optional[str]
        """Decide el nivel de una linea segun el stream del que salio.

        stdout se clasifica solo por contenido. stderr **no** se marca como
        error por el solo hecho de venir de stderr: ``warnings.warn``, la
        libreria ``logging`` y las barras de progreso escriben ahi todo el
        tiempo. Se clasifica por contenido igual que stdout, pero con piso en
        WARN, porque algo que salio por stderr nunca es rutina del todo.
        """
        if not self._is_stderr:
            return None     # que lo clasifique el buffer por contenido
        level = console_mod.classify(line)
        return level if level == console_mod.ERROR else console_mod.WARN

    def flush(self):
        # type: () -> None
        """Vuelca lo que quedo sin salto de linea."""
        context = _current_context()
        thread_id = threading.get_ident()
        with self._lock:
            remainder = self._partial.pop(thread_id, "")
        if remainder and context is not None:
            context.buffer.append(
                remainder, level=self._level_for(remainder), source=context.process.id,
            )
        try:
            self._original.flush()
        except Exception:
            pass

    def isatty(self):
        # type: () -> bool
        return False

    def writable(self):
        # type: () -> bool
        return True


def _answer_prompt(prompt="", secret=False):
    # type: (str, bool) -> str
    """Responde por el usuario un ``getpass()`` o un ``input()`` del notebook.

    Es el motivo por el que el launcher pide la contrasena de red: los
    procesos que suben a DTC y compania la piden por consola, y sin nadie que
    la escriba se quedarian colgados para siempre.

    El prompt se muestra en la consola con la respuesta enmascarada, para que
    el usuario vea que se le pregunto y que se respondio sin exponer nada.
    """
    context = _current_context()
    if context is None:
        # No es una corrida: se deja pasar al comportamiento original.
        return _ORIGINAL_INPUT(prompt) if not secret else _ORIGINAL_GETPASS(prompt)

    text = str(prompt or "")
    answer = _match_answer(text, context.answers, secret)
    shown = "•" * 8 if (secret or _looks_like_password(text)) else answer
    context.buffer.append(
        "{} {}".format(text.strip() or "(prompt)", shown),
        level=console_mod.SYSTEM, source=context.process.id,
    )
    return answer


def _looks_like_password(prompt):
    # type: (str) -> bool
    lowered = prompt.lower()
    return any(word in lowered for word in ("pass", "contrase", "secret", "clave", "pwd"))


def _match_answer(prompt, answers, secret):
    # type: (str, Dict[str, str], bool) -> str
    """Elige que responder segun lo que el notebook pregunto."""
    lowered = prompt.lower()
    if secret or _looks_like_password(lowered):
        return answers.get("PASSWORD", "")
    if any(word in lowered for word in ("user", "usuario", "sid", "login", "account")):
        return answers.get("SID", "")
    # Ante la duda se responde el SID: es lo inocuo. Devolver el password a un
    # prompt que no se entendio seria filtrarlo.
    return answers.get("SID", "")


# Referencias a los originales, tomadas antes de instalar nada.
_ORIGINAL_INPUT = None      # type: Any
_ORIGINAL_GETPASS = None    # type: Any
_patched = False
_patch_lock = threading.RLock()


def install_patches():
    # type: () -> None
    """Instala los enrutadores. Nunca se desinstalan.

    Se llama al construir el ``RunManager`` y otra vez al empezar cada
    corrida. Instalar y desinstalar por corrida seria una carrera con las
    corridas concurrentes; en cambio se verifica que los enrutadores sigan
    puestos y se reinstalan si alguien los reemplazo.

    Esa verificacion no es paranoia: ``sys.stdout`` es una variable global que
    cualquiera puede reasignar despues -- ``contextlib.redirect_stdout``, la
    captura de pytest, una libreria que reinicializa los streams. Sin
    revisarlo, el ruteo dejaria de funcionar sin dar ninguna senal, y la
    consola simplemente se quedaria vacia.

    ``builtins.input`` y ``getpass.getpass`` si se parchean una sola vez: son
    reemplazos permanentes que nadie mas suele tocar.
    """
    global _ORIGINAL_INPUT, _ORIGINAL_GETPASS, _patched
    with _patch_lock:
        if not _patched:
            import builtins
            import getpass as getpass_module

            _ORIGINAL_INPUT = builtins.input
            _ORIGINAL_GETPASS = getpass_module.getpass

            builtins.input = lambda prompt="": _answer_prompt(prompt, secret=False)
            getpass_module.getpass = lambda prompt="Password: ", stream=None: _answer_prompt(
                prompt, secret=True
            )
            _patched = True

        # El isinstance evita anidar un enrutador dentro de otro cuando esto
        # se llama repetidamente.
        if not isinstance(sys.stdout, _StreamRouter):
            sys.stdout = _StreamRouter(sys.stdout, is_stderr=False)
        if not isinstance(sys.stderr, _StreamRouter):
            sys.stderr = _StreamRouter(sys.stderr, is_stderr=True)


# ---------------------------------------------------------------------------
# Lectura del notebook
# ---------------------------------------------------------------------------

def extract_code(notebook_json):
    # type: (Any) -> List[str]
    """Devuelve el codigo de las celdas ejecutables de un notebook.

    Se saltean las celdas de markdown, las vacias y las marcadas con el tag
    ``skip``, que es la forma de dejar una celda de exploracion en el
    notebook sin que el launcher la corra.
    """
    if not isinstance(notebook_json, dict):
        raise ValueError("el notebook no tiene el formato esperado")
    cells = notebook_json.get("cells") or []
    sources = []    # type: List[str]
    for cell in cells:
        if cell.get("cell_type") != "code":
            continue
        tags = (cell.get("metadata") or {}).get("tags") or []
        if "skip" in tags or "launcher:skip" in tags:
            continue
        source = cell.get("source") or ""
        if isinstance(source, list):
            source = "".join(source)
        if source.strip():
            sources.append(source)
    return sources


def transform_cell(source):
    # type: (str) -> str
    """Convierte la fuente de una celda en Python ejecutable.

    Los notebooks usan magics (``%time``, ``!comando``). Adentro de un kernel
    de IPython se traducen con el transformador propio de IPython, que es lo
    que corresponde. Fuera de IPython no hay como ejecutarlas, y se comentan
    en lugar de reventar: es mejor que la celda corra sin el ``%matplotlib``
    a que la corrida entera muera en la primera linea.
    """
    try:
        from IPython.core.interactiveshell import InteractiveShell
        shell = InteractiveShell.instance()
        return shell.input_transformer_manager.transform_cell(source)
    except Exception:
        pass

    lines = []      # type: List[str]
    for raw in source.splitlines():
        stripped = raw.lstrip()
        if stripped.startswith(("%", "!", "?")):
            lines.append(f"{raw[: len(raw) - len(stripped)]}# [launcher] magic omitido: {stripped}")
        else:
            lines.append(raw)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Corrida
# ---------------------------------------------------------------------------

class RunHandle:
    """Una corrida en curso o terminada."""

    def __init__(self, run_id, process, hub_id, sid):
        # type: (str, Process, str, str) -> None
        self.run_id = run_id
        self.process = process
        self.hub_id = hub_id
        self.sid = sid
        self.state = RunState.PENDING
        self.started_at = 0.0
        self.finished_at = 0.0
        self.message = ""
        self.thread = None          # type: Optional[threading.Thread]
        self.lines = 0
        self.warnings = 0
        self.errors = 0
        self._cancel_requested = False

    @property
    def elapsed(self):
        # type: () -> float
        if not self.started_at:
            return 0.0
        end = self.finished_at or time.time()
        return max(0.0, end - self.started_at)

    @property
    def is_active(self):
        # type: () -> bool
        return self.state in (RunState.PENDING, RunState.RUNNING)

    @property
    def cancel_requested(self):
        # type: () -> bool
        return self._cancel_requested

    def to_record(self):
        # type: () -> RunRecord
        def stamp(value):
            # type: (float) -> Optional[str]
            if not value:
                return None
            return datetime.fromtimestamp(value).strftime("%Y-%m-%dT%H:%M:%S")

        return RunRecord(
            run_id=self.run_id, hub_id=self.hub_id, process_id=self.process.id,
            process_name=self.process.name, sid=self.sid, state=self.state,
            started_at=stamp(self.started_at), finished_at=stamp(self.finished_at),
            duration_seconds=self.elapsed, lines=self.lines,
            warnings=self.warnings, errors=self.errors, message=self.message,
        )

    def __repr__(self):
        # type: () -> str
        return f"RunHandle({self.run_id!r}, {self.process.id!r}, {self.state})"


class RunManager:
    """Lanza, sigue y corta corridas.

    Es el unico lugar que ejecuta codigo de notebooks. Antes de arrancar
    consulta al repositorio, asi que no hay camino de ejecucion que se saltee
    la autorizacion.
    """

    def __init__(self, config, buffer=None, on_change=None, on_finished=None):
        # type: (Any, Any, Optional[Callable], Optional[Callable]) -> None
        self.config = config
        # `is not None` y no `or`: ConsoleBuffer define __len__, asi que un
        # buffer vacio es falsy y un `or` lo descartaria para crear otro. El
        # sintoma es peor que un buffer de mas -- las verificaciones sobre la
        # salida pasarian sobre un buffer que nadie escribio.
        self.buffer = (
            buffer if buffer is not None
            else console_mod.ConsoleBuffer(config.get("CONSOLE_MAX_LINES"))
        )
        self.max_concurrent = max(1, int(config.get("MAX_CONCURRENT_RUNS") or 1))
        self._semaphore = threading.BoundedSemaphore(self.max_concurrent)
        self._runs = {}     # type: Dict[str, RunHandle]
        self._lock = threading.RLock()
        self._on_change = on_change
        self._on_finished = on_finished
        install_patches()

    # -- consultas -----------------------------------------------------------

    def runs(self, hub_id=None):
        # type: (Optional[str]) -> List[RunHandle]
        with self._lock:
            items = list(self._runs.values())
        if hub_id:
            items = [r for r in items if r.hub_id == hub_id]
        return sorted(items, key=lambda r: r.started_at or 0, reverse=True)

    def active_runs(self, hub_id=None):
        # type: (Optional[str]) -> List[RunHandle]
        return [r for r in self.runs(hub_id) if r.is_active]

    def stats(self, hub_id=None):
        # type: (Optional[str]) -> Dict[str, int]
        """Los contadores del tablero."""
        counts = {"processes": 0, "running": 0, "completed": 0, "failed": 0}
        for run in self.runs(hub_id):
            if run.is_active:
                counts["running"] += 1
            elif run.state in (RunState.DONE, RunState.WARN):
                counts["completed"] += 1
            elif run.state in RunState.FAILED:
                counts["failed"] += 1
        return counts

    def get(self, run_id):
        # type: (str) -> Optional[RunHandle]
        with self._lock:
            return self._runs.get(run_id)

    # -- ejecucion -----------------------------------------------------------

    def start(self, process, hub_id, sid, notebook_source, credentials=None):
        # type: (Process, str, str, str, Any) -> RunHandle
        """Arranca una corrida y devuelve su handle enseguida.

        ``notebook_source`` es el JSON del notebook ya leido del share: el
        motor no habla con el share, para que se pueda testear sin uno.
        """
        run_id = uuid.uuid4().hex[:12]
        handle = RunHandle(run_id, process, hub_id, sid)
        with self._lock:
            self._runs[run_id] = handle

        answers = {
            "SID": credentials.sid if credentials else sid,
            "PASSWORD": credentials.password if credentials else "",
        }
        thread = threading.Thread(
            target=self._execute, name="run-" + run_id,
            args=(handle, notebook_source, answers), daemon=True,
        )
        handle.thread = thread
        thread.start()
        return handle

    def _execute(self, handle, notebook_source, answers):
        # type: (RunHandle, str, Dict[str, str]) -> None
        process = handle.process
        source_id = process.id

        # La espera por un lugar libre pasa adentro del hilo, no en start(),
        # para que la UI no se congele cuando la cola esta llena.
        if not self._semaphore.acquire(timeout=0.1):
            self.buffer.append(
                f"En cola: hay {self.max_concurrent} corridas activas (maximo configurado).",
                level=console_mod.SYSTEM, source=source_id,
            )
            self._semaphore.acquire()

        if handle.cancel_requested:
            self._finish(handle, RunState.CANCELLED, "Cancelado antes de arrancar")
            self._semaphore.release()
            return

        # Se revalida aca y no solo en __init__: entre la construccion del
        # manager y esta corrida pudo haber pasado cualquier cosa con los
        # streams del proceso.
        install_patches()

        context = _RunContext(handle.run_id, process, self.buffer, answers)
        handle.state = RunState.RUNNING
        handle.started_at = time.time()
        self._changed()

        stats_before = self.buffer.stats
        self.buffer.append(
            f"▶ {process.name} — {process.notebook}",
            level=console_mod.SYSTEM, source=source_id,
        )

        previous_env = self._inject_env(answers, process)
        _register_context(context)
        state = RunState.DONE
        message = ""
        try:
            self._run_notebook(handle, notebook_source, context)
        except RunCancelled:
            state = RunState.CANCELLED
            message = "Cancelado por el usuario"
            self.buffer.append("■ Cancelado.", level=console_mod.WARN, source=source_id)
        except BaseException as exc:                       # noqa: BLE001
            state = RunState.ERROR
            message = redactor.scrub(f"{type(exc).__name__}: {exc}")
            for line in _notebook_traceback(exc):
                self.buffer.append(line, level=console_mod.ERROR, source=source_id)
        finally:
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            except Exception:
                pass
            _unregister_context()
            self._restore_env(previous_env)
            self._semaphore.release()

        # Resultado: el estado explicito gana; si no, se deduce de la salida,
        # igual que hacia la version original de la herramienta.
        stats_after = self.buffer.stats
        handle.lines = stats_after["lines"] - stats_before["lines"]
        handle.warnings = stats_after["warnings"] - stats_before["warnings"]
        handle.errors = stats_after["errors"] - stats_before["errors"]

        # Se decide por los niveles que quedaron en la consola, no por el
        # stream: un notebook puede escribir a stderr sin haber fallado.
        if state == RunState.DONE:
            if handle.errors:
                state = RunState.ERROR
                message = "El proceso imprimio errores sin levantar excepcion"
            elif handle.warnings:
                state = RunState.WARN
                message = "Termino con advertencias"

        self._finish(handle, state, message)

    def _run_notebook(self, handle, notebook_source, context):
        # type: (RunHandle, str, _RunContext) -> None
        """Ejecuta las celdas de codigo del notebook, en orden."""
        try:
            notebook = json.loads(notebook_source)
        except ValueError as exc:
            raise ValueError(f"no se pudo leer el notebook: {exc}") from exc

        cells = extract_code(notebook)
        if not cells:
            self.buffer.append(
                "El notebook no tiene celdas de codigo ejecutables.",
                level=console_mod.WARN, source=handle.process.id,
            )
            return

        # Namespace propio por corrida: dos procesos en paralelo no comparten
        # variables, y nada de lo que definan se filtra al kernel de la UI.
        namespace = {
            "__name__": "__launcher__",
            "__file__": handle.process.notebook,
            "__builtins__": __builtins__,
        }
        # Los parametros del proceso entran como variables, al estilo de
        # papermill pero sin necesitar la dependencia.
        namespace.update(handle.process.parameters)

        deadline = self._deadline(handle.process)
        for index, source in enumerate(cells, start=1):
            if handle.cancel_requested:
                raise RunCancelled()
            if deadline and time.time() > deadline:
                raise TimeoutError(
                    f"supero el limite de {handle.process.timeout_seconds}s"
                )
            code = transform_cell(source)
            try:
                compiled = compile(code, f"<celda {index}>", "exec")
            except SyntaxError as exc:
                raise SyntaxError(
                    f"error de sintaxis en la celda {index}: {exc}"
                ) from exc
            exec(compiled, namespace)      # noqa: S102

    def _deadline(self, process):
        # type: (Process) -> float
        timeout = process.timeout_seconds or int(self.config.get("DEFAULT_TIMEOUT_SECONDS") or 0)
        return time.time() + timeout if timeout else 0.0

    # -- entorno -------------------------------------------------------------

    def _inject_env(self, answers, process):
        # type: (Dict[str, str], Process) -> Dict[str, Optional[str]]
        """Publica SID/PASSWORD como variables de entorno para el notebook.

        Se pasan por entorno y no por linea de comandos justamente porque
        ``ps``/Administrador de tareas muestran los argumentos de un proceso a
        cualquiera en la maquina, y el entorno no.
        """
        values = {
            "SID": answers.get("SID", ""),
            "PASSWORD": answers.get("PASSWORD", ""),
            "LAUNCHER_PROCESS_ID": process.id,
            "LAUNCHER_HUB_ID": process.hub_id,
        }
        previous = {}   # type: Dict[str, Optional[str]]
        for key, value in values.items():
            previous[key] = os.environ.get(key)
            if value:
                os.environ[key] = value
        return previous

    @staticmethod
    def _restore_env(previous):
        # type: (Dict[str, Optional[str]]) -> None
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # -- cancelacion ---------------------------------------------------------

    def stop(self, run_id):
        # type: (str) -> bool
        """Pide cortar una corrida. Ver la nota del encabezado sobre limites."""
        handle = self.get(run_id)
        if handle is None or not handle.is_active:
            return False
        handle._cancel_requested = True
        thread = handle.thread
        if thread is None or not thread.is_alive():
            return False
        self.buffer.append(
            f"Cancelando {handle.process.name}…",
            level=console_mod.SYSTEM, source=handle.process.id,
        )
        return _raise_in_thread(thread.ident, RunCancelled)

    def stop_all(self, hub_id=None):
        # type: (Optional[str]) -> int
        return sum(1 for run in self.active_runs(hub_id) if self.stop(run.run_id))

    # -- notificacion --------------------------------------------------------

    def _finish(self, handle, state, message):
        # type: (RunHandle, str, str) -> None
        handle.state = state
        handle.message = message
        handle.finished_at = time.time()
        icon = {
            RunState.DONE: "✓", RunState.WARN: "▲", RunState.ERROR: "✕",
            RunState.CANCELLED: "■", RunState.TIMEOUT: "⏱",
        }.get(state, "•")
        level = {
            RunState.DONE: console_mod.SUCCESS, RunState.WARN: console_mod.WARN,
            RunState.ERROR: console_mod.ERROR, RunState.TIMEOUT: console_mod.ERROR,
        }.get(state, console_mod.SYSTEM)
        self.buffer.append(
            "{} {} — {} en {:.1f}s{}".format(
                icon, handle.process.name, state, handle.elapsed,
                f" ({message})" if message else "",
            ),
            level=level, source=handle.process.id,
        )
        self._changed()
        if self._on_finished is not None:
            try:
                self._on_finished(handle)
            except Exception:
                pass

    def _changed(self):
        # type: () -> None
        if self._on_change is not None:
            try:
                self._on_change()
            except Exception:
                pass


def _notebook_traceback(exc):
    # type: (BaseException) -> List[str]
    """Traceback recortado a las celdas del notebook.

    El traceback completo arranca con los frames del propio launcher
    (``_execute``, ``_run_notebook``, el ``exec``), que no le dicen nada a
    quien esta mirando por que fallo su proceso y empujan hacia abajo la
    unica linea que importa. Se descarta todo lo anterior a la primera celda.

    Si no se encuentra ninguna celda -- porque el error fue del propio motor,
    no del notebook -- se devuelve el traceback completo: ahi los frames del
    launcher si son la informacion util.
    """
    lines = redactor.scrub(traceback.format_exc()).splitlines()
    start = None
    for index, line in enumerate(lines):
        if "<celda " in line:
            start = index
            break
    if start is None:
        return lines
    return ["Traceback (celdas del notebook):"] + lines[start:]


def _raise_in_thread(thread_id, exception_type):
    # type: (Optional[int], type) -> bool
    """Inyecta una excepcion en otro hilo mediante la API de CPython."""
    if not thread_id:
        return False
    count = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(thread_id), ctypes.py_object(exception_type)
    )
    if count > 1:
        # Se afecto mas de un hilo: se deshace para no dejar el interprete en
        # un estado raro.
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread_id), None)
        return False
    return count == 1
