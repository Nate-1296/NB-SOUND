# =============================================================================
# servicios/dj_privado/persistencia.py
#
# Repositorio de datos del DJ Privado.
#
# Encapsula:
#   - Lectura de pistas con features enriquecidos (LEFT JOIN audio_features,
#     deep_features, vibe_tags, sin filtrar pistas que no esten analizadas).
#   - CRUD de sesiones DJ (dj_sesiones, dj_pistas_sesion).
#   - Eventos de reproduccion/adaptacion (dj_eventos).
#   - Cache de embeddings (dj_concepto_emb, dj_track_emb).
#   - Preferencias del DJ (dj_preferencias).
#
# Toda la persistencia esta aqui para que el scheduler no toque SQL directo
# y los tests puedan mockearlo facilmente.
# =============================================================================

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable, Optional

from db.conexion import (
    ejecutar,
    ejecutar_y_obtener_id,
    obtener_filas,
    obtener_una_fila,
    transaccion,
)


# =============================================================================
# DATAMODELS LIGEROS (proyecciones desde la BD)
# =============================================================================

@dataclass
class PistaCandidata:
    """Pista enriquecida con todos los features relevantes para el scheduler.

    Los campos son intencionadamente opcionales: una pista puede no tener
    audio_features (no analizada) o deep_features (deep no habilitado).
    El scheduler debe degradar graceful en esos casos.
    """

    id: int
    titulo: str
    artista_nombre: str
    album_titulo: str
    artista_id: Optional[int]
    album_id: Optional[int]
    genero: str
    duracion_seg: float
    ruta_archivo: str
    favorita: bool
    veces_reproducida: int

    # Audio features basicos
    bpm: Optional[float] = None
    key_name: Optional[str] = None
    mode: Optional[str] = None
    energy: Optional[float] = None
    valence_proxy: Optional[float] = None
    danceability_proxy: Optional[float] = None
    arousal_proxy: Optional[float] = None
    calmness_proxy: Optional[float] = None
    melancholy_proxy: Optional[float] = None
    aggressiveness_proxy: Optional[float] = None
    brightness: Optional[float] = None
    darkness_proxy: Optional[float] = None
    focus_score_proxy: Optional[float] = None
    workout_score_proxy: Optional[float] = None
    party_score_proxy: Optional[float] = None
    night_score_proxy: Optional[float] = None

    # Deep features (opcionales)
    mood_happy: Optional[float] = None
    mood_sad: Optional[float] = None
    mood_relaxed: Optional[float] = None
    mood_aggressive: Optional[float] = None
    mood_party: Optional[float] = None
    danceability_model: Optional[float] = None
    arousal: Optional[float] = None
    valence: Optional[float] = None
    tags_json: str = "{}"

    # Vibe tags simples (concatenados desde track_vibe_tags)
    vibe_tags: tuple[str, ...] = ()

    def to_features_dict(self) -> dict:
        """Forma dict para alimentar a embeddings.embed_pista()."""
        return {
            "titulo": self.titulo,
            "artista_nombre": self.artista_nombre,
            "album_titulo": self.album_titulo,
            "genero": self.genero,
            "energy": self.energy,
            "valence_proxy": self.valence_proxy,
            "danceability_proxy": self.danceability_proxy,
            "arousal_proxy": self.arousal_proxy,
            "calmness_proxy": self.calmness_proxy,
            "melancholy_proxy": self.melancholy_proxy,
            "aggressiveness_proxy": self.aggressiveness_proxy,
            "brightness": self.brightness,
            "darkness_proxy": self.darkness_proxy,
            "focus_score_proxy": self.focus_score_proxy,
            "workout_score_proxy": self.workout_score_proxy,
            "party_score_proxy": self.party_score_proxy,
            "night_score_proxy": self.night_score_proxy,
            "mood_happy": self.mood_happy,
            "mood_sad": self.mood_sad,
            "mood_relaxed": self.mood_relaxed,
            "mood_aggressive": self.mood_aggressive,
            "mood_party": self.mood_party,
            "danceability_model": self.danceability_model,
            "valence": self.valence,
            "tags": list(self.vibe_tags),
            "tags_json": self.tags_json,
        }

    def to_player_dict(self) -> dict:
        """Forma compatible con Reproductor.reproducir_pista() y la cola.

        El reproductor consume dicts con id/titulo/artista/album/ruta_archivo/
        duracion_seg. Mantenemos el contrato existente para no romper la cola.
        """
        return {
            "id": self.id,
            "titulo": self.titulo,
            "artista": self.artista_nombre,
            "album": self.album_titulo,
            "ruta_archivo": self.ruta_archivo,
            "duracion_seg": float(self.duracion_seg or 0.0),
        }


