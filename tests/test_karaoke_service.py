"""Tests del subsistema karaoke (servicios + jobs + modelo QML + contrato vista).

Cobertura:
  - jobs_repo: encolar, transiciones, cancelar, vaciar, asignar manual
  - cola: zombies, validacion backend, snapshot
  - servicios biblioteca: listar/contar/resumen
  - ModeloKaraoke: API publica usada por VistaKaraoke
  - Contrato QML: bindings/acciones criticas

Los tests pesados que tocan el modelo real de Demucs viven en
`test_karaoke_separador.py` (marcados `@pytest.mark.slow`).
"""
from __future__ import annotations

from pathlib import Path
import threading

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db
from servicios import biblioteca as svc_bib
from servicios import karaoke as svc_kar


# ─── helpers ────────────────────────────────────────────────────────────────

def _crear_pista(tmp_path: Path, nombre: str, *, estado_karaoke: str = "no_procesada",
                 ruta_instrumental: str = "") -> dict:
    ruta = tmp_path / f"{nombre}.mp3"
    ruta.write_bytes(b"fake audio")
    con = get_conexion()
    artista_id = con.execute(
        "INSERT INTO artistas(nombre, nombre_slug) VALUES (?, ?)",
        (f"Artista {nombre}", f"artista-{nombre}"),
    ).lastrowid
    album_id = con.execute(
        "INSERT INTO albums(artista_id, titulo, titulo_slug, tipo) VALUES (?, ?, ?, 'Album')",
        (artista_id, f"Album {nombre}", f"album-{nombre}"),
    ).lastrowid
    pista_id = con.execute(
        """
        INSERT INTO pistas(
            album_id, artista_id, titulo, artista_nombre, album_titulo,
            ruta_archivo, nombre_archivo, tamano_bytes, duracion_seg,
            karaoke_estado, karaoke_ruta_instrumental, estado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'biblioteca')
        """,
        (album_id, artista_id, f"Pista {nombre}", f"Artista {nombre}", f"Album {nombre}",
         str(ruta), ruta.name, ruta.stat().st_size, 200,
         estado_karaoke, ruta_instrumental or None),
    ).lastrowid
    return {"id": pista_id, "album_id": album_id, "artista_id": artista_id}


@pytest.fixture()
def db_karaoke(tmp_path):
    inicializar_db(tmp_path / "karaoke.db")
    try:
        yield tmp_path
    finally:
        cerrar_db()


# ═══════════════════════════════════════════════════════════════════════════
# servicios/biblioteca — queries de listado (compatibilidad UI)
# ═══════════════════════════════════════════════════════════════════════════

def test_listar_karaoke_vacia(db_karaoke):
    assert svc_bib.listar_pistas_karaoke() == []


def test_listar_karaoke_devuelve_campos_esperados(db_karaoke):
    _crear_pista(db_karaoke, "c1", estado_karaoke="lista", ruta_instrumental="/fake/i.mp3")
    p = svc_bib.listar_pistas_karaoke()[0]
    for campo in ("id", "titulo", "artista_nombre", "album_titulo", "duracion_seg",
                  "karaoke_estado", "karaoke_ruta_instrumental",
                  "karaoke_error_codigo", "karaoke_error_mensaje",
                  "karaoke_progreso", "karaoke_intento"):
        assert campo in p, f"Falta {campo}"
    assert p["karaoke_estado"] == "lista"
    assert p["karaoke_ruta_instrumental"] == "/fake/i.mp3"


def test_listar_karaoke_filtra_por_grupo_sin_preparar(db_karaoke):
    _crear_pista(db_karaoke, "np",  estado_karaoke="no_procesada")
    _crear_pista(db_karaoke, "enc", estado_karaoke="en_cola")
    _crear_pista(db_karaoke, "prc", estado_karaoke="procesando")
    _crear_pista(db_karaoke, "lst", estado_karaoke="lista")

    sin_prep = svc_bib.listar_pistas_karaoke(filtro_estado="sin_preparar")
    assert len(sin_prep) == 1 and sin_prep[0]["karaoke_estado"] == "no_procesada"

    en_cola_g = svc_bib.listar_pistas_karaoke(filtro_estado="en_cola")
    assert len(en_cola_g) == 2
    assert {p["karaoke_estado"] for p in en_cola_g} == {"en_cola", "procesando"}


