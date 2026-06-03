import json
import socket
import time
from typing import Optional, Any
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

from infra.logger import obtener_logger

_log = obtener_logger("network_utils")


# -----------------------------------------------------------------------------
# Descubrimiento de interfaz LAN y seleccion de puerto (ecosistema movil)
# -----------------------------------------------------------------------------

def ip_lan_probable() -> str:
    """Devuelve la IP de la interfaz por la que sale el trafico a la LAN.

    Truco estandar: abrir un socket UDP "conectado" a una IP externa no
    enruta ni envia paquetes, pero el SO asigna la IP de origen de la
    interfaz adecuada (la del WiFi/ethernet activo), que es justo la que el
    celular debe usar. Fallback a 127.0.0.1 si no hay red.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 10.255.255.255 es no-enrutable globalmente; solo fuerza la
        # resolucion de la interfaz de salida. No se envia nada.
        sock.connect(("10.255.255.255", 1))
        ip = sock.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    finally:
        sock.close()
    # Segundo intento: resolver el hostname local.
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return "127.0.0.1"


def puerto_libre(host: str, inicio: int = 8731, fin: int = 8799) -> Optional[int]:
    """Devuelve el primer puerto TCP libre de [inicio, fin] en `host`, o None.

    Se enlaza y se cierra para comprobar disponibilidad. El puerto efectivo
    debe usarse inmediatamente para minimizar la ventana de carrera.
    """
    for puerto in range(int(inicio), int(fin) + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, puerto))
                return puerto
            except OSError:
                continue
    return None

class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, max_redirects: int = 3):
        self.max_redirects = max_redirects
        super().__init__()

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not hasattr(req, 'redirect_count'):
            req.redirect_count = 0
        if req.redirect_count >= self.max_redirects:
            raise HTTPError(req.full_url, code, f"Too many redirects ({req.redirect_count})", headers, fp)
        req.redirect_count += 1
        return super().redirect_request(req, fp, code, msg, headers, newurl)

_SAFE_OPENER = build_opener(_SafeRedirectHandler(max_redirects=3))


def safe_download_bytes(
    url: str,
    timeout: int,
    retries: int = 0,
    max_bytes: Optional[int] = None,
    headers: Optional[dict] = None,
    backoff_factor: float = 2.0,
) -> Optional[bytes]:
    """
    Descarga segura de bytes previniendo bucles infinitos de redirección
    y con manejo de timeouts.
    """
    intentos = max(retries, 0) + 1
    for intento in range(1, intentos + 1):
        try:
            req = Request(url, headers=headers or {
                "User-Agent": "NBSoundLocal/1.0",
                "Accept": "*/*",
            })
            with _SAFE_OPENER.open(req, timeout=timeout) as r:
                if r.status != 200:
                    return None
                limite = max_bytes or 0
                if limite > 0:
                    data = r.read(limite + 1)
                    if len(data) > limite:
                        _log.debug(f"Payload demasiado grande, descartado: {url}")
                        return None
                    return data
                return r.read()
        except (HTTPError, URLError, TimeoutError) as e:
            if intento >= intentos:
                _log.debug(f"Fallo de red definitivo en {url}: {e}")
                return None
            time.sleep(backoff_factor * intento)
    return None


def safe_download_json(
    url: str,
    timeout: int,
    retries: int = 0,
    headers: Optional[dict] = None,
    backoff_factor: float = 2.0,
) -> Optional[Any]:
    """Descarga segura de JSON."""
    raw = safe_download_bytes(url, timeout, retries, headers=headers, backoff_factor=backoff_factor)
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, (dict, list)):
            return data
        return None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
