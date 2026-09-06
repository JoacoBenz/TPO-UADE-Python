"""Genera la clave privada y el CSR para pedirle el certificado a AFIP.

Este es el primer paso del tramite, y el unico que se hace desde la
computadora. Produce dos archivos:

  afip.key  -- la clave privada. NUNCA sale de esta maquina, no se manda por
               mail ni se sube a ningun lado. Quien la tenga puede facturar
               en nombre de este CUIT.
  afip.csr  -- el pedido de certificado. Este SI se sube a AFIP, no tiene
               nada secreto adentro.

Despues de correrlo, seguir docs/alta_certificado_afip.md para subir el .csr
y autorizar el servicio.

    python tools/generar_csr.py --cuit 20-11122233-4 --nombre "Club Los Pehuenes"

El subject del CSR sigue el formato que exige AFIP: el CUIT va en el campo
serialNumber como "CUIT 20111222334", y el CN es un nombre libre que despues
aparece en el listado de certificados del portal.
"""

from __future__ import annotations

import argparse
import os
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

#: AFIP pide claves RSA de 2048 bits.
TAMANIO_CLAVE = 2048


def generar(cuit: str, nombre: str, organizacion: str, salida: str,
            forzar: bool = False) -> int:
    cuit_limpio = "".join(ch for ch in cuit if ch.isdigit())
    if len(cuit_limpio) != 11:
        print(f"CUIT invalido: {cuit!r} (tiene que tener 11 digitos)", file=sys.stderr)
        return 2

    key_path = f"{salida}.key"
    csr_path = f"{salida}.csr"

    # La clave privada es irrecuperable: si se pisa una que ya esta dada de
    # alta en AFIP, hay que rehacer el tramite entero.
    existentes = [p for p in (key_path, csr_path) if os.path.exists(p)]
    if existentes and not forzar:
        print(f"Ya existen: {', '.join(existentes)}", file=sys.stderr)
        print("Si los pisas y la clave estaba dada de alta en AFIP, hay que rehacer el "
              "tramite. Usa --forzar solo si estas seguro.", file=sys.stderr)
        return 3

    clave = rsa.generate_private_key(public_exponent=65537, key_size=TAMANIO_CLAVE)

    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, organizacion or nombre),
        x509.NameAttribute(NameOID.COMMON_NAME, nombre),
        # AFIP identifica al titular por este campo, no por el CN.
        x509.NameAttribute(NameOID.SERIAL_NUMBER, f"CUIT {cuit_limpio}"),
    ])
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(subject)
        .sign(clave, hashes.SHA256())
    )

    with open(key_path, "wb") as handle:
        handle.write(clave.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    os.chmod(key_path, 0o600)   # solo el dueño; en Windows es un no-op benigno

    with open(csr_path, "wb") as handle:
        handle.write(csr.public_bytes(serialization.Encoding.PEM))

    print(f"Clave privada : {key_path}   <- NO compartir, no subir a ningun lado")
    print(f"Pedido (CSR)  : {csr_path}   <- este es el que se sube a AFIP")
    print()
    print("Subject del CSR:")
    print(f"  {subject.rfc4514_string()}")
    print()
    print("Proximos pasos (detalle en docs/alta_certificado_afip.md):")
    print("  1. Entrar a afip.gob.ar con Clave Fiscal")
    print("  2. 'Administracion de Certificados Digitales' -> subir el .csr")
    print("  3. Descargar el .crt que devuelve AFIP y guardarlo junto a la clave")
    print("  4. 'Administrador de Relaciones' -> autorizar el servicio 'wsfe'")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python tools/generar_csr.py",
        description="Genera la clave privada y el CSR para el certificado de AFIP.",
    )
    parser.add_argument("--cuit", required=True, help="CUIT del emisor (con o sin guiones)")
    parser.add_argument("--nombre", required=True,
                        help="nombre identificatorio del certificado (ej: 'Club Los Pehuenes')")
    parser.add_argument("--organizacion", default="",
                        help="razon social (si se omite, se usa --nombre)")
    parser.add_argument("--salida", default="afip",
                        help="prefijo de los archivos a generar (default: afip)")
    parser.add_argument("--forzar", action="store_true",
                        help="sobrescribir archivos existentes")
    args = parser.parse_args(argv)
    return generar(args.cuit, args.nombre, args.organizacion, args.salida, args.forzar)


if __name__ == "__main__":
    sys.exit(main())
