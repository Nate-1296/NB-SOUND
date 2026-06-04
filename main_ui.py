#!/usr/bin/env python3
# =============================================================================
# main_ui.py
#
# Punto de entrada de NB SOUND UI v1.
#
# Responsabilidades:
#   1. Resolver rutas de la aplicacion (BD, QML, recursos)
#   2. Inicializar la base de datos
#   3. Instanciar todos los modelos QML y el reproductor
#   4. Exponer los modelos al contexto QML
#   5. Cargar el archivo QML principal y abrir la ventana
#
# La aplicacion puede ejecutarse con:
#   python main_ui.py
#   python main_ui.py --db /ruta/personalizada/nb_sound_ui.db
# =============================================================================

import sys
import argparse
import os
from pathlib import Path

# Asegurar que el directorio del proyecto esta en el path de Python
DIR_PROYECTO = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR_PROYECTO))


def _bootstrap_temprano() -> None:
    """Ejecuta el bootstrap del entorno antes de cualquier import dependiente.

    En instalaciones empaquetadas (PyInstaller) no hay ``.env`` junto al
    ejecutable y, sin esta llamada temprana, el orden de importaciones
    sería:

        1. Algun import de la app trae ``config.settings``.
        2. ``settings.py`` ejecuta ``load_dotenv()`` y no encuentra nada
           porque el ``.env`` del usuario aún no se ha generado.
        3. Todas las ``USER_*_DIR`` quedan vacías para esta ejecución.
        4. Luego el bootstrap genera ``.env`` en ``%APPDATA%/NBSound/``
           (o equivalente), pero ``settings`` ya cargó con valores vacíos.
        5. La UI muestra rutas recomendadas que no coinciden con las
           carpetas que el bootstrap creó, y la importación falla porque
           el directorio de entrada no existe.

    Ejecutándolo ANTES de cualquier import que toque ``config.settings``
    aseguramos que el ``.env`` esté presente cuando ``settings.py`` se
    cargue y, por tanto, los ``DEFAULT_*_DIR`` resuelvan a las rutas
    reales del sistema operativo.

    Es defensivo: si el módulo de bootstrap falla por cualquier motivo,
    el arranque continúa con valores por defecto.
    """
    try:
        from infra.bootstrap import (
            asegurar_entorno,
            primer_arranque_necesario,
            resolver_rutas_estandar,
        )
    except Exception:
        return

    rutas = resolver_rutas_estandar()
    if getattr(sys, "frozen", False):
        env_usuario = rutas.env_file
    else:
        env_usuario = DIR_PROYECTO / ".env"

    necesita = primer_arranque_necesario(env_usuario.exists(), None)
    try:
        asegurar_entorno(
            rutas,
            generar_env=necesita,
            env_destino=env_usuario if necesita else None,
        )
    except Exception:
        # No interrumpir el arranque si la creación de directorios falla
        # (permisos, FS de solo lectura). El resumen real lo emitirá
        # `_aplicar_bootstrap_si_corresponde` mas adelante.
        pass


# Bootstrap antes de cualquier import que cargue config.settings.
_bootstrap_temprano()

# Si en una ejecución previa el usuario instaló dependencias opcionales
# (torch, demucs, essentia, …) a través del wizard de plug & play, esos
# wheels viven en `<datos_usuario>/python/site-packages`. Hay que agregar
# esa ruta a sys.path antes de cualquier import opcional para que la app
# las encuentre sin reiniciar Python.
try:
    from infra.dependencias import aplicar_runtime_pip_userdir
    aplicar_runtime_pip_userdir()
except Exception:
    pass

# TORCH_HOME se setea DESPUÉS de que `_aplicar_rutas_persistidas_a_settings`
# corra (ver `inicializar_aplicacion`). Si lo seteáramos aquí, antes de
# leer las rutas del usuario, apuntaría a la cache XDG fallback en lugar
# de a la ruta que el usuario configuró (p.ej. `~/Música/cache`). Eso
# rompe Karaoke: el plug & play descarga el modelo a una ruta y el
# procesamiento lo busca en otra → "Verifica conexión a internet…".


