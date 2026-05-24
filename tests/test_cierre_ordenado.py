# =============================================================================
# tests/test_cierre_ordenado.py
#
# Verifica el cierre ordenado de Reproductor y modelos UI con workers/timers.
# Estos tests son la red de seguridad contra regresiones del tipo:
#   - "QThread: Destroyed while thread is still running"
#   - VLC sigue sonando tras cerrar la app
#   - Callbacks invocados tras release() del backend
#   - Timers Qt activos durante el teardown
# =============================================================================

from __future__ import annotations

import threading
import time

import pytest

from db.conexion import cerrar_db, inicializar_db
from servicios import reproductor as reproductor_mod
from servicios.reproductor import EstadoReproductor, Reproductor


# -----------------------------------------------------------------------------
# Fixtures comunes
# -----------------------------------------------------------------------------

@pytest.fixture()
def db_temporal(tmp_path):
    inicializar_db(tmp_path / "cierre_test.db")
    try:
        yield tmp_path
    finally:
        cerrar_db()


@pytest.fixture()
def reproductor_simulado(monkeypatch, db_temporal):
    """Reproductor con VLC e hilo de progreso stubs.

    El cierre real liberaria VLC nativo, pero queremos verificar la
    secuencia logica sin dependencia del backend.
    """
    monkeypatch.setattr(
        reproductor_mod.Reproductor, "_inicializar_vlc", lambda self: None
    )
    rep = Reproductor(permitir_modo_simulado=True)
    yield rep


# -----------------------------------------------------------------------------
# Reproductor: cierre ordenado
# -----------------------------------------------------------------------------

class TestReproductorCierre:

    def test_cerrar_marca_estado_cerrado(self, reproductor_simulado):
        rep = reproductor_simulado
        assert rep._cerrado is False
        rep.cerrar()
        assert rep._cerrado is True
        assert rep._estado == EstadoReproductor.DETENIDO

    def test_cerrar_es_idempotente(self, reproductor_simulado):
        rep = reproductor_simulado
        rep.cerrar()
        # Segunda llamada no debe lanzar ni cambiar estado.
        rep.cerrar()
        assert rep._cerrado is True

    def test_cerrar_limpia_callbacks(self, reproductor_simulado):
        rep = reproductor_simulado
        rep.on_progreso(lambda *a: None)
        rep.on_estado(lambda *a: None)
        rep.on_cola(lambda: None)
        rep.on_aviso(lambda *a: None)
        assert len(rep._cb_progreso) == 1
        assert len(rep._cb_estado) == 1
        rep.cerrar()
        assert rep._cb_progreso == []
        assert rep._cb_estado == []
        assert rep._cb_cola == []
        assert rep._cb_aviso == []
        assert rep._cb_modo_dj == []

    def test_cerrar_libera_handles_vlc_si_existen(self, monkeypatch, db_temporal):
        """Si VLC esta inicializado, release() debe llamarse en cierre."""
        liberados = {"media": False, "instancia": False, "detach": False}

        class StubMediaPlayer:
            def stop(self):
                pass

            def release(self):
                liberados["media"] = True

            def event_manager(self):
                class _EM:
                    def event_detach(_self, *a, **kw):
                        liberados["detach"] = True

                    def event_attach(_self, *a, **kw):
                        pass

                return _EM()

        class StubInstancia:
            def media_player_new(self):
                return StubMediaPlayer()

            def release(self):
                liberados["instancia"] = True

        def _stub_init(self):
            self._instancia_vlc = StubInstancia()
            self._media_player = self._instancia_vlc.media_player_new()

        monkeypatch.setattr(reproductor_mod.Reproductor, "_inicializar_vlc", _stub_init)
        rep = Reproductor(permitir_modo_simulado=True)
        rep.cerrar()
        assert liberados["media"] is True
        assert liberados["instancia"] is True
        assert liberados["detach"] is True
        assert rep._media_player is None
        assert rep._instancia_vlc is None

    def test_cerrar_detiene_hilo_progreso(self, reproductor_simulado):
        """El loop de progreso debe salir tras cerrar()."""
        rep = reproductor_simulado
        # Iniciar el hilo manualmente: el fixture stub _iniciar_hilo_progreso? No,
        # esta vez no se stubea: usamos el real para verificar la salida.
        rep._activo = True
        hilo = threading.Thread(target=rep._loop_progreso, daemon=True)
        rep._hilo_progreso = hilo
        hilo.start()
        assert hilo.is_alive()
        rep.cerrar()
        # Tras cerrar, el flag _cerrado bloquea el loop y join debe haber
        # cerrado el hilo dentro del timeout.
        time.sleep(0.6)  # margen sobre el sleep(0.5) del loop
        assert not hilo.is_alive()

    def test_cerrar_cancela_timer_fin_pista(self, reproductor_simulado):
        rep = reproductor_simulado
        disparado = {"valor": False}

        def _accion():
            disparado["valor"] = True

        # Simulamos timer pendiente que dispararia despues
        timer = threading.Timer(5.0, _accion)
        timer.daemon = True
        timer.start()
        rep._timer_fin_pista = timer
        rep.cerrar()
        # Esperamos un poquito y verificamos que el timer cancelado no disparo.
        time.sleep(0.2)
        assert disparado["valor"] is False
        assert rep._timer_fin_pista is None

    def test_avanzar_tras_fin_pista_es_noop_tras_cerrar(self, reproductor_simulado):
        rep = reproductor_simulado
        rep._cerrado = True
        # No debe lanzar ni tocar el lock pese a haber estado activo:
        rep._avanzar_tras_fin_pista()


# -----------------------------------------------------------------------------
# Modelos QML: verifico la existencia y firma de cerrar()
# -----------------------------------------------------------------------------

class TestModelosTienenCerrar:
    """Garantiza que todos los modelos con workers/timers exponen cerrar().

    Si alguno se agrega en el futuro sin cerrar(), main_ui.py lo invocara
    pero hasattr() devolveria False — este test obliga a mantener la
    politica de tener cerrar() en todo modelo con QThread o QTimer.
    """

    @pytest.mark.parametrize(
        "nombre_clase",
        [
            "ModeloReproductor",
            "ModeloBusqueda",
            "ModeloAudioIntelligenceBackground",
            "ModeloImportacion",
            "ModeloPlaylists",
            "ModeloKaraoke",
            "ModeloDjPrivado",
            "ModeloExploradorCiego",
        ],
    )
    def test_modelo_expone_cerrar(self, nombre_clase):
        from ui import modelos_qml

        cls = getattr(modelos_qml, nombre_clase)
        assert hasattr(cls, "cerrar"), f"{nombre_clase} no expone cerrar()"
        assert callable(cls.cerrar)
