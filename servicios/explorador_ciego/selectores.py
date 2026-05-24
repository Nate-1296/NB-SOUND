# =============================================================================
# servicios/explorador_ciego/selectores.py
#
# Selectores de pistas por modo. Cada selector aisla la consulta SQL/Python
# que define el "pool" candidato para un modo de juego.
#
# Contrato:
#   - Cada selector devuelve una lista de dicts con metadatos completos de
#     pista (mismo shape que devuelve `servicios.biblioteca.obtener_pista`).
#   - El servicio aplica luego la aleatorizacion, el cap de N y la
#     deduplicacion por sesion.
#
# Decisiones:
#   - NO usamos los selectores existentes de playlists automaticas
#     directamente para evitar acoplar el juego a esa logica (que puede
#     cambiar sus heuristicas sin previo aviso). Replicamos consultas
#     similares aqui, mas pequenas y mas explicitas.
#   - Filtramos siempre por `estado='biblioteca'` y `ruta_archivo` presente,
#     porque el modo audio necesita reproducir y el modo portada necesita
#     resolver una portada renderizable.
# =============================================================================

from __future__ import annotations

from typing import Iterable

from db.conexion import obtener_filas
from servicios import biblioteca as svc_bib
from .modelos import ModoExplorador


# Tope generoso para evitar leer toda la biblioteca cuando es enorme. Se
# aleatoriza el subconjunto en el servicio antes de cortar a N retos.
_TOPE_CANDIDATOS = 400


def _filas_a_pistas(filas: Iterable[dict]) -> list[dict]:
    """Convierte filas crudas en pistas enriquecidas con portadas resueltas.

    Reutilizamos `_normalizar_pista_fila` de biblioteca para obtener el mismo
    contrato visible que el resto de la app (portadas display, etc.).
    """
    salida: list[dict] = []
    for fila in filas:
        try:
            datos = dict(fila)
        except Exception:
            continue
        try:
            normalizada = svc_bib._normalizar_pista_fila(datos)  # noqa: SLF001
        except Exception:
            normalizada = datos
        salida.append(normalizada)
    return salida


def candidatos_portada() -> list[dict]:
    """Pistas con portada resoluble (album con portada o release MB).

    La portada debe poder mostrarse con suficiente calidad para que adivinar
    no se vuelva imposible por mala fuente. Por eso priorizamos portadas en
    disco (portada_ruta no vacio).
    """
    filas = obtener_filas(
        """
        SELECT
            p.*,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id
        FROM pistas p
        LEFT JOIN albums al ON al.id = p.album_id
        WHERE p.estado = 'biblioteca'
          AND p.ruta_archivo IS NOT NULL
          AND p.ruta_archivo <> ''
          AND (
              (al.portada_ruta IS NOT NULL AND al.portada_ruta <> '')
              OR (p.album_id IS NOT NULL AND al.mb_release_id IS NOT NULL AND al.mb_release_id <> '')
          )
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (_TOPE_CANDIDATOS,),
    )
    pistas = _filas_a_pistas(filas)
    # Filtrar por que la resolucion final si produjo una portada display.
    # Esto descarta filas donde el lookup posterior falla y evita mostrar
    # placeholders genericos en la UI del juego.
    return [
        p for p in pistas
        if str(p.get("portada_display_ruta") or p.get("portada_ruta") or "").strip()
    ]


def candidatos_audio() -> list[dict]:
    """Pistas con audio reproducible. Universo grande, aleatorizado."""
    filas = obtener_filas(
        """
        SELECT
            p.*,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id
        FROM pistas p
        LEFT JOIN albums al ON al.id = p.album_id
        WHERE p.estado = 'biblioteca'
          AND p.ruta_archivo IS NOT NULL
          AND p.ruta_archivo <> ''
          AND COALESCE(p.duracion_seg, 0) > 30
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (_TOPE_CANDIDATOS,),
    )
    return _filas_a_pistas(filas)


def candidatos_redescubrimiento() -> list[dict]:
    """Pistas escuchadas hace mucho tiempo o favoritas olvidadas.

    Heuristica:
      - Tiene al menos 1 reproduccion historica o esta marcada favorita.
      - El ultimo acceso (o fecha de actualizacion como fallback) es viejo:
        ordenamos ascendente para empujar las mas viejas primero.

    A diferencia del selector de playlists automaticas, NO cortamos por
    fecha exacta: el juego prefiere variedad sobre rigor temporal.
    """
    filas = obtener_filas(
        """
        SELECT
            p.*,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id,
            COALESCE(h.reproducciones, p.veces_reproducida, 0) AS reproducciones_total,
            h.ultima_reproduccion AS ultima_reproduccion_h
        FROM pistas p
        LEFT JOIN albums al ON al.id = p.album_id
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones, MAX(reproducido_en) AS ultima_reproduccion
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca'
          AND p.ruta_archivo IS NOT NULL
          AND p.ruta_archivo <> ''
          AND (
              COALESCE(p.favorita, 0) = 1
              OR COALESCE(h.reproducciones, p.veces_reproducida, 0) > 0
          )
        ORDER BY
            datetime(COALESCE(h.ultima_reproduccion, p.ultimo_acceso, p.indexado_en, p.actualizado_en)) ASC,
            reproducciones_total DESC
        LIMIT ?
        """,
        (_TOPE_CANDIDATOS,),
    )
    return _filas_a_pistas(filas)


