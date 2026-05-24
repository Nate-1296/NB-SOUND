#!/usr/bin/env python3
# =============================================================================
# main.py
#
# Punto de entrada de NB SOUND CLI v1 por linea de comandos.
# Para ver la documentacion completa ejecuta:  python main.py --help
# =============================================================================

import sys
import tempfile
import textwrap
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
from config import settings
from infra.execution_control import ControlEjecucion
from infra.version import CLI_BANNER
from db.conexion import inicializar_db, cerrar_db, obtener_filas, obtener_una_fila


def _cerrar_db_seguro() -> None:
    try:
        cerrar_db()
    except RuntimeError:
        return
    except Exception as exc:
        print(f"Advertencia: no se pudo cerrar la conexión SQLite: {exc}", file=sys.stderr)


# =============================================================================
# TEXTO DE AYUDA
# =============================================================================

_DESCRIPCION = textwrap.dedent(f"""\
  {CLI_BANNER} — Catalogador inteligente de bibliotecas de audio
  ──────────────────────────────────────────────────────────────
  Analiza archivos de audio (entrada multiformato, salida final MP3)
  usando fingerprints acusticos (AcoustID),
  reconocimiento de audio (Shazam), consultas a MusicBrainz y,
  cuando hay ambiguedad, desempate con IA. Organiza la biblioteca
  con tags canónicos y estructura de carpetas predecible.
""")

_EPILOG = textwrap.dedent("""\
  ──────────────────────────────────────────────────────────────────────
  CONFIGURACION PERMANENTE (recomendado)
  ──────────────────────────────────────────────────────────────────────

  Edita config/settings.py — SECCION A — y rellena las rutas de usuario:

    USER_INPUT_DIR      = "/home/usuario/Descargas/musica"
    USER_LIBRARY_DIR    = "/home/usuario/Musica/biblioteca"
    USER_QUARANTINE_DIR = "/home/usuario/Musica/cuarentena"
    USER_REVIEW_DIR     = "/home/usuario/Musica/revision"
    USER_LOGS_DIR       = "/home/usuario/Musica/logs"
    USER_PROCESSED_DIR  = "/home/usuario/Musica/procesados"

  Una vez configurado puedes ejecutar simplemente:

    python main.py

  ──────────────────────────────────────────────────────────────────────
  MODULOS OPCIONALES (activan mayor precision)
  ──────────────────────────────────────────────────────────────────────

  AcoustID (fingerprint acustico):
    pip install pyacoustid
    apt install libchromaprint-tools   # o brew install chromaprint
    Clave gratuita en: https://acoustid.org/login
    Agregar en settings.py:  ACOUSTID_API_KEY = "tu_clave"

  Shazam (reconocimiento de audio):
    pip install shazamio
    No requiere clave de API.

  Desempate por IA:
    pip install anthropic
    Clave en: https://console.anthropic.com
    Agregar en settings.py:  ANTHROPIC_API_KEY = "tu_clave"

  ──────────────────────────────────────────────────────────────────────
  EJEMPLOS
  ──────────────────────────────────────────────────────────────────────

  Ejecucion basica (rutas configuradas en settings.py):
    python main.py

  Solo entrada por CLI (el resto viene de settings.py):
    python main.py --input ~/Descargas/musica

  Todas las rutas por CLI:
    python main.py \\
      --input      ~/Descargas/musica \\
      --library    ~/Musica/biblioteca \\
      --quarantine ~/Musica/cuarentena \\
      --review     ~/Musica/revision \\
      --logs       ~/Musica/logs
      --processed  ~/Musica/procesados

  Modo inspeccion (analiza pero NO modifica ni mueve nada):
    python main.py --dry-run

  Limpiar cache antes de ejecutar:
    python main.py --clear-cache

  ──────────────────────────────────────────────────────────────────────
  ESTRUCTURA DE SALIDA
  ──────────────────────────────────────────────────────────────────────

  biblioteca/
    radiohead/albums/ok_computer/01_airbag.mp3
    the_beatles/albums/abbey_road/01_come_together.mp3
    daft_punk/singles/get_lucky/01_get_lucky.mp3

  cuarentena/
    archivo_corrupto/_manifiesto.jsonl
    puntaje_bajo/_manifiesto.jsonl
    sin_candidatos/_manifiesto.jsonl
    metadata_insuficiente/_manifiesto.jsonl

  revision/
    candidatos_ambiguos/_manifiesto.jsonl
    puntaje_intermedio/_manifiesto.jsonl
    ia_revision_manual/_manifiesto.jsonl

  logs/
    tagger_run.log
    tagger_events.jsonl
    20250101_120000_tagger_summary.json

  ──────────────────────────────────────────────────────────────────────
  UMBRALES DE DECISION (ajustables en config/settings.py)
  ──────────────────────────────────────────────────────────────────────

  score >= 0.82  ->  ACEPTADO    (procesado automaticamente)
  score >= 0.55  ->  REVISION    (requiere decision manual)
  score <  0.55  ->  CUARENTENA  (preservado sin modificar)

""")


# =============================================================================
# PARSER
# =============================================================================

