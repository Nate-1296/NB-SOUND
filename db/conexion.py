# =============================================================================
# db/conexion.py
#
# Gestion centralizada de la conexion SQLite.
#
# Patron: singleton de conexion por proceso. Se inicializa una vez al
# arrancar la aplicacion y se cierra al salir. Todas las consultas pasan
# por get_conexion() para garantizar que siempre hay una conexion valida.
# =============================================================================

import sqlite3
import threading
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from db.esquema import CREAR_TABLAS_SQL


def _nb_sortkey(texto: Optional[str]) -> str:
    """Clave de ordenamiento alfabético consciente de alfabetos mixtos.

    `COLLATE NOCASE` ordena por punto de código: deja los diacríticos latinos
    (á, ñ, ü) y los alfabetos no latinos (cirílico, griego, CJK, árabe…) en
    posiciones incoherentes. Esta función produce una clave que:

      - Pliega los diacríticos latinos (á→a, ñ→n) para intercalarlos con su
        letra base, como espera un hispanohablante.
      - Agrupa en tres tramos por el primer carácter significativo:
        dígitos (0) → letras latinas (1) → otros alfabetos (2). Así los
        títulos en cirílico/CJK quedan **después de la Z** en orden ascendente
        (y antes de la A en descendente, que es justo el orden inverso).

    Es determinista (mismo input → mismo output), requisito para registrarla
    con `deterministic=True` y permitir que SQLite la use en índices/ORDER BY.
    """
    if texto is None:
        return "3"  # nulos al final
    s = str(texto).strip()
    if not s:
        return "3"
    descompuesto = unicodedata.normalize("NFKD", s)
    plegado = "".join(c for c in descompuesto if not unicodedata.combining(c)).casefold()
    if not plegado:
        return "3"
    primero = ""
    for c in plegado:
        if c.isalnum():
            primero = c
            break
    if not primero:
        grupo = "2"  # solo símbolos/espacios → junto a "otros"
    elif primero.isdigit():
        grupo = "0"
    elif primero.isascii() and primero.isalpha():
        grupo = "1"
    else:
        grupo = "2"
    return grupo + plegado


def _registrar_funciones_sql(conexion: sqlite3.Connection) -> None:
    """Registra funciones escalares propias en la conexión SQLite."""
    conexion.create_function("nb_sortkey", 1, _nb_sortkey, deterministic=True)

# RLock porque _aplicar_esquema puede llamar a funciones que adquieren el mismo lock.
# Las llamadas externas (ejecutar, transaccion, etc.) tambien lo usan.
_conexion_lock    = threading.RLock()
_conexion_global: Optional[sqlite3.Connection] = None
_ruta_db_global:  Optional[Path] = None


def _crear_conexion(ruta_db: Path) -> sqlite3.Connection:
    """
    Abre la conexion SQLite con check_same_thread=False para permitir acceso
    desde workers Qt (hilos Python distintos al hilo principal). La seguridad
    de concurrencia se delega al lock Python (_conexion_lock), no a SQLite.

    isolation_level=None activa el modo autocommit nativo de sqlite3: las
    transacciones se abren y cierran explicitamente con BEGIN/COMMIT/ROLLBACK.
    row_factory=sqlite3.Row permite acceso por nombre de columna en los resultados.
    """
    conexion = sqlite3.connect(
        str(ruta_db),
        check_same_thread=False,
        isolation_level=None,  # autocommit — los BEGIN/COMMIT son explicitost
    )
    conexion.row_factory = sqlite3.Row
    _registrar_funciones_sql(conexion)
    return conexion


def _es_error_corrupcion(error: Exception) -> bool:
    """Detecta errores de corrupcion de BD por mensaje de SQLite."""
    mensaje = str(error).lower()
    return "malformed" in mensaje or "not a database" in mensaje or "database disk image is malformed" in mensaje


def _mover_db_corrupta(ruta_db: Path) -> Path:
    """
    Desplaza la BD corrupta a un archivo .bak con timestamp para preservarla
    como evidencia. También mueve los archivos WAL y SHM asociados si existen,
    porque SQLite los abre por nombre derivado del path principal.
    """
    marca_tiempo = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    respaldo = ruta_db.with_suffix(f"{ruta_db.suffix}.corrupt_{marca_tiempo}.bak")
    ruta_db.replace(respaldo)

    # SQLite puede tener archivos asociados de WAL/SHM.
    for extra in (".wal", ".shm"):
        asociado = Path(str(ruta_db) + extra)
        if asociado.exists():
            asociado.replace(Path(str(respaldo) + extra))

    return respaldo


