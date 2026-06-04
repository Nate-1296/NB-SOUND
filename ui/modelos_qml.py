# =============================================================================
# ui/modelos_qml.py
#
# Modelos QML: objetos QObject que actuan como puente entre los servicios
# Python y la interfaz QML.
#
# Cada modelo expone propiedades (Q_PROPERTY), listas (QAbstractListModel) y
# slots (@Slot) que QML puede llamar directamente. Los modelos nunca contienen
# logica de negocio — delegan en los servicios de la capa de aplicacion.
#
# Modelos disponibles:
#   - ModeloBiblioteca   : artistas, albums y pistas de la coleccion
#   - ModeloReproductor  : estado del reproductor y cola
#   - ModeloBusqueda     : resultados de busqueda en tiempo real
#   - ModeloImportacion  : progreso de la importacion en curso
#   - ModeloRevision     : archivos en revision y cuarentena
#   - ModeloEstadisticas : metricas de la coleccion
#   - ModeloPlaylists    : playlists manuales, sistema y automaticas locales
# =============================================================================

from typing import Optional
from pathlib import Path
import json
import math
import os
import random
import re
import sys
import tempfile
import time
import unicodedata


def _normalizar_busqueda(texto: str) -> str:
    """Normaliza un texto para búsqueda tolerante a tildes/mayúsculas.

    Aplica NFD para descomponer los caracteres y descarta diacríticos
    (combining marks). Conserva ñ → n por simplicidad (la ñ separa el
    glifo en n + tilde-combinante, que se descarta).
    """
    if not texto:
        return ""
    normalizado = unicodedata.normalize("NFD", str(texto))
    sin_diacriticos = "".join(c for c in normalizado if unicodedata.category(c) != "Mn")
    return sin_diacriticos.lower()

from PySide6.QtCore import (
    QObject, QAbstractListModel, QModelIndex, Qt, Signal, Slot, Property, QUrl,
    QCoreApplication, QTimer,
)
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QImage
from PySide6.QtQml import QJSValue

from infra.logger import obtener_logger
from servicios import biblioteca as svc_bib
from servicios.reproductor import (
    EstadoReproductor, Reproductor,
    EQ_PRESET_NOMBRES_ES, EQ_BANDAS_HZ,
    EQ_AMP_MIN, EQ_AMP_MAX, EQ_PREAMP_MIN, EQ_PREAMP_MAX,
)
from utils.diccionarios import saludo_inicio


_log = obtener_logger("ui.modelos_qml")


# =============================================================================
# WORKER GENÉRICO PARA QUERIES DE UI (ZERO-FREEZE)
# =============================================================================

class _UiQueryWorker(QObject):
    """QObject helper que ejecuta callables en un QThread y entrega el
    resultado por una signal con QueuedConnection automática.

    Por qué existe
    --------------
    Los modelos QML originalmente ejecutaban queries SQL pesadas
    (``svc_bib.listar_artistas``, ``listar_albums``, ``listar_pistas_karaoke``,
    …) directamente en el slot, lo que congelaba la UI durante 100-500ms
    en bibliotecas grandes la primera vez que se abría cada vista.

    Este worker es la solución mínima genérica para mover esas queries a
    un hilo background. Cada llamada a ``run(func, applier)`` arranca un
    QThread descartable, ejecuta ``func()`` ahí, y al terminar emite
    ``terminado(applier, resultado)`` que el slot conectado al modelo
    aplica en el hilo principal (signal/slot atraviesa threads en Qt con
    QueuedConnection si los QObjects viven en threads distintos).

    Patrón thread-safe: el QObject se construye y vive en el thread
    principal; el callable se ejecuta en el worker thread. El resultado
    cruza vía signal, así que mutar listas QML en ``applier`` es seguro.
    """
    terminado = Signal(object, object)  # applier_callable, resultado

    def __init__(self, parent=None):
        super().__init__(parent)
        self._threads: list = []  # mantenemos referencias para que QThread no se libere antes de terminar
        self.terminado.connect(self._aplicar)

    def run(self, func, applier) -> None:
        """Ejecuta ``func()`` en background. ``applier(resultado)`` corre
        en el thread principal cuando ``func`` termina.

        Si ``func`` lanza excepción, ``applier`` recibe None y la
        excepción se loggea. Esto evita que un fallo de query tumbe el
        slot que la lanzó.

        Modo síncrono para tests
        ------------------------
        Si la variable de entorno ``NB_SOUND_UI_WORKER_SYNC`` está
        seteada a ``1/true/yes``, ``func`` y ``applier`` se ejecutan
        sincrónamente en el hilo actual. Permite mantener la suite
        de tests determinista sin tener que bombear eventos Qt
        manualmente después de cada operación.
        """
        import os
        if os.environ.get("NB_SOUND_UI_WORKER_SYNC", "").strip().lower() in {"1", "true", "yes"}:
            try:
                resultado = func()
            except Exception as exc:
                _log.warning("_UiQueryWorker query (sync) falló: %s", exc)
                resultado = None
            try:
                applier(resultado)
            except Exception as exc:
                _log.warning("_UiQueryWorker applier (sync) falló: %s", exc)
            return

        from PySide6.QtCore import QThread

        class _Hilo(QThread):
            def __init__(self_inner, func, parent_worker):
                super().__init__(parent_worker)
                self_inner._func = func
                self_inner._parent_worker = parent_worker
            def run(self_inner):
                try:
                    resultado = self_inner._func()
                except Exception as exc:
                    _log.warning("_UiQueryWorker query falló: %s", exc)
                    resultado = None
                self_inner._parent_worker.terminado.emit(applier, resultado)

        hilo = _Hilo(func, self)
        # Auto-cleanup: cuando termina, liberamos su referencia para que
        # el GC pueda recoger el QThread. Mantenemos la referencia mientras
        # corre para que Qt no lo destruya antes de tiempo.
        self._threads.append(hilo)
        hilo.finished.connect(lambda h=hilo: self._descartar(h))
        hilo.start()

    def _descartar(self, hilo) -> None:
        try:
            self._threads.remove(hilo)
        except ValueError:
            pass
        try:
            hilo.deleteLater()
        except Exception:
            pass

    @Slot(object, object)
    def _aplicar(self, applier, resultado) -> None:
        try:
            applier(resultado)
        except Exception as exc:
            _log.warning("_UiQueryWorker applier falló: %s", exc)


# =============================================================================
# LISTA GENERICA (AbstractListModel para QML ListView)
# =============================================================================

class ListaGenerica(QAbstractListModel):
    """
    Modelo de lista generico que acepta listas de dicts.
    Cada clave del dict se convierte en un rol accesible desde QML.
    """
    totalCambiado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._datos: list[dict] = []
        self._roles: dict[int, bytes] = {}

    def set_datos(self, datos: list[dict]) -> None:
        self.beginResetModel()
        self._datos = datos
        if datos:
            claves: list[str] = []
            vistas = set()
            for fila in datos:
                for clave in fila.keys():
                    if clave not in vistas:
                        vistas.add(clave)
                        claves.append(clave)
            self._roles = {
                Qt.UserRole + i: clave.encode()
                for i, clave in enumerate(claves)
            }
        else:
            self._roles = {}
        self.endResetModel()
        self.totalCambiado.emit()

    def snapshot(self) -> list[dict]:
        return list(self._datos)

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._datos)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._datos):
            return None
        fila = self._datos[index.row()]
        clave = self._roles.get(role, b"").decode()
        valor = fila.get(clave)
        # Convertir None a "" para QML
        return valor if valor is not None else ""

    def roleNames(self) -> dict:
        return self._roles

    @Slot(int, result="QVariant")
    def obtener(self, indice: int) -> dict:
        """Retorna el dict completo de un elemento por indice."""
        if 0 <= indice < len(self._datos):
            return self._datos[indice]
        return {}

    @Property(int, notify=totalCambiado)
    def total(self) -> int:
        return len(self._datos)


# =============================================================================
# MODELO DE BIBLIOTECA
# =============================================================================

class ModeloBiblioteca(QObject):
    """
    Expone la coleccion musical completa a QML.
    Provee listas reactivas de artistas, albums y pistas con filtros.
    """

    artistasCargados    = Signal()
    albumsCargados      = Signal()
    pistasCargadas      = Signal()
    gruposAlbumsCargados = Signal()
    estadoBibliotecaCambiado = Signal()
    albumDetalleActivo  = Signal()
    artistaDetalleActivo = Signal()
    errorCargando       = Signal(str)
    # Notifica cuando una pista cambia de estado favorita. Otros modelos
    # (ModeloPlaylists, ModeloBusqueda) deben escuchar esta señal para
    # refrescar sus listas (la playlist "Me gusta" se actualiza así en vivo).
    favoritaCambiada    = Signal(int, bool)  # (pista_id, nueva_es_favorita)
    # Barrido de duplicados observables (3a capa de dedupe). El refresco de la
    # biblioteca/estadísticas/inicio se hace en vivo al completar; estas señales
    # permiten que la UI muestre progreso y el resumen sin reiniciar la app.
    dedupeObservableProgreso   = Signal(dict)
    dedupeObservableFinalizado = Signal(dict)

    _CLAVE_ESTADO_VISTA = "vista_biblioteca_estado"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._artistas  = ListaGenerica(self)
        self._albums    = ListaGenerica(self)
        self._pistas    = ListaGenerica(self)
        self._grupos_albums = ListaGenerica(self)
        self._album_detalle: Optional[dict] = None
        self._artista_detalle: Optional[dict] = None
        self._cargando  = False
        # Worker para que las queries pesadas (listar_artistas, listar_albums,
        # listar_pistas, …) corran en QThread separados y el slot retorne
        # de inmediato. Sin esto la primera apertura de Biblioteca trababa
        # la UI 100-500ms mientras SQL recorría la tabla `pistas`.
        self._ui_worker = _UiQueryWorker(self)
        # Worker del barrido de duplicados observables (3a capa de dedupe).
        self._worker_dedupe = None

    # ------------------------------------------------------------------
    # PROPIEDADES
    # ------------------------------------------------------------------

    @Property(QObject, notify=artistasCargados)
    def artistas(self) -> ListaGenerica:
        return self._artistas

    @Property(QObject, notify=albumsCargados)
    def albums(self) -> ListaGenerica:
        return self._albums

    @Property(QObject, notify=pistasCargadas)
    def pistas(self) -> ListaGenerica:
        return self._pistas

    @Property(QObject, notify=gruposAlbumsCargados)
    def grupos_albums(self) -> ListaGenerica:
        return self._grupos_albums

    @Property("QVariant", notify=albumDetalleActivo)
    def album_detalle(self) -> dict:
        return self._album_detalle or {}

    @Property("QVariant", notify=artistaDetalleActivo)
    def artista_detalle(self) -> dict:
        return self._artista_detalle or {}

    # ------------------------------------------------------------------
    # SLOTS
    # ------------------------------------------------------------------

    @Slot()
    @Slot(str)
    @Slot(str, str)
    def cargar_artistas(self, filtro_texto: str = "", orden: str = "nombre") -> None:
        # Query SQL puede tardar 100-300ms en bibliotecas con >1000 artistas.
        # La ejecutamos en QThread y aplicamos resultado en main thread.
        self._ui_worker.run(
            lambda: svc_bib.listar_artistas(filtro_texto=filtro_texto, orden=orden),
            self._aplicar_artistas,
        )

    def _aplicar_artistas(self, datos) -> None:
        self._artistas.set_datos(datos or [])
        self.artistasCargados.emit()

    @Slot()
    def cargar_grupos_albums(self) -> None:
        self._ui_worker.run(
            svc_bib.grupos_albums_disponibles,
            self._aplicar_grupos_albums,
        )

    def _aplicar_grupos_albums(self, datos) -> None:
        self._grupos_albums.set_datos(datos or [])
        self.gruposAlbumsCargados.emit()

    @Slot(result=str)
    def primer_grupo_albums(self) -> str:
        grupos = self._grupos_albums.snapshot()
        if not grupos:
            grupos = svc_bib.grupos_albums_disponibles()
            self._grupos_albums.set_datos(grupos)
            self.gruposAlbumsCargados.emit()
        return str(grupos[0].get("clave") or "albums") if grupos else "albums"

    @Slot()
    @Slot(str)
    @Slot(str, str)
    def cargar_albums(self, orden: str = "artista", filtro_texto: str = "") -> None:
        self._ui_worker.run(
            lambda: svc_bib.listar_albums(orden=orden, filtro_texto=filtro_texto),
            self._aplicar_albums,
        )

    def _aplicar_albums(self, datos) -> None:
        self._albums.set_datos(datos or [])
        self.albumsCargados.emit()

    @Slot(str)
    @Slot(str, str)
    @Slot(str, str, str)
    def cargar_albums_por_grupo(self, grupo: str, orden: str = "artista", filtro_texto: str = "") -> None:
        self._ui_worker.run(
            lambda: svc_bib.listar_albums(grupo=grupo, orden=orden, filtro_texto=filtro_texto),
            self._aplicar_albums,
        )

    @Slot(int)
    def cargar_albums_de_artista(self, artista_id: int) -> None:
        datos = svc_bib.listar_albums(artista_id=artista_id)
        self._albums.set_datos(datos)
        self.albumsCargados.emit()

    @Slot(int)
    def cargar_pistas_de_album(self, album_id: int) -> None:
        datos = svc_bib.listar_pistas_de_album(album_id)
        self._pistas.set_datos(datos)
        self.pistasCargadas.emit()

    @Slot()
    @Slot(str)
    @Slot(str, bool, str)
    def cargar_pistas(self, filtro_texto: str = "", solo_favoritas: bool = False, orden: str = "titulo") -> None:
        datos = svc_bib.listar_pistas(
            filtro_texto=filtro_texto,
            solo_favoritas=bool(solo_favoritas),
            orden=orden,
            limite=None,
        )
        self._pistas.set_datos(datos)
        self.pistasCargadas.emit()

    @Slot(int)
    def abrir_album(self, album_id: int) -> None:
        detalle = svc_bib.detalle_album(album_id)
        if detalle:
            self._album_detalle = detalle
            self._pistas.set_datos(detalle.get("pistas", []))
            self.pistasCargadas.emit()
            self.albumDetalleActivo.emit()

    @Slot(int)
    def abrir_artista(self, artista_id: int) -> None:
        detalle = svc_bib.detalle_artista(artista_id)
        if detalle:
            self._artista_detalle = detalle
            self.artistaDetalleActivo.emit()

    @Slot("QVariant", result="QVariantMap")
    def abrir_album_desde_pista(self, datos_pista) -> dict:
        pista = self._normalizar_qvariant_map(datos_pista)
        album_id = self._entero_seguro(pista.get("album_id"))
        if album_id and self._activar_album(album_id):
            return {"ok": True, "fallback": False, "mensaje": ""}

        titulo_album = self._texto_seguro(
            pista.get("album_titulo"),
            pista.get("album"),
        )
        artista = self._texto_seguro(
            pista.get("artista_nombre"),
            pista.get("artista"),
        )
        if len(titulo_album) < 2:
            return {
                "ok": False,
                "fallback": False,
                "mensaje": "No hay álbum suficiente para abrir el detalle.",
            }

        resultados = self._buscar_albums_para_fallback(titulo_album)
        titulo_norm = self._normalizar_texto(titulo_album)
        artista_norm = self._normalizar_texto(artista)
        candidatos = [
            album for album in resultados
            if self._normalizar_texto(album.get("titulo")) == titulo_norm
            and (
                not artista_norm
                or self._normalizar_texto(album.get("artista_nombre")) == artista_norm
            )
        ]

        if len(candidatos) != 1:
            return {
                "ok": False,
                "fallback": False,
                "mensaje": "No se encontró un álbum único con esa metadata.",
            }

        if self._activar_album(self._entero_seguro(candidatos[0].get("id"))):
            return {
                "ok": True,
                "fallback": True,
                "mensaje": "Álbum encontrado por metadata.",
            }
        return {
            "ok": False,
            "fallback": False,
            "mensaje": "No se pudo abrir el álbum encontrado.",
        }

    @Slot("QVariant", result="QVariantMap")
    def abrir_artista_desde_pista(self, datos_pista) -> dict:
        pista = self._normalizar_qvariant_map(datos_pista)
        artista_id = self._entero_seguro(pista.get("artista_id"))
        if artista_id and self._activar_artista(artista_id):
            return {"ok": True, "fallback": False, "mensaje": ""}

        artista = self._texto_seguro(
            pista.get("artista_nombre"),
            pista.get("artista"),
        )
        if len(artista) < 2:
            return {
                "ok": False,
                "fallback": False,
                "mensaje": "No hay artista suficiente para abrir el detalle.",
            }

        resultados = self._buscar_artistas_para_fallback(artista)
        artista_norm = self._normalizar_texto(artista)
        candidatos = [
            candidato for candidato in resultados
            if self._normalizar_texto(candidato.get("nombre")) == artista_norm
        ]

        if len(candidatos) != 1:
            return {
                "ok": False,
                "fallback": False,
                "mensaje": "No se encontró un artista único con esa metadata.",
            }

        if self._activar_artista(self._entero_seguro(candidatos[0].get("id"))):
            return {
                "ok": True,
                "fallback": True,
                "mensaje": "Artista encontrado por metadata.",
            }
        return {
            "ok": False,
            "fallback": False,
            "mensaje": "No se pudo abrir el artista encontrado.",
        }

    @Slot(int, result=bool)
    def toggle_favorita(self, pista_id: int) -> bool:
        nueva = svc_bib.toggle_favorita(pista_id)
        # Notificamos para que ModeloPlaylists y ModeloBusqueda refresquen
        # sus listas (la playlist "Me gusta" se sincroniza en BD vía
        # _sincronizar_playlist_favoritos pero los modelos QML necesitan
        # recargar los datos visibles).
        self.favoritaCambiada.emit(int(pista_id), bool(nueva))
        return nueva


    @Slot()
    def recargar(self) -> None:
        self.cargar_grupos_albums()
        self.cargar_artistas()
        self.cargar_albums_por_grupo(self.primer_grupo_albums())
        self.cargar_pistas()

    @Slot()
    def ejecutar_dedupe_observable(self) -> None:
        """Lanza en background el barrido de duplicados observables (3a capa).

        Detecta pistas que comparten título, artista, álbum, portada y duración
        (duplicado "obvio" sin hash/ISRC/fingerprint comunes) y oculta las
        sobrantes dejando solo la mejor. Corre en un QThread de baja prioridad;
        al completar, refresca la biblioteca en vivo (las ocultas desaparecen
        sin reiniciar la app). Reentrante-seguro: si ya hay un barrido en curso,
        no arranca otro.
        """
        if self._worker_dedupe is not None and self._worker_dedupe.isRunning():
            return
        if QCoreApplication.instance() is None:
            # Sin loop Qt (tests de servicio): ejecuta de forma síncrona.
            try:
                from servicios.dedupe_observable import ejecutar_barrido
                resultado = ejecutar_barrido()
                self.dedupeObservableFinalizado.emit(resultado)
                if int(resultado.get("duplicados_resueltos") or 0) > 0:
                    self.recargar()
            except Exception as exc:
                _log.warning("dedupe observable (sync) falló: %s", exc)
            return

        from workers.workers_qt import WorkerDedupeObservable

        worker = WorkerDedupeObservable(parent=self)
        self._worker_dedupe = worker

        def _al_completar(resultado):
            self.dedupeObservableFinalizado.emit(dict(resultado or {}))
            # Solo refrescamos si realmente se resolvió algo (evita recargas
            # innecesarias cuando no había duplicados).
            if int((resultado or {}).get("duplicados_resueltos") or 0) > 0:
                self.recargar()
            if self._worker_dedupe is worker:
                self._worker_dedupe = None
            worker.deleteLater()

        worker.progreso.connect(self.dedupeObservableProgreso)
        worker.completado.connect(_al_completar)
        worker.error.connect(lambda msg: _log.warning("dedupe observable: %s", msg))
        worker.start()

    def cerrar(self) -> None:
        """Detiene el barrido de duplicados (si corre) en el cierre de la app."""
        worker = self._worker_dedupe
        if worker is not None and worker.isRunning():
            try:
                worker.requestInterruption()
                worker.wait(3000)
            except Exception as exc:
                _log.debug("cerrar worker dedupe fallo: %s", exc)

    @Slot(result="QVariantMap")
    def estado_vista(self) -> dict:
        from db.conexion import obtener_config

        bruto = obtener_config(self._CLAVE_ESTADO_VISTA, "")
        if bruto:
            try:
                estado = json.loads(bruto)
            except json.JSONDecodeError:
                estado = {}
            if isinstance(estado, dict):
                return self._normalizar_estado_vista(estado)

        legado = obtener_config("vista_biblioteca", "album")
        seccion = "albums"
        if legado in {"artistas", "artists"}:
            seccion = "artistas"
        elif legado in {"pistas", "tracks"}:
            seccion = "pistas"
        return self._normalizar_estado_vista({"seccion": seccion})

    @Slot("QVariant")
    def guardar_estado_vista(self, estado) -> None:
        from db.conexion import guardar_config

        normalizado = self._normalizar_estado_vista(self._normalizar_qvariant_map(estado))
        guardar_config(
            self._CLAVE_ESTADO_VISTA,
            json.dumps(normalizado, ensure_ascii=False, sort_keys=True),
        )
        self.estadoBibliotecaCambiado.emit()

    def _activar_album(self, album_id: int) -> bool:
        if not album_id:
            return False
        detalle = svc_bib.detalle_album(album_id)
        if not detalle:
            return False
        self._album_detalle = detalle
        self._pistas.set_datos(detalle.get("pistas", []))
        self.pistasCargadas.emit()
        self.albumDetalleActivo.emit()
        return True

    def _activar_artista(self, artista_id: int) -> bool:
        if not artista_id:
            return False
        detalle = svc_bib.detalle_artista(artista_id)
        if not detalle:
            return False
        self._artista_detalle = detalle
        self.artistaDetalleActivo.emit()
        return True

    def _normalizar_estado_vista(self, estado: dict) -> dict:
        seccion = str(estado.get("seccion") or estado.get("modo_vista") or "albums")
        if seccion not in {"albums", "artistas", "pistas"}:
            seccion = "albums"

        grupo = str(estado.get("grupo_albums") or "albums")
        if grupo not in {"albums", "singles_y_ep", "otros"}:
            grupo = "albums"

        detalle = str(estado.get("detalle") or "")
        if detalle not in {"album", "artista"}:
            detalle = ""

        orden_pistas = str(estado.get("orden_pistas") or "titulo")
        ordenes_pistas = {
            "titulo", "titulo_desc", "artista", "artista_desc", "album", "album_desc",
            "anio", "anio_asc", "duracion", "duracion_asc", "reciente", "reciente_asc",
            "reproducida", "reproducida_asc",
        }
        if orden_pistas not in ordenes_pistas:
            orden_pistas = "titulo"

        orden_albums = str(estado.get("orden_albums") or "artista")
        ordenes_albums = {
            "artista", "artista_desc", "titulo", "titulo_desc", "anio", "anio_asc",
            "duracion", "duracion_asc", "pistas", "pistas_asc",
        }
        if orden_albums not in ordenes_albums:
            orden_albums = "artista"

        orden_artistas = str(estado.get("orden_artistas") or "nombre")
        ordenes_artistas = {
            "nombre", "nombre_desc", "num_pistas", "num_pistas_asc",
            "num_albums", "num_albums_asc", "duracion", "duracion_asc",
        }
        if orden_artistas not in ordenes_artistas:
            orden_artistas = "nombre"

        return {
            "seccion": seccion,
            "grupo_albums": grupo,
            "detalle": detalle,
            "album_id": self._entero_seguro(estado.get("album_id")),
            "artista_id": self._entero_seguro(estado.get("artista_id")),
            "filtro_albums": self._texto_seguro(estado.get("filtro_albums")),
            "filtro_artistas": self._texto_seguro(estado.get("filtro_artistas")),
            "filtro_pistas": self._texto_seguro(estado.get("filtro_pistas")),
            "solo_favoritas": bool(estado.get("solo_favoritas")),
            "orden_pistas": orden_pistas,
            "orden_albums": orden_albums,
            "orden_artistas": orden_artistas,
            "scroll_albums": float(estado.get("scroll_albums") or 0),
            "scroll_artistas": float(estado.get("scroll_artistas") or 0),
            "scroll_pistas": float(estado.get("scroll_pistas") or 0),
        }

    def _normalizar_qvariant_map(self, valor) -> dict:
        if isinstance(valor, QJSValue):
            valor = valor.toVariant()
        return dict(valor) if isinstance(valor, dict) else {}

    def _entero_seguro(self, valor) -> int:
        try:
            return int(valor or 0)
        except (TypeError, ValueError):
            return 0

    def _texto_seguro(self, *valores) -> str:
        for valor in valores:
            texto = str(valor or "").strip()
            if texto:
                return texto
        return ""

    def _normalizar_texto(self, valor) -> str:
        return " ".join(str(valor or "").casefold().split())

    def _buscar_albums_para_fallback(self, termino: str) -> list[dict]:
        try:
            resultados = svc_bib.buscar(termino, limite=20).get("albums", [])
        except Exception as e:
            _log.warning("Busqueda de album por metadata falló: %s", e)
            resultados = []
        if resultados:
            return resultados
        return svc_bib.listar_albums(orden="titulo")

    def _buscar_artistas_para_fallback(self, termino: str) -> list[dict]:
        try:
            resultados = svc_bib.buscar(termino, limite=20).get("artistas", [])
        except Exception as e:
            _log.warning("Busqueda de artista por metadata falló: %s", e)
            resultados = []
        if resultados:
            return resultados
        return svc_bib.listar_artistas(orden="nombre")


# =============================================================================
# MODELO DE REPRODUCTOR
# =============================================================================

class ModeloReproductor(QObject):
    """
    Expone el estado del reproductor y la cola a QML.
    Sincroniza el estado de Python con las propiedades QML via seniales.
    """

    estadoCambiado         = Signal()
    pista_activaCambiada   = Signal()
    pistaVisualCambiada    = Signal()
    letraActivaCambiada    = Signal()
    progresoCambiado       = Signal()
    colaCambiada           = Signal()
    colaBackendCambiada    = Signal()
    volumenCambiado        = Signal()
    modoCambiado           = Signal()
    karaokeCambiado        = Signal()
    sorpresaActivaCambiada = Signal()
    lyricsMoodCambiado     = Signal()
    avisoReproductor       = Signal("QVariant")
    modoDjActivoCambiado   = Signal()
    # Ecualizador y opciones de audio del reproductor GLOBAL (Configuración →
    # Personalización). No afectan al DJ Privado.
    ecualizadorCambiado      = Signal()
    normalizarVolumenCambiado = Signal()
    # Modo "ciego": cuando se activa, las propiedades visibles de la pista
    # se censuran con "???" mientras el id activo coincida con el id
    # registrado por el Explorador Ciego. Es una capa de UI pura — no
    # cambia el audio ni la cola.
    modoCiegoCambiado      = Signal()

    _LRC_TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]")
    _LRC_METADATA_RE = re.compile(
        r"^\[(?:ar|al|ti|au|length|by|offset|re|ve|tool|la|id):[^\]]*\]$",
        re.IGNORECASE,
    )

    def __init__(self, reproductor: Reproductor, parent=None):
        super().__init__(parent)
        self._rep    = reproductor
        # Manager de ownership compartido con el DJ. Se inyecta tras la
        # construcción (main_ui los conecta). Si está presente, cuando el
        # usuario pide reproducir algo y el DJ tiene el audio, lo liberamos
        # primero — eso detiene el motor DJ en cadena via callback.
        self._ownership_dj = None
        self._cola   = ListaGenerica(self)
        self._pos_seg    = 0.0
        self._dur_seg    = 0.0
        self._pista_progreso_id: Optional[int] = None
        self._letra_activa = ""
        self._letra_plain_activa = ""
        self._letra_synced_activa = ""
        self._sugerencias_recientes: list[str] = []
        self._sugerencias_recientes_artistas: list[str] = []
        self._sugerencias_recientes_albums: list[str] = []
        self._sorpresa_clave_activa = ""
        self._sorpresa_activa_visible = False
        self._lyrics_mood_cache: dict[str, dict[str, float]] = {}
        self._karaoke_activo = False
        self._avisos_reproductor_retenidos: list[dict] = []
        self._progreso_ratio_error_reportado = False
        # Modo ciego: id de pista para la cual se ocultan los metadatos
        # visibles. 0 = sin modo ciego. Pertenece al ModeloReproductor (no al
        # backend) porque es estrictamente de presentacion: el audio y la
        # cola se manejan igual; solo cambia lo que renderiza la UI.
        self._blind_pista_id: int = 0
        cola_inicial = self._rep.obtener_cola()
        self._duracion_cola_seg = self._calcular_duracion_cola(cola_inicial)
        self._cola.set_datos(cola_inicial)

        # Restauración de sesión: si el backend trae una posición pendiente
        # (la pista que sonaba al cerrar), reflejarla en la barra de progreso
        # ANTES del primer play. Así el usuario ve "dónde iba" (tiempo + pista)
        # al reabrir; el seek real lo consume el backend en el primer play.
        try:
            seg_pendiente = float(getattr(self._rep, "reanudar_seg_pendiente", 0.0) or 0.0)
            idx_restaurado = int(self._rep.indice_cola)
            if seg_pendiente > 0.0 and 0 <= idx_restaurado < len(cola_inicial):
                self._pos_seg = seg_pendiente
                self._dur_seg = float(cola_inicial[idx_restaurado].get("duracion_seg") or 0.0)
        except Exception as exc:
            _log.debug("No se pudo reflejar la posición restaurada en la barra: %s", exc)

        # Conectar callbacks del reproductor
        self.colaBackendCambiada.connect(self._actualizar_lista_cola)
        self._rep.on_estado(self._al_cambiar_estado)
        self._rep.on_progreso(self._al_progreso)
        self._rep.on_cola(self._al_cambiar_cola_backend)
        self._rep.on_aviso(self._al_aviso_reproductor)
        self._rep.on_modo_dj(self._al_cambiar_modo_dj)
        self.destroyed.connect(lambda *_: self._desregistrar_callbacks())

    # ------------------------------------------------------------------
    # PROPIEDADES
    # ------------------------------------------------------------------

    @Property(str, notify=estadoCambiado)
    def estado(self) -> str:
        return self._rep.estado.value

    @Property(bool, notify=estadoCambiado)
    def reproduciendo(self) -> bool:
        # Si el DJ tomó el audio, el global está suspendido: aunque su estado
        # lógico siga en REPRODUCIENDO (para recordar que sonaba), la barra no
        # debe mostrarlo como "sonando" → el icono pasa a play (continuar).
        if self._rep.modo_dj_activo:
            return False
        return self._rep.estado == EstadoReproductor.REPRODUCIENDO

    @Property(bool, notify=estadoCambiado)
    def pausado(self) -> bool:
        if self._rep.modo_dj_activo:
            return True
        return self._rep.estado == EstadoReproductor.PAUSADO

    @Property(str, notify=pista_activaCambiada)
    def titulo_activo(self) -> str:
        p = self._rep.pista_activa
        if not p:
            return ""
        if self._es_pista_ciega(p.id):
            return "???"
        return p.titulo

    @Property(str, notify=pista_activaCambiada)
    def artista_activo(self) -> str:
        p = self._rep.pista_activa
        if not p:
            return ""
        if self._es_pista_ciega(p.id):
            return "???"
        return p.artista

    @Property(str, notify=pista_activaCambiada)
    def album_activo(self) -> str:
        p = self._rep.pista_activa
        if not p:
            return ""
        if self._es_pista_ciega(p.id):
            return "???"
        return p.album

    @Property("QVariant", notify=pista_activaCambiada)
    def pista_activa(self) -> dict:
        snap = self._snapshot_pista_activa(self._rep.pista_activa)
        return self._censurar_snapshot_si_ciego(snap)

    @Property("QVariant", notify=pistaVisualCambiada)
    def pista_visual(self) -> dict:
        activa = self._snapshot_pista_activa(self._rep.pista_activa)
        if activa:
            return self._censurar_snapshot_si_ciego(activa)
        return self._snapshot_pista_para_continuar()

    @Property(int, notify=modoCiegoCambiado)
    def blind_pista_id(self) -> int:
        """Id de la pista que esta siendo ocultada por el Explorador Ciego.

        0 significa modo ciego desactivado. La UI puede consultar esto si
        necesita reaccionar al estado del juego (p. ej. para mostrar un
        badge en la barra inferior).
        """
        return int(self._blind_pista_id)

    def _es_pista_ciega(self, pista_id) -> bool:
        if not self._blind_pista_id:
            return False
        try:
            return int(pista_id) == int(self._blind_pista_id)
        except (TypeError, ValueError):
            return False

    def _censurar_snapshot_si_ciego(self, snap: dict) -> dict:
        """Aplica censura a un snapshot de pista si coincide con el id ciego.

        Censura tanto metadatos como la portada: sin esto, la barra inferior
        seguiria mostrando la portada real y reventaria el juego en modos
        portada/audio.
        """
        if not snap or not self._es_pista_ciega(snap.get("id")):
            return snap
        # Copia somera para no mutar el snapshot original cacheado por la UI.
        censurado = dict(snap)
        censurado["titulo"] = "???"
        censurado["artista_nombre"] = "???"
        censurado["album_titulo"] = "???"
        censurado["portada_ruta"] = ""
        censurado["portada_hd_ruta"] = ""
        return censurado

    @Property(str, notify=letraActivaCambiada)
    def letra_activa(self) -> str:
        return self._letra_activa

    @Property(str, notify=letraActivaCambiada)
    def letra_plain_activa(self) -> str:
        return self._letra_plain_activa

    @Property(str, notify=letraActivaCambiada)
    def letra_synced_activa(self) -> str:
        return self._letra_synced_activa

    @Property(bool, notify=letraActivaCambiada)
    def tiene_letra(self) -> bool:
        return bool((self._letra_activa or "").strip())

    @Property(float, notify=progresoCambiado)
    def posicion_seg(self) -> float:
        return self._float_no_negativo(self._pos_seg)

    @Property(float, notify=progresoCambiado)
    def duracion_seg(self) -> float:
        return self._float_no_negativo(self._duracion_actual_seg())

    @Property(float, notify=progresoCambiado)
    def progreso_ratio(self) -> float:
        try:
            duracion = self._float_no_negativo(self._duracion_actual_seg())
            posicion = self._float_no_negativo(self._pos_seg)
            if duracion <= 0:
                return 0.0
            return max(0.0, min(1.0, posicion / duracion))
        except Exception as exc:
            if not self._progreso_ratio_error_reportado:
                _log.warning("No se pudo leer progreso_ratio del reproductor: %s", exc)
                self._progreso_ratio_error_reportado = True
            return 0.0

    @Property(int, notify=volumenCambiado)
    def volumen(self) -> int:
        return self._rep.volumen

    @Property(str, notify=modoCambiado)
    def modo_repeticion(self) -> str:
        return self._rep.modo_repeticion

    @Property(bool, notify=modoCambiado)
    def aleatorio(self) -> bool:
        return self._rep.es_aleatorio

    # ── Ecualizador y opciones de audio (solo reproductor global) ──────────
    @Property(bool, notify=ecualizadorCambiado)
    def eq_activo(self) -> bool:
        return self._rep.eq_activo

    @Property(int, notify=ecualizadorCambiado)
    def eq_preset(self) -> int:
        """Índice del preset activo (0..17) o -1 si es 'Personalizado'."""
        return self._rep.eq_preset_idx

    @Property("QVariantList", notify=ecualizadorCambiado)
    def eq_bandas(self) -> list:
        return self._rep.eq_bandas

    @Property(float, notify=ecualizadorCambiado)
    def eq_preamp(self) -> float:
        return self._rep.eq_preamp

    @Property("QVariantList", constant=True)
    def eq_presets_nombres(self) -> list:
        # Nombres de presentación en español para las pastillas de preajuste.
        # El índice (0..17) sigue siendo el canónico que consume el backend.
        return list(EQ_PRESET_NOMBRES_ES)

    @Property("QVariantList", constant=True)
    def eq_bandas_hz(self) -> list:
        return list(EQ_BANDAS_HZ)

    @Property(float, constant=True)
    def eq_amp_min(self) -> float:
        return EQ_AMP_MIN

    @Property(float, constant=True)
    def eq_amp_max(self) -> float:
        return EQ_AMP_MAX

    @Property(float, constant=True)
    def eq_preamp_min(self) -> float:
        return EQ_PREAMP_MIN

    @Property(float, constant=True)
    def eq_preamp_max(self) -> float:
        return EQ_PREAMP_MAX

    @Property(bool, notify=normalizarVolumenCambiado)
    def normalizar_volumen(self) -> bool:
        return self._rep.audio_normalizar

    @Property(str, notify=karaokeCambiado)
    def karaoke_estado(self) -> str:
        return self._datos_karaoke_actuales().get("estado", "no_procesada")

    @Property(bool, notify=karaokeCambiado)
    def karaoke_disponible(self) -> bool:
        datos = self._datos_karaoke_actuales()
        return datos.get("estado") == "lista" and bool(datos.get("ruta_instrumental"))

    @Property(bool, notify=karaokeCambiado)
    def karaoke_activo(self) -> bool:
        return self._karaoke_activo

    @Property(bool, notify=sorpresaActivaCambiada)
    def sorpresa_activa(self) -> bool:
        return self._sorpresa_activa_visible

    @Property(bool, notify=modoDjActivoCambiado)
    def modo_dj_activo(self) -> bool:
        """True cuando una sesion DJ Privado tiene el control de audio.

        La UI usa esto para reemplazar la barra de reproduccion tradicional
        por un overlay informativo. NO se debe usar para alterar logica
        funcional fuera de la UI.
        """
        return self._rep.modo_dj_activo

    @Property("QVariant", notify=lyricsMoodCambiado)
    def lyrics_mood(self) -> dict:
        return self._calcular_lyrics_mood(self._rep.pista_activa)

    @Property("QVariant", notify=lyricsMoodCambiado)
    def mood_visual(self) -> dict:
        return self._calcular_lyrics_mood(self._rep.pista_activa)

    @Property(QObject, notify=colaCambiada)
    def cola(self) -> ListaGenerica:
        return self._cola

    @Property(int, notify=colaCambiada)
    def indice_cola(self) -> int:
        return self._rep.indice_cola

    @Property(float, notify=colaCambiada)
    def duracion_cola_seg(self) -> float:
        return self._duracion_cola_seg

    def _calcular_duracion_cola(self, cola: list[dict]) -> float:
        total = 0.0
        for pista in cola:
            try:
                total += max(0.0, float(pista.get("duracion_seg") or 0.0))
            except (TypeError, ValueError):
                continue
        return total

    def _snapshot_pista_activa(self, pista) -> dict:
        if not pista:
            return {}
        detalle = svc_bib.obtener_pista(pista.id) if pista.id else None
        return {
            "id": pista.id,
            "titulo": pista.titulo,
            "artista_nombre": pista.artista,
            "album_titulo": pista.album,
            "ruta_archivo": pista.ruta_archivo,
            "duracion_seg": pista.duracion_seg,
            "track_number": pista.track_number,
            "portada_ruta": pista.portada_ruta or "",
            "portada_hd_ruta": pista.portada_hd_ruta or "",
            "karaoke_estado": (detalle.get("karaoke_estado") if detalle else pista.karaoke_estado) or "no_procesada",
            "karaoke_ruta_instrumental": (detalle.get("karaoke_ruta_instrumental") if detalle else pista.karaoke_ruta_instrumental) or "",
            "album_id": detalle.get("album_id") if detalle else None,
            "artista_id": detalle.get("artista_id") if detalle else None,
            "anio": detalle.get("anio") if detalle else None,
        }

    def _snapshot_pista_para_continuar(self) -> dict:
        cola = self._cola.snapshot()
        if not cola:
            return {}
        indice = self._rep.indice_cola
        if not (0 <= indice < len(cola)):
            indice = 0
        pista = cola[indice] or {}
        detalle = None
        try:
            pista_id = int(pista.get("id") or 0)
        except (TypeError, ValueError):
            pista_id = 0
        if pista_id:
            detalle = svc_bib.obtener_pista(pista_id)

        def valor(*claves, default=""):
            for clave in claves:
                contenido = pista.get(clave)
                if contenido not in (None, ""):
                    return contenido
            return default

        return {
            "id": pista_id or valor("id"),
            "titulo": valor("titulo", "nombre_archivo", default="Pista sin título"),
            "artista_nombre": valor("artista_nombre", "artista", default="Artista desconocido"),
            "album_titulo": valor("album_titulo", "album"),
            "ruta_archivo": valor("ruta_archivo"),
            "duracion_seg": valor("duracion_seg", default=0.0),
            "track_number": valor("track_number", default=None),
            "portada_ruta": valor("portada_ruta"),
            "portada_hd_ruta": valor("portada_hd_ruta"),
            "karaoke_estado": (detalle.get("karaoke_estado") if detalle else valor("karaoke_estado", default="no_procesada")) or "no_procesada",
            "karaoke_ruta_instrumental": (detalle.get("karaoke_ruta_instrumental") if detalle else valor("karaoke_ruta_instrumental")) or "",
            "album_id": detalle.get("album_id") if detalle else valor("album_id", default=None),
            "artista_id": detalle.get("artista_id") if detalle else valor("artista_id", default=None),
            "anio": detalle.get("anio") if detalle else valor("anio", default=None),
        }

    # ------------------------------------------------------------------
    # OWNERSHIP DJ
    # ------------------------------------------------------------------

    def set_ownership_dj(self, ownership) -> None:
        """Conecta el manager de ownership del DJ.

        Cuando el usuario pide reproducir algo desde el reproductor global
        mientras una sesión DJ está activa, queremos detener el DJ limpiamente
        antes de iniciar la nueva pista (evita audio doble). El manager
        encapsula la transición y avisa al ModeloDjPrivado por callback.
        """
        self._ownership_dj = ownership

    def _liberar_dj_si_activo(self) -> None:
        if self._ownership_dj is None:
            return
        try:
            self._ownership_dj.liberar()
        except Exception as exc:
            _log.debug("Liberación DJ fallida en cambio de pista: %s", exc)

    # ------------------------------------------------------------------
    # SLOTS DE CONTROL
    # ------------------------------------------------------------------

    @Slot("QVariant")
    def reproducir(self, datos_pista) -> None:
        if not isinstance(datos_pista, dict):
            return
        # Si el bloqueo del juego esta activo, solo permitimos reproducir
        # la pista del propio reto (mismo id). Cualquier intento externo
        # (cliquear otra pista en la barra) se ignora silenciosamente.
        if self._bloqueado_por_juego():
            try:
                if int(datos_pista.get("id") or 0) != int(self._blind_pista_id):
                    return
            except (TypeError, ValueError):
                return
        self._liberar_dj_si_activo()
        self._limpiar_sorpresa_activa()
        self._rep.reproducir_pista(datos_pista)

    def _bloqueado_por_juego(self) -> bool:
        """True cuando la pista activa esta marcada como reto ciego.

        Mientras este flag esta activo, los slots de control humano
        (pausar_reanudar, siguiente, anterior, buscar_posicion) NO actuan.
        El Explorador Ciego usa metodos `_forzado` para bypass interno.
        """
        if not self._blind_pista_id:
            return False
        pista = self._rep.pista_activa
        if pista is None:
            return False
        try:
            return int(pista.id) == int(self._blind_pista_id)
        except (TypeError, ValueError):
            return False

    @Slot()
    def pausar_reanudar(self) -> None:
        # Si el global está suspendido porque hay una sesión DJ activa, el
        # usuario quiere recuperar control del audio normal. Liberar el DJ
        # primero evita que ambos suenen a la vez.
        if self._bloqueado_por_juego():
            return
        self._liberar_dj_si_activo()
        self._rep.pausar_reanudar()

    def pausar_reanudar_forzado(self, reanudar: bool = True) -> None:
        """Bypass del bloqueo de juego. Solo para uso interno del Explorador
        Ciego: necesita reanudar/pausar la pista pese al lock.

        `reanudar=True`: si esta pausada, reanudar. Si esta reproduciendo, no hacer nada.
        `reanudar=False`: si esta reproduciendo, pausar.
        """
        reproduciendo = self._rep.estado == EstadoReproductor.REPRODUCIENDO
        if reanudar and not reproduciendo:
            self._rep.pausar_reanudar()
        elif not reanudar and reproduciendo:
            self._rep.pausar_reanudar()

    @Slot()
    def detener_forzado(self) -> None:
        """Bypass del bloqueo: el Explorador Ciego pide detener Y limpiar
        completamente el estado del reproductor cuando el usuario salta.

        También se invoca desde `Principal.qml.onClosing` para cortar el
        audio antes del teardown — sin esto, si el usuario cerraba la app
        con el mini-reproductor visible, VLC seguía emitiendo unos
        segundos hasta que `Reproductor.cerrar()` completaba todo el
        flujo. Llamarlo en línea garantiza el corte inmediato.

        Hace tres cosas necesarias para no spoilear:
          1. Limpia pista activa (barra inferior queda vacia).
          2. Vacia la cola (el panel de cola no muestra residual).
          3. Resetea progreso, letra y karaoke.

        Sin (2), la cola guardaba la pista del reto anterior y, al limpiar
        el modo ciego, se veian sus metadatos reales en el panel de cola
        — spoileando la respuesta de algo que ya pasaste.
        """
        self._limpiar_sorpresa_activa()
        self._rep._detener_y_limpiar_pista_activa()  # noqa: SLF001 acceso controlado
        self._rep.limpiar_cola()
        self._pos_seg = 0.0
        self._dur_seg = 0.0
        self._letra_activa = ""
        self._letra_plain_activa = ""
        self._letra_synced_activa = ""
        self._karaoke_activo = False
        self.progresoCambiado.emit()
        self.estadoCambiado.emit()
        self.pista_activaCambiada.emit()
        self.pistaVisualCambiada.emit()
        self.letraActivaCambiada.emit()
        self.karaokeCambiado.emit()
        self.lyricsMoodCambiado.emit()

    @Slot()
    def detener(self) -> None:
        if self._bloqueado_por_juego():
            return
        self._limpiar_sorpresa_activa()
        self._rep.detener()
        self._pos_seg = 0.0
        self._dur_seg = 0.0
        self._letra_activa = ""
        self._letra_plain_activa = ""
        self._letra_synced_activa = ""
        self._karaoke_activo = False
        self.progresoCambiado.emit()
        self.estadoCambiado.emit()
        self.pista_activaCambiada.emit()
        self.pistaVisualCambiada.emit()
        self.letraActivaCambiada.emit()
        self.karaokeCambiado.emit()
        self.lyricsMoodCambiado.emit()

    @Slot()
    def siguiente(self) -> None:
        if self._bloqueado_por_juego():
            return
        self._limpiar_sorpresa_activa()
        self._rep.siguiente()
        self.colaCambiada.emit()

    @Slot()
    def anterior(self) -> None:
        if self._bloqueado_por_juego():
            return
        self._limpiar_sorpresa_activa()
        self._rep.anterior()
        self.colaCambiada.emit()

    @Slot(float)
    def buscar_posicion(self, posicion_seg: float) -> None:
        if self._bloqueado_por_juego():
            return
        duracion = self._duracion_actual_seg()
        posicion = self._float_no_negativo(posicion_seg)

        if duracion > 0:
            posicion = max(0.0, min(posicion, duracion))
            self._dur_seg = duracion
        else:
            posicion = 0.0
            self._dur_seg = 0.0

        self._rep.buscar_posicion(posicion)
        self._pos_seg = posicion
        self.progresoCambiado.emit()

    @Slot(int)
    def set_volumen(self, volumen: int) -> None:
        volumen_seguro = max(0, min(100, int(volumen)))
        self._rep.set_volumen(volumen_seguro)
        self.volumenCambiado.emit()

    @Slot(str)
    def set_modo_repeticion(self, modo: str) -> None:
        self._rep.set_modo_repeticion(modo)
        self.modoCambiado.emit()

    @Slot(bool)
    def set_aleatorio(self, activo: bool) -> None:
        self._rep.set_aleatorio(activo)
        self._actualizar_lista_cola()
        self.modoCambiado.emit()

    # ── Ecualizador y opciones de audio (solo reproductor global) ──────────
    @Slot(bool)
    def set_ecualizador_activo(self, activo: bool) -> None:
        self._rep.set_ecualizador_activo(bool(activo))
        self.ecualizadorCambiado.emit()

    @Slot(int)
    def aplicar_ecualizador_preset(self, idx: int) -> None:
        self._rep.aplicar_ecualizador_preset(int(idx))
        self.ecualizadorCambiado.emit()

    @Slot(int, float)
    def set_ecualizador_banda(self, idx: int, db: float) -> None:
        self._rep.set_ecualizador_banda(int(idx), float(db))
        self.ecualizadorCambiado.emit()

    @Slot(float)
    def set_ecualizador_preamp(self, db: float) -> None:
        self._rep.set_ecualizador_preamp(float(db))
        self.ecualizadorCambiado.emit()

    @Slot(bool)
    def set_normalizar_volumen(self, activo: bool) -> None:
        self._rep.set_normalizar_volumen(bool(activo))
        self.normalizarVolumenCambiado.emit()

    def _valor_qml_a_python(self, valor):
        if isinstance(valor, QJSValue):
            return valor.toVariant()
        return valor

    @Slot("QVariant")
    @Slot("QVariant", int)
    def reproducir_cola_desde_pistas(self, datos_pistas, desde_indice: int = 0) -> None:
        """Recibe una lista de dicts de pistas y empieza la reproduccion."""
        datos_pistas = self._valor_qml_a_python(datos_pistas)
        if isinstance(datos_pistas, list):
            self._liberar_dj_si_activo()
            self._limpiar_sorpresa_activa()
            self._rep.reproducir_cola(datos_pistas, desde_indice=desde_indice)
            self._actualizar_lista_cola()

    @Slot("QVariant")
    def agregar_a_cola(self, datos_pista) -> None:
        datos_pista = self._valor_qml_a_python(datos_pista)
        if isinstance(datos_pista, dict):
            self._rep.agregar_a_cola(datos_pista)
            self._actualizar_lista_cola()

    @Slot("QVariant")
    def agregar_varias_a_cola(self, datos_pistas) -> None:
        datos_pistas = self._valor_qml_a_python(datos_pistas)
        if isinstance(datos_pistas, list):
            self._rep.agregar_varias_a_cola(datos_pistas)
            self._actualizar_lista_cola()

    @Slot()
    def limpiar_cola(self) -> None:
        self._rep.limpiar_cola()
        self._actualizar_lista_cola()

    @Slot()
    def vaciar_cola_mantener_actual(self) -> None:
        self._rep.vaciar_cola_mantener_actual()
        self._actualizar_lista_cola()

    @Slot(int)
    def quitar_de_cola(self, indice: int) -> None:
        self._rep.quitar_de_cola(indice)
        self._actualizar_lista_cola()

    @Slot(int, int)
    def mover_en_cola(self, desde: int, hasta: int) -> None:
        self._rep.mover_en_cola(desde, hasta)
        self._actualizar_lista_cola()

    @Slot(result=bool)
    def alternar_karaoke(self) -> bool:
        """Alterna entre la mezcla original y el instrumental SIN reiniciar la pista.

        Preserva: pista_id logico, letra sincronizada/plain, timeline, estado
        de reproductor (reproduciendo/pausado), overlay de cola. La fuente de
        audio se cambia in-place en VLC; lyrics y metadata permanecen porque
        la pista logica no cambia.
        """
        pista_activa_obj = self._rep.pista_activa
        if not pista_activa_obj:
            return False

        # Comprobacion de elegibilidad: la DB es la fuente de verdad
        # (refleja el estado mas reciente tras procesamiento o reset).
        datos = self._datos_karaoke_actuales()
        if datos.get("estado") != "lista":
            return False
        ruta_instrumental = datos.get("ruta_instrumental", "")
        if not ruta_instrumental or not Path(ruta_instrumental).expanduser().exists():
            return False

        # Si la pista activa aun no tiene metadata karaoke (raro, por refresco
        # asincrono), la inyectamos en memoria antes del swap.
        if not getattr(pista_activa_obj, "karaoke_ruta_instrumental", None):
            pista_activa_obj.karaoke_estado = "lista"
            pista_activa_obj.karaoke_ruta_instrumental = ruta_instrumental

        usar_instrumental = not self._karaoke_activo
        ok = self._rep.alternar_fuente_audio(usar_instrumental)
        if not ok:
            return False

        self._karaoke_activo = bool(usar_instrumental)
        self.karaokeCambiado.emit()
        return True

    @Slot()
    def refrescar_karaoke_pista_activa(self) -> None:
        """Re-lee el estado karaoke de la pista activa desde la DB sin reiniciar.

        Llamado por la VistaKaraoke cuando alguna accion cambia el estado de
        una pista en DB (resetear, reintentar, marcar no_aplica). Mantiene
        sincronizada la pista activa del reproductor con la verdad de DB.

        Si el karaoke estaba activo y la pista ya no es elegible (resetear,
        reproceso pendiente, etc.) volvemos a la fuente original
        automaticamente — sin reiniciar la pista logica.
        """
        pista = self._rep.pista_activa
        if not pista or not pista.id:
            self.karaokeCambiado.emit()
            return
        try:
            fila = svc_bib.pista_karaoke_por_id(pista.id)
            if fila:
                nuevo_estado = fila.get("karaoke_estado", "no_procesada")
                nueva_ruta   = fila.get("karaoke_ruta_instrumental") or ""
                pista.karaoke_estado            = nuevo_estado
                pista.karaoke_ruta_instrumental = nueva_ruta or None
                if self._karaoke_activo and nuevo_estado != "lista":
                    # El instrumental ya no es elegible: volver a la fuente
                    # original sin recrear la pista logica.
                    self._rep.alternar_fuente_audio(False)
                    self._karaoke_activo = False
        except Exception as exc:
            _log.warning("refrescar_karaoke_pista_activa: %s", exc)
        self.karaokeCambiado.emit()

    @Slot(int, result=bool)
    def reproducir_indice_cola(self, indice: int) -> bool:
        if self._bloqueado_por_juego():
            return False
        self._liberar_dj_si_activo()
        exito = self._rep.reproducir_indice_cola(indice)
        if exito:
            self._limpiar_sorpresa_activa()
            self._actualizar_lista_cola()
        return exito

    @Slot(int, result=bool)
    def reproducir_desde_cola(self, indice: int) -> bool:
        return self.reproducir_indice_cola(indice)

    @Slot(result=bool)
    def sorprenderme(self) -> bool:
        """Selecciona una pista sugerida y la reproduce inmediatamente."""
        candidatas = svc_bib.listar_pistas(orden="reciente", limite=3000)
        if not candidatas:
            return False

        actual = self._rep.pista_activa
        actual_id = self._id_pista_sugerencia(actual)
        actual_clave = self._clave_pista_sugerencia(actual)
        artista_actual = self._clave_sugerencia(actual.artista if actual else "")
        album_actual = self._clave_sugerencia(actual.album if actual else "")
        if artista_actual:
            self._recordar_reciente(self._sugerencias_recientes_artistas, artista_actual, 32)
        if album_actual:
            self._recordar_reciente(self._sugerencias_recientes_albums, album_actual, 48)

        elegibles = []
        for pista in candidatas:
            if not isinstance(pista, dict):
                continue
            pista_id = self._id_pista_sugerencia(pista)
            pista_clave = self._clave_pista_sugerencia(pista)
            if not pista_clave:
                continue
            if pista_clave == actual_clave or (pista_id > 0 and pista_id == actual_id):
                continue
            ruta = str(pista.get("ruta_archivo") or "").strip()
            if not ruta:
                continue
            if not Path(ruta).expanduser().exists():
                continue

            elegibles.append({
                "pista": pista,
                "id": pista_id,
                "clave": pista_clave,
                "artista": self._clave_sugerencia(
                    pista.get("artista_id"),
                    pista.get("artista_nombre"),
                    pista.get("artista"),
                ),
                "album": self._clave_sugerencia(
                    pista.get("album_id"),
                    pista.get("album_titulo"),
                    pista.get("album"),
                    pista.get("mb_release_id"),
                ),
            })

        if not elegibles:
            return False

        limite_recientes = self._limite_sugerencias_recientes(len(elegibles))
        if actual_clave:
            self._recordar_reciente(
                self._sugerencias_recientes,
                actual_clave,
                limite_recientes,
            )

        recientes_claves = set(self._sugerencias_recientes)
        recientes_artistas = set(self._sugerencias_recientes_artistas)
        recientes_albums = set(self._sugerencias_recientes_albums)

        seleccionables = elegibles
        seleccionables = self._filtrar_con_fallback(
            seleccionables,
            lambda item: item["clave"] not in recientes_claves,
        )
        seleccionables = self._filtrar_con_fallback(
            seleccionables,
            lambda item: not artista_actual or item["artista"] != artista_actual,
        )
        seleccionables = self._filtrar_con_fallback(
            seleccionables,
            lambda item: not album_actual or item["album"] != album_actual,
        )
        seleccionables = self._filtrar_con_fallback(
            seleccionables,
            lambda item: not item["artista"] or item["artista"] not in recientes_artistas,
        )
        seleccionables = self._filtrar_con_fallback(
            seleccionables,
            lambda item: not item["album"] or item["album"] not in recientes_albums,
        )

        # Elección aleatoria PONDERADA entre los mejores candidatos en vez de
        # tomar siempre el máximo. Tomar el máximo era determinista: con la
        # misma biblioteca/estado siempre arrancaba en la misma pista y repetía
        # la misma secuencia (comportamiento de "cola fija"). Ponderar por el
        # score conserva gustos/reproducciones/diversidad, pero cada pulsación
        # parte de un punto distinto. El ranking ya penaliza artista/álbum
        # recientes, así que no entra en bucles del mismo artista/álbum.
        puntuados = sorted(
            seleccionables,
            key=lambda item: self._score_sugerencia(item, recientes_claves, recientes_artistas, recientes_albums),
            reverse=True,
        )
        top = puntuados[:max(10, min(40, len(puntuados)))]
        pesos = [len(top) - i for i in range(len(top))]
        sugerida_item = random.choices(top, weights=pesos, k=1)[0]
        sugerida = sugerida_item["pista"]

        sugerida_id = self._id_pista_sugerencia(sugerida)
        self._recordar_sugerencia(sugerida_item, limite_recientes)

        self._sorpresa_clave_activa = sugerida_item["clave"]
        self._rep.reproducir_pista(sugerida)
        activa = self._rep.pista_activa
        if not activa:
            self._limpiar_sorpresa_activa()
            return False
        exito = int(activa.id) == sugerida_id or str(activa.ruta_archivo) == str(sugerida.get("ruta_archivo") or "")
        if exito:
            self._sincronizar_sorpresa_activa(activa)
        else:
            self._limpiar_sorpresa_activa()
        return exito

    @Slot()
    def reenviar_avisos_retenidos(self) -> None:
        for aviso in list(self._avisos_reproductor_retenidos):
            self.avisoReproductor.emit(dict(aviso))

    # ------------------------------------------------------------------
    # MODO CIEGO (Explorador Ciego)
    # ------------------------------------------------------------------
    #
    # El Explorador Ciego puede pedir que las propiedades visibles de la
    # pista activa muestren "???" para no spoilear la respuesta cuando se
    # reproduce un fragmento desde la barra de reproduccion. Esto NO afecta
    # al backend ni a la cola; al revelar/finalizar el reto, la UI llama a
    # `limpiar_modo_ciego()` y los metadatos vuelven a verse.

    @Slot(int)
    def set_modo_ciego(self, pista_id: int) -> None:
        try:
            nuevo = int(pista_id)
        except (TypeError, ValueError):
            return
        if nuevo == self._blind_pista_id:
            return
        self._blind_pista_id = nuevo
        # Emitimos seniales de propiedades visibles para forzar refresco
        # inmediato en la barra inferior, panel de cola y cualquier
        # consumidor. La cola se recalcula con censura por id.
        self.modoCiegoCambiado.emit()
        self.pista_activaCambiada.emit()
        self.pistaVisualCambiada.emit()
        self._actualizar_lista_cola()

    @Slot()
    def limpiar_modo_ciego(self) -> None:
        if self._blind_pista_id == 0:
            return
        self._blind_pista_id = 0
        self.modoCiegoCambiado.emit()
        self.pista_activaCambiada.emit()
        self.pistaVisualCambiada.emit()
        # Refrescar la cola: la pista que estaba censurada vuelve a su
        # apariencia normal.
        self._actualizar_lista_cola()

    # ------------------------------------------------------------------
    # FORMATO DE TIEMPO
    # ------------------------------------------------------------------

    @Slot(float, result=str)
    def formatear_tiempo(self, segundos: float) -> str:
        """Convierte segundos a 'm:ss' para mostrar en QML."""
        if segundos is None:
            return "0:00"
        try:
            valor = float(segundos)
        except (TypeError, ValueError):
            return "0:00"
        if valor <= 0:
            return "0:00"
        total = int(valor + 0.5)
        minutos = total // 60
        segs    = total % 60
        return f"{minutos}:{segs:02d}"

    @Slot(float, result=str)
    def formatear_duracion_larga(self, segundos: float) -> str:
        """Convierte segundos a una etiqueta larga compacta: '1h 2m 5s'."""
        try:
            total = int(max(0.0, float(segundos or 0.0)))
        except (TypeError, ValueError):
            total = 0

        horas = total // 3600
        minutos = (total % 3600) // 60
        segs = total % 60

        if horas > 0:
            return f"{horas}h {minutos}m {segs}s"
        if minutos > 0:
            return f"{minutos}m {segs}s"
        return f"{segs}s"

    # ------------------------------------------------------------------
    # CALLBACKS INTERNOS
    # ------------------------------------------------------------------

    def _al_cambiar_estado(self, estado, pista) -> None:
        lyrics = self._normalizar_lyrics_para_ui(self._rep.obtener_lyrics_pista_activa())
        self._letra_synced_activa = lyrics["synced_lyrics"]
        self._letra_plain_activa = lyrics["plain_lyrics"]
        self._letra_activa = self._letra_synced_activa or self._letra_plain_activa

        progreso_cambio = False
        pista_id = int(pista.id) if pista else None
        pista_cambio = pista_id != self._pista_progreso_id
        if pista_cambio:
            self._pista_progreso_id = pista_id
            self._pos_seg = 0.0
            self._dur_seg = self._duracion_de_pista(pista)
            progreso_cambio = True
        elif pista and self._dur_seg <= 0:
            duracion = self._duracion_de_pista(pista)
            if duracion > 0:
                self._dur_seg = duracion
                progreso_cambio = True

        self.estadoCambiado.emit()
        self.pista_activaCambiada.emit()
        self.pistaVisualCambiada.emit()
        self.letraActivaCambiada.emit()
        self.colaCambiada.emit()
        self._sincronizar_sorpresa_activa(pista)
        self._sincronizar_karaoke_desde_pista(pista)
        self.karaokeCambiado.emit()
        if pista_cambio:
            self.lyricsMoodCambiado.emit()
        if progreso_cambio:
            self.progresoCambiado.emit()

    def _al_progreso(self, pos_seg: float, dur_seg: float) -> None:
        pista = self._rep.pista_activa
        duracion_pista = self._duracion_de_pista(pista)
        try:
            duracion_reportada = max(0.0, float(dur_seg or 0.0))
        except (TypeError, ValueError):
            duracion_reportada = 0.0
        duracion = duracion_pista if duracion_pista > 0 else duracion_reportada

        try:
            posicion = max(0.0, float(pos_seg or 0.0))
        except (TypeError, ValueError):
            posicion = 0.0
        if duracion > 0:
            posicion = min(posicion, duracion)

        self._pos_seg = posicion
        self._dur_seg = duracion
        self._pista_progreso_id = int(pista.id) if pista else None
        try:
            self.progresoCambiado.emit()
        except RuntimeError:
            self._desregistrar_callbacks()

    def _duracion_de_pista(self, pista) -> float:
        if not pista:
            return 0.0
        try:
            return self._float_no_negativo(pista.duracion_seg)
        except Exception:
            return 0.0

    def _duracion_actual_seg(self) -> float:
        try:
            pista = self._rep.pista_activa
            duracion_pista = self._duracion_de_pista(pista) if pista else 0.0
            if duracion_pista > 0:
                return duracion_pista
            return self._float_no_negativo(self._dur_seg)
        except Exception as exc:
            if not self._progreso_ratio_error_reportado:
                _log.warning("No se pudo leer duracion del reproductor: %s", exc)
                self._progreso_ratio_error_reportado = True
            return 0.0

    @staticmethod
    def _float_no_negativo(valor) -> float:
        try:
            numero = float(valor)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        if not math.isfinite(numero):
            return 0.0
        return max(0.0, numero)

    @Slot()
    def _actualizar_lista_cola(self) -> None:
        cola = self._rep.obtener_cola()
        self._duracion_cola_seg = self._calcular_duracion_cola(cola)
        # Aplicar censura a items cuya id coincida con la pista ciega:
        # cuando el Explorador Ciego mete una pista a la cola, el panel
        # de cola seguiria mostrando titulo/artista/album/portada reales,
        # spoileando la respuesta. Censuramos en el momento de exponer
        # al QML para que el spoiler no se filtre por ese camino.
        if self._blind_pista_id:
            cola_censurada = []
            for item in cola:
                try:
                    pid_item = int(item.get("id") or 0)
                except (TypeError, ValueError):
                    pid_item = 0
                if pid_item == int(self._blind_pista_id):
                    copia = dict(item)
                    copia["titulo"] = "???"
                    copia["artista_nombre"] = "???"
                    copia["album_titulo"] = "???"
                    copia["portada_ruta"] = ""
                    copia["portada_hd_ruta"] = ""
                    copia["portada_display_ruta"] = ""
                    copia["portada_thumb_ruta"] = ""
                    copia["album_portada_ruta"] = ""
                    cola_censurada.append(copia)
                else:
                    cola_censurada.append(item)
            cola = cola_censurada
        self._cola.set_datos(cola)
        self.pistaVisualCambiada.emit()
        self.colaCambiada.emit()

    def _al_cambiar_cola_backend(self) -> None:
        self.colaBackendCambiada.emit()

    def _al_aviso_reproductor(self, aviso: dict) -> None:
        aviso_seguro = dict(aviso or {})
        if (
            aviso_seguro.get("nivel") == "critical"
            and aviso_seguro not in self._avisos_reproductor_retenidos
        ):
            self._avisos_reproductor_retenidos.append(aviso_seguro)
        self.avisoReproductor.emit(aviso_seguro)

    def _al_cambiar_modo_dj(self, activo: bool) -> None:
        """Re-emite el cambio de modo DJ a QML. La UI usa esta senal para
        mostrar el overlay "DJ Privado activo" en la barra de reproduccion.

        Tambien re-emitimos `estadoCambiado` para que el icono play/pausa de la
        barra global se actualice de inmediato: cuando el DJ toma el audio, el
        global queda suspendido y debe mostrarse como "en pausa" (icono play),
        aunque su estado lógico interno siga siendo REPRODUCIENDO."""
        self.modoDjActivoCambiado.emit()
        self.estadoCambiado.emit()

    def _normalizar_lyrics_para_ui(self, lyrics: dict) -> dict[str, str]:
        """Devuelve letras seguras para QML, o vacio si el synced viene roto."""
        synced_raw = str((lyrics or {}).get("synced_lyrics") or "").strip()
        plain_raw = str((lyrics or {}).get("plain_lyrics") or "").strip()

        if synced_raw:
            synced = self._normalizar_synced_lyrics(synced_raw)
            if synced:
                return {"synced_lyrics": synced, "plain_lyrics": ""}
            return {"synced_lyrics": "", "plain_lyrics": ""}

        return {
            "synced_lyrics": "",
            "plain_lyrics": self._normalizar_plain_lyrics(plain_raw),
        }

    def _normalizar_synced_lyrics(self, letra: str) -> str:
        lineas_seguras: list[str] = []
        hubo_linea_con_tiempo = False

        for linea in str(letra or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            original = linea.strip()
            if not original:
                continue
            if self._LRC_METADATA_RE.match(original):
                continue

            marcas = list(self._LRC_TIMESTAMP_RE.finditer(original))
            if not marcas:
                return ""
            if original[:marcas[0].start()].strip():
                return ""

            for marca in marcas:
                try:
                    segundos = int(marca.group(2))
                except (TypeError, ValueError):
                    return ""
                if segundos >= 60:
                    return ""

            texto = self._limpiar_texto_lyric(self._LRC_TIMESTAMP_RE.sub("", original))
            if not texto:
                continue

            lineas_seguras.append("".join(m.group(0) for m in marcas) + texto)
            hubo_linea_con_tiempo = True

        if not hubo_linea_con_tiempo:
            return ""
        return "\n".join(lineas_seguras)

    def _normalizar_plain_lyrics(self, letra: str) -> str:
        lineas_seguras: list[str] = []
        for linea in str(letra or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            limpia = linea.strip()
            if not limpia or self._LRC_METADATA_RE.match(limpia):
                continue
            limpia = self._LRC_TIMESTAMP_RE.sub("", limpia)
            limpia = self._limpiar_texto_lyric(limpia)
            if limpia:
                lineas_seguras.append(limpia)
        if self._plain_lyrics_parece_documento(lineas_seguras):
            return ""
        return "\n".join(lineas_seguras)

    def _limpiar_texto_lyric(self, texto: str) -> str:
        limpio = str(texto or "").strip()
        if not limpio:
            return ""
        corte = limpio.find("^")
        if corte >= 0:
            limpio = limpio[:corte].strip()
        return " ".join(limpio.split())

    def _plain_lyrics_parece_documento(self, lineas: list[str]) -> bool:
        if not lineas:
            return False

        total = sum(len(linea) for linea in lineas)
        if total <= 0:
            return True

        max_linea = max(len(linea) for linea in lineas)
        promedio = total / max(1, len(lineas))
        palabras = sum(len(linea.split()) for linea in lineas)
        puntuacion = sum(1 for linea in lineas for char in linea if char in ".,;:!?")
        densidad_puntuacion = puntuacion / total

        if max_linea > 180:
            return True
        if len(lineas) <= 2 and total > 160:
            return True
        if len(lineas) < 4 and palabras > 55:
            return True
        if promedio > 110:
            return True
        return densidad_puntuacion > 0.12 and promedio > 70

    def _limpiar_sorpresa_activa(self) -> None:
        if not self._sorpresa_clave_activa and not self._sorpresa_activa_visible:
            return
        self._sorpresa_clave_activa = ""
        if self._sorpresa_activa_visible:
            self._sorpresa_activa_visible = False
            self.sorpresaActivaCambiada.emit()

    def _sincronizar_sorpresa_activa(self, pista) -> None:
        estado_permite_activa = self._rep.estado not in {
            EstadoReproductor.DETENIDO,
            EstadoReproductor.FINALIZADA,
            EstadoReproductor.ERROR,
        }
        clave_actual = self._clave_pista_sugerencia(pista)
        visible = bool(self._sorpresa_clave_activa and estado_permite_activa and clave_actual == self._sorpresa_clave_activa)

        if self._sorpresa_clave_activa and not visible:
            self._sorpresa_clave_activa = ""

        if visible != self._sorpresa_activa_visible:
            self._sorpresa_activa_visible = visible
            self.sorpresaActivaCambiada.emit()

    def _clave_sugerencia(self, *valores) -> str:
        for valor in valores:
            texto = str(valor or "").strip().lower()
            if texto:
                return texto
        return ""

    def _id_pista_sugerencia(self, pista) -> int:
        if not pista:
            return -1
        valor = pista.get("id") if isinstance(pista, dict) else getattr(pista, "id", -1)
        try:
            return int(valor or -1)
        except (TypeError, ValueError):
            return -1

    def _clave_pista_sugerencia(self, pista) -> str:
        if not pista:
            return ""

        pista_id = self._id_pista_sugerencia(pista)
        if pista_id > 0:
            return f"id:{pista_id}"

        ruta = pista.get("ruta_archivo") if isinstance(pista, dict) else getattr(pista, "ruta_archivo", "")
        ruta_texto = str(ruta or "").strip()
        if not ruta_texto:
            return ""
        try:
            ruta_texto = str(Path(ruta_texto).expanduser().resolve(strict=False))
        except (OSError, RuntimeError):
            ruta_texto = ruta_texto.lower()
        return f"ruta:{ruta_texto}"

    def _limite_sugerencias_recientes(self, total_elegibles: int) -> int:
        try:
            total = max(0, int(total_elegibles))
        except (TypeError, ValueError):
            total = 0
        return min(240, max(80, total // 4))

    def _filtrar_con_fallback(self, items: list[dict], predicado) -> list[dict]:
        filtrados = [item for item in items if predicado(item)]
        return filtrados or items

    def _score_sugerencia(
        self,
        item: dict,
        recientes_claves: set[str],
        recientes_artistas: set[str],
        recientes_albums: set[str],
    ) -> float:
        pista = item["pista"]
        score = 0.0
        if item["clave"] in recientes_claves:
            score -= 120.0
        if item["artista"] and item["artista"] in recientes_artistas:
            score -= 14.0
        if item["album"] and item["album"] in recientes_albums:
            score -= 10.0

        score += min(3.0, float(pista.get("veces_reproducida") or 0) * 0.12)
        score += 1.2 if int(pista.get("favorita") or 0) == 1 else 0.0
        score += min(1.0, max(0.0, float(pista.get("bitrate_kbps") or 0) - 160.0) / 128.0)

        try:
            duracion = max(0.0, float(pista.get("duracion_seg") or 0.0))
        except (TypeError, ValueError):
            duracion = 0.0
        if 45 <= duracion <= 540:
            score += 0.4
        elif 0 < duracion < 30:
            score -= 1.0
        elif duracion > 900:
            score -= 2.0

        if str(pista.get("ultimo_acceso") or "").strip():
            score -= 2.5
        score += random.random() * 0.001
        return score

    def _recordar_reciente(self, contenedor: list, clave, limite: int) -> None:
        if not clave:
            return
        contenedor[:] = [item for item in contenedor if item != clave]
        contenedor.append(clave)
        if len(contenedor) > limite:
            del contenedor[:-limite]

    def _recordar_sugerencia(self, sugerida: dict, limite_pistas: int) -> None:
        self._recordar_reciente(self._sugerencias_recientes, sugerida.get("clave"), limite_pistas)
        self._recordar_reciente(self._sugerencias_recientes_artistas, sugerida.get("artista"), 32)
        self._recordar_reciente(self._sugerencias_recientes_albums, sugerida.get("album"), 48)

    def _calcular_lyrics_mood(self, pista) -> dict[str, float]:
        clave = self._clave_pista_sugerencia(pista) or "fallback:sin-pista"
        if clave in self._lyrics_mood_cache:
            return dict(self._lyrics_mood_cache[clave])

        portada = str(getattr(pista, "portada_ruta", "") or "").strip() if pista else ""
        mood = self._mood_desde_portada(portada) if portada else None
        if mood is None:
            mood = self._mood_fallback(pista)

        self._lyrics_mood_cache[clave] = mood
        if len(self._lyrics_mood_cache) > 128:
            primera = next(iter(self._lyrics_mood_cache))
            self._lyrics_mood_cache.pop(primera, None)
        return dict(mood)

    def _mood_desde_portada(self, ruta_portada: str) -> Optional[dict[str, float]]:
        ruta = Path(ruta_portada).expanduser()
        if not ruta.exists() or not ruta.is_file():
            return None

        imagen = QImage(str(ruta))
        if imagen.isNull():
            return None

        if imagen.width() > 48 or imagen.height() > 48:
            imagen = imagen.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        suma_sin = 0.0
        suma_cos = 0.0
        suma_sat = 0.0
        suma_luz = 0.0
        peso_total = 0.0

        for y in range(imagen.height()):
            for x in range(imagen.width()):
                color = imagen.pixelColor(x, y)
                if color.alphaF() < 0.55:
                    continue

                h, s, l, _ = color.getHslF()
                if h < 0 or s < 0.14 or l < 0.08 or l > 0.92:
                    continue

                peso = max(0.08, s) * (0.45 + min(0.55, l))
                angulo = h * math.tau
                suma_sin += math.sin(angulo) * peso
                suma_cos += math.cos(angulo) * peso
                suma_sat += s * peso
                suma_luz += l * peso
                peso_total += peso

        if peso_total <= 0:
            return None

        hue = (math.atan2(suma_sin, suma_cos) / math.tau) % 1.0
        saturacion = self._clamp((suma_sat / peso_total) * 0.86, 0.34, 0.70)
        luminosidad = self._clamp(0.16 + ((suma_luz / peso_total) * 0.16), 0.16, 0.31)
        return {"h": hue, "s": saturacion, "l": luminosidad}

    def _mood_fallback(self, pista) -> dict[str, float]:
        semilla = self._clave_pista_sugerencia(pista)
        if not semilla and pista:
            semilla = "|".join(
                str(getattr(pista, nombre, "") or "")
                for nombre in ("titulo", "artista", "album", "ruta_archivo")
            )
        if not semilla:
            semilla = "nb-sound-lyrics"

        hash_valor = 2166136261
        for caracter in semilla:
            hash_valor ^= ord(caracter)
            hash_valor = (hash_valor * 16777619) & 0xFFFFFFFF

        hue = (hash_valor % 360) / 360.0
        saturacion = 0.42 + (((hash_valor >> 8) % 20) / 100.0)
        luminosidad = 0.18 + (((hash_valor >> 16) % 9) / 100.0)
        return {
            "h": hue,
            "s": self._clamp(saturacion, 0.34, 0.68),
            "l": self._clamp(luminosidad, 0.16, 0.30),
        }

    def _clamp(self, valor: float, minimo: float, maximo: float) -> float:
        return max(minimo, min(maximo, float(valor)))

    def _datos_karaoke_actuales(self) -> dict:
        pista = self._rep.pista_activa
        if not pista:
            return {"estado": "no_procesada", "ruta_instrumental": "", "ruta_original": "", "detalle": {}}

        detalle = svc_bib.obtener_pista(pista.id) if pista.id else None
        estado = str(
            (detalle.get("karaoke_estado") if detalle else pista.karaoke_estado)
            or "no_procesada"
        ).strip()
        ruta_instrumental = str(
            (detalle.get("karaoke_ruta_instrumental") if detalle else pista.karaoke_ruta_instrumental)
            or ""
        ).strip()
        if ruta_instrumental and not Path(ruta_instrumental).expanduser().exists():
            ruta_instrumental = ""

        ruta_original = str((detalle.get("ruta_archivo") if detalle else "") or pista.ruta_archivo or "").strip()
        return {
            "estado": estado,
            "ruta_instrumental": ruta_instrumental,
            "ruta_original": ruta_original,
            "detalle": detalle or {},
        }

    def _sincronizar_karaoke_desde_pista(self, pista) -> None:
        """Mantiene el flag `_karaoke_activo` alineado con la fuente real del reproductor.

        Cada nueva pista empieza con karaoke desactivado (la fuente VLC es
        siempre la original al cargar una pista). El flag se actualiza cuando
        `alternar_karaoke()` hace el swap. Esta funcion solo cierra el caso de
        que la pista nueva no traiga `ruta_audio_actual`.
        """
        if not pista:
            self._karaoke_activo = False
            return
        ruta_audio_actual = getattr(pista, "ruta_audio_actual", None)
        instr = getattr(pista, "karaoke_ruta_instrumental", None)
        if ruta_audio_actual and instr and str(ruta_audio_actual) == str(instr):
            self._karaoke_activo = True
        else:
            self._karaoke_activo = False

    @Slot()
    def recargar_cola(self) -> None:
        self._actualizar_lista_cola()

    def _desregistrar_callbacks(self) -> None:
        if not self._rep:
            return
        self._rep.off_estado(self._al_cambiar_estado)
        self._rep.off_progreso(self._al_progreso)
        self._rep.off_cola(self._al_cambiar_cola_backend)
        self._rep.off_aviso(self._al_aviso_reproductor)

    @Slot()
    def refrescar_estado_inicial(self) -> None:
        """Re-emite el estado restaurado para que la BARRA lo refleje una vez la
        UI ya está cargada.

        La sesión previa (cola + pista + tiempo) se restaura en la construcción
        del backend, ANTES de que QML evalúe sus bindings. En equipos donde la
        carga inicial tarda, conviene re-emitir las señales una vez la interfaz
        está lista para garantizar que la barra muestre lo persistido sin
        depender del orden exacto de evaluación de los bindings. Idempotente y
        barato: solo notifica, no toca audio ni estado.
        """
        try:
            self.colaCambiada.emit()
            self.pista_activaCambiada.emit()
            self.pistaVisualCambiada.emit()
            self.progresoCambiado.emit()
            self.estadoCambiado.emit()
            self.volumenCambiado.emit()
        except Exception as exc:
            _log.debug("refrescar_estado_inicial falló: %s", exc)

    @Slot()
    def preparar_cierre(self) -> None:
        """Corta el audio al cerrar la ventana preservando la sesión (#0).

        Se invoca desde ``Principal.qml.onClosing``. Reemplaza el uso de
        ``detener_forzado`` en esa ruta, que limpiaba la pista activa y vaciaba
        (y persistía vacía) la cola JUSTO antes de que ``cerrar`` guardara el
        estado — por eso la persistencia del reproductor global no se aplicaba
        aunque a nivel de servicio fuera correcta. Aquí solo se persiste el
        estado y se silencia VLC, dejando la última pista lista para reanudar.
        """
        rep = self._rep
        if rep is None:
            return
        try:
            rep.preparar_cierre()
        except Exception as exc:
            _log.debug("preparar_cierre reproductor fallo: %s", exc)

    def cerrar(self) -> None:
        """Cierra el backend de audio (VLC) antes del teardown de Qt.

        Sin esto, VLC sigue emitiendo audio aunque la ventana ya no exista
        y MediaPlayerEndReached puede dispararse durante el shutdown.
        """
        try:
            self._desregistrar_callbacks()
        except Exception as exc:
            _log.debug("desregistrar_callbacks reproductor fallo: %s", exc)
        rep = self._rep
        if rep is not None and hasattr(rep, "cerrar"):
            try:
                rep.cerrar()
            except Exception as exc:
                _log.warning("Reproductor.cerrar() fallo: %s", exc)

    def refrescar_letras_pista_activa(self) -> None:
        """Re-lee las letras de la pista activa después de invalidar cache.

        Se invoca desde la coordinación de `main_ui` cuando termina una
        importación: aunque enrichment haya escrito letras nuevas en el
        manifest, el cache interno del Reproductor puede conservar un
        valor vacío de una consulta previa. Aquí limpiamos cache y
        notificamos a la UI (vía el mismo callback que usa el cambio de
        estado) para que VistaLyrics actualice en vivo.
        """
        rep = self._rep
        if rep is None:
            return
        try:
            rep.invalidar_cache_letras()
        except Exception as exc:
            _log.debug("invalidar_cache_letras fallo: %s", exc)
        try:
            self._al_cambiar_estado(rep.estado, rep.pista_activa)
        except Exception as exc:
            _log.debug("refrescar letras tras invalidar fallo: %s", exc)


# =============================================================================
# MODELO DE BUSQUEDA
# =============================================================================

class ModeloBusqueda(QObject):
    """Busqueda universal en tiempo real con debounce."""

    resultadosCambiados = Signal()
    resultadosNaturalesCambiados = Signal()
    buscandoNaturalCambiado = Signal()
    buscando            = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pistas    = ListaGenerica(self)
        self._albums    = ListaGenerica(self)
        self._artistas  = ListaGenerica(self)
        self._favoritos = ListaGenerica(self)
        self._termino   = ""
        self._resultados_natural = ListaGenerica(self)
        self._secciones_natural = ListaGenerica(self)
        self._interpretacion_natural = ""
        self._mensaje_natural = ""
        self._estado_analisis_musical = "idle"
        self._hay_features = False
        self._hay_biblioteca = False
        self._total_pistas_biblioteca = 0
        self._porcentaje_features = 0.0
        self._buscando_natural = False
        self._error_natural = ""
        self._worker = None
        self._worker_natural = None
        self._workers_busqueda_obsoletos = []
        self._workers_natural_obsoletos = []
        self._request_seq = 0
        self._active_request_seq = 0
        self._request_seq_natural = 0
        self._active_request_seq_natural = 0

    @Property(str, notify=resultadosCambiados)
    def termino(self) -> str:
        return self._termino

    @Property(QObject, notify=resultadosCambiados)
    def pistas(self) -> ListaGenerica:
        return self._pistas

    @Property(QObject, notify=resultadosCambiados)
    def albums(self) -> ListaGenerica:
        return self._albums

    @Property(QObject, notify=resultadosCambiados)
    def artistas(self) -> ListaGenerica:
        return self._artistas

    @Property(QObject, notify=resultadosCambiados)
    def favoritos(self) -> ListaGenerica:
        return self._favoritos

    @Property(QObject, notify=resultadosNaturalesCambiados)
    def resultadosNatural(self) -> ListaGenerica:
        return self._resultados_natural

    @Property(QObject, notify=resultadosNaturalesCambiados)
    def seccionesNatural(self) -> ListaGenerica:
        return self._secciones_natural

    @Property(str, notify=resultadosNaturalesCambiados)
    def interpretacionNatural(self) -> str:
        return self._interpretacion_natural

    @Property(str, notify=resultadosNaturalesCambiados)
    def mensajeNatural(self) -> str:
        return self._mensaje_natural

    @Property(bool, notify=resultadosNaturalesCambiados)
    def hayFeaturesDisponibles(self) -> bool:
        return self._hay_features

    @Property(bool, notify=resultadosNaturalesCambiados)
    def hayBibliotecaMusical(self) -> bool:
        return self._hay_biblioteca

    @Property(int, notify=resultadosNaturalesCambiados)
    def totalPistasBiblioteca(self) -> int:
        return self._total_pistas_biblioteca

    @Property(float, notify=resultadosNaturalesCambiados)
    def porcentajeBibliotecaAnalizada(self) -> float:
        return self._porcentaje_features

    @Property(str, notify=resultadosNaturalesCambiados)
    def estadoAnalisisMusical(self) -> str:
        return self._estado_analisis_musical

    @Property(bool, notify=buscandoNaturalCambiado)
    def buscandoNatural(self) -> bool:
        return self._buscando_natural

    @Property(str, notify=buscandoNaturalCambiado)
    def errorNatural(self) -> str:
        return self._error_natural
    def _archivar_worker_busqueda(self, worker) -> None:
        try:
            worker.resultados.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            worker.finished.disconnect()
        except (RuntimeError, TypeError):
            pass

        worker.requestInterruption()
        self._workers_busqueda_obsoletos.append(worker)

        def _limpiar_worker_obsoleto(w=worker):
            try:
                self._workers_busqueda_obsoletos.remove(w)
            except ValueError:
                pass
            w.deleteLater()

        worker.finished.connect(_limpiar_worker_obsoleto)

    def _archivar_worker_natural(self, worker) -> None:
        try:
            worker.resultados.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            worker.error.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            worker.finished.disconnect()
        except (RuntimeError, TypeError):
            pass

        worker.requestInterruption()
        self._workers_natural_obsoletos.append(worker)

        def _limpiar_worker_obsoleto(w=worker):
            try:
                self._workers_natural_obsoletos.remove(w)
            except ValueError:
                pass
            w.deleteLater()

        worker.finished.connect(_limpiar_worker_obsoleto)

    def _al_recibir_resultados_naturales(self, payload: dict, request_id: int) -> None:
        if request_id != self._active_request_seq_natural:
            return

        st = dict(payload.get("estado") or {})
        out = dict(payload.get("salida") or {})

        self._aplicar_estado_natural(st)
        self._interpretacion_natural = ""

        warnings = out.get("warnings") or []
        if out.get("user_message"):
            self._mensaje_natural = str(out.get("user_message") or "")
        elif out.get("results"):
            self._mensaje_natural = ""
        elif not self._hay_biblioteca:
            self._mensaje_natural = "Tu biblioteca todavía está vacía."
        elif not self._hay_features:
            self._mensaje_natural = "Todavía no hay datos musicales suficientes para recomendar desde tu biblioteca."
        elif warnings:
            self._mensaje_natural = "No encontré una selección clara para esa intención musical."
        else:
            self._mensaje_natural = "No encontré una selección clara para esa intención musical."

        self._resultados_natural.set_datos(out.get("results", []))
        self._secciones_natural.set_datos(self._normalizar_secciones_naturales(out.get("sections") or []))
        self._estado_analisis_musical = "ready"
        self._error_natural = ""
        self.resultadosNaturalesCambiados.emit()

    def _al_error_busqueda_natural(self, mensaje: str, request_id: int) -> None:
        if request_id != self._active_request_seq_natural:
            return

        self._resultados_natural.set_datos([])
        self._secciones_natural.set_datos([])
        self._mensaje_natural = "No se pudo buscar en tu biblioteca en este momento."
        self._error_natural = str(mensaje)
        self._estado_analisis_musical = "error"
        self.resultadosNaturalesCambiados.emit()

    def _al_finalizar_busqueda_natural(self, request_id: int) -> None:
        if request_id != self._active_request_seq_natural:
            return

        self._buscando_natural = False
        self.buscandoNaturalCambiado.emit()

    def _aplicar_estado_natural(self, estado: dict) -> None:
        self._total_pistas_biblioteca = int(estado.get("total_tracks") or 0)
        self._hay_biblioteca = self._total_pistas_biblioteca > 0
        self._hay_features = bool(estado.get("has_features"))
        self._porcentaje_features = float(estado.get("percentage") or 0.0)

    @Slot()
    def refrescarEstadoNatural(self) -> None:
        try:
            from core.music_discovery_service import MusicDiscoveryService

            self._aplicar_estado_natural(MusicDiscoveryService(None).analysis_state())
            self._estado_analisis_musical = "ready" if self._hay_features else "idle"
            self._error_natural = ""
        except Exception as exc:
            self._hay_biblioteca = False
            self._hay_features = False
            self._total_pistas_biblioteca = 0
            self._porcentaje_features = 0.0
            self._estado_analisis_musical = "error"
            self._error_natural = str(exc)
        self.resultadosNaturalesCambiados.emit()

    @Slot(str)
    def buscar(self, termino: str) -> None:
        self._termino = termino
        self._error_natural = ""
        self._request_seq += 1
        request_id = self._request_seq
        self._active_request_seq = request_id

        if not termino or not termino.strip():
            if self._worker and self._worker.isRunning():
                self._archivar_worker_busqueda(self._worker)
            self._worker = None
            self._pistas.set_datos([])
            self._albums.set_datos([])
            self._artistas.set_datos([])
            self._favoritos.set_datos([])
            self.buscando.emit(False)
            self.resultadosCambiados.emit()
            return

        from workers.workers_qt import WorkerBusqueda
        if self._worker and self._worker.isRunning():
            self._archivar_worker_busqueda(self._worker)
            self._worker = None

        self.buscando.emit(True)
        self._worker = WorkerBusqueda(termino, parent=self)
        self._worker.resultados.connect(
            lambda resultado, rid=request_id: self._al_recibir_resultados(resultado, rid)
        )
        self._worker.finished.connect(
            lambda rid=request_id: self._al_finalizar_busqueda(rid)
        )
        self._worker.start()

    def _al_recibir_resultados(self, resultado: dict, request_id: int) -> None:
        if request_id != self._active_request_seq:
            return
        pistas = list(resultado.get("pistas", []) or [])
        favoritos, pistas_restantes = self._separar_favoritos(pistas)
        self._favoritos.set_datos(favoritos)
        self._pistas.set_datos(pistas_restantes)
        self._albums.set_datos(resultado.get("albums", []))
        self._artistas.set_datos(resultado.get("artistas", []))
        self.resultadosCambiados.emit()

    def _al_finalizar_busqueda(self, request_id: int) -> None:
        if request_id == self._active_request_seq:
            self.buscando.emit(False)

    @Slot(str)
    def buscarNatural(self, texto: str) -> None:
        texto = str(texto or "").strip()
        self._request_seq_natural += 1
        request_id = self._request_seq_natural
        self._active_request_seq_natural = request_id
        self._error_natural = ""

        if not texto:
            if self._worker_natural and self._worker_natural.isRunning():
                self._archivar_worker_natural(self._worker_natural)
            self._worker_natural = None
            self._resultados_natural.set_datos([])
            self._secciones_natural.set_datos([])
            self._interpretacion_natural = ""
            self._mensaje_natural = ""
            self._estado_analisis_musical = "idle"
            self._buscando_natural = False
            self.buscandoNaturalCambiado.emit()
            self.resultadosNaturalesCambiados.emit()
            return

        from workers.workers_qt import WorkerBusquedaNatural

        if self._worker_natural and self._worker_natural.isRunning():
            self._archivar_worker_natural(self._worker_natural)
            self._worker_natural = None

        self._estado_analisis_musical = "running"
        self._buscando_natural = True
        self.buscandoNaturalCambiado.emit()

        self._worker_natural = WorkerBusquedaNatural(texto, limite=25, parent=self)
        self._worker_natural.resultados.connect(
            lambda payload, rid=request_id: self._al_recibir_resultados_naturales(payload, rid)
        )
        self._worker_natural.error.connect(
            lambda mensaje, rid=request_id: self._al_error_busqueda_natural(mensaje, rid)
        )
        self._worker_natural.finished.connect(
            lambda rid=request_id: self._al_finalizar_busqueda_natural(rid)
        )
        self._worker_natural.start()

    @Slot()
    def recargar(self) -> None:
        """Reejecuta la última búsqueda para mantener resultados sincronizados."""
        self.buscar(self._termino)

    def _separar_favoritos(self, pistas: list[dict]) -> tuple[list[dict], list[dict]]:
        favoritos: list[dict] = []
        restantes: list[dict] = []
        ids_favoritos: set[int] = set()
        for pista in pistas:
            try:
                pista_id = int((pista or {}).get("id") or 0)
            except (TypeError, ValueError):
                pista_id = 0
            if int((pista or {}).get("favorita") or 0) == 1:
                favoritos.append(pista)
                if pista_id:
                    ids_favoritos.add(pista_id)
            else:
                restantes.append(pista)
        if not ids_favoritos:
            return favoritos, restantes
        restantes_filtradas: list[dict] = []
        for pista in restantes:
            try:
                pista_id = int((pista or {}).get("id") or 0)
            except (TypeError, ValueError):
                pista_id = 0
            if pista_id not in ids_favoritos:
                restantes_filtradas.append(pista)
        restantes = restantes_filtradas
        return favoritos, restantes

    def _normalizar_secciones_naturales(self, secciones: list[dict]) -> list[dict]:
        normalizadas: list[dict] = []
        for seccion in secciones:
            if not isinstance(seccion, dict):
                continue
            titulo = str(seccion.get("titulo") or seccion.get("title") or "").strip()
            pistas = seccion.get("pistas") or seccion.get("results") or []
            if not titulo or not isinstance(pistas, list) or not pistas:
                continue
            normalizadas.append({
                "titulo": titulo,
                "title": titulo,
                "pistas": pistas,
                "results": pistas,
            })
        return normalizadas

    def cerrar(self) -> None:
        """Interrumpe workers de busqueda pendientes antes del cierre."""
        workers = [self._worker, self._worker_natural,
                   *self._workers_busqueda_obsoletos,
                   *self._workers_natural_obsoletos]
        for w in workers:
            if w is None:
                continue
            try:
                if w.isRunning():
                    w.requestInterruption()
            except RuntimeError:
                continue
            except Exception as exc:
                _log.debug("requestInterruption busqueda fallo: %s", exc)
        for w in workers:
            if w is None:
                continue
            try:
                if w.isRunning():
                    w.wait(500)
            except RuntimeError:
                continue
            except Exception as exc:
                _log.debug("wait busqueda fallo: %s", exc)


# =============================================================================
# MODELO DE AUDIO INTELLIGENCE BACKGROUND
# =============================================================================

class ModeloAudioIntelligenceBackground(QObject):
    """Estado y controles de la cola deep persistente."""

    estadoCambiado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._snapshot = self._snapshot_default()
        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self.refrescarAudioDeepEstado)
        self.refrescarAudioDeepEstado()

    @staticmethod
    def _snapshot_default() -> dict:
        return {
            "estado": "inactivo",
            "activo": False,
            "disponible": False,
            "procesando": False,
            "pausado": False,
            "total": 0,
            "procesadas": 0,
            "ready": 0,
            "failed": 0,
            "skipped": 0,
            "pendientes": 0,
            "porcentaje": 0.0,
            "eta": "",
            "velocidad": 0.0,
            "pista_actual": "",
            "mensaje": "",
            "warning": "",
            "run_id": "",
            "deep_ready": 0,
        }

    def _service(self):
        from core.audio_intelligence_background import AudioIntelligenceBackgroundService

        return AudioIntelligenceBackgroundService()

    def _aplicar_snapshot(self, snapshot: dict | None) -> None:
        data = self._snapshot_default()
        if snapshot:
            data.update(dict(snapshot))
        self._snapshot = data
        if data.get("procesando"):
            if not self._timer.isActive():
                self._timer.start()
        elif self._timer.isActive():
            self._timer.stop()
        self.estadoCambiado.emit()

    @Property(str, notify=estadoCambiado)
    def audioDeepEstado(self) -> str:
        return str(self._snapshot.get("estado") or "inactivo")

    @Property(bool, notify=estadoCambiado)
    def audioDeepActivo(self) -> bool:
        return bool(self._snapshot.get("activo"))

    @Property(bool, notify=estadoCambiado)
    def audioDeepDisponible(self) -> bool:
        return bool(self._snapshot.get("disponible"))

    @Property(bool, notify=estadoCambiado)
    def audioDeepProcesando(self) -> bool:
        return bool(self._snapshot.get("procesando"))

    @Property(bool, notify=estadoCambiado)
    def audioDeepPausado(self) -> bool:
        return bool(self._snapshot.get("pausado"))

    @Property(int, notify=estadoCambiado)
    def audioDeepTotal(self) -> int:
        return int(self._snapshot.get("total") or 0)

    @Property(int, notify=estadoCambiado)
    def audioDeepProcesadas(self) -> int:
        return int(self._snapshot.get("procesadas") or 0)

    @Property(int, notify=estadoCambiado)
    def audioDeepReady(self) -> int:
        return int(self._snapshot.get("ready") or 0)

    @Property(int, notify=estadoCambiado)
    def audioDeepFailed(self) -> int:
        return int(self._snapshot.get("failed") or 0)

    @Property(int, notify=estadoCambiado)
    def audioDeepSkipped(self) -> int:
        return int(self._snapshot.get("skipped") or 0)

    @Property(int, notify=estadoCambiado)
    def audioDeepPendientes(self) -> int:
        return int(self._snapshot.get("pendientes") or 0)

    @Property(float, notify=estadoCambiado)
    def audioDeepPorcentaje(self) -> float:
        return float(self._snapshot.get("porcentaje") or 0.0)

    @Property(str, notify=estadoCambiado)
    def audioDeepETA(self) -> str:
        return str(self._snapshot.get("eta") or "")

    @Property(float, notify=estadoCambiado)
    def audioDeepVelocidad(self) -> float:
        return float(self._snapshot.get("velocidad") or 0.0)

    @Property(str, notify=estadoCambiado)
    def audioDeepPistaActual(self) -> str:
        return str(self._snapshot.get("pista_actual") or "")

    @Property(str, notify=estadoCambiado)
    def audioDeepMensaje(self) -> str:
        return str(self._snapshot.get("mensaje") or "")

    @Property(str, notify=estadoCambiado)
    def audioDeepWarning(self) -> str:
        return str(self._snapshot.get("warning") or "")

    @Property(str, notify=estadoCambiado)
    def audioDeepRunId(self) -> str:
        return str(self._snapshot.get("run_id") or "")

    @Property(int, notify=estadoCambiado)
    def audioDeepReadyBiblioteca(self) -> int:
        return int(self._snapshot.get("deep_ready") or 0)

    @Slot()
    def iniciarAudioDeepBackground(self) -> None:
        self._iniciar_worker(reactivate_cancelled=True, force_retry_failed=False, enqueue_missing=True)

    @Slot()
    def pausarAudioDeepBackground(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
        self._aplicar_snapshot(self._service().pause())

    @Slot()
    def reanudarAudioDeepBackground(self) -> None:
        snapshot = self._service().resume(reactivate_cancelled=False)
        self._aplicar_snapshot(snapshot)
        if int(snapshot.get("pendientes") or 0) > 0:
            self._iniciar_worker(reactivate_cancelled=False, force_retry_failed=False, enqueue_missing=False)

    @Slot()
    def cancelarAudioDeepConservar(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
        self._aplicar_snapshot(self._service().cancel_keep())

    @Slot()
    def cancelarAudioDeepDescartar(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
        self._aplicar_snapshot(self._service().cancel_discard())

    @Slot()
    def reintentarAudioDeepFallidas(self) -> None:
        snapshot = self._service().retry_failed()
        self._aplicar_snapshot(snapshot)
        if int(snapshot.get("pendientes") or 0) > 0:
            self._iniciar_worker(reactivate_cancelled=False, force_retry_failed=True, enqueue_missing=False)

    @Slot()
    def refrescarAudioDeepEstado(self) -> None:
        try:
            self._aplicar_snapshot(self._service().status())
        except Exception as exc:
            snapshot = self._snapshot_default()
            snapshot["estado"] = "error"
            snapshot["warning"] = str(exc)
            self._aplicar_snapshot(snapshot)

    @Slot()
    def autoIniciarAudioDeepSiCorresponde(self) -> None:
        try:
            from core.audio_intelligence_background import AudioIntelligenceBackgroundConfig

            cfg = AudioIntelligenceBackgroundConfig.load()
            if not (cfg.enabled and cfg.background_enabled and cfg.resume_pending_on_startup and cfg.autostart):
                self.refrescarAudioDeepEstado()
                return
            svc = self._service()
            svc.recover_interrupted_jobs()
            snapshot = svc.status()
            self._aplicar_snapshot(snapshot)
            if int(snapshot.get("pendientes") or 0) > 0 and not snapshot.get("warning"):
                self._iniciar_worker(reactivate_cancelled=False, force_retry_failed=False, enqueue_missing=False)
        except Exception as exc:
            _log.warning("No se pudo autoiniciar Audio Intelligence deep background: %s", exc)
            self.refrescarAudioDeepEstado()

    def _iniciar_worker(self, *, reactivate_cancelled: bool, force_retry_failed: bool, enqueue_missing: bool) -> None:
        if self._worker and self._worker.isRunning():
            self.refrescarAudioDeepEstado()
            return
        from workers.workers_qt import WorkerAudioIntelligenceBackground

        self._worker = WorkerAudioIntelligenceBackground(
            reactivate_cancelled=reactivate_cancelled,
            force_retry_failed=force_retry_failed,
            enqueue_missing=enqueue_missing,
            parent=self,
        )
        self._worker.progreso.connect(self._aplicar_snapshot)
        self._worker.completado.connect(self._aplicar_snapshot)
        self._worker.error.connect(self._al_error_worker)
        self._worker.finished.connect(self.refrescarAudioDeepEstado)
        self._timer.start()
        self._worker.start()

    def _al_error_worker(self, mensaje: str) -> None:
        snapshot = dict(self._snapshot)
        snapshot["estado"] = "error"
        snapshot["warning"] = mensaje
        snapshot["procesando"] = False
        self._aplicar_snapshot(snapshot)

    def cerrar(self) -> None:
        """Detiene el timer y solicita interrupcion cooperativa al worker.

        El worker propaga stop_event al servicio batch para que la pista
        en curso termine y los datos parciales se persistan. wait(5000)
        es suficiente: el ciclo del servicio revisa stop_event entre
        pistas (~1-2s por pista).
        """
        try:
            self._timer.stop()
        except Exception as exc:
            _log.debug("stop timer audio deep fallo: %s", exc)
        worker = self._worker
        if worker is not None:
            try:
                if worker.isRunning():
                    worker.requestInterruption()
                    worker.wait(5000)
            except RuntimeError:
                pass
            except Exception as exc:
                _log.debug("cierre worker audio deep fallo: %s", exc)


# =============================================================================
# MODELO DE IMPORTACION
# =============================================================================

class ModeloImportacion(QObject):
    """Estado de la importacion en curso."""

    progresoCambiado  = Signal()
    historialCambiado = Signal()
    diagnosticoCambiado = Signal()
    deepReintentado   = Signal(int)   # nº de jobs deep reencolados
    importacionFin    = Signal(dict)
    importacionCancelada = Signal(dict)
    importacionError  = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._procesados   = 0
        self._total        = 0
        self._nombre_actual = ""
        self._etapa_actual  = ""
        self._en_ejecucion  = False
        self._worker        = None
        self._estado        = "idle"
        self._ultimo_error  = ""
        self._inicio_monotonic = 0.0
        self._ultimo_eta_seg = -1
        self._ema_seg_por_archivo: Optional[float] = None
        self._historial     = ListaGenerica(self)
        self._recovery_worker = None
        self._diagnostico_ejecutando = False
        self._diagnostico_mensaje = ""
        self._diagnostico_post_import = self._diagnostico_default()
        self._resumen_historial = {
            "total_aceptados": 0,
            "total_revision": 0,
            "total_cuarentena": 0,
            "total_pendientes": 0,
            "total_pendientes_historicos": 0,
            "total_ejecuciones": 0,
        }
        # Diferir queries iniciales: si las ejecutamos sincrónicamente en
        # el constructor, el primer arranque de la app bloquea el event
        # loop de Qt durante la query de pendientes + UPDATE de huérfanos,
        # produciendo el "freeze de primera carga" en Importar. Cedemos
        # control al event loop con singleShot(0) para que la ventana
        # pinte primero y la consulta caiga en el primer slice libre.
        # En tests no hay event loop activo, así que el flag síncrono
        # del worker (que conftest fija a "1") también fuerza este
        # bootstrap a ejecutarse en línea — manteniendo determinismo.
        import os as _os
        sync_tests = _os.environ.get("NB_SOUND_UI_WORKER_SYNC", "").strip().lower() in {"1", "true", "yes"}
        if sync_tests:
            self._bootstrap_inicial_diferido()
        else:
            QTimer.singleShot(0, self._bootstrap_inicial_diferido)

    def _bootstrap_inicial_diferido(self) -> None:
        try:
            from servicios.importacion import marcar_sesiones_importacion_huerfanas
            marcar_sesiones_importacion_huerfanas()
        except Exception as e:
            _log.warning(f"No se pudieron marcar sesiones de importacion huerfanas: {e}")
        try:
            self.cargar_historial()
        except Exception as e:
            _log.warning("cargar_historial diferido fallo: %s", e)

    @Property(int, notify=progresoCambiado)
    def procesados(self) -> int:
        return self._procesados

    @Property(int, notify=progresoCambiado)
    def total(self) -> int:
        return self._total

    @Property(str, notify=progresoCambiado)
    def nombre_actual(self) -> str:
        return self._nombre_actual

    @Property(str, notify=progresoCambiado)
    def etapa_actual(self) -> str:
        return self._etapa_actual

    @Property(bool, notify=progresoCambiado)
    def en_ejecucion(self) -> bool:
        return self._en_ejecucion

    @Property(str, notify=progresoCambiado)
    def estado(self) -> str:
        return self._estado

    @Property(str, notify=progresoCambiado)
    def ultimo_error(self) -> str:
        return self._ultimo_error

    @Property(float, notify=progresoCambiado)
    def porcentaje(self) -> float:
        if self._total > 0:
            return self._procesados / self._total
        return 0.0

    @Property(int, notify=progresoCambiado)
    def eta_seg(self) -> int:
        return self._ultimo_eta_seg

    @Property(bool, notify=progresoCambiado)
    def progreso_indeterminado(self) -> bool:
        return self._en_ejecucion and self._total <= 0

    @Property(QObject, notify=historialCambiado)
    def historial(self) -> ListaGenerica:
        return self._historial

    @Property("QVariant", notify=historialCambiado)
    def resumen_historial(self) -> dict:
        return dict(self._resumen_historial)

    @Property("QVariant", notify=diagnosticoCambiado)
    def diagnosticoPostImport(self) -> dict:
        return dict(self._diagnostico_post_import)

    @Property(bool, notify=diagnosticoCambiado)
    def diagnosticoEjecutando(self) -> bool:
        return self._diagnostico_ejecutando

    @Property(str, notify=diagnosticoCambiado)
    def diagnosticoMensaje(self) -> str:
        return self._diagnostico_mensaje

    @Slot("QVariant")
    def iniciar_importacion(self, config_dict) -> None:
        if self._worker and self._worker.isRunning():
            self._estado = "cancelando"
            self.progresoCambiado.emit()
            self._worker.requestInterruption()
            return

        if self._en_ejecucion:
            return

        from pathlib import Path
        from servicios.importacion import ConfigImportacion
        from workers.workers_qt import WorkerImportacion

        # QML suele enviar objetos JS como QJSValue; convertirlos a dict Python.
        if isinstance(config_dict, QJSValue):
            config_dict = config_dict.toVariant()

        if config_dict is None:
            config_dict = {}

        if not isinstance(config_dict, dict):
            raise TypeError(
                f"iniciar_importacion esperaba dict/QJSValue y recibió {type(config_dict).__name__}"
            )

        requeridas = ("entrada", "biblioteca", "revision", "cuarentena", "logs")
        faltantes = [k for k in requeridas if not str(config_dict.get(k, "")).strip()]
        if faltantes:
            msg = "Faltan rutas obligatorias: " + ", ".join(faltantes)
            self._estado = "error"
            self._ultimo_error = msg
            self.progresoCambiado.emit()
            self.importacionError.emit(msg)
            return

        score_accept = float(config_dict.get("score_accept", 0.82))
        score_review = float(config_dict.get("score_review", 0.55))
        if not (0.0 <= score_review <= score_accept <= 1.0):
            msg = "Scores inválidos. Debe cumplirse: 0 <= score_review <= score_accept <= 1."
            self._estado = "error"
            self._ultimo_error = msg
            self.progresoCambiado.emit()
            self.importacionError.emit(msg)
            return

        ajustes_avanzados = config_dict.get("ajustes_avanzados", {})
        if isinstance(ajustes_avanzados, QJSValue):
            ajustes_avanzados = ajustes_avanzados.toVariant()
        if not isinstance(ajustes_avanzados, dict):
            ajustes_avanzados = {}

        config = ConfigImportacion(
            directorio_entrada    = Path(config_dict.get("entrada", "")),
            directorio_biblioteca = Path(config_dict.get("biblioteca", "")),
            directorio_revision   = Path(config_dict.get("revision", "")),
            directorio_cuarentena = Path(config_dict.get("cuarentena", "")),
            directorio_logs       = Path(config_dict.get("logs", "")),
            directorio_procesados = Path(config_dict.get("procesados", "")),
            directorio_cache      = Path(config_dict.get("cache", "")),
            directorio_temp       = Path(config_dict.get("temp", str(Path(tempfile.gettempdir()) / "nb_sound_tmp"))),
            dry_run               = bool(config_dict.get("dry_run", False)),
            enable_shazam         = bool(config_dict.get("enable_shazam", True)),
            enable_acoustid       = bool(config_dict.get("enable_acoustid", True)),
            score_accept          = score_accept,
            score_review          = score_review,
            ia_proveedor          = str(config_dict.get("ia_proveedor", "No")),
            acoustid_key          = str(config_dict.get("acoustid_key", "")),
            anthropic_key         = str(config_dict.get("anthropic_key", "")),
            openai_key            = str(config_dict.get("openai_key", "")),
            ajustes_avanzados     = {str(k): str(v) for k, v in ajustes_avanzados.items()},
        )

        self._procesados    = 0
        self._total         = 0
        self._nombre_actual = ""
        self._etapa_actual  = ""
        self._en_ejecucion  = True
        self._estado        = "en_ejecucion"
        self._ultimo_error  = ""
        self._inicio_monotonic = time.monotonic()
        self._ultimo_eta_seg = -1
        self._ema_seg_por_archivo = None
        self.progresoCambiado.emit()

        self._worker = WorkerImportacion(config, parent=self)
        self._worker.progreso.connect(self._al_progreso)
        self._worker.completado.connect(self._al_completar)
        self._worker.cancelado.connect(self._al_cancelar)
        self._worker.error.connect(self._al_error)
        self._worker.start()

    @Slot()
    def cancelar_importacion(self) -> None:
        """Solicita cancelación sin bloquear el hilo de la UI."""
        if self._worker and self._worker.isRunning() and self._en_ejecucion:
            self._estado = "cancelando"
            self.progresoCambiado.emit()
            self._worker.requestInterruption()

    def _al_progreso(self, procesados: int, total: int, nombre: str, etapa: str) -> None:
        total_seguro = max(0, int(total))
        procesados_seguro = max(0, int(procesados))
        if total_seguro > 0:
            procesados_seguro = min(procesados_seguro, total_seguro)

        # Evita retrocesos visuales espurios en la barra.
        if procesados_seguro < self._procesados:
            procesados_seguro = self._procesados
        if total_seguro < self._total and self._total > 0:
            total_seguro = self._total

        self._procesados    = procesados_seguro
        self._total         = total_seguro
        self._nombre_actual = nombre
        self._etapa_actual  = etapa
        self._actualizar_eta()
        self.progresoCambiado.emit()

    def _al_completar(self, resumen: dict) -> None:
        self._en_ejecucion = False
        self._estado = "completada"
        self._ultimo_eta_seg = 0
        self.progresoCambiado.emit()
        self.cargar_historial()
        self.refrescarDiagnosticoImportacion()
        self.importacionFin.emit(resumen)

    def _al_cancelar(self, resumen: dict) -> None:
        self._en_ejecucion = False
        self._estado = "cancelada"
        self._ultimo_eta_seg = -1
        self.progresoCambiado.emit()
        self.cargar_historial()
        self.importacionCancelada.emit(resumen)

    def _al_error(self, mensaje: str) -> None:
        self._en_ejecucion = False
        self._estado = "error"
        self._ultimo_error = mensaje
        self._ultimo_eta_seg = -1
        self.progresoCambiado.emit()
        self.cargar_historial()
        self.importacionError.emit(mensaje)

    def _actualizar_eta(self) -> None:
        if (
            not self._en_ejecucion
            or self._total <= 0
            or self._procesados <= 0
            or self._procesados >= self._total
        ):
            self._ultimo_eta_seg = -1
            return

        if self._inicio_monotonic <= 0:
            self._ultimo_eta_seg = -1
            return

        transcurrido = time.monotonic() - self._inicio_monotonic
        if transcurrido < 3 or self._procesados < 2:
            # Todavia no hay base estadistica confiable.
            self._ultimo_eta_seg = -1
            return

        seg_por_archivo = transcurrido / max(1, self._procesados)
        alpha = 0.25
        if self._ema_seg_por_archivo is None:
            self._ema_seg_por_archivo = seg_por_archivo
        else:
            self._ema_seg_por_archivo = (
                alpha * seg_por_archivo + (1.0 - alpha) * self._ema_seg_por_archivo
            )

        restantes = max(0, self._total - self._procesados)
        estimado = int(round(self._ema_seg_por_archivo * restantes))
        if restantes > 0 and estimado <= 0:
            estimado = 1
        self._ultimo_eta_seg = estimado

    @Slot()
    def cargar_historial(self) -> None:
        datos = svc_bib.listar_sesiones_import(50)
        self._historial.set_datos(datos)
        self._resumen_historial = self._calcular_resumen_historial(datos)
        self.historialCambiado.emit()

    def conectar_revision(self, modelo_revision: QObject) -> None:
        """Conecta `accionArchivoExitosa` de ModeloRevision para que el
        contador de pendientes del resumen del importador se actualice
        en vivo cuando el usuario marca algo como visto desde Revisión.

        Sin esto, los pendientes en el resumen solo se refrescan al volver
        a abrir la pantalla Importar o al disparar otra importación.
        """
        try:
            modelo_revision.accionArchivoExitosa.connect(
                lambda _msg: self.cargar_historial()
            )
        except Exception as exc:
            _log.debug("conectar_revision fallo: %s", exc)

    @Slot()
    def refrescarDiagnosticoImportacion(self) -> None:
        self._iniciar_recovery("status")

    @Slot()
    def reconciliarDiagnostico(self) -> None:
        """Reconciliación al (re)entrar a la vista de importación.

        Si quedó marcado "ejecutando" pero el worker ya terminó (la señal de
        finalización puede perderse al cambiar de vista), limpia el estado
        fantasma para que el refresco siguiente refleje el estado real. Si el
        worker sigue vivo no interrumpe nada. Es barato: retorna de inmediato
        cuando no hay estado que reconciliar, por lo que es seguro invocarlo en
        cada navegación.
        """
        if not self._diagnostico_ejecutando:
            return
        if self._recovery_worker and self._recovery_worker.isRunning():
            return
        self._recovery_worker = None
        self._diagnostico_ejecutando = False
        self._diagnostico_mensaje = ""
        self.diagnosticoCambiado.emit()

    @Slot()
    def reintentarPortadasFaltantes(self) -> None:
        self._iniciar_recovery("retry_track_covers")

    @Slot()
    def reintentarImagenesArtistasFaltantes(self) -> None:
        self._iniciar_recovery("retry_artist_images")

    @Slot()
    def reintentarAssetsVisualesFaltantes(self) -> None:
        self._iniciar_recovery("retry_visual_assets")

    @Slot()
    def reintentarEnrichmentFallido(self) -> None:
        self._iniciar_recovery("retry_enrichment")

    @Slot()
    def reintentarLyricsFaltantes(self) -> None:
        self._iniciar_recovery("retry_lyrics")

    @Slot()
    def reintentarAudioFeaturesFallidas(self) -> None:
        self._iniciar_recovery("retry_audio_features")

    @Slot()
    def reintentarSidecarsFallidos(self) -> None:
        self._iniciar_recovery("retry_sidecars")

    @Slot()
    def reintentarDeepFallidas(self) -> None:
        self._iniciar_recovery("retry_deep_failed")

    def _iniciar_recovery(self, action: str) -> None:
        # Reconciliación defensiva: si quedó marcado "ejecutando" pero el worker
        # ya no corre (p. ej. la señal de finalización se perdió al cambiar de
        # vista), limpiamos el estado fantasma antes de seguir. Sin esto, el
        # mensaje "Ejecutando…" quedaba congelado y obligaba a reiniciar la app.
        worker_vivo = bool(self._recovery_worker and self._recovery_worker.isRunning())
        if self._diagnostico_ejecutando and not worker_vivo:
            self._diagnostico_ejecutando = False
            self._recovery_worker = None

        if worker_vivo:
            self._diagnostico_mensaje = "Ya hay un reintento en curso."
            self.diagnosticoCambiado.emit()
            return

        self._diagnostico_ejecutando = True
        self._diagnostico_mensaje = self._mensaje_recovery(action, running=True)
        self.diagnosticoCambiado.emit()

        # "status" es una consulta rápida de BD y se ejecuta síncrono.
        # Las acciones de retry (assets, enrichment, audio_features, lyrics,
        # sidecars, deep_failed) son pesadas y se mueven a worker para no
        # bloquear el hilo UI al finalizar una importación.
        if action == "status":
            try:
                from core.import_recovery_service import ImportRecoveryService

                self._al_recovery_completo(ImportRecoveryService().status())
            except Exception as exc:
                self._al_recovery_error(str(exc))
            return

        from workers.workers_qt import WorkerImportRecovery

        self._recovery_worker = WorkerImportRecovery(action, parent=self)
        self._recovery_worker.completado.connect(self._al_recovery_completo)
        self._recovery_worker.error.connect(self._al_recovery_error)
        self._recovery_worker.start()

    def _al_recovery_completo(self, snapshot: dict) -> None:
        self._diagnostico_post_import = self._normalizar_diagnostico(snapshot)
        action = str(snapshot.get("action") or "status") if isinstance(snapshot, dict) else "status"
        processed = int(snapshot.get("processed") or 0) if isinstance(snapshot, dict) else 0
        failed = int(snapshot.get("failed") or 0) if isinstance(snapshot, dict) else 0
        if action == "status":
            self._diagnostico_mensaje = "Diagnóstico actualizado."
        elif action == "retry_deep_failed":
            # El reintento deep solo REENCOLA; el procesamiento ocurre en el
            # worker de "Análisis musical en segundo plano", que el usuario debe
            # reanudar. Avisamos claramente y refrescamos esa sección (señal
            # cableada en main_ui) para que muestre los jobs ya encolados.
            requeued = int(snapshot.get("requeued") or 0) if isinstance(snapshot, dict) else 0
            if requeued > 0:
                self._diagnostico_mensaje = (
                    f"{requeued} análisis deep reencolado(s). Pulsa «Reanudar» en "
                    "«Análisis musical en segundo plano» para procesarlos."
                )
                self.deepReintentado.emit(requeued)
            else:
                self._diagnostico_mensaje = "No hay análisis deep fallidos para reintentar."
        else:
            self._diagnostico_mensaje = f"Reintento finalizado: procesados={processed}, fallidos={failed}."
        self._diagnostico_ejecutando = False
        self._recovery_worker = None
        self.diagnosticoCambiado.emit()

    def _al_recovery_error(self, mensaje: str) -> None:
        data = dict(self._diagnostico_post_import)
        data["warning"] = str(mensaje or "Error en diagnóstico de importación")
        self._diagnostico_post_import = self._normalizar_diagnostico(data)
        self._diagnostico_mensaje = data["warning"]
        self._diagnostico_ejecutando = False
        self._recovery_worker = None
        self.diagnosticoCambiado.emit()

    @staticmethod
    def _diagnostico_default() -> dict:
        return {
            "ok": True,
            "total_tracks": 0,
            "missing_track_covers": 0,
            "missing_album_covers": 0,
            "missing_artist_images": 0,
            "missing_visual_assets": 0,
            "missing_enrichment": 0,
            "missing_lyrics": 0,
            "audio_features_missing": 0,
            "audio_features_failed": 0,
            "deep_failed": 0,
            "deep_pending": 0,
            "warning": "",
        }

    @classmethod
    def _normalizar_diagnostico(cls, snapshot: dict | None) -> dict:
        data = cls._diagnostico_default()
        if isinstance(snapshot, dict):
            data.update(snapshot)
        for key in (
            "total_tracks", "missing_track_covers", "missing_album_covers",
            "missing_artist_images", "missing_visual_assets", "missing_enrichment",
            "missing_lyrics", "audio_features_missing", "audio_features_failed",
            "deep_failed", "deep_pending",
        ):
            try:
                data[key] = max(0, int(data.get(key) or 0))
            except (TypeError, ValueError):
                data[key] = 0
        data["warning"] = str(data.get("warning") or "")
        return data

    @staticmethod
    def _mensaje_recovery(action: str, *, running: bool) -> str:
        verb = "Ejecutando" if running else "Listo"
        nombres = {
            "status": "diagnóstico",
            "retry_track_covers": "reintento de portadas",
            "retry_artist_images": "reintento de imágenes de artistas",
            "retry_visual_assets": "reintento de assets visuales",
            "retry_enrichment": "reintento de enrichment/sidecars",
            "retry_lyrics": "reintento de lyrics",
            "retry_audio_features": "reintento de audio features",
            "retry_sidecars": "reintento de sidecars",
            "retry_deep_failed": "reintento de deep failed",
        }
        return f"{verb} {nombres.get(action, action)}..."

    def _calcular_resumen_historial(self, filas: list[dict]) -> dict:
        # `total_pendientes_historicos` acumula lo que produjeron las
        # sesiones de importación. `total_pendientes` es el contador VIVO:
        # lo consultamos a la tabla de pendientes para que cuando el
        # usuario marque algo como "visto" desde Revisión, el resumen del
        # Importador refleje el cambio sin tener que reabrir la app.
        # `total_duplicados` se deriva por diferencia: lo que el pipeline
        # descartó como duplicado exacto/semántico/mejorable no aparece
        # en aceptados/revisión/cuarentena/errores y antes "desaparecía"
        # del resumen — el usuario reportaba "importé 33, salen 31, las 2
        # restantes no se ven en ningún contador".
        resumen = {
            "total_descubiertos": 0,
            "total_aceptados": 0,
            "total_revision": 0,
            "total_cuarentena": 0,
            "total_revision_historico": 0,
            "total_cuarentena_historico": 0,
            "total_duplicados": 0,
            "total_errores": 0,
            "total_pendientes": 0,
            "total_pendientes_historicos": 0,
            "total_ejecuciones": len(filas),
        }
        for fila in filas:
            descubiertos = self._entero_no_negativo(fila.get("total_descubiertos"))
            aceptados = self._entero_no_negativo(fila.get("total_aceptados"))
            revision = self._entero_no_negativo(fila.get("total_revision"))
            cuarentena = self._entero_no_negativo(fila.get("total_cuarentena"))
            errores = self._entero_no_negativo(fila.get("total_errores"))
            pendientes = revision + cuarentena
            # Lo que no fue aceptado/revisado/encuarentenado/error son
            # duplicados (exacto, semántico o mejorable). Es un cálculo
            # por diferencia: el pipeline no persiste el desglose en la
            # tabla `sesiones_import`, solo en el JSON de summary.
            duplicados = max(0, descubiertos - aceptados - revision - cuarentena - errores)
            resumen["total_descubiertos"] += descubiertos
            resumen["total_aceptados"] += aceptados
            resumen["total_revision_historico"] += revision
            resumen["total_cuarentena_historico"] += cuarentena
            resumen["total_duplicados"] += duplicados
            resumen["total_errores"] += errores
            resumen["total_pendientes_historicos"] += pendientes
        # `total_revision`/`total_cuarentena` del resumen reflejan el estado VIVO
        # (lo que hoy está realmente pendiente en la vista Revisar), no la suma
        # histórica acumulada: así, al marcar pendientes como vistos, el resumen
        # del Importador baja junto con Revisar en lugar de mostrar "Revisión 82"
        # contra una vista que ya está en 0. Los totales históricos quedan en
        # `*_historico` por si se necesitan en otro contexto.
        try:
            actuales = svc_bib.contar_pendientes()
            rev_viva = self._entero_no_negativo(actuales.get("revision"))
            cuar_viva = self._entero_no_negativo(actuales.get("cuarentena"))
            resumen["total_revision"] = rev_viva
            resumen["total_cuarentena"] = cuar_viva
            resumen["total_pendientes"] = rev_viva + cuar_viva
        except Exception as exc:
            _log.debug("contar_pendientes() fallo: %s", exc)
            resumen["total_revision"] = resumen["total_revision_historico"]
            resumen["total_cuarentena"] = resumen["total_cuarentena_historico"]
            resumen["total_pendientes"] = resumen["total_pendientes_historicos"]
        return resumen

    @staticmethod
    def _entero_no_negativo(valor) -> int:
        try:
            return max(0, int(valor or 0))
        except (TypeError, ValueError):
            return 0

    def cerrar(self) -> None:
        """Interrumpe importacion y diagnostico al cerrar la aplicacion.

        La importacion es cooperativa: el worker propaga el flag de
        interrupcion al ServicioImportacion, que cierra la sesion en
        curso, libera locks de cache y marca el run como cancelado para
        que reapertura no relance pistas a medio procesar. wait(10s)
        cubre el cierre normal; si excede, Qt destruye igual.
        """
        worker = self._worker
        if worker is not None:
            try:
                if worker.isRunning():
                    worker.requestInterruption()
                    worker.wait(10000)
            except RuntimeError:
                pass
            except Exception as exc:
                _log.debug("cierre worker importacion fallo: %s", exc)

        recovery = self._recovery_worker
        if recovery is not None:
            try:
                if recovery.isRunning():
                    recovery.requestInterruption()
                    recovery.wait(3000)
            except RuntimeError:
                pass
            except Exception as exc:
                _log.debug("cierre recovery worker fallo: %s", exc)


# =============================================================================
# MODELO DE REVISION
# =============================================================================

class ModeloRevision(QObject):
    """Archivos pendientes de revision o cuarentena."""

    pendientesCambiados  = Signal()
    contadorCambiado     = Signal()
    explainCambiado      = Signal()
    accionArchivoFallida = Signal(str)
    accionArchivoExitosa = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._revision    = ListaGenerica(self)
        self._cuarentena  = ListaGenerica(self)
        self._revision_fuente: list[dict] = []
        self._cuarentena_fuente: list[dict] = []
        self._contadores  = {"revision": 0, "cuarentena": 0}
        self._explain_data: dict = {}
        self._filtro_texto: str = ""
        self._filtro_causa: str = "todas"
        self._filtro_sesion: str = "todas"

    @Property(QObject, notify=pendientesCambiados)
    def revision(self) -> ListaGenerica:
        return self._revision

    @Property(QObject, notify=pendientesCambiados)
    def cuarentena(self) -> ListaGenerica:
        return self._cuarentena

    @Property(int, notify=contadorCambiado)
    def total_revision(self) -> int:
        return self._contadores["revision"]

    @Property(int, notify=contadorCambiado)
    def total_cuarentena(self) -> int:
        return self._contadores["cuarentena"]

    @Property("QVariant", notify=explainCambiado)
    def explain(self) -> dict:
        return self._explain_data

    @Slot()
    def cargar(self) -> None:
        self._revision_fuente = svc_bib.listar_pendientes(tipo="revision")
        self._cuarentena_fuente = svc_bib.listar_pendientes(tipo="cuarentena")
        self._aplicar_filtros()
        self._contadores = svc_bib.contar_pendientes()
        self.pendientesCambiados.emit()
        self.contadorCambiado.emit()

    @Slot(int)
    def marcar_visto(self, pendiente_id: int) -> None:
        if pendiente_id <= 0:
            _log.warning("No se pudo marcar pendiente como visto: id invalido %s", pendiente_id)
            self.accionArchivoFallida.emit("Identificador de pendiente inválido.")
            return
        try:
            svc_bib.marcar_pendiente_resuelto(pendiente_id)
            self.cargar()
            self.accionArchivoExitosa.emit("Pendiente marcado como visto.")
        except Exception as e:
            _log.warning("No se pudo marcar pendiente como visto id=%s: %s", pendiente_id, e)
            self.accionArchivoFallida.emit(f"No se pudo marcar como visto: {e}")

    @Slot(int)
    def marcar_resuelto(self, pendiente_id: int) -> None:
        self.marcar_visto(pendiente_id)

    @Slot(str, str, str)
    def set_filtros(self, texto: str = "", causa: str = "todas", sesion: str = "todas") -> None:
        self._filtro_texto = (texto or "").strip().lower()
        self._filtro_causa = (causa or "todas").strip().lower()
        sesion_normalizada = (sesion or "todas").strip().lower()
        if sesion_normalizada != "todas" and not sesion_normalizada.isdigit():
            sesion_normalizada = "todas"
        self._filtro_sesion = sesion_normalizada
        self._aplicar_filtros()
        self.pendientesCambiados.emit()

    @Slot()
    def limpiar_filtros(self) -> None:
        self._filtro_texto = ""
        self._filtro_causa = "todas"
        self._filtro_sesion = "todas"
        self._aplicar_filtros()
        self.pendientesCambiados.emit()

    def _aplicar_filtros(self) -> None:
        self._revision.set_datos(self._filtrar_items(self._revision_fuente))
        self._cuarentena.set_datos(self._filtrar_items(self._cuarentena_fuente))

    def _filtrar_items(self, items: list[dict]) -> list[dict]:
        if not items:
            return []

        def _coincide(item: dict) -> bool:
            if self._filtro_causa != "todas" and str(item.get("causa", "")).lower() != self._filtro_causa:
                return False
            if self._filtro_sesion != "todas":
                sesion_id = str(item.get("sesion_id", "")).lower()
                if sesion_id != self._filtro_sesion:
                    return False
            if self._filtro_texto:
                texto_base = " ".join([
                    str(item.get("nombre_archivo", "")),
                    str(item.get("ruta_archivo", "")),
                    str(item.get("causa", "")),
                ]).lower()
                if self._filtro_texto not in texto_base:
                    return False
            return True

        return [item for item in items if _coincide(item)]

    @Slot(str)
    def cargar_explain(self, target: str) -> None:
        self._explain_data = svc_bib.explicar_entidad(target)
        self.explainCambiado.emit()

    @Slot(str, result=bool)
    def abrir_archivo(self, ruta_archivo: str) -> bool:
        from PySide6.QtGui import QDesktopServices
        ruta = (ruta_archivo or "").strip()
        if not ruta:
            _log.warning("No se pudo abrir archivo pendiente: ruta vacia")
            return False

        path = Path(ruta)
        if not path.exists():
            _log.warning("No se pudo abrir archivo pendiente, no existe: %s", path)
            return False

        try:
            ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except Exception as e:
            _log.warning("No se pudo abrir archivo pendiente %s: %s", path, e)
            return False
        if not ok:
            _log.warning("QDesktopServices.openUrl devolvio false al abrir archivo: %s", path)
            return False
        return True

    @Slot(str, result=bool)
    def abrir_directorio(self, ruta_archivo: str) -> bool:
        from PySide6.QtGui import QDesktopServices
        ruta = (ruta_archivo or "").strip()
        if not ruta:
            _log.warning("No se pudo abrir carpeta de pendiente: ruta vacia")
            return False

        path = Path(ruta)
        carpeta = path.parent if path.suffix else path
        if not carpeta.exists():
            _log.warning("No se pudo abrir carpeta de pendiente, no existe: %s", carpeta)
            return False

        try:
            ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(carpeta)))
        except Exception as e:
            _log.warning("No se pudo abrir carpeta de pendiente %s: %s", carpeta, e)
            return False
        if not ok:
            _log.warning("QDesktopServices.openUrl devolvio false al abrir carpeta: %s", carpeta)
            return False
        return True


# =============================================================================
# MODELO DE ESTADISTICAS
# =============================================================================

class ModeloEstadisticas(QObject):
    """Metricas de la coleccion para el dashboard."""

    estadisticasCambiadas = Signal()

    LIMITE_RECIENTES_CANCIONES = 60
    LIMITE_RECIENTES_ALBUMS = 50
    LIMITE_RECIENTES_ARTISTAS = 40
    LIMITE_MAS_ESCUCHADAS_CANCIONES = 60
    LIMITE_MAS_ESCUCHADAS_ALBUMS = 50
    LIMITE_MAS_ESCUCHADAS_ARTISTAS = 40
    LIMITE_MAS_ESCUCHADAS_PLAYLISTS = 50
    LIMITE_PARA_VOLVER = 60
    LIMITE_PLAYLISTS_DESTACADAS = 50
    LIMITE_ALBUMS_QUE_GUSTAN = 40
    LIMITE_RECOMENDACIONES = 60
    LIMITE_NUNCA_ESCUCHADAS = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stats: dict = {}
        self._saludo_inicio = ""
        self._recientes_canciones = ListaGenerica(self)
        self._recientes_albums = ListaGenerica(self)
        self._recientes_artistas = ListaGenerica(self)
        self._mas_escuchadas_canciones = ListaGenerica(self)
        self._mas_escuchadas_albums = ListaGenerica(self)
        self._mas_escuchadas_artistas = ListaGenerica(self)
        self._mas_escuchadas_playlists = ListaGenerica(self)
        self._para_volver = ListaGenerica(self)
        self._playlists_destacadas = ListaGenerica(self)
        self._albums_que_gustan = ListaGenerica(self)
        self._recomendaciones_inicio = ListaGenerica(self)
        self._pistas_nunca_escuchadas = ListaGenerica(self)
        self._pistas_menos_escuchadas = ListaGenerica(self)
        self._estadisticas_perfil: dict = {}

    @Property("QVariant", notify=estadisticasCambiadas)
    def resumen(self) -> dict:
        return self._stats

    @Property(QObject, notify=estadisticasCambiadas)
    def recientes_canciones(self) -> ListaGenerica:
        return self._recientes_canciones

    @Property(QObject, notify=estadisticasCambiadas)
    def recientes_albums(self) -> ListaGenerica:
        return self._recientes_albums

    @Property(QObject, notify=estadisticasCambiadas)
    def recientes_artistas(self) -> ListaGenerica:
        return self._recientes_artistas

    @Property(QObject, notify=estadisticasCambiadas)
    def mas_escuchadas_canciones(self) -> ListaGenerica:
        return self._mas_escuchadas_canciones

    @Property(QObject, notify=estadisticasCambiadas)
    def mas_escuchadas_albums(self) -> ListaGenerica:
        return self._mas_escuchadas_albums

    @Property(QObject, notify=estadisticasCambiadas)
    def mas_escuchadas_artistas(self) -> ListaGenerica:
        return self._mas_escuchadas_artistas

    @Property(QObject, notify=estadisticasCambiadas)
    def mas_escuchadas_playlists(self) -> ListaGenerica:
        return self._mas_escuchadas_playlists

    @Property(QObject, notify=estadisticasCambiadas)
    def para_volver(self) -> ListaGenerica:
        return self._para_volver

    @Property(QObject, notify=estadisticasCambiadas)
    def playlists_destacadas(self) -> ListaGenerica:
        return self._playlists_destacadas

    @Property(QObject, notify=estadisticasCambiadas)
    def albums_que_gustan(self) -> ListaGenerica:
        return self._albums_que_gustan

    @Property(QObject, notify=estadisticasCambiadas)
    def recomendaciones_inicio(self) -> ListaGenerica:
        return self._recomendaciones_inicio

    @Property(QObject, notify=estadisticasCambiadas)
    def pistas_nunca_escuchadas(self) -> ListaGenerica:
        return self._pistas_nunca_escuchadas

    @Property(QObject, notify=estadisticasCambiadas)
    def pistas_menos_escuchadas(self) -> ListaGenerica:
        return self._pistas_menos_escuchadas

    @Property("QVariant", notify=estadisticasCambiadas)
    def estadisticas_perfil(self) -> dict:
        return self._estadisticas_perfil

    @Property(str, notify=estadisticasCambiadas)
    def saludo_inicio(self) -> str:
        return self._saludo_inicio

    @Slot()
    def cargar(self) -> None:
        """Carga todas las métricas del dashboard en background.

        VistaInicio es la primera vista al arrancar la app y ejecuta esta
        función desde `Component.onCompleted`. Antes ejecutaba ~12 queries
        SQL secuenciales en el hilo principal (estadísticas_generales,
        recientes/mas_escuchadas/recomendaciones/etc.), bloqueando la UI
        200-500ms en bibliotecas grandes y dando una sensación de
        congelamiento. Ahora todas las queries corren en un QThread y
        el resultado se aplica en el hilo principal.
        """
        if not hasattr(self, "_ui_worker"):
            self._ui_worker = _UiQueryWorker(self)

        limites = {
            "rec_can": self.LIMITE_RECIENTES_CANCIONES,
            "rec_alb": self.LIMITE_RECIENTES_ALBUMS,
            "rec_art": self.LIMITE_RECIENTES_ARTISTAS,
            "me_can": self.LIMITE_MAS_ESCUCHADAS_CANCIONES,
            "me_alb": self.LIMITE_MAS_ESCUCHADAS_ALBUMS,
            "me_art": self.LIMITE_MAS_ESCUCHADAS_ARTISTAS,
            "me_pl": self.LIMITE_MAS_ESCUCHADAS_PLAYLISTS,
            "para_volver": self.LIMITE_PARA_VOLVER,
            "pl_dest": self.LIMITE_PLAYLISTS_DESTACADAS,
            "alb_gustan": self.LIMITE_ALBUMS_QUE_GUSTAN,
            "reco": self.LIMITE_RECOMENDACIONES,
            "nunca": self.LIMITE_NUNCA_ESCUCHADAS,
        }

        def _consultar():
            try:
                perfil = svc_bib.estadisticas_extras_perfil()
            except Exception:
                perfil = {}
            return {
                "stats": svc_bib.estadisticas_generales(),
                "saludo": saludo_inicio(),
                "rec_can": svc_bib.pistas_recientes(limite=limites["rec_can"]),
                "rec_alb": svc_bib.albums_recientes(limite=limites["rec_alb"]),
                "rec_art": svc_bib.artistas_recientes(limite=limites["rec_art"]),
                "me_can": svc_bib.pistas_mas_escuchadas(limite=limites["me_can"]),
                "me_alb": svc_bib.albums_mas_escuchados(limite=limites["me_alb"]),
                "me_art": svc_bib.artistas_mas_escuchados(limite=limites["me_art"]),
                "me_pl": svc_bib.playlists_mas_escuchadas(limite=limites["me_pl"]),
                "para_volver": svc_bib.pistas_para_volver(limite=limites["para_volver"]),
                "pl_dest": svc_bib.playlists_destacadas(limite=limites["pl_dest"]),
                "alb_gustan": svc_bib.albums_con_canciones_que_gustan(limite=limites["alb_gustan"]),
                "reco": svc_bib.recomendaciones_inicio(limite=limites["reco"]),
                "nunca": svc_bib.pistas_nunca_escuchadas(limite=limites["nunca"]),
                "menos": svc_bib.pistas_menos_escuchadas(limite=limites["nunca"]),
                "perfil": perfil,
            }

        self._ui_worker.run(_consultar, self._aplicar_estadisticas)

    def _aplicar_estadisticas(self, resultado) -> None:
        if resultado is None:
            self._stats = {}
            self._saludo_inicio = ""
            self._estadisticas_perfil = {}
            self.estadisticasCambiadas.emit()
            return
        self._stats = resultado.get("stats") or {}
        self._saludo_inicio = resultado.get("saludo") or ""
        self._recientes_canciones.set_datos(self._normalizar_portadas(resultado.get("rec_can") or []))
        self._recientes_albums.set_datos(self._normalizar_portadas(resultado.get("rec_alb") or []))
        self._recientes_artistas.set_datos(self._normalizar_portadas(resultado.get("rec_art") or []))
        self._mas_escuchadas_canciones.set_datos(self._normalizar_portadas(resultado.get("me_can") or []))
        self._mas_escuchadas_albums.set_datos(self._normalizar_portadas(resultado.get("me_alb") or []))
        self._mas_escuchadas_artistas.set_datos(self._normalizar_portadas(resultado.get("me_art") or []))
        self._mas_escuchadas_playlists.set_datos(self._normalizar_portadas(resultado.get("me_pl") or []))
        self._para_volver.set_datos(self._normalizar_portadas(resultado.get("para_volver") or []))
        self._playlists_destacadas.set_datos(self._normalizar_portadas(resultado.get("pl_dest") or []))
        self._albums_que_gustan.set_datos(self._normalizar_portadas(resultado.get("alb_gustan") or []))
        self._recomendaciones_inicio.set_datos(self._normalizar_portadas(resultado.get("reco") or []))
        self._pistas_nunca_escuchadas.set_datos(self._normalizar_portadas(resultado.get("nunca") or []))
        self._pistas_menos_escuchadas.set_datos(self._normalizar_portadas(resultado.get("menos") or []))
        self._estadisticas_perfil = resultado.get("perfil") or {}
        self.estadisticasCambiadas.emit()

    def _normalizar_portadas(self, filas: list[dict]) -> list[dict]:
        out: list[dict] = []
        for fila in filas:
            item = dict(fila)
            for clave in ("portada_ruta", "portada_display_ruta", "portada_thumb_ruta"):
                item[clave] = self._normalizar_ruta_portada(item.get(clave))
            portadas = item.get("portadas")
            if isinstance(portadas, (list, tuple)):
                item["portadas"] = [
                    normalizada
                    for portada in portadas
                    if (normalizada := self._normalizar_ruta_portada(portada))
                ]
            out.append(item)
        return out

    def _normalizar_ruta_portada(self, portada) -> str:
        if not portada:
            return ""
        texto = str(portada)
        if "://" not in texto:
            texto = QUrl.fromLocalFile(texto).toString()
        return texto

    @Slot(str)
    def actualizar_saludo(self, nombre_usuario: str) -> None:
        self._saludo_inicio = saludo_inicio(nombre_usuario)
        self.estadisticasCambiadas.emit()

    @Slot(float, result=str)
    def formatear_duracion(self, segundos: float) -> str:
        """Formatea duracion total de la biblioteca (horas:minutos)."""
        if not segundos:
            return "0h 0m"
        horas   = int(segundos) // 3600
        minutos = (int(segundos) % 3600) // 60
        return f"{horas}h {minutos}m"

    @Slot(float, result=str)
    def formatear_duracion_detallada(self, segundos: float) -> str:
        """Etiqueta compacta con solo unidades distintas de cero: '2d 3h 1m 4s'."""
        try:
            total = int(max(0.0, float(segundos or 0.0)))
        except (TypeError, ValueError):
            total = 0
        if total <= 0:
            return "0s"
        dias = total // 86400
        resto = total % 86400
        horas = resto // 3600
        resto %= 3600
        minutos = resto // 60
        segs = resto % 60
        partes: list[str] = []
        if dias:
            partes.append(f"{dias}d")
        if horas:
            partes.append(f"{horas}h")
        if minutos:
            partes.append(f"{minutos}m")
        if segs:
            partes.append(f"{segs}s")
        return " ".join(partes) if partes else "0s"


# =============================================================================
# MODELO DE PLAYLISTS
# =============================================================================

class ModeloPlaylists(QObject):
    """Puente QML para playlists manuales, de sistema y automaticas locales."""

    playlistsCambiadas = Signal()
    pistasPlaylistCambiadas = Signal()
    playlistActivaCambiada = Signal()
    resultadosAgregarCambiados = Signal()
    estadoCambiado = Signal()
    errorCambiado = Signal(str)
    # Emitida tras el barrido de aseguramiento de carátulas (al arrancar) con la
    # lista de IDs cuya carátula se (re)generó. El contenedor la usa para
    # refrescar también Inicio. No se emite si no hubo cambios.
    portadasAseguradas = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._playlists       = ListaGenerica(self)
        self._pistas_activas  = ListaGenerica(self)
        self._resultados_agregar = ListaGenerica(self)
        self._playlist_activa_id: Optional[int] = None
        self._playlist_activa: dict = {}
        self._estado = ""
        self._error = ""
        self._worker_busqueda_playlist = None
        self._workers_busqueda_playlist_obsoletos = []
        self._request_seq_busqueda_playlist = 0
        self._active_request_seq_busqueda_playlist = 0

    def conectar_biblioteca(self, modelo_biblioteca: "ModeloBiblioteca") -> None:
        """Conecta señales del modelo de biblioteca para mantener la playlist
        'Me gusta' sincronizada cuando el usuario marca/desmarca favoritas
        desde cualquier vista (Búsqueda, Biblioteca, Explorador Ciego)."""
        try:
            modelo_biblioteca.favoritaCambiada.connect(self._al_cambiar_favorita)
        except Exception as exc:
            _log.warning("No se pudo conectar Playlists ↔ Biblioteca: %s", exc)

    @Slot(int, bool)
    def _al_cambiar_favorita(self, pista_id: int, es_favorita: bool) -> None:
        """Refresca la playlist 'Me gusta' y, si está abierta, sus pistas."""
        try:
            self.cargar()
        except Exception as exc:
            _log.debug("Recarga lista playlists tras favorita falló: %s", exc)
        # Si la playlist activa es la de Favoritos, recargar sus pistas
        activa_id = self._playlist_activa_id
        activa = self._playlist_activa or {}
        if activa_id and (activa.get("tipo_playlist") == "favoritos"
                          or activa.get("subtipo") == "favoritos"):
            try:
                self.abrir_playlist(int(activa_id))
            except Exception as exc:
                _log.debug("Recarga pistas playlist favoritos falló: %s", exc)

    def _normalizar_ruta_portada(self, portada) -> str:
        if not portada:
            return ""
        texto = str(portada)
        if "://" not in texto:
            texto = QUrl.fromLocalFile(texto).toString()
        return texto

    def _normalizar_item(self, item: dict) -> dict:
        normalizado = dict(item)
        for clave in (
            "portada_ruta",
            "portada_display_ruta",
            "portada_thumb_ruta",
            "album_portada_ruta",
        ):
            if clave in normalizado:
                normalizado[clave] = self._normalizar_ruta_portada(normalizado.get(clave))
        portadas = normalizado.get("portadas")
        if isinstance(portadas, (list, tuple)):
            normalizado["portadas"] = [
                ruta
                for portada in portadas
                if (ruta := self._normalizar_ruta_portada(portada))
            ]
        return normalizado

    def _normalizar_lista(self, filas: list[dict]) -> list[dict]:
        return [self._normalizar_item(fila) for fila in filas]

    def _set_estado(self, mensaje: str = "", error: str = "") -> None:
        self._estado = mensaje
        self._error = error
        self.estadoCambiado.emit()
        if error:
            self.errorCambiado.emit(error)

    def _ok(self, mensaje: str = "", **extra) -> dict:
        self._set_estado(mensaje, "")
        return {"ok": True, "mensaje": mensaje, **extra}

    def _ok_desde_servicio(self, resultado: dict, mensaje_default: str) -> dict:
        payload = dict(resultado or {})
        mensaje = str(payload.pop("mensaje", "") or mensaje_default)
        ok = bool(payload.pop("ok", True))
        if ok:
            return self._ok(mensaje, **payload)
        self._set_estado("", mensaje)
        return {"ok": False, "mensaje": mensaje, **payload}

    def _fallo(self, exc: Exception, mensaje: str = "No se pudo completar la accion") -> dict:
        texto = str(exc).strip() or mensaje
        _log.warning("Operacion de playlists fallida: %s", texto)
        self._set_estado("", texto)
        return {"ok": False, "mensaje": texto}

    def _refrescar_activa_si_corresponde(self, playlist_id: int) -> None:
        if self._playlist_activa_id == playlist_id:
            self.abrir_playlist(playlist_id)

    def _actualizar_playlist_en_lista(self, playlist_id: int) -> None:
        try:
            detalle = svc_bib.detalle_playlist(int(playlist_id or 0))
        except Exception as exc:
            _log.warning("No se pudo actualizar playlist %s en modelo: %s", playlist_id, exc)
            return
        datos = self._playlists.snapshot()
        reemplazada = False
        salida: list[dict] = []
        if detalle:
            detalle_limpio = dict(detalle)
            detalle_limpio.pop("pistas", None)
            item = self._normalizar_item(detalle_limpio)
        else:
            item = None
        for fila in datos:
            fila_id = int((fila or {}).get("playlist_id") or (fila or {}).get("id") or 0)
            if fila_id == int(playlist_id or 0):
                reemplazada = True
                if item:
                    salida.append(item)
                continue
            salida.append(fila)
        if item and not reemplazada:
            salida.append(item)
        self._playlists.set_datos(salida)
        self.playlistsCambiadas.emit()

    def _quitar_playlist_de_lista(self, playlist_id: int) -> None:
        datos = [
            fila for fila in self._playlists.snapshot()
            if int((fila or {}).get("playlist_id") or (fila or {}).get("id") or 0) != int(playlist_id or 0)
        ]
        self._playlists.set_datos(datos)
        self.playlistsCambiadas.emit()

    def _archivar_worker_busqueda_playlist(self, worker) -> None:
        try:
            worker.resultados.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            worker.error.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            worker.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        worker.requestInterruption()
        self._workers_busqueda_playlist_obsoletos.append(worker)

        def _limpiar_worker_obsoleto(w=worker):
            try:
                self._workers_busqueda_playlist_obsoletos.remove(w)
            except ValueError:
                pass
            w.deleteLater()

        worker.finished.connect(_limpiar_worker_obsoleto)

    def _al_recibir_resultados_agregar(self, resultados: list, request_id: int) -> None:
        if request_id != self._active_request_seq_busqueda_playlist:
            return
        self._resultados_agregar.set_datos(self._normalizar_lista(list(resultados or [])))
        self.resultadosAgregarCambiados.emit()

    def _al_error_busqueda_agregar(self, mensaje: str, request_id: int) -> None:
        if request_id != self._active_request_seq_busqueda_playlist:
            return
        self._fallo(RuntimeError(mensaje), "No se pudo buscar en la biblioteca")

    def _al_finalizar_busqueda_agregar(self, worker, request_id: int) -> None:
        if request_id == self._active_request_seq_busqueda_playlist and self._worker_busqueda_playlist is worker:
            self._worker_busqueda_playlist = None
        worker.deleteLater()

    @Property(QObject, notify=playlistsCambiadas)
    def playlists(self) -> ListaGenerica:
        return self._playlists

    @Property(QObject, notify=pistasPlaylistCambiadas)
    def pistas_activas(self) -> ListaGenerica:
        return self._pistas_activas

    @Property(QObject, notify=resultadosAgregarCambiados)
    def resultados_agregar(self) -> ListaGenerica:
        return self._resultados_agregar

    @Property(int, notify=playlistActivaCambiada)
    def playlist_activa_id(self) -> int:
        return self._playlist_activa_id or -1

    @Property("QVariant", notify=playlistActivaCambiada)
    def playlist_activa(self) -> dict:
        return self._playlist_activa

    @Property(str, notify=estadoCambiado)
    def estado(self) -> str:
        return self._estado

    @Property(str, notify=estadoCambiado)
    def error(self) -> str:
        return self._error

    @Slot()
    def cargar(self) -> None:
        # `svc_bib.listar_playlists` recorre la tabla `playlists` + agregados
        # de portadas, lo que se nota en bibliotecas grandes. Lo movemos a
        # un QThread para que abrir "Playlists" por primera vez no
        # congele la UI. Si la query falla, se emite mensaje de error en
        # el thread principal vía `_aplicar_cargar`.
        if not hasattr(self, "_ui_worker"):
            self._ui_worker = _UiQueryWorker(self)
        self._ui_worker.run(svc_bib.listar_playlists, self._aplicar_cargar)

    def _aplicar_cargar(self, datos) -> None:
        if datos is None:
            self._fallo(RuntimeError("query falló"), "No se pudieron cargar las playlists")
            return
        self._playlists.set_datos(self._normalizar_lista(datos))
        self.playlistsCambiadas.emit()

    @Slot()
    def asegurar_portadas_async(self) -> None:
        """Red de seguridad de carátulas: en background regenera las carátulas
        de las playlists que falten o estén obsoletas (mosaico de las portadas
        de sus canciones) y, si hubo cambios, refresca la lista de Playlists.

        Emite `portadasAseguradas(ids)` para que el contenedor refresque también
        Inicio. Pensada para dispararse al arrancar la app: asegura que toda
        playlist tenga su carátula "hecha" aunque se creara sin canciones con
        portada o se editara por una vía que no la regeneró.
        """
        if not hasattr(self, "_ui_worker"):
            self._ui_worker = _UiQueryWorker(self)
        self._ui_worker.run(
            svc_bib.asegurar_portadas_playlists,
            self._aplicar_asegurar_portadas,
        )

    def _aplicar_asegurar_portadas(self, actualizadas) -> None:
        ids = [int(i) for i in (actualizadas or []) if i]
        if not ids:
            return
        # Recargar la lista para que las nuevas carátulas se reflejen en la vista
        # de Playlists; `portadasAseguradas` deja que el contenedor refresque Inicio.
        self.cargar()
        self.portadasAseguradas.emit(ids)

    @Slot(int)
    def abrir_playlist(self, playlist_id: int) -> None:
        # Lo mismo para detalle: si la playlist tiene cientos de pistas,
        # `detalle_playlist` puede tardar. Background + aplicar en main.
        if not hasattr(self, "_ui_worker"):
            self._ui_worker = _UiQueryWorker(self)
        def _consultar():
            return (playlist_id, svc_bib.detalle_playlist(playlist_id))
        self._ui_worker.run(_consultar, self._aplicar_abrir_playlist)

    def _aplicar_abrir_playlist(self, resultado) -> None:
        if resultado is None:
            self._fallo(RuntimeError("query falló"), "No se pudo abrir la playlist")
            return
        playlist_id, detalle = resultado
        pistas = self._normalizar_lista(detalle.pop("pistas", []))
        self._playlist_activa_id = int(detalle.get("playlist_id") or playlist_id)
        self._playlist_activa = self._normalizar_item(detalle)
        self._pistas_activas.set_datos(pistas)
        self.pistasPlaylistCambiadas.emit()
        self.playlistActivaCambiada.emit()

    @Slot(int, result="QVariantList")
    def pistas_de_playlist(self, playlist_id: int) -> list:
        """Devuelve las pistas de una playlist de forma SÍNCRONA.

        El botón de reproducir de las tarjetas lo usa para sonar al instante
        con un solo clic: `abrir_playlist` carga las pistas en un worker
        asíncrono, por lo que reproducir justo después leía una lista vacía y
        obligaba a un segundo clic. Aquí se consulta directamente la playlist
        objetivo, sin depender del estado de la playlist activa.
        """
        try:
            pistas = svc_bib.pistas_de_playlist(int(playlist_id or 0))
        except Exception as exc:
            _log.warning("pistas_de_playlist falló: %s", exc)
            return []
        return self._normalizar_lista(pistas)

    @Slot(str, result="QVariantMap")
    @Slot(str, str, result="QVariantMap")
    def crear_playlist(self, nombre: str, descripcion: str = "") -> dict:
        try:
            playlist_id = svc_bib.crear_playlist(nombre, descripcion)
            self.cargar()
            self.abrir_playlist(playlist_id)
            return self._ok("Playlist creada", playlist_id=playlist_id)
        except Exception as exc:
            return self._fallo(exc, "No se pudo crear la playlist")

    @Slot(int, str, result="QVariantMap")
    def renombrar_playlist(self, playlist_id: int, nombre: str) -> dict:
        try:
            svc_bib.renombrar_playlist(playlist_id, nombre)
            self._actualizar_playlist_en_lista(playlist_id)
            self._refrescar_activa_si_corresponde(playlist_id)
            return self._ok("Nombre actualizado")
        except Exception as exc:
            return self._fallo(exc, "No se pudo renombrar la playlist")

    @Slot(int, str, result="QVariantMap")
    def editar_descripcion_playlist(self, playlist_id: int, descripcion: str) -> dict:
        try:
            svc_bib.editar_descripcion_playlist(playlist_id, descripcion)
            self._actualizar_playlist_en_lista(playlist_id)
            self._refrescar_activa_si_corresponde(playlist_id)
            return self._ok("Descripción actualizada")
        except Exception as exc:
            return self._fallo(exc, "No se pudo actualizar la descripción")

    @Slot(int, result="QVariantMap")
    def eliminar_playlist(self, playlist_id: int) -> dict:
        try:
            resultado = svc_bib.eliminar_playlist(playlist_id)
            if self._playlist_activa_id == playlist_id:
                self._playlist_activa_id = None
                self._playlist_activa = {}
                self._pistas_activas.set_datos([])
                self.pistasPlaylistCambiadas.emit()
                self.playlistActivaCambiada.emit()
            self._quitar_playlist_de_lista(playlist_id)
            return self._ok_desde_servicio(resultado, "Playlist eliminada")
        except Exception as exc:
            return self._fallo(exc, "No se pudo eliminar la playlist")

    @Slot(int, int, result="QVariantMap")
    def agregar_pista(self, playlist_id: int, pista_id: int) -> dict:
        try:
            resultado = svc_bib.agregar_a_playlist(playlist_id, pista_id)
            self._refrescar_activa_si_corresponde(playlist_id)
            self._actualizar_playlist_en_lista(playlist_id)
            return self._ok_desde_servicio(resultado, "Canción agregada")
        except Exception as exc:
            return self._fallo(exc, "No se pudo agregar la canción")

    @Slot(int, int, result="QVariantMap")
    def quitar_pista(self, playlist_id: int, pista_id: int) -> dict:
        try:
            resultado = svc_bib.quitar_de_playlist(playlist_id, pista_id)
            self._refrescar_activa_si_corresponde(playlist_id)
            self._actualizar_playlist_en_lista(playlist_id)
            return self._ok_desde_servicio(resultado, "Canción quitada")
        except Exception as exc:
            return self._fallo(exc, "No se pudo quitar la canción")

    @Slot(int, result="QVariant")
    def playlists_para_pista(self, pista_id: int) -> list:
        """Playlists manuales del usuario con su estado de pertenencia.

        Alimenta el selector "agregar a playlist" (estilo Spotify): devuelve
        ``[{playlist_id, nombre, num_pistas, contiene}, ...]``. Consulta
        síncrona y barata (el número de playlists manuales es pequeño).
        """
        try:
            return svc_bib.playlists_editables_para_pista(int(pista_id or 0))
        except Exception as exc:
            _log.warning("playlists_para_pista falló: %s", exc)
            return []

    @Slot(int, "QVariant", "QVariant", result="QVariantMap")
    def aplicar_en_playlists(self, pista_id, ids_agregar, ids_quitar) -> dict:
        """Aplica de una sola vez los cambios de pertenencia de una pista.

        ``ids_agregar`` / ``ids_quitar`` son listas de playlist_id. Se ejecuta
        el diff calculado por el selector y se refresca la UI una sola vez
        (lista + playlist activa si fue tocada), evitando el parpadeo de
        llamar `agregar_pista`/`quitar_pista` en bucle.
        """
        try:
            if isinstance(ids_agregar, QJSValue):
                ids_agregar = ids_agregar.toVariant()
            if isinstance(ids_quitar, QJSValue):
                ids_quitar = ids_quitar.toVariant()
            agregar = [int(x) for x in (ids_agregar or []) if x is not None]
            quitar = [int(x) for x in (ids_quitar or []) if x is not None]
            pid = int(pista_id or 0)

            agregadas = 0
            quitadas = 0
            for playlist_id in agregar:
                resultado = svc_bib.agregar_a_playlist(playlist_id, pid)
                if resultado.get("ok"):
                    agregadas += 1
            for playlist_id in quitar:
                resultado = svc_bib.quitar_de_playlist(playlist_id, pid)
                if resultado.get("ok"):
                    quitadas += 1

            tocadas = set(agregar) | set(quitar)
            if tocadas:
                self.cargar()
                for playlist_id in tocadas:
                    self._actualizar_playlist_en_lista(playlist_id)
                if self._playlist_activa_id in tocadas:
                    self._refrescar_activa_si_corresponde(self._playlist_activa_id)

            if agregadas and quitadas:
                mensaje = "Playlists actualizadas"
            elif agregadas:
                mensaje = f"Añadida a {agregadas} playlist" + ("s" if agregadas != 1 else "")
            elif quitadas:
                mensaje = f"Quitada de {quitadas} playlist" + ("s" if quitadas != 1 else "")
            else:
                mensaje = "Sin cambios"
            return self._ok(mensaje, agregadas=agregadas, quitadas=quitadas)
        except Exception as exc:
            return self._fallo(exc, "No se pudieron actualizar las playlists")

    @Slot(str, result="QVariantMap")
    def crear_playlist_para_seleccion(self, nombre: str) -> dict:
        """Crea una playlist manual sin cambiar la playlist activa.

        Variante de :meth:`crear_playlist` para el selector "agregar a
        playlist": no abre la nueva playlist (no toca `playlist_activa`),
        solo refresca la lista y devuelve el id para pre-seleccionarla.
        """
        try:
            playlist_id = svc_bib.crear_playlist(nombre)
            self.cargar()
            return self._ok("Playlist creada", playlist_id=int(playlist_id))
        except Exception as exc:
            return self._fallo(exc, "No se pudo crear la playlist")

    @Slot(int, result="QVariantMap")
    def vaciar_playlist(self, playlist_id: int) -> dict:
        try:
            resultado = svc_bib.vaciar_playlist(playlist_id)
            self._refrescar_activa_si_corresponde(playlist_id)
            self._actualizar_playlist_en_lista(playlist_id)
            return self._ok_desde_servicio(resultado, "Playlist vaciada")
        except Exception as exc:
            return self._fallo(exc, "No se pudo vaciar la playlist")

    @Slot(int, int, int, result="QVariantMap")
    def reordenar_playlist(self, playlist_id: int, pista_id: int, nueva_posicion: int) -> dict:
        try:
            resultado = svc_bib.reordenar_playlist(playlist_id, pista_id, nueva_posicion)
            self._refrescar_activa_si_corresponde(playlist_id)
            return self._ok_desde_servicio(resultado, "Orden actualizado")
        except Exception as exc:
            return self._fallo(exc, "No se pudo reordenar la playlist")

    @Slot(int, "QVariant", result="QVariantMap")
    def reordenar_playlist_completa(self, playlist_id: int, pista_ids) -> dict:
        try:
            if isinstance(pista_ids, QJSValue):
                pista_ids = pista_ids.toVariant()
            resultado = svc_bib.reordenar_playlist_completa(playlist_id, list(pista_ids or []))
            self._refrescar_activa_si_corresponde(playlist_id)
            return self._ok_desde_servicio(resultado, "Orden actualizado")
        except Exception as exc:
            return self._fallo(exc, "No se pudo reordenar la playlist")

    @Slot(int, result="QVariantMap")
    def duplicar_playlist(self, playlist_id: int) -> dict:
        _log.info("ModeloPlaylists.duplicar_playlist: src_id=%s", playlist_id)
        try:
            resultado = svc_bib.duplicar_playlist(playlist_id)
            _log.info("ModeloPlaylists.duplicar_playlist: svc retorno=%s",
                      {k: resultado.get(k) for k in ("ok", "playlist_id", "mensaje")})
            if not resultado.get("ok"):
                return self._ok_desde_servicio(resultado, "No se pudo duplicar la playlist")
            nueva_id = int(resultado.get("playlist_id") or 0)

            # Sincronización inmediata para que el QML vea la duplicada
            # ANTES de que `asegurarSeleccion()` corra y la mande a Me
            # gusta como fallback:
            #
            #   1. Añadir la nueva entrada a `_playlists` (síncrono +
            #      emite `playlistsCambiadas`).
            #   2. Marcar la nueva como activa (emite
            #      `playlistActivaCambiada`).
            #
            # `cargar()` y `abrir_playlist()` siguen disparándose async
            # para que la lista se refresque desde BD (por si hay
            # campos derivados) y se carguen las pistas de la nueva,
            # pero la UI ya no depende de su completado.
            if nueva_id:
                self._actualizar_playlist_en_lista(nueva_id)
                self._playlist_activa_id = nueva_id
                self.playlistActivaCambiada.emit()
            self.cargar()
            if nueva_id:
                self.abrir_playlist(nueva_id)
            return self._ok_desde_servicio(resultado, "Playlist duplicada")
        except Exception as exc:
            _log.exception("ModeloPlaylists.duplicar_playlist excepcion: src_id=%s", playlist_id)
            return self._fallo(exc, "No se pudo duplicar la playlist")

    @Slot(int, bool, result="QVariantMap")
    def anclar_playlist(self, playlist_id: int, anclada: bool) -> dict:
        try:
            resultado = svc_bib.anclar_playlist(playlist_id, bool(anclada))
            self._actualizar_playlist_en_lista(playlist_id)
            self._refrescar_activa_si_corresponde(playlist_id)
            return self._ok_desde_servicio(resultado, "Playlist actualizada")
        except Exception as exc:
            return self._fallo(exc, "No se pudo actualizar el anclado")

    @Slot(str)
    @Slot(str, int)
    def buscar_pistas_para_playlist(self, query: str, playlist_id: int = -1) -> None:
        self._request_seq_busqueda_playlist += 1
        request_id = self._request_seq_busqueda_playlist
        self._active_request_seq_busqueda_playlist = request_id
        pid = playlist_id if playlist_id and playlist_id > 0 else self.playlist_activa_id

        if QCoreApplication.instance() is None:
            try:
                resultados = svc_bib.buscar_pistas_para_playlist(
                    query,
                    pid if pid > 0 else None,
                    limite=50,
                )
                self._al_recibir_resultados_agregar(list(resultados or []), request_id)
            except Exception as exc:
                self._al_error_busqueda_agregar(str(exc), request_id)
            return

        from workers.workers_qt import WorkerBusquedaPlaylist

        if self._worker_busqueda_playlist and self._worker_busqueda_playlist.isRunning():
            self._archivar_worker_busqueda_playlist(self._worker_busqueda_playlist)
            self._worker_busqueda_playlist = None

        self._worker_busqueda_playlist = WorkerBusquedaPlaylist(query, pid if pid > 0 else -1, limite=50, parent=self)
        self._worker_busqueda_playlist.resultados.connect(
            lambda resultados, rid=request_id: self._al_recibir_resultados_agregar(resultados, rid)
        )
        self._worker_busqueda_playlist.error.connect(
            lambda mensaje, rid=request_id: self._al_error_busqueda_agregar(mensaje, rid)
        )
        self._worker_busqueda_playlist.finished.connect(
            lambda w=self._worker_busqueda_playlist, rid=request_id: self._al_finalizar_busqueda_agregar(w, rid)
        )
        self._worker_busqueda_playlist.start()

    @Slot(result="QVariantMap")
    @Slot(int, result="QVariantMap")
    def sincronizar_inteligentes(self, limite_creacion: int = 4) -> dict:
        try:
            resultado = svc_bib.sincronizar_playlists_sistema(limite_creacion)
            self.cargar()
            if self._playlist_activa_id:
                self._refrescar_activa_si_corresponde(self._playlist_activa_id)
            return self._ok_desde_servicio(resultado, "Playlists actualizadas")
        except Exception as exc:
            return self._fallo(exc, "No se pudieron actualizar las playlists")

    @Slot()
    @Slot(int)
    def sincronizar_inteligentes_async(self, limite_creacion: int = 0) -> None:
        """Versión fire-and-forget de :meth:`sincronizar_inteligentes`.

        Pensada para invocarse desde `Component.onCompleted` de
        VistaPlaylists: la sincronización recorre toda la biblioteca y
        congelaba la UI al abrir la vista. Aquí movemos la lógica a un
        ``_UiQueryWorker`` y aplicamos el resultado (recargar lista +
        refrescar playlist activa) en el hilo principal cuando termina.
        Si falla, log y se queda como está; no devuelve nada.
        """
        if not hasattr(self, "_ui_worker"):
            self._ui_worker = _UiQueryWorker(self)

        def _consultar():
            try:
                return svc_bib.sincronizar_playlists_sistema(int(limite_creacion or 0))
            except Exception as exc:
                _log.warning("sincronizar_inteligentes_async: %s", exc)
                return None

        def _aplicar(resultado) -> None:
            self.cargar()
            if self._playlist_activa_id:
                self._refrescar_activa_si_corresponde(self._playlist_activa_id)

        self._ui_worker.run(_consultar, _aplicar)

    @Slot(int, result="QVariantMap")
    def regenerar_playlist(self, playlist_id: int) -> dict:
        try:
            resultado = svc_bib.regenerar_playlist_automatica(playlist_id)
            self.cargar()
            self._refrescar_activa_si_corresponde(playlist_id)
            return self._ok_desde_servicio(resultado, "Playlist regenerada")
        except Exception as exc:
            return self._fallo(exc, "No se pudo regenerar la playlist")

    def cerrar(self) -> None:
        """Interrumpe workers de busqueda playlist al cerrar la app."""
        workers = [self._worker_busqueda_playlist,
                   *self._workers_busqueda_playlist_obsoletos]
        for w in workers:
            if w is None:
                continue
            try:
                if w.isRunning():
                    w.requestInterruption()
            except RuntimeError:
                continue
            except Exception as exc:
                _log.debug("requestInterruption playlist fallo: %s", exc)
        for w in workers:
            if w is None:
                continue
            try:
                if w.isRunning():
                    w.wait(500)
            except RuntimeError:
                continue
            except Exception as exc:
                _log.debug("wait playlist fallo: %s", exc)


# =============================================================================
# MODELO DE CONFIGURACION
# =============================================================================

class ModeloTema(QObject):
    """Sistema de temas UI centralizado y reactivo para QML."""

    temaCambiado = Signal()

    _TEMAS = {
        "negro_puro": {
            "nombre": "Negro Puro (OLED)",
            "fondo": "#000000",
            "fondoElevado": "#0a0a0a",
            "superficie": "#121212",
            "superficieAlt": "#1a1a1a",
            "borde": "#2a2a2a",
            "texto": "#ffffff",
            "textoSec": "#b0b0b0",
            "textoMuted": "#787878",
            "acento": "#00e5ff",
            "acentoFuerte": "#00c8e0",
            "hover": "#1f1f1f",
            "seleccion": "#2a2a2a",
            "exito": "#00ff88",
            "peligro": "#ff4757",
            "advertencia": "#ffa502",
        },
        "arcilla_nocturna": {
            "nombre": "Arcilla Nocturna",
            "fondo": "#1a1613",
            "fondoElevado": "#221d19",
            "superficie": "#2a2420",
            "superficieAlt": "#352e28",
            "borde": "#483f37",
            "texto": "#f4f1ea",
            "textoSec": "#cabfb0",
            "textoMuted": "#968b7c",
            "acento": "#e07a52",
            "acentoFuerte": "#c15f3c",
            "hover": "#38302a",
            "seleccion": "#443a32",
            "exito": "#6cc28d",
            "peligro": "#ff6f5e",
            "advertencia": "#f0b45a",
        },
        "arcilla_calida": {
            "nombre": "Arcilla Cálida",
            "fondo": "#f4f3ee",
            "fondoElevado": "#faf9f4",
            "superficie": "#ffffff",
            "superficieAlt": "#ebe9e1",
            "borde": "#b1ada1",
            "texto": "#2a2520",
            "textoSec": "#5c5447",
            "textoMuted": "#8a8273",
            "acento": "#c15f3c",
            "acentoFuerte": "#a54b2c",
            "hover": "#ebe8df",
            "seleccion": "#e3ded2",
            "exito": "#5a9b6a",
            "peligro": "#d23b3b",
            "advertencia": "#c98a2e",
        },
        "oro_liquido": {
            "nombre": "Oro Líquido",
            "fondo": "#0d0d0d",
            "fondoElevado": "#15110a",
            "superficie": "#1d1709",
            "superficieAlt": "#241c0a",
            "borde": "#735809",
            "texto": "#ffffff",
            "textoSec": "#d8cfbf",
            "textoMuted": "#9c917a",
            "acento": "#f2b90f",
            "acentoFuerte": "#f2a30f",
            "hover": "#2a1d04",
            "seleccion": "#402b05",
            "exito": "#6fd49a",
            "peligro": "#ff6b5e",
            "advertencia": "#ffcf5a",
        },
        "oscuro_profundo": {
            "nombre": "Abismo Profundo",
            "fondo": "#050505",
            "fondoElevado": "#0d0d0d",
            "superficie": "#141414",
            "superficieAlt": "#1c1c1c",
            "borde": "#2d2d2d",
            "texto": "#fafafa",
            "textoSec": "#a8a8a8",
            "textoMuted": "#707070",
            "acento": "#4fc3f7",
            "acentoFuerte": "#29b6f6",
            "hover": "#1e1e1e",
            "seleccion": "#282828",
            "exito": "#66bb6a",
            "peligro": "#ef5350",
            "advertencia": "#ffa726",
        },
        "electrico_voltaje": {
            "nombre": "Voltaje Azul",
            "fondo": "#03040a",
            "fondoElevado": "#080a1f",
            "superficie": "#0d1138",
            "superficieAlt": "#151a52",
            "borde": "#3d56b5",
            "texto": "#f5f7ff",
            "textoSec": "#c7d4ff",
            "textoMuted": "#9ab0f0",
            "acento": "#00f0ff",
            "acentoFuerte": "#00d4e8",
            "hover": "#2a3575",
            "seleccion": "#364594",
            "exito": "#64ffda",
            "peligro": "#ff5e7a",
            "advertencia": "#ffd966",
        },
        "lima_suave": {
            "nombre": "Lima Láser",
            "fondo": "#060b06",
            "fondoElevado": "#0c160c",
            "superficie": "#142414",
            "superficieAlt": "#1c331c",
            "borde": "#356b35",
            "texto": "#e8f5e8",
            "textoSec": "#a8cfa8",
            "textoMuted": "#76a376",
            "acento": "#7fff7f",
            "acentoFuerte": "#5ce65c",
            "hover": "#254525",
            "seleccion": "#2f572f",
            "exito": "#8aff9f",
            "peligro": "#ff7a8a",
            "advertencia": "#ffe082",
        },
        "carmesi_nocturno": {
            "nombre": "Carmesí Nocturno",
            "fondo": "#0f0507",
            "fondoElevado": "#1a090e",
            "superficie": "#26111a",
            "superficieAlt": "#331623",
            "borde": "#5a2d3a",
            "texto": "#fceef2",
            "textoSec": "#d4b5c0",
            "textoMuted": "#a68691",
            "acento": "#ff4d73",
            "acentoFuerte": "#e6385e",
            "hover": "#42212e",
            "seleccion": "#552a3a",
            "exito": "#66e09a",
            "peligro": "#ff7b7b",
            "advertencia": "#ffc985",
        },
        "aurora_boreal": {
            "nombre": "Aurora Boreal",
            "fondo": "#040c1a",
            "fondoElevado": "#0a1529",
            "superficie": "#111f3d",
            "superficieAlt": "#192e59",
            "borde": "#3a5a99",
            "texto": "#ebf3ff",
            "textoSec": "#b8d0f5",
            "textoMuted": "#8ba8cf",
            "acento": "#4db8ff",
            "acentoFuerte": "#2aa3f0",
            "hover": "#23457a",
            "seleccion": "#2d5694",
            "exito": "#5ae0bf",
            "peligro": "#ff7a96",
            "advertencia": "#ffd782",
        },
        "selva_neon": {
            "nombre": "Selva Neón",
            "fondo": "#07120d",
            "fondoElevado": "#0d1f16",
            "superficie": "#153224",
            "superficieAlt": "#1d4230",
            "borde": "#3a755a",
            "texto": "#e6fff5",
            "textoSec": "#b0e5cb",
            "textoMuted": "#82b89e",
            "acento": "#5effb3",
            "acentoFuerte": "#45e69f",
            "hover": "#2a5a42",
            "seleccion": "#356f52",
            "exito": "#7affbf",
            "peligro": "#ff8296",
            "advertencia": "#ffe08a",
        },
        "crepusculo_violeta": {
            "nombre": "Crepúsculo Violeta",
            "fondo": "#150d1a",
            "fondoElevado": "#201429",
            "superficie": "#2d1b3a",
            "superficieAlt": "#3b234d",
            "borde": "#634078",
            "texto": "#ffeaff",
            "textoSec": "#dfc0ea",
            "textoMuted": "#b090c0",
            "acento": "#d77dff",
            "acentoFuerte": "#b957e8",
            "hover": "#4a2f59",
            "seleccion": "#5a3a6b",
            "exito": "#7edfb5",
            "peligro": "#ff7fa2",
            "advertencia": "#ffd982",
        },
        "cobalto_night": {
            "nombre": "Cobalto Nocturno",
            "fondo": "#060a17",
            "fondoElevado": "#0e1429",
            "superficie": "#151f3f",
            "superficieAlt": "#1e2b55",
            "borde": "#3d5599",
            "texto": "#eef4ff",
            "textoSec": "#baccea",
            "textoMuted": "#8fa3d0",
            "acento": "#7ab0ff",
            "acentoFuerte": "#5c9af7",
            "hover": "#2b3f75",
            "seleccion": "#384f8f",
            "exito": "#6ae0bc",
            "peligro": "#ff7b8f",
            "advertencia": "#ffd482",
        },
        "menta_fresh": {
            "nombre": "Menta Fresh",
            "fondo": "#e8f7f3",
            "fondoElevado": "#f2fffb",
            "superficie": "#ffffff",
            "superficieAlt": "#daf0e8",
            "borde": "#b8d8cc",
            "texto": "#0f2b24",
            "textoSec": "#2f5247",
            "textoMuted": "#52756a",
            "acento": "#1abc9c",
            "acentoFuerte": "#16a085",
            "hover": "#cce8dc",
            "seleccion": "#bfe0d4",
            "exito": "#1fad7a",
            "peligro": "#e0546d",
            "advertencia": "#d4942a",
        },
        "carbono": {
            "nombre": "Carbono Frío",
            "fondo": "#0c0d0f",
            "fondoElevado": "#14161a",
            "superficie": "#1d2026",
            "superficieAlt": "#272b33",
            "borde": "#424955",
            "texto": "#f0f2f5",
            "textoSec": "#bcc3cd",
            "textoMuted": "#8d96a3",
            "acento": "#aab5c8",
            "acentoFuerte": "#94a0b5",
            "hover": "#343a46",
            "seleccion": "#3e4552",
            "exito": "#6bd0a8",
            "peligro": "#f07085",
            "advertencia": "#ecbe6a",
        },
        "vampiro_royal": {
            "nombre": "Vampiro Royal",
            "fondo": "#0e0e16",
            "fondoElevado": "#161624",
            "superficie": "#1f1f33",
            "superficieAlt": "#292945",
            "borde": "#424266",
            "texto": "#f6f6f0",
            "textoSec": "#c5c5dc",
            "textoMuted": "#8f8faf",
            "acento": "#c49bff",
            "acentoFuerte": "#b080ff",
            "hover": "#35355a",
            "seleccion": "#404068",
            "exito": "#64ff92",
            "peligro": "#ff6b6b",
            "advertencia": "#ffc97a",
        },
        "ambar_calido": {
            "nombre": "Ámbar Cálido",
            "fondo": "#16110d",
            "fondoElevado": "#211914",
            "superficie": "#2c221c",
            "superficieAlt": "#382b24",
            "borde": "#554238",
            "texto": "#fff2e6",
            "textoSec": "#d9c0b0",
            "textoMuted": "#a68f7f",
            "acento": "#ffb073",
            "acentoFuerte": "#ff9a57",
            "hover": "#45352d",
            "seleccion": "#574236",
            "exito": "#8adcb0",
            "peligro": "#ff7b6d",
            "advertencia": "#ffd485",
        },
        "nieve": {
            "nombre": "Nieve",
            "fondo": "#eaf0f6",
            "fondoElevado": "#f5f9ff",
            "superficie": "#ffffff",
            "superficieAlt": "#e2e9f3",
            "borde": "#c5d0e0",
            "texto": "#121d2e",
            "textoSec": "#3f4f66",
            "textoMuted": "#5f728a",
            "acento": "#1ab0ff",
            "acentoFuerte": "#0f9ae8",
            "hover": "#d6e3f3",
            "seleccion": "#cadef0",
            "exito": "#2fa878",
            "peligro": "#e05265",
            "advertencia": "#d4942a",
        },
        # NUEVOS TEMAS - Tonalidades únicas
        "ocean_profundo": {
            "nombre": "Océano Abisal",
            "fondo": "#00121a",
            "fondoElevado": "#001f2b",
            "superficie": "#003344",
            "superficieAlt": "#004455",
            "borde": "#006677",
            "texto": "#e0f7fa",
            "textoSec": "#80deea",
            "textoMuted": "#4dd0e1",
            "acento": "#00bcd4",
            "acentoFuerte": "#00acc1",
            "hover": "#005566",
            "seleccion": "#006677",
            "exito": "#26a69a",
            "peligro": "#ef5350",
            "advertencia": "#ffa726",
        },
        "galaxia": {
            "nombre": "Galaxia Púrpura",
            "fondo": "#0a0514",
            "fondoElevado": "#140a28",
            "superficie": "#1f0f3c",
            "superficieAlt": "#2a1450",
            "borde": "#4a2a7a",
            "texto": "#f0e6ff",
            "textoSec": "#d0b8ff",
            "textoMuted": "#a890d0",
            "acento": "#d580ff",
            "acentoFuerte": "#c060ff",
            "hover": "#3a2060",
            "seleccion": "#4a2878",
            "exito": "#a0ffa0",
            "peligro": "#ff80ab",
            "advertencia": "#ffd740",
        },
        "desierto_dorado": {
            "nombre": "Desierto Dorado",
            "fondo": "#1a140a",
            "fondoElevado": "#281f0f",
            "superficie": "#362a14",
            "superficieAlt": "#443519",
            "borde": "#665026",
            "texto": "#fff8e6",
            "textoSec": "#e8d4b0",
            "textoMuted": "#c0a880",
            "acento": "#ffd54f",
            "acentoFuerte": "#ffca28",
            "hover": "#554422",
            "seleccion": "#665228",
            "exito": "#9ccc65",
            "peligro": "#ff7043",
            "advertencia": "#ffca28",
        },
        "bosque_mistico": {
            "nombre": "Bosque Místico",
            "fondo": "#0a140f",
            "fondoElevado": "#0f1f16",
            "superficie": "#142a1f",
            "superficieAlt": "#1a3628",
            "borde": "#2a5540",
            "texto": "#e8f5f0",
            "textoSec": "#a8d8c0",
            "textoMuted": "#7ab898",
            "acento": "#80cbc4",
            "acentoFuerte": "#6ab8a8",
            "hover": "#1f4030",
            "seleccion": "#28503c",
            "exito": "#81c784",
            "peligro": "#e57373",
            "advertencia": "#ffb74d",
        },
        # ── NUEVOS TEMAS (v2) ────────────────────────────────────────────────
        "fuego_solar": {
            "nombre": "Fuego Solar",
            "fondo": "#100804",
            "fondoElevado": "#1c1008",
            "superficie": "#2a1a0c",
            "superficieAlt": "#3a2410",
            "borde": "#5c3c1a",
            "texto": "#fff3e0",
            "textoSec": "#f0c896",
            "textoMuted": "#c8945a",
            "acento": "#ff8c00",
            "acentoFuerte": "#e67c00",
            "hover": "#4a2e14",
            "seleccion": "#5a3818",
            "exito": "#76c442",
            "peligro": "#ff4545",
            "advertencia": "#ffd200",
        },
        "sakura_nocturno": {
            "nombre": "Sakura Nocturno",
            "fondo": "#130810",
            "fondoElevado": "#1e101a",
            "superficie": "#2e1828",
            "superficieAlt": "#3e2038",
            "borde": "#6a3860",
            "texto": "#fff0f8",
            "textoSec": "#f0b8e0",
            "textoMuted": "#c888b0",
            "acento": "#ff80c0",
            "acentoFuerte": "#ff60a8",
            "hover": "#4e2c46",
            "seleccion": "#603558",
            "exito": "#80e0a0",
            "peligro": "#ff6060",
            "advertencia": "#ffd060",
        },
        "glacial": {
            "nombre": "Glaciar Azul",
            "fondo": "#eef6fb",
            "fondoElevado": "#f8fcff",
            "superficie": "#ffffff",
            "superficieAlt": "#ddeef8",
            "borde": "#b4d4e8",
            "texto": "#0d1e2e",
            "textoSec": "#2c4a62",
            "textoMuted": "#4e7090",
            "acento": "#0096c7",
            "acentoFuerte": "#0077a8",
            "hover": "#cce4f4",
            "seleccion": "#bcd8ec",
            "exito": "#2e9e6a",
            "peligro": "#d93a4e",
            "advertencia": "#c87020",
        },
        "terminal_verde": {
            "nombre": "Terminal Verde",
            "fondo": "#000600",
            "fondoElevado": "#000e00",
            "superficie": "#001a00",
            "superficieAlt": "#002400",
            "borde": "#004800",
            "texto": "#00ff41",
            "textoSec": "#00cc33",
            "textoMuted": "#009922",
            "acento": "#39ff14",
            "acentoFuerte": "#2ee00e",
            "hover": "#003000",
            "seleccion": "#003e00",
            "exito": "#00e676",
            "peligro": "#ff1744",
            "advertencia": "#ffea00",
        },
        "sangre_dragon": {
            "nombre": "Sangre de Dragón",
            "fondo": "#0e0000",
            "fondoElevado": "#1a0000",
            "superficie": "#280000",
            "superficieAlt": "#360000",
            "borde": "#600000",
            "texto": "#ffeeee",
            "textoSec": "#ffbbbb",
            "textoMuted": "#dd8888",
            "acento": "#ff2020",
            "acentoFuerte": "#e00000",
            "hover": "#460000",
            "seleccion": "#580000",
            "exito": "#66e09a",
            "peligro": "#ff8080",
            "advertencia": "#ffc070",
        },
        "prisma": {
            "nombre": "Prisma",
            "fondo": "#080e14",
            "fondoElevado": "#0e1a22",
            "superficie": "#152838",
            "superficieAlt": "#1c3448",
            "borde": "#3a6880",
            "texto": "#e8f8ff",
            "textoSec": "#90d0e8",
            "textoMuted": "#60a8c4",
            "acento": "#00e5c8",
            "acentoFuerte": "#00ccb2",
            "hover": "#234460",
            "seleccion": "#2c5475",
            "exito": "#a0ffbc",
            "peligro": "#ff6090",
            "advertencia": "#ffe060",
        },
        "lava": {
            "nombre": "Lava Negra",
            "fondo": "#0e0500",
            "fondoElevado": "#1c0e00",
            "superficie": "#2c1800",
            "superficieAlt": "#3c2200",
            "borde": "#703000",
            "texto": "#fff8f0",
            "textoSec": "#ffd0a0",
            "textoMuted": "#e09050",
            "acento": "#ff6600",
            "acentoFuerte": "#e05800",
            "hover": "#4c2c00",
            "seleccion": "#5e3600",
            "exito": "#88e060",
            "peligro": "#ff3030",
            "advertencia": "#ffcc00",
        },
        "sepia": {
            "nombre": "Sepia Imperial",
            "fondo": "#f5f0e8",
            "fondoElevado": "#fffdf5",
            "superficie": "#ffffff",
            "superficieAlt": "#ede5d4",
            "borde": "#c8b89a",
            "texto": "#2c1e0c",
            "textoSec": "#54381c",
            "textoMuted": "#7a5838",
            "acento": "#8b5e3c",
            "acentoFuerte": "#704a28",
            "hover": "#e0d4c0",
            "seleccion": "#d8c8a8",
            "exito": "#4a9c6e",
            "peligro": "#c0402e",
            "advertencia": "#b87020",
        },
        "medianoche": {
            "nombre": "Medianoche Azul",
            "fondo": "#020408",
            "fondoElevado": "#060c14",
            "superficie": "#0c1620",
            "superficieAlt": "#14202e",
            "borde": "#283848",
            "texto": "#dce8f2",
            "textoSec": "#8aa8c0",
            "textoMuted": "#506880",
            "acento": "#4888b8",
            "acentoFuerte": "#3470a0",
            "hover": "#1a2c40",
            "seleccion": "#22384e",
            "exito": "#5aaa80",
            "peligro": "#e06060",
            "advertencia": "#d4a840",
        },
        "esmeralda": {
            "nombre": "Esmeralda",
            "fondo": "#050f0a",
            "fondoElevado": "#0a1a10",
            "superficie": "#122818",
            "superficieAlt": "#1a3420",
            "borde": "#306040",
            "texto": "#e0f8ec",
            "textoSec": "#90d8b0",
            "textoMuted": "#60a878",
            "acento": "#00e080",
            "acentoFuerte": "#00c070",
            "hover": "#1e4028",
            "seleccion": "#284e32",
            "exito": "#80ffb0",
            "peligro": "#ff6080",
            "advertencia": "#ffd860",
        },
        "titanio": {
            "nombre": "Titanio",
            "fondo": "#0a0b0c",
            "fondoElevado": "#111315",
            "superficie": "#1a1c1f",
            "superficieAlt": "#232629",
            "borde": "#3a3e44",
            "texto": "#e8eaec",
            "textoSec": "#9ea4aa",
            "textoMuted": "#606870",
            "acento": "#8cb4c8",
            "acentoFuerte": "#70a0b8",
            "hover": "#2e3238",
            "seleccion": "#383e46",
            "exito": "#60c090",
            "peligro": "#e06870",
            "advertencia": "#d4a840",
        },
        "coral_sunrise": {
            "nombre": "Coral Amanecer",
            "fondo": "#fff5f2",
            "fondoElevado": "#fffaf8",
            "superficie": "#ffffff",
            "superficieAlt": "#ffe8e0",
            "borde": "#f0c4b4",
            "texto": "#2c1010",
            "textoSec": "#6a2e20",
            "textoMuted": "#9a5040",
            "acento": "#e84c2c",
            "acentoFuerte": "#cc3c20",
            "hover": "#f8dcd4",
            "seleccion": "#f4ccc0",
            "exito": "#2ea070",
            "peligro": "#c03030",
            "advertencia": "#c07020",
        },
        "indigo_profundo": {
            "nombre": "Índigo Profundo",
            "fondo": "#05050f",
            "fondoElevado": "#0c0c1e",
            "superficie": "#141430",
            "superficieAlt": "#1c1c42",
            "borde": "#3c3c78",
            "texto": "#f0f0ff",
            "textoSec": "#c0c0f0",
            "textoMuted": "#9090d0",
            "acento": "#8080ff",
            "acentoFuerte": "#6060ee",
            "hover": "#282858",
            "seleccion": "#32326e",
            "exito": "#60e0b0",
            "peligro": "#ff6080",
            "advertencia": "#ffd040",
        },
        "aurora_rosa": {
            "nombre": "Aurora Rosa",
            "fondo": "#0f0414",
            "fondoElevado": "#1a0820",
            "superficie": "#28102e",
            "superficieAlt": "#38183e",
            "borde": "#703080",
            "texto": "#fff4ff",
            "textoSec": "#f0a0f8",
            "textoMuted": "#c870d8",
            "acento": "#ff40ff",
            "acentoFuerte": "#ee20ee",
            "hover": "#4a2054",
            "seleccion": "#5c2868",
            "exito": "#80ffc0",
            "peligro": "#ff8060",
            "advertencia": "#ffd840",
        },
        "cafe_nocturno": {
            "nombre": "Café Nocturno",
            "fondo": "#0c0805",
            "fondoElevado": "#18120a",
            "superficie": "#241c10",
            "superficieAlt": "#302616",
            "borde": "#58421e",
            "texto": "#fff8ee",
            "textoSec": "#dcc498",
            "textoMuted": "#a89060",
            "acento": "#c49a50",
            "acentoFuerte": "#ae8438",
            "hover": "#3c3018",
            "seleccion": "#4a3c20",
            "exito": "#70cc88",
            "peligro": "#e86060",
            "advertencia": "#f0c040",
        },
        "obsidiana_neon": {
            "nombre": "Obsidiana Neón",
            "fondo": "#020305",
            "fondoElevado": "#070b12",
            "superficie": "#0d1420",
            "superficieAlt": "#152235",
            "borde": "#2c465f",
            "texto": "#eef8ff",
            "textoSec": "#a8c9e6",
            "textoMuted": "#7191ad",
            "acento": "#20f0ff",
            "acentoFuerte": "#00c8dc",
            "hover": "#1b3044",
            "seleccion": "#203b54",
            "exito": "#5df2a8",
            "peligro": "#ff5f7d",
            "advertencia": "#ffd166",
            "modoBoxFondo": "#090f18",
            "modoBoxBorde": "#2b86a1",
        },
        "hielo_oled": {
            "nombre": "Hielo OLED",
            "fondo": "#000000",
            "fondoElevado": "#05090d",
            "superficie": "#0a121a",
            "superficieAlt": "#10202e",
            "borde": "#254356",
            "texto": "#f6fbff",
            "textoSec": "#b5d7e8",
            "textoMuted": "#7ea5ba",
            "acento": "#8ee8ff",
            "acentoFuerte": "#57d6f4",
            "hover": "#163144",
            "seleccion": "#1e4058",
            "exito": "#76e6b1",
            "peligro": "#ff6d86",
            "advertencia": "#ffd47a",
            "modoBoxFondo": "#050f17",
            "modoBoxBorde": "#32677e",
        },
        "blanco_editorial": {
            "nombre": "Blanco Editorial",
            "fondo": "#f7f7f4",
            "fondoElevado": "#ffffff",
            "superficie": "#fbfbf8",
            "superficieAlt": "#ececea",
            "borde": "#cfd2d4",
            "texto": "#171a1f",
            "textoSec": "#434a54",
            "textoMuted": "#68717d",
            "acento": "#1f6feb",
            "acentoFuerte": "#175bc2",
            "hover": "#e2e7ee",
            "seleccion": "#d6e2f4",
            "exito": "#16845b",
            "peligro": "#c93c4c",
            "advertencia": "#b97816",
            "modoBoxFondo": "#ffffff",
            "modoBoxBorde": "#b8c2cf",
        },
        "oro_negro": {
            "nombre": "Oro Negro",
            "fondo": "#060503",
            "fondoElevado": "#0f0c06",
            "superficie": "#1a1408",
            "superficieAlt": "#241c0b",
            "borde": "#5c4618",
            "texto": "#fff7de",
            "textoSec": "#e2c681",
            "textoMuted": "#aa9055",
            "acento": "#f4c84a",
            "acentoFuerte": "#d9a914",
            "hover": "#30250d",
            "seleccion": "#3d2f10",
            "exito": "#8bdc8b",
            "peligro": "#ff6868",
            "advertencia": "#ffd36a",
            "modoBoxFondo": "#130f07",
            "modoBoxBorde": "#725819",
        },
        "jade_nocturno": {
            "nombre": "Jade Nocturno",
            "fondo": "#020b08",
            "fondoElevado": "#071510",
            "superficie": "#0d241a",
            "superficieAlt": "#153324",
            "borde": "#2b674d",
            "texto": "#eafff5",
            "textoSec": "#a8e5c9",
            "textoMuted": "#75b594",
            "acento": "#35f0a0",
            "acentoFuerte": "#18c980",
            "hover": "#1e4834",
            "seleccion": "#275a42",
            "exito": "#70ffb0",
            "peligro": "#ff6f8f",
            "advertencia": "#ffd36f",
            "modoBoxFondo": "#0a1d15",
            "modoBoxBorde": "#2e7a58",
        },
        "plasma_morado": {
            "nombre": "Plasma Morado",
            "fondo": "#100416",
            "fondoElevado": "#1a0824",
            "superficie": "#2a1038",
            "superficieAlt": "#3a1650",
            "borde": "#7a35a0",
            "texto": "#fff2ff",
            "textoSec": "#dfb0f5",
            "textoMuted": "#ad7ccc",
            "acento": "#d95cff",
            "acentoFuerte": "#b936e8",
            "hover": "#4e2368",
            "seleccion": "#612b80",
            "exito": "#74efb2",
            "peligro": "#ff6f9b",
            "advertencia": "#ffd166",
            "modoBoxFondo": "#210c2e",
            "modoBoxBorde": "#8a42b0",
        },
        "amanecer_sintetico": {
            "nombre": "Amanecer Sintético",
            "fondo": "#160a14",
            "fondoElevado": "#24121d",
            "superficie": "#331927",
            "superficieAlt": "#462236",
            "borde": "#8f4c68",
            "texto": "#fff4f2",
            "textoSec": "#ffc3b3",
            "textoMuted": "#cf8e86",
            "acento": "#ff7a59",
            "acentoFuerte": "#ff5a3a",
            "hover": "#5b2d45",
            "seleccion": "#713752",
            "exito": "#7de0a3",
            "peligro": "#ff6275",
            "advertencia": "#ffd05f",
            "modoBoxFondo": "#2b1524",
            "modoBoxBorde": "#a35b76",
        },
        "tinta_marina": {
            "nombre": "Tinta Marina",
            "fondo": "#020814",
            "fondoElevado": "#071225",
            "superficie": "#0e2038",
            "superficieAlt": "#16304c",
            "borde": "#315b86",
            "texto": "#eef6ff",
            "textoSec": "#a9c8ee",
            "textoMuted": "#7898bf",
            "acento": "#4da3ff",
            "acentoFuerte": "#2f85df",
            "hover": "#203f62",
            "seleccion": "#2a4f76",
            "exito": "#6ee0bd",
            "peligro": "#ff7088",
            "advertencia": "#ffd275",
            "modoBoxFondo": "#0b1a2e",
            "modoBoxBorde": "#3a6f9d",
        },
        "frambuesa_dark": {
            "nombre": "Frambuesa Dark",
            "fondo": "#12040b",
            "fondoElevado": "#1f0913",
            "superficie": "#30101f",
            "superficieAlt": "#43162c",
            "borde": "#873253",
            "texto": "#fff0f6",
            "textoSec": "#f0adc7",
            "textoMuted": "#be7895",
            "acento": "#ff4f93",
            "acentoFuerte": "#e82c74",
            "hover": "#5a2140",
            "seleccion": "#6e294e",
            "exito": "#71e2a5",
            "peligro": "#ff6b6b",
            "advertencia": "#ffd070",
            "modoBoxFondo": "#270d19",
            "modoBoxBorde": "#9b3b62",
        },
        "cielo_coral": {
            "nombre": "Cielo Coral",
            "fondo": "#f1f8ff",
            "fondoElevado": "#fbfdff",
            "superficie": "#ffffff",
            "superficieAlt": "#e4f0fb",
            "borde": "#b7cee2",
            "texto": "#132333",
            "textoSec": "#36556e",
            "textoMuted": "#638095",
            "acento": "#ff6b58",
            "acentoFuerte": "#df4f3f",
            "hover": "#dbeaf5",
            "seleccion": "#ffd6ce",
            "exito": "#24966f",
            "peligro": "#cf4050",
            "advertencia": "#bd7a1d",
            "modoBoxFondo": "#ffffff",
            "modoBoxBorde": "#e7a69a",
        },
        "violeta_laser": {
            "nombre": "Violeta Láser",
            "fondo": "#060311",
            "fondoElevado": "#0d0820",
            "superficie": "#17102f",
            "superficieAlt": "#211842",
            "borde": "#5745a8",
            "texto": "#f5f1ff",
            "textoSec": "#c8b9ff",
            "textoMuted": "#9280d4",
            "acento": "#9b7cff",
            "acentoFuerte": "#7d5dff",
            "hover": "#2e235c",
            "seleccion": "#392c72",
            "exito": "#72e5b0",
            "peligro": "#ff6b9b",
            "advertencia": "#ffd25f",
            "modoBoxFondo": "#120b28",
            "modoBoxBorde": "#6650c0",
        },
        "acero_azul": {
            "nombre": "Acero Azul",
            "fondo": "#0a0f14",
            "fondoElevado": "#111922",
            "superficie": "#1b2632",
            "superficieAlt": "#253443",
            "borde": "#495c6f",
            "texto": "#edf3f8",
            "textoSec": "#b9c8d4",
            "textoMuted": "#8496a5",
            "acento": "#7fb6d6",
            "acentoFuerte": "#5b9abc",
            "hover": "#314456",
            "seleccion": "#3c5064",
            "exito": "#74c99c",
            "peligro": "#e76d7e",
            "advertencia": "#d9aa55",
            "modoBoxFondo": "#15202a",
            "modoBoxBorde": "#5a7188",
        },
        "rosa_polar": {
            "nombre": "Rosa Polar",
            "fondo": "#f8f2f8",
            "fondoElevado": "#fffaff",
            "superficie": "#ffffff",
            "superficieAlt": "#f0e4f2",
            "borde": "#d8bddc",
            "texto": "#241629",
            "textoSec": "#5b4364",
            "textoMuted": "#826b8c",
            "acento": "#c65acb",
            "acentoFuerte": "#a843ad",
            "hover": "#ead9ed",
            "seleccion": "#e4c6e8",
            "exito": "#288f68",
            "peligro": "#ca4058",
            "advertencia": "#b77a18",
            "modoBoxFondo": "#fffaff",
            "modoBoxBorde": "#cfa6d4",
        },
        "circuito_verde": {
            "nombre": "Circuito Verde",
            "fondo": "#020804",
            "fondoElevado": "#061208",
            "superficie": "#0b1e10",
            "superficieAlt": "#102a17",
            "borde": "#245f32",
            "texto": "#eaffed",
            "textoSec": "#a9e8b8",
            "textoMuted": "#75b583",
            "acento": "#48ff6a",
            "acentoFuerte": "#1edc45",
            "hover": "#183b22",
            "seleccion": "#204c2d",
            "exito": "#77ff96",
            "peligro": "#ff667f",
            "advertencia": "#ffe169",
            "modoBoxFondo": "#08180c",
            "modoBoxBorde": "#2c7a3b",
        },
        "ultra_violeta": {
            "nombre": "Ultra Violeta",
            "fondo": "#0b0618",
            "fondoElevado": "#120b26",
            "superficie": "#201340",
            "superficieAlt": "#2e1b5a",
            "borde": "#6540b5",
            "texto": "#f8f0ff",
            "textoSec": "#d0b4ff",
            "textoMuted": "#9e7bd8",
            "acento": "#bf5cff",
            "acentoFuerte": "#a338ee",
            "hover": "#3d2670",
            "seleccion": "#4c2f88",
            "exito": "#74ebb8",
            "peligro": "#ff6b8e",
            "advertencia": "#ffd56b",
            "modoBoxFondo": "#180e32",
            "modoBoxBorde": "#764bcf",
        },
        "marfil_grafito": {
            "nombre": "Marfil Grafito",
            "fondo": "#f1efe8",
            "fondoElevado": "#fbfaf5",
            "superficie": "#ffffff",
            "superficieAlt": "#e6e2d8",
            "borde": "#c7c0b2",
            "texto": "#1f2225",
            "textoSec": "#4d5359",
            "textoMuted": "#747b82",
            "acento": "#2f6f7e",
            "acentoFuerte": "#245867",
            "hover": "#ddd8cc",
            "seleccion": "#cfe2e5",
            "exito": "#248760",
            "peligro": "#b9414b",
            "advertencia": "#a96d1a",
            "modoBoxFondo": "#fbfaf5",
            "modoBoxBorde": "#aeb9b9",
        },
        "noche_arcade": {
            "nombre": "Noche Arcade",
            "fondo": "#070716",
            "fondoElevado": "#10102a",
            "superficie": "#191943",
            "superficieAlt": "#252560",
            "borde": "#4d4aa3",
            "texto": "#f4f3ff",
            "textoSec": "#c6c1ff",
            "textoMuted": "#8f8ac8",
            "acento": "#00d9ff",
            "acentoFuerte": "#ff4fd8",
            "hover": "#33337a",
            "seleccion": "#403f91",
            "exito": "#67f08f",
            "peligro": "#ff5f6e",
            "advertencia": "#ffe45f",
            "modoBoxFondo": "#131333",
            "modoBoxBorde": "#625fff",
        },
        "neon_citrico": {
            "nombre": "Neón Cítrico",
            "fondo": "#030604",
            "fondoElevado": "#08110b",
            "superficie": "#102018",
            "superficieAlt": "#1a3323",
            "borde": "#4b7d3a",
            "texto": "#f4ffe8",
            "textoSec": "#d0f0a6",
            "textoMuted": "#9ec775",
            "acento": "#d7ff3f",
            "acentoFuerte": "#b8e51d",
            "hover": "#25452a",
            "seleccion": "#335a32",
            "exito": "#5dffa1",
            "peligro": "#ff5f79",
            "advertencia": "#ffd45c",
            "modoBoxFondo": "#0c1a10",
            "modoBoxBorde": "#74a83e",
        },
        # ── NUEVOS TEMAS CREATIVOS (v3) ────────────────────────────────────────
        "cosmic_latte": {
            "nombre": "Latte Cósmico",
            "fondo": "#1a0f0a",
            "fondoElevado": "#241610",
            "superficie": "#2f1e16",
            "superficieAlt": "#3d281c",
            "borde": "#6b4a32",
            "texto": "#fff0e6",
            "textoSec": "#e8c8b0",
            "textoMuted": "#c0a088",
            "acento": "#d4a574",
            "acentoFuerte": "#c4905a",
            "hover": "#4a3224",
            "seleccion": "#5a3e2e",
            "exito": "#8bc47a",
            "peligro": "#ff7a6a",
            "advertencia": "#ffc87a",
            "modoBoxFondo": "#1f120c",
            "modoBoxBorde": "#7a583a",
        },
        "turquesa_electrica": {
            "nombre": "Turquesa Eléctrica",
            "fondo": "#001418",
            "fondoElevado": "#002228",
            "superficie": "#00343c",
            "superficieAlt": "#004650",
            "borde": "#007a8a",
            "texto": "#e6ffff",
            "textoSec": "#a0e8ee",
            "textoMuted": "#70bcc4",
            "acento": "#00e0e8",
            "acentoFuerte": "#00c0c8",
            "hover": "#005260",
            "seleccion": "#006678",
            "exito": "#60e8b0",
            "peligro": "#ff6a8a",
            "advertencia": "#ffd860",
            "modoBoxFondo": "#002a32",
            "modoBoxBorde": "#0090a0",
        },
        "magma_violeta": {
            "nombre": "Magma Violeta",
            "fondo": "#140410",
            "fondoElevado": "#1f0818",
            "superficie": "#2e0c24",
            "superficieAlt": "#3e1030",
            "borde": "#6a2a50",
            "texto": "#ffe6f6",
            "textoSec": "#f0a8d8",
            "textoMuted": "#c878b0",
            "acento": "#ff40c0",
            "acentoFuerte": "#e820a8",
            "hover": "#521840",
            "seleccion": "#662050",
            "exito": "#80e8a0",
            "peligro": "#ff5a70",
            "advertencia": "#ffcc50",
            "modoBoxFondo": "#240a1c",
            "modoBoxBorde": "#7a3060",
        },
        "bruma_artica": {
            "nombre": "Bruma Ártica",
            "fondo": "#0a1418",
            "fondoElevado": "#101e24",
            "superficie": "#182a32",
            "superficieAlt": "#203640",
            "borde": "#3a5a68",
            "texto": "#e8f4f8",
            "textoSec": "#b8d4e0",
            "textoMuted": "#88acb8",
            "acento": "#70c0d0",
            "acentoFuerte": "#50a8b8",
            "hover": "#2a4048",
            "seleccion": "#324e58",
            "exito": "#68c890",
            "peligro": "#ff7080",
            "advertencia": "#ffd060",
            "modoBoxFondo": "#14222a",
            "modoBoxBorde": "#456878",
        },
        "cobre_oxidado": {
            "nombre": "Cobre Oxidado",
            "fondo": "#140e0a",
            "fondoElevado": "#1f1610",
            "superficie": "#2e2016",
            "superficieAlt": "#3d2a1c",
            "borde": "#6a4830",
            "texto": "#f8ebe0",
            "textoSec": "#d8b898",
            "textoMuted": "#b08868",
            "acento": "#c87840",
            "acentoFuerte": "#b06030",
            "hover": "#4a3222",
            "seleccion": "#5a3e2a",
            "exito": "#78c060",
            "peligro": "#e85a50",
            "advertencia": "#f0b840",
            "modoBoxFondo": "#241810",
            "modoBoxBorde": "#7a5838",
        },
        "sombra_lima": {
            "nombre": "Sombra Lima",
            "fondo": "#081004",
            "fondoElevado": "#0e1a08",
            "superficie": "#14280c",
            "superficieAlt": "#1c3610",
            "borde": "#3a5a18",
            "texto": "#f0ffe6",
            "textoSec": "#c8e8a0",
            "textoMuted": "#98c070",
            "acento": "#a8e840",
            "acentoFuerte": "#90d028",
            "hover": "#2a4010",
            "seleccion": "#345014",
            "exito": "#80e060",
            "peligro": "#ff6060",
            "advertencia": "#ffe040",
            "modoBoxFondo": "#10200a",
            "modoBoxBorde": "#456a20",
        },
        "zafiro_medianoche": {
            "nombre": "Zafiro Medianoche",
            "fondo": "#040814",
            "fondoElevado": "#081020",
            "superficie": "#0c1a30",
            "superficieAlt": "#102440",
            "borde": "#284068",
            "texto": "#e6f0ff",
            "textoSec": "#a8c0e8",
            "textoMuted": "#7890b8",
            "acento": "#5080e0",
            "acentoFuerte": "#3868c8",
            "hover": "#1a2a48",
            "seleccion": "#223458",
            "exito": "#58d090",
            "peligro": "#ff6070",
            "advertencia": "#ffc850",
            "modoBoxFondo": "#0a1428",
            "modoBoxBorde": "#305078",
        },
        "rosa_quimera": {
            "nombre": "Rosa Quimera",
            "fondo": "#14040c",
            "fondoElevado": "#1f0814",
            "superficie": "#2e0c1c",
            "superficieAlt": "#3e1028",
            "borde": "#6a2040",
            "texto": "#ffe6f0",
            "textoSec": "#f0a8c8",
            "textoMuted": "#c87898",
            "acento": "#ff5090",
            "acentoFuerte": "#e83078",
            "hover": "#4a1830",
            "seleccion": "#5a203c",
            "exito": "#70e090",
            "peligro": "#ff6068",
            "advertencia": "#ffd060",
            "modoBoxFondo": "#240a18",
            "modoBoxBorde": "#7a2850",
        },
        "grafito_radioactivo": {
            "nombre": "Grafito Radioactivo",
            "fondo": "#0a0c08",
            "fondoElevado": "#10140c",
            "superficie": "#182012",
            "superficieAlt": "#202c18",
            "borde": "#3a4a28",
            "texto": "#e8f0e0",
            "textoSec": "#b8c8a8",
            "textoMuted": "#889878",
            "acento": "#90e040",
            "acentoFuerte": "#78c830",
            "hover": "#2a3818",
            "seleccion": "#34441e",
            "exito": "#70d860",
            "peligro": "#ff5a60",
            "advertencia": "#ffd050",
            "modoBoxFondo": "#121a10",
            "modoBoxBorde": "#455830",
        },
    }

    _CLAVES_COLOR = [
        "fondo", "fondoElevado", "superficie", "superficieAlt", "borde",
        "texto", "textoSec", "textoMuted", "acento", "acentoFuerte",
        "hover", "seleccion", "exito", "peligro", "advertencia",
        "modoBoxFondo", "modoBoxBorde",
    ]

    for _tema in _TEMAS.values():
        _tema.setdefault("modoBoxFondo", _tema.get("fondoElevado", "#0a0a0a"))
        _tema.setdefault("modoBoxBorde", _tema.get("borde", "#2a2a2a"))
    del _tema

    def __init__(self, configuracion: "ModeloConfiguracion", parent=None):
        super().__init__(parent)
        self._configuracion = configuracion
        self._tema_id = "negro_puro"
        self._tema_custom: dict[str, str] = {}
        self._cargar_tema_guardado()

    def _cargar_tema_guardado(self) -> None:
        self._tema_custom = self._configuracion.tema_personalizado_desde_config()
        tema = self._configuracion.obtener("tema") or "negro_puro"
        if tema == "custom":
            self._tema_id = "custom"
            return
        self._tema_id = tema if tema in self._TEMAS else "negro_puro"

    def _tema_actual(self) -> dict[str, str]:
        if self._tema_id == "custom":
            return self._tema_custom or self._TEMAS["negro_puro"]
        return self._TEMAS[self._tema_id]

    def _valor(self, clave: str) -> str:
        tema = self._tema_actual()
        if clave in tema:
            return tema[clave]
        if clave == "modoBoxFondo":
            return tema.get("fondoElevado", "#0a0a0a")
        if clave == "modoBoxBorde":
            return tema.get("borde", "#2a2a2a")
        return self._TEMAS["negro_puro"].get(clave, "#000000")

    @Property(str, notify=temaCambiado)
    def tema_id(self) -> str:
        return self._tema_id

    @Property("QVariantList", notify=temaCambiado)
    def temas_disponibles(self) -> list[dict]:
        def _preview(tema_id: str, data: dict[str, str]) -> dict[str, str]:
            payload = {
                "id": tema_id,
                "nombre": data.get("nombre", "Personalizado"),
            }
            for clave in self._CLAVES_COLOR:
                payload[clave] = data.get(clave, self._TEMAS["negro_puro"].get(clave, "#000000"))
            return payload

        temas = [_preview(k, v) for k, v in self._TEMAS.items()]
        custom = self._tema_custom or {}
        base_custom = {
            clave: custom.get(clave, self._TEMAS["negro_puro"].get(clave, "#000000"))
            for clave in self._CLAVES_COLOR
        }
        base_custom["nombre"] = custom.get("nombre", "Personalizado")
        temas.append(_preview("custom", base_custom))
        return temas

    @Slot(str)
    def aplicar_tema(self, tema_id: str) -> None:
        if tema_id == self._tema_id:
            return
        if tema_id == "custom":
            self._tema_custom = self._configuracion.tema_personalizado_desde_config()
            self._tema_id = "custom"
            self._configuracion.guardar("tema", "custom")
            self.temaCambiado.emit()
            return
        if tema_id not in self._TEMAS:
            return
        self._tema_id = tema_id
        self._configuracion.guardar("tema", tema_id)
        self.temaCambiado.emit()

    @Slot("QVariant", str)
    def aplicar_tema_personalizado(self, colores, nombre: str = "Personalizado") -> None:
        colores_dict = colores.toVariant() if isinstance(colores, QJSValue) else colores
        if not isinstance(colores_dict, dict):
            return
        base = dict(self._TEMAS["negro_puro"])
        base["nombre"] = (nombre or "Personalizado").strip() or "Personalizado"
        for clave in self._CLAVES_COLOR:
            valor = str(colores_dict.get(clave, "")).strip()
            if len(valor) == 7 and valor.startswith("#"):
                base[clave] = valor
        self._configuracion.guardar_tema_personalizado(base)
        self._tema_custom = base
        self._tema_id = "custom"
        self._configuracion.guardar("tema", "custom")
        self.temaCambiado.emit()

    @Slot(result="QVariantMap")
    def tema_personalizado_actual(self) -> dict:
        return dict(self._tema_custom)

    @Slot()
    def recargar_desde_config(self) -> None:
        anterior = self._tema_id
        self._cargar_tema_guardado()
        if anterior != self._tema_id:
            self.temaCambiado.emit()

    def _color(self, clave: str) -> QColor:
        # Devolver QColor en vez de str para que QML pueda hacer `tema.X.r .g .b`
        # directamente. Antes (str), `string.r` era undefined → `Qt.rgba(undef,...)`
        # pintaba NEGRO sobre fondos claros (Inicio se veía mal en temas claros).
        return QColor(self._valor(clave))

    @Property(QColor, notify=temaCambiado)
    def fondo(self) -> QColor: return self._color("fondo")

    @Property(QColor, notify=temaCambiado)
    def fondoElevado(self) -> QColor: return self._color("fondoElevado")

    @Property(QColor, notify=temaCambiado)
    def superficie(self) -> QColor: return self._color("superficie")

    @Property(QColor, notify=temaCambiado)
    def superficieAlt(self) -> QColor: return self._color("superficieAlt")

    @Property(QColor, notify=temaCambiado)
    def borde(self) -> QColor: return self._color("borde")

    @Property(QColor, notify=temaCambiado)
    def texto(self) -> QColor: return self._color("texto")

    @Property(QColor, notify=temaCambiado)
    def textoSec(self) -> QColor: return self._color("textoSec")

    @Property(QColor, notify=temaCambiado)
    def textoMuted(self) -> QColor: return self._color("textoMuted")

    @Property(QColor, notify=temaCambiado)
    def acento(self) -> QColor: return self._color("acento")

    @Property(QColor, notify=temaCambiado)
    def acentoFuerte(self) -> QColor: return self._color("acentoFuerte")

    @Property(QColor, notify=temaCambiado)
    def hover(self) -> QColor: return self._color("hover")

    @Property(QColor, notify=temaCambiado)
    def seleccion(self) -> QColor: return self._color("seleccion")

    @Property(QColor, notify=temaCambiado)
    def exito(self) -> QColor: return self._color("exito")

    @Property(QColor, notify=temaCambiado)
    def peligro(self) -> QColor: return self._color("peligro")

    @Property(QColor, notify=temaCambiado)
    def advertencia(self) -> QColor: return self._color("advertencia")

    @Property(QColor, notify=temaCambiado)
    def modoBoxFondo(self) -> QColor: return self._color("modoBoxFondo")

    @Property(QColor, notify=temaCambiado)
    def modoBoxBorde(self) -> QColor: return self._color("modoBoxBorde")

    @staticmethod
    def _luminancia_relativa(hex_color: str) -> float:
        # Luminancia relativa estándar WCAG. Devuelve [0, 1].
        valor = (hex_color or "").lstrip("#")
        if len(valor) != 6:
            return 1.0
        try:
            r = int(valor[0:2], 16) / 255.0
            g = int(valor[2:4], 16) / 255.0
            b = int(valor[4:6], 16) / 255.0
        except ValueError:
            return 1.0
        def _lin(c: float) -> float:
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)

    @Property(str, notify=temaCambiado)
    def textoSobreAcento(self) -> str:
        # Texto óptimo sobre fondos del color de acento. Negro en acentos
        # claros, blanco en acentos oscuros. Centraliza el patrón antes
        # disperso (lum > 0.5 ? "#000" : "#fff").
        return "#000000" if self._luminancia_relativa(self._valor("acento")) > 0.5 else "#ffffff"

    @Property(str, notify=temaCambiado)
    def textoSobrePeligro(self) -> str:
        return "#000000" if self._luminancia_relativa(self._valor("peligro")) > 0.5 else "#ffffff"

    @Property(str, notify=temaCambiado)
    def textoSobreExito(self) -> str:
        """Texto optimo sobre fondos verdes/exito (toasts, badges)."""
        return "#000000" if self._luminancia_relativa(self._valor("exito")) > 0.5 else "#ffffff"

    @Property(str, notify=temaCambiado)
    def textoSobreAdvertencia(self) -> str:
        """Texto optimo sobre fondos amarillos/naranjas (toasts, badges)."""
        return "#000000" if self._luminancia_relativa(self._valor("advertencia")) > 0.5 else "#ffffff"

    @Property(str, notify=temaCambiado)
    def textoInmersivo(self) -> str:
        # Texto sobre superficies inmersivas (vistas que imponen fondo
        # dinámico saturado oscuro, ej. reproducción expandida, lyrics
        # fullscreen, mini reproductor). El fondo está intencionalmente
        # forzado a hsla con lightness clamped a [0.09, 0.48], por lo
        # que el texto siempre debe ser claro independientemente del tema.
        return "#ffffff"

class ModeloConfiguracion(QObject):
    """Configuracion de la aplicacion (rutas, opciones de importacion)."""

    configuracionCambiada = Signal()
    guardadoCambiado = Signal()

    _RUTAS_REQUIRED_KEYS = [
        "dir_entrada", "dir_biblioteca", "dir_revision", "dir_cuarentena",
        "dir_logs", "dir_procesados",
    ]
    _RUTAS_OPTIONAL_KEYS = [
        "dir_assets", "dir_cache", "dir_temp", "dir_manifests",
    ]
    _RUTAS_KEYS = _RUTAS_REQUIRED_KEYS + _RUTAS_OPTIONAL_KEYS
    _RUTAS_DEFAULT_ATTRS = {
        "dir_entrada": "DEFAULT_INPUT_DIR",
        "dir_biblioteca": "DEFAULT_LIBRARY_DIR",
        "dir_cuarentena": "DEFAULT_QUARANTINE_DIR",
        "dir_revision": "DEFAULT_REVIEW_DIR",
        "dir_logs": "DEFAULT_LOGS_DIR",
        "dir_procesados": "DEFAULT_PROCESSED_DIR",
        "dir_assets": "DEFAULT_ASSETS_DIR",
        "dir_cache": "DEFAULT_CACHE_DIR",
        "dir_temp": "DEFAULT_TEMP_DIR",
        "dir_manifests": "DEFAULT_MANIFESTS_DIR",
    }

    _ENV_TO_CONFIG_KEY = {
        "USER_INPUT_DIR": "dir_entrada",
        "USER_LIBRARY_DIR": "dir_biblioteca",
        "USER_QUARANTINE_DIR": "dir_cuarentena",
        "USER_REVIEW_DIR": "dir_revision",
        "USER_LOGS_DIR": "dir_logs",
        "USER_PROCESSED_DIR": "dir_procesados",
        "USER_CACHE_DIR": "dir_cache",
        "USER_TEMP_DIR": "dir_temp",
        "USER_ASSETS_DIR": "dir_assets",
        "USER_MANIFESTS_DIR": "dir_manifests",
        "ACOUSTID_API_KEY": "acoustid_key",
        "ENABLE_ACOUSTID": "enable_acoustid",
        "ENABLE_SHAZAM": "enable_shazam",
        "SHAZAM_TIMEOUT_SEG": "shazam_timeout_seg",
        "SHAZAM_MIN_DURACION_SEG": "shazam_min_duracion_seg",
        "IA_PROVEEDOR": "ia_proveedor",
        "ANTHROPIC_API_KEY": "anthropic_key",
        "OPENAI_API_KEY": "openai_key",
        "ENABLE_IA_TIEBREAK": "enable_ia_tiebreak",
        "IA_TIEBREAK_MIN_GAP": "ia_tiebreak_min_gap",
        "IA_MAX_TOKENS": "ia_max_tokens",
        "IA_TIMEOUT_SEG": "ia_timeout_seg",
        "SKIP_ALREADY_PROCESSED": "skip_already_processed",
        "INIT_COMPONENT_MAX_RETRIES": "init_component_max_retries",
        "INIT_COMPONENT_RETRY_BACKOFF_SEG": "init_component_retry_backoff_seg",
        "ENABLE_DEDUPLICATION": "enable_deduplication",
        "ENABLE_SEMANTIC_DEDUPLICATION": "enable_semantic_deduplication",
        "DUPLICATE_POLICY": "duplicate_policy",
        "DUPLICATE_BETTER_MIN_DELTA": "duplicate_better_min_delta",
        "ENABLE_ASSETS_PIPELINE": "enable_assets_pipeline",
        "ENABLE_COVER_ART_ARCHIVE": "enable_cover_art_archive",
        "ENABLE_THEAUDIODB_ARTIST_IMAGES": "enable_theaudiodb_artist_images",
        "ENABLE_ITUNES_COVER_FALLBACK": "enable_itunes_cover_fallback",
        "ENABLE_DEEZER_ARTIST_IMAGES": "enable_deezer_artist_images",
        "ENABLE_WIKIPEDIA_ARTIST_IMAGES": "enable_wikipedia_artist_images",
        "ENABLE_ITUNES_ARTIST_IMAGES": "enable_itunes_artist_images",
        "THEAUDIODB_API_KEY": "theaudiodb_api_key",
        "ASSETS_TIMEOUT_SEG": "assets_timeout_seg",
        "ASSETS_MAX_RETRIES": "assets_max_retries",
        "ASSETS_RETRY_BACKOFF_SEG": "assets_retry_backoff_seg",
        "ASSETS_CACHE_TTL_SEG": "assets_cache_ttl_seg",
        "ASSETS_NEGATIVE_CACHE_TTL_SEG": "assets_negative_cache_ttl_seg",
        "ASSETS_MIN_RESOLUTION": "assets_min_resolution",
        "ASSETS_HD_MAX_IMAGE_BYTES": "assets_hd_max_image_bytes",
        "ENABLE_EXTERNAL_ENRICHMENT": "enable_external_enrichment",
        "ENABLE_LYRICS_ENRICHMENT": "enable_lyrics_enrichment",
        "ENABLE_LRCLIB": "enable_lrclib",
        "ENABLE_LYRICS_OVH": "enable_lyrics_ovh",
        "LYRICS_TIMEOUT_SEG": "lyrics_timeout_seg",
        "LYRICS_MAX_RETRIES": "lyrics_max_retries",
        "LYRICS_RETRY_BACKOFF_SEG": "lyrics_retry_backoff_seg",
        "LYRICS_SUGGEST_LIMIT": "lyrics_suggest_limit",
        "ENABLE_SECOND_STAGE_RESOLUTION": "enable_second_stage_resolution",
        "SECOND_STAGE_MAX_CANDIDATES": "second_stage_max_candidates",
        "SECOND_STAGE_MIN_EVIDENCE": "second_stage_min_evidence",
        "SECOND_STAGE_MIN_GAP": "second_stage_min_gap",
        "SECOND_STAGE_CAUSE_ENABLED": "second_stage_cause_enabled",
        "ENABLE_THIRD_STAGE_RESOLUTION": "enable_third_stage_resolution",
        "THIRD_STAGE_MIN_EVIDENCE": "third_stage_min_evidence",
        "THIRD_STAGE_MIN_GAP": "third_stage_min_gap",
        "ENABLE_IA_DISCOGRAPHY": "enable_ia_discography",
        "DISCOGRAPHY_IA_MIN_CONFIDENCE": "discography_ia_min_confidence",
        "MANIFEST_SCHEMA_VERSION": "manifest_schema_version",
        "ENABLE_OVERRIDES": "enable_overrides",
        "NB_SOUND_PROGRESS_MODE": "nb_sound_progress_mode",
        "NB_SOUND_PROGRESS_INTERVAL_SEC": "nb_sound_progress_interval_sec",
        "SIDECAR_FUTURE_TIMEOUT_SEG": "sidecar_future_timeout_seg",
        "SIDECAR_WAIT_HEARTBEAT_SEG": "sidecar_wait_heartbeat_seg",
                "ENABLE_AUDIO_FEATURES": "enable_audio_features",
        "AUDIO_FEATURES_MODE": "audio_features_mode",
        "AUDIO_FEATURES_ANALYZE_ON_IMPORT": "audio_features_analyze_on_import",
        "AUDIO_FEATURES_BACKGROUND": "audio_features_background",
        "AUDIO_FEATURES_MAX_WORKERS": "audio_features_max_workers",
        "AUDIO_FEATURES_ANALYZE_FULL_TRACK": "audio_features_analyze_full_track",
        "AUDIO_FEATURES_SAMPLE_STRATEGY": "audio_features_sample_strategy",
        "AUDIO_FEATURES_SEGMENT_SECONDS": "audio_features_segment_seconds",
        "AUDIO_FEATURES_REANALYZE_ON_VERSION_CHANGE": "audio_features_reanalyze_on_version_change",
        "AUDIO_FEATURES_FAIL_SILENTLY": "audio_features_fail_silently",
        "ENABLE_AUDIO_INTELLIGENCE_DEEP": "enable_audio_intelligence_deep",
        "AUDIO_INTELLIGENCE_BACKEND": "audio_intelligence_backend",
        "ENABLE_AUDIO_MOOD_MODELS": "enable_audio_mood_models",
        "ENABLE_AUDIO_EMBEDDINGS": "enable_audio_embeddings",
        "ENABLE_AUDIO_TAGGING_MODELS": "enable_audio_tagging_models",
        "AUDIO_INTELLIGENCE_ANALYZE_AFTER_IMPORT_BACKGROUND": "audio_intelligence_analyze_after_import_background",
        "AUDIO_INTELLIGENCE_RESUME_PENDING_ON_STARTUP": "audio_intelligence_resume_pending_on_startup",
        "AUDIO_INTELLIGENCE_BACKGROUND_AUTOSTART": "audio_intelligence_background_autostart",
        "AUDIO_INTELLIGENCE_BACKGROUND": "audio_intelligence_background",
        "AUDIO_INTELLIGENCE_MAX_WORKERS": "audio_intelligence_max_workers",
        "AUDIO_INTELLIGENCE_BACKGROUND_BATCH_SIZE": "audio_intelligence_background_batch_size",
        "AUDIO_INTELLIGENCE_BACKGROUND_IDLE_DELAY_SEC": "audio_intelligence_background_idle_delay_sec",
        "AUDIO_INTELLIGENCE_BACKGROUND_MAX_RUNTIME_MIN": "audio_intelligence_background_max_runtime_min",
        "AUDIO_INTELLIGENCE_MODEL_DIR": "audio_intelligence_model_dir",
        "AUDIO_INTELLIGENCE_ALLOW_MODEL_DOWNLOADS": "audio_intelligence_allow_model_downloads",
        "AUDIO_INTELLIGENCE_SAMPLE_STRATEGY": "audio_intelligence_sample_strategy",
        "AUDIO_INTELLIGENCE_SEGMENT_SECONDS": "audio_intelligence_segment_seconds",
        "AUDIO_INTELLIGENCE_REANALYZE_ON_MODEL_CHANGE": "audio_intelligence_reanalyze_on_model_change",
        "AUDIO_INTELLIGENCE_RETRY_FAILED": "audio_intelligence_retry_failed",
        "AUDIO_INTELLIGENCE_MAX_ATTEMPTS": "audio_intelligence_max_attempts",
        "AUDIO_INTELLIGENCE_CANCEL_DISCARD_OUTPUTS": "audio_intelligence_cancel_discard_outputs",
        "AUDIO_INTELLIGENCE_FAIL_SILENTLY": "audio_intelligence_fail_silently",
        "ENABLE_MUSIC_DISCOVERY": "enable_music_discovery",
        "MUSIC_DISCOVERY_USE_AUDIO_FEATURES": "music_discovery_use_audio_features",
        "MUSIC_DISCOVERY_USE_DEEP_FEATURES": "music_discovery_use_deep_features",
        "MUSIC_DISCOVERY_MIN_CONFIDENCE": "music_discovery_min_confidence",
        "MUSIC_DISCOVERY_DEFAULT_LIMIT": "music_discovery_default_limit",
        "MUSIC_DISCOVERY_EXPLAIN_RESULTS": "music_discovery_explain_results",
    }

    _BASIC_CONFIG_KEYS = _RUTAS_KEYS + [
        "enable_acoustid",
        "acoustid_key",
        "enable_shazam",
    ]

    _ADVANCED_CONFIG_KEYS = [
        "shazam_timeout_seg",
        "shazam_min_duracion_seg",
        "ia_proveedor",
        "anthropic_key",
        "openai_key",
        "enable_ia_tiebreak",
        "ia_tiebreak_min_gap",
        "ia_max_tokens",
        "ia_timeout_seg",
        "skip_already_processed",
        "init_component_max_retries",
        "init_component_retry_backoff_seg",
        "enable_deduplication",
        "enable_semantic_deduplication",
        "duplicate_policy",
        "duplicate_better_min_delta",
        "enable_assets_pipeline",
        "enable_cover_art_archive",
        "enable_theaudiodb_artist_images",
        "enable_itunes_cover_fallback",
        "enable_deezer_artist_images",
        "enable_wikipedia_artist_images",
        "enable_itunes_artist_images",
        "theaudiodb_api_key",
        "assets_timeout_seg",
        "assets_max_retries",
        "assets_retry_backoff_seg",
        "assets_cache_ttl_seg",
        "assets_negative_cache_ttl_seg",
        "assets_min_resolution",
        "assets_hd_max_image_bytes",
        "enable_external_enrichment",
        "enable_lyrics_enrichment",
        "enable_lrclib",
        "enable_lyrics_ovh",
        "lyrics_timeout_seg",
        "lyrics_max_retries",
        "lyrics_retry_backoff_seg",
        "lyrics_suggest_limit",
        "enable_second_stage_resolution",
        "second_stage_max_candidates",
        "second_stage_min_evidence",
        "second_stage_min_gap",
        "second_stage_cause_enabled",
        "enable_third_stage_resolution",
        "third_stage_min_evidence",
        "third_stage_min_gap",
        "enable_ia_discography",
        "discography_ia_min_confidence",
        "manifest_schema_version",
        "enable_overrides",
        "nb_sound_progress_mode",
        "nb_sound_progress_interval_sec",
        "sidecar_future_timeout_seg",
        "sidecar_wait_heartbeat_seg",
        "enable_audio_features","audio_features_mode","audio_features_analyze_on_import","audio_features_background","audio_features_max_workers","audio_features_analyze_full_track","audio_features_sample_strategy","audio_features_segment_seconds","audio_features_reanalyze_on_version_change","audio_features_fail_silently","enable_audio_intelligence_deep","audio_intelligence_backend","enable_audio_mood_models","enable_audio_embeddings","enable_audio_tagging_models","audio_intelligence_analyze_after_import_background","audio_intelligence_resume_pending_on_startup","audio_intelligence_background_autostart","audio_intelligence_background","audio_intelligence_max_workers","audio_intelligence_background_batch_size","audio_intelligence_background_idle_delay_sec","audio_intelligence_background_max_runtime_min","audio_intelligence_model_dir","audio_intelligence_allow_model_downloads","audio_intelligence_sample_strategy","audio_intelligence_segment_seconds","audio_intelligence_reanalyze_on_model_change","audio_intelligence_retry_failed","audio_intelligence_max_attempts","audio_intelligence_cancel_discard_outputs","audio_intelligence_fail_silently","enable_music_discovery","music_discovery_use_audio_features","music_discovery_use_deep_features","music_discovery_min_confidence","music_discovery_default_limit","music_discovery_explain_results",
    ]

    # Defaults sensatos:
    #   - AcoustID arranca apagado: requiere API key. Si la falta, no habilitarlo
    #     ahorra al usuario una llamada de red garantizada en error.
    #   - IA desempate/discografia apagadas: usan modelos externos pagos y
    #     pueden saturar latencia del pipeline si el usuario no configuro key.
    #   - skip_already_processed=1: evita reprocesar archivos al volver a
    #     correr importacion sobre la misma entrada (comportamiento esperado).
    #   - audio_intelligence_backend=essentia_tensorflow: cuando el usuario
    #     active deep, no le pedimos elegir backend; el unico soportado es ese.
    #   - audio_intelligence_model_dir: vacio aqui; se completa al cargar
    #     defaults con la ruta del bootstrap (<assets>/modelos_essentia).
    _DEFAULTS = {
        "enable_shazam": "1",
        "enable_acoustid": "0",
        "enable_ia_tiebreak": "0",
        "acoustid_key": "",
        "anthropic_key": "",
        "openai_key": "",
        "ia_proveedor": "No",
        "score_accept": "0.82",
        "score_review": "0.55",
        "shazam_timeout_seg": "12",
        "shazam_min_duracion_seg": "20",
        "ia_tiebreak_min_gap": "0.12",
        "ia_max_tokens": "512",
        "ia_timeout_seg": "20",
        "skip_already_processed": "1",
        "init_component_max_retries": "2",
        "init_component_retry_backoff_seg": "0.7",
        "enable_deduplication": "1",
        "enable_semantic_deduplication": "1",
        "duplicate_policy": "replace_if_better",
        "duplicate_better_min_delta": "0.08",
        "enable_assets_pipeline": "1",
        "enable_cover_art_archive": "1",
        "enable_theaudiodb_artist_images": "1",
        "enable_itunes_cover_fallback": "1",
        "enable_deezer_artist_images": "1",
        "enable_wikipedia_artist_images": "1",
        "enable_itunes_artist_images": "1",
        "theaudiodb_api_key": "123",
        "assets_timeout_seg": "10",
        "assets_max_retries": "2",
        "assets_retry_backoff_seg": "0.8",
        "assets_cache_ttl_seg": "259200",
        "assets_negative_cache_ttl_seg": "21600",
        "assets_min_resolution": "250",
        "assets_hd_max_image_bytes": "25000000",
        "enable_external_enrichment": "1",
        "enable_lyrics_enrichment": "1",
        "enable_lrclib": "1",
        "enable_lyrics_ovh": "1",
        "lyrics_timeout_seg": "8",
        "lyrics_max_retries": "1",
        "lyrics_retry_backoff_seg": "0.8",
        "lyrics_suggest_limit": "3",
        "enable_second_stage_resolution": "1",
        "second_stage_max_candidates": "5",
        "second_stage_min_evidence": "0.86",
        "second_stage_min_gap": "0.12",
        "second_stage_cause_enabled": "1",
        "enable_third_stage_resolution": "1",
        "third_stage_min_evidence": "0.90",
        "third_stage_min_gap": "0.14",
        "enable_ia_discography": "0",
        "discography_ia_min_confidence": "0.90",
        # Deep audio intelligence: apagado por defecto. Requiere
        # essentia-tensorflow (no embebido en bundles release por tamaño) y
        # modelos descargados aparte. Activarlo sin esas dependencias produce
        # corridas que no analizan nada pero parecen estar trabajando.
        "enable_audio_intelligence_deep": "0",
        "audio_intelligence_backend": "essentia_tensorflow",
        "enable_audio_mood_models": "0",
        "enable_audio_embeddings": "0",
        "enable_audio_tagging_models": "0",
        "audio_intelligence_analyze_after_import_background": "0",
        "audio_intelligence_background": "0",
        "audio_intelligence_background_autostart": "0",
        "audio_intelligence_allow_model_downloads": "0",
        "audio_intelligence_model_dir": "",
        "enable_overrides": "1",
        "manifest_schema_version": "1",
        "nb_sound_progress_mode": "auto",
        "nb_sound_progress_interval_sec": "2.0",
        "sidecar_future_timeout_seg": "90.0",
        "sidecar_wait_heartbeat_seg": "2.0",
        "nombre_usuario": "",
        "foto_perfil": "",
        "tema": "negro_puro",
        "ui_mode": "simple",
        "ui_scale": "100",
        "ui_font_family": "Inter",
        "hotkeys_reproduccion": "{}",
        "tema_custom_nombre": "Personalizado",
        "tema_custom_fondo": "#000000",
        "tema_custom_fondoElevado": "#0a0a0a",
        "tema_custom_superficie": "#121212",
        "tema_custom_superficieAlt": "#1a1a1a",
        "tema_custom_borde": "#2a2a2a",
        "tema_custom_texto": "#ffffff",
        "tema_custom_textoSec": "#9eb2cd",
        "tema_custom_textoMuted": "#7286a3",
        "tema_custom_acento": "#47c8ff",
        "tema_custom_acentoFuerte": "#22b6ff",
        "tema_custom_hover": "#1b2b43",
        "tema_custom_seleccion": "#233a58",
        "tema_custom_exito": "#3ecf8e",
        "tema_custom_peligro": "#ff5d73",
        "tema_custom_advertencia": "#ffb454",
        "tema_custom_modoBoxFondo": "",
        "tema_custom_modoBoxBorde": "",
    }

    _FUENTES_PREFERIDAS = [
        "Inter", "Noto Sans", "Noto Sans UI", "Segoe UI", "SF Pro Text",
        "Roboto", "Open Sans", "Ubuntu", "Cantarell", "Source Sans 3",
        "Source Sans Pro", "Fira Sans", "Fira Sans Condensed", "IBM Plex Sans",
        "Atkinson Hyperlegible", "Manrope", "Work Sans", "Nunito Sans",
        "Montserrat", "Lato", "Liberation Sans", "Arial", "Helvetica",
        "DejaVu Sans", "Noto Serif", "Liberation Serif", "DejaVu Serif",
        "JetBrains Mono", "Fira Code", "Fira Mono", "Source Code Pro",
        "IBM Plex Mono", "Cascadia Mono", "DejaVu Sans Mono",
    ]

    _FONT_DENYLIST_TOKENS = {
        "symbol", "symbols", "ding", "dingbats", "webdings", "wingdings",
        "emoji", "emoticon", "icons", "icon", "awesome", "material",
        "math", "music", "braille", "fallback", "unifont", "opensymbol",
        "ukai", "uming", "droid sans fallback", "cjk", "han", "hangul",
        "kana", "arabic", "hebrew", "thai", "devanagari", "bengali",
        "gujarati", "gurmukhi", "tamil", "telugu", "kannada", "malayalam",
        "sinhala", "tibetan", "lao", "khmer", "armenian", "ethiopic",
        "cherokee", "georgian", "mongolian", "myanmar", "syriac",
        "d050", "c059", "p052", "z003",
    }
    _FONT_PREFIX_DENYLIST = ("ar pl ",)
    _FONT_STYLE_DENYLIST_TOKENS = {
        "black", "bold", "book", "compressed", "eight", "extralight",
        "extra light", "four", "hair", "heavy", "light", "medium",
        "narrow", "semibold", "semi bold", "thin", "two", "ultralight",
        "ultra light",
    }
    _FONT_EXTRA_SAFE_FAMILIES = {
        "freesans", "freeserif", "freemono", "liberation mono",
        "monospace", "sans serif", "serif", "noto mono", "noto sans mono",
        "nimbus sans", "nimbus roman", "nimbus mono ps",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: dict = {}
        self._cargar()
        self._ultima_guardada = ""
        self._sincronizar_fuente_ui()

    def _to_dict(self, data) -> dict:
        if isinstance(data, QJSValue):
            data = data.toVariant()
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _valor_config_texto(valor) -> str:
        if isinstance(valor, bool):
            return "1" if valor else "0"
        if valor is None:
            return ""
        return str(valor).strip()

    @classmethod
    def _defaults_desde_settings(cls) -> dict[str, str]:
        from config import settings

        defaults: dict[str, str] = {}
        for env_name, config_key in cls._ENV_TO_CONFIG_KEY.items():
            if hasattr(settings, env_name):
                defaults[config_key] = cls._valor_config_texto(getattr(settings, env_name))
        defaults["score_accept"] = cls._valor_config_texto(getattr(settings, "SCORE_THRESHOLD_ACCEPT", 0.82))
        defaults["score_review"] = cls._valor_config_texto(getattr(settings, "SCORE_THRESHOLD_REVIEW", 0.55))
        return defaults

    # Claves cuyo valor por defecto debe venir SIEMPRE de _DEFAULTS (UI) y
    # nunca ser sobrescrito por config.settings. Permite que la UI exponga
    # un default mas conservador que el del modulo settings (que se mantiene
    # como hasta ahora para no romper tests / scripts CLI que dependian de
    # esos defaults).
    _DEFAULTS_UI_GANA = frozenset({
        "enable_acoustid",
        "enable_ia_tiebreak",
        "enable_ia_discography",
        "skip_already_processed",
        "enable_audio_intelligence_deep",
        "audio_intelligence_backend",
        "enable_audio_mood_models",
        "enable_audio_embeddings",
        "enable_audio_tagging_models",
        "audio_intelligence_analyze_after_import_background",
        "audio_intelligence_background",
        "audio_intelligence_background_autostart",
        "audio_intelligence_allow_model_downloads",
        "audio_intelligence_model_dir",
    })

    @classmethod
    def _model_dir_recomendado(cls) -> str:
        """Ruta sugerida para modelos Essentia: `<assets>/modelos_essentia`.
        Se computa lazy a partir de la ruta de assets que ya conoce el bootstrap,
        para que esa carpeta este alineada con el resto de datos del usuario.
        """
        try:
            from config import settings
            assets = settings.DEFAULT_ASSETS_DIR
            if assets is not None:
                return str(Path(assets) / "modelos_essentia")
        except Exception:
            pass
        try:
            from infra.bootstrap import resolver_rutas_estandar
            rutas = resolver_rutas_estandar()
            return str(rutas.assets / "modelos_essentia")
        except Exception:
            return ""

    def _defaults_config(self) -> dict[str, str]:
        defaults = dict(self._DEFAULTS)
        # _defaults_desde_settings sobrescribe lo de _DEFAULTS, EXCEPTO para
        # las claves que la UI considera owned (apagar deep / IA por defecto,
        # forzar backend essentia_tf, etc.). Para esas, _DEFAULTS gana.
        desde_settings = self._defaults_desde_settings()
        for k, v in desde_settings.items():
            if k in self._DEFAULTS_UI_GANA:
                continue
            defaults[k] = v
        # audio_intelligence_model_dir: el _DEFAULTS lo deja vacio para que
        # esta funcion compute la ruta concreta en runtime. Si quedo vacio,
        # rellenarla con la ruta recomendada bajo `<assets>/modelos_essentia`.
        if not defaults.get("audio_intelligence_model_dir"):
            defaults["audio_intelligence_model_dir"] = self._model_dir_recomendado()
        return defaults

    def _fallbacks_rutas(self) -> dict[str, str]:
        from config.settings import DEFAULT_ASSETS_DIR, DEFAULT_CACHE_DIR, DEFAULT_MANIFESTS_DIR, DEFAULT_TEMP_DIR

        return {
            "dir_assets": str(DEFAULT_ASSETS_DIR) if DEFAULT_ASSETS_DIR else "",
            "dir_cache": str(DEFAULT_CACHE_DIR) if DEFAULT_CACHE_DIR else "",
            "dir_temp": str(DEFAULT_TEMP_DIR) if DEFAULT_TEMP_DIR else "",
            "dir_manifests": str(DEFAULT_MANIFESTS_DIR) if DEFAULT_MANIFESTS_DIR else "",
        }

    def _rutas_recomendadas(self) -> dict[str, str]:
        """Rutas sugeridas para usuarios sin configuracion previa.

        Se sincronizan con :func:`infra.bootstrap.resolver_rutas_estandar`
        para que las carpetas que muestra la UI sean **exactamente** las que
        el bootstrap creó en el primer arranque. Si tuvieran rutas distintas
        (ej. el modelo recomendara ``~/Music/entrada`` mientras bootstrap
        creara ``~/Music/NBSound_Entrada``), el usuario apuntaría a una
        carpeta que no existe y la importación fallaría sin pista visible.
        """
        try:
            from infra.bootstrap import resolver_rutas_estandar
            rutas = resolver_rutas_estandar()
            return {
                "dir_entrada": str(rutas.input_dir),
                "dir_biblioteca": str(rutas.library),
                "dir_cuarentena": str(rutas.quarantine),
                "dir_revision": str(rutas.review),
                "dir_logs": str(rutas.logs),
                "dir_procesados": str(rutas.processed),
                "dir_assets": str(rutas.assets),
                "dir_cache": str(rutas.cache),
                "dir_temp": str(rutas.temp),
                "dir_manifests": str(rutas.manifests),
            }
        except Exception:
            # Fallback minimo si el bootstrap no pudiera resolverse.
            home = Path.home()
            musica = home / "Música"
            if not musica.exists():
                musica = home / "Music"
            base = musica if musica.exists() else home / "NBSound"
            return {
                "dir_entrada": str(base / "NBSound_Entrada"),
                "dir_biblioteca": str(base / "biblioteca"),
                "dir_cuarentena": str(base / "cuarentena"),
                "dir_revision": str(base / "revision"),
                "dir_logs": str(base / "logs"),
                "dir_procesados": str(base / "procesados"),
                "dir_assets": str(base / "assets"),
                "dir_cache": str(base / "cache"),
                "dir_temp": str(base / "tmp"),
                "dir_manifests": str(base / "manifests"),
            }

    def _defaults_rutas_basica(self) -> dict[str, str]:
        from config import settings

        recomendadas = self._rutas_recomendadas()
        rutas: dict[str, str] = {}
        for clave, attr in self._RUTAS_DEFAULT_ATTRS.items():
            valor_settings = self._valor_config_texto(getattr(settings, attr, ""))
            rutas[clave] = valor_settings or recomendadas[clave]
        return rutas

    def _cargar(self) -> None:
        from db.conexion import obtener_config
        defaults = self._defaults_config()
        rutas_default = self._defaults_rutas_basica()
        self._config = {
            clave: obtener_config(clave, valor)
            for clave, valor in rutas_default.items()
        }
        for k, v in defaults.items():
            if k in self._config:
                continue
            self._config[k] = obtener_config(k, v)
        # Reflejar las rutas persistidas en el modulo settings ANTES de que
        # cualquier servicio (Reproductor, Biblioteca, EnrichmentPipeline,
        # CacheLocal, GestorManifests) las consulte. Sin esto, los servicios
        # ven los DEFAULT_*_DIR resueltos al importar config.settings (que
        # caen al fallback XDG/AppData) en lugar de la ruta configurada.
        self._sincronizar_settings_runtime(self._config)

    @classmethod
    def _fuentes_sistema(cls) -> list[str]:
        if QGuiApplication.instance() is None:
            return []
        try:
            fuentes = [str(f).strip() for f in QFontDatabase.families()]
        except Exception as exc:
            _log.warning("No fue posible consultar fuentes del sistema: %s", exc)
            return []
        vistas = set()
        salida: list[str] = []
        for fuente in fuentes:
            if fuente and fuente not in vistas:
                vistas.add(fuente)
                salida.append(fuente)
        return salida

    @classmethod
    def _fuente_legible_ui(cls, fuente: str) -> bool:
        nombre = str(fuente or "").strip()
        if not nombre:
            return False
        lower = nombre.lower()
        if any(lower.startswith(prefijo) for prefijo in cls._FONT_PREFIX_DENYLIST):
            return False
        if any(token in lower for token in cls._FONT_DENYLIST_TOKENS):
            return False
        if not re.fullmatch(r"[A-Za-z0-9À-ÿ .,+_\-/()[\]&']+", nombre):
            return False
        if nombre in cls._FUENTES_PREFERIDAS:
            return True
        if any(re.search(rf"(^|[\s_-]){re.escape(token)}($|[\s_-])", lower) for token in cls._FONT_STYLE_DENYLIST_TOKENS):
            return False
        if len(nombre.split()) > 4:
            return False
        normalizada = re.sub(r"\s*\[.*\]\s*$", "", lower).strip()
        return normalizada in cls._FONT_EXTRA_SAFE_FAMILIES

    @classmethod
    def _fuentes_ui_legibles(cls) -> list[str]:
        fuentes = cls._fuentes_sistema()
        if not fuentes:
            return []
        disponibles = set(fuentes)
        salida: list[str] = []
        vistos: set[str] = set()
        for fuente in [*cls._FUENTES_PREFERIDAS, *fuentes]:
            if fuente not in disponibles or fuente in vistos:
                continue
            if not cls._fuente_legible_ui(fuente):
                continue
            clave_vista = fuente if fuente in cls._FUENTES_PREFERIDAS else re.sub(r"\s*\[.*\]\s*$", "", fuente.lower()).strip()
            if clave_vista in vistos:
                continue
            vistos.add(clave_vista)
            salida.append(fuente)
        return salida

    @classmethod
    def _resolver_fuente_ui(cls, fuente: str) -> str:
        solicitada = str(fuente or "").strip()
        fuentes = cls._fuentes_ui_legibles()
        if not fuentes:
            return solicitada or "Inter"
        if solicitada in fuentes:
            return solicitada

        app = QGuiApplication.instance()
        candidatas = [*cls._FUENTES_PREFERIDAS]
        if app is not None:
            candidatas.append(app.font().family())
        for candidata in candidatas:
            if candidata in fuentes:
                return candidata
        return fuentes[0]

    @classmethod
    def _aplicar_fuente_global(cls, fuente: str) -> str:
        familia = cls._resolver_fuente_ui(fuente)
        app = QGuiApplication.instance()
        if app is not None:
            app.setFont(QFont(familia))
        return familia

    def _sincronizar_fuente_ui(self) -> None:
        self._config["ui_font_family"] = self._aplicar_fuente_global(
            self._config.get("ui_font_family", self._DEFAULTS["ui_font_family"])
        )

    # Mapa de claves dir_* del UI -> atributos DEFAULT_*_DIR del modulo settings.
    # Cuando el usuario cambia una ruta y la guarda, ademas de persistirla en
    # config_ui hay que sobrescribir el atributo del modulo para que el resto
    # del backend (audit, manifests, enrichment, cache externo, reproductor,
    # biblioteca de portadas) lo vea en runtime sin reiniciar la app. Los
    # modulos consumidores acceden via `settings.DEFAULT_X_DIR` (lazy lookup),
    # no via `from config.settings import DEFAULT_X_DIR` (snapshot al importar).
    _CLAVES_DIR_A_SETTINGS = {
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

    # Claves que NO son rutas DEFAULT_*_DIR pero también deben volcarse al
    # módulo settings cuando se guardan, porque servicios del backend las
    # leen vía `getattr(settings, X)`. Diferencia con _CLAVES_DIR_A_SETTINGS:
    # estos atributos son strings simples, no Path.
    _CLAVES_STR_A_SETTINGS = {
        "audio_intelligence_model_dir": "AUDIO_INTELLIGENCE_MODEL_DIR",
        "audio_intelligence_backend":   "AUDIO_INTELLIGENCE_BACKEND",
    }

    @classmethod
    def _sincronizar_settings_runtime(cls, datos: dict[str, str]) -> None:
        """Sobrescribe los atributos del modulo settings cuando los valores
        correspondientes cambian en config_ui. Sin esto, el backend usa los
        valores resueltos al importar (fallback XDG / vacío) ignorando lo
        guardado por el usuario.

        Cubre dos familias:
          - Rutas Path (DEFAULT_*_DIR) listadas en _CLAVES_DIR_A_SETTINGS.
          - Strings simples (AUDIO_INTELLIGENCE_MODEL_DIR / BACKEND) listados
            en _CLAVES_STR_A_SETTINGS.
        """
        try:
            from config import settings as _cfg
        except Exception:
            return
        for clave, attr in cls._CLAVES_DIR_A_SETTINGS.items():
            if clave not in datos:
                continue
            valor = str(datos[clave]).strip()
            if not valor:
                continue
            try:
                setattr(_cfg, attr, Path(valor).expanduser().resolve())
            except Exception:
                continue
        for clave, attr in cls._CLAVES_STR_A_SETTINGS.items():
            if clave not in datos:
                continue
            valor = str(datos[clave]).strip()
            try:
                setattr(_cfg, attr, valor)
            except Exception:
                continue

    def _guardar_multiples(self, datos: dict[str, str]) -> None:
        from db.conexion import guardar_config
        for clave, valor in datos.items():
            guardar_config(clave, str(valor))
            self._config[clave] = str(valor)
            self._ultima_guardada = clave
        # Reflejar inmediatamente los cambios de rutas en el modulo settings.
        self._sincronizar_settings_runtime(datos)
        self.guardadoCambiado.emit()
        self.configuracionCambiada.emit()

    def _normalizar_y_crear_ruta(self, clave: str, valor: str) -> tuple[bool, str, str]:
        try:
            ruta = Path(valor).expanduser().resolve()
            if ruta.exists() and not ruta.is_dir():
                return False, "", f"{clave}: existe y no es carpeta"
            ruta.mkdir(parents=True, exist_ok=True)
            return True, str(ruta), ""
        except Exception as exc:
            return False, "", f"{clave}: {exc}"

    def _validar_ruta_sin_crear(self, clave: str, valor: str, obligatoria: bool) -> tuple[bool, str, str]:
        texto = str(valor or "").strip()
        if not texto:
            if obligatoria:
                return False, "", f"{clave}: campo obligatorio"
            return True, "", ""
        try:
            ruta = Path(texto).expanduser().resolve()
            if ruta.exists():
                if not ruta.is_dir():
                    return False, "", f"{clave}: existe y no es carpeta"
                if not os.access(ruta, os.R_OK | os.W_OK):
                    return False, "", f"{clave}: sin permisos de lectura/escritura"
                return True, str(ruta), ""

            padre = ruta.parent
            while not padre.exists() and padre != padre.parent:
                padre = padre.parent
            if padre.exists() and not os.access(padre, os.W_OK):
                return False, "", f"{clave}: sin permisos para crear dentro de {padre}"
            return True, str(ruta), ""
        except Exception as exc:
            return False, "", f"{clave}: {exc}"

    def _payload_validacion_rutas(self, incoming: dict) -> tuple[dict[str, str], dict[str, str]]:
        normalizadas: dict[str, str] = {}
        errores: dict[str, str] = {}
        for key in self._RUTAS_REQUIRED_KEYS:
            ok, ruta, error = self._validar_ruta_sin_crear(key, incoming.get(key, ""), True)
            if ok:
                normalizadas[key] = ruta
            else:
                errores[key] = error

        for key in self._RUTAS_OPTIONAL_KEYS:
            valor = str(incoming.get(key, "")).strip()
            if not valor:
                continue
            ok, ruta, error = self._validar_ruta_sin_crear(key, valor, False)
            if ok and ruta:
                normalizadas[key] = ruta
            elif not ok:
                errores[key] = error
        return normalizadas, errores

    @Slot("QVariant", result="QVariantMap")
    def validar_rutas_basica(self, data) -> dict:
        incoming = self._to_dict(data)
        normalizadas, errores = self._payload_validacion_rutas(incoming)
        mensaje = "Rutas válidas" if not errores else " | ".join(errores.values())
        return {
            "ok": not errores,
            "mensaje": mensaje,
            "erroresPorClave": errores,
            "rutas": normalizadas,
        }

    @Slot(str, result=str)
    def ruta_local_desde_url(self, url: str) -> str:
        qurl = QUrl(str(url))
        if qurl.isLocalFile():
            return qurl.toLocalFile()
        texto = str(url or "")
        if texto.startswith("file://"):
            return QUrl(texto).toLocalFile()
        return texto

    @Property("QVariant", notify=configuracionCambiada)
    def valores(self) -> dict:
        return self._config

    @Slot(str, result=str)
    def obtener(self, clave: str) -> str:
        if clave in self._config:
            return self._config[clave]
        # Preferencias de UI guardadas con guardar() que no figuran en los
        # defaults (p. ej. playlists_modo_vista, playlists_categoria) no se
        # cargan en _config al arranque, así que sin este fallback se perdían
        # entre sesiones (la BD las tenía, pero obtener() devolvía ""). Las
        # recuperamos de config_ui y las cacheamos para no penalizar lecturas
        # posteriores (este getter es un hot path en bindings QML).
        from db.conexion import obtener_config

        valor = obtener_config(clave, "")
        self._config[clave] = valor
        return valor

    @Slot(str, str)
    def guardar(self, clave: str, valor: str) -> None:
        if clave == "ui_font_family":
            valor = self._aplicar_fuente_global(valor)
        self._guardar_multiples({clave: valor})

    @Property(str, notify=guardadoCambiado)
    def ultima_guardada(self) -> str:
        return self._ultima_guardada

    @Property("QVariantList", notify=configuracionCambiada)
    def fuentes_disponibles(self) -> list[str]:
        fuentes = self._fuentes_ui_legibles()
        if not fuentes:
            return [self.obtener("ui_font_family") or "Inter"]
        return fuentes

    @Slot(result=bool)
    def rutas_configuradas(self) -> bool:
        return all(self._config.get(r, "").strip() for r in self._RUTAS_REQUIRED_KEYS)

    @Slot(result="QVariantMap")
    def rutas_recomendadas(self) -> dict:
        return self._rutas_recomendadas()

    @Slot(str, result=str)
    def fallback_ruta(self, clave: str) -> str:
        return self._fallbacks_rutas().get(clave, "")

    @Slot(result="QVariantMap")
    def tema_personalizado_desde_config(self) -> dict:
        modo_box_fondo = str(self._config.get("tema_custom_modoBoxFondo", "")).strip()
        if not modo_box_fondo:
            modo_box_fondo = self._config.get("tema_custom_fondoElevado", self._DEFAULTS["tema_custom_fondoElevado"])

        modo_box_borde = str(self._config.get("tema_custom_modoBoxBorde", "")).strip()
        if not modo_box_borde:
            modo_box_borde = self._config.get("tema_custom_borde", self._DEFAULTS["tema_custom_borde"])

        tema = {
            "nombre": self._config.get("tema_custom_nombre", self._DEFAULTS["tema_custom_nombre"]),
            "fondo": self._config.get("tema_custom_fondo", self._DEFAULTS["tema_custom_fondo"]),
            "fondoElevado": self._config.get("tema_custom_fondoElevado", self._DEFAULTS["tema_custom_fondoElevado"]),
            "superficie": self._config.get("tema_custom_superficie", self._DEFAULTS["tema_custom_superficie"]),
            "superficieAlt": self._config.get("tema_custom_superficieAlt", self._DEFAULTS["tema_custom_superficieAlt"]),
            "borde": self._config.get("tema_custom_borde", self._DEFAULTS["tema_custom_borde"]),
            "texto": self._config.get("tema_custom_texto", self._DEFAULTS["tema_custom_texto"]),
            "textoSec": self._config.get("tema_custom_textoSec", self._DEFAULTS["tema_custom_textoSec"]),
            "textoMuted": self._config.get("tema_custom_textoMuted", self._DEFAULTS["tema_custom_textoMuted"]),
            "acento": self._config.get("tema_custom_acento", self._DEFAULTS["tema_custom_acento"]),
            "acentoFuerte": self._config.get("tema_custom_acentoFuerte", self._DEFAULTS["tema_custom_acentoFuerte"]),
            "hover": self._config.get("tema_custom_hover", self._DEFAULTS["tema_custom_hover"]),
            "seleccion": self._config.get("tema_custom_seleccion", self._DEFAULTS["tema_custom_seleccion"]),
            "exito": self._config.get("tema_custom_exito", self._DEFAULTS["tema_custom_exito"]),
            "peligro": self._config.get("tema_custom_peligro", self._DEFAULTS["tema_custom_peligro"]),
            "advertencia": self._config.get("tema_custom_advertencia", self._DEFAULTS["tema_custom_advertencia"]),
            "modoBoxFondo": modo_box_fondo,
            "modoBoxBorde": modo_box_borde,
        }
        return tema

    def guardar_tema_personalizado(self, tema: dict[str, str]) -> None:
        payload = {
            "tema_custom_nombre": tema.get("nombre", "Personalizado"),
            "tema_custom_fondo": tema.get("fondo", self._DEFAULTS["tema_custom_fondo"]),
            "tema_custom_fondoElevado": tema.get("fondoElevado", self._DEFAULTS["tema_custom_fondoElevado"]),
            "tema_custom_superficie": tema.get("superficie", self._DEFAULTS["tema_custom_superficie"]),
            "tema_custom_superficieAlt": tema.get("superficieAlt", self._DEFAULTS["tema_custom_superficieAlt"]),
            "tema_custom_borde": tema.get("borde", self._DEFAULTS["tema_custom_borde"]),
            "tema_custom_texto": tema.get("texto", self._DEFAULTS["tema_custom_texto"]),
            "tema_custom_textoSec": tema.get("textoSec", self._DEFAULTS["tema_custom_textoSec"]),
            "tema_custom_textoMuted": tema.get("textoMuted", self._DEFAULTS["tema_custom_textoMuted"]),
            "tema_custom_acento": tema.get("acento", self._DEFAULTS["tema_custom_acento"]),
            "tema_custom_acentoFuerte": tema.get("acentoFuerte", self._DEFAULTS["tema_custom_acentoFuerte"]),
            "tema_custom_hover": tema.get("hover", self._DEFAULTS["tema_custom_hover"]),
            "tema_custom_seleccion": tema.get("seleccion", self._DEFAULTS["tema_custom_seleccion"]),
            "tema_custom_exito": tema.get("exito", self._DEFAULTS["tema_custom_exito"]),
            "tema_custom_peligro": tema.get("peligro", self._DEFAULTS["tema_custom_peligro"]),
            "tema_custom_advertencia": tema.get("advertencia", self._DEFAULTS["tema_custom_advertencia"]),
            "tema_custom_modoBoxFondo": tema.get("modoBoxFondo", tema.get("fondoElevado", self._DEFAULTS["tema_custom_fondoElevado"])),
            "tema_custom_modoBoxBorde": tema.get("modoBoxBorde", tema.get("borde", self._DEFAULTS["tema_custom_borde"])),
        }
        self._guardar_multiples(payload)

    @Slot("QVariant", result="QVariantMap")
    def guardar_basica(self, data) -> dict:
        incoming = self._to_dict(data)
        normalizadas: dict[str, str] = {}
        errores: list[str] = []
        for key in self._RUTAS_REQUIRED_KEYS:
            valor = str(incoming.get(key, "")).strip()
            if not valor:
                errores.append(f"{key}: campo obligatorio")
                continue
            ok, ruta, error = self._normalizar_y_crear_ruta(key, valor)
            if not ok:
                errores.append(error)
            else:
                normalizadas[key] = ruta
        for key in self._RUTAS_OPTIONAL_KEYS:
            valor = str(incoming.get(key, "")).strip()
            if not valor:
                valor = self.fallback_ruta(key) or self._rutas_recomendadas().get(key, "")
            if not valor:
                continue
            ok, ruta, error = self._normalizar_y_crear_ruta(key, valor)
            if not ok:
                errores.append(error)
            else:
                normalizadas[key] = ruta
        if errores:
            return {"ok": False, "mensaje": " | ".join(errores), "rutas": normalizadas}

        def _bool_key(clave: str, default: str = "1") -> str:
            return "1" if str(incoming.get(clave, self._config.get(clave, default))) == "1" else "0"

        precision = str(incoming.get("precision_mode", "equilibrado"))
        if precision == "conservador":
            score_accept, score_review = "0.88", "0.62"
        elif precision == "flexible":
            score_accept, score_review = "0.76", "0.48"
        else:
            score_accept, score_review = "0.82", "0.55"

        # Validacion de coherencia AcoustID <-> API key.
        # AcoustID requiere clave para funcionar (cualquier llamada falla con
        # 401 sin key). Si el usuario marca "activar" sin proveer clave,
        # forzamos enable_acoustid=0 antes de persistir y avisamos por el
        # mensaje de retorno para que la UI pueda mostrar el por que.
        acoustid_key = str(incoming.get("acoustid_key", self._config.get("acoustid_key", ""))).strip()
        enable_acoustid_raw = _bool_key("enable_acoustid")
        coherencia_aviso = ""
        if enable_acoustid_raw == "1" and not acoustid_key:
            enable_acoustid_raw = "0"
            coherencia_aviso = (
                " AcoustID se guardó desactivado porque requiere una API key."
            )

        payload = {
            **normalizadas,
            "enable_acoustid": enable_acoustid_raw,
            "acoustid_key": acoustid_key,
            "enable_shazam": _bool_key("enable_shazam"),
            "score_accept": score_accept,
            "score_review": score_review,
        }
        self._guardar_multiples(payload)
        mensaje = "Configuración básica guardada correctamente" + coherencia_aviso
        return {"ok": True, "mensaje": mensaje, "rutas": normalizadas}

    @Slot("QVariant", result="QVariantMap")
    def guardar_avanzada(self, data) -> dict:
        incoming = self._to_dict(data)
        def _bool_key(clave: str, default: str = "1") -> str:
            return "1" if str(incoming.get(clave, self._config.get(clave, default))) == "1" else "0"

        def _float_key(clave: str, default: str, minimo: float, maximo: float) -> float:
            valor = float(incoming.get(clave, self._config.get(clave, default)))
            if valor < minimo or valor > maximo:
                raise ValueError(f"{clave} fuera de rango ({minimo}..{maximo})")
            return valor

        def _int_key(clave: str, default: str, minimo: int, maximo: int) -> int:
            valor = int(float(incoming.get(clave, self._config.get(clave, default))))
            if valor < minimo or valor > maximo:
                raise ValueError(f"{clave} fuera de rango ({minimo}..{maximo})")
            return valor

        try:
            if "score_accept" in incoming or "score_review" in incoming:
                score_accept = _float_key("score_accept", "0.82", 0.0, 1.0)
                score_review = _float_key("score_review", "0.55", 0.0, 1.0)
                if score_review > score_accept:
                    return {"ok": False, "mensaje": "Debe cumplirse 0 <= score_review <= score_accept <= 1."}
            shazam_timeout = _int_key("shazam_timeout_seg", "12", 1, 120)
            shazam_min_dur = _int_key("shazam_min_duracion_seg", "20", 1, 900)
            ia_min_gap = _float_key("ia_tiebreak_min_gap", "0.12", 0.0, 1.0)
            ia_max_tokens = _int_key("ia_max_tokens", "512", 64, 8192)
            ia_timeout = _int_key("ia_timeout_seg", "20", 1, 180)
            init_retries = _int_key("init_component_max_retries", "2", 0, 10)
            init_backoff = _float_key("init_component_retry_backoff_seg", "0.7", 0.1, 30.0)
            duplicate_delta = _float_key("duplicate_better_min_delta", "0.08", 0.0, 1.0)
            assets_timeout = _int_key("assets_timeout_seg", "10", 1, 300)
            assets_retries = _int_key("assets_max_retries", "2", 0, 12)
            assets_backoff = _float_key("assets_retry_backoff_seg", "0.8", 0.1, 30.0)
            assets_cache_ttl = _int_key("assets_cache_ttl_seg", "259200", 60, 31536000)
            assets_negative_ttl = _int_key("assets_negative_cache_ttl_seg", "21600", 60, 31536000)
            assets_min_res = _int_key("assets_min_resolution", "250", 64, 4096)
            assets_hd_max_bytes = _int_key("assets_hd_max_image_bytes", "25000000", 1000000, 100000000)
            lyrics_timeout = _int_key("lyrics_timeout_seg", "8", 2, 300)
            lyrics_retries = _int_key("lyrics_max_retries", "1", 0, 5)
            lyrics_backoff = _float_key("lyrics_retry_backoff_seg", "0.8", 0.1, 30.0)
            lyrics_suggest_limit = _int_key("lyrics_suggest_limit", "3", 0, 10)
            second_stage_max = _int_key("second_stage_max_candidates", "5", 1, 50)
            second_stage_min_evidence = _float_key("second_stage_min_evidence", "0.86", 0.0, 1.0)
            second_stage_min_gap = _float_key("second_stage_min_gap", "0.12", 0.0, 1.0)
            third_stage_min_evidence = _float_key("third_stage_min_evidence", "0.90", 0.0, 1.0)
            third_stage_min_gap = _float_key("third_stage_min_gap", "0.14", 0.0, 1.0)
            discography_min_confidence = _float_key("discography_ia_min_confidence", "0.90", 0.0, 1.0)
            manifest_schema = _int_key("manifest_schema_version", "1", 1, 99)
            progress_interval = _float_key("nb_sound_progress_interval_sec", "2.0", 0.25, 60.0)
            sidecar_future_timeout = _float_key("sidecar_future_timeout_seg", "90.0", 5.0, 3600.0)
            sidecar_heartbeat = _float_key("sidecar_wait_heartbeat_seg", "2.0", 0.25, 60.0)
            audio_features_workers = _int_key("audio_features_max_workers", "1", 1, 8)
            audio_features_segment = _int_key("audio_features_segment_seconds", "90", 1, 3600)
            deep_workers = _int_key("audio_intelligence_max_workers", "1", 1, 4)
            deep_batch_size = _int_key("audio_intelligence_background_batch_size", "1", 1, 50)
            deep_idle_delay = _float_key("audio_intelligence_background_idle_delay_sec", "2.0", 0.0, 3600.0)
            deep_max_runtime = _int_key("audio_intelligence_background_max_runtime_min", "0", 0, 1440)
            deep_segment = _int_key("audio_intelligence_segment_seconds", "120", 1, 3600)
            deep_max_attempts = _int_key("audio_intelligence_max_attempts", "1", 1, 20)
            discovery_confidence = _float_key("music_discovery_min_confidence", "0.35", 0.0, 1.0)
            discovery_limit = _int_key("music_discovery_default_limit", "25", 1, 500)
        except ValueError as exc:
            return {"ok": False, "mensaje": f"Revisa los campos numéricos del módulo avanzado. {exc}"}

        proveedor = str(incoming.get("ia_proveedor", self._config.get("ia_proveedor", "No")))
        if proveedor not in {"No", "Anthropic", "OpenAI"}:
            proveedor = "No"
        anthropic_key = str(incoming.get("anthropic_key", self._config.get("anthropic_key", ""))).strip()
        openai_key = str(incoming.get("openai_key", self._config.get("openai_key", ""))).strip()
        enable_ia_tiebreak = _bool_key("enable_ia_tiebreak")
        enable_ia_discography = _bool_key("enable_ia_discography")
        ia_solicitada = enable_ia_tiebreak == "1" or enable_ia_discography == "1"
        proveedor_listo = (
            (proveedor == "OpenAI" and bool(openai_key))
            or (proveedor == "Anthropic" and bool(anthropic_key))
        )
        ia_normalizada = ia_solicitada and not proveedor_listo
        if ia_normalizada:
            proveedor = "No"
            enable_ia_tiebreak = "0"
            enable_ia_discography = "0"
        elif not ia_solicitada:
            proveedor = "No"

        progress_mode = str(incoming.get("nb_sound_progress_mode", self._config.get("nb_sound_progress_mode", "auto"))).strip().lower()
        if progress_mode not in {"auto", "tty", "log", "quiet"}:
            return {"ok": False, "mensaje": "NB_SOUND_PROGRESS_MODE debe ser auto, tty, log o quiet."}

        duplicate_policy = str(incoming.get("duplicate_policy", self._config.get("duplicate_policy", "replace_if_better"))).strip()
        if duplicate_policy not in {"replace_if_better", "prefer_new_if_quality_higher"}:
            duplicate_policy = "replace_if_better"

        audio_features_mode = str(incoming.get("audio_features_mode", self._config.get("audio_features_mode", "light"))).strip()
        if audio_features_mode not in {"light", "standard"}:
            return {"ok": False, "mensaje": "AUDIO_FEATURES_MODE debe ser light o standard."}
        audio_features_sample = str(incoming.get("audio_features_sample_strategy", self._config.get("audio_features_sample_strategy", "smart_segments"))).strip()
        if audio_features_sample not in {"smart_segments", "first_segment", "middle_segment", "full_track"}:
            return {"ok": False, "mensaje": "AUDIO_FEATURES_SAMPLE_STRATEGY inválido."}

        deep_backend = str(incoming.get("audio_intelligence_backend", self._config.get("audio_intelligence_backend", "none"))).strip().lower()
        if deep_backend not in {"none", "essentia", "essentia_tensorflow", "essentia-tensorflow"}:
            return {"ok": False, "mensaje": "AUDIO_INTELLIGENCE_BACKEND debe ser none o essentia_tensorflow."}
        if deep_backend == "essentia-tensorflow":
            deep_backend = "essentia_tensorflow"
        deep_sample = str(incoming.get("audio_intelligence_sample_strategy", self._config.get("audio_intelligence_sample_strategy", "smart_segments"))).strip()
        if deep_sample not in {"smart_segments", "first_segment", "middle_segment", "full_track"}:
            return {"ok": False, "mensaje": "AUDIO_INTELLIGENCE_SAMPLE_STRATEGY inválido."}
        model_dir = str(incoming.get("audio_intelligence_model_dir", self._config.get("audio_intelligence_model_dir", ""))).strip()
        enable_deep = _bool_key("enable_audio_intelligence_deep", "0")
        allow_downloads = _bool_key("audio_intelligence_allow_model_downloads", "0")
        warnings: list[str] = []

        # Validacion de coherencia deep <-> backend / modelos / runtime.
        # Si enable_deep=1 pero faltan pre-condiciones (backend none, modelos
        # ausentes, essentia-tensorflow no importable, etc.), forzamos
        # enable_deep=0 antes de persistir. Asi evitamos el sintoma reportado
        # por el usuario: "se comporta como si estuviera trabajando pero no
        # hace nada".
        def _desactivar_deep(motivo: str) -> None:
            nonlocal enable_deep
            if enable_deep == "1":
                enable_deep = "0"
                warnings.append(motivo)

        if enable_deep == "1" and deep_backend == "none":
            _desactivar_deep(
                "Audio Intelligence deep desactivado: backend = none. "
                "Selecciona essentia_tensorflow para habilitarlo."
            )
        if enable_deep == "1" and not model_dir and allow_downloads == "0":
            _desactivar_deep(
                "Audio Intelligence deep desactivado: falta "
                "AUDIO_INTELLIGENCE_MODEL_DIR y las descargas automáticas "
                "están deshabilitadas."
            )
        if enable_deep == "1" and deep_backend != "none":
            try:
                import essentia.standard as es  # type: ignore
                missing = [
                    name for name in ("TensorflowPredictMusiCNN", "TensorflowPredict2D")
                    if not hasattr(es, name)
                ]
                if missing:
                    _desactivar_deep(
                        "Audio Intelligence deep desactivado: essentia-tensorflow "
                        "no expone " + ", ".join(missing)
                    )
            except Exception as exc:
                _desactivar_deep(
                    "Audio Intelligence deep desactivado: essentia-tensorflow "
                    f"no está instalado o no carga ({exc})."
                )
            if enable_deep == "1" and model_dir:
                model_path = Path(model_dir).expanduser()
                if not model_path.exists():
                    if allow_downloads == "0":
                        _desactivar_deep(
                            "Audio Intelligence deep desactivado: el directorio "
                            f"{model_path} no existe."
                        )
                    else:
                        warnings.append(
                            f"El directorio de modelos deep {model_path} aún no existe; "
                            "se intentarán descargas automáticas."
                        )
                elif not list(model_path.glob("*.pb")):
                    if allow_downloads == "0":
                        _desactivar_deep(
                            f"Audio Intelligence deep desactivado: no hay modelos "
                            f".pb en {model_path}."
                        )
                    else:
                        warnings.append(
                            f"No hay modelos .pb en {model_path}; se intentarán "
                            "descargas automáticas."
                        )

        payload = {
            "enable_ia_tiebreak": enable_ia_tiebreak,
            "anthropic_key": anthropic_key,
            "openai_key": openai_key,
            "ia_proveedor": proveedor,
            "shazam_timeout_seg": str(shazam_timeout),
            "shazam_min_duracion_seg": str(shazam_min_dur),
            "ia_tiebreak_min_gap": f"{ia_min_gap:.3f}",
            "ia_max_tokens": str(ia_max_tokens),
            "ia_timeout_seg": str(ia_timeout),
            "skip_already_processed": _bool_key("skip_already_processed", "0"),
            "init_component_max_retries": str(init_retries),
            "init_component_retry_backoff_seg": f"{init_backoff:.2f}",
            "enable_deduplication": _bool_key("enable_deduplication"),
            "enable_semantic_deduplication": _bool_key("enable_semantic_deduplication"),
            "duplicate_policy": duplicate_policy,
            "duplicate_better_min_delta": f"{duplicate_delta:.3f}",
            "enable_assets_pipeline": _bool_key("enable_assets_pipeline"),
            "enable_cover_art_archive": _bool_key("enable_cover_art_archive"),
            "enable_theaudiodb_artist_images": _bool_key("enable_theaudiodb_artist_images"),
            "enable_itunes_cover_fallback": _bool_key("enable_itunes_cover_fallback"),
            "enable_deezer_artist_images": _bool_key("enable_deezer_artist_images"),
            "enable_wikipedia_artist_images": _bool_key("enable_wikipedia_artist_images"),
            "enable_itunes_artist_images": _bool_key("enable_itunes_artist_images"),
            "theaudiodb_api_key": str(incoming.get("theaudiodb_api_key", self._config.get("theaudiodb_api_key", "123"))).strip(),
            "assets_timeout_seg": str(assets_timeout),
            "assets_max_retries": str(assets_retries),
            "assets_retry_backoff_seg": f"{assets_backoff:.2f}",
            "assets_cache_ttl_seg": str(assets_cache_ttl),
            "assets_negative_cache_ttl_seg": str(assets_negative_ttl),
            "assets_min_resolution": str(assets_min_res),
            "assets_hd_max_image_bytes": str(assets_hd_max_bytes),
            "enable_external_enrichment": _bool_key("enable_external_enrichment"),
            "enable_lyrics_enrichment": _bool_key("enable_lyrics_enrichment"),
            "enable_lrclib": _bool_key("enable_lrclib"),
            "enable_lyrics_ovh": _bool_key("enable_lyrics_ovh"),
            "lyrics_timeout_seg": str(lyrics_timeout),
            "lyrics_max_retries": str(lyrics_retries),
            "lyrics_retry_backoff_seg": f"{lyrics_backoff:.2f}",
            "lyrics_suggest_limit": str(lyrics_suggest_limit),
            "enable_second_stage_resolution": _bool_key("enable_second_stage_resolution"),
            "second_stage_max_candidates": str(second_stage_max),
            "second_stage_min_evidence": f"{second_stage_min_evidence:.2f}",
            "second_stage_min_gap": f"{second_stage_min_gap:.2f}",
            "second_stage_cause_enabled": _bool_key("second_stage_cause_enabled"),
            "enable_third_stage_resolution": _bool_key("enable_third_stage_resolution"),
            "third_stage_min_evidence": f"{third_stage_min_evidence:.2f}",
            "third_stage_min_gap": f"{third_stage_min_gap:.2f}",
            "enable_ia_discography": enable_ia_discography,
            "discography_ia_min_confidence": f"{discography_min_confidence:.2f}",
            "enable_overrides": _bool_key("enable_overrides"),
            "manifest_schema_version": str(manifest_schema),
            "nb_sound_progress_mode": progress_mode,
            "nb_sound_progress_interval_sec": f"{progress_interval:.2f}",
            "sidecar_future_timeout_seg": f"{sidecar_future_timeout:.2f}",
            "sidecar_wait_heartbeat_seg": f"{sidecar_heartbeat:.2f}",
            "enable_audio_features": _bool_key("enable_audio_features"),
            "audio_features_mode": audio_features_mode,
            "audio_features_analyze_on_import": _bool_key("audio_features_analyze_on_import"),
            "audio_features_background": _bool_key("audio_features_background"),
            "audio_features_max_workers": str(audio_features_workers),
            "audio_features_analyze_full_track": _bool_key("audio_features_analyze_full_track", "0"),
            "audio_features_sample_strategy": audio_features_sample,
            "audio_features_segment_seconds": str(audio_features_segment),
            "audio_features_reanalyze_on_version_change": _bool_key("audio_features_reanalyze_on_version_change"),
            "audio_features_fail_silently": _bool_key("audio_features_fail_silently"),
            "enable_audio_intelligence_deep": enable_deep,
            "audio_intelligence_backend": deep_backend,
            "enable_audio_mood_models": _bool_key("enable_audio_mood_models", "0"),
            "enable_audio_embeddings": _bool_key("enable_audio_embeddings", "0"),
            "enable_audio_tagging_models": _bool_key("enable_audio_tagging_models", "0"),
            "audio_intelligence_analyze_after_import_background": _bool_key("audio_intelligence_analyze_after_import_background"),
            "audio_intelligence_resume_pending_on_startup": _bool_key("audio_intelligence_resume_pending_on_startup"),
            "audio_intelligence_background_autostart": _bool_key("audio_intelligence_background_autostart"),
            "audio_intelligence_background": _bool_key("audio_intelligence_background"),
            "audio_intelligence_max_workers": str(deep_workers),
            "audio_intelligence_background_batch_size": str(deep_batch_size),
            "audio_intelligence_background_idle_delay_sec": f"{deep_idle_delay:.2f}",
            "audio_intelligence_background_max_runtime_min": str(deep_max_runtime),
            "audio_intelligence_model_dir": model_dir,
            "audio_intelligence_allow_model_downloads": allow_downloads,
            "audio_intelligence_sample_strategy": deep_sample,
            "audio_intelligence_segment_seconds": str(deep_segment),
            "audio_intelligence_reanalyze_on_model_change": _bool_key("audio_intelligence_reanalyze_on_model_change"),
            "audio_intelligence_retry_failed": _bool_key("audio_intelligence_retry_failed", "0"),
            "audio_intelligence_max_attempts": str(deep_max_attempts),
            "audio_intelligence_cancel_discard_outputs": _bool_key("audio_intelligence_cancel_discard_outputs", "0"),
            "audio_intelligence_fail_silently": _bool_key("audio_intelligence_fail_silently"),
            "enable_music_discovery": _bool_key("enable_music_discovery"),
            "music_discovery_use_audio_features": _bool_key("music_discovery_use_audio_features"),
            "music_discovery_use_deep_features": _bool_key("music_discovery_use_deep_features"),
            "music_discovery_min_confidence": f"{discovery_confidence:.3f}",
            "music_discovery_default_limit": str(discovery_limit),
            "music_discovery_explain_results": _bool_key("music_discovery_explain_results"),
        }
        self._guardar_multiples(payload)
        mensaje = "Configuración avanzada guardada"
        if warnings:
            mensaje += " | Advertencias: " + " | ".join(warnings)
        return {
            "ok": True,
            "mensaje": mensaje,
            "ia_normalizada": ia_normalizada,
            "warnings": warnings,
        }

    @Slot("QVariant", result="QVariantMap")
    def guardar_personalizacion(self, data) -> dict:
        incoming = self._to_dict(data)
        scale = str(incoming.get("ui_scale", self._config.get("ui_scale", "100"))).replace("%", "").strip()
        if scale not in {"100", "125", "150", "175", "200"}:
            scale = "100"
        fuente = self._aplicar_fuente_global(
            str(incoming.get("ui_font_family", self._config.get("ui_font_family", "Inter"))).strip() or "Inter"
        )
        payload = {
            "ui_scale": scale,
            "ui_font_family": fuente,
            "ui_mode": str(incoming.get("ui_mode", self._config.get("ui_mode", "simple"))),
        }
        self._guardar_multiples(payload)
        return {"ok": True, "mensaje": "Personalización guardada"}

    @Slot(str, result="QVariantMap")
    def valores_predeterminados_modulo(self, modulo: str) -> dict:
        if modulo == "basica":
            defaults = self._defaults_config()
            return {
                **self._defaults_rutas_basica(),
                "enable_acoustid": defaults.get("enable_acoustid", "1"),
                "acoustid_key": defaults.get("acoustid_key", ""),
                "enable_shazam": defaults.get("enable_shazam", "1"),
                "precision_mode": "equilibrado",
            }
        if modulo == "avanzada":
            defaults = self._defaults_config()
            return {clave: defaults.get(clave, "") for clave in self._ADVANCED_CONFIG_KEYS}
        return {
            "ui_scale": "100",
            "ui_font_family": "Inter",
            "ui_mode": "simple",
            "tema": "negro_puro",
        }


    @Slot(str, result=str)
    def guardar_foto_perfil(self, url_origen: str) -> str:
        """Copia la imagen de perfil al directorio de caché configurado.
        Usa nombre único con timestamp para forzar recarga en QML.
        Compatible con Linux/macOS/Windows vía QUrl.toLocalFile()."""
        import shutil
        import time
        from pathlib import Path
        from PySide6.QtCore import QUrl
        try:
            ruta_local = QUrl(str(url_origen or "")).toLocalFile()
            if not ruta_local:
                return ""
            origen = Path(ruta_local)
            if not origen.is_file():
                _log.warning("Foto de perfil: archivo no encontrado: %s", origen)
                return ""

            # Directorio de caché: usa el valor configurado, con fallback a settings
            dir_cache_str = self._config.get("dir_cache", "").strip()
            if dir_cache_str:
                cache_dir = Path(dir_cache_str)
            else:
                from config.settings import DEFAULT_CACHE_DIR
                cache_dir = Path(str(DEFAULT_CACHE_DIR))

            destino_dir = cache_dir / "perfil"
            destino_dir.mkdir(parents=True, exist_ok=True)

            ext = origen.suffix.lower()
            if ext not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                ext = ".jpg"

            # Timestamp en el nombre → URL diferente → QML recarga la imagen
            ts = int(time.time())
            destino = destino_dir / f"foto_perfil_{ts}{ext}"

            # Eliminar fotos de perfil anteriores para no acumular archivos
            for vieja in destino_dir.glob("foto_perfil_*"):
                try:
                    vieja.unlink()
                except OSError:
                    pass

            shutil.copy2(str(origen), str(destino))
            ruta_guardada = str(destino)
            self.guardar("foto_perfil", ruta_guardada)
            return ruta_guardada
        except Exception as exc:
            _log.warning("No se pudo guardar la foto de perfil: %s", exc)
            return ""

    @Slot()
    def recargar(self) -> None:
        self._cargar()
        self._sincronizar_fuente_ui()
        self.configuracionCambiada.emit()




# =============================================================================
# MODELO KARAOKE
#
# Fachada delgada entre la VistaKaraoke (QML) y el subsistema
# `servicios.karaoke`. La logica de procesamiento/separacion vive integramente
# en Python puro; este modelo solo:
#   - mantiene paginacion/filtros/seleccion
#   - lanza el worker y propaga sus snapshots a QML
#   - reexpone operaciones de cola/job para que la vista las invoque
# =============================================================================

class ModeloKaraoke(QObject):
    """Coordina la VistaKaraoke con el servicio de cola karaoke.

    Flujo:
      1. La vista llama a `cargar()` para poblar la lista paginada.
      2. El usuario encola pistas via `encolar_pistas`/`encolar_todas`.
      3. `iniciar_procesamiento()` arranca un WorkerKaraokeCola.
      4. El worker emite snapshots (`procesandoCambiado`) que la UI consume.
      5. Cuando un job termina, `karaokeActualizado` notifica al
         reproductor para refrescar la pista activa si aplica.
    """

    pistasCargadas      = Signal()
    resumenCambiado     = Signal()
    paginaCambiada      = Signal()
    procesandoCambiado  = Signal()
    backendDiagCambiado = Signal()
    operacionOk         = Signal(str)
    operacionError      = Signal(str)
    karaokeActualizado  = Signal(int)  # pista_id

    LIMITE_PAGINA = 50

    _RESUMEN_VACIO: dict = {
        "no_procesada": 0, "en_cola": 0, "procesando": 0,
        "lista": 0, "fallida": 0, "no_aplica": 0,
        "sin_preparar": 0, "total": 0,
    }
    _SNAP_PROC_DEFAULT: dict = {
        "estado": "inactivo", "procesando": False,
        "backend": "", "device": "", "modelo": "",
        "total": 0, "procesadas": 0, "ready": 0, "failed": 0, "cancelled": 0,
        "pendientes": 0, "porcentaje": 0.0, "porcentaje_job": 0.0,
        "eta": "", "eta_seg": -1.0, "velocidad": 0.0,
        "pista_actual": "", "job_id_actual": 0,
        "mensaje": "", "warning": "", "error_codigo": "",
    }
    _DIAG_DEFAULT: dict = {
        "backend_listo": False, "mensaje": "Sin detectar",
        "instrucciones": "", "demucs_disponible": False, "ffmpeg_disponible": False,
        "device_disponible": "cpu", "devices_soportados": ["cpu"],
        "demucs_version": "", "torch_version": "", "ffmpeg_version": "",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pistas         = ListaGenerica(self)
        self._resumen: dict  = dict(self._RESUMEN_VACIO)
        self._filtro_estado  = "sin_preparar"
        self._filtro_texto   = ""
        self._pagina_actual  = 0
        self._total_filtrado = 0
        self._snap_proc: dict   = dict(self._SNAP_PROC_DEFAULT)
        self._diag_backend: dict = dict(self._DIAG_DEFAULT)
        self._worker = None
        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self._refrescar_desde_db)

    # ── Propiedades expuestas a QML ──────────────────────────────────────

    @Property(QObject, notify=pistasCargadas)
    def pistas(self) -> "ListaGenerica":
        return self._pistas

    @Property("QVariant", notify=resumenCambiado)
    def resumen(self) -> dict:
        return self._resumen

    @Property(str, notify=pistasCargadas)
    def filtro_estado(self) -> str:
        return self._filtro_estado

    @Property(str, notify=pistasCargadas)
    def filtro_texto(self) -> str:
        return self._filtro_texto

    @Property(int, notify=paginaCambiada)
    def pagina_actual(self) -> int:
        return self._pagina_actual

    @Property(int, notify=paginaCambiada)
    def total_filtrado(self) -> int:
        return self._total_filtrado

    @Property(int, notify=paginaCambiada)
    def total_paginas(self) -> int:
        return max(1, math.ceil(self._total_filtrado / self.LIMITE_PAGINA))

    @Property(int, notify=paginaCambiada)
    def limite_pagina(self) -> int:
        return self.LIMITE_PAGINA

    @Property("QVariant", notify=procesandoCambiado)
    def snap_proceso(self) -> dict:
        return self._snap_proc

    @Property(bool, notify=procesandoCambiado)
    def procesando(self) -> bool:
        return bool(self._snap_proc.get("procesando"))

    @Property(str, notify=procesandoCambiado)
    def estado_proceso(self) -> str:
        return str(self._snap_proc.get("estado", "inactivo"))

    @Property(float, notify=procesandoCambiado)
    def porcentaje_proceso(self) -> float:
        return float(self._snap_proc.get("porcentaje", 0.0))

    @Property(float, notify=procesandoCambiado)
    def porcentaje_job(self) -> float:
        return float(self._snap_proc.get("porcentaje_job", 0.0))

    @Property(str, notify=procesandoCambiado)
    def pista_actual_proceso(self) -> str:
        return str(self._snap_proc.get("pista_actual", ""))

    @Property(str, notify=procesandoCambiado)
    def eta_proceso(self) -> str:
        return str(self._snap_proc.get("eta", ""))

    @Property(str, notify=procesandoCambiado)
    def backend_activo(self) -> str:
        return str(self._snap_proc.get("backend", "") or self._diag_backend.get("mensaje", ""))

    @Property(str, notify=procesandoCambiado)
    def device_activo(self) -> str:
        return str(self._snap_proc.get("device") or self._diag_backend.get("device_disponible", ""))

    @Property(str, notify=procesandoCambiado)
    def modelo_activo(self) -> str:
        return str(self._snap_proc.get("modelo", ""))

    @Property(str, notify=procesandoCambiado)
    def mensaje_proceso(self) -> str:
        return str(self._snap_proc.get("mensaje", ""))

    @Property(str, notify=procesandoCambiado)
    def warning_proceso(self) -> str:
        return str(self._snap_proc.get("warning", ""))

    @Property(float, notify=procesandoCambiado)
    def velocidad_proceso(self) -> float:
        return float(self._snap_proc.get("velocidad", 0.0))

    @Property(int, notify=procesandoCambiado)
    def total_proceso(self) -> int:
        return int(self._snap_proc.get("total", 0))

    @Property(int, notify=procesandoCambiado)
    def procesadas_proceso(self) -> int:
        return int(self._snap_proc.get("procesadas", 0))

    @Property(int, notify=procesandoCambiado)
    def ready_proceso(self) -> int:
        return int(self._snap_proc.get("ready", 0))

    @Property(int, notify=procesandoCambiado)
    def failed_proceso(self) -> int:
        return int(self._snap_proc.get("failed", 0))

    @Property(int, notify=procesandoCambiado)
    def pendientes_proceso(self) -> int:
        return int(self._snap_proc.get("pendientes", 0))

    @Property("QVariant", notify=backendDiagCambiado)
    def backend_diag(self) -> dict:
        return self._diag_backend

    @Property(bool, notify=backendDiagCambiado)
    def backend_listo(self) -> bool:
        return bool(self._diag_backend.get("backend_listo"))

    # ── Slots de carga y filtros ─────────────────────────────────────────

    @Slot()
    def cargar(self) -> None:
        # Las queries SQL del karaoke (`contar_pistas_karaoke` +
        # `listar_pistas_karaoke`) tardan varios cientos de ms en
        # bibliotecas grandes. Las movemos a un QThread vía
        # `_UiQueryWorker` para que la UI nunca se trabe al entrar a
        # "Preparar Karaoke". El resultado se aplica en el thread
        # principal vía la signal del worker.
        if not hasattr(self, "_ui_worker"):
            self._ui_worker = _UiQueryWorker(self)
        filtro = self._filtro_estado if self._filtro_estado not in ("todos", "") else None
        filtro_texto = self._filtro_texto
        pagina_actual = self._pagina_actual

        def _consultar():
            total = svc_bib.contar_pistas_karaoke(
                filtro_estado=filtro, filtro_texto=filtro_texto,
            )
            paginas = max(1, math.ceil(total / self.LIMITE_PAGINA))
            pagina = max(0, min(pagina_actual, paginas - 1))
            datos = svc_bib.listar_pistas_karaoke(
                filtro_estado=filtro, filtro_texto=filtro_texto,
                limite=self.LIMITE_PAGINA, offset=pagina * self.LIMITE_PAGINA,
            )
            try:
                resumen = svc_bib.resumen_karaoke()
            except Exception as exc:
                _log.warning("ModeloKaraoke resumen_karaoke (worker) error: %s", exc)
                resumen = None
            return {"total": total, "pagina": pagina, "datos": datos, "resumen": resumen}

        self._ui_worker.run(_consultar, self._aplicar_carga)

    def _aplicar_carga(self, resultado) -> None:
        if resultado is None:
            self._pistas.set_datos([])
            self._total_filtrado = 0
        else:
            self._total_filtrado = int(resultado.get("total") or 0)
            self._pagina_actual = int(resultado.get("pagina") or 0)
            self._pistas.set_datos(resultado.get("datos") or [])
            resumen = resultado.get("resumen")
            if isinstance(resumen, dict):
                self._resumen = resumen
                self.resumenCambiado.emit()
        self.pistasCargadas.emit()
        self.paginaCambiada.emit()

    def _recargar_resumen(self) -> None:
        try:
            self._resumen = svc_bib.resumen_karaoke()
        except Exception as exc:
            _log.warning("ModeloKaraoke._recargar_resumen error: %s", exc)
        self.resumenCambiado.emit()

    @Slot(str)
    def establecer_filtro_estado(self, estado: str) -> None:
        self._filtro_estado = estado or "sin_preparar"
        self._pagina_actual = 0
        self._filtro_texto = ""
        self.cargar()

    @Slot(str)
    def establecer_filtro_texto(self, texto: str) -> None:
        self._filtro_texto = texto or ""
        self._pagina_actual = 0
        self.cargar()

    @Slot(int)
    def ir_a_pagina(self, pagina: int) -> None:
        pagina = max(0, min(pagina, self.total_paginas - 1))
        if pagina != self._pagina_actual:
            self._pagina_actual = pagina
            self.cargar()

    @Slot()
    def pagina_siguiente(self) -> None:
        self.ir_a_pagina(self._pagina_actual + 1)

    @Slot()
    def pagina_anterior(self) -> None:
        self.ir_a_pagina(self._pagina_actual - 1)

    @Slot("QVariant", result="QVariant")
    def pistas_snapshot_por_ids(self, ids_qml) -> list:
        if hasattr(ids_qml, "toVariant"):
            ids_qml = ids_qml.toVariant()
        if not isinstance(ids_qml, list):
            return []
        ids_set = {int(x) for x in ids_qml if x is not None}
        return [p for p in self._pistas.snapshot() if p.get("id") in ids_set]

    @Slot(result="QVariant")
    def todas_las_pistas_snapshot(self) -> list:
        return self._pistas.snapshot()

    # ── Slots de cola ────────────────────────────────────────────────────

    @Slot("QVariant", result=int)
    def encolar_pistas(self, ids_qml) -> int:
        if hasattr(ids_qml, "toVariant"):
            ids_qml = ids_qml.toVariant()
        if not ids_qml:
            return 0
        try:
            from servicios.karaoke import encolar_muchas
            ids = [int(x) for x in ids_qml if x is not None]
            n = encolar_muchas(ids)
            if n > 0:
                self._recargar_resumen()
                self.cargar()
                self.operacionOk.emit(f"{n} pista(s) añadidas a la cola de karaoke.")
            else:
                self.operacionOk.emit("Ninguna pista se pudo encolar (ya estaban en cola o no aplican).")
            return n
        except Exception as exc:
            _log.warning("encolar_pistas error: %s", exc)
            self.operacionError.emit(str(exc))
            return 0

    @Slot(result=int)
    def encolar_todas_sin_preparar(self) -> int:
        try:
            from servicios.karaoke import encolar_todas_sin_preparar as _enq
            n = _enq()
            if n > 0:
                self._recargar_resumen()
                self.cargar()
                self.operacionOk.emit(f"{n} pista(s) encoladas para procesamiento.")
            else:
                self.operacionOk.emit("No hay pistas sin preparar para encolar.")
            return n
        except Exception as exc:
            _log.warning("encolar_todas_sin_preparar error: %s", exc)
            self.operacionError.emit(str(exc))
            return 0

    @Slot(int, result=bool)
    def sacar_de_cola(self, pista_id: int) -> bool:
        try:
            from servicios.karaoke import sacar_de_cola
            ok = sacar_de_cola(int(pista_id))
            if ok:
                self.cargar()
                self.karaokeActualizado.emit(int(pista_id))
                self.operacionOk.emit("Pista sacada de la cola.")
            return ok
        except Exception as exc:
            _log.warning("sacar_de_cola error: %s", exc)
            self.operacionError.emit(str(exc))
            return False

    @Slot(int, result=bool)
    def cancelar_pista(self, pista_id: int) -> bool:
        """Cancela el karaoke de UNA pista sea cual sea su estado (en cola o
        procesando) y reconcilia su estado, robusto ante el 'procesando falso'.

        Resuelve el caso en que los botones por estado no respondían: si la
        pista es justo la que el worker procesa ahora, además se le pide
        interrupción cooperativa; si quedó colgada sin worker vivo, el reset de
        BD la libera de inmediato. La UI se refresca siempre.
        """
        pista_id = int(pista_id)
        es_job_activo = False
        try:
            from servicios.karaoke import job_activo_por_pista
            job = job_activo_por_pista(pista_id)
            if (job
                    and int(job.get("id") or 0) == int(self._snap_proc.get("job_id_actual") or -1)
                    and str(job.get("estado")) in ("preparando", "procesando", "generando")):
                es_job_activo = True
        except Exception as exc:
            _log.debug("cancelar_pista: no se pudo determinar job activo: %s", exc)

        try:
            from servicios.karaoke import cancelar_pista as _cancelar_pista
            ok = _cancelar_pista(pista_id)
        except Exception as exc:
            _log.warning("cancelar_pista karaoke error: %s", exc)
            self.operacionError.emit(str(exc))
            return False

        # Si era el job en curso, interrumpir el worker (cooperativo) y reflejar
        # de inmediato que ya no procesa esta pista para que el botón "responda".
        if es_job_activo and self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            snap = dict(self._snap_proc)
            snap.update({
                "estado": "cancelado", "procesando": False,
                "mensaje": "Procesamiento cancelado.",
            })
            self._snap_proc = snap
            self.procesandoCambiado.emit()

        self._recargar_resumen()
        self.cargar()
        self.karaokeActualizado.emit(pista_id)
        if ok:
            self.operacionOk.emit("Karaoke cancelado.")
        return ok

    @Slot()
    def vaciar_cola(self) -> None:
        try:
            from servicios.karaoke import vaciar_cola
            n = vaciar_cola()
            if n > 0:
                self.cargar()
                self.operacionOk.emit(f"Cola vaciada: {n} pista(s) regresaron a sin preparar.")
            else:
                self.operacionOk.emit("La cola ya estaba vacia.")
        except Exception as exc:
            _log.warning("vaciar_cola error: %s", exc)
            self.operacionError.emit(str(exc))

    @Slot(int, result=bool)
    def reintentar_fallida(self, pista_id: int) -> bool:
        try:
            from servicios.karaoke import encolar
            ok = encolar(int(pista_id)) is not None
            if ok:
                self.cargar()
                self.operacionOk.emit("Pista encolada para reintento.")
            return ok
        except Exception as exc:
            _log.warning("reintentar_fallida error: %s", exc)
            self.operacionError.emit(str(exc))
            return False

    @Slot(int, result=bool)
    def reprocesar(self, pista_id: int) -> bool:
        """Fuerza un reproceso desde cero (borra cache + encola).

        Distinto a `reintentar_fallida`: reprocesar parte de una pista 'lista'
        cuya calidad no satisfizo al usuario; el archivo previo se borra para
        que el separador no haga cache hit y se ejecute Demucs de nuevo.
        """
        try:
            from servicios.karaoke import marcar_para_reprocesar
            jid = marcar_para_reprocesar(int(pista_id))
            if jid:
                self.cargar()
                self.karaokeActualizado.emit(int(pista_id))
                self.operacionOk.emit("Pista marcada para reprocesar.")
                return True
            self.operacionError.emit("No se pudo marcar para reprocesar.")
            return False
        except Exception as exc:
            _log.warning("reprocesar error: %s", exc)
            self.operacionError.emit(str(exc))
            return False

    @Slot()
    def reintentar_todas_fallidas(self) -> None:
        try:
            from servicios.karaoke import encolar_todas_sin_preparar as _enq
            n = _enq()
            if n > 0:
                self._recargar_resumen()
                self.cargar()
                self.operacionOk.emit(f"{n} pistas reencoladas.")
            else:
                self.operacionOk.emit("No hay pistas fallidas para reintentar.")
        except Exception as exc:
            _log.warning("reintentar_todas_fallidas error: %s", exc)
            self.operacionError.emit(str(exc))

    @Slot(int, result=bool)
    def resetear_estado(self, pista_id: int) -> bool:
        try:
            from servicios.karaoke import resetear_estado_pista
            ok = resetear_estado_pista(int(pista_id))
            if ok:
                self.cargar()
                self.karaokeActualizado.emit(int(pista_id))
            return ok
        except Exception as exc:
            _log.warning("resetear_estado error: %s", exc)
            self.operacionError.emit(str(exc))
            return False

    @Slot(int, str, result=bool)
    def asignar_instrumental(self, pista_id: int, ruta: str) -> bool:
        ruta_limpia = (ruta or "").strip()
        if not ruta_limpia:
            self.operacionError.emit("La ruta del archivo instrumental no puede estar vacía.")
            return False
        try:
            from servicios.karaoke import asignar_instrumental_manual
            ok = asignar_instrumental_manual(int(pista_id), ruta_limpia)
            if ok:
                self.cargar()
                self.karaokeActualizado.emit(int(pista_id))
                self.operacionOk.emit("Instrumental asignado correctamente.")
            else:
                self.operacionError.emit("No se pudo asignar el instrumental.")
            return ok
        except Exception as exc:
            _log.warning("asignar_instrumental error: %s", exc)
            self.operacionError.emit(str(exc))
            return False

    @Slot(int, result=bool)
    def marcar_no_aplica(self, pista_id: int) -> bool:
        try:
            from servicios.karaoke import marcar_no_aplica
            ok = marcar_no_aplica(int(pista_id))
            if ok:
                self.cargar()
                self.karaokeActualizado.emit(int(pista_id))
            return ok
        except Exception as exc:
            _log.warning("marcar_no_aplica error: %s", exc)
            self.operacionError.emit(str(exc))
            return False

    @Slot(int, result=bool)
    def restaurar_no_aplica(self, pista_id: int) -> bool:
        try:
            from servicios.karaoke import restaurar_de_no_aplica
            ok = restaurar_de_no_aplica(int(pista_id))
            if ok:
                self.cargar()
                self.karaokeActualizado.emit(int(pista_id))
            return ok
        except Exception as exc:
            _log.warning("restaurar_no_aplica error: %s", exc)
            self.operacionError.emit(str(exc))
            return False

    @Slot(int, result="QVariant")
    def detalle_job(self, pista_id: int) -> dict:
        """Devuelve los datos del job mas reciente para una pista.

        Util para mostrar el error completo en un modal cuando el usuario
        pulsa "Ver error".
        """
        try:
            from servicios.karaoke import ultimo_job_por_pista
            datos = ultimo_job_por_pista(int(pista_id)) or {}
            return {
                "estado":        datos.get("estado", ""),
                "intento":       int(datos.get("intento") or 0),
                "max_intentos":  int(datos.get("max_intentos") or 0),
                "progreso":      float(datos.get("progreso") or 0.0),
                "modelo":        str(datos.get("modelo") or ""),
                "device":        str(datos.get("device") or ""),
                "ruta_salida":   str(datos.get("ruta_salida") or ""),
                "bytes_salida":  int(datos.get("bytes_salida") or 0),
                "duracion_ms":   int(datos.get("duracion_proc_ms") or 0),
                "error_codigo":  str(datos.get("error_codigo") or ""),
                "error_mensaje": str(datos.get("error_mensaje") or ""),
                "creado_en":     str(datos.get("creado_en") or ""),
                "finalizado_en": str(datos.get("finalizado_en") or ""),
            }
        except Exception as exc:
            _log.warning("detalle_job error: %s", exc)
            return {}

    # ── Procesamiento background ─────────────────────────────────────────

    @Slot()
    def detectar_backend(self) -> None:
        """Refresca el diagnostico del backend (demucs/ffmpeg/device).

        El diagnóstico invoca subprocess Python externos (para no cargar
        torch nativo en el proceso UI), lo que añade 100-300 ms en el
        primer llamado. Movemos la consulta a un QThread para que la
        UI no se congele al entrar en Karaoke.
        """
        if not hasattr(self, "_ui_worker"):
            self._ui_worker = _UiQueryWorker(self)

        def _consultar():
            try:
                from servicios.karaoke import diagnostico
                return diagnostico()
            except Exception as exc:
                _log.warning("detectar_backend error: %s", exc)
                return {
                    **dict(self._DIAG_DEFAULT),
                    "mensaje": f"Error detectando backend: {exc}",
                }

        self._ui_worker.run(_consultar, self._aplicar_diag_backend)

    def _aplicar_diag_backend(self, resultado) -> None:
        if resultado is None:
            self._diag_backend = {
                **dict(self._DIAG_DEFAULT),
                "mensaje": "Error detectando backend",
            }
        else:
            self._diag_backend = resultado
        self.backendDiagCambiado.emit()

    @Slot()
    def iniciar_procesamiento(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        # Refrescamos el diagnóstico SIEMPRE antes de arrancar, pero sin
        # bloquear el hilo principal. La detección lanza un subprocess
        # Python externo (~100-300 ms) para evitar `import torch` en el
        # proceso de la UI. Lo encadenamos vía _UiQueryWorker y, cuando
        # llegue el resultado, arrancamos el WorkerKaraokeCola si todo
        # está listo. Mientras tanto la UI sigue respondiendo.
        if not hasattr(self, "_ui_worker"):
            self._ui_worker = _UiQueryWorker(self)

        # Snapshot inmediato "preparando" para feedback visual.
        self._snap_proc = {
            **dict(self._SNAP_PROC_DEFAULT),
            "estado": "preparando", "procesando": True,
            "mensaje": "Verificando backend de karaoke...",
        }
        self.procesandoCambiado.emit()

        def _consultar():
            try:
                from servicios.karaoke import diagnostico
                return diagnostico()
            except Exception as exc:
                _log.warning("iniciar_procesamiento detectar_backend: %s", exc)
                return None

        self._ui_worker.run(_consultar, self._arrancar_worker_si_listo)

    def _arrancar_worker_si_listo(self, diag) -> None:
        """Continuación de :meth:`iniciar_procesamiento`.

        Se invoca en el hilo principal cuando el diagnóstico del backend
        termina. Si el backend está listo arranca ``WorkerKaraokeCola``;
        si no, emite error y limpia el snapshot.
        """
        if diag is None:
            diag = dict(self._DIAG_DEFAULT)
        self._diag_backend = diag
        self.backendDiagCambiado.emit()

        if not diag.get("backend_listo"):
            mensaje = diag.get("mensaje") or "Backend no disponible"
            self.operacionError.emit(mensaje)
            self._snap_proc = {
                **dict(self._SNAP_PROC_DEFAULT),
                "estado": "error", "procesando": False,
                "mensaje": mensaje,
                "warning": diag.get("instrucciones", ""),
                "error_codigo": "backend_no_disponible",
            }
            self.procesandoCambiado.emit()
            return
        try:
            from config import settings
            from workers.workers_qt import WorkerKaraokeCola

            cache_dir = str(settings.DEFAULT_CACHE_DIR)
            self._worker = WorkerKaraokeCola(
                cache_dir=cache_dir,
                device_pref="auto",
                nombre_modelo="htdemucs",
                parent=self,
            )
            self._worker.progreso.connect(self._al_progreso)
            self._worker.completado.connect(self._al_completado)
            self._worker.error.connect(self._al_error_proceso)
            self._worker.finished.connect(self._al_finished_worker)
            self._worker.start()

            self._snap_proc = {
                **dict(self._SNAP_PROC_DEFAULT),
                "estado": "preparando", "procesando": True,
                "backend": "demucs",
                "device": diag.get("device_disponible", ""),
                "modelo": "htdemucs",
                "mensaje": "Iniciando procesamiento karaoke...",
            }
            self.procesandoCambiado.emit()
            if not self._timer.isActive():
                self._timer.start()
        except Exception as exc:
            _log.exception("iniciar_procesamiento error")
            self._snap_proc = dict(self._SNAP_PROC_DEFAULT)
            self.procesandoCambiado.emit()
            self.operacionError.emit(f"No se pudo iniciar el procesamiento: {exc}")

    @Slot()
    def cancelar_procesamiento(self) -> None:
        """Cancela el job en curso. La cola se mantiene (otros jobs en_cola siguen)."""
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
        # Liberar el estado del job activo en BD de inmediato: el worker es
        # cooperativo y puede tardar en acusar la interrupción (Demucs revisa
        # stop_event entre segmentos). Sin esto, "Cancelar actual" se quedaba en
        # "cancelando..." sin avanzar cuando el procesamiento estaba trabado.
        job_id = int(self._snap_proc.get("job_id_actual") or 0)
        if job_id > 0:
            try:
                from servicios.karaoke import jobs_repo
                jobs_repo.marcar_cancelado(job_id, mensaje="Cancelado por el usuario")
            except Exception as exc:
                _log.debug("cancelar_procesamiento marcar_cancelado: %s", exc)
        snap = dict(self._snap_proc)
        snap.update({
            "estado": "cancelado", "procesando": False,
            "mensaje": "Procesamiento cancelado.",
        })
        self._snap_proc = snap
        self.procesandoCambiado.emit()
        self._recargar_resumen()
        self.cargar()

    @Slot()
    def cancelar_y_vaciar(self) -> None:
        """Cancela el job en curso Y vacia la cola pendiente."""
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
        job_id = int(self._snap_proc.get("job_id_actual") or 0)
        if job_id > 0:
            try:
                from servicios.karaoke import jobs_repo
                jobs_repo.marcar_cancelado(job_id, mensaje="Cancelado por el usuario")
            except Exception as exc:
                _log.debug("cancelar_y_vaciar marcar_cancelado: %s", exc)
        try:
            from servicios.karaoke import vaciar_cola
            vaciar_cola()
        except Exception as exc:
            _log.warning("cancelar_y_vaciar: %s", exc)
        snap = dict(self._snap_proc)
        snap.update({
            "estado": "cancelado", "procesando": False,
            "mensaje": "Procesamiento cancelado · cola vaciada.",
        })
        self._snap_proc = snap
        self.procesandoCambiado.emit()
        self._recargar_resumen()
        self.cargar()

    # ── Callbacks del worker ─────────────────────────────────────────────

    def _al_progreso(self, snapshot: dict) -> None:
        self._snap_proc = {**dict(self._SNAP_PROC_DEFAULT), **dict(snapshot or {})}
        pista_id = int(self._snap_proc.get("job_id_actual") or 0)
        self.procesandoCambiado.emit()
        # Cada vez que cambia el job activo, notificar al reproductor por si
        # la pista activa ahora tiene su instrumental listo.
        if self._snap_proc.get("estado") == "procesando" and pista_id > 0:
            # No emitimos karaokeActualizado en cada tick; solo al completar.
            pass

    def _al_completado(self, snapshot: dict) -> None:
        self._snap_proc = {
            **dict(self._SNAP_PROC_DEFAULT),
            **dict(snapshot or {}),
            "procesando": False,
        }
        self.procesandoCambiado.emit()
        self._timer.stop()
        self._recargar_resumen()
        self.cargar()
        # Notificar al reproductor que algo cambio (puede que la pista activa
        # ahora tenga su instrumental disponible).
        self.karaokeActualizado.emit(0)

    def _al_error_proceso(self, mensaje: str) -> None:
        self._snap_proc = {
            **dict(self._SNAP_PROC_DEFAULT),
            "estado": "error", "procesando": False,
            "mensaje": mensaje, "warning": mensaje,
            "error_codigo": "error_desconocido",
        }
        self.procesandoCambiado.emit()
        self._timer.stop()

    def _al_finished_worker(self) -> None:
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if not self._snap_proc.get("procesando"):
            self._timer.stop()

    @Slot()
    def _refrescar_desde_db(self) -> None:
        """Tick periodico durante el procesamiento para mantener UI viva."""
        self._recargar_resumen()

    def cerrar(self) -> None:
        """Cleanup en cierre de aplicación.

        Pide interrupción al worker de karaoke (cooperativa, propaga al
        stop_event de Demucs entre segmentos) y espera con timeout para
        evitar el "QThread: Destroyed while thread is still running" que
        Qt aborta cuando la app sale con un QThread vivo.
        """
        try:
            self._timer.stop()
        except Exception as exc:
            _log.debug("Stop timer karaoke falló en cierre: %s", exc)
        worker = self._worker
        if worker is not None and worker.isRunning():
            try:
                worker.requestInterruption()
            except Exception as exc:
                _log.debug("requestInterruption worker karaoke falló: %s", exc)
            try:
                # 5s es razonable: Demucs revisa stop_event entre segmentos
                # (~1s cada uno). Si tarda más, el siguiente paso es kill,
                # que ya hace Qt al destruir el objeto.
                worker.wait(5000)
            except Exception as exc:
                _log.debug("worker.wait karaoke falló: %s", exc)


# =============================================================================
# DJ PRIVADO
# =============================================================================

class ModeloDjPrivado(QObject):
    """Puente entre la VistaDJPrivado y servicios.dj_privado.

    Flujo principal:
      1. La vista llama `iniciar_sesion(prompt, minutos)`.
      2. El modelo invoca DjPrivadoService.iniciar_sesion en un worker thread
         (QThread) para no bloquear la UI durante la lectura del pool.
      3. Al terminar, emite `sesionLista` con el primer bloque visible.
      4. La UI puede llamar `reproducir_sesion` para empezar a tocar, mientras
         `continuar_construccion` se invoca en background para extender la cola.
      5. Eventos del reproductor (pista terminada, skip) se canalizan al
         servicio via `notificar_*`.

    El modelo NO contiene logica de seleccion ni scoring. Solo coordina.
    """

    estadoSesionCambiado    = Signal()
    sesionLista             = Signal()
    bloqueAgregado          = Signal(int)   # cantidad nueva en el bloque
    sesionFinalizada        = Signal()
    error                   = Signal(str)
    construyendoCambiado    = Signal()
    djVolumenCambiado       = Signal()
    historialCambiado       = Signal()
    estadoMotorCambiado     = Signal()
    avisoUi                 = Signal(str, str)  # mensaje, tono
    playlistGuardada        = Signal(int)       # playlist_id creada desde una sesión
    # Senales del reproductor propio de la sesion
    reproduccionCambiada    = Signal()         # play/pause/stop/finalizado
    progresoSesionCambiado  = Signal()         # tick de posicion
    pistaActualCambiada     = Signal(int)      # indice nuevo
    transicionCambiada      = Signal()         # entra/sale transicion activa

    def __init__(self, reproductor: Reproductor, parent=None):
        super().__init__(parent)
        self._reproductor = reproductor
        self._servicio = None       # lazy: solo se crea cuando se inicia sesion
        self._pistas_planificadas = ListaGenerica(self)
        self._historial = ListaGenerica(self)
        self._sesion_info: dict = {}
        self._resumen: dict = {}
        self._intent_visible: dict = {}
        self._estado_motor: dict = {}
        self._construyendo = False
        self._sesion_id_actual: int = 0
        # Id de la playlist en la que se guardó esta sesión (0 = no guardada o
        # la playlist guardada fue borrada). Validado contra existencia real.
        self._playlist_guardada_id: int = 0
        # Worker thread para construccion no bloqueante
        self._thread = None
        self._worker = None
        # Reproductor de sesion DJ (lazy)
        self._reproductor_sesion = None
        # Manager de ownership: centraliza el bloqueo/restauracion del global.
        # En vez de llamar a `_reproductor.set_modo_dj()` desde varios sitios
        # (lo cual producia estados fantasmas), todo pasa por aqui.
        from servicios.dj_privado.ownership import SessionOwnershipManager, Owner
        self._ownership = SessionOwnershipManager(reproductor)

        # Cuando algo externo (UI global, biblioteca, búsqueda) reproduce una
        # pista mientras DJ tiene ownership, hay que silenciar el motor DJ
        # sin tirar su estado: PAUSAMOS en vez de detener, conservando la
        # posición y los decks. Así, cuando el usuario vuelve al DJ y le
        # da play, reanuda desde donde iba. El cierre intencional sí pasa
        # por `detener_sesion()` (vía botón "Cerrar sesión"), que limpia
        # explícitamente el estado del modelo.
        def _on_cambio_owner(nuevo: Owner, anterior: Owner) -> None:
            if nuevo == Owner.GLOBAL and anterior == Owner.SESION_DJ:
                if self._reproductor_sesion is not None:
                    try:
                        self._reproductor_sesion.pause()
                    except Exception:
                        _log.warning(
                            "no se pudo pausar el reproductor DJ al perder ownership",
                            exc_info=True,
                        )
        self._ownership.on_cambio(_on_cambio_owner)
        # Estado expuesto del reproductor DJ
        self._estado_dj: str = "detenido"
        self._indice_pista_dj: int = -1
        self._pos_sesion_seg: float = 0.0
        self._dur_sesion_seg: float = 0.0
        self._pos_pista_seg: float = 0.0
        self._dur_pista_seg: float = 0.0
        self._transicion_dj: dict = {}
        # Filtros del workspace
        self._filtro_historial_texto: str = ""
        self._filtro_historial_estado: str = ""
        # Suscribirse al estado del reproductor global para registrar reproducciones
        self._reproductor.on_estado(self._on_estado_reproductor)
        self._pista_anterior_id: Optional[int] = None

        # Reanudacion de sesion DJ tras reabrir la app (#7a). Si al arrancar
        # habia una sesion activa, se restaura la vista en PAUSADO y se guarda
        # aqui {sesion_id, pista_id, indice, offset} para que el PRIMER play
        # la retome en la pista/posicion exactas (consumo unico). None = no hay
        # reanudacion pendiente; el play arranca desde el principio.
        self._reanudar_sesion_pendiente: Optional[dict] = None

        # Pre-warm de los imports DJ en background.
        # ---------------------------------------------------------------
        # Los servicios `servicios.dj_privado.mix_engine`,
        # `stems_karaoke`, `reproductor_sesion`, `transiciones` y
        # `hardware_profile` se cargan la primera vez que el usuario
        # entra a la vista DJ Privado, lo que añadía 100-300 ms de
        # bloqueo al hilo de la UI. Disparamos los imports en un
        # QThread one-shot 1.5s después del arranque para que cuando
        # el usuario pulse "Play sesión DJ" ya estén calientes en el
        # módulo cache de Python. No construimos el `ReproductorSesionDj`
        # aquí: necesita la `vlc.Instance` del hilo principal y la
        # construcción ya es instantánea cuando los módulos están
        # cacheados.
        self._prewarm_thread = None
        try:
            QTimer.singleShot(1500, self._prewarm_dj_imports)
        except Exception:
            pass

    def _prewarm_dj_imports(self) -> None:
        """Carga en background los módulos pesados de DJ Privado.

        Sólo se ejecuta una vez. Si el hilo ya corrió o sigue activo,
        no hace nada. Es seguro llamarlo aunque la sesión nunca se
        use: solo paga el coste de imports una vez en background.
        """
        if self._prewarm_thread is not None:
            return
        from PySide6.QtCore import QThread

        class _HiloPrewarm(QThread):
            def run(self_inner):
                try:
                    # Forzar la carga de los módulos en el cache de Python.
                    import servicios.dj_privado.mix_engine  # noqa: F401
                    import servicios.dj_privado.stems_karaoke  # noqa: F401
                    import servicios.dj_privado.reproductor_sesion  # noqa: F401
                    import servicios.dj_privado.transiciones  # noqa: F401
                    import servicios.dj_privado.hardware_profile  # noqa: F401
                    import servicios.dj_privado.persistencia  # noqa: F401
                except Exception as exc:
                    _log.debug("prewarm DJ imports falló: %s", exc)

        hilo = _HiloPrewarm(self)
        self._prewarm_thread = hilo
        hilo.finished.connect(lambda: self._descartar_prewarm())
        hilo.start()

    def _descartar_prewarm(self) -> None:
        hilo = self._prewarm_thread
        self._prewarm_thread = None
        if hilo is not None:
            try:
                hilo.deleteLater()
            except Exception:
                pass

    # ----------------------------------------------------------------
    # Propiedades expuestas a QML
    # ----------------------------------------------------------------

    @Property(QObject, notify=sesionLista)
    def pistas_planificadas(self) -> "ListaGenerica":
        return self._pistas_planificadas

    @Property(QObject, notify=historialCambiado)
    def historial(self) -> "ListaGenerica":
        return self._historial

    @Property("QVariant", notify=estadoSesionCambiado)
    def sesion_info(self) -> dict:
        return self._sesion_info

    @Property("QVariant", notify=estadoSesionCambiado)
    def resumen(self) -> dict:
        return self._resumen

    @Property("QVariant", notify=estadoSesionCambiado)
    def intent(self) -> dict:
        return self._intent_visible

    @Property("QVariant", notify=estadoMotorCambiado)
    def estado_motor(self) -> dict:
        return self._estado_motor

    @Property(bool, notify=construyendoCambiado)
    def construyendo(self) -> bool:
        return self._construyendo

    @Property(bool, notify=estadoSesionCambiado)
    def tiene_sesion(self) -> bool:
        return self._sesion_id_actual > 0

    @Property(int, notify=estadoSesionCambiado)
    def sesion_id(self) -> int:
        return self._sesion_id_actual

    @Property(int, notify=estadoSesionCambiado)
    def playlist_guardada_id(self) -> int:
        """Id de la playlist guardada para esta sesión, o 0.

        La UI usa esto para que el botón "Guardar como playlist" no duplique:
        si > 0, el botón pasa a "Abrir playlist". Vuelve a 0 si la playlist se
        borró (ver :meth:`revalidarPlaylistGuardada`)."""
        return self._playlist_guardada_id

    def _revalidar_playlist_guardada(self) -> None:
        """Recalcula `_playlist_guardada_id` validando que la playlist exista.

        Si el usuario borró la playlist guardada, vuelve a 0 y el botón de
        guardar reaparece."""
        pid = int(self._sesion_info.get("playlist_id") or 0)
        nuevo = pid if (pid > 0 and svc_bib.playlist_existe(pid)) else 0
        if nuevo != self._playlist_guardada_id:
            self._playlist_guardada_id = nuevo
            self.estadoSesionCambiado.emit()

    @Slot()
    def revalidarPlaylistGuardada(self) -> None:
        """Para invocar al entrar a la vista DJ: detecta si la playlist guardada
        fue borrada externamente y reactiva el botón de guardar."""
        self._revalidar_playlist_guardada()

    @Slot(result=str)
    def nombreSugeridoPlaylist(self) -> str:
        """Nombre por defecto al guardar: "DJ Privado: Music Session, Vol. X"
        (sin repetir). El resumen del prompt va a la descripción, no al título."""
        try:
            from servicios.dj_privado.servicio import DjPrivadoService
            return DjPrivadoService._nombre_auto_playlist()
        except Exception as exc:
            _log.debug("nombreSugeridoPlaylist falló: %s", exc)
            return "DJ Privado: Music Session, Vol. 1"

    # --- Propiedades del reproductor propio de la sesion DJ ---

    @Property(str, notify=reproduccionCambiada)
    def estado_dj(self) -> str:
        """detenido | preparando | reproduciendo | transicionando | pausado | finalizado | error"""
        return self._estado_dj

    @Property(bool, notify=reproduccionCambiada)
    def dj_reproduciendo(self) -> bool:
        return self._estado_dj in ("reproduciendo", "transicionando")

    @Property(bool, notify=reproduccionCambiada)
    def dj_pausado(self) -> bool:
        return self._estado_dj == "pausado"

    @Property(bool, notify=transicionCambiada)
    def dj_transicionando(self) -> bool:
        return bool(self._transicion_dj)

    @Property("QVariant", notify=transicionCambiada)
    def dj_transicion_activa(self) -> dict:
        return self._transicion_dj

    @Property(int, notify=pistaActualCambiada)
    def dj_indice_actual(self) -> int:
        return self._indice_pista_dj

    @Property(float, notify=progresoSesionCambiado)
    def dj_pos_sesion_seg(self) -> float:
        return self._pos_sesion_seg

    @Property(float, notify=progresoSesionCambiado)
    def dj_dur_sesion_seg(self) -> float:
        return self._dur_sesion_seg

    @Property(float, notify=progresoSesionCambiado)
    def dj_pos_pista_seg(self) -> float:
        return self._pos_pista_seg

    @Property(float, notify=progresoSesionCambiado)
    def dj_dur_pista_seg(self) -> float:
        return self._dur_pista_seg

    # ----------------------------------------------------------------
    # Slots invocados desde QML
    # ----------------------------------------------------------------

    @Slot()
    def cargar_historial(self) -> None:
        """Refresca el panel de sesiones recientes con filtros aplicados.

        Aplica filtros en memoria (texto sobre prompt; estado exacto). Se
        leen hasta 60 sesiones para tener margen sin pesar la consulta.
        """
        try:
            self._asegurar_servicio()
            sesiones = self._servicio.listar_sesiones_recientes(limite=60)
            datos = []
            # Búsqueda tolerante a tildes y mayúsculas: normalizamos AMBOS
            # lados con NFD-strip de diacríticos antes de comparar. Así
            # "cinematico" encuentra "cinemático" y viceversa.
            txt_norm = _normalizar_busqueda(self._filtro_historial_texto)
            est = self._filtro_historial_estado
            for s in sesiones:
                if est and s.estado != est:
                    continue
                if txt_norm and txt_norm not in _normalizar_busqueda(s.prompt_original or ""):
                    continue
                resumen = self._parse_json(s.resumen_json)
                datos.append({
                    "id": s.id,
                    "prompt": s.prompt_original,
                    "estado": s.estado,
                    "minutos": s.objetivo_minutos,
                    "creado_en": s.creado_en,
                    "playlist_id": s.playlist_id or 0,
                    "total_pistas": int(resumen.get("total_pistas") or 0),
                    "artistas_distintos": int(resumen.get("artistas_distintos") or 0),
                    "duracion_seg": float(resumen.get("duracion_seg") or 0.0),
                    "transiciones_buenas": int(resumen.get("transiciones_buenas") or 0),
                    "transiciones_total": int(resumen.get("transiciones_total") or 0),
                })
            self._historial.set_datos(datos)
            self.historialCambiado.emit()
        except Exception as e:
            _log.warning(f"[dj] cargar_historial falló: {e}", exc_info=True)
            self.error.emit("No se pudo cargar el historial de sesiones.")

    @Slot()
    def refrescar_estado_motor(self) -> None:
        try:
            self._asegurar_servicio()
            self._estado_motor = self._servicio.estado_motor()
            self.estadoMotorCambiado.emit()
        except Exception as e:
            _log.warning(f"[dj] estado_motor falló: {e}", exc_info=True)

    @Slot(str, int)
    def iniciar_sesion(self, prompt: str, minutos: int) -> None:
        """Inicia construccion en un worker thread.

        El primer bloque se entrega rapido (callback sesionLista). El resto
        sigue construyendose en background hasta cubrir la duracion objetivo.
        """
        prompt_limpio = (prompt or "").strip()
        if not prompt_limpio:
            self.avisoUi.emit("Escribe lo que quieres escuchar.", "warning")
            return
        if minutos <= 0:
            minutos = 60
        if minutos > 480:
            self.avisoUi.emit(
                "El máximo son 480 minutos (8 horas). Reduce la duración.",
                "warning",
            )
            return
        if self._construyendo:
            self.avisoUi.emit("Ya hay una sesión construyéndose.", "warning")
            return
        # Validación temprana: si la biblioteca está vacía o tiene muy
        # pocas pistas, ahorrarle al usuario el spinner de "construyendo"
        # que termina en error vacío. `total_pistas` es count rápido.
        try:
            stats = svc_bib.estadisticas_generales()
            total_pistas = int(stats.get("total_pistas") or 0)
        except Exception:
            total_pistas = -1  # desconocido; dejamos pasar.
        if total_pistas == 0:
            self.avisoUi.emit(
                "Tu biblioteca está vacía. Importa música antes de crear una sesión.",
                "warning",
            )
            return
        if 0 < total_pistas < 5:
            self.avisoUi.emit(
                f"Solo tienes {total_pistas} pista(s). El DJ necesita más variedad. "
                "Importa más música y vuelve a intentarlo.",
                "warning",
            )
            return
        self._lanzar_worker_inicio(prompt_limpio, minutos)

    @Slot()
    def regenerar(self) -> None:
        """Regenera la sesion con misma intencion (otra semilla)."""
        if self._construyendo:
            return
        if not self._sesion_id_actual:
            self.avisoUi.emit("No hay una sesión activa para regenerar.", "warning")
            return
        if not self._servicio:
            return
        prompt = self._sesion_info.get("prompt") or ""
        minutos = int(self._sesion_info.get("minutos") or 60)
        try:
            self._servicio.descartar_sesion_activa()
            self._sesion_id_actual = 0
        except Exception:
            pass
        self._lanzar_worker_inicio(prompt, minutos)

    @Slot()
    def reproducir_sesion(self) -> None:
        """Inicia la sesion DJ usando el reproductor propio (NO el global).

        Si el reproductor global estaba sonando, lo pausamos limpiamente
        ANTES de tomar el audio (set_modo_dj(True) lo hace) y avisamos al
        usuario para que entienda por qué su música anterior se quedó
        callada. Cuando la sesión termine, el global se reanuda en la
        posición exacta donde quedó.
        """
        if not self._sesion_id_actual or not self._servicio:
            self.avisoUi.emit("Construye una sesión primero.", "warning")
            return
        try:
            rep_sesion = self._asegurar_reproductor_sesion()
            n = rep_sesion.cargar_sesion(self._sesion_id_actual)
            if n == 0:
                self.avisoUi.emit("La sesión no tiene pistas reproducibles.", "warning")
                return
            # Detectar si el global está sonando para avisar al usuario.
            global_estaba_sonando = False
            try:
                from servicios.reproductor import EstadoReproductor
                global_estaba_sonando = (
                    self._reproductor is not None
                    and self._reproductor.estado == EstadoReproductor.REPRODUCIENDO
                )
            except Exception:
                global_estaba_sonando = False
            # Reanudacion tras reabrir la app (#7a): si esta sesion fue
            # restaurada, dejamos preparada la pista/offset guardados ANTES del
            # play para que retome donde se cerro (no desde el principio). Es
            # consumo unico: tras prepararla se descarta.
            pendiente = self._reanudar_sesion_pendiente
            if pendiente and int(pendiente.get("sesion_id") or 0) == int(self._sesion_id_actual):
                try:
                    rep_sesion.preparar_reanudacion(
                        int(pendiente.get("pista_id") or 0),
                        float(pendiente.get("offset") or 0.0),
                        int(pendiente.get("indice") or 0),
                    )
                except Exception:
                    _log.debug("[dj] preparar_reanudacion falló", exc_info=True)
                self._reanudar_sesion_pendiente = None
            # Adquirir ownership ANTES de arrancar audio DJ. El manager hace
            # set_modo_dj(True) si veniamos de GLOBAL (pausa el media del
            # global), o transfiere si otra sesion estaba activa.
            self._ownership.adquirir_para_sesion(self._sesion_id_actual)
            ok = rep_sesion.play()
            if not ok:
                self._ownership.liberar_si_es_de(self._sesion_id_actual)
                self.avisoUi.emit("No se pudo iniciar la reproducción DJ.", "warning")
                return
            if global_estaba_sonando:
                self.avisoUi.emit(
                    "Pausamos tu música normal mientras suena la sesión DJ.",
                    "info",
                )
            else:
                self.avisoUi.emit("DJ Privado en reproducción.", "info")
        except Exception as e:
            _log.error(f"[dj] reproducir_sesion falló: {e}", exc_info=True)
            try:
                self._ownership.liberar_si_es_de(self._sesion_id_actual)
            except Exception:
                pass
            self.error.emit("No se pudo iniciar la reproducción.")

    # ----------------------------------------------------------------
    # Control de reproduccion DJ (propio, aislado del reproductor global)
    # ----------------------------------------------------------------

    def _asegurar_reproductor_sesion(self):
        if self._reproductor_sesion is None:
            from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj
            from servicios.dj_privado.mix_engine import MixEngine
            from servicios.dj_privado.stems_karaoke import StemsKaraokeProvider
            from servicios.dj_privado import hardware_profile as hp

            # Lanzamos el benchmark de hardware en background si nunca se hizo.
            # No bloquea el arranque: el motor opera en LOW hasta que termine
            # y entonces el siguiente preparar_transicion ya verá el perfil
            # actualizado (el MixEngine consulta perfil_efectivo() cada vez).
            try:
                hp.lanzar_benchmark_si_falta(
                    on_completado=lambda res: self._reproductor_sesion
                        and self._reproductor_sesion._mix_engine
                        and self._reproductor_sesion._mix_engine.actualizar_perfil(res.perfil)
                )
            except Exception:
                pass

            mix_engine = MixEngine(stems_provider=StemsKaraokeProvider())
            # Compartir la instancia VLC del Reproductor principal evita
            # tener dos `vlc.Instance` vivas en el mismo proceso (libvlc
            # inicializa módulos globales no thread-safe y la segunda
            # Instance puede crashear la app a los segundos de arrancar
            # la reproducción de sesión DJ — síntoma reportado: la app
            # se cierra ~2s después del play).
            instancia_compartida = getattr(self._reproductor, "_instancia_vlc", None)
            r = ReproductorSesionDj(
                mix_engine=mix_engine,
                vlc_instance=instancia_compartida,
            )
            r.on_estado(self._on_estado_dj)
            r.on_progreso(self._on_progreso_dj)
            r.on_pista_cambio(self._on_pista_cambio_dj)
            r.on_transicion(self._on_transicion_dj)
            # Arrancar con el volumen persistido para que el audio coincida con
            # lo que muestra el deslizador (que ya lo reflejaba sin reproductor).
            try:
                r.set_volumen(self._dj_volumen_persistido())
            except Exception:
                pass
            self._reproductor_sesion = r
            self.djVolumenCambiado.emit()
        return self._reproductor_sesion

    @Slot()
    def dj_play_pause(self) -> None:
        """Play/pause de la sesión activa con manejo correcto de ownership.

        Tres casos a resolver:

        1. No hay reproductor (primer uso) o la sesión actual no está
           cargada en él → llamamos `reproducir_sesion()`, que carga +
           adquiere ownership + arranca audio.

        2. La sesión está pausada pero el ownership está en GLOBAL (el
           usuario reprodujo algo más y luego volvió al DJ) → readquirimos
           ownership ANTES del toggle. Eso pausa el global, mantiene el
           deck DJ con su posición intacta, y `toggle()` reanuda exacta-
           mente donde quedó.

        3. La sesión coincide y el motor está en reproduciendo/pausado/
           transicionando con ownership DJ → toggle simple.
        """
        if self._reproductor_sesion is None:
            self.reproducir_sesion()
            return
        sesion_cargada = getattr(self._reproductor_sesion, "sesion_id", 0)
        estado = (self._estado_dj or "").lower()
        coincide = (
            int(sesion_cargada) == int(self._sesion_id_actual)
            and int(self._sesion_id_actual) > 0
            and estado in ("reproduciendo", "pausado", "transicionando")
        )
        if not coincide:
            # Sesión nueva o motor en detenido/finalizado/error: ruta completa.
            self.reproducir_sesion()
            return
        # Reanudar conservando posición: si perdimos ownership (porque sonó
        # algo en el global), readquirirlo antes para que vuelva a quedar
        # bloqueada la barra global. El motor DJ ya estaba pausado por el
        # callback de ownership, así que el toggle reanudará al instante.
        try:
            from servicios.dj_privado.ownership import Owner
            if self._ownership.owner != Owner.SESION_DJ:
                self._ownership.adquirir_para_sesion(self._sesion_id_actual)
        except Exception:
            _log.debug("[dj] readquirir ownership en play falló", exc_info=True)
        self._reproductor_sesion.toggle()

    def _asegurar_reproduccion_dj(self):
        """Prepara la sesión en el motor DJ y ADQUIERE el ownership del audio
        antes de cualquier control que produzca sonido (anterior/siguiente/
        saltar/seek global). Sin esto, esos controles hacían sonar el motor DJ
        a la vez que el reproductor global (nunca se tomaba el ownership).

        Devuelve el reproductor de sesión listo, o None si no hay sesión.
        """
        if not self._sesion_id_actual:
            return None
        rs = self._reproductor_sesion
        cargada = int(getattr(rs, "sesion_id", 0)) if rs is not None else 0
        if rs is None or cargada != int(self._sesion_id_actual):
            try:
                rs = self._asegurar_reproductor_sesion()
                if rs.cargar_sesion(self._sesion_id_actual) == 0:
                    self.avisoUi.emit("La sesión no tiene pistas reproducibles.", "warning")
                    return None
            except Exception:
                _log.error("[dj] no se pudo cargar la sesión para el control", exc_info=True)
                return None
            # Al saltar manualmente se descarta el punto de reanudación previo.
            self._reanudar_sesion_pendiente = None
        # Tomar (o readquirir) el ownership ANTES de producir audio: esto pausa
        # el reproductor global y evita que ambos suenen a la vez.
        try:
            from servicios.dj_privado.ownership import Owner
            if self._ownership.owner != Owner.SESION_DJ:
                self._ownership.adquirir_para_sesion(self._sesion_id_actual)
        except Exception:
            _log.debug("[dj] adquirir ownership en control falló", exc_info=True)
        return rs

    @Slot()
    def dj_siguiente(self) -> None:
        rs = self._asegurar_reproduccion_dj()
        if rs is not None:
            rs.siguiente()

    @Slot()
    def dj_anterior(self) -> None:
        rs = self._asegurar_reproduccion_dj()
        if rs is not None:
            rs.anterior()

    @Slot(int)
    def dj_saltar_a(self, indice: int) -> None:
        rs = self._asegurar_reproduccion_dj()
        if rs is not None:
            rs.saltar_a(int(indice))

    @Slot(float)
    def dj_buscar(self, seg: float) -> None:
        # Seek dentro de la pista actual: no arranca audio nuevo, así que no
        # necesita forzar ownership (no produce solapamiento con el global).
        if self._reproductor_sesion is not None:
            self._reproductor_sesion.buscar_posicion(float(seg))

    @Slot(float)
    def dj_buscar_global(self, seg_global: float) -> None:
        """Salta a una posicion absoluta en el timeline de la sesion.

        Eq: click en el timeline a X segundos -> ir a la pista correcta + offset.
        Adquiere ownership primero (el salto global arranca reproducción).
        """
        rs = self._asegurar_reproduccion_dj()
        if rs is not None:
            rs.buscar_posicion_global(float(seg_global))

    @Property(int, notify=djVolumenCambiado)
    def dj_volumen(self) -> int:
        rs = self._reproductor_sesion
        if rs is not None:
            return int(getattr(rs, "_volumen", 80))
        # Sin reproductor de sesión aún (p.ej. sesión recién restaurada o antes
        # del primer play): el deslizador debe reflejar el valor persistido.
        return self._dj_volumen_persistido()

    @staticmethod
    def _dj_volumen_persistido() -> int:
        try:
            from db.conexion import obtener_config
            return max(0, min(100, int(obtener_config("dj_volumen", "80") or "80")))
        except Exception:
            return 80

    @Slot(int)
    def dj_set_volumen(self, valor: int) -> None:
        v = max(0, min(100, int(valor)))
        # Persistir SIEMPRE (sobrevive reaperturas y permite ajustar el volumen
        # aunque el reproductor de sesión aún no exista).
        try:
            from db.conexion import guardar_config
            guardar_config("dj_volumen", str(v))
        except Exception as exc:
            _log.debug("[dj] no se pudo guardar dj_volumen: %s", exc)
        if self._reproductor_sesion is not None:
            self._reproductor_sesion.set_volumen(v)
        self.djVolumenCambiado.emit()

    @Slot(int, result=str)
    def dj_portada_pista(self, indice: int) -> str:
        """Ruta (file path) de la portada de la pista planificada en `indice`.

        Resuelve por el mismo camino que la barra de reproducción global
        (`Reproductor._resolver_portada_pista`), así el player DJ y el global
        muestran la misma carátula. Devuelve "" si no hay portada.
        """
        try:
            datos = self._pistas_planificadas.obtener(int(indice))
            if not datos:
                return ""
            pista_id = int(datos.get("pista_id") or 0)
            if pista_id <= 0:
                return ""
            resolver = getattr(self._reproductor, "_resolver_portada_pista", None)
            if resolver is None:
                return ""
            return str(resolver({"id": pista_id}) or "")
        except Exception:
            return ""

    @Slot()
    def detener_sesion(self) -> None:
        """Detiene la sesion DJ y la "cierra" desde la perspectiva de la UI.

        Al pulsar "Cerrar sesión" el usuario expresa la intención de
        terminar esta experiencia: además de detener el audio, vaciamos la
        sesión activa en memoria para que la vista "En sesión" pueda
        mostrar un estado vacío con sugerencias (ir a historial o
        construir una nueva). La sesión permanece en BD para reaparecer
        en el historial.
        """
        if self._reproductor_sesion is not None:
            try:
                self._reproductor_sesion.detener()
            except Exception:
                _log.debug("[dj] detener fallo", exc_info=True)
        # Liberar ownership (idempotente).
        try:
            self._ownership.liberar()
        except Exception:
            _log.debug("[dj] ownership.liberar fallo", exc_info=True)
        # Cerrar la sesión es intencional: no la restauraremos al reabrir (#7a).
        self._limpiar_estado_sesion_persistido()
        # Limpiar el estado visible de la sesión activa.
        self._sesion_id_actual = 0
        self._sesion_info = {}
        self._resumen = {}
        self._intent_visible = {}
        self._pistas_planificadas.set_datos([])
        self._indice_pista_dj = -1
        self._pos_sesion_seg = 0.0
        self._dur_sesion_seg = 0.0
        self._pos_pista_seg = 0.0
        self._dur_pista_seg = 0.0
        self._transicion_dj = {}
        # NO emitimos sesionLista al cerrar: esa señal está pensada para
        # cuando aparece UNA sesión nueva en escena, no cuando desaparece.
        # tiene_sesion ahora será False, y estadoSesionCambiado disparará
        # el rebind de la UI hacia el empty state.
        self.estadoSesionCambiado.emit()
        self.pistaActualCambiada.emit(-1)
        self.progresoSesionCambiado.emit()
        self.transicionCambiada.emit()
        self.reproduccionCambiada.emit()

    # ----------------------------------------------------------------
    # Workspace: gestion de sesiones historicas
    # ----------------------------------------------------------------

    @Slot(int, result=bool)
    def eliminar_sesion(self, sesion_id: int) -> bool:
        """Elimina una sesion historica de la BD."""
        try:
            # Si la sesion a eliminar era la dueña del audio, parar
            # reproduccion y liberar ownership ANTES de borrar.
            if self._ownership.sesion_id_activa == int(sesion_id):
                if self._reproductor_sesion is not None:
                    try: self._reproductor_sesion.detener()
                    except Exception: pass
                self._ownership.liberar_si_es_de(int(sesion_id))
            from db.conexion import transaccion
            with transaccion() as con:
                con.execute("DELETE FROM dj_eventos WHERE sesion_id = ?", (int(sesion_id),))
                con.execute("DELETE FROM dj_pistas_sesion WHERE sesion_id = ?", (int(sesion_id),))
                con.execute("DELETE FROM dj_sesiones WHERE id = ?", (int(sesion_id),))
            if int(sesion_id) == int(self._sesion_id_actual):
                # Era la activa: limpiar estado local.
                self._sesion_id_actual = 0
                self._sesion_info = {}
                self._resumen = {}
                self._intent_visible = {}
                self._pistas_planificadas.set_datos([])
                self.estadoSesionCambiado.emit()
                self.sesionLista.emit()
            self.cargar_historial()
            self.avisoUi.emit("Sesión eliminada.", "info")
            return True
        except Exception as e:
            _log.error(f"[dj] eliminar_sesion falló: {e}", exc_info=True)
            self.error.emit("No se pudo eliminar la sesión.")
            return False

    @Slot(int, result=int)
    def duplicar_sesion(self, sesion_id: int) -> int:
        """Crea una sesion nueva con el mismo prompt (regenerada)."""
        try:
            self._asegurar_servicio()
            from servicios.dj_privado import persistencia as dj_persist
            fila = dj_persist.obtener_sesion(int(sesion_id))
            if not fila:
                self.avisoUi.emit("La sesión no existe.", "warning")
                return 0
            # Lanzar construccion fresca con mismo prompt.
            self._lanzar_worker_inicio(fila.prompt_original, int(fila.objetivo_minutos))
            self.avisoUi.emit("Generando sesión nueva con el mismo prompt…", "info")
            return 1
        except Exception as e:
            _log.error(f"[dj] duplicar_sesion falló: {e}", exc_info=True)
            self.error.emit("No se pudo duplicar la sesión.")
            return 0

    @Slot(str)
    def establecer_filtro_historial_texto(self, texto: str) -> None:
        # Guardamos el texto tal cual; la normalización (NFD + strip
        # diacríticos + lower) la hace `cargar_historial` al comparar.
        self._filtro_historial_texto = (texto or "").strip()
        self.cargar_historial()

    @Slot(str)
    def establecer_filtro_historial_estado(self, estado: str) -> None:
        self._filtro_historial_estado = (estado or "").strip()
        self.cargar_historial()

    # ----------------------------------------------------------------
    # Callbacks del reproductor de sesion
    # ----------------------------------------------------------------

    def _on_estado_dj(self, estado, indice: int, total: int) -> None:
        self._estado_dj = getattr(estado, "value", str(estado))
        self._indice_pista_dj = int(indice)
        self.reproduccionCambiada.emit()
        if self._estado_dj in ("finalizado", "detenido", "error"):
            # Restaurar reproductor global via manager (idempotente).
            try:
                self._ownership.liberar()
            except Exception:
                pass
            # Sesión terminada/en error: no hay nada que restaurar al reabrir.
            # (El cierre de la app persiste ANTES de llamar a close(), que no
            # emite estado, así que esto no pisa el guardado de #7a.)
            if self._estado_dj in ("finalizado", "error"):
                self._limpiar_estado_sesion_persistido()
            if self._estado_dj == "finalizado":
                self.sesionFinalizada.emit()

    def _on_progreso_dj(self, pos_global: float, dur_total: float,
                        pos_pista: float, dur_pista: float) -> None:
        self._pos_sesion_seg = float(pos_global)
        self._dur_sesion_seg = float(dur_total)
        self._pos_pista_seg = float(pos_pista)
        self._dur_pista_seg = float(dur_pista)
        self.progresoSesionCambiado.emit()

    def _on_pista_cambio_dj(self, indice: int, datos: dict) -> None:
        self._indice_pista_dj = int(indice)
        self.pistaActualCambiada.emit(int(indice))

    def _on_transicion_dj(self, plan: dict, idx_a: int, idx_b: int) -> None:
        if plan:
            self._transicion_dj = dict(plan)
        else:
            self._transicion_dj = {}
        self.transicionCambiada.emit()

    @Slot(int, int)
    def notificar_skip(self, posicion: int, pista_id: int) -> None:
        if not self._servicio:
            return
        try:
            self._servicio.registrar_skip(int(posicion), int(pista_id))
            self._recargar_pistas_planificadas()
        except Exception as e:
            _log.debug(f"[dj] skip ignorado: {e}")

    @Slot(int, int)
    def notificar_like(self, posicion: int, pista_id: int) -> None:
        if not self._servicio:
            return
        self._servicio.registrar_like(int(posicion), int(pista_id))

    @Slot(str, result=int)
    def guardar_como_playlist(self, nombre: str) -> int:
        if not self._sesion_id_actual or not self._servicio:
            self.avisoUi.emit("No hay sesión para guardar.", "warning")
            return 0
        try:
            # Nombre vacío → el servicio genera "DJ Privado: Music Session, Vol. X".
            playlist_id = self._servicio.guardar_como_playlist(nombre.strip())
            self.avisoUi.emit("Sesión guardada como playlist.", "info")
            # Marcar la sesión como guardada para que el botón pase a "Abrir
            # playlist" y no se generen duplicados al pulsar de nuevo.
            self._sesion_info = {**self._sesion_info, "playlist_id": int(playlist_id)}
            self._playlist_guardada_id = int(playlist_id)
            self.estadoSesionCambiado.emit()
            # Refresco en vivo: la vista de Playlists debe ver la nueva sin
            # reiniciar la app (la conexión se cablea en main_ui).
            self.playlistGuardada.emit(int(playlist_id))
            return int(playlist_id)
        except ValueError as e:
            self.avisoUi.emit(str(e), "warning")
            return 0
        except Exception as e:
            _log.error(f"[dj] guardar playlist falló: {e}", exc_info=True)
            self.error.emit("No se pudo guardar la sesión como playlist.")
            return 0

    @Slot()
    def descartar(self) -> None:
        """Descarta la sesion activa y libera todos los recursos.

        Es idempotente: aunque no haya servicio inicializado, libera el
        modo DJ del reproductor global (por si quedo un flag colgado tras
        un crash o un cambio de estado anomalo).
        """
        # 1) Parar reproductor de sesion si esta corriendo.
        if self._reproductor_sesion is not None:
            try:
                self._reproductor_sesion.detener()
            except Exception:
                _log.debug("[dj] detener sesion antes de descartar fallo", exc_info=True)
        # 2) Liberar ownership (idempotente via manager).
        try:
            self._ownership.liberar()
        except Exception:
            pass
        # Descartar es intencional: no restaurar esta sesión al reabrir (#7a).
        self._limpiar_estado_sesion_persistido()
        # 3) Descartar en backend si hay servicio.
        if self._servicio is not None:
            try:
                self._servicio.descartar_sesion_activa()
            except Exception:
                _log.debug("[dj] descartar_sesion_activa fallo", exc_info=True)
        # 4) Limpiar estado local.
        self._sesion_id_actual = 0
        self._sesion_info = {}
        self._resumen = {}
        self._intent_visible = {}
        self._playlist_guardada_id = 0
        self._pistas_planificadas.set_datos([])
        self.estadoSesionCambiado.emit()
        self.sesionLista.emit()

    @Slot(int)
    def cargar_sesion_anterior(self, sesion_id: int) -> None:
        """Restaura una sesion previa como la activa visible.

        Si hay otra sesión sonando, la detenemos antes de cambiar la vista:
        de lo contrario, la UI mostraría datos de una sesión mientras el
        audio sigue siendo de otra (estado confuso para el usuario).
        """
        try:
            self._asegurar_servicio()
            nueva_id = int(sesion_id)
            estado = (self._estado_dj or "").lower()
            if (estado in ("reproduciendo", "transicionando", "pausado")
                    and self._sesion_id_actual
                    and int(self._sesion_id_actual) != nueva_id):
                if self._reproductor_sesion is not None:
                    try:
                        self._reproductor_sesion.detener()
                    except Exception:
                        pass
                try:
                    self._ownership.liberar()
                except Exception:
                    pass
            sesion = self._servicio.cargar_sesion(nueva_id)
            self._sesion_id_actual = sesion.sesion_id
            self._publicar_sesion(sesion)
            self.avisoUi.emit("Sesión cargada.", "info")
        except Exception as e:
            _log.error(f"[dj] cargar_sesion_anterior falló: {e}", exc_info=True)
            self.error.emit("No se pudo cargar la sesión.")

    @Slot(str, result="QVariantList")
    def previsualizar_intent(self, prompt: str) -> list:
        """Para chips/sugerencias en vivo: lista de conceptos detectados."""
        try:
            from servicios.dj_privado.ontologia import buscar_conceptos
            matches = buscar_conceptos(prompt)
            return [
                {"name": m.concepto.name, "alias": m.alias, "role": m.concepto.role}
                for m in matches
            ]
        except Exception:
            return []

    # ----------------------------------------------------------------
    # Worker thread
    # ----------------------------------------------------------------

    def _asegurar_servicio(self) -> None:
        if self._servicio is None:
            from servicios.dj_privado import DjPrivadoService
            self._servicio = DjPrivadoService()
            self._estado_motor = self._servicio.estado_motor()
            self.estadoMotorCambiado.emit()

    def _lanzar_worker_inicio(self, prompt: str, minutos: int) -> None:
        """Lanza la construccion de la sesion en un QThread.

        Importamos QThread aqui para evitar la dependencia en la cabecera del
        modulo (la UI ya carga PySide6 al arranque y este import es liviano).
        """
        from PySide6.QtCore import QThread, QObject as _QObject

        class _Worker(_QObject):
            terminado = Signal("QVariant")
            falla = Signal(str)

            def __init__(self, prompt: str, minutos: int, parent=None):
                super().__init__(parent)
                self._prompt = prompt
                self._minutos = minutos

            def correr(self):
                try:
                    from servicios.dj_privado import DjPrivadoService, OpcionesConstructor
                    svc = DjPrivadoService()
                    sesion = svc.iniciar_sesion(
                        self._prompt,
                        duracion_minutos=self._minutos,
                        opciones=OpcionesConstructor(tam_bloque_inicial=8),
                    )
                    # Continuar bloques hasta cubrir o pool vacio
                    while not sesion.completada:
                        bloque = svc.continuar_construccion()
                        if not bloque or not bloque.pistas:
                            break
                    self.terminado.emit({
                        "sesion_id": sesion.sesion_id,
                        "completada": sesion.completada,
                    })
                except Exception as exc:
                    self.falla.emit(str(exc))

        self._asegurar_servicio()
        self._construyendo = True
        self.construyendoCambiado.emit()

        self._thread = QThread(self)
        self._worker = _Worker(prompt, minutos)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.correr)
        self._worker.terminado.connect(self._on_worker_terminado)
        self._worker.falla.connect(self._on_worker_falla)
        self._worker.terminado.connect(self._thread.quit)
        self._worker.falla.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _on_worker_terminado(self, info: dict) -> None:
        self._construyendo = False
        self.construyendoCambiado.emit()
        try:
            self._asegurar_servicio()
            nueva_id = int(info.get("sesion_id") or 0)
            sesion = self._servicio.cargar_sesion(nueva_id)
            # Si hay otra sesión sonando AHORA, no la reemplazamos en frío:
            # la nueva queda visible en el historial y, cuando el usuario
            # termine la actual o explícitamente la abra, se carga. Esto
            # evita que la UI muestre datos de la nueva mientras el audio
            # sigue siendo de la anterior.
            estado = (self._estado_dj or "").lower()
            reproduciendo_otra = (
                estado in ("reproduciendo", "transicionando", "pausado")
                and self._sesion_id_actual
                and int(self._sesion_id_actual) != nueva_id
            )
            if reproduciendo_otra:
                self.cargar_historial()
                self.avisoUi.emit(
                    "Tu nueva sesión está lista — la verás en el historial",
                    "info",
                )
                return
            self._sesion_id_actual = sesion.sesion_id
            self._publicar_sesion(sesion)
            self.cargar_historial()
            self.sesionLista.emit()
            # Si la sesión salió incompleta (la biblioteca no alcanzó
            # para cubrir la duración pedida), avisamos. Sin esto el
            # usuario veía la sesión más corta que pidió sin saber por
            # qué.
            if not bool(info.get("completada", False)):
                objetivo = int(self._sesion_info.get("minutos") or 0)
                duracion_real = float((self._resumen or {}).get("duracion_seg") or 0.0)
                minutos_reales = max(0, int(duracion_real // 60))
                if objetivo and minutos_reales and minutos_reales < objetivo:
                    self.avisoUi.emit(
                        f"Tu biblioteca alcanzó para {minutos_reales} min "
                        f"de los {objetivo} solicitados. Importa más música "
                        "para sesiones más largas.",
                        "info",
                    )
                else:
                    self.avisoUi.emit(
                        "Sesión generada con todas las pistas disponibles.",
                        "info",
                    )
        except Exception as e:
            _log.error(f"[dj] post-construccion fallo: {e}", exc_info=True)
            self.error.emit("Se construyó la sesión pero no se pudo cargar.")

    def _on_worker_falla(self, mensaje: str) -> None:
        self._construyendo = False
        self.construyendoCambiado.emit()
        _log.warning(f"[dj] worker falló: {mensaje}")
        self.error.emit(mensaje or "Error al construir la sesión.")

    def _cleanup_thread(self) -> None:
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if self._thread:
            self._thread.deleteLater()
            self._thread = None

    def cerrar(self) -> None:
        """Cleanup ordenado al cerrar la aplicación.

        Detiene el reproductor de sesión (libera decks VLC + para hilo de
        polling) y espera a que el worker de construcción termine. Sin
        esto, Qt aborta con "QThread: Destroyed while thread is still
        running" cuando hay actividad pendiente al salir.
        """
        # Persistir la sesión activa ANTES de liberar el reproductor de sesión
        # (necesitamos su `pista_actual` para el pista_id). Si no hay sesión
        # reproducible, esto limpia el estado para no restaurar algo obsoleto.
        self._guardar_estado_sesion()
        # Reproductor de sesión: cierra los dos decks y para el hilo de poll.
        if self._reproductor_sesion is not None:
            try:
                self._reproductor_sesion.close()
            except Exception:
                pass
            self._reproductor_sesion = None
        # Worker de construcción (QThread): pedir quit y esperar con timeout.
        thread = self._thread
        if thread is not None and thread.isRunning():
            try:
                thread.quit()
                thread.wait(2000)
            except Exception:
                pass

    # ----------------------------------------------------------------
    # Persistencia / restauracion de la sesion (#7a)
    # ----------------------------------------------------------------

    _CLAVES_SESION_PERSIST = (
        "dj_sesion_id", "dj_pista_id", "dj_indice_pista",
        "dj_pos_pista_seg", "dj_pos_global_seg",
    )

    @Slot()
    def restaurar_sesion_persistida(self) -> None:
        """Restaura al arranque la sesion DJ que quedo activa al cerrar (#7a).

        Deja la sesion visible en PAUSADO en la pista/posicion guardadas, SIN
        arrancar audio (evita un blip o sorpresa al abrir). El PRIMER play la
        retoma desde ahi (ver :meth:`reproducir_sesion` +
        :meth:`ReproductorSesionDj.preparar_reanudacion`). Imita el patron del
        reproductor global (`_restaurar_pista_activa_persistida`).

        Idempotente: no hace nada si ya hay una sesion cargada, y descarta
        sesiones no reproducibles (descartadas/finalizadas/en error).
        """
        if self._sesion_id_actual:
            return  # ya hay una sesion cargada; no pisarla
        try:
            from db.conexion import obtener_config
            sid = int(obtener_config("dj_sesion_id", "0") or 0)
        except (TypeError, ValueError):
            sid = 0
        if sid <= 0:
            return
        try:
            from servicios.dj_privado import persistencia as dj_persist
            fila = dj_persist.obtener_sesion(sid)
        except Exception as exc:
            _log.debug("[dj] restaurar: obtener_sesion(%s) falló: %s", sid, exc)
            return
        # Solo restauramos sesiones reproducibles ('lista'); las descartadas,
        # finalizadas, en error o aun construyendose se ignoran y se limpian.
        if fila is None or (fila.estado or "").lower() != "lista":
            self._limpiar_estado_sesion_persistido()
            return
        try:
            from db.conexion import obtener_config
            pista_id = int(obtener_config("dj_pista_id", "0") or 0)
            indice_guardado = int(obtener_config("dj_indice_pista", "0") or 0)
            offset = float(obtener_config("dj_pos_pista_seg", "0") or 0.0)
            glob = float(obtener_config("dj_pos_global_seg", "0") or 0.0)
        except (TypeError, ValueError):
            pista_id, indice_guardado, offset, glob = 0, 0, 0.0, 0.0
        try:
            self._asegurar_servicio()
            sesion = self._servicio.cargar_sesion(sid)
            self._sesion_id_actual = sesion.sesion_id
            self._publicar_sesion(sesion)
        except Exception as exc:
            _log.warning("[dj] no se pudo restaurar la sesión %s: %s", sid, exc)
            self._sesion_id_actual = 0
            self._limpiar_estado_sesion_persistido()
            return
        # Indice para resaltar en la UI (la lista planificada va por posicion).
        indice = indice_guardado
        try:
            for i, p in enumerate(self._pistas_planificadas.snapshot()):
                if pista_id and int(p.get("pista_id") or 0) == pista_id:
                    indice = i
                    break
        except Exception:
            pass
        # Estado visible: PAUSADO en la pista/posicion guardadas, sin audio.
        # El play consume esta reanudacion (ver reproducir_sesion).
        self._reanudar_sesion_pendiente = {
            "sesion_id": sid, "pista_id": pista_id,
            "indice": int(indice), "offset": max(0.0, offset),
        }
        self._estado_dj = "pausado"
        self._indice_pista_dj = int(indice)
        self._pos_sesion_seg = max(0.0, glob)
        self._pos_pista_seg = max(0.0, offset)
        self.reproduccionCambiada.emit()
        self.pistaActualCambiada.emit(int(indice))
        self.progresoSesionCambiado.emit()
        _log.info(
            "[dj] sesión %s restaurada en pausa (pista_id=%s, offset=%.1fs)",
            sid, pista_id, offset,
        )

    def _guardar_estado_sesion(self) -> None:
        """Persiste la sesion DJ activa para reanudarla al reabrir (#7a).

        Solo guarda si hay una sesion reproducible en curso (sonando o en
        pausa). En cualquier otro caso (sin sesion, detenida, finalizada,
        descartada) limpia el estado para no restaurar algo obsoleto.
        """
        try:
            from db.conexion import guardar_config
            sid = int(self._sesion_id_actual or 0)
            estado = (self._estado_dj or "").lower()
            if sid <= 0 or estado not in ("reproduciendo", "pausado", "transicionando"):
                self._limpiar_estado_sesion_persistido()
                return
            indice = int(self._indice_pista_dj) if self._indice_pista_dj >= 0 else 0
            offset = max(0.0, float(self._pos_pista_seg or 0.0))
            glob = max(0.0, float(self._pos_sesion_seg or 0.0))
            # pista_id de la pista en curso: del reproductor de sesion si esta
            # vivo; si no (sesion restaurada y aun no reproducida), de la
            # reanudacion pendiente.
            pista_id = 0
            rs = self._reproductor_sesion
            if rs is not None:
                p = getattr(rs, "pista_actual", None)
                if p is not None:
                    pista_id = int(getattr(p, "pista_id", 0) or 0)
            if pista_id <= 0 and self._reanudar_sesion_pendiente:
                pista_id = int(self._reanudar_sesion_pendiente.get("pista_id") or 0)
            guardar_config("dj_sesion_id", str(sid))
            guardar_config("dj_pista_id", str(pista_id))
            guardar_config("dj_indice_pista", str(indice))
            guardar_config("dj_pos_pista_seg", f"{offset:.3f}")
            guardar_config("dj_pos_global_seg", f"{glob:.3f}")
        except Exception as exc:
            _log.debug("[dj] no se pudo guardar estado de sesión: %s", exc)

    def _limpiar_estado_sesion_persistido(self) -> None:
        """Marca que no hay sesion DJ por restaurar (sin tocar el esquema)."""
        self._reanudar_sesion_pendiente = None
        try:
            from db.conexion import guardar_config
            guardar_config("dj_sesion_id", "0")
        except Exception as exc:
            _log.debug("[dj] no se pudo limpiar estado de sesión: %s", exc)

    # ----------------------------------------------------------------
    # Publicacion de datos a QML
    # ----------------------------------------------------------------

    def _publicar_sesion(self, sesion) -> None:
        from servicios.dj_privado import persistencia as dj_persist
        fila = dj_persist.obtener_sesion(sesion.sesion_id)
        if not fila:
            return
        resumen = self._parse_json(fila.resumen_json)
        self._sesion_info = {
            "id": sesion.sesion_id,
            "estado": fila.estado,
            "prompt": fila.prompt_original,
            "minutos": fila.objetivo_minutos,
            "motor_version": fila.motor_version,
            "creado_en": fila.creado_en,
            "playlist_id": fila.playlist_id or 0,
        }
        _pid_guardada = int(fila.playlist_id or 0)
        self._playlist_guardada_id = (
            _pid_guardada if (_pid_guardada > 0 and svc_bib.playlist_existe(_pid_guardada)) else 0
        )
        self._resumen = resumen
        self._intent_visible = {
            "prompt": sesion.intent.prompt,
            "resumen": sesion.intent.resumen,
            "focos": list(sesion.intent.focos),
            "exclusiones": list(sesion.intent.exclusiones),
            "curva": sesion.intent.curva_energia,
            "estilo": sesion.intent.estilo_transicion or {},
            "vacio": sesion.intent.vacio,
            "notas": list(sesion.intent.notas),
        }
        self._recargar_pistas_planificadas()
        self.estadoSesionCambiado.emit()

    def _recargar_pistas_planificadas(self) -> None:
        if not self._sesion_id_actual:
            self._pistas_planificadas.set_datos([])
            return
        from servicios.dj_privado import persistencia as dj_persist
        filas = dj_persist.listar_pistas_sesion(self._sesion_id_actual)
        datos = []
        for fila in filas:
            datos.append({
                "posicion": int(fila["posicion"]),
                "pista_id": int(fila["pista_id"]) if fila.get("pista_id") else 0,
                "titulo": fila.get("titulo") or "",
                "artista": fila.get("artista_nombre") or "",
                "album": fila.get("album_titulo") or "",
                "duracion_seg": float(fila.get("duracion_seg") or 0.0),
                "ruta_archivo": fila.get("ruta_archivo") or "",
                "score_total": float(fila.get("score_total") or 0.0),
                "score_intent": float(fila.get("score_intent") or 0.0),
                "score_transicion": float(fila.get("score_transicion") or 0.0),
                "score_curva": float(fila.get("score_curva") or 0.0),
                "razones": list(fila.get("razones") or []),
                "transicion": fila.get("transicion") or {},
                "estado": fila.get("estado") or "planificada",
                "bloqueada": bool(fila.get("bloqueada") or False),
            })
        self._pistas_planificadas.set_datos(datos)
        self.sesionLista.emit()

    def _parse_json(self, payload) -> dict:
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except (TypeError, ValueError):
            return {}

    # ----------------------------------------------------------------
    # Integracion con reproductor
    # ----------------------------------------------------------------

    def _on_estado_reproductor(self, estado, pista_activa) -> None:
        """Detecta cambios de pista para registrar reproducciones/skips.

        Heuristica:
          - Si la pista activa cambia y la pista anterior pertenecia a la
            sesion activa, registramos como reproducida.
          - El skip explicito se debe disparar via notificar_skip; aqui solo
            cubrimos el avance natural.
        """
        if not self._servicio or not self._sesion_id_actual:
            self._pista_anterior_id = pista_activa.id if pista_activa else None
            return
        pista_id_actual = pista_activa.id if pista_activa else None
        if self._pista_anterior_id and self._pista_anterior_id != pista_id_actual:
            try:
                posicion = self._posicion_para_pista(self._pista_anterior_id)
                if posicion is not None:
                    self._servicio.registrar_reproduccion(posicion, self._pista_anterior_id)
            except Exception:
                _log.debug("[dj] no se pudo registrar reproduccion", exc_info=True)
        self._pista_anterior_id = pista_id_actual

    def _posicion_para_pista(self, pista_id: int) -> Optional[int]:
        from db.conexion import obtener_una_fila
        fila = obtener_una_fila(
            "SELECT posicion FROM dj_pistas_sesion WHERE sesion_id=? AND pista_id=? ORDER BY posicion LIMIT 1",
            (int(self._sesion_id_actual), int(pista_id)),
        )
        if fila:
            return int(fila["posicion"])
        return None


# =============================================================================
# MODELO EXPLORADOR CIEGO
# =============================================================================

class ModeloExploradorCiego(QObject):
    """Puente entre la VistaExploradorCiego y el servicio Python.

    Arquitectura:
      - `ExploradorCiegoService` mantiene el estado puro de la ronda.
      - Este modelo coordina:
          * lectura de candidatos via QTimer (no bloquea UI),
          * reproduccion de fragmentos en el reproductor global,
          * sincronizacion del flag de "modo ciego" del ModeloReproductor.
      - El modelo NO sabe SQL ni audio; solo conecta servicio + reproductor.

    Decisiones tecnicas:
      - Reusamos el reproductor global en vez de un motor aislado: minimiza
        complejidad, mantiene una sola fuente de verdad de audio y permite
        que "reproducir completa" sea instantaneo (la pista ya esta cargada).
      - El fragmento se temporiza con QTimer en el thread de UI (operacion
        liviana: solo pide pausar al backend cuando termina).
      - La carga de candidatos puede tardar en bibliotecas grandes; usamos
        QTimer.singleShot(0, ...) para liberar el frame de UI antes de la
        consulta. Para bibliotecas tipicas (< 50k pistas) el cost no
        justifica un QThread.
    """

    rondaIniciada      = Signal()
    rondaTerminada     = Signal("QVariant")  # resumen final
    retoCambiado       = Signal()
    revelacionCambiada = Signal()
    fragmentoCambiado  = Signal()
    disponibilidadCambiada = Signal()
    error              = Signal(str)
    mensajeUi          = Signal(str, str)  # mensaje, tono

    def __init__(self, modelo_reproductor: "ModeloReproductor", modelo_biblioteca: "ModeloBiblioteca | None" = None, parent=None):
        super().__init__(parent)
        from servicios.explorador_ciego import (
            ExploradorCiegoService,
            ModoExplorador,
            NivelRevelacion,
            EstadoReto,
        )
        # Importacion local: evita que un fallo del modulo rompa la carga
        # del resto de modelos al arrancar la app.
        self._modulo_modos = ModoExplorador
        self._modulo_niveles = NivelRevelacion
        self._modulo_estados = EstadoReto
        self._modelo_reproductor = modelo_reproductor
        # Referencia opcional a ModeloBiblioteca para delegar toggle_favorita
        # y propagar la señal `favoritaCambiada` a otros modelos (Playlists).
        self._modelo_biblioteca = modelo_biblioteca
        self._servicio = ExploradorCiegoService()
        # Memoria local de pistas ya jugadas en la sesion para evitar
        # repeticiones consecutivas. Se vacia al cerrar la app.
        self._pistas_jugadas_sesion: set[int] = set()
        # Disponibilidad por modo cacheada para que la UI no haga COUNT en
        # cada render. Se recalcula al pulsar "Refrescar" o al iniciar ronda.
        self._disponibles: dict[str, int] = {}
        # Datos visibles del reto actual (snapshot listo para QML).
        self._reto_visible: dict = {}
        # Estado del fragmento que esta sonando ahora mismo en el global.
        self._fragmento_pista_id: int = 0
        self._fragmento_segundos: float = 0.0
        # Timer que limita la duracion del fragmento de audio.
        self._timer_fragmento = QTimer(self)
        self._timer_fragmento.setSingleShot(True)
        self._timer_fragmento.timeout.connect(self._al_terminar_fragmento)
        # Suscripcion a cambios de pista del reproductor: si el usuario salta
        # manualmente desde la barra inferior mientras hay un fragmento del
        # juego sonando, cancelamos el modo ciego para que no queden "???"
        # huerfanos sobre una pista que ya no es del juego.
        try:
            self._modelo_reproductor.pista_activaCambiada.connect(
                self._al_cambiar_pista_global
            )
        except Exception:
            pass
        # Refrescar disponibilidad al inicializar para que la UI muestre
        # contadores reales en cuanto se monta.
        QTimer.singleShot(0, self._recargar_disponibilidad)

    def conectar_importacion(self, modelo_importacion: QObject) -> None:
        """Refresca la disponibilidad en cuanto termina una importación.

        Sin este enlace, "A Ciegas" se quedaba con el contador vacío
        hasta que el usuario reiniciaba la app: una biblioteca recién
        importada no aparecía en los modos del juego. Conectamos
        `importacionFin` (emitido por ``ModeloImportacion`` al cerrar
        una sesión de importación) para volver a contar pistas
        disponibles automáticamente.
        """
        try:
            modelo_importacion.importacionFin.connect(
                lambda _info: self._recargar_disponibilidad()
            )
        except Exception as exc:
            _log.debug("conectar_importacion (ExploradorCiego) fallo: %s", exc)

    # ----------------------------------------------------------------
    # Propiedades expuestas a QML
    # ----------------------------------------------------------------

    @Property("QVariant", notify=disponibilidadCambiada)
    def disponibles_por_modo(self) -> dict:
        """Diccionario {modo: n} para que la UI pinte contadores por modo."""
        return self._disponibles

    @Property(int, notify=disponibilidadCambiada)
    def total_biblioteca(self) -> int:
        """Suma de las pistas disponibles. Cero si no hay biblioteca."""
        try:
            return sum(int(v) for v in self._disponibles.values())
        except Exception:
            return 0

    @Property(bool, notify=disponibilidadCambiada)
    def hay_biblioteca(self) -> bool:
        return self.total_biblioteca > 0

    @Property(str, notify=retoCambiado)
    def modo_activo(self) -> str:
        return self._servicio.modo.value if self._servicio.modo else ""

    @Property(bool, notify=retoCambiado)
    def ronda_activa(self) -> bool:
        return self._servicio.ronda_activa

    @Property(bool, notify=retoCambiado)
    def ronda_terminada(self) -> bool:
        return self._servicio.ronda_terminada

    @Property(int, notify=retoCambiado)
    def indice_reto(self) -> int:
        return self._servicio.indice

    @Property(int, notify=retoCambiado)
    def total_retos(self) -> int:
        return self._servicio.total

    @Property("QVariant", notify=retoCambiado)
    def reto(self) -> dict:
        return self._reto_visible

    @Property("QVariant", notify=retoCambiado)
    def conteo(self) -> dict:
        """Acertados/revelados/pasados/en_curso de la ronda actual."""
        return self._servicio.conteo_estados()

    @Property(bool, notify=fragmentoCambiado)
    def fragmento_reproduciendose(self) -> bool:
        return self._fragmento_pista_id > 0 and self._timer_fragmento.isActive()

    @Property(int, notify=fragmentoCambiado)
    def fragmento_pista_id(self) -> int:
        return int(self._fragmento_pista_id)

    @Property(float, notify=fragmentoCambiado)
    def segundos_fragmento(self) -> float:
        return float(self._servicio.segundos_fragmento)

    # ----------------------------------------------------------------
    # Slots (operaciones disponibles desde QML)
    # ----------------------------------------------------------------

    @Slot()
    def refrescar(self) -> None:
        self._recargar_disponibilidad()

    @Slot(str, int, result=bool)
    def iniciar_ronda(self, modo_str: str, retos: int = 5) -> bool:
        modo = self._parsear_modo(modo_str)
        if modo is None:
            self.error.emit("Modo de juego desconocido.")
            return False
        if not self._servicio.puede_iniciar(modo, int(retos or 5)):
            self.error.emit(
                "No hay suficientes pistas en tu biblioteca para este modo."
            )
            return False
        # Detenemos cualquier fragmento previo para no encadenar audio.
        self._cancelar_fragmento_en_curso()
        reto = self._servicio.iniciar_ronda(
            modo,
            int(retos or 5),
            evitar_pistas_ids=set(self._pistas_jugadas_sesion),
        )
        if reto is None:
            self.error.emit("No se pudo construir la ronda.")
            return False
        # Recordamos las ids elegidas para que la proxima ronda no las repita.
        for r in self._servicio._retos:  # noqa: SLF001 acceso interno controlado
            self._pistas_jugadas_sesion.add(int(r.pista_id))
        self._publicar_reto()
        self.rondaIniciada.emit()
        return True

    @Slot(result=bool)
    def reproducir_fragmento(self) -> bool:
        """Empieza el fragmento de audio del reto actual.

        Flujo:
          1. Cancela timer y modo ciego previo si los habia.
          2. Pide al reproductor global cargar y reproducir la pista.
          3. Activa el modo ciego en el reproductor SOLO si el reto sigue
             en curso. Si ya esta acertado/revelado/pasado, dejamos los
             metadatos visibles: el usuario ya conoce la respuesta.
          4. Salta al offset recomendado y arranca el timer que pausara
             al cumplirse `segundos_fragmento`.

        El boton "reproducir completa" simplemente cancela el timer y la
        pista sigue sonando.
        """
        reto = self._servicio.reto_actual()
        if reto is None:
            return False
        ruta = str(reto.pista.get("ruta_archivo") or "").strip()
        if not ruta:
            self.error.emit("Esta pista no tiene archivo reproducible.")
            return False
        self._cancelar_fragmento_en_curso()
        # Estado actual: si ya termino la fase oculta, no activamos censura.
        try:
            estado_actual = str(reto.estado.value if hasattr(reto.estado, "value") else reto.estado)
        except Exception:
            estado_actual = ""
        reto_en_juego = estado_actual == "en_curso"

        # Reproducir reutilizando el modelo de reproductor: respeta la
        # liberacion del DJ y registra historial igual que cualquier otra
        # reproduccion. La pista entra como "pista unica" en la cola.
        try:
            self._modelo_reproductor.reproducir(dict(reto.pista))
        except Exception as exc:
            _log.warning("[explorador_ciego] no se pudo reproducir: %s", exc)
            self.error.emit("No se pudo reproducir la pista.")
            return False
        pista_id = int(reto.pista_id)
        self._fragmento_pista_id = pista_id
        self._fragmento_segundos = float(self._servicio.segundos_fragmento)
        if reto_en_juego:
            # Activa modo ciego en el reproductor para censurar la barra
            # inferior mientras se juega. Si revelan o terminan, la UI lo
            # limpia.
            try:
                self._modelo_reproductor.set_modo_ciego(pista_id)
            except Exception:
                pass
        else:
            # Reto ya finalizado: aseguramos que el modo ciego este
            # apagado (puede haber quedado un valor previo).
            try:
                self._modelo_reproductor.limpiar_modo_ciego()
            except Exception:
                pass
        # Saltar a la posicion sugerida. Damos un pequeno respiro para que
        # VLC abra el media antes de buscar — set_position antes de eso es
        # ignorado. 250 ms es suficiente en la mayoria de casos.
        offset = self._servicio.posicion_inicio_fragmento(reto)
        QTimer.singleShot(250, lambda: self._aplicar_seek(offset))
        # Programar pausa al final del fragmento.
        ms = int(max(2.0, self._fragmento_segundos) * 1000)
        self._timer_fragmento.start(ms)
        self._servicio.marcar_fragmento_escuchado()
        self._publicar_reto()
        self.fragmentoCambiado.emit()
        return True

    @Slot()
    def detener_fragmento(self) -> None:
        """Pausa el fragmento sin revelar nada. Util si el usuario se rinde
        a oirlo pero no quiere revelar aun."""
        self._cancelar_fragmento_en_curso(pausar_audio=True)

    @Slot()
    def revelar_artista(self) -> None:
        self._servicio.revelar_artista()
        self._publicar_reto()
        self.revelacionCambiada.emit()

    @Slot()
    def revelar_album(self) -> None:
        self._servicio.revelar_album()
        self._publicar_reto()
        self.revelacionCambiada.emit()

    @Slot()
    def revelar_todo(self) -> None:
        self._servicio.revelar_total()
        self._publicar_reto()
        # Al revelar todo, retiramos el modo ciego del reproductor: la
        # barra inferior puede ya mostrar la info real.
        try:
            self._modelo_reproductor.limpiar_modo_ciego()
        except Exception:
            pass
        self.revelacionCambiada.emit()

    @Slot()
    def marcar_acertada(self) -> None:
        """Salida alternativa para titulos en alfabetos no latinos.

        Confiamos en el usuario (no validamos): para titulos en cirilico,
        chino, etc. la UI muestra esta opcion en vez del input de texto
        porque pedir teclear esos alfabetos rompe el flow del juego.
        """
        self._servicio.marcar_acertada()
        self._publicar_reto()
        try:
            self._modelo_reproductor.limpiar_modo_ciego()
        except Exception:
            pass
        self.revelacionCambiada.emit()
        self.mensajeUi.emit("¡Acertaste!", "info")

    @Slot(str, result="QVariant")
    def intentar_adivinar(self, texto: str) -> dict:
        """Valida un intento escrito y devuelve el resultado a QML.

        Resultado: dict {"acierto", "cerca", "ratio"}.
          - acierto=True: el reto pasa a estado ACERTADO con nivel TOTAL.
          - cerca=True: animar feedback "muy cerca" pero no avanzar.
          - resto: incrementa contador de intentos fallidos para que la UI
            pueda mostrar hint progresiva ("¿Quieres una pista?").

        Los toasts los emite el modelo (no la QML) porque las `signal` de
        componentes QML no devuelven valores; si la UI consume el resultado
        del slot tras un `signal -> function -> return`, recibe `undefined`.
        Aqui centralizamos el feedback para evitar ese bug.
        """
        resultado = self._servicio.intentar_adivinar(texto or "")
        if resultado.get("acierto"):
            try:
                self._modelo_reproductor.limpiar_modo_ciego()
            except Exception:
                pass
            self._publicar_reto()
            self.revelacionCambiada.emit()
            self.mensajeUi.emit("¡Acertaste!", "info")
        elif resultado.get("cerca"):
            # Aviso suave: el usuario va bien encaminado.
            self._publicar_reto()
            self.mensajeUi.emit("Muy cerca, vuelve a intentarlo.", "info")
        else:
            self._publicar_reto()
            self.mensajeUi.emit("No es esa. Pide una pista o pulsa Me rindo.", "warning")
        return dict(resultado)

    @Slot(str)
    def revelar_hint(self, clave: str) -> None:
        """Desbloquea una hint del catalogo (empieza_con, termina_con, etc.).

        Las hints no afectan el estado del reto, solo agregan informacion
        visible. Si el usuario revela demasiadas, el reto sigue siendo
        adivinable: no penalizamos esta accion (la penalizacion ya esta en
        el resumen final, donde lo que cuenta es acertar vs. rendirse).
        """
        self._servicio.revelar_hint(str(clave or "").strip())
        self._publicar_reto()
        self.revelacionCambiada.emit()

    @Slot()
    def marcar_pasado(self) -> None:
        self._servicio.marcar_pasado()
        self._publicar_reto()
        self.revelacionCambiada.emit()

    @Slot(result=bool)
    def reproducir_completa(self) -> bool:
        """Reproduce la pista del reto hasta el final SIN revelar metadatos.

        Diferencia con "revelar_todo": este metodo NO toca el nivel de
        revelacion del reto. El usuario puede querer oirla entera sin
        que la app le diga la respuesta — sigue siendo parte del juego.

        Casuistica:
          A) Fragmento activo: pista cargada y SONANDO. Solo cancelamos
             timer. La pista continua hasta el final.
          B) Fragmento ya termino (timer pauso el audio): pista cargada
             pero PAUSADA. Llamamos a `pausar_reanudar()` para retomar.
          C) Pista distinta sonando o nada cargado: arrancamos la pista
             del reto desde cero.

        El modo ciego del reproductor se MANTIENE: la barra inferior
        sigue censurada para que la cancion suene sin spoilear. Solo se
        libera cuando el usuario decide revelar o rendirse.
        """
        reto = self._servicio.reto_actual()
        if reto is None:
            return False
        # Detener el limite del fragmento si seguia activo.
        if self._timer_fragmento.isActive():
            self._timer_fragmento.stop()

        try:
            pista_activa = self._modelo_reproductor.pista_activa or {}
            id_activo = int(pista_activa.get("id") or 0)
        except Exception:
            id_activo = 0

        if id_activo == int(reto.pista_id):
            # La pista correcta ya esta cargada. Si esta pausada,
            # reanudamos. El bloqueo del reproductor (set_juego_blind_activo)
            # evita que el usuario pueda volver a pausarla, garantizando
            # que la cancion suena hasta el final del fragmento del juego.
            try:
                if not self._modelo_reproductor.reproduciendo:
                    self._modelo_reproductor.pausar_reanudar_forzado(True)
            except Exception:
                self.error.emit("No se pudo reanudar la reproducción.")
                return False
        else:
            # Otra pista (o ninguna): cargar la del reto desde el principio.
            try:
                self._modelo_reproductor.reproducir(dict(reto.pista))
            except Exception:
                self.error.emit("No se pudo iniciar la reproducción.")
                return False
            # Restaurar el flag del modo ciego (se pierde si la pista cambio).
            try:
                self._modelo_reproductor.set_modo_ciego(int(reto.pista_id))
            except Exception:
                pass

        # No marcamos fragmento activo: a partir de aqui el audio puede
        # correr libremente sin timer hasta que el usuario avance.
        self._fragmento_pista_id = 0
        self._fragmento_segundos = 0.0
        self.fragmentoCambiado.emit()
        # Solo invitamos a adivinar si el reto sigue oculto. Si ya esta
        # acertado/revelado/pasado, el mensaje confunde al usuario que ya
        # sabe la respuesta y solo quiere oirla entera.
        try:
            estado_actual = str(reto.estado.value if hasattr(reto.estado, "value") else reto.estado)
        except Exception:
            estado_actual = ""
        if estado_actual == "en_curso":
            self.mensajeUi.emit("Reproduciendo completa. Adivina antes que termine.", "info")
        else:
            self.mensajeUi.emit("Reproduciendo completa.", "info")
        return True

    @Slot()
    def revelar_titulo(self) -> None:
        """Revela el titulo del reto actual sin marcar como rendido.

        Util cuando el usuario ya escucho lo suficiente y quiere ver la
        respuesta sin penalizar el resumen con "saltada". El estado del
        reto pasa a REVELADO (no a PASADO).
        """
        reto = self._servicio.revelar_total()
        if reto is None:
            return
        try:
            self._modelo_reproductor.limpiar_modo_ciego()
        except Exception:
            pass
        self._publicar_reto()
        self.revelacionCambiada.emit()

    @Slot(result=bool)
    def agregar_a_cola(self) -> bool:
        reto = self._servicio.reto_actual()
        if reto is None:
            return False
        try:
            self._modelo_reproductor.agregar_a_cola(dict(reto.pista))
        except Exception as exc:
            _log.warning("[explorador_ciego] agregar_a_cola fallo: %s", exc)
            return False
        self.mensajeUi.emit("Añadida a la cola.", "info")
        return True

    @Slot()
    def siguiente_reto(self) -> None:
        # Al cambiar de reto, detenemos el audio anterior por completo.
        # Sin esto, la pista anterior seguia sonando en la barra inferior
        # y el reproductor no asociaba la siguiente al juego.
        self._detener_audio_del_reto()
        reto = self._servicio.avanzar()
        if reto is None:
            # No hay mas retos: terminar ronda y emitir resumen.
            resumen = self._servicio.cerrar_ronda()
            self._reto_visible = {}
            self.retoCambiado.emit()
            payload = resumen.to_dict() if resumen else {}
            self.rondaTerminada.emit(payload)
            return
        self._publicar_reto()

    @Slot()
    def reto_anterior(self) -> None:
        self._detener_audio_del_reto()
        if self._servicio.retroceder() is not None:
            self._publicar_reto()

    @Slot()
    def terminar_ronda(self) -> None:
        """Cierra la ronda actual incluso si quedan retos pendientes."""
        self._detener_audio_del_reto()
        resumen = self._servicio.cerrar_ronda()
        self._reto_visible = {}
        self.retoCambiado.emit()
        payload = resumen.to_dict() if resumen else {}
        self.rondaTerminada.emit(payload)

    @Slot(int, result=bool)
    def alternar_favorita(self, pista_id: int) -> bool:
        """Permite marcar la pista del reto como favorita sin salir del juego.

        Delega en ModeloBiblioteca cuando está disponible para que la
        señal `favoritaCambiada` se propague a Playlists y Búsqueda.
        """
        try:
            if self._modelo_biblioteca is not None:
                nuevo = self._modelo_biblioteca.toggle_favorita(int(pista_id))
            else:
                nuevo = svc_bib.toggle_favorita(int(pista_id))
        except Exception:
            return False
        reto = self._servicio.reto_actual()
        if reto is not None and int(reto.pista_id) == int(pista_id):
            reto.pista["favorita"] = bool(nuevo)
            self._publicar_reto()
        self.mensajeUi.emit(
            "Añadida a tus favoritas." if nuevo else "Quitada de favoritas.",
            "info",
        )
        return bool(nuevo)

    @Slot(float)
    def set_segundos_fragmento(self, segundos: float) -> None:
        self._servicio.set_segundos_fragmento(segundos)
        self.fragmentoCambiado.emit()

    # ----------------------------------------------------------------
    # Internos
    # ----------------------------------------------------------------

    def _parsear_modo(self, modo_str: str):
        if not modo_str:
            return None
        try:
            return self._modulo_modos(str(modo_str))
        except ValueError:
            return None

    def _recargar_disponibilidad(self) -> None:
        try:
            self._disponibles = dict(self._servicio.disponibles_por_modo())
        except Exception as exc:
            _log.warning("[explorador_ciego] recargar disponibilidad: %s", exc)
            self._disponibles = {}
        self.disponibilidadCambiada.emit()

    def _publicar_reto(self) -> None:
        reto = self._servicio.reto_actual()
        if reto is None:
            self._reto_visible = {}
        else:
            self._reto_visible = reto.datos_visibles()
        self.retoCambiado.emit()

    def _cancelar_fragmento_en_curso(self, *, pausar_audio: bool = False) -> None:
        """Cancela el timer del fragmento. NO toca el modo ciego: lo gestiona
        quien llama (avanzar reto -> liberar; jugar de nuevo -> reactivar).

        `pausar_audio` aqui significa "pausar sin liberar la pista cargada",
        para el caso de que el usuario pulse "Pausar fragmento" sin avanzar.
        Para detener completamente al cambiar de reto usamos `_detener_audio`.
        """
        if self._timer_fragmento.isActive():
            self._timer_fragmento.stop()
        if pausar_audio and self._fragmento_pista_id:
            try:
                self._modelo_reproductor.pausar_reanudar_forzado(False)
            except Exception:
                pass
        self._fragmento_pista_id = 0
        self._fragmento_segundos = 0.0
        self.fragmentoCambiado.emit()

    def _detener_audio_del_reto(self) -> None:
        """Detiene completamente el audio del reto y libera el modo ciego.

        Se llama al cambiar de reto, terminar la ronda o retroceder: la
        pista anterior NO debe seguir sonando aunque el usuario solo haya
        pulsado "Siguiente". Usa el bypass `detener_forzado` porque el
        bloqueo de juego ya silenciaria `detener()`.
        """
        if self._timer_fragmento.isActive():
            self._timer_fragmento.stop()
        try:
            self._modelo_reproductor.detener_forzado()
        except Exception:
            pass
        try:
            self._modelo_reproductor.limpiar_modo_ciego()
        except Exception:
            pass
        self._fragmento_pista_id = 0
        self._fragmento_segundos = 0.0
        self.fragmentoCambiado.emit()

    def _aplicar_seek(self, segundos: float) -> None:
        try:
            # El bloqueo del juego silenciaria `buscar_posicion()` para el
            # publico; el seek inicial del fragmento es interno asi que
            # usamos el reproductor backend directamente para hacer el
            # offset al chorus sin pelearnos con el lock.
            self._modelo_reproductor._rep.buscar_posicion(float(segundos))  # noqa: SLF001
        except Exception:
            # En caso de que la pista no sea seekeable (formato raro) seguimos
            # con la reproduccion desde donde inicio: no es critico para el
            # juego.
            pass

    @Slot()
    def _al_terminar_fragmento(self) -> None:
        """Cuando el QTimer cumple, pausamos audio via bypass (el bloqueo
        del juego silenciaria un pausar_reanudar publico). La pista sigue
        cargada en el reproductor: "Reproducir completa" solo necesita
        reanudar."""
        try:
            self._modelo_reproductor.pausar_reanudar_forzado(False)
        except Exception:
            pass
        self._fragmento_pista_id = 0
        self._fragmento_segundos = 0.0
        self.fragmentoCambiado.emit()

    @Slot()
    def _al_cambiar_pista_global(self) -> None:
        """Si el reproductor pasa a otra pista (skip manual, fin natural en
        cola, etc.) y la nueva NO coincide con la del juego, liberamos el
        modo ciego para no dejar "???" sobre algo que no pertenece al juego."""
        try:
            datos = self._modelo_reproductor.pista_activa or {}
            id_activo = int(datos.get("id") or 0)
        except Exception:
            id_activo = 0
        if not self._fragmento_pista_id:
            return
        if id_activo == int(self._fragmento_pista_id):
            return
        # Pista distinta: cancelar fragmento + limpiar ciego.
        if self._timer_fragmento.isActive():
            self._timer_fragmento.stop()
        self._fragmento_pista_id = 0
        self._fragmento_segundos = 0.0
        try:
            self._modelo_reproductor.limpiar_modo_ciego()
        except Exception:
            pass
        self.fragmentoCambiado.emit()

    def cerrar(self) -> None:
        """Detiene el timer de fragmento para que no dispare durante el cierre."""
        try:
            if self._timer_fragmento.isActive():
                self._timer_fragmento.stop()
        except Exception as exc:
            _log.debug("stop timer fragmento explorador ciego fallo: %s", exc)


# =============================================================================
# MODELO DE DEPENDENCIAS (PLUG & PLAY)
# =============================================================================

class _WorkerInstalarDep(QObject):
    """Worker que corre en un QThread y dispara la instalación de una
    dependencia. Emite señales de progreso, éxito y error. Sin él, el
    proceso de pip (que bloquea segundos o minutos) congelaría la UI.
    """
    progreso = Signal(str, str)   # (dep_id, linea_stdout)
    completado = Signal(str, bool, str, str)  # (dep_id, ok, mensaje, detalle)

    def __init__(self, dep_id: str, pip_specifier: str,
                 extra_index_url: str = "", parent=None) -> None:
        super().__init__(parent)
        self._dep_id = dep_id
        self._pip_specifier = pip_specifier
        self._extra_index_url = extra_index_url

    @Slot()
    def ejecutar(self) -> None:
        from infra.instalador import instalar_pip

        def _cb(linea: str) -> None:
            try:
                self.progreso.emit(self._dep_id, linea)
            except Exception:
                pass

        res = instalar_pip(
            self._pip_specifier,
            extra_index_url=self._extra_index_url,
            en_progreso=_cb,
        )
        # Post-install hook: cuando se instala Demucs, pre-descargamos los
        # pesos del modelo htdemucs (~80MB) a la carpeta cache de NB Sound.
        # Sin esto, la primera vez que el usuario arranca el procesamiento
        # de Karaoke, Demucs intenta descargar vía torch.hub desde el
        # bundle PyInstaller (Python sin pip ni certs estándar) y suele
        # fallar con "Verifica conexión a internet".
        if res.ok and self._dep_id == "demucs":
            try:
                from infra.instalador import precargar_modelo_demucs
                self.progreso.emit(self._dep_id,
                                   "Pre-descargando modelo htdemucs (~80 MB)...")
                modelo_res = precargar_modelo_demucs(
                    "htdemucs", en_progreso=_cb,
                )
                if not modelo_res.ok:
                    res = type(res)(
                        ok=False,
                        mensaje=(res.mensaje + " | Pesos del modelo: "
                                 + modelo_res.mensaje),
                        detalle=modelo_res.detalle,
                    )
                else:
                    res = type(res)(
                        ok=True,
                        mensaje=res.mensaje + " | " + modelo_res.mensaje,
                        detalle=res.detalle,
                    )
            except Exception as exc:
                _log.warning("Pre-descarga demucs fallo: %s", exc)
        self.completado.emit(self._dep_id, bool(res.ok), res.mensaje, res.detalle)


class _WorkerRepararPython(QObject):
    """Worker que dispara `infra.instalador.reparar_python_linux` en QThread."""
    progreso = Signal(str)
    completado = Signal(bool, str, str)

    @Slot()
    def ejecutar(self) -> None:
        try:
            from infra.instalador import (
                auditar_python_sistema,
                reparar_python_linux,
            )
        except Exception as exc:
            self.completado.emit(False, f"No se pudo importar instalador: {exc}", "")
            return

        chq = auditar_python_sistema()
        if chq.utilizable:
            self.completado.emit(True, "Python ya está correctamente configurado.", "")
            return

        def _cb(linea: str) -> None:
            try:
                self.progreso.emit(linea)
            except Exception:
                pass

        res = reparar_python_linux(chq, en_progreso=_cb)
        self.completado.emit(bool(res.ok), res.mensaje, res.detalle)


class _WorkerDescargarModelosEssentia(QObject):
    """Worker que descarga los modelos .pb de Essentia faltantes a la
    carpeta configurada por el usuario. Emite progreso por archivo y un
    resumen final al terminar.
    """
    progreso = Signal(str, str)              # (dep_id, linea)
    completado = Signal(str, bool, str, str) # (dep_id, ok, mensaje, detalle)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._dep_id = "modelos_essentia"

    @Slot()
    def ejecutar(self) -> None:
        try:
            from infra.modelos_essentia import descargar_faltantes
        except Exception as exc:
            self.completado.emit(self._dep_id, False,
                                 f"No se pudo importar modelos_essentia: {exc}", "")
            return

        def _mensaje(linea: str) -> None:
            try:
                self.progreso.emit(self._dep_id, linea)
            except Exception:
                pass

        def _archivo(nombre: str, leido: int, total: int) -> None:
            if total > 0:
                pct = (leido * 100) // total
                self.progreso.emit(self._dep_id, f"  {nombre}: {pct}%")

        resultado = descargar_faltantes(en_archivo=_archivo, en_mensaje=_mensaje)
        if resultado.ok:
            mensaje = (
                f"Descargados {len(resultado.descargados)}, "
                f"{len(resultado.omitidos)} ya estaban presentes."
            )
            self.completado.emit(self._dep_id, True, mensaje, "")
        else:
            mensaje = (
                f"Faltaron {len(resultado.fallidos)} archivos. "
                "Pulsa 'Reintentar' para volver a descargarlos."
            )
            detalle = "; ".join(f"{k}: {v}" for k, v in resultado.fallidos.items())
            self.completado.emit(self._dep_id, False, mensaje, detalle[:500])


class ModeloDependencias(QObject):
    """Bridge QML <-> infra.dependencias.

    Expone:
      * ``estado``: lista de dicts ({id, nombre, estado, version, …}) para
        que QML pinte la pantalla "Estado del sistema".
      * ``faltanRequeridas`` / ``faltanOpcionales``: booleanos para que la
        UI muestre banners y wizards.
      * ``revisarTodas()``, ``revisarUna(id)``: re-detección manual.
      * ``instalar(id)``: lanza instalación pip en QThread para deps PIP.
      * ``abrirInstruccionesSO(id)``: abre la URL de descarga para
        dependencias de sistema (VLC).
    """

    estadoCambiado = Signal()
    progresoInstalacion = Signal(str, str)       # dep_id, linea
    instalacionTerminada = Signal(str, bool, str, str)  # dep_id, ok, mensaje, detalle
    instalarTodoCambiado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reportes: list[dict] = []
        self._workers: dict[str, QObject] = {}
        self._hilos: dict[str, object] = {}
        # Cola de "Instalar todo": instala las dependencias auto-instalables
        # pendientes una por una (secuencial), respetando el filtrado por OS.
        self._cola_instalar_todo: list[str] = []
        self._instalar_todo_activo = False
        self.instalacionTerminada.connect(self._al_terminar_instalacion_de_cola)
        self._cargar(force_refresh=False)

    @Property("QVariantList", notify=estadoCambiado)
    def estado(self) -> list[dict]:
        return list(self._reportes)

    @Property(bool, notify=estadoCambiado)
    def faltanRequeridas(self) -> bool:
        return any(r.get("requerida") and r.get("estado") != "ok" for r in self._reportes)

    @Property(bool, notify=estadoCambiado)
    def faltanOpcionales(self) -> bool:
        return any((not r.get("requerida")) and r.get("estado") != "ok" for r in self._reportes)

    @Property(bool, constant=True)
    def deepAnalyticsDisponible(self) -> bool:
        """True si la plataforma soporta análisis profundo (deep).

        En Windows es False (``essentia-tensorflow`` sin wheel funcional);
        la UI usa esta propiedad —o la context property global homónima
        expuesta en ``main_ui.exponer_modelos``— para ocultar los controles
        deep. Constante durante la vida del proceso.
        """
        from infra.dependencias import deep_analytics_disponible
        return deep_analytics_disponible()

    @Property("QVariantMap", notify=estadoCambiado)
    def diagnostico(self) -> dict:
        try:
            from infra.instalador import diagnostico_entorno
            return diagnostico_entorno()
        except Exception:
            return {}

    @Slot()
    def revisarTodas(self) -> None:
        self._cargar(force_refresh=True)

    @Slot(str)
    def revisarUna(self, dep_id: str) -> None:
        try:
            from infra.dependencias import detectar_uno
            detectar_uno(dep_id)
        except Exception as exc:
            _log.warning("revisarUna(%s) fallo: %s", dep_id, exc)
        self._cargar(force_refresh=False)

    @Slot(str)
    def instalar(self, dep_id: str) -> None:
        """Despacha la instalación de ``dep_id`` en un QThread.

        Soporta dos tipos:
          * PIP: usa `_WorkerInstalarDep` para invocar `pip install --target`.
          * MODELOS: usa `_WorkerDescargarModelosEssentia` para bajar los
            `.pb`+`.json` del catálogo a la carpeta configurada.

        Para SISTEMA / BINARIO_PATH la UI debe llamar a
        ``abrirInstruccionesSO`` (los paquetes del SO requieren UAC/sudo
        y se manejan distinto en cada plataforma).
        """
        rep = next((r for r in self._reportes if r.get("id") == dep_id), None)
        if rep is None:
            _log.warning("instalar(%s): no existe en el catálogo", dep_id)
            return
        if dep_id in self._workers:
            _log.info("instalar(%s) ignorado: ya hay instalación en curso", dep_id)
            return

        tipo = rep.get("tipo")
        if tipo not in ("pip", "modelos"):
            _log.info("instalar(%s) ignorado: tipo %s no es auto-instalable", dep_id, tipo)
            return

        from PySide6.QtCore import QThread

        hilo = QThread(self)
        if tipo == "modelos":
            worker: QObject = _WorkerDescargarModelosEssentia()
        else:
            # Para torch en Windows + AMD/Intel/CPU, la rueda oficial está en
            # download.pytorch.org/whl/cpu. Para Linux/Mac la rueda CPU también
            # se sirve desde ese índice; lo añadimos defensivamente.
            extra_index = ""
            if dep_id in ("torch", "torchaudio"):
                extra_index = "https://download.pytorch.org/whl/cpu"
            worker = _WorkerInstalarDep(dep_id, rep.get("pip_specifier", ""),
                                        extra_index_url=extra_index)
        worker.moveToThread(hilo)

        def _al_progreso(d_id: str, linea: str) -> None:
            self.progresoInstalacion.emit(d_id, linea)

        def _al_terminar(d_id: str, ok: bool, mensaje: str, detalle: str) -> None:
            self.instalacionTerminada.emit(d_id, ok, mensaje, detalle)
            # Re-detectar la dependencia: si la instalación creó el
            # site-packages runtime y aplicar_runtime_pip_userdir lo agregó
            # a sys.path, la próxima verificación debería marcarla OK.
            try:
                from infra.dependencias import aplicar_runtime_pip_userdir, detectar_uno
                aplicar_runtime_pip_userdir()
                detectar_uno(d_id)
            except Exception:
                pass
            self._cargar(force_refresh=False)
            hilo.quit()

        worker.progreso.connect(_al_progreso)
        worker.completado.connect(_al_terminar)
        hilo.started.connect(worker.ejecutar)
        hilo.finished.connect(lambda d=dep_id: self._limpiar_hilo(d))

        self._workers[dep_id] = worker
        self._hilos[dep_id] = hilo
        hilo.start()

    @Property(bool, notify=instalarTodoCambiado)
    def instalandoTodo(self) -> bool:
        return self._instalar_todo_activo

    @Property(bool, notify=estadoCambiado)
    def hayInstalablesPendientes(self) -> bool:
        """True si queda alguna dependencia auto-instalable pendiente.

        Solo cuenta tipos `pip`/`modelos` (las de SO requieren instrucciones
        manuales). Como `_reportes` ya viene filtrado por plataforma, en
        Windows no contabiliza essentia/modelos deep: el botón "Instalar todo"
        es coherente con el OS sin lógica adicional aquí.
        """
        return any(
            r.get("estado") != "ok" and r.get("tipo") in ("pip", "modelos")
            for r in self._reportes
        )

    @Slot()
    def instalarTodo(self) -> None:
        """Instala secuencialmente todas las dependencias auto-instalables
        pendientes (pip/modelos), simulando pulsar "Instalar" en cada una.

        Las de tipo SO/binario se omiten (requieren UAC/sudo o descarga
        manual). El estado de cada tarjeta se actualiza solo al completar cada
        instalación (vía `instalacionTerminada` → `_cargar`).
        """
        if self._instalar_todo_activo:
            return
        pendientes = [
            r.get("id")
            for r in self._reportes
            if r.get("id") and r.get("estado") != "ok" and r.get("tipo") in ("pip", "modelos")
        ]
        if not pendientes:
            return
        self._cola_instalar_todo = list(pendientes)
        self._instalar_todo_activo = True
        self.instalarTodoCambiado.emit()
        self._instalar_siguiente_de_cola()

    def _instalar_siguiente_de_cola(self) -> None:
        # Saltar las que ya estén OK o no sean auto-instalables (pudieron
        # quedar resueltas por una instalación previa de la cola).
        while self._cola_instalar_todo:
            dep_id = self._cola_instalar_todo[0]
            rep = next((r for r in self._reportes if r.get("id") == dep_id), None)
            if rep is None or rep.get("estado") == "ok" or rep.get("tipo") not in ("pip", "modelos"):
                self._cola_instalar_todo.pop(0)
                continue
            self.instalar(dep_id)
            return
        # Cola vacía: terminamos.
        self._instalar_todo_activo = False
        self.instalarTodoCambiado.emit()

    def _al_terminar_instalacion_de_cola(self, dep_id: str, ok: bool, mensaje: str, detalle: str) -> None:
        if not self._instalar_todo_activo:
            return
        if self._cola_instalar_todo and self._cola_instalar_todo[0] == dep_id:
            self._cola_instalar_todo.pop(0)
            self._instalar_siguiente_de_cola()

    @Slot()
    def repararPython(self) -> None:
        """Intenta reparar el Python del sistema (Linux): instala
        python3-pip + python3-venv vía pkexec. Si no hay pkexec / sudo
        emite mensaje con instrucciones manuales.

        Para Windows/macOS no hacemos nada automático (los wheels de
        Python.org / Homebrew traen pip + venv por defecto); la UI
        muestra instrucciones según `diagnostico.python_*`.
        """
        from PySide6.QtCore import QThread

        if "__python__" in self._workers:
            return

        worker = _WorkerRepararPython()
        hilo = QThread(self)
        worker.moveToThread(hilo)

        def _al_progreso(linea: str) -> None:
            self.progresoInstalacion.emit("__python__", linea)

        def _al_terminar(ok: bool, mensaje: str, detalle: str) -> None:
            self.instalacionTerminada.emit("__python__", ok, mensaje, detalle)
            self._cargar(force_refresh=True)
            hilo.quit()

        worker.progreso.connect(_al_progreso)
        worker.completado.connect(_al_terminar)
        hilo.started.connect(worker.ejecutar)
        hilo.finished.connect(lambda: self._limpiar_hilo("__python__"))

        self._workers["__python__"] = worker
        self._hilos["__python__"] = hilo
        hilo.start()

    @Slot(str, result=bool)
    def abrirInstruccionesSO(self, dep_id: str) -> bool:
        """Abre el navegador con la URL de instalación recomendada para el
        SO actual. Devuelve True si abrió algo.
        """
        try:
            from infra.dependencias import construir_catalogo
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl as _QUrl
            dep = next((d for d in construir_catalogo() if d.id == dep_id), None)
            if dep is None:
                return False
            url = dep.urls_descarga.get(sys.platform) or next(iter(dep.urls_descarga.values()), "")
            if not url:
                return False
            QDesktopServices.openUrl(_QUrl(url))
            return True
        except Exception as exc:
            _log.warning("abrirInstruccionesSO(%s) fallo: %s", dep_id, exc)
            return False

    def _limpiar_hilo(self, dep_id: str) -> None:
        hilo = self._hilos.pop(dep_id, None)
        worker = self._workers.pop(dep_id, None)
        if hilo is not None:
            try:
                hilo.wait(2000)
                hilo.deleteLater()
            except Exception:
                pass
        if worker is not None:
            try:
                worker.deleteLater()
            except Exception:
                pass

    def _cargar(self, force_refresh: bool) -> None:
        try:
            from infra.dependencias import (
                IDS_DEPENDENCIAS_DEEP,
                deep_analytics_disponible,
                detectar,
            )
            reportes = detectar(force_refresh=force_refresh)
            datos = [r.a_dict() for r in reportes]
            # En plataformas sin análisis deep (Windows: essentia-tensorflow
            # no tiene wheel funcional) ocultamos esas dependencias del
            # catálogo visible. Así sus tarjetas desaparecen de "Estado del
            # sistema" y, al no quedar opcionales faltantes irresolubles,
            # `faltanOpcionales` puede ser False y el estado global "todo OK".
            # El catálogo Python NO se altera (CLI y tests quedan intactos).
            if not deep_analytics_disponible():
                datos = [d for d in datos if d.get("id") not in IDS_DEPENDENCIAS_DEEP]
            self._reportes = datos
        except Exception as exc:
            _log.warning("ModeloDependencias._cargar fallo: %s", exc)
            self._reportes = []
        self.estadoCambiado.emit()

    def cerrar(self) -> None:
        """Detiene los hilos pendientes durante el cierre de la app."""
        for dep_id in list(self._hilos.keys()):
            hilo = self._hilos.get(dep_id)
            try:
                if hilo is not None:
                    hilo.quit()
                    hilo.wait(3000)
            except Exception:
                pass
        self._hilos.clear()
        self._workers.clear()


# =============================================================================
# ModeloSincronizacion — bridge Qt del ecosistema movil (servidor local + QR)
# =============================================================================

class _WorkerSyncAccion(QObject):
    """Ejecuta una accion bloqueante del servidor (iniciar/detener) en un
    QThread para no congelar la UI mientras el site arranca (hasta ~10 s).
    """
    terminado = Signal(bool, str)  # (ok, mensaje_error)

    def __init__(self, accion, parent=None) -> None:
        super().__init__(parent)
        self._accion = accion

    @Slot()
    def ejecutar(self) -> None:
        try:
            self._accion()
            self.terminado.emit(True, "")
        except Exception as exc:
            self.terminado.emit(False, str(exc))


class _WorkerBackup(QObject):
    """Crea o restaura un backup en un QThread (I/O de disco pesado).

    `modo` es "crear" o "restaurar". Emite `terminado(ok, mensaje, ruta)`.
    """
    terminado = Signal(bool, str, str)

    def __init__(self, modo: str, ruta: str, parent=None) -> None:
        super().__init__(parent)
        self._modo = modo
        self._ruta = ruta

    @Slot()
    def ejecutar(self) -> None:
        try:
            from servicios import backup as svc_backup
            from pathlib import Path as _Path

            if self._modo == "crear":
                from datetime import datetime
                carpeta = _Path(self._ruta)
                nombre = "nb_sound_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".nbsound-backup"
                destino = carpeta / nombre
                res = svc_backup.crear_backup(destino)
                if res.get("ok"):
                    self.terminado.emit(True, "Backup creado correctamente.", res.get("ruta", ""))
                else:
                    self.terminado.emit(False, res.get("error", "No se pudo crear el backup."), "")
            else:
                from db.conexion import inicializar_db, ruta_db_actual

                destino_db = ruta_db_actual()
                if destino_db is None:
                    self.terminado.emit(False, "No hay base de datos activa para restaurar.", "")
                    return
                res = svc_backup.restaurar_backup(_Path(self._ruta), _Path(destino_db))
                if res.get("ok"):
                    # restaurar_backup cerro la conexion viva: reabrirla para que
                    # la app siga funcionando sin reiniciar.
                    inicializar_db(_Path(destino_db))
                    self.terminado.emit(True, "Backup restaurado. Tu biblioteca se actualizó.", str(destino_db))
                else:
                    self.terminado.emit(False, res.get("error", "No se pudo restaurar."), "")
        except Exception as exc:
            self.terminado.emit(False, str(exc), "")


class ModeloSincronizacion(QObject):
    """Bridge QML <-> servicios.servidor_sync (ecosistema movil).

    Gobierna el arranque/parada BAJO DEMANDA del servidor de sincronizacion,
    expone la lista de dispositivos emparejados, el QR de emparejamiento y el
    diagnostico de dependencias. Tambien actua de puente entre el reproductor
    (señales Qt) y el canal WS de control: empuja estado a los clientes y
    marshala los comandos entrantes al hilo de Qt.

    El servidor corre en su propio hilo/event loop; este modelo nunca comparte
    objetos Qt con ese hilo: solo intercambia dicts planos y callbacks.
    """

    activoCambiado        = Signal()
    dispositivosCambiado  = Signal()
    qrCambiado            = Signal()
    estadoCambiado        = Signal()
    mensajeCambiado       = Signal()
    dispositivoEmparejado = Signal("QVariant")
    backupProgreso        = Signal(str)
    backupTerminado       = Signal(bool, str, str)  # (ok, mensaje, ruta)
    backupConfigCambiada  = Signal()  # carpeta / frecuencia / última copia programada
    backupEnCursoCambiado = Signal()  # hay (o no) una copia en ejecución
    # Señal interna: marshala un comando recibido por WS (hilo servidor) al
    # hilo de Qt mediante conexion en cola.
    _comandoRecibido      = Signal(object)

    def __init__(self, modelo_reproductor=None, parent=None) -> None:
        super().__init__(parent)
        self._reproductor = modelo_reproductor
        self._servidor = None
        self._worker = None
        self._hilo = None
        self._ocupado = False
        self._mensaje = ""
        self._dispositivos: list[dict] = []
        self._qr_ruta = ""
        self._qr_contador = 0
        self._estado_snapshot: dict = self._construir_snapshot()
        self._backup_worker = None
        self._backup_hilo = None

        disp_ok, faltantes = self._dependencias()
        self._dep_disponibles = disp_ok
        self._dep_faltantes = faltantes

        # Puente de comandos: la señal se emite desde el hilo del servidor y se
        # entrega (en cola) a _aplicar_comando en el hilo de Qt.
        self._comandoRecibido.connect(self._aplicar_comando)
        # Tras cualquier backup exitoso refrescamos la UI de "última copia"
        # (backup_ultimo se escribe en el hilo worker; la señal se entrega en
        # cola al hilo de Qt, donde es seguro reemitir backupConfigCambiada).
        self.backupTerminado.connect(self._on_backup_terminado_interno)
        self._cablear_reproductor()
        self._recargar_dispositivos(emitir=False)

        # Reloj de las copias automáticas: corre solo mientras la app está
        # abierta. El vencimiento real se decide contra backup_ultimo en BD,
        # así que un chequeo periódico holgado basta para sesiones largas; el
        # caso común (app reabierta tras días) lo cubre el chequeo al arranque.
        self._timer_backup = QTimer(self)
        self._timer_backup.setInterval(6 * 60 * 60 * 1000)  # 6 horas
        self._timer_backup.timeout.connect(self.verificarBackupProgramado)
        self._timer_backup.start()

    # ── Dependencias ─────────────────────────────────────────────────────────

    @staticmethod
    def _dependencias() -> tuple[bool, list[str]]:
        try:
            from servicios.servidor_sync import dependencias_disponibles
            return dependencias_disponibles()
        except Exception:
            return False, ["aiohttp", "zeroconf", "qrcode"]

    @Property(bool, notify=estadoCambiado)
    def dependenciasDisponibles(self) -> bool:
        return self._dep_disponibles

    @Property("QVariantList", notify=estadoCambiado)
    def dependenciasFaltantes(self) -> list:
        return list(self._dep_faltantes)

    # ── Propiedades de estado ────────────────────────────────────────────────

    @Property(bool, notify=activoCambiado)
    def activo(self) -> bool:
        return bool(self._servidor and self._servidor.activo)

    @Property(bool, notify=estadoCambiado)
    def ocupado(self) -> bool:
        return self._ocupado

    @Property(str, notify=activoCambiado)
    def host(self) -> str:
        return (self._servidor.host if self._servidor and self._servidor.activo else "") or ""

    @Property(int, notify=activoCambiado)
    def puerto(self) -> int:
        return int(self._servidor.puerto) if self._servidor and self._servidor.activo and self._servidor.puerto else 0

    @Property(str, notify=activoCambiado)
    def direccion(self) -> str:
        if self._servidor and self._servidor.activo and self._servidor.puerto:
            return f"{self._servidor.host}:{self._servidor.puerto}"
        return ""

    @Property(int, notify=estadoCambiado)
    def clientesConectados(self) -> int:
        return self._servidor.numero_clientes_ws() if self._servidor and self._servidor.activo else 0

    @Property(str, notify=mensajeCambiado)
    def mensaje(self) -> str:
        return self._mensaje

    @Property("QVariantList", notify=dispositivosCambiado)
    def dispositivos(self) -> list:
        return list(self._dispositivos)

    @Property(str, notify=qrCambiado)
    def qrImagen(self) -> str:
        return self._qr_ruta

    @Property(str, notify=qrCambiado)
    def pairingToken(self) -> str:
        if self._servidor and self._servidor.activo:
            payload = self._servidor.payload_qr()
            return (payload or {}).get("token", "") if payload else ""
        return ""

    # ── Slots de control del servidor ────────────────────────────────────────

    @Slot()
    def encender(self) -> None:
        if self._ocupado or (self._servidor and self._servidor.activo):
            return
        disp_ok, faltantes = self._dependencias()
        self._dep_disponibles = disp_ok
        self._dep_faltantes = faltantes
        if not disp_ok:
            self._set_mensaje("Falta instalar aiohttp para activar la sincronización.")
            self.estadoCambiado.emit()
            return
        if self._servidor is None:
            self._servidor = self._crear_servidor()
        self._set_ocupado(True)
        self._set_mensaje("Encendiendo servidor…")
        self._lanzar_worker(self._servidor.iniciar, self._on_encendido)

    @Slot()
    def apagar(self) -> None:
        if self._ocupado or not (self._servidor and self._servidor.activo):
            return
        self._set_ocupado(True)
        self._set_mensaje("Apagando servidor…")
        self._lanzar_worker(self._servidor.detener, self._on_apagado)

    @Slot()
    def alternar(self) -> None:
        if self._servidor and self._servidor.activo:
            self.apagar()
        else:
            self.encender()

    @Slot()
    def regenerarQr(self) -> None:
        if not (self._servidor and self._servidor.activo):
            return
        self._servidor.regenerar_token()
        self._refrescar_qr()
        self._set_mensaje("Código QR regenerado.")

    @Slot(int)
    def revocar(self, dispositivo_id: int) -> None:
        try:
            from servicios import sync_repositorio
            sync_repositorio.revocar_dispositivo(int(dispositivo_id))
        except Exception as exc:
            _log.warning("revocar(%s) falló: %s", dispositivo_id, exc)
        self._recargar_dispositivos()

    @Slot()
    def recargarDispositivos(self) -> None:
        self._recargar_dispositivos()

    @Slot(int, str)
    def guardarSeleccion(self, dispositivo_id: int, seleccion_json: str) -> None:
        try:
            from servicios import sync_repositorio
            seleccion = json.loads(seleccion_json or "{}")
            sync_repositorio.guardar_seleccion(int(dispositivo_id), seleccion)
        except Exception as exc:
            _log.warning("guardarSeleccion(%s) falló: %s", dispositivo_id, exc)
        self._recargar_dispositivos()

    # ── Worker QThread para iniciar/detener ──────────────────────────────────

    def _lanzar_worker(self, accion, on_done) -> None:
        from PySide6.QtCore import QThread

        hilo = QThread(self)
        worker = _WorkerSyncAccion(accion)
        worker.moveToThread(hilo)

        def _terminado(ok: bool, error: str) -> None:
            try:
                on_done(ok, error)
            finally:
                hilo.quit()

        worker.terminado.connect(_terminado)
        hilo.started.connect(worker.ejecutar)
        hilo.finished.connect(self._limpiar_worker)
        self._worker = worker
        self._hilo = hilo
        hilo.start()

    def _limpiar_worker(self) -> None:
        hilo = self._hilo
        worker = self._worker
        self._hilo = None
        self._worker = None
        if hilo is not None:
            try:
                hilo.wait(2000)
                hilo.deleteLater()
            except Exception:
                pass
        if worker is not None:
            try:
                worker.deleteLater()
            except Exception:
                pass

    def _on_encendido(self, ok: bool, error: str) -> None:
        self._set_ocupado(False)
        if not ok:
            self._set_mensaje(f"No se pudo encender: {error}")
        else:
            self._set_mensaje(f"Servidor activo en {self.direccion}")
            self._refrescar_qr()
            self._recargar_dispositivos()
        self.activoCambiado.emit()
        self.estadoCambiado.emit()

    def _on_apagado(self, ok: bool, error: str) -> None:
        self._set_ocupado(False)
        self._set_mensaje("Servidor apagado." if ok else f"Error al apagar: {error}")
        self._qr_ruta = ""
        self.qrCambiado.emit()
        self.activoCambiado.emit()
        self.estadoCambiado.emit()

    # ── Construccion del servidor + callbacks ────────────────────────────────

    def _crear_servidor(self):
        from servicios.servidor_sync import ServidorSync

        return ServidorSync(
            comando_control=self._comando_control_thread_safe,
            estado_provider=lambda: self._estado_snapshot,
            on_dispositivo_emparejado=self._on_dispositivo_emparejado,
            nombre_servicio="NB Sound",
        )

    def _comando_control_thread_safe(self, mensaje: dict) -> dict:
        """Llamado desde el hilo del servidor. Marshala al hilo de Qt vía señal
        en cola y devuelve un ack inmediato (fire-and-forget)."""
        try:
            self._comandoRecibido.emit(mensaje)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "encolado": True}

    def _on_dispositivo_emparejado(self, dispositivo: dict) -> None:
        """Callback del hilo del servidor: refresca lista + QR en el hilo de Qt."""
        # Emitir señales es thread-safe; los slots conectados corren en Qt.
        try:
            self.dispositivoEmparejado.emit(dispositivo)
        except Exception:
            pass
        # Reusar la señal de comando (cola) para ejecutar el refresco en Qt.
        self._comandoRecibido.emit({"comando": "__refrescar_sync__"})

    # ── Puente reproductor -> WS ─────────────────────────────────────────────

    def _cablear_reproductor(self) -> None:
        rep = self._reproductor
        if rep is None:
            return
        # Señales del reproductor que disparan un push de estado por WS.
        for nombre in (
            "estadoCambiado", "pista_activaCambiada", "progresoCambiado",
            "colaCambiada", "volumenCambiado", "modoCambiado", "karaokeCambiado",
        ):
            señal = getattr(rep, nombre, None)
            if señal is not None:
                try:
                    señal.connect(self._on_reproductor_cambio)
                except Exception:
                    pass

    @Slot()
    def _on_reproductor_cambio(self) -> None:
        self._estado_snapshot = self._construir_snapshot()
        if self._servidor and self._servidor.activo:
            self._servidor.difundir_estado(self._estado_snapshot)

    def _construir_snapshot(self) -> dict:
        """Estado del reproductor en el esquema PLANO que espera el móvil
        (ver nb_sound_mobile/docs/remote-control.md): pista{...} + campos."""
        rep = self._reproductor
        if rep is None:
            return {
                "reproduciendo": False, "pista": None, "posicion_seg": 0.0,
                "volumen": 100, "modo_repeticion": "ninguno", "aleatorio": False,
                "karaoke_activo": False, "indice_cola": -1,
            }

        def _g(attr, default):
            try:
                return getattr(rep, attr)
            except Exception:
                return default

        pista_raw = _g("pista_activa", {}) or {}
        pista = None
        if isinstance(pista_raw, dict) and (pista_raw.get("id") or pista_raw.get("titulo")):
            album_id = pista_raw.get("album_id")
            pista = {
                "id": pista_raw.get("id"),
                "titulo": str(pista_raw.get("titulo") or _g("titulo_activo", "") or ""),
                "artista": str(pista_raw.get("artista_nombre") or _g("artista_activo", "") or ""),
                "album": str(pista_raw.get("album_titulo") or _g("album_activo", "") or ""),
                "duracion_seg": float(_g("duracion_seg", 0.0) or 0.0),
                "cover_url": f"/api/v1/asset/cover/{album_id}" if album_id else None,
            }
        return {
            "reproduciendo": bool(_g("reproduciendo", False)),
            "pista": pista,
            "posicion_seg": float(_g("posicion_seg", 0.0) or 0.0),
            "volumen": int(_g("volumen", 100) or 100),
            "modo_repeticion": str(_g("modo_repeticion", "ninguno") or "ninguno"),
            "aleatorio": bool(_g("aleatorio", False)),
            "karaoke_activo": bool(_g("karaoke_activo", False)),
            "indice_cola": int(_g("indice_cola", -1) if _g("indice_cola", -1) is not None else -1),
        }

    @Slot(object)
    def _aplicar_comando(self, mensaje) -> None:
        """Corre en el hilo de Qt. Traduce un comando WS a una acción del
        reproductor. Acepta el esquema canónico del móvil ({accion, ...}) y
        alias legacy. Acciones: play_pause, next, prev, seek (posicion_seg),
        set_volume (volumen), play_index (indice), repeat (modo),
        shuffle (activo), queue (consulta)."""
        if not isinstance(mensaje, dict):
            return
        accion = str(mensaje.get("accion") or mensaje.get("comando") or "")
        if accion == "__refrescar_sync__":
            self._recargar_dispositivos()
            self._refrescar_qr()
            return
        rep = self._reproductor
        if rep is None:
            return
        try:
            if accion in ("play_pause", "play", "pause", "toggle"):
                rep.pausar_reanudar()
            elif accion in ("next", "siguiente"):
                rep.siguiente()
            elif accion in ("prev", "previous", "anterior"):
                rep.anterior()
            elif accion in ("stop", "detener"):
                rep.detener()
            elif accion == "seek":
                rep.buscar_posicion(float(mensaje.get("posicion_seg", 0) or 0))
            elif accion in ("set_volume", "volume", "volumen"):
                valor = mensaje.get("volumen", mensaje.get("valor", 100))
                rep.set_volumen(int(valor if valor is not None else 100))
            elif accion in ("play_index", "play_indice"):
                rep.reproducir_indice_cola(int(mensaje.get("indice", 0) or 0))
            elif accion in ("repeat", "repeticion"):
                rep.set_modo_repeticion(str(mensaje.get("modo", "ninguno")))
            elif accion in ("shuffle", "aleatorio"):
                rep.set_aleatorio(bool(mensaje.get("activo", False)))
            elif accion in ("queue", "cola"):
                self._difundir_cola()
            else:
                _log.debug("Acción WS desconocida: %s", accion)
        except Exception as exc:
            _log.debug("No se pudo aplicar acción WS %s: %s", accion, exc)

    def _difundir_cola(self) -> None:
        """Publica la cola actual del reproductor como frame WS (consulta queue)."""
        rep = self._reproductor
        srv = self._servidor
        if rep is None or srv is None or not srv.activo:
            return
        items = []
        try:
            cola = getattr(rep, "cola", None)
            crudos = cola.snapshot() if cola is not None and hasattr(cola, "snapshot") else []
            for it in crudos:
                items.append({
                    "id": it.get("id"),
                    "titulo": it.get("titulo"),
                    "artista": it.get("artista_nombre") or it.get("artista"),
                    "album": it.get("album_titulo") or it.get("album"),
                    "duracion_seg": it.get("duracion_seg"),
                })
        except Exception as exc:
            _log.debug("No se pudo construir la cola para WS: %s", exc)
        indice = -1
        try:
            indice = int(getattr(rep, "indice_cola", -1) or -1)
        except Exception:
            pass
        srv.difundir_frame({"tipo": "cola", "items": items, "indice": indice})

    # ── Dispositivos y QR ────────────────────────────────────────────────────

    def _recargar_dispositivos(self, emitir: bool = True) -> None:
        try:
            from servicios import sync_repositorio
            self._dispositivos = sync_repositorio.listar_dispositivos(incluir_revocados=False)
        except Exception as exc:
            _log.debug("No se pudieron listar dispositivos: %s", exc)
            self._dispositivos = []
        if emitir:
            self.dispositivosCambiado.emit()
            self.estadoCambiado.emit()

    def _refrescar_qr(self) -> None:
        self._qr_ruta = ""
        if not (self._servidor and self._servidor.activo):
            self.qrCambiado.emit()
            return
        try:
            from servicios.servidor_sync import generar_qr_png

            payload = self._servidor.payload_qr()
            if payload:
                png = generar_qr_png(json.dumps(payload, ensure_ascii=False))
                if png:
                    ruta = self._escribir_qr_temporal(png)
                    if ruta:
                        self._qr_ruta = QUrl.fromLocalFile(str(ruta)).toString()
        except Exception as exc:
            _log.debug("No se pudo generar el QR: %s", exc)
        self.qrCambiado.emit()

    def _escribir_qr_temporal(self, png: bytes):
        try:
            base = None
            try:
                from config import settings as _s
                if getattr(_s, "DEFAULT_TEMP_DIR", None):
                    base = Path(_s.DEFAULT_TEMP_DIR)
            except Exception:
                base = None
            if base is None:
                base = Path(tempfile.gettempdir())
            base.mkdir(parents=True, exist_ok=True)
            self._qr_contador += 1
            ruta = base / f"nb_sound_qr_{self._qr_contador}.png"
            ruta.write_bytes(png)
            # Limpiar el anterior para no acumular archivos temporales.
            previo = base / f"nb_sound_qr_{self._qr_contador - 1}.png"
            if previo.exists():
                try:
                    previo.unlink()
                except OSError:
                    pass
            return ruta
        except Exception as exc:
            _log.debug("No se pudo escribir QR temporal: %s", exc)
            return None

    # ── Helpers de estado ────────────────────────────────────────────────────

    def _set_ocupado(self, valor: bool) -> None:
        if self._ocupado != valor:
            self._ocupado = valor
            self.estadoCambiado.emit()

    def _set_mensaje(self, texto: str) -> None:
        self._mensaje = texto
        self.mensajeCambiado.emit()

    # ── Copia de seguridad programada (config_ui) ────────────────────────────

    @Property(str, notify=backupConfigCambiada)
    def backupCarpeta(self) -> str:
        """Carpeta destino de las copias automáticas (ruta local, no URL)."""
        try:
            from db.conexion import obtener_config
            return obtener_config("backup_carpeta", "") or ""
        except Exception:
            return ""

    @Property(int, notify=backupConfigCambiada)
    def backupFrecuenciaDias(self) -> int:
        """Frecuencia en días de la copia automática; 0 = desactivada."""
        try:
            from db.conexion import obtener_config
            return int(obtener_config("backup_frecuencia_dias", "0") or "0")
        except Exception:
            return 0

    @Property(str, notify=backupConfigCambiada)
    def backupUltimo(self) -> str:
        """Marca ISO de la última copia (manual o automática). Vacío si nunca."""
        try:
            from db.conexion import obtener_config
            return obtener_config("backup_ultimo", "") or ""
        except Exception:
            return ""

    @Property(bool, notify=backupEnCursoCambiado)
    def backupEnCurso(self) -> bool:
        """True mientras se ejecuta una copia (manual o automática). La UI lo
        usa para deshabilitar el botón de crear copia y evitar solapamientos."""
        return self._backup_hilo is not None

    @Slot(str)
    def setBackupCarpeta(self, carpeta_url: str) -> None:
        ruta = self._desde_url(carpeta_url)
        try:
            from db.conexion import guardar_config
            guardar_config("backup_carpeta", ruta)
        except Exception as exc:
            _log.warning("No se pudo guardar backup_carpeta: %s", exc)
            return
        self.backupConfigCambiada.emit()
        # Si al fijar la carpeta ya había una frecuencia activa vencida, crea
        # la primera copia de inmediato (set & forget).
        self.verificarBackupProgramado()

    @Slot(int)
    def setBackupFrecuenciaDias(self, dias: int) -> None:
        try:
            valor = max(0, int(dias))
        except (TypeError, ValueError):
            valor = 0
        try:
            from db.conexion import guardar_config
            guardar_config("backup_frecuencia_dias", str(valor))
        except Exception as exc:
            _log.warning("No se pudo guardar backup_frecuencia_dias: %s", exc)
            return
        self.backupConfigCambiada.emit()
        # Al activar una frecuencia (y si ya hay carpeta) respaldamos enseguida
        # en vez de esperar el primer periodo completo.
        self.verificarBackupProgramado()

    @Slot()
    def verificarBackupProgramado(self) -> None:
        """Crea una copia automática en background si el plazo venció.

        Idempotente y barato: lee la config, decide con la función pura
        `backup_programado_vencido` y solo entonces lanza el worker. No hace
        nada si las copias están desactivadas, falta carpeta, ya hay un backup
        en curso o la carpeta dejó de existir.
        """
        if self._backup_hilo is not None:
            return  # no encadenar copias; el reloj reintentará luego
        try:
            from db.conexion import obtener_config
            from servicios.backup import backup_programado_vencido
        except Exception as exc:
            _log.debug("verificarBackupProgramado: import falló: %s", exc)
            return
        try:
            frecuencia = int(obtener_config("backup_frecuencia_dias", "0") or "0")
        except (TypeError, ValueError):
            frecuencia = 0
        carpeta = (obtener_config("backup_carpeta", "") or "").strip()
        if frecuencia <= 0 or not carpeta:
            return
        ultimo = obtener_config("backup_ultimo", "")
        if not backup_programado_vencido(frecuencia, ultimo):
            return
        if not Path(carpeta).is_dir():
            _log.warning(
                "Backup programado: la carpeta '%s' no existe; se omite.", carpeta
            )
            return
        _log.info(
            "Backup programado vencido (cada %d día[s]); creando copia en %s",
            frecuencia, carpeta,
        )
        self._lanzar_backup("crear", carpeta)

    @Slot(bool, str, str)
    def _on_backup_terminado_interno(self, ok: bool, _mensaje: str, _ruta: str) -> None:
        # backup_ultimo ya se persistió en el worker; refrescamos los bindings
        # de la UI ("última copia") en el hilo de Qt.
        if ok:
            self.backupConfigCambiada.emit()

    # ── Backup / restauracion (worker QThread) ───────────────────────────────

    @Slot(str)
    def crearBackup(self, carpeta_destino: str) -> None:
        self._lanzar_backup("crear", self._desde_url(carpeta_destino))

    @Slot(str)
    def restaurarBackup(self, ruta: str) -> None:
        self._lanzar_backup("restaurar", self._desde_url(ruta))

    @staticmethod
    def _desde_url(valor: str) -> str:
        v = str(valor or "")
        if v.startswith("file://"):
            try:
                return QUrl(v).toLocalFile()
            except Exception:
                return v[7:]
        return v

    def _lanzar_backup(self, modo: str, ruta: str) -> None:
        if self._backup_hilo is not None:
            self.backupTerminado.emit(False, "Ya hay una operación de backup en curso.", "")
            return
        from PySide6.QtCore import QThread

        hilo = QThread(self)
        worker = _WorkerBackup(modo, ruta)
        worker.moveToThread(hilo)

        def _terminado(ok: bool, mensaje: str, ruta_res: str) -> None:
            # Registrar la fecha de la copia reinicia el reloj de las copias
            # automáticas (tanto si fue manual como programada): "última vez
            # que se respaldó la biblioteca".
            if ok and modo == "crear":
                try:
                    from db.conexion import guardar_config
                    from servicios.backup import ahora_utc_iso
                    guardar_config("backup_ultimo", ahora_utc_iso())
                except Exception as exc:
                    _log.debug("No se pudo registrar backup_ultimo: %s", exc)
            self.backupTerminado.emit(ok, mensaje, ruta_res)
            hilo.quit()

        worker.terminado.connect(_terminado)
        hilo.started.connect(worker.ejecutar)
        hilo.finished.connect(self._limpiar_backup)
        self._backup_worker = worker
        self._backup_hilo = hilo
        self.backupEnCursoCambiado.emit()
        hilo.start()

    def _limpiar_backup(self) -> None:
        hilo = self._backup_hilo
        worker = self._backup_worker
        self._backup_hilo = None
        self._backup_worker = None
        self.backupEnCursoCambiado.emit()
        if hilo is not None:
            try:
                hilo.wait(2000)
                hilo.deleteLater()
            except Exception:
                pass
        if worker is not None:
            try:
                worker.deleteLater()
            except Exception:
                pass

    # ── Cierre ordenado (lo invoca main_ui._ORDEN_CIERRE) ────────────────────

    def cerrar(self) -> None:
        try:
            if self._timer_backup is not None:
                self._timer_backup.stop()
        except Exception:
            pass
        try:
            if self._servidor is not None:
                self._servidor.detener()
        except Exception as exc:
            _log.debug("Cierre del servidor de sync falló: %s", exc)
        for hilo in (self._hilo, self._backup_hilo):
            if hilo is not None:
                try:
                    hilo.quit()
                    hilo.wait(3000)
                except Exception:
                    pass
        self._hilo = None
        self._worker = None
        self._backup_hilo = None
        self._backup_worker = None