# Aseguramos que el `bin/` empacado por PyInstaller (`_MEIPASS/bin/`,
# que en .deb queda como `/opt/nb-sound/_internal/bin/`) esté en el
# `PATH` del proceso. Sin esto, librerías como `demucs.audio` que
# invocan `subprocess.run(['ffmpeg', ...])` o `ffprobe` directamente
# por nombre pueden fallar si el entorno de lanzamiento (COSMIC,
# GNOME on Wayland, sesiones SDDM con PATH minimal) no expone
# `/usr/bin`. Caso reportado: Karaoke fallaba con "No se pudo
# decodificar X.mp3" aunque ffmpeg estaba disponible en el sistema.
try:
    _meipass_root = getattr(sys, "_MEIPASS", None)
    _bin_dir_bundle = Path(_meipass_root) / "bin" if _meipass_root else None
    if _bin_dir_bundle and _bin_dir_bundle.is_dir():
        _bin_str = str(_bin_dir_bundle)
        _path_actual = os.environ.get("PATH", "")
        _entradas_actuales = _path_actual.split(os.pathsep) if _path_actual else []
        if _bin_str not in _entradas_actuales:
            # Anteponemos el bundle (donde está nuestro ffmpeg GPL) y
            # garantizamos que `/usr/bin` / `/usr/local/bin` están en
            # PATH también — en entornos de lanzamiento sin shell
            # (COSMIC app launcher, ciertas sesiones SDDM) el PATH
            # llega vacío y subprocesses como ffprobe (que demucs
            # invoca por nombre) fallan con "audio_corrupto".
            extras = [_bin_str]
            for d in ("/usr/local/bin", "/usr/bin"):
                if d not in _entradas_actuales:
                    extras.append(d)
            os.environ["PATH"] = os.pathsep.join(
                extras + ([_path_actual] if _path_actual else [])
            )
except Exception:
    pass

from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QUrl, Qt, QTimer

from infra.logger import obtener_logger
from infra.version import UI_NAME, UI_BANNER

_log = obtener_logger("main_ui")

# =============================================================================
# RESOLVER BASE DE DATOS
# =============================================================================

def _resolver_db_default() -> Path:
    """Resuelve la ruta canónica de la base de datos compartida CLI/UI.

    Si `USER_LIBRARY_DIR` está configurado, la base de datos vive dentro de
    esa biblioteca para que CLI y UI compartan el mismo índice. En caso
    contrario, se delega a `infra.bootstrap.resolver_rutas_estandar`, que
    devuelve el directorio de datos correcto del sistema operativo.
    """
    try:
        from config import settings

        if settings.DEFAULT_LIBRARY_DIR:
            return settings.DEFAULT_LIBRARY_DIR / "nb_sound.sqlite3"
    except Exception as exc:
        _log.debug("No se pudo resolver DEFAULT_LIBRARY_DIR: %s", exc)

    try:
        from infra.bootstrap import resolver_rutas_estandar
        rutas = resolver_rutas_estandar()
        return rutas.library / "nb_sound.sqlite3"
    except Exception as exc:
        _log.debug("Bootstrap no disponible para resolver DB default: %s", exc)
        return Path.home() / "nb_sound" / "nb_sound.sqlite3"

# =============================================================================
# CONSTANTES
# =============================================================================

NOMBRE_APP   = UI_NAME
VERSION_APP  = UI_BANNER
ARCHIVO_QML  = DIR_PROYECTO / "ui" / "qml" / "Principal.qml"
RUTA_DB_DEFAULT = _resolver_db_default()

# =============================================================================
# INICIALIZACION
# =============================================================================

def _aplicar_bootstrap_si_corresponde() -> None:
    """Inicializa rutas estandar y .env minimo en el primer arranque.

    Se ejecuta antes de inicializar la BD para garantizar que el
    directorio padre del .sqlite existe (especialmente con instalaciones
    empaquetadas donde el usuario no clono el repo).
    """
    try:
        from infra.bootstrap import (
            asegurar_entorno,
            emitir_resumen,
            primer_arranque_necesario,
            resolver_rutas_estandar,
        )
    except Exception as exc:
        _log.debug("Bootstrap no disponible: %s", exc)
        return

    rutas = resolver_rutas_estandar()

    # En un bundle PyInstaller, DIR_PROYECTO apunta al directorio _internal/
    # dentro de /opt/nb-sound/ (o equivalente), que es de solo lectura.
    # El .env del usuario va siempre al directorio de configuracion del SO.
    if getattr(sys, "frozen", False):
        env_usuario = rutas.env_file
    else:
        env_usuario = DIR_PROYECTO / ".env"

    env_existe = env_usuario.exists()
    try:
        from config import settings as _settings
        library_resuelta = _settings.DEFAULT_LIBRARY_DIR
    except Exception:
        library_resuelta = None

    necesita_primer_arranque = primer_arranque_necesario(env_existe, library_resuelta)
    resultado = asegurar_entorno(
        rutas,
        generar_env=necesita_primer_arranque,
        env_destino=env_usuario if necesita_primer_arranque else None,
    )
    emitir_resumen(resultado)


