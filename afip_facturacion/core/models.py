"""Tipos de dominio y tablas de codigos de AFIP/ARCA.

Los codigos de esta seccion no se inventan: cada uno esta verificado contra
la documentacion oficial vigente o contra `pyafipws` (la libreria de
referencia de la comunidad, en produccion desde hace mas de una decada).
Estan comentados con su significado porque un numero suelto como "15" no le
dice nada a quien lea esto dentro de un año.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# ---------------------------------------------------------------------------
# Tipos de comprobante (CbteTipo)
# ---------------------------------------------------------------------------
# Los que terminan en "C" son los que emite un monotributista (sin
# discriminar IVA). Verificado contra la wiki de pyafipws.

CBTE_TIPO_FACTURA_C = 11
CBTE_TIPO_NOTA_DEBITO_C = 12
CBTE_TIPO_NOTA_CREDITO_C = 13
CBTE_TIPO_RECIBO_C = 15

# ---------------------------------------------------------------------------
# Concepto: que se esta facturando
# ---------------------------------------------------------------------------
# Servicios (2) y Productos y Servicios (3) requieren informar el periodo
# facturado (FchServDesde/FchServHasta) y la fecha de vencimiento de pago.

CONCEPTO_PRODUCTOS = 1
CONCEPTO_SERVICIOS = 2
CONCEPTO_PRODUCTOS_Y_SERVICIOS = 3

_CONCEPTOS_CON_PERIODO = (CONCEPTO_SERVICIOS, CONCEPTO_PRODUCTOS_Y_SERVICIOS)

# ---------------------------------------------------------------------------
# Tipo de documento del receptor (DocTipo)
# ---------------------------------------------------------------------------

DOC_TIPO_CUIT = 80
DOC_TIPO_DNI = 96
DOC_TIPO_CONSUMIDOR_FINAL = 99  # "sin identificar" -- solo con tope de monto

# ---------------------------------------------------------------------------
# Condicion frente al IVA del receptor (CondicionIVAReceptorId)
# ---------------------------------------------------------------------------
# Obligatorio en todo pedido de CAE desde el 1/9/2026 (RG AFIP 5616, WSFEv1
# v4.7). Antes de esa fecha era opcional; hoy un comprobante sin este campo
# se rechaza. Los nombres son los mismos que ya aparecian en el desplegable
# "Condicion frente al IVA" del portal RCEL -- es la misma tabla.

CONDICION_IVA_RESPONSABLE_INSCRIPTO = 1
CONDICION_IVA_EXENTO = 4
CONDICION_IVA_CONSUMIDOR_FINAL = 5
CONDICION_IVA_MONOTRIBUTO = 6
CONDICION_IVA_SUJETO_NO_CATEGORIZADO = 7
CONDICION_IVA_PROVEEDOR_EXTERIOR = 8
CONDICION_IVA_CLIENTE_EXTERIOR = 9
CONDICION_IVA_LIBERADO_LEY_19640 = 10
CONDICION_IVA_MONOTRIBUTO_SOCIAL = 13
CONDICION_IVA_NO_ALCANZADO = 15
CONDICION_IVA_MONOTRIBUTO_INDEPENDIENTE_PROMOVIDO = 16

#: Nombres tal como los escribe una persona en el Excel -> codigo AFIP.
#: Sin tildes y en minusculas para que la busqueda sea tolerante.
CONDICIONES_IVA_POR_NOMBRE = {
    "responsable inscripto": CONDICION_IVA_RESPONSABLE_INSCRIPTO,
    "exento": CONDICION_IVA_EXENTO,
    "consumidor final": CONDICION_IVA_CONSUMIDOR_FINAL,
    "monotributo": CONDICION_IVA_MONOTRIBUTO,
    "responsable monotributo": CONDICION_IVA_MONOTRIBUTO,
    "no categorizado": CONDICION_IVA_SUJETO_NO_CATEGORIZADO,
    "proveedor del exterior": CONDICION_IVA_PROVEEDOR_EXTERIOR,
    "cliente del exterior": CONDICION_IVA_CLIENTE_EXTERIOR,
    "monotributo social": CONDICION_IVA_MONOTRIBUTO_SOCIAL,
    "no alcanzado": CONDICION_IVA_NO_ALCANZADO,
    "monotributo independiente promovido": CONDICION_IVA_MONOTRIBUTO_INDEPENDIENTE_PROMOVIDO,
}


def resolver_condicion_iva(valor: object) -> int:
    """Acepta el codigo numerico o el nombre en texto libre de una celda.

    Devuelve el default (Consumidor Final) si la celda vino vacia, para que
    no haga falta llenar esta columna cuando todos los receptores son el
    mismo tipo -- que es el caso comun (socios de un club, clientes
    minoristas).
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return CONDICION_IVA_CONSUMIDOR_FINAL
    if isinstance(valor, (int, float)):
        return int(valor)
    texto = str(valor).strip().lower()
    if texto.isdigit():
        return int(texto)
    if texto not in CONDICIONES_IVA_POR_NOMBRE:
        raise ValueError(
            "condicion frente al IVA desconocida: {!r}. Usar uno de: {}".format(
                valor, ", ".join(sorted(CONDICIONES_IVA_POR_NOMBRE))
            )
        )
    return CONDICIONES_IVA_POR_NOMBRE[texto]


