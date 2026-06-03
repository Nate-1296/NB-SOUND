import unittest
from pathlib import Path

from config import settings
import core.writer as writer
from core.writer import construir_ruta_destino, escribir_y_mover
from domain.models import ArchivoAudio, CandidatoMB, DecisionArchivo, DecisionTipo


class WriterPathTests(unittest.TestCase):
    def test_usa_titulo_real_en_nombre_destino(self):
        c = CandidatoMB(
            artista_principal="Test Artist",
            titulo_oficial="My Song",
            album_oficial="",
            tipo_release="Single",
            track_number=1,
        )
        carpeta, nombre = construir_ruta_destino(c, directorio_biblioteca=Path("/tmp/lib"))
        self.assertIn("test_artist", str(carpeta))
        self.assertIn("my_song", nombre)

    def test_falla_si_titulo_esta_vacio(self):
        c = CandidatoMB(
            artista_principal="Test Artist",
            titulo_oficial="",
            tipo_release="Single",
            track_number=1,
        )
        with self.assertRaises(ValueError):
            construir_ruta_destino(c, directorio_biblioteca=Path("/tmp/lib"))

    def test_writer_path_con_cirilico_no_usa_sin_titulo(self):
        c = CandidatoMB(
            artista_principal="Шарлот",
            titulo_oficial="Малышка",
            album_oficial="Малышка",
            tipo_release="Single",
            track_number=1,
        )
        carpeta, nombre = construir_ruta_destino(c, directorio_biblioteca=Path("/tmp/lib"))
        ruta = str(carpeta / nombre)
        self.assertIn("шарлот", ruta)
        self.assertIn("малышка", ruta)
        self.assertNotIn("/sin_titulo/", ruta)
        self.assertNotIn("00_sin_titulo.mp3", ruta)

    def test_escribir_y_mover_respeta_dry_run_y_no_crea_destino(self):
        base = Path(self.id().replace(".", "_"))
        # Usar TemporaryDirectory aquí evita dejar residuos aunque el assert falle.
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            origen = base / "entrada" / "song.mp3"
            origen.parent.mkdir(parents=True, exist_ok=True)
            origen.write_bytes(b"fake-mp3")

            decision = DecisionArchivo(
                tipo=DecisionTipo.ACEPTADO,
                archivo=ArchivoAudio(ruta_original=origen),
                candidato_elegido=CandidatoMB(
                    artista_principal="Artist",
                    titulo_oficial="Song",
                    album_oficial="Album",
                    tipo_release="Album",
                    track_number=1,
                ),
            )

            original_dry_run = settings.DRY_RUN
            original_mutagen = writer.MUTAGEN_DISPONIBLE
            settings.DRY_RUN = True
            writer.MUTAGEN_DISPONIBLE = True
            try:
                ok, causa, mensaje = escribir_y_mover(
                    decision,
                    directorio_biblioteca=base / "biblioteca",
                    directorio_temp=base / "temp",
                )

                self.assertTrue(ok)
                self.assertIsNone(causa)
                self.assertIn("DRY_RUN", mensaje)
                self.assertTrue(origen.exists())
                self.assertIsNotNone(decision.ruta_destino)
                self.assertFalse(decision.ruta_destino.exists())
                self.assertFalse((base / "temp").exists())
            finally:
                settings.DRY_RUN = original_dry_run
                writer.MUTAGEN_DISPONIBLE = original_mutagen


if __name__ == "__main__":
    unittest.main()
