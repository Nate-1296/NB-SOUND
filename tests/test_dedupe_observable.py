# =============================================================================
# tests/test_dedupe_observable.py
#
# Fase 2 — Tercera capa de deduplicacion (duplicado observable).
#
# Cubre:
#   * Logica pura (core.dedupe): clave_observable, duraciones_equivalentes,
#     hash_portada.
#   * Servicio periodico (servicios.dedupe_observable): deteccion + resolucion
#     por DUPLICATE_POLICY, casos limite, idempotencia/reanudacion, cancelacion.
#   * Validacion integral: datos sinteticos con los TRES tipos de duplicado
#     (hash, semantico, observable) -> tras una corrida completa no queda
#     ningun duplicado observable en estado 'biblioteca'.
# =============================================================================

from __future__ import annotations

from pathlib import Path

import pytest

from db.conexion import (
    inicializar_db,
    cerrar_db,
    ejecutar_y_obtener_id,
    obtener_filas,
)
from utils.text import construir_slug_artista, construir_slug_album


@pytest.fixture
def _db(tmp_path):
    inicializar_db(tmp_path / "lib.sqlite3")
    yield
    cerrar_db()


def _crear_portada(tmp_path: Path, nombre: str, contenido: bytes) -> str:
    p = tmp_path / nombre
    p.write_bytes(contenido)
    return str(p)


def _crear_artista(nombre: str = "Artista") -> int:
    return ejecutar_y_obtener_id(
        "INSERT INTO artistas(nombre, nombre_slug) VALUES (?, ?)",
        (nombre, construir_slug_artista(nombre)),
    )


def _crear_album(artista_id: int, titulo: str, portada_ruta) -> int:
    return ejecutar_y_obtener_id(
        "INSERT INTO albums(artista_id, titulo, titulo_slug, tipo, portada_ruta) "
        "VALUES (?,?,?,?,?)",
        (artista_id, titulo, construir_slug_album(titulo), "Album", portada_ruta),
    )


def _crear_pista(
    *,
    titulo: str,
    artista: str = "Artista",
    album: str = "Album",
    album_id=None,
    artista_id=None,
    duracion_seg: float = 200.0,
    bitrate_kbps: int = 256,
    tamano_bytes: int = 5_000_000,
    hash_sha256=None,
    mb_recording_id=None,
    isrc=None,
    favorita: int = 0,
    veces_reproducida: int = 0,
    estado: str = "biblioteca",
    ruta=None,
) -> int:
    ruta = ruta or f"/music/{titulo}-{hash_sha256 or mb_recording_id or isrc or 'x'}.mp3"
    return ejecutar_y_obtener_id(
        "INSERT INTO pistas (album_id, artista_id, titulo, artista_nombre, "
        "album_titulo, duracion_seg, bitrate_kbps, tamano_bytes, ruta_archivo, "
        "nombre_archivo, hash_sha256, mb_recording_id, isrc, favorita, "
        "veces_reproducida, estado) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (album_id, artista_id, titulo, artista, album, duracion_seg, bitrate_kbps,
         tamano_bytes, ruta, Path(ruta).name, hash_sha256, mb_recording_id, isrc,
         favorita, veces_reproducida, estado),
    )


def _estados():
    return {int(f["id"]): f["estado"]
            for f in obtener_filas("SELECT id, estado FROM pistas ORDER BY id")}


# -----------------------------------------------------------------------------
# Logica pura
# -----------------------------------------------------------------------------

def test_hash_portada_por_contenido_no_ruta(tmp_path):
    from core.dedupe import hash_portada
    a = _crear_portada(tmp_path, "a.jpg", b"PORTADA-XYZ")
    b = _crear_portada(tmp_path, "b.jpg", b"PORTADA-XYZ")   # mismo contenido, otra ruta
    c = _crear_portada(tmp_path, "c.jpg", b"OTRA-COSA")
    assert hash_portada(a) == hash_portada(b)
    assert hash_portada(a) != hash_portada(c)
    assert hash_portada(None) is None
    assert hash_portada("/no/existe.jpg") is None


