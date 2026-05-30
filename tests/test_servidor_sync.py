# =============================================================================
# tests/test_servidor_sync.py
#
# Integracion del servidor de sincronizacion local (BLOQUE 2.2 + 3.x del plan):
#   - /ping sin auth; /pair con token valido (200) e invalido (401).
#   - Resto de endpoints exigen device_token (401 sin él).
#   - /manifest delta por sync_version.
#   - /track/{id}/audio con Range (206) reensamblado == hash_sha256.
#   - /history: merge last-write-wins de favoritos por timestamp.
#   - /track/{id}/stems opt-in (404 si la pista no tiene instrumental).
#   - /control (WS): un comando pausa el reproductor (handler) y devuelve ack.
#   - detener() no deja hilos colgados.
# =============================================================================

import asyncio
import hashlib

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db, marcar_sync_version, sync_version_actual
from servicios import sync_repositorio

aiohttp = pytest.importorskip("aiohttp")
from servicios.servidor_sync import ServidorSync  # noqa: E402


# ── Helpers de datos ─────────────────────────────────────────────────────────

def _sembrar_pista(tmp_path, titulo="Cancion", contenido=b"AUDIO-BYTES-1234567890") -> dict:
    """Crea artista+album+pista con un archivo de audio real en disco."""
    con = get_conexion()
    art = con.execute(
        "INSERT INTO artistas(nombre, nombre_slug) VALUES (?, ?)", ("Artista", "artista")
    ).lastrowid
    alb = con.execute(
        "INSERT INTO albums(artista_id, titulo, titulo_slug) VALUES (?, 'Album', 'album')",
        (art,),
    ).lastrowid
    ruta = tmp_path / f"{titulo}.mp3"
    ruta.write_bytes(contenido)
    sha = hashlib.sha256(contenido).hexdigest()
    pid = con.execute(
        """
        INSERT INTO pistas(album_id, artista_id, titulo, artista_nombre, album_titulo,
                           ruta_archivo, nombre_archivo, hash_sha256)
        VALUES (?, ?, ?, 'Artista', 'Album', ?, ?, ?)
        """,
        (alb, art, titulo, str(ruta), ruta.name, sha),
    ).lastrowid
    marcar_sync_version("pistas", pid)
    return {"pista_id": pid, "album_id": alb, "artista_id": art, "ruta": ruta, "sha": sha, "contenido": contenido}


def _run(coro):
    return asyncio.run(coro)


# ── Fixture del servidor ─────────────────────────────────────────────────────

class _Reproductor:
    """Doble de prueba que registra comandos recibidos por WS."""

    def __init__(self):
        self.comandos = []

    def manejar(self, mensaje):
        self.comandos.append(mensaje)
        return {"ok": True, "comando": mensaje.get("comando")}

    def estado(self):
        return {"reproduciendo": False, "titulo": "—"}


@pytest.fixture()
def servidor(tmp_path):
    inicializar_db(tmp_path / "sync_srv.sqlite3")
    rep = _Reproductor()
    srv = ServidorSync(
        host="127.0.0.1",
        anunciar_mdns=False,
        comando_control=rep.manejar,
        estado_provider=rep.estado,
    )
    info = srv.iniciar()
    base = f"http://{info['host']}:{info['puerto']}"
    try:
        yield srv, base, rep, tmp_path
    finally:
        srv.detener()
        cerrar_db()


# ── /ping y /pair ────────────────────────────────────────────────────────────

def test_ping_sin_auth(servidor):
    srv, base, _rep, _tmp = servidor

    async def _t():
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{base}/api/v1/ping") as r:
                assert r.status == 200
                data = await r.json()
                assert data["ok"] is True
                assert data["version_protocolo"] == sync_repositorio.PROTOCOLO_VERSION

    _run(_t())


def test_pair_token_valido_e_invalido(servidor):
    srv, base, _rep, _tmp = servidor
    token = srv.payload_qr()["token"]

    async def _t():
        async with aiohttp.ClientSession() as s:
            # Token invalido -> 401
            async with s.post(f"{base}/api/v1/pair", json={"token": "malo", "nombre": "X"}) as r:
                assert r.status == 401
            # Token valido -> 200 + device_token
            async with s.post(
                f"{base}/api/v1/pair", json={"token": token, "nombre": "Pixel", "plataforma": "android"}
            ) as r:
                assert r.status == 200
                data = await r.json()
                assert data["ok"] is True
                assert data["device_token"]
                return data["device_token"]

    device_token = _run(_t())
    # El dispositivo quedo registrado y el token de pairing rotó (un solo uso).
    disp = sync_repositorio.obtener_dispositivo_por_token(device_token)
    assert disp is not None
    assert disp["nombre"] == "Pixel"
    assert srv.payload_qr()["token"] != token


