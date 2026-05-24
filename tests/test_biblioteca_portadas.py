import tempfile
import unittest
import queue
from pathlib import Path

from servicios import biblioteca as svc_bib
from config import settings as _settings


class BibliotecaPortadasTests(unittest.TestCase):
    def setUp(self) -> None:
        svc_bib._CACHE_PORTADAS_ASSETS["firma"] = None
        svc_bib._CACHE_PORTADAS_ASSETS["mapa_releases"] = {}
        svc_bib._CACHE_PORTADAS_ASSETS["mapa_artistas"] = {}
        svc_bib._CACHE_PORTADAS_ASSETS["mapa_releases_hd"] = {}
        svc_bib._CACHE_PORTADAS_ASSETS["mapa_artistas_hd"] = {}
        svc_bib._CACHE_PORTADAS_DISPLAY.clear()
        svc_bib._PORTADAS_WARMUP_ENQUEUED.clear()
        svc_bib._PORTADAS_WARNED.clear()
        svc_bib._PILLOW_DISPONIBLE = None
        while True:
            try:
                svc_bib._PORTADAS_WARMUP_QUEUE.get_nowait()
            except queue.Empty:
                break
            else:
                svc_bib._PORTADAS_WARMUP_QUEUE.task_done()

    def _require_pillow(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow no está instalado")
        return Image

    def test_resuelve_portada_desde_manifest_por_release_id(self):
        with tempfile.TemporaryDirectory() as td:
            assets_dir = Path(td)
            manifest = assets_dir / "assets_manifest.jsonl"
            manifest.write_text(
                '{"release_id":"rel-1","album_cover":"/covers/a.jpg","track_cover":"/covers/t.jpg"}\n',
                encoding="utf-8",
            )

            original_assets_dir = _settings.DEFAULT_ASSETS_DIR
            try:
                _settings.DEFAULT_ASSETS_DIR = assets_dir
                portada = svc_bib._resolver_portada_fila(None, "rel-1")
                self.assertEqual(portada, "/covers/a.jpg")
            finally:
                _settings.DEFAULT_ASSETS_DIR = original_assets_dir

    def test_si_no_hay_album_cover_usa_track_cover(self):
        with tempfile.TemporaryDirectory() as td:
            assets_dir = Path(td)
            manifest = assets_dir / "assets_manifest.jsonl"
            manifest.write_text(
                '{"release_id":"rel-2","track_cover":"/covers/t.jpg"}\n',
                encoding="utf-8",
            )

            original_assets_dir = _settings.DEFAULT_ASSETS_DIR
            try:
                _settings.DEFAULT_ASSETS_DIR = assets_dir
                portada = svc_bib._resolver_portada_fila("", "rel-2")
                self.assertEqual(portada, "/covers/t.jpg")
            finally:
                _settings.DEFAULT_ASSETS_DIR = original_assets_dir

    def test_resuelve_avatar_artista_desde_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            assets_dir = Path(td)
            manifest = assets_dir / "assets_manifest.jsonl"
            manifest.write_text(
                '{"release_id":"rel-3","artista":"Daft Punk","artist_avatar":"/artists/dp/avatar.jpg"}\n',
                encoding="utf-8",
            )

            original_assets_dir = _settings.DEFAULT_ASSETS_DIR
            try:
                _settings.DEFAULT_ASSETS_DIR = assets_dir
                portada = svc_bib._resolver_avatar_artista("", "daft punk")
                self.assertEqual(portada, "/artists/dp/avatar.jpg")
            finally:
                _settings.DEFAULT_ASSETS_DIR = original_assets_dir

    def test_resuelve_portada_hd_desde_manifest_sin_reemplazar_estandar(self):
        with tempfile.TemporaryDirectory() as td:
            assets_dir = Path(td)
            manifest = assets_dir / "assets_manifest.jsonl"
            manifest.write_text(
                '{"release_id":"rel-hd","album_cover":"/covers/a.jpg","album_cover_hd":"/covers/a-hd.jpg"}\n',
                encoding="utf-8",
            )

            original_assets_dir = _settings.DEFAULT_ASSETS_DIR
            try:
                _settings.DEFAULT_ASSETS_DIR = assets_dir
                portada = svc_bib._resolver_portada_fila(None, "rel-hd")
                portada_hd = svc_bib._resolver_portada_hd_fila(None, "rel-hd")
                self.assertEqual(portada, "/covers/a.jpg")
                self.assertEqual(portada_hd, "/covers/a-hd.jpg")
            finally:
                _settings.DEFAULT_ASSETS_DIR = original_assets_dir

    def test_resuelve_avatar_hd_desde_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            assets_dir = Path(td)
            manifest = assets_dir / "assets_manifest.jsonl"
            manifest.write_text(
                '{"release_id":"rel-4","artista":"Daft Punk","artist_avatar_hd":"/artists/dp/avatar-hd.jpg"}\n',
                encoding="utf-8",
            )

            original_assets_dir = _settings.DEFAULT_ASSETS_DIR
            try:
                _settings.DEFAULT_ASSETS_DIR = assets_dir
                portada = svc_bib._resolver_avatar_hd_artista("", "daft punk")
                self.assertEqual(portada, "/artists/dp/avatar-hd.jpg")
            finally:
                _settings.DEFAULT_ASSETS_DIR = original_assets_dir

    def test_portada_display_crea_thumb_sanitizado_sin_icc(self):
        Image = self._require_pillow()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            origen = base / "cover.jpg"
            Image.new("RGB", (480, 320), (40, 80, 120)).save(
                origen,
                format="JPEG",
                icc_profile=b"perfil-icc-invalido",
            )

            original_cache_dir = _settings.DEFAULT_CACHE_DIR
            try:
                _settings.DEFAULT_CACHE_DIR = base / "cache"
                display = svc_bib._resolver_portada_display(
                    str(origen),
                    max_px=128,
                    generar_si_falta=True,
                )

                self.assertNotEqual(display, str(origen))
                thumb = Path(display)
                self.assertTrue(thumb.exists())
                with Image.open(thumb) as img:
                    self.assertLessEqual(max(img.size), 128)
                    self.assertNotIn("icc_profile", img.info)
            finally:
                _settings.DEFAULT_CACHE_DIR = original_cache_dir

    def test_portada_display_invalida_no_reexpone_original_local(self):
        self._require_pillow()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            origen = base / "cover.jpg"
            origen.write_bytes(b"no es una imagen")

            original_cache_dir = _settings.DEFAULT_CACHE_DIR
            try:
                _settings.DEFAULT_CACHE_DIR = base / "cache"
                display = svc_bib._resolver_portada_display(
                    str(origen),
                    max_px=128,
                    generar_si_falta=True,
                )

                self.assertEqual(display, "")
            finally:
                _settings.DEFAULT_CACHE_DIR = original_cache_dir

    def test_portada_display_en_frio_no_bloquea_y_programa_warmup(self):
        Image = self._require_pillow()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            origen = base / "cover.jpg"
            Image.new("RGB", (480, 320), (40, 80, 120)).save(origen, format="JPEG")

            original_cache_dir = _settings.DEFAULT_CACHE_DIR
            original_programar = svc_bib._programar_thumb_portada
            programadas = []

            def fake_programar(path, stat, max_px):
                programadas.append((path, max_px))
                return True

            try:
                _settings.DEFAULT_CACHE_DIR = base / "cache"
                svc_bib._programar_thumb_portada = fake_programar
                display = svc_bib._resolver_portada_display(str(origen), max_px=128)

                self.assertEqual(display, str(origen))
                self.assertEqual(programadas, [(origen, 128)])
                self.assertFalse(any((base / "cache").glob("**/*.png")))
            finally:
                svc_bib._programar_thumb_portada = original_programar
                _settings.DEFAULT_CACHE_DIR = original_cache_dir


if __name__ == "__main__":
    unittest.main()
