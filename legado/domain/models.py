# =============================================================================
# domain/models.py
#
# Estructuras de datos centrales de NB SOUND CLI v1.
# Son la "lengua franca" entre todos los modulos: pipeline, matcher, writer,
# reportes y sistemas de auditoria hablan en estos tipos.
#
# Novedades v3:
#   - ResultadoAcoustID: grabaciones identificadas via fingerprint acustico
#   - ResultadoShazam: identificacion por reconocimiento de audio (incluye ISRC)
#   - FuenteIdentificacion: enum para rastrear de donde vino cada dato
#   - ArchivoAudio: nuevos campos para fingerprint, Shazam y AcoustID
#   - CandidatoMB: campo isrc para coincidencia exacta con fuente externa
#   - DecisionIA: resultado estructurado del modelo de desempate
#   - RevisionCausa: nuevas causas relacionadas con fuentes externas
#   - CuarentenaCausa: causa adicional para fallo de fuentes externas
# =============================================================================

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


# =============================================================================
# ENUMERACIONES DE ESTADO
# =============================================================================

class DecisionTipo(Enum):
    """Resultado de la evaluacion de un archivo por el motor de decision."""
    ACEPTADO              = "aceptado"               # Supero umbral de confianza, listo para escribir
    ACEPTADO_PROVISIONAL  = "aceptado_provisional"   # Identidad solida, clasificacion de release incompleta
    REVISION              = "revision"               # Puntaje intermedio, requiere revision humana
    CUARENTENA            = "cuarentena"             # Puntaje bajo o condicion critica, no tocar
    DUPLICADO_EXACTO      = "duplicado_exacto"       # Duplicado binario exacto
    DUPLICADO_SEMANTICO   = "duplicado_semantico"    # Misma identidad canonica (ISRC/recording)
    DUPLICADO_MEJORABLE   = "duplicado_mejorable"    # Duplicado con potencial de reemplazo
    OMITIDO               = "omitido"                # Archivo ya procesado o explicitamente excluido
    ERROR                 = "error"                  # Fallo tecnico durante el procesamiento


class CuarentenaCausa(Enum):
    """Motivo por el que un archivo fue enviado a cuarentena."""
    ARCHIVO_CORRUPTO          = "archivo_corrupto"
    ARCHIVO_MUY_PEQUENO       = "archivo_muy_pequeno"
    ARCHIVO_ILEGIBLE          = "archivo_ilegible"
    DURACION_INVALIDA         = "duracion_invalida"
    BITRATE_INSUFICIENTE      = "bitrate_insuficiente"
    METADATA_INSUFICIENTE     = "metadata_insuficiente"
    METADATA_FINAL_INVALIDA   = "metadata_final_invalida"
    SIN_CANDIDATOS            = "sin_candidatos"
    PUNTAJE_BAJO              = "puntaje_bajo"
    OWNERSHIP_INVALIDO        = "ownership_invalido"
    ESCRITURA_FALLIDA         = "escritura_fallida"
    VALIDACION_POST_ESCRITURA = "validacion_post_escritura"
    ERROR_INESPERADO          = "error_inesperado"


class RevisionCausa(Enum):
    """Motivo por el que un archivo fue enviado a revision manual."""
    PUNTAJE_INTERMEDIO      = "puntaje_intermedio"
    CANDIDATOS_AMBIGUOS     = "candidatos_ambiguos"
    OWNERSHIP_AMBIGUO       = "ownership_ambiguo"
    RELEASE_TYPE_DUDOSO     = "release_type_dudoso"
    DURACION_MARGINAL       = "duracion_marginal"
    IA_REVISION_MANUAL      = "ia_revision_manual"       # La IA decidio no elegir
    FUENTES_DISCREPANTES    = "fuentes_discrepantes"     # Shazam y AcoustID difieren
    CLASIFICACION_PROVISIONAL = "clasificacion_provisional"  # Identidad OK, release desconocido


class FuenteIdentificacion(Enum):
    """Origen de los datos de identificacion de un archivo."""
    TAG_LOCAL     = "tag_local"       # Tags ID3 existentes en el archivo
    NOMBRE_ARCHIVO = "nombre_archivo" # Inferido del nombre del archivo
    ACOUSTID      = "acoustid"        # Identificado via fingerprint acustico
    SHAZAM        = "shazam"          # Identificado via reconocimiento Shazam
    MUSICBRAINZ   = "musicbrainz"     # Confirmado por MusicBrainz
    IA            = "ia"              # Desempatado por modelo de IA


# =============================================================================
# IDENTIFICACION ACUSTICA — ACOUSTID
# =============================================================================

