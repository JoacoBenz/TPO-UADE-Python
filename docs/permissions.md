# Permisos del share: qué pedirle a IT

Este documento existe por una razón puntual, y conviene decirla sin vueltas:

> **Los chequeos de permisos que hace el launcher no son un control de acceso.**
> Son experiencia de usuario y defensa en profundidad. El control de acceso
> real son las ACLs de NTFS/DFS sobre las carpetas de los hubs.

Si todos los equipos pueden leer toda la carpeta de automatizaciones, cualquiera
abre el file browser de JupyterLab, se para en `_hubs/treasury/members.json` y lo
lee — sin pasar nunca por este código. Un `if` en Python no protege un archivo
que está a un click de distancia.

Con las ACLs puestas, las dos capas coinciden: la Contents API devuelve 403 en
los hubs ajenos, `build_principal()` no encuentra pertenencia ahí, y el usuario
ve exactamente lo mismo que le habría mostrado la política de la aplicación.

Para saber en cuál de los dos escenarios estás parado:

```
python -m automation_launcher doctor
```

La sección `[aislamiento entre equipos]` dice si el proceso puede leer todos los
hubs o si hay ACLs activas.

---

## Estructura de carpetas

```
<CONTENTS_DIR>\                      p. ej. jupyter\notebooks\automations
├── notebooks\                       biblioteca de .ipynb (lectura para todos)
└── _hubs\
    ├── registry.json                catálogo de hubs (lectura para todos)
    ├── treasury\                    ← una ACL propia por hub
    │   ├── hub.json
    │   ├── members.json             lo reescribe el jefe desde la UI
    │   ├── processes.json
    │   └── runs\                    historial, un archivo por día
    ├── clo_ops\                     ← ACL propia
    └── hg_settlement\               ← ACL propia
```

---

## Grupos de AD a crear

Dos por hub. La convención de nombres es lo de menos; lo que importa es que sean
dos y no uno.

| Grupo | Quiénes | Para qué |
|---|---|---|
| `AL-HUB-<hub>-MEMBERS` | todo el equipo, jefes incluidos | ver el hub y correr sus automatizaciones |
| `AL-HUB-<hub>-LEADS` | solo los jefes | además, editar `members.json` |

`AL-HUB-<hub>-LEADS` conviene anidarlo dentro de `AL-HUB-<hub>-MEMBERS`, así un
jefe no necesita figurar dos veces.

---

## ACLs por carpeta

### Raíz de automatizaciones y biblioteca de notebooks

Lectura para todos los usuarios del launcher. Los notebooks son código, no datos
de un equipo.

```bat
icacls "\\corp-fs01\automations"           /grant "CORP\AL-LAUNCHER-USERS:(OI)(CI)(RX)"
icacls "\\corp-fs01\automations\notebooks" /grant "CORP\AL-LAUNCHER-USERS:(OI)(CI)(RX)"
```

### `_hubs\` — el catálogo

`registry.json` es solo nombres y rutas de hubs: que sea legible para todos no
filtra nada y permite que el launcher los descubra. Lo que **no** se hereda es el
acceso al contenido de cada hub.

```bat
icacls "\\corp-fs01\automations\_hubs" /grant "CORP\AL-LAUNCHER-USERS:(RX)"
```

Sin `(OI)(CI)`: la lectura llega al directorio, no a lo que hay adentro.

### Carpeta de cada hub — **acá está la barrera**

```bat
set HUB=\\corp-fs01\automations\_hubs\treasury

REM 1. Cortar la herencia, quedandose con una copia de las ACEs actuales
icacls "%HUB%" /inheritance:d

REM 2. Sacar el acceso amplio que venia heredado
icacls "%HUB%" /remove:g "CORP\AL-LAUNCHER-USERS"
icacls "%HUB%" /remove:g "Authenticated Users"

REM 3. El equipo lee; escribe unicamente en runs\
icacls "%HUB%" /grant "CORP\AL-HUB-TREASURY-MEMBERS:(OI)(CI)(RX)"

REM 4. Los jefes ademas modifican members.json
icacls "%HUB%\members.json" /grant "CORP\AL-HUB-TREASURY-LEADS:(M)"

REM 5. Todo el equipo escribe el historial de corridas
icacls "%HUB%\runs" /grant "CORP\AL-HUB-TREASURY-MEMBERS:(OI)(CI)(M)"

REM 6. Administradores del launcher
icacls "%HUB%" /grant "CORP\AL-LAUNCHER-ADMINS:(OI)(CI)(F)"
```

Repetir por hub, cambiando `%HUB%` y el nombre de los grupos.

### Verificación

```bat
icacls "\\corp-fs01\automations\_hubs\treasury"
```

En la salida **no** tiene que aparecer `AL-LAUNCHER-USERS` ni `Authenticated
Users`. Si aparecen, la separación entre equipos todavía no existe.

---

## Cómo comprobar que quedó bien

1. **Desde una cuenta que no sea de Treasury**, abrir el file browser de
   JupyterLab e intentar entrar a `_hubs\treasury`. Tiene que fallar.
2. Con esa misma cuenta:
   ```
   python -m automation_launcher whoami
   ```
   No debe listar `treasury`.
3. Como jefe de Treasury, agregar a alguien desde el tab **Miembros**. Tiene que
   guardar sin error.
4. Como miembro común de Treasury, comprobar que el tab **Miembros** no aparece
   y que `members.json` no se puede escribir a mano.

---

## Preguntas que suelen aparecer

**¿Por qué el equipo necesita escritura en `runs\`?**
Porque el historial lo escribe el proceso del usuario que corre la
automatización, y es lo que alimenta el tab de métricas del jefe. Si solo
escribieran los jefes, el historial quedaría casi vacío.

**¿Por qué el registro de auditoría no está en el share?**
Porque un rechazo tiene que quedar anotado *incluso cuando la persona rechazada
no tiene permiso de escribir en ningún lado*. Va a un archivo local del servidor
(`AUDIT_LOG_PATH`). Si querés centralizarlo, apuntá esa ruta a una carpeta donde
escriba la cuenta de servicio del launcher, no los usuarios.

**¿Qué pasa si un hub se queda sin jefe?**
El launcher lo impide desde la UI: `save_membership` rechaza dejar `leads` vacío.
Si igual pasara — alguien editó el JSON a mano —, `doctor` lo reporta y hay que
arreglarlo con una cuenta de `AL-LAUNCHER-ADMINS`.

**¿Alcanza con esto para decir que hay RLS?**
Row-level security en el sentido estricto — políticas por fila en un motor de
base de datos — no, porque no hay base de datos. Lo que hay es aislamiento por
equipo apoyado en el control de acceso del sistema de archivos, con la
aplicación aplicando la misma regla por segunda vez y dejando registro de cada
decisión. Si mañana aparece un Postgres, `core/repository.py` es la única pieza
que hay que reimplementar: la política, la interfaz y toda la UI quedan igual.