def _checkpoint_wal_seguro(conexion: sqlite3.Connection) -> None:
    """
    Ejecuta checkpoint WAL sin interrumpir arranque si el FS no soporta TRUNCATE
    o devuelve errores transitorios de I/O.
    """
    try:
        conexion.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.DatabaseError as error:
        mensaje = str(error).lower()
        if "disk i/o error" in mensaje or "readonly" in mensaje or "unable to open" in mensaje:
            print(f"[WARN] No se pudo completar WAL checkpoint: {error}")
            return
        raise


def _aplicar_esquema(conexion: sqlite3.Connection) -> None:
    """
    Aplica PRAGMAs criticos y ejecuta el DDL completo del esquema.

    PRAGMA synchronous = FULL garantiza durabilidad ante caida de proceso o
    sistema operativo. Es mas lento que NORMAL pero protege la integridad.
    busy_timeout permite que hilos en espera del lock de SQLite reintenten
    durante 30 segundos antes de lanzar OperationalError.
    WAL se usa para permitir lecturas concurrentes sin bloquear escrituras.
    Si el filesystem no soporta WAL (p.ej. NFS), cae a DELETE sin fallar.
    """
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA synchronous = FULL")
    conexion.execute("PRAGMA busy_timeout = 30000")  # 30 segundos
    
    try:
        conexion.execute("PRAGMA journal_mode = WAL")
    except sqlite3.DatabaseError as error:
        mensaje = str(error).lower()
        if "disk i/o error" in mensaje or "readonly" in mensaje or "unable to open" in mensaje:
            conexion.execute("PRAGMA journal_mode = DELETE")
        else:
            raise

    conexion.executescript(CREAR_TABLAS_SQL)
    _aplicar_migraciones_ligeras(conexion)


def _columna_existe(conexion: sqlite3.Connection, tabla: str, columna: str) -> bool:
    """Verifica la existencia de una columna via PRAGMA table_info."""
    filas = conexion.execute(f"PRAGMA table_info({tabla})").fetchall()
    return any(fila["name"] == columna for fila in filas)


