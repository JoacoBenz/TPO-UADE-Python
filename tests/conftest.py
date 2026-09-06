"""Fixtures compartidas.

Regla de estos tests: **nunca se llama a AFIP**. Ni a homologacion. Todo lo
que habla con la red esta detras de un doble inyectado por constructor, y lo
criptografico se prueba contra un certificado de prueba generado al vuelo.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from afip_facturacion.core.models import ComprobanteRequest, EmisorConfig


@pytest.fixture
def certificado(tmp_path):
    """Un par clave/certificado autofirmado, en PEM, como los de AFIP."""
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-afip")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(nombre)
        .issuer_name(nombre)
        .public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=1))
        .sign(clave, hashes.SHA256())
    )
    cert_path = tmp_path / "afip.crt"
    key_path = tmp_path / "afip.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(clave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    return SimpleNamespace(cert_path=str(cert_path), key_path=str(key_path))


@pytest.fixture
def emisor():
    return EmisorConfig(cuit="20111222334", punto_venta=1)


@pytest.fixture
def wsaa_falso():
    """Un WSAA que siempre devuelve el mismo ticket, sin tocar la red."""
    return SimpleNamespace(
        obtener_ticket=lambda servicio: SimpleNamespace(token="TOKEN", sign="SIGN")
    )


@pytest.fixture
def hacer_comprobante():
    """Fabrica de ComprobanteRequest con valores por defecto razonables."""
    def _crear(**kwargs):
        base = {
            "doc_nro": "30111222",
            "importe": 21500.0,
            "fecha": datetime.date(2026, 7, 27),
            "periodo_desde": datetime.date(2026, 7, 1),
            "periodo_hasta": datetime.date(2026, 7, 31),
            "vencimiento_pago": datetime.date(2026, 7, 31),
            "nombre": "Socio Prueba",
        }
        base.update(kwargs)
        return ComprobanteRequest(**base)

    return _crear