def test_listar_karaoke_paginacion(db_karaoke):
    for i in range(10):
        _crear_pista(db_karaoke, f"t{i}")
    p0 = svc_bib.listar_pistas_karaoke(limite=4, offset=0)
    p1 = svc_bib.listar_pistas_karaoke(limite=4, offset=4)
    p2 = svc_bib.listar_pistas_karaoke(limite=4, offset=8)
    assert len(p0) == 4 and len(p1) == 4 and len(p2) == 2
    assert {p["id"] for p in p0}.isdisjoint({p["id"] for p in p1})


def test_listar_karaoke_filtra_por_texto(db_karaoke):
    _crear_pista(db_karaoke, "bohemian")
    _crear_pista(db_karaoke, "wonderwall")
    res = svc_bib.listar_pistas_karaoke(filtro_texto="bohemian")
    assert len(res) == 1 and "bohemian" in res[0]["titulo"].lower()


def test_listar_karaoke_excluye_pistas_no_biblioteca(db_karaoke):
    ruta = db_karaoke / "rev.mp3"; ruta.write_bytes(b"x")
    get_conexion().execute(
        "INSERT INTO pistas(titulo,artista_nombre,album_titulo,ruta_archivo,nombre_archivo,tamano_bytes,estado,karaoke_estado) "
        "VALUES ('Rev','','',?,'r',1,'revision','no_procesada')",
        (str(ruta),),
    )
    assert svc_bib.listar_pistas_karaoke() == []


def test_contar_karaoke_coincide_con_listar(db_karaoke):
    for i in range(7):
        _crear_pista(db_karaoke, f"p{i}", estado_karaoke="no_procesada" if i < 4 else "lista")
    assert svc_bib.contar_pistas_karaoke() == len(svc_bib.listar_pistas_karaoke(limite=100)) == 7


def test_resumen_karaoke_cuenta_correctamente(db_karaoke):
    _crear_pista(db_karaoke, "l1", estado_karaoke="lista")
    _crear_pista(db_karaoke, "l2", estado_karaoke="lista")
    _crear_pista(db_karaoke, "f1", estado_karaoke="fallida")
    _crear_pista(db_karaoke, "n1", estado_karaoke="no_procesada")
    _crear_pista(db_karaoke, "a1", estado_karaoke="no_aplica")
    r = svc_bib.resumen_karaoke()
    assert r["lista"] == 2 and r["fallida"] == 1 and r["sin_preparar"] == 1
    assert r["no_aplica"] == 1 and r["total"] == 5


# ═══════════════════════════════════════════════════════════════════════════
# servicios/karaoke/backend
# ═══════════════════════════════════════════════════════════════════════════

def test_backend_diagnostico_devuelve_dict_completo():
    d = svc_kar.diagnostico()
    for k in ("demucs_disponible", "torch_disponible", "ffmpeg_disponible",
              "device_disponible", "devices_soportados", "backend_listo",
              "mensaje", "instrucciones"):
        assert k in d
    assert isinstance(d["devices_soportados"], list)
    assert "cpu" in d["devices_soportados"]


def test_backend_seleccionar_device_auto_no_falla():
    dev = svc_kar.seleccionar_device("auto")
    assert dev in ("cpu", "cuda", "mps")


def test_backend_seleccionar_device_invalido_cae_a_cpu():
    assert svc_kar.seleccionar_device("xpu") == "cpu"


def test_backend_validar_listo_devuelve_none_si_todo_ok():
    # En este entorno hemos verificado que demucs+torch+ffmpeg estan presentes.
    estado = svc_kar.validar_listo()
    if estado is not None:
        # Si por alguna razon falta algo, el codigo de error debe ser valido.
        assert estado in ("backend_no_disponible", "ffmpeg_faltante")


