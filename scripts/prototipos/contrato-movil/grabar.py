"""F0.4.5: graba las respuestas doradas del servidor móvil de la V1.

Herramienta de desarrollo (ver check-sin-python). Se ejecuta con el entorno de la
V1, desde `legado/`:

    cd legado && .venv/bin/python ../scripts/prototipos/contrato-movil/grabar.py [--comprobar]

Siembra una base temporal con el escenario de `escenario.json` (datos inventados,
nada del usuario), arranca el `ServidorSync` real de la V1 en 127.0.0.1 con TLS,
recorre la lista de peticiones de ese mismo archivo y escribe lo que respondió en
`src-tauri/tests/contrato_movil/respuestas.json`. El servidor de la V2 tiene que
dar lo mismo con el mismo escenario (ADR-005); el arnés de Rust de la Fase 3 lee
estos dos archivos.

Lo que cambia en cada ejecución (tokens, fechas, puertos) se sustituye por un
marcador `<...>` del mismo tipo, para que la comparación sea estable.

El estado y la cola del WebSocket los construye en la V1 el modelo de Qt
(`ModeloSincronizacion._construir_snapshot` y `_difundir_cola`); aquí se llaman esas
mismas funciones con un reproductor de prueba, sin arrancar Qt.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

import aiohttp  # noqa: E402

from db.conexion import (  # noqa: E402
    cerrar_db,
    get_conexion,
    inicializar_db,
    marcar_sync_version,
    registrar_tombstone,
)
from servicios import biblioteca  # noqa: E402
from servicios.servidor_sync import ServidorSync  # noqa: E402

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
DESTINO = RAIZ / "src-tauri" / "tests" / "contrato_movil"
CABECERAS = (
    "content-type",
    "content-length",
    "content-range",
    "accept-ranges",
    "x-nb-sound-hash",
)
VOLATILES = {
    "device_token": "<device_token>",
    "token": "<token>",
    "generado_en": "<fecha>",
    "codigo": "<codigo>",
}


def normalizar(valor):
    if isinstance(valor, dict):
        return {k: (VOLATILES[k] if k in VOLATILES and valor[k] else normalizar(v)) for k, v in valor.items()}
    if isinstance(valor, list):
        return [normalizar(v) for v in valor]
    return valor


def sembrar(escenario: dict, base: Path) -> dict:
    """Inserta el escenario en la base de la V1 con la API de la V1."""
    con = get_conexion()
    rutas = {}
    for a in escenario["artistas"]:
        con.execute(
            "INSERT INTO artistas(id, nombre, nombre_slug) VALUES (?, ?, ?)",
            (a["id"], a["nombre"], a["nombre"].lower().replace(" ", "-")),
        )
        marcar_sync_version("artistas", a["id"])
    for al in escenario["albums"]:
        portada = None
        if al.get("portada"):
            portada = base / f"portada_{al['id']}.jpg"
            portada.write_bytes(al["portada"].encode())
        con.execute(
            "INSERT INTO albums(id, artista_id, titulo, titulo_slug, anio, tipo, portada_ruta)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (al["id"], al["artista_id"], al["titulo"], al["titulo"].lower(), al.get("anio"),
             al.get("tipo", "Album"), str(portada) if portada else None),
        )
        marcar_sync_version("albums", al["id"])
    for p in escenario["pistas"]:
        contenido = (p["audio"] * 64).encode()
        ruta = base / f"pista_{p['id']}.mp3"
        ruta.write_bytes(contenido)
        rutas[p["id"]] = ruta
        stem = None
        if p.get("instrumental"):
            stem = base / f"instrumental_{p['id']}.mp3"
            stem.write_bytes((p["instrumental"] * 64).encode())
        con.execute(
            """INSERT INTO pistas(id, album_id, artista_id, titulo, artista_nombre, album_titulo,
                   ruta_archivo, nombre_archivo, hash_sha256, track_number, duracion_seg, anio,
                   genero, favorita, favorita_actualizada_en, karaoke_ruta_instrumental,
                   karaoke_estado)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (p["id"], p["album_id"], p["artista_id"], p["titulo"], p["artista_nombre"],
             p["album_titulo"], str(ruta), ruta.name, hashlib.sha256(contenido).hexdigest(),
             p.get("track_number"), p.get("duracion_seg"), p.get("anio"), p.get("genero"),
             1 if p.get("favorita") else 0, p.get("favorita_actualizada_en"),
             str(stem) if stem else None, "lista" if stem else "no_procesada"),
        )
        marcar_sync_version("pistas", p["id"])
    for pl in escenario["playlists"]:
        con.execute(
            "INSERT INTO playlists(id, nombre, tipo, visible) VALUES (?, ?, ?, ?)",
            (pl["id"], pl["nombre"], pl.get("tipo", "manual"), 1 if pl.get("visible", True) else 0),
        )
        for pos, pid in enumerate(pl["pista_ids"]):
            con.execute(
                "INSERT INTO pistas_playlist(playlist_id, pista_id, posicion) VALUES (?, ?, ?)",
                (pl["id"], pid, pos),
            )
        marcar_sync_version("playlists", pl["id"])
    for clave, valor in escenario.get("perfil", {}).items():
        con.execute("INSERT OR REPLACE INTO config_ui(clave, valor) VALUES (?, ?)", (clave, valor))
    for t in escenario.get("borrados", []):
        registrar_tombstone(t["entidad"], t["entidad_id"])
    return rutas


