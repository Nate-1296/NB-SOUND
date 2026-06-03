# =============================================================================
# tests/test_reproductor_persistencia.py
#
# Regresión de la persistencia del reproductor GLOBAL entre reaperturas:
#   - Guardar al cerrar: pista_id + posición + índice de cola en config_ui y la
#     cola en la tabla `cola`.
#   - Restaurar al construir: el backend relee la cola y posiciona el índice
#     activo + el seek pendiente que consumirá el primer play.
#   - Robustez: si no se guardó pista_id pero sí la posición de cola, igual se
#     restaura el índice (la barra retoma la pista correcta).
#
# Determinista y sin audio: siembra config_ui/`cola` como lo haría una sesión
# previa y comprueba el round-trip. (El camino con VLC real está cubierto a
# mano por el usuario; aquí validamos la lógica de persistencia.)
# =============================================================================
from __future__ import annotations

from pathlib import Path

import pytest

from db.conexion import (
    cerrar_db, ejecutar_muchos, get_conexion, guardar_config, obtener_config, inicializar_db,
)
from servicios.reproductor import Reproductor, EstadoReproductor, PistaActiva


@pytest.fixture()
def db(tmp_path):
    inicializar_db(tmp_path / "rep_persist.sqlite3")
    try:
        yield tmp_path
    finally:
        cerrar_db()


def _seed_pistas(n: int = 3) -> list[int]:
    con = get_conexion()
    ids = []
    for i in range(n):
        art = con.execute("INSERT INTO artistas(nombre,nombre_slug) VALUES(?,?)", (f"A{i}", f"a{i}")).lastrowid
        alb = con.execute(
            "INSERT INTO albums(artista_id,titulo,titulo_slug,tipo) VALUES(?,?,?,'Album')",
            (art, f"Al{i}", f"al{i}"),
        ).lastrowid
        pid = con.execute(
            "INSERT INTO pistas(album_id,artista_id,titulo,artista_nombre,album_titulo,"
            "ruta_archivo,nombre_archivo,duracion_seg,estado) VALUES(?,?,?,?,?,?,?,?, 'biblioteca')",
            (alb, art, f"T{i}", f"A{i}", f"Al{i}", f"/m/{i}.mp3", f"{i}.mp3", 200.0),
        ).lastrowid
        ids.append(int(pid))
    return ids


def _seed_cola(ids: list[int]) -> None:
    ejecutar_muchos("INSERT INTO cola(posicion,pista_id) VALUES(?,?)",
                    [(i, pid) for i, pid in enumerate(ids)])


# ── Restaurar al construir ────────────────────────────────────────────────────

def test_restaura_cola_indice_y_posicion(db):
    ids = _seed_pistas(3)
    _seed_cola(ids)
    guardar_config("reproductor_pista_id", str(ids[1]))
    guardar_config("reproductor_pos_cola", "1")
    guardar_config("reproductor_pos_seg", "42.5")

    r = Reproductor(permitir_modo_simulado=True)  # __init__ restaura
    try:
        assert len(r.obtener_cola()) == 3
        assert r.indice_cola == 1
        assert r._activa_desde_cola is True
        assert r._reanudar_seg_pendiente == pytest.approx(42.5)
    finally:
        r.cerrar()


def test_restaura_por_pista_id_aunque_cambie_el_orden(db):
    # La cola se guardó en un orden; el índice activo se localiza por pista_id.
    ids = _seed_pistas(3)
    # Cola persistida en orden inverso: la pista activa (ids[0]) queda al final.
    ejecutar_muchos("INSERT INTO cola(posicion,pista_id) VALUES(?,?)",
                    [(0, ids[2]), (1, ids[1]), (2, ids[0])])
    guardar_config("reproductor_pista_id", str(ids[0]))
    guardar_config("reproductor_pos_cola", "0")  # desactualizado a propósito

    r = Reproductor(permitir_modo_simulado=True)
    try:
        # Gana el pista_id: ids[0] está en la posición 2.
        assert r.indice_cola == 2
    finally:
        r.cerrar()


def test_cola_sin_pista_activa_se_restaura_sin_activar(db):
    # Contrato: una cola persistida que nunca se reprodujo (pista_id=0) se
    # restaura SIN índice activo (indice_cola=-1), pero la cola sí vuelve para
    # que la barra muestre la pista "para continuar".
    ids = _seed_pistas(3)
    _seed_cola(ids)
    guardar_config("reproductor_pista_id", "0")
    guardar_config("reproductor_pos_cola", "0")

    r = Reproductor(permitir_modo_simulado=True)
    try:
        assert len(r.obtener_cola()) == 3
        assert r.indice_cola == -1
        assert r._activa_desde_cola is False
    finally:
        r.cerrar()


def test_cola_vacia_no_restaura_ni_revienta(db):
    guardar_config("reproductor_pista_id", "999")
    guardar_config("reproductor_pos_cola", "0")
    r = Reproductor(permitir_modo_simulado=True)
    try:
        assert r.obtener_cola() == []
        assert r.indice_cola == -1
        assert r._activa_desde_cola is False
    finally:
        r.cerrar()


# ── Guardar al cerrar ─────────────────────────────────────────────────────────

