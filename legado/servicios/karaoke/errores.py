# =============================================================================
# servicios/karaoke/errores.py
#
# Excepciones tipadas del subsistema karaoke. Cada error mapea a un codigo
# estable (string) que se persiste en `karaoke_jobs.error_codigo` y se usa
# tanto para logging como para que la UI muestre el mensaje apropiado.
#
# Jerarquia:
#   KaraokeError (base)
#   ├── BackendNoDisponibleError  — demucs/torch ausentes
#   ├── ModeloFaltanteError       — pesos no descargados o importacion fallida
#   ├── FfmpegFaltanteError       — ffmpeg no encontrado en PATH
#   ├── AudioCorruptoError        — decodificacion fallida o tensor invalido
#   ├── ArchivoNoExisteError      — ruta de pista no existe en disco
#   ├── MemoriaInsuficienteError  — OOM durante inferencia GPU/CPU
#   ├── TimeoutKaraokeError       — procesamiento excedio tiempo limite
#   └── KaraokeCanceladoError     — interrupcion cooperativa por stop_event
#
# El campo `codigo` de cada excepcion es el valor que se escribe en
# `karaoke_jobs.error_codigo`. La UI lo usa para elegir el mensaje
# localizado que se muestra al usuario. Mantener los codigos estables
# entre versiones para no romper jobs persistidos.
#
# El campo `detalle` transporta el traceback o mensaje tecnico original
# para logging; no se muestra directamente al usuario.
# =============================================================================

from __future__ import annotations


class KaraokeError(Exception):
    """Excepcion base del subsistema karaoke.

    Todos los errores del dominio karaoke heredan de esta clase. El atributo
    `codigo` identifica el tipo de error de forma estable (se persiste en BD).
    El argumento `detalle` acepta el mensaje tecnico original (stderr, traceback
    reducido, etc.) para logging sin exponerlo directamente en la UI.
    """

    codigo: str = "error_desconocido"

    def __init__(self, mensaje: str = "", *, detalle: str = "") -> None:
        self.detalle = detalle
        super().__init__(mensaje or self.__doc__ or self.codigo)


class BackendNoDisponibleError(KaraokeError):
    """Demucs no esta instalado o no se pudo importar."""
    codigo = "backend_no_disponible"


class ModeloFaltanteError(KaraokeError):
    """El modelo de demucs no se pudo cargar (no descargado o corrupto).

    Se lanza cuando `demucs.pretrained.get_model()` falla, ya sea porque los
    pesos no se descargaron aun, el hash es incorrecto, o el nombre del modelo
    es desconocido. La primera descarga de htdemucs (~80 MB) requiere internet.
    """
    codigo = "modelo_faltante"


class FfmpegFaltanteError(KaraokeError):
    """ffmpeg no esta disponible en el PATH del sistema.

    Se lanza tanto en la comprobacion previa de `separar_pista_instrumental`
    como si la conversion WAV→MP3 final falla. La instalacion de ffmpeg es
    responsabilidad del sistema operativo (apt/brew/pacman).
    """
    codigo = "ffmpeg_faltante"


class AudioCorruptoError(KaraokeError):
    """El archivo de audio no se pudo decodificar o proceso produjo un tensor invalido.

    Causas tipicas: formato no soportado por ffmpeg, archivo truncado, tensor
    de dimensiones inesperadas tras la decodificacion.
    """
    codigo = "audio_corrupto"


class ArchivoNoExisteError(KaraokeError):
    """La pista apunta a un archivo que no esta en disco.

    Puede ocurrir si la biblioteca fue movida o el archivo borrado entre el
    momento en que se encolo el job y el momento en que se procesa.
    """
    codigo = "archivo_no_existe"


class MemoriaInsuficienteError(KaraokeError):
    """El proceso se quedo sin memoria durante la separacion.

    Tipicamente un RuntimeError de CUDA con "out of memory". En modo CPU
    puede ocurrir con pistas muy largas (>30 min) en maquinas con poca RAM.
    """
    codigo = "memoria_insuficiente"


class TimeoutKaraokeError(KaraokeError):
    """El procesamiento excedio el tiempo maximo permitido."""
    codigo = "timeout"


class KaraokeCanceladoError(KaraokeError):
    """El job fue cancelado por el usuario antes de completarse.

    Se lanza cuando `stop_event.is_set()` es detectado entre segmentos del
    modelo en `_separar_por_segmentos`. El job queda en estado `cancelada`
    y la pista vuelve a `no_procesada`.
    """
    codigo = "cancelado"
