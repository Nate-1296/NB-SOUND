# =============================================================================
# core/matcher.py
#
# Motor de puntuacion multicriterio y decision final sobre candidatos MB.
#
# Novedades v3 — scoring ampliado y desempate inteligente:
#   - Criterio ISRC: si el ISRC del archivo coincide exactamente con el
#     ISRC del candidato, se aplica un bonus muy alto (BONUS_ISRC_EXACTO).
#     Esto eleva practicamente cualquier candidato por encima del umbral.
#   - Bonus por procedencia AcoustID: candidatos encontrados directamente
#     por recording_id de AcoustID reciben un bonus adicional de confianza.
#   - Bonus por confianza de identificacion: si la normalizacion reporta
#     alta confianza (Shazam + coincidencia), el puntaje base se eleva.
#   - Desempate con IA: si hay ambiguedad entre los dos mejores candidatos
#     y el modulo de IA esta disponible, se delega la decision al modelo.
#   - Trazabilidad ampliada: fuentes_usadas se propaga a la DecisionArchivo.
# =============================================================================

from typing import Optional

from config.settings import (
    SCORE_WEIGHTS,
    SCORE_THRESHOLD_ACCEPT,
    SCORE_THRESHOLD_REVIEW,
    DURATION_TOLERANCE_PERFECT,
    DURATION_TOLERANCE_PARTIAL,
    MAX_CANDIDATES_PER_FILE,
    PENALTY_COMPILATION,
    PENALTY_LIVE_REMIX,
    PENALTY_AMBIGUITY_GAP,
    MIN_SCORE_GAP,
    ACCEPTED_RELEASE_TYPES,
    PENALIZED_RELEASE_TYPES,
    BONUS_YEAR_MATCH,
    BONUS_ISRC_EXACTO,
    IA_TIEBREAK_MIN_GAP,
)
from domain.models import (
    ArchivoAudio,
    CandidatoMB,
    DecisionArchivo,
    DecisionTipo,
    CuarentenaCausa,
    RevisionCausa,
    FuenteIdentificacion,
    MetadataNormalizada,
)
from external.ia_client import ClienteIA
from infra.logger import obtener_logger
from utils.text import similitud_combinada, para_comparacion, limpiar_version_titulo, detectar_tipo_variante

_log = obtener_logger("matcher")


# =============================================================================
# FUNCION PRINCIPAL
# =============================================================================

