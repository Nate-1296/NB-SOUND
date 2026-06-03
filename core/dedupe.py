# =============================================================================
# core/dedupe.py
#
# Deteccion de duplicados dentro de una ejecucion del pipeline.
#
# Capas implementadas:
#   1) Duplicado exacto por hash SHA256 (archivo binariamente equivalente).
#   2) Duplicado semantico por identidad musical (ISRC o recording_id de MB).
#   3) Duplicado observable por metadatos visibles (titulo/artista/album
#      normalizados + duracion +-tolerancia + hash del archivo de portada).
#      Captura el "duplicado obvio" que no comparte hash ni ISRC/MBID: la misma
#      grabacion reimportada con otra codificacion/tag pero misma portada y
#      metadatos. El barrido periodico de servicios/dedupe_observable.py aplica
#      esta misma regla sobre la biblioteca ya catalogada.
#
# Este modulo no elimina archivos por si solo; solo toma decisiones de si un
# archivo debe considerarse duplicado frente a otro ya aceptado en la corrida.
#
# La normalizacion de texto del eje observable usa el MISMO algoritmo que el
# resto del sistema (utils.text.normalizar_para_comparar, re-exportado por
# servicios.explorador_ciego.hints). El hash de portada se calcula sobre el
# CONTENIDO del archivo, no sobre su ruta.
# =============================================================================

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config.settings import (
    DUPLICATE_POLICY,
    DUPLICATE_BETTER_MIN_DELTA,
    DUPLICATE_OBSERVABLE_TOLERANCIA_SEG,
)
from domain.models import ArchivoAudio, DecisionArchivo
from infra.logger import obtener_logger
from utils.text import normalizar_para_comparar

_log = obtener_logger("core.dedupe")


@dataclass(frozen=True)
class DuplicadoDetectado:
    tipo: str
    referencia: str


# -----------------------------------------------------------------------------
# Eje observable: utilidades puras reutilizables (importacion y barrido periodico)
# -----------------------------------------------------------------------------

# Clave observable de texto+portada (la duracion se compara aparte, con
# tolerancia): (titulo_norm, artista_norm, album_norm, portada_hash).
ClaveObservable = tuple[str, str, str, str]


def hash_portada(ruta) -> Optional[str]:
    """SHA256 del *contenido* del archivo de portada (no de su ruta).

    Devuelve ``None`` si la ruta es falsy o el archivo no puede leerse, de modo
    que la ausencia de portada nunca produzca una coincidencia observable. Lee
    por bloques para no cargar imagenes grandes en memoria.
    """
    if not ruta:
        return None
    try:
        h = hashlib.sha256()
        with open(ruta, "rb") as f:
            for bloque in iter(lambda: f.read(65536), b""):
                h.update(bloque)
        return h.hexdigest()
    except OSError:
        return None


def clave_observable(
    titulo: Optional[str],
    artista: Optional[str],
    album: Optional[str],
    portada_hash: Optional[str],
) -> Optional[ClaveObservable]:
    """Construye la clave observable normalizada o ``None`` si falta señal.

    Conservador por diseño: si cualquiera de los cuatro componentes (titulo,
    artista, album, portada) queda vacio tras normalizar, NO se forma clave, de
    modo que la ausencia de datos jamas produzca un falso positivo. La duracion
    se compara por separado (con tolerancia) porque no admite igualdad exacta.
    """
    t = normalizar_para_comparar(titulo or "")
    a = normalizar_para_comparar(artista or "")
    al = normalizar_para_comparar(album or "")
    if not t or not a or not al or not portada_hash:
        return None
    return (t, a, al, portada_hash)


def duraciones_equivalentes(
    dur_a,
    dur_b,
    tolerancia_seg: float = DUPLICATE_OBSERVABLE_TOLERANCIA_SEG,
) -> bool:
    """True si dos duraciones difieren a lo sumo ``tolerancia_seg`` segundos.

    Si alguna duracion es desconocida (None/no numerica) devuelve False: sin
    duracion comparable no podemos afirmar que sean el mismo material.
    """
    try:
        a = float(dur_a)
        b = float(dur_b)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= float(tolerancia_seg)