def _aplicar_rutas_persistidas_a_settings() -> None:
    """Vuelca las rutas guardadas en `config_ui` sobre `config.settings`.

    Debe correr DESPUES de inicializar la BD y ANTES de construir los modelos
    QML / servicios. Sin esto, modulos como Reproductor, ModeloBiblioteca o
    EnrichmentPipeline (que en su construccion consultan
    `settings.DEFAULT_X_DIR`) obtienen el valor inicial resuelto al importar
    `config.settings` — es decir, los fallbacks XDG / AppData — aunque el
    usuario haya configurado otra cosa desde la pantalla Configuracion.

    El mapeo de claves de UI a atributos de settings es el mismo que usa
    `ModeloConfiguracion._sincronizar_settings_runtime`; mantenerlo aqui
    duplicado mantiene la inicializacion sin acoplar a la UI.
    """
    mapeo_path = {
        "dir_entrada":    "DEFAULT_INPUT_DIR",
        "dir_biblioteca": "DEFAULT_LIBRARY_DIR",
        "dir_cuarentena": "DEFAULT_QUARANTINE_DIR",
        "dir_revision":   "DEFAULT_REVIEW_DIR",
        "dir_logs":       "DEFAULT_LOGS_DIR",
        "dir_procesados": "DEFAULT_PROCESSED_DIR",
        "dir_cache":      "DEFAULT_CACHE_DIR",
        "dir_temp":       "DEFAULT_TEMP_DIR",
        "dir_assets":     "DEFAULT_ASSETS_DIR",
        "dir_manifests":  "DEFAULT_MANIFESTS_DIR",
    }
    # Claves no-Path que también deben volcarse al modulo settings antes
    # de construir los servicios. Mantener en sincronía con
    # ModeloConfiguracion._CLAVES_STR_A_SETTINGS.
    mapeo_str = {
        "audio_intelligence_model_dir": "AUDIO_INTELLIGENCE_MODEL_DIR",
        "audio_intelligence_backend":   "AUDIO_INTELLIGENCE_BACKEND",
    }
    try:
        from db.conexion import obtener_config
        from config import settings as _settings
    except Exception as exc:
        _log.debug("No se pudieron aplicar rutas persistidas a settings: %s", exc)
        return
    for clave, attr in mapeo_path.items():
        try:
            valor = obtener_config(clave, "").strip()
        except Exception:
            continue
        if not valor:
            continue
        try:
            setattr(_settings, attr, Path(valor).expanduser().resolve())
        except Exception:
            continue
    for clave, attr in mapeo_str.items():
        try:
            valor = obtener_config(clave, "").strip()
        except Exception:
            continue
        if not valor:
            continue
        try:
            setattr(_settings, attr, valor)
        except Exception:
            continue


def _promover_pesos_demucs_si_corresponde(torch_home_actual: Path) -> None:
    """Reusa pesos ya descargados aunque vivan en otro cache.

    Cuando el plug & play descargaba el modelo a la cache XDG fija
    (`~/.cache/nb_sound/karaoke/models`) y el usuario configuró una
    cache distinta (`~/Música/cache`), `cargar_modelo` no los
    encontraba y mostraba "Verifica conexión a internet…". Aquí, si
    detectamos pesos `.th` en una cache "histórica" pero no en la
    activa, los copiamos (no movemos: el cache XDG sigue válido para
    sesiones futuras con otra configuración) — operación cheap,
    ~80 MB.
    """
    try:
        destino = torch_home_actual / "hub" / "checkpoints"
        if destino.is_dir() and any(destino.glob("*.th")):
            return  # ya hay pesos en la cache activa
        from infra.bootstrap import resolver_rutas_estandar
        rutas_so = resolver_rutas_estandar()
        origen = rutas_so.cache / "karaoke" / "models" / "hub" / "checkpoints"
        if not origen.is_dir():
            return
        if origen.resolve() == destino.resolve():
            return
        pesos = list(origen.glob("*.th"))
        if not pesos:
            return
        destino.mkdir(parents=True, exist_ok=True)
        import shutil
        for peso in pesos:
            dst = destino / peso.name
            if not dst.exists():
                shutil.copy2(peso, dst)
        _log.info("Pesos Demucs promovidos a %s (%d archivo[s])", destino, len(pesos))
    except Exception as exc:
        _log.debug("No se pudieron promover pesos Demucs: %s", exc)


