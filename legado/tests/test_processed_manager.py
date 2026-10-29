import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from config import settings
from domain.models import DecisionTipo
from infra.processed import GestorProcesados


class ProcessedManagerTests(unittest.TestCase):
    def test_archivar_mueve_archivo_a_subcarpeta_por_decision(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            origen = base / "entrada" / "track.mp3"
            origen.parent.mkdir(parents=True, exist_ok=True)
            origen.write_bytes(b"fake-mp3")

            gestor = GestorProcesados(base / "procesados")
            ruta_final = gestor.archivar(origen, DecisionTipo.ACEPTADO)

            self.assertIsNotNone(ruta_final)
            self.assertFalse(origen.exists())
            self.assertTrue((base / "procesados" / "aceptado" / "track.mp3").exists())

    def test_archivar_resuelve_conflictos_de_nombre(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            carpeta = base / "procesados" / "aceptado"
            carpeta.mkdir(parents=True, exist_ok=True)
            (carpeta / "track.mp3").write_bytes(b"existente")

            origen = base / "entrada" / "track.mp3"
            origen.parent.mkdir(parents=True, exist_ok=True)
            origen.write_bytes(b"nuevo")

            gestor = GestorProcesados(base / "procesados")
            ruta_final = gestor.archivar(origen, DecisionTipo.ACEPTADO)

            self.assertEqual(ruta_final.name, "track_2.mp3")
            self.assertTrue((carpeta / "track.mp3").exists())
            self.assertTrue((carpeta / "track_2.mp3").exists())

    def test_archivar_respeta_dry_run_y_no_mueve(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            origen = base / "entrada" / "track.mp3"
            origen.parent.mkdir(parents=True, exist_ok=True)
            origen.write_bytes(b"fake-mp3")

            original_dry_run = settings.DRY_RUN
            settings.DRY_RUN = True
            try:
                gestor = GestorProcesados(base / "procesados")
                ruta_final = gestor.archivar(origen, DecisionTipo.ACEPTADO)

                self.assertIsNone(ruta_final)
                self.assertTrue(origen.exists())
                self.assertFalse((base / "procesados").exists())
            finally:
                settings.DRY_RUN = original_dry_run


if __name__ == "__main__":
    unittest.main()