def test_clave_observable_conservadora():
    from core.dedupe import clave_observable
    assert clave_observable("t", "a", "al", None) is None      # sin portada
    assert clave_observable("t", "a", "", "ph") is None        # sin album
    assert clave_observable("", "a", "al", "ph") is None       # sin titulo
    k1 = clave_observable("Canción", "Artista", "Álbum", "PH")
    k2 = clave_observable("cancion", "artista", "album", "PH")
    assert k1 == k2 == ("cancion", "artista", "album", "PH")


def test_duraciones_equivalentes_tolerancia():
    from core.dedupe import duraciones_equivalentes
    assert duraciones_equivalentes(200, 202) is True
    assert duraciones_equivalentes(200, 203) is True   # limite +-3
    assert duraciones_equivalentes(200, 204) is False
    assert duraciones_equivalentes(200, None) is False


# -----------------------------------------------------------------------------
# Servicio: deteccion y resolucion observable
# -----------------------------------------------------------------------------

def test_observable_resuelve_y_conserva_mejor_bitrate(_db, tmp_path):
    art = _crear_artista()
    portada = _crear_portada(tmp_path, "cover.jpg", b"COVER-A")
    alb = _crear_album(art, "Album", portada)
    buena = _crear_pista(titulo="Tema", album_id=alb, artista_id=art,
                         duracion_seg=200, bitrate_kbps=320, hash_sha256="h1")
    mala = _crear_pista(titulo="Tema", album_id=alb, artista_id=art,
                        duracion_seg=201, bitrate_kbps=128, hash_sha256="h2")

    from servicios.dedupe_observable import ServicioDedupeObservable
    res = ServicioDedupeObservable().escanear()

    assert res.completado is True
    assert res.grupos_detectados == 1
    assert res.duplicados_resueltos == 1
    estados = _estados()
    assert estados[buena] == "biblioteca"
    assert estados[mala] == "duplicado"


def test_observable_conserva_favorita(_db, tmp_path):
    art = _crear_artista()
    portada = _crear_portada(tmp_path, "cover.jpg", b"COVER-A")
    alb = _crear_album(art, "Album", portada)
    fav = _crear_pista(titulo="Tema", album_id=alb, artista_id=art,
                       duracion_seg=200, bitrate_kbps=128, favorita=1, hash_sha256="h1")
    otra = _crear_pista(titulo="Tema", album_id=alb, artista_id=art,
                        duracion_seg=200, bitrate_kbps=320, favorita=0, hash_sha256="h2")

    from servicios.dedupe_observable import ServicioDedupeObservable
    ServicioDedupeObservable().escanear()
    estados = _estados()
    assert estados[fav] == "biblioteca"
    assert estados[otra] == "duplicado"


def test_observable_sin_portada_no_resuelve(_db, tmp_path):
    art = _crear_artista()
    alb = _crear_album(art, "Album", None)
    a = _crear_pista(titulo="Tema", album_id=alb, artista_id=art, hash_sha256="h1")
    b = _crear_pista(titulo="Tema", album_id=alb, artista_id=art, hash_sha256="h2")

    from servicios.dedupe_observable import ServicioDedupeObservable
    res = ServicioDedupeObservable().escanear()
    assert res.grupos_detectados == 0
    estados = _estados()
    assert estados[a] == "biblioteca" and estados[b] == "biblioteca"


def test_observable_duracion_fuera_de_tolerancia(_db, tmp_path):
    art = _crear_artista()
    portada = _crear_portada(tmp_path, "cover.jpg", b"COVER-A")
    alb = _crear_album(art, "Album", portada)
    a = _crear_pista(titulo="Tema", album_id=alb, artista_id=art,
                     duracion_seg=200, hash_sha256="h1")
    b = _crear_pista(titulo="Tema", album_id=alb, artista_id=art,
                     duracion_seg=210, hash_sha256="h2")   # +10s

    from servicios.dedupe_observable import ServicioDedupeObservable
    ServicioDedupeObservable().escanear()
    estados = _estados()
    assert estados[a] == "biblioteca" and estados[b] == "biblioteca"


