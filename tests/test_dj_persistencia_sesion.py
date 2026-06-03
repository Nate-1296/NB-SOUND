# =============================================================================
# tests/test_dj_persistencia_sesion.py
#
# #7a — Persistencia y restauración de la sesión DJ entre reaperturas.
#   Backend (ReproductorSesionDj, modo simulado, sin audio real):
#     - preparar_reanudacion deja PAUSADO + seek pendiente sin tocar audio.
#     - el primer play() consume la reanudación (arranca + limpia el seek).
#     - busca la pista por pista_id (robusto a reordenamientos); cae al índice.
#   Modelo (ModeloDjPrivado, headless, sin crear el reproductor de audio):
#     - _guardar_estado_sesion persiste solo si la sesión está en curso.
#     - restaurar_sesion_persistida deja la sesión visible en PAUSA.
#     - round-trip guardar→restaurar.
#     - descartar/detener limpian el estado; sesiones no 'lista' no se restauran.
# =============================================================================
from __future__ import annotations

from pathlib import Path

import pytest

from db.conexion import cerrar_db, get_conexion, guardar_config, obtener_config, inicializar_db


# ─── fixtures / helpers (reusa el patrón de test_dj_reproductor_sesion) ───────

@pytest.fixture()
def db_dj(tmp_path):
    inicializar_db(tmp_path / "dj_persist.db")
    try:
        yield tmp_path
    finally:
        cerrar_db()


def _crear_pista(tmp_path: Path, nombre: str, duracion: float = 30.0) -> int:
    ruta = tmp_path / f"{nombre}.mp3"
    ruta.write_bytes(b"fake audio")
    con = get_conexion()
    art_id = con.execute(
        "INSERT INTO artistas(nombre, nombre_slug) VALUES (?, ?)",
        (f"A {nombre}", f"a-{nombre}"),
    ).lastrowid
    alb_id = con.execute(
        "INSERT INTO albums(artista_id, titulo, titulo_slug, tipo) VALUES (?, ?, ?, 'Album')",
        (art_id, f"Al {nombre}", f"al-{nombre}"),
    ).lastrowid
    pid = con.execute(
        """
        INSERT INTO pistas(album_id, artista_id, titulo, artista_nombre, album_titulo,
                           ruta_archivo, nombre_archivo, tamano_bytes, duracion_seg, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'biblioteca')
        """,
        (alb_id, art_id, f"P {nombre}", f"A {nombre}", f"Al {nombre}",
         str(ruta), ruta.name, ruta.stat().st_size, duracion),
    ).lastrowid
    return int(pid)


def _crear_sesion_con_pistas(tmp_path: Path, n_pistas: int = 3, estado: str = "lista") -> int:
    from servicios.dj_privado import persistencia as dj_persist
    from servicios.dj_privado.intencion import parsear_intent
    # Intent válido (el servicio lo deserializa con IntentMusical.from_json al
    # restaurar la sesión); un "{}" crudo no es un intent legítimo.
    intent = parsear_intent("sesion persistencia", duracion_minutos=10)
    sid = dj_persist.crear_sesion(
        prompt="sesion persistencia", intent_json=intent.to_json(), objetivo_minutos=10,
        motor_version="dj_v1", semilla=None, resumen={},
    )
    filas = []
    for i in range(n_pistas):
        pid = _crear_pista(tmp_path, f"persist_{sid}_t{i}", duracion=120.0)
        filas.append(dj_persist.PistaSesionRow(
            sesion_id=sid, posicion=i, pista_id=pid,
            score_total=0.8, score_intent=0.7, score_transicion=0.75, score_curva=0.5,
            razones=[], transicion={}, estado="planificada", bloqueada=False,
        ))
    dj_persist.insertar_pistas_sesion(sid, filas)
    dj_persist.actualizar_estado_sesion(sid, estado)
    return sid


def _pista_ids(sid: int) -> list[int]:
    filas = get_conexion().execute(
        "SELECT pista_id FROM dj_pistas_sesion WHERE sesion_id=? ORDER BY posicion", (sid,)
    ).fetchall()
    return [int(f["pista_id"]) for f in filas]


# ═════════════════════════════════════════════════════════════════════════════
# Backend: preparar_reanudacion + consumo en el primer play (modo simulado)
# ═════════════════════════════════════════════════════════════════════════════

def test_preparar_reanudacion_deja_pausado_sin_audio(db_dj):
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=3)
    ids = _pista_ids(sid)
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
    r = ReproductorSesionDj(permitir_modo_simulado=True)
    assert r.cargar_sesion(sid) == 3
    # Preparar reanudación en la 2ª pista (índice 1), offset 40s.
    ok = r.preparar_reanudacion(ids[1], 40.0, indice_fallback=0)
    assert ok is True
    assert r.estado.value == "pausado"
    assert r.indice_actual == 1
    assert r._reanudacion_pendiente is True
    assert r._offset_reanudacion_seg == pytest.approx(40.0)
    r.close()