def test_endpoints_requieren_auth(servidor):
    srv, base, _rep, _tmp = servidor

    async def _t():
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{base}/api/v1/manifest") as r:
                assert r.status == 401

    _run(_t())


# ── Helper de emparejamiento para los tests autenticados ─────────────────────

def _emparejar(base, srv) -> str:
    token = srv.payload_qr()["token"]

    async def _t():
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{base}/api/v1/pair", json={"token": token, "nombre": "Test"}) as r:
                data = await r.json()
                return data["device_token"]

    return _run(_t())


# ── /manifest ────────────────────────────────────────────────────────────────

def test_manifest_delta_por_sync_version(servidor):
    srv, base, _rep, tmp = servidor
    info = _sembrar_pista(tmp, "Tema A")
    device_token = _emparejar(base, srv)
    headers = {"Authorization": f"Bearer {device_token}"}

    async def _t():
        async with aiohttp.ClientSession(headers=headers) as s:
            async with s.get(f"{base}/api/v1/manifest?since=0") as r:
                assert r.status == 200
                m = await r.json()
                ids = [p["id"] for p in m["pistas"]]
                assert info["pista_id"] in ids
                hwm = m["sync_version"]
            # since = high-water mark => sin cambios nuevos
            async with s.get(f"{base}/api/v1/manifest?since={hwm}") as r:
                m2 = await r.json()
                assert m2["pistas"] == []

    _run(_t())


# ── /track/{id}/audio con Range ──────────────────────────────────────────────

def test_audio_range_reensamblado_coincide_hash(servidor):
    srv, base, _rep, tmp = servidor
    info = _sembrar_pista(tmp, "Tema R", contenido=b"0123456789ABCDEFGHIJ")
    device_token = _emparejar(base, srv)
    headers = {"Authorization": f"Bearer {device_token}"}
    pid = info["pista_id"]

    async def _t():
        async with aiohttp.ClientSession(headers=headers) as s:
            async with s.get(f"{base}/api/v1/track/{pid}/audio", headers={"Range": "bytes=0-9"}) as r:
                assert r.status == 206
                parte1 = await r.read()
            async with s.get(f"{base}/api/v1/track/{pid}/audio", headers={"Range": "bytes=10-"}) as r:
                assert r.status == 206
                parte2 = await r.read()
        ensamblado = parte1 + parte2
        assert hashlib.sha256(ensamblado).hexdigest() == info["sha"]
        assert ensamblado == info["contenido"]

    _run(_t())


# ── /history merge (favorito last-write-wins) ────────────────────────────────

def test_history_merge_favorito_last_write_wins(servidor):
    srv, base, _rep, tmp = servidor
    info = _sembrar_pista(tmp, "Tema F")
    pid = info["pista_id"]
    # Estado local: favorita=0 con timestamp viejo.
    get_conexion().execute(
        "UPDATE pistas SET favorita = 0, favorita_actualizada_en = '2020-01-01T00:00:00.000Z' WHERE id = ?",
        (pid,),
    )
    device_token = _emparejar(base, srv)
    headers = {"Authorization": f"Bearer {device_token}"}

    async def _t():
        async with aiohttp.ClientSession(headers=headers) as s:
            payload = {
                "historial": [{"pista_id": pid, "reproducido_en": "2024-06-01T10:00:00.000Z"}],
                "favoritos": [{"pista_id": pid, "favorita": True, "actualizada_en": "2024-06-01T10:00:00.000Z"}],
            }
            async with s.post(f"{base}/api/v1/history", json=payload) as r:
                assert r.status == 200
                res = await r.json()
                assert res["favoritos_aplicados"] == 1
                assert res["historial_insertado"] == 1

    _run(_t())
    # El favorito remoto (mas reciente) gano.
    fila = get_conexion().execute(
        "SELECT favorita, favorita_actualizada_en FROM pistas WHERE id = ?", (pid,)
    ).fetchone()
    assert fila["favorita"] == 1
    assert fila["favorita_actualizada_en"] == "2024-06-01T10:00:00.000Z"
    # Un favorito remoto MAS VIEJO no debe pisar el valor recien aplicado.
    device_token2 = device_token

    async def _t2():
        async with aiohttp.ClientSession(headers={"Authorization": f"Bearer {device_token2}"}) as s:
            payload = {"favoritos": [{"pista_id": pid, "favorita": False, "actualizada_en": "2021-01-01T00:00:00.000Z"}]}
            async with s.post(f"{base}/api/v1/history", json=payload) as r:
                res = await r.json()
                assert res["favoritos_ignorados"] == 1

    _run(_t2())
    fila2 = get_conexion().execute("SELECT favorita FROM pistas WHERE id = ?", (pid,)).fetchone()
    assert fila2["favorita"] == 1  # sigue siendo favorita


