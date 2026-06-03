# =============================================================================
# tests/test_dj_vlc_compartido.py
#
# Verifica que `ReproductorSesionDj` puede compartir la instancia VLC
# del Reproductor principal. Tener dos `vlc.Instance` vivas en el mismo
# proceso era la causa del crash a los ~2s al arrancar la sesión DJ:
# libvlc inicializa módulos globales no thread-safe y la segunda
# Instance los reinicializa sin sincronización.
# =============================================================================

from __future__ import annotations

import pytest


def test_dj_no_crea_segunda_instancia_si_recibe_vlc_inyectada():
    """Cuando `vlc_instance` se pasa al constructor, el reproductor DJ
    debe reutilizarla en lugar de crear una nueva con `vlc.Instance(...)`.
    Si el atributo `_instancia_inyectada` retiene el valor, la limpieza
    no liberará la instancia inyectada (es propiedad del Reproductor
    principal).
    """
    from servicios.dj_privado.reproductor_sesion import ReproductorSesionDj

    class _DummyInstancia:
        """Fake instancia VLC: solo necesita `media_player_new()`."""
        def media_player_new(self):
            return _DummyDeck()

    class _DummyDeck:
        def audio_set_volume(self, *_): pass
        def stop(self): pass
        def release(self): pass

    dummy = _DummyInstancia()
    rep = ReproductorSesionDj(
        permitir_modo_simulado=True,
        vlc_instance=dummy,
    )
    assert rep._instancia is dummy
    assert rep._instancia_inyectada is dummy
    rep.close()
    # Tras cerrar, la instancia inyectada NO debe estar liberada (no
    # somos dueños).


def test_dj_release_solo_cuando_creamos_la_instancia(monkeypatch):
    """Si nadie inyecta `vlc_instance`, el reproductor DJ crea su propia
    Instance y debe liberarla al cerrar. Si la inyectaron, NO la libera.
    """
    from servicios.dj_privado import reproductor_sesion as mod

    creadas = []
    releases = []

    class _FakeInst:
        def __init__(self):
            creadas.append(self)
        def media_player_new(self):
            return _FakeDeck()
        def release(self):
            releases.append(self)

    class _FakeDeck:
        def audio_set_volume(self, *_): pass
        def stop(self): pass
        def release(self): pass

    class _FakeVLC:
        @staticmethod
        def Instance(args):
            return _FakeInst()

    monkeypatch.setattr(mod, "VLC_DISPONIBLE", True)
    monkeypatch.setattr(mod, "_vlc", _FakeVLC)

    # Caso 1: instancia propia → release al cerrar.
    rep_propio = mod.ReproductorSesionDj(permitir_modo_simulado=True)
    assert len(creadas) == 1
    rep_propio.close()
    assert len(releases) == 1

    # Caso 2: instancia inyectada → NO release.
    inyectada = _FakeInst()
    rep_compartido = mod.ReproductorSesionDj(
        permitir_modo_simulado=True,
        vlc_instance=inyectada,
    )
    assert rep_compartido._instancia is inyectada
    rep_compartido.close()
    # Solo la instancia "propia" del caso 1 se liberó.
    assert releases == [creadas[0]]
