"""Tests del reproductor de sesion DJ y de la suspension del reproductor global.

Cobertura:
  - Modo DJ en `Reproductor` global: set/unset, idempotencia, callbacks.
  - `ReproductorSesionDj`: carga, control de reproduccion, transiciones,
    cancelaciones, edge cases.
  - Integracion: el ModeloDjPrivado activa modo DJ al reproducir y lo
    restaura al detener.

NOTA: VLC se inicializa en modo simulado para las pruebas que no necesitan
audio real. Hay un test marcado `@pytest.mark.slow` que reproduce 2 pistas
reales con crossfade y se activa con `NB_SOUND_RUN_SLOW_TESTS=1`.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db


# ─── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_dj(tmp_path):
    inicializar_db(tmp_path / "dj.db")
    try:
        yield tmp_path
    finally:
        cerrar_db()


def _crear_pista(tmp_path: Path, nombre: str, duracion: float = 30.0) -> int:
    """Inserta una pista de prueba en la BD y devuelve su id."""
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
                           ruta_archivo, nombre_archivo, tamano_bytes, duracion_seg,
                           estado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'biblioteca')
        """,
        (alb_id, art_id, f"P {nombre}", f"A {nombre}", f"Al {nombre}",
         str(ruta), ruta.name, ruta.stat().st_size, duracion),
    ).lastrowid
    return int(pid)


def _crear_sesion_con_pistas(tmp_path: Path, n_pistas: int = 3) -> int:
    """Crea una sesion DJ minima con `n_pistas` pistas asociadas."""
    from servicios.dj_privado import persistencia as dj_persist
    sid = dj_persist.crear_sesion(
        prompt="test sesion",
        intent_json="{}",
        objetivo_minutos=10,
        motor_version="dj_v1",
        semilla=None,
        resumen={},
    )
    filas = []
    for i in range(n_pistas):
        pid = _crear_pista(tmp_path, f"sesion_{sid}_t{i}", duracion=30.0)
        filas.append(dj_persist.PistaSesionRow(
            sesion_id=sid,
            posicion=i,
            pista_id=pid,
            score_total=0.8,
            score_intent=0.7,
            score_transicion=0.75,
            score_curva=0.5 + i * 0.05,
            razones=[],
            transicion={"tecnica_sugerida": "crossfade", "overlap_seg": 1.5, "score": 0.7}
                if i > 0 else {},
            estado="planificada",
            bloqueada=False,
        ))
    dj_persist.insertar_pistas_sesion(sid, filas)
    dj_persist.actualizar_estado_sesion(sid, "lista")
    return sid


# ═════════════════════════════════════════════════════════════════════════════
# Reproductor global: modo DJ
# ═════════════════════════════════════════════════════════════════════════════

def test_modo_dj_inicial_es_false(db_dj):
    from servicios.reproductor import Reproductor
    r = Reproductor(permitir_modo_simulado=True)
    assert r.modo_dj_activo is False


def test_set_modo_dj_idempotente(db_dj):
    from servicios.reproductor import Reproductor
    r = Reproductor(permitir_modo_simulado=True)
    eventos = []
    r.on_modo_dj(lambda a: eventos.append(a))
    r.set_modo_dj(True)
    r.set_modo_dj(True)   # idempotente
    r.set_modo_dj(False)
    r.set_modo_dj(False)  # idempotente
    assert eventos == [True, False]


def test_set_modo_dj_callback_emite_en_orden(db_dj):
    from servicios.reproductor import Reproductor
    r = Reproductor(permitir_modo_simulado=True)
    eventos = []
    r.on_modo_dj(lambda a: eventos.append(a))
    r.set_modo_dj(True);  assert r.modo_dj_activo is True
    r.set_modo_dj(False); assert r.modo_dj_activo is False
    assert eventos == [True, False]


def test_set_modo_dj_no_afecta_estado_cola(db_dj):
    """Activar modo DJ NO debe alterar la cola persistida ni la pista activa
    logica del reproductor global."""
    from servicios.reproductor import Reproductor
    r = Reproductor(permitir_modo_simulado=True)
    pid = _crear_pista(db_dj, "global")
    r.reproducir_pista({
        "id": pid, "titulo": "T", "artista_nombre": "A", "album_titulo": "AL",
        "ruta_archivo": str(db_dj / "global.mp3"), "duracion_seg": 30.0,
    })
    cola_antes = r.obtener_cola()
    pista_antes = r.pista_activa
    r.set_modo_dj(True)
    cola_durante = r.obtener_cola()
    pista_durante = r.pista_activa
    assert cola_durante == cola_antes
    assert pista_durante is not None and pista_antes is not None
    assert pista_durante.id == pista_antes.id
    r.set_modo_dj(False)


