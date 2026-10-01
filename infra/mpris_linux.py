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
            return "nb_sound"


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
            if self.reproductor.estado() == EstadoReproductor.REPRODUCIENDO:
                self.reproductor.pausar_reanudar()
                
        @Slot()
        def PlayPause(self):
            self.reproductor.pausar_reanudar()
            
        @Slot()
        def Stop(self):
            self.reproductor.detener()
            
        @Slot()
        def Play(self):
            if self.reproductor.estado() != EstadoReproductor.REPRODUCIENDO:
                self.reproductor.pausar_reanudar()
                
        @Property(str)
        def PlaybackStatus(self):
            st = self.reproductor.estado()
            if st == EstadoReproductor.REPRODUCIENDO:
                return "Playing"
            elif st == EstadoReproductor.PAUSADO:
                return "Paused"
            else:
                return "Stopped"
                
        @Property(str)
        def LoopStatus(self):
            # Opcional
            return "None"
            
        @Property(float)
        def Rate(self):
            return 1.0
            
        @Property(bool)
        def Shuffle(self):
            return self.reproductor.es_aleatorio()
            
        @Property('QVariantMap')
        def Metadata(self):
            pista = self.reproductor.pista_activa()
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
                meta["mpris:length"] = int(pista.duracion_seg * 1000000)
                
            ruta_portada = pista.portada_hd_ruta or pista.portada_ruta
            if ruta_portada:
                meta["mpris:artUrl"] = f"file://{ruta_portada}"
                
            return meta
            
        @Property(float)
        def Volume(self):
            return self.reproductor.volumen() / 100.0
            
        @Volume.setter
        def Volume(self, value: float):
            self.reproductor.set_volumen(int(value * 100))
            
        @Property(int)
        def Position(self):
            return int(self.reproductor.posicion_seg() * 1000000)
            
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
            
        def _al_cambiar_estado(self, estado: EstadoReproductor, pista: Optional[PistaActiva]):
            """
            Se llama cuando el Reproductor cambia de pista o hace pausa/play.
            Notificamos a D-Bus que las propiedades han cambiado.
            """
            msg = QDBusMessage.createSignal(
                "/org/mpris/MediaPlayer2",
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged"
            )
            
            # Solo enviamos lo que cambio
            changed_props = {
                "PlaybackStatus": self.player_adaptor.PlaybackStatus,
                "Metadata": self.player_adaptor.Metadata
            }
            
            msg.setArguments(["org.mpris.MediaPlayer2.Player", changed_props, []])
            self.bus.send(msg)

def inicializar_mpris(reproductor: Reproductor) -> Optional[object]:
    """Factory seguro que retorna MprisBridge solo si esta soportado."""
    if sys.platform.startswith("linux") and DBUS_DISPONIBLE:
        try:
            return MprisBridge(reproductor)
        except Exception as e:
            logger.error(f"Fallo al inicializar MPRIS: {e}")
    return None
