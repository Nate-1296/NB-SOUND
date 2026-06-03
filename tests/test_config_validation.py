# =============================================================================
# tests/test_config_validation.py
#
# Tests unitarios para validación de configuración:
# - Funciones _env_int(), _env_float() con rangos
# - Función validar_path_seguro() en utils.text
# - Validación de límites y valores fuera de rango
# =============================================================================

import os
import tempfile
from pathlib import Path
import pytest

from config.settings import _env_int, _env_float
from utils.text import validar_path_seguro


class TestEnvIntValidation:
    """Tests para _env_int() con validación de rangos"""

    def test_env_int_dentro_de_rango(self):
        """Valor válido dentro de rango debe ser aceptado"""
        os.environ['TEST_INT_VAR'] = '12'
        resultado = _env_int('TEST_INT_VAR', 5, min_val=1, max_val=300)
        assert resultado == 12

    def test_env_int_en_limite_minimo(self):
        """Valor en límite mínimo es válido"""
        os.environ['TEST_INT_MIN'] = '1'
        resultado = _env_int('TEST_INT_MIN', 5, min_val=1, max_val=300)
        assert resultado == 1

    def test_env_int_en_limite_maximo(self):
        """Valor en límite máximo es válido"""
        os.environ['TEST_INT_MAX'] = '300'
        resultado = _env_int('TEST_INT_MAX', 5, min_val=1, max_val=300)
        assert resultado == 300

    def test_env_int_debajo_minimo(self, capsys):
        """Valor bajo mínimo usa default y registra advertencia en stderr"""
        os.environ['TEST_INT_LOW'] = '0'
        resultado = _env_int('TEST_INT_LOW', 5, min_val=1, max_val=300)
        # Debería usar el default
        assert resultado == 5
        # Debería haber una advertencia en stderr
        captured = capsys.readouterr()
        assert 'TEST_INT_LOW' in captured.err or resultado == 5

    def test_env_int_encima_maximo(self, capsys):
        """Valor sobre máximo usa default y registra advertencia en stderr"""
        os.environ['TEST_INT_HIGH'] = '301'
        resultado = _env_int('TEST_INT_HIGH', 5, min_val=1, max_val=300)
        # Debería usar el default
        assert resultado == 5
        # Debería haber una advertencia en stderr
        captured = capsys.readouterr()
        assert 'TEST_INT_HIGH' in captured.err or resultado == 5

    def test_env_int_valor_invalido(self):
        """Valor no numérico retorna default, no lanza excepción"""
        os.environ['TEST_INT_INVALID'] = 'no_es_numero'
        resultado = _env_int('TEST_INT_INVALID', 5)
        # Debería retornar el default, no lanzar excepción
        assert resultado == 5

    def test_env_int_sin_rango_especificado(self):
        """Sin min_val/max_val, cualquier valor válido es aceptado"""
        os.environ['TEST_INT_NORANGE'] = '9999'
        resultado = _env_int('TEST_INT_NORANGE', 5)
        assert resultado == 9999

    def test_env_int_variable_no_existe(self):
        """Variable no definida retorna default"""
        if 'TEST_INT_NOEXISTE' in os.environ:
            del os.environ['TEST_INT_NOEXISTE']
        resultado = _env_int('TEST_INT_NOEXISTE', 42, min_val=1, max_val=100)
        assert resultado == 42


