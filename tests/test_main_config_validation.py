from unittest.mock import patch
from pathlib import Path

from main import validar_configuracion_operativa
from config import settings


def test_falla_si_ia_openai_activa_sin_api_key():
    with patch("main.settings.ENABLE_IA_TIEBREAK", True), \
         patch("main.settings.IA_PROVEEDOR", "OpenAI"), \
         patch("main.settings.OPENAI_API_KEY_RESOLVED", ""):
        errores = validar_configuracion_operativa()
    assert any("OPENAI_API_KEY" in e for e in errores)


def test_falla_si_ia_anthropic_activa_sin_api_key():
    with patch("main.settings.ENABLE_IA_TIEBREAK", True), \
         patch("main.settings.IA_PROVEEDOR", "Anthropic"), \
         patch("main.settings.ANTHROPIC_API_KEY_RESOLVED", ""):
        errores = validar_configuracion_operativa()
    assert any("ANTHROPIC_API_KEY" in e for e in errores)


def test_audio_intelligence_background_defaults_seguros():
    assert isinstance(settings.AUDIO_INTELLIGENCE_ANALYZE_ON_IMPORT, bool)
    assert isinstance(settings.AUDIO_INTELLIGENCE_ANALYZE_AFTER_IMPORT_BACKGROUND, bool)
    assert isinstance(settings.AUDIO_INTELLIGENCE_RESUME_PENDING_ON_STARTUP, bool)
    assert isinstance(settings.AUDIO_INTELLIGENCE_BACKGROUND_AUTOSTART, bool)
    assert settings.AUDIO_INTELLIGENCE_BACKGROUND_BATCH_SIZE == 1
    assert settings.AUDIO_INTELLIGENCE_BACKGROUND_IDLE_DELAY_SEC >= 0
    assert settings.AUDIO_INTELLIGENCE_MAX_ATTEMPTS >= 1
    assert isinstance(settings.AUDIO_INTELLIGENCE_RETRY_FAILED, bool)


def test_env_example_cubre_variables_operativas_audio_assets_y_sidecars():
    env = Path(".env.example").read_text(encoding="utf-8")
    for clave in (
        "USER_LIBRARY_DIR=",
        "ENABLE_ASSETS_PIPELINE=",
        "SIDECAR_FUTURE_TIMEOUT_SEG=",
        "ENABLE_AUDIO_FEATURES=",
        "ENABLE_AUDIO_INTELLIGENCE_DEEP=",
        "AUDIO_INTELLIGENCE_BACKEND=",
        "AUDIO_INTELLIGENCE_BACKGROUND_AUTOSTART=",
        "AUDIO_INTELLIGENCE_MAX_WORKERS=1",
        "ENABLE_MUSIC_DISCOVERY=",
    ):
        assert clave in env
    assert "ENABLE_AUDIO_INTELLIGENCE_DEEP=False" in env
    assert "AUDIO_INTELLIGENCE_BACKEND=none" in env
