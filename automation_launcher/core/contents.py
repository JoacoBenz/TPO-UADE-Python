"""Acceso al share: una sola interfaz, dos implementaciones.

En produccion el share SMB esta montado por jupyterfs y se lee a traves de la
Contents API de Jupyter (HTTP, con token). En una maquina de desarrollo no hay
ni Jupyter ni SMB, asi que la misma interfaz se implementa sobre el sistema de
archivos local.

Que las dos expongan exactamente los mismos metodos es lo que permite que el
resto del launcher no sepa donde esta parado: el codigo que corre en tu
notebook local es literalmente el mismo que corre en produccion.

    class ContentsBackend:
        def list_dir(path)   -> List[Entry]
        def read_text(path)  -> str
        def read_json(path)  -> Any
        def write_json(path, data)
        def exists(path)     -> bool

Todas las rutas son relativas a la raiz del backend, con "/" como separador.
"""

from __future__ import annotations

import json
import os
import posixpath
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # solo para los comentarios `# type:` de abajo
    from typing import Any, Dict, List, Optional  # noqa: F401  (los usan los comentarios `# type:`)

# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------

class ContentsError(Exception):
    """Fallo generico al hablar con el backend de contenidos."""


class NotFound(ContentsError):
    """La ruta pedida no existe."""


class AccessDenied(ContentsError):
    """El backend respondio 403.

    Vale la pena distinguirlo de ``NotFound``: cuando las ACLs de NTFS estan
    puestas, un hub ajeno se manifiesta como este error, y el repositorio lo
    trata como "no existe para vos" en lugar de como una falla.
    """


# ---------------------------------------------------------------------------
# Entrada de directorio
# ---------------------------------------------------------------------------

class Entry:
    """Un archivo o carpeta listado en el share."""

    __slots__ = ("name", "path", "type", "size", "last_modified")

    def __init__(self, name, path, type_, size=0, last_modified=""):
        # type: (str, str, str, int, str) -> None
        self.name = name
        self.path = path
        self.type = type_          # "directory" | "notebook" | "file"
        self.size = size
        self.last_modified = last_modified

    @property
    def is_dir(self):
        # type: () -> bool
        return self.type == "directory"

    @property
    def is_notebook(self):
        # type: () -> bool
        return self.type == "notebook" or self.name.endswith(".ipynb")

    def __repr__(self):
        # type: () -> str
        return f"Entry({self.path!r}, {self.type!r})"


def join(*parts):
    # type: (*str) -> str
    """Une segmentos de ruta del share y normaliza.

    Rechaza cualquier segmento que intente salir de la raiz. Los ids de hub y
    de proceso vienen de archivos JSON en el share, asi que se los trata como
    entrada no confiable aunque hoy los escriban personas de confianza.
    """
    cleaned = []    # type: List[str]
    for part in parts:
        if not part:
            continue
        text = str(part).replace("\\", "/").strip("/")
        if not text:
            continue
        for segment in text.split("/"):
            if segment in ("", "."):
                continue
            if segment == "..":
                raise ValueError("ruta invalida: '..' no esta permitido")
            cleaned.append(segment)
    return posixpath.join(*cleaned) if cleaned else ""


# ---------------------------------------------------------------------------
# Cache con expiracion
# ---------------------------------------------------------------------------

class _TTLCache:
    """Cache chico con expiracion por tiempo.

    Cada lectura del share es un round-trip HTTP y, por debajo, SMB sobre la
    red corporativa. Sin cache, redibujar el dashboard cuesta decenas de
    llamadas. Con TTL corto la UI sigue sintiendose viva y el boton Refresh
    lo limpia explicitamente.
    """

    def __init__(self, ttl_seconds=30):
        # type: (int) -> None
        self.ttl = max(0, int(ttl_seconds))
        self._lock = threading.RLock()
        self._data = {}     # type: Dict[str, Any]

    def get(self, key):
        # type: (str) -> Any
        if self.ttl <= 0:
            return None
        with self._lock:
            hit = self._data.get(key)
        if not hit:
            return None
        stored_at, value = hit
        if time.time() - stored_at > self.ttl:
            with self._lock:
                self._data.pop(key, None)
            return None
        return value

    def put(self, key, value):
        # type: (str, Any) -> None
        if self.ttl <= 0:
            return
        with self._lock:
            self._data[key] = (time.time(), value)

    def clear(self):
        # type: () -> None
        with self._lock:
            self._data.clear()