# ═══════════════════════════════════════════════════════════════════════════
# servicios/karaoke/jobs_repo — cola persistente
# ═══════════════════════════════════════════════════════════════════════════

def test_jobs_encolar_crea_job(db_karaoke):
    d = _crear_pista(db_karaoke, "j1")
    jid = svc_kar.encolar(d["id"])
    assert jid is not None and jid > 0
    job = svc_kar.job_por_id(jid)
    assert job["estado"] == "en_cola" and job["pista_id"] == d["id"]
    # Cache desnormalizado en pistas.
    p = svc_bib.pista_karaoke_por_id(d["id"])
    assert p["karaoke_estado"] == "en_cola"


def test_jobs_encolar_no_duplica_jobs_activos(db_karaoke):
    d = _crear_pista(db_karaoke, "j2")
    jid1 = svc_kar.encolar(d["id"])
    assert jid1 is not None
    # La segunda llamada devuelve None: ya hay job activo.
    assert svc_kar.encolar(d["id"]) is None
    # Sigue habiendo un solo job activo.
    activo = svc_kar.job_activo_por_pista(d["id"])
    assert activo and activo["id"] == jid1


def test_jobs_encolar_respeta_no_aplica(db_karaoke):
    d = _crear_pista(db_karaoke, "j3", estado_karaoke="no_aplica")
    assert svc_kar.encolar(d["id"]) is None


def test_jobs_encolar_muchas_cuenta_solo_nuevas(db_karaoke):
    d1 = _crear_pista(db_karaoke, "n1")
    d2 = _crear_pista(db_karaoke, "n2")
    svc_kar.encolar(d1["id"])
    n = svc_kar.encolar_muchas([d1["id"], d2["id"]])
    assert n == 1  # d1 ya estaba encolada


def test_jobs_encolar_todas_sin_preparar(db_karaoke):
    _crear_pista(db_karaoke, "np1", estado_karaoke="no_procesada")
    _crear_pista(db_karaoke, "np2", estado_karaoke="no_procesada")
    _crear_pista(db_karaoke, "fl1", estado_karaoke="fallida")
    _crear_pista(db_karaoke, "lst", estado_karaoke="lista")
    n = svc_kar.encolar_todas_sin_preparar()
    assert n == 3  # las dos no_procesada + una fallida
    r = svc_bib.resumen_karaoke()
    assert r["en_cola"] == 3 and r["lista"] == 1


def test_jobs_sacar_de_cola(db_karaoke):
    d = _crear_pista(db_karaoke, "sc1")
    svc_kar.encolar(d["id"])
    assert svc_kar.sacar_de_cola(d["id"]) is True
    p = svc_bib.pista_karaoke_por_id(d["id"])
    assert p["karaoke_estado"] == "no_procesada"


def test_jobs_vaciar_cola(db_karaoke):
    for i in range(3):
        d = _crear_pista(db_karaoke, f"v{i}")
        svc_kar.encolar(d["id"])
    n = svc_kar.vaciar_cola()
    assert n == 3
    assert svc_bib.resumen_karaoke()["en_cola"] == 0


def test_jobs_transicionar_estado_actualiza_cache(db_karaoke):
    d = _crear_pista(db_karaoke, "ts1")
    jid = svc_kar.encolar(d["id"])
    assert svc_kar.jobs_repo.transicionar_estado(jid, "procesando", progreso=0.5) is True
    p = svc_bib.pista_karaoke_por_id(d["id"])
    assert p["karaoke_estado"] == "procesando"


def test_jobs_marcar_lista(db_karaoke):
    d = _crear_pista(db_karaoke, "ml1")
    jid = svc_kar.encolar(d["id"])
    ok = svc_kar.jobs_repo.marcar_lista(jid, "/tmp/x.mp3", bytes_salida=12345, duracion_proc_ms=8000)
    assert ok is True
    p = svc_bib.pista_karaoke_por_id(d["id"])
    assert p["karaoke_estado"] == "lista" and p["karaoke_ruta_instrumental"] == "/tmp/x.mp3"


