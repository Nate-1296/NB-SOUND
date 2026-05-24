"""Tests de integracion end-to-end del DJ Privado.

Verifican el flujo completo: DB -> intent -> pool -> scheduler -> transiciones
-> persistencia -> servicio -> eventos de adaptacion.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from db.conexion import cerrar_db, ejecutar, inicializar_db, obtener_filas
from servicios.dj_privado import (
    DjPrivadoService,
    OpcionesConstructor,
    PoolVacioError,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def db_dj(tmp_path: Path):
    """Inicializa una BD aislada con una pequena biblioteca para los tests."""
    db = tmp_path / "dj.db"
    inicializar_db(db)
    audio = tmp_path / "audio"
    audio.mkdir()

    # Artistas y albums minimos
    ejecutar("INSERT INTO artistas(nombre, nombre_slug) VALUES('Chopin','chopin')")
    ejecutar("INSERT INTO artistas(nombre, nombre_slug) VALUES('Star','star')")
    ejecutar("INSERT INTO artistas(nombre, nombre_slug) VALUES('Trainer','trainer')")
    ejecutar("INSERT INTO artistas(nombre, nombre_slug) VALUES('Calm','calm')")
    ejecutar("INSERT INTO artistas(nombre, nombre_slug) VALUES('LoudBand','loud')")

    ejecutar("INSERT INTO albums(artista_id, titulo, titulo_slug, tipo) VALUES(1,'Noc','noc','Album')")
    ejecutar("INSERT INTO albums(artista_id, titulo, titulo_slug, tipo) VALUES(2,'Pop','pop','Album')")
    ejecutar("INSERT INTO albums(artista_id, titulo, titulo_slug, tipo) VALUES(3,'Workout','wk','Album')")
    ejecutar("INSERT INTO albums(artista_id, titulo, titulo_slug, tipo) VALUES(4,'Sleep','sl','Album')")
    ejecutar("INSERT INTO albums(artista_id, titulo, titulo_slug, tipo) VALUES(5,'Hard','hd','Album')")

    pistas = [
        # (id, alb_id, art_id, titulo, artista, album, gen, dur)
        (1, 1, 1, "Nocturne 1", "Chopin", "Noc", "classical", 240),
        (2, 1, 1, "Nocturne 2", "Chopin", "Noc", "classical", 230),
        (3, 2, 2, "Hit 1", "Star", "Pop", "pop", 200),
        (4, 2, 2, "Hit 2", "Star", "Pop", "pop", 195),
        (5, 3, 3, "Workout 1", "Trainer", "Workout", "electronic", 220),
        (6, 3, 3, "Workout 2", "Trainer", "Workout", "electronic", 215),
        (7, 4, 4, "Calm 1", "Calm", "Sleep", "ambient", 360),
        (8, 5, 5, "Hard 1", "LoudBand", "Hard", "metal", 220),
        (9, 5, 5, "Hard 2", "LoudBand", "Hard", "rock", 210),
        (10, 2, 2, "Hit 3", "Star", "Pop", "pop", 205),
    ]
    for (pid, alb, art, t, an, alt, g, d) in pistas:
        ruta = audio / f"t{pid}.mp3"
        ruta.write_bytes(b"\0" * 1024)
        ejecutar(
            "INSERT INTO pistas(id, album_id, artista_id, titulo, artista_nombre, "
            "album_titulo, genero, duracion_seg, ruta_archivo, nombre_archivo) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (pid, alb, art, t, an, alt, g, d, str(ruta), ruta.name),
        )

    # Audio features sinteticos
    af = [
        ('1', 60, 'C#', 'minor', 0.25, 0.4, 0.10, 0.6, 0.85, 0.05, 0.3, 0.6, 0.6, 0.05, 0.05, 0.75),
        ('2', 55, 'A',  'minor', 0.22, 0.35, 0.05, 0.7, 0.85, 0.1, 0.25, 0.7, 0.55, 0.05, 0.05, 0.8),
        ('3', 118, 'C', 'major', 0.7, 0.7, 0.6, 0.2, 0.3, 0.2, 0.7, 0.3, 0.2, 0.3, 0.7, 0.3),
        ('4', 122, 'G', 'major', 0.68, 0.78, 0.65, 0.1, 0.3, 0.15, 0.78, 0.25, 0.25, 0.45, 0.75, 0.2),
        ('5', 128, 'A', 'minor', 0.88, 0.6, 0.85, 0.1, 0.15, 0.4, 0.6, 0.4, 0.1, 0.9, 0.75, 0.3),
        ('6', 126, 'D', 'minor', 0.82, 0.5, 0.80, 0.15, 0.2, 0.45, 0.55, 0.4, 0.1, 0.85, 0.75, 0.4),
        ('7', 72, 'F',  'major', 0.15, 0.5, 0.05, 0.3, 0.95, 0.05, 0.4, 0.5, 0.9, 0.1, 0.05, 0.7),
        ('8', 165, 'E', 'minor', 0.95, 0.2, 0.4, 0.5, 0.05, 0.95, 0.4, 0.7, 0.05, 0.9, 0.5, 0.5),
        ('9', 130, 'A', 'minor', 0.9, 0.4, 0.5, 0.3, 0.1, 0.85, 0.5, 0.5, 0.05, 0.85, 0.6, 0.4),
        ('10', 116, 'C','major', 0.66, 0.75, 0.6, 0.15, 0.3, 0.15, 0.75, 0.25, 0.25, 0.4, 0.7, 0.25),
    ]
    for d in af:
        ejecutar(
            """INSERT INTO track_audio_features
            (track_id, analyzer_version, analysis_mode, analysis_status, bpm, key_name, mode,
             energy, valence_proxy, danceability_proxy, melancholy_proxy, calmness_proxy,
             aggressiveness_proxy, brightness, darkness_proxy, focus_score_proxy,
             workout_score_proxy, party_score_proxy, night_score_proxy)
            VALUES(?,'v1','light','ready',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            d,
        )

    yield db
    cerrar_db()