def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nb_sound_cli_v2",
        description=_DESCRIPCION,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True,
    )

    grupo_rutas = parser.add_argument_group(
        "RUTAS (sobreescriben config/settings.py si se pasan)"
    )

    grupo_rutas.add_argument(
        "--input", "-i",
        metavar="RUTA", type=Path,
        default=settings.DEFAULT_INPUT_DIR,
        help="Carpeta de entrada con archivos de audio soportados a procesar",
    )
    grupo_rutas.add_argument(
        "--library", "-l",
        metavar="RUTA", type=Path,
        default=settings.DEFAULT_LIBRARY_DIR,
        help="Carpeta de biblioteca organizada de salida",
    )
    grupo_rutas.add_argument(
        "--quarantine", "-q",
        metavar="RUTA", type=Path,
        default=settings.DEFAULT_QUARANTINE_DIR,
        help="Carpeta de cuarentena para archivos con problemas o puntaje bajo",
    )
    grupo_rutas.add_argument(
        "--review",
        metavar="RUTA", type=Path,
        default=settings.DEFAULT_REVIEW_DIR,
        help="Carpeta de revision manual para archivos con puntaje intermedio",
    )
    grupo_rutas.add_argument(
        "--logs",
        metavar="RUTA", type=Path,
        default=settings.DEFAULT_LOGS_DIR,
        help="Carpeta donde se guardan logs y el reporte JSON",
    )
    grupo_rutas.add_argument(
        "--processed",
        metavar="RUTA", type=Path,
        default=settings.DEFAULT_PROCESSED_DIR,
        help="Carpeta para archivar archivos ya procesados (aceptados/omitidos)",
    )
    grupo_rutas.add_argument(
        "--cache",
        metavar="RUTA", type=Path,
        default=settings.DEFAULT_CACHE_DIR,
        help="Carpeta de cache de consultas (default: ~/.cache/nb_sound)",
    )
    grupo_rutas.add_argument(
        "--temp",
        metavar="RUTA", type=Path,
        default=settings.DEFAULT_TEMP_DIR,
        help=f"Directorio temporal para escritura segura (default: {settings.DEFAULT_TEMP_DIR})",
    )

    grupo_ops = parser.add_argument_group("OPCIONES DE EJECUCION")

    grupo_ops.add_argument(
        "--dry-run",
        action="store_true", default=False,
        help="Analiza y decide pero no modifica ni mueve ningun archivo",
    )
    grupo_ops.add_argument(
        "--clear-cache",
        action="store_true", default=False,
        help="Elimina entradas de cache expiradas antes de iniciar",
    )
    grupo_ops.add_argument(
        "--version",
        action="version", version=CLI_BANNER,
    )
    grupo_ops.add_argument("--assets-only", action="store_true", help="Procesa solo el pipeline de assets sobre biblioteca existente")
    grupo_ops.add_argument("--metadata-only", action="store_true", help="Procesa identificacion/tagging sin descargar assets")
    grupo_ops.add_argument("--rebuild-manifests", action="store_true", help="Regenera manifiestos canónicos desde DB/biblioteca")
    grupo_ops.add_argument("--review-only", action="store_true", help="Reprocesa únicamente casos en revisión")
    grupo_ops.add_argument("--duplicates-only", action="store_true", help="Ejecuta chequeos de duplicados sin ingestar nuevos archivos")
    grupo_ops.add_argument("--missing-assets-only", action="store_true", help="Completa assets faltantes")
    grupo_ops.add_argument("--audit", action="store_true", help="Audita consistencia biblioteca/manifests/assets")
    grupo_ops.add_argument("--repair", action="store_true", help="Ejecuta reparaciones seguras de biblioteca")
    grupo_ops.add_argument("--explain", metavar="TARGET", help="Muestra explicación de una pista o entidad canónica")
    grupo_ops.add_argument("--discography-organize", action="store_true", help="Reorganiza biblioteca por discografía oficial de forma conservadora")
    grupo_ops.add_argument("--no-hotkeys", action="store_true", help="Desactiva atajos CLI (p=pausar/reanudar, c=cancelar+rollback)")
    grupo_ops.add_argument("--import-recovery-status", action="store_true", help="Estado y dashboard de operaciones de recuperacion")
    grupo_ops.add_argument("--assets-retry-missing", action="store_true", help="Reintenta obtener todos los assets visuales faltantes")
    grupo_ops.add_argument("--assets-retry-covers-only", action="store_true", help="Reintenta obtener SOLO carátulas de álbum y pista")
    grupo_ops.add_argument("--assets-retry-artists-only", action="store_true", help="Reintenta obtener SOLO fotos de artistas")
    grupo_ops.add_argument("--enrichment-retry-missing", action="store_true", help="Reintenta enrichment faltante (lyrics+analysis)")
    grupo_ops.add_argument("--lyrics-retry-missing", action="store_true", help="Reintenta SOLO obtencion de lyrics faltantes")
    grupo_ops.add_argument("--sidecars-retry-failed", action="store_true", help="Reintenta assets y enrichment faltantes/retryable")
    grupo_ops.add_argument("--audio-features-analyze", action="store_true", help="Analiza audio features locales pendientes")
    grupo_ops.add_argument("--audio-features-status", action="store_true", help="Estado de audio features")
    grupo_ops.add_argument("--audio-features-reanalyze", action="store_true", help="Reanaliza audio features")
    grupo_ops.add_argument("--audio-intelligence-deep", action="store_true", help="Ejecuta Audio Intelligence profunda opcional")
    grupo_ops.add_argument("--audio-intelligence-deep-status", action="store_true", help="Estado de Audio Intelligence deep background")
    grupo_ops.add_argument("--audio-intelligence-deep-resume", action="store_true", help="Reanuda jobs pendientes de Audio Intelligence deep background")
    grupo_ops.add_argument("--audio-intelligence-deep-pause", action="store_true", help="Pausa Audio Intelligence deep background")
    grupo_ops.add_argument("--audio-intelligence-deep-cancel-keep", action="store_true", help="Cancela deep background conservando avances listos")
    grupo_ops.add_argument("--audio-intelligence-deep-cancel-discard", action="store_true", help="Cancela deep background descartando outputs de la corrida")
    grupo_ops.add_argument("--audio-intelligence-deep-retry-failed", action="store_true", help="Reintenta jobs deep fallidos si quedan intentos disponibles")
    grupo_ops.add_argument("--audio-features-retry-failed", action="store_true", help="Reintenta audio features faltantes o fallidas")

    grupo_ops.add_argument("--music-discovery", metavar="CONSULTA", help="Consulta natural musical")
    grupo_ops.add_argument("--limit", type=int, default=25, help="Límite para --music-discovery")
    grupo_ops.add_argument("--all", action="store_true", help="Aplicar comando de análisis a toda la biblioteca")

    return parser


# =============================================================================
# VALIDACION DE RUTAS
# =============================================================================

