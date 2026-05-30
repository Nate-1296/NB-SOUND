# =============================================================================
# servicios/servidor_sync.py
#
# Servidor local del ecosistema movil (lado PC). HTTP REST + WebSocket sobre
# aiohttp, corriendo en su PROPIO hilo con su PROPIO event loop, aislado del
# event loop de Qt. La UI nunca bloquea: se comunica con este servidor por
# callbacks/colas, nunca compartiendo objetos Qt entre hilos.
#
# Arranque BAJO DEMANDA (no al iniciar la app). Ver docs/mobile-ecosystem.md.
#
# Seguridad (v1):
#   - Emparejamiento por QR con token efimero (TTL corto, un solo uso).
#   - Todo el trafico (salvo /ping y /pair) autenticado con `device_token`
#     persistente (header Authorization: Bearer ...).
#   - Bind a la IP de la subred LAN (nunca 0.0.0.0 publico).
#   - TLS: NO en v1 (LAN + token). Trade-off documentado en mobile-ecosystem.md
#     (la opcion minima v1 explicitamente contemplada). El campo
#     `tls_fingerprint` del QR queda vacio para forward-compat del cliente.
#
# Complejidad: alta. El teardown es determinista y con timeout: detener() no
# deja hilos ni puertos colgados (cubierto por tests de lifecycle).
# =============================================================================

from __future__ import annotations

import asyncio
import importlib.util
import threading
import time
from typing import Any, Callable, Optional

from infra.logger import obtener_logger
from servicios import sync_repositorio
from utils.network import ip_lan_probable, puerto_libre

_log = obtener_logger("servidor_sync")

# Nombre del servicio mDNS (DNS-SD). El celular descubre el PC por aqui cuando
# ya esta emparejado (el QR es el camino primario para el primer emparejamiento).
TIPO_SERVICIO_MDNS = "_nbsound._tcp.local."

# TTL del token de emparejamiento efimero (segundos).
TTL_TOKEN_EMPAREJAMIENTO = 300

RANGO_PUERTOS = (8731, 8799)


def dependencias_disponibles() -> tuple[bool, list[str]]:
    """(servidor_arrancable, lista_de_faltantes).

    aiohttp es imprescindible para el servidor. zeroconf (mDNS) y qrcode son
    mejoras: sin ellas el servidor arranca igual (QR/descubrimiento degradados).
    """
    faltantes = [m for m in ("aiohttp", "zeroconf", "qrcode") if importlib.util.find_spec(m) is None]
    arrancable = importlib.util.find_spec("aiohttp") is not None
    return arrancable, faltantes