def test_guardar_estado_al_cerrar_persiste_pista_y_cola(db):
    ids = _seed_pistas(3)
    r = Reproductor(permitir_modo_simulado=True)
    # Mimetiza "reproduciendo la pista 1 desde la cola".
    r._cola = [{"id": pid, "titulo": f"T{k}", "artista_nombre": f"A{k}",
                "album_titulo": f"Al{k}", "ruta_archivo": f"/m/{k}.mp3",
                "duracion_seg": 200.0} for k, pid in enumerate(ids)]
    r._cola_base = [dict(p) for p in r._cola]
    r._posicion_cola = 1
    r._activa_desde_cola = True
    r._estado = EstadoReproductor.REPRODUCIENDO
    r._pista_activa = PistaActiva(id=ids[1], titulo="T1", artista="A1", album="Al1",
                                  ruta_archivo="/m/1.mp3", duracion_seg=200.0)
    r._persistir_cola()  # como en cada play
    r.cerrar()           # guarda estado

    assert int(obtener_config("reproductor_pista_id")) == ids[1]
    assert int(obtener_config("reproductor_pos_cola")) == 1
    filas = get_conexion().execute("SELECT posicion,pista_id FROM cola ORDER BY posicion").fetchall()
    assert [f["pista_id"] for f in filas] == ids

    # Y un reproductor nuevo lo restaura.
    r2 = Reproductor(permitir_modo_simulado=True)
    try:
        assert r2.indice_cola == 1
        assert r2._activa_desde_cola is True
    finally:
        r2.cerrar()


def test_modelo_refleja_pista_y_tiempo_restaurados(db):
    """La barra (ModeloReproductor) muestra la pista y la posición guardadas al
    reabrir, antes del primer play."""
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    from ui.modelos_qml import ModeloReproductor
    QGuiApplication.instance() or QGuiApplication([])

    ids = _seed_pistas(3)
    _seed_cola(ids)
    guardar_config("reproductor_pista_id", str(ids[1]))
    guardar_config("reproductor_pos_cola", "1")
    guardar_config("reproductor_pos_seg", "42.5")

    rep = Reproductor(permitir_modo_simulado=True)
    m = ModeloReproductor(rep)
    try:
        pv = m.pista_visual
        assert int(pv.get("id") or 0) == ids[1]
        assert pv.get("titulo") == "T1"
        # El tiempo guardado se refleja en la barra (no 0) aunque no haya audio.
        assert m.posicion_seg == pytest.approx(42.5)
    finally:
        m.cerrar()


# ── Cierre de ventana: la sesión sobrevive (regresión del bug real #0) ─────────

def test_preparar_cierre_conserva_la_sesion(db):
    """Regresión del bug observado en producción.

    `Principal.qml.onClosing` cortaba el audio con `detener_forzado()`, que
    vaciaba la cola y limpiaba la pista activa ANTES de que `cerrar()` guardara
    el estado → cada cierre persistía `pista_id=0` y `cola=[]` (verificado en el
    log real). Ahora `onClosing` usa `preparar_cierre()`, que persiste y silencia
    sin destruir el estado, de modo que la sesión se restaura al reabrir.
    """
    ids = _seed_pistas(3)
    # `reproducir_pista` valida que el archivo exista: creamos uno real.
    ruta = db / "pista0.mp3"
    ruta.write_bytes(b"\x00")
    r = Reproductor(permitir_modo_simulado=True)
    r.reproducir_pista({
        "id": ids[0], "titulo": "T0", "artista_nombre": "A0", "album_titulo": "Al0",
        "ruta_archivo": str(ruta), "duracion_seg": 200.0,
    })
    assert [f["pista_id"] for f in
            get_conexion().execute("SELECT pista_id FROM cola ORDER BY posicion").fetchall()] == [ids[0]]

    # Cierre de ventana real: onClosing → preparar_cierre; aboutToQuit → cerrar.
    r.preparar_cierre()
    r.cerrar()

    assert int(obtener_config("reproductor_pista_id")) == ids[0]
    assert [f["pista_id"] for f in
            get_conexion().execute("SELECT pista_id FROM cola ORDER BY posicion").fetchall()] == [ids[0]]

    # Reapertura: la sesión vuelve.
    r2 = Reproductor(permitir_modo_simulado=True)
    try:
        assert [p.get("id") for p in r2.obtener_cola()] == [ids[0]]
        assert r2.indice_cola == 0
        assert r2._activa_desde_cola is True
    finally:
        r2.cerrar()


def test_preparar_cierre_no_es_machacado_por_cerrar(db):
    """`cerrar()` no debe re-guardar tras `preparar_cierre()` (VLC ya parado
    leería posición 0 y borraría el punto de reanudación)."""
    ids = _seed_pistas(2)
    r = Reproductor(permitir_modo_simulado=True)
    r._cola = [{"id": ids[0], "titulo": "T0", "artista_nombre": "A0",
                "album_titulo": "Al0", "ruta_archivo": "/m/0.mp3", "duracion_seg": 200.0}]
    r._cola_base = [dict(p) for p in r._cola]
    r._posicion_cola = 0
    r._activa_desde_cola = True
    r._estado = EstadoReproductor.PAUSADO
    r._pista_activa = PistaActiva(id=ids[0], titulo="T0", artista="A0", album="Al0",
                                  ruta_archivo="/m/0.mp3", duracion_seg=200.0)
    r._reanudar_seg_pendiente = 88.0  # punto de reanudación simulado
    r._persistir_cola()
    r.preparar_cierre()
    guardado = obtener_config("reproductor_pista_id")
    # Si cerrar() volviera a guardar con pista_activa nula machacaría a 0.
    r._pista_activa = None  # estado tras un teardown defensivo
    r.cerrar()
    assert obtener_config("reproductor_pista_id") == guardado == str(ids[0])