# =============================================================================
# LECTURA DE CANDIDATOS
# =============================================================================

_SQL_CANDIDATOS_BASE = """
SELECT
    p.id              AS id,
    p.titulo          AS titulo,
    p.artista_nombre  AS artista_nombre,
    p.album_titulo    AS album_titulo,
    p.artista_id      AS artista_id,
    p.album_id        AS album_id,
    COALESCE(p.genero, '')      AS genero,
    COALESCE(p.duracion_seg, 0) AS duracion_seg,
    p.ruta_archivo    AS ruta_archivo,
    COALESCE(p.favorita, 0)     AS favorita,
    COALESCE(p.veces_reproducida, 0) AS veces_reproducida,
    af.bpm                      AS bpm,
    af.key_name                 AS key_name,
    af.mode                     AS mode,
    af.energy                   AS energy,
    af.valence_proxy            AS valence_proxy,
    af.danceability_proxy       AS danceability_proxy,
    af.arousal_proxy            AS arousal_proxy,
    af.calmness_proxy           AS calmness_proxy,
    af.melancholy_proxy         AS melancholy_proxy,
    af.aggressiveness_proxy     AS aggressiveness_proxy,
    af.brightness               AS brightness,
    af.darkness_proxy           AS darkness_proxy,
    af.focus_score_proxy        AS focus_score_proxy,
    af.workout_score_proxy      AS workout_score_proxy,
    af.party_score_proxy        AS party_score_proxy,
    af.night_score_proxy        AS night_score_proxy,
    df.mood_happy               AS mood_happy,
    df.mood_sad                 AS mood_sad,
    df.mood_relaxed             AS mood_relaxed,
    df.mood_aggressive          AS mood_aggressive,
    df.mood_party               AS mood_party,
    df.danceability_model       AS danceability_model,
    df.arousal                  AS arousal,
    df.valence                  AS valence,
    COALESCE(df.tags_json, '{}') AS tags_json
FROM pistas p
LEFT JOIN track_audio_features af
       ON af.track_id = CAST(p.id AS TEXT)
LEFT JOIN track_deep_audio_features df
       ON df.track_id = CAST(p.id AS TEXT)
WHERE p.estado = 'biblioteca'
"""


def _filas_a_candidatos(filas: Iterable, tags_por_pista: dict[int, tuple[str, ...]]) -> list[PistaCandidata]:
    candidatas: list[PistaCandidata] = []
    for fila in filas:
        data = dict(fila)
        pid = int(data["id"])
        candidatas.append(PistaCandidata(
            id=pid,
            titulo=data["titulo"] or "",
            artista_nombre=data.get("artista_nombre") or "",
            album_titulo=data.get("album_titulo") or "",
            artista_id=data.get("artista_id"),
            album_id=data.get("album_id"),
            genero=data.get("genero") or "",
            duracion_seg=float(data.get("duracion_seg") or 0.0),
            ruta_archivo=data["ruta_archivo"],
            favorita=bool(data.get("favorita") or 0),
            veces_reproducida=int(data.get("veces_reproducida") or 0),
            bpm=_safe_float(data.get("bpm")),
            key_name=data.get("key_name") or None,
            mode=data.get("mode") or None,
            energy=_safe_float(data.get("energy")),
            valence_proxy=_safe_float(data.get("valence_proxy")),
            danceability_proxy=_safe_float(data.get("danceability_proxy")),
            arousal_proxy=_safe_float(data.get("arousal_proxy")),
            calmness_proxy=_safe_float(data.get("calmness_proxy")),
            melancholy_proxy=_safe_float(data.get("melancholy_proxy")),
            aggressiveness_proxy=_safe_float(data.get("aggressiveness_proxy")),
            brightness=_safe_float(data.get("brightness")),
            darkness_proxy=_safe_float(data.get("darkness_proxy")),
            focus_score_proxy=_safe_float(data.get("focus_score_proxy")),
            workout_score_proxy=_safe_float(data.get("workout_score_proxy")),
            party_score_proxy=_safe_float(data.get("party_score_proxy")),
            night_score_proxy=_safe_float(data.get("night_score_proxy")),
            mood_happy=_safe_float(data.get("mood_happy")),
            mood_sad=_safe_float(data.get("mood_sad")),
            mood_relaxed=_safe_float(data.get("mood_relaxed")),
            mood_aggressive=_safe_float(data.get("mood_aggressive")),
            mood_party=_safe_float(data.get("mood_party")),
            danceability_model=_safe_float(data.get("danceability_model")),
            arousal=_safe_float(data.get("arousal")),
            valence=_safe_float(data.get("valence")),
            tags_json=data.get("tags_json") or "{}",
            vibe_tags=tags_por_pista.get(pid, ()),
        ))
    return candidatas