def test_observable_distinta_portada_no_es_duplicado(_db, tmp_path):
    art = _crear_artista()
    p1 = _crear_portada(tmp_path, "c1.jpg", b"COVER-1")
    p2 = _crear_portada(tmp_path, "c2.jpg", b"COVER-2")
    alb1 = _crear_album(art, "Album", p1)
    alb2 = _crear_album(art, "Album Dos", p2)
    a = _crear_pista(titulo="Tema", album="Album", album_id=alb1, artista_id=art, hash_sha256="h1")
    b = _crear_pista(titulo="Tema", album="Album Dos", album_id=alb2, artista_id=art, hash_sha256="h2")

    from servicios.dedupe_observable import ServicioDedupeObservable
    res = ServicioDedupeObservable().escanear()
    assert res.grupos_detectados == 0


def test_observable_normalizacion_tolerante(_db, tmp_path):
    art = _crear_artista("Sóly")
    portada = _crear_portada(tmp_path, "cover.jpg", b"COVER-A")
    alb = _crear_album(art, "Álbum", portada)
    a = _crear_pista(titulo="Canción (En Vivo)", artista="Sóly", album="Álbum",
                     album_id=alb, artista_id=art, duracion_seg=200, bitrate_kbps=320, hash_sha256="h1")
    b = _crear_pista(titulo="cancion en vivo", artista="soly", album="album",
                     album_id=alb, artista_id=art, duracion_seg=202, bitrate_kbps=128, hash_sha256="h2")

    from servicios.dedupe_observable import ServicioDedupeObservable
    res = ServicioDedupeObservable().escanear()
    assert res.duplicados_resueltos == 1
    estados = _estados()
    assert estados[a] == "biblioteca" and estados[b] == "duplicado"


def test_observable_idempotente(_db, tmp_path):
    art = _crear_artista()
    portada = _crear_portada(tmp_path, "cover.jpg", b"COVER-A")
    alb = _crear_album(art, "Album", portada)
    _crear_pista(titulo="Tema", album_id=alb, artista_id=art, bitrate_kbps=320, hash_sha256="h1")
    _crear_pista(titulo="Tema", album_id=alb, artista_id=art, bitrate_kbps=128, hash_sha256="h2")

    from servicios.dedupe_observable import ServicioDedupeObservable
    r1 = ServicioDedupeObservable().escanear()
    assert r1.duplicados_resueltos == 1
    r2 = ServicioDedupeObservable().escanear()
    assert r2.grupos_detectados == 0
    assert r2.duplicados_resueltos == 0


def test_observable_cancelacion_deja_consistente(_db, tmp_path):
    art = _crear_artista()
    portada = _crear_portada(tmp_path, "cover.jpg", b"COVER-A")
    alb = _crear_album(art, "Album", portada)
    a = _crear_pista(titulo="Tema", album_id=alb, artista_id=art, bitrate_kbps=320, hash_sha256="h1")
    b = _crear_pista(titulo="Tema", album_id=alb, artista_id=art, bitrate_kbps=128, hash_sha256="h2")

    class _Stop:
        def is_set(self):
            return True

    from servicios.dedupe_observable import ServicioDedupeObservable
    res = ServicioDedupeObservable().escanear(stop_event=_Stop())
    assert res.cancelado is True
    estados = _estados()
    assert estados[a] == "biblioteca" and estados[b] == "biblioteca"


def test_observable_dry_run_no_modifica(_db, tmp_path):
    art = _crear_artista()
    portada = _crear_portada(tmp_path, "cover.jpg", b"COVER-A")
    alb = _crear_album(art, "Album", portada)
    a = _crear_pista(titulo="Tema", album_id=alb, artista_id=art, bitrate_kbps=320, hash_sha256="h1")
    b = _crear_pista(titulo="Tema", album_id=alb, artista_id=art, bitrate_kbps=128, hash_sha256="h2")

    from servicios.dedupe_observable import ServicioDedupeObservable
    res = ServicioDedupeObservable().escanear(aplicar=False)
    assert res.grupos_detectados == 1
    assert res.duplicados_resueltos == 0
    estados = _estados()
    assert estados[a] == "biblioteca" and estados[b] == "biblioteca"