@dataclass
class ResultadoAcoustID:
    """
    Resultado de la consulta de fingerprint a la API de AcoustID.
    Puede incluir uno o mas recording_ids de MusicBrainz con sus scores.
    """
    recording_ids:    list[str]   = field(default_factory=list)
    scores:           list[float] = field(default_factory=list)
    fingerprint:      str         = ""    # Fingerprint crudo de Chromaprint
    duracion_seg:     Optional[float] = None
    disponible:       bool        = False  # True si el modulo pudo ejecutarse
    error:            Optional[str] = None

    @property
    def mejor_recording_id(self) -> Optional[str]:
        """Retorna el recording_id con mayor score, o None si no hay resultados."""
        if self.recording_ids and self.scores:
            idx = self.scores.index(max(self.scores))
            return self.recording_ids[idx]
        return None

    @property
    def mejor_score(self) -> float:
        return max(self.scores) if self.scores else 0.0


# =============================================================================
# IDENTIFICACION POR SHAZAM
# =============================================================================

@dataclass
class ResultadoShazam:
    """
    Resultado de la identificacion de audio via Shazam.
    Incluye titulo, artista y opcionalmente ISRC y album.
    El ISRC es extremadamente valioso para localizar la grabacion exacta en MB.
    """
    titulo:           str         = ""
    artista:          str         = ""
    isrc:             Optional[str] = None
    album:            Optional[str] = None
    anio:             Optional[int] = None
    genero:           Optional[str] = None
    disponible:       bool        = False  # True si el modulo pudo ejecutarse
    identificado:     bool        = False  # True si Shazam encontro la cancion
    error:            Optional[str] = None

    @property
    def tiene_datos_utiles(self) -> bool:
        """True si hay al menos titulo o artista reconocidos."""
        return bool(self.titulo or self.artista)


# =============================================================================
# DECISION DEL MODELO DE IA
# =============================================================================

@dataclass
class DecisionIA:
    """
    Respuesta estructurada del modelo de IA usado para desempate.
    El modelo solo puede elegir entre candidatos existentes o
    devolver revision_manual. Nunca inventa datos.
    """
    decision:     str         = ""    # "album", "single", "ep", "revision_manual"
    release_id:   Optional[str] = None
    confianza:    float       = 0.0
    razones:      list[str]   = field(default_factory=list)
    modelo_usado: str         = ""
    tokens_usados: int        = 0
    valida:       bool        = False  # True si la respuesta paso la validacion


# =============================================================================
# METADATOS CRUDOS DE UN ARCHIVO MP3
# =============================================================================

@dataclass
class MetadataCruda:
    """
    Valores extraidos directamente del archivo sin ninguna limpieza.
    Se conservan como referencia auditora durante todo el proceso.
    """
    titulo:        Optional[str]   = None
    artista:       Optional[str]   = None
    album:         Optional[str]   = None
    artista_album: Optional[str]   = None
    track_number:  Optional[str]   = None  # Puede ser '3/12', '3', etc.
    anio:          Optional[str]   = None
    genero:        Optional[str]   = None
    duracion_seg:  Optional[float] = None
    bitrate_kbps:  Optional[int]   = None
    es_vbr:        bool            = False
    sample_rate:   Optional[int]   = None
    modo:          Optional[str]   = None  # stereo, joint_stereo, mono, etc.

    # Campos editoriales ampliados
    subtitle:      Optional[str]   = None
    comment:       Optional[str]   = None
    language:      Optional[str]   = None
    website:       Optional[str]   = None
    disc_number:   Optional[str]   = None
    total_discs:   Optional[str]   = None
    original_date: Optional[str]   = None
    original_year: Optional[str]   = None

    # Créditos y obra
    composer:      Optional[str]   = None
    composer_sort: Optional[str]   = None
    lyricist:      Optional[str]   = None
    arranger:      Optional[str]   = None
    conductor:     Optional[str]   = None
    director:      Optional[str]   = None
    djmixer:       Optional[str]   = None
    engineer:      Optional[str]   = None
    mixer:         Optional[str]   = None
    producer:      Optional[str]   = None
    remixer:       Optional[str]   = None
    writer:        Optional[str]   = None
    work:          Optional[str]   = None
    performer_roles: dict[str, str] = field(default_factory=dict)

    # Letras embebidas
    lyrics_plain:  Optional[str]   = None
    lyrics_synced: Optional[str]   = None

    # IDs externos embebidos
    musicbrainz_ids: dict[str, str] = field(default_factory=dict)
    acoustid_id: Optional[str]       = None
    acoustid_fingerprint: Optional[str] = None


# =============================================================================
# METADATOS NORMALIZADOS PARA MATCHING
# =============================================================================

