# =============================================================================
# tests/test_dependencias.py
#
# Cobertura del módulo `infra.dependencias` y del wrapper QML
# `ModeloDependencias`. Las pruebas no requieren red ni acceso a archivos del
# sistema: los verificadores se monkeypatchean para devolver resultados
# determinísticos.
# =============================================================================

from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _aislar_db(tmp_path, monkeypatch):
    """Aísla la BD de config_ui en cada test usando un sqlite temporal."""
    from db import conexion
    monkeypatch.setattr(conexion, "_conexion", None, raising=False)
    db_path = tmp_path / "config.sqlite3"
    conexion.inicializar_db(db_path)
    yield
    try:
        conexion.cerrar_db()
    except Exception:
        pass


def test_catalogo_contiene_deps_esenciales():
    """El catálogo debe declarar VLC, ffmpeg, fpcalc, librosa, torch, demucs,
    essentia y modelos. Si alguna falta, la pantalla de Estado del sistema
    aparecería incompleta.
    """
    from infra.dependencias import construir_catalogo
    ids = {d.id for d in construir_catalogo()}
    esperados = {
        "vlc", "ffmpeg", "fpcalc", "librosa", "soundfile",
        "torch", "torchaudio", "demucs",
        "essentia_tensorflow", "modelos_essentia",
    }
    assert esperados <= ids, f"Faltan en catálogo: {esperados - ids}"


def test_requeridas_minimas_marcadas_correctamente():
    """VLC, ffmpeg y librosa son requeridas; el resto opcionales."""
    from infra.dependencias import construir_catalogo
    cat = {d.id: d for d in construir_catalogo()}
    assert cat["vlc"].requerida is True
    assert cat["ffmpeg"].requerida is True
    assert cat["librosa"].requerida is True
    assert cat["torch"].requerida is False
    assert cat["essentia_tensorflow"].requerida is False
    assert cat["modelos_essentia"].requerida is False


def test_detectar_persiste_cache_en_config_ui(monkeypatch):
    """Tras detectar(), `config_ui` debe contener una entrada serializable
    JSON con el estado de cada dependencia. Un segundo `detectar()` reusa el
    cache sin volver a invocar los verificadores.
    """
    from infra import dependencias as deps
    contador = {"n": 0}

    def _fake_verificador():
        contador["n"] += 1
        return True, "1.0.0"

    monkeypatch.setattr(deps, "construir_catalogo", lambda: [
        deps.Dependencia(
            id="dummy",
            nombre="Dummy",
            descripcion="d",
            tipo=deps.TipoDependencia.PIP,
            requerida=False,
            funciones_que_habilita=[],
            verificador=_fake_verificador,
            pip_specifier="dummy",
        ),
    ])

    rep1 = deps.detectar(force_refresh=True)
    assert len(rep1) == 1
    assert rep1[0].estado == "ok"
    assert rep1[0].version == "1.0.0"
    assert contador["n"] == 1

    # Cache reciente: no debería ejecutar verificador de nuevo.
    rep2 = deps.detectar(force_refresh=False)
    assert contador["n"] == 1
    assert rep2[0].estado == "ok"

    # Force refresh: vuelve a ejecutar.
    deps.detectar(force_refresh=True)
    assert contador["n"] == 2


def test_detectar_uno_actualiza_solo_esa_entrada(monkeypatch):
    """`detectar_uno` no debe reverificar el resto del catálogo."""
    from infra import dependencias as deps
    llamadas = {"a": 0, "b": 0}

    def _ver_a():
        llamadas["a"] += 1
        return True, "1"

    def _ver_b():
        llamadas["b"] += 1
        return False, ""

    monkeypatch.setattr(deps, "construir_catalogo", lambda: [
        deps.Dependencia(id="a", nombre="A", descripcion="", tipo=deps.TipoDependencia.PIP,
                         requerida=False, funciones_que_habilita=[], verificador=_ver_a),
        deps.Dependencia(id="b", nombre="B", descripcion="", tipo=deps.TipoDependencia.PIP,
                         requerida=False, funciones_que_habilita=[], verificador=_ver_b),
    ])

    deps.detectar(force_refresh=True)
    assert llamadas == {"a": 1, "b": 1}

    rep = deps.detectar_uno("a")
    assert rep is not None
    assert rep.estado == "ok"
    # `a` se reverificó pero `b` no.
    assert llamadas == {"a": 2, "b": 1}


def test_cache_obsoleto_por_aperturas():
    """Tras N aperturas, cache_obsoleto() debe devolver True aunque el cache
    sea reciente en tiempo.
    """
    from infra import dependencias as deps
    from db.conexion import guardar_config
    import datetime as _dt

    guardar_config(deps._CLAVE_CACHE, "{}")
    guardar_config(deps._CLAVE_TIMESTAMP,
                   _dt.datetime.now(_dt.timezone.utc).isoformat())
    guardar_config(deps._CLAVE_APERTURAS, "0")

    assert deps.cache_obsoleto() is False
    for _ in range(deps.APERTURAS_HASTA_REVALIDAR):
        deps.registrar_apertura()
    assert deps.cache_obsoleto() is True


