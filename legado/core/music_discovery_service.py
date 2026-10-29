from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from config import settings
from db.conexion import obtener_filas, obtener_una_fila
from servicios import biblioteca as svc_bib
from utils.text import para_comparacion



@dataclass
class ParsedIntent:
    intent: str
    interpretation: str
    weights: dict


KEYWORDS = {
    "sad": ["triste", "melanc", "bajon", "llorar", "sentimental", "nostalg", "sad", "blue"],
    "happy": ["feliz", "alegre", "positiva", "content", "happy", "uplifting", "animad", "animo", "optimista"],
    "party": ["fiesta", "party", "bail", "bailable", "dance", "club", "celebr", "limpiar"],
    "workout": ["entren", "gym", "correr", "caminar", "energia", "energetic", "energetico", "energetica", "potente", "activo", "activa", "workout", "run", "running", "walk"],
    "focus": ["concentr", "estudi", "enfoque", "focus", "study", "trabajar", "trabajo", "productiv", "manejar", "conducir", "drive", "driving"],
    "chill": ["chill", "tranquil", "relajad", "calma", "calm", "relax", "sueno", "dormir", "sleep", "cocinar", "romant"],
    "dark": ["oscur", "nocturn", "noche", "dark", "night", "sombr"],
    "intense": ["intens", "agresiv", "pesad", "fuerte", "hard", "aggressive"],
    "soft": ["suave", "soft", "liger", "gentle"],
    "fast": ["rapido", "veloz", "rapidas", "fast", "quick", "acelerad"],
    "slow": ["lento", "despacio", "slow", "pausad"],
}

PHRASE_HINTS = (
    ("baja energia", "soft", 1.0),
    ("energia baja", "soft", 1.0),
    ("alta energia", "workout", 1.0),
    ("energia alta", "workout", 1.0),
    ("levantar animo", "happy", 1.0),
    ("para manejar", "focus", 0.95),
    ("para conducir", "focus", 0.95),
    ("para caminar", "workout", 0.95),
    ("para trabajar", "focus", 0.95),
    ("para estudiar", "focus", 0.95),
    ("para dormir", "chill", 1.0),
    ("para cocinar", "chill", 0.9),
    ("para limpiar", "party", 0.9),
    ("musica de noche", "dark", 1.0),
    ("musica para concentrarme", "focus", 1.0),
    ("musica para fiesta", "party", 1.0),
)

NO_INTENT_MESSAGE = (
    "No entendí una intención musical en esa frase. "
    "Prueba con algo como: 'para fiesta', 'algo triste', "
    "'para concentrarme' o 'música rápida'."
)

INTENT_LABELS = {
    "sad": "triste",
    "happy": "alegre",
    "party": "para fiesta",
    "workout": "para entrenar",
    "focus": "para concentrarte",
    "chill": "tranquila",
    "dark": "nocturna",
    "intense": "intensa",
    "soft": "suave",
    "fast": "rápida",
    "slow": "lenta",
}


def parse_query(q: str) -> ParsedIntent:
    text = para_comparacion(q or "")
    if not text:
        return ParsedIntent("generic", "Selección musical general", {"generic": 1.0})

    weights: dict[str, float] = {}
    for phrase, intent, weight in PHRASE_HINTS:
        if phrase in text:
            weights[intent] = max(weights.get(intent, 0.0), weight)

    for intent, keywords in KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in text)
        if hits:
            weights[intent] = min(1.0, 0.75 + hits * 0.15)

    if "baja energia" in text or "energia baja" in text:
        tiene_entrenamiento_explicito = any(
            palabra in text
            for palabra in ("entren", "gym", "correr", "workout", "run", "caminar")
        )
        if not tiene_entrenamiento_explicito:
            weights.pop("workout", None)

    if not weights:
        return ParsedIntent("generic", "Selección musical general", {"generic": 1.0})

    if len(weights) == 1:
        intent = next(iter(weights))
        return ParsedIntent(intent, f"Selección {INTENT_LABELS.get(intent, intent)}", weights)

    labels = [INTENT_LABELS.get(intent, intent) for intent in weights]
    return ParsedIntent("mixed", "Selección " + " + ".join(labels), weights)