_RUTAS_REQUERIDAS = {
    "--input / -i":    "input",
    "--library / -l":  "library",
    "--quarantine/-q": "quarantine",
    "--review":        "review",
    "--logs":          "logs",
}


def validar_rutas(args: argparse.Namespace) -> list[str]:
    """Retorna lista de argumentos obligatorios no configurados."""
    return [
        nombre_arg
        for nombre_arg, attr in _RUTAS_REQUERIDAS.items()
        if getattr(args, attr, None) is None
    ]


def imprimir_error_rutas_faltantes(faltantes: list[str]) -> None:
    print("\n  ERROR: Las siguientes rutas son obligatorias y no estan configuradas:\n")
    for nombre in faltantes:
        print(f"    {nombre}")
    print()
    print("  Opciones para solucionarlo:\n")
    print("  1) Pasar las rutas directamente en el comando:")
    print("       python main.py --input /ruta/audio --library /ruta/biblioteca \\")
    print("                      --quarantine /ruta/cuarentena --review /ruta/revision \\")
    print("                      --logs /ruta/logs\n")
    print("  2) Configurar valores permanentes en config/settings.py (SECCION A):")
    print("       USER_INPUT_DIR      = \"/home/usuario/Descargas/musica\"")
    print("       USER_LIBRARY_DIR    = \"/home/usuario/Musica/biblioteca\"")
    print("       USER_QUARANTINE_DIR = \"/home/usuario/Musica/cuarentena\"")
    print("       USER_REVIEW_DIR     = \"/home/usuario/Musica/revision\"")
    print("       USER_LOGS_DIR       = \"/home/usuario/Musica/logs\"")
    print()
    print("  Para ver la ayuda completa:  python main.py --help\n")


def verificar_solapamiento_rutas(args: argparse.Namespace) -> list[str]:
    """Detecta si alguna ruta de salida esta dentro del directorio de entrada."""
    advertencias = []
    dir_entrada   = args.input

    rutas_salida = {
        "library":    args.library,
        "quarantine": args.quarantine,
        "review":     args.review,
        "logs":       args.logs,
        "processed":  args.processed,
        "cache":      args.cache,
        "temp":       args.temp,
    }

    for nombre, ruta in rutas_salida.items():
        if ruta is None:
            continue
        try:
            ruta.relative_to(dir_entrada)
            advertencias.append(
                f"  ADVERTENCIA: --{nombre} ({ruta}) esta dentro de "
                f"--input ({dir_entrada}). Puede causar que el programa "
                f"procese sus propios archivos generados."
            )
        except ValueError:
            continue

    return advertencias


