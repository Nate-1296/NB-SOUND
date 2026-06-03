# =============================================================================
# servicios/dj_privado/embeddings.py
#
# Capa de embeddings del DJ Privado con FALLBACK GRACEFUL.
#
# Filosofia: la arquitectura semantica del DJ funciona SIEMPRE. Si el
# usuario tiene onnxruntime + sentence-transformers (ej. all-MiniLM-L6-v2)
# disponibles, usamos embeddings reales. Si no, usamos vectores deterministas
# derivados de la ontologia. El scheduler usa la misma interfaz en ambos casos.
#
# El proveedor deterministico NO finge ser un embedding real: produce un
# vector COMPACTO sobre las dimensiones perceptuales (ejes + conceptos) que
# permite comparar prompts y pistas de forma matematicamente consistente.
# Es suficiente para re-ranking y similaridad, sin pretender capturar
# matices linguisticos no vistos en la ontologia.
#
# Contrato publico:
#   - obtener_provider() -> EmbeddingProvider activo
#   - EmbeddingProvider.embed_texto(texto) -> list[float]
#   - EmbeddingProvider.embed_pista(features) -> list[float]
#   - similitud_coseno(a, b) -> float in [-1, 1]
# =============================================================================

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Optional, Protocol

from servicios.dj_privado.ontologia import (
    CONCEPTOS,
    EJES,
    agregar_ejes,
    buscar_conceptos,
)


# =============================================================================
# INTERFAZ
# =============================================================================

class EmbeddingProvider(Protocol):
    """Contrato comun para proveedores de embeddings."""

    @property
    def model_id(self) -> str:
        """Identificador estable del modelo. Util para invalidar cache."""
        ...

    @property
    def dim(self) -> int:
        """Dimensionalidad del vector retornado."""
        ...

    @property
    def is_real(self) -> bool:
        """True si usa un modelo neural; False si es deterministico."""
        ...

    def embed_texto(self, texto: str) -> list[float]:
        """Genera un embedding para un texto libre.

        Para textos vacios retorna un vector cero.
        El vector NO esta necesariamente normalizado (la similitud lo normaliza).
        """
        ...

    def embed_pista(self, features: dict) -> list[float]:
        """Genera un embedding para una pista a partir de sus features.

        `features` es un dict con cualquier subconjunto de:
          - bpm, energy, valence_proxy, danceability_proxy, brightness,
            darkness_proxy, calmness_proxy, melancholy_proxy, etc.
          - genero (str), mood_happy, mood_sad, mood_aggressive, ...
          - tags (lista de str), titulo, artista_nombre, album_titulo

        El provider deterministico se basa en los features numericos +
        en buscar conceptos de la ontologia en los metadatos textuales.
        El provider real concatena los textos relevantes y los embeddea.
        """
        ...


# =============================================================================
# UTILIDADES MATEMATICAS
# =============================================================================

def similitud_coseno(a: list[float], b: list[float]) -> float:
    """Similitud coseno entre dos vectores. Devuelve 0.0 si alguno es cero.

    Manejo defensivo de longitudes distintas: se trunca al menor (situacion
    que solo deberia ocurrir si se mezclan vectores de modelos distintos,
    lo cual el cache de la BD ya previene marcandolos con model_id).
    """
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for i in range(n):
        va = float(a[i])
        vb = float(b[i])
        dot += va * vb
        norm_a += va * va
        norm_b += vb * vb
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / math.sqrt(norm_a * norm_b)


def normalizar_vector(vec: list[float]) -> list[float]:
    """Normaliza a magnitud unitaria. Retorna vector cero si la norma es 0."""
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return list(vec)
    return [v / norm for v in vec]


# =============================================================================
# PROVIDER DETERMINISTICO (siempre disponible)
#
# Construye un vector sobre las dimensiones:
#   primera mitad : EJES (mismo orden que ontologia.EJES)
#   segunda mitad : CONCEPTOS (presencia/ausencia)
#
# Para texto: buscar conceptos, sumar ejes, marcar conceptos activos.
# Para pista: usar features numericos para ejes, derivar conceptos por tags.
# =============================================================================

