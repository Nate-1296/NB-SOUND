from pathlib import Path
from tempfile import TemporaryDirectory

import core.pipeline as pipeline_module
from db.conexion import inicializar_db, cerrar_db
from core.overrides import MemoriaOverrides
from core.overrides import OverrideResult
from core.manifests import GestorManifests
from domain.models import ArchivoAudio, MetadataNormalizada, DecisionArchivo, DecisionTipo, CandidatoMB


def test_override_lookup_and_upsert():
    with TemporaryDirectory() as td:
        inicializar_db(Path(td) / "test.db")
        mem = MemoriaOverrides()
        mem.guardar("artist_title", "artist::song", {"recording_id": "rid-1"}, reason="manual")

        archivo = ArchivoAudio(ruta_original=Path("/tmp/a.mp3"), hash_sha256="h")
        norm = MetadataNormalizada(artista_principal="Artist", titulo="Song")
        ov = mem.buscar_para(archivo, norm)
        assert ov is not None
        assert ov.payload["recording_id"] == "rid-1"
        cerrar_db()


def test_override_payload_validation_and_candidate():
    assert MemoriaOverrides.validar_payload({"recording_id": "rid-x"}) is True
    assert MemoriaOverrides.validar_payload({}) is False
    assert MemoriaOverrides.candidato_desde_payload({}) is None
    cand = MemoriaOverrides.candidato_desde_payload({"recording_id": "rid-x", "artista_principal": "A", "titulo_oficial": "T"})
    assert cand is not None
    assert cand.recording_id == "rid-x"


def test_manifests_track_album_artist_written_and_explain():
    with TemporaryDirectory() as td:
        inicializar_db(Path(td) / "test.db")
        gm = GestorManifests(Path(td) / "manifests")
        archivo = ArchivoAudio(ruta_original=Path("/tmp/a.mp3"), hash_sha256="hash-1")
        cand = CandidatoMB(recording_id="rid", release_id="rel", release_group_id="rg", artista_principal="Art", titulo_oficial="Tit", album_oficial="Alb")
        d = DecisionArchivo(tipo=DecisionTipo.ACEPTADO, archivo=archivo, candidato_elegido=cand, puntaje_maximo=0.9)
        d.ruta_destino = Path("/music/Art/albums/Alb/01_tit.mp3")
        gm.escribir_decision(d)

        tracks = list((Path(td) / "manifests" / "tracks").glob("*.json"))
        assert tracks
        key = tracks[0].stem
        assert gm.explicar(key)
        cerrar_db()


def test_track_id_prioriza_identidad_semantica():
    with TemporaryDirectory() as td:
        inicializar_db(Path(td) / "test.db")
        gm = GestorManifests(Path(td) / "manifests")
        archivo = ArchivoAudio(ruta_original=Path("/tmp/a.mp3"), hash_sha256="h1")
        cand = CandidatoMB(
            recording_id="rid-semantic",
            release_id="rel-x",
            artista_principal="Art",
            titulo_oficial="Tit",
            album_oficial="Alb",
            isrc="USAAA1111111",
        )
        d = DecisionArchivo(tipo=DecisionTipo.ACEPTADO, archivo=archivo, candidato_elegido=cand)
        d.ruta_destino = Path("/music/Art/albums/Alb/01_tit.mp3")
        gm.escribir_decision(d)
        track_manifest = list((Path(td) / "manifests" / "tracks").glob("*.json"))[0]
        data = __import__("json").loads(track_manifest.read_text(encoding="utf-8"))
        assert data["track_id"].startswith("rec:")
        assert data["track_id_legacy"]
        cerrar_db()


