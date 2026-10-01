import pytest
import sys
from unittest.mock import MagicMock, patch

from servicios.reproductor import Reproductor, EstadoReproductor, PistaActiva
from infra.mpris_linux import inicializar_mpris, DBUS_DISPONIBLE

@pytest.mark.skipif(not DBUS_DISPONIBLE, reason="PySide6.QtDBus no esta disponible en el entorno de pruebas")
def test_mpris_bridge_instantiation():
    """Prueba que el puente MPRIS se inicializa y expone propiedades correctamente."""
    rep = Reproductor(permitir_modo_simulado=True)
    
    with patch("sys.platform", "linux"), \
         patch("infra.mpris_linux.QDBusConnection") as mock_qdbus:
         
        mock_bus = MagicMock()
        mock_bus.isConnected.return_value = True
        mock_bus.registerService.return_value = True
        mock_bus.registerObject.return_value = True
        mock_qdbus.sessionBus.return_value = mock_bus
        
        bridge = inicializar_mpris(rep)
        
        # En Linux con DBus disponible, deberia retornar el puente
        assert bridge is not None
        
        # Test propiedades cuando no hay pista
        with patch.object(rep, "pista_activa", return_value=None), \
             patch.object(rep, "estado", return_value=EstadoReproductor.DETENIDO):
            assert bridge.player_adaptor.PlaybackStatus == "Stopped"
            assert bridge.player_adaptor.Metadata == {}
            
        # Test propiedades con pista activa
        pista = PistaActiva()
        pista.id = 42
        pista.titulo = "Bohemian Rhapsody"
        pista.artista = "Queen"
        pista.album = "A Night at the Opera"
        pista.duracion_seg = 354.0
        pista.portada_ruta = "/tmp/cover.jpg"
        
        with patch.object(rep, "pista_activa", return_value=pista), \
             patch.object(rep, "estado", return_value=EstadoReproductor.REPRODUCIENDO):
            
            meta = bridge.player_adaptor.Metadata
            assert meta["xesam:title"] == "Bohemian Rhapsody"
            assert meta["xesam:artist"] == ["Queen"]
            assert meta["xesam:album"] == "A Night at the Opera"
            assert meta["mpris:length"] == 354000000
            assert meta["mpris:artUrl"] == "file:///tmp/cover.jpg"
            
            assert bridge.player_adaptor.PlaybackStatus == "Playing"
            
            # Comprobamos que lanza el signal a D-Bus al cambiar estado
            with patch.object(mock_bus, "send") as mock_send:
                bridge._al_cambiar_estado(EstadoReproductor.REPRODUCIENDO, pista)
                mock_send.assert_called_once()
                # Argumentos del mensaje D-Bus
                call_args = mock_send.call_args[0][0]
                assert call_args.interface() == "org.freedesktop.DBus.Properties"
                assert call_args.member() == "PropertiesChanged"

@pytest.mark.skipif(not DBUS_DISPONIBLE, reason="PySide6.QtDBus no esta disponible en el entorno de pruebas")
def test_mpris_bridge_commands():
    """Prueba que los metodos MPRIS delegan correctamente al reproductor."""
    rep = Reproductor(permitir_modo_simulado=True)
    
    with patch("sys.platform", "linux"), \
         patch("infra.mpris_linux.QDBusConnection") as mock_qdbus:
         
        mock_bus = MagicMock()
        mock_bus.isConnected.return_value = True
        mock_qdbus.sessionBus.return_value = mock_bus
        
        bridge = inicializar_mpris(rep)
        assert bridge is not None
        
        with patch.object(rep, "pausar_reanudar") as mock_pausar:
            # PlayPause deberia siempre hacer toggle
            bridge.player_adaptor.PlayPause()
            mock_pausar.assert_called_once()
            
        with patch.object(rep, "siguiente") as mock_next:
            bridge.player_adaptor.Next()
            mock_next.assert_called_once()
            
        with patch.object(rep, "anterior") as mock_prev:
            bridge.player_adaptor.Previous()
            mock_prev.assert_called_once()
