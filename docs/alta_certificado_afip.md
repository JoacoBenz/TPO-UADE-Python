# Alta del certificado en AFIP (ARCA)

Trámite de una sola vez, todo online y autogestionado: no hay cola de espera
ni aprobación de nadie del otro lado. Toma unos 15 minutos.

Necesitás **Clave Fiscal nivel 2 o superior**. Si tenés nivel 1, primero hay
que elevarlo (se hace desde el mismo sitio, vinculando homebanking o desde un
cajero automático).

> **AFIP ahora se llama ARCA** (Agencia de Recaudación y Control Aduanero,
> desde 2024). Cambió el nombre y el logo; los servicios web, los endpoints y
> el trámite son los mismos. Vas a ver las dos marcas mezcladas en el sitio.

---

## Paso 1 — Generar la clave privada y el pedido de certificado

En tu máquina, dentro de la carpeta del proyecto:

```bash
python tools/generar_csr.py --cuit 20-11122233-4 --nombre "Club Los Pehuenes"
```

Genera dos archivos:

| Archivo | Qué es | Cuidado |
|---|---|---|
| `afip.key` | La clave privada | **Nunca** se comparte ni se sube a ningún lado. Quien la tenga puede facturar en nombre de tu CUIT. |
| `afip.csr` | El pedido de certificado | Este sí se sube a AFIP. No tiene nada secreto adentro. |

Si perdés el `.key`, hay que rehacer el trámite entero: el certificado que
AFIP emitió queda inservible sin su clave.

---

## Paso 2 — Subir el CSR y descargar el certificado

1. Entrá a **afip.gob.ar** → *Iniciar sesión con Clave Fiscal*.
2. Buscá el servicio **"Administración de Certificados Digitales"**.
   - Si no aparece en tu lista de servicios, hay que habilitarlo primero
     desde *Administrador de Relaciones de Clave Fiscal* →
     *Adherir servicio* → AFIP → Servicios Interactivos.
3. *Agregar alias* → poné un nombre para identificar este certificado
   (por ejemplo `facturacion-cuotas`) y subí el archivo **`afip.csr`**.
4. AFIP genera el certificado en el momento. Descargalo — es un archivo
   `.crt` o `.pem`.
5. Guardalo en la carpeta del proyecto como **`afip.crt`**, al lado de
   `afip.key`.

---

## Paso 3 — Autorizar el certificado para facturar

Tener el certificado no alcanza: hay que decirle a AFIP que ese certificado
puede usar el servicio de facturación electrónica.

1. En el mismo sitio, entrá a **"Administrador de Relaciones de Clave Fiscal"**.
2. *Nueva Relación*.
3. Completá:
   - **Representado**: tu CUIT (o el de la entidad, si facturás por ella).
   - **Servicio**: buscá y elegí **"Facturación Electrónica"**
     (el servicio técnico se llama `wsfe`).
   - **Representante**: seleccioná el **certificado** que subiste en el paso 2
     (aparece por el alias que le pusiste).
4. Confirmá. Queda activo enseguida.

---

## Paso 4 — Dar de alta el punto de venta

Este paso se olvida seguido y es el que produce el error más confuso.

Los puntos de venta de **web services** son una numeración **separada** de los
del portal "Comprobantes en línea" (RCEL). Si venías facturando por la web, ese
punto de venta **no sirve** acá: hay que crear uno nuevo del tipo correcto.

1. En afip.gob.ar, entrá al servicio
   **"Administración de puntos de venta y domicilios"**.
2. *Agregar punto de venta*.
3. Elegí el sistema **"RECE para aplicativo y web services"**.
4. Anotá el número que te asigna: ese es el que va en `PUNTO_VENTA` en
   `config.py`.

---

## Paso 5 — Probar primero en homologación

AFIP tiene un ambiente de pruebas (**homologación**) donde los comprobantes
no tienen validez fiscal y no consumen numeración real. El proyecto apunta ahí
por defecto: hay que pasar `--produccion` explícitamente para emitir de verdad.

Para usar homologación hay que repetir los pasos 2 a 4 **en el sitio de
homologación**, que es independiente del de producción:

- Certificados de prueba: <https://wsass-homo.afip.gob.ar/wsass/portal/main.aspx>
- Ahí mismo se autoriza el servicio `wsfe` para el ambiente de pruebas.

Con eso listo:

```bash
python -m afip_facturacion --excel cuotas.xlsx --hoja Julio \
    --fecha 27/07/2026 --desde 01/07/2026 --hasta 31/07/2026 \
    --importe 21500 --descripcion "Cuota Social Julio 2026"
```

Si te devuelve CAE en homologación, la integración funciona. Recién ahí conviene
agregar `--produccion`.

---

## Errores frecuentes y qué significan

| Mensaje de AFIP | Qué pasó |
|---|---|
| `600 - CUIT no autorizado a acceder al servicio` | Falta el paso 3: el certificado no está asociado al servicio `wsfe`. |
| `602 - Sin resultados` / punto de venta inexistente | Falta el paso 4, o el punto de venta es de "Comprobantes en línea" en vez de web services. |
| `10242 - El campo Condicion IVA receptor es obligatorio` | Comprobante sin `CondicionIVAReceptorId`. El proyecto siempre lo manda, así que si aparece es porque la condición del receptor quedó en un valor que AFIP no acepta para ese tipo de comprobante. |
| `El CEE ya posee un TA valido` | Se pidió un ticket nuevo teniendo uno vigente. Pasa si se borró `afip_cache/`. Hay que esperar a que venza (hasta 12 horas). |
| `10016 - El numero de comprobante no es correlativo` | Alguien emitió comprobantes por otra vía (el portal web) entre medio. Volvé a correr: la numeración se consulta de nuevo en cada corrida. |

---

## Qué guardar y qué no

- `afip.key` y `afip.crt`: en la máquina que factura, con backup en un lugar
  seguro (no en el repositorio, no en un mail, no en un Drive compartido).
  Están en `.gitignore` justamente para que no se suban por accidente.
- `afip_cache/`: se puede borrar sin drama, salvo por lo dicho arriba sobre el
  ticket vigente. Se regenera solo.
- El Excel con los DNI de los socios: son datos personales de terceros.
  También está en `.gitignore`.
