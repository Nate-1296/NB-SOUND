# =============================================================================
# tests/test_sync_playlists.py
#
# Exposición de PLAYLISTS y FAVORITOS al ecosistema móvil.
#
# Bugs cubiertos:
#   - Las playlists nunca se sincronizaban: ninguna ruta bumpeaba su
#     `sync_version` y el backfill legacy no las cubría, así que `_playlists_desde`
#     (filtra `sync_version > since`) jamás las enviaba (incluida "Me gusta").
#   - Marcar/quitar favorita por la vía de la playlist "Me gusta" no bumpeaba el
#     `sync_version` de la pista, dejando favoritos fuera del delta por-pista.
# =============================================================================

from pathlib import Path

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db, sync_version_actual
from servicios import biblioteca as bib
from servicios import sync_repositorio


@pytest.fixture()
def db(tmp_path):
    inicializar_db(tmp_path / "sync_playlists.sqlite3")
    try:
        yield tmp_path
    finally:
        cerrar_db()


def _pista(titulo: str, ruta: str = "") -> int:
    ruta = ruta or f"/m/{titulo}.mp3"
    return get_conexion().execute(
        """
        INSERT INTO pistas(titulo, artista_nombre, album_titulo, ruta_archivo,
                           nombre_archivo, estado)
        VALUES (?, 'A', 'B', ?, ?, 'biblioteca')
        """,
        (titulo, ruta, Path(ruta).name),
    ).lastrowid


def _me_gusta_id() -> int:
    fila = get_conexion().execute(
        "SELECT id FROM playlists WHERE subtipo = 'favoritos'"
    ).fetchone()
    return int(fila["id"]) if fila else 0


def _playlist_del_manifest(manifest: dict, playlist_id: int) -> dict:
    return next(p for p in manifest["playlists"] if p["id"] == playlist_id)


# ── Playlists creadas por el usuario ─────────────────────────────────────────

def test_crear_playlist_la_expone_en_manifest_con_info_completa(db):
    pid = bib.crear_playlist("Mi mezcla", "Para entrenar")
    p1 = _pista("uno")
    bib.agregar_a_playlist(pid, p1)

    manifest = sync_repositorio.construir_manifest(0)
    pl = _playlist_del_manifest(manifest, pid)

    assert pl["nombre"] == "Mi mezcla"
    assert pl["descripcion"] == "Para entrenar"
    assert pl["categoria"] == "creada"          # creada por mí
    assert pl["etiqueta"] == "Manual"
    assert pl["es_favoritos"] is False
    assert pl["pista_ids"] == [p1]
    assert pl["num_pistas"] == 1


def test_editar_playlist_rebumpea_sync_version_para_delta(db):
    pid = bib.crear_playlist("Lista", "")
    # Tras la creación el cliente queda al día en este high-water mark.
    hwm = sync_version_actual()
    bib.renombrar_playlist(pid, "Lista renombrada")

    delta = sync_repositorio.construir_manifest(hwm)
    ids = [p["id"] for p in delta["playlists"]]
    assert pid in ids
    assert _playlist_del_manifest(delta, pid)["nombre"] == "Lista renombrada"


# ── "Me gusta" = todos los favoritos (bug: solo salían algunos) ──────────────

def test_me_gusta_expone_todas_las_favoritas(db):
    ids = [_pista(f"fav{i}") for i in range(8)]
    for pid in ids:
        bib.toggle_favorita(pid)
    # Disparar la materialización de "Me gusta" (como al abrir la vista Playlists).
    bib.listar_playlists()

    manifest = sync_repositorio.construir_manifest(0)
    me_gusta = _playlist_del_manifest(manifest, _me_gusta_id())

    assert me_gusta["categoria"] == "me_gusta"
    assert me_gusta["es_favoritos"] is True
    assert sorted(me_gusta["pista_ids"]) == sorted(ids)
    assert me_gusta["num_pistas"] == len(ids)


def test_favoritar_via_playlist_propaga_en_delta_por_pista(db):
    pid = _pista("cancion")
    bib.listar_playlists()  # crea "Me gusta" (vacía)
    hwm = sync_version_actual()

    # Marcar favorita por la vía "agregar a Me gusta" (no el corazón directo).
    bib.agregar_a_playlist(_me_gusta_id(), pid)

    delta = sync_repositorio.construir_manifest(hwm)
    pista_delta = next(p for p in delta["pistas"] if p["id"] == pid)
    assert pista_delta["favorita"] is True


