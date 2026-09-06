"""Cliente de WSFEv1: pide el CAE de cada comprobante.

El CAE (Codigo de Autorizacion Electronico) es lo que convierte un papel en
un comprobante valido. Sin el, el recibo no existe para AFIP.

El flujo por lote es:

  1. ``FECompUltimoAutorizado`` dice cual fue el ultimo numero autorizado
     para ese punto de venta y tipo de comprobante.
  2. Se numeran los comprobantes del lote a partir de ahi, correlativos.
  3. ``FECAESolicitar`` manda el lote entero en UNA llamada y devuelve, por
     cada comprobante, si quedo aprobado y con que CAE.

Se manda en lote y no de a uno por dos razones: es lo que espera AFIP (el
metodo recibe un array), y porque numerar de a uno significa una consulta de
numeracion por comprobante, multiplicando las llamadas sin necesidad.

Sobre los rechazos: AFIP puede aprobar unos comprobantes del lote y rechazar
otros. Por eso el resultado es una lista con el detalle de cada uno, y no un
booleano global -- si tres socios de veinte fallan, hay que poder decir
exactamente cuales y por que.
"""

from __future__ import annotations

from typing import Any

from .models import ComprobanteRequest, ComprobanteResultado

WSDL_HOMOLOGACION = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
WSDL_PRODUCCION = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"

#: Maximo de comprobantes por llamada a FECAESolicitar, segun el manual del
#: desarrollador. Los lotes mas grandes se parten solos.
MAX_POR_LOTE = 250

#: Moneda: pesos argentinos, cotizacion 1. Facturar en otra moneda implica
#: informar la cotizacion del dia, que este proyecto no necesita.
MONEDA_PESOS = "PES"
COTIZACION_PESOS = 1


class WSFEError(Exception):
    """Error del servicio de facturacion (no de un comprobante puntual)."""


def _fmt_fecha(valor: Any) -> str | None:
    """AFIP espera las fechas como 'yyyymmdd', sin separadores."""
    if valor is None:
        return None
    return valor.strftime("%Y%m%d")


