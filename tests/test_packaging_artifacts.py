"""Tests que validan la presencia de artefactos para empaquetado v1."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_existe_y_contiene_metadata_minima():
    pp = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for clave in ("[project]", 'name = "nb_sound"', "[project.scripts]", "nb_sound =", "nb_sound_ui ="):
        assert clave in pp, f"pyproject.toml: falta {clave}"


def test_changelog_existe_con_release_1():
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "[1.0.0]" in cl


def test_packaging_specs_existen():
    for spec in ("packaging/linux/nb_sound.spec",
                 "packaging/windows/nb_sound.spec",
                 "packaging/macos/nb_sound.spec"):
        assert (ROOT / spec).exists(), f"Falta {spec}"


def test_desktop_file_linux_existe():
    desk = ROOT / "packaging" / "linux" / "nb-sound.desktop"
    assert desk.exists()
    contenido = desk.read_text(encoding="utf-8")
    for clave in ("Type=Application", "Name=NB SOUND", "Categories=", "Exec="):
        assert clave in contenido


def test_logos_multi_resolucion_existen():
    logo_dir = ROOT / "ui" / "qml" / "assets" / "logo"
    for n in (16, 32, 48, 64, 128, 256, 512):
        png = logo_dir / f"logo_{n}.png"
        assert png.exists(), f"Falta logo_{n}.png"
    assert (logo_dir / "logo.ico").exists(), "Falta logo.ico (Windows)"
    assert (logo_dir / "logo.icns").exists(), "Falta logo.icns (macOS)"


def test_macos_spec_declara_identifier_correcto():
    """El bundle identifier macOS debe coincidir con `infra.version.APP_IDENTIFIER`.

    `infra/version.py` es la fuente única de verdad; el spec puede
    referenciar la variable o el literal equivalente.
    """
    spec = (ROOT / "packaging" / "macos" / "nb_sound.spec").read_text(encoding="utf-8")
    from infra.version import APP_IDENTIFIER
    assert APP_IDENTIFIER == "com.nbsound.app", (
        "APP_IDENTIFIER cambio: actualizar test y firma macOS"
    )
    referencia_variable = "bundle_identifier=APP_IDENTIFIER" in spec
    referencia_literal = (
        'bundle_identifier="com.nbsound.app"' in spec
        or "bundle_identifier='com.nbsound.app'" in spec
    )
    assert referencia_variable or referencia_literal, (
        "macos/nb_sound.spec no declara bundle_identifier reconocible"
    )


def test_specs_referencian_iconos_existentes():
    """Cada spec debe referenciar un icono que sí exista."""
    base = ROOT / "ui" / "qml" / "assets" / "logo"
    for spec_path, icon_name in [
        ("packaging/linux/nb_sound.spec", "logo_256.png"),
        ("packaging/windows/nb_sound.spec", "logo.ico"),
        ("packaging/macos/nb_sound.spec", "logo.icns"),
    ]:
        contenido = (ROOT / spec_path).read_text(encoding="utf-8")
        assert icon_name in contenido, f"{spec_path}: no referencia {icon_name}"
        assert (base / icon_name).exists(), f"Icono real ausente: {icon_name}"
