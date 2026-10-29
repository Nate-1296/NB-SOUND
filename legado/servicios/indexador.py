# =============================================================================
# servicios/indexador.py
#
# Indexador de biblioteca: escanea la carpeta de biblioteca y mantiene
# la BD sincronizada con los archivos fisicos.
#
# El indexador es el puente entre el mundo fisico (archivos MP3 con tags ID3)
# y el mundo logico (tablas en SQLite). Lee los tags directamente con mutagen,
# crea/actualiza artistas, albums y pistas, y elimina registros de archivos
# que ya no existen en disco.
#
# Se usa desde los servicios de importacion/background para mantener SQLite
# sincronizado sin poner logica de indexado dentro de QML.
# =============================================================================

import hashlib
from pathlib import Path
from typing import Optional, Callable

try:
    from mutagen.id3 import ID3, ID3NoHeaderError
    from mutagen.mp3 import MP3
    MUTAGEN_DISPONIBLE = True
except ImportError:
    MUTAGEN_DISPONIBLE = False

from db.conexion import obtener_filas, obtener_una_fila, ejecutar, ejecutar_muchos, ejecutar_y_obtener_id
from utils.text import construir_slug_artista, construir_slug_album
from infra.logger import obtener_logger

logger = obtener_logger(__name__)

# Callback de progreso: (procesados, total, nombre_archivo) -> None
TipoCallbackProgreso = Callable[[int, int, str], None]


# =============================================================================
# LECTURA DE TAGS
# =============================================================================

def leer_tags_mp3(ruta: Path) -> dict:
    """
    Lee los tags ID3 de un archivo MP3 y retorna un diccionario normalizado.
    Retorna un dict con claves: titulo, artista, album, track_number, anio,
    genero, duracion_seg, bitrate_kbps, tamano_bytes, isrc,
    mb_recording_id, mb_release_id, mb_release_type, tagger_fuentes.
    """
    resultado = {
        "titulo":           ruta.stem,
        "artista":          "",
        "album":            "",
        "track_number":     None,
        "anio":             None,
        "genero":           "",
        "duracion_seg":     None,
        "bitrate_kbps":     None,
        "tamano_bytes":     ruta.stat().st_size if ruta.exists() else 0,
        "isrc":             None,
        "mb_recording_id":  None,
        "mb_release_id":    None,
        "mb_release_type":  None,
        "tagger_fuentes":   None,
    }

    if not MUTAGEN_DISPONIBLE or not ruta.exists():
        return resultado

    try:
        audio = MP3(str(ruta))
        resultado["duracion_seg"] = audio.info.length
        resultado["bitrate_kbps"] = int(audio.info.bitrate / 1000)
    except Exception as _exc:
        logger.debug("Excepcion ignorada en %s: %s", "indexador.py", _exc)

    try:
        tags = ID3(str(ruta))

        def _leer(frame_id: str) -> str:
            frame = tags.get(frame_id)
            return str(frame.text[0]).strip() if frame and frame.text else ""

        titulo = _leer("TIT2")
        if titulo:
            resultado["titulo"] = titulo

        artista = _leer("TPE1")
        if artista:
            resultado["artista"] = artista

        album = _leer("TALB")
        if album:
            resultado["album"] = album

        genero = _leer("TCON")
        if genero:
            resultado["genero"] = genero

        isrc = _leer("TSRC")
        if isrc:
            resultado["isrc"] = isrc

        # Anio
        anio_str = _leer("TDRC")
        if anio_str:
            try:
                resultado["anio"] = int(anio_str[:4])
            except ValueError:
                pass

        # Track number (puede ser "3/12" o "3")
        track_str = _leer("TRCK")
        if track_str:
            try:
                resultado["track_number"] = int(track_str.split("/")[0])
            except ValueError:
                pass

        # Tags TXXX del tagger
        for frame in tags.getall("TXXX"):
            desc = frame.desc.lower() if frame.desc else ""
            valor = str(frame.text[0]).strip() if frame.text else ""
            if desc == "mb_recording_id":
                resultado["mb_recording_id"] = valor or None
            elif desc == "mb_release_id":
                resultado["mb_release_id"] = valor or None
            elif desc == "mb_release_type":
                resultado["mb_release_type"] = valor or None
            elif desc == "tagger_sources":
                resultado["tagger_fuentes"] = valor or None

    except (ID3NoHeaderError, Exception):
        pass

    return resultado