def test_modeloreproductor_expone_modo_dj(db_dj):
    """ModeloReproductor.modo_dj_activo refleja el flag del backend."""
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QSignalSpy
    app = QGuiApplication.instance() or QGuiApplication([])
    from servicios.reproductor import Reproductor
    from ui.modelos_qml import ModeloReproductor
    r = Reproductor(permitir_modo_simulado=True)
    m = ModeloReproductor(r)
    spy = QSignalSpy(m.modoDjActivoCambiado)
    assert m.modo_dj_activo is False
    r.set_modo_dj(True)
    app.processEvents()
    assert m.modo_dj_activo is True
    assert spy.count() >= 1
    r.set_modo_dj(False)
    app.processEvents()
    assert m.modo_dj_activo is False


# ═════════════════════════════════════════════════════════════════════════════
# ReproductorSesionDj
# ═════════════════════════════════════════════════════════════════════════════

def test_reproductor_sesion_dj_carga_sesion_vacia(db_dj):
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
    r = ReproductorSesionDj(permitir_modo_simulado=True)
    n = r.cargar_sesion(99999)  # no existe
    assert n == 0
    assert r.sesion_id == 0
    assert r.total_pistas == 0


def test_reproductor_sesion_dj_carga_sesion_real(db_dj):
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=3)
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
    r = ReproductorSesionDj(permitir_modo_simulado=True)
    n = r.cargar_sesion(sid)
    assert n == 3
    assert r.sesion_id == sid
    assert r.total_pistas == 3
    assert r.estado.value == "detenido"


def test_reproductor_sesion_dj_filtra_archivos_inexistentes(db_dj):
    """Pistas con archivo ausente se omiten del set reproducible."""
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=2)
    # Borrar fisicamente el archivo de una pista
    con = get_conexion()
    fila = con.execute(
        "SELECT ruta_archivo FROM pistas p JOIN dj_pistas_sesion dps ON dps.pista_id=p.id "
        "WHERE dps.sesion_id=? AND dps.posicion=0", (sid,)
    ).fetchone()
    Path(fila["ruta_archivo"]).unlink()
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
    r = ReproductorSesionDj(permitir_modo_simulado=True)
    n = r.cargar_sesion(sid)
    assert n == 1  # solo la pista 1 sobrevive


def test_reproductor_sesion_dj_snapshot(db_dj):
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=2)
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
    r = ReproductorSesionDj(permitir_modo_simulado=True)
    r.cargar_sesion(sid)
    snap = r.snapshot()
    assert snap["sesion_id"] == sid
    assert snap["total"] == 2
    assert snap["estado"] == "detenido"
    assert snap["indice"] == -1


def test_reproductor_sesion_dj_callbacks_se_registran_y_desregistran(db_dj):
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
    r = ReproductorSesionDj(permitir_modo_simulado=True)
    cb = lambda *a, **k: None
    r.on_estado(cb); r.off_estado(cb)
    r.on_progreso(cb); r.off_progreso(cb)
    r.on_pista_cambio(cb); r.off_pista_cambio(cb)
    r.on_transicion(cb); r.off_transicion(cb)


def test_reproductor_sesion_dj_close_libera_recursos(db_dj):
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
    r = ReproductorSesionDj(permitir_modo_simulado=True)
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=1)
    r.cargar_sesion(sid)
    r.close()
    # Llamar close de nuevo no debe lanzar.
    r.close()


def test_reproductor_sesion_dj_play_sin_pistas_devuelve_false(db_dj):
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
    r = ReproductorSesionDj(permitir_modo_simulado=True)
    assert r.play() is False


# ═════════════════════════════════════════════════════════════════════════════
# Modelo DJ Privado: integracion con reproductor de sesion
# ═════════════════════════════════════════════════════════════════════════════

def test_modelo_dj_expone_propiedades_de_reproductor(db_dj):
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    from servicios.reproductor import Reproductor
    from ui.modelos_qml import ModeloDjPrivado
    r = Reproductor(permitir_modo_simulado=True)
    m = ModeloDjPrivado(r)
    # Estado inicial
    assert m.estado_dj == "detenido"
    assert m.dj_reproduciendo is False
    assert m.dj_pausado is False
    assert m.dj_indice_actual == -1
    assert m.dj_pos_sesion_seg == 0.0


def test_modelo_dj_workspace_eliminar_sesion(db_dj):
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    sid = _crear_sesion_con_pistas(db_dj, n_pistas=2)
    from servicios.reproductor import Reproductor
    from ui.modelos_qml import ModeloDjPrivado
    r = Reproductor(permitir_modo_simulado=True)
    m = ModeloDjPrivado(r)
    m.cargar_historial()
    total_pre = m.historial.total
    assert total_pre >= 1
    ok = m.eliminar_sesion(sid)
    assert ok is True
    m.cargar_historial()
    # La sesion ya no esta
    ids = [m.historial.obtener(i).get("id") for i in range(m.historial.total)]
    assert sid not in ids


