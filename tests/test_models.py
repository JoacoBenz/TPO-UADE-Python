"""Modelos y tablas de codigos de AFIP."""

from __future__ import annotations

from datetime import date

import pytest

from afip_facturacion.core.models import (
    CBTE_TIPO_RECIBO_C,
    CONCEPTO_PRODUCTOS,
    CONCEPTO_SERVICIOS,
    CONDICION_IVA_CONSUMIDOR_FINAL,
    CONDICION_IVA_MONOTRIBUTO,
    ComprobanteRequest,
    ComprobanteResultado,
    EmisorConfig,
    resolver_condicion_iva,
)


def test_recibo_c_es_el_codigo_15():
    """Verificado contra la tabla oficial de tipos de comprobante."""
    assert CBTE_TIPO_RECIBO_C == 15


@pytest.mark.parametrize("entrada,esperado", [
    (None, CONDICION_IVA_CONSUMIDOR_FINAL),
    ("", CONDICION_IVA_CONSUMIDOR_FINAL),
    ("   ", CONDICION_IVA_CONSUMIDOR_FINAL),
    ("Consumidor Final", CONDICION_IVA_CONSUMIDOR_FINAL),
    ("consumidor final", CONDICION_IVA_CONSUMIDOR_FINAL),
    ("Responsable Monotributo", CONDICION_IVA_MONOTRIBUTO),
    ("monotributo", CONDICION_IVA_MONOTRIBUTO),
    (6, CONDICION_IVA_MONOTRIBUTO),
    ("6", CONDICION_IVA_MONOTRIBUTO),
])
def test_resolver_condicion_iva(entrada, esperado):
    assert resolver_condicion_iva(entrada) == esperado


def test_condicion_iva_desconocida_lista_las_validas():
    """El error tiene que decir que poner, no solo que esta mal."""
    with pytest.raises(ValueError) as error:
        resolver_condicion_iva("responsable no inscripto")
    assert "consumidor final" in str(error.value)


def test_comprobante_rechaza_importe_no_positivo():
    for importe in (0, -100):
        with pytest.raises(ValueError):
            ComprobanteRequest(doc_nro="30111222", importe=importe, fecha=date.today())


def test_comprobante_rechaza_documento_vacio():
    with pytest.raises(ValueError):
        ComprobanteRequest(doc_nro="  ", importe=100, fecha=date.today())


def test_emisor_normaliza_el_cuit():
    assert EmisorConfig(cuit="20-11122233-4", punto_venta=1).cuit == "20111222334"


def test_emisor_rechaza_cuit_de_largo_incorrecto():
    for cuit in ("123", "2011122233", "201112223345"):
        with pytest.raises(ValueError):
            EmisorConfig(cuit=cuit, punto_venta=1)


def test_requiere_periodo_solo_con_servicios():
    """Con Productos, AFIP rechaza el comprobante si van las fechas de servicio."""
    assert EmisorConfig(cuit="20111222334", punto_venta=1,
                        concepto=CONCEPTO_SERVICIOS).requiere_periodo
    assert not EmisorConfig(cuit="20111222334", punto_venta=1,
                            concepto=CONCEPTO_PRODUCTOS).requiere_periodo


def test_etiqueta_del_resultado_identifica_la_fila():
    """Para que un rechazo se pueda ubicar en el Excel sin adivinar."""
    solicitud = ComprobanteRequest(doc_nro="30111222", importe=100, fecha=date.today(),
                                   nombre="Ana Perez", fila_excel=7)
    assert ComprobanteResultado(solicitud, aprobado=False).etiqueta == "fila 7 (Ana Perez)"


def test_etiqueta_cae_al_documento_sin_nombre():
    solicitud = ComprobanteRequest(doc_nro="30111222", importe=100, fecha=date.today())
    assert ComprobanteResultado(solicitud, aprobado=True).etiqueta == "30111222"
