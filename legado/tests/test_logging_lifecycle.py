import logging
import os
import tempfile
import unittest
from pathlib import Path

from core.pipeline import PipelineCatalogacion
from infra import logger as logger_mod
from infra.logger import LOGGER_RAIZ, cerrar_logging, inicializar_logging, obtener_logger


class LoggingLifecycleTests(unittest.TestCase):
    def tearDown(self):
        cerrar_logging()

    def test_cerrar_logging_limpia_handlers_y_permite_reinicializar(self):
        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            dir_logs_1 = Path(td1)
            dir_logs_2 = Path(td2)

            inicializar_logging(dir_logs_1)
            obtener_logger("test").info("primera corrida")
            cerrar_logging()

            logger_raiz = logging.getLogger(LOGGER_RAIZ)
            self.assertEqual(logger_raiz.handlers, [])

            inicializar_logging(dir_logs_2)
            obtener_logger("test").info("segunda corrida")
            cerrar_logging()

            self.assertTrue((dir_logs_1 / "tagger_run.log").exists())
            self.assertTrue((dir_logs_1 / "tagger_events.jsonl").exists())
            self.assertTrue((dir_logs_2 / "tagger_run.log").exists())
            self.assertTrue((dir_logs_2 / "tagger_events.jsonl").exists())

    def test_pipeline_cierra_logging_en_retorno_temprano(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            pipeline = PipelineCatalogacion(
                directorio_entrada=base / "no_existe",
                directorio_biblioteca=base / "library",
                directorio_quarantine=base / "quarantine",
                directorio_revision=base / "review",
                directorio_logs=base / "logs",
                directorio_procesados=base / "processed",
                directorio_cache=base / "cache",
                directorio_temp=base / "temp",
            )

            resultado = pipeline.ejecutar()
            self.assertIsNotNone(resultado.timestamp_fin)
            self.assertIsNone(logger_mod._eventos_fh)
            self.assertEqual(logging.getLogger(LOGGER_RAIZ).handlers, [])

    def test_formatter_color_respeta_no_color_sin_resets_ansi(self):
        os.environ["NO_COLOR"] = "1"
        try:
            formatter = logger_mod._FormatterColor("%(levelname)s %(message)s")
            record = logging.LogRecord(
                name="nb_sound.test",
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg="mensaje",
                args=(),
                exc_info=None,
            )
            record.terminal_color = "\033[91m"

            salida = formatter.format(record)
        finally:
            os.environ.pop("NO_COLOR", None)

        self.assertEqual(salida, "INFO mensaje")
        self.assertNotIn("\033", salida)


if __name__ == "__main__":
    unittest.main()