def inicializar_aplicacion(ruta_db: Path) -> None:
    """
    Inicializa la base de datos y crea los directorios necesarios.
    Debe llamarse antes de crear cualquier modelo QML.
    """
    _aplicar_bootstrap_si_corresponde()
    ruta_db.parent.mkdir(parents=True, exist_ok=True)
    from db.conexion import inicializar_db
    inicializar_db(ruta_db)
    # Las rutas que el usuario guardo desde Configuracion deben volcarse a
    # settings.DEFAULT_*_DIR antes de que el Reproductor / Biblioteca /
    # EnrichmentPipeline las consulten al construirse.
    _aplicar_rutas_persistidas_a_settings()
    # Inicializar el logger de archivo de la UI. Hasta ahora la UI sólo
    # escribía a stdout/stderr (que en un bundle GUI se descarta), de modo
    # que cuando algo fallaba (lyrics no encontradas, deep no progresa,
    # cierre incompleto…) no quedaba rastro en disco. Apuntar el log al
    # directorio que el usuario configuró garantiza que cualquier
    # `_log.warning(...)` futuro sea diagnosticable.
    try:
        from config import settings as _settings
        from infra.logger import inicializar_logging
        logs_dir = _settings.DEFAULT_LOGS_DIR
        if logs_dir is None:
            from infra.bootstrap import resolver_rutas_estandar
            logs_dir = resolver_rutas_estandar().logs
        inicializar_logging(Path(logs_dir))
        _log.info("UI logger inicializado. Logs en %s", logs_dir)
    except Exception as exc:
        _log.debug("No se pudo inicializar el logger de archivo: %s", exc)
    # TORCH_HOME debe apuntar al cache que el USUARIO configuró, no al
    # XDG fallback. Solo lo seteamos aquí (post-vuelco) para que coincida
    # con el `cache_dir` que `WorkerKaraokeCola` pasa a `cargar_modelo`.
    # Si el plug & play descargó el modelo en otra ruta histórica
    # (cache XDG estándar), lo "promovemos" para que la app lo encuentre
    # sin necesidad de re-descargar.
    try:
        from infra.instalador import directorio_modelos_karaoke
        _torch_home = directorio_modelos_karaoke()
        if _torch_home is not None:
            os.environ["TORCH_HOME"] = str(_torch_home)
            _promover_pesos_demucs_si_corresponde(_torch_home)
    except Exception as exc:
        _log.debug("No se pudo ajustar TORCH_HOME tras vuelco de rutas: %s", exc)
    # Incrementa el contador de aperturas; cuando cruza el umbral la
    # próxima llamada a `infra.dependencias.detectar()` revalida todo el
    # catálogo (incluso si el cache todavía no expiró por tiempo).
    try:
        from infra.dependencias import registrar_apertura
        registrar_apertura()
    except Exception:
        pass