def validar_configuracion_operativa() -> list[str]:
    errores: list[str] = []
    if settings.MB_REQUEST_TIMEOUT <= 0:
        errores.append("MB_REQUEST_TIMEOUT debe ser > 0")
    if settings.MB_MAX_RETRIES < 0:
        errores.append("MB_MAX_RETRIES no puede ser negativo")
    if settings.CACHE_TTL_SECONDS <= 0:
        errores.append("CACHE_TTL_SECONDS debe ser > 0")
    if settings.CACHE_TTL_NEGATIVE_SECONDS <= 0:
        errores.append("CACHE_TTL_NEGATIVE_SECONDS debe ser > 0")
    if settings.INIT_COMPONENT_MAX_RETRIES < 0:
        errores.append("INIT_COMPONENT_MAX_RETRIES no puede ser negativo")
    if settings.INIT_COMPONENT_RETRY_BACKOFF_SEG <= 0:
        errores.append("INIT_COMPONENT_RETRY_BACKOFF_SEG debe ser > 0")
    if settings.SHAZAM_TIMEOUT_SEG <= 0:
        errores.append("SHAZAM_TIMEOUT_SEG debe ser > 0")
    if settings.SECOND_STAGE_MAX_CANDIDATES <= 0:
        errores.append("SECOND_STAGE_MAX_CANDIDATES debe ser > 0")
    if not (0.0 <= settings.SECOND_STAGE_MIN_EVIDENCE <= 1.0):
        errores.append("SECOND_STAGE_MIN_EVIDENCE debe estar entre 0 y 1")
    if settings.SECOND_STAGE_MIN_GAP < 0:
        errores.append("SECOND_STAGE_MIN_GAP no puede ser negativo")
    if not (0.0 <= settings.THIRD_STAGE_MIN_EVIDENCE <= 1.0):
        errores.append("THIRD_STAGE_MIN_EVIDENCE debe estar entre 0 y 1")
    if settings.THIRD_STAGE_MIN_GAP < 0:
        errores.append("THIRD_STAGE_MIN_GAP no puede ser negativo")
    if not (0.0 <= settings.DISCOGRAPHY_IA_MIN_CONFIDENCE <= 1.0):
        errores.append("DISCOGRAPHY_IA_MIN_CONFIDENCE debe estar entre 0 y 1")
    if settings.ASSETS_TIMEOUT_SEG <= 0:
        errores.append("ASSETS_TIMEOUT_SEG debe ser > 0")
    if settings.ASSETS_MAX_RETRIES < 0:
        errores.append("ASSETS_MAX_RETRIES no puede ser negativo")
    if settings.ASSETS_RETRY_BACKOFF_SEG <= 0:
        errores.append("ASSETS_RETRY_BACKOFF_SEG debe ser > 0")
    if settings.DUPLICATE_POLICY not in {
        "skip_keep_existing",
        "replace_if_better",
        "merge_assets_only",
        "prefer_existing_if_canonical",
        "prefer_new_if_quality_higher",
    }:
        errores.append("DUPLICATE_POLICY invalida")
    if settings.ENABLE_IA_TIEBREAK and settings.IA_PROVEEDOR == "OpenAI" and not settings.OPENAI_API_KEY_RESOLVED:
        errores.append("IA habilitada con OpenAI pero OPENAI_API_KEY no esta configurada")
    if settings.ENABLE_IA_TIEBREAK and settings.IA_PROVEEDOR == "Anthropic" and not settings.ANTHROPIC_API_KEY_RESOLVED:
        errores.append("IA habilitada con Anthropic pero ANTHROPIC_API_KEY no esta configurada")
    if settings.AUDIO_FEATURES_MODE not in {"light", "standard"}:
        errores.append("AUDIO_FEATURES_MODE debe ser light o standard")
    if settings.AUDIO_FEATURES_MAX_WORKERS < 1:
        errores.append("AUDIO_FEATURES_MAX_WORKERS debe ser >= 1")
    if settings.AUDIO_FEATURES_SEGMENT_SECONDS <= 0:
        errores.append("AUDIO_FEATURES_SEGMENT_SECONDS debe ser > 0")
    if settings.AUDIO_FEATURES_SAMPLE_STRATEGY not in {"smart_segments", "first_segment", "middle_segment", "full_track"}:
        errores.append("AUDIO_FEATURES_SAMPLE_STRATEGY invalida")
    if settings.AUDIO_INTELLIGENCE_BACKEND not in {"none", "essentia", "essentia_tensorflow", "essentia-tensorflow"}:
        errores.append("AUDIO_INTELLIGENCE_BACKEND debe ser none o essentia_tensorflow")
    if settings.AUDIO_INTELLIGENCE_MAX_WORKERS < 1:
        errores.append("AUDIO_INTELLIGENCE_MAX_WORKERS debe ser >= 1")
    if settings.AUDIO_INTELLIGENCE_BACKGROUND_BATCH_SIZE < 1:
        errores.append("AUDIO_INTELLIGENCE_BACKGROUND_BATCH_SIZE debe ser >= 1")
    if settings.AUDIO_INTELLIGENCE_BACKGROUND_IDLE_DELAY_SEC < 0:
        errores.append("AUDIO_INTELLIGENCE_BACKGROUND_IDLE_DELAY_SEC no puede ser negativo")
    if settings.AUDIO_INTELLIGENCE_BACKGROUND_MAX_RUNTIME_MIN < 0:
        errores.append("AUDIO_INTELLIGENCE_BACKGROUND_MAX_RUNTIME_MIN no puede ser negativo")
    if settings.AUDIO_INTELLIGENCE_MAX_ATTEMPTS < 1:
        errores.append("AUDIO_INTELLIGENCE_MAX_ATTEMPTS debe ser >= 1")
    if settings.AUDIO_INTELLIGENCE_SEGMENT_SECONDS <= 0:
        errores.append("AUDIO_INTELLIGENCE_SEGMENT_SECONDS debe ser > 0")
    if settings.AUDIO_INTELLIGENCE_SAMPLE_STRATEGY not in {"smart_segments", "first_segment", "middle_segment", "full_track"}:
        errores.append("AUDIO_INTELLIGENCE_SAMPLE_STRATEGY invalida")
    if (
        settings.ENABLE_AUDIO_INTELLIGENCE_DEEP
        and not settings.AUDIO_INTELLIGENCE_ALLOW_MODEL_DOWNLOADS
        and settings.AUDIO_INTELLIGENCE_BACKEND not in {"none", ""}
        and not settings.AUDIO_INTELLIGENCE_MODEL_DIR
    ):
        errores.append("AUDIO_INTELLIGENCE_MODEL_DIR requerido si deep esta activo y descargas desactivadas")
    if not (0.0 <= settings.MUSIC_DISCOVERY_MIN_CONFIDENCE <= 1.0):
        errores.append("MUSIC_DISCOVERY_MIN_CONFIDENCE debe estar entre 0 y 1")
    if settings.MUSIC_DISCOVERY_DEFAULT_LIMIT <= 0:
        errores.append("MUSIC_DISCOVERY_DEFAULT_LIMIT debe ser > 0")
    return errores


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================



def _ensure_db(args):
    if not args.library:
        print("No hay biblioteca configurada. Usa --library o configura USER_LIBRARY_DIR.")
        return False
    ruta_db = args.library / "nb_sound.sqlite3"
    ruta_db.parent.mkdir(parents=True, exist_ok=True)
    inicializar_db(ruta_db)
    return True


def _print_run_progress(snapshot: dict) -> None:
    total = int(snapshot.get("total_tracks") or snapshot.get("total") or 0)
    processed = int(snapshot.get("processed_tracks") or snapshot.get("processed") or 0)
    speed = float(snapshot.get("tracks_per_minute") or 0.0)
    eta = snapshot.get("eta_human") or "desconocido"
    stage = snapshot.get("current_stage") or ""
    print(
        f"etapa={stage} progreso={processed}/{total} "
        f"velocidad={speed:.2f} pistas/min ETA={eta}",
        flush=True,
    )


def _tracks_for_basic(cx, *, all_tracks: bool, reanalyze: bool):
    from core.audio_features import ANALYZER_VERSION as BASIC_ANALYZER_VERSION

    _ = cx
    where = ["p.estado='biblioteca'"]
    if not (all_tracks or reanalyze):
        clauses = ["taf.track_id IS NULL"]
        if settings.AUDIO_FEATURES_REANALYZE_ON_VERSION_CHANGE:
            clauses.append("taf.analyzer_version IS NOT NULL AND taf.analyzer_version != ?")
            clauses.append("p.hash_sha256 IS NOT NULL AND taf.file_hash IS NOT NULL AND taf.file_hash != p.hash_sha256")
            params = [BASIC_ANALYZER_VERSION]
        else:
            params = []
        where.append("(" + " OR ".join(clauses) + ")")
    else:
        params = []
    query = f"""
        SELECT p.id, p.ruta_archivo, p.hash_sha256
        FROM pistas p
        LEFT JOIN track_audio_features taf ON taf.track_id=CAST(p.id AS TEXT)
        WHERE {' AND '.join(where)}
        ORDER BY p.id
    """
    return obtener_filas(query, tuple(params))