def calcular_hash(ruta: Path, fragmento_bytes: int = 65_536) -> Optional[str]:
    """
    Calcula un hash SHA-256 usando solo los primeros N bytes del archivo.
    Es suficientemente unico para detectar duplicados sin leer archivos
    enteros de 50-100 MB.
    """
    try:
        hasher = hashlib.sha256()
        with ruta.open("rb") as f:
            hasher.update(f.read(fragmento_bytes))
        return hasher.hexdigest()
    except OSError:
        return None


# =============================================================================
# INDEXACION
# =============================================================================

class IndexadorBiblioteca:
    """
    Escanea la carpeta de biblioteca y mantiene la BD actualizada.

    Uso:
        idx = IndexadorBiblioteca(dir_biblioteca)
        idx.ejecutar_rescan(callback_progreso=mi_funcion)
    """

    def __init__(self, directorio_biblioteca: Path) -> None:
        self._dir_biblioteca = directorio_biblioteca

    # ------------------------------------------------------------------
    # API PUBLICA
    # ------------------------------------------------------------------

    def ejecutar_rescan(
        self,
        callback_progreso: Optional[TipoCallbackProgreso] = None,
    ) -> dict:
        """
        Escanea todos los archivos .mp3 en la biblioteca e indexa los nuevos
        o modificados. Elimina registros de archivos que ya no existen.

        Retorna un dict con: indexados, actualizados, eliminados, errores.
        """
        archivos = list(self._dir_biblioteca.rglob("*.mp3")) if self._dir_biblioteca.exists() else []
        total = len(archivos)
        stats = {"indexados": 0, "actualizados": 0, "eliminados": 0, "errores": 0}

        # Paso 1: Indexar/actualizar archivos presentes
        for i, ruta in enumerate(archivos):
            nombre = ruta.name
            if callback_progreso:
                callback_progreso(i + 1, total, nombre)
            try:
                resultado = self._indexar_archivo(ruta)
                if resultado == "indexado":
                    stats["indexados"] += 1
                elif resultado == "actualizado":
                    stats["actualizados"] += 1
            except Exception:
                stats["errores"] += 1

        # Paso 2: Eliminar registros de archivos que ya no existen
        stats["eliminados"] = self._limpiar_inexistentes()

        return stats

    def indexar_archivo_nuevo(self, ruta: Path) -> bool:
        """
        Indexa un unico archivo (llamado despues de que el tagger lo acepta).
        Retorna True si se indexo correctamente.
        """
        try:
            self._indexar_archivo(ruta)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # IMPLEMENTACION INTERNA
    # ------------------------------------------------------------------

    def _indexar_archivo(self, ruta: Path) -> str:
        """
        Inserta o actualiza el registro de una pista.
        Retorna 'indexado', 'actualizado', 'omitido' o 'duplicado_hash'.

        Defensa contra duplicados (caso real en reimportación):
        si el pipeline aceptó dos archivos binariamente idénticos en
        rutas distintas (porque el dedupe en memoria no detectó la
        previa entrada de la BD por algún fallo de inicialización),
        este método aún detecta el hash colisionado contra otras
        ``ruta_archivo`` ya existentes y descarta el nuevo. Sin esto,
        la tabla ``pistas`` quedaba con N pistas duplicadas (mismo
        hash + mismo mb_recording_id, distintas rutas).
        """
        ruta_str = str(ruta)
        hash_archivo = calcular_hash(ruta)

        # 1. ¿Existe ya con esa ruta exacta? (caso típico: re-indexar)
        fila_existente = obtener_una_fila(
            "SELECT id, hash_sha256 FROM pistas WHERE ruta_archivo = ?",
            (ruta_str,)
        )

        if fila_existente:
            if fila_existente["hash_sha256"] == hash_archivo:
                return "omitido"
            # El archivo cambio — actualizar
            accion = "actualizado"
        else:
            # 2. ¿Existe ya con el mismo HASH en otra ruta?
            #    Reimportación bug: el writer renombra a `..._2.mp3`
            #    cuando el destino existe; sin esta validación, el
            #    indexador inserta una pista nueva con mismo hash que
            #    una ya registrada, dejando duplicados en la BD.
            colision = obtener_una_fila(
                "SELECT id, ruta_archivo FROM pistas "
                "WHERE hash_sha256 = ? AND ruta_archivo <> ?",
                (hash_archivo, ruta_str),
            )
            if colision:
                # Limpiar el archivo recién copiado para no dejar
                # basura en biblioteca/.
                try:
                    ruta.unlink()
                except Exception:
                    pass
                # Y limpiar carpeta del archivo si quedó vacía (común
                # cuando la ruta es <biblioteca>/<artista>/<album>/x.mp3
                # y el album/artista existieron solo por este archivo).
                try:
                    parent = ruta.parent
                    if parent.is_dir() and not any(parent.iterdir()):
                        parent.rmdir()
                except Exception:
                    pass
                return "duplicado_hash"
            accion = "indexado"

        tags = leer_tags_mp3(ruta)

        artista_id = self._obtener_o_crear_artista(tags["artista"] or "Desconocido")
        album_id   = self._obtener_o_crear_album(
            artista_id=artista_id,
            titulo=tags["album"] or "Sin album",
            tipo=tags.get("mb_release_type") or "Album",
            anio=tags.get("anio"),
            mb_release_id=tags.get("mb_release_id"),
            ruta_carpeta=str(ruta.parent),
        )

        if accion == "actualizado":
            ejecutar(
                """
                UPDATE pistas SET
                    album_id        = ?,
                    artista_id      = ?,
                    titulo          = ?,
                    artista_nombre  = ?,
                    album_titulo    = ?,
                    track_number    = ?,
                    duracion_seg    = ?,
                    bitrate_kbps    = ?,
                    anio            = ?,
                    genero          = ?,
                    isrc            = ?,
                    nombre_archivo  = ?,
                    tamano_bytes    = ?,
                    hash_sha256     = ?,
                    mb_recording_id = ?,
                    mb_release_id   = ?,
                    mb_release_type = ?,
                    tagger_fuentes  = ?,
                    actualizado_en  = datetime('now')
                WHERE ruta_archivo = ?
                """,
                (
                    album_id, artista_id, tags["titulo"],
                    tags["artista"], tags["album"],
                    tags["track_number"], tags["duracion_seg"],
                    tags["bitrate_kbps"], tags["anio"],
                    tags["genero"], tags["isrc"],
                    ruta.name, tags["tamano_bytes"], hash_archivo,
                    tags["mb_recording_id"], tags["mb_release_id"],
                    tags["mb_release_type"], tags["tagger_fuentes"],
                    ruta_str,
                ),
            )
        else:
            ejecutar(
                """
                INSERT INTO pistas (
                    album_id, artista_id, titulo, artista_nombre,
                    album_titulo, track_number, duracion_seg, bitrate_kbps,
                    anio, genero, isrc, ruta_archivo, nombre_archivo,
                    tamano_bytes, hash_sha256, mb_recording_id,
                    mb_release_id, mb_release_type, tagger_fuentes
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    album_id, artista_id, tags["titulo"],
                    tags["artista"], tags["album"],
                    tags["track_number"], tags["duracion_seg"],
                    tags["bitrate_kbps"], tags["anio"],
                    tags["genero"], tags["isrc"],
                    ruta_str, ruta.name, tags["tamano_bytes"],
                    hash_archivo, tags["mb_recording_id"],
                    tags["mb_release_id"], tags["mb_release_type"],
                    tags["tagger_fuentes"],
                ),
            )

        # Ecosistema movil: marca la pista con la proxima sync_version para
        # que el cliente detecte el alta/cambio en el delta. Best-effort: un
        # fallo aqui no debe abortar la indexacion.
        try:
            from db.conexion import marcar_sync_version
            fila_id = obtener_una_fila(
                "SELECT id FROM pistas WHERE ruta_archivo = ?", (ruta_str,)
            )
            if fila_id:
                marcar_sync_version("pistas", fila_id["id"])
        except Exception as exc:
            logger.debug("No se pudo marcar sync_version de la pista %s: %s", ruta_str, exc)

        return accion

    def _obtener_o_crear_artista(self, nombre: str) -> int:
        slug = construir_slug_artista(nombre)
        fila = obtener_una_fila(
            "SELECT id FROM artistas WHERE nombre_slug = ?", (slug,)
        )
        if fila:
            return fila["id"]
        artista_id = ejecutar_y_obtener_id(
            "INSERT INTO artistas(nombre, nombre_slug) VALUES (?, ?)",
            (nombre, slug),
        )
        try:
            from db.conexion import marcar_sync_version
            marcar_sync_version("artistas", artista_id)
        except Exception as exc:
            logger.debug("No se pudo marcar sync_version del artista %s: %s", artista_id, exc)
        return artista_id

    def _obtener_o_crear_album(
        self,
        artista_id: int,
        titulo: str,
        tipo: str,
        anio: Optional[int],
        mb_release_id: Optional[str],
        ruta_carpeta: str,
    ) -> int:
        slug = construir_slug_album(titulo)
        fila = obtener_una_fila(
            "SELECT id FROM albums WHERE artista_id = ? AND titulo_slug = ?",
            (artista_id, slug),
        )
        if fila:
            return fila["id"]
        album_id = ejecutar_y_obtener_id(
            """
            INSERT INTO albums(artista_id, titulo, titulo_slug, tipo, anio, mb_release_id, ruta_carpeta)
            VALUES (?,?,?,?,?,?,?)
            """,
            (artista_id, titulo, slug, tipo, anio, mb_release_id, ruta_carpeta),
        )
        try:
            from db.conexion import marcar_sync_version
            marcar_sync_version("albums", album_id)
        except Exception as exc:
            logger.debug("No se pudo marcar sync_version del album %s: %s", album_id, exc)
        return album_id

    def _limpiar_inexistentes(self) -> int:
        """
        Elimina registros de pistas cuyo archivo ya no existe en disco.
        Retorna el numero de registros eliminados.
        
        Optimizacion: Usa batch delete para evitar O(N²).
        Timeout máximo: 10 segundos para evitar bloqueos largos.
        """
        import time
        
        inicio = time.time()
        timeout_seg = 10  # máximo tiempo permitido
        
        try:
            # Cargar rutas de BD (con id para registrar tombstones de sync)
            filas_en_bd = [
                (fila["id"], fila["ruta_archivo"])
                for fila in obtener_filas("SELECT id, ruta_archivo FROM pistas")
            ]

            # Identificar cuáles NO existen, respetando timeout
            a_eliminar = []
            ids_eliminados = []
            for pista_id, ruta in filas_en_bd:
                if time.time() - inicio > timeout_seg:
                    logger.warning(
                        f"_limpiar_inexistentes: timeout alcanzado ({timeout_seg}s) "
                        f"después de procesar {len(a_eliminar)} archivos. "
                        f"Continuando con lo acumulado."
                    )
                    break
                if not Path(ruta).exists():
                    a_eliminar.append((ruta,))
                    ids_eliminados.append(pista_id)

            # Registrar tombstones ANTES del DELETE para propagar el borrado al
            # ecosistema movil (un DELETE no se detecta por sync_version).
            if ids_eliminados:
                try:
                    from db.conexion import registrar_tombstone
                    for pista_id in ids_eliminados:
                        registrar_tombstone("pista", pista_id)
                except Exception as exc:
                    logger.debug("No se pudieron registrar tombstones de pistas: %s", exc)

            # Batch delete con executemany (más eficiente que loop individual)
            if a_eliminar:
                ejecutar_muchos(
                    "DELETE FROM pistas WHERE ruta_archivo = ?",
                    a_eliminar
                )
            
            if a_eliminar:
                logger.info(f"_limpiar_inexistentes: eliminados {len(a_eliminar)} registros")
            
            return len(a_eliminar)
        except Exception as e:
            logger.error(f"Error en _limpiar_inexistentes: {e}", exc_info=True)
            return 0