def construir_modelos(app: QGuiApplication):
    """
    Instancia todos los modelos QML y el reproductor.
    Retorna un dict con los modelos listos para exponer al contexto QML.
    """
    from servicios.reproductor import Reproductor
    from ui.modelos_qml import (
        ModeloBiblioteca,
        ModeloReproductor,
        ModeloBusqueda,
        ModeloAudioIntelligenceBackground,
        ModeloImportacion,
        ModeloRevision,
        ModeloEstadisticas,
        ModeloPlaylists,
        ModeloConfiguracion,
        ModeloTema,
        ModeloKaraoke,
        ModeloDjPrivado,
        ModeloExploradorCiego,
        ModeloDependencias,
        ModeloSincronizacion,
    )

    reproductor_backend = Reproductor()

    modelos = {
        "biblioteca":    ModeloBiblioteca(parent=app),
        "reproductor":   ModeloReproductor(reproductor_backend, parent=app),
        "busqueda":      ModeloBusqueda(parent=app),
        "audioDeep":     ModeloAudioIntelligenceBackground(parent=app),
        "importacion":   ModeloImportacion(parent=app),
        "revision":      ModeloRevision(parent=app),
        "estadisticas":  ModeloEstadisticas(parent=app),
        "playlists":     ModeloPlaylists(parent=app),
        "configuracion": ModeloConfiguracion(parent=app),
        "karaoke":       ModeloKaraoke(parent=app),
        "djPrivado":     ModeloDjPrivado(reproductor_backend, parent=app),
        # Plug & play: detecta y permite instalar dependencias opcionales
        # (torch/demucs/essentia, modelos .pb) sin reiniciar la app.
        "dependencias": ModeloDependencias(parent=app),
    }

    # El explorador ciego necesita el modelo de reproductor ya construido
    # porque usa su capa de censura y delega reproducciones reales.
    # También recibe el modelo de biblioteca para que `alternar_favorita`
    # propague la señal `favoritaCambiada` (sincroniza Playlists "Me gusta").
    modelos["exploradorCiego"] = ModeloExploradorCiego(
        modelos["reproductor"], modelos["biblioteca"], parent=app,
    )

    # Ecosistema movil: el servidor de sincronizacion arranca BAJO DEMANDA
    # (desde la Vista de Sincronizacion), no aqui. Solo construimos el modelo
    # y le pasamos el reproductor para el puente de control remoto (WS).
    modelos["sincronizacion"] = ModeloSincronizacion(modelos["reproductor"], parent=app)

    modelos["temaUi"] = ModeloTema(modelos["configuracion"], parent=app)

    # Conecta Playlists ↔ Biblioteca para que la playlist "Me gusta"
    # se refresque en vivo cuando el usuario marca/desmarca favoritas.
    try:
        modelos["playlists"].conectar_biblioteca(modelos["biblioteca"])
    except Exception as exc:
        _log.warning("No se pudo conectar Playlists ↔ Biblioteca: %s", exc)

    # Conecta Importacion ↔ Revision: al marcar pendientes como vistos,
    # el contador del resumen del importador se refresca en vivo.
    try:
        modelos["importacion"].conectar_revision(modelos["revision"])
    except Exception as exc:
        _log.warning("No se pudo conectar Importacion ↔ Revision: %s", exc)

    # Al reintentar análisis deep desde Importación (reencola), refresca el
    # panel "Análisis musical en segundo plano" para que muestre los jobs ya
    # encolados sin pulsar refrescar manualmente.
    try:
        modelos["importacion"].deepReintentado.connect(
            lambda _n, _d=modelos.get("audioDeep"): _d and _d.refrescarAudioDeepEstado()
        )
    except Exception as exc:
        _log.warning("No se pudo conectar reintento deep ↔ audioDeep: %s", exc)

    # Conecta DJ ↔ Playlists: al guardar una sesión como playlist, la vista de
    # Playlists se refresca en vivo (sin reiniciar la app).
    try:
        modelos["djPrivado"].playlistGuardada.connect(
            lambda _pid, _pl=modelos["playlists"]: _pl.cargar()
        )
    except Exception as exc:
        _log.warning("No se pudo conectar DJ ↔ Playlists: %s", exc)

    # Cuando el barrido de duplicados oculta pistas, los contadores de Karaoke
    # y Estadísticas (Inicio) deben reflejarlo en vivo: si no, "Preparar
    # Karaoke" seguiría contando duplicados ya retirados de la biblioteca.
    def _refrescar_tras_dedupe(_resultado: dict) -> None:
        if not isinstance(_resultado, dict) or int(_resultado.get("duplicados_resueltos") or 0) <= 0:
            return
        # Inicio (estadisticas), Preparar Karaoke y el diagnóstico de Importación
        # cuentan pistas de biblioteca; deben bajar junto con las duplicadas
        # ocultadas. Biblioteca ya se recarga en el propio modelo (recargar()).
        for clave, accion in (
            ("estadisticas", "cargar"),
            ("karaoke", "cargar"),
            ("importacion", "refrescarDiagnosticoImportacion"),
        ):
            modelo = modelos.get(clave)
            metodo = getattr(modelo, accion, None) if modelo is not None else None
            if metodo is not None:
                try:
                    metodo()
                except Exception as exc:
                    _log.debug("Refresco post-dedupe (%s) falló: %s", clave, exc)
    try:
        modelos["biblioteca"].dedupeObservableFinalizado.connect(_refrescar_tras_dedupe)
    except Exception as exc:
        _log.warning("No se pudo conectar dedupe ↔ refrescos: %s", exc)

    # Conecta Importacion ↔ ExploradorCiego: cuando termina una importación
    # la vista "A Ciegas" debe ver la nueva biblioteca sin reiniciar la app.
    try:
        modelos["exploradorCiego"].conectar_importacion(modelos["importacion"])
    except Exception as exc:
        _log.warning("No se pudo conectar Importacion ↔ ExploradorCiego: %s", exc)

    # Conectar el ownership del DJ al reproductor global: cuando el usuario
    # pide reproducir algo desde la UI normal y hay una sesión DJ activa,
    # el reproductor libera al DJ antes (evita audio doble).
    try:
        modelos["reproductor"].set_ownership_dj(modelos["djPrivado"]._ownership)
    except Exception as exc:
        _log.warning("No se pudo enlazar ownership DJ→reproductor: %s", exc)

    # Cleanup ordenado al cerrar la app: detener workers/timers/VLC antes
    # de que Qt destruya los QObject. Sin esto:
    #   - Qt aborta con "QThread: Destroyed while thread is still running".
    #   - VLC puede seguir emitiendo audio aunque la ventana haya cerrado.
    #   - Callbacks de fin de pista pueden tocar objetos liberados (segfault).
    #
    # Orden: primero detenemos modelos con QThread propio (karaoke, djPrivado,
    # importacion, audioDeep, busqueda, playlists, exploradorCiego); por
    # ultimo el reproductor, porque otros modelos publican eventos a traves
    # de el durante su propio teardown.
    _ORDEN_CIERRE = (
        "dependencias",
        # El servidor de sincronizacion se detiene antes que el reproductor:
        # su hilo/event loop propio debe pararse de forma determinista y deja
        # de escuchar señales del reproductor antes de que este se destruya.
        "sincronizacion",
        "exploradorCiego",
        "karaoke",
        "djPrivado",
        "importacion",
        "audioDeep",
        "busqueda",
        "playlists",
        "biblioteca",
        "reproductor",
    )

    def _cleanup_modelos() -> None:
        for clave in _ORDEN_CIERRE:
            modelo = modelos.get(clave)
            if modelo is None or not hasattr(modelo, "cerrar"):
                continue
            try:
                modelo.cerrar()
            except Exception as exc:
                _log.warning("Cleanup '%s' fallo: %s", clave, exc)
    try:
        app.aboutToQuit.connect(_cleanup_modelos)
    except Exception as exc:
        _log.warning("No se pudo conectar cleanup a aboutToQuit: %s", exc)

    return modelos