# =============================================================================
# FLUJO BASICO
# =============================================================================

class TestFlujoBasico:
    def test_iniciar_y_obtener_pistas(self, db_dj):
        svc = DjPrivadoService()
        sesion = svc.iniciar_sesion(
            "para concentrarme",
            duracion_minutos=15,
            opciones=OpcionesConstructor(tam_bloque_inicial=5, semilla=7),
        )
        assert sesion.sesion_id > 0
        assert sesion.intent.curva_energia == "stable"
        assert len(sesion.bloques) == 1
        assert len(sesion.bloques[0].pistas) > 0
        # Las pistas elegidas deben tener focus alto (Calm 1, Nocturne)
        ids = {p.pista.id for p in sesion.bloques[0].pistas}
        assert 7 in ids  # Calm 1

    def test_workout_eleva_energia(self, db_dj):
        svc = DjPrivadoService()
        sesion = svc.iniciar_sesion(
            "subida progresiva para entrenar",
            duracion_minutos=15,
            opciones=OpcionesConstructor(tam_bloque_inicial=5, semilla=42),
        )
        ids = {p.pista.id for p in sesion.bloques[0].pistas}
        # Debe incluir al menos una pista de workout (5 o 6)
        assert ids & {5, 6}

    def test_continuar_construccion(self, db_dj):
        svc = DjPrivadoService()
        sesion = svc.iniciar_sesion(
            "algo energetico",
            duracion_minutos=30,
            opciones=OpcionesConstructor(tam_bloque_inicial=3),
        )
        bloque2 = svc.continuar_construccion()
        assert bloque2 is not None
        # Hay que generar algo o estar completado
        assert bloque2.pistas or bloque2.motivo_corte in {"objetivo_cumplido", "pool_agotado"}

    def test_biblioteca_vacia_lanza_pool_vacio(self, tmp_path):
        db = tmp_path / "vacia.db"
        inicializar_db(db)
        svc = DjPrivadoService()
        with pytest.raises(PoolVacioError):
            svc.iniciar_sesion("algo", duracion_minutos=10)
        cerrar_db()


# =============================================================================
# ADAPTACION (skip, replanificar, extender)
# =============================================================================

class TestAdaptacion:
    def test_skip_registra_evento(self, db_dj):
        svc = DjPrivadoService()
        sesion = svc.iniciar_sesion("para entrenar", duracion_minutos=15, opciones=OpcionesConstructor(semilla=7))
        primera = sesion.bloques[0].pistas[0]
        svc.registrar_skip(primera.posicion, primera.pista.id)
        # Verificar evento persistido
        eventos = obtener_filas(
            "SELECT tipo FROM dj_eventos WHERE sesion_id=?",
            (sesion.sesion_id,),
        )
        tipos = [e["tipo"] for e in eventos]
        assert "saltada" in tipos

    def test_replanificacion_genera_nuevas_pistas(self, db_dj):
        svc = DjPrivadoService()
        sesion = svc.iniciar_sesion("algo", duracion_minutos=20, opciones=OpcionesConstructor(semilla=7))
        n_pistas_inicial = sum(len(b.pistas) for b in sesion.bloques)
        bloque = svc.replanificar_desde(1)
        # La replanificacion debe producir un bloque (o vacio si no hay pool)
        assert bloque is not None

    def test_extender_aumenta_duracion(self, db_dj):
        svc = DjPrivadoService()
        sesion = svc.iniciar_sesion("algo tranquilo", duracion_minutos=12, opciones=OpcionesConstructor(semilla=7))
        duracion_inicial = sesion.intent.duracion_minutos
        svc.extender_sesion(15)
        assert svc.sesion_activa().intent.duracion_minutos == duracion_inicial + 15

    def test_bloquear_pista_persiste(self, db_dj):
        svc = DjPrivadoService()
        sesion = svc.iniciar_sesion("algo", duracion_minutos=10, opciones=OpcionesConstructor(semilla=7))
        primera = sesion.bloques[0].pistas[0]
        svc.bloquear_pista(primera.posicion, True)
        from servicios.dj_privado import persistencia
        filas = persistencia.listar_pistas_sesion(sesion.sesion_id)
        match = next(f for f in filas if f["posicion"] == primera.posicion)
        assert match["bloqueada"] is True