def evaluar_candidatos(
    archivo: ArchivoAudio,
    candidatos: list[CandidatoMB],
    cliente_ia: Optional[ClienteIA] = None,
) -> DecisionArchivo:
    """
    Evalua todos los candidatos y retorna la DecisionArchivo resultante.

    Si el scoring determinista produce ambiguedad entre los dos mejores
    candidatos y el cliente de IA esta disponible, se delega el desempate.
    """
    if not candidatos:
        _log.debug(f"Sin candidatos para: {archivo.nombre_archivo}")
        return DecisionArchivo(
            tipo=DecisionTipo.CUARENTENA,
            archivo=archivo,
            causa_cuarentena=CuarentenaCausa.SIN_CANDIDATOS,
            mensaje_decision="No se encontraron candidatos en MusicBrainz",
        )

    norm = archivo.metadata_norm
    if norm is None:
        return DecisionArchivo(
            tipo=DecisionTipo.CUARENTENA,
            archivo=archivo,
            causa_cuarentena=CuarentenaCausa.METADATA_INSUFICIENTE,
            mensaje_decision="Sin metadata normalizada para evaluar",
        )

    # --- Puntuar cada candidato ---
    candidatos_puntuados: list[CandidatoMB] = []
    for candidato in candidatos[:MAX_CANDIDATES_PER_FILE]:
        puntaje, detalle, penalizaciones = _puntuar_candidato(
            candidato, norm, isrc_archivo=archivo.isrc_disponible
        )
        candidato.puntaje_total   = puntaje
        candidato.puntaje_detalle = detalle
        candidato.penalizaciones  = penalizaciones
        candidatos_puntuados.append(candidato)

    candidatos_puntuados.sort(key=lambda c: c.puntaje_total, reverse=True)

    # --- Validacion cruzada: Shazam + filename coinciden → elevar confianza ---
    # Si ambas fuentes independientes apuntan al mismo track, el mejor candidato
    # recibe un bonus que reduce la dependencia de MB cuando MB es debil.
    _aplicar_bonus_validacion_cruzada(archivo, norm, candidatos_puntuados)

    # Re-ordenar por si el bonus cambio el ranking
    candidatos_puntuados.sort(key=lambda c: c.puntaje_total, reverse=True)

    mejor  = candidatos_puntuados[0]
    segundo = candidatos_puntuados[1] if len(candidatos_puntuados) > 1 else None

    _log.debug(
        f"Top: '{mejor.artista_principal}' - '{mejor.titulo_oficial}' "
        f"[{mejor.tipo_release}] score={mejor.puntaje_total:.3f} | "
        f"{archivo.nombre_archivo}"
    )

    # --- Penalizacion por ambiguedad entre top-1 y top-2 ---
    gap = mejor.puntaje_total - (segundo.puntaje_total if segundo else 0)
    hay_ambiguedad = segundo is not None and gap < MIN_SCORE_GAP

    if hay_ambiguedad:
        score_antes = mejor.puntaje_total
        mejor.puntaje_total -= PENALTY_AMBIGUITY_GAP
        mejor.penalizaciones.append("ambiguedad_entre_candidatos")
        _log.debug(f"Penalizacion por ambiguedad | gap={gap:.3f}")

        # La penalización no puede hundir el score por debajo de REVISION si
        # el score base estaba por encima: eso saltaría la revisión manual,
        # que es exactamente el mecanismo de seguridad para casos ambiguos.
        if score_antes >= SCORE_THRESHOLD_REVIEW:
            mejor.puntaje_total = max(mejor.puntaje_total, SCORE_THRESHOLD_REVIEW)

    puntaje_final = max(0.0, mejor.puntaje_total)

    # --- Determinar fuentes usadas para trazabilidad ---
    fuentes = _determinar_fuentes_usadas(archivo, norm)

    # --- Desempate con IA si hay ambiguedad y el modulo esta activo ---
    decision_ia = None
    if (hay_ambiguedad
            and cliente_ia is not None
            and cliente_ia.activo
            and gap < IA_TIEBREAK_MIN_GAP):

        _log.debug(
            f"Activando desempate IA (gap={gap:.3f} < {IA_TIEBREAK_MIN_GAP}) | "
            f"{archivo.nombre_archivo}"
        )
        decision_ia = cliente_ia.desempatar(
            norm=norm,
            candidatos=candidatos_puntuados,
            resultado_shazam=archivo.resultado_shazam,
            resultado_acoustid=archivo.resultado_acoustid,
        )

        if decision_ia.valida and decision_ia.decision != "revision_manual":
            # Encontrar el candidato elegido por la IA
            candidato_ia = next(
                (c for c in candidatos_puntuados
                 if c.release_id == decision_ia.release_id),
                None,
            )
            if candidato_ia:
                mejor = candidato_ia
                # Usar la confianza de la IA como puntaje final
                puntaje_final = max(
                    SCORE_THRESHOLD_ACCEPT,
                    decision_ia.confianza,
                )
                fuentes.append(FuenteIdentificacion.IA)
                _log.debug(
                    f"IA eligio: '{candidato_ia.artista_principal}' - "
                    f"'{candidato_ia.titulo_oficial}' | "
                    f"confianza={decision_ia.confianza:.2f}"
                )

        elif decision_ia.valida and decision_ia.decision == "revision_manual":
            # La IA determino que ningun candidato es adecuado
            _log.debug("IA recomendo revision manual")
            return DecisionArchivo(
                tipo=DecisionTipo.REVISION,
                archivo=archivo,
                candidato_elegido=mejor,
                causa_revision=RevisionCausa.IA_REVISION_MANUAL,
                puntaje_maximo=puntaje_final,
                total_candidatos=len(candidatos_puntuados),
                decision_ia=decision_ia,
                fuentes_usadas=fuentes,
                mensaje_decision=(
                    f"IA recomendo revision manual: score={puntaje_final:.3f} | "
                    f"'{mejor.artista_principal}' - '{mejor.titulo_oficial}'"
                ),
            )

    return _aplicar_umbrales(
        archivo=archivo,
        mejor=mejor,
        puntaje_final=puntaje_final,
        total_candidatos=len(candidatos_puntuados),
        decision_ia=decision_ia,
        fuentes_usadas=fuentes,
    )