def cablear_refrescos_post_import(modelos: dict) -> None:
    """Refresco en vivo tras una importación.

    Filosofía de la app: el usuario nunca debe reiniciar para ver
    cambios. Cuando termina una importación, los modelos siguientes
    refrescan automáticamente:

      * Reproductor → invalida cache de letras + re-lee el manifest.
        Sin esto, una pista que ya estaba en cache antes de que
        enrichment escribiera sus letras se queda con ``{}`` cacheado
        hasta el próximo arranque.
      * Estadísticas → recarga dashboard (Inicio).
      * Biblioteca → recarga grupos de albums.
      * Playlists → re-sincroniza inteligentes.
      * Karaoke → recarga (puede haber nuevas pistas).
      * audioDeep → refresca snapshot (nuevos jobs pendientes).

    Se invoca desde :func:`main` (no desde :func:`construir_modelos`),
    para que los tests que solo construyen modelos no acumulen
    conexiones globales entre runtimes (lo que hace flaky a tests QML
    runtime sensibles al orden de eventos).
    """
    try:
        imp = modelos["importacion"]
    except KeyError:
        return

    def _on_import_fin(_info: dict) -> None:
        # Re-inicializar el logger primero: `PipelineCatalogacion` llama
        # a `cerrar_logging()` en su `finally`, cerrando todos los
        # handlers. Sin esta llamada, cualquier `_log.warning` posterior
        # (karaoke, deep, DJ, reproductor) va a un logger sin handlers
        # y los errores se pierden — exactamente el síntoma que hace
        # imposible diagnosticar fallos post-importación.
        try:
            from infra.logger import inicializar_logging
            from config import settings as _s_log
            logs_dir = _s_log.DEFAULT_LOGS_DIR
            if logs_dir is None:
                from infra.bootstrap import resolver_rutas_estandar
                logs_dir = resolver_rutas_estandar().logs
            inicializar_logging(Path(logs_dir))
        except Exception as exc:
            _log.debug("Re-init logger tras import fallo: %s", exc)

        for clave, accion in (
            ("reproductor",  "refrescar_letras_pista_activa"),
            ("estadisticas", "cargar"),
            ("biblioteca",   "cargar_grupos_albums"),
            ("playlists",    "sincronizar_inteligentes_async"),
            ("karaoke",      "cargar"),
            ("audioDeep",    "refrescarAudioDeepEstado"),
            # 3a capa de dedupe: una importación puede haber introducido
            # duplicados observables (mismo título/artista/álbum/portada/
            # duración). El barrido los oculta en background y refresca la
            # biblioteca en vivo al terminar.
            ("biblioteca",   "ejecutar_dedupe_observable"),
        ):
            modelo = modelos.get(clave)
            if modelo is None:
                continue
            metodo = getattr(modelo, accion, None)
            if metodo is None:
                continue
            try:
                metodo()
            except Exception as exc:
                _log.debug("Refresco post-import (%s.%s) falló: %s",
                           clave, accion, exc)

    try:
        imp.importacionFin.connect(_on_import_fin)
    except Exception as exc:
        _log.warning("No se pudo cablear refresco post-import: %s", exc)


