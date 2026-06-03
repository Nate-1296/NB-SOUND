from pathlib import Path

from config import settings
from domain.models import ArchivoAudio, DecisionArchivo, DecisionTipo, CuarentenaCausa, RevisionCausa
from infra.quarantine import GestorCuarentena


def test_dry_run_quarantine_no_mueve_ni_escribe_manifest(tmp_path: Path):
    origen = tmp_path / "input" / "bad.mp3"
    origen.parent.mkdir(parents=True)
    origen.write_bytes(b"fake-mp3")

    original_dry_run = settings.DRY_RUN
    settings.DRY_RUN = True
    try:
        gestor = GestorCuarentena(
            directorio_cuarentena=tmp_path / "cuarentena",
            directorio_revision=tmp_path / "revision",
        )

        decision = DecisionArchivo(
            tipo=DecisionTipo.CUARENTENA,
            archivo=ArchivoAudio(ruta_original=origen),
            causa_cuarentena=CuarentenaCausa.PUNTAJE_BAJO,
        )

        destino = gestor.procesar_decision(decision)

        assert destino is None
        assert origen.exists()
        assert not (tmp_path / "cuarentena").exists()
    finally:
        settings.DRY_RUN = original_dry_run


def test_dry_run_revision_no_mueve_ni_escribe_manifest(tmp_path: Path):
    origen = tmp_path / "input" / "review.mp3"
    origen.parent.mkdir(parents=True)
    origen.write_bytes(b"fake-mp3")

    original_dry_run = settings.DRY_RUN
    settings.DRY_RUN = True
    try:
        gestor = GestorCuarentena(
            directorio_cuarentena=tmp_path / "cuarentena",
            directorio_revision=tmp_path / "revision",
        )

        decision = DecisionArchivo(
            tipo=DecisionTipo.REVISION,
            archivo=ArchivoAudio(ruta_original=origen),
            causa_revision=RevisionCausa.PUNTAJE_INTERMEDIO,
        )

        destino = gestor.procesar_decision(decision)

        assert destino is None
        assert origen.exists()
        assert not (tmp_path / "revision").exists()
    finally:
        settings.DRY_RUN = original_dry_run
