"""Tests para el servicio Explorador Ciego (Fase 12).

Cubren:
  - Construccion de rondas (cantidad, modos, edge cases).
  - Transiciones de revelacion (oculto -> artista -> album -> total).
  - Estados finales (acertado, revelado, pasado).
  - Selectores por modo (audio, portada, redescubrimiento, nunca_eliges).
  - Helpers: posicion sugerida de fragmento, conteos por modo.

No tocan QML ni audio: el servicio es puro Python.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from db.conexion import cerrar_db, get_conexion, inicializar_db
from servicios.explorador_ciego import (
    EstadoReto,
    ExploradorCiegoService,
    ModoExplorador,
    NivelRevelacion,
)
from servicios.explorador_ciego import selectores as sel


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _crear_pista(
    tmp_path: Path,
    nombre: str,
    *,
    favorita: bool = False,
    reproducciones: int = 0,
    con_portada: bool = False,
    duracion: float = 180.0,
) -> dict:
    ruta = tmp_path / f"{nombre}.mp3"
    ruta.write_bytes(b"audio")
    con = get_conexion()
    artista_id = con.execute(
        "INSERT INTO artistas(nombre, nombre_slug) VALUES (?, ?)",
        (f"Artista {nombre}", f"artista-{nombre}"),
    ).lastrowid
    portada_path = ""
    if con_portada:
        portada_path = str(tmp_path / f"{nombre}-cover.jpg")
        Path(portada_path).write_bytes(b"jpg")
    album_id = con.execute(
        """
        INSERT INTO albums(artista_id, titulo, titulo_slug, tipo, portada_ruta)
        VALUES (?, ?, ?, 'Album', ?)
        """,
        (artista_id, f"Album {nombre}", f"album-{nombre}", portada_path or None),
    ).lastrowid
    pista_id = con.execute(
        """
        INSERT INTO pistas(
            album_id, artista_id, titulo, artista_nombre, album_titulo,
            ruta_archivo, nombre_archivo, tamano_bytes, duracion_seg,
            veces_reproducida, favorita, estado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'biblioteca')
        """,
        (
            album_id, artista_id, f"Pista {nombre}",
            f"Artista {nombre}", f"Album {nombre}",
            str(ruta), ruta.name, ruta.stat().st_size, duracion,
            reproducciones, 1 if favorita else 0,
        ),
    ).lastrowid
    return {"id": pista_id, "album_id": album_id, "artista_id": artista_id}


def _registrar_historial(pista_id: int, n: int = 1) -> None:
    con = get_conexion()
    for _ in range(n):
        con.execute(
            """
            INSERT INTO historial(pista_id, titulo_snap, artista_snap, duracion_seg, completada)
            VALUES (?, 'snap', 'artista', 180, 1)
            """,
            (pista_id,),
        )


@pytest.fixture()
def db_juego(tmp_path):
    inicializar_db(tmp_path / "explorador.db")
    try:
        yield tmp_path
    finally:
        cerrar_db()


# ─── Selectores ──────────────────────────────────────────────────────────────

def test_selector_audio_devuelve_pistas_con_audio(db_juego, tmp_path):
    _crear_pista(tmp_path, "uno", duracion=180)
    _crear_pista(tmp_path, "dos", duracion=180)
    # Pista demasiado corta: el selector audio la excluye.
    _crear_pista(tmp_path, "corta", duracion=10)

    pistas = sel.candidatos_audio()
    titulos = [p["titulo"] for p in pistas]
    assert "Pista uno" in titulos
    assert "Pista dos" in titulos
    assert "Pista corta" not in titulos


def test_selector_portada_solo_con_portada(db_juego, tmp_path):
    _crear_pista(tmp_path, "uno", con_portada=True)
    _crear_pista(tmp_path, "sin", con_portada=False)
    pistas = sel.candidatos_portada()
    titulos = [p["titulo"] for p in pistas]
    assert "Pista uno" in titulos
    assert "Pista sin" not in titulos


def test_selector_redescubrimiento_requiere_favorita_o_historial(db_juego, tmp_path):
    p_nueva = _crear_pista(tmp_path, "nueva")  # 0 reproducciones, no favorita
    p_fav = _crear_pista(tmp_path, "fav", favorita=True)
    p_esc = _crear_pista(tmp_path, "esc", reproducciones=4)
    _registrar_historial(p_esc["id"], n=4)

    pistas = sel.candidatos_redescubrimiento()
    ids = {p["id"] for p in pistas}
    assert p_fav["id"] in ids
    assert p_esc["id"] in ids
    assert p_nueva["id"] not in ids


def test_selector_nunca_eliges_solo_no_escuchadas(db_juego, tmp_path):
    p_nunca = _crear_pista(tmp_path, "nunca")
    p_esc = _crear_pista(tmp_path, "escuchada", reproducciones=5)
    _registrar_historial(p_esc["id"], n=5)

    pistas = sel.candidatos_nunca_eliges()
    ids = {p["id"] for p in pistas}
    assert p_nunca["id"] in ids
    assert p_esc["id"] not in ids


def test_selector_nunca_eliges_fallback_si_no_hay_zero(db_juego, tmp_path):
    # Todas las pistas tienen alguna reproduccion -> el selector debe usar
    # el fallback relajado (<= 2 reproducciones).
    p_baja = _crear_pista(tmp_path, "baja", reproducciones=1)
    _registrar_historial(p_baja["id"], n=1)
    p_alta = _crear_pista(tmp_path, "alta", reproducciones=20)
    _registrar_historial(p_alta["id"], n=20)

    pistas = sel.candidatos_nunca_eliges()
    ids = {p["id"] for p in pistas}
    assert p_baja["id"] in ids
    # alta no deberia estar (>2 reproducciones)
    assert p_alta["id"] not in ids


def test_contar_disponibles_por_modo(db_juego, tmp_path):
    _crear_pista(tmp_path, "1", duracion=200, con_portada=True)
    _crear_pista(tmp_path, "2", duracion=200, favorita=True)
    _crear_pista(tmp_path, "3", duracion=10)  # excluida de audio

    assert sel.contar_disponibles(ModoExplorador.AUDIO) == 2
    assert sel.contar_disponibles(ModoExplorador.PORTADA) >= 1
    # Redescubrimiento: 1 favorita (id 2)
    assert sel.contar_disponibles(ModoExplorador.REDESCUBRIMIENTO) >= 1


# ─── Servicio: construccion de ronda ──────────────────────────────────────────

def test_iniciar_ronda_sin_biblioteca_falla(db_juego):
    svc = ExploradorCiegoService()
    reto = svc.iniciar_ronda(ModoExplorador.AUDIO, retos=3)
    assert reto is None
    assert not svc.ronda_activa


def test_iniciar_ronda_cantidad_acotada(db_juego, tmp_path):
    for i in range(8):
        _crear_pista(tmp_path, str(i), duracion=180)
    svc = ExploradorCiegoService()
    reto = svc.iniciar_ronda(ModoExplorador.AUDIO, retos=5)
    assert reto is not None
    assert svc.total == 5
    assert svc.ronda_activa
    assert svc.indice == 0


def test_iniciar_ronda_evita_pistas_indicadas(db_juego, tmp_path):
    creadas = []
    for i in range(4):
        creadas.append(_crear_pista(tmp_path, str(i), duracion=180)["id"])
    svc = ExploradorCiegoService()
    a_evitar = {creadas[0], creadas[1]}
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=2, evitar_pistas_ids=a_evitar)
    ids_seleccionados = {r.pista_id for r in svc._retos}
    # Si hay suficientes alternativas, ninguna pista evitada deberia entrar.
    assert ids_seleccionados.isdisjoint(a_evitar)


def test_iniciar_ronda_relaja_si_evitar_vacia_pool(db_juego, tmp_path):
    p_id = _crear_pista(tmp_path, "sola", duracion=180)["id"]
    svc = ExploradorCiegoService()
    # Pedir evitar la unica pista disponible: el servicio NO debe quedarse
    # sin ronda; debe permitir repetir.
    reto = svc.iniciar_ronda(
        ModoExplorador.AUDIO, retos=1, evitar_pistas_ids={p_id},
    )
    assert reto is not None
    assert reto.pista_id == p_id


def test_iniciar_ronda_minimo_uno(db_juego, tmp_path):
    _crear_pista(tmp_path, "uno", duracion=180)
    svc = ExploradorCiegoService()
    # retos=0 (invalido) deberia subir a MIN_RETOS_POR_RONDA=1
    reto = svc.iniciar_ronda(ModoExplorador.AUDIO, retos=0)
    assert reto is not None
    assert svc.total == 1


# ─── Servicio: niveles de revelacion ──────────────────────────────────────────

def test_revelar_progresivo(db_juego, tmp_path):
    _crear_pista(tmp_path, "p", duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=1)
    reto = svc.reto_actual()
    assert reto.nivel == NivelRevelacion.OCULTO

    svc.revelar_artista()
    assert svc.reto_actual().nivel == NivelRevelacion.ARTISTA

    svc.revelar_album()
    assert svc.reto_actual().nivel == NivelRevelacion.ALBUM

    svc.revelar_total()
    assert svc.reto_actual().nivel == NivelRevelacion.TOTAL
    assert svc.reto_actual().estado == EstadoReto.REVELADO


def test_revelar_album_salta_artista_si_oculto(db_juego, tmp_path):
    _crear_pista(tmp_path, "p", duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=1)
    svc.revelar_album()  # Saltamos artista directamente
    assert svc.reto_actual().nivel == NivelRevelacion.ALBUM


def test_datos_visibles_censura_segun_nivel(db_juego, tmp_path):
    _crear_pista(tmp_path, "p", duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=1)
    reto = svc.reto_actual()

    vis = reto.datos_visibles()
    assert vis["titulo"] == "???"
    assert vis["artista"] == "???"
    assert vis["album"] == "???"

    svc.revelar_artista()
    vis = svc.reto_actual().datos_visibles()
    assert vis["titulo"] == "???"
    assert vis["artista"] != "???"
    assert vis["album"] == "???"

    svc.revelar_total()
    vis = svc.reto_actual().datos_visibles()
    assert vis["titulo"] != "???"
    assert vis["album"] != "???"


# ─── Servicio: estados (acertado/pasado/revelado) ─────────────────────────────

def test_marcar_acertada_revela_todo_y_marca_acertado(db_juego, tmp_path):
    _crear_pista(tmp_path, "p", duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=1)
    svc.marcar_acertada()
    reto = svc.reto_actual()
    assert reto.estado == EstadoReto.ACERTADO
    assert reto.nivel == NivelRevelacion.TOTAL


def test_marcar_pasado_no_revela(db_juego, tmp_path):
    _crear_pista(tmp_path, "p", duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=1)
    svc.marcar_pasado()
    reto = svc.reto_actual()
    assert reto.estado == EstadoReto.PASADO
    assert reto.nivel == NivelRevelacion.OCULTO


def test_avanzar_marca_pasado_lo_no_resuelto(db_juego, tmp_path):
    _crear_pista(tmp_path, "a", duracion=180)
    _crear_pista(tmp_path, "b", duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=2)
    # Usuario no hace nada y avanza
    svc.avanzar()
    assert svc._retos[0].estado == EstadoReto.PASADO


# ─── Servicio: navegacion ────────────────────────────────────────────────────

def test_avanzar_y_retroceder(db_juego, tmp_path):
    for i in range(3):
        _crear_pista(tmp_path, str(i), duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=3)
    assert svc.indice == 0
    svc.marcar_pasado()
    svc.avanzar()
    assert svc.indice == 1
    svc.retroceder()
    assert svc.indice == 0


def test_avanzar_al_final_termina_ronda(db_juego, tmp_path):
    _crear_pista(tmp_path, "a", duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=1)
    svc.marcar_acertada()
    siguiente = svc.avanzar()
    assert siguiente is None
    assert svc.ronda_terminada


def test_cerrar_ronda_retorna_resumen(db_juego, tmp_path):
    for i in range(3):
        _crear_pista(tmp_path, str(i), duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=3)
    svc.marcar_acertada()
    svc.avanzar()
    svc.revelar_total()
    svc.avanzar()
    svc.marcar_pasado()
    resumen = svc.cerrar_ronda()
    assert resumen is not None
    payload = resumen.to_dict()
    assert payload["total"] == 3
    assert payload["acertados"] == 1
    assert payload["revelados"] == 1
    assert payload["pasados"] == 1
    # Tras cerrar, no hay ronda activa
    assert not svc.ronda_activa


# ─── Helpers de la UI ────────────────────────────────────────────────────────

def test_posicion_inicio_fragmento_pista_corta(db_juego, tmp_path):
    # Duracion 45s: pasa el filtro del selector (>30s) pero es <60s
    # asi que debe empezar en 0.
    _crear_pista(tmp_path, "p", duracion=45)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=1)
    pos = svc.posicion_inicio_fragmento(svc.reto_actual())
    assert pos == 0.0


def test_posicion_inicio_fragmento_pista_larga(db_juego, tmp_path):
    _crear_pista(tmp_path, "p", duracion=200)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=1)
    pos = svc.posicion_inicio_fragmento(svc.reto_actual())
    # 30% de 200s = 60s
    assert 55 < pos < 65


def test_set_segundos_fragmento_acotado(db_juego):
    svc = ExploradorCiegoService()
    svc.set_segundos_fragmento(0.5)
    assert svc.segundos_fragmento >= 4.0
    svc.set_segundos_fragmento(120)
    assert svc.segundos_fragmento <= 30.0
    svc.set_segundos_fragmento(15)
    assert svc.segundos_fragmento == 15.0


def test_disponibles_por_modo_devuelve_todos(db_juego, tmp_path):
    _crear_pista(tmp_path, "p", duracion=180)
    svc = ExploradorCiegoService()
    d = svc.disponibles_por_modo()
    assert set(d.keys()) == {m.value for m in ModoExplorador}


def test_conteo_estados_se_actualiza(db_juego, tmp_path):
    for i in range(3):
        _crear_pista(tmp_path, str(i), duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=3)
    svc.marcar_acertada()
    svc.avanzar()
    svc.revelar_total()
    svc.avanzar()
    c = svc.conteo_estados()
    assert c["acertados"] == 1
    assert c["revelados"] == 1
    assert c["en_curso"] == 1  # ultimo reto sigue en curso


# ─── Caches ──────────────────────────────────────────────────────────────────

def test_invalidar_caches_limpia_pool(db_juego, tmp_path):
    _crear_pista(tmp_path, "p", duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=1)
    assert ModoExplorador.AUDIO in svc._pool_por_modo
    svc.invalidar_caches()
    assert svc._pool_por_modo == {}


# ─── Edge cases adicionales ──────────────────────────────────────────────────

def test_reto_actual_sin_ronda_es_none(db_juego):
    svc = ExploradorCiegoService()
    assert svc.reto_actual() is None
    assert not svc.ronda_activa


def test_no_se_puede_iniciar_modo_invalido_por_string(db_juego, tmp_path):
    _crear_pista(tmp_path, "p", duracion=180)
    # El enum acepta solo modos validos: probamos por valor.
    with pytest.raises(ValueError):
        ModoExplorador("inexistente")


# ─── Validacion por escritura + hints ───────────────────────────────────────

def test_intentar_adivinar_acierto_marca_reto_acertado(db_juego, tmp_path):
    _crear_pista(tmp_path, "p", duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=1)
    titulo_real = svc.reto_actual().pista.get("titulo")
    r = svc.intentar_adivinar(titulo_real)
    assert r["acierto"] is True
    assert svc.reto_actual().estado == EstadoReto.ACERTADO
    assert svc.reto_actual().nivel == NivelRevelacion.TOTAL


def test_intentar_adivinar_fallo_incrementa_contador(db_juego, tmp_path):
    _crear_pista(tmp_path, "p", duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=1)
    svc.intentar_adivinar("algo random totalmente lejano abc xyz")
    svc.intentar_adivinar("otra cosa diferente")
    assert svc.reto_actual().intentos_fallidos == 2
    assert svc.reto_actual().estado == EstadoReto.EN_CURSO


def test_intentar_adivinar_sin_ronda_devuelve_no_acierto(db_juego):
    svc = ExploradorCiegoService()
    r = svc.intentar_adivinar("cualquier cosa")
    assert r["acierto"] is False


def test_revelar_hint_marca_hint_como_visible(db_juego, tmp_path):
    _crear_pista(tmp_path, "p", duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=1)
    svc.revelar_hint("empieza_con")
    visibles = svc.reto_actual().datos_visibles().get("hints_visibles", {})
    assert "empieza_con" in visibles
    assert visibles["empieza_con"]  # no vacio


def test_revelar_hint_clave_invalida_se_ignora(db_juego, tmp_path):
    _crear_pista(tmp_path, "p", duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=1)
    svc.revelar_hint("revelar_titulo_completo_HACK")
    assert "revelar_titulo_completo_HACK" not in svc.reto_actual().hints_reveladas


def test_datos_visibles_incluye_alfabeto_y_requiere_escritura(db_juego, tmp_path):
    _crear_pista(tmp_path, "p", duracion=180)
    svc = ExploradorCiegoService()
    svc.iniciar_ronda(ModoExplorador.AUDIO, retos=1)
    vis = svc.reto_actual().datos_visibles()
    assert "alfabeto" in vis
    assert "requiere_escritura" in vis
    assert vis["alfabeto"] == "latino"
    assert vis["requiere_escritura"] is True
