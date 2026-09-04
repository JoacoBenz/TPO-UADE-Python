"""El motor: ejecucion, resultado, cancelacion, concurrencia y credenciales."""

from __future__ import annotations

import json
import time

from automation_launcher.core.config import LauncherConfig
from automation_launcher.core.console import ConsoleBuffer
from automation_launcher.core.engine import RunManager, extract_code, transform_cell
from automation_launcher.core.models import Credentials, Process, RunState
from automation_launcher.core.secrets import redactor


def notebook(*fuentes):
    return json.dumps({
        "cells": [{"cell_type": "code", "metadata": {}, "source": s} for s in fuentes]
        + [{"cell_type": "markdown", "metadata": {}, "source": "# no ejecutable"}],
        "nbformat": 4, "nbformat_minor": 5,
    })


def proceso(pid="p", timeout=60):
    return Process(id=pid, name=pid, notebook="n.ipynb", hub_id="h", timeout_seconds=timeout)


def manager(max_concurrent=3):
    buffer = ConsoleBuffer(2000)
    config = LauncherConfig({"MAX_CONCURRENT_RUNS": max_concurrent})
    return RunManager(config, buffer=buffer), buffer


def esperar(handle, limite=30):
    inicio = time.time()
    while handle.is_active and time.time() - inicio < limite:
        time.sleep(0.05)
    return handle


# ---------------------------------------------------------------------------
# Lectura del notebook
# ---------------------------------------------------------------------------

def test_extract_code_ignora_markdown_y_vacias():
    data = json.loads(notebook("print(1)", "", "print(2)"))
    assert extract_code(data) == ["print(1)", "print(2)"]


def test_extract_code_respeta_el_tag_skip():
    """Permite dejar celdas de exploracion sin que el launcher las corra."""
    data = {"cells": [
        {"cell_type": "code", "metadata": {"tags": ["skip"]}, "source": "romper()"},
        {"cell_type": "code", "metadata": {}, "source": "print(1)"},
    ]}
    assert extract_code(data) == ["print(1)"]


def test_extract_code_acepta_source_como_lista():
    """nbformat guarda `source` como lista de lineas tanto como string."""
    data = {"cells": [{"cell_type": "code", "metadata": {},
                       "source": ["a = 1\n", "print(a)\n"]}]}
    assert extract_code(data) == ["a = 1\nprint(a)\n"]


def test_transform_cell_no_rompe_con_magics():
    """Sin IPython las magics se comentan: mejor que matar la corrida entera."""
    resultado = transform_cell("%matplotlib inline\nx = 1")
    assert "x = 1" in resultado
    assert compile(resultado, "<t>", "exec")


# ---------------------------------------------------------------------------
# Resultado de la corrida
# ---------------------------------------------------------------------------

def test_una_corrida_limpia_termina_en_done():
    mgr, _buffer = manager()
    handle = esperar(mgr.start(proceso(), "h", "ana.g", notebook("print('ok, 0 errors')")))
    assert handle.state == RunState.DONE


def test_una_excepcion_termina_en_error():
    mgr, _buffer = manager()
    handle = esperar(mgr.start(proceso(), "h", "ana.g",
                               notebook("raise ValueError('falta el archivo')")))
    assert handle.state == RunState.ERROR
    assert "ValueError" in handle.message


def test_escribir_a_stderr_no_es_por_si_solo_un_error():
    """Escribir a stderr no significa que la corrida fallo.

    warnings.warn, logging y las barras de progreso escriben a stderr todo el
    tiempo. Tratar 'escribio a stderr' como fallo pinta de rojo a media
    biblioteca de Python.

    Se escribe a stderr directamente en vez de usar ``warnings.warn`` porque
    el plugin de warnings de pytest lo intercepta y nunca llegaria al stream,
    con lo que el test pasaria sin probar nada.
    """
    mgr, _buffer = manager()
    handle = esperar(mgr.start(proceso(), "h", "ana.g", notebook(
        "import sys\n"
        "sys.stderr.write('UserWarning: el archivo del custodio llego tarde\\n')")))
    assert handle.state == RunState.WARN


