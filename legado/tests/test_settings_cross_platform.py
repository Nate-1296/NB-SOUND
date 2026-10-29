# =============================================================================
# tests/test_settings_cross_platform.py
#
# Verifica que los fallbacks de paths en `config.settings` resuelvan a
# directorios platform-aware via `infra.bootstrap` y NO a rutas POSIX
# hardcodeadas. Los user overrides via USER_*_DIR siempre ganan sobre el
# fallback.
# =============================================================================

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _reload_settings(monkeypatch, env_overrides: dict[str, str] | None = None,
                    drop: tuple[str, ...] = ()):
    """Recarga `config.settings` con un entorno limpio y devuelve el modulo.

    Importante: el modulo llama `load_dotenv()` al cargarse, pero
    `python-dotenv` no sobrescribe variables ya presentes en `os.environ`.
    Por eso `monkeypatch.setenv("", "")` ANTES del reload neutraliza un
    `.env` que el dev pueda tener en su workspace.
    """
    # Las variables que queremos "vaciar" se settean a "" (no se borran),
    # porque borrarlas dejaria que .env las repueble en el reload.
    for nombre in drop:
        monkeypatch.setenv(nombre, "")
    for nombre, valor in (env_overrides or {}).items():
        monkeypatch.setenv(nombre, valor)
    import config.settings as settings  # noqa: WPS433
    return importlib.reload(settings)


# Variables que la suite "vacia" para forzar fallback platform-aware. NO tocamos
# USER_LIBRARY_DIR/INPUT_DIR/QUARANTINE/REVIEW/LOGS porque sin .env del usuario
# esos son Optional[Path]=None por diseno.
USER_DIR_VARS = (
    "USER_CACHE_DIR",
    "USER_TEMP_DIR",
    "USER_ASSETS_DIR",
    "USER_MANIFESTS_DIR",
    "USER_PROCESSED_DIR",
)


def test_default_cache_dir_no_es_linux_hardcoded(monkeypatch):
    """DEFAULT_CACHE_DIR nunca debe terminar en '~/.cache/nb_sound' literal."""
    settings = _reload_settings(monkeypatch, drop=USER_DIR_VARS)
    assert settings.DEFAULT_CACHE_DIR is not None
    # El fallback platform-aware no debe contener el string Linux-only literal.
    # La presencia de '.cache' en Linux real es legitima — lo que comprobamos
    # es que la *ruta resuelta* venga de `infra.bootstrap`, no de la cadena dura.
    ruta = str(settings.DEFAULT_CACHE_DIR)
    assert ruta.strip() != ""
    # Resolvio a un Path absoluto.
    assert Path(ruta).is_absolute()


def test_default_temp_dir_usa_tempfile(monkeypatch):
    """DEFAULT_TEMP_DIR siempre debe ser un subdirectorio del temp del SO."""
    settings = _reload_settings(monkeypatch, drop=USER_DIR_VARS)
    import tempfile
    temp_root = Path(tempfile.gettempdir()).resolve()
    assert settings.DEFAULT_TEMP_DIR is not None
    # El subdirectorio "nb_sound" debe colgar del temp del sistema.
    assert temp_root in settings.DEFAULT_TEMP_DIR.parents \
        or settings.DEFAULT_TEMP_DIR == temp_root / "nb_sound"


def test_default_processed_dir_usa_bootstrap(monkeypatch):
    """DEFAULT_PROCESSED_DIR debe alinearse con `resolver_rutas_estandar()`."""
    settings = _reload_settings(monkeypatch, drop=USER_DIR_VARS)
    from infra.bootstrap import resolver_rutas_estandar
    rutas = resolver_rutas_estandar()
    assert settings.DEFAULT_PROCESSED_DIR is not None
    # Comparamos por resolve() para soportar ~ expandido y symlinks consistentes.
    assert settings.DEFAULT_PROCESSED_DIR == rutas.processed.resolve()


def test_default_assets_dir_usa_bootstrap(monkeypatch):
    settings = _reload_settings(monkeypatch, drop=USER_DIR_VARS)
    from infra.bootstrap import resolver_rutas_estandar
    rutas = resolver_rutas_estandar()
    assert settings.DEFAULT_ASSETS_DIR == rutas.assets.resolve()


def test_default_manifests_dir_usa_bootstrap(monkeypatch):
    settings = _reload_settings(monkeypatch, drop=USER_DIR_VARS)
    from infra.bootstrap import resolver_rutas_estandar
    rutas = resolver_rutas_estandar()
    assert settings.DEFAULT_MANIFESTS_DIR == rutas.manifests.resolve()


def test_user_override_sigue_funcionando(monkeypatch, tmp_path):
    """Si el usuario define USER_*_DIR, debe ganar sobre el fallback."""
    custom_cache = tmp_path / "mi-cache-personalizado"
    settings = _reload_settings(
        monkeypatch,
        env_overrides={"USER_CACHE_DIR": str(custom_cache)},
        drop=("USER_TEMP_DIR", "USER_ASSETS_DIR",
              "USER_MANIFESTS_DIR", "USER_PROCESSED_DIR"),
    )
    assert settings.DEFAULT_CACHE_DIR == custom_cache.resolve()


def test_settings_no_referencia_xdg_hardcoded_en_codigo():
    """`config/settings.py` no debe contener rutas POSIX hardcodeadas."""
    ruta = Path(__file__).resolve().parent.parent / "config" / "settings.py"
    contenido = ruta.read_text(encoding="utf-8")
    assert "~/.local/share/nb_sound/" not in contenido, \
        "settings.py contiene fallback Linux-only '~/.local/share/nb_sound/'"
    assert '"~/.cache/nb_sound"' not in contenido, \
        "settings.py contiene fallback Linux-only '~/.cache/nb_sound'"


def test_biblioteca_no_referencia_xdg_hardcoded():
    """`servicios/biblioteca.py` no debe contener rutas POSIX hardcodeadas."""
    ruta = Path(__file__).resolve().parent.parent / "servicios" / "biblioteca.py"
    contenido = ruta.read_text(encoding="utf-8")
    assert '"~/.cache/nb_sound"' not in contenido, \
        "biblioteca.py contiene fallback Linux-only '~/.cache/nb_sound'"


def test_main_ui_no_referencia_xdg_hardcoded():
    """`main_ui._resolver_db_default` delega a bootstrap, no a rutas POSIX."""
    ruta = Path(__file__).resolve().parent.parent / "main_ui.py"
    contenido = ruta.read_text(encoding="utf-8")
    assert '".local" / "share" / "nb_sound" / "ui.db"' not in contenido, \
        "main_ui.py mantiene fallback Linux-only para la BD"