# =============================================================================
# VALIDACION CRUZADA DE FUENTES
# =============================================================================

def _aplicar_bonus_validacion_cruzada(
    archivo: ArchivoAudio,
    norm: MetadataNormalizada,
    candidatos_puntuados: list[CandidatoMB],
) -> None:
    """
    Si Shazam y el nombre de archivo coinciden en titulo/artista de forma
    independiente, el mejor candidato recibe un bonus de confianza.
    Esto reduce la dependencia de MB cuando MB tiene cobertura debil
    (ej: artistas regionales, remixes, pistas en alfabetos no latinos).

    El bonus es moderado (0.04) para no distorsionar decisiones correctas.
    Solo se aplica si al menos hay un candidato y el bonus realmente importa.
    """
    if not candidatos_puntuados:
        return

    shazam = archivo.resultado_shazam
    if not (shazam and shazam.identificado):
        return

    # Verificar que el nombre de archivo aporta algo coherente con Shazam
    from utils.text import normalizar_titulo, normalizar_artista

    shazam_titulo  = para_comparacion(normalizar_titulo(shazam.titulo or ""))
    shazam_artista = para_comparacion(normalizar_artista(shazam.artista or ""))

    # Solo activar si los tags locales o filename coinciden con Shazam
    coincide_titulo = (
        shazam_titulo
        and norm.titulo_para_match
        and similitud_combinada(norm.titulo_para_match, shazam_titulo) >= 0.75
    )
    coincide_artista = (
        shazam_artista
        and norm.artista_para_match
        and similitud_combinada(norm.artista_para_match, shazam_artista) >= 0.70
    )

    if coincide_titulo and coincide_artista:
        bonus = 0.06  # Ambas fuentes independientes coinciden: bonus mayor
    elif coincide_titulo or coincide_artista:
        bonus = 0.03  # Solo una dimension coincide: bonus moderado
    else:
        return  # Shazam y tags/filename divergen: no aplicar bonus

    mejor = candidatos_puntuados[0]
    mejor.puntaje_total = min(1.0, mejor.puntaje_total + bonus)
    mejor.penalizaciones.append(f"bonus_validacion_cruzada:{bonus:.2f}")
    _log.debug(
        f"Validacion cruzada (Shazam+local): bonus={bonus:.2f} → "
        f"score ajustado={mejor.puntaje_total:.3f}"
    )


# =============================================================================
# PUNTUACION POR CRITERIO
# =============================================================================