class DeterministicEmbeddingProvider:
    """Embeddings deterministicos derivados de la ontologia.

    No requiere ninguna dependencia externa. Funciona sin red, sin GPU,
    sin descargar nada. La calidad esta acotada al vocabulario de la
    ontologia, pero es predecible y testeable.
    """

    MODEL_ID = "dj_deterministic_v1"

    def __init__(self) -> None:
        self._concept_index: dict[str, int] = {
            concepto.name: idx for idx, concepto in enumerate(CONCEPTOS)
        }
        self._axis_index: dict[str, int] = {nombre: idx for idx, nombre in enumerate(EJES)}
        self._dim = len(EJES) + len(CONCEPTOS)
        # Mapa de generos de tags MSD a nombres internos de concepto.
        self._mapeo_genero_a_concepto = _construir_mapeo_genero_concepto()

    @property
    def model_id(self) -> str:
        return self.MODEL_ID

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def is_real(self) -> bool:
        return False

    def embed_texto(self, texto: str) -> list[float]:
        vec = [0.0] * self._dim
        if not texto:
            return vec
        matches = buscar_conceptos(texto)
        if not matches:
            return vec
        axes_acumulados = agregar_ejes(matches)
        for eje, valor in axes_acumulados.items():
            idx = self._axis_index.get(eje)
            if idx is not None:
                vec[idx] = valor
        # Marcamos presencia de conceptos (segunda mitad)
        offset = len(EJES)
        for match in matches:
            idx = self._concept_index.get(match.concepto.name)
            if idx is not None:
                vec[offset + idx] = match.concepto.perceptual_weight
        return vec

    def embed_pista(self, features: dict) -> list[float]:
        vec = [0.0] * self._dim
        if not features:
            return vec

        # ---- 1. Mapear features numericos a ejes ----
        # Estos mapeos son intencionalmente directos. Cada feature de la BD
        # mapea a un eje perceptual conocido.
        mapeos = {
            "energy": "energy",
            "danceability_proxy": "danceability",
            "danceability_model": "danceability",
            "valence_proxy": "euphoria",
            "valence": "euphoria",
            "arousal_proxy": "energy",
            "arousal": "energy",
            "calmness_proxy": "calmness",
            "melancholy_proxy": "melancholy",
            "brightness": "brightness",
            "darkness_proxy": "darkness",
            "aggressiveness_proxy": "aggressiveness",
            "mood_aggressive": "aggressiveness",
            "mood_relaxed": "calmness",
            "mood_happy": "euphoria",
            "mood_sad": "melancholy",
            "mood_party": "club_energy",
            "focus_score_proxy": "focus_score",
            "workout_score_proxy": "workout_score",
            "party_score_proxy": "club_energy",
            "night_score_proxy": "night_score",
        }
        for feature_key, axis_name in mapeos.items():
            valor = features.get(feature_key)
            if valor is None:
                continue
            try:
                v = float(valor)
            except (TypeError, ValueError):
                continue
            # Llevamos los proxies [0,1] al rango [-1,+1] para que coincidan
            # con la convencion de los ejes del intent (positivo atrae,
            # negativo repele). Un valor de 0.5 queda neutro.
            ajustado = (v - 0.5) * 2.0
            idx = self._axis_index.get(axis_name)
            if idx is not None:
                vec[idx] += ajustado

        # ---- 2. Genero -> concepto ----
        offset = len(EJES)
        genero = (features.get("genero") or "").strip()
        if genero:
            # Permite que un genero crudo active el concepto correspondiente.
            nombre_concepto = self._mapeo_genero_a_concepto.get(genero.lower())
            if nombre_concepto:
                idx = self._concept_index.get(nombre_concepto)
                if idx is not None:
                    vec[offset + idx] += 1.0

        # ---- 3. Tags (de track_vibe_tags o tags_json deep) ----
        tags_raw = features.get("tags") or features.get("tags_list") or ()
        if isinstance(tags_raw, str):
            try:
                tags_raw = json.loads(tags_raw)
            except json.JSONDecodeError:
                tags_raw = ()
        if isinstance(tags_raw, dict):
            # tags_json deep tiene shape {model: [{label, score}, ...]}
            flat = []
            for valor in tags_raw.values():
                if isinstance(valor, list):
                    for item in valor:
                        if isinstance(item, dict):
                            flat.append((item.get("label", ""), float(item.get("score", 0.5))))
            tags_raw = flat
        elif isinstance(tags_raw, (list, tuple)):
            # Lista simple o lista de pares
            normalized = []
            for item in tags_raw:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    normalized.append((str(item[0]), float(item[1])))
                else:
                    normalized.append((str(item), 1.0))
            tags_raw = normalized
        else:
            tags_raw = ()

        for label, score in tags_raw:
            if not label:
                continue
            # Permite que un tag active conceptos por busqueda directa en la
            # ontologia (mismo mecanismo que para texto).
            matches = buscar_conceptos(label)
            for match in matches:
                idx_c = self._concept_index.get(match.concepto.name)
                if idx_c is not None:
                    vec[offset + idx_c] += score * match.concepto.perceptual_weight
                # Tambien aplicar el efecto del concepto sobre los ejes:
                for eje, delta in match.concepto.axes.items():
                    idx_e = self._axis_index.get(eje)
                    if idx_e is not None:
                        vec[idx_e] += delta * score * 0.5

        # ---- 4. Texto enriquecido (titulo, artista) ----
        # Buscar conceptos en el titulo y artista puede ayudar a detectar
        # "instrumental" en titulos como "X (Instrumental)" o atmosferas
        # como "Nocturne Op. 9".
        texto_meta = " ".join(
            str(features.get(k, "") or "")
            for k in ("titulo", "artista_nombre", "album_titulo")
        )
        if texto_meta:
            for match in buscar_conceptos(texto_meta):
                idx_c = self._concept_index.get(match.concepto.name)
                if idx_c is not None:
                    vec[offset + idx_c] += match.concepto.perceptual_weight * 0.5

        return vec