def test_pipeline_override_invalido_va_a_revision(monkeypatch):
    with TemporaryDirectory() as td:
        inicializar_db(Path(td) / "test.db")
        pipeline = pipeline_module.PipelineCatalogacion(
            directorio_entrada=Path(td) / "in",
            directorio_biblioteca=Path(td) / "library",
            directorio_quarantine=Path(td) / "quarantine",
            directorio_revision=Path(td) / "review",
            directorio_logs=Path(td) / "logs",
            directorio_procesados=Path(td) / "processed",
            directorio_cache=Path(td) / "cache",
            directorio_temp=Path(td) / "temp",
        )
        pipeline._acoustid._activo = False
        pipeline._shazam._activo = False

        monkeypatch.setattr(pipeline_module, "ENABLE_DEDUPLICATION", False)
        monkeypatch.setattr(pipeline_module, "validar_archivo", lambda _: (True, None))

        def _normalizar_ok(archivo):
            archivo.metadata_norm = MetadataNormalizada(
                titulo="Song",
                titulo_para_match="song",
                artista_principal="Artist",
                artista_para_match="artist",
            )
            return True, None

        monkeypatch.setattr(pipeline_module, "normalizar_metadata", _normalizar_ok)
        monkeypatch.setattr(
            pipeline._overrides,
            "buscar_para",
            lambda *_: OverrideResult(
                key="artist::song",
                match_type="artist_title",
                payload={},
                reason="invalid-payload",
                source="test",
            ),
        )

        resultado = pipeline_module.ResultadoEjecucion()
        archivo = ArchivoAudio(ruta_original=Path(td) / "input.mp3")
        decision = pipeline._pipeline_individual(archivo, resultado)

        assert decision.tipo == DecisionTipo.REVISION
        assert decision.causa_revision == pipeline_module.RevisionCausa.CANDIDATOS_AMBIGUOS
        assert decision.override_aplicado is not None
        assert decision.override_aplicado["valid"] is False
        cerrar_db()


def test_pipeline_cierra_promociones_de_fase(monkeypatch):
    with TemporaryDirectory() as td:
        inicializar_db(Path(td) / "test.db")
        pipeline = pipeline_module.PipelineCatalogacion(
            directorio_entrada=Path(td) / "in",
            directorio_biblioteca=Path(td) / "library",
            directorio_quarantine=Path(td) / "quarantine",
            directorio_revision=Path(td) / "review",
            directorio_logs=Path(td) / "logs",
            directorio_procesados=Path(td) / "processed",
            directorio_cache=Path(td) / "cache",
            directorio_temp=Path(td) / "temp",
        )
        archivo = ArchivoAudio(ruta_original=Path(td) / "input.mp3")
        decision = DecisionArchivo(
            tipo=DecisionTipo.REVISION,
            archivo=archivo,
            candidato_elegido=CandidatoMB(
                recording_id="rid",
                release_id="rel",
                artista_principal="Art",
                titulo_oficial="Tit",
            ),
        )
        tipos_entrada = {id(decision): DecisionTipo.REVISION}
        decision.tipo = DecisionTipo.ACEPTADO

        llamadas = []
        monkeypatch.setattr(
            pipeline,
            "_post_aceptacion_materializada",
            lambda d, n: llamadas.append((d, n)),
        )

        pipeline._cerrar_promociones_de_fase([decision], tipos_entrada, "fase_2")

        assert llamadas == [(decision, "input.mp3")]
        assert decision.esquema_explicacion["resolution_phase"] == "fase_2"
        cerrar_db()


def test_post_aceptacion_escribe_manifest_si_no_hay_sidecars(monkeypatch):
    with TemporaryDirectory() as td:
        inicializar_db(Path(td) / "test.db")
        pipeline = pipeline_module.PipelineCatalogacion(
            directorio_entrada=Path(td) / "in",
            directorio_biblioteca=Path(td) / "library",
            directorio_quarantine=Path(td) / "quarantine",
            directorio_revision=Path(td) / "review",
            directorio_logs=Path(td) / "logs",
            directorio_procesados=Path(td) / "processed",
            directorio_cache=Path(td) / "cache",
            directorio_temp=Path(td) / "temp",
        )
        pipeline._assets = None
        pipeline._enrichment = None
        monkeypatch.setattr(pipeline._dedupe, "registrar_identidad_aceptada", lambda *_: None)

        archivo = ArchivoAudio(ruta_original=Path(td) / "input.mp3", hash_sha256="h")
        decision = DecisionArchivo(
            tipo=DecisionTipo.ACEPTADO,
            archivo=archivo,
            candidato_elegido=CandidatoMB(
                recording_id="rid",
                release_id="rel",
                artista_principal="Art",
                titulo_oficial="Tit",
                album_oficial="Alb",
            ),
        )
        decision.ruta_destino = Path(td) / "library" / "01_tit.mp3"

        pipeline._post_aceptacion_materializada(decision, "input.mp3")

        data = pipeline._manifests.explicar("rec:rid")
        assert data
        assert data["explain"]["sidecars"]["assets"]["status"] == "disabled"
        assert data["explain"]["sidecars"]["enrichment"]["status"] == "disabled"
        assert data["explain"]["sidecars"]["manifest"]["status"] == "saved"
        cerrar_db()