# ---------------------------------------------------------------------------
# Backend: Contents API de Jupyter (produccion)
# ---------------------------------------------------------------------------

class JupyterContentsClient:
    """Lee y escribe el share a traves de la Contents API de Jupyter.

    La autenticacion se resuelve por estrategias en orden, porque segun como
    se haya levantado el kernel el token aparece en un lado o en otro:

      1. token pasado explicitamente
      2. la variable de entorno de ``TOKEN_ENV``
      3. la variable de ``FALLBACK_TOKEN_ENV``
      4. ``JUPYTER_TOKEN``
      5. sin token (cuando el servidor no lo exige)

    La primera que devuelva algo distinto de 401/403 gana, y queda fijada para
    las llamadas siguientes.
    """

    def __init__(self, base_url, token=None, token_env=None, fallback_token_env=None,
                 verify_tls=False, timeout=30, cache_ttl=30, session=None):
        # type: (str, Optional[str], Optional[str], Optional[str], bool, int, int, Any) -> None
        self.base_url = (base_url or "").rstrip("/")
        self.verify_tls = bool(verify_tls)
        self.timeout = int(timeout)
        self._cache = _TTLCache(cache_ttl)
        self._session = session
        self._token_candidates = self._collect_tokens(token, token_env, fallback_token_env)
        self._active_token = None       # type: Optional[str]
        self._token_locked = False

    @staticmethod
    def _collect_tokens(token, token_env, fallback_token_env):
        # type: (Optional[str], Optional[str], Optional[str]) -> List[Optional[str]]
        candidates = []     # type: List[Optional[str]]
        if token:
            candidates.append(token)
        for env_name in (token_env, fallback_token_env, "JUPYTER_TOKEN"):
            if not env_name:
                continue
            value = os.environ.get(env_name)
            if value and value not in candidates:
                candidates.append(value)
        candidates.append(None)     # ultimo intento: servidor sin token
        return candidates

    # -- HTTP ---------------------------------------------------------------

    def _get_session(self):
        # type: () -> Any
        if self._session is None:
            import requests  # import diferido: el core no lo necesita para testear
            self._session = requests.Session()
        return self._session

    def _url(self, path):
        # type: (str) -> str
        import urllib.parse
        safe = urllib.parse.quote(path.strip("/"), safe="/")
        return f"{self.base_url}/api/contents/{safe}"

    def _request(self, method, path, payload=None):
        # type: (str, str, Optional[Dict[str, Any]]) -> Any
        session = self._get_session()
        url = self._url(path)
        tokens = [self._active_token] if self._token_locked else self._token_candidates
        last_error = None       # type: Optional[Exception]

        for token in tokens:
            headers = {"Accept": "application/json"}
            if token:
                headers["Authorization"] = f"token {token}"
            if payload is not None:
                headers["Content-Type"] = "application/json"
            try:
                response = session.request(
                    method, url, headers=headers,
                    json=payload if payload is not None else None,
                    verify=self.verify_tls, timeout=self.timeout,
                )
            except Exception as exc:
                last_error = exc
                continue

            if response.status_code in (401, 403):
                # Con el token fijado, un 403 ya no es un problema de auth
                # sino una ACL: el usuario no puede ver esta ruta.
                if self._token_locked:
                    raise AccessDenied(f"403 en {path}")
                last_error = AccessDenied(f"{response.status_code} en {path}")
                continue
            if response.status_code == 404:
                self._lock_token(token)
                raise NotFound(path)
            if response.status_code >= 400:
                self._lock_token(token)
                raise ContentsError(
                    f"{method} {path} -> HTTP {response.status_code}"
                )

            self._lock_token(token)
            if method == "GET":
                return response.json()
            return None

        if isinstance(last_error, ContentsError):
            raise last_error
        raise ContentsError(
            f"no se pudo hablar con la Contents API en {self.base_url}: {last_error}"
        )

    def _lock_token(self, token):
        # type: (Optional[str]) -> None
        if not self._token_locked:
            self._active_token = token
            self._token_locked = True

    # -- interfaz ------------------------------------------------------------

    def list_dir(self, path):
        # type: (str) -> List[Entry]
        cache_key = "list:" + path
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        data = self._request("GET", path)
        if data.get("type") != "directory":
            raise ContentsError(f"{path} no es un directorio")
        entries = [
            Entry(
                name=item.get("name", ""),
                path=item.get("path", ""),
                type_=item.get("type", "file"),
                size=int(item.get("size") or 0),
                last_modified=str(item.get("last_modified") or ""),
            )
            for item in data.get("content") or []
        ]
        self._cache.put(cache_key, entries)
        return entries

    def read_text(self, path):
        # type: (str) -> str
        cache_key = "text:" + path
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        data = self._request("GET", path)
        content = data.get("content")
        if data.get("format") == "base64" and isinstance(content, str):
            import base64
            text = base64.b64decode(content).decode("utf-8", "replace")
        elif isinstance(content, (dict, list)):
            text = json.dumps(content)
        else:
            text = content if isinstance(content, str) else ""
        self._cache.put(cache_key, text)
        return text

    def read_json(self, path):
        # type: (str) -> Any
        text = self.read_text(path)
        try:
            return json.loads(text)
        except ValueError as exc:
            raise ContentsError(f"{path} no es JSON valido: {exc}") from exc

    def write_json(self, path, data):
        # type: (str, Any) -> None
        payload = {
            "type": "file",
            "format": "text",
            "content": json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True),
        }
        self._request("PUT", path, payload)
        self._cache.clear()

    def write_text(self, path, text):
        # type: (str, str) -> None
        """Escribe texto crudo (para .jsonl, que no es un documento JSON)."""
        self._request("PUT", path, {"type": "file", "format": "text", "content": text})
        self._cache.clear()

    def exists(self, path):
        # type: (str) -> bool
        try:
            self._request("GET", path)
            return True
        except (NotFound, AccessDenied):
            return False
        except ContentsError:
            return False

    def clear_cache(self):
        # type: () -> None
        self._cache.clear()

    def describe(self):
        # type: () -> str
        return "Contents API en {}".format(self.base_url or "<sin URL>")