def test_un_traceback_en_stderr_si_es_error():
    """La contracara: stderr con contenido de error si tiene que ser rojo."""
    mgr, _buffer = manager()
    handle = esperar(mgr.start(proceso(), "h", "ana.g", notebook(
        "import sys\nsys.stderr.write('ConnectionError: se corto el link\\n')")))
    assert handle.state == RunState.ERROR


def test_un_error_impreso_sin_excepcion_igual_es_error():
    mgr, _buffer = manager()
    handle = esperar(mgr.start(proceso(), "h", "ana.g",
                               notebook("print('ValueError: algo salio mal')")))
    assert handle.state == RunState.ERROR


def test_un_notebook_sin_celdas_no_rompe():
    mgr, buffer = manager()
    handle = esperar(mgr.start(proceso(), "h", "ana.g", json.dumps({"cells": []})))
    assert handle.state in (RunState.DONE, RunState.WARN)


def test_un_notebook_ilegible_termina_en_error():
    mgr, _buffer = manager()
    handle = esperar(mgr.start(proceso(), "h", "ana.g", "esto no es json"))
    assert handle.state == RunState.ERROR


def test_un_error_de_sintaxis_dice_que_celda():
    mgr, _buffer = manager()
    handle = esperar(mgr.start(proceso(), "h", "ana.g", notebook("x = 1", "def (")))
    assert handle.state == RunState.ERROR
    assert "celda 2" in handle.message


# ---------------------------------------------------------------------------
# Credenciales
# ---------------------------------------------------------------------------

def test_getpass_e_input_se_responden_solos():
    """Es la razon de ser del login: sin esto los procesos se cuelgan."""
    mgr, buffer = manager()
    creds = Credentials(sid="ana.g", password="Tr3as*ry!2026")
    redactor.remember(creds.password)
    handle = esperar(mgr.start(proceso(), "h", "ana.g", notebook(
        "import getpass\n"
        "u = input('Usuario de red: ')\n"
        "p = getpass.getpass('Contrasena: ')\n"
        "assert u == 'ana.g', u\n"
        "assert p == 'Tr3as*ry!2026', 'password mal inyectado'\n"
        "print('credenciales ok')"
    ), creds))
    assert handle.state == RunState.DONE, handle.message


def test_sid_y_password_llegan_por_entorno():
    """Por entorno y no por argv: los argumentos de un proceso son visibles
    para cualquiera en la maquina."""
    mgr, _buffer = manager()
    creds = Credentials(sid="ana.g", password="Tr3as*ry!2026")
    redactor.remember(creds.password)
    handle = esperar(mgr.start(proceso(), "h", "ana.g", notebook(
        "import os\n"
        "assert os.environ['SID'] == 'ana.g'\n"
        "assert os.environ['PASSWORD'] == 'Tr3as*ry!2026'\n"
        "print('entorno ok')"
    ), creds))
    assert handle.state == RunState.DONE, handle.message


def test_el_password_nunca_llega_a_la_consola_ni_al_historial():
    """La afirmacion mas importante del proyecto.

    El notebook intenta filtrarlo de las tres formas en que suele escaparse:
    desde el entorno, desde el valor devuelto por getpass, e interpolado en
    una cadena.
    """
    password = "Tr3as*ry!2026"
    mgr, buffer = manager()
    creds = Credentials(sid="ana.g", password=password)
    redactor.remember(password)
    handle = esperar(mgr.start(proceso(), "h", "ana.g", notebook(
        "import os, getpass\n"
        "clave = getpass.getpass('Contrasena: ')\n"
        "print('entorno:', os.environ.get('PASSWORD'))\n"
        "print('getpass:', clave)\n"
        "print('url: https://x?pass=%s' % clave)\n"
    ), creds))

    assert handle.state == RunState.DONE
    consola = buffer.text()
    assert password not in consola
    assert redactor.is_clean(consola)
    assert password not in json.dumps(handle.to_record().to_dict())


def test_el_entorno_se_restaura_al_terminar():
    import os
    previo = os.environ.get("PASSWORD")
    mgr, _buffer = manager()
    creds = Credentials(sid="ana.g", password="Tr3as*ry!2026")
    redactor.remember(creds.password)
    esperar(mgr.start(proceso(), "h", "ana.g", notebook("pass"), creds))
    assert os.environ.get("PASSWORD") == previo


