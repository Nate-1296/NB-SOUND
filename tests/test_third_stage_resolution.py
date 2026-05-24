from pathlib import Path

from core.third_stage import TerceraFaseResolucion
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
from external.itunes_client import ItunesTrackHint


class FakeMB:
    def __init__(self, candidatos):
        self._candidatos = candidatos

    def buscar_candidatos(self, *_args, **_kwargs):
        return self._candidatos


class FakeItunes:
    def __init__(self, hint):
        self._hint = hint

    def buscar_hint(self, *_args, **_kwargs):
        return self._hint


def _archivo():
    return ArchivoAudio(
        ruta_original=Path("/tmp/source.mp3"),
        metadata_norm=MetadataNormalizada(
            titulo="Song",
            titulo_para_match="song",
            artista_principal="Artist",
            artista_para_match="artist",
            duracion_seg=200,
        ),
        resultado_acoustid=ResultadoAcoustID(recording_ids=["rid-1"], scores=[0.95]),
    )


def test_tercera_fase_promueve_con_evidencia_fuerte():
    d = DecisionArchivo(tipo=DecisionTipo.REVISION, archivo=_archivo(), causa_revision=RevisionCausa.CANDIDATOS_AMBIGUOS)
    cand = CandidatoMB(recording_id="rid-1", release_id="rel-1", titulo_oficial="Song", artista_principal="Artist", duracion_seg=200, tipo_release="Album", isrc="USAAA1111111")
    hint = ItunesTrackHint(artist="Artist", title="Song", isrc="USAAA1111111", duration_sec=200)
    resolver = TerceraFaseResolucion(
        mb_client=FakeMB([cand]),
        itunes_client=FakeItunes(hint),
        directorio_biblioteca=Path("/tmp/lib"),
        directorio_temp=Path("/tmp/tmp"),
        writer_fn=lambda *_a, **_k: (True, None, "ok"),
    )
    finales, resumen = resolver.procesar([d])
    assert finales[0].tipo in {DecisionTipo.ACEPTADO, DecisionTipo.ACEPTADO_PROVISIONAL}
    assert resumen.promovidos == 1


def test_tercera_fase_sube_de_cuarentena_a_revision_si_hay_mejora_no_concluyente():
    d = DecisionArchivo(tipo=DecisionTipo.CUARENTENA, archivo=_archivo(), causa_cuarentena=CuarentenaCausa.PUNTAJE_BAJO)
    cand = CandidatoMB(recording_id="rid-x", release_id="rel-x", titulo_oficial="Otra", artista_principal="Artist", duracion_seg=340)
    hint = ItunesTrackHint(artist="Artist", title="Song", duration_sec=200)
    resolver = TerceraFaseResolucion(
        mb_client=FakeMB([cand]),
        itunes_client=FakeItunes(hint),
        directorio_biblioteca=Path("/tmp/lib"),
        directorio_temp=Path("/tmp/tmp"),
        writer_fn=lambda *_a, **_k: (True, None, "ok"),
    )
    finales, _ = resolver.procesar([d])
    assert finales[0].tipo == DecisionTipo.REVISION