@dataclass
class MetadataNormalizada:
    """
    Version limpia y normalizada de los metadatos, lista para busquedas
    externas y comparaciones de matching.

    Novedades v3:
      - isrc: disponible si Shazamio lo proporciono
      - fuente_artista / fuente_titulo: rastrean de donde vino cada campo
      - confianza_identificacion: nivel de confianza global de la normalizacion
    """
    titulo:                  str          = ""
    titulo_para_match:       str          = ""    # Sin versiones, sin sufijos promo
    artista_principal:       str          = ""
    artista_para_match:      str          = ""    # Minusculas, sin acentos, sin feat
    featuring:               Optional[str] = None
    album:                   str          = ""
    album_para_match:        str          = ""
    track_number:            Optional[int] = None
    anio:                    Optional[int] = None
    duracion_seg:            Optional[float] = None
    isrc:                    Optional[str] = None  # Codigo ISRC si fue identificado

    # Trazabilidad: de donde proviene cada campo principal
    fuente_titulo:           FuenteIdentificacion = FuenteIdentificacion.TAG_LOCAL
    fuente_artista:          FuenteIdentificacion = FuenteIdentificacion.TAG_LOCAL

    # Nivel de confianza global (0-1) combinando todas las fuentes
    confianza_identificacion: float = 0.0


# =============================================================================
# ARCHIVO DE AUDIO CON SU ESTADO COMPLETO
# =============================================================================

@dataclass
class ArchivoAudio:
    """
    Representa un archivo MP3 a lo largo de todo su ciclo de procesamiento.
    Contiene ruta, metadatos crudos, normalizados, resultados de fuentes
    externas y el historial de decisiones tomadas sobre el.
    """
    ruta_original:    Path
    ruta_fuente_original: Optional[Path] = None
    tamano_bytes:     int                        = 0
    es_legible:       bool                       = False
    metadata_cruda:   Optional[MetadataCruda]    = None
    metadata_norm:    Optional[MetadataNormalizada] = None
    hash_sha256:      Optional[str]              = None   # Para detectar duplicados

    # Resultados de identificacion acustica y por Shazam
    resultado_acoustid: Optional[ResultadoAcoustID] = None
    resultado_shazam:   Optional[ResultadoShazam]   = None

    # Estado del procesamiento
    etapa_actual:     str       = "descubierto"
    errores:          list[str] = field(default_factory=list)
    advertencias:     list[str] = field(default_factory=list)

    def agregar_error(self, mensaje: str) -> None:
        self.errores.append(mensaje)

    def agregar_advertencia(self, mensaje: str) -> None:
        self.advertencias.append(mensaje)

    @property
    def nombre_archivo(self) -> str:
        return self.ruta_original.name

    @property
    def ruta_entrada(self) -> Path:
        """Ruta física de entrada que debe archivarse/reubicarse al finalizar."""
        return self.ruta_fuente_original or self.ruta_original

    @property
    def tiene_errores(self) -> bool:
        return len(self.errores) > 0

    @property
    def isrc_disponible(self) -> Optional[str]:
        """
        Retorna el ISRC si fue identificado por alguna fuente externa.
        Prioridad: Shazam > metadata normalizada.
        """
        if self.resultado_shazam and self.resultado_shazam.isrc:
            return self.resultado_shazam.isrc
        if self.metadata_norm and self.metadata_norm.isrc:
            return self.metadata_norm.isrc
        return None

    @property
    def tiene_identificacion_externa(self) -> bool:
        """True si al menos una fuente externa identifico el audio."""
        shazam_ok = (
            self.resultado_shazam is not None
            and self.resultado_shazam.identificado
        )
        acoustid_ok = (
            self.resultado_acoustid is not None
            and bool(self.resultado_acoustid.recording_ids)
        )
        return shazam_ok or acoustid_ok


# =============================================================================
# CANDIDATO DE MATCHING DESDE FUENTE EXTERNA
# =============================================================================

@dataclass
class CandidatoMB:
    """
    Representa una grabacion o release encontrado en MusicBrainz como
    candidato para ser asignado a un archivo local.

    Novedades v3:
      - isrc: si MusicBrainz tiene el ISRC de esta grabacion
      - procedencia_acoustid: indica si fue encontrado via AcoustID
    """
    # Identificadores MusicBrainz
    recording_id:          str  = ""
    release_id:            str  = ""
    release_group_id:      str  = ""

    # Datos canonicos del candidato
    titulo_oficial:        str           = ""
    artista_principal:     str           = ""
    artistas_credito:      list[str]     = field(default_factory=list)
    album_oficial:         str           = ""
    track_number:          Optional[int] = None
    track_total:           Optional[int] = None
    anio_release:          Optional[int] = None
    duracion_seg:          Optional[float] = None
    isrc:                  Optional[str] = None   # ISRC registrado en MusicBrainz

    # Tipo y status del release
    tipo_release:          str       = ""      # Album, Single, EP, etc.
    tipos_secundarios:     list[str] = field(default_factory=list)  # Live, Remix, etc.
    status_release:        str       = ""      # Official, Bootleg, Promotion, etc.
    es_oficial:            bool = False
    es_compilacion:        bool = False

    # Origen del candidato
    procedencia_acoustid:  bool = False   # True si vino de un recording_id de AcoustID

    # Puntuacion asignada por el motor
    puntaje_total:    float           = 0.0
    puntaje_detalle:  dict[str, float] = field(default_factory=dict)
    penalizaciones:   list[str]       = field(default_factory=list)


