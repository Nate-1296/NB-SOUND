# =============================================================================
# tests/test_sync_e2e.py
#
# BLOQUE 6: extremo a extremo del lado PC con un cliente movil simulado.
# Flujo completo y determinista (reanudable por Range / sync_version):
#   ping -> pair -> manifest -> descarga audio (Range, 2 tramos) -> descarga
#   portada -> push historial/favorito (LWW) -> control por WS -> delta
#   incremental tras el cambio -> revocar (token deja de valer).
# =============================================================================

import asyncio
import hashlib

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db, marcar_sync_version
from servicios import sync_repositorio

aiohttp = pytest.importorskip("aiohttp")
from servicios.servidor_sync import ServidorSync  # noqa: E402


def _cliente(headers=None):
    """ClientSession que NO verifica el cert autofirmado (en producción el
    cliente fija la huella del QR — TOFU)."""
    return aiohttp.ClientSession(headers=headers, connector=aiohttp.TCPConnector(ssl=False))


class _Reproductor:
    def __init__(self):
        self.comandos = []

    def manejar(self, mensaje):
        self.comandos.append(mensaje)
        return {"ok": True}

    def estado(self):
        return {"reproduciendo": False, "titulo": "—"}


def _sembrar(tmp_path):
    con = get_conexion()
    art = con.execute(
        "INSERT INTO artistas(nombre, nombre_slug) VALUES ('Daft Punk', 'daft-punk')"
    ).lastrowid
    alb = con.execute(
        "INSERT INTO albums(artista_id, titulo, titulo_slug, portada_ruta) VALUES (?, 'Discovery', 'discovery', ?)",
        (art, str(tmp_path / "cover.jpg")),
    ).lastrowid
    (tmp_path / "cover.jpg").write_bytes(b"COVER-IMAGE-DATA")
    contenido = bytes(range(256)) * 8  # 2048 bytes deterministas
    ruta = tmp_path / "one_more_time.mp3"
    ruta.write_bytes(contenido)
    sha = hashlib.sha256(contenido).hexdigest()
    pid = con.execute(
        """
        INSERT INTO pistas(album_id, artista_id, titulo, artista_nombre, album_titulo,
                           ruta_archivo, nombre_archivo, hash_sha256, favorita,
                           favorita_actualizada_en)
        VALUES (?, ?, 'One More Time', 'Daft Punk', 'Discovery', ?, ?, ?, 0, '2020-01-01T00:00:00.000Z')
        """,
        (alb, art, str(ruta), ruta.name, sha),
    ).lastrowid
    marcar_sync_version("pistas", pid)
    marcar_sync_version("albums", alb)
    marcar_sync_version("artistas", art)
    return {"pista_id": pid, "album_id": alb, "sha": sha, "contenido": contenido}


@pytest.fixture()
def entorno(tmp_path):
    inicializar_db(tmp_path / "e2e.sqlite3")
    datos = _sembrar(tmp_path)
    rep = _Reproductor()
    srv = ServidorSync(host="127.0.0.1", anunciar_mdns=False,
                       dir_certificados=tmp_path / "certs",
                       comando_control=rep.manejar, estado_provider=rep.estado)
    info = srv.iniciar()
    esquema = "https" if info["tls"] else "http"
    base = f"{esquema}://{info['host']}:{info['puerto']}"
    try:
        yield srv, base, rep, datos
    finally:
        srv.detener()
        cerrar_db()