def _tracks_for_deep(cx, *, all_tracks: bool):
    from core.audio_intelligence_deep import ANALYZER_VERSION as DEEP_ANALYZER_VERSION

    _ = cx
    where = ["p.estado='biblioteca'"]
    params = []
    if not all_tracks:
        clauses = ["tdf.track_id IS NULL"]
        if settings.AUDIO_INTELLIGENCE_REANALYZE_ON_MODEL_CHANGE:
            clauses.append("tdf.analyzer_version IS NOT NULL AND tdf.analyzer_version != ?")
            clauses.append("p.hash_sha256 IS NOT NULL AND tdf.file_hash IS NOT NULL AND tdf.file_hash != p.hash_sha256")
            params.append(DEEP_ANALYZER_VERSION)
        where.append("(" + " OR ".join(clauses) + ")")
    query = f"""
        SELECT p.id, p.ruta_archivo, p.hash_sha256
        FROM pistas p
        LEFT JOIN track_deep_audio_features tdf ON tdf.track_id=CAST(p.id AS TEXT)
        WHERE {' AND '.join(where)}
        ORDER BY p.id
    """
    return obtener_filas(query, tuple(params))

def _audio_features_status(args):
    if not _ensure_db(args):
        return
    total = obtener_una_fila("SELECT COUNT(*) c FROM pistas WHERE estado='biblioteca'")["c"]
    ready = obtener_una_fila("SELECT COUNT(*) c FROM track_audio_features WHERE analysis_status='ready'")["c"]
    rows = obtener_filas("SELECT analysis_status, COUNT(*) c FROM track_audio_features GROUP BY analysis_status")
    latest = obtener_una_fila(
        "SELECT * FROM audio_analysis_runs WHERE mode=? ORDER BY started_at DESC LIMIT 1",
        ("audio_features_basic",),
    )
    print("audio_features_status")
    print(f"- biblioteca: {total}")
    print(f"- ready: {ready}")
    print(f"- pendiente_aproximado: {max(0, total - ready)}")
    for r in rows: print(f"- {r['analysis_status']}: {r['c']}")
    if latest:
        print(
            f"- ultima_corrida: processed={latest['processed_tracks']}/{latest['total_tracks']} "
            f"ready={latest['ready_tracks']} failed={latest['failed_tracks']} "
            f"skipped={latest['skipped_tracks']} ETA={latest['eta_human'] or latest['eta_last_value'] or '0s'}"
        )
    cerrar_db()

def _audio_features_analyze(args, reanalyze=False):
    from core.audio_features import AudioFeatureAnalyzer
    from core.audio_feature_store import persist_basic_analysis
    from core.audio_analysis_runs import AudioRunTracker

    if not _ensure_db(args):
        return
    if not settings.ENABLE_AUDIO_FEATURES:
        print("Audio Features desactivado en configuración.")
        cerrar_db()
        return
    az=AudioFeatureAnalyzer()
    tracks=_tracks_for_basic(None, all_tracks=bool(args.all), reanalyze=reanalyze)
    total=len(tracks); done=0
    mode = "standard" if settings.AUDIO_FEATURES_ANALYZE_FULL_TRACK else settings.AUDIO_FEATURES_MODE
    run=AudioRunTracker(mode='audio_features_basic', config={
        'reanalyze':reanalyze,
        'all':bool(args.all),
        'analysis_mode': mode,
        'settings': {
            'ENABLE_AUDIO_FEATURES': settings.ENABLE_AUDIO_FEATURES,
            'AUDIO_FEATURES_MODE': settings.AUDIO_FEATURES_MODE,
            'AUDIO_FEATURES_ANALYZE_FULL_TRACK': settings.AUDIO_FEATURES_ANALYZE_FULL_TRACK,
            'AUDIO_FEATURES_SAMPLE_STRATEGY': settings.AUDIO_FEATURES_SAMPLE_STRATEGY,
            'AUDIO_FEATURES_SEGMENT_SECONDS': settings.AUDIO_FEATURES_SEGMENT_SECONDS,
        },
    })
    run.set_total(total)
    _print_run_progress(run.update_progress(current_stage='audio_features_basic'))
    for t in tracks:
        path = Path(t['ruta_archivo'])
        job_id=run.register_job(str(t['id']), 'basic', current_file_path=str(path), current_stage='audio_features_basic')
        r=az.analyze(str(t['id']), path, mode=mode)
        persist_basic_analysis(None, settings.DEFAULT_ASSETS_DIR, r)
        done += 1
        snapshot = run.finish_job(
            job_id,
            'ready' if r.analysis_status=='ready' else 'failed',
            r.error_code or '',
            r.error_message or '',
            current_track_id=str(t['id']),
            current_file_path=str(path),
            current_stage='audio_features_basic',
        )
        _print_run_progress(snapshot)
    summary=run.finish()
    print(
        f"audio_features_run etapa=final progreso={done}/{total} "
        f"ready={summary['ready']} failed={summary['failed']} skipped={summary['skipped']} "
        f"elapsed_ms={summary['elapsed_ms']} ETA={summary['eta_human']}"
    )
    cerrar_db()

