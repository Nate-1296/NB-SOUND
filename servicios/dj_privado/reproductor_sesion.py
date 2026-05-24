# =============================================================================
# servicios/dj_privado/reproductor_sesion.py
#
# Reproductor propio de la sesion DJ. Aislado del reproductor global.
#
# Filosofia:
#   - Una sesion DJ NO es una playlist normal: tiene transiciones planificadas
#     (TransicionPlan) que deben EJECUTARSE como crossfade real, no como
#     cambios de pista secos.
#   - Usa DOS instancias de VLC (deck A y deck B) para poder mezclar dos
#     pistas durante la ventana de overlap.
#   - Vive en un hilo de polling propio (~50ms tick) que orquesta el
#     crossfade y reporta posicion.
#   - Es state-machine simple: detenido | preparando | reproduciendo |
#     transicionando | pausado | finalizado.
#   - NO toca el reproductor global. El llamador es responsable de suspenderlo
#     y reanudarlo (Reproductor.set_modo_dj).
#
# Tecnicas de transicion implementadas:
#   - cut:           cambio seco (sin solapamiento).
#   - crossfade:     fade lineal sobre overlap_seg.
#   - mix_armonico:  fade exponencial mas largo (mejor sensacion organica).
#   - drone:         decay lento de A, B entra suave (final cinematic).
# =============================================================================

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from infra.logger import obtener_logger
from servicios.dj_privado.mix_engine import (
    EjecutorMezcla,
    MixEngine,
    PlanMezcla,
)
from servicios.dj_privado.persistencia import listar_pistas_sesion, obtener_sesion
from servicios.dj_privado.transiciones import TransicionPlan

logger = obtener_logger(__name__)

try:
    import vlc as _vlc  # type: ignore
    VLC_DISPONIBLE = True
except Exception:
    _vlc = None  # type: ignore
    VLC_DISPONIBLE = False


def _extraer_perfil_narrativo(resumen_json: str) -> list:
    """Reconstruye la lista de SessionPhase del resumen guardado.

    El resumen puede no traer el perfil (sesiones antiguas); en ese caso
    devolvemos lista vacía y el mix engine usará "groove" como default.
    """
    if not resumen_json:
        return []
    try:
        data = json.loads(resumen_json) if isinstance(resumen_json, str) else dict(resumen_json)
    except Exception:
        return []
    bruto = data.get("perfil_narrativo") or []
    if not isinstance(bruto, list):
        return []
    try:
        from servicios.dj_privado.narrativa import SessionPhase
    except Exception:
        return []
    fases = []
    for item in bruto:
        if not isinstance(item, dict):
            continue
        try:
            fases.append(SessionPhase(
                name=str(item.get("name") or ""),
                start_t=float(item.get("start_t") or 0.0),
                end_t=float(item.get("end_t") or 0.0),
                target_energy=float(item.get("target_energy") or 0.5),
                target_tension=float(item.get("target_tension") or 0.5),
                target_density=float(item.get("target_density") or 0.5),
                target_brightness=float(item.get("target_brightness") or 0.5),
                target_calmness=float(item.get("target_calmness") or 0.5),
                descripcion=str(item.get("descripcion") or ""),
            ))
        except Exception:
            continue
    return fases


# =============================================================================
# ESTADOS
# =============================================================================

class EstadoSesion(Enum):
    DETENIDO        = "detenido"
    PREPARANDO      = "preparando"
    REPRODUCIENDO   = "reproduciendo"
    TRANSICIONANDO  = "transicionando"
    PAUSADO         = "pausado"
    FINALIZADO      = "finalizado"
    ERROR           = "error"


# =============================================================================
# DATAMODEL: pista cargada en sesion
# =============================================================================

@dataclass
class PistaSesion:
    """Datos mínimos para reproducir una pista de la sesion.

    `bpm` se carga del JOIN con `track_audio_features` (puede ser None) y
    se usa para que el mix engine decida técnica y mix points.

    `mix_in_seg` y `mix_out_seg` son los puntos óptimos de entrada y
    salida calculados por el mix engine. El reproductor:
      - Hace seek a `mix_in_seg` en el deck entrante de cada transición.
      - Arranca la transición saliente al llegar a `mix_out_seg` en lugar
        de esperar al final natural. Esto es lo que hace que la sesión
        mezcle SEGMENTOS de pistas, no pistas completas.
    """
    posicion: int
    pista_id: int
    titulo: str
    artista: str
    album: str
    ruta_archivo: str
    duracion_seg: float
    transicion: Optional[TransicionPlan] = None   # transicion que ENTRA a esta pista
    estado: str = "planificada"
    bloqueada: bool = False
    bpm: Optional[float] = None
    mix_in_seg: Optional[float] = None
    mix_out_seg: Optional[float] = None


# =============================================================================
# CALLBACKS
# =============================================================================

# (estado: EstadoSesion, indice_actual: int, total: int) -> None
TipoCallbackEstado     = Callable[["EstadoSesion", int, int], None]
# (posicion_global_seg, duracion_total_seg, posicion_pista_seg, duracion_pista_seg)
TipoCallbackProgreso   = Callable[[float, float, float, float], None]
# (indice_nuevo, datos_pista_dict)
TipoCallbackPistaCambio = Callable[[int, dict], None]
# (plan_dict, indice_a, indice_b)
TipoCallbackTransicion = Callable[[dict, int, int], None]


# =============================================================================
# REPRODUCTOR DE SESION
# =============================================================================

