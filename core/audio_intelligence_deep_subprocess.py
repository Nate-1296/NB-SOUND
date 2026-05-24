"""
core/audio_intelligence_deep_subprocess.py
------------------------------------------

Adaptador thread-safe que ejecuta ``EssentiaTensorflowAnalyzer.analyze``
en un subprocess Python externo aislado del bundle PyInstaller.

Problema que resuelve
---------------------

El análisis deep carga TensorFlow + modelos `.pb` (~700 MB en memoria).
Cuando se hace en el mismo proceso que la UI Qt:

  * Las operaciones Python pre/post-procesamiento (numpy → tensor →
    numpy, normalización, persistencia) acaparan el GIL y la UI se
    congela durante segundos.

  * Si TF/Essentia tienen un fault nativo (libtensorflow.so vs libstdc++
    incompatible), todo el proceso muere.

Aislar el análisis en un subprocess elimina ambos problemas. La UI Qt
sigue respondiendo mientras el subprocess gira al 100 % de CPU; un crash
del subprocess solo afecta a la tarea actual y NB Sound puede
reintentar.

Diseño
------

* El subprocess (`infra/deep_runner.py`) corre con el Python EXTERNO del
  sistema (`infra.instalador.python_para_subprocess`) y PYTHONPATH al
  site-packages runtime. Así Essentia / TF importan con su ABI nativa.

* Una instancia ``DeepAnalyzerSubprocess`` administra UN solo subprocess
  daemon que sobrevive a varios `analyze`. Cargar TF + modelos toma
  10-15 s; pagar ese costo en cada track sería inviable, por eso el
  daemon reutiliza el estado entre llamadas.

* `analyze(track_id, file_path)` envía una línea JSON por stdin y lee
  la respuesta por stdout. Es la misma firma que la del analyzer
  in-process, por lo que `AudioIntelligenceBackgroundService` puede
  cambiarlo vía ``analyzer_factory`` sin refactorizar la cola.

* `close()` envía ``shutdown`` y espera la confirmación; si el daemon
  no responde en `_TIMEOUT_SHUTDOWN`, lo mata.

Compatibilidad
--------------

API equivalente a `EssentiaTensorflowAnalyzer`:

  * ``analyze(track_id, file_path) -> dict``
  * ``backend_available() -> tuple[bool, str]``
  * Atributos descriptivos (``model_dir``, ``backend``, …) inspeccionables
    desde la UI y los tests.

Reentrada
---------

Los métodos públicos toman ``_lock`` antes de tocar el subprocess.
El caller puede llamar ``analyze`` desde múltiples hilos sin temor a
intercalar peticiones; cada `analyze` es serializado.

Recovery
--------

Si el subprocess muere entre llamadas (OOM, SIGSEGV en TF), el siguiente
``analyze`` lo detecta (``proc.poll() != None``), lo recrea y reintenta
una vez. Si vuelve a morir, se devuelve un resultado ``failed`` con
``error_code='subprocess_crash'``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from infra.logger import obtener_logger

_log = obtener_logger("audio_intelligence_deep_subprocess")


_TIMEOUT_ANALIZAR_SEG = 600.0   # 10 min por track: razonable para CPU y modelos grandes.
_TIMEOUT_SHUTDOWN_SEG = 10.0
_TIMEOUT_READY_SEG = 30.0


@dataclass
class _ConfigAnalyzer:
    """Snapshot serializable que va al subprocess en cada `analyze`."""
    model_dir: str
    backend: str
    enable_mood_models: bool
    enable_embeddings: bool
    enable_tagging_models: bool

    def to_dict(self) -> dict:
        return {
            "model_dir": self.model_dir,
            "backend": self.backend,
            "enable_mood_models": bool(self.enable_mood_models),
            "enable_embeddings": bool(self.enable_embeddings),
            "enable_tagging_models": bool(self.enable_tagging_models),
        }


class DeepAnalyzerSubprocess:
    """Adaptador que delega `analyze` a un subprocess daemon persistente.

    Su API replica la de ``EssentiaTensorflowAnalyzer`` para que el
    backend service pueda cambiar entre los dos sin más.

    Si no se puede lanzar el subprocess (no hay Python externo, faltan
    deps, etc.) el ``analyze`` devuelve siempre el mismo error en lugar
    de propagar excepciones — la cola del backend service espera dict.
    """

    def __init__(
        self,
        model_dir: str | None = None,
        *,
        backend: str | None = None,
        enable_mood_models: bool | None = None,
        enable_embeddings: bool | None = None,
        enable_tagging_models: bool | None = None,
    ) -> None:
        from config import settings
        # `model_dir` debe ser ``Path`` (no str) para que el caller pueda
        # llamar `.exists()` directamente — la API de
        # `EssentiaTensorflowAnalyzer` que esta clase reemplaza expone
        # `model_dir` como Path. Sin esto,
        # `AudioIntelligenceBackgroundService._availability_warning`
        # explotaba con `AttributeError: 'str' has no attribute 'exists'`
        # y el deep nunca arrancaba.
        ruta_raw = (model_dir if model_dir is not None
                    else settings.AUDIO_INTELLIGENCE_MODEL_DIR or "")
        ruta_str = str(ruta_raw).strip()
        self.model_dir = Path(ruta_str).expanduser() if ruta_str else Path("")
        self.model_dir_configured = bool(ruta_str)
        self.backend = (backend if backend is not None else settings.AUDIO_INTELLIGENCE_BACKEND).strip().lower()
        self.enable_mood_models = settings.ENABLE_AUDIO_MOOD_MODELS if enable_mood_models is None else bool(enable_mood_models)
        self.enable_embeddings = settings.ENABLE_AUDIO_EMBEDDINGS if enable_embeddings is None else bool(enable_embeddings)
        self.enable_tagging_models = settings.ENABLE_AUDIO_TAGGING_MODELS if enable_tagging_models is None else bool(enable_tagging_models)

        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()
        self._cerrado = False

    def available_models(self) -> list[dict]:
        """Lista de modelos compatible con EssentiaTensorflowAnalyzer.

        En el subprocess wrapper no podemos importar Essentia para
        introspectar modelos (eso anularía el propósito de aislarlo).
        Devolvemos un resumen basado en los flags + presencia de
        archivos `.pb` en ``model_dir``. Suficiente para que
        `_availability_warning` decida si hay algo procesable.
        """
        if not self.model_dir_configured:
            return []
        try:
            base = self.model_dir
            if not base.is_dir():
                return []
            pbs = sorted(base.glob("*.pb"))
        except Exception:
            return []
        return [
            {
                "name": pb.stem,
                "path": str(pb),
                "is_available": True,
                "enabled": True,
            }
            for pb in pbs
        ]

    # ------------------------------------------------------------------
    # API compatible con EssentiaTensorflowAnalyzer
    # ------------------------------------------------------------------

    def backend_available(self) -> tuple[bool, str]:
        """Indica si el subprocess puede ejecutarse.

        No carga Essentia en el proceso de la app; solo verifica que
        haya un Python externo apto.
        """
        if self.backend in {"", "none", "disabled"}:
            return False, "backend_disabled"
        try:
            from infra.instalador import python_para_subprocess
            ejecutable, _env = python_para_subprocess()
        except Exception as exc:
            return False, f"helper_subprocess_fail: {exc}"
        if ejecutable is None:
            return False, "python_externo_no_disponible"
        return True, ""

    def analyze(self, track_id: str, audio_path: str) -> dict:
        """Envía la petición al daemon y devuelve el dict resultante.

        Errores de IPC se reportan como `analysis_status='failed'` con
        códigos específicos:

          * ``subprocess_unavailable`` → no se pudo lanzar el daemon.
          * ``subprocess_crash`` → el daemon murió durante la llamada.
          * ``subprocess_timeout`` → no respondió en el timeout.
        """
        with self._lock:
            if self._cerrado:
                return self._resultado_fallido(track_id, audio_path,
                                               "subprocess_unavailable",
                                               "El analyzer fue cerrado")
            proc = self._asegurar_proceso()
            if proc is None:
                return self._resultado_fallido(track_id, audio_path,
                                               "subprocess_unavailable",
                                               "No hay Python externo disponible")
            return self._enviar_analyze(track_id, audio_path)

    def close(self) -> None:
        """Cierra el daemon de forma ordenada. Idempotente."""
        with self._lock:
            self._cerrado = True
            proc = self._proc
            self._proc = None
        if proc is None or proc.poll() is not None:
            return
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.write(json.dumps({"action": "shutdown"}) + "\n")
                proc.stdin.flush()
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=_TIMEOUT_SHUTDOWN_SEG)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass

    def __del__(self):
        # Defensa: si alguien olvida `close()`, no dejamos un daemon
        # zombie con TF cargado consumiendo RAM.
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    def _config_snapshot(self) -> dict:
        return _ConfigAnalyzer(
            model_dir=str(self.model_dir) if self.model_dir_configured else "",
            backend=self.backend,
            enable_mood_models=self.enable_mood_models,
            enable_embeddings=self.enable_embeddings,
            enable_tagging_models=self.enable_tagging_models,
        ).to_dict()

    def _asegurar_proceso(self) -> Optional[subprocess.Popen]:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            return proc
        # Necesitamos lanzar (o relanzar). Limpiamos referencias muertas.
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            from infra.instalador import python_para_subprocess
            ejecutable, env = python_para_subprocess()
        except Exception as exc:
            _log.warning("python_para_subprocess fallo: %s", exc)
            return None
        if ejecutable is None:
            return None

        # Ejecutamos `python -m infra.deep_runner` con PYTHONPATH al
        # repo (para que el subprocess encuentre `core.audio_intelligence_deep`).
        # En frozen pasamos también el repo extraído por PyInstaller; en
        # desarrollo `sys.path[0]` es la raíz del proyecto.
        env = dict(env)
        proyecto_root = self._resolver_proyecto_root()
        if proyecto_root:
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                str(proyecto_root) + ((":" + existing) if existing and sys.platform != "win32"
                                       else ((";" + existing) if existing else ""))
            )
        cmd = [ejecutable, "-m", "infra.deep_runner"]
        kwargs: dict = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "bufsize": 1,  # line buffered
            "env": env,
        }
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        _log.info(
            "deep_runner: lanzando subprocess. ejecutable=%s PYTHONPATH=%s",
            ejecutable, env.get("PYTHONPATH", "")[:300],
        )
        try:
            proc = subprocess.Popen(cmd, **kwargs)
        except Exception as exc:
            _log.warning("No se pudo lanzar deep_runner: %s", exc)
            return None

        # Esperar la línea "ready" del daemon.
        linea = self._leer_linea(proc, timeout=_TIMEOUT_READY_SEG)
        if linea is None:
            # Si el proceso ya murió, capturamos stderr para diagnosticar
            # qué falló en el import. Sin esto, "subprocess_unavailable"
            # es opaco: no sabemos si fue ModuleNotFoundError, ImportError
            # de torch, o cualquier otra cosa.
            try:
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
            try:
                stderr = (proc.stderr.read() or "")[-2000:] if proc.stderr else ""
            except Exception:
                stderr = ""
            _log.error(
                "deep_runner no respondió 'ready' en %ds. returncode=%s stderr=%s",
                int(_TIMEOUT_READY_SEG), proc.returncode, stderr,
            )
            return None
        try:
            msg = json.loads(linea)
            if msg.get("event") != "ready":
                _log.debug("deep_runner respondió: %s", msg)
        except Exception:
            _log.debug("deep_runner línea inicial inesperada: %s", linea[:200])

        self._proc = proc
        return proc

    def _enviar_analyze(self, track_id: str, audio_path: str) -> dict:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            # Intento de recovery (1 vez).
            proc = self._asegurar_proceso()
            if proc is None:
                return self._resultado_fallido(track_id, audio_path,
                                               "subprocess_unavailable",
                                               "No se pudo relanzar el daemon")
        payload = {
            "action": "analyze",
            "track_id": str(track_id),
            "file_path": str(audio_path),
            "config": self._config_snapshot(),
        }
        try:
            assert proc.stdin is not None
            proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            proc.stdin.flush()
        except Exception as exc:
            _log.warning("deep_runner stdin write fallo: %s", exc)
            # Subprocess murió mientras enviamos. Reintento limpio (1 vez).
            self._matar_proceso()
            return self._reintentar_analyze(track_id, audio_path)

        linea = self._leer_linea(proc, timeout=_TIMEOUT_ANALIZAR_SEG)
        if linea is None:
            self._matar_proceso()
            return self._resultado_fallido(track_id, audio_path,
                                           "subprocess_timeout",
                                           "El daemon no respondió a tiempo")
        try:
            return json.loads(linea)
        except Exception as exc:
            _log.warning("deep_runner respuesta inválida: %s", exc)
            return self._resultado_fallido(track_id, audio_path,
                                           "subprocess_bad_response",
                                           f"JSON inválido: {exc}")

    def _reintentar_analyze(self, track_id: str, audio_path: str) -> dict:
        proc = self._asegurar_proceso()
        if proc is None:
            return self._resultado_fallido(track_id, audio_path,
                                           "subprocess_crash",
                                           "Daemon murió y no se pudo relanzar")
        # Intento limpio una vez sin recursión adicional para evitar loops.
        try:
            assert proc.stdin is not None
            proc.stdin.write(json.dumps({
                "action": "analyze",
                "track_id": str(track_id),
                "file_path": str(audio_path),
                "config": self._config_snapshot(),
            }, ensure_ascii=False) + "\n")
            proc.stdin.flush()
        except Exception as exc:
            return self._resultado_fallido(track_id, audio_path,
                                           "subprocess_crash",
                                           f"Daemon crashed: {exc}")
        linea = self._leer_linea(proc, timeout=_TIMEOUT_ANALIZAR_SEG)
        if linea is None:
            return self._resultado_fallido(track_id, audio_path,
                                           "subprocess_timeout",
                                           "Timeout en reintento")
        try:
            return json.loads(linea)
        except Exception:
            return self._resultado_fallido(track_id, audio_path,
                                           "subprocess_bad_response",
                                           "JSON inválido en reintento")

    def _leer_linea(self, proc: subprocess.Popen, *, timeout: float) -> Optional[str]:
        """Lee una línea de stdout respetando un timeout total.

        Implementación simple: ``readline()`` bloqueante pero con
        verificación periódica del estado del proceso. No usamos
        `select` directamente porque no funciona con pipes en Windows.
        """
        inicio = time.monotonic()
        # Si el proceso ya murió antes de leer, devolvemos None inmediato.
        if proc.stdout is None:
            return None

        # Hilo lector con timeout vía Event. Es portable y simple.
        resultado: list = [None]
        evento_listo = threading.Event()

        def _leer():
            try:
                resultado[0] = proc.stdout.readline()
            except Exception:
                resultado[0] = None
            finally:
                evento_listo.set()

        hilo = threading.Thread(target=_leer, daemon=True)
        hilo.start()
        if not evento_listo.wait(timeout=timeout):
            return None
        linea = resultado[0]
        if not linea:
            return None
        return linea.strip()

    def _matar_proceso(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            proc.kill()
        except Exception:
            pass

    @staticmethod
    def _resultado_fallido(track_id: str, file_path: str, code: str, msg: str) -> dict:
        return {
            "track_id": str(track_id),
            "file_path": str(file_path),
            "analysis_status": "failed",
            "error_code": code,
            "error_message": msg[:500],
        }

    @staticmethod
    def _resolver_proyecto_root() -> Optional[Path]:
        """Carpeta que contiene `infra/deep_runner.py`.

        En desarrollo: la raíz del repo (subiendo desde este módulo).
        En bundle PyInstaller: ``sys._MEIPASS`` (datos del bundle).
        """
        try:
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass and (Path(meipass) / "infra" / "deep_runner.py").exists():
                return Path(meipass)
        except Exception:
            pass
        aqui = Path(__file__).resolve()
        candidato = aqui.parent.parent
        if (candidato / "infra" / "deep_runner.py").exists():
            return candidato
        return None