class GestorDuplicados:
    """Mantiene indices para detectar duplicados.

    Pre-carga los hashes / recording_ids / ISRCs de pistas ya en biblioteca
    al construirse, así una corrida que repite archivos ya importados en
    sesiones anteriores los marca como duplicados en vez de añadirlos
    como nuevos. Sin esta precarga, cancelar una importación a mitad y
    relanzarla suele dejar canciones duplicadas en la biblioteca (la
    primera corrida ya las había copiado, la segunda no las identifica
    porque los índices internos arrancaban vacíos cada vez).

    Tambien mantiene un indice observable (titulo/artista/album normalizados +
    portada -> duracion) que permite detectar el "duplicado obvio" de la tercera
    capa durante la importacion.
    """

    def __init__(self) -> None:
        self._por_hash: dict[str, Path] = {}
        self._por_identidad: dict[str, Path] = {}
        self._calidad_por_identidad: dict[str, float] = {}
        # Eje observable: clave (titulo,artista,album,portada_hash) -> lista de
        # (ruta, duracion_seg). Lista porque dos pistas pueden compartir clave
        # de texto+portada pero diferir en duracion mas alla de la tolerancia
        # (no serian el mismo material).
        self._por_observable: dict[ClaveObservable, list[tuple[Path, float]]] = {}
        self._precargar_desde_biblioteca()

    def _precargar_desde_biblioteca(self) -> None:
        """Llena los índices con lo que ya está catalogado en la BD.

        Lee de la tabla ``pistas``: las claves de identidad MusicBrainz
        (``mb_recording_id``) e ISRC viven ahí, no en una tabla aparte. Para el
        eje observable se hace LEFT JOIN con ``albums`` para obtener la portada
        del álbum (``albums.portada_ruta``), cuyo contenido se hashea.

        Si la BD aún no se inicializó (primera ejecución), no hay tabla y la
        consulta lanza excepción; en ese caso arrancamos con índices vacíos,
        equivalente al comportamiento anterior.
        """
        try:
            from db.conexion import obtener_filas
            filas = obtener_filas(
                "SELECT p.hash_sha256, p.ruta_archivo, p.mb_recording_id, p.isrc, "
                "       p.titulo, p.artista_nombre, p.album_titulo, p.duracion_seg, "
                "       a.portada_ruta "
                "FROM pistas p LEFT JOIN albums a ON a.id = p.album_id "
                "WHERE p.estado = 'biblioteca'"
            )
        except Exception as exc:
            _log.warning(
                "GestorDuplicados: precarga falló (%s). Iniciando con "
                "índices vacíos — reimportar puede crear duplicados.",
                exc,
            )
            return
        _log.info(
            "GestorDuplicados: precarga OK, %d filas leídas de la BD",
            len(filas),
        )
        # Cache de hashes de portada por ruta: varias pistas comparten album,
        # evitamos rehashear el mismo archivo de portada.
        cache_portada: dict[str, Optional[str]] = {}
        for fila in filas:
            ruta = Path(str(fila["ruta_archivo"] or ""))
            h = str(fila["hash_sha256"] or "")
            rid = str(fila["mb_recording_id"] or "")
            isrc = str(fila["isrc"] or "")
            if h and h not in self._por_hash:
                self._por_hash[h] = ruta
            for clave in (f"rid:{rid}" if rid else "", f"isrc:{isrc}" if isrc else ""):
                if clave and clave not in self._por_identidad:
                    self._por_identidad[clave] = ruta
                    # Calidad neutra. Si la corrida actual encuentra un
                    # candidato con calidad >> 0.5 podrá marcarse como
                    # "duplicado_mejorable"; en caso contrario, identidad
                    # semántica (descartar).
                    self._calidad_por_identidad[clave] = 0.5
            # Eje observable de la pista ya catalogada.
            portada_ruta = fila["portada_ruta"] if "portada_ruta" in fila.keys() else None
            if portada_ruta:
                clave_p = str(portada_ruta)
                if clave_p not in cache_portada:
                    cache_portada[clave_p] = hash_portada(clave_p)
                portada_h = cache_portada[clave_p]
            else:
                portada_h = None
            self._registrar_observable(
                ruta=ruta,
                titulo=fila["titulo"],
                artista=fila["artista_nombre"],
                album=fila["album_titulo"],
                duracion_seg=fila["duracion_seg"],
                portada_hash=portada_h,
            )

    def _registrar_observable(
        self,
        *,
        ruta: Path,
        titulo,
        artista,
        album,
        duracion_seg,
        portada_hash,
    ) -> None:
        """Indexa una pista en el eje observable si tiene señal suficiente."""
        clave = clave_observable(titulo, artista, album, portada_hash)
        if clave is None:
            return
        try:
            dur = float(duracion_seg)
        except (TypeError, ValueError):
            return
        self._por_observable.setdefault(clave, []).append((ruta, dur))

    def registrar_hash(self, archivo: ArchivoAudio) -> Optional[DuplicadoDetectado]:
        """
        Registra hash del archivo y detecta duplicado exacto.

        Returns:
            DuplicadoDetectado si ya existia ese hash, None en caso contrario.
        """
        if not archivo.hash_sha256:
            return None

        existente = self._por_hash.get(archivo.hash_sha256)
        if existente is not None:
            return DuplicadoDetectado(
                tipo="hash_exacto",
                referencia=str(existente),
            )

        self._por_hash[archivo.hash_sha256] = archivo.ruta_original
        return None

    def registrar_identidad_aceptada(
        self,
        decision: DecisionArchivo,
    ) -> Optional[DuplicadoDetectado]:
        """
        Registra la identidad musical de una decision aceptada y detecta
        duplicado semantico respecto a un track ya aceptado anteriormente.
        """
        candidato = decision.candidato_elegido
        if candidato is None:
            return None

        claves: list[str] = []
        if candidato.recording_id:
            claves.append(f"rid:{candidato.recording_id}")

        isrc = decision.archivo.isrc_disponible or candidato.isrc
        if isrc:
            claves.append(f"isrc:{isrc}")

        conflicto = self.detectar_duplicado_identidad(decision)
        if conflicto is not None:
            return conflicto

        ruta_ref = decision.ruta_destino or decision.archivo.ruta_original
        calidad = self._score_calidad(decision)
        for clave in claves:
            self._por_identidad[clave] = ruta_ref
            self._calidad_por_identidad[clave] = calidad

        return None

    def detectar_duplicado_identidad(self, decision: DecisionArchivo) -> Optional[DuplicadoDetectado]:
        candidato = decision.candidato_elegido
        if candidato is None:
            return None

        claves: list[str] = []
        if candidato.recording_id:
            claves.append(f"rid:{candidato.recording_id}")
        isrc = decision.archivo.isrc_disponible or candidato.isrc
        if isrc:
            claves.append(f"isrc:{isrc}")

        for clave in claves:
            existente = self._por_identidad.get(clave)
            if existente is not None:
                calidad_nueva = self._score_calidad(decision)
                calidad_existente = self._calidad_por_identidad.get(clave, 0.0)
                if (
                    DUPLICATE_POLICY in {"replace_if_better", "prefer_new_if_quality_higher"}
                    and (calidad_nueva - calidad_existente) >= DUPLICATE_BETTER_MIN_DELTA
                ):
                    tipo = "duplicado_mejorable"
                else:
                    tipo = "identidad_semantica"
                return DuplicadoDetectado(
                    tipo=tipo,
                    referencia=str(existente),
                )
        return None

    def detectar_duplicado_observable(
        self,
        *,
        titulo,
        artista,
        album,
        duracion_seg,
        portada_hash,
    ) -> Optional[DuplicadoDetectado]:
        """Eje 3: duplicado obvio por metadatos visibles + portada.

        Requiere coincidencia simultánea de título/artista/álbum normalizados y
        hash de portada, con la duración dentro de la tolerancia configurada.
        Recibe textos crudos (los normaliza con el algoritmo canónico) y el hash
        del *contenido* de la portada (ver :func:`hash_portada`). Solo consulta;
        la indexación se hace vía :meth:`registrar_observable_aceptado`.
        """
        clave = clave_observable(titulo, artista, album, portada_hash)
        if clave is None:
            return None
        candidatos = self._por_observable.get(clave)
        if not candidatos:
            return None
        for ruta_existente, dur_existente in candidatos:
            if duraciones_equivalentes(dur_existente, duracion_seg):
                return DuplicadoDetectado(
                    tipo="observable",
                    referencia=str(ruta_existente),
                )
        return None

    def registrar_observable_aceptado(
        self,
        *,
        ruta,
        titulo,
        artista,
        album,
        duracion_seg,
        portada_hash,
    ) -> None:
        """Indexa en el eje observable una pista aceptada en esta corrida.

        Pensado para usarse tras escribir una pista (cuando ya hay portada
        resuelta) de modo que pistas posteriores de la misma corrida se
        detecten contra ella sin esperar al barrido periódico.
        """
        self._registrar_observable(
            ruta=Path(str(ruta)),
            titulo=titulo,
            artista=artista,
            album=album,
            duracion_seg=duracion_seg,
            portada_hash=portada_hash,
        )

    @staticmethod
    def _score_calidad(decision: DecisionArchivo) -> float:
        archivo = decision.archivo
        cand = decision.candidato_elegido
        score = 0.0
        if decision.puntaje_maximo:
            score += min(0.5, decision.puntaje_maximo * 0.5)
        if cand:
            if cand.recording_id:
                score += 0.1
            if cand.release_id:
                score += 0.08
            if cand.isrc:
                score += 0.06
            if cand.track_number:
                score += 0.04
        if archivo.metadata_cruda:
            if archivo.metadata_cruda.bitrate_kbps and archivo.metadata_cruda.bitrate_kbps >= 256:
                score += 0.1
            if archivo.metadata_cruda.titulo and archivo.metadata_cruda.artista:
                score += 0.05
        if archivo.resultado_acoustid and archivo.resultado_acoustid.recording_ids:
            score += 0.07
        if archivo.isrc_disponible:
            score += 0.05
        return round(min(score, 1.0), 4)