class ReproductorSesionDj:
    """Controla la reproduccion de una sesion DJ con crossfade real.

    Uso tipico:
        rep = ReproductorSesionDj()
        rep.cargar_sesion(sesion_id=42)
        rep.play()
        ...
        rep.detener()

    Es seguro instanciar uno por vista. NO mantiene estado entre sesiones; al
    llamar `cargar_sesion` se reinicia todo.
    """

    # Frecuencia del hilo de polling (segundos). 50ms = 20Hz, suficiente para
    # crossfade percibido como suave sin saturar CPU.
    TICK = 0.05

    # Si una transicion no especifica overlap, usa este valor por defecto.
    OVERLAP_DEFAULT = 4.0

    def __init__(
        self,
        *,
        permitir_modo_simulado: bool = False,
        mix_engine: Optional[MixEngine] = None,
        vlc_instance: Optional[object] = None,
    ) -> None:
        self._permitir_modo_simulado = bool(permitir_modo_simulado)
        # Si se inyecta una instancia VLC (la del Reproductor principal),
        # reutilizamos esa para crear los decks. Dos `vlc.Instance` vivas
        # en el mismo proceso a veces crashean libvlc en Linux porque sus
        # módulos internos se inicializan dos veces sin sincronización.
        self._instancia_inyectada = vlc_instance
        self._sesion_id: int = 0
        self._sesion_prompt: str = ""
        self._pistas: list[PistaSesion] = []
        self._indice_actual: int = -1

        self._estado: EstadoSesion = EstadoSesion.DETENIDO
        self._volumen: int = 80   # 0..100, volumen "objetivo" de la sesion

        self._cb_estado:       list[TipoCallbackEstado] = []
        self._cb_progreso:     list[TipoCallbackProgreso] = []
        self._cb_pista_cambio: list[TipoCallbackPistaCambio] = []
        self._cb_transicion:   list[TipoCallbackTransicion] = []

        # VLC
        self._instancia: Optional[object] = None
        self._deck_a: Optional[object] = None   # reproduce la pista "principal"
        self._deck_b: Optional[object] = None   # se prepara para la siguiente
        self._deck_activo: str = "a"            # "a" o "b"
        self._inicializar_vlc()

        # Mix engine: si no se inyecta, el reproductor sigue funcionando con
        # crossfade volumétrico clásico (compatibilidad con tests existentes).
        self._mix_engine: Optional[MixEngine] = mix_engine

        # Perfil narrativo (fases) de la sesión activa. Vacío si la sesión
        # no se ha cargado o no tiene perfil registrado.
        self._perfil_narrativo: list = []

        # Caché de duraciones para construir el progreso global sin iterar
        # toda la lista cada tick (~5 Hz). Se recalcula al cargar/saltar.
        self._duracion_total_seg: float = 0.0
        self._prefijo_duraciones: list[float] = []

        # Estado de transicion en vivo (None si no hay crossfade ahora mismo)
        self._transicion_activa: Optional[dict] = None
        # Ejecutor de mezcla activo (cuando hay mix_engine). Mantiene los
        # ecualizadores asignados durante la transición.
        self._ejecutor_mezcla: Optional[EjecutorMezcla] = None

        # Lock y hilo
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._hilo: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # CONFIGURACIÓN DE MOTOR
    # ------------------------------------------------------------------

    def configurar_mix_engine(self, mix_engine: Optional[MixEngine]) -> None:
        """Permite inyectar/reemplazar el mix engine en runtime.

        Cambiarlo durante una transición activa no afecta la transición en
        curso (el ejecutor ya tiene su PlanMezcla); aplicará a la siguiente.
        """
        with self._lock:
            self._mix_engine = mix_engine

    # ------------------------------------------------------------------
    # INIT
    # ------------------------------------------------------------------

    def _inicializar_vlc(self) -> None:
        if not VLC_DISPONIBLE:
            if not self._permitir_modo_simulado:
                logger.warning("VLC no disponible para ReproductorSesionDj")
            return
        try:
            if self._instancia_inyectada is not None:
                # Reutilizar la instancia del Reproductor principal: solo
                # creamos media_players nuevos sobre ella. Las opciones
                # que antes le pasábamos a `_vlc.Instance` (`--codec=avcodec`,
                # `--avcodec-error-resilience=4`) ahora se aplican por
                # media via `media.add_option(...)` al cargar cada pista.
                self._instancia = self._instancia_inyectada
            else:
                # Fallback (tests / uso aislado): instancia propia. En la
                # app real siempre se inyecta la del Reproductor para
                # evitar tener dos instancias libvlc compitiendo por el
                # sink de audio.
                self._instancia = _vlc.Instance(
                    "--no-xlib --quiet --codec=avcodec --avcodec-error-resilience=4"
                )
            self._deck_a = self._instancia.media_player_new()
            self._deck_b = self._instancia.media_player_new()
            # Volumen inicial cero en deck B para que entre desde silencio.
            try:
                self._deck_a.audio_set_volume(self._volumen)
                self._deck_b.audio_set_volume(0)
            except Exception as _exc:
                logger.debug("Excepcion ignorada en %s: %s", "reproductor_sesion.py", _exc)
        except Exception as exc:
            logger.warning("VLC no inicializo para sesion DJ: %s", exc, exc_info=True)
            self._instancia = None
            self._deck_a = None
            self._deck_b = None

    # ------------------------------------------------------------------
    # CALLBACKS
    # ------------------------------------------------------------------

    def on_estado(self, cb: TipoCallbackEstado) -> None:
        self._cb_estado.append(cb)

    def on_progreso(self, cb: TipoCallbackProgreso) -> None:
        self._cb_progreso.append(cb)

    def on_pista_cambio(self, cb: TipoCallbackPistaCambio) -> None:
        self._cb_pista_cambio.append(cb)

    def on_transicion(self, cb: TipoCallbackTransicion) -> None:
        self._cb_transicion.append(cb)

    def off_estado(self, cb: TipoCallbackEstado) -> None:
        try: self._cb_estado.remove(cb)
        except ValueError: pass

    def off_progreso(self, cb: TipoCallbackProgreso) -> None:
        try: self._cb_progreso.remove(cb)
        except ValueError: pass

    def off_pista_cambio(self, cb: TipoCallbackPistaCambio) -> None:
        try: self._cb_pista_cambio.remove(cb)
        except ValueError: pass

    def off_transicion(self, cb: TipoCallbackTransicion) -> None:
        try: self._cb_transicion.remove(cb)
        except ValueError: pass

    def _emitir_estado(self) -> None:
        for cb in list(self._cb_estado):
            try:
                cb(self._estado, self._indice_actual, len(self._pistas))
            except Exception:
                logger.exception("cb estado fallo")

    def _recalcular_prefijo_duraciones_locked(self) -> None:
        """Reconstruye el prefijo acumulado de duraciones.

        El polling lo usa para calcular la posición global sin iterar la
        lista de pistas en cada tick (~5 Hz). Llamar tras cualquier
        mutación de `self._pistas` que afecte cuentas.
        """
        acumulado = 0.0
        self._prefijo_duraciones = []
        for p in self._pistas:
            self._prefijo_duraciones.append(acumulado)
            acumulado += float(p.duracion_seg or 0.0)
        self._duracion_total_seg = acumulado

    def _emitir_pista_cambio(self, indice: int) -> None:
        if indice < 0 or indice >= len(self._pistas):
            return
        p = self._pistas[indice]
        datos = {
            "posicion":     p.posicion,
            "pista_id":     p.pista_id,
            "titulo":       p.titulo,
            "artista":      p.artista,
            "album":        p.album,
            "duracion_seg": p.duracion_seg,
            "indice":       indice,
            "total":        len(self._pistas),
        }
        for cb in list(self._cb_pista_cambio):
            try:
                cb(indice, datos)
            except Exception:
                logger.exception("cb pista_cambio fallo")

    def _emitir_transicion(self, plan: dict, idx_a: int, idx_b: int) -> None:
        for cb in list(self._cb_transicion):
            try:
                cb(plan, idx_a, idx_b)
            except Exception:
                logger.exception("cb transicion fallo")

    # ------------------------------------------------------------------
    # CARGA DE SESION
    # ------------------------------------------------------------------

    def cargar_sesion(self, sesion_id: int) -> int:
        """Carga las pistas de una sesion desde BD.

        Devuelve el numero de pistas reproducibles.
        """
        with self._lock:
            self._detener_interno(notificar=False)
            fila = obtener_sesion(int(sesion_id))
            if not fila:
                self._sesion_id = 0
                self._sesion_prompt = ""
                self._pistas = []
                self._indice_actual = -1
                self._perfil_narrativo = []
                return 0
            self._sesion_id = int(sesion_id)
            self._sesion_prompt = fila.prompt_original or ""
            self._perfil_narrativo = _extraer_perfil_narrativo(fila.resumen_json)

            filas = listar_pistas_sesion(int(sesion_id))
            pistas: list[PistaSesion] = []
            for f in filas:
                if f["estado"] == "saltada":
                    # Las saltadas no se vuelven a reproducir automaticamente.
                    continue
                trans_dict = f.get("transicion") or {}
                trans_plan: Optional[TransicionPlan] = None
                if trans_dict and isinstance(trans_dict, dict) and "score" in trans_dict:
                    try:
                        trans_plan = TransicionPlan(
                            score=float(trans_dict.get("score") or 0.0),
                            factor_bpm=float(trans_dict.get("factor_bpm") or 0.0),
                            factor_key=float(trans_dict.get("factor_key") or 0.0),
                            factor_energia=float(trans_dict.get("factor_energia") or 0.0),
                            delta_bpm=trans_dict.get("delta_bpm"),
                            delta_camelot=trans_dict.get("delta_camelot"),
                            delta_energia=trans_dict.get("delta_energia"),
                            razones=list(trans_dict.get("razones") or []),
                            tecnica_sugerida=str(trans_dict.get("tecnica_sugerida") or "crossfade"),
                            overlap_seg=float(trans_dict.get("overlap_seg") or self.OVERLAP_DEFAULT),
                            estilo_aplicado=str(trans_dict.get("estilo_aplicado") or "smooth"),
                        )
                    except (TypeError, ValueError):
                        trans_plan = None
                bpm_raw = f.get("bpm")
                pistas.append(PistaSesion(
                    posicion=int(f["posicion"]),
                    pista_id=int(f.get("pista_id") or 0),
                    titulo=str(f.get("titulo") or ""),
                    artista=str(f.get("artista_nombre") or ""),
                    album=str(f.get("album_titulo") or ""),
                    ruta_archivo=str(f.get("ruta_archivo") or ""),
                    duracion_seg=float(f.get("duracion_seg") or 0.0),
                    transicion=trans_plan,
                    estado=str(f.get("estado") or "planificada"),
                    bloqueada=bool(f.get("bloqueada") or False),
                    bpm=float(bpm_raw) if bpm_raw is not None else None,
                ))
            # Validar archivos disponibles para evitar saltos en runtime.
            pistas_validas = []
            for p in pistas:
                if not p.ruta_archivo:
                    continue
                if not Path(p.ruta_archivo).expanduser().exists():
                    logger.warning("sesion %d: archivo no existe %s", sesion_id, p.ruta_archivo)
                    continue
                pistas_validas.append(p)
            self._pistas = pistas_validas
            self._indice_actual = -1
            self._transicion_activa = None
            self._recalcular_prefijo_duraciones_locked()
            # Calcular mix points por BPM (barato e inmediato). El cálculo
            # por RMS es opt-in y solo se haría en pre-fetch agresivo.
            self._calcular_mix_points_basicos_locked()
            # Pre-fetch de stems en background: encola las primeras pistas
            # para HARMONIC_MIX. Es no bloqueante; si el motor está en LOW
            # o karaoke no está disponible, simplemente no hace nada.
            self._lanzar_pre_fetch_stems_locked()
            return len(self._pistas)

    def _lanzar_pre_fetch_stems_locked(self) -> None:
        """Encola en background el procesamiento de stems para las primeras
        pistas. Idempotente y silencioso si el motor no soporta HARMONIC_MIX.
        """
        if self._mix_engine is None or not self._pistas:
            return
        try:
            from servicios.dj_privado.stems_prefetch import pre_fetch_inicial_async
            pre_fetch_inicial_async(
                [p.pista_id for p in self._pistas if p.pista_id > 0],
                perfil=self._mix_engine.perfil,
            )
        except Exception:
            logger.exception("no se pudo lanzar pre-fetch de stems")

    def _calcular_mix_points_basicos_locked(self) -> None:
        """Pobla mix_in_seg/mix_out_seg de cada pista usando solo BPM.

        Es una operación O(N) sin I/O: el motor decide por reglas simples
        sobre BPM y duración. Si no hay mix engine inyectado, no hace nada
        y las pistas se reproducen completas (comportamiento legacy).
        """
        if self._mix_engine is None:
            return
        for p in self._pistas:
            if p.mix_in_seg is not None and p.mix_out_seg is not None:
                continue
            try:
                mp = self._mix_engine.calcular_mix_points(
                    p.pista_id, p.ruta_archivo, p.duracion_seg, p.bpm,
                    permitir_rms=False,
                )
                p.mix_in_seg = mp.mix_in_seg
                p.mix_out_seg = mp.mix_out_seg
            except Exception:
                # Falla en una pista: dejarla a "tocar completa" sin propagar.
                logger.exception("mix points fallaron para pista %d", p.pista_id)

    # ------------------------------------------------------------------
    # PROPIEDADES PUBLICAS
    # ------------------------------------------------------------------

    @property
    def sesion_id(self) -> int:
        return self._sesion_id

    @property
    def sesion_prompt(self) -> str:
        return self._sesion_prompt

    @property
    def estado(self) -> EstadoSesion:
        return self._estado

    @property
    def indice_actual(self) -> int:
        return self._indice_actual

    @property
    def total_pistas(self) -> int:
        return len(self._pistas)

    @property
    def pista_actual(self) -> Optional[PistaSesion]:
        if 0 <= self._indice_actual < len(self._pistas):
            return self._pistas[self._indice_actual]
        return None

    @property
    def transicion_activa(self) -> Optional[dict]:
        return self._transicion_activa

    @property
    def volumen(self) -> int:
        return self._volumen

    def snapshot(self) -> dict:
        """Estado serializable para la UI."""
        return {
            "sesion_id":     self._sesion_id,
            "prompt":        self._sesion_prompt,
            "estado":        self._estado.value,
            "indice":        self._indice_actual,
            "total":         len(self._pistas),
            "volumen":       self._volumen,
            "transicion":    self._transicion_activa,
        }

    # ------------------------------------------------------------------
    # CONTROL
    # ------------------------------------------------------------------

    def play(self) -> bool:
        """Inicia o reanuda la reproduccion.

        Si esta detenido, arranca en la pista 0. Si esta pausado, reanuda.
        """
        with self._lock:
            if not self._pistas:
                return False
            if self._estado == EstadoSesion.PAUSADO:
                self._reanudar_desde_pausa_locked()
                return True
            if self._estado in (EstadoSesion.DETENIDO, EstadoSesion.FINALIZADO, EstadoSesion.ERROR):
                self._indice_actual = 0
                ok = self._reproducir_pista_actual_locked()
                if not ok:
                    return False
                self._estado = EstadoSesion.REPRODUCIENDO
                self._emitir_estado()
                self._emitir_pista_cambio(self._indice_actual)
                self._iniciar_hilo_polling_locked()
                return True
            # Ya esta reproduciendo o transicionando: no-op.
            return True

    def pause(self) -> bool:
        with self._lock:
            if self._estado not in (EstadoSesion.REPRODUCIENDO, EstadoSesion.TRANSICIONANDO):
                return False
            if self._deck_a is not None:
                try: self._deck_a.set_pause(1)
                except Exception: pass
            if self._deck_b is not None:
                try: self._deck_b.set_pause(1)
                except Exception: pass
            self._estado = EstadoSesion.PAUSADO
            self._emitir_estado()
            return True

    def _reanudar_desde_pausa_locked(self) -> None:
        if self._deck_a is not None:
            try: self._deck_a.set_pause(0)
            except Exception: pass
        if self._deck_b is not None:
            try: self._deck_b.set_pause(0)
            except Exception: pass
        self._estado = EstadoSesion.REPRODUCIENDO
        self._emitir_estado()

    def toggle(self) -> None:
        if self._estado == EstadoSesion.PAUSADO:
            self.play()
        elif self._estado in (EstadoSesion.REPRODUCIENDO, EstadoSesion.TRANSICIONANDO):
            self.pause()
        else:
            self.play()

    def siguiente(self) -> bool:
        with self._lock:
            siguiente = self._indice_actual + 1
            if siguiente >= len(self._pistas):
                self._finalizar_locked()
                return False
            return self._saltar_a_locked(siguiente, hard_cut=True)

    def anterior(self) -> bool:
        with self._lock:
            anterior = max(0, self._indice_actual - 1)
            return self._saltar_a_locked(anterior, hard_cut=True)

    def saltar_a(self, indice: int) -> bool:
        with self._lock:
            if not (0 <= indice < len(self._pistas)):
                return False
            return self._saltar_a_locked(indice, hard_cut=True)

    def buscar_posicion(self, seg: float) -> bool:
        """Salta a una posicion dentro de la pista actual."""
        with self._lock:
            deck = self._deck_actual()
            if deck is None:
                return False
            pista = self.pista_actual
            if pista is None or pista.duracion_seg <= 0:
                return False
            porc = max(0.0, min(1.0, float(seg) / pista.duracion_seg))
            try:
                deck.set_position(porc)
                return True
            except Exception:
                return False

    def buscar_posicion_global(self, seg_global: float) -> bool:
        """Salta a una posición absoluta en el timeline COMPLETO de la sesión.

        Si la sesión tiene 3 pistas de 200s cada una y `seg_global=350`,
        salta a la pista 1 (índice 1) en offset 150s.

        Cancela cualquier transición activa antes del salto.
        """
        with self._lock:
            if not self._pistas:
                return False
            objetivo = max(0.0, float(seg_global))
            acum = 0.0
            indice_objetivo = -1
            offset_local = 0.0
            for idx, p in enumerate(self._pistas):
                dur_efectiva = p.duracion_seg
                if dur_efectiva <= 0:
                    continue
                if objetivo < acum + dur_efectiva:
                    indice_objetivo = idx
                    offset_local = max(0.0, objetivo - acum)
                    break
                acum += dur_efectiva
            if indice_objetivo < 0:
                # Pasado el final: ir a la ultima
                indice_objetivo = len(self._pistas) - 1
                offset_local = 0.0

            # Cancelar transicion en curso (si la hay) volviendo volumenes al objetivo.
            self._liberar_ejecutor_mezcla_locked()
            self._transicion_activa = None
            inactivo = self._deck_inactivo()
            if inactivo is not None:
                try: inactivo.stop(); inactivo.audio_set_volume(0)
                except Exception: pass

            # Saltar a la pista objetivo (puede ser la misma actual)
            if indice_objetivo == self._indice_actual:
                deck = self._deck_actual()
                if deck is None or self.pista_actual is None or self.pista_actual.duracion_seg <= 0:
                    return False
                porc = max(0.0, min(1.0, offset_local / self.pista_actual.duracion_seg))
                try:
                    deck.set_position(porc)
                    return True
                except Exception:
                    return False

            # Carga pista nueva con offset
            self._indice_actual = indice_objetivo
            ok = self._reproducir_pista_actual_locked()
            if not ok:
                return False
            self._estado = EstadoSesion.REPRODUCIENDO
            self._emitir_estado()
            self._emitir_pista_cambio(self._indice_actual)
            # Aplicar el offset
            if offset_local > 0.5:
                # Diferir el seek igual que en alternar_fuente_audio del global
                pista_obj = self.pista_actual
                if pista_obj and pista_obj.duracion_seg > 0:
                    porc = max(0.0, min(1.0, offset_local / pista_obj.duracion_seg))
                    threading.Thread(
                        target=self._aplicar_seek_diferido_locked,
                        args=(porc,), daemon=True,
                    ).start()
            return True

    def _aplicar_seek_diferido_locked(self, porc: float) -> None:
        """Espera a que VLC abra el media y aplica set_position. Polling corto."""
        deadline = time.monotonic() + 2.5
        while time.monotonic() < deadline:
            with self._lock:
                deck = self._deck_actual()
                if deck is None:
                    return
                try:
                    longitud = deck.get_length()
                except Exception:
                    longitud = -1
                if longitud and longitud > 0:
                    try:
                        deck.set_position(porc)
                    except Exception as _exc:
                        logger.debug("Excepcion ignorada en %s: %s", "reproductor_sesion.py", _exc)
                    return
            time.sleep(0.05)

    def set_volumen(self, valor: int) -> None:
        with self._lock:
            v = max(0, min(100, int(valor)))
            self._volumen = v
            # Si no estamos transicionando, ambos decks reflejan el volumen
            # objetivo (el deck inactivo siempre esta a 0 fuera de transicion).
            if self._transicion_activa is None:
                deck = self._deck_actual()
                if deck is not None:
                    try: deck.audio_set_volume(v)
                    except Exception: pass

    def detener(self) -> None:
        """Detiene la reproduccion sin cerrar la sesion (puede reanudarse con play)."""
        with self._lock:
            self._detener_interno(notificar=True)

    # ------------------------------------------------------------------
    # LIFECYCLE
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Libera recursos VLC. Tras esto, la instancia queda inservible.

        Marca el estado como DETENIDO antes del join: si el polling thread
        está esperando el lock, al despertarse verá el estado terminal y
        saldrá sin hacer trabajo. Luego liberamos decks e instancia bajo
        lock para que cualquier llamada concurrente (improbable a esta
        altura) vea decks None y no haga set/get sobre punteros muertos.
        """
        with self._lock:
            self._estado = EstadoSesion.DETENIDO
            self._liberar_ejecutor_mezcla_locked()
            self._transicion_activa = None
        self._stop_event.set()
        h = self._hilo
        if h is not None and h.is_alive():
            h.join(timeout=1.0)
        self._hilo = None
        with self._lock:
            for deck in (self._deck_a, self._deck_b):
                if deck is None: continue
                try: deck.stop()
                except Exception: pass
                try: deck.release()
                except Exception: pass
            self._deck_a = None
            self._deck_b = None
            inst = self._instancia
            self._instancia = None
        # Solo liberar la instancia VLC si la creamos nosotros. Si nos la
        # inyectó el Reproductor principal (caso normal en la app), es
        # propietario y la liberará él al cerrar.
        if inst is not None and self._instancia_inyectada is None:
            try: inst.release()
            except Exception: pass

    # ------------------------------------------------------------------
    # INTERNALS
    # ------------------------------------------------------------------

    def _deck_actual(self) -> Optional[object]:
        return self._deck_a if self._deck_activo == "a" else self._deck_b

    def _deck_inactivo(self) -> Optional[object]:
        return self._deck_b if self._deck_activo == "a" else self._deck_a

    def _swap_decks(self) -> None:
        self._deck_activo = "b" if self._deck_activo == "a" else "a"

    def _liberar_ejecutor_mezcla_locked(self) -> None:
        """Desconecta el EQ de los decks si había un ejecutor activo.

        Idempotente: seguro de llamar incluso si no hay ejecutor. Llamar
        siempre antes de marcar `_transicion_activa = None`.
        """
        if self._ejecutor_mezcla is not None:
            try:
                self._ejecutor_mezcla.liberar()
            except Exception as _exc:
                logger.debug("Excepcion ignorada en %s: %s", "reproductor_sesion.py", _exc)
            self._ejecutor_mezcla = None

    def _detener_interno(self, *, notificar: bool) -> None:
        self._liberar_ejecutor_mezcla_locked()
        for deck in (self._deck_a, self._deck_b):
            if deck is None: continue
            try: deck.stop()
            except Exception: pass
            try: deck.audio_set_volume(0)
            except Exception: pass
        if self._deck_a is not None:
            try: self._deck_a.audio_set_volume(self._volumen)
            except Exception: pass
        self._deck_activo = "a"
        self._estado = EstadoSesion.DETENIDO
        self._transicion_activa = None
        self._stop_event.set()
        self._hilo = None
        if notificar:
            self._emitir_estado()

    def _finalizar_locked(self) -> None:
        self._liberar_ejecutor_mezcla_locked()
        for deck in (self._deck_a, self._deck_b):
            if deck is None: continue
            try: deck.stop()
            except Exception: pass
        self._estado = EstadoSesion.FINALIZADO
        self._transicion_activa = None
        self._stop_event.set()
        self._hilo = None
        self._emitir_estado()

    def _reproducir_pista_actual_locked(self) -> bool:
        """Carga la pista actual en el deck activo y arranca."""
        pista = self.pista_actual
        if pista is None:
            return False
        deck = self._deck_actual()
        if deck is None:
            if self._permitir_modo_simulado:
                return True
            return False
        try:
            media = self._instancia.media_new(str(pista.ruta_archivo))
            # Aplicar las opciones que antes vivían en la Instance.
            # Si compartimos la Instance con el Reproductor principal,
            # estas opciones deben ir por media para no contaminar la
            # reproducción regular.
            try:
                media.add_option(":codec=avcodec")
                media.add_option(":avcodec-error-resilience=4")
            except Exception:
                pass
            deck.set_media(media)
            # Reset volumenes: actual al objetivo, inactivo a 0.
            try: deck.audio_set_volume(self._volumen)
            except Exception: pass
            inactivo = self._deck_inactivo()
            if inactivo is not None:
                try: inactivo.audio_set_volume(0); inactivo.stop()
                except Exception: pass
            deck.play()
            return True
        except Exception as exc:
            logger.error("error reproduciendo %s: %s", pista.ruta_archivo, exc, exc_info=True)
            self._estado = EstadoSesion.ERROR
            self._emitir_estado()
            return False

    def _saltar_a_locked(self, indice: int, *, hard_cut: bool = False) -> bool:
        """Salta a `indice` con cut seco (sin crossfade)."""
        self._indice_actual = indice
        self._liberar_ejecutor_mezcla_locked()
        self._transicion_activa = None
        ok = self._reproducir_pista_actual_locked()
        if not ok:
            return False
        if self._estado != EstadoSesion.PAUSADO:
            self._estado = EstadoSesion.REPRODUCIENDO
        self._emitir_estado()
        self._emitir_pista_cambio(self._indice_actual)
        self._iniciar_hilo_polling_locked()
        return True

    def _iniciar_hilo_polling_locked(self) -> None:
        """Arranca el hilo de polling SOLO si no hay uno vivo.

        Reinstanciar `_stop_event` mientras el viejo hilo sigue iterando
        produciría dos polling threads compitiendo por el lock y mutando
        estado en paralelo. La guard de `is_alive()` lo evita.
        """
        if self._hilo is not None and self._hilo.is_alive():
            return
        self._stop_event = threading.Event()
        t = threading.Thread(target=self._loop_polling, daemon=True, name="dj_sesion_loop")
        self._hilo = t
        t.start()

    # ------------------------------------------------------------------
    # CROSSFADE / POLLING
    # ------------------------------------------------------------------

    def _loop_polling(self) -> None:
        """Hilo de control: monitorea posición y orquesta crossfades.

        Cada tick (50 ms) lee la posición del deck activo bajo lock,
        decide si arrancar una transición, aplica el ejecutor activo si lo
        hay, y emite progreso a la UI ~5 Hz. Los callbacks se invocan
        FUERA del lock para evitar deadlocks con slots Qt que puedan
        re-entrar al reproductor.

        TODO el cuerpo va envuelto en try/except + log para que cualquier
        excepción Python (las nativas / SIGSEGV no las capturamos desde
        Python) deje rastro en disco y la sesión se cierre limpiamente
        en vez de dejar la app en un estado inconsistente.
        """
        try:
            self._loop_polling_inner()
        except Exception:
            logger.exception("DJ polling thread crashed")
            try:
                with self._lock:
                    self._estado = EstadoSesion.ERROR
                    self._stop_event.set()
                self._emitir_estado()
            except Exception:
                pass

    def _loop_polling_inner(self) -> None:
        ultima_emision_progreso = 0.0
        while not self._stop_event.wait(self.TICK):
            pendientes: list[tuple[str, tuple]] = []
            with self._lock:
                if self._estado not in (
                    EstadoSesion.REPRODUCIENDO,
                    EstadoSesion.TRANSICIONANDO,
                    EstadoSesion.PAUSADO,
                ):
                    break

                deck = self._deck_actual()
                pista = self.pista_actual
                if deck is None or pista is None:
                    continue

                # Pausados: no avanzamos pero seguimos vivos para reanudar.
                if self._estado == EstadoSesion.PAUSADO:
                    continue

                # Posición y duración del media activo. VLC retorna -1
                # mientras aún no parsea el archivo.
                try: pos_ms = deck.get_time()
                except Exception: pos_ms = -1
                pos_seg = max(0.0, pos_ms / 1000.0) if pos_ms is not None and pos_ms >= 0 else 0.0
                try: dur_ms = deck.get_length()
                except Exception: dur_ms = -1
                dur_seg = (dur_ms / 1000.0) if dur_ms and dur_ms > 0 else (pista.duracion_seg or 0.0)

                # Progreso ~5 Hz: encolamos para emitir fuera del lock.
                ahora = time.monotonic()
                if ahora - ultima_emision_progreso >= 0.2:
                    idx = max(0, self._indice_actual)
                    base = (
                        self._prefijo_duraciones[idx]
                        if 0 <= idx < len(self._prefijo_duraciones)
                        else self._duracion_total_seg
                    )
                    pendientes.append(("progreso", (
                        base + pos_seg, self._duracion_total_seg, pos_seg, dur_seg,
                    )))
                    ultima_emision_progreso = ahora

                # "Fin efectivo": `mix_out_seg` cuando hay siguiente pista
                # (mezcla segmentos); si es la última, su final natural.
                fin_efectivo = dur_seg
                tiene_siguiente = self._indice_actual + 1 < len(self._pistas)
                if (tiene_siguiente
                        and pista.mix_out_seg is not None
                        and pista.mix_out_seg > 0):
                    fin_efectivo = min(fin_efectivo, pista.mix_out_seg)

                # Disparar transición si toca.
                if self._transicion_activa is None and tiene_siguiente:
                    siguiente = self._pistas[self._indice_actual + 1]
                    plan_trans = siguiente.transicion
                    overlap = plan_trans.overlap_seg if plan_trans else self.OVERLAP_DEFAULT
                    tecnica = plan_trans.tecnica_sugerida if plan_trans else "crossfade"
                    if tecnica == "cut":
                        overlap = 0.0
                    restantes = max(0.0, fin_efectivo - pos_seg) if fin_efectivo > 0 else 999.0
                    if overlap > 0.0 and fin_efectivo > 0 and restantes <= overlap + 0.05:
                        self._iniciar_transicion_locked(overlap, tecnica, plan_trans)
                    elif overlap == 0.0 and fin_efectivo > 0 and restantes <= 0.05:
                        self._finalizar_pista_actual_locked()

                # Avanzar la transición activa.
                if self._transicion_activa is not None:
                    self._tick_transicion_locked(pos_seg, fin_efectivo)

                # Última pista: terminar al llegar al final.
                if (self._transicion_activa is None
                        and not tiene_siguiente
                        and fin_efectivo > 0
                        and pos_seg >= fin_efectivo - 0.05):
                    self._finalizar_locked()
                    break

            # Emitimos callbacks acumulados fuera del lock. Si el callback
            # vuelve a entrar al reproductor (vía señales Qt re-entrantes
            # en otro thread), no se autobloquea.
            for tipo, args in pendientes:
                if tipo == "progreso":
                    for cb in list(self._cb_progreso):
                        try: cb(*args)
                        except Exception: logger.exception("cb progreso fallo")

    def _iniciar_transicion_locked(self, overlap: float, tecnica: str, plan: Optional[TransicionPlan]) -> None:
        """Arranca crossfade: carga siguiente en deck inactivo y prepara fade.

        Si hay mix_engine inyectado, consulta el plan de mezcla concreto y
        crea un EjecutorMezcla. Si no hay mix_engine, se mantiene el
        comportamiento clásico (crossfade volumétrico simple).
        """
        siguiente_idx = self._indice_actual + 1
        if siguiente_idx >= len(self._pistas):
            return
        siguiente = self._pistas[siguiente_idx]
        actual = self.pista_actual
        inactivo = self._deck_inactivo()
        if inactivo is None or self._instancia is None:
            return

        # Plan de mezcla: si hay mix engine y datos suficientes, lo calcula.
        # Si falla por cualquier razón, fallback al overlap/tecnica clásicos.
        plan_mezcla: Optional[PlanMezcla] = None
        if self._mix_engine is not None and plan is not None and actual is not None:
            try:
                fase = self._fase_narrativa_actual_locked()
                plan_mezcla = self._mix_engine.preparar_transicion(
                    plan_transicion=plan,
                    pista_a_id=actual.pista_id,
                    pista_b_id=siguiente.pista_id,
                    pista_a_ruta=actual.ruta_archivo,
                    pista_b_ruta=siguiente.ruta_archivo,
                    pista_a_duracion=actual.duracion_seg,
                    pista_b_duracion=siguiente.duracion_seg,
                    pista_a_bpm=actual.bpm,
                    pista_b_bpm=siguiente.bpm,
                    fase_narrativa=fase,
                )
            except Exception:
                logger.exception("mix_engine.preparar_transicion falló; usando fallback")
                plan_mezcla = None

        ruta_audio_b = siguiente.ruta_archivo
        mix_in_b_seg = 0.0
        if plan_mezcla is not None:
            overlap = float(max(0.05, plan_mezcla.overlap_seg))
            tecnica = plan_mezcla.tecnica.value
            if plan_mezcla.ruta_audio_b_override:
                ruta_audio_b = plan_mezcla.ruta_audio_b_override
            mix_in_b_seg = max(0.0, float(plan_mezcla.mix_in_b_seg))

        try:
            media = self._instancia.media_new(str(ruta_audio_b))
            try:
                media.add_option(":codec=avcodec")
                media.add_option(":avcodec-error-resilience=4")
            except Exception:
                pass
            inactivo.set_media(media)
            inactivo.audio_set_volume(0)
            inactivo.play()
        except Exception as exc:
            logger.error("no se pudo iniciar siguiente deck: %s", exc, exc_info=True)
            # Caemos a cut seco si falla.
            self._finalizar_pista_actual_locked()
            return

        # Si la pista entrante debe empezar en un offset, programamos un seek
        # diferido (VLC necesita ~50-200 ms para abrir el media antes de
        # aceptar set_position).
        if mix_in_b_seg > 0.5 and siguiente.duracion_seg > 0:
            porc = max(0.0, min(0.95, mix_in_b_seg / siguiente.duracion_seg))
            threading.Thread(
                target=self._aplicar_seek_en_deck_inactivo,
                args=(porc,), daemon=True,
            ).start()

        # Liberar cualquier ejecutor previo (en teoría no debería haber:
        # cada transición libera al completar o cancelar) ANTES de crear el
        # nuevo, para no tener dos AudioEqualizer asignados al mismo deck.
        self._liberar_ejecutor_mezcla_locked()
        if plan_mezcla is not None:
            try:
                self._ejecutor_mezcla = EjecutorMezcla(
                    plan_mezcla,
                    deck_a=self._deck_actual(),
                    deck_b=inactivo,
                    volumen_objetivo=self._volumen,
                )
            except Exception:
                logger.exception("no se pudo crear EjecutorMezcla; usando fallback")
                self._ejecutor_mezcla = None

        self._transicion_activa = {
            "inicio_ts":   time.monotonic(),
            "overlap":     float(max(0.05, overlap)),
            "tecnica":     tecnica,
            "idx_a":       self._indice_actual,
            "idx_b":       siguiente_idx,
            "score":       (plan.score if plan else 0.5),
            "razones":     (list(plan.razones) if plan else []),
            "etiqueta_ui": (plan_mezcla.etiqueta_ui if plan_mezcla else None),
            "mix_in_b":    mix_in_b_seg,
            "stems_listos": bool(plan_mezcla.ruta_audio_b_override) if plan_mezcla else False,
        }
        self._estado = EstadoSesion.TRANSICIONANDO
        self._emitir_estado()
        # Emitir evento al modelo
        plan_dict = dict(self._transicion_activa)
        if plan is not None:
            plan_dict.update({
                "delta_bpm":     plan.delta_bpm,
                "delta_camelot": plan.delta_camelot,
                "delta_energia": plan.delta_energia,
            })
        self._emitir_transicion(plan_dict, self._indice_actual, siguiente_idx)

    def _fase_narrativa_actual_locked(self) -> str:
        """Calcula el nombre de la fase narrativa en la posición actual.

        Si no hay perfil cargado, asume "groove" (la fase más neutra). El
        cálculo de t normalizado suma la duración de las pistas anteriores
        más la actual, lo que aproxima "estamos saliendo de esta pista" —
        que es justo el momento en que el mix engine necesita la fase para
        decidir la técnica de la siguiente transición.
        """
        if not self._perfil_narrativo or not self._pistas:
            return "groove"
        dur_total = 0.0
        pos_global = 0.0
        idx_actual = self._indice_actual
        for idx, p in enumerate(self._pistas):
            dur_efectiva = p.duracion_seg
            dur_total += dur_efectiva
            if idx <= idx_actual:
                pos_global += dur_efectiva
        if dur_total <= 0:
            return "groove"
        t = max(0.0, min(1.0, pos_global / dur_total))
        try:
            from servicios.dj_privado.narrativa import fase_en_t
            return fase_en_t(self._perfil_narrativo, t).name
        except Exception:
            return "groove"

    def _aplicar_seek_en_deck_inactivo(self, porc: float) -> None:
        """Como _aplicar_seek_diferido_locked pero apuntando al deck inactivo.

        Es para el caso "la pista entrante arranca en mix_in_seg": el deck
        inactivo aún no abrió el media cuando llamamos al constructor del
        ejecutor, así que hacemos polling hasta tener longitud válida.
        """
        deadline = time.monotonic() + 2.5
        while time.monotonic() < deadline:
            with self._lock:
                deck = self._deck_inactivo()
                if deck is None:
                    return
                try:
                    longitud = deck.get_length()
                except Exception:
                    longitud = -1
                if longitud and longitud > 0:
                    try:
                        deck.set_position(porc)
                    except Exception as _exc:
                        logger.debug("Excepcion ignorada en %s: %s", "reproductor_sesion.py", _exc)
                    return
            time.sleep(0.05)

    def _tick_transicion_locked(self, pos_seg: float, dur_seg: float) -> None:
        """Aplica volumen (y EQ si aplica) y avanza si terminó la transición.

        Si hay un EjecutorMezcla activo, delega la modulación en él. Si no,
        usa las curvas clásicas (cut/mix_armonico/drone/crossfade).
        """
        info = self._transicion_activa
        if info is None:
            return
        elapsed = time.monotonic() - info["inicio_ts"]
        overlap = info["overlap"]
        progreso = max(0.0, min(1.0, elapsed / overlap))
        tecnica = info.get("tecnica") or "crossfade"

        deck_a_actual = self._deck_actual()
        deck_b_entrando = self._deck_inactivo()
        ejecutor = self._ejecutor_mezcla

        if ejecutor is not None:
            ejecutor.aplicar_tick(progreso)
        else:
            # Curvas clásicas: ruta de compatibilidad cuando no hay mix engine.
            if tecnica == "mix_armonico":
                v_a = (1.0 - progreso) ** 0.5
                v_b = progreso ** 0.5
            elif tecnica == "drone":
                v_a = max(0.0, (1.0 - progreso)) ** 0.7
                v_b = (progreso ** 1.2) * 0.85
            elif tecnica == "cut":
                v_a = 1.0 if progreso < 0.95 else 0.0
                v_b = 0.0 if progreso < 0.95 else 1.0
            else:
                v_a = 1.0 - progreso
                v_b = progreso
            vol_obj = self._volumen
            if deck_a_actual is not None:
                try: deck_a_actual.audio_set_volume(int(round(v_a * vol_obj)))
                except Exception: pass
            if deck_b_entrando is not None:
                try: deck_b_entrando.audio_set_volume(int(round(v_b * vol_obj)))
                except Exception: pass

        if progreso >= 1.0:
            # Transicion completa: swap, parar deck viejo, avanzar indice.
            try: deck_a_actual.stop()
            except Exception: pass
            try: deck_a_actual.audio_set_volume(0)
            except Exception: pass
            if ejecutor is not None:
                try:
                    ejecutor.liberar()
                except Exception as _exc:
                    logger.debug("Excepcion ignorada en %s: %s", "reproductor_sesion.py", _exc)
                self._ejecutor_mezcla = None
            self._swap_decks()
            self._indice_actual += 1
            self._transicion_activa = None
            self._estado = EstadoSesion.REPRODUCIENDO
            self._emitir_estado()
            self._emitir_pista_cambio(self._indice_actual)

    def _finalizar_pista_actual_locked(self) -> None:
        """Cut seco: detiene pista actual y arranca siguiente sin overlap."""
        siguiente_idx = self._indice_actual + 1
        if siguiente_idx >= len(self._pistas):
            self._finalizar_locked()
            return
        self._indice_actual = siguiente_idx
        # Reusar deck actual: para no liberar instancia VLC.
        ok = self._reproducir_pista_actual_locked()
        if ok:
            self._estado = EstadoSesion.REPRODUCIENDO
            self._emitir_estado()
            self._emitir_pista_cambio(self._indice_actual)