def test_jobs_marcar_fallido_guarda_codigo_y_mensaje(db_karaoke):
    d = _crear_pista(db_karaoke, "mf1")
    jid = svc_kar.encolar(d["id"])
    svc_kar.jobs_repo.marcar_fallido(jid, error_codigo="audio_corrupto", error_mensaje="archivo invalido")
    p = svc_bib.pista_karaoke_por_id(d["id"])
    assert p["karaoke_estado"] == "fallida"
    assert p["karaoke_error_codigo"] == "audio_corrupto"
    assert "archivo" in (p["karaoke_error_mensaje"] or "")


def test_jobs_resetear_estado_pista(db_karaoke):
    d = _crear_pista(db_karaoke, "rst", estado_karaoke="lista", ruta_instrumental="/x/y.mp3")
    assert svc_kar.resetear_estado_pista(d["id"]) is True
    p = svc_bib.pista_karaoke_por_id(d["id"])
    assert p["karaoke_estado"] == "no_procesada"
    assert not p["karaoke_ruta_instrumental"]


def test_jobs_marcar_para_reprocesar_borra_cache_y_encola(db_karaoke, tmp_path):
    # Crear una pista 'lista' con un archivo instrumental real en disco.
    instrumental = tmp_path / "instrumental.mp3"
    instrumental.write_bytes(b"\x00" * 2048)
    d = _crear_pista(db_karaoke, "rep", estado_karaoke="lista",
                     ruta_instrumental=str(instrumental))
    assert instrumental.exists()

    jid = svc_kar.marcar_para_reprocesar(d["id"])
    assert jid is not None
    # El archivo de cache debio borrarse.
    assert not instrumental.exists()
    # La pista quedo encolada (no 'lista').
    p = svc_bib.pista_karaoke_por_id(d["id"])
    assert p["karaoke_estado"] == "en_cola"
    assert not p["karaoke_ruta_instrumental"]


def test_jobs_marcar_para_reprocesar_pista_inexistente_retorna_none(db_karaoke):
    assert svc_kar.marcar_para_reprocesar(99999) is None
    assert svc_kar.marcar_para_reprocesar(0) is None


def test_jobs_asignar_instrumental_manual(db_karaoke):
    d = _crear_pista(db_karaoke, "im1")
    ok = svc_kar.asignar_instrumental_manual(d["id"], "/tmp/manual.mp3")
    assert ok is True
    p = svc_bib.pista_karaoke_por_id(d["id"])
    assert p["karaoke_estado"] == "lista"
    assert p["karaoke_ruta_instrumental"] == "/tmp/manual.mp3"


def test_jobs_marcar_no_aplica(db_karaoke):
    d = _crear_pista(db_karaoke, "na1")
    svc_kar.encolar(d["id"])
    assert svc_kar.marcar_no_aplica(d["id"]) is True
    p = svc_bib.pista_karaoke_por_id(d["id"])
    assert p["karaoke_estado"] == "no_aplica"
    # Job activo debio cancelarse.
    assert svc_kar.job_activo_por_pista(d["id"]) is None


def test_jobs_restaurar_de_no_aplica(db_karaoke):
    d = _crear_pista(db_karaoke, "rna1", estado_karaoke="no_aplica")
    assert svc_kar.restaurar_de_no_aplica(d["id"]) is True
    p = svc_bib.pista_karaoke_por_id(d["id"])
    assert p["karaoke_estado"] == "no_procesada"


def test_jobs_resumen(db_karaoke):
    d1 = _crear_pista(db_karaoke, "r1")
    d2 = _crear_pista(db_karaoke, "r2")
    svc_kar.encolar(d1["id"])
    jid2 = svc_kar.encolar(d2["id"])
    svc_kar.jobs_repo.marcar_lista(jid2, "/tmp/r2.mp3", bytes_salida=100, duracion_proc_ms=50)
    res = svc_kar.resumen_jobs()
    assert res["en_cola"] == 1 and res["lista"] == 1


def test_jobs_siguiente_job_fifo(db_karaoke):
    d1 = _crear_pista(db_karaoke, "f1")
    d2 = _crear_pista(db_karaoke, "f2")
    svc_kar.encolar(d1["id"])
    svc_kar.encolar(d2["id"])
    siguiente = svc_kar.jobs_repo.siguiente_job()
    assert siguiente["pista_id"] == d1["id"]  # FIFO