def _music_discovery(args):
    from core.music_discovery_service import MusicDiscoveryService

    try:
        if not _ensure_db(args):
            return
        if not settings.ENABLE_MUSIC_DISCOVERY:
            print("Music Discovery desactivado en configuración.")
            cerrar_db(); return
        svc=MusicDiscoveryService(
            None,
            use_audio_features=settings.MUSIC_DISCOVERY_USE_AUDIO_FEATURES,
            use_deep=settings.MUSIC_DISCOVERY_USE_DEEP_FEATURES,
            min_confidence=settings.MUSIC_DISCOVERY_MIN_CONFIDENCE,
            explain_results=settings.MUSIC_DISCOVERY_EXPLAIN_RESULTS,
        )
        st=svc.analysis_state()
        if st['total_tracks']==0:
            print('Biblioteca vacía: no hay pistas indexadas.')
            cerrar_db(); return
        if not st['has_features']:
            print('No hay audio features disponibles. Ejecuta --audio-features-analyze primero.')
            cerrar_db(); return
        limit = int(args.limit or settings.MUSIC_DISCOVERY_DEFAULT_LIMIT)
        out=svc.discover(args.music_discovery or '', limit=limit)
        print(
            f"music_discovery etapa=consulta progreso={st['ready_features']}/{st['total_tracks']} "
            f"features={st['percentage']:.0%} deep_ready={st.get('ready_deep', 0)}"
        )
        print("\n--- Resultados de Music Discovery ---")
        if not out.get("results"):
            print("No se encontraron resultados para la consulta.")
        else:
            for idx, res in enumerate(out["results"], start=1):
                track = res.get("track", {})
                print(f"{idx}. {track.get('titulo', 'Desconocido')} - {track.get('artista_principal', 'Desconocido')}")
                print(f"   Score: {res.get('final_score', 0):.2f} (Base: {res.get('base_score', 0):.2f}, Bonus: {res.get('bonus', 0):.2f})")
                print(f"   Ruta:  {track.get('ruta_archivo', '')}")
                if res.get('explanation'):
                    print(f"   Razón: {res.get('explanation')}")
                print()
    except Exception as exc:
        print(f'Music Discovery no disponible: {exc}')
    finally:
        _cerrar_db_seguro()


def _audio_intelligence_deep(args):
    from core.audio_intelligence_deep import EssentiaTensorflowAnalyzer, persist_deep_analysis
    from core.audio_analysis_runs import AudioRunTracker

    try:
        if not _ensure_db(args):
            return
        if not settings.ENABLE_AUDIO_INTELLIGENCE_DEEP:
            print("Audio Intelligence profunda desactivada en configuración.")
            return
        analyzer = EssentiaTensorflowAnalyzer()
        if settings.AUDIO_INTELLIGENCE_BACKEND.strip().lower() in {"", "none"}:
            print("Advertencia: backend deep configurado como none; la corrida se marcará skipped.")
        rows = _tracks_for_deep(None, all_tracks=bool(args.all))
        total = 0
        run = AudioRunTracker(mode='audio_intelligence_deep', config={
            'all':bool(args.all),
            'settings': {
                'ENABLE_AUDIO_INTELLIGENCE_DEEP': settings.ENABLE_AUDIO_INTELLIGENCE_DEEP,
                'AUDIO_INTELLIGENCE_BACKEND': settings.AUDIO_INTELLIGENCE_BACKEND,
                'ENABLE_AUDIO_MOOD_MODELS': settings.ENABLE_AUDIO_MOOD_MODELS,
                'ENABLE_AUDIO_EMBEDDINGS': settings.ENABLE_AUDIO_EMBEDDINGS,
                'ENABLE_AUDIO_TAGGING_MODELS': settings.ENABLE_AUDIO_TAGGING_MODELS,
                'AUDIO_INTELLIGENCE_MODEL_DIR': settings.AUDIO_INTELLIGENCE_MODEL_DIR,
                'AUDIO_INTELLIGENCE_SAMPLE_STRATEGY': settings.AUDIO_INTELLIGENCE_SAMPLE_STRATEGY,
                'AUDIO_INTELLIGENCE_SEGMENT_SECONDS': settings.AUDIO_INTELLIGENCE_SEGMENT_SECONDS,
            },
        })
        run.set_total(len(rows))
        _print_run_progress(run.update_progress(current_stage='audio_intelligence_deep'))
        for row in rows:
            total += 1
            job_id = run.register_job(
                str(row["id"]),
                "deep",
                current_file_path=str(row["ruta_archivo"]),
                current_stage="audio_intelligence_deep",
            )
            out = analyzer.analyze(str(row["id"]), str(row["ruta_archivo"]))
            persist_deep_analysis(None, settings.DEFAULT_ASSETS_DIR, out, file_hash=row["hash_sha256"] or "")
            snapshot = run.finish_job(
                job_id,
                out["analysis_status"],
                out.get("error_code",""),
                out.get("error_message",""),
                current_track_id=str(row["id"]),
                current_file_path=str(row["ruta_archivo"]),
                current_stage="audio_intelligence_deep",
            )
            _print_run_progress(snapshot)
        summary = run.finish()
        print(
            f"Audio Intelligence deep completado: pistas={total} ready={summary['ready']} "
            f"failed={summary['failed']} skipped={summary['skipped']} "
            f"elapsed_ms={summary['elapsed_ms']} ETA={summary['eta_human']}"
        )
    except Exception as exc:
        print(f"Audio Intelligence deep no disponible: {exc}")
    finally:
        _cerrar_db_seguro()


def _print_deep_background_status(snapshot: dict) -> None:
    print("audio_intelligence_deep_background")
    print(f"- estado: {snapshot.get('estado', 'desconocido')}")
    print(f"- run_id: {snapshot.get('run_id', '') or '-'}")
    print(
        f"- progreso: {snapshot.get('procesadas', 0)}/{snapshot.get('total', 0)} "
        f"ready={snapshot.get('ready', 0)} failed={snapshot.get('failed', 0)} "
        f"skipped={snapshot.get('skipped', 0)} pending={snapshot.get('pendientes', 0)}"
    )
    print(f"- deep_ready_biblioteca: {snapshot.get('deep_ready', 0)}/{snapshot.get('library_total', 0)}")
    print(f"- velocidad: {float(snapshot.get('velocidad') or 0.0):.2f} pistas/min")
    print(f"- ETA: {snapshot.get('eta', 'desconocido')}")
    if snapshot.get("pista_actual"):
        print(f"- pista_actual: {snapshot.get('pista_actual')}")
    if snapshot.get("warning"):
        print(f"- warning: {snapshot.get('warning')}")
    if snapshot.get("mensaje"):
        print(f"- mensaje: {snapshot.get('mensaje')}")