def _safe_float(valor) -> Optional[float]:
    if valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _cargar_vibe_tags_para(ids: list[int]) -> dict[int, tuple[str, ...]]:
    """Carga tags simples desde track_vibe_tags agrupados por pista.

    Limitamos a tags con score >= 0.4 para reducir ruido. El scheduler usa
    estos tags como senales debiles de re-ranking, no como filtros duros.
    """
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    sql = f"""
        SELECT track_id, tag, score
        FROM track_vibe_tags
        WHERE CAST(track_id AS INTEGER) IN ({placeholders})
          AND score >= 0.4
    """
    filas = obtener_filas(sql, tuple(str(i) for i in ids))
    agrupados: dict[int, list[str]] = {}
    for fila in filas:
        try:
            pid = int(fila["track_id"])
        except (TypeError, ValueError):
            continue
        agrupados.setdefault(pid, []).append(fila["tag"])
    return {pid: tuple(tags) for pid, tags in agrupados.items()}


def cargar_candidatos(
    *,
    limite: int = 5000,
    excluir_ids: Optional[Iterable[int]] = None,
    requerir_features: bool = False,
) -> list[PistaCandidata]:
    """Carga el pool de pistas candidatas para una sesion.

    - limite: tope de pistas (proteccion para bibliotecas enormes).
    - excluir_ids: pistas a omitir (ya tocadas, bloqueadas, etc.).
    - requerir_features: si True, solo pistas con audio_features analizados.

    Devuelve pistas sin orden particular: el scheduler las puntua/ordena.
    """
    sql = _SQL_CANDIDATOS_BASE
    if requerir_features:
        sql += " AND af.analysis_status = 'ready'"
    excluidos = tuple(int(i) for i in (excluir_ids or ()) if isinstance(i, int) or str(i).isdigit())
    if excluidos:
        placeholders = ",".join("?" * len(excluidos))
        sql += f" AND p.id NOT IN ({placeholders})"
    sql += " ORDER BY p.id LIMIT ?"
    params = excluidos + (int(limite),)
    filas = obtener_filas(sql, params)
    ids = [int(f["id"]) for f in filas]
    tags = _cargar_vibe_tags_para(ids)
    return _filas_a_candidatos(filas, tags)


def cargar_candidatas_por_ids(ids: Iterable[int]) -> list[PistaCandidata]:
    """Carga un conjunto especifico de pistas con sus features.

    Util para reconstruir una sesion guardada (vuelve a leer features
    actualizados aunque la sesion original tenga snapshot).
    """
    lista_ids = [int(i) for i in ids]
    if not lista_ids:
        return []
    placeholders = ",".join("?" * len(lista_ids))
    sql = _SQL_CANDIDATOS_BASE + f" AND p.id IN ({placeholders})"
    filas = obtener_filas(sql, tuple(lista_ids))
    tags = _cargar_vibe_tags_para(lista_ids)
    return _filas_a_candidatos(filas, tags)


# =============================================================================
# CRUD DE SESIONES
# =============================================================================

@dataclass
class SesionDjRow:
    id: int
    prompt_original: str
    intent_json: str
    objetivo_minutos: int
    estado: str
    motor_version: str
    semilla: Optional[int]
    notas: Optional[str]
    resumen_json: str
    playlist_id: Optional[int]
    creado_en: str
    actualizado_en: str
    finalizado_en: Optional[str]


