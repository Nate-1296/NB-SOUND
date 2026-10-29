import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from db.conexion import _aplicar_esquema, _checkpoint_wal_seguro, cerrar_db, get_conexion, inicializar_db


class DatabaseRecoveryTests(unittest.TestCase):
    def tearDown(self):
        cerrar_db()

    def test_recover_from_malformed_sqlite_file(self):
        # La conexión SQLite se libera dentro del `with` para que el cleanup
        # del TemporaryDirectory pueda borrar el archivo en Windows, donde
        # `os.unlink` falla mientras un proceso mantiene el handle abierto.
        with tempfile.TemporaryDirectory() as td:
            ruta_db = Path(td) / "ui.db"
            ruta_db.write_bytes(b"no-es-una-base-sqlite-valida")

            inicializar_db(ruta_db)
            try:
                tablas = get_conexion().execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='config_ui'"
                ).fetchall()
                self.assertEqual(len(tablas), 1)

                respaldos = list(Path(td).glob("ui.db.corrupt_*.bak"))
                self.assertEqual(len(respaldos), 1)
                self.assertTrue(ruta_db.exists())
            finally:
                cerrar_db()

    def test_checkpoint_wal_seguro_ignora_disk_io_error(self):
        conexion = Mock()
        conexion.execute.side_effect = Exception("disk I/O error")
        # Simular contrato sqlite.DatabaseError
        import sqlite3
        conexion.execute.side_effect = sqlite3.DatabaseError("disk I/O error")

        _checkpoint_wal_seguro(conexion)
        conexion.execute.assert_called_once()

    def test_aplicar_esquema_hace_fallback_si_wal_falla_por_disk_io(self):
        conexion = Mock()
        import sqlite3

        def _execute(sql):
            if sql == "PRAGMA journal_mode = WAL":
                raise sqlite3.DatabaseError("disk I/O error")
            if sql.startswith("PRAGMA table_info"):
                return Mock(fetchall=Mock(return_value=[
                    {"name": "karaoke_estado"},
                    {"name": "karaoke_ruta_instrumental"},
                    {"name": "karaoke_actualizado_en"},
                ]))
            return None

        conexion.execute.side_effect = _execute

        _aplicar_esquema(conexion)

        llamadas = [args[0][0] for args in conexion.execute.call_args_list]
        self.assertIn("PRAGMA journal_mode = DELETE", llamadas)
        conexion.executescript.assert_called_once()


if __name__ == "__main__":
    unittest.main()
