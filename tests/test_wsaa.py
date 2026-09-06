"""Autenticacion WSAA: armado del TRA, firma CMS y cache del ticket."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from datetime import datetime, timedelta
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest

from afip_facturacion.core.wsaa import (
    WSAA,
    TicketAcceso,
    WSAAError,
    _crear_tra,
    _firmar_cms,
)


def _respuesta_wsaa(token="TOKEN-ABC", sign="SIGN-XYZ", horas=12):
    vencimiento = (datetime.now().astimezone() + timedelta(hours=horas)).isoformat()
    return (
        '<?xml version="1.0"?><loginTicketResponse>'
        f"<header><expirationTime>{vencimiento}</expirationTime></header>"
        f"<credentials><token>{token}</token><sign>{sign}</sign></credentials>"
        "</loginTicketResponse>"
    )


class ClienteFalso:
    """Un WSAA de mentira que registra con que lo llamaron."""

    def __init__(self, respuesta=None, excepcion=None):
        self.llamadas = []
        self._respuesta = respuesta if respuesta is not None else _respuesta_wsaa()
        self._excepcion = excepcion
        self.service = SimpleNamespace(loginCms=self._login_cms)

    def _login_cms(self, in0):
        self.llamadas.append(in0)
        if self._excepcion:
            raise self._excepcion
        return self._respuesta


# ---------------------------------------------------------------------------
# TRA
# ---------------------------------------------------------------------------

def test_el_tra_tiene_la_estructura_que_espera_wsaa():
    raiz = ElementTree.fromstring(_crear_tra("wsfe").decode())
    assert raiz.tag == "loginTicketRequest"
    assert raiz.findtext("service") == "wsfe"
    header = raiz.find("header")
    assert header.findtext("uniqueId").isdigit()
    assert header.findtext("generationTime")
    assert header.findtext("expirationTime")


def test_la_ventana_del_tra_rodea_el_momento_actual():
    """generationTime tiene que estar en el pasado y expirationTime en el futuro.

    Si el reloj de la maquina esta corrido unos minutos respecto del de AFIP
    y la ventana fuera muy justa, WSAA rechazaria el pedido.
    """
    raiz = ElementTree.fromstring(_crear_tra("wsfe").decode())
    generacion = datetime.fromisoformat(raiz.find("header").findtext("generationTime"))
    expiracion = datetime.fromisoformat(raiz.find("header").findtext("expirationTime"))
    ahora = datetime.now(generacion.tzinfo)
    assert generacion < ahora < expiracion
    assert expiracion - generacion >= timedelta(minutes=20)


# ---------------------------------------------------------------------------
# Firma CMS
# ---------------------------------------------------------------------------

def test_la_firma_es_base64_de_un_cms_der(certificado):
    firmado = _firmar_cms(b"<test/>", certificado.cert_path, certificado.key_path)
    crudo = base64.b64decode(firmado, validate=True)
    # 0x30 es el primer byte de toda estructura DER (SEQUENCE).
    assert crudo[:1] == b"\x30"


@pytest.mark.skipif(shutil.which("openssl") is None, reason="requiere el binario openssl")
def test_openssl_valida_la_firma_y_recupera_el_contenido(certificado, tmp_path):
    """La prueba que de verdad importa: que un verificador ajeno acepte el CMS.

    Se usa openssl como arbitro independiente. Si esto pasa, WSAA -- que hace
    la misma verificacion -- tambien deberia aceptarlo. Es lo mas cerca que se
    puede estar de probar la firma sin llamar a AFIP.
    """
    tra = _crear_tra("wsfe")
    firmado = _firmar_cms(tra, certificado.cert_path, certificado.key_path)

    der = tmp_path / "firma.der"
    recuperado = tmp_path / "recuperado.xml"
    der.write_bytes(base64.b64decode(firmado))

    proceso = subprocess.run(
        ["openssl", "cms", "-verify", "-in", str(der), "-inform", "DER",
         "-noverify", "-out", str(recuperado)],
        capture_output=True, text=True,
    )
    assert proceso.returncode == 0, proceso.stderr
    # El contenido firmado tiene que ser el TRA original, sin una coma de mas.
    assert recuperado.read_bytes() == tra


def test_error_claro_si_falta_el_certificado(tmp_path):
    autenticador = WSAA("20111222334", "/no/existe.crt", "/no/existe.key",
                        str(tmp_path), cliente_soap=ClienteFalso())
    with pytest.raises(WSAAError) as error:
        autenticador.obtener_ticket("wsfe")
    assert "no se encontro el certificado" in str(error.value)


def test_error_claro_si_el_certificado_no_es_pem(tmp_path):
    basura = tmp_path / "basura.crt"
    basura.write_text("esto no es un certificado")
    autenticador = WSAA("20111222334", str(basura), str(basura), str(tmp_path),
                        cliente_soap=ClienteFalso())
    with pytest.raises(WSAAError):
        autenticador.obtener_ticket("wsfe")


# ---------------------------------------------------------------------------
# Ticket y cache
# ---------------------------------------------------------------------------

def test_obtiene_y_cachea_el_ticket(certificado, tmp_path):
    cliente = ClienteFalso()
    autenticador = WSAA("20111222334", certificado.cert_path, certificado.key_path,
                        str(tmp_path / "cache"), cliente_soap=cliente)

    primero = autenticador.obtener_ticket("wsfe")
    assert (primero.token, primero.sign) == ("TOKEN-ABC", "SIGN-XYZ")
    assert len(cliente.llamadas) == 1

    # La segunda vez sale del cache: WSAA no admite pedir otro ticket
    # mientras haya uno vigente, asi que pedirlo de nuevo seria un error.
    segundo = autenticador.obtener_ticket("wsfe")
    assert segundo.token == primero.token
    assert len(cliente.llamadas) == 1


def test_el_cache_separa_por_cuit_servicio_y_ambiente(certificado, tmp_path):
    """Dos ambientes o dos CUIT no pueden pisarse el ticket."""
    cache = tmp_path / "cache"
    WSAA("20111222334", certificado.cert_path, certificado.key_path, str(cache),
         produccion=False, cliente_soap=ClienteFalso()).obtener_ticket("wsfe")
    WSAA("20111222334", certificado.cert_path, certificado.key_path, str(cache),
         produccion=True, cliente_soap=ClienteFalso()).obtener_ticket("wsfe")
    archivos = sorted(p.name for p in cache.iterdir())
    assert archivos == ["ta_20111222334_wsfe_homo.json", "ta_20111222334_wsfe_prod.json"]


def test_un_ticket_vencido_se_renueva(certificado, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    vencido = TicketAcceso(
        "VIEJO", "VIEJO",
        (datetime.now().astimezone() - timedelta(hours=1)).isoformat(),
    )
    (cache / "ta_20111222334_wsfe_homo.json").write_text(json.dumps(vencido.to_dict()))

    cliente = ClienteFalso()
    ticket = WSAA("20111222334", certificado.cert_path, certificado.key_path,
                  str(cache), cliente_soap=cliente).obtener_ticket("wsfe")
    assert ticket.token == "TOKEN-ABC"
    assert len(cliente.llamadas) == 1


def test_un_cache_corrupto_no_rompe(certificado, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "ta_20111222334_wsfe_homo.json").write_text("{ no es json")
    cliente = ClienteFalso()
    ticket = WSAA("20111222334", certificado.cert_path, certificado.key_path,
                  str(cache), cliente_soap=cliente).obtener_ticket("wsfe")
    assert ticket.token == "TOKEN-ABC"


def test_ticket_por_vencer_se_considera_vencido():
    """Se renueva con margen para que una corrida larga no quede sin token."""
    casi = TicketAcceso("T", "S", (datetime.now().astimezone() + timedelta(minutes=2)).isoformat())
    holgado = TicketAcceso("T", "S", (datetime.now().astimezone() + timedelta(hours=5)).isoformat())
    assert casi.por_vencer()
    assert not holgado.por_vencer()


def test_mensaje_util_cuando_afip_dice_que_ya_hay_un_ticket(certificado, tmp_path):
    """El error crudo de AFIP no explica que hacer; el nuestro si."""
    cliente = ClienteFalso(excepcion=RuntimeError("El CEE ya posee un TA valido"))
    autenticador = WSAA("20111222334", certificado.cert_path, certificado.key_path,
                        str(tmp_path), cliente_soap=cliente)
    with pytest.raises(WSAAError) as error:
        autenticador.obtener_ticket("wsfe")
    assert "esperar a que venza" in str(error.value)


def test_respuesta_sin_token_es_error(certificado, tmp_path):
    cliente = ClienteFalso(respuesta='<?xml version="1.0"?><loginTicketResponse>'
                                     "<header><expirationTime>x</expirationTime></header>"
                                     "<credentials></credentials></loginTicketResponse>")
    autenticador = WSAA("20111222334", certificado.cert_path, certificado.key_path,
                        str(tmp_path), cliente_soap=cliente)
    with pytest.raises(WSAAError):
        autenticador.obtener_ticket("wsfe")