def exponer_modelos(engine: QQmlApplicationEngine, modelos: dict) -> None:
    """
    Expone todos los modelos como propiedades del contexto raiz de QML.
    Cada modelo queda disponible con su nombre en todos los archivos QML.

    Además expone ``deepAnalyticsDisponible`` (bool) como propiedad de
    contexto global: en Windows, donde ``essentia-tensorflow`` no tiene
    wheel funcional, toda la UI de análisis profundo (deep) se oculta
    mediante ``visible: deepAnalyticsDisponible``. Se evalúa una sola vez
    aquí (al iniciar) y es estable durante la vida del proceso. La lógica
    Python deep NO se elimina; solo se condiciona su exposición visual.
    """
    ctx = engine.rootContext()
    for nombre, modelo in modelos.items():
        ctx.setContextProperty(nombre, modelo)

    try:
        from infra.dependencias import deep_analytics_disponible
        deep_disponible = deep_analytics_disponible()
    except Exception as exc:
        # Defensivo: si la detección falla, no ocultamos nada (comportamiento
        # histórico). El gap real solo existe en Windows.
        _log.debug("No se pudo resolver deep_analytics_disponible: %s", exc)
        deep_disponible = True
    ctx.setContextProperty("deepAnalyticsDisponible", bool(deep_disponible))


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