def _agregar_columna_si_falta(
    conexion: sqlite3.Connection,
    tabla: str,
    columna: str,
    definicion: str,
) -> None:
    """
    Agrega una columna solo si no existe. Patron seguro para migraciones
    incrementales: idempotente y sin necesidad de tabla de versiones.
    SQLite no soporta DROP COLUMN en versiones antiguas, por lo que las
    migraciones solo agregan; nunca eliminan columnas en caliente.
    """
    if _columna_existe(conexion, tabla, columna):
        return
    conexion.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def _aplicar_migraciones_ligeras(conexion: sqlite3.Connection) -> None:
    """Agrega columnas compatibles hacia adelante sin reescribir tablas existentes."""
    for columna, definicion in {
        "subtipo": "TEXT",
        "origen": "TEXT NOT NULL DEFAULT 'usuario'",
        "auto_key": "TEXT",
        "es_anclada": "INTEGER NOT NULL DEFAULT 0",
        "visible": "INTEGER NOT NULL DEFAULT 1",
        "portada_ruta": "TEXT",
        "ultima_generacion_en": "TEXT",
        "auto_actualizable": "INTEGER NOT NULL DEFAULT 0",
        "editada_por_usuario": "INTEGER NOT NULL DEFAULT 0",
        "anclada_en": "TEXT",
    }.items():
        _agregar_columna_si_falta(conexion, "playlists", columna, definicion)

    conexion.execute("CREATE INDEX IF NOT EXISTS idx_playlists_tipo ON playlists(tipo)")
    conexion.execute("CREATE INDEX IF NOT EXISTS idx_playlists_subtipo ON playlists(subtipo)")
    conexion.execute("CREATE INDEX IF NOT EXISTS idx_playlists_auto_key ON playlists(auto_key)")
    conexion.execute("CREATE INDEX IF NOT EXISTS idx_playlists_visible ON playlists(visible)")

    _agregar_columna_si_falta(
        conexion,
        "pistas",
        "karaoke_estado",
        "TEXT NOT NULL DEFAULT 'no_procesada'",
    )
    _agregar_columna_si_falta(
        conexion,
        "pistas",
        "karaoke_ruta_instrumental",
        "TEXT",
    )
    _agregar_columna_si_falta(
        conexion,
        "pistas",
        "karaoke_actualizado_en",
        "TEXT",
    )
    _agregar_columna_si_falta(
        conexion,
        "pistas",
        "karaoke_error_codigo",
        "TEXT",
    )
    _agregar_columna_si_falta(
        conexion,
        "pistas",
        "karaoke_error_mensaje",
        "TEXT",
    )
    _agregar_columna_si_falta(
        conexion,
        "audio_analysis_jobs",
        "run_id",
        "TEXT",
    )
    _agregar_columna_si_falta(
        conexion,
        "track_deep_audio_features",
        "last_run_id",
        "TEXT",
    )
    for columna, definicion in {
        "model_version": "TEXT",
        "file_hash": "TEXT",
        "updated_at": "TEXT",
    }.items():
        _agregar_columna_si_falta(
            conexion,
            "audio_analysis_jobs",
            columna,
            definicion,
        )
    for columna, definicion in {
        "status": "TEXT DEFAULT 'pending'",
        "current_track_id": "TEXT",
        "current_file_path": "TEXT",
        "current_stage": "TEXT",
        "last_update_at": "TEXT",
        "pending_tracks": "INTEGER DEFAULT 0",
        "avg_ms_per_track": "REAL",
        "tracks_per_minute": "REAL",
        "eta_seconds": "REAL",
        "eta_human": "TEXT",
        "cancel_policy": "TEXT",
    }.items():
        _agregar_columna_si_falta(
            conexion,
            "audio_analysis_runs",
            columna,
            definicion,
        )
    # DJ Privado: trim de la ultima pista para respetar la duracion
    # objetivo (cuando la suma natural excede el objetivo, se setea este
    # valor para que el reproductor de sesion arranque la transicion
    # final aqui en vez de al final natural).
    _agregar_columna_si_falta(
        conexion,
        "dj_pistas_sesion",
        "fade_out_at_seg",
        "REAL",
    )
    conexion.execute(
        "CREATE INDEX IF NOT EXISTS idx_audio_analysis_jobs_run ON audio_analysis_jobs(run_id)"
    )
    conexion.execute(
        "CREATE INDEX IF NOT EXISTS idx_audio_analysis_jobs_deep_track ON audio_analysis_jobs(job_type, track_id, model_version, file_hash)"
    )
    conexion.execute(
        "CREATE INDEX IF NOT EXISTS idx_track_deep_audio_features_run ON track_deep_audio_features(last_run_id)"
    )

    # Ecosistema movil: columnas aditivas para deteccion de delta (sync_version)
    # y merge last-write-wins de favoritos (favorita_actualizada_en).
    # Ver docs/mobile-ecosystem.md (seccion C) y mobile-rollout-plan.md (1.1).
    _agregar_columna_si_falta(conexion, "pistas", "sync_version", "INTEGER NOT NULL DEFAULT 0")
    _agregar_columna_si_falta(conexion, "pistas", "favorita_actualizada_en", "TEXT")
    _agregar_columna_si_falta(conexion, "albums", "sync_version", "INTEGER NOT NULL DEFAULT 0")
    _agregar_columna_si_falta(conexion, "artistas", "sync_version", "INTEGER NOT NULL DEFAULT 0")
    _agregar_columna_si_falta(conexion, "playlists", "sync_version", "INTEGER NOT NULL DEFAULT 0")
    conexion.execute(
        "CREATE INDEX IF NOT EXISTS idx_pistas_sync_version ON pistas(sync_version)"
    )
    conexion.execute(
        "CREATE INDEX IF NOT EXISTS idx_albums_sync_version ON albums(sync_version)"
    )
    conexion.execute(
        "CREATE INDEX IF NOT EXISTS idx_artistas_sync_version ON artistas(sync_version)"
    )
    conexion.execute(
        "CREATE INDEX IF NOT EXISTS idx_playlists_sync_version ON playlists(sync_version)"
    )