def _puntuar_candidato(
    candidato: CandidatoMB,
    norm: MetadataNormalizada,
    isrc_archivo: Optional[str] = None,
) -> tuple[float, dict[str, float], list[str]]:
    """
    Calcula el puntaje total de un candidato respecto a los metadatos locales.
    Retorna (puntaje_total, detalle_por_criterio, lista_de_penalizaciones).
    """
    detalle: dict[str, float] = {}
    penalizaciones: list[str] = []

    # --- ISRC (peso: 0.07, pero con bonus especial si coincide exactamente) ---
    score_isrc = 0.5  # Neutro si no hay informacion
    if isrc_archivo and candidato.isrc:
        if isrc_archivo == candidato.isrc:
            score_isrc = 1.0
        else:
            score_isrc = 0.1  # ISRCs distintos es una señal negativa
    elif isrc_archivo and not candidato.isrc:
        score_isrc = 0.4  # Candidato sin ISRC registrado, levemente penalizado
    detalle["isrc"] = score_isrc

    # --- Titulo (peso: 0.28) ---
    # v3.3: detectar variante en titulo local para scoring inteligente
    titulo_local_base = limpiar_version_titulo(norm.titulo_para_match)
    variante_local    = detectar_tipo_variante(norm.titulo or "")

    titulo_candidato_base = para_comparacion(
        limpiar_version_titulo(candidato.titulo_oficial)
    )
    score_titulo = similitud_combinada(titulo_local_base, titulo_candidato_base)

    if score_titulo < 0.7:
        score_titulo_full = similitud_combinada(
            norm.titulo_para_match,
            para_comparacion(candidato.titulo_oficial),
        )
        score_titulo = max(score_titulo, score_titulo_full * 0.95)

    detalle["titulo"] = round(score_titulo, 4)

    # --- Artista (peso: 0.23) ---
    score_artista = similitud_combinada(
        norm.artista_para_match,
        para_comparacion(candidato.artista_principal),
    )

    # Bonus si el artista local aparece en los creditos del candidato
    if score_artista < 0.9 and norm.artista_para_match:
        for artista_credito in candidato.artistas_credito:
            bonus = similitud_combinada(
                norm.artista_para_match,
                para_comparacion(artista_credito),
            )
            if bonus > score_artista:
                # Penalizar levemente: no es el artista principal
                score_artista = min(bonus, 0.82)

    detalle["artista"] = round(score_artista, 4)

    # --- Duracion (peso: 0.18) ---
    score_duracion = _puntuar_duracion(norm.duracion_seg, candidato.duracion_seg)
    detalle["duracion"] = score_duracion

    # --- Album (peso: 0.10) ---
    if norm.album_para_match and candidato.album_oficial:
        album_local = limpiar_version_titulo(norm.album_para_match)
        album_cand  = para_comparacion(limpiar_version_titulo(candidato.album_oficial))
        score_album = similitud_combinada(album_local, album_cand)
    elif not norm.album_para_match:
        score_album = 0.5  # Sin info local, puntaje neutro
    else:
        score_album = 0.2  # Candidato sin album
    detalle["album"] = round(score_album, 4)

    # --- Track number (peso: 0.07) ---
    score_track = _puntuar_track_number(norm.track_number, candidato.track_number)
    detalle["track_number"] = score_track

    # --- Tipo de release (peso: 0.07) ---
    # v3.3: si el titulo local ya indica una variante (ej. "Remix"), y el
    # candidato es de ese mismo tipo secundario, no se penaliza — es un
    # match valido de variante, no un mismatch.
    score_tipo, penalizacion_tipo = _puntuar_tipo_release(
        candidato, variante_local=variante_local
    )
    detalle["tipo_release"] = score_tipo
    if penalizacion_tipo:
        penalizaciones.append(penalizacion_tipo)

    # --- Penalizacion por release no oficial ---
    if not candidato.es_oficial and candidato.status_release:
        penalizaciones.append(f"release_no_oficial:{candidato.status_release}")
        factor = 0.90 if candidato.status_release == "Promotion" else 0.80
        for k in detalle:
            detalle[k] *= factor

    # --- Penalizacion por compilacion ---
    if candidato.es_compilacion:
        penalizaciones.append("compilacion")

    # --- Puntaje base ponderado ---
    puntaje_base = sum(
        detalle.get(criterio, 0.0) * peso
        for criterio, peso in SCORE_WEIGHTS.items()
    )

    # --- Aplicar penalizaciones ---
    puntaje_final = puntaje_base
    if "compilacion" in penalizaciones:
        puntaje_final -= PENALTY_COMPILATION

    # v3.3: penalizacion inteligente por tipo secundario Live/Remix/etc.
    # Si el titulo local ya indica la misma variante que el tipo secundario
    # del candidato, aplicamos una penalizacion reducida (mismatch tolerable)
    # en lugar de la penalizacion completa (PENALTY_LIVE_REMIX).
    tiene_tipo_secundario_penalizado = any(
        p.startswith("tipo_secundario:") for p in penalizaciones
    )
    if tiene_tipo_secundario_penalizado:
        # Extraer el tipo secundario detectado en el candidato
        tipos_sec_candidato = {
            p.split(":", 1)[1] for p in penalizaciones
            if p.startswith("tipo_secundario:")
        }
        # Si el titulo local indica la misma variante → mismatch tolerable
        variante_coincide = (
            variante_local is not None
            and variante_local in tipos_sec_candidato
        )
        if variante_coincide:
            # Penalizacion reducida: el archivo ES esa variante, match valido
            puntaje_final -= PENALTY_LIVE_REMIX * 0.30
            penalizaciones.append(f"variante_coincide:{variante_local}")
        else:
            puntaje_final -= PENALTY_LIVE_REMIX

    # --- Bonus por coincidencia de año ---
    if norm.anio and candidato.anio_release:
        if norm.anio == candidato.anio_release:
            puntaje_final += BONUS_YEAR_MATCH
            penalizaciones.append(f"bonus_anio:{norm.anio}")
        elif abs(norm.anio - candidato.anio_release) <= 1:
            puntaje_final += BONUS_YEAR_MATCH * 0.5

    # --- Bonus ISRC exacto (override masivo de confianza) ---
    if isrc_archivo and candidato.isrc and isrc_archivo == candidato.isrc:
        puntaje_final += BONUS_ISRC_EXACTO
        penalizaciones.append(f"bonus_isrc_exacto:{isrc_archivo}")

    # --- Bonus por procedencia AcoustID ---
    if candidato.procedencia_acoustid:
        puntaje_final += 0.08
        penalizaciones.append("bonus_acoustid")

    # --- Bonus por confianza de identificacion del archivo ---
    if norm.confianza_identificacion > 0.7:
        puntaje_final += 0.03
    elif norm.confianza_identificacion > 0.5:
        puntaje_final += 0.01

    puntaje_final = max(0.0, min(1.0, puntaje_final))

    return puntaje_final, detalle, penalizaciones


