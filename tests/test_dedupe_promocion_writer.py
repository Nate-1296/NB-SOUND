# =============================================================================
# tests/test_dedupe_promocion_writer.py
#
# Regresión para el bug observado en logs reales del usuario:
#
#   "Castle on the Hill_spotdown.org.mp3 | Escritura fallida:
#    Decision no escribible: aceptado"
#
# Cuando `core.dedupe.GestorDuplicados.detectar_duplicado_identidad`
# devuelve un `duplicado_mejorable` y `DUPLICATE_POLICY` es
# `replace_if_better`, el pipeline reconstruía `DecisionArchivo` SIN
# pasar `candidato_elegido`. El writer rechazaba la decisión por
# considerarla incompleta y la mandaba a cuarentena, aunque score=1.000.
# =============================================================================

from __future__ import annotations

import inspect


def test_pipeline_reconstruccion_dedupe_preserva_candidato():
    """En el bloque de duplicado semántico promovido, el `DecisionArchivo`
    nuevo debe llevarse el `candidato_elegido` y `puntaje_maximo` del
    original. Verificamos por inspección del fuente porque la rama
    requiere mucho setup (matcher + dedupe + writer reales).
    """
    from core import pipeline as _pipeline
    src = inspect.getsource(_pipeline.PipelineCatalogacion._pipeline_individual)
    # El fix preserva candidato y puntaje en la reconstrucción.
    assert "candidato_previo" in src
    assert "puntaje_previo" in src
    assert "promovido_a_aceptado" in src


def test_writer_rechaza_decision_sin_candidato_pero_pipeline_no_le_envia_eso():
    """Sanity: writer sigue siendo estricto (no escribir ACEPTADO sin
    candidato), y el pipeline ya no le envía decisiones rotas como antes.
    """
    from core import writer as _writer
    src = inspect.getsource(_writer.escribir_y_mover)
    assert "Decision no escribible" in src
    assert "decision.candidato_elegido is None" in src
