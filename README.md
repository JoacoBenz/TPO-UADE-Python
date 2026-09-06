# Facturación electrónica AFIP desde Python

Emite comprobantes electrónicos (Recibo C, Factura C, notas de crédito/débito)
contra el web service oficial de AFIP/ARCA — **WSFEv1** — leyendo los datos de
un Excel. Devuelve el **CAE** de cada comprobante, o el motivo exacto del
rechazo, fila por fila.

Reemplaza un bot de UiPath que hacía lo mismo clickeando el portal web de AFIP
(RCEL). La diferencia de fondo: esto no depende de que una página no cambie de
diseño ni de que haya un Chrome abierto — le habla directo al sistema de AFIP.

---

## Por qué API y no automatizar el navegador

| | Portal RCEL (lo que hacía el bot de UiPath) | WSFEv1 (esto) |
|---|---|---|
| Cómo funciona | Clickea el formulario web de AFIP | Le pide el CAE al sistema de AFIP |
| Se rompe si… | AFIP mueve un botón o cambia el HTML | Prácticamente nunca: es un contrato versionado |
| Necesita | Chrome abierto y sesión con Clave Fiscal | Un certificado digital (trámite único) |
| Corre desatendido | Con dificultad | Sí |
| Velocidad | ~1 comprobante cada 30–60 s | 250 comprobantes en **una** llamada |

El precio a pagar es un trámite de 15 minutos en el sitio de AFIP, una sola vez:
[`docs/alta_certificado_afip.md`](docs/alta_certificado_afip.md).

---

## Puesta en marcha

```bash
pip install -r requirements.txt

# 1. Generar la clave privada y el pedido de certificado
python tools/generar_csr.py --cuit 20-11122233-4 --nombre "Club Los Pehuenes"

# 2. Dar de alta el certificado en AFIP (ver docs/alta_certificado_afip.md)

# 3. Configurar el emisor
cp config.example.py config.py     # y completar CUIT y PUNTO_VENTA
```

---

## Uso

Una corrida por mes:

```bash
python -m afip_facturacion --excel cuotas.xlsx --hoja Julio \
    --fecha 27/07/2026 --desde 01/07/2026 --hasta 31/07/2026 \
    --importe 21500 --descripcion "Cuota Social Julio 2026"
```

```
Ambiente : homologacion (prueba)
Emisor   : CUIT 20111222334, punto de venta 1, tipo de comprobante 15
A emitir : 3 comprobante(s)

COMPROBANTE                     NRO  ESTADO     CAE              DETALLE
------------------------------------------------------------------------------
fila 2 (Ana Perez)               42  aprobado   75102938471023
fila 3 (Luis Gomez)              43  RECHAZADO  -                10015 - Documento invalido
fila 4 (Sara Diaz)               44  aprobado   75102938471025
------------------------------------------------------------------------------
2 aprobado(s), 1 rechazado(s)
```

### Dos banderas que importan

- **`--dry-run`** — lee el Excel y muestra qué se emitiría, sin llamar a AFIP.
  Conviene correrlo siempre antes.
- **`--produccion`** — emite comprobantes **reales**. Sin esta bandera todo va
  al ambiente de pruebas de AFIP. Es opt-in a propósito: un comprobante
  autorizado no se borra, se anula con una nota de crédito.

---

## El Excel

La única columna obligatoria es el **documento del receptor**. Todo lo demás
puede venir en el Excel o pasarse por línea de comandos para toda la corrida.

Esa flexibilidad es deliberada: en el caso típico —la cuota de un mes— la
fecha, el período y el importe son idénticos para los cuarenta socios, y
repetirlos cuarenta veces solo agrega errores de tipeo. Pero si un socio paga
distinto, se agrega la columna y esa fila la usa.

