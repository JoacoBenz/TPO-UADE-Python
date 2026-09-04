# Automation Launcher

Panel web para correr automatizaciones en Jupyter, servido con **Voila**. Cada
equipo tiene su **hub**: ve solamente sus procesos, los corre desde el navegador
y sigue la salida en una consola en vivo. El jefe del equipo administra quién
entra y tiene un tab de métricas.

Está pensado para un entorno controlado donde Jupyter es lo único disponible:
las carpetas llegan por **DFS/SMB** (montadas con jupyterfs) y la autenticación
se hace contra el share administrativo `IPC$`, porque no hay otro proveedor de
identidad al que preguntarle.

---

## Probarlo ahora, sin nada instalado

```bash
./run_local.sh          # Linux / macOS
run_local.bat           # Windows
```

Levanta `http://localhost:8866` con un share de mentira (`demo/share`) y tres
hubs cargados. No hace falta red de la empresa, ni SMB, ni credenciales reales.
El código que corre es exactamente el mismo que va a producción.

Entrá con **cualquier contraseña de 4 caracteres o más**. El selector del login
te deja ver la aplicación con los ojos de distintos roles:

| Usuario | Qué muestra |
|---|---|
| `ana.g` | jefa de Treasury: ve los tabs **Miembros** y **Métricas** |
| `joaquin.benz` | miembro de dos hubs: selector de hub, sin tabs de jefe |
| `carlos.m` | jefe de CLO y miembro de Treasury: jefe en uno solo |
| `lucia.r` | un solo hub: entra directo, sin selector |
| `intruso` | sin ningún hub: muestra el rechazo y su registro de auditoría |

Entrar como `carlos.m` y comparar los dos hubs es la forma más rápida de ver el
aislamiento funcionando: en CLO tiene los tabs de jefe, en Treasury no.

Los notebooks de demo cubren los cuatro finales posibles: `ok` termina bien,
`warns` avisa (ámbar), `fails` explota (rojo), `slow` dura un minuto para probar
el botón **Stop**, y `needs_creds` pide credenciales por consola e intenta
imprimir la contraseña de tres formas distintas — sirve para verificar que el
redactor las tapa.

---

## Cómo está organizado

La decisión que sostiene el proyecto: **`core/` no importa `ipywidgets`.**

```
core\    config, autorización, ejecución, historial, métricas   Python puro
ui\      la capa de widgets, construida sobre core
cli.py   la misma lógica desde la terminal
```

Gracias a eso los tests corren sin levantar Jupyter, el motor se reusa desde una
CLI para automatizaciones agendadas, y la lógica de autorización — la parte que
no se puede equivocar — se prueba a fondo sin abrir un navegador.

```
launcher_config.py               configuración del deploy (no se versiona)
launcher_config.example.py       plantilla comentada campo por campo
app.ipynb                        el notebook de Voila: 5 líneas

automation_launcher/
  core/
    models.py        Hub, Process, Principal, RunRecord, Credentials
    config.py        carga launcher_config.py con defaults del lado del código
    secrets.py       Redactor: tapa la contraseña en todo texto que sale
    contents.py      Contents API de Jupyter + backend local, misma interfaz
    authz.py         la política: el único lugar donde se decide quién puede qué
    repository.py    acceso al share, siempre acotado a un principal
    auth.py          IPC$ sobre SMB, y un backend mock para desarrollo
    engine.py        ejecución de notebooks en hilos, con cancelación
    console.py       buffer circular de la consola
    history.py       historial de corridas y registro de auditoría
    metrics.py       agregaciones para el tab del jefe
  ui/
    theme.py         todo el CSS en un solo lugar
    widgets.py       componentes: tarjetas, consola, botones
    login.py         la pantalla de ingreso
    dashboard.py     el control room
    members.py       administración de miembros (solo jefes)
    metrics_tab.py   métricas (solo jefes)
    app.py           el router que arma todo
  cli.py             list | run | doctor | whoami

tools/
  build_single_notebook.py   empaqueta todo en un .ipynb autocontenido
  check_py37.py              verifica compatibilidad con el kernel Athena
tests/                       172 tests, sin Jupyter
demo/                        share falso y notebooks de juguete
docs/permissions.md          las ACLs que hay que pedirle a IT
```