def _puntuar_duracion(
    duracion_local: Optional[float],
    duracion_candidato: Optional[float],
) -> float:
    """
    Compara duraciones y retorna puntaje entre 0 y 1.
    Tolerancia perfecta: +-3s  = 1.0
    Tolerancia parcial:  +-10s = gradiente 0.5-1.0
    Gradiente hasta 0.0 a los 30s de diferencia.
    Sin datos: puntaje neutro 0.5
    """
    if duracion_local is None or duracion_candidato is None:
        return 0.5

    diferencia = abs(duracion_local - duracion_candidato)

    if diferencia <= DURATION_TOLERANCE_PERFECT:
        return 1.0
    elif diferencia <= DURATION_TOLERANCE_PARTIAL:
        rango    = DURATION_TOLERANCE_PARTIAL - DURATION_TOLERANCE_PERFECT
        progreso = (diferencia - DURATION_TOLERANCE_PERFECT) / rango
        return round(1.0 - (0.5 * progreso), 4)
    elif diferencia <= 30:
        progreso = (diferencia - DURATION_TOLERANCE_PARTIAL) / 20
        return round(max(0.05, 0.5 - (0.45 * progreso)), 4)
    else:
        return 0.0


def _puntuar_track_number(
    track_local: Optional[int],
    track_candidato: Optional[int],
) -> float:
    if track_local is None or track_candidato is None:
        return 0.5  # Neutro
    if track_local == track_candidato:
        return 1.0
    if abs(track_local - track_candidato) == 1:
        return 0.4
    return 0.0