# =============================================================================
# DECISION FINAL SOBRE UN ARCHIVO
# =============================================================================

@dataclass
class DecisionArchivo:
    """
    Resultado final del motor de decision para un archivo dado.
    Determina que debe hacerse con el archivo y con que metadatos finales.

    Novedades v3:
      - decision_ia: si intervino el modelo de desempate, aqui esta su respuesta
      - fuentes_usadas: lista de fuentes que contribuyeron a la decision
    """
    tipo:              DecisionTipo
    archivo:           ArchivoAudio
    candidato_elegido: Optional[CandidatoMB] = None

    # Causa especifica si no es ACEPTADO
    causa_cuarentena:  Optional[CuarentenaCausa] = None
    causa_revision:    Optional[RevisionCausa]   = None
    mensaje_decision:  str = ""

    # Datos derivados de la decision (solo si ACEPTADO)
    ruta_destino:      Optional[Path] = None
    nombre_destino:    Optional[str]  = None
    metadata_final:    Optional[dict] = None

    # Metricas de la decision
    puntaje_maximo:    float          = 0.0
    total_candidatos:  int            = 0

    # Trazabilidad ampliada v3
    decision_ia:       Optional[DecisionIA]            = None
    fuentes_usadas:    list[FuenteIdentificacion]       = field(default_factory=list)
    esquema_explicacion: dict = field(default_factory=dict)
    override_aplicado: Optional[dict] = None
    info_duplicado: Optional[dict] = None


# =============================================================================
# RESULTADO DE UNA EJECUCION COMPLETA
# =============================================================================

@dataclass
class ResultadoEjecucion:
    """
    Acumula las metricas y resultados de una corrida completa del pipeline.
    Se serializa al final como reporte JSON.

    Novedades v3:
      - total_identificados_shazam
      - total_identificados_acoustid
      - total_desempatados_ia
    """
    timestamp_inicio:          str   = ""
    timestamp_fin:             str   = ""
    duracion_total_seg:        float = 0.0
    directorio_entrada:        str   = ""

    # Contadores por resultado
    total_descubiertos:        int   = 0
    total_aceptados:           int   = 0
    total_aceptados_provisional: int = 0  # Identidad OK, clasificacion de release provisional
    total_revision:            int   = 0
    total_cuarentena:          int   = 0
    total_duplicado_exacto:    int   = 0
    total_duplicado_semantico: int   = 0
    total_duplicado_mejorable: int   = 0
    total_revision_inicial:    int   = 0
    total_cuarentena_inicial:  int   = 0
    total_omitidos:            int   = 0
    total_errores:             int   = 0

    # Metricas de fuentes externas
    consultas_mb:              int   = 0
    cache_hits:                int   = 0
    reintentos_mb:             int   = 0
    total_identificados_shazam:   int = 0
    total_identificados_acoustid: int = 0
    total_desempatados_ia:        int = 0
    total_isrc_usados:            int = 0
    segunda_fase_habilitada:      bool = False
    segunda_fase_elegibles:       int = 0
    segunda_fase_excluidos:       int = 0
    segunda_fase_resueltos:       int = 0
    segunda_fase_duracion_seg:    float = 0.0
    tercera_fase_habilitada:      bool = False
    tercera_fase_elegibles:       int = 0
    tercera_fase_promovidos:      int = 0
    tercera_fase_mejorados_revision: int = 0
    tercera_fase_sin_cambio:      int = 0
    tercera_fase_duracion_seg:    float = 0.0

    # Metricas de rendimiento
    tiempo_promedio_seg:       float = 0.0

    # Listas de archivos por categoria (solo nombres, no rutas completas)
    archivos_aceptados:    list[str] = field(default_factory=list)
    archivos_revision:     list[str] = field(default_factory=list)
    archivos_cuarentena:   list[str] = field(default_factory=list)
    archivos_duplicados:   list[str] = field(default_factory=list)
    archivos_error:        list[str] = field(default_factory=list)

    def total_procesados(self) -> int:
        return (self.total_aceptados + self.total_aceptados_provisional +
                self.total_revision + self.total_cuarentena + self.total_errores +
                self.total_duplicado_exacto + self.total_duplicado_semantico +
                self.total_duplicado_mejorable)

    def porcentaje_exito(self) -> float:
        if self.total_descubiertos == 0:
            return 0.0
        exitos = self.total_aceptados + self.total_aceptados_provisional
        return round(exitos / self.total_descubiertos * 100, 1)