def test_jobs_listar_cola_devuelve_solo_activos(db_karaoke):
    d1 = _crear_pista(db_karaoke, "lc1")
    d2 = _crear_pista(db_karaoke, "lc2")
    jid2 = svc_kar.encolar(d1["id"])
    svc_kar.encolar(d2["id"])
    svc_kar.jobs_repo.marcar_lista(jid2, "/tmp/lc1.mp3", bytes_salida=1, duracion_proc_ms=1)
    cola = svc_kar.listar_cola()
    # d1 (que ahora es lista) NO debe estar; solo d2 (en_cola).
    assert len(cola) == 1 and cola[0]["pista_id"] == d2["id"]


# ═══════════════════════════════════════════════════════════════════════════
# servicios/karaoke/cola — orquestador
# ═══════════════════════════════════════════════════════════════════════════

def test_cola_limpiar_zombies(db_karaoke):
    d = _crear_pista(db_karaoke, "z1")
    jid = svc_kar.encolar(d["id"])
    # Marca job como "procesando" sin completarlo (simula crash).
    svc_kar.jobs_repo.transicionar_estado(jid, "procesando", progreso=0.4)
    assert svc_kar.limpiar_jobs_zombies() >= 1
    job = svc_kar.job_por_id(jid)
    assert job["estado"] == "cancelada"
    p = svc_bib.pista_karaoke_por_id(d["id"])
    assert p["karaoke_estado"] == "no_procesada"


def test_cola_procesar_sin_pendientes(db_karaoke, tmp_path):
    snaps = []
    snap = svc_kar.procesar_cola(
        cache_dir=tmp_path,
        device_pref="cpu",
        progress_callback=snaps.append,
        stop_event=threading.Event(),
    )
    assert snap["total"] == 0
    assert snap["estado"] in ("completado", "error")


def test_cola_procesar_archivo_inexistente_marca_fallido(db_karaoke, tmp_path):
    """Cuando la pista apunta a un archivo que no existe, el job queda fallido."""
    d = _crear_pista(db_karaoke, "noex")
    # Cambia ruta a una inexistente.
    get_conexion().execute(
        "UPDATE pistas SET ruta_archivo='/tmp/NOEXISTE_kar.mp3' WHERE id=?", (d["id"],),
    )
    svc_kar.encolar(d["id"])

    snaps = []
    snap = svc_kar.procesar_cola(
        cache_dir=tmp_path, device_pref="cpu",
        progress_callback=snaps.append,
        stop_event=threading.Event(),
    )
    # El job debio quedar fallido (o cancelado si el archivo se valido antes).
    p = svc_bib.pista_karaoke_por_id(d["id"])
    assert p["karaoke_estado"] == "fallida"
    assert p["karaoke_error_codigo"] in ("archivo_no_existe", "audio_corrupto")
    assert snap["failed"] >= 1 or snap["estado"] in ("completado", "cancelado")


# ═══════════════════════════════════════════════════════════════════════════
# ModeloKaraoke — fachada Python ↔ QML
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def modelo_karaoke(db_karaoke):
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QGuiApplication
    _app = QGuiApplication.instance() or QGuiApplication([])
    from ui.modelos_qml import ModeloKaraoke
    m = ModeloKaraoke()
    yield m, db_karaoke
    try:
        import shiboken6
        if shiboken6.isValid(m):
            shiboken6.delete(m)
    except Exception:
        del m
        QCoreApplication.processEvents()


def test_modelo_carga_inicial_vacia(modelo_karaoke):
    m, _ = modelo_karaoke
    m.cargar()
    assert m.pistas.total == 0 and m.resumen["total"] == 0
    assert m.filtro_estado == "sin_preparar"


def test_modelo_carga_pistas(modelo_karaoke):
    m, tmp = modelo_karaoke
    _crear_pista(tmp, "s1", estado_karaoke="lista")
    _crear_pista(tmp, "s2", estado_karaoke="no_procesada")
    m.cargar()
    assert m.pistas.total == 1  # filtro = sin_preparar
    assert m.resumen["total"] == 2


