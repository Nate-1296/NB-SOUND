# =============================================================================
# servicios/reproductor.py
#
# Servicio de reproduccion de audio.
#
# Usa python-vlc como backend. El modo simulado solo se habilita de forma
# explicita en tests; en la UI real la ausencia de VLC es un error critico.
#
# Responsabilidades:
#   - Reproducir, pausar, detener y saltar pistas
#   - Mantener y manipular la cola de reproduccion
#   - Persistir la cola en la BD entre sesiones
#   - Registrar cada reproduccion en el historial
#   - Emitir callbacks de progreso para actualizar la UI
# =============================================================================

import random
import threading
import time
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Callable

from db.conexion import obtener_filas, obtener_una_fila, ejecutar, ejecutar_muchos, obtener_config, guardar_config
from servicios import biblioteca as svc_bib
from infra.logger import obtener_logger
from config import settings as _settings

logger = obtener_logger(__name__)

try:
    import vlc as _vlc
    VLC_DISPONIBLE = True
except ImportError:
    VLC_DISPONIBLE = False

# =============================================================================
# ECUALIZADOR Y OPCIONES DE AUDIO (solo reproductor GLOBAL)
#
# Estas constantes describen el ecualizador de libVLC 3.0.x y las opciones de
# audio que NB Sound expone en Configuracion -> Personalizacion. Aplican SOLO al
# reproductor global; el DJ Privado tiene su propia cadena de audio y nunca se
# ve afectado (ver docs/plan_item7_ecualizador_y_opciones_reproductor.md §5).
#
# La tabla `EQ_PRESETS` se extrajo de la propia libVLC de este equipo
# (libvlc_audio_equalizer_new_from_preset). No son valores inventados:
# tests/test_reproductor_ecualizador.py la contrasta contra la librería para
# detectar cualquier desviación si cambia la versión de VLC.
# =============================================================================

# Numero de bandas y frecuencias centrales (Hz) del ecualizador de libVLC.
EQ_NUM_BANDAS: int = 10
EQ_BANDAS_HZ: tuple[int, ...] = (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)

# Rango util de ganancia por banda y de preamplificacion (dB).
EQ_AMP_MIN: float = -20.0
EQ_AMP_MAX: float = 20.0
EQ_PREAMP_MIN: float = -20.0
EQ_PREAMP_MAX: float = 20.0

# Opciones del normalizador de volumen (normvol). Se aplican PER-MEDIA en el
# reproductor global (media.add_option), nunca como args de la instancia VLC:
# la instancia se comparte con el DJ y no debe heredar filtros del global.
NORM_MAX_LEVEL: float = 2.0
NORM_BUFF_SIZE: int = 20

# Tabla canonica de los 18 presets de libVLC: (nombre, preamp_dB, (10 bandas dB)).
# Orden = indice que espera libvlc_audio_equalizer_new_from_preset.
EQ_PRESETS: tuple[tuple[str, float, tuple[float, ...]], ...] = (
    ("Flat",                 12.0, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
    ("Classical",            12.0, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -7.2, -7.2, -7.2, -9.6)),
    ("Club",                  6.0, (0.0, 0.0, 8.0, 5.6, 5.6, 5.6, 3.2, 0.0, 0.0, 0.0)),
    ("Dance",                 5.0, (9.6, 7.2, 2.4, 0.0, 0.0, -5.6, -7.2, -7.2, 0.0, 0.0)),
    ("Full bass",             5.0, (-8.0, 9.6, 9.6, 5.6, 1.6, -4.0, -8.0, -10.4, -11.2, -11.2)),
    ("Full bass and treble",  4.0, (7.2, 5.6, 0.0, -7.2, -4.8, 1.6, 8.0, 11.2, 12.0, 12.0)),
    ("Full treble",           3.0, (-9.6, -9.6, -9.6, -4.0, 2.4, 11.2, 16.0, 16.0, 16.0, 16.8)),
    ("Headphones",            4.0, (4.8, 11.2, 5.6, -3.2, -2.4, 1.6, 4.8, 9.6, 12.8, 14.4)),
    ("Large Hall",            5.0, (10.4, 10.4, 5.6, 5.6, 0.0, -4.8, -4.8, -4.8, 0.0, 0.0)),
    ("Live",                  7.0, (-4.8, 0.0, 4.0, 5.6, 5.6, 5.6, 4.0, 2.4, 2.4, 2.4)),
    ("Party",                 6.0, (7.2, 7.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 7.2, 7.2)),
    ("Pop",                   6.0, (-1.6, 4.8, 7.2, 8.0, 5.6, 0.0, -2.4, -2.4, -1.6, -1.6)),
    ("Reggae",                8.0, (0.0, 0.0, 0.0, -5.6, 0.0, 6.4, 6.4, 0.0, 0.0, 0.0)),
    ("Rock",                  5.0, (8.0, 4.8, -5.6, -8.0, -3.2, 4.0, 8.8, 11.2, 11.2, 11.2)),
    ("Ska",                   6.0, (-2.4, -4.8, -4.0, 0.0, 4.0, 5.6, 8.8, 9.6, 11.2, 9.6)),
    ("Soft",                  5.0, (4.8, 1.6, 0.0, -2.4, 0.0, 4.0, 8.0, 9.6, 11.2, 12.0)),
    ("Soft rock",             7.0, (4.0, 4.0, 2.4, 0.0, -4.0, -5.6, -3.2, 0.0, 2.4, 8.8)),
    ("Techno",                5.0, (8.0, 5.6, 0.0, -5.6, -4.8, 0.0, 8.0, 9.6, 9.6, 8.8)),
)
EQ_PRESET_NOMBRES: tuple[str, ...] = tuple(nombre for nombre, _, _ in EQ_PRESETS)

# Nombres de presentación en español (mismo orden/índice que EQ_PRESETS). Los
# géneros y términos sin traducción natural se conservan (Pop, Rock, Reggae, Ska,
# Techno, Club, Dance, Soft rock). El índice canónico no cambia: estos nombres
# son SOLO para la UI; la persistencia y la API siguen usando el índice.
EQ_PRESET_NOMBRES_ES: tuple[str, ...] = (
    "Plano",          # Flat
    "Clásica",        # Classical
    "Club",           # Club
    "Dance",          # Dance
    "Graves",         # Full bass
    "Graves y agudos",  # Full bass and treble
    "Agudos",         # Full treble
    "Auriculares",    # Headphones
    "Sala grande",    # Large Hall
    "En vivo",        # Live
    "Fiesta",         # Party
    "Pop",            # Pop
    "Reggae",         # Reggae
    "Rock",           # Rock
    "Ska",            # Ska
    "Suave",          # Soft
    "Soft rock",      # Soft rock
    "Techno",         # Techno
)


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    """Acota `valor` al rango [minimo, maximo]."""
    return max(minimo, min(maximo, valor))


def bandas_de_preset(preset_idx: int) -> list[float]:
    """Devuelve las 10 amplitudes (dB) del preset `preset_idx` (0..17).

    Funcion pura: no depende de VLC ni de estado mutable. Lanza IndexError si el
    indice esta fuera de rango (contrato explicito para detectar usos invalidos).
    """
    return list(EQ_PRESETS[preset_idx][2])


def preamp_de_preset(preset_idx: int) -> float:
    """Devuelve la preamplificacion (dB) del preset `preset_idx` (0..17). Pura."""
    return float(EQ_PRESETS[preset_idx][1])


def _preamp_con_headroom(preamp: float, bandas) -> float:
    """Preamp EFECTIVO (dB) con headroom anti-clipping.

    Los presets de libVLC traen un preamp alto (Flat/Classical = +12 dB) y
    bandas con boost de hasta +16 dB. El volumen del reproductor llega como
    mucho a 100, que en VLC es ganancia UNIDAD (no atenua): a ese nivel el
    boost del EQ empuja la senal por encima de 0 dBFS y recorta (la distorsion
    que se oye al subir el volumen con el EQ activo). A volumen medio la
    atenuacion del propio volumen da headroom y por eso ahi no se nota.

    Para que el EQ no recorte a NINGUN volumen, se baja el preamp aplicado de
    modo que el pico teorico (preamp + mayor ganancia de banda) no supere 0 dB.
    No cambia la forma del EQ (las diferencias entre bandas se conservan), solo
    su nivel absoluto. El preamp "nominal" que se muestra/guarda del preset NO
    se altera; este ajuste es solo el valor que se manda a libVLC.
    """
    try:
        pico_bandas = max((float(b) for b in bandas), default=0.0)
    except (TypeError, ValueError):
        pico_bandas = 0.0
    techo = -max(0.0, pico_bandas)
    return min(float(preamp), techo)


# =============================================================================
# TIPOS Y ENUMERACIONES
# =============================================================================

class EstadoReproductor(Enum):
    DETENIDO   = "detenido"
    REPRODUCIENDO = "reproduciendo"
    PAUSADO    = "pausado"
    CARGANDO   = "cargando"
    FINALIZADA = "finalizada"
    ERROR      = "error"


class ModoRepeticion(Enum):
    NINGUNO  = "ninguno"
    UNO      = "uno"
    TODO     = "todo"


@dataclass
class PistaActiva:
    """Snapshot de la pista que se esta reproduciendo ahora.

    `ruta_archivo` siempre es la ruta LOGICA original del archivo de audio.
    Indexa la pista (lyrics, metadata, manifest de enrichment) y NO cambia
    cuando se alterna el modo karaoke.

    `ruta_audio_actual` indica que archivo de audio reproduce VLC en este
    momento. None significa "ruta_archivo" (modo normal); un valor distinto
    indica que VLC esta sirviendo el instrumental de karaoke.
    """
    id:             int
    titulo:         str
    artista:        str
    album:          str
    ruta_archivo:   str
    duracion_seg:   float = 0.0
    track_number:   Optional[int] = None
    portada_ruta:   Optional[str] = None
    portada_hd_ruta: Optional[str] = None
    karaoke_estado: str = "no_procesada"
    karaoke_ruta_instrumental: Optional[str] = None
    # Ruta efectiva en VLC. None => igual a ruta_archivo.
    ruta_audio_actual: Optional[str] = None

    def fuente_audio_efectiva(self) -> str:
        """Ruta del archivo que VLC esta reproduciendo realmente."""
        return self.ruta_audio_actual or self.ruta_archivo


# Tipo de callback de progreso: (posicion_seg, duracion_seg) -> None
TipoCallbackProgreso = Callable[[float, float], None]
# Callback de cambio de estado: (estado, pista_activa) -> None
TipoCallbackEstado   = Callable[[EstadoReproductor, Optional[PistaActiva]], None]
TipoCallbackCola     = Callable[[], None]
TipoCallbackAviso    = Callable[[dict], None]


# =============================================================================
# REPRODUCTOR PRINCIPAL
# =============================================================================

