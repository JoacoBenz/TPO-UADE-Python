"""Configuracion del emisor -- copiar a config.py y completar.

config.py NO se versiona (esta en .gitignore): tiene el CUIT real y apunta a
los archivos del certificado. Cada instalacion tiene el suyo.
"""

# CUIT del emisor, con o sin guiones.
CUIT = "20-11122233-4"

# Punto de venta habilitado en AFIP para web services. Ojo: es el numero del
# punto de venta, no el del comprobante. Se da de alta en el portal de AFIP
# ("Administracion de puntos de venta y domicilios") y tiene que ser del tipo
# "Web Services" -- un punto de venta de "Comprobantes en linea" (el portal
# RCEL) no sirve para facturar por API, son numeraciones separadas.
PUNTO_VENTA = 1

# Tipo de comprobante a emitir. Los codigos estan en core/models.py:
#   11 = Factura C     12 = Nota de Debito C
#   13 = Nota de Credito C     15 = Recibo C
CBTE_TIPO = 15

# Que se factura: 1 = Productos, 2 = Servicios, 3 = Productos y Servicios.
# Servicios y "Productos y Servicios" obligan a informar el periodo
# facturado (desde/hasta) y el vencimiento de pago.
CONCEPTO = 2

# Certificado y clave privada autorizados en AFIP para el servicio "wsfe".
# Se generan con tools/generar_csr.py y se dan de alta siguiendo
# docs/alta_certificado_afip.md.
CERT_PATH = "afip.crt"
KEY_PATH = "afip.key"

# Donde se guarda el ticket de acceso de WSAA (vale 12 horas). Se puede
# borrar sin consecuencias: si no esta, se pide uno nuevo.
CACHE_DIR = "afip_cache"
