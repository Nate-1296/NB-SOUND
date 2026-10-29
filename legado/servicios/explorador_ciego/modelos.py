# =============================================================================
# servicios/explorador_ciego/modelos.py
#
# Dataclasses y enumeraciones del Explorador Ciego.
#
# Diseno:
#   - Los modos son la unidad principal de configuracion del juego: definen
#     que pool de pistas se usa y como se presenta el reto.
#   - Un Reto encapsula una pista enmascarada y su estado de revelacion.
#   - Una Ronda es una secuencia de retos del mismo modo; el servicio la
#     mantiene en memoria mientras este abierta.
#
# El estado vive 100% en memoria del proceso. NO persistimos historial del
# juego en BD: el redescubrimiento es desechable; lo unico que importa son
# los efectos secundarios (reproducir, encolar, marcar favorita, etc.), que
# ya se persisten por las vias normales del reproductor.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ModoExplorador(str, Enum):
    """Modos congelados para version 1.

    - PORTADA: se muestra la portada (sin texto) y el usuario adivina.
    - AUDIO: se reproduce un fragmento y el usuario adivina sin ver datos.
    - REDESCUBRIMIENTO: pistas que el usuario amo en algun momento y dejo de
      tocar; el juego es opcionalmente adivinar antes de reconocerlas.
    - NUNCA_ELIGES: pistas con 0 (o casi 0) reproducciones; ayuda a expandir
      el uso real de la biblioteca.

    Los modos REDESCUBRIMIENTO y NUNCA_ELIGES funcionan como "modos suaves":
    la revelacion es inmediata si el usuario lo prefiere, pero igual disparan
    el mismo loop de interaccion (reproducir/encolar/saltar).
    """

    PORTADA = "portada"
    AUDIO = "audio"
    REDESCUBRIMIENTO = "redescubrimiento"
    NUNCA_ELIGES = "nunca_eliges"


class NivelRevelacion(str, Enum):
    """Granularidad progresiva de pistas que se han revelado al usuario."""

    OCULTO = "oculto"
    ARTISTA = "artista"
    ALBUM = "album"
    TOTAL = "total"


class EstadoReto(str, Enum):
    """Estado final que el usuario asigno a un reto al avanzar.

    Estos estados son una abstraccion ludica: NO modifican la biblioteca.
    Sirven para que la ronda muestre un resumen al final.
    """

    EN_CURSO = "en_curso"
    ACERTADO = "acertado"  # marcada como acertada antes de revelar
    REVELADO = "revelado"  # se uso "revelar todo"
    PASADO = "pasado"  # se salto sin resolver


@dataclass
class Reto:
    """Estado de un reto individual dentro de una ronda.

    `pista` contiene todos los metadatos de la pista subyacente; la UI usa
    `nivel` para decidir que campos mostrar y cuales censurar con "???".

    `hints_reveladas` es un set de claves del catalogo de hints (ver
    `hints.generar_hints`) que el usuario ya desbloqueo. La UI las muestra
    acumulativamente; el servicio solo registra cuales estan visibles.
    """

    pista_id: int
    pista: dict
    modo: ModoExplorador
    nivel: NivelRevelacion = NivelRevelacion.OCULTO
    estado: EstadoReto = EstadoReto.EN_CURSO
    # Marcador de si el usuario pidio reproducir el fragmento al menos una vez.
    fragmento_escuchado: bool = False
    # Hints sobre el titulo desbloqueadas por el usuario.
    hints_reveladas: set = field(default_factory=set)
    # Cantidad de intentos fallidos de adivinanza. Usado para feedback de
    # progresion ("cerca" / "vas calentando").
    intentos_fallidos: int = 0

    def datos_visibles(self) -> dict:
        """Devuelve los campos publicos segun el nivel de revelacion.

        Esta es la unica funcion que la UI debe usar para renderizar el
        contenido del reto. Censura titulo/artista/album con "???" hasta que
        cada uno haya sido revelado.
        """
        # Importacion local para evitar ciclo (hints importa de modelos).
        from .hints import generar_hints

        oculto = "???"
        titulo_real = self.pista.get("titulo", "") or ""
        catalogo_hints = generar_hints(titulo_real)
        # Solo exponemos a la UI las hints que el usuario YA desbloqueo.
        hints_visibles = {
            clave: valor
            for clave, valor in catalogo_hints.items()
            if clave in self.hints_reveladas
        }
        return {
            "pista_id": self.pista_id,
            "modo": self.modo.value,
            "nivel": self.nivel.value,
            "estado": self.estado.value,
            "fragmento_escuchado": self.fragmento_escuchado,
            # Censuras progresivas
            "titulo": titulo_real if self.nivel == NivelRevelacion.TOTAL else oculto,
            "artista": (
                self.pista.get("artista_nombre", "")
                if self.nivel in (NivelRevelacion.ARTISTA, NivelRevelacion.ALBUM, NivelRevelacion.TOTAL)
                else oculto
            ),
            "album": (
                self.pista.get("album_titulo", "")
                if self.nivel in (NivelRevelacion.ALBUM, NivelRevelacion.TOTAL)
                else oculto
            ),
            "anio": self.pista.get("anio") if self.nivel == NivelRevelacion.TOTAL else None,
            "artista_id": self.pista.get("artista_id"),
            "album_id": self.pista.get("album_id"),
            "duracion_seg": float(self.pista.get("duracion_seg") or 0.0),
            "portada_ruta": self.pista.get("portada_ruta") or "",
            "ruta_archivo": self.pista.get("ruta_archivo") or "",
            # Hint cuantitativo: cuantas reproducciones tiene la pista (util
            # para mostrar contexto despues de revelar — "la has escuchado X
            # veces", "no la has tocado nunca").
            "veces_reproducida": int(self.pista.get("veces_reproducida") or 0),
            "favorita": bool(self.pista.get("favorita")),
            # Sistema de adivinanza por escritura.
            "alfabeto": catalogo_hints["alfabeto"],
            "requiere_escritura": catalogo_hints["requiere_escritura"],
            "hints_disponibles": [
                k for k in (
                    "alfabeto", "empieza_con", "termina_con",
                    "cantidad_palabras", "cantidad_letras",
                )
                if k in catalogo_hints
            ],
            "hints_reveladas": sorted(self.hints_reveladas),
            "hints_visibles": hints_visibles,
            "intentos_fallidos": int(self.intentos_fallidos),
        }


@dataclass
class ResumenRonda:
    """Snapshot final de una ronda, util para mostrar feedback al usuario."""

    modo: ModoExplorador
    total: int
    acertados: int
    revelados: int
    pasados: int

    def to_dict(self) -> dict:
        return {
            "modo": self.modo.value,
            "total": int(self.total),
            "acertados": int(self.acertados),
            "revelados": int(self.revelados),
            "pasados": int(self.pasados),
        }