---

## El modelo de permisos

### Cómo se decide

Un `Principal` tiene un rol **por hub** — no un rol global. Los roles no se los
pasa nadie: se derivan de los `members.json` que hay en el share, así que cuando
un jefe agrega a alguien, en el próximo ingreso ya está, sin redeploy.

| Acción | Miembro | Jefe |
|---|:--:|:--:|
| Ver el hub y sus automatizaciones | ✅ | ✅ |
| Ejecutar automatizaciones | ✅ | ✅ |
| Ver el historial | ✅ | ✅ |
| Ver el tab de Métricas | ❌ | ✅ |
| Agregar y sacar gente | ❌ | ✅ |

Todo pasa por `core/authz.py`. No hay chequeos de permisos desparramados por la
interfaz: si un botón se dibuja o no, y si una corrida arranca o no, sale
siempre de `Policy.check`. Cada decisión, permitida o denegada, queda en el
registro de auditoría.

El acceso a los datos va por `HubRepository`, que recibe el principal **en el
constructor**. No existe forma de pedirle un hub al que no pertenecés: no es que
filtre después de traer los datos, es que no los va a buscar.

### Qué protege de verdad, y qué no

Hay que ser preciso acá, porque es lo primero que va a preguntar una revisión:

> Los chequeos de la aplicación son **defensa en profundidad y experiencia de
> usuario**. La barrera dura es la **ACL de NTFS/DFS sobre la carpeta de cada
> hub**. Sin esas ACLs hay segregación, no seguridad: cualquiera abre el file
> browser de JupyterLab y lee la carpeta de otro equipo.

Las dos capas coinciden por diseño: con las ACLs puestas, la Contents API
devuelve 403 en los hubs ajenos y la aplicación llega al mismo resultado.

`python -m automation_launcher doctor` te dice en cuál de los dos escenarios
estás. Las ACLs exactas para pedirle a IT están en
**[`docs/permissions.md`](docs/permissions.md)**.

---

## Las credenciales

El launcher pide la contraseña de red porque la necesita dos veces: para
verificar quién sos (conectándose a `IPC$`) y para responder por vos cuando un
notebook llama a `getpass()` o `input()`. Sin eso, los procesos que suben a DTC
y compañía se quedarían colgados esperando a alguien que escriba.

Eso obliga a tratar el secreto con cuidado:

- **Nunca toca el disco.** Ni la configuración, ni el historial, ni la consola,
  ni un notebook de salida.
- Vive en memoria mientras dura la sesión; **Sign Out lo borra**.
- `Credentials.__repr__` devuelve `password=***`, para que no se escape por un
  `print` o un traceback.
- Se pasa a los notebooks **por variable de entorno**, nunca por línea de
  comandos: los argumentos de un proceso los ve cualquiera en la máquina.
- Todo texto que va a pantalla o a un archivo pasa antes por `secrets.Redactor`,
  que también tapa las variantes URL-encoded y escapadas en HTML.

Hay un test que lo verifica sobre las tres salidas, con un notebook que intenta
filtrar la contraseña a propósito de tres formas distintas.

---

## Instalar en el trabajo

1. Copiar el repositorio (o el `.ipynb` autocontenido, ver abajo) al servidor.
2. `cp launcher_config.example.py launcher_config.py` y ajustar
   `CONTENTS_DIR`, `AUTH_HOST` y `AUTH_DOMAIN`.
