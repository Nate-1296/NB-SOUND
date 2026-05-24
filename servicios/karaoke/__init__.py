# =============================================================================
# servicios/karaoke/__init__.py
#
# API publica del subsistema karaoke. Reexporta lo que consumen los
# modelos QML, el worker Qt y los tests. Todo lo demas es interno.
# =============================================================================

from .backend import (
    DevicePref,
    DiagnosticoBackend,
    diagnostico,
    seleccionar_device,
    validar_listo,
)
from .cola import limpiar_jobs_zombies, procesar_cola, SnapshotProceso
from .errores import (
    ArchivoNoExisteError,
    AudioCorruptoError,
    BackendNoDisponibleError,
    FfmpegFaltanteError,
    KaraokeCanceladoError,
    KaraokeError,
    MemoriaInsuficienteError,
    ModeloFaltanteError,
    TimeoutKaraokeError,
)
from .jobs_repo import (
    ESTADOS_JOB,
    ESTADOS_PISTA,
    asignar_instrumental_manual,
    contar_pendientes,
    encolar,
    encolar_muchas,
    encolar_todas_sin_preparar,
    job_activo_por_pista,
    job_por_id,
    listar_cola,
    marcar_no_aplica,
    marcar_para_reprocesar,
    resetear_estado_pista,
    restaurar_de_no_aplica,
    resumen_jobs,
    sacar_de_cola,
    ultimo_job_por_pista,
    vaciar_cola,
)
from .rutas import (
    directorio_karaoke,
    directorio_modelos,
    directorio_instrumentales,
    ruta_instrumental_para_pista,
)
from .modelo import MODELO_DEFAULT

__all__ = [
    # Backend
    "DevicePref",
    "DiagnosticoBackend",
    "diagnostico",
    "seleccionar_device",
    "validar_listo",
    # Cola
    "SnapshotProceso",
    "limpiar_jobs_zombies",
    "procesar_cola",
    # Errores
    "ArchivoNoExisteError",
    "AudioCorruptoError",
    "BackendNoDisponibleError",
    "FfmpegFaltanteError",
    "KaraokeCanceladoError",
    "KaraokeError",
    "MemoriaInsuficienteError",
    "ModeloFaltanteError",
    "TimeoutKaraokeError",
    # Jobs repo
    "ESTADOS_JOB",
    "ESTADOS_PISTA",
    "asignar_instrumental_manual",
    "contar_pendientes",
    "encolar",
    "encolar_muchas",
    "encolar_todas_sin_preparar",
    "job_activo_por_pista",
    "job_por_id",
    "listar_cola",
    "marcar_no_aplica",
    "marcar_para_reprocesar",
    "resetear_estado_pista",
    "restaurar_de_no_aplica",
    "resumen_jobs",
    "sacar_de_cola",
    "ultimo_job_por_pista",
    "vaciar_cola",
    # Rutas
    "directorio_karaoke",
    "directorio_modelos",
    "directorio_instrumentales",
    "ruta_instrumental_para_pista",
    # Modelo
    "MODELO_DEFAULT",
]