def test_flujo_completo_cliente_movil(entorno):
    srv, base, rep, datos = entorno
    pista_id = datos["pista_id"]
    album_id = datos["album_id"]

    async def _flujo():
        async with _cliente() as s:
            # 1) ping
            async with s.get(f"{base}/api/v1/ping") as r:
                assert r.status == 200
                assert (await r.json())["version_protocolo"] == sync_repositorio.PROTOCOLO_VERSION

            # 2) pair
            token_qr = srv.payload_qr()["token"]
            async with s.post(f"{base}/api/v1/pair",
                              json={"token": token_qr, "nombre": "Pixel 8", "plataforma": "android"}) as r:
                assert r.status == 200
                device_token = (await r.json())["device_token"]

            auth = {"Authorization": f"Bearer {device_token}"}

            # 3) manifest inicial
            async with s.get(f"{base}/api/v1/manifest?since=0", headers=auth) as r:
                assert r.status == 200
                manifest = await r.json()
                assert any(p["id"] == pista_id for p in manifest["pistas"])
                hwm = manifest["sync_version"]
                pista = next(p for p in manifest["pistas"] if p["id"] == pista_id)
                assert pista["audio_url"] == f"/api/v1/track/{pista_id}/audio"
                assert pista["hash_sha256"] == datos["sha"]

            # 4) descarga de audio en 2 tramos (Range) y validacion por hash
            async with s.get(f"{base}{pista['audio_url']}", headers={**auth, "Range": "bytes=0-1023"}) as r:
                assert r.status == 206
                p1 = await r.read()
            async with s.get(f"{base}{pista['audio_url']}", headers={**auth, "Range": "bytes=1024-"}) as r:
                assert r.status == 206
                p2 = await r.read()
            assert hashlib.sha256(p1 + p2).hexdigest() == datos["sha"]

            # 5) descarga de portada
            async with s.get(f"{base}/api/v1/asset/cover/{album_id}", headers=auth) as r:
                assert r.status == 200
                assert (await r.read()) == b"COVER-IMAGE-DATA"

            # 6) push de historial + favorito (LWW, remoto mas reciente gana)
            payload = {
                "historial": [{"pista_id": pista_id, "reproducido_en": "2024-07-01T12:00:00.000Z"}],
                "favoritos": [{"pista_id": pista_id, "favorita": True, "actualizada_en": "2024-07-01T12:00:00.000Z"}],
            }
            async with s.post(f"{base}/api/v1/history", headers=auth, json=payload) as r:
                assert r.status == 200
                res = await r.json()
                assert res["favoritos_aplicados"] == 1
                assert res["historial_insertado"] == 1

            # 7) control por WS: play_pause (esquema canónico tipo+accion)
            async with s.ws_connect(f"{base}/api/v1/control", headers=auth) as ws:
                primero = await asyncio.wait_for(ws.receive_json(), timeout=3.0)  # estado inicial
                assert primero["tipo"] == "estado"
                await ws.send_json({"tipo": "comando", "accion": "play_pause"})
                ack = await asyncio.wait_for(ws.receive_json(), timeout=3.0)
                assert ack["tipo"] == "ack"
                assert ack["accion"] == "play_pause"

            # 8) delta incremental: el favorito recien aplicado aparece tras hwm
            async with s.get(f"{base}/api/v1/manifest?since={hwm}", headers=auth) as r:
                delta = await r.json()
                ids = [p["id"] for p in delta["pistas"]]
                assert pista_id in ids
                pista_delta = next(p for p in delta["pistas"] if p["id"] == pista_id)
                assert pista_delta["favorita"] is True

            return device_token

    device_token = asyncio.run(_flujo())

    # El historial quedó registrado y el favorito ganó por timestamp.
    fav = get_conexion().execute("SELECT favorita FROM pistas WHERE id = ?", (pista_id,)).fetchone()
    assert fav["favorita"] == 1
    hist = get_conexion().execute("SELECT COUNT(*) c FROM historial WHERE pista_id = ?", (pista_id,)).fetchone()
    assert hist["c"] == 1
    assert any(c.get("accion") == "play_pause" for c in rep.comandos)

    # 9) revocar: el token deja de autenticar.
    disp = sync_repositorio.obtener_dispositivo_por_token(device_token)
    assert sync_repositorio.revocar_dispositivo(disp["id"]) is True

    async def _post_revoke():
        async with _cliente() as s:
            async with s.get(f"{base}/api/v1/manifest", headers={"Authorization": f"Bearer {device_token}"}) as r:
                assert r.status == 401

    asyncio.run(_post_revoke())
