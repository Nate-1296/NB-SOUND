from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from config import settings
from db.conexion import obtener_filas, ejecutar


@dataclass
class AuditIssue:
    code: str
    severity: str
    detail: str


class DoctorBiblioteca:
    def __init__(self, library_dir: Path, processed_dir: Path) -> None:
        self._library = library_dir
        self._processed = processed_dir
        # Acceso lazy via modulo: si el usuario cambia las rutas desde
        # Configuracion en runtime, las nuevas se reflejan en la siguiente
        # ejecucion de la auditoria sin reiniciar la app.
        self._assets = settings.DEFAULT_ASSETS_DIR
        self._manifests = settings.DEFAULT_MANIFESTS_DIR

    def audit(self) -> dict:
        issues: list[AuditIssue] = []
        if self._assets:
            issues.extend(self._assets_huerfanos())
        issues.extend(self._tracks_sin_cover())
        issues.extend(self._manifests_faltantes())
        issues.extend(self._referencias_rotas_assets())
        issues.extend(self._nombres_fuera_plantilla())
        if not self._processed.exists():
            issues.append(AuditIssue("processed_missing", "warning", f"No existe {self._processed}"))

        resumen = {
            "total_issues": len(issues),
            "issues": [asdict(i) for i in issues],
        }
        try:
            ejecutar(
                "INSERT INTO auditorias_biblioteca(mode, dry_run, resumen_json) VALUES ('audit', 1, ?)",
                (json.dumps(resumen, ensure_ascii=False),),
            )
        except RuntimeError:
            pass
        return resumen

    def repair(self, dry_run: bool = True) -> dict:
        acciones = []
        if self._assets and self._assets.exists():
            for p in self._assets.rglob("*"):
                if p.is_file() and p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".json", ".jsonl"}:
                    acciones.append({"action": "quarantine_asset", "path": str(p)})
                    if not dry_run:
                        p.rename(p.with_suffix(p.suffix + ".broken"))

        resumen = {"dry_run": dry_run, "actions": acciones, "total_actions": len(acciones)}
        try:
            ejecutar(
                "INSERT INTO auditorias_biblioteca(mode, dry_run, resumen_json) VALUES ('repair', ?, ?)",
                (1 if dry_run else 0, json.dumps(resumen, ensure_ascii=False)),
            )
        except RuntimeError:
            pass
        return resumen

    def _assets_huerfanos(self) -> list[AuditIssue]:
        if not self._assets or not self._assets.exists():
            return []
        refs = self._asset_refs_from_manifest()
        for row in self._fetch_rows("SELECT portada_ruta FROM albums WHERE portada_ruta IS NOT NULL AND portada_ruta != ''"):
            refs.add(Path(row["portada_ruta"]).resolve())
        issues = []
        for f in self._assets.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            if f.resolve() not in refs and "artists" not in f.parts and "artists_hd" not in f.parts:
                issues.append(AuditIssue("orphan_asset", "info", str(f)))
        return issues

    def _tracks_sin_cover(self) -> list[AuditIssue]:
        q = """
        SELECT p.ruta_archivo FROM pistas p
        LEFT JOIN albums a ON a.id = p.album_id
        WHERE p.estado='biblioteca' AND (a.portada_ruta IS NULL OR a.portada_ruta='')
        """
        return [AuditIssue("track_without_cover", "warning", r["ruta_archivo"]) for r in self._fetch_rows(q)]

    def _manifests_faltantes(self) -> list[AuditIssue]:
        if not self._manifests:
            return []
        issues = []
        for row in self._fetch_rows("SELECT manifest_path, entity_type, entity_key FROM manifests_index"):
            p = Path(row["manifest_path"])
            if not p.exists():
                issues.append(AuditIssue("missing_manifest", "warning", f"{row['entity_type']}:{row['entity_key']}"))
        return issues

    def _referencias_rotas_assets(self) -> list[AuditIssue]:
        issues = []
        for row in self._fetch_rows("SELECT portada_ruta FROM albums WHERE portada_ruta IS NOT NULL AND portada_ruta != ''"):
            p = Path(row["portada_ruta"])
            if not p.exists():
                issues.append(AuditIssue("broken_asset_ref", "warning", str(p)))
        for ref in self._asset_refs_from_manifest():
            if not ref.exists():
                issues.append(AuditIssue("broken_asset_ref", "warning", str(ref)))
        return issues

    def _asset_refs_from_manifest(self) -> set[Path]:
        refs: set[Path] = set()
        if not self._assets:
            return refs
        manifest = self._assets / "assets_manifest.jsonl"
        if not manifest.exists():
            return refs
        keys = {
            "track_cover",
            "album_cover",
            "artist_avatar",
            "track_cover_hd",
            "album_cover_hd",
            "artist_avatar_hd",
        }
        try:
            with manifest.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    for key in keys:
                        value = str(row.get(key) or "").strip()
                        if value:
                            refs.add(Path(value).resolve())
        except OSError:
            return refs
        return refs

    def _nombres_fuera_plantilla(self) -> list[AuditIssue]:
        issues = []
        for mp3 in self._library.rglob("*.mp3"):
            name = mp3.name
            if len(name) < 7 or name[2] != "_":
                issues.append(AuditIssue("filename_template_mismatch", "info", str(mp3)))
        return issues

    @staticmethod
    def _fetch_rows(sql: str):
        try:
            return obtener_filas(sql)
        except RuntimeError:
            return []