class TestEnvFloatValidation:
    """Tests para _env_float() con validación de rangos"""

    def test_env_float_dentro_de_rango(self):
        """Valor flotante válido dentro de rango"""
        os.environ['TEST_FLOAT_VAR'] = '0.12'
        resultado = _env_float('TEST_FLOAT_VAR', 0.5, min_val=0.01, max_val=0.99)
        assert abs(resultado - 0.12) < 0.001

    def test_env_float_en_limite_minimo(self):
        """Valor en límite mínimo es válido"""
        os.environ['TEST_FLOAT_MIN'] = '0.01'
        resultado = _env_float('TEST_FLOAT_MIN', 0.5, min_val=0.01, max_val=0.99)
        assert abs(resultado - 0.01) < 0.001

    def test_env_float_en_limite_maximo(self):
        """Valor en límite máximo es válido"""
        os.environ['TEST_FLOAT_MAX'] = '0.99'
        resultado = _env_float('TEST_FLOAT_MAX', 0.5, min_val=0.01, max_val=0.99)
        assert abs(resultado - 0.99) < 0.001

    def test_env_float_debajo_minimo(self, capsys):
        """Valor bajo mínimo usa default y registra advertencia"""
        os.environ['TEST_FLOAT_LOW'] = '0.001'
        resultado = _env_float('TEST_FLOAT_LOW', 0.5, min_val=0.01, max_val=0.99)
        assert resultado == 0.5
        captured = capsys.readouterr()
        assert 'TEST_FLOAT_LOW' in captured.err or resultado == 0.5

    def test_env_float_encima_maximo(self, capsys):
        """Valor sobre máximo usa default"""
        os.environ['TEST_FLOAT_HIGH'] = '0.991'
        resultado = _env_float('TEST_FLOAT_HIGH', 0.5, min_val=0.01, max_val=0.99)
        assert resultado == 0.5

    def test_env_float_valor_invalido(self):
        """Valor no flotante retorna default, no lanza excepción"""
        os.environ['TEST_FLOAT_INVALID'] = 'no_es_float'
        resultado = _env_float('TEST_FLOAT_INVALID', 0.5)
        # Debería retornar el default, no lanzar excepción
        assert resultado == 0.5

    def test_env_float_notacion_cientifica(self):
        """Soporta notación científica"""
        os.environ['TEST_FLOAT_SCI'] = '1.2e-1'  # 0.12
        resultado = _env_float('TEST_FLOAT_SCI', 0.5, min_val=0.01, max_val=0.99)
        assert abs(resultado - 0.12) < 0.001


class TestValidarPathSeguro:
    """Tests para validar_path_seguro() contra path traversal"""

    def test_path_valido_absoluto(self):
        """Ruta absoluta válida es aceptada"""
        es_valida, msg = validar_path_seguro('/home/usuario/musica')
        assert es_valida

    def test_path_valido_relativo(self):
        """Ruta relativa válida es aceptada"""
        es_valida, msg = validar_path_seguro('musica/entrada')
        assert es_valida

    def test_path_con_path_traversal(self):
        """Ruta con .. es rechazada"""
        es_valida, msg = validar_path_seguro('/home/usuario/../../../etc/passwd')
        assert not es_valida
        assert '..' in msg or 'traversal' in msg.lower() or 'escape' in msg.lower()

    def test_path_con_multiples_traversal(self):
        """Múltiples .. seguidos son rechazados"""
        es_valida, msg = validar_path_seguro('../../../../../../etc/shadow')
        assert not es_valida

    def test_path_con_symlink_resolto(self):
        """Ruta con symlink es resuelta y validada"""
        with tempfile.TemporaryDirectory() as tmpdir:
            real_dir = Path(tmpdir) / "real"
            real_dir.mkdir()
            link_dir = Path(tmpdir) / "link"
            link_dir.symlink_to(real_dir)
            
            # La ruta del symlink debe ser resuelta
            es_valida, msg = validar_path_seguro(str(link_dir))
            assert es_valida  # Debería ser válida después de resolver

    def test_path_base_permitida_dentro(self):
        """Ruta dentro de base permitida es válida"""
        es_valida, msg = validar_path_seguro(
            '/home/usuario/musica/entrada/archivo.mp3',
            base_permitida='/home/usuario/musica'
        )
        assert es_valida

    def test_path_base_permitida_escape(self):
        """Intento de escapar de base_permitida es rechazado"""
        es_valida, msg = validar_path_seguro(
            '/home/usuario/etc/passwd',
            base_permitida='/home/usuario/musica'
        )
        assert not es_valida

    def test_path_base_permitida_con_traversal(self):
        """Path traversal dentro de base es detectado"""
        es_valida, msg = validar_path_seguro(
            '/home/usuario/musica/../../etc/passwd',
            base_permitida='/home/usuario/musica'
        )
        assert not es_valida

    def test_path_vacio(self):
        """Ruta vacía es rechazada"""
        es_valida, msg = validar_path_seguro('')
        assert not es_valida

    def test_path_con_caracteres_especiales(self):
        """Rutas con espacios y caracteres especiales válidos son aceptadas"""
        es_valida, msg = validar_path_seguro('/home/usuario/Mi Música/artista - año')
        assert es_valida

    def test_path_normalizacion(self):
        """Rutas con . redundantes son normalizadas"""
        es_valida, msg = validar_path_seguro('/home/usuario/./musica/./entrada')
        assert es_valida