# ---------------------------------------------------------------------------
# Un comprobante a pedir, y el resultado que devuelve AFIP
# ---------------------------------------------------------------------------

@dataclass
class ComprobanteRequest:
    """Los datos de un recibo/factura a autorizar, ya validados.

    Sale de una fila de Excel (ver ``excel_reader.py``); no sabe nada de
    Excel ni de SOAP, por eso se puede armar a mano en un test.
    """

    doc_nro: str
    importe: float
    fecha: date
    periodo_desde: date | None = None
    periodo_hasta: date | None = None
    vencimiento_pago: date | None = None
    descripcion: str = ""
    doc_tipo: int = DOC_TIPO_DNI
    condicion_iva: int = CONDICION_IVA_CONSUMIDOR_FINAL
    nombre: str = ""          # solo para mostrar en el reporte; no va a AFIP
    fila_excel: int | None = None   # para poder decir "fila 7" en un error

    def __post_init__(self) -> None:
        if self.importe <= 0:
            raise ValueError("el importe tiene que ser mayor que cero")
        if not str(self.doc_nro).strip():
            raise ValueError("falta el numero de documento")


@dataclass
class ComprobanteResultado:
    """Lo que AFIP contesto para un comprobante: aprobado o no, y por que."""

    solicitud: ComprobanteRequest
    aprobado: bool
    numero: int | None = None
    cae: str | None = None
    cae_vencimiento: str | None = None
    observaciones: str = ""

    @property
    def etiqueta(self) -> str:
        """Como identificar esta fila en un reporte para humanos."""
        base = self.solicitud.nombre or self.solicitud.doc_nro
        if self.solicitud.fila_excel:
            return f"fila {self.solicitud.fila_excel} ({base})"
        return base


@dataclass
class EmisorConfig:
    """Datos fijos del emisor: quien factura, con que punto de venta y como."""

    cuit: str
    punto_venta: int
    cbte_tipo: int = CBTE_TIPO_RECIBO_C
    concepto: int = CONCEPTO_SERVICIOS
    cert_path: str = "afip.crt"
    key_path: str = "afip.key"
    produccion: bool = False
    cache_dir: str = "afip_cache"

    def __post_init__(self) -> None:
        cuit_limpio = "".join(ch for ch in str(self.cuit) if ch.isdigit())
        if len(cuit_limpio) != 11:
            raise ValueError(
                f"CUIT invalido: {self.cuit!r} (tiene que tener 11 digitos)"
            )
        self.cuit = cuit_limpio

    @property
    def requiere_periodo(self) -> bool:
        return self.concepto in _CONCEPTOS_CON_PERIODO