def candidatos_nunca_eliges() -> list[dict]:
    """Pistas con 0 (o casi 0) reproducciones. La biblioteca infrautilizada.

    Universo: nunca reproducidas en `historial` y `veces_reproducida=0`.
    Si la biblioteca tiene muy poco "cola larga", relajamos el criterio en
    `_candidatos_nunca_eliges_relajado` para no quedarnos sin pool.
    """
    filas = obtener_filas(
        """
        SELECT
            p.*,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id
        FROM pistas p
        LEFT JOIN albums al ON al.id = p.album_id
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca'
          AND p.ruta_archivo IS NOT NULL
          AND p.ruta_archivo <> ''
          AND COALESCE(h.reproducciones, 0) = 0
          AND COALESCE(p.veces_reproducida, 0) = 0
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (_TOPE_CANDIDATOS,),
    )
    pistas = _filas_a_pistas(filas)
    if pistas:
        return pistas
    return _candidatos_nunca_eliges_relajado()


def _candidatos_nunca_eliges_relajado() -> list[dict]:
    """Fallback para bibliotecas pequenas: pistas con <= 2 reproducciones."""
    filas = obtener_filas(
        """
        SELECT
            p.*,
            al.portada_ruta AS album_portada_ruta,
            al.mb_release_id AS album_mb_release_id,
            COALESCE(h.reproducciones, p.veces_reproducida, 0) AS reproducciones_total
        FROM pistas p
        LEFT JOIN albums al ON al.id = p.album_id
        LEFT JOIN (
            SELECT pista_id, COUNT(*) AS reproducciones
            FROM historial
            GROUP BY pista_id
        ) h ON h.pista_id = p.id
        WHERE p.estado = 'biblioteca'
          AND p.ruta_archivo IS NOT NULL
          AND p.ruta_archivo <> ''
          AND COALESCE(h.reproducciones, p.veces_reproducida, 0) <= 2
        ORDER BY reproducciones_total ASC, RANDOM()
        LIMIT ?
        """,
        (_TOPE_CANDIDATOS,),
    )
    return _filas_a_pistas(filas)


# Mapa publico: el servicio importa esto para resolver "modo -> selector".
SELECTORES: dict[ModoExplorador, callable] = {
    ModoExplorador.PORTADA: candidatos_portada,
    ModoExplorador.AUDIO: candidatos_audio,
    ModoExplorador.REDESCUBRIMIENTO: candidatos_redescubrimiento,
    ModoExplorador.NUNCA_ELIGES: candidatos_nunca_eliges,
}


def candidatos_para(modo: ModoExplorador) -> list[dict]:
    """Punto unico de entrada para obtener candidatos por modo."""
    selector = SELECTORES.get(modo)
    if selector is None:
        return []
    try:
        return selector()
    except Exception:
        # No queremos que un error de SQL deje a la vista en estado roto;
        # devolver lista vacia hace que el modelo emita "sin candidatos" y
        # la UI muestre el EmptyState correspondiente.
        return []


def contar_disponibles(modo: ModoExplorador) -> int:
    """Cuenta candidatos disponibles sin cargar payloads completos.

    Mas barata que `candidatos_para`: util para los selectores de modo en
    la UI (mostrar "23 pistas listas" en cada tarjeta de modo).
    """
    if modo == ModoExplorador.PORTADA:
        sql = """
            SELECT COUNT(*) AS n
            FROM pistas p
            LEFT JOIN albums al ON al.id = p.album_id
            WHERE p.estado = 'biblioteca'
              AND p.ruta_archivo IS NOT NULL AND p.ruta_archivo <> ''
              AND (
                  (al.portada_ruta IS NOT NULL AND al.portada_ruta <> '')
                  OR (p.album_id IS NOT NULL AND al.mb_release_id IS NOT NULL AND al.mb_release_id <> '')
              )
        """
        filas = obtener_filas(sql)
    elif modo == ModoExplorador.AUDIO:
        sql = """
            SELECT COUNT(*) AS n
            FROM pistas p
            WHERE p.estado = 'biblioteca'
              AND p.ruta_archivo IS NOT NULL AND p.ruta_archivo <> ''
              AND COALESCE(p.duracion_seg, 0) > 30
        """
        filas = obtener_filas(sql)
    elif modo == ModoExplorador.REDESCUBRIMIENTO:
        sql = """
            SELECT COUNT(*) AS n
            FROM pistas p
            LEFT JOIN (
                SELECT pista_id, COUNT(*) AS reproducciones
                FROM historial
                GROUP BY pista_id
            ) h ON h.pista_id = p.id
            WHERE p.estado = 'biblioteca'
              AND p.ruta_archivo IS NOT NULL AND p.ruta_archivo <> ''
              AND (
                  COALESCE(p.favorita, 0) = 1
                  OR COALESCE(h.reproducciones, p.veces_reproducida, 0) > 0
              )
        """
        filas = obtener_filas(sql)
    elif modo == ModoExplorador.NUNCA_ELIGES:
        sql = """
            SELECT COUNT(*) AS n
            FROM pistas p
            LEFT JOIN (
                SELECT pista_id, COUNT(*) AS reproducciones
                FROM historial
                GROUP BY pista_id
            ) h ON h.pista_id = p.id
            WHERE p.estado = 'biblioteca'
              AND p.ruta_archivo IS NOT NULL AND p.ruta_archivo <> ''
              AND COALESCE(h.reproducciones, 0) = 0
              AND COALESCE(p.veces_reproducida, 0) = 0
        """
        filas = obtener_filas(sql)
    else:
        return 0
    if not filas:
        return 0
    try:
        return int(filas[0]["n"])
    except (KeyError, TypeError, ValueError):
        return 0
