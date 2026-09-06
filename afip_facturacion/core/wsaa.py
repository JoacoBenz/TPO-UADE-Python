"""Autenticacion contra WSAA (Web Service de Autenticacion y Autorizacion).

Todo servicio de AFIP/ARCA (WSFEv1 incluido) exige un "ticket de acceso"
(TA) para cada llamada. Conseguirlo es un proceso en tres pasos:

  1. Armar un TRA (Ticket de Requerimiento de Acceso): un XML chico que dice
     quien pregunta, cuando, y para que servicio ("wsfe").
  2. Firmar ese XML en CMS/PKCS#7 con la clave privada y el certificado que
     AFIP autorizo para el servicio. Esta firma es la prueba de identidad:
     nadie mas tiene esa clave privada.
  3. Mandar la firma a WSAA, que devuelve un `token` y un `sign` validos
     por 12 horas. Esos dos valores son lo que despues se manda en cada
     llamada a WSFEv1 (no el certificado ni la clave).

La firma se hace con ``cryptography`` puro -- sin invocar al binario
``openssl`` por subprocess, que es como lo hacen las implementaciones de
referencia mas viejas (pyafipws usa M2Crypto o un subprocess a openssl).
Eso evita depender de que ``openssl.exe`` este instalado y en el PATH, algo
que en Windows no se puede dar por sentado. La receta se verifico a mano:
se firmo un TRA de prueba y se comprobo con ``openssl cms -verify`` que el
CMS resultante es identico, byte a byte, al que produce la herramienta de
referencia.

Un detalle que importa para no pedir tickets de mas: WSAA no permite pedir
un TA nuevo para un servicio si ya hay uno vigente -- responde con el error
"ya posee un TA valido". Por eso el ticket se cachea en disco y solo se pide
uno nuevo cuando el guardado esta por vencer.
"""

from __future__ import annotations

import base64
import json
import os
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from xml.etree import ElementTree

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import Any, Optional  # noqa: F401

WSDL_HOMOLOGACION = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl"
WSDL_PRODUCCION = "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl"

#: Margen alrededor de "ahora" para generationTime/expirationTime del TRA.
#: 40 minutos de holgura (igual que pyafipws) absorbe que el reloj de la
#: maquina este un poco desfasado del de AFIP sin arriesgar nada: el TA que
#: se obtiene igual dura 12 horas independientemente de esta ventana.
_TRA_MARGEN_SEGUNDOS = 40 * 60

#: Se pide un TA nuevo si al guardado le quedan menos de esto por vencer.
#: Bastante margen para que una corrida larga no se quede sin token a mitad
#: de camino.
_RENOVAR_SI_QUEDAN_MENOS_DE = timedelta(minutes=10)


class WSAAError(Exception):
    """Fallo autenticando contra AFIP: certificado, firma, o red."""


def _crear_tra(servicio: str) -> bytes:
    ahora = datetime.now(UTC).astimezone()
    generacion = ahora - timedelta(seconds=_TRA_MARGEN_SEGUNDOS)
    expiracion = ahora + timedelta(seconds=_TRA_MARGEN_SEGUNDOS)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<loginTicketRequest version="1.0">'
        "<header>"
        "<uniqueId>{unique_id}</uniqueId>"
        "<generationTime>{generacion}</generationTime>"
        "<expirationTime>{expiracion}</expirationTime>"
        "</header>"
        "<service>{servicio}</service>"
        "</loginTicketRequest>"
    ).format(
        unique_id=int(time.time()),
        generacion=generacion.isoformat(timespec="seconds"),
        expiracion=expiracion.isoformat(timespec="seconds"),
        servicio=servicio,
    )
    return xml.encode("utf-8")


def _firmar_cms(tra: bytes, cert_path: str, key_path: str) -> str:
    """Firma el TRA en CMS/PKCS7 y devuelve el resultado en base64.

    Base64 porque el WSDL de WSAA declara el parametro ``in0`` del metodo
    ``loginCms`` como ``xsd:string`` (verificado contra la especificacion
    tecnica publicada por AFIP) -- no como ``base64Binary``, que es lo que
    haria que una libreria SOAP lo codificara sola. Si se mandara el CMS
    crudo, o se lo codificara dos veces, WSAA lo rechaza sin un mensaje que
    ayude a entender por que.
    """
    try:
        with open(cert_path, "rb") as handle:
            certificado = x509.load_pem_x509_certificate(handle.read())
        with open(key_path, "rb") as handle:
            clave_privada = serialization.load_pem_private_key(handle.read(), password=None)
    except FileNotFoundError as exc:
        raise WSAAError(
            f"no se encontro el certificado o la clave privada ({exc}). "
            "Revisa cert_path/key_path en la config, o generalos con "
            "tools/generar_csr.py y complete el alta en AFIP."
        ) from exc
    except ValueError as exc:
        raise WSAAError(
            f"el certificado o la clave no se pudieron leer como PEM: {exc}"
        ) from exc

    cms_der = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(tra)
        .add_signer(certificado, clave_privada, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary])
    )
    return base64.b64encode(cms_der).decode("ascii")


