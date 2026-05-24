#!/usr/bin/env python3
"""
infra/deep_runner.py
--------------------
CLI daemon que ejecuta análisis profundo (Essentia/TensorFlow) en un
**subprocess separado del bundle principal de NB Sound**.

Motivación
----------
TensorFlow y Essentia, al cargarse en el mismo proceso que la UI Qt,
acaparan el GIL durante el pre/post-procesamiento Python y producen
trabas perceptibles en la interfaz (especialmente al iniciar). Aislar
todo el análisis deep en un subprocess elimina ese acoplamiento: la UI
sigue respondiendo siempre, sin importar lo que esté haciendo el motor.

Protocolo
---------
El daemon lee de stdin **una línea JSON por petición** y responde con
**una línea JSON** en stdout. Líneas reconocidas:

* ``{"action": "analyze", "track_id": "...", "file_path": "...", "config": {...}}``
  → ejecuta ``EssentiaTensorflowAnalyzer.analyze`` y devuelve el dict
  con el resultado completo. Si ``config`` cambia respecto al ciclo
  anterior, reconstruye el analyzer (poco común: la config es estable
  dentro de una run).

* ``{"action": "shutdown"}`` → cierra el daemon limpiamente.

* ``{"action": "ping"}`` → devuelve ``{"ok": true, "alive": true}`` sin
  cargar nada. Útil para sondeos de salud.

Errores de carga de Essentia/TF no abortan el daemon: se reportan en la
respuesta JSON con ``analysis_status="failed"`` y un código apropiado,
para que el caller pueda decidir si reintenta o pasa a otro track.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Optional


def _imprimir(payload: dict) -> None:
    """Escribe una línea JSON a stdout y la flushea. ``flush`` es
    obligatorio: el caller lee línea por línea y no debe quedarse
    bloqueado en un buffer del SO."""
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _construir_analyzer(config: dict):
    """Importa Essentia perezosamente y construye el analyzer.

    El import puede demorar segundos la primera vez (carga
    libtensorflow.so y los modelos .pb que el spec declare). Por eso
    queda fuera del módulo: solo se ejecuta cuando el daemon recibe
    el primer ``analyze``.
    """
    from core.audio_intelligence_deep import EssentiaTensorflowAnalyzer
    return EssentiaTensorflowAnalyzer(
        model_dir=config.get("model_dir") or "",
        backend=config.get("backend") or "",
        enable_mood_models=config.get("enable_mood_models"),
        enable_embeddings=config.get("enable_embeddings"),
        enable_tagging_models=config.get("enable_tagging_models"),
    )


def _config_iguales(a: Optional[dict], b: Optional[dict]) -> bool:
    if a is None or b is None:
        return False
    claves = (
        "model_dir", "backend", "enable_mood_models",
        "enable_embeddings", "enable_tagging_models",
    )
    return all(a.get(k) == b.get(k) for k in claves)


def main() -> int:
    analyzer = None
    config_actual: Optional[dict] = None
    _imprimir({"event": "ready"})

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            mensaje = json.loads(raw)
        except json.JSONDecodeError as exc:
            _imprimir({"event": "error", "error": f"json decode: {exc}"})
            continue

        accion = mensaje.get("action")
        if accion == "shutdown":
            _imprimir({"event": "shutdown_ack"})
            return 0
        if accion == "ping":
            _imprimir({"ok": True, "alive": True})
            continue
        if accion != "analyze":
            _imprimir({"event": "error", "error": f"accion desconocida: {accion}"})
            continue

        track_id = str(mensaje.get("track_id") or "")
        file_path = str(mensaje.get("file_path") or "")
        config = mensaje.get("config") or {}

        # Reconstruir analyzer solo si la config cambió (común: 1 sola
        # config por run, así que el primer analyze paga la carga de TF
        # y los siguientes reutilizan).
        if analyzer is None or not _config_iguales(config_actual, config):
            try:
                analyzer = _construir_analyzer(config)
                config_actual = config
            except Exception as exc:
                _imprimir({
                    "track_id": track_id,
                    "file_path": file_path,
                    "analysis_status": "failed",
                    "error_code": "analyzer_init_failed",
                    "error_message": f"No se pudo inicializar el analyzer: {exc}",
                    "traceback": traceback.format_exc()[-1000:],
                })
                continue

        try:
            resultado = analyzer.analyze(track_id, file_path)
        except Exception as exc:
            _imprimir({
                "track_id": track_id,
                "file_path": file_path,
                "analysis_status": "failed",
                "error_code": "analyze_exception",
                "error_message": str(exc)[:500],
                "traceback": traceback.format_exc()[-1000:],
            })
            continue

        # `analyze` devuelve un dict listo para persistir; lo dejamos
        # pasar tal cual. El caller decide qué columnas guardar.
        if not isinstance(resultado, dict):
            resultado = {
                "track_id": track_id,
                "file_path": file_path,
                "analysis_status": "failed",
                "error_code": "bad_result_type",
                "error_message": f"analyzer devolvió {type(resultado).__name__}",
            }
        _imprimir(resultado)

    return 0


if __name__ == "__main__":
    # Aseguramos que stdin/stdout vivan en modo línea: si el bundle PyInstaller
    # nos ejecuta como hijo, podría haber buffering distinto al esperado.
    try:
        sys.stdin.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main())