def _puntuar_tipo_release(
    candidato: CandidatoMB,
    variante_local: Optional[str] = None,
) -> tuple[float, Optional[str]]:
    """
    v3.3: Si el titulo local ya indica una variante (ej. "Remix") y el tipo
    de release del candidato coincide, se asigna puntaje neutro en lugar de
    penalizado — es un match valido, no un mismatch.
    """
    tipo = candidato.tipo_release

    # Verificar si la variante local coincide con tipos secundarios del candidato
    tipos_sec = set(candidato.tipos_secundarios)
    variante_coincide_sec = (
        variante_local is not None and variante_local in tipos_sec
    )
    variante_coincide_primary = (
        variante_local is not None and variante_local == tipo
    )

    if tipo in ACCEPTED_RELEASE_TYPES:
        return (1.0, None)
    elif tipo in PENALIZED_RELEASE_TYPES:
        if variante_coincide_primary or variante_coincide_sec:
            # Match de variante: el archivo ES de este tipo → puntaje neutro
            return (0.65, f"tipo_penalizado_tolerado:{tipo}")
        return (0.2, f"tipo_penalizado:{tipo}")
    elif not tipo:
        return (0.4, None)
    else:
        return (0.5, None)


# =============================================================================
# APLICACION DE UMBRALES
# =============================================================================