# ── /track/{id}/stems opt-in ─────────────────────────────────────────────────

def test_stems_opt_in_404_sin_instrumental(servidor):
    srv, base, _rep, tmp = servidor
    info = _sembrar_pista(tmp, "Tema S")
    device_token = _emparejar(base, srv)
    headers = {"Authorization": f"Bearer {device_token}"}
    pid = info["pista_id"]

    async def _t():
        async with aiohttp.ClientSession(headers=headers) as s:
            async with s.get(f"{base}/api/v1/track/{pid}/stems") as r:
                assert r.status == 404

    _run(_t())

    # Con instrumental generado, ahora 200.
    stem = tmp / "instrumental.wav"
    stem.write_bytes(b"INSTRUMENTAL")
    get_conexion().execute(
        "UPDATE pistas SET karaoke_ruta_instrumental = ?, karaoke_estado = 'lista' WHERE id = ?",
        (str(stem), pid),
    )

    async def _t2():
        async with aiohttp.ClientSession(headers=headers) as s:
            async with s.get(f"{base}/api/v1/track/{pid}/stems") as r:
                assert r.status == 200
                data = await r.read()
                assert data == b"INSTRUMENTAL"

    _run(_t2())
    estado = sync_repositorio.estado_stem(
        sync_repositorio.obtener_dispositivo_por_token(device_token)["id"], pid
    )
    assert estado is not None
    assert estado["estado"] == "in_progress"


# ── /control WebSocket ───────────────────────────────────────────────────────

def test_control_ws_comando_pausa(servidor):
    srv, base, rep, tmp = servidor
    device_token = _emparejar(base, srv)

    async def _t():
        async with aiohttp.ClientSession(headers={"Authorization": f"Bearer {device_token}"}) as s:
            async with s.ws_connect(f"{base}/api/v1/control") as ws:
                # Frame inicial de estado.
                primero = await asyncio.wait_for(ws.receive_json(), timeout=3.0)
                assert primero["tipo"] == "estado"
                # Enviar comando de pausa.
                await ws.send_json({"comando": "pause"})
                ack = await asyncio.wait_for(ws.receive_json(), timeout=3.0)
                assert ack["tipo"] == "ack"
                assert ack["comando"] == "pause"

    _run(_t())
    assert any(c.get("comando") == "pause" for c in rep.comandos)


def test_difundir_estado_llega_a_clientes_ws(servidor):
    srv, base, rep, tmp = servidor
    device_token = _emparejar(base, srv)

    async def _t():
        async with aiohttp.ClientSession(headers={"Authorization": f"Bearer {device_token}"}) as s:
            async with s.ws_connect(f"{base}/api/v1/control") as ws:
                await asyncio.wait_for(ws.receive_json(), timeout=3.0)  # estado inicial
                # Difundir desde el hilo principal (thread-safe).
                srv.difundir_estado({"reproduciendo": True, "titulo": "Nueva"})
                frame = await asyncio.wait_for(ws.receive_json(), timeout=3.0)
                assert frame["tipo"] == "estado"
                assert frame["payload"]["titulo"] == "Nueva"

    _run(_t())


# ── Teardown limpio ──────────────────────────────────────────────────────────

def test_detener_no_deja_hilos(tmp_path):
    import threading

    inicializar_db(tmp_path / "sync_stop.sqlite3")
    try:
        srv = ServidorSync(host="127.0.0.1", anunciar_mdns=False)
        srv.iniciar()
        assert srv.activo
        assert any(t.name == "nb-sound-sync-server" for t in threading.enumerate())
        srv.detener()
        assert not srv.activo
        # El hilo del servidor debe haber terminado.
        import time

        for _ in range(20):
            if not any(t.name == "nb-sound-sync-server" for t in threading.enumerate()):
                break
            time.sleep(0.05)
        assert not any(t.name == "nb-sound-sync-server" for t in threading.enumerate())
        # iniciar/detener es idempotente.
        srv.detener()
    finally:
        cerrar_db()