# -----------------------------------------------------------------------------
# Validacion integral: los TRES tipos de duplicado
# -----------------------------------------------------------------------------

def test_tres_tipos_de_duplicado_ninguno_observable_queda(_db, tmp_path):
    """Datos sinteticos con duplicado por hash, semantico y observable.

    - Observable: lo resuelve el barrido (esta capa). Tras la corrida no queda
      ningun par 'biblioteca' que sea duplicado observable.
    - Hash y semantico: los detecta el GestorDuplicados del pipeline sobre la
      biblioteca precargada (se valida la deteccion).
    """
    art = _crear_artista()
    portada = _crear_portada(tmp_path, "cover.jpg", b"COVER-A")
    alb = _crear_album(art, "Album", portada)

    # OBSERVABLE: mismo texto+portada+duracion, distinto hash, sin IDs.
    obs_keep = _crear_pista(titulo="Observable", album_id=alb, artista_id=art,
                            duracion_seg=180, bitrate_kbps=320, hash_sha256="obs1")
    obs_dup = _crear_pista(titulo="Observable", album_id=alb, artista_id=art,
                           duracion_seg=181, bitrate_kbps=128, hash_sha256="obs2")

    # HASH: misma firma binaria que una pista catalogada.
    _crear_pista(titulo="PorHash", album_id=alb, artista_id=art,
                 hash_sha256="HASHDUP", ruta="/music/porhash1.mp3")

    # SEMANTICO: mismo mb_recording_id que una pista catalogada.
    _crear_pista(titulo="PorSemantica", album_id=alb, artista_id=art,
                 mb_recording_id="MBID-123", ruta="/music/sem1.mp3")

    # 1) Barrido observable.
    from servicios.dedupe_observable import ServicioDedupeObservable
    ServicioDedupeObservable().escanear()
    estados = _estados()
    assert estados[obs_keep] == "biblioteca"
    assert estados[obs_dup] == "duplicado"

    # 2) Ningun par 'biblioteca' es duplicado observable tras el barrido.
    from core.dedupe import clave_observable, duraciones_equivalentes, hash_portada
    filas = obtener_filas(
        "SELECT p.id, p.titulo, p.artista_nombre, p.album_titulo, p.duracion_seg, "
        "a.portada_ruta FROM pistas p LEFT JOIN albums a ON a.id=p.album_id "
        "WHERE p.estado='biblioteca'"
    )
    vistos: dict = {}
    for f in filas:
        ph = hash_portada(f["portada_ruta"]) if f["portada_ruta"] else None
        k = clave_observable(f["titulo"], f["artista_nombre"], f["album_titulo"], ph)
        if k is None:
            continue
        for (_id, dp) in vistos.get(k, []):
            assert not duraciones_equivalentes(dp, f["duracion_seg"]), \
                "Quedo un duplicado observable sin resolver"
        vistos.setdefault(k, []).append((f["id"], f["duracion_seg"]))

    # 3) Hash y semantico: detectados por el GestorDuplicados (pipeline).
    from core.dedupe import GestorDuplicados
    from domain.models import ArchivoAudio, DecisionArchivo, CandidatoMB, DecisionTipo
    gestor = GestorDuplicados()

    archivo_hash = ArchivoAudio(ruta_original=Path("/music/reimport_hash.mp3"))
    archivo_hash.hash_sha256 = "HASHDUP"
    dup_h = gestor.registrar_hash(archivo_hash)
    assert dup_h is not None and dup_h.tipo == "hash_exacto"

    archivo_sem = ArchivoAudio(ruta_original=Path("/music/reimport_sem.mp3"))
    decision = DecisionArchivo(
        tipo=DecisionTipo.ACEPTADO,
        archivo=archivo_sem,
        candidato_elegido=CandidatoMB(recording_id="MBID-123"),
    )
    dup_s = gestor.detectar_duplicado_identidad(decision)
    assert dup_s is not None and dup_s.tipo in ("identidad_semantica", "duplicado_mejorable")