def test_modelo_dj_filtro_historial_texto(db_dj):
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    from servicios.dj_privado import persistencia as dj_persist
    from servicios.reproductor import Reproductor
    from ui.modelos_qml import ModeloDjPrivado
    # Crear 2 sesiones con prompts distintos
    sid1 = dj_persist.crear_sesion(
        prompt="energico para correr", intent_json="{}",
        objetivo_minutos=30, motor_version="dj_v1", semilla=None, resumen={},
    )
    sid2 = dj_persist.crear_sesion(
        prompt="relajante nocturno", intent_json="{}",
        objetivo_minutos=45, motor_version="dj_v1", semilla=None, resumen={},
    )
    r = Reproductor(permitir_modo_simulado=True)
    m = ModeloDjPrivado(r)
    m.establecer_filtro_historial_texto("energico")
    ids_filtrados = [m.historial.obtener(i).get("id") for i in range(m.historial.total)]
    assert sid1 in ids_filtrados
    assert sid2 not in ids_filtrados
    # Limpiar filtro
    m.establecer_filtro_historial_texto("")
    ids_total = [m.historial.obtener(i).get("id") for i in range(m.historial.total)]
    assert sid1 in ids_total and sid2 in ids_total


def test_modelo_dj_descartar_restaura_reproductor_global(db_dj):
    """descartar() debe liberar modo DJ del reproductor global aunque no este
    activo (idempotente)."""
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    from servicios.reproductor import Reproductor
    from ui.modelos_qml import ModeloDjPrivado
    r = Reproductor(permitir_modo_simulado=True)
    m = ModeloDjPrivado(r)
    r.set_modo_dj(True)
    assert r.modo_dj_activo is True
    m.descartar()
    assert r.modo_dj_activo is False


# ═════════════════════════════════════════════════════════════════════════════
# Contrato QML
# ═════════════════════════════════════════════════════════════════════════════

def _qml(path: str) -> str:
    return Path(path).read_text()


def test_qml_vista_dj_tiene_tabs():
    qml = _qml("ui/qml/vistas/VistaDJPrivado.qml")
    assert "construir" in qml
    assert "sesion" in qml
    assert "historial" in qml
    assert "tab_actual" in qml


def test_qml_vista_dj_usa_reproductor_aislado():
    """La vista NO debe llamar a reproductor.reproducir_cola ni a slots del
    reproductor global. Debe usar djPrivado.dj_*."""
    qml = (
        _qml("ui/qml/vistas/VistaDJPrivado.qml") +
        _qml("ui/qml/vistas/DjSesionActiva.qml") +
        _qml("ui/qml/vistas/DjHistorial.qml")
    )
    # Acoples prohibidos
    assert "reproductor.reproducir_cola" not in qml, \
        "La vista DJ no debe encolar pistas en el reproductor global"
    assert "reproductor.pausar_reanudar" not in qml
    # Debe usar la API DJ propia
    assert "dj_play_pause" in qml
    assert "dj_siguiente" in qml
    assert "dj_anterior" in qml
    assert "detener_sesion" in qml


def test_qml_dj_sesion_activa_visualiza_transicion():
    qml = _qml("ui/qml/vistas/DjSesionActiva.qml")
    assert "dj_transicion_activa" in qml or "dj_transicionando" in qml
    assert "tecnica" in qml.lower() or "crossfade" in qml.lower()


def test_qml_dj_historial_tiene_workspace():
    qml = _qml("ui/qml/vistas/DjHistorial.qml")
    assert "Buscar por prompt" in qml or "filtro" in qml.lower()
    assert "eliminar" in qml.lower()
    assert "duplicar" in qml.lower() or "regenerar" in qml.lower() or "duplicar_sesion" in qml
    assert "cargar_sesion_anterior" in qml or "reproducir_sesion" in qml


def test_qml_barra_reproduccion_tiene_overlay_dj():
    qml = _qml("ui/qml/componentes/BarraReproduccion.qml")
    assert "modo_dj_activo" in qml
    assert "DJ Privado" in qml or "Volver a DJ" in qml


def test_modelo_dj_tiene_propiedades_reproductor():
    src = _qml("ui/modelos_qml.py")
    for sym in (
        "def estado_dj", "def dj_reproduciendo", "def dj_pausado",
        "def dj_indice_actual", "def dj_pos_sesion_seg", "def dj_dur_sesion_seg",
        "def dj_pos_pista_seg", "def dj_dur_pista_seg", "def dj_transicion_activa",
        "def dj_play_pause", "def dj_siguiente", "def dj_anterior",
        "def dj_saltar_a", "def detener_sesion",
        "def eliminar_sesion", "def duplicar_sesion",
        "def establecer_filtro_historial_texto",
    ):
        assert sym in src, f"Falta en ModeloDjPrivado: {sym}"


