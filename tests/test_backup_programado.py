# =============================================================================
# tests/test_backup_programado.py
#
# #8b — Copia de seguridad programada. La decisión "¿toca crear una copia?" es
# una función pura (`servicios.backup.backup_programado_vencido`) y se prueba
# aquí de forma aislada, sin Qt ni audio.
# =============================================================================

from datetime import datetime, timedelta, timezone

import pytest

from servicios.backup import (
    ahora_utc_iso,
    backup_programado_vencido,
    _parsear_iso_utc,
)

AHORA = datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)


# ── Desactivado ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("frecuencia", [0, -1, -30])
def test_desactivado_nunca_vence(frecuencia):
    # Aunque nunca se haya respaldado, frecuencia <= 0 no programa nada.
    assert backup_programado_vencido(frecuencia, "", AHORA) is False
    assert backup_programado_vencido(frecuencia, None, AHORA) is False


# ── Nunca se respaldó ────────────────────────────────────────────────────────

@pytest.mark.parametrize("ultimo", ["", None, "   ", "no-es-fecha"])
def test_sin_marca_previa_vence(ultimo):
    assert backup_programado_vencido(7, ultimo, AHORA) is True


# ── Límite exacto del periodo ────────────────────────────────────────────────

def test_justo_antes_del_plazo_no_vence():
    ultimo = (AHORA - timedelta(days=7) + timedelta(seconds=1)).isoformat()
    assert backup_programado_vencido(7, ultimo, AHORA) is False


def test_exactamente_en_el_plazo_vence():
    ultimo = (AHORA - timedelta(days=7)).isoformat()
    assert backup_programado_vencido(7, ultimo, AHORA) is True


def test_pasado_el_plazo_vence():
    ultimo = (AHORA - timedelta(days=40)).isoformat()
    assert backup_programado_vencido(30, ultimo, AHORA) is True


def test_dentro_del_plazo_no_vence():
    ultimo = (AHORA - timedelta(days=3)).isoformat()
    assert backup_programado_vencido(7, ultimo, AHORA) is False


# ── Formatos de fecha aceptados ──────────────────────────────────────────────

def test_acepta_formato_canonico_con_z():
    # Formato que escribe ahora_utc_iso(): "...T...Z".
    ultimo = "2026-05-01T00:00:00Z"
    assert backup_programado_vencido(7, ultimo, AHORA) is True


def test_marca_sin_zona_se_interpreta_utc():
    # Sin tzinfo: se asume UTC (no debe lanzar por restar naive y aware).
    ultimo = (AHORA - timedelta(days=10)).replace(tzinfo=None).isoformat()
    assert backup_programado_vencido(7, ultimo, AHORA) is True


def test_ahora_naive_se_interpreta_utc():
    # `ahora` naive tampoco debe romper la resta.
    ahora_naive = AHORA.replace(tzinfo=None)
    ultimo = "2026-05-01T00:00:00Z"
    assert backup_programado_vencido(7, ultimo, ahora_naive) is True


def test_marca_con_offset_se_normaliza_a_utc():
    # 09:00 en -03:00 == 12:00 UTC; con frecuencia 1 día y "ahora" 24h después.
    ultimo = "2026-06-01T09:00:00-03:00"  # = 2026-06-01T12:00:00Z
    ahora = datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)
    assert backup_programado_vencido(1, ultimo, ahora) is True
    ahora_justo_antes = datetime(2026, 6, 2, 11, 59, 59, tzinfo=timezone.utc)
    assert backup_programado_vencido(1, ultimo, ahora_justo_antes) is False


# ── Helpers ──────────────────────────────────────────────────────────────────

def test_ahora_utc_iso_es_parseable_y_redondo():
    iso = ahora_utc_iso()
    assert iso.endswith("Z")
    dt = _parsear_iso_utc(iso)
    assert dt is not None and dt.tzinfo is not None


def test_parsear_iso_invalido_devuelve_none():
    assert _parsear_iso_utc("") is None
    assert _parsear_iso_utc(None) is None
    assert _parsear_iso_utc("basura") is None


def test_ciclo_completo_con_marca_recien_creada():
    # Recién respaldado → no vence todavía para ninguna frecuencia razonable.
    iso = ahora_utc_iso()
    assert backup_programado_vencido(1, iso) is False
    assert backup_programado_vencido(30, iso) is False