def inicializar_db(ruta_db: Path) -> None:
    """
    Abre (o crea) la base de datos en ruta_db y aplica el esquema completo.
    Debe llamarse una sola vez al inicio de la aplicacion, antes de cualquier
    otra operacion de base de datos.

    Flujo de recuperacion ante corrupcion:
        1. Intenta abrir y aplicar esquema normalmente.
        2. Si detecta error de corrupcion, mueve el archivo a .bak con timestamp.
        3. Crea una BD nueva limpia y valida su integridad minima.
        4. Si la BD nueva tampoco pasa la validacion, lanza RuntimeError.

    El directorio padre se crea si no existe (util en primer arranque).
    Side-effect: asigna _conexion_global y _ruta_db_global al terminar.
    """
    global _conexion_global, _ruta_db_global

    with _conexion_lock:
        ruta_db.parent.mkdir(parents=True, exist_ok=True)

        try:
            conexion = _crear_conexion(ruta_db)
            # Aplicar pragmas y crear tablas
            _aplicar_esquema(conexion)
            _checkpoint_wal_seguro(conexion)
        except sqlite3.DatabaseError as error:
            if 'conexion' in locals():
                try:
                    conexion.close()
                except Exception:
                    pass

            if not _es_error_corrupcion(error):
                raise

            respaldo = _mover_db_corrupta(ruta_db)
            print(f"[WARN] BD corrupta detectada. Respaldo guardado en: {respaldo}")
            
            # Recrear BD limpia
            try:
                conexion = _crear_conexion(ruta_db)
                _aplicar_esquema(conexion)
                _checkpoint_wal_seguro(conexion)
                
                # Validar que la nueva BD es realmente válida
                try:
                    conexion.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                    print("[INFO] Nueva BD creada y validada exitosamente")
                except sqlite3.DatabaseError as e_val:
                    conexion.close()
                    raise RuntimeError(
                        f"La BD nueva no pasó validación: {e_val}. "
                        "Comprueba permisos de escritura en el directorio."
                    )
            except Exception as e_create:
                raise RuntimeError(
                    f"No se pudo crear BD nueva después de detectar corrupción: {e_create}"
                )

        _conexion_global = conexion
        _ruta_db_global  = ruta_db


def get_conexion() -> sqlite3.Connection:
    """Retorna la conexion activa. Lanza RuntimeError si no se inicializo."""
    if _conexion_global is None:
        raise RuntimeError(
            "Base de datos no inicializada. "
            "Llama a inicializar_db() antes de get_conexion()."
        )
    return _conexion_global


def ruta_db_actual() -> Optional[Path]:
    """Ruta del archivo SQLite activo (o None si no se inicializo)."""
    return _ruta_db_global


def cerrar_db() -> None:
    """
    Cierra la conexion activa de forma segura.

    Ejecuta un checkpoint WAL completo antes de cerrar para asegurar que
    todos los datos del archivo WAL esten escritos en el archivo principal.
    Ignora errores durante el cierre para no propagar excepciones al shutdown.
    """
    global _conexion_global

    with _conexion_lock:
        if _conexion_global is not None:
            try:
                _conexion_global.execute("PRAGMA wal_checkpoint(FULL)")
                _conexion_global.close()
            except Exception:
                pass
            finally:
                _conexion_global = None