class ServidorSync:
    """Servidor de sincronizacion local. Arranque/parada idempotentes.

    Parametros:
      comando_control: callable(dict) -> dict | None. Se invoca (en el hilo del
        servidor) cuando llega un comando por WS. DEBE ser thread-safe y no
        bloquear: el modelo Qt lo implementa marshalando al hilo de Qt. Devuelve
        un dict de ack opcional.
      estado_provider: callable() -> dict. Devuelve el estado actual del
        reproductor para el frame inicial que recibe un cliente WS al conectar.
      on_dispositivo_emparejado: callable(dict). Notifica (hilo servidor) que un
        device se emparejo, para que la UI refresque la lista y el QR.
      nombre_servicio: nombre legible anunciado por mDNS.
    """

    def __init__(
        self,
        *,
        comando_control: Optional[Callable[[dict], Optional[dict]]] = None,
        estado_provider: Optional[Callable[[], dict]] = None,
        on_dispositivo_emparejado: Optional[Callable[[dict], None]] = None,
        nombre_servicio: str = "NB Sound",
        rango_puertos: tuple[int, int] = RANGO_PUERTOS,
        host: Optional[str] = None,
        anunciar_mdns: bool = True,
    ) -> None:
        self._comando_control = comando_control
        self._estado_provider = estado_provider
        self._on_dispositivo_emparejado = on_dispositivo_emparejado
        self._nombre_servicio = nombre_servicio
        self._rango_puertos = rango_puertos
        # host fijo opcional (tests/loopback). Si es None se autodetecta la LAN.
        self._host_forzado = host
        self._mdns_habilitado = anunciar_mdns

        self._lock = threading.RLock()
        self._activo = False
        self._host: Optional[str] = None
        self._puerto: Optional[int] = None

        self._hilo: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._runner = None
        self._site = None
        self._app = None
        self._listo = threading.Event()
        self._error_arranque: Optional[str] = None

        self._ws_clientes: set = set()
        self._zeroconf = None
        self._mdns_info = None

        self._pairing_token: Optional[str] = None
        self._pairing_expira: float = 0.0

    # ── Propiedades de estado ────────────────────────────────────────────────

    @property
    def activo(self) -> bool:
        return self._activo

    @property
    def host(self) -> Optional[str]:
        return self._host

    @property
    def puerto(self) -> Optional[int]:
        return self._puerto

    def numero_clientes_ws(self) -> int:
        return len(self._ws_clientes)

    def info(self) -> dict:
        """Snapshot serializable del estado (para el modelo Qt / UI)."""
        return {
            "activo": self._activo,
            "host": self._host,
            "puerto": self._puerto,
            "version_protocolo": sync_repositorio.PROTOCOLO_VERSION,
            "pairing_token": self._pairing_token if self._token_vigente() else None,
            "clientes_ws": self.numero_clientes_ws(),
            "error": self._error_arranque,
        }

    def payload_qr(self) -> Optional[dict]:
        """Contenido a codificar en el QR de emparejamiento.

        El cliente lee host+puerto+token y llama /pair. `tls_fingerprint` vacio
        en v1 (sin TLS); el campo se mantiene para forward-compat del cliente.
        """
        if not self._activo or not self._token_vigente():
            return None
        return {
            "host": self._host,
            "puerto": self._puerto,
            "token": self._pairing_token,
            "version": sync_repositorio.PROTOCOLO_VERSION,
            "tls_fingerprint": "",
            "servicio": self._nombre_servicio,
        }

    # ── Token de emparejamiento efimero ──────────────────────────────────────

    def _token_vigente(self) -> bool:
        return bool(self._pairing_token) and time.monotonic() < self._pairing_expira

    def regenerar_token(self) -> str:
        """Emite un nuevo token efimero (invalida el anterior). Devuelve el token."""
        self._pairing_token = sync_repositorio.generar_token()
        self._pairing_expira = time.monotonic() + TTL_TOKEN_EMPAREJAMIENTO
        return self._pairing_token

    # ── Ciclo de vida ────────────────────────────────────────────────────────

    def iniciar(self) -> dict:
        """Arranca el servidor (idempotente). Devuelve `info()`.

        Selecciona un puerto libre del rango, levanta aiohttp en un hilo propio
        y anuncia el servicio por mDNS (best-effort). Lanza RuntimeError si
        aiohttp no esta disponible o si no hay puerto libre.
        """
        with self._lock:
            if self._activo:
                return self.info()

            arrancable, _ = dependencias_disponibles()
            if not arrancable:
                raise RuntimeError("aiohttp no está instalado: no se puede iniciar el servidor de sincronización.")

            host = self._host_forzado or ip_lan_probable()
            puerto = puerto_libre(host, *self._rango_puertos)
            if puerto is None:
                raise RuntimeError(
                    f"No hay puertos libres en el rango {self._rango_puertos[0]}–{self._rango_puertos[1]}."
                )

            self._host = host
            self._puerto = puerto
            self._error_arranque = None
            self._listo.clear()
            self.regenerar_token()

            self._hilo = threading.Thread(
                target=self._run_loop, name="nb-sound-sync-server", daemon=True
            )
            self._hilo.start()

            # Esperar a que el site arranque (o falle) con timeout.
            if not self._listo.wait(timeout=10.0):
                self._error_arranque = self._error_arranque or "timeout al arrancar el servidor"
                self._detener_interno()
                raise RuntimeError(self._error_arranque)

            if self._error_arranque:
                self._detener_interno()
                raise RuntimeError(self._error_arranque)

            self._activo = True
            self._anunciar_mdns()
            _log.info("Servidor de sincronización activo en %s:%s", host, puerto)
            return self.info()

    def detener(self) -> None:
        """Para el servidor de forma determinista (idempotente, con timeout)."""
        with self._lock:
            self._detener_interno()

    # Alias usado por el orden de cierre de la app (main_ui._ORDEN_CIERRE).
    def cerrar(self) -> None:
        self.detener()

    def _detener_interno(self) -> None:
        self._retirar_mdns()
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(self._teardown(), loop)
                fut.result(timeout=5.0)
            except Exception as exc:
                _log.debug("Teardown async incompleto: %s", exc)
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
        if self._hilo is not None and self._hilo.is_alive():
            self._hilo.join(timeout=5.0)
            if self._hilo.is_alive():
                _log.warning("El hilo del servidor de sincronización no terminó en 5s.")
        self._activo = False
        self._hilo = None
        self._loop = None
        self._runner = None
        self._site = None
        self._app = None
        self._ws_clientes = set()

    async def _teardown(self) -> None:
        # Cerrar WS abiertos antes de tumbar el runner.
        for ws in list(self._ws_clientes):
            try:
                await ws.close(code=1001, message=b"servidor apagado")
            except Exception:
                pass
        self._ws_clientes.clear()
        if self._site is not None:
            try:
                await self._site.stop()
            except Exception:
                pass
        if self._runner is not None:
            try:
                await self._runner.cleanup()
            except Exception:
                pass

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._arrancar_site())
        except Exception as exc:
            self._error_arranque = str(exc)
            _log.error("Fallo al arrancar el servidor de sincronización: %s", exc)
            self._listo.set()
            loop.close()
            return
        self._listo.set()
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()

    async def _arrancar_site(self) -> None:
        from aiohttp import web

        app = web.Application(middlewares=[self._construir_middleware_auth(web)])
        app.add_routes(self._rutas(web))
        self._app = app
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, self._host, self._puerto)
        await site.start()
        self._runner = runner
        self._site = site

    # ── Rutas ────────────────────────────────────────────────────────────────

    def _rutas(self, web):
        return [
            web.get("/api/v1/ping", self._h_ping),
            web.post("/api/v1/pair", self._h_pair),
            web.get("/api/v1/manifest", self._h_manifest),
            web.get("/api/v1/track/{id}/audio", self._h_audio),
            web.get("/api/v1/track/{id}/stems", self._h_stems),
            web.get("/api/v1/track/{id}/lyrics", self._h_lyrics),
            web.get("/api/v1/asset/{tipo}/{id}", self._h_asset),
            web.post("/api/v1/history", self._h_history),
            web.get("/api/v1/control", self._h_control_ws),
        ]

    # ── Middleware de autenticacion ──────────────────────────────────────────

    _RUTAS_PUBLICAS = ("/api/v1/ping", "/api/v1/pair")

    def _construir_middleware_auth(self, web):
        """Construye el middleware (estilo @web.middleware) ligado a este server."""

        @web.middleware
        async def auth_mw(request, handler):
            if request.path in self._RUTAS_PUBLICAS:
                return await handler(request)
            token = self._extraer_bearer(request)
            dispositivo = sync_repositorio.obtener_dispositivo_por_token(token)
            if not dispositivo:
                return web.json_response({"error": "no_autorizado"}, status=401)
            request["dispositivo"] = dispositivo
            try:
                sync_repositorio.tocar_dispositivo(dispositivo["id"])
            except Exception:
                pass
            return await handler(request)

        return auth_mw

    @staticmethod
    def _extraer_bearer(request) -> str:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return request.headers.get("X-Device-Token", "").strip()

    # ── Handlers HTTP ────────────────────────────────────────────────────────

    async def _h_ping(self, request):
        from aiohttp import web

        return web.json_response(
            {
                "ok": True,
                "servicio": self._nombre_servicio,
                "version_protocolo": sync_repositorio.PROTOCOLO_VERSION,
            }
        )

    async def _h_pair(self, request):
        from aiohttp import web

        try:
            datos = await request.json()
        except Exception:
            datos = {}
        token = str(datos.get("token") or "")
        if not self._token_vigente() or token != self._pairing_token:
            return web.json_response({"error": "token_invalido_o_expirado"}, status=401)

        nombre = str(datos.get("nombre") or "Dispositivo móvil")
        plataforma = datos.get("plataforma")
        dispositivo = sync_repositorio.registrar_dispositivo(nombre, plataforma)

        # Token de emparejamiento de un solo uso: regenerar para el siguiente
        # device y notificar a la UI para que refresque lista + QR.
        self.regenerar_token()
        if self._on_dispositivo_emparejado:
            try:
                self._on_dispositivo_emparejado(dispositivo)
            except Exception as exc:
                _log.debug("Callback on_dispositivo_emparejado falló: %s", exc)

        return web.json_response(
            {
                "ok": True,
                "device_token": dispositivo.get("device_token"),
                "dispositivo_id": dispositivo.get("id"),
                "nombre": dispositivo.get("nombre"),
            }
        )

    async def _h_manifest(self, request):
        from aiohttp import web

        try:
            since = int(request.query.get("since", "0") or "0")
        except ValueError:
            since = 0
        manifest = sync_repositorio.construir_manifest(since)
        try:
            sync_repositorio.guardar_ultima_sync_version(
                request["dispositivo"]["id"], manifest["sync_version"]
            )
        except Exception:
            pass
        return web.json_response(manifest)

    async def _h_audio(self, request):
        from aiohttp import web

        pista_id = self._id_int(request)
        ruta = sync_repositorio.ruta_audio_pista(pista_id) if pista_id else None
        if ruta is None:
            return web.json_response({"error": "no_encontrado"}, status=404)
        headers = {}
        hsh = sync_repositorio.ruta_hash_pista(pista_id)
        if hsh:
            headers["X-NB-Sound-Hash"] = hsh
        # FileResponse soporta Range (206) y conditional GET de forma nativa.
        return web.FileResponse(ruta, headers=headers)

    async def _h_stems(self, request):
        from aiohttp import web

        pista_id = self._id_int(request)
        ruta = sync_repositorio.ruta_stem_pista(pista_id) if pista_id else None
        if ruta is None:
            return web.json_response({"error": "sin_stems"}, status=404)
        dispositivo = request.get("dispositivo") or {}
        try:
            sync_repositorio.registrar_progreso_stem(
                dispositivo.get("id"), pista_id, "in_progress", 0
            )
        except Exception:
            pass
        return web.FileResponse(ruta)

    async def _h_lyrics(self, request):
        from aiohttp import web

        pista_id = self._id_int(request)
        texto = self._resolver_lyrics(pista_id) if pista_id else None
        if not texto:
            return web.json_response({"error": "sin_lyrics"}, status=404)
        return web.Response(text=texto, content_type="text/plain", charset="utf-8")

    async def _h_asset(self, request):
        from aiohttp import web

        tipo = request.match_info.get("tipo", "")
        try:
            asset_id = int(request.match_info.get("id", "0"))
        except ValueError:
            return web.json_response({"error": "id_invalido"}, status=400)
        ruta = None
        if tipo in ("cover", "album"):
            ruta = sync_repositorio.ruta_portada_album(asset_id)
        elif tipo == "artist":
            ruta = self._resolver_imagen_artista(asset_id)
        if ruta is None:
            return web.json_response({"error": "no_encontrado"}, status=404)
        return web.FileResponse(ruta)

    async def _h_history(self, request):
        from aiohttp import web

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "json_invalido"}, status=400)
        resultado = sync_repositorio.aplicar_historial_remoto(payload or {})
        return web.json_response({"ok": True, **resultado})

    async def _h_control_ws(self, request):
        from aiohttp import web

        ws = web.WebSocketResponse(heartbeat=30.0)
        await ws.prepare(request)
        self._ws_clientes.add(ws)
        try:
            # Frame inicial de estado para que el cliente pinte de inmediato.
            if self._estado_provider:
                try:
                    estado = self._estado_provider()
                    await ws.send_json({"tipo": "estado", "payload": estado})
                except Exception as exc:
                    _log.debug("Estado inicial WS falló: %s", exc)
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self._procesar_mensaje_ws(ws, msg.data)
                elif msg.type == web.WSMsgType.ERROR:
                    _log.debug("WS cerrado con excepción: %s", ws.exception())
        finally:
            self._ws_clientes.discard(ws)
        return ws

    async def _procesar_mensaje_ws(self, ws, data: str) -> None:
        import json

        try:
            mensaje = json.loads(data)
        except (ValueError, TypeError):
            await ws.send_json({"tipo": "error", "detalle": "json_invalido"})
            return
        ack = None
        if self._comando_control:
            try:
                ack = self._comando_control(mensaje)
            except Exception as exc:
                _log.debug("Handler de comando de control falló: %s", exc)
                ack = {"ok": False, "error": str(exc)}
        await ws.send_json({"tipo": "ack", "comando": mensaje.get("comando"), "resultado": ack})

    # ── Difusion de estado a clientes WS (thread-safe) ───────────────────────

    def difundir_estado(self, estado: dict) -> None:
        """Empuja un frame de estado del reproductor a todos los clientes WS.

        Llamable desde CUALQUIER hilo (lo invoca el modelo Qt al recibir
        señales del reproductor). Marshala al event loop del servidor con
        call_soon_threadsafe; no toca objetos Qt.
        """
        loop = self._loop
        if loop is None or not self._activo:
            return
        try:
            loop.call_soon_threadsafe(self._programar_difusion, estado)
        except RuntimeError:
            pass

    def _programar_difusion(self, estado: dict) -> None:
        if not self._ws_clientes:
            return
        frame = {"tipo": "estado", "payload": estado}
        for ws in list(self._ws_clientes):
            asyncio.ensure_future(self._enviar_seguro(ws, frame))

    async def _enviar_seguro(self, ws, frame: dict) -> None:
        try:
            if not ws.closed:
                await ws.send_json(frame)
        except Exception:
            self._ws_clientes.discard(ws)

    # ── Resolucion auxiliar ──────────────────────────────────────────────────

    @staticmethod
    def _id_int(request) -> Optional[int]:
        try:
            return int(request.match_info.get("id", "0"))
        except (ValueError, TypeError):
            return None

    def _resolver_lyrics(self, pista_id: int) -> Optional[str]:
        """Resuelve el LRC/letra de una pista vía el servicio de biblioteca.

        Best-effort: la resolucion de letras vive en la capa de reproductor/
        enrichment; aqui solo intentamos leerla sin acoplar Qt.
        """
        try:
            from servicios import biblioteca as bib

            pista = bib.obtener_pista(pista_id)
            if not pista:
                return None
            resolver = getattr(bib, "obtener_lyrics_por_ruta", None)
            if resolver:
                datos = resolver(pista.get("ruta_archivo"))
                if isinstance(datos, dict):
                    return datos.get("lrc") or datos.get("texto") or None
                if isinstance(datos, str):
                    return datos or None
        except Exception as exc:
            _log.debug("No se pudo resolver lyrics de la pista %s: %s", pista_id, exc)
        return None

    def _resolver_imagen_artista(self, artista_id: int):
        try:
            from servicios import biblioteca as bib

            resolver = getattr(bib, "ruta_imagen_artista", None)
            if resolver:
                ruta = resolver(artista_id)
                if ruta:
                    from pathlib import Path

                    p = Path(ruta)
                    return p if p.is_file() else None
        except Exception:
            pass
        return None

    # ── mDNS (Zeroconf) ──────────────────────────────────────────────────────

    def _anunciar_mdns(self) -> None:
        if not self._mdns_habilitado:
            return
        if importlib.util.find_spec("zeroconf") is None:
            _log.debug("zeroconf no disponible: descubrimiento mDNS deshabilitado (QR sigue funcionando).")
            return
        try:
            import socket

            from zeroconf import ServiceInfo, Zeroconf

            nombre_instancia = f"{self._nombre_servicio}._nbsound._tcp.local."
            info = ServiceInfo(
                TIPO_SERVICIO_MDNS,
                nombre_instancia,
                addresses=[socket.inet_aton(self._host)],
                port=int(self._puerto),
                properties={
                    "version": str(sync_repositorio.PROTOCOLO_VERSION),
                    "servicio": self._nombre_servicio,
                },
                server=f"nbsound-{self._puerto}.local.",
            )
            zc = Zeroconf()
            zc.register_service(info)
            self._zeroconf = zc
            self._mdns_info = info
            _log.debug("Servicio mDNS anunciado: %s", nombre_instancia)
        except Exception as exc:
            _log.debug("No se pudo anunciar mDNS: %s", exc)
            self._zeroconf = None
            self._mdns_info = None

    def _retirar_mdns(self) -> None:
        zc = self._zeroconf
        info = self._mdns_info
        self._zeroconf = None
        self._mdns_info = None
        if zc is None:
            return
        try:
            if info is not None:
                zc.unregister_service(info)
        except Exception:
            pass
        try:
            zc.close()
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Generacion del QR (sobre qrcode + Pillow). Devuelve PNG en bytes.
# -----------------------------------------------------------------------------

def generar_qr_png(contenido: str, *, box_size: int = 8, border: int = 2) -> Optional[bytes]:
    """Genera un PNG (bytes) con el QR de `contenido`, o None si falta qrcode."""
    if importlib.util.find_spec("qrcode") is None:
        return None
    try:
        import io

        import qrcode

        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(contenido)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception as exc:
        _log.debug("No se pudo generar el QR: %s", exc)
        return None
