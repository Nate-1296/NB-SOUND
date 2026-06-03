from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core.assets_pipeline import PipelineAssets
from domain.models import ArchivoAudio, CandidatoMB, DecisionArchivo, DecisionTipo


def _png_bytes(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"data"


def _jpeg_bytes(width: int, height: int) -> bytes:
    return (
        b"\xff\xd8"
        + b"\xff\xc0\x00\x11\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
        + b"\xff\xd9"
    )


def test_imagen_artista_descargada_desde_theaudiodb():
    with TemporaryDirectory() as td:
        p = PipelineAssets(Path(td))
        imagen = _jpeg_bytes(720, 720)
        with patch("core.assets_pipeline.THEAUDIODB_API_KEY", "123"), \
             patch("core.assets_pipeline._descargar_json", return_value={
                 "artists": [{"strArtistThumb": "https://r2.theaudiodb.com/images/media/artist/thumb/example.jpg"}]
             }), \
             patch("core.assets_pipeline._descargar_bytes", return_value=imagen):
            ruta, _ = p._descargar_imagen_artista("Daft Punk")

        assert ruta is not None
        assert ruta.exists()
        assert ruta.name == "avatar.jpg"
        assert ruta.read_bytes() == imagen


def test_imagen_artista_none_si_api_no_retorna_artistas():
    with TemporaryDirectory() as td:
        p = PipelineAssets(Path(td))
        with patch("core.assets_pipeline.THEAUDIODB_API_KEY", "123"), \
             patch("core.assets_pipeline._descargar_json", return_value={"artists": None}):
            ruta, _ = p._descargar_imagen_artista("Artista X")
        assert ruta is None


def test_imagen_artista_fallback_deezer_si_falla_theaudiodb():
    with TemporaryDirectory() as td:
        p = PipelineAssets(Path(td))
        imagen = _png_bytes(1000, 1000)
        with patch("core.assets_pipeline.ENABLE_THEAUDIODB_ARTIST_IMAGES", True), \
             patch("core.assets_pipeline.ENABLE_DEEZER_ARTIST_IMAGES", True), \
             patch("core.assets_pipeline.ENABLE_ITUNES_ARTIST_IMAGES", False), \
             patch("core.assets_pipeline.ENABLE_WIKIPEDIA_ARTIST_IMAGES", False), \
             patch("core.assets_pipeline.THEAUDIODB_API_KEY", "123"), \
             patch.object(p._cache, "obtener", return_value=None), \
             patch.object(p._cache, "guardar", return_value=None), \
             patch("core.assets_pipeline._descargar_json", side_effect=[
                 {"artists": []},
                 {"data": [{"picture_xl": "https://cdn.example.com/artist.png"}]},
             ]) as mock_json, \
             patch("core.assets_pipeline._descargar_bytes", return_value=imagen):
            ruta, _ = p._descargar_imagen_artista("Daft Punk")

        assert ruta is not None
        assert ruta.name == "avatar.png"
        assert ruta.read_bytes() == imagen
        assert "theaudiodb.com" in mock_json.call_args_list[0].args[0]
        assert "api.deezer.com" in mock_json.call_args_list[1].args[0]


def test_portada_album_fallback_itunes():
    with TemporaryDirectory() as td:
        p = PipelineAssets(Path(td))
        imagen = _jpeg_bytes(600, 600)
        with patch("core.assets_pipeline.ENABLE_ITUNES_COVER_FALLBACK", True), \
             patch("core.assets_pipeline._descargar_json", return_value={
                 "results": [{"collectionName": "Discovery", "artworkUrl100": "https://is.example/100x100bb.jpg"}]
             }), \
             patch("core.assets_pipeline._descargar_bytes", return_value=imagen):
            ruta = p._descargar_portada_album_fallback("Daft Punk", "Discovery")

        assert ruta is not None
        assert ruta.name.endswith(".jpg")
        assert ruta.read_bytes() == imagen


def test_portada_album_cover_art_archive_descarga_estandar_y_hd():
    with TemporaryDirectory() as td:
        p = PipelineAssets(Path(td))
        metadata = {
            "images": [{
                "front": True,
                "image": "https://coverartarchive.org/release/rel/original.jpg",
                "thumbnails": {
                    "500": "https://coverartarchive.org/release/rel/500.jpg",
                    "1200": "https://coverartarchive.org/release/rel/1200.jpg",
                },
            }]
        }
        with patch("core.assets_pipeline._descargar_json", return_value=metadata), \
             patch("core.assets_pipeline._descargar_bytes", side_effect=[
                 _png_bytes(500, 500),
                 _png_bytes(1600, 1600),
             ]):
            normal, hd = p._descargar_portadas_album("rel", "")

        assert normal is not None
        assert hd is not None
        assert normal.path.exists()
        assert hd.path.exists()
        assert "albums_hd" in str(hd.path)
        assert hd.width == 1600


def test_portada_album_itunes_hd_valida_descendente():
    with TemporaryDirectory() as td:
        p = PipelineAssets(Path(td))
        with patch("core.assets_pipeline.ENABLE_ITUNES_COVER_FALLBACK", True), \
             patch("core.assets_pipeline._descargar_json", return_value={
                 "results": [{"collectionName": "Discovery", "artworkUrl100": "https://is.example/100x100bb.jpg"}]
             }), \
             patch("core.assets_pipeline._descargar_bytes", side_effect=[
                 _png_bytes(600, 600),
                 _png_bytes(800, 800),
                 _png_bytes(1400, 1400),
             ]):
            normal, hd = p._descargar_portadas_album_fallback("Daft Punk", "Discovery")

        assert normal is not None
        assert hd is not None
        assert "albums_hd" in str(hd.path)
        assert hd.width == 1400


def test_descarga_asset_descarta_bytes_no_imagen():
    with TemporaryDirectory() as td:
        p = PipelineAssets(Path(td))
        carpeta = Path(td) / "manual_invalid"
        with patch("core.assets_pipeline._descargar_bytes", return_value=b"<html>not an image</html>"):
            asset = p._descargar_y_guardar_asset(
                url="https://cdn.example.com/cover.jpg",
                carpeta=carpeta,
                prefijo="cover",
                provider="test",
                strict=False,
            )

        assert asset is None
        assert not list(carpeta.glob("*"))


def test_imagen_artista_itunes_como_provider_adicional():
    with TemporaryDirectory() as td:
        p = PipelineAssets(Path(td))
        with patch("core.assets_pipeline.ENABLE_THEAUDIODB_ARTIST_IMAGES", False), \
             patch("core.assets_pipeline.ENABLE_DEEZER_ARTIST_IMAGES", False), \
             patch("core.assets_pipeline.ENABLE_ITUNES_ARTIST_IMAGES", True), \
             patch("core.assets_pipeline.ENABLE_WIKIPEDIA_ARTIST_IMAGES", False), \
             patch.object(p._cache, "obtener", return_value=None), \
             patch.object(p._cache, "guardar", return_value=None), \
             patch("core.assets_pipeline._descargar_json", return_value={"results": [{"artworkUrl100": "https://is.example.com/a.jpg"}]}), \
             patch("core.assets_pipeline._descargar_bytes", return_value=_jpeg_bytes(600, 600)):
            ruta, _ = p._descargar_imagen_artista("Muse")
        assert ruta is not None
        assert ruta.exists()


def test_imagen_artista_deezer_descarga_hd_si_picture_xl_valida():
    with TemporaryDirectory() as td:
        p = PipelineAssets(Path(td))
        with patch("core.assets_pipeline.ENABLE_THEAUDIODB_ARTIST_IMAGES", False), \
             patch("core.assets_pipeline.ENABLE_DEEZER_ARTIST_IMAGES", True), \
             patch("core.assets_pipeline.ENABLE_ITUNES_ARTIST_IMAGES", False), \
             patch("core.assets_pipeline.ENABLE_WIKIPEDIA_ARTIST_IMAGES", False), \
             patch.object(p._cache, "obtener", return_value=None), \
             patch("core.assets_pipeline._descargar_json", return_value={
                 "data": [{"picture_xl": "https://cdn.example.com/artist.png"}]
             }), \
             patch("core.assets_pipeline._descargar_bytes", side_effect=[
                 _png_bytes(1000, 1000),
                 _png_bytes(1000, 1000),
             ]):
            normal, hd, candidates = p._descargar_imagen_artista_assets("Daft Punk")

        assert normal is not None
        assert hd is not None
        assert candidates[0].provider_name == "deezer"
        assert "artists_hd" in str(hd.path)


def test_negative_cache_artist_lookup():
    with TemporaryDirectory() as td:
        p = PipelineAssets(Path(td))
        with patch("core.assets_pipeline.ENABLE_THEAUDIODB_ARTIST_IMAGES", False), \
             patch("core.assets_pipeline.ENABLE_DEEZER_ARTIST_IMAGES", False), \
             patch("core.assets_pipeline.ENABLE_ITUNES_ARTIST_IMAGES", False), \
             patch("core.assets_pipeline.ENABLE_WIKIPEDIA_ARTIST_IMAGES", False), \
             patch.object(p._cache, "obtener", return_value=None), \
             patch.object(p._cache, "guardar_con_ttl") as mock_guardar:
            selected, candidates = p._buscar_url_imagen_artista("Unknown Artist")
        assert selected is None
        assert candidates == []
        assert mock_guardar.called


def test_assets_manifest_guarda_provider_ganador_y_alternativas():
    with TemporaryDirectory() as td:
        p = PipelineAssets(Path(td))
        decision = DecisionArchivo(
            tipo=DecisionTipo.ACEPTADO,
            archivo=ArchivoAudio(ruta_original=Path("/tmp/a.mp3")),
            candidato_elegido=CandidatoMB(
                recording_id="rid",
                release_id="rel",
                artista_principal="Artist",
                album_oficial="Album",
                titulo_oficial="Song",
            ),
        )
        decision.ruta_destino = Path(td) / "song.mp3"
        decision.ruta_destino.write_bytes(b"mp3")
        p._registrar_manifest(
            decision=decision,
            portada_track=None,
            portada_album=None,
            artist_image=None,
            asset_selection={"artist": {"provider": "theaudiodb", "score": 0.9, "alternatives": [{"provider": "deezer", "score": 0.7}]}}
        )
        data = (Path(td) / "assets_manifest.jsonl").read_text(encoding="utf-8").strip()
        assert "\"provider\": \"theaudiodb\"" in data
        assert "\"alternatives\"" in data


def test_assets_manifest_incluye_timestamp_y_politica_seleccion():
    with TemporaryDirectory() as td:
        p = PipelineAssets(Path(td))
        decision = DecisionArchivo(
            tipo=DecisionTipo.ACEPTADO,
            archivo=ArchivoAudio(ruta_original=Path('/tmp/a.mp3')),
            candidato_elegido=CandidatoMB(
                recording_id='rid',
                release_id='rel',
                artista_principal='Artist',
                album_oficial='Album',
                titulo_oficial='Song',
            ),
        )
        decision.ruta_destino = Path(td) / 'song.mp3'
        decision.ruta_destino.write_bytes(b'mp3')
        p._registrar_manifest(decision, None, None, None, asset_selection={})
        data = (Path(td) / 'assets_manifest.jsonl').read_text(encoding='utf-8')
        assert '"obtained_at"' in data
        assert '"selection_policy"' in data


def test_assets_manifest_v2_incluye_rutas_hd():
    with TemporaryDirectory() as td:
        p = PipelineAssets(Path(td))
        decision = DecisionArchivo(
            tipo=DecisionTipo.ACEPTADO,
            archivo=ArchivoAudio(ruta_original=Path('/tmp/a.mp3')),
            candidato_elegido=CandidatoMB(
                recording_id='rid',
                release_id='rel',
                artista_principal='Artist',
                album_oficial='Album',
                titulo_oficial='Song',
            ),
        )
        decision.ruta_destino = Path(td) / 'song.mp3'
        decision.ruta_destino.write_bytes(b'mp3')
        p._registrar_manifest(
            decision,
            None,
            Path("/covers/a.jpg"),
            Path("/artists/a.jpg"),
            portada_album_hd=Path("/covers/a-hd.jpg"),
            artist_image_hd=Path("/artists/a-hd.jpg"),
            asset_selection={},
        )
        data = (Path(td) / 'assets_manifest.jsonl').read_text(encoding='utf-8')
        assert '"schema_version": 2' in data
        assert '"album_cover_hd": "/covers/a-hd.jpg"' in data
        assert '"artist_avatar_hd": "/artists/a-hd.jpg"' in data