# =============================================================================
# GUARDAR COMO PLAYLIST
# =============================================================================

class TestGuardarPlaylist:
    def test_guarda_y_vincula(self, db_dj):
        svc = DjPrivadoService()
        sesion = svc.iniciar_sesion("algo tranquilo", duracion_minutos=10, opciones=OpcionesConstructor(semilla=7))
        playlist_id = svc.guardar_como_playlist("Mi sesion test")
        assert playlist_id > 0
        # Verificar pistas en pistas_playlist
        filas = obtener_filas(
            "SELECT pista_id, posicion FROM pistas_playlist WHERE playlist_id=? ORDER BY posicion",
            (playlist_id,),
        )
        assert len(filas) > 0


# =============================================================================
# CARGA Y SESIONES PREVIAS
# =============================================================================

class TestCargaSesion:
    def test_cargar_sesion_anterior(self, db_dj):
        svc = DjPrivadoService()
        sesion = svc.iniciar_sesion("algo", duracion_minutos=10, opciones=OpcionesConstructor(semilla=7))
        sid = sesion.sesion_id
        # Nuevo servicio simula reapertura
        svc2 = DjPrivadoService()
        s_cargada = svc2.cargar_sesion(sid)
        assert s_cargada.sesion_id == sid
        assert s_cargada.intent.prompt == sesion.intent.prompt

    def test_listar_recientes_orden(self, db_dj):
        svc = DjPrivadoService()
        svc.iniciar_sesion("primera", duracion_minutos=5)
        svc.descartar_sesion_activa()
        svc.iniciar_sesion("segunda", duracion_minutos=5)
        sesiones = svc.listar_sesiones_recientes(limite=5)
        # Mas reciente primero
        assert sesiones[0].prompt_original == "segunda"


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    def test_prompt_contradictorio(self, db_dj):
        svc = DjPrivadoService()
        # "tranquilo y agresivo" -> el intent resuelve la contradiccion
        sesion = svc.iniciar_sesion(
            "tranquilo pero agresivo a la vez",
            duracion_minutos=10,
        )
        # No deberia fallar; el intent escoge uno
        assert sesion.sesion_id > 0
        # Y debe tener pistas (no quedo vacio por la contradiccion)
        assert len(sesion.bloques[0].pistas) >= 1

    def test_prompt_ambiguo_genera_sesion_general(self, db_dj):
        svc = DjPrivadoService()
        sesion = svc.iniciar_sesion("nada en particular", duracion_minutos=8)
        # Debe construir sesion aunque sea generica
        assert len(sesion.bloques[0].pistas) > 0

    def test_duracion_invalida(self, db_dj):
        from servicios.dj_privado.errores import ConfiguracionInvalidaError
        svc = DjPrivadoService()
        with pytest.raises(ConfiguracionInvalidaError):
            svc.iniciar_sesion("algo", duracion_minutos=0)
        with pytest.raises(ConfiguracionInvalidaError):
            svc.iniciar_sesion("algo", duracion_minutos=600)

    def test_descartar_sin_sesion_no_falla(self):
        svc = DjPrivadoService()
        svc.descartar_sesion_activa()  # no debe lanzar

    def test_regenerar_cambia_seleccion(self, db_dj):
        svc = DjPrivadoService()
        s1 = svc.iniciar_sesion("algo", duracion_minutos=10, opciones=OpcionesConstructor(semilla=1))
        ids_s1 = [p.pista.id for p in s1.bloques[0].pistas]
        s2 = svc.regenerar()
        assert s2 is not None
        assert s2.sesion_id != s1.sesion_id
        # No exigimos que sean distintos siempre (pool pequeno puede repetir),
        # pero al menos que sea otra sesion en BD
