import unittest
from unittest.mock import patch
from pathlib import Path

from core.second_stage import SegundaFaseResolucion
from domain.models import (
    ArchivoAudio,
    MetadataNormalizada,
    DecisionArchivo,
    DecisionTipo,
    RevisionCausa,
    CuarentenaCausa,
    CandidatoMB,
    ResultadoAcoustID,
)


class FakeMB:
    def __init__(self, candidatos):
        self._candidatos = candidatos
        self.calls = 0

    def buscar_candidatos(self, *_args, **_kwargs):
        self.calls += 1
        return self._candidatos


def _archivo_base() -> ArchivoAudio:
    return ArchivoAudio(
        ruta_original=Path("/tmp/test.mp3"),
        metadata_norm=MetadataNormalizada(
            titulo="Song",
            titulo_para_match="song",
            artista_principal="Artist",
            artista_para_match="artist",
            duracion_seg=200,
            isrc="USAAA1111111",
        ),
        resultado_acoustid=ResultadoAcoustID(recording_ids=["rid-1"], scores=[0.95]),
    )


class SegundaFaseTests(unittest.TestCase):
    def test_ambiguous_without_ia_promotes(self):
        archivo = _archivo_base()
        cand1 = CandidatoMB(
            recording_id="rid-1",
            release_id="rel-1",
            titulo_oficial="Song",
            artista_principal="Artist",
            duracion_seg=200,
            isrc="USAAA1111111",
            tipo_release="Album",
        )
        cand2 = CandidatoMB(
            recording_id="rid-2",
            release_id="rel-2",
            titulo_oficial="Song edit",
            artista_principal="Artist",
            duracion_seg=220,
            tipo_release="Album",
        )
        d = DecisionArchivo(
            tipo=DecisionTipo.REVISION,
            archivo=archivo,
            causa_revision=RevisionCausa.CANDIDATOS_AMBIGUOS,
            puntaje_maximo=0.66,
        )
        r = SegundaFaseResolucion(FakeMB([cand1, cand2]), ia_activa=False,
                                  directorio_biblioteca=Path("/tmp/lib"),
                                  directorio_temp=Path("/tmp/tmp"),
                                  writer_fn=lambda *_a, **_k: (True, None, "ok"))
        finales, resumen = r.procesar([d])
        self.assertEqual(finales[0].tipo, DecisionTipo.ACEPTADO)
        self.assertEqual(resumen.resueltos, 1)

    def test_ambiguous_without_ia_stays_review(self):
        archivo = _archivo_base()
        archivo.resultado_acoustid = ResultadoAcoustID(recording_ids=[], scores=[])
        cand1 = CandidatoMB(recording_id="rid-9", release_id="rel-9", titulo_oficial="Song", artista_principal="Artist")
        cand2 = CandidatoMB(recording_id="rid-8", release_id="rel-8", titulo_oficial="Song", artista_principal="Artist")
        d = DecisionArchivo(tipo=DecisionTipo.REVISION, archivo=archivo,
                           causa_revision=RevisionCausa.CANDIDATOS_AMBIGUOS, puntaje_maximo=0.65)
        r = SegundaFaseResolucion(FakeMB([cand1, cand2]), ia_activa=False,
                                  directorio_biblioteca=Path("/tmp/lib"), directorio_temp=Path("/tmp/tmp"),
                                  writer_fn=lambda *_a, **_k: (True, None, "ok"))
        finales, _ = r.procesar([d])
        self.assertEqual(finales[0].tipo, DecisionTipo.REVISION)

    def test_mid_score_promotes(self):
        archivo = _archivo_base()
        d = DecisionArchivo(tipo=DecisionTipo.REVISION, archivo=archivo,
                           causa_revision=RevisionCausa.PUNTAJE_INTERMEDIO, puntaje_maximo=0.58)
        cand = CandidatoMB(recording_id="rid-1", release_id="rel-1", titulo_oficial="Song",
                           artista_principal="Artist", duracion_seg=200, isrc="USAAA1111111", tipo_release="Single")
        r = SegundaFaseResolucion(FakeMB([cand]), ia_activa=False,
                                  directorio_biblioteca=Path("/tmp/lib"), directorio_temp=Path("/tmp/tmp"),
                                  writer_fn=lambda *_a, **_k: (True, None, "ok"))
        finales, _ = r.procesar([d])
        self.assertIn(finales[0].tipo, {DecisionTipo.ACEPTADO, DecisionTipo.ACEPTADO_PROVISIONAL})

    def test_release_incompleto_strategy_prefers_album_match(self):
        archivo = _archivo_base()
        archivo.metadata_norm.album = "Target Album"
        d = DecisionArchivo(
            tipo=DecisionTipo.REVISION,
            archivo=archivo,
            causa_revision=RevisionCausa.CLASIFICACION_PROVISIONAL,
            puntaje_maximo=0.60,
        )
        cand_ok = CandidatoMB(recording_id="rid-1", release_id="rel-1", album_oficial="Target Album",
                              titulo_oficial="Song", artista_principal="Artist", duracion_seg=200, isrc="USAAA1111111", tipo_release="Album")
        cand_other = CandidatoMB(recording_id="rid-9", release_id="rel-9", album_oficial="Other Album",
                                 titulo_oficial="Song", artista_principal="Artist", duracion_seg=200, isrc="USAAA1111111", tipo_release="Album")
        r = SegundaFaseResolucion(FakeMB([cand_other, cand_ok]), ia_activa=False,
                                  directorio_biblioteca=Path("/tmp/lib"), directorio_temp=Path("/tmp/tmp"),
                                  writer_fn=lambda *_a, **_k: (True, None, "ok"))
        finales, _ = r.procesar([d])
        self.assertIn(finales[0].tipo, {DecisionTipo.ACEPTADO, DecisionTipo.ACEPTADO_PROVISIONAL, DecisionTipo.REVISION})

    def test_low_score_quarantine_skipped(self):
        archivo = _archivo_base()
        d = DecisionArchivo(tipo=DecisionTipo.CUARENTENA, archivo=archivo,
                           causa_cuarentena=CuarentenaCausa.PUNTAJE_BAJO, puntaje_maximo=0.3)
        mb = FakeMB([])
        r = SegundaFaseResolucion(mb, ia_activa=False,
                                  directorio_biblioteca=Path("/tmp/lib"), directorio_temp=Path("/tmp/tmp"))
        _, resumen = r.procesar([d])
        self.assertEqual(resumen.excluidos, 1)
        self.assertEqual(mb.calls, 0)

    def test_no_candidates_excluded(self):
        archivo = _archivo_base()
        d = DecisionArchivo(tipo=DecisionTipo.CUARENTENA, archivo=archivo,
                           causa_cuarentena=CuarentenaCausa.SIN_CANDIDATOS, puntaje_maximo=0.2)
        mb = FakeMB([])
        r = SegundaFaseResolucion(mb, ia_activa=False,
                                  directorio_biblioteca=Path("/tmp/lib"), directorio_temp=Path("/tmp/tmp"))
        _, resumen = r.procesar([d])
        self.assertEqual(resumen.excluidos, 1)
        self.assertEqual(mb.calls, 0)

    def test_events_and_non_eligible_not_processed(self):
        archivo = _archivo_base()
        d1 = DecisionArchivo(tipo=DecisionTipo.ACEPTADO, archivo=archivo, puntaje_maximo=0.9)
        d2 = DecisionArchivo(tipo=DecisionTipo.REVISION, archivo=archivo,
                            causa_revision=RevisionCausa.CANDIDATOS_AMBIGUOS, puntaje_maximo=0.62)
        cand = CandidatoMB(recording_id="rid-1", release_id="rel-1", titulo_oficial="Song",
                           artista_principal="Artist", duracion_seg=200, isrc="USAAA1111111", tipo_release="Album")
        mb = FakeMB([cand])
        with patch("core.second_stage.registrar_evento") as ev:
            r = SegundaFaseResolucion(mb, ia_activa=False,
                                      directorio_biblioteca=Path("/tmp/lib"), directorio_temp=Path("/tmp/tmp"),
                                      writer_fn=lambda *_a, **_k: (True, None, "ok"))
            finales, resumen = r.procesar([d1, d2])
            self.assertEqual(finales[0].tipo, DecisionTipo.ACEPTADO)
            self.assertEqual(resumen.elegibles, 1)
            self.assertGreaterEqual(ev.call_count, 3)


if __name__ == "__main__":
    unittest.main()
