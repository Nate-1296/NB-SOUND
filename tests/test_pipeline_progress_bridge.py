import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from core.pipeline import PipelineCatalogacion
from domain.models import ArchivoAudio, DecisionArchivo, DecisionTipo
from servicios.importacion import _BarraProgresoBridge


class _BarraDummy:
    def __init__(self):
        self.total = None
        self.iniciada = False
        self.finalizada = False

    def set_total_archivos(self, total: int) -> None:
        self.total = total

    def iniciar(self) -> None:
        self.iniciada = True

    def actualizar_archivo(self, nombre: str, etapa: str) -> None:
        _ = (nombre, etapa)

    def registrar_resultado(self, resultado: str, duracion_archivo_seg=None) -> None:
        _ = (resultado, duracion_archivo_seg)

    def mensaje(self, texto: str, nivel: str = "info") -> None:
        _ = (texto, nivel)

    def finalizar(self) -> None:
        self.finalizada = True


class PipelineProgressBridgeTests(unittest.TestCase):
    def test_bridge_implementa_interfaz_compatible(self):
        eventos = []
        bridge = _BarraProgresoBridge(
            callback=lambda p, t, n, e: eventos.append((p, t, n, e)),
            cancelar_evento=threading.Event(),
        )
        bridge.set_total_archivos(5)
        bridge.iniciar()
        bridge.actualizar_archivo("tema.mp3", "normalizando")
        bridge.registrar_resultado("aceptado", duracion_archivo_seg=1.2)
        bridge.mensaje("ok", nivel="info")
        bridge.finalizar()

        self.assertGreaterEqual(len(eventos), 4)
        self.assertEqual(eventos[0][1], 5)
        self.assertEqual(eventos[1][2], "tema.mp3")

    def test_pipeline_respeta_barra_inyectada(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            pipeline = PipelineCatalogacion(
                directorio_entrada=base / "input",
                directorio_biblioteca=base / "library",
                directorio_quarantine=base / "quarantine",
                directorio_revision=base / "review",
                directorio_logs=base / "logs",
                directorio_procesados=base / "processed",
                directorio_cache=base / "cache",
                directorio_temp=base / "temp",
            )
            barra = _BarraDummy()
            pipeline._barra = barra

            archivo = ArchivoAudio(ruta_original=base / "input" / "track.mp3")

            with (
                patch("core.pipeline.descubrir_archivos", return_value=[archivo]),
                patch.object(
                    PipelineCatalogacion,
                    "_procesar_archivo",
                    side_effect=lambda a, r: DecisionArchivo(
                        tipo=DecisionTipo.OMITIDO,
                        archivo=a,
                        mensaje_decision="test",
                    ),
                ),
                patch.object(PipelineCatalogacion, "_ejecutar_segunda_fase", side_effect=lambda ds, r: ds),
                patch.object(PipelineCatalogacion, "_aplicar_decisiones_finales", return_value=None),
                patch("core.pipeline.imprimir_resumen_consola", return_value=None),
                patch("core.pipeline.guardar_reporte", return_value=base / "logs" / "reporte.json"),
            ):
                pipeline.ejecutar()

            self.assertTrue(barra.iniciada)
            self.assertTrue(barra.finalizada)
            self.assertEqual(barra.total, 1)


if __name__ == "__main__":
    unittest.main()
