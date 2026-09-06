"""Cliente WSFEv1: armado del pedido, numeracion y lectura de la respuesta."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from afip_facturacion.core.models import (
    CONCEPTO_PRODUCTOS,
    CONDICION_IVA_MONOTRIBUTO,
    EmisorConfig,
)
from afip_facturacion.core.wsfe import MAX_POR_LOTE, WSFE, WSFEError


class ServicioFalso:
    """Un WSFEv1 de mentira: guarda los pedidos y contesta lo que se le diga."""

    def __init__(self, ultimo=41, resultados=None, errores_request=None):
        self.pedidos = []
        self.ultimo = ultimo
        self.resultados = resultados      # lista de "A"/"R" por comprobante
        self.errores_request = errores_request

    def FECompUltimoAutorizado(self, Auth, PtoVta, CbteTipo):   # noqa: N803
        self.pedidos.append(("ultimo", Auth, PtoVta, CbteTipo))
        return SimpleNamespace(CbteNro=self.ultimo, Errors=None)

    def FECAESolicitar(self, Auth, FeCAEReq):                   # noqa: N803
        self.pedidos.append(("cae", Auth, FeCAEReq))
        if self.errores_request:
            return SimpleNamespace(
                FeDetResp=None,
                Errors=SimpleNamespace(Err=[
                    SimpleNamespace(Code=c, Msg=m) for c, m in self.errores_request
                ]),
            )
        detalles = []
        for indice, item in enumerate(FeCAEReq["FeDetReq"]):
            numero = item["FECAEDetRequest"]["CbteDesde"]
            estado = self.resultados[indice] if self.resultados else "A"
            if estado == "A":
                detalles.append(SimpleNamespace(
                    Resultado="A", CbteDesde=numero, CAE=f"7510{numero}",
                    CAEFchVto="20260916", Observaciones=None))
            else:
                detalles.append(SimpleNamespace(
                    Resultado="R", CbteDesde=numero, CAE=None, CAEFchVto=None,
                    Observaciones=SimpleNamespace(Obs=[
                        SimpleNamespace(Code=10015, Msg="Documento invalido")])))
        return SimpleNamespace(
            FeDetResp=SimpleNamespace(FECAEDetResponse=detalles), Errors=None)


def _cliente(emisor, wsaa_falso, servicio):
    return WSFE(emisor, wsaa_falso, cliente_soap=SimpleNamespace(service=servicio))


# ---------------------------------------------------------------------------
# Armado del pedido
# ---------------------------------------------------------------------------

def test_el_pedido_incluye_la_condicion_iva_del_receptor(emisor, wsaa_falso, hacer_comprobante):
    """Obligatorio desde el 1/9/2026: sin este campo AFIP rechaza el comprobante."""
    servicio = ServicioFalso()
    _cliente(emisor, wsaa_falso, servicio).solicitar_cae([hacer_comprobante()])
    detalle = servicio.pedidos[-1][2]["FeDetReq"][0]["FECAEDetRequest"]
    assert "CondicionIVAReceptorId" in detalle
    assert detalle["CondicionIVAReceptorId"] == 5      # Consumidor Final


def test_la_condicion_iva_de_la_fila_se_respeta(emisor, wsaa_falso, hacer_comprobante):
    servicio = ServicioFalso()
    _cliente(emisor, wsaa_falso, servicio).solicitar_cae(
        [hacer_comprobante(condicion_iva=CONDICION_IVA_MONOTRIBUTO)])
    detalle = servicio.pedidos[-1][2]["FeDetReq"][0]["FECAEDetRequest"]
    assert detalle["CondicionIVAReceptorId"] == CONDICION_IVA_MONOTRIBUTO


def test_un_comprobante_c_no_discrimina_iva(emisor, wsaa_falso, hacer_comprobante):
    """En un comprobante C el total va integro en ImpNeto y el IVA en cero.

    Mandar ImpIVA distinto de cero en un comprobante C hace que AFIP lo
    rechace, porque el emisor monotributista no discrimina IVA.
    """
    servicio = ServicioFalso()
    _cliente(emisor, wsaa_falso, servicio).solicitar_cae([hacer_comprobante(importe=21500)])
    detalle = servicio.pedidos[-1][2]["FeDetReq"][0]["FECAEDetRequest"]
    assert detalle["ImpTotal"] == 21500
    assert detalle["ImpNeto"] == 21500
    assert detalle["ImpIVA"] == 0
    assert detalle["ImpTrib"] == 0
    assert detalle["ImpOpEx"] == 0
    assert detalle["ImpTotConc"] == 0


def test_las_fechas_van_en_formato_afip(emisor, wsaa_falso, hacer_comprobante):
    servicio = ServicioFalso()
    _cliente(emisor, wsaa_falso, servicio).solicitar_cae([hacer_comprobante()])
    detalle = servicio.pedidos[-1][2]["FeDetReq"][0]["FECAEDetRequest"]
    assert detalle["CbteFch"] == "20260727"
    assert detalle["FchServDesde"] == "20260701"
    assert detalle["FchServHasta"] == "20260731"
    assert detalle["FchVtoPago"] == "20260731"


def test_con_concepto_productos_no_se_manda_el_periodo(wsaa_falso, hacer_comprobante):
    """AFIP rechaza el comprobante si van fechas de servicio con Concepto=Productos."""
    emisor = EmisorConfig(cuit="20111222334", punto_venta=1, concepto=CONCEPTO_PRODUCTOS)
    servicio = ServicioFalso()
    _cliente(emisor, wsaa_falso, servicio).solicitar_cae([hacer_comprobante()])
    detalle = servicio.pedidos[-1][2]["FeDetReq"][0]["FECAEDetRequest"]
    assert "FchServDesde" not in detalle
    assert "FchServHasta" not in detalle
    assert "FchVtoPago" not in detalle


def test_sin_periodo_cargado_usa_la_fecha_del_hacer_comprobante(emisor, wsaa_falso, hacer_comprobante):
    """Con Servicios las fechas son obligatorias: hay que mandar algo coherente."""
    servicio = ServicioFalso()
    _cliente(emisor, wsaa_falso, servicio).solicitar_cae(
        [hacer_comprobante(periodo_desde=None, periodo_hasta=None, vencimiento_pago=None)])
    detalle = servicio.pedidos[-1][2]["FeDetReq"][0]["FECAEDetRequest"]
    assert detalle["FchServDesde"] == detalle["FchServHasta"] == "20260727"
    assert detalle["FchVtoPago"] == "20260727"


def test_la_cabecera_declara_la_cantidad_real(emisor, wsaa_falso, hacer_comprobante):
    servicio = ServicioFalso()
    _cliente(emisor, wsaa_falso, servicio).solicitar_cae([hacer_comprobante(), hacer_comprobante()])
    cabecera = servicio.pedidos[-1][2]["FeCabReq"]
    assert cabecera == {"CantReg": 2, "PtoVta": 1, "CbteTipo": 15}


def test_el_auth_lleva_token_sign_y_cuit(emisor, wsaa_falso, hacer_comprobante):
    servicio = ServicioFalso()
    _cliente(emisor, wsaa_falso, servicio).solicitar_cae([hacer_comprobante()])
    auth = servicio.pedidos[-1][1]
    assert auth == {"Token": "TOKEN", "Sign": "SIGN", "Cuit": "20111222334"}


# ---------------------------------------------------------------------------
# Numeracion
# ---------------------------------------------------------------------------

def test_numera_correlativo_desde_el_ultimo_autorizado(emisor, wsaa_falso, hacer_comprobante):
    servicio = ServicioFalso(ultimo=41)
    resultados = _cliente(emisor, wsaa_falso, servicio).solicitar_cae(
        [hacer_comprobante(), hacer_comprobante(), hacer_comprobante()])
    assert [r.numero for r in resultados] == [42, 43, 44]


def test_se_puede_forzar_el_numero_inicial(emisor, wsaa_falso, hacer_comprobante):
    """Sirve para reintentar un lote sin volver a consultar la numeracion."""
    servicio = ServicioFalso(ultimo=41)
    resultados = _cliente(emisor, wsaa_falso, servicio).solicitar_cae(
        [hacer_comprobante()], numero_inicial=100)
    assert resultados[0].numero == 100
    assert not any(p[0] == "ultimo" for p in servicio.pedidos)


def test_un_lote_grande_se_parte_respetando_la_numeracion(emisor, wsaa_falso, hacer_comprobante):
    """AFIP acepta hasta MAX_POR_LOTE por llamada; los numeros no se pisan."""
    servicio = ServicioFalso(ultimo=0)
    cantidad = MAX_POR_LOTE + 5
    resultados = _cliente(emisor, wsaa_falso, servicio).solicitar_cae(
        [hacer_comprobante() for _ in range(cantidad)])

    llamadas_cae = [p for p in servicio.pedidos if p[0] == "cae"]
    assert len(llamadas_cae) == 2
    assert [r.numero for r in resultados] == list(range(1, cantidad + 1))


# ---------------------------------------------------------------------------
# Lectura de la respuesta
# ---------------------------------------------------------------------------

def test_aprobado_trae_cae_y_vencimiento(emisor, wsaa_falso, hacer_comprobante):
    servicio = ServicioFalso(ultimo=41)
    resultado = _cliente(emisor, wsaa_falso, servicio).solicitar_cae([hacer_comprobante()])[0]
    assert resultado.aprobado
    assert resultado.cae == "751042"
    assert resultado.cae_vencimiento == "20260916"


def test_afip_puede_aprobar_unos_y_rechazar_otros(emisor, wsaa_falso, hacer_comprobante):
    """Un rechazo parcial no invalida el resto: hay que reportar fila por fila."""
    servicio = ServicioFalso(ultimo=41, resultados=["A", "R", "A"])
    resultados = _cliente(emisor, wsaa_falso, servicio).solicitar_cae(
        [hacer_comprobante(nombre="Ana"), hacer_comprobante(nombre="Luis"), hacer_comprobante(nombre="Sara")])

    assert [r.aprobado for r in resultados] == [True, False, True]
    rechazado = resultados[1]
    assert rechazado.cae is None
    assert "10015" in rechazado.observaciones
    assert "Documento invalido" in rechazado.observaciones


def test_un_error_de_request_marca_todo_el_lote_como_fallido(emisor, wsaa_falso, hacer_comprobante):
    """Si AFIP rechaza el pedido entero, ninguna fila se emitio."""
    servicio = ServicioFalso(errores_request=[(600, "CUIT no autorizado")])
    resultados = _cliente(emisor, wsaa_falso, servicio).solicitar_cae(
        [hacer_comprobante(), hacer_comprobante()])

    assert len(resultados) == 2
    assert not any(r.aprobado for r in resultados)
    assert all("CUIT no autorizado" in r.observaciones for r in resultados)


def test_error_al_consultar_la_numeracion(emisor, wsaa_falso, hacer_comprobante):
    class ServicioRoto:
        def FECompUltimoAutorizado(self, Auth, PtoVta, CbteTipo):    # noqa: N803
            return SimpleNamespace(
                CbteNro=0,
                Errors=SimpleNamespace(Err=[SimpleNamespace(Code=600, Msg="No autorizado")]),
            )

    with pytest.raises(WSFEError) as error:
        _cliente(emisor, wsaa_falso, ServicioRoto()).solicitar_cae([hacer_comprobante()])
    assert "No autorizado" in str(error.value)


def test_lista_vacia_no_llama_a_afip(emisor, wsaa_falso, hacer_comprobante):
    servicio = ServicioFalso()
    assert _cliente(emisor, wsaa_falso, servicio).solicitar_cae([]) == []
    assert servicio.pedidos == []


def test_si_afip_devuelve_menos_detalles_que_los_pedidos(emisor, wsaa_falso, hacer_comprobante):
    """No se puede asumir que la respuesta trae un detalle por comprobante."""
    class ServicioIncompleto(ServicioFalso):
        def FECAESolicitar(self, Auth, FeCAEReq):                    # noqa: N803
            respuesta = super().FECAESolicitar(Auth, FeCAEReq)
            respuesta.FeDetResp.FECAEDetResponse = respuesta.FeDetResp.FECAEDetResponse[:1]
            return respuesta

    resultados = _cliente(emisor, wsaa_falso, ServicioIncompleto(ultimo=41)).solicitar_cae(
        [hacer_comprobante(), hacer_comprobante()])
    assert resultados[0].aprobado
    assert not resultados[1].aprobado
    assert "no devolvio respuesta" in resultados[1].observaciones