@dataclass
class PistaSesionRow:
    sesion_id: int
    posicion: int
    pista_id: int
    score_total: float
    score_intent: float
    score_transicion: float
    score_curva: float
    razones: list[str] = field(default_factory=list)
    transicion: dict = field(default_factory=dict)
    estado: str = "planificada"
    bloqueada: bool = False


def crear_sesion(
    *,
    prompt: str,
    intent_json: str,
    objetivo_minutos: int,
    motor_version: str,
    semilla: Optional[int] = None,
    resumen: Optional[dict] = None,
) -> int:
    """Crea una sesion en estado 'construyendo'. Devuelve el id."""
    sql = """
        INSERT INTO dj_sesiones
            (prompt_original, intent_json, objetivo_minutos, estado,
             motor_version, semilla, resumen_json, creado_en, actualizado_en)
        VALUES (?, ?, ?, 'construyendo', ?, ?, ?, datetime('now'), datetime('now'))
    """
    return int(ejecutar_y_obtener_id(sql, (
        prompt,
        intent_json,
        int(objetivo_minutos),
        motor_version,
        int(semilla) if semilla is not None else None,
        json.dumps(resumen or {}, ensure_ascii=False),
    )))


def actualizar_estado_sesion(sesion_id: int, estado: str, *, finalizar: bool = False) -> None:
    """Mueve la sesion a un nuevo estado.

    Si finalizar=True, escribe finalizado_en con la fecha actual.
    """
    if finalizar:
        sql = """
            UPDATE dj_sesiones
            SET estado=?, actualizado_en=datetime('now'), finalizado_en=datetime('now')
            WHERE id=?
        """
    else:
        sql = """
            UPDATE dj_sesiones
            SET estado=?, actualizado_en=datetime('now')
            WHERE id=?
        """
    ejecutar(sql, (estado, int(sesion_id)))


def actualizar_resumen_sesion(sesion_id: int, resumen: dict) -> None:
    sql = """
        UPDATE dj_sesiones
        SET resumen_json=?, actualizado_en=datetime('now')
        WHERE id=?
    """
    ejecutar(sql, (json.dumps(resumen, ensure_ascii=False), int(sesion_id)))


def insertar_pistas_sesion(sesion_id: int, pistas: list[PistaSesionRow]) -> None:
    """Inserta (o reemplaza) las pistas planificadas para la sesion.

    Usa una transaccion para garantizar atomicidad.
    """
    if not pistas:
        return
    # La columna `fade_out_at_seg` existe en BD por compatibilidad con
    # sesiones generadas por versiones anteriores; se conserva pero las
    # inserciones nuevas la dejan en NULL (el reproductor la ignora y la
    # duración de cada pista se respeta natural).
    sql_insert = """
        INSERT OR REPLACE INTO dj_pistas_sesion
            (sesion_id, posicion, pista_id, score_total, score_intent,
             score_transicion, score_curva, razones_json, transicion_json,
             estado, bloqueada, agregado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """
    with transaccion() as conn:
        for p in pistas:
            conn.execute(sql_insert, (
                int(p.sesion_id), int(p.posicion), int(p.pista_id),
                float(p.score_total), float(p.score_intent),
                float(p.score_transicion), float(p.score_curva),
                json.dumps(p.razones, ensure_ascii=False),
                json.dumps(p.transicion, ensure_ascii=False),
                p.estado, 1 if p.bloqueada else 0,
            ))


def borrar_pistas_sesion(sesion_id: int, *, desde_posicion: Optional[int] = None) -> None:
    """Elimina pistas planificadas. Si desde_posicion se da, solo a partir de ahi."""
    if desde_posicion is None:
        sql = "DELETE FROM dj_pistas_sesion WHERE sesion_id=?"
        params = (int(sesion_id),)
    else:
        sql = "DELETE FROM dj_pistas_sesion WHERE sesion_id=? AND posicion>=?"
        params = (int(sesion_id), int(desde_posicion))
    ejecutar(sql, params)


