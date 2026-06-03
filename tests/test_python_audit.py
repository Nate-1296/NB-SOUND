# =============================================================================
# tests/test_python_audit.py
#
# Verifica que `infra.instalador.auditar_python_sistema` reporta
# correctamente el estado del intérprete y construye el comando de
# reparación apropiado para el SO. No reinstala nada en el sistema real.
# =============================================================================

from __future__ import annotations

import sys

import pytest


def test_python_chequeado_utilizable_requiere_pip_y_venv():
    """`utilizable` debe ser False si pip o venv faltan, aunque la versión
    sea suficiente — ese es el caso típico de Debian sin python3-venv.
    """
    from infra.instalador import PythonChequeado
    sin_pip = PythonChequeado(ruta="/x", version=(3, 12), pip_presente=False, venv_presente=True)
    sin_venv = PythonChequeado(ruta="/x", version=(3, 12), pip_presente=True, venv_presente=False)
    viejo = PythonChequeado(ruta="/x", version=(3, 9), pip_presente=True, venv_presente=True)
    ok = PythonChequeado(ruta="/x", version=(3, 12), pip_presente=True, venv_presente=True)
    assert sin_pip.utilizable is False
    assert sin_venv.utilizable is False
    assert viejo.utilizable is False
    assert ok.utilizable is True


def test_auditar_python_sistema_devuelve_chequeado_estable():
    """Llamar a `auditar_python_sistema` no debe lanzar excepciones en
    entornos donde Python está bien instalado (como el de los tests)."""
    from infra.instalador import auditar_python_sistema
    chq = auditar_python_sistema()
    assert chq.ruta != ""
    assert chq.version >= (3, 10)


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="reparación automática solo aplica a Linux")
def test_comando_reparacion_linux_solo_construye_si_hay_gestor(monkeypatch):
    """El comando de reparación debe ser None cuando no hay gestor de
    paquetes conocido. Esto evita que la UI ofrezca un botón inservible."""
    from infra import instalador
    from infra.instalador import PythonChequeado, comando_reparacion_linux
    # Forzar que ningún gestor exista.
    monkeypatch.setattr(instalador, "_detectar_gestor_paquetes_linux", lambda: None)
    chq = PythonChequeado(ruta="/x", version=(3, 12), pip_presente=False, venv_presente=False)
    assert comando_reparacion_linux(chq) is None


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="apt solo en Linux")
def test_comando_reparacion_apt_incluye_python3_venv(monkeypatch):
    """En distros con apt, el comando debe incluir python3-pip y python3-venv,
    porque ese es el síntoma reportado por el usuario."""
    from infra import instalador
    from infra.instalador import PythonChequeado, comando_reparacion_linux
    monkeypatch.setattr(instalador, "_detectar_gestor_paquetes_linux",
                        lambda: ("apt", ["apt-get", "install", "-y", "--no-install-recommends"]))
    monkeypatch.setattr(instalador.shutil, "which", lambda x: "/usr/bin/" + x)
    chq = PythonChequeado(ruta="/x", version=(3, 12), pip_presente=False, venv_presente=False)
    cmd = comando_reparacion_linux(chq)
    assert cmd is not None
    cmd_str = " ".join(cmd)
    assert "python3-pip" in cmd_str
    assert "python3-venv" in cmd_str
    # Debe usar pkexec o sudo para elevar privilegios (apt-get install requiere root).
    assert cmd[0] in ("pkexec", "sudo")


def test_diagnostico_entorno_incluye_campos_reparacion():
    """`diagnostico_entorno` debe siempre exponer las claves que la UI
    QML consulta (incluso si son strings vacíos), para que los bindings
    no truenen al renderizar."""
    from infra.instalador import diagnostico_entorno
    diag = diagnostico_entorno()
    for clave in ("python_sistema", "python_detectado", "python_version",
                  "python_utilizable", "python_falta_pip", "python_falta_venv",
                  "site_packages_runtime", "frozen", "ejecutable",
                  "plataforma", "reparacion_disponible", "reparacion_comando"):
        assert clave in diag


def test_python_para_subprocess_desarrollo_devuelve_sys_executable():
    """Fuera del bundle (`sys.frozen` no seteado), el helper debe devolver
    el ``sys.executable`` actual sin tocar el entorno: el Python que corre
    el test ya tiene todo lo necesario en su sys.path."""
    from infra.instalador import python_para_subprocess
    ejecutable, env = python_para_subprocess()
    assert ejecutable == sys.executable
    assert "PYTHONPATH" not in env or env["PYTHONPATH"] == os.environ.get("PYTHONPATH", "")


def test_python_para_subprocess_frozen_usa_python_externo(monkeypatch, tmp_path):
    """En modo bundle, el helper debe usar el Python externo (no el
    bootloader nativo) y agregar el site-packages runtime al PYTHONPATH."""
    import os as _os
    from infra import instalador
    sp = tmp_path / "site-packages"
    sp.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(instalador, "detectar_python_sistema",
                        lambda: "/usr/bin/python3")
    monkeypatch.setattr(instalador, "ruta_site_packages_runtime", lambda: sp)
    ejecutable, env = instalador.python_para_subprocess()
    assert ejecutable == "/usr/bin/python3"
    assert env.get("PYTHONPATH", "").startswith(str(sp))


def test_python_para_subprocess_frozen_sin_python_externo(monkeypatch):
    """En modo bundle sin Python externo, el helper devuelve (None, env)
    para que el caller pueda decidir fallback (no marcar como faltante
    automáticamente)."""
    from infra import instalador
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(instalador, "detectar_python_sistema", lambda: None)
    ejecutable, env = instalador.python_para_subprocess()
    assert ejecutable is None
    assert isinstance(env, dict)


def test_verificador_subprocess_usa_helper(monkeypatch):
    """`_verificar_modulo_subprocess` debe invocar `python_para_subprocess`
    al menos una vez para no caer en el bug del bootloader nativo en frozen.
    """
    from infra import dependencias, instalador
    llamadas = {"n": 0}
    original = instalador.python_para_subprocess

    def _wrap():
        llamadas["n"] += 1
        return original()

    monkeypatch.setattr(instalador, "python_para_subprocess", _wrap)
    # Probar contra un modulo que existe seguro: 'os' (stdlib).
    ok, ver = dependencias._verificar_modulo_subprocess("os")
    assert ok is True
    assert ver  # alguna version (o 'desconocida')
    assert llamadas["n"] >= 1


# Helper imports usados arriba
import os  # noqa: E402
