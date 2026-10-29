# =============================================================================
# servicios/dj_privado/stems_karaoke.py
#
# Adaptador que conecta el MixEngine con el subsistema karaoke como fuente
# de stems "sin voz" para la técnica HARMONIC_MIX.
#
# Lógica:
#   - Cuando el karaoke ya procesó una pista, su `karaoke_ruta_instrumental`
#     apunta a un MP3 de la mezcla sin voz. Eso es lo que necesita
#     HARMONIC_MIX para superponer dos pistas sin choque vocal.
#   - Si la pista todavía NO tiene karaoke, este provider devuelve None y el
#     mix engine degradará a otra técnica sin avisar al usuario.
#   - Encolar la generación del instrumental (pre-fetch agresivo) es
#     responsabilidad del servicio DJ; este módulo solo lee el estado
#     actual.
# =============================================================================

from __future__ import annotations

from pathlib import Path
from typing import Optional

from infra.logger import obtener_logger

logger = obtener_logger(__name__)


class StemsKaraokeProvider:
    """Implementación de `mix_engine.StemsProvider` apoyada en karaoke.

    Es trivial por diseño: el contrato del provider solo expone una función
    que devuelve la ruta del stem si existe, o None en caso contrario.
    Mantenerlo simple permite probarlo sin depender del estado real de BD.
    """

    def ruta_no_vocals(self, pista_id: int, ruta_audio: str) -> Optional[Path]:
        """Consulta `pistas.karaoke_ruta_instrumental` y valida en disco.

        Devuelve None si:
            - La BD no está inicializada (caso típico en tests aislados).
            - La pista no tiene karaoke procesado.
            - La ruta registrada apunta a un archivo inexistente.
        """
        try:
            from db.conexion import obtener_una_fila
        except Exception:
            return None
        if int(pista_id) <= 0:
            return None
        try:
            fila = obtener_una_fila(
                """
                SELECT karaoke_estado, karaoke_ruta_instrumental
                FROM pistas
                WHERE id = ?
                """,
                (int(pista_id),),
            )
        except Exception as exc:
            logger.info("stems karaoke: consulta BD falló para pista %d: %s", pista_id, exc)
            return None
        if not fila:
            return None
        estado = str(fila["karaoke_estado"] or "")
        ruta = str(fila["karaoke_ruta_instrumental"] or "")
        if estado != "lista" or not ruta:
            return None
        ruta_path = Path(ruta).expanduser()
        if not ruta_path.exists():
            logger.info(
                "stems karaoke: pista %d marcada lista pero archivo no existe: %s",
                pista_id, ruta_path,
            )
            return None
        return ruta_path