def _parsear_login_ticket_response(xml_texto: str) -> dict:
    raiz = ElementTree.fromstring(xml_texto)
    credenciales = raiz.find("credentials")
    header = raiz.find("header")
    if credenciales is None or header is None:
        raise WSAAError(f"respuesta de WSAA con formato inesperado: {xml_texto[:300]!r}")
    return {
        "token": credenciales.findtext("token"),
        "sign": credenciales.findtext("sign"),
        "expiration_time": header.findtext("expirationTime"),
    }


class TicketAcceso:
    """Un token+sign vigente, con su vencimiento."""

    __slots__ = ("token", "sign", "expiration_time")

    def __init__(self, token: str, sign: str, expiration_time: str) -> None:
        self.token = token
        self.sign = sign
        self.expiration_time = expiration_time  # ISO 8601, tal como lo da AFIP

    def por_vencer(self) -> bool:
        try:
            vencimiento = datetime.fromisoformat(self.expiration_time)
        except ValueError:
            return True   # si no se puede interpretar, mejor pedir uno nuevo
        ahora = datetime.now(vencimiento.tzinfo or UTC)
        return vencimiento - ahora < _RENOVAR_SI_QUEDAN_MENOS_DE

    def to_dict(self) -> dict:
        return {"token": self.token, "sign": self.sign, "expiration_time": self.expiration_time}

    @classmethod
    def from_dict(cls, data: dict) -> TicketAcceso:
        return cls(data["token"], data["sign"], data["expiration_time"])


class WSAA:
    """Consigue y cachea el ticket de acceso para un servicio (p. ej. "wsfe")."""

    def __init__(self, cuit: str, cert_path: str, key_path: str, cache_dir: str,
                 produccion: bool = False, cliente_soap: Any = None) -> None:
        self.cuit = cuit
        self.cert_path = cert_path
        self.key_path = key_path
        self.cache_dir = cache_dir
        self.wsdl = WSDL_PRODUCCION if produccion else WSDL_HOMOLOGACION
        #: Inyectable para poder testear sin llamar a AFIP de verdad.
        self._cliente_soap = cliente_soap

    def _cache_path(self, servicio: str) -> str:
        ambiente = "prod" if self.wsdl == WSDL_PRODUCCION else "homo"
        nombre = f"ta_{self.cuit}_{servicio}_{ambiente}.json"
        return os.path.join(self.cache_dir, nombre)

    def _leer_cache(self, servicio: str) -> TicketAcceso | None:
        path = self._cache_path(servicio)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as handle:
                ticket = TicketAcceso.from_dict(json.load(handle))
        except (ValueError, KeyError, OSError):
            return None
        return None if ticket.por_vencer() else ticket

    def _guardar_cache(self, servicio: str, ticket: TicketAcceso) -> None:
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(self._cache_path(servicio), "w", encoding="utf-8") as handle:
            json.dump(ticket.to_dict(), handle)

    def obtener_ticket(self, servicio: str) -> TicketAcceso:
        """El token+sign vigentes, del cache o pidiendo uno nuevo a WSAA."""
        cacheado = self._leer_cache(servicio)
        if cacheado is not None:
            return cacheado

        tra = _crear_tra(servicio)
        cms_b64 = _firmar_cms(tra, self.cert_path, self.key_path)
        cliente = self._cliente_soap or self._crear_cliente_soap()

        try:
            respuesta = cliente.service.loginCms(in0=cms_b64)
        except Exception as exc:                                    # noqa: BLE001
            texto = str(exc)
            if "ya posee un TA valido" in texto or "alreadyAuthenticated" in texto:
                raise WSAAError(
                    f"AFIP dice que ya existe un ticket vigente para '{servicio}', pero no esta en "
                    f"el cache local ({self._cache_path(servicio)}). Puede haberse generado desde otra maquina o antes "
                    "de borrar afip_cache/; hay que esperar a que venza (hasta 12 horas) o "
                    "recuperar ese cache."
                ) from exc
            raise WSAAError(f"WSAA rechazo la autenticacion: {texto}") from exc

        datos = _parsear_login_ticket_response(respuesta)
        if not datos["token"] or not datos["sign"]:
            raise WSAAError(f"WSAA respondio sin token/sign: {respuesta!r}")

        ticket = TicketAcceso(datos["token"], datos["sign"], datos["expiration_time"])
        self._guardar_cache(servicio, ticket)
        return ticket

    def _crear_cliente_soap(self) -> Any:
        import zeep  # import diferido: el core no lo necesita para testear la firma
        return zeep.Client(wsdl=self.wsdl)