def main() -> int:
    # El binario empaquetado (bundle PyInstaller) es el MISMO para la GUI y la
    # CLI: en el PC del usuario no existe `python main.py` ni el repo clonado,
    # así que la única forma de exponer la CLI del catalogador en la terminal es
    # a través de este ejecutable (que el instalador registra como `nb-sound`).
    #   * `nb-sound`            → abre la interfaz gráfica.
    #   * `nb-sound cli ...`    → ejecuta la CLI del catalogador (main.main()).
    #   * `nb-sound cli --help` → ayuda de la CLI.
    argv = sys.argv[1:]
    if argv and argv[0] == "cli":
        from main import main as cli_main

        # Reconstruye argv sin el subcomando `cli` para que el parser de la CLI
        # vea exactamente los argumentos que el usuario escribió tras `cli`.
        sys.argv = [f"{sys.argv[0]} cli", *argv[1:]]
        return cli_main()

    parser = argparse.ArgumentParser(
        prog="nb_sound_ui",
        description=f"{UI_BANNER} — Capa visual para el pipeline",
    )
    parser.add_argument(
        "--db",
        metavar="RUTA",
        default=str(RUTA_DB_DEFAULT),
        help=f"Ruta de la base de datos SQLite (predeterminado: {RUTA_DB_DEFAULT})",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=UI_BANNER,
    )
    args = parser.parse_args()

    ruta_db = Path(args.db).expanduser().resolve()

    # Evita reutilizar bytecode QML obsoleto entre ejecuciones cuando se hacen
    # cambios de interfaz durante desarrollo.
    os.environ.setdefault("QML_DISABLE_DISK_CACHE", "1")

    # Atributos necesarios para Qt en algunos escritorios Wayland
    QGuiApplication.setAttribute(Qt.AA_ShareOpenGLContexts)

    app = QGuiApplication(sys.argv)
    app.setApplicationName(NOMBRE_APP)
    app.setApplicationVersion(VERSION_APP)
    app.setOrganizationName("NBSOUND")
    # app_id / desktop file: en Wayland (GNOME/Pop!_OS) el panel asocia la
    # ventana ABIERTA con su .desktop por el app_id; debe coincidir con el
    # nombre del archivo instalado (`nb-sound.desktop`) o la ventana abierta
    # cae a un icono genérico aunque el lanzador fijado sí muestre el logo.
    # Debe llamarse antes de crear ventanas. En X11 ayuda con el WM_CLASS.
    app.setDesktopFileName("nb-sound")

    # Icono de aplicacion: busca en orden assets/logo/ (oficial), fallback recursos/.
    for icono_candidato in (
        DIR_PROYECTO / "ui" / "qml" / "assets" / "logo" / "logo_blanco_negro.png",
        DIR_PROYECTO / "ui" / "recursos" / "icono.png",
    ):
        if icono_candidato.exists():
            app.setWindowIcon(QIcon(str(icono_candidato)))
            break

    # Inicializar BD
    try:
        inicializar_aplicacion(ruta_db)
    except Exception as e:
        print(f"[ERROR] No se pudo inicializar la base de datos: {e}", file=sys.stderr)
        return 1

    try:
        # Construir modelos
        try:
            modelos = construir_modelos(app)
        except Exception as e:
            print(f"[ERROR] No se pudieron construir los modelos UI: {e}", file=sys.stderr)
            raise

        # Cablear refresco automático de modelos tras una importación.
        # Vive en `main()` (no en `construir_modelos`) para que los
        # tests QML runtime que crean varios runtimes en cadena no
        # acumulen conexiones globales entre ellos.
        cablear_refrescos_post_import(modelos)

        # Configurar motor QML
        engine = QQmlApplicationEngine()

        # Registrar directorios de componentes QML
        dir_qml = DIR_PROYECTO / "ui" / "qml"
        engine.addImportPath(str(dir_qml))
        engine.addImportPath(str(dir_qml / "componentes"))
        engine.addImportPath(str(dir_qml / "vistas"))

        # Exponer modelos al contexto QML
        exponer_modelos(engine, modelos)
        if "audioDeep" in modelos:
            modelos["audioDeep"].autoIniciarAudioDeepSiCorresponde()

        # Diagnóstico de Karaoke al arranque (no al entrar a la vista).
        # `detectar_backend` ya corre en un QThread descartable, así que no
        # bloquea; lo diferimos con singleShot(0) para que arranque una vez el
        # event loop está activo y no compita con el primer frame. Cuando el
        # usuario navegue a "Preparar Karaoke", el diagnóstico ya estará
        # resuelto y la vista no mostrará el confuso "backend no detectado"
        # mientras todavía lo está buscando.
        _karaoke_modelo = modelos.get("karaoke")
        if _karaoke_modelo is not None:
            QTimer.singleShot(0, _karaoke_modelo.detectar_backend)

        # Barrido de duplicados observables al arranque, diferido para no
        # competir con el primer frame: limpia duplicados preexistentes que
        # quedaron de importaciones anteriores. Corre en QThread de baja
        # prioridad y refresca la biblioteca en vivo si resuelve algo.
        _biblioteca_modelo = modelos.get("biblioteca")
        if _biblioteca_modelo is not None:
            QTimer.singleShot(2500, _biblioteca_modelo.ejecutar_dedupe_observable)

        # Copia de seguridad programada: si el usuario configuró una frecuencia
        # y ya venció el plazo desde la última copia (reloj en BD), crea una
        # automática en background. Diferido para no competir con el primer
        # frame ni con el barrido de duplicados. El reloj solo avanza con la
        # app abierta; un QTimer interno del modelo re-chequea en sesiones largas.
        _sync_modelo = modelos.get("sincronizacion")
        if _sync_modelo is not None:
            QTimer.singleShot(6000, _sync_modelo.verificarBackupProgramado)

        # Restaurar la sesión DJ que quedó activa al cerrar (#7a). Diferido
        # para no competir con el primer frame; el prewarm de imports DJ
        # (1.5s) ya dejó calientes los módulos. La sesión vuelve en PAUSA, sin
        # audio: el primer play la retoma en la pista/posición exactas.
        _dj_modelo = modelos.get("djPrivado")
        if _dj_modelo is not None:
            QTimer.singleShot(3500, _dj_modelo.restaurar_sesion_persistida)

        # Red de seguridad de carátulas de playlists: al arrancar, regenera en
        # background las carátulas (mosaico con las portadas de las canciones) de
        # las playlists que falten o estén obsoletas, y refresca Playlists e
        # Inicio si hubo cambios. Diferido (4.5s) para no competir con el primer
        # frame ni con el barrido de duplicados. Garantiza que toda playlist
        # tenga su carátula "hecha" aunque se haya creado sin canciones con
        # portada o se editara por una vía que no la regeneró.
        _playlists_modelo = modelos.get("playlists")
        _estadisticas_modelo = modelos.get("estadisticas")
        if _playlists_modelo is not None and hasattr(_playlists_modelo, "asegurar_portadas_async"):
            if _estadisticas_modelo is not None:
                try:
                    _playlists_modelo.portadasAseguradas.connect(
                        lambda _ids, _e=_estadisticas_modelo: _e.cargar()
                    )
                except Exception as exc:
                    _log.debug("No se pudo cablear refresco de Inicio tras asegurar portadas: %s", exc)
            QTimer.singleShot(4500, _playlists_modelo.asegurar_portadas_async)

        # Cargar QML principal
        if not ARCHIVO_QML.exists():
            print(f"[ERROR] No se encontro el archivo QML principal: {ARCHIVO_QML}", file=sys.stderr)
            return 1

        engine.load(QUrl.fromLocalFile(str(ARCHIVO_QML)))

        if not engine.rootObjects():
            print("[ERROR] El motor QML no pudo cargar la interfaz.", file=sys.stderr)
            return 1

        # Una vez la UI está cargada, re-emitimos el estado restaurado del
        # reproductor para que la barra refleje la sesión previa (cola + pista
        # + tiempo) aunque sus bindings se hubieran evaluado antes de tiempo en
        # equipos donde la carga inicial tarda un par de segundos.
        _rep_modelo = modelos.get("reproductor")
        if _rep_modelo is not None and hasattr(_rep_modelo, "refrescar_estado_inicial"):
            QTimer.singleShot(0, _rep_modelo.refrescar_estado_inicial)
            QTimer.singleShot(800, _rep_modelo.refrescar_estado_inicial)

        return app.exec()
    finally:
        # Cierre limpio incluso si falla la carga de QML o el arranque de modelos.
        from db.conexion import cerrar_db
        cerrar_db()


if __name__ == "__main__":
    sys.exit(main())
