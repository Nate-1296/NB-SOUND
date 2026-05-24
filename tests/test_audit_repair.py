from pathlib import Path
from tempfile import TemporaryDirectory

from db.conexion import inicializar_db, cerrar_db, get_conexion
from core.audit import DoctorBiblioteca


def test_audit_and_repair_record_reports():
    with TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        inicializar_db(db_path)
        lib = Path(td) / "lib"
        proc = Path(td) / "proc"
        lib.mkdir(parents=True, exist_ok=True)
        proc.mkdir(parents=True, exist_ok=True)
        (lib / "badname.mp3").write_bytes(b"x")

        d = DoctorBiblioteca(lib, proc)
        audit = d.audit()
        assert "total_issues" in audit

        repair = d.repair(dry_run=True)
        assert repair["dry_run"] is True

        rows = get_conexion().execute("SELECT COUNT(*) as c FROM auditorias_biblioteca").fetchone()
        assert rows["c"] >= 2
        cerrar_db()