class Reproductor:
    """Atributos que lee `_construir_snapshot` en la V1."""

    def __init__(self, estado: dict, cola: list[dict]):
        for k, v in estado.items():
            setattr(self, k, v)
        self._cola = cola

    class _Cola:
        def __init__(self, items):
            self._items = items

        def snapshot(self):
            return self._items

    @property
    def cola(self):
        return Reproductor._Cola(self._cola)


async def recorrer(escenario: dict, srv: ServidorSync, base_url: str) -> list[dict]:
    from ui.modelos_qml import ModeloSincronizacion

    pista_activa = escenario["reproductor"]["pista_activa"]
    rep = Reproductor(escenario["reproductor"]["estado"] | {"pista_activa": pista_activa},
                      escenario["reproductor"]["cola"])
    falso = type("Modelo", (), {"_reproductor": rep, "_servidor": srv})()
    snapshot = ModeloSincronizacion._construir_snapshot(falso)
    srv._estado_provider = lambda: snapshot
    srv._comando_control = lambda m: (
        ModeloSincronizacion._difundir_cola(falso) if (m.get("accion") or m.get("comando")) == "queue" else None
    ) or {"ok": True, "encolado": True}

    grabadas = []
    contexto = {}
    conector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=conector) as sesion:
        for paso in escenario["peticiones"]:
            if paso.get("ws"):
                grabadas.append(await recorrer_ws(sesion, base_url, contexto, paso))
                continue
            cabeceras = dict(paso.get("cabeceras", {}))
            if paso.get("auth", True) and "device_token" in contexto:
                cabeceras["Authorization"] = f"Bearer {contexto['device_token']}"
            cuerpo = paso.get("cuerpo")
            if isinstance(cuerpo, dict) and cuerpo.get("token") == "<token>":
                cuerpo = cuerpo | {"token": srv._pairing_token}
            async with sesion.request(paso["metodo"], base_url + paso["ruta"],
                                      json=cuerpo, headers=cabeceras) as r:
                datos = await r.read()
                tipo = r.headers.get("content-type", "")
                if "json" in tipo:
                    cuerpo_resp = json.loads(datos)
                    if paso["ruta"].endswith("/pair") and r.status == 200:
                        contexto["device_token"] = cuerpo_resp["device_token"]
                    cuerpo_resp = normalizar(cuerpo_resp)
                else:
                    cuerpo_resp = {"bytes": len(datos), "sha256": hashlib.sha256(datos).hexdigest()}
                grabadas.append({
                    "nombre": paso["nombre"],
                    "estado": r.status,
                    "cabeceras": {k: r.headers[k] for k in CABECERAS if k in r.headers},
                    "cuerpo": cuerpo_resp,
                })
    return grabadas


async def recorrer_ws(sesion, base_url, contexto, paso) -> dict:
    cabeceras = {"Authorization": f"Bearer {contexto['device_token']}"}
    frames = []
    async with sesion.ws_connect(base_url + "/api/v1/control", headers=cabeceras) as ws:
        frames.append(await asyncio.wait_for(ws.receive_json(), 3))
        for mensaje in paso["mensajes"]:
            if isinstance(mensaje, str):
                await ws.send_str(mensaje)
            else:
                await ws.send_json(mensaje)
            esperados = 2 if isinstance(mensaje, dict) and mensaje.get("accion") == "queue" else 1
            recibidos = [await asyncio.wait_for(ws.receive_json(), 3) for _ in range(esperados)]
            # El frame de cola llega por difusión y el ack por respuesta: el orden
            # entre ellos no forma parte del contrato.
            frames.extend(sorted(recibidos, key=lambda f: f.get("tipo", "")))
    return {"nombre": paso["nombre"], "frames": frames}


def main() -> None:
    escenario = json.loads((DESTINO / "escenario.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        inicializar_db(base / "v1.sqlite3")
        sembrar(escenario, base)
        letras = {p["id"]: p["letras"] for p in escenario["pistas"] if p.get("letras")}
        rutas_a_id = {str(base / f"pista_{i}.mp3"): i for i in letras}
        biblioteca.obtener_lyrics_por_ruta = lambda ruta: letras.get(
            rutas_a_id.get(str(ruta)), {"synced_lyrics": "", "plain_lyrics": ""}
        )
        srv = ServidorSync(host="127.0.0.1", anunciar_mdns=False, dir_certificados=base / "certs")
        info = srv.iniciar()
        try:
            url = f"https://{info['host']}:{info['puerto']}"
            grabadas = asyncio.run(recorrer(escenario, srv, url))
        finally:
            srv.detener()
            cerrar_db()
    salida = {
        "origen": "NB Sound v1.1.16 (legado/servicios/servidor_sync.py)",
        "version_protocolo": 1,
        "respuestas": grabadas,
    }
    texto = json.dumps(salida, ensure_ascii=False, indent=2) + "\n"
    texto = re.sub(r"https://127\.0\.0\.1:\d+", "<base>", texto)
    destino = DESTINO / "respuestas.json"
    if "--comprobar" in sys.argv:
        # El arnés contra la V1: grabar otra vez y exigir lo mismo byte a byte.
        if destino.read_text() != texto:
            print("Las respuestas de la V1 no coinciden con las grabadas.", file=sys.stderr)
            sys.exit(1)
        print(f"{len(grabadas)} respuestas: la V1 responde exactamente lo grabado.")
        return
    destino.write_text(texto)
    print(f"{len(grabadas)} respuestas grabadas en {destino}")


if __name__ == "__main__":
    main()
