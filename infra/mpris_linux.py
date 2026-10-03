# =============================================================================
# infra/mpris_linux.py
#
# Puente entre el servicio Reproductor y el bus de escritorio D-Bus (MPRIS).
# Esto permite que los entornos de escritorio en Linux (KDE, GNOME) y
# herramientas como KDE Connect puedan leer metadatos y controlar NB Sound.
# =============================================================================

import sys
import logging
from typing import Optional

from servicios.reproductor import Reproductor, EstadoReproductor, PistaActiva

logger = logging.getLogger(__name__)

# Importacion condicional para no romper Windows/macOS ni fallar si no hay DBus
try:
    from PySide6.QtCore import QObject, Slot, Property, ClassInfo
    from PySide6.QtDBus import QDBusConnection, QDBusAbstractAdaptor, QDBusMessage
    DBUS_DISPONIBLE = True
except Exception as e:
    logger.error(f"Error importando dependencias de D-Bus: {e}", exc_info=True)
    DBUS_DISPONIBLE = False

_fn_metatype = None
_fn_variant_ctor = None
_fn_append_variant = None
_helpers_inicializados = False


def _init_int64_helpers():
    global _fn_metatype, _fn_variant_ctor, _fn_append_variant, _helpers_inicializados
    if _helpers_inicializados:
        return
    _helpers_inicializados = True
    try:
        import ctypes
        from pathlib import Path
        from PySide6 import QtCore, QtDBus

        rutas_core = [
            Path(QtCore.__file__).parent / "Qt" / "lib" / "libQt6Core.so.6",
            Path(QtCore.__file__).parent / "Qt" / "lib" / "libQt6Core.so",
            Path(sys.executable).parent / "_internal" / "libQt6Core.so.6",
            Path(sys.executable).parent / "_internal" / "PySide6" / "Qt" / "lib" / "libQt6Core.so.6",
        ]
        rutas_dbus = [
            Path(QtDBus.__file__).parent / "Qt" / "lib" / "libQt6DBus.so.6",
            Path(QtDBus.__file__).parent / "Qt" / "lib" / "libQt6DBus.so",
            Path(sys.executable).parent / "_internal" / "libQt6DBus.so.6",
            Path(sys.executable).parent / "_internal" / "PySide6" / "Qt" / "lib" / "libQt6DBus.so.6",
        ]
        if hasattr(sys, "_MEIPASS"):
            rutas_core.append(Path(sys._MEIPASS) / "libQt6Core.so.6")
            rutas_core.append(Path(sys._MEIPASS) / "PySide6" / "Qt" / "lib" / "libQt6Core.so.6")
            rutas_dbus.append(Path(sys._MEIPASS) / "libQt6DBus.so.6")
            rutas_dbus.append(Path(sys._MEIPASS) / "PySide6" / "Qt" / "lib" / "libQt6DBus.so.6")

        core_lib = None
        for r in rutas_core:
            if r.exists():
                core_lib = ctypes.CDLL(str(r))
                break

        dbus_lib = None
        for r in rutas_dbus:
            if r.exists():
                dbus_lib = ctypes.CDLL(str(r))
                break

        if core_lib and dbus_lib:
            _fn_metatype = core_lib._ZN9QMetaTypeC1Ei
            _fn_metatype.argtypes = [ctypes.c_void_p, ctypes.c_int]
            _fn_metatype.restype = None

            _fn_variant_ctor = core_lib._ZN8QVariantC1E9QMetaTypePKv
            _fn_variant_ctor.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p]
            _fn_variant_ctor.restype = None

            _fn_append_variant = dbus_lib._ZN13QDBusArgument13appendVariantERK8QVariant
            _fn_append_variant.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            _fn_append_variant.restype = None
    except Exception as e:
        logger.debug(f"No se pudieron inicializar helpers nativos de int64 para D-Bus: {e}")


def _make_int64_dbus_arg(val: int):
    """Convierte un entero a QDBusArgument con firma estricta 'x' (int64).

    PySide6 serializa números enteros de Python en QVariant como 'i' (int32) si caben en
    32 bits (< 2^31). La especificación MPRIS exige que 'mpris:length' sea 'x' (int64).
    """
    try:
        _init_int64_helpers()
        if _fn_metatype and _fn_variant_ctor and _fn_append_variant:
            import ctypes
            import shiboken6
            from PySide6.QtDBus import QDBusArgument
            var_buf = (ctypes.c_uint8 * 32)()
            mt = ctypes.c_uint64(0)
            _fn_metatype(ctypes.byref(mt), 4)  # 4 = QMetaType::Type::LongLong
            v = ctypes.c_int64(int(val))
            _fn_variant_ctor(ctypes.byref(var_buf), mt.value, ctypes.byref(v))
            arg = QDBusArgument()
            arg_ptr = shiboken6.getCppPointer(arg)[0]
            _fn_append_variant(arg_ptr, ctypes.byref(var_buf))
            return arg
    except Exception as e:
        logger.debug(f"Fallback int64 D-Bus argument: {e}")
    return int(val)