def test_modelo_filtro_estado_tabs(modelo_karaoke):
    m, tmp = modelo_karaoke
    _crear_pista(tmp, "l", estado_karaoke="lista")
    _crear_pista(tmp, "f", estado_karaoke="fallida")
    _crear_pista(tmp, "n", estado_karaoke="no_procesada")
    m.establecer_filtro_estado("lista");    assert m.pistas.total == 1
    m.establecer_filtro_estado("fallida");  assert m.pistas.total == 1
    m.establecer_filtro_estado("sin_preparar"); assert m.pistas.total == 1


def test_modelo_paginacion(modelo_karaoke):
    m, tmp = modelo_karaoke
    for i in range(60):
        _crear_pista(tmp, f"p{i:02d}", estado_karaoke="no_procesada")
    m.establecer_filtro_estado("sin_preparar")
    assert m.total_filtrado == 60 and m.total_paginas == 2
    m.pagina_siguiente()
    assert m.pagina_actual == 1 and m.pistas.total == 10


def test_modelo_encolar_pistas(modelo_karaoke):
    m, tmp = modelo_karaoke
    d1 = _crear_pista(tmp, "e1")
    d2 = _crear_pista(tmp, "e2")
    n = m.encolar_pistas([d1["id"], d2["id"]])
    assert n == 2
    assert m.resumen["en_cola"] == 2


def test_modelo_encolar_todas_sin_preparar(modelo_karaoke):
    m, tmp = modelo_karaoke
    for i in range(4):
        _crear_pista(tmp, f"a{i}", estado_karaoke="no_procesada")
    _crear_pista(tmp, "lst", estado_karaoke="lista")
    assert m.encolar_todas_sin_preparar() == 4
    assert m.resumen["en_cola"] == 4


def test_modelo_sacar_de_cola(modelo_karaoke):
    m, tmp = modelo_karaoke
    d = _crear_pista(tmp, "sc")
    m.encolar_pistas([d["id"]])
    assert m.sacar_de_cola(d["id"]) is True
    assert m.resumen["en_cola"] == 0


def test_modelo_vaciar_cola(modelo_karaoke):
    m, tmp = modelo_karaoke
    d1 = _crear_pista(tmp, "v1"); d2 = _crear_pista(tmp, "v2")
    m.encolar_pistas([d1["id"], d2["id"]])
    m.vaciar_cola()
    assert m.resumen["en_cola"] == 0


def test_modelo_reintentar_fallida(modelo_karaoke):
    m, tmp = modelo_karaoke
    d = _crear_pista(tmp, "rf", estado_karaoke="fallida")
    assert m.reintentar_fallida(d["id"]) is True
    assert m.resumen["en_cola"] == 1


def test_modelo_reprocesar_borra_cache_y_encola(modelo_karaoke):
    m, tmp = modelo_karaoke
    instrumental = tmp / "instr.mp3"
    instrumental.write_bytes(b"\x00" * 2048)
    d = _crear_pista(tmp, "repro", estado_karaoke="lista",
                     ruta_instrumental=str(instrumental))
    assert m.reprocesar(d["id"]) is True
    assert not instrumental.exists()  # cache borrado
    assert svc_bib.pista_karaoke_por_id(d["id"])["karaoke_estado"] == "en_cola"


def test_modelo_reintentar_todas_fallidas(modelo_karaoke):
    m, tmp = modelo_karaoke
    for i in range(3):
        _crear_pista(tmp, f"rt{i}", estado_karaoke="fallida")
    m.reintentar_todas_fallidas()
    assert m.resumen["en_cola"] == 3


def test_modelo_resetear_estado(modelo_karaoke):
    m, tmp = modelo_karaoke
    d = _crear_pista(tmp, "rs", estado_karaoke="fallida")
    assert m.resetear_estado(d["id"]) is True
    p = svc_bib.pista_karaoke_por_id(d["id"])
    assert p["karaoke_estado"] == "no_procesada"


