from pathlib import Path

from core.pipeline import PipelineCatalogacion


def test_crear_componente_reintentable_reintenta_y_recupera(tmp_path: Path):
    p = PipelineCatalogacion(
        directorio_entrada=tmp_path / "in",
        directorio_biblioteca=tmp_path / "lib",
        directorio_quarantine=tmp_path / "q",
        directorio_revision=tmp_path / "r",
        directorio_logs=tmp_path / "logs",
        directorio_procesados=tmp_path / "proc",
        directorio_cache=tmp_path / "cache",
        directorio_temp=tmp_path / "tmp",
    )
    intentos = {"n": 0}

    def _factory():
        intentos["n"] += 1
        if intentos["n"] < 2:
            raise RuntimeError("falla transitoria")
        return {"ok": True}

    comp = p._crear_componente_reintentable("test", _factory, _factory)
    assert comp["ok"] is True
    assert intentos["n"] >= 2