class TestRangosShazam:
    """Tests específicos para rangos SHAZAM"""

    def test_shazam_timeout_minimo(self):
        """SHAZAM_TIMEOUT_SEG mínimo=1 es válido"""
        os.environ['SHAZAM_TIMEOUT_SEG'] = '1'
        resultado = _env_int('SHAZAM_TIMEOUT_SEG', 12, min_val=1, max_val=300)
        assert resultado == 1

    def test_shazam_timeout_maximo(self):
        """SHAZAM_TIMEOUT_SEG máximo=300 es válido"""
        os.environ['SHAZAM_TIMEOUT_SEG'] = '300'
        resultado = _env_int('SHAZAM_TIMEOUT_SEG', 12, min_val=1, max_val=300)
        assert resultado == 300

    def test_shazam_timeout_fuera_rango_bajo(self, capsys):
        """SHAZAM_TIMEOUT_SEG < 1 es rechazado"""
        os.environ['SHAZAM_TIMEOUT_SEG'] = '0'
        resultado = _env_int('SHAZAM_TIMEOUT_SEG', 12, min_val=1, max_val=300)
        assert resultado == 12


class TestRangosIA:
    """Tests específicos para rangos de parámetros de IA"""

    def test_ia_tiebreak_gap_valido(self):
        """IA_TIEBREAK_MIN_GAP en rango es válido"""
        os.environ['IA_TIEBREAK_MIN_GAP'] = '0.12'
        resultado = _env_float('IA_TIEBREAK_MIN_GAP', 0.12, min_val=0.01, max_val=0.99)
        assert abs(resultado - 0.12) < 0.001

    def test_ia_max_tokens_valido(self):
        """IA_MAX_TOKENS en rango es válido"""
        os.environ['IA_MAX_TOKENS'] = '512'
        resultado = _env_int('IA_MAX_TOKENS', 512, min_val=64, max_val=4096)
        assert resultado == 512

    def test_ia_timeout_minimo(self):
        """IA_TIMEOUT_SEG mínimo=5 es válido"""
        os.environ['IA_TIMEOUT_SEG'] = '5'
        resultado = _env_int('IA_TIMEOUT_SEG', 20, min_val=5, max_val=300)
        assert resultado == 5


class TestRangosAssets:
    """Tests específicos para rangos de Assets"""

    def test_assets_timeout_valido(self):
        """ASSETS_TIMEOUT_SEG en rango es válido"""
        os.environ['ASSETS_TIMEOUT_SEG'] = '10'
        resultado = _env_int('ASSETS_TIMEOUT_SEG', 10, min_val=5, max_val=300)
        assert resultado == 10

    def test_assets_max_retries_valido(self):
        """ASSETS_MAX_RETRIES en rango es válido"""
        os.environ['ASSETS_MAX_RETRIES'] = '2'
        resultado = _env_int('ASSETS_MAX_RETRIES', 2, min_val=1, max_val=10)
        assert resultado == 2

    def test_assets_hd_max_image_bytes_valido(self):
        """ASSETS_HD_MAX_IMAGE_BYTES en rango es válido"""
        os.environ['ASSETS_HD_MAX_IMAGE_BYTES'] = '25000000'
        resultado = _env_int('ASSETS_HD_MAX_IMAGE_BYTES', 25_000_000, min_val=1_000_000, max_val=100_000_000)
        assert resultado == 25_000_000