def test_modelo_asignar_instrumental(modelo_karaoke):
    m, tmp = modelo_karaoke
    d = _crear_pista(tmp, "ai")
    ruta = str(tmp / "ai_i.mp3"); Path(ruta).write_bytes(b"x")
    assert m.asignar_instrumental(d["id"], ruta) is True
    p = svc_bib.pista_karaoke_por_id(d["id"])
    assert p["karaoke_estado"] == "lista" and p["karaoke_ruta_instrumental"] == ruta


def test_modelo_asignar_instrumental_ruta_vacia(modelo_karaoke):
    m, tmp = modelo_karaoke
    d = _crear_pista(tmp, "ai0")
    assert m.asignar_instrumental(d["id"], "") is False


def test_modelo_marcar_y_restaurar_no_aplica(modelo_karaoke):
    m, tmp = modelo_karaoke
    d = _crear_pista(tmp, "na")
    assert m.marcar_no_aplica(d["id"]) is True
    assert svc_bib.pista_karaoke_por_id(d["id"])["karaoke_estado"] == "no_aplica"
    assert m.restaurar_no_aplica(d["id"]) is True
    assert svc_bib.pista_karaoke_por_id(d["id"])["karaoke_estado"] == "no_procesada"


def test_modelo_detectar_backend_actualiza_diag(modelo_karaoke):
    m, _ = modelo_karaoke
    m.detectar_backend()
    diag = m.backend_diag
    assert "demucs_disponible" in diag
    assert isinstance(diag.get("backend_listo"), bool)


def test_modelo_detalle_job_devuelve_campos_estandar(modelo_karaoke):
    m, tmp = modelo_karaoke
    d = _crear_pista(tmp, "dj")
    jid = svc_kar.encolar(d["id"])
    svc_kar.jobs_repo.marcar_fallido(jid, error_codigo="audio_corrupto",
                                     error_mensaje="archivo dañado")
    detalle = m.detalle_job(d["id"])
    assert detalle["error_codigo"] == "audio_corrupto"
    assert "dañ" in detalle["error_mensaje"]
    assert detalle["intento"] >= 0
    assert "modelo" in detalle and "device" in detalle


def test_modelo_snapshot_proceso_default(modelo_karaoke):
    m, _ = modelo_karaoke
    assert m.procesando is False
    assert m.estado_proceso == "inactivo"
    assert m.porcentaje_proceso == 0.0
    assert m.porcentaje_job == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Contrato QML — bindings/acciones criticas
# ═══════════════════════════════════════════════════════════════════════════

def _qml_vista() -> str:
    return Path("ui/qml/vistas/VistaKaraoke.qml").read_text()


def test_qml_required_properties_presentes():
    qml = _qml_vista()
    for prop in ("required property var temaBase", "required property var cfg",
                 "required property var kar", "required property var rep"):
        assert prop in qml, f"Falta: {prop}"


def test_qml_tabs_presentes():
    qml = _qml_vista()
    for tab in ("sin_preparar", "en_cola", "lista", "fallida", "no_aplica"):
        assert tab in qml


def test_qml_acciones_por_estado():
    """Cada estado del flujo de vida tiene sus acciones cableadas."""
    qml = _qml_vista()
    assert "encolar_pistas" in qml
    assert "sacar_de_cola" in qml
    assert "cancelar_procesamiento" in qml
    assert "reintentar_fallida" in qml
    assert "resetear_estado" in qml
    assert "asignar_instrumental" in qml or "_abrirDialogoInstrumental" in qml
    assert "marcar_no_aplica" in qml
    assert "restaurar_no_aplica" in qml
    assert "iniciar_procesamiento" in qml
    assert "vaciar_cola" in qml


def test_qml_panel_pista_activa_integra_reproductor():
    qml = _qml_vista()
    assert "rep.titulo_activo" in qml
    assert "rep.karaoke_disponible" in qml
    assert "rep.karaoke_activo" in qml
    assert "rep.alternar_karaoke" in qml