def _audio_intelligence_background(args, action: str):
    try:
        if not _ensure_db(args):
            return
        from core.audio_intelligence_background import AudioIntelligenceBackgroundService

        svc = AudioIntelligenceBackgroundService()
        if action == "status":
            snapshot = svc.status()
        elif action == "resume":
            snapshot = svc.resume(reactivate_cancelled=True)
            if int(snapshot.get("pendientes") or 0) > 0:
                snapshot = svc.process_pending(reactivate_cancelled=True, enqueue_missing=False)
        elif action == "pause":
            snapshot = svc.pause()
        elif action == "cancel_keep":
            snapshot = svc.cancel_keep()
        elif action == "cancel_discard":
            snapshot = svc.cancel_discard()
        elif action == "retry_failed":
            snapshot = svc.retry_failed()
            if int(snapshot.get("pendientes") or 0) > 0:
                snapshot = svc.process_pending(force_retry_failed=True, enqueue_missing=False)
        else:
            snapshot = svc.status(warning=f"Accion desconocida: {action}")
        _print_deep_background_status(snapshot)
    except Exception as exc:
        print(f"Audio Intelligence deep background no disponible: {exc}")
    finally:
        _cerrar_db_seguro()


def _import_recovery(args, action: str):
    try:
        if not _ensure_db(args):
            return
        from core.import_recovery_service import ImportRecoveryService

        svc = ImportRecoveryService()
        if action == "status":
            snapshot = svc.status()
        elif action == "assets":
            snapshot = svc.retry_assets_missing()
        elif action == "assets_covers":
            snapshot = svc.retry_assets_missing(kinds={"track", "album"})
        elif action == "assets_artists":
            snapshot = svc.retry_assets_missing(kinds={"artist"})
        elif action == "enrichment":
            snapshot = svc.retry_enrichment_missing()
        elif action == "lyrics":
            snapshot = svc.retry_enrichment_missing(lyrics_only=True)
        elif action == "sidecars":
            snapshot = svc.retry_sidecars_failed()
        elif action == "audio_features":
            snapshot = svc.retry_audio_features_failed(include_missing=True)
        else:
            snapshot = {**svc.status(), "warning": f"Accion desconocida: {action}"}
        
        print("\n--- Estado de Diagnóstico y Recuperación Post-Import ---")
        if "mensaje" in snapshot and snapshot["mensaje"]:
            print(f"Mensaje: {snapshot['mensaje']}")
        if "warning" in snapshot and snapshot["warning"]:
            print(f"Advertencia: {snapshot['warning']}")
        
        print("\nAuditoría:")
        print(f"  - Pistas en biblioteca: {snapshot.get('library_total', 0)}")
        print(f"  - Manifests válidos:    {snapshot.get('manifests_valid', 0)}")
        print(f"  - Manifests ausentes:   {snapshot.get('manifests_missing', 0)}")

        print("\nAssets Visuales:")
        print(f"  - Pistas con todos los assets: {snapshot.get('assets_ok', 0)}")
        print(f"  - Pistas con assets faltantes: {snapshot.get('assets_missing', 0)}")
        print(f"  - Fallos en assets (retryable): {snapshot.get('assets_failed_retryable', 0)}")

        print("\nEnriquecimiento (Sidecars/Lyrics/Tags):")
        print(f"  - Pistas enriquecidas:  {snapshot.get('enrichment_ok', 0)}")
        print(f"  - Pistas sin sidecar:   {snapshot.get('enrichment_missing', 0)}")
        print(f"  - Fallos en enrichment: {snapshot.get('enrichment_failed_retryable', 0)}")
        print(f"  - Pistas con lyrics:    {snapshot.get('lyrics_ok', 0)}")
        print(f"  - Pistas sin lyrics:    {snapshot.get('lyrics_missing', 0)}")

        print("\nAudio Features:")
        print(f"  - Básicas listas: {snapshot.get('features_ready', 0)}")
        print(f"  - Básicas faltantes/fallidas: {snapshot.get('features_missing', 0) + snapshot.get('features_failed_retryable', 0)}")
        print(f"  - Profundas (Deep) listas: {snapshot.get('deep_ready', 0)}")
        print(f"  - Profundas (Deep) faltantes/fallidas: {snapshot.get('deep_missing', 0) + snapshot.get('deep_failed_retryable', 0)}")
        
        if "procesadas" in snapshot and snapshot["procesadas"] > 0:
            print("\nResultados de Reintento:")
            print(f"  - Reintentos exitosos (ready): {snapshot.get('ready', 0)}")
            print(f"  - Reintentos fallidos: {snapshot.get('failed', 0)}")
            print(f"  - Omitidos: {snapshot.get('skipped', 0)}")
        print("-" * 56 + "\n")
    except Exception as exc:
        print(f"Diagnostico/reintento post-import no disponible: {exc}")
    finally:
        _cerrar_db_seguro()


