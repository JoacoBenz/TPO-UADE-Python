"""Agregaciones del tab de metricas."""

from __future__ import annotations

import pytest

from automation_launcher.core.metrics import HubMetrics, percentile


def run(process_id, state, duration=10.0, sid="ana.g", day="2026-09-04"):
    return {"process_id": process_id, "process_name": process_id.upper(),
            "state": state, "duration_seconds": duration, "sid": sid,
            "started_at": day + "T10:00:00"}


@pytest.mark.parametrize("valores,fraccion,esperado", [
    ([], 0.5, 0.0),
    ([5], 0.5, 5.0),
    ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.5, 5.5),
    ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.95, 9.55),
    ([1, 2, 3], 0.0, 1.0),
    ([1, 2, 3], 1.0, 3.0),
])
def test_percentile(valores, fraccion, esperado):
    """Implementado a mano porque statistics.quantiles es de Python 3.8."""
    assert percentile(valores, fraccion) == pytest.approx(esperado)


def test_las_canceladas_no_castigan_la_tasa_de_exito():
    """El usuario aborto: no es una falla del proceso. Contarlas castigaria a
    los procesos largos que la gente corta seguido."""
    m = HubMetrics("h", [run("a", "done"), run("a", "cancelled"), run("a", "cancelled")])
    assert m.success_rate == 100.0


def test_cuenta_por_estado():
    m = HubMetrics("h", [run("a", "done"), run("a", "warn"),
                         run("a", "error"), run("a", "timeout")])
    assert (m.ok, m.warn, m.failed) == (1, 1, 2)
    assert m.success_rate == pytest.approx(50.0)


def test_agrupa_por_proceso_y_ordena_por_uso():
    m = HubMetrics("h", [run("a", "done")] * 3 + [run("b", "done")] * 5)
    assert list(m.by_process) == ["b", "a"]
    assert m.by_process["b"].total == 5


def test_most_fragile_ignora_los_de_pocas_corridas():
    """Un proceso nuevo que fallo una vez no puede encabezar la lista con 0%
    y tapar al que viene fallando hace dos semanas."""
    registros = [run("nuevo", "error")]
    registros += [run("cronico", "error")] * 4 + [run("cronico", "done")] * 6
    fragiles = [s.process_id for s in HubMetrics("h", registros).most_fragile(min_runs=3)]
    assert fragiles == ["cronico"]


def test_serie_diaria_ordenada():
    m = HubMetrics("h", [run("a", "done", day="2026-09-02"),
                         run("a", "error", day="2026-09-01"),
                         run("a", "done", day="2026-09-01")])
    serie = m.daily_series()
    assert [d["day"] for d in serie] == ["2026-09-01", "2026-09-02"]
    assert serie[0] == {"day": "2026-09-01", "total": 2, "failed": 1}


def test_top_users():
    m = HubMetrics("h", [run("a", "done", sid="ana.g")] * 3
                        + [run("a", "done", sid="joaquin.benz")])
    assert m.top_users(1) == [("ana.g", 3)]


def test_historial_vacio_no_rompe():
    m = HubMetrics("h", [])
    assert m.total == 0
    assert m.success_rate == 0.0
    assert m.daily_series() == []


def test_registros_corruptos_no_rompen():
    """El historial se lee de archivos que pueden venir mal escritos."""
    m = HubMetrics("h", [{"process_id": "a", "state": "done",
                          "duration_seconds": "no-es-un-numero"}])
    assert m.total == 1