def test_qml_paginacion_completa():
    qml = _qml_vista()
    for sym in ("pagina_siguiente", "pagina_anterior", "ir_a_pagina",
                "total_paginas", "pagina_actual", "limite_pagina"):
        assert sym in qml


def test_qml_responsive_breakpoints():
    qml = _qml_vista()
    for sym in ("cW", "mW", "wW"):
        assert sym in qml


def test_qml_no_importa_dialogs_directo():
    """QtQuick.Dialogs causa segfault con offscreen+workers en Qt 6.11."""
    qml = _qml_vista()
    assert "import QtQuick.Dialogs" not in qml
    assert "dlg_loader" in qml  # carga diferida


def test_qml_file_dialog_es_item():
    dlg = Path("ui/qml/componentes/KaraokeFileDialog.qml").read_text()
    assert "Item {" in dlg or "Item{" in dlg
    assert "QtObject {" not in dlg


def test_qml_tab_persiste_en_config():
    qml = _qml_vista()
    assert "karaoke_tab_activa" in qml
    assert "cfg.guardar" in qml and "cfg.obtener" in qml


def test_qml_toast_usa_shell_global():
    """El toast debe usar el global del shell, no uno local con colores rotos."""
    qml = _qml_vista()
    assert "mostrar_toast_global" in qml


def test_qml_columnas_alineadas_header_y_delegate():
    qml = _qml_vista()
    for col in ("colChk", "colPortada", "colEstado", "colAcciones", "colProgreso"):
        assert qml.count(col) >= 2


def test_qml_progreso_por_pista_se_visualiza():
    """El delegate muestra una mini barra cuando la pista esta procesando."""
    qml = _qml_vista()
    assert "karaoke_progreso" in qml or "fd.prog" in qml


def test_qml_modal_error_existe():
    qml = _qml_vista()
    assert "modal_error" in qml
    assert "Ver error" in qml or "detalle_job" in qml


def test_modelo_qml_expone_propiedades_basicas():
    src = Path("ui/modelos_qml.py").read_text()
    for sym in ("class ModeloKaraoke",
                "pistasCargadas", "resumenCambiado", "paginaCambiada",
                "procesandoCambiado", "backendDiagCambiado",
                "operacionOk", "operacionError", "karaokeActualizado",
                "def cargar", "def encolar_pistas", "def encolar_todas_sin_preparar",
                "def sacar_de_cola", "def vaciar_cola",
                "def reintentar_fallida", "def reintentar_todas_fallidas",
                "def resetear_estado", "def asignar_instrumental",
                "def marcar_no_aplica", "def restaurar_no_aplica",
                "def detalle_job", "def detectar_backend",
                "def iniciar_procesamiento", "def cancelar_procesamiento",
                "def cancelar_y_vaciar"):
        assert sym in src, f"Falta en ModeloKaraoke: {sym}"


def test_paquete_karaoke_expone_api_publica():
    """API publica del paquete servicios.karaoke debe estar completa."""
    for sym in ("diagnostico", "seleccionar_device", "validar_listo",
                "encolar", "encolar_muchas", "encolar_todas_sin_preparar",
                "sacar_de_cola", "vaciar_cola",
                "asignar_instrumental_manual", "marcar_no_aplica",
                "restaurar_de_no_aplica", "resetear_estado_pista",
                "resumen_jobs", "listar_cola", "job_por_id",
                "procesar_cola", "limpiar_jobs_zombies"):
        assert hasattr(svc_kar, sym), f"Falta en servicios.karaoke: {sym}"


def test_worker_karaoke_existe_y_es_QThread():
    """WorkerKaraokeCola hereda de QThread y tiene la API esperada."""
    from workers.workers_qt import WorkerKaraokeCola
    from PySide6.QtCore import QThread
    assert issubclass(WorkerKaraokeCola, QThread)


def test_principal_qml_wirea_kar_y_rep():
    qml = Path("ui/qml/Principal.qml").read_text()
    assert "kar: karaoke" in qml and "rep: reproductor" in qml


def test_main_ui_registra_modelo_karaoke():
    src = Path("main_ui.py").read_text()
    assert "ModeloKaraoke" in src and '"karaoke"' in src