def _aplicar_umbrales(
    archivo: ArchivoAudio,
    mejor: CandidatoMB,
    puntaje_final: float,
    total_candidatos: int,
    decision_ia=None,
    fuentes_usadas=None,
) -> DecisionArchivo:
    fuentes = fuentes_usadas or []

    # --- v3.3: si el archivo es una variante reconocida y el candidato
    #     coincide en variante, tratar el mismatch de release como tolerable
    #     y NO degradar a cuarentena por eso.
    variante_local_archivo = detectar_tipo_variante(
        archivo.metadata_norm.titulo if archivo.metadata_norm else ""
    )
    variante_coincide_candidato = (
        variante_local_archivo is not None
        and (
            variante_local_archivo == mejor.tipo_release
            or variante_local_archivo in mejor.tipos_secundarios
        )
    )

    # --- Detectar si la identidad del track es solida independientemente
    #     del release. Criterio: titulo + artista fuertes + al menos Shazam
    #     o ISRC disponible.
    identidad_solida = _identidad_es_solida(archivo, mejor)

    # --- Detectar si la duracion fue el unico factor que bajo el score ---
    duracion_es_problema = mejor.puntaje_detalle.get("duracion", 1.0) < 0.35
    resto_es_fuerte = (
        mejor.puntaje_detalle.get("titulo", 0.0) >= 0.75
        and mejor.puntaje_detalle.get("artista", 0.0) >= 0.70
    )

    if puntaje_final >= SCORE_THRESHOLD_ACCEPT:
        # v3.2: Solo degradar a PROVISIONAL si falta TANTO el tipo de release
        # como una estructura bibliografica confiable (album/release title).
        # Si hay album consistente aunque falte el tipo formal → ACEPTADO limpio.
        release_type_ausente = not mejor.tipo_release
        album_ausente = not mejor.album_oficial

        debe_ser_provisional = (
            identidad_solida
            and release_type_ausente
            and album_ausente
        )

        if debe_ser_provisional:
            return DecisionArchivo(
                tipo=DecisionTipo.ACEPTADO_PROVISIONAL,
                archivo=archivo,
                candidato_elegido=mejor,
                causa_revision=RevisionCausa.CLASIFICACION_PROVISIONAL,
                puntaje_maximo=puntaje_final,
                total_candidatos=total_candidatos,
                decision_ia=decision_ia,
                fuentes_usadas=fuentes,
                mensaje_decision=(
                    f"Aceptado provisional score={puntaje_final:.3f} | "
                    f"'{mejor.artista_principal}' - '{mejor.titulo_oficial}' "
                    f"[sin tipo ni album]"
                ),
            )

        return DecisionArchivo(
            tipo=DecisionTipo.ACEPTADO,
            archivo=archivo,
            candidato_elegido=mejor,
            puntaje_maximo=puntaje_final,
            total_candidatos=total_candidatos,
            decision_ia=decision_ia,
            fuentes_usadas=fuentes,
            mensaje_decision=(
                f"Aceptado score={puntaje_final:.3f} | "
                f"'{mejor.artista_principal}' - '{mejor.titulo_oficial}' "
                f"[{mejor.tipo_release}]"
            ),
        )

    elif puntaje_final >= SCORE_THRESHOLD_REVIEW:
        # Conversion REVISION → PROVISIONAL solo si la identidad es genuinamente
        # fuerte.
        _UMBRAL_PROVISIONAL = SCORE_THRESHOLD_ACCEPT - 0.10
        puede_ser_provisional = (
            duracion_es_problema
            and resto_es_fuerte
            and identidad_solida
            and puntaje_final >= _UMBRAL_PROVISIONAL
            and "ambiguedad_entre_candidatos" not in mejor.penalizaciones
        )

        # v3.3: variante coincidente en zona de revision → promover a provisional
        # si la identidad base es solida (mismo track, distinta version editorial)
        puede_ser_provisional_variante = (
            not puede_ser_provisional
            and variante_coincide_candidato
            and identidad_solida
            and puntaje_final >= _UMBRAL_PROVISIONAL
            and mejor.puntaje_detalle.get("titulo", 0.0) >= 0.70
            and mejor.puntaje_detalle.get("artista", 0.0) >= 0.65
            and "ambiguedad_entre_candidatos" not in mejor.penalizaciones
        )

        if puede_ser_provisional or puede_ser_provisional_variante:
            causa_prov = (
                RevisionCausa.DURACION_MARGINAL
                if puede_ser_provisional
                else RevisionCausa.CLASIFICACION_PROVISIONAL
            )
            razon_prov = (
                "duracion marginal, identidad solida"
                if puede_ser_provisional
                else f"variante reconocida ({variante_local_archivo}), identidad solida"
            )
            return DecisionArchivo(
                tipo=DecisionTipo.ACEPTADO_PROVISIONAL,
                archivo=archivo,
                candidato_elegido=mejor,
                causa_revision=causa_prov,
                puntaje_maximo=puntaje_final,
                total_candidatos=total_candidatos,
                decision_ia=decision_ia,
                fuentes_usadas=fuentes,
                mensaje_decision=(
                    f"Aceptado provisional ({razon_prov}) "
                    f"score={puntaje_final:.3f} | "
                    f"'{mejor.artista_principal}' - '{mejor.titulo_oficial}'"
                ),
            )

        causa = _diagnosticar_causa_revision(mejor, puntaje_final, variante_local_archivo)
        return DecisionArchivo(
            tipo=DecisionTipo.REVISION,
            archivo=archivo,
            candidato_elegido=mejor,
            causa_revision=causa,
            puntaje_maximo=puntaje_final,
            total_candidatos=total_candidatos,
            decision_ia=decision_ia,
            fuentes_usadas=fuentes,
            mensaje_decision=(
                f"Revision: score={puntaje_final:.3f} | "
                f"'{mejor.artista_principal}' - '{mejor.titulo_oficial}' | "
                f"causa={causa.value}"
            ),
        )

    else:
        # v3.3: si el archivo indica claramente una variante que coincide con
        # el candidato, pero el score es bajo, promover a REVISION en lugar de
        # cuarentena — hay suficiente evidencia para revision humana.
        if (variante_coincide_candidato
                and identidad_solida
                and puntaje_final >= SCORE_THRESHOLD_REVIEW * 0.80
                and mejor.puntaje_detalle.get("titulo", 0.0) >= 0.65):
            causa_rev = _diagnosticar_causa_revision(mejor, puntaje_final, variante_local_archivo)
            return DecisionArchivo(
                tipo=DecisionTipo.REVISION,
                archivo=archivo,
                candidato_elegido=mejor,
                causa_revision=causa_rev,
                puntaje_maximo=puntaje_final,
                total_candidatos=total_candidatos,
                decision_ia=decision_ia,
                fuentes_usadas=fuentes,
                mensaje_decision=(
                    f"Revision (variante {variante_local_archivo} con match parcial): "
                    f"score={puntaje_final:.3f} | "
                    f"'{mejor.artista_principal}' - '{mejor.titulo_oficial}'"
                ),
            )

        causa = _diagnosticar_causa_cuarentena(mejor, puntaje_final)
        return DecisionArchivo(
            tipo=DecisionTipo.CUARENTENA,
            archivo=archivo,
            candidato_elegido=mejor,
            causa_cuarentena=causa,
            puntaje_maximo=puntaje_final,
            total_candidatos=total_candidatos,
            decision_ia=decision_ia,
            fuentes_usadas=fuentes,
            mensaje_decision=(
                f"Cuarentena: score={puntaje_final:.3f} | "
                f"mejor: '{mejor.artista_principal}' - '{mejor.titulo_oficial}'"
            ),
        )


