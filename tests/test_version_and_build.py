"""Tests del módulo infra.version y consistencia de versionado."""
from pathlib import Path

from infra.version import (
    APP_NAME,
    APP_VERSION,
    APP_VERSION_DISPLAY,
    CLI_NAME,
    UI_NAME,
    CLI_BANNER,
    UI_BANNER,
    APP_DESCRIPTION,
    APP_AUTHOR,
    APP_LICENSE,
    APP_HOMEPAGE,
    APP_IDENTIFIER,
)


def test_app_version_es_semver():
    parts = APP_VERSION.split(".")
    assert len(parts) >= 2
    for p in parts:
        assert p.isdigit(), f"Componente no numérico: {p}"


def test_app_version_display_coherente():
    # Display debe reflejar la versión completa (p. ej. "v1.1.0").
    assert APP_VERSION_DISPLAY == f"v{APP_VERSION}"


def test_banners_contienen_nombre_y_version():
    assert APP_NAME in CLI_BANNER
    assert APP_NAME in UI_BANNER
    assert APP_VERSION_DISPLAY in CLI_BANNER
    assert APP_VERSION_DISPLAY in UI_BANNER


def test_nombres_separan_cli_ui():
    assert "CLI" in CLI_NAME
    assert "UI" in UI_NAME


def test_metadata_no_vacia():
    for valor in (APP_DESCRIPTION, APP_AUTHOR, APP_LICENSE, APP_HOMEPAGE, APP_IDENTIFIER):
        assert valor and isinstance(valor, str), f"Metadata vacía o tipo inválido: {valor!r}"


def test_identifier_formato_reverse_dns():
    """APP_IDENTIFIER debe usar formato reverse-DNS para empaquetado nativo."""
    assert "." in APP_IDENTIFIER
    partes = APP_IDENTIFIER.split(".")
    assert len(partes) >= 2


def test_pyproject_coincide_con_version():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{APP_VERSION}"' in pyproject, (
        "pyproject.toml debe declarar la misma versión que infra/version.py"
    )


def test_no_referencias_a_v2_en_codigo_visible():
    """Cabeceras de archivos críticos no deben referenciar versión antigua v2.x."""
    archivos = [
        Path("main.py"),
        Path("main_ui.py"),
        Path("config/settings.py"),
        Path("infra/reports.py"),
        Path("infra/progress.py"),
        Path("domain/models.py"),
        Path("core/pipeline.py"),
    ]
    for ruta in archivos:
        if not ruta.exists():
            continue
        contenido = ruta.read_text(encoding="utf-8")
        # Tolera "v3.x" en comentarios de evolución interna del CLI antiguo,
        # pero NO la marca de versión actual ya retirada.
        assert "NB SOUND CLI v2" not in contenido, f"{ruta} aún referencia v2"
        assert "NB SOUND UI V1" not in contenido, f"{ruta} usa formato viejo 'UI V1'"
