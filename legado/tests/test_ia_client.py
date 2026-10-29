from unittest.mock import patch

from domain.models import CandidatoMB, DecisionIA
from external.ia_client import ClienteIA


def _candidatos():
    return [
        CandidatoMB(release_id="rel-1", recording_id="rec-1"),
        CandidatoMB(release_id="rel-2", recording_id="rec-2"),
    ]


def test_parsea_json_valido_y_limita_confianza():
    client = ClienteIA()
    base = DecisionIA()
    out = client._parsear_y_validar_respuesta(
        '{"decision":"album","release_id":"rel-1","confianza":1.7,"razones":["ok"]}',
        base,
        _candidatos(),
    )
    assert out.valida is True
    assert out.release_id == "rel-1"
    assert out.confianza == 1.0


def test_descarta_release_que_no_esta_en_candidatos():
    client = ClienteIA()
    out = client._parsear_y_validar_respuesta(
        '{"decision":"single","release_id":"inventado","confianza":0.9,"razones":[]}',
        DecisionIA(),
        _candidatos(),
    )
    assert out.valida is False


def test_revision_manual_valida_sin_release_id():
    client = ClienteIA()
    out = client._parsear_y_validar_respuesta(
        '{"decision":"revision_manual","release_id":null,"confianza":"0.4","razones":["duda"]}',
        DecisionIA(),
        _candidatos(),
    )
    assert out.valida is True
    assert out.decision == "revision_manual"
    assert out.release_id is None


def test_desempatar_fallback_si_proveedor_falla():
    client = ClienteIA()
    client._activo = True
    client._client = object()
    client._proveedor = "OpenAI"
    with patch.object(client, "_llamar_openai", side_effect=RuntimeError("timeout")):
        out = client.desempatar(norm=type("N", (), {"titulo":"t", "artista_principal":"a", "album":"", "anio":None, "duracion_seg":200, "isrc":None, "fuente_titulo":type("F", (), {"value":"tag"})(), "fuente_artista":type("F", (), {"value":"tag"})()})(), candidatos=_candidatos())
    assert out.valida is False
