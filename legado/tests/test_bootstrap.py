# =============================================================================
# tests/test_bootstrap.py
#
# Verifica que el bootstrap inicial:
#   1. resuelve rutas estandar por SO correctamente,
#   2. crea directorios faltantes sin destruir los existentes,
#   3. genera un .env minimo solo cuando se solicita y no existe,
#   4. es idempotente.
# =============================================================================

from __future__ import annotations

from pathlib import Path

import pytest

from infra.bootstrap import (
    RutasEstandar,
    asegurar_entorno,
    elevar_limite_descriptores,
    primer_arranque_necesario,
    resolver_rutas_estandar,
)


# -----------------------------------------------------------------------------
# Resolucion por SO
# -----------------------------------------------------------------------------

class TestResolucionPorSO:

    def test_linux_usa_xdg(self, tmp_path, monkeypatch):
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        rutas = resolver_rutas_estandar(home=tmp_path, so="Linux")
        assert rutas.library.parent == tmp_path / ".local" / "share" / "nb_sound"
        assert rutas.cache == tmp_path / ".cache" / "nb_sound"
        assert rutas.config == tmp_path / ".config" / "nb_sound"

    def test_linux_respeta_xdg_data_home(self, tmp_path, monkeypatch):
        custom_data = tmp_path / "custom-data"
        monkeypatch.setenv("XDG_DATA_HOME", str(custom_data))
        rutas = resolver_rutas_estandar(home=tmp_path, so="Linux")
        assert rutas.library.parent == custom_data / "nb_sound"

    def test_macos_usa_library(self, tmp_path):
        rutas = resolver_rutas_estandar(home=tmp_path, so="Darwin")
        assert rutas.library.parent == tmp_path / "Library" / "Application Support" / "NBSound"
        assert rutas.cache == tmp_path / "Library" / "Caches" / "NBSound"

    def test_windows_usa_appdata(self, tmp_path, monkeypatch):
        local = tmp_path / "AppData" / "Local"
        roaming = tmp_path / "AppData" / "Roaming"
        monkeypatch.setenv("LOCALAPPDATA", str(local))
        monkeypatch.setenv("APPDATA", str(roaming))
        rutas = resolver_rutas_estandar(home=tmp_path, so="Windows")
        assert rutas.library.parent == local / "NBSound"
        assert rutas.config == roaming / "NBSound"


# -----------------------------------------------------------------------------
# Creacion de directorios
# -----------------------------------------------------------------------------

class TestAsegurarEntorno:

    def test_crea_directorios_faltantes(self, tmp_path):
        rutas = resolver_rutas_estandar(home=tmp_path, so="Linux")
        resultado = asegurar_entorno(rutas, generar_env=False)
        assert resultado.ok
        assert rutas.library.exists()
        assert rutas.cache.exists()
        assert rutas.logs.exists()
        assert resultado.creados, "Debio crear al menos un directorio"

    def test_idempotente(self, tmp_path):
        rutas = resolver_rutas_estandar(home=tmp_path, so="Linux")
        primera = asegurar_entorno(rutas, generar_env=False)
        segunda = asegurar_entorno(rutas, generar_env=False)
        assert primera.ok and segunda.ok
        assert segunda.creados == [], "La segunda corrida no debe crear nada"
        assert len(segunda.existentes) >= len(primera.creados)

    def test_no_destruye_contenido_existente(self, tmp_path):
        rutas = resolver_rutas_estandar(home=tmp_path, so="Linux")
        rutas.library.mkdir(parents=True, exist_ok=True)
        marca = rutas.library / "existing.txt"
        marca.write_text("contenido del usuario", encoding="utf-8")
        asegurar_entorno(rutas, generar_env=False)
        assert marca.read_text(encoding="utf-8") == "contenido del usuario"

    def test_reporta_error_si_archivo_bloquea_path(self, tmp_path):
        rutas = resolver_rutas_estandar(home=tmp_path, so="Linux")
        # Hacemos que la "library" sea un archivo, no un directorio:
        rutas.library.parent.mkdir(parents=True, exist_ok=True)
        rutas.library.write_text("soy un archivo", encoding="utf-8")
        resultado = asegurar_entorno(rutas, generar_env=False)
        assert not resultado.ok
        assert any("biblioteca" in err for err in resultado.errores)