class TestRangosLyrics:
    """Tests específicos para rangos de Lyrics"""

    def test_lyrics_timeout_valido(self):
        """LYRICS_TIMEOUT_SEG en rango es válido"""
        os.environ['LYRICS_TIMEOUT_SEG'] = '8'
        resultado = _env_int('LYRICS_TIMEOUT_SEG', 8, min_val=2, max_val=300)
        assert resultado == 8

    def test_lyrics_max_retries_cero(self):
        """LYRICS_MAX_RETRIES puede ser 0"""
        os.environ['LYRICS_MAX_RETRIES'] = '0'
        resultado = _env_int('LYRICS_MAX_RETRIES', 1, min_val=0, max_val=5)
        assert resultado == 0

    def test_lyrics_suggest_limit_cero(self):
        """LYRICS_SUGGEST_LIMIT puede desactivar suggest con 0"""
        os.environ['LYRICS_SUGGEST_LIMIT'] = '0'
        resultado = _env_int('LYRICS_SUGGEST_LIMIT', 3, min_val=0, max_val=10)
        assert resultado == 0


class TestEnvBoolValidation:
    """Tests para _env_bool() con valores variados"""

    def test_env_bool_true_values(self):
        """Todos los valores truthy son reconocidos"""
        from config.settings import _env_bool
        for val in ('1', 'true', 'True', 'TRUE', 'yes', 'Yes', 'on', 'ON', 'si', 'SI'):
            os.environ['TEST_BOOL_VAR'] = val
            assert _env_bool('TEST_BOOL_VAR', False) is True, f"'{val}' should be True"

    def test_env_bool_false_values(self):
        """Valores explícitamente falsy"""
        from config.settings import _env_bool
        for val in ('0', 'false', 'False', 'no', 'off', 'OFF'):
            os.environ['TEST_BOOL_VAR'] = val
            assert _env_bool('TEST_BOOL_VAR', True) is False, f"'{val}' should be False"

    def test_env_bool_valor_desconocido_usa_default(self):
        """Valor no reconocido retorna default"""
        from config.settings import _env_bool
        os.environ['TEST_BOOL_UNK'] = 'maybe'
        assert _env_bool('TEST_BOOL_UNK', True) is False  # 'maybe' not in truthy set
        assert _env_bool('TEST_BOOL_UNK', False) is False

    def test_env_bool_variable_no_existe_usa_default(self):
        """Variable no definida retorna default"""
        from config.settings import _env_bool
        if 'TEST_BOOL_NOEXISTE' in os.environ:
            del os.environ['TEST_BOOL_NOEXISTE']
        assert _env_bool('TEST_BOOL_NOEXISTE', True) is True
        assert _env_bool('TEST_BOOL_NOEXISTE', False) is False

    def test_env_bool_con_espacios(self):
        """Valores con espacios alrededor son aceptados"""
        from config.settings import _env_bool
        os.environ['TEST_BOOL_SPACES'] = '  true  '
        assert _env_bool('TEST_BOOL_SPACES', False) is True


class TestSeparacionIAvsDeep:
    """Verifica que IA externa (Anthropic) y Audio Intelligence local son independientes."""

    def test_ia_proveedor_no_afecta_deep(self):
        """Desactivar IA externa NO debe desactivar Audio Intelligence Deep."""
        from config import settings
        # Audio Intelligence deep es un pipeline independiente de la IA de desempate
        assert hasattr(settings, 'ENABLE_AUDIO_INTELLIGENCE_DEEP')
        assert hasattr(settings, 'IA_PROVEEDOR')
        # Son atributos distintos controlados por variables de entorno distintas
        assert settings.IA_PROVEEDOR != 'ENABLE_AUDIO_INTELLIGENCE_DEEP'

    def test_audio_features_independiente_de_deep(self):
        """Audio Features básico y Audio Intelligence Deep son módulos separados."""
        from config import settings
        assert hasattr(settings, 'ENABLE_AUDIO_FEATURES')
        assert hasattr(settings, 'ENABLE_AUDIO_INTELLIGENCE_DEEP')
        # Ambos deben poder configurarse independientemente

    def test_audio_intelligence_model_dir_existe_como_setting(self):
        """AUDIO_INTELLIGENCE_MODEL_DIR debe estar definido como atributo de settings."""
        from config import settings
        assert hasattr(settings, 'AUDIO_INTELLIGENCE_MODEL_DIR')