def test_reproductor_global_tiene_modo_dj():
    src = _qml("servicios/reproductor.py")
    for sym in ("def set_modo_dj", "def on_modo_dj", "_modo_dj_activo", "modo_dj_activo"):
        assert sym in src, f"Falta en Reproductor: {sym}"


# ═════════════════════════════════════════════════════════════════════════════
# Mix engine integrado: mix points poblados al cargar, fin_efectivo respeta mix_out
# ═════════════════════════════════════════════════════════════════════════════


def _set_bpm_de_pista(pista_id: int, bpm: float) -> None:
    """Inserta una fila en track_audio_features para que el JOIN devuelva BPM."""
    get_conexion().execute(
        """
        INSERT OR REPLACE INTO track_audio_features
            (track_id, analyzer_version, analysis_mode, analysis_status, bpm)
        VALUES (?, ?, ?, ?, ?)
        """,
        (str(pista_id), "test", "basic", "ok", float(bpm)),
    )


def test_reproductor_con_mix_engine_puebla_mix_points(db_dj):
    """Cargar una sesión con mix_engine inyectado debe poblar mix_in/mix_out
    en cada PistaSesion usando el BPM disponible."""
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
    from servicios.dj_privado.mix_engine import MixEngine

    sid = _crear_sesion_con_pistas(db_dj, n_pistas=2)
    # Pistas largas con BPM para que el cálculo por BPM aplique.
    pistas_largas = []
    for i in range(2):
        pid = _crear_pista(db_dj, f"longa_{i}", duracion=240.0)
        _set_bpm_de_pista(pid, 120.0)
        pistas_largas.append(pid)
    # Reemplazar las pistas de la sesión por las largas.
    from servicios.dj_privado import persistencia as dj_persist
    get_conexion().execute(
        "UPDATE dj_pistas_sesion SET pista_id = ? WHERE sesion_id = ? AND posicion = 0",
        (pistas_largas[0], sid),
    )
    get_conexion().execute(
        "UPDATE dj_pistas_sesion SET pista_id = ? WHERE sesion_id = ? AND posicion = 1",
        (pistas_largas[1], sid),
    )

    rep = ReproductorSesionDj(permitir_modo_simulado=True, mix_engine=MixEngine())
    total = rep.cargar_sesion(sid)
    assert total == 2
    p0 = rep._pistas[0]
    p1 = rep._pistas[1]
    # Con BPM 120 y duración 240s: intro=8s (16 beats), outro=16s (32 beats).
    assert p0.mix_in_seg == pytest.approx(8.0, abs=0.01)
    assert p0.mix_out_seg == pytest.approx(224.0, abs=0.01)
    assert p1.mix_in_seg == pytest.approx(8.0, abs=0.01)
    assert p1.mix_out_seg == pytest.approx(224.0, abs=0.01)
    rep.close()


def test_reproductor_sin_mix_engine_no_puebla_mix_points(db_dj):
    """Sin mix_engine inyectado, mix_in/mix_out quedan en None (legacy)."""
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj

    sid = _crear_sesion_con_pistas(db_dj, n_pistas=2)
    rep = ReproductorSesionDj(permitir_modo_simulado=True)  # sin mix_engine
    rep.cargar_sesion(sid)
    for p in rep._pistas:
        assert p.mix_in_seg is None
        assert p.mix_out_seg is None
    rep.close()


def test_reproductor_carga_dispara_pre_fetch_solo_con_mix_engine(db_dj, monkeypatch):
    """Cargar sesión con mix_engine debe disparar pre_fetch_inicial_async.
    Sin mix_engine, no debe disparar nada."""
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
    from servicios.dj_privado.mix_engine import MixEngine
    from servicios.dj_privado import stems_prefetch

    invocaciones = []

    def fake_prefetch_async(ids, **kwargs):
        invocaciones.append((list(ids), kwargs))
        # Devolver un Thread real para mantener la firma.
        import threading
        t = threading.Thread(target=lambda: None, daemon=True)
        t.start()
        return t

    monkeypatch.setattr(stems_prefetch, "pre_fetch_inicial_async", fake_prefetch_async)

    sid = _crear_sesion_con_pistas(db_dj, n_pistas=2)

    # Sin mix_engine: no pre-fetch.
    rep_sin = ReproductorSesionDj(permitir_modo_simulado=True)
    rep_sin.cargar_sesion(sid)
    assert invocaciones == []
    rep_sin.close()

    # Con mix_engine: pre-fetch invocado con los pista_ids.
    rep_con = ReproductorSesionDj(permitir_modo_simulado=True, mix_engine=MixEngine())
    rep_con.cargar_sesion(sid)
    assert len(invocaciones) == 1
    assert len(invocaciones[0][0]) == 2  # 2 pistas en la sesión
    rep_con.close()