# ---------------------------------------------------------------------------
# Backend: sistema de archivos local (desarrollo y demo)
# ---------------------------------------------------------------------------

class LocalContentsClient:
    """La misma interfaz, contra una carpeta local.

    Es lo que permite correr y testear el launcher completo sin Jupyter, sin
    SMB y sin red: se le apunta a ``demo/share`` y la app no nota diferencia.

    Tambien respeta los permisos del sistema de archivos: si una carpeta no es
    legible levanta ``AccessDenied``, igual que la Contents API con un 403.
    Eso hace que el comportamiento con ACLs se pueda probar de verdad en local
    con un simple ``chmod``.
    """

    def __init__(self, root, cache_ttl=0):
        # type: (str, int) -> None
        self.root = os.path.abspath(root)
        self._cache = _TTLCache(cache_ttl)

    def _resolve(self, path):
        # type: (str) -> str
        relative = join(path)
        full = os.path.abspath(os.path.join(self.root, relative))
        # Defensa en profundidad: aunque join() ya rechaza "..", se verifica
        # que el resultado siga adentro de la raiz.
        if full != self.root and not full.startswith(self.root + os.sep):
            raise ContentsError(f"ruta fuera de la raiz: {path}")
        return full

    def list_dir(self, path):
        # type: (str) -> List[Entry]
        full = self._resolve(path)
        if not os.path.isdir(full):
            raise NotFound(path)
        entries = []    # type: List[Entry]
        try:
            names = sorted(os.listdir(full))
        except PermissionError:
            raise AccessDenied(path) from None
        for name in names:
            if name.startswith("."):
                continue
            child = os.path.join(full, name)
            rel = join(path, name)
            if os.path.isdir(child):
                kind = "directory"
                size = 0
            else:
                kind = "notebook" if name.endswith(".ipynb") else "file"
                size = os.path.getsize(child)
            entries.append(
                Entry(
                    name=name, path=rel, type_=kind, size=size,
                    last_modified=time.strftime(
                        "%Y-%m-%dT%H:%M:%S", time.gmtime(os.path.getmtime(child))
                    ),
                )
            )
        return entries

    def read_text(self, path):
        # type: (str) -> str
        full = self._resolve(path)
        if not os.path.isfile(full):
            raise NotFound(path)
        try:
            with open(full, encoding="utf-8") as handle:
                return handle.read()
        except PermissionError:
            raise AccessDenied(path) from None

    def read_json(self, path):
        # type: (str) -> Any
        text = self.read_text(path)
        try:
            return json.loads(text)
        except ValueError as exc:
            raise ContentsError(f"{path} no es JSON valido: {exc}") from exc

    def write_json(self, path, data):
        # type: (str, Any) -> None
        full = self._resolve(path)
        parent = os.path.dirname(full)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        # Escritura atomica: se escribe al lado y se renombra, para que un
        # corte a mitad de camino no deje un members.json truncado.
        temp = full + ".tmp"
        try:
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=True)
            os.replace(temp, full)
        except PermissionError:
            raise AccessDenied(path) from None
        finally:
            if os.path.exists(temp):
                os.remove(temp)
        self._cache.clear()

    def write_text(self, path, text):
        # type: (str, str) -> None
        """Escribe texto crudo. Lo usa el historial, que es JSONL y no JSON."""
        full = self._resolve(path)
        parent = os.path.dirname(full)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        temp = full + ".tmp"
        try:
            with open(temp, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(temp, full)
        except PermissionError:
            raise AccessDenied(path) from None
        finally:
            if os.path.exists(temp):
                os.remove(temp)
        self._cache.clear()

    def exists(self, path):
        # type: (str) -> bool
        try:
            return os.path.exists(self._resolve(path))
        except ContentsError:
            return False

    def clear_cache(self):
        # type: () -> None
        self._cache.clear()

    def describe(self):
        # type: () -> str
        return f"carpeta local {self.root}"


# ---------------------------------------------------------------------------
# Fabrica
# ---------------------------------------------------------------------------

def build_client(config):
    # type: (Any) -> Any
    """Elige el backend segun la config.

    ``LOCAL_SHARE_ROOT`` gana sobre todo lo demas: es el interruptor que pone
    al launcher en modo local sin tocar ninguna otra clave.
    """
    local_root = config.get("LOCAL_SHARE_ROOT")
    if local_root:
        return LocalContentsClient(local_root, cache_ttl=0)

    base_url = config.get("JUPYTER_URL") or _detect_jupyter_url()
    return JupyterContentsClient(
        base_url=base_url,
        token_env=config.get("TOKEN_ENV"),
        fallback_token_env=config.get("FALLBACK_TOKEN_ENV"),
        verify_tls=config.get("VERIFY_TLS"),
        timeout=config.get("REQUEST_TIMEOUT"),
        cache_ttl=config.get("CACHE_TTL_SECONDS"),
    )


def _detect_jupyter_url():
    # type: () -> str
    """Adivina la URL del servidor Jupyter desde el entorno del kernel."""
    for name in ("JUPYTERHUB_SERVICE_URL", "JUPYTER_SERVER_URL", "JPY_API_URL"):
        value = os.environ.get(name)
        if value:
            return value.rstrip("/")
    host = os.environ.get("JUPYTER_HOST") or "127.0.0.1"
    port = os.environ.get("JUPYTER_PORT") or "8888"
    return f"http://{host}:{port}"