def _identidad_es_solida(archivo: ArchivoAudio, candidato: CandidatoMB) -> bool:
    """
    Determina si la identidad del track (titulo + artista) es suficientemente
    solida con independencia de la clasificacion de release.

    v3.2: También acepta coincidencias muy fuertes solo por MB (sin Shazam/ISRC)
    cuando el score de título y artista son muy altos, para no inflar provisionales
    por ausencia de módulos opcionales.
    """
    titulo_score  = candidato.puntaje_detalle.get("titulo", 0.0)
    artista_score = candidato.puntaje_detalle.get("artista", 0.0)
    if titulo_score < 0.75 or artista_score < 0.65:
        return False

    tiene_shazam = (
        archivo.resultado_shazam is not None
        and archivo.resultado_shazam.identificado
    )
    tiene_isrc = bool(
        archivo.isrc_disponible
        or (archivo.resultado_shazam and archivo.resultado_shazam.isrc)
    )

    # FIX v3.2: si título y artista son muy fuertes solo desde MB, también
    # es identidad sólida (evita inflación de provisionales cuando Shazam/AcoustID
    # no están configurados).
    identidad_mb_muy_fuerte = (titulo_score >= 0.90 and artista_score >= 0.85)

    return tiene_shazam or tiene_isrc or identidad_mb_muy_fuerte


def _diagnosticar_causa_revision(
    mejor: CandidatoMB, puntaje: float, variante_local: Optional[str] = None
) -> RevisionCausa:
    if "ambiguedad_entre_candidatos" in mejor.penalizaciones:
        return RevisionCausa.CANDIDATOS_AMBIGUOS
    # v3.3: si el tipo de release no coincide pero hay variante local reconocida
    # el tipo dudoso no es la causa raiz — usar puntaje intermedio
    if mejor.tipo_release not in ACCEPTED_RELEASE_TYPES and variante_local is None:
        return RevisionCausa.RELEASE_TYPE_DUDOSO
    if mejor.puntaje_detalle.get("duracion", 1.0) < 0.3:
        return RevisionCausa.DURACION_MARGINAL
    return RevisionCausa.PUNTAJE_INTERMEDIO


def _diagnosticar_causa_cuarentena(
    mejor: CandidatoMB, puntaje: float
) -> CuarentenaCausa:
    if not mejor.es_oficial:
        return CuarentenaCausa.OWNERSHIP_INVALIDO
    if mejor.puntaje_detalle.get("titulo", 0.0) < 0.3:
        return CuarentenaCausa.METADATA_INSUFICIENTE
    return CuarentenaCausa.PUNTAJE_BAJO


# =============================================================================
# TRAZABILIDAD DE FUENTES
# =============================================================================

def _determinar_fuentes_usadas(
    archivo: ArchivoAudio,
    norm: MetadataNormalizada,
) -> list[FuenteIdentificacion]:
    """Construye la lista de fuentes que contribuyeron a la identificacion."""
    fuentes: list[FuenteIdentificacion] = []

    if norm.fuente_titulo == FuenteIdentificacion.TAG_LOCAL or \
       norm.fuente_artista == FuenteIdentificacion.TAG_LOCAL:
        fuentes.append(FuenteIdentificacion.TAG_LOCAL)

    if (archivo.resultado_shazam
            and archivo.resultado_shazam.identificado):
        fuentes.append(FuenteIdentificacion.SHAZAM)

    if (archivo.resultado_acoustid
            and archivo.resultado_acoustid.recording_ids):
        fuentes.append(FuenteIdentificacion.ACOUSTID)

    fuentes.append(FuenteIdentificacion.MUSICBRAINZ)

    return fuentes