# ── Backfill de playlists preexistentes ──────────────────────────────────────

def test_backfill_asigna_sync_version_a_playlists_legacy(db):
    from db.conexion import _backfill_sync_version_playlists

    con = get_conexion()
    con.execute(
        "INSERT INTO playlists(nombre, tipo, visible, sync_version) "
        "VALUES ('Legacy', 'manual', 1, 0)"
    )
    # Simula que el backfill aún no había corrido.
    con.execute("DELETE FROM sync_estado WHERE clave = 'backfill_playlists_sync_v1'")

    _backfill_sync_version_playlists(con)

    fila = con.execute("SELECT sync_version FROM playlists WHERE nombre = 'Legacy'").fetchone()
    assert int(fila["sync_version"]) > 0
    # Idempotente: una segunda corrida no vuelve a tocar nada.
    version_previa = int(fila["sync_version"])
    _backfill_sync_version_playlists(con)
    fila2 = con.execute("SELECT sync_version FROM playlists WHERE nombre = 'Legacy'").fetchone()
    assert int(fila2["sync_version"]) == version_previa


# ── Migración automática de arranque (renovar estado preexistente) ───────────

def test_exposicion_inicial_resella_favoritos_viejos_y_versiona_playlists(db):
    """Simula el caso real: favoritas marcadas por una vía que no bumpeaba el
    delta y una playlist legacy en sync_version=0. La migración (automática al
    arrancar) debe dejar TODO listo para la próxima sync, sin acción del usuario.
    """
    con = get_conexion()
    # Favoritas "viejas": favorita=1 puesto directamente, sin bump de sync_version.
    ids = [_pista(f"vieja{i}") for i in range(5)]
    for pid in ids:
        con.execute("UPDATE pistas SET favorita = 1 WHERE id = ?", (pid,))
    # Playlist manual legacy sin versión.
    plid = con.execute(
        "INSERT INTO playlists(nombre, tipo, visible, sync_version) VALUES ('Vieja', 'manual', 1, 0)"
    ).lastrowid

    # El celular ya estaba al día en este punto (no vería las favoritas viejas).
    hwm = sync_version_actual()

    sync_repositorio.asegurar_exposicion_inicial_sync()

    # Las 5 favoritas entran ahora en el delta por-pista (sync_version > hwm).
    delta = sync_repositorio.construir_manifest(hwm)
    favs_en_delta = {p["id"] for p in delta["pistas"] if p["favorita"]}
    assert set(ids) <= favs_en_delta

    # La playlist legacy quedó versionada y "Me gusta" trae todas las favoritas.
    manifest = sync_repositorio.construir_manifest(0)
    pl_ids = {p["id"] for p in manifest["playlists"]}
    assert plid in pl_ids
    me_gusta = _playlist_del_manifest(manifest, _me_gusta_id())
    assert sorted(me_gusta["pista_ids"]) == sorted(ids)

    # Idempotente: una segunda corrida no vuelve a tocar el contador.
    version_tras_migracion = sync_version_actual()
    sync_repositorio.asegurar_exposicion_inicial_sync()
    assert sync_version_actual() == version_tras_migracion


# ── Carátula de playlist ─────────────────────────────────────────────────────

def test_cover_url_y_ruta_portada_playlist(db, tmp_path):
    portada = tmp_path / "portada.png"
    portada.write_bytes(b"\x89PNG\r\n")
    pid = bib.crear_playlist("Con portada", "")
    get_conexion().execute(
        "UPDATE playlists SET portada_ruta = ? WHERE id = ?", (str(portada), pid)
    )

    manifest = sync_repositorio.construir_manifest(0)
    pl = _playlist_del_manifest(manifest, pid)
    assert pl["cover_url"] == f"/api/v1/asset/playlist/{pid}"
    assert sync_repositorio.ruta_portada_playlist(pid) == portada

    # Sin portada (portada_ruta vacía) → cover_url None y ruta None.
    pid2 = bib.crear_playlist("Sin portada", "")
    get_conexion().execute("UPDATE playlists SET portada_ruta = '' WHERE id = ?", (pid2,))
    manifest2 = sync_repositorio.construir_manifest(0)
    pl2 = _playlist_del_manifest(manifest2, pid2)
    assert pl2["cover_url"] is None
    assert sync_repositorio.ruta_portada_playlist(pid2) is None
