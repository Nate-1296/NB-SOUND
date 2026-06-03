"""Tests para el ModeloExploradorCiego y el modo ciego del ModeloReproductor.

Validan la capa de integracion QObject:
  - Apertura/cierre del juego desde el modelo.
  - Censura "???" en titulo/artista/album mientras el id ciego coincide.
  - Limpieza del modo ciego al revelar/cerrar/cambiar de pista.
  - Manejo de modos invalidos sin romper estado.

NOTA: Los tests crean instancias minimas usando un Reproductor en modo
simulado (sin VLC). Eso aisla la logica de presentacion del backend.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from db.conexion import cerrar_db, get_conexion, inicializar_db
from servicios.reproductor import Reproductor
from ui.modelos_qml import ModeloExploradorCiego, ModeloReproductor


@pytest.fixture(scope="session")
def qt_app():
    """Una sola QApplication por sesion de tests."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def _crear_pista(tmp_path: Path, nombre: str, *, duracion: float = 180.0) -> int:
    ruta = tmp_path / f"{nombre}.mp3"
    ruta.write_bytes(b"audio")
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
            ruta_archivo, nombre_archivo, tamano_bytes, duracion_seg, estado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'biblioteca')
        """,
        (
            album_id, artista_id, f"Pista {nombre}",
            f"Artista {nombre}", f"Album {nombre}",
            str(ruta), ruta.name, ruta.stat().st_size, duracion,
        ),
    ).lastrowid
    return pista_id


@pytest.fixture()
def db_juego(tmp_path, qt_app):
    inicializar_db(tmp_path / "explorador_modelo.db")
    try:
        yield tmp_path
    finally:
        cerrar_db()


@pytest.fixture()
def modelos(qt_app, db_juego):
    """Construye los dos modelos minimos necesarios para los tests."""
    rep = Reproductor(permitir_modo_simulado=True)
    mr = ModeloReproductor(rep)
    me = ModeloExploradorCiego(mr)
    yield mr, me, rep


# ─── Disponibilidad ──────────────────────────────────────────────────────────

def test_modelo_arranca_sin_biblioteca(qt_app, db_juego):
    rep = Reproductor(permitir_modo_simulado=True)
    mr = ModeloReproductor(rep)
    me = ModeloExploradorCiego(mr)
    me._recargar_disponibilidad()
    assert me.hay_biblioteca is False
    assert me.total_biblioteca == 0


def test_modelo_calcula_disponibles_por_modo(modelos, db_juego, tmp_path):
    _, me, _ = modelos
    _crear_pista(tmp_path, "uno")
    _crear_pista(tmp_path, "dos")
    me._recargar_disponibilidad()
    d = dict(me.disponibles_por_modo)
    assert d.get("audio") == 2
    assert me.hay_biblioteca is True


# ─── Iniciar ronda ───────────────────────────────────────────────────────────

def test_iniciar_ronda_modo_invalido_emite_error(modelos, db_juego, tmp_path):
    _, me, _ = modelos
    _crear_pista(tmp_path, "uno")
    me._recargar_disponibilidad()
    errores = []
    me.error.connect(lambda msg: errores.append(msg))
    ok = me.iniciar_ronda("inexistente", 3)
    assert ok is False
    assert errores  # llego al menos un error


def test_iniciar_ronda_sin_biblioteca_falla(modelos, db_juego):
    _, me, _ = modelos
    me._recargar_disponibilidad()
    errores = []
    me.error.connect(lambda msg: errores.append(msg))
    ok = me.iniciar_ronda("audio", 3)
    assert ok is False
    assert errores


def test_iniciar_ronda_publica_reto(modelos, db_juego, tmp_path):
    _, me, _ = modelos
    _crear_pista(tmp_path, "uno")
    _crear_pista(tmp_path, "dos")
    me._recargar_disponibilidad()
    assert me.iniciar_ronda("audio", 2) is True
    assert me.ronda_activa is True
    assert me.total_retos == 2
    reto = me.reto
    assert reto["titulo"] == "???"
    assert reto["artista"] == "???"
    assert reto["album"] == "???"


# ─── Revelacion ──────────────────────────────────────────────────────────────

def test_revelar_artista_actualiza_reto_visible(modelos, db_juego, tmp_path):
    _, me, _ = modelos
    _crear_pista(tmp_path, "p")
    me._recargar_disponibilidad()
    me.iniciar_ronda("audio", 1)
    me.revelar_artista()
    reto = me.reto
    assert reto["artista"] != "???"
    assert reto["titulo"] == "???"
    assert reto["album"] == "???"


def test_revelar_todo_limpia_modo_ciego_del_reproductor(modelos, db_juego, tmp_path):
    mr, me, _ = modelos
    _crear_pista(tmp_path, "p")
    me._recargar_disponibilidad()
    me.iniciar_ronda("audio", 1)
    # Simular que activamos modo ciego manualmente (el flujo real lo hace
    # reproducir_fragmento, pero aqui aislamos sin tocar VLC).
    mr.set_modo_ciego(me.reto.get("pista_id"))
    assert mr.blind_pista_id == me.reto.get("pista_id")
    me.revelar_todo()
    assert mr.blind_pista_id == 0


# ─── Modo ciego del ModeloReproductor ────────────────────────────────────────

def test_modo_ciego_censura_pista_activa(modelos, db_juego, tmp_path, qt_app):
    mr, me, rep = modelos
    pid = _crear_pista(tmp_path, "x")
    # Reproducir pista (modo simulado: VLC inexistente).
    pista = {
        "id": pid, "titulo": "Pista x", "artista_nombre": "Artista x",
        "album_titulo": "Album x", "ruta_archivo": str(tmp_path / "x.mp3"),
        "duracion_seg": 180,
    }
    rep.reproducir_pista(pista)
    # Pista activa con metadatos visibles.
    assert mr.titulo_activo == "Pista x"
    assert mr.artista_activo == "Artista x"
    assert mr.album_activo == "Album x"
    # Activar modo ciego.
    mr.set_modo_ciego(pid)
    assert mr.titulo_activo == "???"
    assert mr.artista_activo == "???"
    assert mr.album_activo == "???"
    # Limpiar.
    mr.limpiar_modo_ciego()
    assert mr.titulo_activo == "Pista x"


def test_modo_ciego_no_afecta_otras_pistas(modelos, db_juego, tmp_path):
    mr, me, rep = modelos
    p1 = _crear_pista(tmp_path, "uno")
    p2 = _crear_pista(tmp_path, "dos")
    pista2 = {
        "id": p2, "titulo": "Pista dos", "artista_nombre": "Artista dos",
        "album_titulo": "Album dos", "ruta_archivo": str(tmp_path / "dos.mp3"),
        "duracion_seg": 180,
    }
    rep.reproducir_pista(pista2)
    # Activamos modo ciego para p1 (no es la pista activa).
    mr.set_modo_ciego(p1)
    # Como la activa es p2, NO debe censurarse.
    assert mr.titulo_activo == "Pista dos"
    assert mr.artista_activo == "Artista dos"


def test_modo_ciego_idempotente(modelos, db_juego, tmp_path):
    mr, me, _ = modelos
    senal_count = []
    mr.modoCiegoCambiado.connect(lambda: senal_count.append(1))
    mr.set_modo_ciego(123)
    primer_count = len(senal_count)
    mr.set_modo_ciego(123)  # mismo id: no debe re-emitir
    assert len(senal_count) == primer_count
    mr.set_modo_ciego(456)  # id diferente: si emite
    assert len(senal_count) == primer_count + 1


# ─── Navegacion de ronda ─────────────────────────────────────────────────────

def test_siguiente_reto_termina_ronda(modelos, db_juego, tmp_path, qt_app):
    _, me, _ = modelos
    _crear_pista(tmp_path, "p")
    me._recargar_disponibilidad()
    me.iniciar_ronda("audio", 1)
    eventos = []
    me.rondaTerminada.connect(lambda payload: eventos.append(payload))
    me.marcar_acertada()
    me.siguiente_reto()
    # rondaTerminada se emite sincronamente.
    assert len(eventos) == 1
    assert eventos[0]["total"] == 1
    assert eventos[0]["acertados"] == 1
    assert me.ronda_activa is False


def test_terminar_ronda_explicito(modelos, db_juego, tmp_path):
    _, me, _ = modelos
    _crear_pista(tmp_path, "a")
    _crear_pista(tmp_path, "b")
    me._recargar_disponibilidad()
    me.iniciar_ronda("audio", 2)
    eventos = []
    me.rondaTerminada.connect(lambda p: eventos.append(p))
    me.terminar_ronda()
    assert len(eventos) == 1
    # Las pistas no resueltas cuentan como pasadas.
    assert eventos[0]["total"] == 2


# ─── Alternar favorita ───────────────────────────────────────────────────────

def test_alternar_favorita_actualiza_reto(modelos, db_juego, tmp_path):
    _, me, _ = modelos
    pid = _crear_pista(tmp_path, "fav")
    me._recargar_disponibilidad()
    me.iniciar_ronda("audio", 1)
    asumido = me.reto.get("favorita")
    es_fav_ahora = me.alternar_favorita(pid)
    assert es_fav_ahora != asumido
    # El reto visible se actualizo.
    assert bool(me.reto.get("favorita")) == bool(es_fav_ahora)


# ─── Modo ciego censura tambien portada en pista activa ──────────────────

def test_modo_ciego_censura_portada(modelos, db_juego, tmp_path):
    mr, _me, rep = modelos
    pid = _crear_pista(tmp_path, "pista_portada")
    pista = {
        "id": pid, "titulo": "Pista pista_portada",
        "artista_nombre": "Artista pista_portada",
        "album_titulo": "Album pista_portada",
        "ruta_archivo": str(tmp_path / "pista_portada.mp3"),
        "duracion_seg": 180,
        "portada_ruta": "/tmp/no_existe_pero_da_igual_para_test.jpg",
    }
    rep.reproducir_pista(pista)
    # Sin modo ciego: portada visible (no vacia).
    snap = mr.pista_activa
    assert snap.get("portada_ruta")
    # Activar modo ciego: la portada queda vacia.
    mr.set_modo_ciego(pid)
    snap_ciego = mr.pista_activa
    assert snap_ciego.get("portada_ruta") == ""
    assert snap_ciego.get("portada_hd_ruta") == ""
    # Quitar: vuelve.
    mr.limpiar_modo_ciego()
    assert mr.pista_activa.get("portada_ruta")


# ─── Adivinar por escritura desde el modelo ──────────────────────────────

def test_intentar_adivinar_desde_modelo_acierto(modelos, db_juego, tmp_path):
    _, me, _ = modelos
    _crear_pista(tmp_path, "guess")
    me._recargar_disponibilidad()
    me.iniciar_ronda("audio", 1)
    titulo = me.reto.get("titulo") if me.reto.get("nivel") == "total" else None
    # Cuando el reto esta oculto, el modelo SI ve el titulo censurado;
    # accedemos al servicio para confirmar el real.
    real = me._servicio.reto_actual().pista.get("titulo")
    r = me.intentar_adivinar(real)
    assert r["acierto"] is True
    assert me.reto.get("nivel") == "total"
    assert me.reto.get("estado") == "acertado"


def test_intentar_adivinar_desde_modelo_fallo_publica_intentos(modelos, db_juego, tmp_path):
    _, me, _ = modelos
    _crear_pista(tmp_path, "guess")
    me._recargar_disponibilidad()
    me.iniciar_ronda("audio", 1)
    me.intentar_adivinar("respuesta totalmente incorrecta xyz abc 999")
    assert int(me.reto.get("intentos_fallidos") or 0) >= 1


# ─── Revelar hint desde el modelo ────────────────────────────────────────

def test_revelar_hint_desde_modelo_actualiza_vista(modelos, db_juego, tmp_path):
    _, me, _ = modelos
    _crear_pista(tmp_path, "hintme")
    me._recargar_disponibilidad()
    me.iniciar_ronda("audio", 1)
    me.revelar_hint("empieza_con")
    vis = me.reto.get("hints_visibles") or {}
    assert "empieza_con" in vis


# ─── Bloqueo del reproductor cuando hay pista ciega ─────────────────────

def test_bloqueo_pausar_reanudar_con_pista_ciega(modelos, db_juego, tmp_path):
    """pausar_reanudar publico debe ser no-op cuando la pista activa
    coincide con blind_pista_id (modo juego activo)."""
    mr, _me, rep = modelos
    pid = _crear_pista(tmp_path, "lock")
    pista = {
        "id": pid, "titulo": "Pista lock",
        "artista_nombre": "Artista lock", "album_titulo": "Album lock",
        "ruta_archivo": str(tmp_path / "lock.mp3"), "duracion_seg": 180,
    }
    rep.reproducir_pista(pista)
    estado_inicial = mr.estado
    mr.set_modo_ciego(pid)
    mr.pausar_reanudar()  # bloqueado: no debe alterar estado
    assert mr.estado == estado_inicial
    # Liberar bloqueo: ahora si debe responder.
    mr.limpiar_modo_ciego()
    mr.pausar_reanudar()
    assert mr.estado != estado_inicial


def test_bloqueo_siguiente_anterior_con_pista_ciega(modelos, db_juego, tmp_path):
    mr, _me, rep = modelos
    pid = _crear_pista(tmp_path, "lock2")
    pista = {
        "id": pid, "titulo": "Pista lock2",
        "artista_nombre": "Artista lock2", "album_titulo": "Album lock2",
        "ruta_archivo": str(tmp_path / "lock2.mp3"), "duracion_seg": 180,
    }
    rep.reproducir_pista(pista)
    mr.set_modo_ciego(pid)
    # `siguiente()` y `anterior()` deben silenciar sin tocar el reproductor.
    # No podemos comprobar mucho mas sin VLC real; basta con que no excepcione.
    mr.siguiente()
    mr.anterior()


def test_bypass_pausar_reanudar_forzado(modelos, db_juego, tmp_path):
    """El metodo no expuesto (no es Slot) debe funcionar pese al bloqueo:
    el ModeloExploradorCiego lo usa internamente para reanudar tras el
    fragmento."""
    mr, _me, rep = modelos
    pid = _crear_pista(tmp_path, "bypass")
    pista = {
        "id": pid, "titulo": "Pista bypass",
        "artista_nombre": "Artista bypass", "album_titulo": "Album bypass",
        "ruta_archivo": str(tmp_path / "bypass.mp3"), "duracion_seg": 180,
    }
    rep.reproducir_pista(pista)
    mr.set_modo_ciego(pid)
    estado_antes = mr.estado
    # Pausar y reanudar via bypass: cambia el estado.
    mr.pausar_reanudar_forzado(False)
    assert mr.estado != estado_antes
    mr.pausar_reanudar_forzado(True)
    assert mr.estado == estado_antes


# ─── revelar_titulo sin marcar pasado ───────────────────────────────────

def test_revelar_titulo_no_marca_pasado(modelos, db_juego, tmp_path):
    """revelar_titulo deja estado REVELADO (no PASADO). Asi se diferencia
    de 'Me rindo' que si marca pasado."""
    _, me, _ = modelos
    _crear_pista(tmp_path, "reveal")
    me._recargar_disponibilidad()
    me.iniciar_ronda("audio", 1)
    me.revelar_titulo()
    assert me.reto.get("estado") == "revelado"
    assert me.reto.get("nivel") == "total"


def test_rendirse_combinado_marca_pasado(modelos, db_juego, tmp_path):
    """Marcar pasado ANTES de revelar deja el reto con estado PASADO.
    Este es el flujo correcto del boton 'Me rindo' en la vista."""
    _, me, _ = modelos
    _crear_pista(tmp_path, "rendirse")
    me._recargar_disponibilidad()
    me.iniciar_ronda("audio", 1)
    # Orden importante: pasado primero, luego revelar.
    me.marcar_pasado()
    me.revelar_titulo()
    assert me.reto.get("estado") == "pasado"
    assert me.reto.get("nivel") == "total"


# ─── Reproducir completa NO revela ──────────────────────────────────────

def test_reproducir_completa_no_revela_titulo(modelos, db_juego, tmp_path):
    """El boton 'Reproducir completa' solo reanuda audio; no muestra el
    titulo. Antes habia un acoplamiento que revelaba automaticamente,
    rompiendo el juego cuando el usuario solo queria oirla entera."""
    _, me, _ = modelos
    _crear_pista(tmp_path, "completa")
    me._recargar_disponibilidad()
    me.iniciar_ronda("audio", 1)
    me.reproducir_completa()
    # El nivel sigue oculto (o lo que sea distinto a total).
    assert me.reto.get("nivel") != "total"
    assert me.reto.get("titulo") == "???"


# ─── Cola censurada y limpieza al saltar ─────────────────────────────────

def test_cola_censurada_con_pista_ciega(modelos, db_juego, tmp_path):
    """La cola debe reportar la pista ciega con campos "???" para no
    spoilear en el panel de cola."""
    mr, _me, rep = modelos
    pid = _crear_pista(tmp_path, "ciegacola")
    pista = {
        "id": pid, "titulo": "Pista ciegacola",
        "artista_nombre": "Artista ciegacola",
        "album_titulo": "Album ciegacola",
        "ruta_archivo": str(tmp_path / "ciegacola.mp3"), "duracion_seg": 180,
        "portada_ruta": "/tmp/falsa.jpg",
    }
    rep.reproducir_pista(pista)
    mr.set_modo_ciego(pid)
    item_cola = mr.cola.obtener(0)
    assert item_cola.get("titulo") == "???"
    assert item_cola.get("artista_nombre") == "???"
    assert item_cola.get("album_titulo") == "???"
    assert item_cola.get("portada_ruta") == ""
    # Al limpiar el ciego, la cola vuelve a su forma normal.
    mr.limpiar_modo_ciego()
    item_cola2 = mr.cola.obtener(0)
    assert item_cola2.get("titulo") == "Pista ciegacola"


def test_saltar_cancion_limpia_pista_activa_y_cola(modelos, db_juego, tmp_path):
    """siguiente_reto debe dejar la barra inferior y la cola en blanco
    para evitar mostrar metadatos de la pista anterior cuando se libera
    el modo ciego."""
    mr, me, _ = modelos
    _crear_pista(tmp_path, "skip_a")
    _crear_pista(tmp_path, "skip_b")
    me._recargar_disponibilidad()
    me.iniciar_ronda("audio", 2)
    me.reproducir_fragmento()
    # Sanity: hay cola.
    assert mr.cola.total >= 1
    me.siguiente_reto()
    # La cola y la pista activa deben quedar vacias hasta nuevo play.
    assert mr.cola.total == 0
    assert mr.pista_activa.get("id", 0) == 0


# ─── Fragmento sin censura cuando reto finalizado ───────────────────────

def test_fragmento_no_censura_si_ya_acerto(modelos, db_juego, tmp_path):
    """Si el reto ya esta acertado/revelado, pulsar play del fragmento no
    debe reactivar el modo ciego: el usuario ya conoce la respuesta."""
    mr, me, _ = modelos
    _crear_pista(tmp_path, "ya_acerto")
    me._recargar_disponibilidad()
    me.iniciar_ronda("audio", 1)
    real = me._servicio.reto_actual().pista.get("titulo")
    me.intentar_adivinar(real)  # acertar -> nivel TOTAL
    assert me.reto.get("nivel") == "total"
    assert mr.blind_pista_id == 0
    me.reproducir_fragmento()
    # Tras reproducir el fragmento del reto ya finalizado, NO debe
    # reactivarse el modo ciego.
    assert mr.blind_pista_id == 0


def test_reproducir_completa_sin_toast_de_adivinar_si_finalizado(modelos, db_juego, tmp_path):
    """Cuando el reto ya esta acertado, el toast no debe sugerir adivinar."""
    _, me, _ = modelos
    _crear_pista(tmp_path, "completa_ya")
    me._recargar_disponibilidad()
    me.iniciar_ronda("audio", 1)
    real = me._servicio.reto_actual().pista.get("titulo")
    me.intentar_adivinar(real)
    mensajes = []
    me.mensajeUi.connect(lambda msg, tono: mensajes.append(msg))
    me.reproducir_completa()
    # Buscamos el toast emitido al reproducir completa.
    assert any("Reproduciendo completa" in m for m in mensajes)
    # No debe contener la frase de adivinanza cuando ya esta resuelto.
    assert not any("Adivina antes" in m for m in mensajes)