class Reproductor:
    """
    Facade de reproduccion que encapsula VLC y la logica de cola.

    Se instancia una vez como singleton en la aplicacion y se inyecta
    en los servicios y modelos QML que lo necesiten.
    """

    def __init__(self, *, permitir_modo_simulado: bool = False) -> None:
        self._estado        = EstadoReproductor.DETENIDO
        self._pista_activa: Optional[PistaActiva] = None
        self._cola:         list[dict] = []          # lista de dicts de pista
        self._posicion_cola = 0                      # indice actual en la cola
        self._cola_base:    list[dict] = []          # orden no aleatorio restante
        self._contexto_reproduccion: list[dict] = [] # orden completo no consumible
        self._posicion_contexto = 0
        self._modo_repeticion = ModoRepeticion.NINGUNO
        self._aleatorio       = False
        self._volumen         = 80                   # 0-100

        # Ecualizador (solo reproductor global). El estado lógico vive aquí; el
        # objeto vlc.AudioEqualizer se (re)construye al aplicarse y se mantiene
        # vivo en `_equalizer` mientras esté asignado al media_player.
        #   _eq_preset_idx: índice de preset (0..17) o None = "Personalizado".
        self._eq_activo: bool = False
        self._eq_preset_idx: Optional[int] = 0
        self._eq_bandas: list[float] = [0.0] * EQ_NUM_BANDAS
        self._eq_preamp: float = 0.0
        self._equalizer: Optional[object] = None
        # Normalización de volumen (normvol). Se aplica per-media (no toca al DJ).
        self._audio_normalizar: bool = False

        # Callbacks registrados por la UI
        self._cb_progreso:  list[TipoCallbackProgreso] = []
        self._cb_estado:    list[TipoCallbackEstado]   = []
        self._cb_cola:      list[TipoCallbackCola]     = []
        self._cb_aviso:     list[TipoCallbackAviso]    = []
        self._avisos_retenidos: list[dict] = []

        # VLC
        self._instancia_vlc: Optional[object] = None
        self._media_player:  Optional[object] = None
        self._hilo_progreso: Optional[threading.Thread] = None
        self._activo = False  # flag para el hilo de progreso
        self._permitir_modo_simulado = bool(permitir_modo_simulado)
        self._audio_disponible = True

        self._lock = threading.Lock()
        self._activa_desde_cola = False
        # Posición (seg) a la que debe saltar la PRÓXIMA reproducción en frío
        # tras restaurar la sesión previa al arrancar la app. Se consume una vez.
        self._reanudar_seg_pendiente: float = 0.0
        # Modo DJ: cuando una sesion DJ Privado toma control, el reproductor
        # global se suspende. Recordamos la posicion para reanudar.
        self._modo_dj_activo: bool = False
        self._modo_dj_snapshot: Optional[dict] = None
        # Callbacks especificos del modo DJ (UI los suscribe).
        self._cb_modo_dj: list[Callable[[bool], None]] = []
        self._cache_letras: dict[str, dict[str, str]] = {}
        self._manifest_letras_ruta: Optional[Path] = self._resolver_manifest_letras_ruta()
        self._manifest_letras_mtime: float = -1.0
        self._indice_letras_por_archivo: dict[str, dict[str, str]] = {}
        # Timer diferido usado por _al_terminar_pista (necesita ser cancelable
        # en cierre para no emitir avances tras release() de VLC).
        self._timer_fin_pista: Optional[threading.Timer] = None
        self._cerrado = False
        # Cierre en dos fases: `preparar_cierre()` (desde onClosing) corta el
        # audio y persiste el estado de sesión ANTES de que Qt destruya la
        # ventana; `cerrar()` (desde aboutToQuit) completa el teardown. El flag
        # evita que `cerrar()` vuelva a guardar (con VLC ya detenido leería
        # posición 0 y machacaría el punto de reanudación real).
        self._cierre_preparado = False
        self._inicializar_vlc()
        self._cargar_estado_persistido()
        self._cargar_config_audio()
        self._restaurar_cola_persistida()

    # ------------------------------------------------------------------
    # INICIALIZACION
    # ------------------------------------------------------------------

    def _inicializar_vlc(self) -> None:
        if not VLC_DISPONIBLE:
            self._audio_disponible = False
            if not self._permitir_modo_simulado:
                self._emitir_aviso(
                    nivel="critical",
                    codigo="vlc_no_disponible",
                    titulo="Backend de audio no disponible",
                    mensaje="NB Sound no puede reproducir audio porque python-vlc o VLC no está disponible.",
                    soluciones=[
                        "Instala VLC y python-vlc en el entorno actual.",
                        "Reinicia la aplicación después de instalar VLC.",
                        "Verifica que el sistema pueda cargar las librerías nativas de VLC.",
                    ],
                    retener=True,
                )
            return
        # Lista de argumentos a probar, del más completo al más conservador.
        # --no-xlib: desactiva integración X11 (compatible con XWayland y Wayland).
        # --vout=dummy: evita que VLC busque un output de video real; NB Sound no
        #   necesita video — reproduce solo audio. Sin esto, libvlc_new puede
        #   devolver NULL en sistemas con displays o drivers no estándar.
        # --aout=pulse: fuerza PulseAudio/PipeWire (disponible en todos los desktops
        #   modernos). Fallback automático a ALSA si no encuentra PulseAudio.
        _intentos_args = (
            "--no-xlib --quiet --vout=dummy --aout=pulse",
            "--no-xlib --quiet --vout=dummy",
            "--quiet",
        )
        instancia = None
        for args in _intentos_args:
            try:
                instancia = _vlc.Instance(args)
            except Exception as e:
                logger.warning(f"VLC.Instance('{args}') lanzó {e}", exc_info=True)
                instancia = None
            if instancia is not None:
                break

        if instancia is None:
            # libvlc_new() devolvió NULL en todos los intentos. Normalmente
            # significa que VLC del sistema no está disponible o tiene plugins
            # incompatibles. No relanzamos para no romper la UI: la app sigue
            # arrancando con audio deshabilitado y el usuario ve el aviso.
            logger.warning(
                "No se pudo crear vlc.Instance tras %d intentos. "
                "Audio deshabilitado.", len(_intentos_args),
            )
            self._instancia_vlc = None
            self._media_player = None
            self._audio_disponible = False
            if not self._permitir_modo_simulado:
                self._emitir_aviso(
                    nivel="critical",
                    codigo="vlc_inicializacion_fallida",
                    titulo="VLC no pudo inicializarse",
                    mensaje="El backend de audio falló al iniciar y la reproducción está deshabilitada.",
                    soluciones=[
                        "Confirma que VLC esté instalado correctamente.",
                        "Revisa permisos y librerías nativas de VLC.",
                        "Reinicia NB Sound después de corregir la instalación.",
                    ],
                    retener=True,
                )
            return

        try:
            self._instancia_vlc = instancia
            self._media_player = instancia.media_player_new()
            em = self._media_player.event_manager()
            em.event_attach(_vlc.EventType.MediaPlayerEndReached, self._al_terminar_pista)
        except Exception as e:
            logger.warning(f"VLC media_player_new falló: {e}", exc_info=True)
            self._instancia_vlc = None
            self._media_player = None
            self._audio_disponible = False
            if not self._permitir_modo_simulado:
                self._emitir_aviso(
                    nivel="critical",
                    codigo="vlc_inicializacion_fallida",
                    titulo="VLC no pudo inicializarse",
                    mensaje="El backend de audio falló al iniciar y la reproducción está deshabilitada.",
                    soluciones=[
                        "Confirma que VLC esté instalado correctamente.",
                        "Revisa permisos y librerías nativas de VLC.",
                        "Reinicia NB Sound después de corregir la instalación.",
                    ],
                    retener=True,
                )

    def _cargar_estado_persistido(self) -> None:
        """Restaura volumen y modos desde config_ui."""
        try:
            self._volumen = int(obtener_config("volumen", "80"))
            modo_str = obtener_config("modo_repeticion", "ninguno")
            self._modo_repeticion = ModoRepeticion(modo_str)
            self._aleatorio = obtener_config("modo_aleatorio", "0") == "1"
        except (ValueError, KeyError) as e:
            logger.warning(f"Config corrupta, usando defaults: {e}")
        except Exception as e:
            logger.error(f"Error inesperado cargando configuración: {e}", exc_info=True)

    def _cargar_config_audio(self) -> None:
        """Restaura ecualizador y normalización de volumen desde config_ui.

        No aplica nada a VLC aquí (al arrancar aún no hay media activa): el EQ se
        asocia en cada `_reproducir_pista` y normvol se inyecta per-media. Solo
        deja el estado lógico listo para esa primera reproducción.
        """
        try:
            self._eq_activo = obtener_config("eq_activo", "0") == "1"
            self._audio_normalizar = obtener_config("audio_normalizar", "0") == "1"

            # Bandas persistidas: JSON de 10 floats. Si falta o es inválido, se
            # derivan del preset (o quedan planas si el preset es "custom").
            bandas: Optional[list[float]] = None
            bandas_raw = obtener_config("eq_bandas", "")
            if bandas_raw:
                try:
                    datos = json.loads(bandas_raw)
                    if isinstance(datos, list) and len(datos) == EQ_NUM_BANDAS:
                        bandas = [_clamp(float(x), EQ_AMP_MIN, EQ_AMP_MAX) for x in datos]
                except (json.JSONDecodeError, TypeError, ValueError):
                    bandas = None

            preset = obtener_config("eq_preset", "0")
            if preset == "custom":
                self._eq_preset_idx = None
                self._eq_bandas = bandas if bandas is not None else [0.0] * EQ_NUM_BANDAS
            else:
                try:
                    idx = int(preset)
                except (TypeError, ValueError):
                    idx = 0
                if not (0 <= idx < len(EQ_PRESETS)):
                    idx = 0
                self._eq_preset_idx = idx
                self._eq_bandas = (
                    bandas if bandas is not None
                    else [_clamp(v, EQ_AMP_MIN, EQ_AMP_MAX) for v in bandas_de_preset(idx)]
                )

            try:
                self._eq_preamp = _clamp(float(obtener_config("eq_preamp", "0")),
                                         EQ_PREAMP_MIN, EQ_PREAMP_MAX)
            except (TypeError, ValueError):
                self._eq_preamp = (
                    preamp_de_preset(self._eq_preset_idx)
                    if self._eq_preset_idx is not None else 0.0
                )
        except Exception as e:
            logger.error(f"Error cargando config de audio (EQ/normvol): {e}", exc_info=True)

    # ------------------------------------------------------------------
    # REGISTRO DE CALLBACKS
    # ------------------------------------------------------------------

    def on_progreso(self, callback: TipoCallbackProgreso) -> None:
        """Registra un callback que se llama ~cada segundo con la posicion."""
        self._cb_progreso.append(callback)

    def on_estado(self, callback: TipoCallbackEstado) -> None:
        """Registra un callback que se llama cuando el estado cambia."""
        self._cb_estado.append(callback)

    def off_progreso(self, callback: TipoCallbackProgreso) -> None:
        """Desregistra callback de progreso si existe."""
        try:
            self._cb_progreso.remove(callback)
        except ValueError:
            pass

    def off_estado(self, callback: TipoCallbackEstado) -> None:
        """Desregistra callback de estado si existe."""
        try:
            self._cb_estado.remove(callback)
        except ValueError:
            pass

    def on_cola(self, callback: TipoCallbackCola) -> None:
        """Registra un callback para cambios de cola."""
        self._cb_cola.append(callback)

    def off_cola(self, callback: TipoCallbackCola) -> None:
        """Desregistra callback de cola si existe."""
        try:
            self._cb_cola.remove(callback)
        except ValueError:
            pass

    def on_aviso(self, callback: TipoCallbackAviso) -> None:
        """Registra un callback para avisos de UI del reproductor."""
        self._cb_aviso.append(callback)
        for aviso in list(self._avisos_retenidos):
            try:
                callback(aviso)
            except Exception as e:
                logger.error(f"Error en callback de aviso: {e}", exc_info=True)

    def off_aviso(self, callback: TipoCallbackAviso) -> None:
        """Desregistra callback de avisos si existe."""
        try:
            self._cb_aviso.remove(callback)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # CONTROL DE REPRODUCCION
    # ------------------------------------------------------------------

    def reproducir_pista(self, datos_pista: dict, *, registrar_en_cola: bool = True) -> None:
        """
        Inicia una pista individual.

        Por contrato de UI, una pista elegida directamente tambien se muestra
        como elemento activo de la cola para que pueda consumirse al finalizar.
        """
        if not isinstance(datos_pista, dict):
            self._notificar_fallo_reproducible(
                "pista_invalida",
                "No se pudo reproducir",
                "La pista seleccionada no tiene datos válidos.",
            )
            return

        ruta_texto = str(datos_pista.get("ruta_archivo") or "").strip()
        if not ruta_texto:
            self._notificar_fallo_reproducible(
                "pista_sin_ruta",
                "No se pudo reproducir",
                "La pista seleccionada no tiene una ruta de archivo reproducible.",
            )
            return
        ruta = Path(ruta_texto)
        if not ruta.exists():
            self._notificar_fallo_reproducible(
                "pista_no_encontrada",
                "Archivo no encontrado",
                "No se pudo reproducir la pista porque el archivo ya no existe.",
            )
            return

        datos = self._normalizar_datos_pista(datos_pista)
        if registrar_en_cola:
            with self._lock:
                self._reemplazar_cola_con_pista_unica_locked(datos)
                pista = self._cola[self._posicion_cola]
            self._persistir_cola()
            self._emitir_cola()
            self._reproducir_pista(pista, desde_cola=True)
            return

        with self._lock:
            desde_cola = self._activa_desde_cola
        self._reproducir_pista(datos, desde_cola=desde_cola)

    def _reproducir_pista(self, datos_pista: dict, *, desde_cola: bool, posicion_inicial_seg: float = 0.0) -> None:
        """
        Inicia la reproduccion de una pista especifica.
        datos_pista debe tener al menos: id, titulo, artista, album, ruta_archivo, duracion_seg.

        ``posicion_inicial_seg`` permite arrancar la pista desde un punto dado
        (reanudación de la sesión previa al abrir la app). El seek se aplica de
        forma diferida con la misma maquinaria probada de cambio de fuente.
        """
        ruta = Path(datos_pista.get("ruta_archivo", ""))
        if not ruta.exists():
            self._notificar_fallo_reproducible(
                "pista_no_encontrada",
                "Archivo no encontrado",
                "No se pudo reproducir la pista porque el archivo ya no existe.",
            )
            return

        datos = self._normalizar_datos_pista(datos_pista)

        with self._lock:
            self._pista_activa = PistaActiva(
                id           = int(datos.get("id", -1)),
                titulo       = datos.get("titulo", ""),
                artista      = datos.get("artista_nombre", datos.get("artista", "")),
                album        = datos.get("album_titulo",  datos.get("album", "")),
                ruta_archivo = str(ruta),
                duracion_seg = datos.get("duracion_seg") or 0.0,
                track_number = datos.get("track_number"),
                portada_ruta = datos.get("portada_ruta"),
                portada_hd_ruta = datos.get("portada_hd_ruta"),
                karaoke_estado = datos.get("karaoke_estado") or "no_procesada",
                karaoke_ruta_instrumental = datos.get("karaoke_ruta_instrumental"),
            )
            self._activa_desde_cola = bool(desde_cola)
            self._estado = EstadoReproductor.CARGANDO
        self._emitir_estado()

        with self._lock:
            if self._media_player:
                try:
                    media = self._crear_media(str(ruta))
                    self._media_player.set_media(media)
                    self._media_player.audio_set_volume(self._volumen)
                    self._media_player.play()
                    # set_equalizer se asocia al media actual: hay que reaplicar
                    # el EQ en cada pista nueva para que el ajuste sea "pegajoso".
                    self._aplicar_equalizer_a_media_player()
                    self._estado = EstadoReproductor.REPRODUCIENDO
                except Exception as e:
                    logger.error(f"Error al reproducir {ruta}: {e}", exc_info=True)
                    self._estado = EstadoReproductor.ERROR
                    self._activo = False
                    self._emitir_aviso(
                        nivel="warning",
                        codigo="playback_fallido",
                        titulo="No se pudo reproducir",
                        mensaje="La pista no pudo iniciar. Puede estar corrupta o no ser compatible.",
                    )
            else:
                if self._permitir_modo_simulado:
                    self._estado = EstadoReproductor.REPRODUCIENDO
                else:
                    self._estado = EstadoReproductor.ERROR
                    self._activo = False
                    self._emitir_aviso(
                        nivel="critical",
                        codigo="vlc_no_disponible",
                        titulo="Backend de audio no disponible",
                        mensaje="No se puede reproducir audio porque VLC no está disponible.",
                        soluciones=[
                            "Instala VLC y python-vlc en el entorno actual.",
                            "Reinicia NB Sound después de instalar VLC.",
                            "Verifica que las librerías nativas de VLC estén en el PATH del sistema.",
                        ],
                        retener=True,
                    )

        self._emitir_estado()

        if self._estado == EstadoReproductor.REPRODUCIENDO:
            # Seek de reanudación (sesión previa): salta al punto guardado en un
            # hilo aparte (VLC tarda en abrir el media), manteniendo la pista
            # sonando (estado_previo=REPRODUCIENDO no pausa).
            if posicion_inicial_seg and posicion_inicial_seg > 0.5:
                threading.Thread(
                    target=self._aplicar_seek_diferido,
                    args=(float(posicion_inicial_seg), EstadoReproductor.REPRODUCIENDO),
                    daemon=True,
                ).start()
            self._iniciar_hilo_progreso()

    def _reemplazar_cola_con_pista_unica_locked(self, pista: dict) -> None:
        """Define una pista elegida directamente como unica fila activa de cola."""
        self._cola = [pista]
        self._posicion_cola = 0
        self._activa_desde_cola = True
        self._actualizar_cola_base_desde_cola_locked()
        self._actualizar_contexto_desde_cola_locked()

    def pausar_reanudar(self) -> None:
        """Alterna entre reproduccion y pausa.

        Si no hay reproduccion activa pero existe cola, inicia desde la posicion actual.
        """
        pista_a_reproducir = None
        desde_cola = False
        emitir_estado = False
        seek_inicial = 0.0
        with self._lock:
            if self._estado == EstadoReproductor.REPRODUCIENDO:
                if self._media_player:
                    self._media_player.pause()
                self._estado = EstadoReproductor.PAUSADO
                emitir_estado = True
            elif self._estado == EstadoReproductor.PAUSADO:
                if self._media_player:
                    self._media_player.play()
                self._estado = EstadoReproductor.REPRODUCIENDO
                emitir_estado = True
            elif self._cola:
                self._normalizar_indice_cola()
                self._posicion_cola = max(0, min(self._posicion_cola, len(self._cola) - 1))
                pista_a_reproducir = self._cola[self._posicion_cola]
                desde_cola = True
                # Arranque en frío tras restaurar sesión: consumir el seek.
                seek_inicial = self._reanudar_seg_pendiente
                self._reanudar_seg_pendiente = 0.0
            elif self._pista_activa:
                pista_a_reproducir = self._datos_pista_activa()
                seek_inicial = self._reanudar_seg_pendiente
                self._reanudar_seg_pendiente = 0.0

        if emitir_estado:
            self._emitir_estado()
        if pista_a_reproducir is not None:
            self._reproducir_pista(pista_a_reproducir, desde_cola=desde_cola, posicion_inicial_seg=seek_inicial)

    # ------------------------------------------------------------------
    # MODO DJ — suspension contextual del reproductor global
    # ------------------------------------------------------------------

    def on_modo_dj(self, callback: Callable[[bool], None]) -> None:
        """Registra callback que se invoca cuando entra/sale el modo DJ."""
        self._cb_modo_dj.append(callback)

    def off_modo_dj(self, callback: Callable[[bool], None]) -> None:
        try:
            self._cb_modo_dj.remove(callback)
        except ValueError:
            pass

    @property
    def modo_dj_activo(self) -> bool:
        return self._modo_dj_activo

    def set_modo_dj(self, activo: bool) -> None:
        """Activa/desactiva la suspension del reproductor global.

        Cuando se activa:
          - Recordamos pista activa, posicion (seg) y estado.
          - Pausamos VLC (sin tirar la cola ni el estado interno).
          - Subimos el flag `_modo_dj_activo`. Los slots publicos lo respetan.

        Cuando se desactiva:
          - Restauramos posicion (si habia pista activa).
          - Conservamos pausa o reproduccion segun lo guardado.

        Idempotente: llamar dos veces con el mismo valor no hace nada.
        """
        with self._lock:
            if bool(activo) == self._modo_dj_activo:
                return
            if activo:
                # Snapshot del estado previo
                pos_seg = 0.0
                if self._media_player is not None and self._estado != EstadoReproductor.DETENIDO:
                    try:
                        pos_seg = max(0.0, self._media_player.get_time() / 1000.0)
                    except Exception:
                        pos_seg = 0.0
                self._modo_dj_snapshot = {
                    "estado":  self._estado.value,
                    "pos_seg": pos_seg,
                    # Guardar pista_id por si la cola se altera mientras DJ activo.
                    "pista_id": int(self._pista_activa.id) if self._pista_activa else 0,
                }
                # Pausar VLC sin emitir cambio de estado: el ModeloReproductor
                # debe entender que esto es suspension, no pausa del usuario.
                if self._media_player is not None and self._estado == EstadoReproductor.REPRODUCIENDO:
                    try:
                        self._media_player.set_pause(1)
                    except Exception as _exc:
                        logger.debug("Excepcion ignorada en %s: %s", "reproductor.py", _exc)
                self._modo_dj_activo = True
            else:
                snap = self._modo_dj_snapshot or {}
                self._modo_dj_activo = False
                self._modo_dj_snapshot = None
                # Restaurar la POSICIÓN de la pista global, pero NO reanudar
                # la reproducción aunque estuviera sonando antes. Si el DJ
                # terminó (natural o por el usuario), el global se queda en
                # pausa: silencio predecible en lugar de un "auto-play" que
                # sorprende al usuario después de la sesión. Para retomar,
                # el usuario pulsa play en la barra global.
                pos_seg = float(snap.get("pos_seg") or 0.0)
                if (self._media_player is not None and self._pista_activa
                        and pos_seg > 0.5 and self._pista_activa.duracion_seg > 0):
                    try:
                        porc = min(1.0, max(0.0, pos_seg / self._pista_activa.duracion_seg))
                        self._media_player.set_position(porc)
                    except Exception as _exc:
                        logger.debug("Excepcion ignorada en %s: %s", "reproductor.py", _exc)
                # Si el estado lógico decía REPRODUCIENDO, lo bajamos a
                # PAUSADO para que UI y backend coincidan (VLC está
                # pausado desde set_modo_dj(True)).
                if self._estado == EstadoReproductor.REPRODUCIENDO:
                    self._estado = EstadoReproductor.PAUSADO
        # Emitir notificacion fuera del lock
        for cb in list(self._cb_modo_dj):
            try:
                cb(bool(activo))
            except Exception:
                logger.exception("cb modo_dj fallo")

    def alternar_fuente_audio(self, usar_instrumental: bool) -> bool:
        """Cambia la fuente de audio de VLC SIN reiniciar la pista logica.

        Preserva:
          - `_pista_activa` (id, titulo, lyrics asociadas via ruta_archivo).
          - posicion temporal (seek tras swap).
          - estado reproductor (reproduciendo/pausado).
          - cola, contexto, modo aleatorio/repeticion.

        No emite `cola` ni un cambio de `pista` — solo un `_emitir_estado()`
        ligero para que la UI refresque indicadores derivados (p.ej. karaoke
        activo si lo deriva del estado). Para enterarse del swap, la UI debe
        consultar `pista.ruta_audio_actual` o `karaoke_activo()`.

        Retorna False si no hay pista activa, no hay instrumental disponible,
        o el archivo destino no existe.
        """
        with self._lock:
            pista = self._pista_activa
            if not pista:
                return False
            destino_str: Optional[str]
            if usar_instrumental:
                destino_str = pista.karaoke_ruta_instrumental
                if not destino_str:
                    return False
            else:
                destino_str = pista.ruta_archivo
            try:
                destino = Path(str(destino_str)).expanduser()
            except Exception:
                return False
            if not destino.exists():
                return False

            actual = pista.fuente_audio_efectiva()
            if str(destino) == str(actual):
                # Ya estamos reproduciendo la fuente solicitada.
                return True

            estado_previo = self._estado
            posicion_seg = 0.0
            if self._media_player and estado_previo != EstadoReproductor.DETENIDO:
                try:
                    posicion_seg = max(0.0, self._media_player.get_time() / 1000.0)
                except Exception:
                    posicion_seg = 0.0

            ok = False
            if self._media_player:
                try:
                    media = self._crear_media(str(destino))
                    self._media_player.set_media(media)
                    self._media_player.audio_set_volume(self._volumen)
                    # play() siempre arranca; el ajuste a pausado se hace despues
                    self._media_player.play()
                    # Reaplicar el EQ: el swap cambió el media en curso.
                    self._aplicar_equalizer_a_media_player()
                    ok = True
                except Exception as exc:
                    logger.error(f"alternar_fuente_audio fallo: {exc}", exc_info=True)
                    ok = False
            else:
                # Modo simulado: solo actualizamos el campo.
                ok = self._permitir_modo_simulado

            if ok:
                pista.ruta_audio_actual = str(destino) if usar_instrumental else None
                # Si estabamos pausados, mantenemos pausa tras el seek; si
                # estabamos detenidos, restauramos detenido.
                if estado_previo == EstadoReproductor.PAUSADO:
                    self._estado = EstadoReproductor.PAUSADO
                elif estado_previo == EstadoReproductor.REPRODUCIENDO:
                    self._estado = EstadoReproductor.REPRODUCIENDO
                # else: mantenemos lo que haya (CARGANDO -> REPRODUCIENDO via play)

        if not ok:
            return False

        # Seek y ajuste de pausa en otro hilo: VLC tarda ~10-50ms en abrir
        # el media tras set_media+play. Hacemos polling corto con backoff
        # en vez de timers QML hardcodeados.
        threading.Thread(
            target=self._aplicar_seek_diferido,
            args=(posicion_seg, estado_previo),
            daemon=True,
        ).start()

        self._emitir_estado()
        return True

    def _aplicar_seek_diferido(self, posicion_seg: float, estado_previo: "EstadoReproductor") -> None:
        """Aplica seek y pausa en otro hilo, esperando a que VLC abra el media."""
        deadline = time.monotonic() + 2.5
        aplicado = False
        while time.monotonic() < deadline:
            try:
                if self._media_player is None:
                    return
                # VLC necesita un instante para abrir el stream antes de aceptar set_position.
                # get_length devuelve -1 mientras no este listo.
                longitud_ms = self._media_player.get_length()
                if longitud_ms > 0 and self._pista_activa:
                    duracion = self._pista_activa.duracion_seg or (longitud_ms / 1000.0)
                    if posicion_seg > 0.0 and duracion > 0.0:
                        porc = min(1.0, max(0.0, posicion_seg / duracion))
                        self._media_player.set_position(porc)
                    if estado_previo == EstadoReproductor.PAUSADO:
                        self._media_player.set_pause(1)
                    aplicado = True
                    break
            except Exception as _exc:
                logger.debug("Excepcion ignorada en %s: %s", "reproductor.py", _exc)
            time.sleep(0.05)

        if not aplicado and posicion_seg > 0.0:
            # Fallback: aplicamos el seek aunque get_length no este listo todavia.
            try:
                if self._media_player and self._pista_activa and self._pista_activa.duracion_seg > 0:
                    porc = min(1.0, max(0.0, posicion_seg / self._pista_activa.duracion_seg))
                    self._media_player.set_position(porc)
                if estado_previo == EstadoReproductor.PAUSADO and self._media_player:
                    self._media_player.set_pause(1)
            except Exception as _exc:
                logger.debug("Excepcion ignorada en %s: %s", "reproductor.py", _exc)

    def detener(self) -> None:
        """Detiene la reproduccion completamente."""
        with self._lock:
            if self._media_player:
                self._media_player.stop()
            self._estado       = EstadoReproductor.DETENIDO
            self._activo       = False
            self._activa_desde_cola = False
        self._emitir_estado()

    def _detener_y_limpiar_pista_activa(self, estado: EstadoReproductor = EstadoReproductor.DETENIDO) -> None:
        """Detiene playback y deja el reproductor sin metadata activa."""
        with self._lock:
            if self._media_player:
                self._media_player.stop()
            self._estado = estado
            self._activo = False
            self._pista_activa = None
            self._posicion_cola = 0
            self._activa_desde_cola = False
        self._emitir_estado()

    def _detener_conservando_cola(self, estado: EstadoReproductor = EstadoReproductor.FINALIZADA) -> None:
        """Detiene al agotar la cola sin consumir la pista ni la cola.

        A diferencia de `detener()`, conserva `_activa_desde_cola`,
        `_pista_activa` y el puntero `_posicion_cola` en la última pista: ésta
        sigue marcada como actual en el panel (`indice_cola` sigue siendo
        válido) y `play` la reanuda, como en Spotify/Apple Music.
        """
        with self._lock:
            if self._media_player:
                self._media_player.stop()
            self._estado = estado
            self._activo = False
        self._emitir_estado()

    def siguiente(self) -> None:
        """Avanza a la siguiente pista en la cola."""
        detener_reproduccion = False
        pista = None
        desde_cola = False
        with self._lock:
            if not self._cola:
                if self._modo_repeticion == ModoRepeticion.UNO and self._pista_activa:
                    pista = self._datos_pista_activa()
                elif self._pista_activa:
                    detener_reproduccion = True
                else:
                    return
            elif self._modo_repeticion == ModoRepeticion.UNO:
                self._normalizar_indice_cola()
                pista = self._cola[self._posicion_cola]
                desde_cola = True
            else:
                self._normalizar_indice_cola()
                if not self._activa_desde_cola:
                    self._posicion_cola = 0
                    pista = self._cola[self._posicion_cola]
                    desde_cola = True
                else:
                    siguiente_pos = self._posicion_cola + 1
                    if siguiente_pos >= len(self._cola):
                        if self._modo_repeticion == ModoRepeticion.TODO:
                            siguiente_pos = 0
                        else:
                            detener_reproduccion = True
                    if not detener_reproduccion:
                        self._posicion_cola = siguiente_pos
                        pista = self._cola[self._posicion_cola]
                        desde_cola = True

        if detener_reproduccion:
            self.detener()
            return

        if pista is not None:
            self._reproducir_pista(pista, desde_cola=desde_cola)

    def anterior(self) -> None:
        """Retrocede a la pista anterior en la cola."""
        pista = None
        desde_cola = False
        with self._lock:
            if not self._cola:
                if self._pista_activa:
                    pista = self._datos_pista_activa()
            elif not self._activa_desde_cola:
                if self._pista_activa:
                    pista = self._datos_pista_activa()
            else:
                self._normalizar_indice_cola()
                if self._posicion_cola == 0 and self._modo_repeticion == ModoRepeticion.TODO:
                    posicion = len(self._cola) - 1
                else:
                    posicion = max(0, self._posicion_cola - 1)
                self._posicion_cola = posicion
                pista = self._cola[self._posicion_cola]
                desde_cola = True

        if pista is not None:
            self._reproducir_pista(pista, desde_cola=desde_cola)

    def _normalizar_indice_cola(self) -> None:
        """Mantiene el indice actual dentro del rango de la cola."""
        if self._cola:
            self._posicion_cola = max(0, min(self._posicion_cola, len(self._cola) - 1))
        else:
            self._posicion_cola = 0

    def _datos_pista_activa(self) -> dict:
        """Devuelve la pista activa en el formato de entrada del reproductor."""
        if not self._pista_activa:
            return {}
        return {
            "id": self._pista_activa.id,
            "titulo": self._pista_activa.titulo,
            "artista_nombre": self._pista_activa.artista,
            "album_titulo": self._pista_activa.album,
            "ruta_archivo": self._pista_activa.ruta_archivo,
            "duracion_seg": self._pista_activa.duracion_seg,
            "track_number": self._pista_activa.track_number,
            "portada_ruta": self._pista_activa.portada_ruta,
            "portada_hd_ruta": self._pista_activa.portada_hd_ruta,
            "karaoke_estado": self._pista_activa.karaoke_estado,
            "karaoke_ruta_instrumental": self._pista_activa.karaoke_ruta_instrumental,
            "ruta_audio_actual": self._pista_activa.ruta_audio_actual,
        }

    def _normalizar_datos_pista(self, datos_pista: dict) -> dict:
        """Copia una pista y completa metadatos que la UI necesita de forma estable."""
        pista = dict(datos_pista)
        portada = self._resolver_portada_pista(pista)
        if portada:
            pista["portada_ruta"] = portada
        portada_hd = self._resolver_portada_hd_pista(pista)
        if portada_hd:
            pista["portada_hd_ruta"] = portada_hd
        return pista

    def _resolver_portada_hd_pista(self, datos_pista: dict) -> Optional[str]:
        """Resuelve la portada HD sin reemplazar la portada estandar."""
        for clave in ("portada_hd_ruta", "album_portada_hd", "al_portada_hd"):
            portada = str(datos_pista.get(clave) or "").strip()
            if portada:
                return portada

        mb_release_id = str(datos_pista.get("mb_release_id") or "").strip()
        pista_id = datos_pista.get("id")
        album_id = datos_pista.get("album_id")

        try:
            if pista_id is not None:
                fila = obtener_una_fila(
                    """
                    SELECT
                        p.mb_release_id AS p_mb_release_id,
                        al.mb_release_id AS al_mb_release_id
                    FROM pistas p
                    LEFT JOIN albums al ON al.id = p.album_id
                    WHERE p.id = ?
                    """,
                    (int(pista_id),),
                )
                release_id = mb_release_id
                if fila:
                    release_id = release_id or fila["p_mb_release_id"] or fila["al_mb_release_id"]
                portada = svc_bib._resolver_portada_hd_fila(None, release_id)
                if portada:
                    return portada

            if album_id is not None:
                fila = obtener_una_fila(
                    "SELECT mb_release_id FROM albums WHERE id = ?",
                    (int(album_id),),
                )
                portada = svc_bib._resolver_portada_hd_fila(
                    None,
                    mb_release_id or (fila["mb_release_id"] if fila else None),
                )
                if portada:
                    return portada
        except Exception as e:
            logger.warning(f"Error resolviendo portada HD para {mb_release_id}: {e}")
            return None

        if mb_release_id:
            return svc_bib._resolver_portada_hd_fila(None, mb_release_id)
        return None

    def _resolver_portada_pista(self, datos_pista: dict) -> Optional[str]:
        """Resuelve la portada de una pista desde datos enriquecidos, DB o assets."""
        for clave in ("portada_ruta", "album_portada", "al_portada"):
            portada = str(datos_pista.get(clave) or "").strip()
            if portada:
                return portada

        pista_id = datos_pista.get("id")
        album_id = datos_pista.get("album_id")
        mb_release_id = str(datos_pista.get("mb_release_id") or "").strip()

        try:
            if pista_id is not None:
                fila = obtener_una_fila(
                    """
                    SELECT
                        p.mb_release_id AS p_mb_release_id,
                        al.portada_ruta AS al_portada,
                        al.mb_release_id AS al_mb_release_id
                    FROM pistas p
                    LEFT JOIN albums al ON al.id = p.album_id
                    WHERE p.id = ?
                    """,
                    (int(pista_id),),
                )
                release_id = mb_release_id
                if fila and not release_id:
                    release_id = fila["p_mb_release_id"] or fila["al_mb_release_id"]
                portada = svc_bib._resolver_portada_fila(
                    fila["al_portada"] if fila else None,
                    release_id,
                )
                if portada:
                    return portada

            if album_id is not None:
                fila = obtener_una_fila(
                    "SELECT portada_ruta, mb_release_id FROM albums WHERE id = ?",
                    (int(album_id),),
                )
                portada = svc_bib._resolver_portada_fila(
                    fila["portada_ruta"] if fila else None,
                    mb_release_id or (fila["mb_release_id"] if fila else None),
                )
                if portada:
                    return portada

            if mb_release_id:
                fila = obtener_una_fila(
                    "SELECT portada_ruta FROM albums WHERE mb_release_id = ? AND portada_ruta IS NOT NULL AND portada_ruta <> '' LIMIT 1",
                    (mb_release_id,),
                )
                portada = svc_bib._resolver_portada_fila(
                    fila["portada_ruta"] if fila else None,
                    mb_release_id,
                )
                if portada:
                    return portada
        except Exception as e:
            logger.warning(f"Error resolviendo portada para {mb_release_id}: {e}")
            return None

        if mb_release_id:
            return svc_bib._resolver_portada_fila(None, mb_release_id)

        return None

    def obtener_letra_pista_activa(self) -> str:
        """Retorna letra priorizando synced_lyrics y fallback a plain_lyrics."""
        lyrics = self.obtener_lyrics_pista_activa()
        synced = str(lyrics.get("synced_lyrics") or "").strip()
        if synced:
            return synced
        return str(lyrics.get("plain_lyrics") or "").strip()

    def obtener_lyrics_pista_activa(self) -> dict[str, str]:
        """Retorna lyrics de la pista activa desde enrichment_manifest.jsonl.

        Siempre usa `pista.ruta_archivo` (la ruta LOGICA original),
        nunca la fuente de audio que pueda estar reproduciendo VLC. Eso
        garantiza que el modo karaoke NO rompe la asociacion con la letra:
        la pista logica sigue siendo la misma aunque VLC sirva el
        instrumental.
        """
        pista = self._pista_activa
        if not pista or not pista.ruta_archivo:
            return {"plain_lyrics": "", "synced_lyrics": ""}
        return self._leer_letra_desde_enrichment(pista.ruta_archivo)

    def karaoke_activo(self) -> bool:
        """True si VLC esta reproduciendo el instrumental de la pista activa."""
        pista = self._pista_activa
        if not pista or not pista.ruta_audio_actual:
            return False
        instr = pista.karaoke_ruta_instrumental
        if not instr:
            return False
        return str(pista.ruta_audio_actual) == str(instr)

    def _resolver_manifest_letras_ruta(self) -> Optional[Path]:
        """Calcula la ruta del manifest de letras desde el settings actual.

        Se invoca lazy desde `_recargar_indice_letras_si_necesario` (no
        solo en `__init__`) para que si el usuario cambia
        `DEFAULT_ASSETS_DIR` mientras la app corre (vía Configuración),
        las letras nuevas se encuentren sin reiniciar.
        """
        if _settings.DEFAULT_ASSETS_DIR is None:
            return None
        return Path(_settings.DEFAULT_ASSETS_DIR) / "enrichment" / "enrichment_manifest.jsonl"

    def _leer_letra_desde_enrichment(self, ruta_archivo: str) -> dict[str, str]:
        """Lee lyrics (plain/synced) desde índice de enrichment por ruta.

        Reglas de caché:

        * `_recargar_indice_letras_si_necesario()` se invoca SIEMPRE primero
          (es barato: solo hace `stat` y compara mtime). Si el manifest
          cambió, ese método invalida `_cache_letras` para que la siguiente
          línea no devuelva un valor envenenado.

        * Sin la inversión de orden, si la primera consulta para una pista
          ocurre antes de que enrichment haya escrito sus lyrics (caso real
          al importar mientras la UI está mostrando la pista activa),
          `_cache_letras[ruta] = {}` queda fijo: las consultas posteriores
          hacen cache-hit sin invocar el recargar y la UI sigue viendo
          "sin letra" hasta reiniciar la app.
        """
        ruta = str(ruta_archivo or "").strip()
        if not ruta:
            return {"plain_lyrics": "", "synced_lyrics": ""}

        self._recargar_indice_letras_si_necesario()

        if ruta in self._cache_letras:
            return self._cache_letras[ruta]

        lyrics: dict[str, str] = {"plain_lyrics": "", "synced_lyrics": ""}
        try:
            ruta_normalizada = str(Path(ruta).expanduser().resolve())
        except Exception:
            ruta_normalizada = ruta

        lyrics = dict(self._indice_letras_por_archivo.get(ruta_normalizada, {}))
        if not lyrics:
            lyrics = dict(self._indice_letras_por_archivo.get(ruta, {}))

        self._cache_letras[ruta] = lyrics
        return lyrics

    def invalidar_cache_letras(self) -> None:
        """Fuerza la próxima consulta a re-leer el manifest desde disco.

        Lo invocamos al terminar una importación: aunque el `mtime` del
        manifest haya cambiado y `_recargar_indice` lo detecte, los
        ``cache_letras`` con valor vacío que se grabaron antes de que se
        escribieran las letras pueden quedar persistentes en escenarios
        edge (mismo `mtime` por escritura batched, FS sin granularidad de
        sub-segundo, etc.). Limpiar cache + mtime garantiza una recarga
        completa al próximo `_leer_letra_desde_enrichment`.
        """
        self._cache_letras = {}
        self._manifest_letras_mtime = -1.0

    def _recargar_indice_letras_si_necesario(self) -> None:
        # Re-resolver el path si no apunta a un archivo existente.
        # `DEFAULT_ASSETS_DIR` puede haber cambiado entre `__init__`
        # (cuando aún se podía estar leyendo el fallback XDG) y la
        # primera consulta de lyrics (cuando ya se han volcado las
        # rutas configuradas por el usuario). Si el manifest actual no
        # existe pero el resolver dinámico apunta a uno que sí existe,
        # adoptamos esa ruta. Si el manifest actual SÍ existe lo
        # respetamos (cubre monkeypatch en tests y configuraciones
        # válidas estables).
        if self._manifest_letras_ruta is None or not self._manifest_letras_ruta.exists():
            propuesto = self._resolver_manifest_letras_ruta()
            if propuesto is not None and propuesto != self._manifest_letras_ruta:
                self._manifest_letras_ruta = propuesto
                self._manifest_letras_mtime = -1.0
                self._indice_letras_por_archivo = {}
                self._cache_letras = {}
        manifest = self._manifest_letras_ruta
        if manifest is None or not manifest.exists():
            self._indice_letras_por_archivo = {}
            self._manifest_letras_mtime = -1.0
            return

        try:
            mtime = manifest.stat().st_mtime
        except OSError:
            return

        if mtime == self._manifest_letras_mtime:
            return

        indice: dict[str, dict[str, str]] = {}
        try:
            with manifest.open("r", encoding="utf-8") as fh:
                for linea in fh:
                    texto = linea.strip()
                    if not texto:
                        continue
                    try:
                        fila = json.loads(texto)
                    except json.JSONDecodeError:
                        continue

                    ruta = str(fila.get("file") or "").strip()
                    if not ruta:
                        continue
                    lyrics = fila.get("lyrics") or {}
                    if not isinstance(lyrics, dict):
                        continue

                    synced = str(lyrics.get("synced_lyrics") or "").strip()
                    plain = str(lyrics.get("plain_lyrics") or "").strip()
                    if not synced and not plain:
                        continue

                    entry = {
                        "synced_lyrics": synced,
                        "plain_lyrics": plain,
                    }
                    indice[ruta] = entry
                    try:
                        ruta_resuelta = str(Path(ruta).expanduser().resolve())
                        indice[ruta_resuelta] = entry
                    except Exception as _exc:
                        logger.debug("Excepcion ignorada en %s: %s", "reproductor.py", _exc)
        except OSError as e:
            logger.warning(f"No se pudo leer manifest de enrichment: {manifest} ({e})")
            return

        self._indice_letras_por_archivo = indice
        self._manifest_letras_mtime = mtime
        self._cache_letras = {}

    def buscar_posicion(self, posicion_seg: float) -> None:
        """Salta a una posicion especifica en la pista actual."""
        if self._media_player and self._pista_activa:
            duracion = self._pista_activa.duracion_seg or 1
            porcentaje = min(1.0, max(0.0, posicion_seg / duracion))
            self._media_player.set_position(porcentaje)

    # ------------------------------------------------------------------
    # COLA
    # ------------------------------------------------------------------

    def reproducir_cola(self, pistas: list[dict], desde_indice: int = 0) -> None:
        """Reemplaza la cola con la lista dada y empieza a reproducir."""
        with self._lock:
            self._cola          = [self._normalizar_datos_pista(p) for p in pistas]
            self._cola_base     = [dict(pista) for pista in self._cola]
            self._posicion_cola = max(0, min(desde_indice, len(self._cola) - 1))
            if self._aleatorio:
                self._aleatorizar_cola_locked()
            self._actualizar_contexto_desde_cola_locked()

        if self._cola:
            self._reproducir_pista(self._cola[self._posicion_cola], desde_cola=True)
        self._persistir_cola()
        self._emitir_cola()

    def reproducir_indice_cola(self, indice: int) -> bool:
        """Reproduce una pista existente de la cola sin reconstruirla."""
        try:
            indice_seguro = int(indice)
        except (TypeError, ValueError):
            return False

        pista = None
        with self._lock:
            if not (0 <= indice_seguro < len(self._cola)):
                return False
            candidata = self._cola[indice_seguro]
            ruta = Path(str(candidata.get("ruta_archivo") or ""))
            if not ruta.exists():
                self._emitir_aviso(
                    nivel="warning",
                    codigo="pista_no_encontrada",
                    titulo="Archivo no encontrado",
                    mensaje="No se pudo reproducir esa fila de la cola porque el archivo ya no existe.",
                )
                return False
            self._posicion_cola = indice_seguro
            self._sincronizar_posicion_contexto_con_pista_locked(candidata)
            pista = candidata

        self._reproducir_pista(pista, desde_cola=True)
        self._persistir_cola()
        self._emitir_cola()

        activa = self._pista_activa
        if not activa:
            return False
        try:
            pista_id = int(pista.get("id") or -1)
        except (TypeError, ValueError):
            pista_id = -1
        return (
            activa.id == pista_id
            or str(activa.ruta_archivo) == str(pista.get("ruta_archivo") or "")
        )

    def agregar_a_cola(self, pista: dict, siguiente: bool = False) -> None:
        """Agrega una pista al final de la cola (o despues de la actual)."""
        pista_normalizada = self._normalizar_datos_pista(pista)
        with self._lock:
            if siguiente:
                insertar_en = self._posicion_cola + 1 if self._activa_desde_cola else 0
                self._cola.insert(insertar_en, pista_normalizada)
                self._insertar_en_cola_base_locked(pista_normalizada, despues_de_activa=True)
            elif self._aleatorio and self._cola:
                self._normalizar_indice_cola()
                inicio = self._posicion_cola + 1 if self._activa_desde_cola else 0
                insertar_en = random.randint(inicio, len(self._cola))
                self._cola.insert(insertar_en, pista_normalizada)
                self._cola_base.append(dict(pista_normalizada))
            else:
                self._cola.append(pista_normalizada)
                self._cola_base.append(dict(pista_normalizada))
            self._actualizar_contexto_desde_cola_locked()
        self._persistir_cola()
        self._emitir_cola()

    def agregar_varias_a_cola(self, pistas: list[dict]) -> None:
        """Agrega varias pistas a la cola y emite cambios una sola vez."""
        pistas_normalizadas = [
            self._normalizar_datos_pista(pista)
            for pista in list(pistas or [])
            if isinstance(pista, dict)
        ]
        if not pistas_normalizadas:
            return

        with self._lock:
            for pista_normalizada in pistas_normalizadas:
                if self._aleatorio and self._cola:
                    self._normalizar_indice_cola()
                    inicio = self._posicion_cola + 1 if self._activa_desde_cola else 0
                    insertar_en = random.randint(inicio, len(self._cola))
                    self._cola.insert(insertar_en, pista_normalizada)
                    self._cola_base.append(dict(pista_normalizada))
                else:
                    self._cola.append(pista_normalizada)
                    self._cola_base.append(dict(pista_normalizada))
            self._actualizar_contexto_desde_cola_locked()
        self._persistir_cola()
        self._emitir_cola()

    def limpiar_cola(self) -> None:
        """Vacia la cola de reproduccion sin interrumpir la pista activa."""
        with self._lock:
            self._cola = []
            self._posicion_cola = 0
            self._activa_desde_cola = False
            self._cola_base = []
            self._contexto_reproduccion = []
            self._posicion_contexto = 0
        self._persistir_cola()
        self._emitir_cola()

    def vaciar_cola_mantener_actual(self) -> None:
        """Vacia la cola y conserva solo la pista actualmente marcada en la cola."""
        with self._lock:
            puede_conservar_actual = (
                self._activa_desde_cola
                and 0 <= self._posicion_cola < len(self._cola)
            )
            if puede_conservar_actual:
                pista_actual = dict(self._cola[self._posicion_cola])
                self._cola = [pista_actual]
                self._posicion_cola = 0
                self._activa_desde_cola = True
                self._actualizar_cola_base_desde_cola_locked()
                self._actualizar_contexto_desde_cola_locked()
            else:
                self._cola = []
                self._posicion_cola = 0
                self._activa_desde_cola = False
                self._cola_base = []
                self._contexto_reproduccion = []
                self._posicion_contexto = 0
        self._persistir_cola()
        self._emitir_cola()

    def mover_en_cola(self, desde: int, hasta: int) -> None:
        """Reordena un elemento de la cola."""
        with self._lock:
            if 0 <= desde < len(self._cola) and 0 <= hasta < len(self._cola):
                pista = self._cola.pop(desde)
                self._cola.insert(hasta, pista)
                if self._activa_desde_cola:
                    if desde == self._posicion_cola:
                        self._posicion_cola = hasta
                    elif desde < self._posicion_cola <= hasta:
                        self._posicion_cola -= 1
                    elif hasta <= self._posicion_cola < desde:
                        self._posicion_cola += 1
                else:
                    self._posicion_cola = 0
                self._actualizar_contexto_desde_cola_locked()
                self._actualizar_cola_base_desde_cola_locked()
        self._persistir_cola()
        self._emitir_cola()


    def quitar_de_cola(self, indice: int) -> None:
        """Elimina una pista de la cola por indice."""
        try:
            indice_seguro = int(indice)
        except (TypeError, ValueError):
            return

        limpiar_reproduccion = False
        pista_a_reproducir = None
        with self._lock:
            if not (0 <= indice_seguro < len(self._cola)):
                return

            removida_es_activa = (
                self._activa_desde_cola
                and indice_seguro == self._posicion_cola
            )
            removida = self._cola.pop(indice_seguro)
            if not removida_es_activa and not self._activa_desde_cola:
                removida_es_activa = self._pista_coincide_con_activa_locked(removida)
            self._quitar_de_cola_base_locked(removida)

            if not self._cola:
                self._posicion_cola = 0
                self._activa_desde_cola = False
                limpiar_reproduccion = removida_es_activa
            elif removida_es_activa:
                self._posicion_cola = min(indice_seguro, len(self._cola) - 1)
                pista_a_reproducir = self._cola[self._posicion_cola]
            elif indice_seguro < self._posicion_cola:
                self._posicion_cola -= 1
            elif indice_seguro == self._posicion_cola:
                self._posicion_cola = min(self._posicion_cola, len(self._cola) - 1)
            self._actualizar_contexto_desde_cola_locked()

        if limpiar_reproduccion:
            self._detener_y_limpiar_pista_activa()
        elif pista_a_reproducir is not None:
            self._reproducir_pista(pista_a_reproducir, desde_cola=True)
        self._persistir_cola()
        self._emitir_cola()

    def purgar_pista(self, pista_id) -> None:
        """Quita TODAS las apariciones de una pista de la cola.

        Pensado para cuando la pista se elimina de la biblioteca: reutiliza la
        lógica de `quitar_de_cola` (que gestiona la pista activa, el avance y la
        persistencia). Si la pista eliminada es además la activa fuera de cola,
        se detiene la reproducción para no dejar sonando un archivo inexistente.
        """
        try:
            pid = int(pista_id)
        except (TypeError, ValueError):
            return
        while True:
            with self._lock:
                indice = next(
                    (i for i, p in enumerate(self._cola) if int(p.get("id") or 0) == pid),
                    -1,
                )
            if indice < 0:
                break
            self.quitar_de_cola(indice)

        # Pista activa que no provenía de la cola (reproducción suelta): detener.
        with self._lock:
            activa = self._pista_activa
            activa_de_cola = self._activa_desde_cola
        if activa is not None and not activa_de_cola and int(getattr(activa, "id", 0) or 0) == pid:
            self._detener_y_limpiar_pista_activa()
            self._emitir_cola()

    def obtener_cola(self) -> list[dict]:
        with self._lock:
            return list(self._cola)

    # ------------------------------------------------------------------
    # VOLUMEN Y MODOS
    # ------------------------------------------------------------------

    def set_volumen(self, volumen: int) -> None:
        """Establece el volumen (0-100)."""
        self._volumen = max(0, min(100, volumen))
        if self._media_player:
            self._media_player.audio_set_volume(self._volumen)
        guardar_config("volumen", str(self._volumen))

    def set_modo_repeticion(self, modo: str) -> None:
        """Establece el modo de repeticion: 'ninguno' | 'uno' | 'todo'."""
        try:
            self._modo_repeticion = ModoRepeticion(modo)
            guardar_config("modo_repeticion", modo)
        except ValueError:
            pass

    def set_aleatorio(self, activo: bool) -> None:
        activo = bool(activo)
        cola_modificada = False
        with self._lock:
            cambio = self._aleatorio != activo
            self._aleatorio = activo
            if activo and cambio:
                self._aleatorizar_cola_locked()
                self._actualizar_contexto_desde_cola_locked()
                cola_modificada = True
            elif not activo and cambio:
                cola_modificada = self._reconstruir_cola_desde_base_locked()
        guardar_config("modo_aleatorio", "1" if activo else "0")
        if cola_modificada:
            self._persistir_cola()
            self._emitir_cola()

    # ------------------------------------------------------------------
    # ECUALIZADOR Y OPCIONES DE AUDIO (solo reproductor GLOBAL)
    #
    # El ecualizador se asocia al `media_player` global vía set_equalizer y la
    # normalización se inyecta per-media. Ninguna de las dos toca al DJ Privado,
    # que mantiene su propia cadena de audio (decks + AudioEqualizer propios).
    # ------------------------------------------------------------------

    @property
    def eq_activo(self) -> bool:
        return self._eq_activo

    @property
    def eq_preset_idx(self) -> int:
        """Índice del preset activo (0..17) o -1 si es 'Personalizado'."""
        return self._eq_preset_idx if self._eq_preset_idx is not None else -1

    @property
    def eq_bandas(self) -> list[float]:
        return list(self._eq_bandas)

    @property
    def eq_preamp(self) -> float:
        return float(self._eq_preamp)

    @property
    def audio_normalizar(self) -> bool:
        return self._audio_normalizar

    def _crear_media(self, ruta: str):
        """Crea el `vlc.Media` del reproductor GLOBAL con sus opciones de audio.

        Las opciones (normvol) son PER-MEDIA a propósito: así el filtro afecta
        solo a la reproducción global y nunca al DJ Privado, que crea sus propios
        media sobre la instancia VLC compartida (ver plan_item7 §5). Cambiar
        normvol no exige recrear la instancia: basta recargar el media actual.
        """
        media = self._instancia_vlc.media_new(str(ruta))
        if self._audio_normalizar:
            try:
                media.add_option(":audio-filter=normvol")
                media.add_option(f":norm-max-level={NORM_MAX_LEVEL}")
                media.add_option(f":norm-buff-size={NORM_BUFF_SIZE}")
            except Exception as exc:
                logger.warning("No se pudieron aplicar opciones normvol al media: %s", exc)
        return media

    def _aplicar_equalizer_a_media_player(self) -> None:
        """Asocia (o desasocia) el ecualizador al `media_player` global actual.

        `set_equalizer` se asocia al media en curso, por eso se reaplica en cada
        `_reproducir_pista`/swap de fuente. Mantiene viva la referencia Python al
        `AudioEqualizer` mientras esté asignado (libVLC no la retiene por sí) y
        libera la anterior al reemplazarla.

        Presets: se construyen con `libvlc_audio_equalizer_new_from_preset(idx)`,
        que es la API de la librería para preajustes (balance banda/preamp
        correcto). Solo el modo "Personalizado" arma el ecualizador a mano desde
        las bandas/preamp editadas por el usuario.
        """
        mp = self._media_player
        if mp is None or not VLC_DISPONIBLE:
            return
        try:
            if not self._eq_activo:
                mp.set_equalizer(None)
                self._liberar_equalizer_actual()
                return

            if self._eq_preset_idx is not None:
                eq = _vlc.libvlc_audio_equalizer_new_from_preset(self._eq_preset_idx)
                # El preset trae su preamp original (p. ej. +12 dB en Flat); se
                # reemplaza por uno con headroom para que no recorte a volumen
                # alto. Las bandas del preset (forma del EQ) se conservan.
                if eq is not None:
                    eq.set_preamp(_clamp(
                        _preamp_con_headroom(
                            preamp_de_preset(self._eq_preset_idx),
                            bandas_de_preset(self._eq_preset_idx),
                        ),
                        EQ_PREAMP_MIN, EQ_PREAMP_MAX,
                    ))
            else:
                eq = _vlc.AudioEqualizer()
                eq.set_preamp(_clamp(
                    _preamp_con_headroom(float(self._eq_preamp), self._eq_bandas),
                    EQ_PREAMP_MIN, EQ_PREAMP_MAX,
                ))
                for i in range(EQ_NUM_BANDAS):
                    eq.set_amp_at_index(
                        _clamp(float(self._eq_bandas[i]), EQ_AMP_MIN, EQ_AMP_MAX), i
                    )
            if eq is None:
                return
            mp.set_equalizer(eq)
            # Conservar vivo el handle aplicado y liberar el anterior.
            anterior = self._equalizer
            self._equalizer = eq
            if anterior is not None and anterior is not eq:
                try:
                    anterior.release()
                except Exception as _exc:
                    logger.debug("Excepcion ignorada en %s: %s", "reproductor.py", _exc)
        except Exception as exc:
            logger.warning("No se pudo aplicar el ecualizador: %s", exc)

    def _liberar_equalizer_actual(self) -> None:
        """Libera el `AudioEqualizer` activo (si lo hay) y lo deja en None."""
        if self._equalizer is not None:
            try:
                self._equalizer.release()
            except Exception as _exc:
                logger.debug("Excepcion ignorada en %s: %s", "reproductor.py", _exc)
            self._equalizer = None

    def _persistir_config_ecualizador(self) -> None:
        """Guarda el estado del ecualizador en config_ui (sin cambio de esquema)."""
        try:
            guardar_config("eq_activo", "1" if self._eq_activo else "0")
            guardar_config(
                "eq_preset",
                "custom" if self._eq_preset_idx is None else str(self._eq_preset_idx),
            )
            guardar_config("eq_bandas",
                           json.dumps([round(float(b), 3) for b in self._eq_bandas]))
            guardar_config("eq_preamp", f"{float(self._eq_preamp):.3f}")
        except Exception as exc:
            logger.error("No se pudo persistir config de ecualizador: %s", exc, exc_info=True)

    def set_ecualizador_activo(self, activo: bool) -> None:
        """Activa/desactiva el ecualizador y lo aplica en vivo al media actual."""
        self._eq_activo = bool(activo)
        guardar_config("eq_activo", "1" if self._eq_activo else "0")
        self._aplicar_equalizer_a_media_player()

    def aplicar_ecualizador_preset(self, preset_idx: int) -> None:
        """Carga un preajuste (0..17): fija las 10 bandas y el preamp y lo aplica."""
        try:
            idx = int(preset_idx)
        except (TypeError, ValueError):
            return
        if not (0 <= idx < len(EQ_PRESETS)):
            return
        self._eq_preset_idx = idx
        self._eq_bandas = [_clamp(v, EQ_AMP_MIN, EQ_AMP_MAX) for v in bandas_de_preset(idx)]
        self._eq_preamp = _clamp(preamp_de_preset(idx), EQ_PREAMP_MIN, EQ_PREAMP_MAX)
        self._persistir_config_ecualizador()
        self._aplicar_equalizer_a_media_player()

    def set_ecualizador_banda(self, idx: int, db: float) -> None:
        """Ajusta una banda (dB). Mover una banda pasa el preset a 'Personalizado'."""
        try:
            i = int(idx)
            valor = _clamp(float(db), EQ_AMP_MIN, EQ_AMP_MAX)
        except (TypeError, ValueError):
            return
        if not (0 <= i < EQ_NUM_BANDAS):
            return
        self._eq_bandas[i] = valor
        self._eq_preset_idx = None  # desviación manual => Personalizado
        self._persistir_config_ecualizador()
        self._aplicar_equalizer_a_media_player()

    def set_ecualizador_preamp(self, db: float) -> None:
        """Ajusta la preamplificación (dB). También pasa a 'Personalizado'."""
        try:
            valor = _clamp(float(db), EQ_PREAMP_MIN, EQ_PREAMP_MAX)
        except (TypeError, ValueError):
            return
        self._eq_preamp = valor
        self._eq_preset_idx = None
        self._persistir_config_ecualizador()
        self._aplicar_equalizer_a_media_player()

    def set_normalizar_volumen(self, activo: bool) -> None:
        """Activa/desactiva el normalizador de volumen (normvol) del global.

        normvol es una opción per-media: se persiste y se aplica recargando el
        media actual en su misma posición (micro-corte de audio), SIN recrear la
        instancia VLC. Así el DJ Privado, que comparte la instancia, no se ve
        afectado en ningún caso.
        """
        activo = bool(activo)
        if activo == self._audio_normalizar:
            return
        self._audio_normalizar = activo
        guardar_config("audio_normalizar", "1" if activo else "0")
        self._recargar_media_actual_para_filtros()

    def _recargar_media_actual_para_filtros(self) -> None:
        """Recarga el media GLOBAL actual para aplicar en vivo un cambio de
        opciones per-media (normvol), conservando pista/posición/estado.

        No hace nada si no hay pista activa, no hay audio, o el modo DJ tiene el
        control (en ese caso el cambio se aplicará en la próxima reproducción).
        """
        with self._lock:
            pista = self._pista_activa
            if (pista is None
                    or self._media_player is None
                    or self._modo_dj_activo
                    or self._estado not in (EstadoReproductor.REPRODUCIENDO,
                                            EstadoReproductor.PAUSADO)):
                return
            fuente = pista.fuente_audio_efectiva()
            estado_previo = self._estado
            try:
                pos_seg = max(0.0, self._media_player.get_time() / 1000.0)
            except Exception:
                pos_seg = 0.0
            ok = False
            try:
                media = self._crear_media(str(fuente))
                self._media_player.set_media(media)
                self._media_player.audio_set_volume(self._volumen)
                self._media_player.play()
                ok = True
            except Exception as exc:
                logger.error("Recargar media para filtros falló: %s", exc, exc_info=True)

        if not ok:
            return
        # Reaplicar EQ y restaurar posición/pausa con la maquinaria de seek diferido.
        self._aplicar_equalizer_a_media_player()
        threading.Thread(
            target=self._aplicar_seek_diferido,
            args=(pos_seg, estado_previo),
            daemon=True,
        ).start()
        self._emitir_estado()

    def _aleatorizar_cola_locked(self) -> None:
        """Reordena la cola para que siguiente/anterior sigan un orden aleatorio visible."""
        if len(self._cola) <= 1:
            self._normalizar_indice_cola()
            return

        if not self._activa_desde_cola:
            random.shuffle(self._cola)
            self._posicion_cola = 0
            return

        indice_actual = self._indice_pista_activa_en_cola_locked()
        if indice_actual is None:
            indice_actual = self._posicion_cola
        self._posicion_cola = max(0, min(indice_actual, len(self._cola) - 1))

        actual = self._cola[self._posicion_cola]
        restantes = [
            pista for i, pista in enumerate(self._cola)
            if i != self._posicion_cola
        ]
        random.shuffle(restantes)
        self._cola = [actual, *restantes]
        self._posicion_cola = 0

    def _actualizar_contexto_desde_cola_locked(self) -> None:
        self._contexto_reproduccion = [dict(pista) for pista in self._cola]
        if self._contexto_reproduccion:
            self._posicion_contexto = max(
                0,
                min(self._posicion_cola, len(self._contexto_reproduccion) - 1),
            )
        else:
            self._posicion_contexto = 0

    def _actualizar_cola_base_desde_cola_locked(self) -> None:
        self._cola_base = [dict(pista) for pista in self._cola]

    def _insertar_en_cola_base_locked(self, pista: dict, *, despues_de_activa: bool) -> None:
        pista_copia = dict(pista)
        if not despues_de_activa or not self._cola_base:
            self._cola_base.append(pista_copia)
            return

        if self._pista_activa:
            for indice, candidata in enumerate(self._cola_base):
                if self._pista_coincide_con_activa_locked(candidata):
                    self._cola_base.insert(indice + 1, pista_copia)
                    return
        self._cola_base.insert(0, pista_copia)

    def _quitar_de_cola_base_locked(self, pista: dict) -> None:
        for indice, candidata in enumerate(self._cola_base):
            if self._pista_coincide_dicts(candidata, pista):
                self._cola_base.pop(indice)
                return

    def _reconstruir_cola_desde_base_locked(self) -> bool:
        cola_base = [dict(pista) for pista in self._cola_base]
        if self._cola == cola_base:
            self._normalizar_indice_cola()
            return False

        self._cola = cola_base
        if self._cola:
            if self._activa_desde_cola:
                indice_activo = self._indice_pista_activa_en_cola_locked()
                if indice_activo is not None:
                    self._posicion_cola = indice_activo
                else:
                    self._normalizar_indice_cola()
            else:
                self._posicion_cola = 0
        else:
            self._posicion_cola = 0
            self._activa_desde_cola = False
        return True

    def _sincronizar_posicion_contexto_con_pista_locked(self, pista: dict) -> None:
        for indice, candidata in enumerate(self._contexto_reproduccion):
            if self._pista_coincide_dicts(candidata, pista):
                self._posicion_contexto = indice
                return
        self._posicion_contexto = 0

    def _reconstruir_cola_desde_contexto_locked(self) -> bool:
        if not self._contexto_reproduccion:
            return False
        self._cola = [dict(pista) for pista in self._contexto_reproduccion]
        self._actualizar_cola_base_desde_cola_locked()
        self._posicion_cola = 0
        self._posicion_contexto = 0
        self._activa_desde_cola = True
        return True

    def _indice_pista_activa_en_cola_locked(self) -> Optional[int]:
        if not self._pista_activa:
            return None
        for indice, pista in enumerate(self._cola):
            if self._pista_coincide_con_activa_locked(pista):
                return indice
        return None

    def _pista_coincide_con_activa_locked(self, pista: dict) -> bool:
        if not self._pista_activa:
            return False

        try:
            pista_id = int(pista.get("id") or 0)
        except (TypeError, ValueError):
            pista_id = 0
        if pista_id > 0 and pista_id == self._pista_activa.id:
            return True

        ruta = str(pista.get("ruta_archivo") or "").strip()
        return bool(ruta) and ruta == self._pista_activa.ruta_archivo

    def _pista_coincide_dicts(self, izquierda: dict, derecha: dict) -> bool:
        try:
            izquierda_id = int(izquierda.get("id") or 0)
            derecha_id = int(derecha.get("id") or 0)
        except (TypeError, ValueError):
            izquierda_id = 0
            derecha_id = 0
        if izquierda_id > 0 and izquierda_id == derecha_id:
            return True

        izquierda_ruta = str(izquierda.get("ruta_archivo") or "").strip()
        derecha_ruta = str(derecha.get("ruta_archivo") or "").strip()
        return bool(izquierda_ruta) and izquierda_ruta == derecha_ruta

    # ------------------------------------------------------------------
    # PROPIEDADES DE ESTADO
    # ------------------------------------------------------------------

    @property
    def estado(self) -> EstadoReproductor:
        return self._estado

    @property
    def pista_activa(self) -> Optional[PistaActiva]:
        return self._pista_activa

    @property
    def posicion_seg(self) -> float:
        if self._media_player and self._estado != EstadoReproductor.DETENIDO:
            try:
                posicion = max(0.0, self._media_player.get_time() / 1000.0)
                duracion = 0.0
                if self._pista_activa:
                    try:
                        duracion = max(0.0, float(self._pista_activa.duracion_seg or 0.0))
                    except (TypeError, ValueError):
                        duracion = 0.0
                return min(posicion, duracion) if duracion > 0 else posicion
            except Exception as _exc:
                logger.debug("Excepcion ignorada en %s: %s", "reproductor.py", _exc)
        return 0.0

    @property
    def volumen(self) -> int:
        return self._volumen

    @property
    def modo_repeticion(self) -> str:
        return self._modo_repeticion.value

    @property
    def es_aleatorio(self) -> bool:
        return self._aleatorio

    @property
    def indice_cola(self) -> int:
        if self._activa_desde_cola and self._cola:
            return self._posicion_cola
        return -1

    @property
    def reanudar_seg_pendiente(self) -> float:
        """Posición (seg) que el PRÓXIMO play consumirá tras restaurar la
        sesión. La UI la usa para mostrar el tiempo guardado en la barra antes
        de que el usuario pulse play. 0.0 si no hay reanudación pendiente."""
        return float(self._reanudar_seg_pendiente or 0.0)

    # ------------------------------------------------------------------
    # HILO DE PROGRESO
    # ------------------------------------------------------------------

    def _iniciar_hilo_progreso(self) -> None:
        if self._cerrado:
            return
        self._activo = True
        if self._hilo_progreso and self._hilo_progreso.is_alive():
            return
        self._hilo_progreso = threading.Thread(
            target=self._loop_progreso, daemon=True, name="reproductor_progreso"
        )
        self._hilo_progreso.start()

    def _loop_progreso(self) -> None:
        while self._activo and not self._cerrado:
            if self._estado == EstadoReproductor.REPRODUCIENDO:
                pos = self.posicion_seg
                dur = self._pista_activa.duracion_seg if self._pista_activa else 0
                for cb in tuple(self._cb_progreso):
                    try:
                        cb(pos, dur)
                    except Exception as e:
                        logger.error(f"Error en callback de progreso: {e}", exc_info=True)
            time.sleep(0.5)

    # ------------------------------------------------------------------
    # EVENTOS VLC
    # ------------------------------------------------------------------

    def _al_terminar_pista(self, evento) -> None:
        """Llamado por VLC cuando una pista termina."""
        if self._cerrado:
            return
        if self._pista_activa:
            self._registrar_reproduccion(self._pista_activa.id, completada=True)

        # Desacoplar llamadas de vlc para evitar deadlock. Guardamos referencia
        # al Timer para poder cancelarlo en cerrar() y evitar que dispare
        # despues de release() (race que aborta VLC nativo).
        timer = threading.Timer(0.1, self._avanzar_tras_fin_pista)
        timer.daemon = True
        self._timer_fin_pista = timer
        timer.start()

    def _avanzar_tras_fin_pista(self) -> None:
        """Consume la pista actual si venia de la cola y prepara lo siguiente."""
        if self._cerrado:
            return
        pista = None
        desde_cola = False
        detener_reproduccion = False
        limpiar_pista_al_detener = False
        conservar_cola_al_detener = False
        cola_modificada = False

        with self._lock:
            if self._modo_repeticion == ModoRepeticion.UNO and self._pista_activa:
                pista = self._datos_pista_activa()
                desde_cola = self._activa_desde_cola
            elif self._activa_desde_cola:
                if self._cola:
                    # Cola NO consumible: la pista que termina PERMANECE en la
                    # cola; solo avanza el puntero (igual que `siguiente`). Así
                    # la lista se conserva, se puede retroceder y el panel
                    # muestra el historial, como en Spotify/Apple Music.
                    self._normalizar_indice_cola()
                    siguiente_pos = self._posicion_cola + 1
                    if siguiente_pos >= len(self._cola):
                        if self._modo_repeticion == ModoRepeticion.TODO:
                            siguiente_pos = 0
                        else:
                            # Fin de la cola sin repetición: detiene pero
                            # conserva la pista, la cola y el puntero al final.
                            # La pista sigue marcada como actual (resaltada en
                            # el panel) y `play` la reanuda, como en Spotify.
                            detener_reproduccion = True
                            conservar_cola_al_detener = True
                    if not detener_reproduccion:
                        self._posicion_cola = siguiente_pos
                        pista = self._cola[self._posicion_cola]
                        desde_cola = True
                        cola_modificada = True  # cambió el puntero: persistir + emitir
                else:
                    # Caso límite: cola vacía. Con repetir-todo reconstruye
                    # desde el contexto; si no, detiene conservando la pista.
                    if (
                        self._modo_repeticion == ModoRepeticion.TODO
                        and self._reconstruir_cola_desde_contexto_locked()
                    ):
                        pista = self._cola[self._posicion_cola]
                        desde_cola = True
                        cola_modificada = True
                    else:
                        self._posicion_cola = 0
                        self._activa_desde_cola = False
                        detener_reproduccion = True
                        limpiar_pista_al_detener = True
            elif self._cola:
                self._posicion_cola = 0
                pista = self._cola[self._posicion_cola]
                desde_cola = True
            else:
                detener_reproduccion = True
                limpiar_pista_al_detener = self._pista_activa is not None

        if cola_modificada:
            self._persistir_cola()
            self._emitir_cola()

        if pista is not None:
            self._reproducir_pista(pista, desde_cola=desde_cola)
        elif detener_reproduccion:
            if conservar_cola_al_detener:
                self._detener_conservando_cola(EstadoReproductor.FINALIZADA)
            elif limpiar_pista_al_detener:
                self._detener_y_limpiar_pista_activa(EstadoReproductor.FINALIZADA)
            else:
                self.detener()

    def _registrar_reproduccion(self, pista_id: int, completada: bool = True) -> None:
        """Registra la reproduccion en historial y actualiza contador."""
        try:
            pista = self._pista_activa
            ejecutar(
                """
                INSERT INTO historial(pista_id, titulo_snap, artista_snap, duracion_seg, completada)
                VALUES (?,?,?,?,?)
                """,
                (
                    pista_id,
                    pista.titulo   if pista else "",
                    pista.artista  if pista else "",
                    pista.duracion_seg if pista else 0,
                    1 if completada else 0,
                ),
            )
            ejecutar(
                """
                UPDATE pistas
                SET veces_reproducida = veces_reproducida + 1,
                    ultimo_acceso = datetime('now')
                WHERE id = ?
                """,
                (pista_id,),
            )
        except Exception as e:
            logger.error(f"Error registrando reproducción de pista {pista_id}: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # CALLBACKS
    # ------------------------------------------------------------------

    def _emitir_estado(self) -> None:
        estado   = self._estado
        pista    = self._pista_activa
        for cb in tuple(self._cb_estado):
            try:
                cb(estado, pista)
            except Exception as e:
                logger.error(f"Error en callback de estado: {e}", exc_info=True)

    def _emitir_cola(self) -> None:
        for cb in tuple(self._cb_cola):
            try:
                cb()
            except Exception as e:
                logger.error(f"Error en callback de cola: {e}", exc_info=True)

    def _emitir_aviso(
        self,
        *,
        nivel: str,
        codigo: str,
        titulo: str,
        mensaje: str,
        soluciones: Optional[list[str]] = None,
        retener: bool = False,
    ) -> None:
        aviso = {
            "nivel": str(nivel or "warning"),
            "codigo": str(codigo or "aviso_reproductor"),
            "titulo": str(titulo or "Aviso del reproductor"),
            "mensaje": str(mensaje or ""),
            "soluciones": list(soluciones or []),
        }
        if retener and aviso not in self._avisos_retenidos:
            self._avisos_retenidos.append(aviso)
        for cb in tuple(self._cb_aviso):
            try:
                cb(aviso)
            except Exception as e:
                logger.error(f"Error en callback de aviso: {e}", exc_info=True)

    def _notificar_fallo_reproducible(self, codigo: str, titulo: str, mensaje: str) -> None:
        cambiar_estado = False
        with self._lock:
            if self._pista_activa is None:
                self._estado = EstadoReproductor.ERROR
                self._activo = False
                cambiar_estado = True
        self._emitir_aviso(
            nivel="warning",
            codigo=codigo,
            titulo=titulo,
            mensaje=mensaje,
        )
        if cambiar_estado:
            self._emitir_estado()

    # ------------------------------------------------------------------
    # PERSISTENCIA DE COLA
    # ------------------------------------------------------------------

    def _persistir_cola(self) -> None:
        """Guarda la cola actual en la BD para restaurarla al reiniciar.
        
        Valida que cada pista_id sea válido antes de guardar.
        """
        try:
            ejecutar("DELETE FROM cola")
            
            pistas_guardadas = 0
            pistas_invalidas = 0
            
            datos_muchos = []
            for pos, pista in enumerate(self._cola):
                pista_id = pista.get("id")
                # Validar que pista_id sea un entero válido
                try:
                    pista_id = int(pista_id) if pista_id else None
                except (ValueError, TypeError):
                    pista_id = None
                
                if not pista_id:
                    pistas_invalidas += 1
                    continue
                
                datos_muchos.append((pos, pista_id))
                pistas_guardadas += 1
            
            if datos_muchos:
                ejecutar_muchos(
                    "INSERT INTO cola(posicion, pista_id) VALUES (?,?)",
                    datos_muchos
                )
            
            if pistas_invalidas > 0:
                logger.warning(
                    f"_persistir_cola: {pistas_guardadas} pistas guardadas, "
                    f"{pistas_invalidas} ignoradas por ID inválido"
                )

            # Índice activo dentro de la cola: al reabrir la app retomamos la
            # pista que estaba sonando, no la primera de la cola.
            guardar_config("reproductor_pos_cola", str(int(self._posicion_cola)))

        except Exception as e:
            logger.error(f"Error persistiendo cola: {e}", exc_info=True)

    def _guardar_estado_reproduccion(self) -> None:
        """Guarda pista activa + posición (seg) para reanudar al reabrir la app.

        Se llama al cerrar: captura el tiempo de VLC ANTES de detener. La cola
        y el índice activo se persisten aparte en :meth:`_persistir_cola`.
        """
        try:
            pista_id = int(self._pista_activa.id) if self._pista_activa else 0
            pos_seg = 0.0
            if (self._media_player is not None
                    and self._estado in (EstadoReproductor.REPRODUCIENDO, EstadoReproductor.PAUSADO)):
                try:
                    pos_seg = max(0.0, self._media_player.get_time() / 1000.0)
                except Exception:
                    pos_seg = 0.0
            # Caso "sesión restaurada pero no reproducida aún": no hay
            # pista_activa, pero sí un índice activo y una posición pendiente.
            # Preservamos esos valores para no perder el punto de reanudación.
            if pista_id <= 0 and self._activa_desde_cola and self._cola:
                idx = max(0, min(self._posicion_cola, len(self._cola) - 1))
                pista_id = int(self._cola[idx].get("id") or 0)
                if pos_seg <= 0.0:
                    pos_seg = max(0.0, float(self._reanudar_seg_pendiente or 0.0))
            guardar_config("reproductor_pista_id", str(pista_id))
            guardar_config("reproductor_pos_seg", f"{pos_seg:.3f}")
            guardar_config("reproductor_pos_cola", str(int(self._posicion_cola)))
            logger.info(
                "Estado del reproductor guardado: pista_id=%s, pos=%.1fs, "
                "pos_cola=%d, cola=%d pista(s).",
                pista_id, pos_seg, int(self._posicion_cola), len(self._cola),
            )
        except Exception as exc:
            logger.debug("No se pudo guardar estado de reproducción: %s", exc)

    # ------------------------------------------------------------------
    # CIERRE ORDENADO
    # ------------------------------------------------------------------

    def preparar_cierre(self) -> None:
        """Corta el audio al cerrar la ventana SIN perder la sesión.

        Se invoca desde ``Principal.qml.onClosing`` para silenciar VLC de
        inmediato (la ruta de ``aboutToQuit`` puede tardar y dejaría audio
        huérfano). A diferencia de :meth:`_detener_y_limpiar_pista_activa` +
        :meth:`limpiar_cola` (lo que se usaba antes), NO borra la pista activa
        ni vacía la cola: solo persiste el estado actual y para el audio. Así
        la última pista/posición/cola sobrevive al cierre y se reanuda al
        reabrir la app — esa limpieza prematura era la causa real de que la
        persistencia "no se aplicara" pese a ser correcta a nivel de servicio.

        Idempotente. Tras llamarla, :meth:`cerrar` omite el guardado (con VLC
        ya detenido la posición leería 0 y machacaría el punto de reanudación).
        """
        if self._cerrado or self._cierre_preparado:
            return
        # 1) Persistir estado ANTES de tocar VLC: _guardar_estado_reproduccion
        #    necesita get_time() para capturar la posición de reanudación.
        self._guardar_estado_reproduccion()
        self._cierre_preparado = True
        # 2) Detener el hilo de progreso y cortar el audio, conservando el
        #    estado lógico (pista_activa, cola, posición de cola) intacto.
        self._activo = False
        try:
            if self._media_player is not None:
                self._media_player.stop()
        except Exception as exc:
            logger.debug("preparar_cierre stop() fallo: %s", exc)

    def cerrar(self) -> None:
        """Detiene reproduccion, libera VLC y para el hilo de progreso.

        Debe llamarse antes de que la app salga (idealmente desde
        QGuiApplication.aboutToQuit). Sin esto:
          - VLC puede seguir emitiendo audio tras cerrar la ventana.
          - El callback MediaPlayerEndReached puede disparar despues de
            que VLC se haya liberado (segfault nativo).
          - El hilo de progreso queda corriendo aunque sea daemon, lo
            que mantiene callbacks vivos durante el teardown.

        Idempotente: se puede invocar varias veces sin efecto adicional.
        """
        if self._cerrado:
            return
        self._cerrado = True

        # 0) Guardar estado de reproducción (pista + posición) ANTES de detener
        #    VLC, para poder reanudar la sesión al reabrir la app. Si ya se
        #    guardó en preparar_cierre() (cierre normal de ventana), no se
        #    repite: VLC ya está parado y leería posición 0.
        if not self._cierre_preparado:
            self._guardar_estado_reproduccion()

        # 1) Marcar inactivo para que el hilo de progreso salga del while.
        self._activo = False

        # 2) Cancelar el Timer diferido de fin de pista antes de tocar VLC.
        timer_fin = self._timer_fin_pista
        self._timer_fin_pista = None
        if timer_fin is not None:
            try:
                timer_fin.cancel()
            except Exception as exc:
                logger.debug("cancelar timer fin pista fallo: %s", exc)

        # 3) Desconectar evento de fin antes de stop() para evitar reentrancia.
        try:
            if self._media_player is not None:
                em = self._media_player.event_manager()
                em.event_detach(_vlc.EventType.MediaPlayerEndReached)
        except Exception as exc:
            logger.debug("event_detach VLC fallo: %s", exc)

        # 4) Detener reproduccion. stop() es seguro aunque ya este detenido.
        try:
            if self._media_player is not None:
                self._media_player.stop()
        except Exception as exc:
            logger.debug("media_player.stop() fallo en cierre: %s", exc)

        # 5) Esperar a que el hilo de progreso salga (es daemon, pero
        # esperar previene que callbacks vivos toquen pista_activa
        # mientras destruimos el reproductor).
        hilo = self._hilo_progreso
        if hilo is not None and hilo.is_alive():
            try:
                hilo.join(timeout=1.0)
            except Exception as exc:
                logger.debug("join hilo progreso fallo: %s", exc)
        self._hilo_progreso = None

        # 6) Liberar handles de VLC. Tras release() el objeto no debe
        # tocarse mas: lo dejamos en None.
        try:
            if self._media_player is not None:
                self._media_player.release()
        except Exception as exc:
            logger.debug("media_player.release() fallo: %s", exc)
        finally:
            self._media_player = None

        try:
            if self._instancia_vlc is not None:
                self._instancia_vlc.release()
        except Exception as exc:
            logger.debug("instancia_vlc.release() fallo: %s", exc)
        finally:
            self._instancia_vlc = None

        # 7) Vaciar callbacks: nadie debe seguir recibiendo eventos
        # despues del cierre.
        self._cb_progreso.clear()
        self._cb_estado.clear()
        self._cb_cola.clear()
        self._cb_aviso.clear()
        self._cb_modo_dj.clear()

        self._estado = EstadoReproductor.DETENIDO

    def _restaurar_cola_persistida(self) -> None:
        """Restaura cola desde SQLite para retomar sesión previa."""
        try:
            filas = obtener_filas(
                """
                SELECT p.*
                FROM cola c
                JOIN pistas p ON p.id = c.pista_id
                WHERE p.estado='biblioteca'
                ORDER BY c.posicion
                """
            )
            self._cola = [self._normalizar_datos_pista(dict(f)) for f in filas]
            self._cola_base = [dict(pista) for pista in self._cola]
            self._posicion_cola = 0
            self._activa_desde_cola = False
            if self._aleatorio:
                self._aleatorizar_cola_locked()
            self._actualizar_contexto_desde_cola_locked()
            self._restaurar_pista_activa_persistida()
        except Exception as e:
            logger.warning(f"No se pudo restaurar cola persistida: {e}")
            self._cola = []
            self._cola_base = []
            self._activa_desde_cola = False
            self._contexto_reproduccion = []
            self._posicion_contexto = 0

    def _restaurar_pista_activa_persistida(self) -> None:
        """Retoma la pista que sonaba al cerrar (no la primera de la cola).

        Posiciona la cola en la pista activa previa y anota la posición (seg)
        para reanudarla en cuanto el usuario pulse play. NO marca `pista_activa`
        ni arranca audio: respeta el contrato "cola restaurada sin activar"
        (la barra la muestra vía `pista_visual`). Solo actúa si en la sesión
        anterior había una pista realmente activa (``reproductor_pista_id`` > 0);
        una cola que nunca se reprodujo se restaura tal cual, sin índice activo.
        """
        if not self._cola:
            return
        try:
            pista_id_guardada = int(obtener_config("reproductor_pista_id", "0") or 0)
            pos_cola_guardada = int(obtener_config("reproductor_pos_cola", "0") or 0)
            pos_seg_guardada = float(obtener_config("reproductor_pos_seg", "0") or 0.0)
        except (ValueError, TypeError):
            return

        # Contrato: solo se restaura un índice ACTIVO si en la sesión anterior
        # había una pista realmente activa (`reproductor_pista_id` > 0). Una
        # cola que se cargó pero nunca se reprodujo se restaura tal cual, sin
        # índice activo (la barra la muestra vía `pista_visual`/continuar).
        if pista_id_guardada <= 0:
            return

        idx = -1
        for i, pista in enumerate(self._cola):
            if int(pista.get("id") or 0) == pista_id_guardada:
                idx = i
                break
        if idx < 0 and 0 <= pos_cola_guardada < len(self._cola):
            idx = pos_cola_guardada
        if idx < 0:
            return

        self._posicion_cola = idx
        self._activa_desde_cola = True
        # Reanudar posición salvo que estuviéramos casi al final de la pista.
        dur = float(self._cola[idx].get("duracion_seg") or 0.0)
        if pos_seg_guardada > 0.5 and (dur <= 0 or pos_seg_guardada < dur - 2.0):
            self._reanudar_seg_pendiente = pos_seg_guardada
        logger.info(
            "Reproductor restaurado: pista índice %d/%d (pista_id=%s) reanuda en %.1fs.",
            idx, len(self._cola), pista_id_guardada, self._reanudar_seg_pendiente,
        )