def test_play_consume_reanudacion_pendiente(db_dj):
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=3)
    ids = _pista_ids(sid)
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
    r = ReproductorSesionDj(permitir_modo_simulado=True)
    r.cargar_sesion(sid)
    r.preparar_reanudacion(ids[2], 10.0, indice_fallback=0)
    assert r.play() is True
    # Tras el primer play: arranca en la pista preparada y el seek se consume.
    assert r.estado.value == "reproduciendo"
    assert r.indice_actual == 2
    assert r._reanudacion_pendiente is False
    assert r._offset_reanudacion_seg == 0.0
    r.close()


def test_preparar_reanudacion_busca_por_pista_id_no_indice(db_dj):
    """Si el índice guardado no coincide, manda el pista_id (robusto a
    reordenamientos o a pistas filtradas al recargar)."""
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=3)
    ids = _pista_ids(sid)
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
    r = ReproductorSesionDj(permitir_modo_simulado=True)
    r.cargar_sesion(sid)
    # pista_id de la 3ª pista pero índice_fallback erróneo (0) → gana el id.
    r.preparar_reanudacion(ids[2], 0.0, indice_fallback=0)
    assert r.indice_actual == 2
    r.close()


def test_preparar_reanudacion_cae_al_indice_si_pista_desconocida(db_dj):
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=3)
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
    r = ReproductorSesionDj(permitir_modo_simulado=True)
    r.cargar_sesion(sid)
    # pista_id inexistente → usa el índice_fallback (acotado al rango).
    r.preparar_reanudacion(99999999, 5.0, indice_fallback=2)
    assert r.indice_actual == 2
    # Fuera de rango se acota.
    r.preparar_reanudacion(0, 0.0, indice_fallback=99)
    assert r.indice_actual == 2
    r.close()


def test_cargar_sesion_descarta_reanudacion_pendiente(db_dj):
    """Recargar la sesión invalida un seek preparado pero no consumido."""
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=2)
    ids = _pista_ids(sid)
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
    r = ReproductorSesionDj(permitir_modo_simulado=True)
    r.cargar_sesion(sid)
    r.preparar_reanudacion(ids[1], 30.0)
    assert r._reanudacion_pendiente is True
    r.cargar_sesion(sid)  # recarga
    assert r._reanudacion_pendiente is False
    assert r._offset_reanudacion_seg == 0.0
    r.close()


# ═════════════════════════════════════════════════════════════════════════════
# Modelo: guardar / restaurar (headless, sin reproductor de audio)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def app():
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.instance() or QGuiApplication([])


def _modelo(app):
    from servicios.reproductor import Reproductor
    from ui.modelos_qml import ModeloDjPrivado
    r = Reproductor(permitir_modo_simulado=True)
    return ModeloDjPrivado(r), r


def test_restaurar_sesion_persistida_deja_pausa(app, db_dj):
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=3)
    ids = _pista_ids(sid)
    # Estado persistido como si se hubiera cerrado en la 2ª pista a 40s.
    guardar_config("dj_sesion_id", str(sid))
    guardar_config("dj_pista_id", str(ids[1]))
    guardar_config("dj_indice_pista", "1")
    guardar_config("dj_pos_pista_seg", "40.0")
    guardar_config("dj_pos_global_seg", "160.0")

    m, _r = _modelo(app)
    m.restaurar_sesion_persistida()

    assert m.tiene_sesion is True
    assert m.sesion_id == sid
    assert m.estado_dj == "pausado"
    assert m.dj_pausado is True
    assert m.dj_reproduciendo is False
    assert m.dj_indice_actual == 1
    assert m.dj_pos_sesion_seg == pytest.approx(160.0)
    # Reanudación pendiente lista para el primer play.
    assert m._reanudar_sesion_pendiente is not None
    assert int(m._reanudar_sesion_pendiente["pista_id"]) == ids[1]
    # No se creó el reproductor de audio (sin blip al abrir).
    assert m._reproductor_sesion is None


def test_restaurar_sin_estado_no_hace_nada(app, db_dj):
    m, _r = _modelo(app)
    m.restaurar_sesion_persistida()
    assert m.tiene_sesion is False
    assert m.estado_dj == "detenido"


def test_restaurar_ignora_sesion_descartada(app, db_dj):
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=2, estado="descartada")
    guardar_config("dj_sesion_id", str(sid))
    m, _r = _modelo(app)
    m.restaurar_sesion_persistida()
    assert m.tiene_sesion is False
    # Y limpia el marcador para no reintentar.
    assert int(obtener_config("dj_sesion_id", "0") or 0) == 0