def test_aplicar_runtime_pip_userdir_idempotente(tmp_path, monkeypatch):
    """Llamar `aplicar_runtime_pip_userdir` dos veces no debe duplicar la
    entrada en sys.path ni añadirla si el directorio no existe.
    """
    import sys
    from infra import dependencias, instalador
    monkeypatch.setattr(instalador, "ruta_site_packages_runtime",
                        lambda: tmp_path / "site-packages")

    dependencias.aplicar_runtime_pip_userdir()  # dir no existe -> noop
    assert str(tmp_path / "site-packages") not in sys.path

    (tmp_path / "site-packages").mkdir()
    dependencias.aplicar_runtime_pip_userdir()
    assert sys.path[0] == str(tmp_path / "site-packages")

    # Llamada repetida: no añade duplicado.
    dependencias.aplicar_runtime_pip_userdir()
    apariciones = sum(1 for p in sys.path if p == str(tmp_path / "site-packages"))
    assert apariciones == 1


def test_instalador_falla_limpio_si_no_hay_python(monkeypatch):
    """Si no hay Python del sistema, `instalar_pip` debe devolver
    ResultadoInstalacion(ok=False) sin lanzar excepciones."""
    from infra import instalador
    monkeypatch.setattr(instalador, "detectar_python_sistema", lambda: None)
    res = instalador.instalar_pip("torch")
    assert res.ok is False
    assert "Python" in res.mensaje


def test_diagnostico_entorno_devuelve_dict():
    """`diagnostico_entorno` siempre devuelve un dict con las claves esperadas
    para que la UI no tenga que defenderse contra None."""
    from infra import instalador
    diag = instalador.diagnostico_entorno()
    for clave in ("python_sistema", "site_packages_runtime", "frozen",
                  "ejecutable", "plataforma"):
        assert clave in diag


def test_reporte_serializable_a_json():
    """Cada ReporteDependencia debe ser JSON-serializable, porque se
    guarda en config_ui via json.dumps. Si algún campo deja de serializar,
    la cache deja de cargar."""
    from infra.dependencias import ReporteDependencia
    rep = ReporteDependencia(
        id="x", nombre="X", descripcion="d", tipo="pip", requerida=True,
        funciones_que_habilita=["F"], estado="ok", version="1.0", detalle="",
        instruccion_manual="", pip_specifier="x", verificado_en="2026-01-01",
    )
    s = json.dumps(rep.a_dict(), ensure_ascii=False)
    assert "ok" in s


# ─── Resiliencia del instalador (issue: re-instalar tras corte) ──────────────

def test_instalar_pip_fuerza_reinstalacion_limpia_y_reintentos(tmp_path, monkeypatch):
    """`instalar_pip` siempre repara: una instalación previa interrumpida deja
    el --target a medias y pip, sin estas banderas, la daba por 'ya presente'
    (código 0) mientras la app nunca la reconocía. El comando debe forzar la
    reinstalación limpia y traer reintentos de red."""
    from infra import instalador
    monkeypatch.setattr(instalador, "detectar_python_sistema", lambda: "/usr/bin/python3")
    monkeypatch.setattr(instalador, "ruta_site_packages_runtime", lambda: tmp_path / "sp")
    capturado = {}

    def _fake_ejecutar(cmd, timeout=None, en_callback=None):
        capturado["cmd"] = list(cmd)
        return 0, "instalado", ""

    monkeypatch.setattr(instalador, "_ejecutar", _fake_ejecutar)
    res = instalador.instalar_pip("aiohttp>=3.9.0")
    assert res.ok is True
    cmd = capturado["cmd"]
    assert "--upgrade" in cmd
    assert "--force-reinstall" in cmd
    assert "--retries" in cmd
    assert "--target" in cmd
    assert cmd[-1] == "aiohttp>=3.9.0"


def test_aplicar_runtime_pip_userdir_invalida_caches(tmp_path, monkeypatch):
    """Tras añadir el site-packages runtime a sys.path se deben invalidar los
    caches de importlib; si no, una verificación in-process seguía viendo el
    módulo recién instalado como faltante."""
    import importlib
    from infra import dependencias, instalador
    monkeypatch.setattr(instalador, "ruta_site_packages_runtime",
                        lambda: tmp_path / "sp")
    (tmp_path / "sp").mkdir()
    contador = {"n": 0}
    monkeypatch.setattr(importlib, "invalidate_caches",
                        lambda: contador.__setitem__("n", contador["n"] + 1))
    dependencias.aplicar_runtime_pip_userdir()
    assert contador["n"] >= 1


# ─── Arranque no bloqueante: lectura de cache sin ejecutar verificadores ─────

def test_reportes_cacheados_no_ejecuta_verificadores(monkeypatch):
    """`reportes_cacheados` jamás debe construir el catálogo ni correr
    verificadores (subprocesos torch/essentia, instancia VLC): eso congelaba
    el arranque cuando el cache caducaba."""
    from infra import dependencias as deps

    def _boom():
        raise AssertionError("construir_catalogo NO debe llamarse al leer cache")

    monkeypatch.setattr(deps, "construir_catalogo", _boom)

    # Sin cache: lista vacía, sin tocar el catálogo.
    assert deps.reportes_cacheados() == []

    # Con cache poblado: devuelve los reportes, también sin verificar.
    from db.conexion import guardar_config
    guardar_config("dependencias_cache",
                   json.dumps({"vlc": {"id": "vlc", "estado": "ok", "version": "3.0"}}))
    reps = deps.reportes_cacheados()
    assert len(reps) == 1 and reps[0].id == "vlc" and reps[0].estado == "ok"