def listar_pistas_sesion(sesion_id: int) -> list[dict]:
    """Lee las pistas planificadas de una sesion con su metadata.

    Hace LEFT JOIN con pistas para devolver al menos titulo/artista.
    """
    sql = """
        SELECT
            dps.sesion_id, dps.posicion, dps.pista_id,
            dps.score_total, dps.score_intent, dps.score_transicion, dps.score_curva,
            dps.razones_json, dps.transicion_json, dps.estado, dps.bloqueada,
            p.titulo, p.artista_nombre, p.album_titulo, p.duracion_seg,
            p.ruta_archivo,
            af.bpm    AS bpm,
            af.energy AS energy
        FROM dj_pistas_sesion dps
        LEFT JOIN pistas p ON p.id = dps.pista_id
        LEFT JOIN track_audio_features af ON af.track_id = CAST(p.id AS TEXT)
        WHERE dps.sesion_id=?
        ORDER BY dps.posicion
    """
    filas = obtener_filas(sql, (int(sesion_id),))
    salida: list[dict] = []
    for fila in filas:
        data = dict(fila)
        data["razones"] = json.loads(data.pop("razones_json", "[]") or "[]")
        data["transicion"] = json.loads(data.pop("transicion_json", "{}") or "{}")
        data["bloqueada"] = bool(data.get("bloqueada") or 0)
        salida.append(data)
    return salida


def obtener_sesion(sesion_id: int) -> Optional[SesionDjRow]:
    fila = obtener_una_fila(
        "SELECT * FROM dj_sesiones WHERE id=?",
        (int(sesion_id),),
    )
    if not fila:
        return None
    data = dict(fila)
    return SesionDjRow(
        id=int(data["id"]),
        prompt_original=data["prompt_original"] or "",
        intent_json=data["intent_json"] or "{}",
        objetivo_minutos=int(data["objetivo_minutos"] or 60),
        estado=data["estado"] or "construyendo",
        motor_version=data["motor_version"] or "dj_v1",
        semilla=data.get("semilla"),
        notas=data.get("notas"),
        resumen_json=data["resumen_json"] or "{}",
        playlist_id=data.get("playlist_id"),
        creado_en=data["creado_en"],
        actualizado_en=data["actualizado_en"],
        finalizado_en=data.get("finalizado_en"),
    )


def sesiones_recientes(limite: int = 10) -> list[SesionDjRow]:
    # Tiebreaker por id DESC: si dos sesiones se crean en el mismo segundo
    # (test rapido o batch), el id estable resuelve el orden de forma
    # deterministica (el id mayor es la sesion mas reciente).
    filas = obtener_filas(
        "SELECT * FROM dj_sesiones ORDER BY creado_en DESC, id DESC LIMIT ?",
        (int(limite),),
    )
    salida: list[SesionDjRow] = []
    for fila in filas:
        data = dict(fila)
        salida.append(SesionDjRow(
            id=int(data["id"]),
            prompt_original=data["prompt_original"] or "",
            intent_json=data["intent_json"] or "{}",
            objetivo_minutos=int(data["objetivo_minutos"] or 60),
            estado=data["estado"] or "construyendo",
            motor_version=data["motor_version"] or "dj_v1",
            semilla=data.get("semilla"),
            notas=data.get("notas"),
            resumen_json=data["resumen_json"] or "{}",
            playlist_id=data.get("playlist_id"),
            creado_en=data["creado_en"],
            actualizado_en=data["actualizado_en"],
            finalizado_en=data.get("finalizado_en"),
        ))
    return salida


def vincular_playlist(sesion_id: int, playlist_id: int) -> None:
    sql = """
        UPDATE dj_sesiones SET playlist_id=?, actualizado_en=datetime('now')
        WHERE id=?
    """
    ejecutar(sql, (int(playlist_id), int(sesion_id)))


# =============================================================================
# EVENTOS DJ (skips, likes, replanificaciones)
# =============================================================================

def registrar_evento(
    sesion_id: int,
    tipo: str,
    *,
    pista_id: Optional[int] = None,
    payload: Optional[dict] = None,
) -> None:
    sql = """
        INSERT INTO dj_eventos (sesion_id, pista_id, tipo, payload_json)
        VALUES (?, ?, ?, ?)
    """
    ejecutar(sql, (
        int(sesion_id),
        int(pista_id) if pista_id is not None else None,
        tipo,
        json.dumps(payload or {}, ensure_ascii=False),
    ))