def test_guardar_estado_sesion_persiste_en_pausa(app, db_dj):
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=3)
    ids = _pista_ids(sid)
    guardar_config("dj_sesion_id", str(sid))
    guardar_config("dj_pista_id", str(ids[2]))
    guardar_config("dj_indice_pista", "2")
    guardar_config("dj_pos_pista_seg", "12.5")
    guardar_config("dj_pos_global_seg", "252.5")
    m, _r = _modelo(app)
    m.restaurar_sesion_persistida()
    # Simular que cierra estando en pausa: debe re-persistir los mismos datos.
    guardar_config("dj_sesion_id", "0")  # ensuciar para comprobar que reescribe
    m._guardar_estado_sesion()
    assert int(obtener_config("dj_sesion_id", "0")) == sid
    assert int(obtener_config("dj_pista_id", "0")) == ids[2]
    assert int(obtener_config("dj_indice_pista", "0")) == 2


def test_guardar_estado_sin_sesion_limpia(app, db_dj):
    guardar_config("dj_sesion_id", "777")  # marcador obsoleto
    m, _r = _modelo(app)
    # Sin sesión activa (estado 'detenido'): debe limpiar.
    m._guardar_estado_sesion()
    assert int(obtener_config("dj_sesion_id", "0") or 0) == 0


def test_round_trip_guardar_restaurar(app, db_dj):
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=3)
    ids = _pista_ids(sid)
    # Modelo 1: restaura un estado inicial, luego "cierra" (persiste).
    guardar_config("dj_sesion_id", str(sid))
    guardar_config("dj_pista_id", str(ids[1]))
    guardar_config("dj_indice_pista", "1")
    guardar_config("dj_pos_pista_seg", "33.0")
    guardar_config("dj_pos_global_seg", "153.0")
    m1, _r1 = _modelo(app)
    m1.restaurar_sesion_persistida()
    m1._guardar_estado_sesion()

    # Modelo 2 (nueva apertura): restaura desde lo persistido por m1.
    m2, _r2 = _modelo(app)
    m2.restaurar_sesion_persistida()
    assert m2.sesion_id == sid
    assert m2.estado_dj == "pausado"
    assert int(m2._reanudar_sesion_pendiente["pista_id"]) == ids[1]


def test_descartar_limpia_estado_persistido(app, db_dj):
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=2)
    guardar_config("dj_sesion_id", str(sid))
    m, _r = _modelo(app)
    m.restaurar_sesion_persistida()
    assert m.tiene_sesion is True
    m.descartar()
    assert int(obtener_config("dj_sesion_id", "0") or 0) == 0
    assert m._reanudar_sesion_pendiente is None


def test_detener_sesion_limpia_estado_persistido(app, db_dj):
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=2)
    guardar_config("dj_sesion_id", str(sid))
    m, _r = _modelo(app)
    m.restaurar_sesion_persistida()
    assert m.tiene_sesion is True
    m.detener_sesion()
    assert int(obtener_config("dj_sesion_id", "0") or 0) == 0
    assert m._reanudar_sesion_pendiente is None


# ═════════════════════════════════════════════════════════════════════════════
# #7b — Portada del player DJ (slot resolutor, sin GUI)
# ═════════════════════════════════════════════════════════════════════════════

def test_dj_siguiente_adquiere_ownership(app, db_dj):
    """Pulsar anterior/siguiente en el player DJ debe TOMAR el ownership del
    audio (antes sonaba el motor DJ a la vez que el reproductor global)."""
    from servicios.dj_privado.ownership import Owner
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=3)
    guardar_config("dj_sesion_id", str(sid))
    m, r = _modelo(app)
    try:
        m.restaurar_sesion_persistida()  # sesión cargada, aún sin reproducir
        assert m.tiene_sesion is True
        assert m._ownership.owner == Owner.GLOBAL  # global tiene el audio
        m.dj_siguiente()
        # Ahora el DJ es dueño del audio y el global quedó suspendido.
        assert m._ownership.owner == Owner.SESION_DJ
        assert r.modo_dj_activo is True
    finally:
        m.cerrar()


def test_dj_portada_pista_devuelve_str_sin_lanzar(app, db_dj):
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=2)
    guardar_config("dj_sesion_id", str(sid))
    m, _r = _modelo(app)
    m.restaurar_sesion_persistida()
    # Índice válido: devuelve una cadena (vacía si la pista no tiene portada).
    val = m.dj_portada_pista(0)
    assert isinstance(val, str)
    # Índices inválidos: cadena vacía, nunca excepción.
    assert m.dj_portada_pista(-1) == ""
    assert m.dj_portada_pista(999) == ""
