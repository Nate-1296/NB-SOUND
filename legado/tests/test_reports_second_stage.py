import io
import unittest
from contextlib import redirect_stdout

from domain.models import ResultadoEjecucion
from infra.reports import imprimir_resumen_consola


class ReportsSecondStageTests(unittest.TestCase):
    def test_summary_prints_initial_vs_final_counts(self):
        r = ResultadoEjecucion(
            total_descubiertos=10,
            total_aceptados=4,
            total_aceptados_provisional=1,
            total_revision=2,
            total_cuarentena=1,
            total_revision_inicial=4,
            total_cuarentena_inicial=3,
            segunda_fase_habilitada=True,
            segunda_fase_elegibles=5,
            segunda_fase_excluidos=2,
            segunda_fase_resueltos=3,
            segunda_fase_duracion_seg=1.7,
            tercera_fase_habilitada=True,
            tercera_fase_elegibles=2,
            tercera_fase_promovidos=1,
            tercera_fase_mejorados_revision=1,
            tercera_fase_sin_cambio=0,
            tercera_fase_duracion_seg=0.9,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            imprimir_resumen_consola(r)
        salida = buf.getvalue()
        self.assertIn("Fase 2 rev. inicial", salida)
        self.assertIn("Fase 3 promovidos", salida)
        self.assertIn("Revision final", salida)
        self.assertIn("Cuarentena final", salida)


if __name__ == "__main__":
    unittest.main()