def _construir_mapeo_genero_concepto() -> dict[str, str]:
    """Construye un mapa de strings de genero (lowercase) a concepto interno.

    Recorre los conceptos que declaran genres y los registra. Permite que un
    genero "Hip-Hop" en la BD active el concepto "hip_hop" del DJ.
    """
    mapa: dict[str, str] = {}
    for concepto in CONCEPTOS:
        for genre in concepto.genres:
            mapa[genre.lower()] = concepto.name
    return mapa


# =============================================================================
# PROVIDER REAL (onnxruntime + sentence-transformers tokenizer)
#
# Si la maquina del usuario tiene:
#   - onnxruntime
#   - tokenizers (HuggingFace) o un tokenizer simple
#   - un modelo onnx de embeddings de oracion ligero (ej. MiniLM)
#
# Lo cargamos. Si no, no fallamos: simplemente reportamos no_disponible.
#
# Esta implementacion es defensiva: no descarga modelos automaticamente
# (eso requiere consentimiento explicito via setting). Si el modelo no
# existe en disco, no se inicializa.
# =============================================================================

class OnnxEmbeddingProvider:
    """Embeddings reales con onnxruntime + tokenizer HuggingFace.

    Requiere que el modelo este descargado previamente en una ruta conocida
    (no hace fetch automatico). La ruta se resuelve por:
      1. settings.DJ_EMBEDDING_MODEL_DIR
      2. variable de entorno DJ_EMBEDDING_MODEL_DIR
      3. ~/.local/share/nb_sound/dj_embedding/

    Espera dos archivos en esa carpeta:
      - model.onnx
      - tokenizer.json
    """

    MODEL_ID_PREFIX = "dj_onnx:"

    def __init__(self, model_dir: Path) -> None:
        import onnxruntime as ort  # type: ignore[import-not-found]
        from tokenizers import Tokenizer  # type: ignore[import-not-found]

        self._model_dir = model_dir
        self._session = ort.InferenceSession(
            str(model_dir / "model.onnx"),
            providers=["CPUExecutionProvider"],
        )
        self._tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        # Inferir dim a partir de un encoding pequeno
        sample = self._embed_textos(["test"])
        self._dim_real = len(sample[0]) if sample else 384
        # Hash del directorio para invalidar cache si el modelo cambia
        hasher = hashlib.sha256()
        for name in ("model.onnx", "tokenizer.json"):
            archivo = model_dir / name
            if archivo.exists():
                hasher.update(name.encode())
                hasher.update(str(archivo.stat().st_mtime_ns).encode())
        self._model_id = self.MODEL_ID_PREFIX + hasher.hexdigest()[:12]

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dim(self) -> int:
        return self._dim_real

    @property
    def is_real(self) -> bool:
        return True

    def embed_texto(self, texto: str) -> list[float]:
        if not texto:
            return [0.0] * self._dim_real
        out = self._embed_textos([texto])
        return out[0] if out else [0.0] * self._dim_real

    def embed_pista(self, features: dict) -> list[float]:
        # Concatena los metadatos textuales mas un resumen de los ejes.
        partes: list[str] = []
        for key in ("titulo", "artista_nombre", "album_titulo", "genero"):
            valor = (features.get(key) or "").strip()
            if valor:
                partes.append(valor)
        tags_raw = features.get("tags") or ()
        if isinstance(tags_raw, (list, tuple)):
            for item in tags_raw:
                if isinstance(item, (list, tuple)) and item:
                    partes.append(str(item[0]))
                elif isinstance(item, str):
                    partes.append(item)
        texto = ". ".join(partes)
        return self.embed_texto(texto)

    def _embed_textos(self, textos: list[str]) -> list[list[float]]:
        """Tokeniza, ejecuta el modelo y aplica mean pooling sobre tokens."""
        import numpy as np  # type: ignore[import-not-found]

        encodings = [self._tokenizer.encode(t) for t in textos]
        max_len = max((len(e.ids) for e in encodings), default=0)
        if max_len == 0:
            return [[0.0] * self._dim_real for _ in textos]
        max_len = min(max_len, 256)  # truncar a 256 tokens (suficiente)
        ids = np.zeros((len(encodings), max_len), dtype=np.int64)
        mask = np.zeros((len(encodings), max_len), dtype=np.int64)
        for i, enc in enumerate(encodings):
            length = min(len(enc.ids), max_len)
            ids[i, :length] = enc.ids[:length]
            mask[i, :length] = 1
        feed = {
            "input_ids": ids,
            "attention_mask": mask,
        }
        # Algunos modelos requieren token_type_ids
        input_names = {inp.name for inp in self._session.get_inputs()}
        if "token_type_ids" in input_names:
            feed["token_type_ids"] = np.zeros_like(ids)
        outputs = self._session.run(None, feed)
        # outputs[0] suele tener shape (batch, seq, hidden)
        hidden = outputs[0]
        if hidden.ndim == 3:
            # Mean pooling con mascara
            mask_expanded = mask[..., None].astype(np.float32)
            summed = (hidden * mask_expanded).sum(axis=1)
            counts = np.clip(mask_expanded.sum(axis=1), 1e-9, None)
            pooled = summed / counts
        else:
            pooled = hidden
        return [row.astype(float).tolist() for row in pooled]