3. Crear la estructura de `_hubs\` en el share, con un `members.json` y un
   `processes.json` por equipo (`demo/share/_hubs/` sirve de molde).
4. Aplicar las ACLs de [`docs/permissions.md`](docs/permissions.md).
5. `python -m automation_launcher doctor` hasta que no reporte problemas.
6. `voila app.ipynb`

### Si solo podés mover un archivo

```bash
python tools/build_single_notebook.py
```

Genera `dist/automation_launcher_standalone.ipynb`: el paquete entero adentro de
un notebook, sin dependencias del repositorio. Se copia junto a un
`launcher_config.py` y se sirve igual con `voila`.

Ese notebook **no se edita a mano**: se regenera. Se sigue desarrollando en los
`.py`, que git compara y pytest prueba; el bundle es solo el formato de entrega.

---

## Configuración

Todo vive en `launcher_config.py`. Cada clave tiene un valor por defecto del
lado del código, así que el archivo puede tener solo lo que cambia, y una clave
faltante o un share inalcanzable **no rompen la aplicación**: arranca en modo
degradado y lo dice en la consola.

Las que más se tocan:

| Clave | Para qué |
|---|---|
| `CONTENTS_DIR` | raíz de las automatizaciones dentro de la Contents API |
| `AUTH_HOST`, `AUTH_DOMAIN` | contra qué host SMB se valida la contraseña |
| `TOKEN_ENV` | variable de entorno con el token de Jupyter |
| `MAX_CONCURRENT_RUNS` | cuántas automatizaciones pueden correr a la vez |
| `CONSOLE_REFRESH_MS` | cada cuánto se repinta la consola |
| `LOCAL_SHARE_ROOT` | apunta a una carpeta local: es el modo desarrollo |

`launcher_config.example.py` tiene todas, comentadas una por una.

---

## Desde la terminal

Como el núcleo no depende de widgets, todo se puede manejar sin navegador:

```bash
python -m automation_launcher doctor              # diagnóstico del entorno
python -m automation_launcher whoami --sid ana.g  # permisos efectivos
python -m automation_launcher list --sid ana.g    # automatizaciones visibles
python -m automation_launcher run eod_positions --hub treasury
```

`doctor` es lo primero que conviene correr cuando algo no anda: reporta la
configuración, el acceso al share, el estado de cada hub, si las ACLs están
puestas y qué backend de ejecución hay disponible.

`run` sirve para agendar automatizaciones en un scheduler, sin interfaz.

---

## Desarrollo

```bash
python -m pip install -r requirements-dev.txt
python -m pytest                        # 172 tests, sin Jupyter
ruff check .
python tools/check_py37.py              # compatibilidad con el kernel Athena
```

### Sobre Python 3.7

El kernel de producción (Athena) es **Python 3.7**, así que el código evita todo
lo posterior: nada de operador morsa, parámetros posicionales, `typing.Protocol`
ni `statistics.quantiles`. `tools/check_py37.py` lo verifica de dos maneras —
parsea cada archivo con la gramática de 3.7 y busca por nombre funciones de la
biblioteca estándar que entraron después.

Ese mismo código corre sin cambios en 3.11, que es lo que permite desarrollar
local con una versión moderna.

---

## Detalles de implementación que conviene conocer

**Las corridas van en hilos del mismo proceso, no en subprocesos.** Es la única
forma de responder por el usuario cuando un notebook llama a `getpass()`, porque
para eso hay que reemplazar esa función en el intérprete que ejecuta el código.
Como `sys.stdout` y `getpass` son globales, el parche se instala **una sola vez**
y funciona como enrutador: mira qué hilo está escribiendo y manda la salida a la
consola de esa corrida. Así dos automatizaciones en paralelo no se mezclan.

**El Stop tiene un límite conocido.** Cancelar un hilo usa
`PyThreadState_SetAsyncExc`, que solo entrega la excepción cuando el hilo está
ejecutando bytecode de Python. Si el notebook está bloqueado en una llamada de
red, el corte no ocurre hasta que esa llamada vuelve: el launcher marca la
corrida como cancelada y libera el lugar en la cola, pero el trabajo de fondo
puede seguir un rato. No es un bug, es la limitación de la técnica.

**La consola se repinta agrupada por tiempo**, como máximo cada
`CONSOLE_REFRESH_MS`. Repintar por línea satura el websocket de Voila y traba el
navegador con notebooks verbosos.

**El historial está partido en un archivo por día.** Con un año de corridas, un
solo archivo obligaría a bajar decenas de megabytes por SMB cada vez que alguien
abre el tab de métricas.

---

## Lo que falta probar en el trabajo

Tres cosas no se pueden verificar fuera de la red de la empresa. Están cubiertas
por tests que simulan `subprocess` y `requests`, pero la prueba real es allá:

1. `SmbAuth` contra un `IPC$` de verdad (necesita Windows y dominio).
2. La Contents API con el token de Athena.
3. jupyterfs montando el share SMB.

`python -m automation_launcher doctor` valida las tres en un solo paso.