class WSFE:
    """Habla con WSFEv1 en nombre de un emisor."""

    def __init__(self, emisor: Any, wsaa: Any, cliente_soap: Any = None) -> None:
        self.emisor = emisor
        self.wsaa = wsaa
        self.wsdl = WSDL_PRODUCCION if emisor.produccion else WSDL_HOMOLOGACION
        #: Inyectable para testear sin llamar a AFIP.
        self._cliente_soap = cliente_soap

    # -- infraestructura -----------------------------------------------------

    @property
    def cliente(self) -> Any:
        if self._cliente_soap is None:
            import zeep  # import diferido: los tests no necesitan zeep
            self._cliente_soap = zeep.Client(wsdl=self.wsdl)
        return self._cliente_soap

    def _auth(self) -> dict:
        ticket = self.wsaa.obtener_ticket("wsfe")
        return {"Token": ticket.token, "Sign": ticket.sign, "Cuit": self.emisor.cuit}

    @staticmethod
    def _errores(respuesta: Any) -> str:
        """Junta los errores de nivel de request (no los de un comprobante)."""
        errores = getattr(respuesta, "Errors", None)
        if not errores:
            return ""
        items = getattr(errores, "Err", None) or []
        return "; ".join(
            "{} - {}".format(getattr(e, "Code", "?"), getattr(e, "Msg", "")) for e in items
        )

    # -- numeracion ----------------------------------------------------------

    def ultimo_autorizado(self) -> int:
        """El numero del ultimo comprobante autorizado para este punto de venta."""
        respuesta = self.cliente.service.FECompUltimoAutorizado(
            Auth=self._auth(),
            PtoVta=self.emisor.punto_venta,
            CbteTipo=self.emisor.cbte_tipo,
        )
        error = self._errores(respuesta)
        if error:
            raise WSFEError(f"no se pudo consultar la numeracion: {error}")
        return int(respuesta.CbteNro)

    # -- solicitud de CAE ----------------------------------------------------

    def _detalle(self, solicitud: ComprobanteRequest, numero: int) -> dict:
        """Arma el FECAEDetRequest de un comprobante.

        Nota sobre los importes: en un comprobante "C" el emisor es
        monotributista y no discrimina IVA, asi que el total va integro en
        ImpNeto y todos los campos de impuestos van en cero. Mandar ImpIVA
        distinto de cero en un comprobante C hace que AFIP lo rechace.
        """
        detalle = {
            "Concepto": self.emisor.concepto,
            "DocTipo": solicitud.doc_tipo,
            "DocNro": int(solicitud.doc_nro),
            "CbteDesde": numero,
            "CbteHasta": numero,
            "CbteFch": _fmt_fecha(solicitud.fecha),
            "ImpTotal": round(solicitud.importe, 2),
            "ImpTotConc": 0,
            "ImpNeto": round(solicitud.importe, 2),
            "ImpOpEx": 0,
            "ImpTrib": 0,
            "ImpIVA": 0,
            "MonId": MONEDA_PESOS,
            "MonCotiz": COTIZACION_PESOS,
            # Obligatorio en todo pedido de CAE desde el 1/9/2026 (RG 5616).
            "CondicionIVAReceptorId": solicitud.condicion_iva,
        }
        # El periodo facturado y el vencimiento de pago solo se informan
        # cuando el concepto incluye servicios; para productos, AFIP rechaza
        # el comprobante si vienen cargados.
        if self.emisor.requiere_periodo:
            detalle["FchServDesde"] = _fmt_fecha(solicitud.periodo_desde or solicitud.fecha)
            detalle["FchServHasta"] = _fmt_fecha(solicitud.periodo_hasta or solicitud.fecha)
            detalle["FchVtoPago"] = _fmt_fecha(solicitud.vencimiento_pago or solicitud.fecha)
        return detalle

    def solicitar_cae(self, solicitudes: list[ComprobanteRequest],
                      numero_inicial: int | None = None) -> list[ComprobanteResultado]:
        """Pide el CAE de todos los comprobantes y devuelve el detalle de cada uno."""
        if not solicitudes:
            return []

        siguiente = (self.ultimo_autorizado() + 1) if numero_inicial is None else numero_inicial
        resultados: list[ComprobanteResultado] = []

        for inicio in range(0, len(solicitudes), MAX_POR_LOTE):
            lote = solicitudes[inicio:inicio + MAX_POR_LOTE]
            resultados.extend(self._solicitar_lote(lote, siguiente))
            siguiente += len(lote)
        return resultados

    def _solicitar_lote(self, lote: list[ComprobanteRequest],
                        numero_inicial: int) -> list[ComprobanteResultado]:
        detalles = [
            self._detalle(solicitud, numero_inicial + offset)
            for offset, solicitud in enumerate(lote)
        ]
        peticion = {
            "FeCabReq": {
                "CantReg": len(detalles),
                "PtoVta": self.emisor.punto_venta,
                "CbteTipo": self.emisor.cbte_tipo,
            },
            "FeDetReq": [{"FECAEDetRequest": detalle} for detalle in detalles],
        }

        respuesta = self.cliente.service.FECAESolicitar(Auth=self._auth(), FeCAEReq=peticion)

        error = self._errores(respuesta)
        if error:
            # Un error a este nivel invalida el lote entero (credenciales,
            # punto de venta inexistente, numeracion pisada). No hay CAE
            # para nadie, y hay que decirlo fila por fila igual.
            return [
                ComprobanteResultado(
                    solicitud=solicitud, aprobado=False,
                    numero=numero_inicial + offset, observaciones=error,
                )
                for offset, solicitud in enumerate(lote)
            ]

        return self._parsear_respuesta(lote, respuesta, numero_inicial)

    @staticmethod
    def _parsear_respuesta(lote: list[ComprobanteRequest], respuesta: Any,
                           numero_inicial: int) -> list[ComprobanteResultado]:
        detalles_resp = []
        cuerpo = getattr(respuesta, "FeDetResp", None)
        if cuerpo is not None:
            detalles_resp = getattr(cuerpo, "FECAEDetResponse", None) or []

        resultados: list[ComprobanteResultado] = []
        for offset, solicitud in enumerate(lote):
            numero = numero_inicial + offset
            detalle = detalles_resp[offset] if offset < len(detalles_resp) else None
            if detalle is None:
                resultados.append(
                    ComprobanteResultado(
                        solicitud=solicitud, aprobado=False, numero=numero,
                        observaciones="AFIP no devolvio respuesta para este comprobante",
                    )
                )
                continue

            aprobado = getattr(detalle, "Resultado", "") == "A"
            resultados.append(
                ComprobanteResultado(
                    solicitud=solicitud,
                    aprobado=aprobado,
                    numero=int(getattr(detalle, "CbteDesde", numero) or numero),
                    cae=getattr(detalle, "CAE", None) or None,
                    cae_vencimiento=getattr(detalle, "CAEFchVto", None) or None,
                    observaciones=_texto_observaciones(detalle),
                )
            )
        return resultados


def _texto_observaciones(detalle: Any) -> str:
    """Las observaciones de AFIP para un comprobante, legibles.

    Aparecen tanto cuando se rechaza (explican por que) como cuando se
    aprueba con advertencias -- estas ultimas conviene no esconderlas.
    """
    partes = []
    observaciones = getattr(detalle, "Observaciones", None)
    if observaciones:
        for obs in getattr(observaciones, "Obs", None) or []:
            partes.append("{} - {}".format(getattr(obs, "Code", "?"), getattr(obs, "Msg", "")))
    return "; ".join(partes)