def main() -> int:
    parser = construir_parser()
    args   = parser.parse_args()

    acciones_exclusivas = [
        args.audio_features_status,
        args.audio_features_analyze,
        args.audio_features_reanalyze,
        bool(args.music_discovery),
        args.audio_intelligence_deep,
        args.audio_intelligence_deep_status,
        args.audio_intelligence_deep_resume,
        args.audio_intelligence_deep_pause,
        args.audio_intelligence_deep_cancel_keep,
        args.audio_intelligence_deep_cancel_discard,
        args.audio_intelligence_deep_retry_failed,
        args.import_recovery_status,
        args.assets_retry_missing,
        args.assets_retry_covers_only,
        args.assets_retry_artists_only,
        args.enrichment_retry_missing,
        args.lyrics_retry_missing,
        args.sidecars_retry_failed,
        args.audio_features_retry_failed,
        args.assets_only,
        args.metadata_only,
        args.rebuild_manifests,
        args.review_only,
        args.duplicates_only,
        args.missing_assets_only,
        args.audit,
        args.repair,
        bool(args.explain),
        args.discography_organize,
    ]

    if sum(bool(x) for x in acciones_exclusivas) > 1:
        print("\n  ERROR: Usa solo un modo de acción por ejecución.\n")
        return 1

    if args.audio_features_status:
        _audio_features_status(args); return 0
    if args.audio_features_analyze:
        _audio_features_analyze(args, reanalyze=False); return 0
    if args.audio_features_reanalyze:
        _audio_features_analyze(args, reanalyze=True); return 0
    if args.music_discovery:
        _music_discovery(args); return 0
    if args.audio_intelligence_deep:
        _audio_intelligence_deep(args); return 0
    if args.audio_intelligence_deep_status:
        _audio_intelligence_background(args, "status"); return 0
    if args.audio_intelligence_deep_resume:
        _audio_intelligence_background(args, "resume"); return 0
    if args.audio_intelligence_deep_pause:
        _audio_intelligence_background(args, "pause"); return 0
    if args.audio_intelligence_deep_cancel_keep:
        _audio_intelligence_background(args, "cancel_keep"); return 0
    if args.audio_intelligence_deep_cancel_discard:
        _audio_intelligence_background(args, "cancel_discard"); return 0
    if args.audio_intelligence_deep_retry_failed:
        _audio_intelligence_background(args, "retry_failed"); return 0
    if args.import_recovery_status:
        _import_recovery(args, "status"); return 0
    if args.assets_retry_missing:
        _import_recovery(args, "assets"); return 0
    if args.assets_retry_covers_only:
        _import_recovery(args, "assets_covers"); return 0
    if args.assets_retry_artists_only:
        _import_recovery(args, "assets_artists"); return 0
    if args.enrichment_retry_missing:
        _import_recovery(args, "enrichment"); return 0
    if args.lyrics_retry_missing:
        _import_recovery(args, "lyrics"); return 0
    if args.sidecars_retry_failed:
        _import_recovery(args, "sidecars"); return 0
    if args.audio_features_retry_failed:
        _import_recovery(args, "audio_features"); return 0

    errores_cfg = validar_configuracion_operativa()
    if errores_cfg:
        print("\n  ERROR: configuracion operativa invalida:\n")
        for e in errores_cfg:
            print(f"    - {e}")
        print()
        return 1

    if args.dry_run:
        settings.DRY_RUN = True
        print("\n  [MODO DRY-RUN] No se modificara ni movera ningun archivo.\n")

    modo_sin_input = (
        args.rebuild_manifests
        or args.audit
        or args.repair
        or bool(args.explain)
        or args.discography_organize
    )
    if not modo_sin_input:
        faltantes = validar_rutas(args)
        if faltantes:
            imprimir_error_rutas_faltantes(faltantes)
            return 1

        if not args.input.exists():
            print(f"\n  ERROR: El directorio de entrada no existe: {args.input}")
            print("  Verifica la ruta y vuelve a intentarlo.\n")
            return 1

        if not args.input.is_dir():
            print(f"\n  ERROR: La ruta de entrada no es un directorio: {args.input}\n")
            return 1

    advertencias = verificar_solapamiento_rutas(args)
    for adv in advertencias:
        print(adv)
    if advertencias:
        print()

    if args.clear_cache:
        from external.cache import CacheLocal
        cache     = CacheLocal(directorio=args.cache)
        eliminadas = cache.limpiar_expiradas()
        print(f"  Cache: {eliminadas} entradas expiradas eliminadas.\n")

    from core.pipeline import PipelineCatalogacion
    logs_dir = args.logs or settings.DEFAULT_LOGS_DIR or (Path(tempfile.gettempdir()) / "nb_sound_logs")
    control = ControlEjecucion(logs_dir / "run_state.json")
    tecla_thread = _iniciar_hotkeys_cli(control, habilitado=(not args.no_hotkeys))

    modo = "full"
    if args.rebuild_manifests:
        modo = "rebuild_manifests"
    elif args.audit:
        modo = "audit"
    elif args.repair:
        modo = "repair"
    elif args.explain:
        modo = "explain"
    elif args.assets_only:
        modo = "assets_only"
    elif args.metadata_only:
        modo = "metadata_only"
    elif args.review_only:
        modo = "review_only"
    elif args.duplicates_only:
        modo = "duplicates_only"
    elif args.missing_assets_only:
        modo = "missing_assets_only"
    elif args.discography_organize:
        modo = "discography_organize"

    pipeline = PipelineCatalogacion(
        directorio_entrada=args.input,
        directorio_biblioteca=args.library,
        directorio_quarantine=args.quarantine,
        directorio_revision=args.review,
        directorio_logs=args.logs,
        directorio_procesados=args.processed,
        directorio_cache=args.cache,
        directorio_temp=args.temp,
        modo=modo,
        explain_target=args.explain,
        dry_run=args.dry_run,
        control=control,
    )

    try:
        resultado = pipeline.ejecutar()
    except KeyboardInterrupt:
        print("\n\n  Ejecucion interrumpida por el usuario.")
        return 130
    except Exception as e:
        print(f"\n  ERROR CRITICO: {e}")
        import traceback
        traceback.print_exc()
        return 1

    if resultado.total_errores > 0 and resultado.total_aceptados == 0:
        return 1
    if tecla_thread and tecla_thread.is_alive():
        tecla_thread.join(timeout=0.1)
    return 0


def _iniciar_hotkeys_cli(control: ControlEjecucion, habilitado: bool) -> threading.Thread | None:
    if not habilitado or not sys.stdin.isatty():
        return None

    print("  Atajos CLI activos: [p]=pausar/reanudar | [c]=cancelar y revertir cambios")

    def _loop() -> None:
        while not control.cancelado():
            try:
                tecla = sys.stdin.read(1)
            except Exception:
                break
            if not tecla:
                break
            tecla = tecla.lower()
            if tecla == "p":
                if control.pausa_activa():
                    control.reanudar()
                    print("\n  [control] ejecución reanudada.")
                else:
                    control.pausar("cli_hotkey")
                    print("\n  [control] ejecución pausada.")
            elif tecla == "c":
                control.cancelar("cli_hotkey")
                print("\n  [control] cancelación solicitada: iniciando rollback.")
                break

    t = threading.Thread(target=_loop, name="nb_sound_hotkeys", daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    sys.exit(main())