# ---------------------------------------------------------------------------
# Cancelacion y concurrencia
# ---------------------------------------------------------------------------

def test_stop_cancela_una_corrida_larga():
    mgr, _buffer = manager()
    handle = mgr.start(proceso(), "h", "ana.g", notebook(
        "import time\nfor i in range(300): time.sleep(0.05)"))
    time.sleep(1.0)
    assert handle.state == RunState.RUNNING
    assert mgr.stop(handle.run_id)
    esperar(handle, 10)
    assert handle.state == RunState.CANCELLED


def test_stop_sobre_algo_terminado_no_hace_nada():
    mgr, _buffer = manager()
    handle = esperar(mgr.start(proceso(), "h", "ana.g", notebook("pass")))
    assert not mgr.stop(handle.run_id)
    assert not mgr.stop("no-existe")


def test_las_corridas_concurrentes_no_se_mezclan():
    """Con el parche global ingenuo, la salida de un proceso aparece en la
    consola del otro. Cada linea tiene que quedar atribuida a su proceso."""
    mgr, buffer = manager(max_concurrent=3)
    handles = [
        mgr.start(proceso(f"p{i}"), "h", "ana.g",
                  notebook("import time\nfor i in range(5):\n"
                           f"    print('soy {i}', i)\n    time.sleep(0.05)"))
        for i in range(3)
    ]
    for handle in handles:
        esperar(handle)
    assert all(h.state == RunState.DONE for h in handles)
    for i in range(3):
        lineas = buffer.lines(source=f"p{i}")
        assert lineas
        assert all(line.source == f"p{i}" for line in lineas)


def test_el_limite_de_concurrencia_se_respeta():
    mgr, _buffer = manager(max_concurrent=1)
    lento = notebook("import time\ntime.sleep(1.2)")
    primero = mgr.start(proceso("a"), "h", "ana.g", lento)
    time.sleep(0.3)
    segundo = mgr.start(proceso("b"), "h", "ana.g", lento)
    time.sleep(0.3)
    activos = [h for h in (primero, segundo) if h.state == RunState.RUNNING]
    assert len(activos) == 1
    esperar(primero, 15)
    esperar(segundo, 15)
    assert primero.state == RunState.DONE
    assert segundo.state == RunState.DONE


def test_stats_cuenta_bien():
    mgr, _buffer = manager()
    esperar(mgr.start(proceso("ok"), "h", "ana.g", notebook("pass")))
    esperar(mgr.start(proceso("mal"), "h", "ana.g", notebook("raise RuntimeError('x')")))
    stats = mgr.stats("h")
    assert stats["completed"] == 1
    assert stats["failed"] == 1
    assert stats["running"] == 0


def test_los_namespaces_no_se_comparten():
    """Dos corridas en paralelo no pueden pisarse las variables."""
    mgr, _buffer = manager()
    primero = esperar(mgr.start(proceso("a"), "h", "ana.g", notebook("secreto_local = 42")))
    segundo = esperar(mgr.start(proceso("b"), "h", "ana.g",
                                notebook("assert 'secreto_local' not in dir()")))
    assert primero.state == RunState.DONE
    assert segundo.state == RunState.DONE


def test_los_parametros_llegan_como_variables():
    mgr, _buffer = manager()
    proc = proceso()
    proc.parameters = {"run_date": "2026-09-04", "reintentos": 3}
    handle = esperar(mgr.start(proc, "h", "ana.g", notebook(
        "assert run_date == '2026-09-04'\nassert reintentos == 3\nprint('params ok')")))
    assert handle.state == RunState.DONE, handle.message


def test_el_buffer_que_se_pasa_es_el_que_se_usa():
    """ConsoleBuffer define __len__, asi que uno vacio es falsy: con `or` en
    vez de `is not None` el manager crearia otro y la salida se perderia."""
    buffer = ConsoleBuffer(100)
    mgr = RunManager(LauncherConfig({}), buffer=buffer)
    assert mgr.buffer is buffer
    esperar(mgr.start(proceso(), "h", "ana.g", notebook("print('hola')")))
    assert any("hola" in line.text for line in buffer.lines())
