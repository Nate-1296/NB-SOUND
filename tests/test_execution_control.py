import json
from pathlib import Path

from infra.execution_control import ControlEjecucion


def test_control_ejecucion_persistencia_basica(tmp_path: Path):
    ruta = tmp_path / "run_state.json"
    c = ControlEjecucion(ruta)
    c.checkpoint(total_descubiertos=10, procesados=3, current_file="a.mp3", current_stage="validando")
    c.pausar("test")
    c.reanudar()
    c.registrar_operacion("move", tmp_path / "in.mp3", tmp_path / "out.mp3")
    c.cerrar("completed")

    data = ruta.read_text(encoding="utf-8")
    assert "\"status\": \"completed\"" in data
    assert "\"total_descubiertos\": 10" in data
    assert "\"procesados\": 3" in data
    assert "\"operaciones\"" in data


def test_control_ejecucion_limpia_eta_y_extras(tmp_path: Path):
    ruta = tmp_path / "run_state.json"
    control = ControlEjecucion(ruta)

    control.checkpoint(
        eta_seconds=12.5,
        phase_eta_seconds=3.0,
        elapsed_seconds=1.0,
        extras={"assets": {"pending": 1}},
    )
    control.checkpoint(eta_seconds=None, phase_eta_seconds=None, extras=None)

    data = json.loads(ruta.read_text(encoding="utf-8"))
    assert data["eta_seconds"] is None
    assert data["phase_eta_seconds"] is None
    assert data["extras"] == {}


def test_control_ejecucion_persistencia_atomica_usa_replace(tmp_path: Path, monkeypatch):
    ruta = tmp_path / "run_state.json"
    llamadas_replace: list[tuple[str, str]] = []
    replace_original = Path.replace

    def replace_espiado(self: Path, target):
        destino = Path(target)
        if self.name.startswith(".run_state.json.") and self.name.endswith(".tmp"):
            llamadas_replace.append((self.name, destino.name))
        return replace_original(self, target)

    monkeypatch.setattr(Path, "replace", replace_espiado)

    control = ControlEjecucion(ruta)
    control.checkpoint(total_descubiertos=2, procesados=1)

    assert llamadas_replace
    assert all(destino == "run_state.json" for _, destino in llamadas_replace)
    assert not list(tmp_path.glob(".run_state.json.*.tmp"))
    data = json.loads(ruta.read_text(encoding="utf-8"))
    assert data["total_descubiertos"] == 2
    assert data["procesados"] == 1