# =============================================================================
# RESOLUCION DEL PROVIDER ACTIVO
# =============================================================================

_provider_singleton: Optional[EmbeddingProvider] = None
_provider_lock_estado: dict[str, str] = {"backend": "", "detalle": ""}


def _resolver_model_dir() -> Optional[Path]:
    """Localiza el directorio del modelo ONNX. Retorna None si no existe."""
    try:
        from config import settings
        rutas_candidatas: list[Path] = []
        atributo = getattr(settings, "DJ_EMBEDDING_MODEL_DIR", "")
        if atributo:
            rutas_candidatas.append(Path(atributo).expanduser())
        import os
        env_val = os.environ.get("DJ_EMBEDDING_MODEL_DIR", "").strip()
        if env_val:
            rutas_candidatas.append(Path(env_val).expanduser())
        # Default convencional
        rutas_candidatas.append(Path.home() / ".local" / "share" / "nb_sound" / "dj_embedding")
        for ruta in rutas_candidatas:
            if (ruta / "model.onnx").exists() and (ruta / "tokenizer.json").exists():
                return ruta
    except Exception:
        return None
    return None


def obtener_provider(*, forzar_deterministico: bool = False) -> EmbeddingProvider:
    """Devuelve el provider activo (singleton por proceso).

    Estrategia:
      1. Si forzar_deterministico=True -> Deterministico.
      2. Intentar OnnxEmbeddingProvider si el modelo esta presente y las
         dependencias se importan. Cualquier fallo cae al deterministico.
      3. DeterministicEmbeddingProvider (siempre disponible).

    El singleton se cachea para evitar reinicializar onnx en cada llamada.
    """
    global _provider_singleton
    if _provider_singleton is not None and not forzar_deterministico:
        return _provider_singleton

    if forzar_deterministico:
        _provider_singleton = DeterministicEmbeddingProvider()
        _provider_lock_estado["backend"] = "deterministic"
        _provider_lock_estado["detalle"] = "forzado_por_caller"
        return _provider_singleton

    model_dir = _resolver_model_dir()
    if model_dir is not None:
        try:
            provider = OnnxEmbeddingProvider(model_dir)
            _provider_singleton = provider
            _provider_lock_estado["backend"] = "onnx"
            _provider_lock_estado["detalle"] = str(model_dir)
            return provider
        except ImportError as e:
            _provider_lock_estado["detalle"] = f"imports_faltantes:{e}"
        except Exception as e:
            _provider_lock_estado["detalle"] = f"onnx_init_fallo:{e}"
    else:
        _provider_lock_estado["detalle"] = "modelo_no_presente"

    _provider_singleton = DeterministicEmbeddingProvider()
    _provider_lock_estado["backend"] = "deterministic"
    return _provider_singleton


def estado_provider() -> dict:
    """Diagnostico legible del backend activo. No fuerza la inicializacion."""
    provider_actual = _provider_singleton
    info = {
        "inicializado": provider_actual is not None,
        "model_id": provider_actual.model_id if provider_actual else "",
        "dim": provider_actual.dim if provider_actual else 0,
        "is_real": provider_actual.is_real if provider_actual else False,
    }
    info.update(_provider_lock_estado)
    return info


def reset_provider() -> None:
    """Util para tests: descarta el singleton activo."""
    global _provider_singleton
    _provider_singleton = None
    _provider_lock_estado["backend"] = ""
    _provider_lock_estado["detalle"] = ""