# -----------------------------------------------------------------------------
# Generacion de .env
# -----------------------------------------------------------------------------

class TestGenerarEnv:

    def test_genera_env_si_falta(self, tmp_path):
        rutas = resolver_rutas_estandar(home=tmp_path, so="Linux")
        destino = tmp_path / ".env"
        resultado = asegurar_entorno(rutas, generar_env=True, env_destino=destino)
        assert resultado.env_generado is True
        assert destino.exists()
        contenido = destino.read_text(encoding="utf-8")
        assert "USER_LIBRARY_DIR=" in contenido
        assert str(rutas.library) in contenido

    def test_no_sobreescribe_env_existente(self, tmp_path):
        rutas = resolver_rutas_estandar(home=tmp_path, so="Linux")
        destino = tmp_path / ".env"
        destino.write_text("USER_LIBRARY_DIR=/mi/ruta\n", encoding="utf-8")
        resultado = asegurar_entorno(rutas, generar_env=True, env_destino=destino)
        assert resultado.env_generado is False
        assert destino.read_text(encoding="utf-8") == "USER_LIBRARY_DIR=/mi/ruta\n"


# -----------------------------------------------------------------------------
# Heuristica primer_arranque_necesario
# -----------------------------------------------------------------------------

class TestPrimerArranque:

    def test_activa_si_no_env_y_no_library(self):
        assert primer_arranque_necesario(env_existe=False, library_resuelta=None) is True

    def test_no_activa_si_env_existe(self, tmp_path):
        assert primer_arranque_necesario(env_existe=True, library_resuelta=None) is False

    def test_no_activa_si_library_ya_resuelta(self, tmp_path):
        # Caso real: usuario sin .env pero con USER_LIBRARY_DIR via env var
        assert primer_arranque_necesario(env_existe=False, library_resuelta=tmp_path) is False


# -----------------------------------------------------------------------------
# Limite de descriptores de archivo (RLIMIT_NOFILE)
# -----------------------------------------------------------------------------

class TestElevarLimiteDescriptores:

    def test_sube_blando_y_es_idempotente(self):
        resource = pytest.importorskip("resource")
        original = resource.getrlimit(resource.RLIMIT_NOFILE)
        _soft0, hard0 = original
        esperado = 8192 if hard0 == resource.RLIM_INFINITY else min(8192, hard0)
        try:
            # Fuerza un blando bajo (sin tocar el duro: bajarlo no requiere
            # privilegios, pero restaurarlo si lo elevaramos, si) para ejercitar
            # la elevacion.
            resource.setrlimit(resource.RLIMIT_NOFILE, (min(256, esperado), hard0))
            res = elevar_limite_descriptores()
            assert res is not None
            soft_final = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
            assert soft_final == esperado == res[0]
            # Idempotente: una segunda llamada no baja el limite.
            elevar_limite_descriptores()
            assert resource.getrlimit(resource.RLIMIT_NOFILE)[0] == esperado
        finally:
            resource.setrlimit(resource.RLIMIT_NOFILE, original)

    def test_no_rompe_en_plataforma_sin_resource(self, monkeypatch):
        # En Windows `import resource` lanza ImportError; el helper debe
        # devolver None sin propagar.
        import builtins

        real_import = builtins.__import__

        def _import_falla(nombre, *args, **kwargs):
            if nombre == "resource":
                raise ImportError("simulado: plataforma sin resource")
            return real_import(nombre, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _import_falla)
        assert elevar_limite_descriptores() is None
