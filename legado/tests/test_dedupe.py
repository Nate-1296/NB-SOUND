from pathlib import Path

from core.dedupe import GestorDuplicados
from domain.models import ArchivoAudio, DecisionArchivo, DecisionTipo, CandidatoMB


def _decision(recording_id: str, isrc: str | None) -> DecisionArchivo:
    archivo = ArchivoAudio(ruta_original=Path('/tmp/a.mp3'))
    if isrc:
        from domain.models import ResultadoShazam
        archivo.resultado_shazam = ResultadoShazam(isrc=isrc, identificado=True, disponible=True)
    cand = CandidatoMB(recording_id=recording_id, release_id='rel-x', artista_principal='a', titulo_oficial='t')
    return DecisionArchivo(tipo=DecisionTipo.ACEPTADO, archivo=archivo, candidato_elegido=cand)


def test_dedupe_hash_exacto_detecta_repetido():
    g = GestorDuplicados()
    a1 = ArchivoAudio(ruta_original=Path('/tmp/1.mp3'), hash_sha256='abc')
    a2 = ArchivoAudio(ruta_original=Path('/tmp/2.mp3'), hash_sha256='abc')

    assert g.registrar_hash(a1) is None
    dup = g.registrar_hash(a2)
    assert dup is not None
    assert dup.tipo == 'hash_exacto'


def test_dedupe_identidad_semantica_por_recording_id():
    g = GestorDuplicados()
    d1 = _decision('rid-1', None)
    d2 = _decision('rid-1', None)

    assert g.detectar_duplicado_identidad(d1) is None
    assert g.registrar_identidad_aceptada(d1) is None
    dup = g.detectar_duplicado_identidad(d2)
    assert dup is not None
    assert dup.tipo == 'identidad_semantica'


def test_dedupe_identidad_mejorable_si_calidad_superior():
    g = GestorDuplicados()
    d1 = _decision('rid-1', None)
    d1.puntaje_maximo = 0.6
    d2 = _decision('rid-1', "USAAA1111111")
    d2.puntaje_maximo = 0.95

    assert g.registrar_identidad_aceptada(d1) is None
    dup = g.detectar_duplicado_identidad(d2)
    assert dup is not None
    assert dup.tipo in {'duplicado_mejorable', 'identidad_semantica'}
