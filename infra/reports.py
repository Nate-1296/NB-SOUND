# =============================================================================
# infra/reports.py
#
# Generacion del informe de ejecucion final. Serializa el ResultadoEjecucion
# a JSON y lo escribe en el directorio de logs con timestamp en el nombre
# para distinguir entre ejecuciones.
#
# Novedades v3:
#   - El reporte incluye los nuevos contadores: shazam_ids, acoustid_ids,
#     ia_desempates, isrc_usados.
#   - imprimir_resumen_consola() muestra estos datos en la tabla final.
# =============================================================================

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings as _settings
from config.settings import REPORT_SUMMARY_FILE_NAME
from domain.models import ResultadoEjecucion
from infra.logger import obtener_logger
from infra.version import CLI_BANNER

_log = obtener_logger("reports")


def guardar_reporte(
    resultado: ResultadoEjecucion,
    directorio_logs: Optional[Path] = None,
) -> Path:
    """
    Serializa el resultado de ejecucion a un archivo JSON en el directorio
    de logs. El nombre incluye el timestamp para no sobreescribir reportes
    de ejecuciones anteriores.

    Returns:
        Ruta del archivo de reporte generado.
    """
    directorio = directorio_logs or _settings.DEFAULT_LOGS_DIR
    directorio.mkdir(parents=True, exist_ok=True)

    ts             = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"{ts}_{REPORT_SUMMARY_FILE_NAME}"
    ruta_reporte   = directorio / nombre_archivo

    datos = asdict(resultado)
    datos["porcentaje_exito"] = resultado.porcentaje_exito()
    datos["porcentaje_exito_limpio"] = round(
        resultado.total_aceptados / max(resultado.total_descubiertos, 1) * 100, 1
    )
    datos["total_procesados"] = resultado.total_procesados()

    try:
        with open(ruta_reporte, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        _log.info(f"Reporte guardado en: {ruta_reporte}")
    except OSError as e:
        _log.error(f"No se pudo guardar el reporte: {e}")

    return ruta_reporte


def imprimir_resumen_consola(resultado: ResultadoEjecucion) -> None:
    """
    Imprime un resumen compacto en consola al finalizar la ejecucion.
    """
    print("\n  ───────────────── RESUMEN FINAL ─────────────────")
    print("  Estado: completado (ver JSON de reporte para detalle auditable)")
    print("  ╔══════════════════════════════════════════════╗")
    print(f"  ║   REPORTE FINAL — {CLI_BANNER:<24} ║")
    print("  ╠══════════════════════════════════════════════╣")
    print(f"  ║  Archivos descubiertos   : {resultado.total_descubiertos:<17}║")
    print(f"  ║  Aceptados (limpios)     : {resultado.total_aceptados:<17}║")
    print(f"  ║  Aceptados (prov.)       : {resultado.total_aceptados_provisional:<17}║")
    print(f"  ║  Enviados a revision     : {resultado.total_revision:<17}║")
    print(f"  ║  Enviados a cuarentena   : {resultado.total_cuarentena:<17}║")
    print(f"  ║  Duplicado exacto        : {resultado.total_duplicado_exacto:<17}║")
    print(f"  ║  Duplicado semantico     : {resultado.total_duplicado_semantico:<17}║")
    print(f"  ║  Duplicado mejorable     : {resultado.total_duplicado_mejorable:<17}║")
    print(f"  ║  Omitidos                : {resultado.total_omitidos:<17}║")
    print(f"  ║  Errores reales          : {resultado.total_errores:<17}║")
    print(f"  ║  Total procesados        : {resultado.total_procesados():<17}║")
    print("  ╠══════════════════════════════════════════════╣")
    exito_limpio = round(resultado.total_aceptados / max(resultado.total_descubiertos, 1) * 100, 1)
    print(f"  ║  Exito limpio            : {exito_limpio:<16.1f}%║")
    print(f"  ║  Exito total (c/prov.)   : {resultado.porcentaje_exito():<16.1f}%║")
    print("  ╠══════════════════════════════════════════════╣")
    print(f"  ║  Identificados Shazam    : {resultado.total_identificados_shazam:<17}║")
    print(f"  ║  Identificados AcoustID  : {resultado.total_identificados_acoustid:<17}║")
    print(f"  ║  ISRC utilizados         : {resultado.total_isrc_usados:<17}║")
    print(f"  ║  Desempates por IA       : {resultado.total_desempatados_ia:<17}║")
    print("  ╠══════════════════════════════════════════════╣")
    print(f"  ║  Consultas MB            : {resultado.consultas_mb:<17}║")
    print(f"  ║  Cache hits              : {resultado.cache_hits:<17}║")
    print(f"  ║  Reintentos MB           : {resultado.reintentos_mb:<17}║")
    if resultado.segunda_fase_habilitada:
        print("  ╠══════════════════════════════════════════════╣")
        print(f"  ║  Fase 2 rev. inicial     : {resultado.total_revision_inicial:<17}║")
        print(f"  ║  Fase 2 cuar. inicial    : {resultado.total_cuarentena_inicial:<17}║")
        print(f"  ║  Fase 2 elegibles        : {resultado.segunda_fase_elegibles:<17}║")
        print(f"  ║  Fase 2 excluidos        : {resultado.segunda_fase_excluidos:<17}║")
        print(f"  ║  Fase 2 promovidos       : {resultado.segunda_fase_resueltos:<17}║")
        print(f"  ║  Fase 2 tiempo           : {resultado.segunda_fase_duracion_seg:<14.1f}s ║")
    if resultado.tercera_fase_habilitada:
        print("  ╠══════════════════════════════════════════════╣")
        print(f"  ║  Fase 3 elegibles        : {resultado.tercera_fase_elegibles:<17}║")
        print(f"  ║  Fase 3 promovidos       : {resultado.tercera_fase_promovidos:<17}║")
        print(f"  ║  Fase 3 -> revision      : {resultado.tercera_fase_mejorados_revision:<17}║")
        print(f"  ║  Fase 3 sin cambios      : {resultado.tercera_fase_sin_cambio:<17}║")
        print(f"  ║  Fase 3 tiempo           : {resultado.tercera_fase_duracion_seg:<14.1f}s ║")
    if resultado.segunda_fase_habilitada or resultado.tercera_fase_habilitada:
        print("  ╠══════════════════════════════════════════════╣")
        print(f"  ║  Revision final          : {resultado.total_revision:<17}║")
        print(f"  ║  Cuarentena final        : {resultado.total_cuarentena:<17}║")
    print(f"  ║  Duracion total          : {resultado.duracion_total_seg:<14.1f}s ║")
    print("  ╚══════════════════════════════════════════════╝\n")