def ejecutar(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    """
    Atajo para ejecutar una sentencia y retornar el cursor.
    Todas las operaciones están bajo lock para evitar race conditions.
    """
    with _conexion_lock:
        return get_conexion().execute(sql, params)


def ejecutar_y_obtener_id(sql: str, params: tuple = ()) -> int:
    """
    Ejecuta un INSERT y retorna el id de la fila creada.
    Operación bajo lock para garantizar que el ID corresponde al INSERT realizado.
    """
    with _conexion_lock:
        cur = get_conexion().execute(sql, params)
        return cur.lastrowid



def obtener_filas(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """
    Ejecuta una consulta y retorna todas las filas como una lista.
    Operación bajo lock.
    """
    with _conexion_lock:
        return get_conexion().execute(sql, params).fetchall()


def obtener_una_fila(sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
    """
    Ejecuta una consulta y retorna la primera fila o None.
    Operación bajo lock.
    """
    with _conexion_lock:
        return get_conexion().execute(sql, params).fetchone()


def ejecutar_muchos(sql: str, lista_params: list) -> None:
    """
    Atajo para executemany con una lista de parametros.
    Todas las operaciones están bajo lock para evitar race conditions.
    """
    with _conexion_lock:
        get_conexion().executemany(sql, lista_params)


@contextmanager
def transaccion():
    """
    Administrador de contexto para agrupar multiples operaciones en una sola
    transaccion atomica bajo lock.

    Uso tipico:
        with transaccion() as con:
            con.execute("INSERT ...")
            con.execute("UPDATE ...")

    El lock se mantiene durante toda la transaccion para garantizar que
    ningun otro hilo intervenga entre el BEGIN y el COMMIT/ROLLBACK.
    Ante cualquier excepcion dentro del bloque se ejecuta ROLLBACK automatico.
    """
    with _conexion_lock:
        conexion = get_conexion()
        try:
            conexion.execute("BEGIN")
            yield conexion
            conexion.execute("COMMIT")
        except Exception:
            conexion.execute("ROLLBACK")
            raise


def obtener_config(clave: str, default: str = "") -> str:
    """
    Lee un valor de config_ui por clave.

    config_ui actua como tabla clave/valor para persistir preferencias de la UI
    (volumen, tema, estado de vistas). Retorna default si la clave no existe.
    Operacion bajo lock.
    """
    with _conexion_lock:
        fila = get_conexion().execute(
            "SELECT valor FROM config_ui WHERE clave = ?", (clave,)
        ).fetchone()
    return fila["valor"] if fila else default


def guardar_config(clave: str, valor: str) -> None:
    """
    Inserta o actualiza un valor en config_ui.
    Operación UPSERT bajo lock para evitar race conditions.
    """
    with _conexion_lock:
        get_conexion().execute(
            """
            INSERT INTO config_ui(clave, valor, actualizado_en)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(clave) DO UPDATE SET
                valor = excluded.valor,
                actualizado_en = excluded.actualizado_en
            """,
            (clave, valor),
        )


# =============================================================================
# SINCRONIZACION (ecosistema movil) — contador monotonico y tombstones
#
# Helper unico para incrementar la version de sync de las entidades
# sincronizables. Centralizar el incremento aqui (en vez de repetir SQL en
# cada servicio) garantiza que todas las escrituras usen el mismo contador
# global y evita inconsistencias en el delta que consume el cliente movil.
# Ver docs/mobile-ecosystem.md (seccion B/C) y mobile-rollout-plan.md (1.2).
# =============================================================================

_CLAVE_SYNC_VERSION = "sync_version_actual"

# Tablas cuya columna `sync_version` puede actualizar `marcar_sync_version`.
# Whitelist explicita porque el nombre de tabla se interpola en el SQL: nunca
# debe provenir de entrada externa.
_TABLAS_SINCRONIZABLES = frozenset({"pistas", "albums", "artistas", "playlists"})

# Entidades validas para un tombstone (espejo logico de las tablas).
_ENTIDADES_SINCRONIZABLES = frozenset({"pista", "album", "artista", "playlist"})


def siguiente_sync_version() -> int:
    """
    Incrementa el contador global monotonico de sync y devuelve el nuevo valor.

    El contador vive en `sync_estado` como clave/valor (TEXT). Se usa un UPSERT
    atomico bajo lock para que dos escrituras concurrentes nunca obtengan el
    mismo numero. El primer incremento parte de 1.
    """
    with _conexion_lock:
        con = get_conexion()
        con.execute(
            """
            INSERT INTO sync_estado(clave, valor) VALUES (?, '1')
            ON CONFLICT(clave) DO UPDATE SET
                valor = CAST(sync_estado.valor AS INTEGER) + 1
            """,
            (_CLAVE_SYNC_VERSION,),
        )
        fila = con.execute(
            "SELECT valor FROM sync_estado WHERE clave = ?", (_CLAVE_SYNC_VERSION,)
        ).fetchone()
    return int(fila["valor"]) if fila else 0


def sync_version_actual() -> int:
    """Devuelve el valor actual del contador global sin incrementarlo."""
    with _conexion_lock:
        fila = get_conexion().execute(
            "SELECT valor FROM sync_estado WHERE clave = ?", (_CLAVE_SYNC_VERSION,)
        ).fetchone()
    return int(fila["valor"]) if fila else 0


def marcar_sync_version(tabla: str, entidad_id: int) -> int:
    """
    Asigna a la fila indicada la proxima `sync_version` global y la devuelve.

    `tabla` debe pertenecer a la whitelist `_TABLAS_SINCRONIZABLES`; cualquier
    otro valor lanza ValueError (defensa contra inyeccion via nombre de tabla).
    """
    if tabla not in _TABLAS_SINCRONIZABLES:
        raise ValueError(f"Tabla no sincronizable: {tabla!r}")
    version = siguiente_sync_version()
    with _conexion_lock:
        get_conexion().execute(
            f"UPDATE {tabla} SET sync_version = ? WHERE id = ?",
            (version, entidad_id),
        )
    return version


def registrar_tombstone(entidad: str, entidad_id: int) -> int:
    """
    Registra el borrado de una entidad sincronizable para propagarlo al cliente.

    Devuelve la `sync_version` asignada al tombstone. `entidad` debe ser una de
    `_ENTIDADES_SINCRONIZABLES`.
    """
    if entidad not in _ENTIDADES_SINCRONIZABLES:
        raise ValueError(f"Entidad no sincronizable: {entidad!r}")
    version = siguiente_sync_version()
    with _conexion_lock:
        get_conexion().execute(
            "INSERT INTO sync_tombstones(entidad, entidad_id, sync_version) VALUES (?, ?, ?)",
            (entidad, entidad_id, version),
        )
    return version