class MprisRootAdaptor:
    pass

class MprisPlayerAdaptor:
    pass

class MprisBridge:
    def __init__(self, reproductor: Reproductor):
        pass

if DBUS_DISPONIBLE:
    @ClassInfo({"D-Bus Interface": "org.mpris.MediaPlayer2"})
    class MprisRootAdaptor(QDBusAbstractAdaptor):
        
        def __init__(self, parent: QObject, reproductor: Reproductor):
            super().__init__(parent)
            self.reproductor = reproductor
            
        @Slot()
        def Quit(self):
            logger.info("Cierre solicitado via MPRIS")
            self.reproductor.detener()
            
        @Slot()
        def Raise(self):
            pass
            
        @Property(bool)
        def CanQuit(self):
            return False
            
        @Property(bool)
        def CanRaise(self):
            return False
            
        @Property(bool)
        def HasTrackList(self):
            return False
            
        @Property(str)
        def Identity(self):
            return "NB Sound"
            
        @Property(str)
        def DesktopEntry(self):
            return "nb-sound"  # Debe coincidir con nb-sound.desktop


    @ClassInfo({"D-Bus Interface": "org.mpris.MediaPlayer2.Player"})
    class MprisPlayerAdaptor(QDBusAbstractAdaptor):
        
        def __init__(self, parent: QObject, reproductor: Reproductor):
            super().__init__(parent)
            self.reproductor = reproductor
            
        @Slot()
        def Next(self):
            self.reproductor.siguiente()
            
        @Slot()
        def Previous(self):
            self.reproductor.anterior()
            
        @Slot()
        def Pause(self):
            if self.reproductor.estado == EstadoReproductor.REPRODUCIENDO:
                self.reproductor.pausar_reanudar()
                
        @Slot()
        def PlayPause(self):
            self.reproductor.pausar_reanudar()
            
        @Slot()
        def Stop(self):
            self.reproductor.detener()
            
        @Slot()
        def Play(self):
            if self.reproductor.estado != EstadoReproductor.REPRODUCIENDO:
                self.reproductor.pausar_reanudar()
                
        @Property(str)
        def PlaybackStatus(self):
            st = self.reproductor.estado
            if st == EstadoReproductor.REPRODUCIENDO:
                return "Playing"
            elif st == EstadoReproductor.PAUSADO:
                return "Paused"
            else:
                return "Stopped"
                
        @Property(str)
        def LoopStatus(self):
            rep = self.reproductor.modo_repeticion
            if rep == "uno": return "Track"
            if rep == "todo": return "Playlist"
            return "None"
            
        @LoopStatus.setter
        def LoopStatus(self, value: str):
            if value == "Track": self.reproductor.set_modo_repeticion("uno")
            elif value == "Playlist": self.reproductor.set_modo_repeticion("todo")
            else: self.reproductor.set_modo_repeticion("ninguno")
            
        @Property(float)
        def Rate(self):
            return 1.0
            
        @Property(bool)
        def Shuffle(self):
            return self.reproductor.es_aleatorio
            
        @Shuffle.setter
        def Shuffle(self, value: bool):
            self.reproductor.set_aleatorio(value)
            
        @Property('QVariantMap')
        def Metadata(self):
            pista = self.reproductor.pista_activa
            if not pista:
                return {}
                
            from PySide6.QtDBus import QDBusObjectPath
            
            # Limpiar el id para que sea un path valido (no guiones, etc.)
            clean_id = str(pista.id).replace('-', '_').replace(' ', '_')
            
            meta = {
                "mpris:trackid": QDBusObjectPath(f"/org/mpris/MediaPlayer2/Track/{clean_id}"),
                "xesam:title": pista.titulo or "Desconocido",
            }
            if pista.artista:
                meta["xesam:artist"] = [pista.artista]
            if pista.album:
                meta["xesam:album"] = pista.album
            if pista.duracion_seg > 0:
                meta["mpris:length"] = _make_int64_dbus_arg(int(pista.duracion_seg * 1000000))
                
            ruta_portada = pista.portada_hd_ruta or pista.portada_ruta
            if ruta_portada:
                import urllib.parse
                meta["mpris:artUrl"] = f"file://{urllib.parse.quote(ruta_portada)}"
                
            return meta
            
        @Property(float)
        def Volume(self):
            return self.reproductor.volumen / 100.0
            
        @Volume.setter
        def Volume(self, value: float):
            self.reproductor.set_volumen(int(value * 100))
            
        @Property('qint64')
        def Position(self):
            return int(self.reproductor.posicion_seg * 1000000)
            
        @Property(float)
        def MinimumRate(self): return 1.0
        
        @Property(float)
        def MaximumRate(self): return 1.0
        
        @Property(bool)
        def CanGoNext(self): return True
        
        @Property(bool)
        def CanGoPrevious(self): return True
        
        @Property(bool)
        def CanPlay(self): return True
        
        @Property(bool)
        def CanPause(self): return True
        
        @Property(bool)
        def CanSeek(self): return False # Simplificado por ahora
        
        @Property(bool)
        def CanControl(self): return True


    class MprisBridge(QObject):
        """
        Instancia principal que registra el servicio en D-Bus y escucha
        los eventos del Reproductor.
        """
        def __init__(self, reproductor: Reproductor):
            super().__init__()
            self.reproductor = reproductor
            
            if not sys.platform.startswith("linux"):
                logger.debug("MPRIS solo soportado en Linux. Se ignora.")
                return
                
            self.bus = QDBusConnection.sessionBus()
            if not self.bus.isConnected():
                logger.warning("MPRIS: No conectado a D-Bus de sesion.")
                return
                
            self.root_adaptor = MprisRootAdaptor(self, reproductor)
            self.player_adaptor = MprisPlayerAdaptor(self, reproductor)
            
            nombre_servicio = "org.mpris.MediaPlayer2.nbsound"
            
            # Registrar
            if not self.bus.registerService(nombre_servicio):
                logger.warning(f"MPRIS: No se pudo registrar {nombre_servicio}. Tal vez ya este en uso?")
                return
                
            if not self.bus.registerObject("/org/mpris/MediaPlayer2", self, QDBusConnection.RegisterOption.ExportAdaptors):
                logger.warning("MPRIS: No se pudo registrar el objeto base.")
                return
                
            logger.info("MPRIS: Integracion con escritorio registrada correctamente.")
            
            # Escuchar eventos de reproduccion
            self.reproductor.on_estado(self._al_cambiar_estado)
            self.reproductor.on_cola(self._al_cambiar_cola)

        def _emitir_cambios(self, changed_props: dict) -> None:
            """Emite PropertiesChanged con la firma exacta 'sa{sv}as'.

            IMPORTANTE: una lista Python vacia se serializa como 'av', lo que
            produce la firma 'sa{sv}av'. Los clientes Qt/KDE (Plasma, KDE
            Connect) se suscriben con 'sa{sv}as' y descartan la senal en
            silencio, dejando todo como "Desconocido". Por eso se construye un
            array de strings tipado explicitamente.
            """
            try:
                from PySide6.QtCore import QMetaType
                from PySide6.QtDBus import QDBusArgument
                invalidadas = QDBusArgument()
                invalidadas.beginArray(QMetaType(QMetaType.Type.QString).id())
                invalidadas.endArray()

                msg = QDBusMessage.createSignal(
                    "/org/mpris/MediaPlayer2",
                    "org.freedesktop.DBus.Properties",
                    "PropertiesChanged"
                )
                msg.setArguments(["org.mpris.MediaPlayer2.Player", changed_props, invalidadas])
                self.bus.send(msg)
            except Exception as e:
                logger.error(f"MPRIS: fallo emitiendo PropertiesChanged: {e}", exc_info=True)

        def _al_cambiar_estado(self, estado, pista):
            self._emitir_cambios({
                "PlaybackStatus": self.player_adaptor.PlaybackStatus,
                "Metadata": self.player_adaptor.Metadata,
            })

        def _al_cambiar_cola(self, *args):
            self._emitir_cambios({
                "Shuffle": self.player_adaptor.Shuffle,
                "LoopStatus": self.player_adaptor.LoopStatus,
            })

def inicializar_mpris(reproductor: Reproductor) -> Optional[object]:
    """Factory seguro que retorna MprisBridge solo si esta soportado."""
    if sys.platform.startswith("linux") and DBUS_DISPONIBLE:
        try:
            return MprisBridge(reproductor)
        except Exception as e:
            logger.error(f"Fallo al inicializar MPRIS: {e}")
    return None
