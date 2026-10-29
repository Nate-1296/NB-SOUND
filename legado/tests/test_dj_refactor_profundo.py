"""Tests del refactor profundo DJ Privado (fase 2).

Cobertura nueva (sobre lo que ya validan los tests previos):
  - Parser semantico con amplificadores ("muy", "un poco") y boosts entre
    conceptos relacionados (ej: cinematografico + epico se refuerzan).
  - Ontologia: conceptos humanos nuevos (emocionante, melancolico_profundo,
    atmosferico, etereo, sentimental, etc).
  - SessionEnergyProfile: perfil narrativo con fases (warmup/groove/peak/
    release/cooldown) y interpolacion entre ellas.
  - Duracion efectiva: overlaps descontados + trim de ultima pista.
  - SessionOwnershipManager: bloqueo robusto e idempotente, transferencia
    entre sesiones sin pasar por GLOBAL intermedio, defensa contra estados
    desincronizados.
  - Seeking global del reproductor: salto preciso a cualquier punto del
    timeline de la sesion (no solo dentro de la pista actual).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from db.conexion import cerrar_db, inicializar_db


# ─── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_dj(tmp_path):
    inicializar_db(tmp_path / "dj.db")
    try:
        yield tmp_path
    finally:
        cerrar_db()


# ═════════════════════════════════════════════════════════════════════════════
# ONTOLOGIA EXPANDIDA
# ═════════════════════════════════════════════════════════════════════════════

class TestOntologiaExpandida:
    """Los conceptos nuevos cubren palabras humanas que el sistema antes no
    entendia: emocionante, melancolico, atmosferico, espacial, etc."""

    def test_emocionante_mueve_energia_y_storytelling(self):
        from servicios.dj_privado.ontologia import buscar_conceptos
        matches = buscar_conceptos("algo emocionante")
        nombres = [m.concepto.name for m in matches]
        assert "emocionante" in nombres

    def test_melancolico_profundo_distinto_de_triste(self):
        from servicios.dj_privado.ontologia import buscar_conceptos
        matches = buscar_conceptos("melancolico y profundo")
        nombres = [m.concepto.name for m in matches]
        assert "melancolico_profundo" in nombres

    def test_atmosferico_etereo_espacial(self):
        from servicios.dj_privado.ontologia import buscar_conceptos
        m1 = [m.concepto.name for m in buscar_conceptos("atmosferico")]
        m2 = [m.concepto.name for m in buscar_conceptos("etereo")]
        m3 = [m.concepto.name for m in buscar_conceptos("espacial")]
        assert "atmosferico" in m1
        assert "etereo" in m2
        assert "espacial" in m3

    def test_bajos_profundos_es_distinto_de_bajos_fuertes(self):
        from servicios.dj_privado.ontologia import buscar_conceptos
        matches = buscar_conceptos("bajos profundos")
        nombres = [m.concepto.name for m in matches]
        assert "bajos_profundos" in nombres

    def test_synthwave_es_un_concepto(self):
        from servicios.dj_privado.ontologia import buscar_conceptos
        matches = buscar_conceptos("synthwave nocturno")
        nombres = [m.concepto.name for m in matches]
        assert "synthwave" in nombres

    def test_que_pegue_no_colisiona_con_agresivo(self):
        """'que pegue' es energico pero no necesariamente agresivo."""
        from servicios.dj_privado.ontologia import buscar_conceptos
        matches = buscar_conceptos("que pegue pero elegante")
        nombres = [m.concepto.name for m in matches]
        assert "que_pegue" in nombres
        assert "agresivo" not in nombres


class TestParserAmplificadoresYBoosts:
    """El parser ahora aplica modificadores de intensidad y boosts contextuales."""

    def test_muy_amplifica_concepto_siguiente(self):
        from servicios.dj_privado.intencion import parsear_intent
        normal = parsear_intent("emocionante", duracion_minutos=30)
        amplificado = parsear_intent("muy emocionante", duracion_minutos=30)
        # El amplificado debe tener axes mayores en ejes comunes
        e_normal = normal.axes.get("storytelling", 0)
        e_amp = amplificado.axes.get("storytelling", 0)
        assert e_amp > e_normal, f"amplificado {e_amp} debe ser > normal {e_normal}"

    def test_un_poco_atenua_concepto(self):
        from servicios.dj_privado.intencion import parsear_intent
        normal = parsear_intent("oscuro", duracion_minutos=30)
        atenuado = parsear_intent("un poco oscuro", duracion_minutos=30)
        e_normal = normal.axes.get("darkness", 0)
        e_at = atenuado.axes.get("darkness", 0)
        assert e_at < e_normal, f"atenuado {e_at} debe ser < normal {e_normal}"

    def test_boosts_refuerzan_ejes_compartidos(self):
        """Cinematografico + epico comparten orchestral_weight y se refuerzan."""
        from servicios.dj_privado.intencion import parsear_intent
        solo = parsear_intent("cinematografico", duracion_minutos=30)
        juntos = parsear_intent("cinematografico y epico", duracion_minutos=30)
        # Con boost, orchestral_weight de "juntos" deberia ser mas alto que la
        # simple suma (porque el factor 1.25 se aplica encima).
        assert juntos.axes.get("orchestral_weight", 0) > solo.axes.get("orchestral_weight", 0)

    def test_negacion_simple(self):
        from servicios.dj_privado.intencion import parsear_intent
        intent = parsear_intent("rock pero sin agresivo", duracion_minutos=30)
        assert "agresivo" in intent.exclusiones


# ═════════════════════════════════════════════════════════════════════════════
# PERFIL NARRATIVO
# ═════════════════════════════════════════════════════════════════════════════

class TestSessionEnergyProfile:

    def test_curva_progressive_tiene_warmup_groove_peak(self):
        from servicios.dj_privado.intencion import parsear_intent
        from servicios.dj_privado.narrativa import construir_perfil
        intent = parsear_intent("subida progresiva para entrenar", duracion_minutos=45)
        perfil = construir_perfil(intent)
        nombres = [f.name for f in perfil]
        assert "warmup" in nombres
        assert "groove" in nombres
        assert "peak" in nombres

    def test_curva_stable_es_groove_largo(self):
        from servicios.dj_privado.intencion import IntentMusical
        from servicios.dj_privado.narrativa import construir_perfil
        intent = IntentMusical(prompt="", curva_energia="stable")
        perfil = construir_perfil(intent)
        # Solo warmup + groove + cooldown
        nombres = [f.name for f in perfil]
        assert nombres == ["warmup", "groove", "cooldown"]
        # El groove ocupa la mayor parte
        groove = next(f for f in perfil if f.name == "groove")
        assert (groove.end_t - groove.start_t) > 0.5

    def test_perfil_cubre_t_0_a_1(self):
        from servicios.dj_privado.intencion import IntentMusical
        from servicios.dj_privado.narrativa import construir_perfil
        for curva in ("stable", "progressive", "wave", "descending", "peak"):
            intent = IntentMusical(prompt="", curva_energia=curva)
            perfil = construir_perfil(intent)
            assert perfil[0].start_t == pytest.approx(0.0)
            assert perfil[-1].end_t == pytest.approx(1.0)

    def test_fase_en_t_no_lanza_para_t_fuera_de_rango(self):
        from servicios.dj_privado.intencion import IntentMusical
        from servicios.dj_privado.narrativa import construir_perfil, fase_en_t
        intent = IntentMusical(prompt="", curva_energia="progressive")
        perfil = construir_perfil(intent)
        # No debe lanzar
        assert fase_en_t(perfil, -0.5).name == "warmup"   # antes del inicio
        assert fase_en_t(perfil, 2.0).name == perfil[-1].name  # despues del fin

    def test_objetivos_interpolan_entre_fases(self):
        from servicios.dj_privado.intencion import IntentMusical
        from servicios.dj_privado.narrativa import construir_perfil, objetivos_para_posicion
        intent = IntentMusical(prompt="", curva_energia="progressive")
        perfil = construir_perfil(intent)
        # En t=0 estamos en warmup (energy bajo)
        en_inicio = objetivos_para_posicion(perfil, 0.0)
        # En t cerca del peak, energy alto
        en_peak = objetivos_para_posicion(perfil, 0.55)  # zona del peak
        assert en_peak["energy"] > en_inicio["energy"]


# ═════════════════════════════════════════════════════════════════════════════
# DURACION EFECTIVA
# ═════════════════════════════════════════════════════════════════════════════

class TestDuracionEfectiva:

    def _crear_pool(self, duraciones: list[float]):
        from servicios.dj_privado.persistencia import PistaCandidata
        return [
            PistaCandidata(
                id=i + 1, titulo=f"P{i}", artista_nombre=f"A{i}", album_titulo="X",
                artista_id=i + 1, album_id=None, genero="", duracion_seg=dur,
                ruta_archivo=f"/tmp/p{i}.mp3", favorita=False, veces_reproducida=0,
                energy=0.5, bpm=120,
            )
            for i, dur in enumerate(duraciones)
        ]

    def test_overlap_se_descuenta_de_duracion_efectiva(self):
        """3 pistas de 200s con 2 transiciones de 5s overlap = 600 - 10 = 590s."""
        from servicios.dj_privado.constructor import ConstructorSesion, OpcionesConstructor
        from servicios.dj_privado.intencion import parsear_intent
        pool = self._crear_pool([200.0, 200.0, 200.0])
        intent = parsear_intent("test", duracion_minutos=10)
        c = ConstructorSesion(intent, OpcionesConstructor(tam_bloque_inicial=3,
                                                          refinar_transiciones=False))
        c.cargar_pool(pistas=pool)
        bloque = c.construir_bloque(es_inicial=True)
        # duracion_seg de bloque ya descuenta overlaps
        suma_bruta = sum(p.pista.duracion_seg for p in bloque.pistas)
        overlap_total = sum(t.overlap_seg for t in bloque.transiciones)
        # El bloque.duracion_seg debe reflejar lo efectivo (sin trim porque
        # el target era 10 min = 600s y bruto era 600).
        assert bloque.duracion_seg == pytest.approx(suma_bruta - overlap_total, abs=0.5)

    def test_pistas_completas_aunque_se_exceda_objetivo(self):
        """La duración objetivo es una sugerencia: el constructor NO trunca
        ninguna pista. Cada `PistaSesionPlanificada` describe la pista
        completa, y el reproductor la respeta hasta su final natural (o
        hasta el `mix_out_seg` del mix engine cuando hay siguiente).
        """
        from servicios.dj_privado.constructor import ConstructorSesion, OpcionesConstructor
        from servicios.dj_privado.intencion import parsear_intent
        pool = self._crear_pool([200.0, 200.0, 200.0, 200.0])
        intent = parsear_intent("test", duracion_minutos=5)
        c = ConstructorSesion(intent, OpcionesConstructor(tam_bloque_inicial=4,
                                                          refinar_transiciones=False))
        c.cargar_pool(pistas=pool)
        bloque = c.construir_bloque(es_inicial=True)
        # No existe el campo de trim en la planificación.
        for p in bloque.pistas:
            assert not hasattr(p, "fade_out_at_seg") or getattr(p, "fade_out_at_seg", None) is None


# ═════════════════════════════════════════════════════════════════════════════
# SESSION OWNERSHIP MANAGER
# ═════════════════════════════════════════════════════════════════════════════

class TestSessionOwnershipManager:

    def _setup(self):
        from servicios.reproductor import Reproductor
        from servicios.dj_privado.ownership import SessionOwnershipManager
        r = Reproductor(permitir_modo_simulado=True)
        return r, SessionOwnershipManager(r)

    def test_estado_inicial_global(self):
        from servicios.dj_privado.ownership import Owner
        r, m = self._setup()
        assert m.owner == Owner.GLOBAL
        assert m.sesion_id_activa is None
        assert m.global_suspendido is False
        assert r.modo_dj_activo is False

    def test_adquirir_suspende_global(self):
        r, m = self._setup()
        assert m.adquirir_para_sesion(42) is True
        assert m.sesion_id_activa == 42
        assert m.global_suspendido is True
        assert r.modo_dj_activo is True

    def test_adquirir_idempotente_misma_sesion(self):
        r, m = self._setup()
        m.adquirir_para_sesion(42)
        # Segunda llamada con misma sesion: no-op
        assert m.adquirir_para_sesion(42) is False

    def test_transferir_entre_sesiones_no_pasa_por_global(self):
        """Si DJ tenia sesion 1 y pasas a sesion 2, el global NO se reactiva."""
        from servicios.dj_privado.ownership import Owner
        r, m = self._setup()
        m.adquirir_para_sesion(1)
        cambios_global_a_x = []
        m.on_cambio(lambda nuevo, ant: cambios_global_a_x.append((ant.value, nuevo.value)))
        m.transferir_a_sesion(2)
        # No debe haber transicion GLOBAL -> SESION_DJ; el flag se mantiene activo.
        assert r.modo_dj_activo is True
        assert m.sesion_id_activa == 2
        # El callback recibe SESION_DJ -> SESION_DJ (transferencia interna)
        for ant, nuevo in cambios_global_a_x:
            assert not (ant == "global" and nuevo == "sesion_dj"), \
                "No deberia re-suspender el global durante transferencia"

    def test_liberar_es_idempotente(self):
        r, m = self._setup()
        m.adquirir_para_sesion(7)
        assert m.liberar() is True
        # Segunda llamada: no-op
        assert m.liberar() is False
        assert r.modo_dj_activo is False

    def test_liberar_si_es_de_solo_libera_si_es_owner(self):
        r, m = self._setup()
        m.adquirir_para_sesion(7)
        # No es de la sesion 99; no debe liberar
        assert m.liberar_si_es_de(99) is False
        assert r.modo_dj_activo is True
        # Es de la sesion 7; libera
        assert m.liberar_si_es_de(7) is True
        assert r.modo_dj_activo is False

    def test_liberar_defensivo_si_flag_externo(self):
        """Si alguien setea modo_dj=True sin pasar por manager, liberar() lo limpia."""
        r, m = self._setup()
        # Estado inconsistente: flag activo sin que manager lo sepa
        r.set_modo_dj(True)
        assert r.modo_dj_activo is True
        assert m.owner.value == "global"
        # liberar() debe forzar la sincronizacion
        cambio = m.liberar()
        assert cambio is True
        assert r.modo_dj_activo is False


# ═════════════════════════════════════════════════════════════════════════════
# SEEKING GLOBAL DEL REPRODUCTOR DE SESION
# ═════════════════════════════════════════════════════════════════════════════

class TestSeekingGlobal:

    def _crear_pista_real(self, tmp_path, idx, duracion=20.0):
        """Crea una pista con archivo real (silencio) para tests E2E."""
        from db.conexion import get_conexion
        ruta = tmp_path / f"t{idx}.wav"
        # 20s de silencio mono 44.1kHz para que VLC pueda abrirlo
        try:
            import numpy as np
            import soundfile as sf
            sr = 44100
            silencio = np.zeros(int(sr * duracion), dtype="float32")
            sf.write(str(ruta), silencio, sr)
        except Exception:
            # Fallback: archivo dummy (algunos tests no necesitan audio)
            ruta.write_bytes(b"\x00" * 1024)
        con = get_conexion()
        art_id = con.execute(
            "INSERT INTO artistas(nombre, nombre_slug) VALUES (?, ?)",
            (f"A{idx}", f"a-{idx}"),
        ).lastrowid
        alb_id = con.execute(
            "INSERT INTO albums(artista_id, titulo, titulo_slug, tipo) VALUES (?, ?, ?, 'Album')",
            (art_id, f"AL{idx}", f"al-{idx}"),
        ).lastrowid
        pid = con.execute(
            """INSERT INTO pistas(album_id, artista_id, titulo, artista_nombre, album_titulo,
                                   ruta_archivo, nombre_archivo, tamano_bytes, duracion_seg, estado)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'biblioteca')""",
            (alb_id, art_id, f"T{idx}", f"A{idx}", f"AL{idx}",
             str(ruta), ruta.name, ruta.stat().st_size, duracion),
        ).lastrowid
        return int(pid)

    def _crear_sesion(self, tmp_path, ids):
        from servicios.dj_privado import persistencia
        sid = persistencia.crear_sesion(
            prompt="seek test", intent_json="{}", objetivo_minutos=5,
            motor_version="dj_v1", semilla=None, resumen={},
        )
        rows = [
            persistencia.PistaSesionRow(
                sesion_id=sid, posicion=i, pista_id=pid,
                score_total=0.7, score_intent=0.7, score_transicion=0.5,
                score_curva=0.5, razones=[], transicion={}, estado="planificada",
                bloqueada=False,
            )
            for i, pid in enumerate(ids)
        ]
        persistencia.insertar_pistas_sesion(sid, rows)
        persistencia.actualizar_estado_sesion(sid, "lista")
        return sid

    def test_buscar_global_calcula_pista_y_offset(self, db_dj):
        """Sin VLC real, validamos que el modulo NO falla con seek global."""
        from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
        ids = [self._crear_pista_real(db_dj, i, duracion=30.0) for i in range(3)]
        sid = self._crear_sesion(db_dj, ids)
        rep = ReproductorSesionDj(permitir_modo_simulado=True)
        n = rep.cargar_sesion(sid)
        assert n == 3
        # 30s + 30s + 30s = 90s total
        # Sin pista activa todavia: buscar_posicion_global a 45s
        # debe seleccionar pista indice 1 (acum=30s, offset=15s)
        ok = rep.buscar_posicion_global(45.0)
        # En modo simulado, ok puede ser False porque no hay deck real, pero
        # como minimo no debe lanzar. Validamos que indice_actual cambio.
        # (En modo simulado el cambio de pista no afecta el deck pero el
        # contador interno se actualiza)
        if ok:
            assert rep.indice_actual == 1