def _clip01(value) -> float:
    try:
        return float(max(0.0, min(1.0, float(value))))
    except (TypeError, ValueError):
        return 0.0


def _inv01(value) -> float:
    return 1.0 - _clip01(value)


class MusicDiscoveryService:
    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        *,
        use_audio_features: bool | None = None,
        use_deep: bool | None = None,
        min_confidence: float | None = None,
        explain_results: bool | None = None,
    ):
        self.conn = conn

        self.use_audio_features = settings.MUSIC_DISCOVERY_USE_AUDIO_FEATURES if use_audio_features is None else bool(use_audio_features)
        self.use_deep = settings.MUSIC_DISCOVERY_USE_DEEP_FEATURES if use_deep is None else bool(use_deep)
        self.min_confidence = settings.MUSIC_DISCOVERY_MIN_CONFIDENCE if min_confidence is None else _clip01(min_confidence)
        self.explain_results = settings.MUSIC_DISCOVERY_EXPLAIN_RESULTS if explain_results is None else bool(explain_results)

    def analysis_state(self) -> dict:
        if self.conn:
            total = self.conn.execute("SELECT COUNT(*) c FROM pistas WHERE estado='biblioteca'").fetchone()["c"]
            ready = self.conn.execute("SELECT COUNT(*) c FROM track_audio_features WHERE analysis_status='ready'").fetchone()["c"]
        else:
            total = obtener_una_fila("SELECT COUNT(*) c FROM pistas WHERE estado='biblioteca'")["c"]
            ready = obtener_una_fila("SELECT COUNT(*) c FROM track_audio_features WHERE analysis_status='ready'")["c"]
        
        ready_deep = 0
        if self._table_exists("track_deep_audio_features"):
            if self.conn:
                ready_deep = self.conn.execute("SELECT COUNT(*) c FROM track_deep_audio_features WHERE analysis_status='ready'").fetchone()["c"]
            else:
                ready_deep = obtener_una_fila("SELECT COUNT(*) c FROM track_deep_audio_features WHERE analysis_status='ready'")["c"]


        pct = (ready / total) if total else 0.0
        return {
            "total_tracks": total,
            "ready_features": ready,
            "ready_deep": ready_deep,
            "percentage": pct,
            "has_features": ready > 0,
            "use_audio_features": self.use_audio_features,
            "use_deep": self.use_deep,
        }

    def discover(self, query: str, limit: int = 25) -> dict:
        parsed = parse_query(query)
        limit = max(1, int(limit or settings.MUSIC_DISCOVERY_DEFAULT_LIMIT))
        warnings = []
        if parsed.intent == "generic":
            return self._empty(
                query,
                parsed,
                warnings,
                understood=False,
                user_message=NO_INTENT_MESSAGE,
            )

        if not self.use_audio_features:
            warnings.append("Music Discovery está configurado sin Audio Features; no hay ranking musical local.")
            return self._empty(query, parsed, warnings)

        rows = self._fetch_feature_rows()
        if not rows:
            warnings.append("No hay Audio Features listas para discovery.")
            return self._empty(query, parsed, warnings)

        results = []
        for row in rows:
            item = dict(row)
            score, why, origin = self._score_row(parsed.intent, item, parsed.weights)
            confidence = score
            if confidence < self.min_confidence:
                continue
            titulo = item.get("titulo") or ""
            artista = item.get("artista_nombre") or ""
            album = item.get("album_titulo") or ""
            portada = svc_bib._resolver_portada_fila(
                item.get("album_portada_ruta") or "",
                item.get("album_mb_release_id"),
            )
            metrics = self._metricas_row(item)
            result = {
                "track_id": str(item.get("track_id")),
                "id": int(item.get("track_id") or 0),
                "title": titulo,
                "titulo": titulo,
                "artist": artista,
                "artista_nombre": artista,
                "album": album,
                "album_titulo": album,
                "album_id": int(item.get("album_id") or 0),
                "artista_id": int(item.get("artista_id") or 0),
                "duracion_seg": item.get("duracion_seg"),
                "favorita": int(item.get("favorita") or 0),
                "ruta_archivo": item.get("ruta_archivo") or "",
                "portada_ruta": portada,
                "album_portada_ruta": portada,
                "score": round(score, 4),
                "confidence": round(confidence, 4),
                "why": why[:4],
                "explanation": "; ".join(why[:4]) if self.explain_results else "",
                "origin": origin,
                "source": origin,
                "feature_summary": {
                    "bpm": item.get("bpm"),
                    "energy": item.get("energy"),
                    "valence_proxy": item.get("valence_proxy"),
                    "danceability_proxy": item.get("danceability_proxy"),
                    "deep_valence": item.get("deep_valence"),
                    "deep_arousal": item.get("deep_arousal"),
                },
                "actions": {
                    "play": True,
                    "queue": True,
                    "open_album": bool(item.get("album_id")),
                    "open_artist": bool(item.get("artista_id")),
                    "save_playlist": False,
                },
                "_metrics": metrics,
            }
            svc_bib._agregar_portada_display(result)
            results.append(result)

        results.sort(key=lambda item: item["score"], reverse=True)
        results_limitados = results[:limit]
        sections = self._build_sections(parsed, results_limitados)
        return {
            "query": query,
            "intent": parsed.intent,
            "interpretation": parsed.interpretation,
            "filters": {"min_confidence": self.min_confidence},
            "ranking_weights": parsed.weights,
            "results": [self._public_result(item) for item in results_limitados],
            "sections": sections,
            "understood": True,
            "user_message": "",
            "warnings": warnings,
        }

    def _empty(
        self,
        query: str,
        parsed: ParsedIntent,
        warnings: list[str],
        *,
        understood: bool = True,
        user_message: str = "",
    ) -> dict:
        return {
            "query": query,
            "intent": parsed.intent,
            "interpretation": parsed.interpretation,
            "filters": {"min_confidence": self.min_confidence},
            "ranking_weights": parsed.weights,
            "results": [],
            "sections": [],
            "understood": understood,
            "user_message": user_message,
            "warnings": warnings,
        }

    def _fetch_feature_rows(self) -> list[sqlite3.Row]:
        has_deep_table = self._table_exists("track_deep_audio_features")
        deep_columns = self._deep_select_columns()
        deep_join = "LEFT JOIN track_deep_audio_features tdf ON tdf.track_id=taf.track_id" if has_deep_table else ""
        sql = f"""
            SELECT
                p.id AS track_id,
                p.album_id,
                p.artista_id,
                p.titulo,
                p.artista_nombre,
                p.album_titulo,
                p.ruta_archivo,
                p.duracion_seg,
                p.favorita,
                al.portada_ruta AS album_portada_ruta,
                al.mb_release_id AS album_mb_release_id,
                taf.bpm,
                taf.energy,
                taf.melancholy_proxy,
                taf.valence_proxy,
                taf.brightness,
                taf.party_score_proxy,
                taf.danceability_proxy,
                taf.workout_score_proxy,
                taf.calmness_proxy,
                taf.focus_score_proxy,
                taf.night_score_proxy,
                taf.darkness_proxy,
                taf.aggressiveness_proxy,
                {deep_columns}
            FROM pistas p
            JOIN track_audio_features taf ON taf.track_id=CAST(p.id AS TEXT)
            LEFT JOIN albums al ON al.id=p.album_id
            {deep_join}
            WHERE p.estado='biblioteca' AND taf.analysis_status='ready'
            """
        if self.conn:
            return self.conn.execute(sql).fetchall()
        return obtener_filas(sql)



    def _deep_select_columns(self) -> str:
        columns = self._columns("track_deep_audio_features")

        def expr(name: str, alias: str) -> str:
            if name in columns and self.use_deep:
                return f"tdf.{name} AS {alias}"
            return f"NULL AS {alias}"

        parts = [
            expr("analysis_status", "deep_status"),
            expr("mood_sad", "deep_mood_sad"),
            expr("mood_happy", "deep_mood_happy"),
            expr("mood_relaxed", "deep_mood_relaxed"),
            expr("mood_aggressive", "deep_mood_aggressive"),
            expr("mood_party", "deep_mood_party"),
            expr("danceability_model", "deep_danceability"),
            expr("arousal", "deep_arousal"),
            expr("valence", "deep_valence"),
            expr("tags_json", "deep_tags_json"),
        ]
        return ",\n                ".join(parts)

    def _score_row(self, intent: str, row: dict, weights: dict | None = None) -> tuple[float, list[str], str]:
        deep_ready = self.use_deep and row.get("deep_status") == "ready"
        origin = "basic+deep" if deep_ready else "basic"
        energy = _clip01(row.get("energy"))
        valence = _clip01(row.get("valence_proxy"))
        dance = _clip01(row.get("danceability_proxy"))
        calm = _clip01(row.get("calmness_proxy"))
        melancholy = _clip01(row.get("melancholy_proxy"))
        party = _clip01(row.get("party_score_proxy"))
        workout = _clip01(row.get("workout_score_proxy"))
        focus = _clip01(row.get("focus_score_proxy"))
        night = _clip01(row.get("night_score_proxy"))
        dark = _clip01(row.get("darkness_proxy"))
        aggressive = _clip01(row.get("aggressiveness_proxy"))
        bpm = float(row.get("bpm") or 0.0)

        deep = {
            "sad": _clip01(row.get("deep_mood_sad")) if deep_ready else 0.0,
            "happy": _clip01(row.get("deep_mood_happy")) if deep_ready else 0.0,
            "relaxed": _clip01(row.get("deep_mood_relaxed")) if deep_ready else 0.0,
            "aggressive": _clip01(row.get("deep_mood_aggressive")) if deep_ready else 0.0,
            "party": _clip01(row.get("deep_mood_party")) if deep_ready else 0.0,
            "dance": _clip01(row.get("deep_danceability")) if deep_ready else 0.0,
            "valence": _clip01(row.get("deep_valence")) if deep_ready else 0.0,
            "arousal": _clip01(row.get("deep_arousal")) if deep_ready else 0.0,
        }

        def _score_intent(intent_name: str) -> tuple[float, list[str]]:
            if intent_name == "sad":
                return (
                    0.45 * melancholy + 0.25 * _inv01(valence) + 0.15 * calm + 0.15 * deep["sad"],
                    ["melancolía alta", "valence baja"],
                )
            if intent_name == "happy":
                return (
                    0.45 * valence + 0.20 * energy + 0.20 * deep["happy"] + 0.15 * _clip01(row.get("brightness")),
                    ["valence alta", "energía positiva"],
                )
            if intent_name == "party":
                return (
                    0.35 * party + 0.25 * dance + 0.20 * energy + 0.20 * max(deep["party"], deep["dance"]),
                    ["fiesta/bailable", "energía útil para moverse"],
                )
            if intent_name == "workout":
                return (
                    0.40 * workout + 0.30 * energy + 0.20 * _clip01(bpm / 170.0) + 0.10 * deep["arousal"],
                    ["energía alta", "BPM orientado a entrenamiento"],
                )
            if intent_name in {"focus", "chill"}:
                return (
                    0.35 * calm + 0.30 * focus + 0.20 * deep["relaxed"] + 0.15 * _inv01(aggressive),
                    ["calma alta", "baja agresividad"],
                )
            if intent_name == "dark":
                return (
                    0.45 * night + 0.35 * dark + 0.20 * melancholy,
                    ["perfil nocturno", "brillo bajo"],
                )
            if intent_name == "intense":
                return (
                    0.35 * aggressive + 0.30 * energy + 0.20 * deep["aggressive"] + 0.15 * deep["arousal"],
                    ["intensidad/agresividad", "energía alta"],
                )
            if intent_name == "soft":
                return (
                    0.45 * _inv01(energy) + 0.30 * calm + 0.25 * _inv01(aggressive),
                    ["energía baja", "textura suave"],
                )
            if intent_name == "fast":
                return (
                    0.70 * _clip01(bpm / 180.0) + 0.30 * energy,
                    ["BPM alto", "energía de apoyo"],
                )
            if intent_name == "slow":
                return (
                    0.65 * _inv01(bpm / 160.0) + 0.35 * calm,
                    ["BPM bajo", "calma de apoyo"],
                )
            return (
                0.30 * energy + 0.25 * valence + 0.20 * dance + 0.15 * focus + 0.10 * max(deep.values() or [0.0]),
                ["balance general de energía, valence y utilidad musical"],
            )

        intent_weights = {
            key: _clip01(value)
            for key, value in dict(weights or {}).items()
            if key in KEYWORDS
        }
        if not intent_weights:
            intent_weights = {intent if intent in KEYWORDS else "generic": 1.0}

        total_weight = sum(intent_weights.values()) or 1.0
        score = 0.0
        why: list[str] = []
        for intent_name, weight in intent_weights.items():
            parcial, razones = _score_intent(intent_name)
            score += parcial * (weight / total_weight)
            for razon in razones:
                if razon not in why:
                    why.append(razon)

        if deep_ready:
            why.append("incluye señales deep locales")
        return _clip01(score), why, origin

    def _metricas_row(self, row: dict) -> dict[str, float]:
        bpm = float(row.get("bpm") or 0.0)
        return {
            "energy": _clip01(row.get("energy")),
            "melancholy": _clip01(row.get("melancholy_proxy")),
            "valence": _clip01(row.get("valence_proxy")),
            "brightness": _clip01(row.get("brightness")),
            "party": _clip01(row.get("party_score_proxy")),
            "dance": _clip01(row.get("danceability_proxy")),
            "workout": _clip01(row.get("workout_score_proxy")),
            "calm": _clip01(row.get("calmness_proxy")),
            "focus": _clip01(row.get("focus_score_proxy")),
            "night": _clip01(row.get("night_score_proxy")),
            "dark": _clip01(row.get("darkness_proxy")),
            "aggressive": _clip01(row.get("aggressiveness_proxy")),
            "bpm": bpm,
            "bpm_fast": _clip01(bpm / 180.0),
            "bpm_slow": _inv01(bpm / 160.0),
        }

    def _public_result(self, item: dict) -> dict:
        publico = dict(item)
        publico.pop("_metrics", None)
        return publico

    def _build_sections(self, parsed: ParsedIntent, results: list[dict]) -> list[dict]:
        if not results:
            return []

        specs = self._section_specs(parsed)
        if not specs:
            specs = [
                ("Selección sugerida", lambda m: m["energy"] * 0.35 + m["valence"] * 0.35 + m["dance"] * 0.30),
            ]

        sections: list[dict] = []
        usados: set[int] = set()
        for titulo, scorer in specs:
            candidatos = []
            for item in results:
                metrics = item.get("_metrics") or {}
                try:
                    valor = float(scorer(metrics))
                except (TypeError, ValueError, KeyError):
                    valor = 0.0
                if valor <= 0:
                    continue
                candidatos.append((valor, float(item.get("score") or 0.0), item))

            candidatos.sort(key=lambda par: (par[0], par[1]), reverse=True)
            pistas = []
            for _valor, _score, item in candidatos:
                item_id = int(item.get("id") or 0)
                if item_id in usados:
                    continue
                pistas.append(self._public_result(item))
                if item_id:
                    usados.add(item_id)
                if len(pistas) >= 8:
                    break

            if pistas:
                sections.append({"title": titulo, "titulo": titulo, "results": pistas, "pistas": pistas})

        if not sections and results:
            pistas = [self._public_result(item) for item in results[:8]]
            sections.append({
                "title": "Selección sugerida",
                "titulo": "Selección sugerida",
                "results": pistas,
                "pistas": pistas,
            })
        return sections

    def _section_specs(self, parsed: ParsedIntent) -> list[tuple[str, object]]:
        intents = [intent for intent in parsed.weights if intent in KEYWORDS]
        if parsed.intent != "mixed" and parsed.intent in KEYWORDS:
            intents = [parsed.intent]

        specs: list[tuple[str, object]] = []
        agregados: set[str] = set()

        def add(title: str, scorer) -> None:
            if title in agregados:
                return
            agregados.add(title)
            specs.append((title, scorer))

        for intent in intents:
            if intent == "party":
                add("Más fiesteras", lambda m: m["party"])
                add("Más bailables", lambda m: m["dance"])
                add("Más rápidas", lambda m: m["bpm_fast"])
                add("Energía alta", lambda m: m["energy"])
            elif intent == "sad":
                add("Más melancólicas", lambda m: m["melancholy"])
                add("Tristes pero suaves", lambda m: m["melancholy"] * 0.65 + m["calm"] * 0.35)
                add("Tristes con más energía", lambda m: m["melancholy"] * 0.55 + m["energy"] * 0.45)
            elif intent == "workout":
                add("Más intensas", lambda m: m["workout"] * 0.60 + m["energy"] * 0.40)
                add("Ritmo alto", lambda m: m["bpm_fast"])
                add("Energía para moverse", lambda m: m["energy"] * 0.55 + m["dance"] * 0.45)
            elif intent == "focus":
                add("Más enfocadas", lambda m: m["focus"])
                add("Tranquilas para trabajar", lambda m: m["focus"] * 0.45 + m["calm"] * 0.45 + (1.0 - m["aggressive"]) * 0.10)
                add("Baja distracción", lambda m: m["calm"] * 0.55 + (1.0 - m["aggressive"]) * 0.45)
            elif intent == "dark":
                add("Más nocturnas", lambda m: m["night"])
                add("Oscuras y calmadas", lambda m: m["dark"] * 0.55 + m["calm"] * 0.45)
                add("Suaves de noche", lambda m: m["night"] * 0.45 + m["calm"] * 0.40 + (1.0 - m["energy"]) * 0.15)
            elif intent == "chill":
                add("Más tranquilas", lambda m: m["calm"])
                add("Suaves para bajar ritmo", lambda m: m["calm"] * 0.55 + (1.0 - m["energy"]) * 0.45)
            elif intent == "happy":
                add("Para levantar ánimo", lambda m: m["valence"] * 0.60 + m["energy"] * 0.25 + m["brightness"] * 0.15)
                add("Alegres y ligeras", lambda m: m["valence"] * 0.65 + (1.0 - m["aggressive"]) * 0.35)
            elif intent == "intense":
                add("Más intensas", lambda m: m["aggressive"] * 0.55 + m["energy"] * 0.45)
                add("Energía alta", lambda m: m["energy"])
            elif intent == "soft":
                add("Más suaves", lambda m: (1.0 - m["energy"]) * 0.45 + m["calm"] * 0.35 + (1.0 - m["aggressive"]) * 0.20)
                add("Baja energía", lambda m: 1.0 - m["energy"])
            elif intent == "fast":
                add("Más rápidas", lambda m: m["bpm_fast"])
                add("Ritmo alto", lambda m: m["bpm_fast"] * 0.70 + m["energy"] * 0.30)
            elif intent == "slow":
                add("Más lentas", lambda m: m["bpm_slow"])
                add("Baja velocidad", lambda m: m["bpm_slow"] * 0.70 + m["calm"] * 0.30)
        return specs

    def _table_exists(self, table: str) -> bool:
        sql = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"
        if self.conn:
            row = self.conn.execute(sql, (table,)).fetchone()
        else:
            row = obtener_una_fila(sql, (table,))
        return row is not None



    def _columns(self, table: str) -> set[str]:
        if not self._table_exists(table):
            return set()
        sql = f"PRAGMA table_info({table})"
        if self.conn:
            return {row["name"] for row in self.conn.execute(sql).fetchall()}
        return {row["name"] for row in obtener_filas(sql)}