| Columna | Obligatoria | Alias que reconoce |
|---|---|---|
| Documento | **sí** | `DNI`, `Documento`, `N° Documento`, `Nro. Doc`, `CUIT`… |
| Nombre | no (solo para el reporte) | `Socio`, `Nombre`, `Cliente`, `Razón Social` |
| Importe | no, si se pasa `--importe` | `Importe`, `Monto`, `Precio`, `Cuota` |
| Fecha | no, si se pasa `--fecha` | `Fecha`, `Fecha del Comprobante` |
| Período desde / hasta | no, si se pasan `--desde` / `--hasta` | `Desde`, `Período Desde` |
| Vencimiento | no, si se pasa `--vencimiento` | `Vto.`, `Vencimiento`, `Vto. para el Pago` |
| Descripción | no, si se pasa `--descripcion` | `Descripción`, `Concepto`, `Detalle` |
| Condición IVA | no (default: Consumidor Final) | `Condición frente al IVA`, `IVA` |
| Tipo de documento | no (default: DNI) | `Tipo de Documento` |

Los encabezados se comparan sin distinguir mayúsculas, tildes ni `N°`/`Nº`.
Los importes aceptan `$21.500,50`, `21500`, `21.500`. Las fechas aceptan
`dd/mm/aaaa` o celdas con formato fecha de Excel.

Una fila con un dato ilegible **no frena la corrida**: se reporta con su
número de fila y las demás se emiten igual.

---

## Cómo está organizado

```
afip_facturacion/
  core/
    models.py         Comprobante, resultado, y las tablas de códigos de AFIP
    wsaa.py           Autenticación: TRA, firma CMS, caché del ticket
    wsfe.py           Cliente WSFEv1: numeración, pedido de CAE, respuestas
    excel_reader.py   Lectura del Excel, tolerante a cómo escribe la gente
  cli.py              La línea de comandos
tools/generar_csr.py  Genera la clave privada y el CSR para el trámite
docs/                 El trámite en AFIP, paso a paso
tests/                97 tests, ninguno toca AFIP
```

`core/` no sabe nada de la línea de comandos ni del Excel: recibe objetos y
devuelve objetos. Por eso los tests corren en dos segundos sin red.

---

## Detalles que conviene conocer

**El `CondicionIVAReceptorId` es obligatorio desde el 1/9/2026.** Lo exige la
RG 5616 y AFIP rechaza el comprobante si falta. Muchos ejemplos y librerías que
circulan son anteriores a esa fecha y no lo mandan. Acá va siempre, con
Consumidor Final como default.

**La numeración se consulta antes de cada lote.** El primer comprobante toma el
número siguiente al último autorizado. Si alguien emitió por otra vía en el
medio, la corrida siguiente lo detecta sola.

**El ticket de acceso se cachea.** WSAA no permite pedir uno nuevo si ya hay uno
vigente (dura 12 horas) — pedirlo igual es un error. Se guarda en `afip_cache/`
y se renueva solo cuando está por vencer.

**Un rechazo no consume numeración.** Si AFIP rechaza una fila, ese número
queda libre. Se corrige el dato y se vuelve a correr.

**Comprobantes tipo C no discriminan IVA.** El total va íntegro en `ImpNeto` y
los campos de impuestos van en cero: mandar `ImpIVA` distinto de cero en un
comprobante C hace que AFIP lo rechace.

---

## Desarrollo

```bash
pip install -r requirements-dev.txt
python -m pytest        # 97 tests
ruff check .
```

Los tests **nunca llaman a AFIP**, ni siquiera a homologación. Lo que habla con
la red está detrás de un doble inyectado por constructor. Lo criptográfico
—que es lo que no se puede probar "a ojo"— se verifica con un árbitro externo:
se firma un TRA y se comprueba con `openssl cms -verify` que la firma es válida
y que el contenido vuelve byte a byte idéntico.

## Lo que no se pudo probar acá

La integración real contra AFIP necesita un certificado autorizado para un CUIT
real, así que estas tres cosas quedan para la primera corrida en tu máquina:

1. Que WSAA acepte la firma CMS (verificada contra `openssl`, pero no contra AFIP).
2. Que el certificado esté bien asociado al servicio `wsfe`.
3. Que el punto de venta sea del tipo correcto (web services, no RCEL).

Las tres se validan de una corriendo contra **homologación** antes de producción.