def listar_eventos(sesion_id: int) -> list[dict]:
    filas = obtener_filas(
        "SELECT * FROM dj_eventos WHERE sesion_id=? ORDER BY creado_en, id",
        (int(sesion_id),),
    )
    salida = []
    for fila in filas:
        data = dict(fila)
        data["payload"] = json.loads(data.pop("payload_json", "{}") or "{}")
        salida.append(data)
    return salida


# =============================================================================
# MARCADO DE ESTADO POR PISTA
# =============================================================================

def marcar_pista_estado(sesion_id: int, posicion: int, estado: str) -> None:
    sql = """
        UPDATE dj_pistas_sesion SET estado=? WHERE sesion_id=? AND posicion=?
    """
    ejecutar(sql, (estado, int(sesion_id), int(posicion)))


def ids_excluidos_por_eventos(sesion_id: int, tipos: tuple[str, ...]) -> list[int]:
    """Pista ids con eventos de los tipos dados (ej. saltada, dislike)."""
    if not tipos:
        return []
    placeholders = ",".join("?" * len(tipos))
    sql = f"""
        SELECT DISTINCT pista_id FROM dj_eventos
        WHERE sesion_id=? AND tipo IN ({placeholders}) AND pista_id IS NOT NULL
    """
    filas = obtener_filas(sql, (int(sesion_id), *tipos))
    return [int(f["pista_id"]) for f in filas if f["pista_id"] is not None]


# =============================================================================
# CACHE DE EMBEDDINGS
# =============================================================================

def leer_embedding_concepto(concepto: str, modelo: str) -> Optional[list[float]]:
    fila = obtener_una_fila(
        "SELECT vector_json FROM dj_concepto_emb WHERE concepto=? AND modelo=?",
        (concepto, modelo),
    )
    if not fila:
        return None
    try:
        return list(json.loads(fila["vector_json"]))
    except (TypeError, json.JSONDecodeError):
        return None


def guardar_embedding_concepto(concepto: str, modelo: str, vector: list[float]) -> None:
    sql = """
        INSERT INTO dj_concepto_emb (concepto, modelo, dim, vector_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(concepto) DO UPDATE SET
            modelo=excluded.modelo, dim=excluded.dim,
            vector_json=excluded.vector_json
    """
    ejecutar(sql, (concepto, modelo, len(vector), json.dumps(vector)))


def leer_embedding_pista(pista_id: int, modelo: str) -> Optional[list[float]]:
    fila = obtener_una_fila(
        "SELECT vector_json FROM dj_track_emb WHERE pista_id=? AND modelo=?",
        (int(pista_id), modelo),
    )
    if not fila:
        return None
    try:
        return list(json.loads(fila["vector_json"]))
    except (TypeError, json.JSONDecodeError):
        return None


def guardar_embedding_pista(
    pista_id: int,
    modelo: str,
    vector: list[float],
    fuente_hash: str,
) -> None:
    sql = """
        INSERT INTO dj_track_emb (pista_id, modelo, dim, vector_json, fuente_hash)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(pista_id) DO UPDATE SET
            modelo=excluded.modelo,
            dim=excluded.dim,
            vector_json=excluded.vector_json,
            fuente_hash=excluded.fuente_hash,
            actualizado_en=datetime('now')
    """
    ejecutar(sql, (int(pista_id), modelo, len(vector), json.dumps(vector), fuente_hash))


# =============================================================================
# PREFERENCIAS DJ
# =============================================================================

def leer_preferencia(clave: str) -> Optional[dict]:
    fila = obtener_una_fila(
        "SELECT valor_json FROM dj_preferencias WHERE clave=?",
        (clave,),
    )
    if not fila:
        return None
    try:
        return json.loads(fila["valor_json"])
    except (TypeError, json.JSONDecodeError):
        return None


def guardar_preferencia(clave: str, valor: dict) -> None:
    sql = """
        INSERT INTO dj_preferencias (clave, valor_json)
        VALUES (?, ?)
        ON CONFLICT(clave) DO UPDATE SET
            valor_json=excluded.valor_json,
            actualizado_en=datetime('now')
    """
    ejecutar(sql, (clave, json.dumps(valor, ensure_ascii=False)))
