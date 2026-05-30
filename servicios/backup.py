# =============================================================================
# servicios/backup.py
#
# Backup y restauracion de la biblioteca de NB Sound. Sin dependencias de Qt:
# el modelo Qt lo invoca en un worker. Ver docs/mobile-ecosystem.md (seccion E).
#
# Formato `.nbsound-backup` = ZIP con:
#   - db.sqlite3       : copia consistente de la BD vía `VACUUM INTO` (no
#                        bloquea ni copia el WAL a medio camino).
#   - assets/...       : portadas e imagenes de artista (opcional).
#   - manifest.json    : version de app, fecha, contenido y checksums sha256.
#
# Excluye: audio original (es la biblioteca del usuario, no de la app) y
# `.env`/claves. La restauracion valida checksums + integridad SQLite antes de
# reemplazar atomicamente la BD viva (reutiliza la recuperacion de db/conexion).
# =============================================================================

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from infra.logger import obtener_logger
from infra.version import APP_VERSION

_log = obtener_logger("backup")

FORMATO = "nbsound-backup"
NOMBRE_DB_EN_ZIP = "db.sqlite3"
NOMBRE_MANIFEST = "manifest.json"
PREFIJO_ASSETS = "assets/"
EXTENSION = ".nbsound-backup"


# -----------------------------------------------------------------------------
# Utilidades
# -----------------------------------------------------------------------------

def _sha256_archivo(ruta: Path, _bloque: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for chunk in iter(lambda: f.read(_bloque), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _exportar_db_consistente(destino: Path) -> None:
    """Copia la BD activa a `destino` con `VACUUM INTO` (consistente, sin WAL).

    VACUUM INTO produce un archivo SQLite limpio y compacto sin necesidad de
    bloquear escrituras prolongadamente. Requiere SQLite >= 3.27 (Python 3.12
    lo cumple). Cae a copia por backup API si VACUUM INTO no estuviera soportado.
    """
    from db.conexion import _conexion_lock, get_conexion

    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        destino.unlink()
    with _conexion_lock:
        con = get_conexion()
        try:
            con.execute("VACUUM INTO ?", (str(destino),))
            return
        except sqlite3.OperationalError as exc:
            _log.debug("VACUUM INTO no disponible (%s); usando backup API.", exc)
        # Fallback: API de backup online de SQLite (consistente también).
        destino_con = sqlite3.connect(str(destino))
        try:
            con.backup(destino_con)
        finally:
            destino_con.close()


def _dir_assets() -> Optional[Path]:
    try:
        from config import settings
        if getattr(settings, "DEFAULT_ASSETS_DIR", None):
            ruta = Path(settings.DEFAULT_ASSETS_DIR)
            return ruta if ruta.is_dir() else None
    except Exception:
        pass
    return None


# -----------------------------------------------------------------------------
# Exportacion
# -----------------------------------------------------------------------------

def crear_backup(destino: Path, *, incluir_assets: bool = True) -> dict:
    """Genera un `.nbsound-backup` en `destino`. Devuelve un resumen.

    El archivo es un ZIP con la BD, los assets (opcional) y un manifest con
    checksums sha256 de cada entrada para validar la integridad al restaurar.
    """
    destino = Path(destino)
    if destino.suffix != EXTENSION.lstrip("."):
        # Permitir tanto "x.nbsound-backup" como rutas sin extension explicita.
        if not str(destino).endswith(EXTENSION):
            destino = destino.with_name(destino.name + EXTENSION)
    destino.parent.mkdir(parents=True, exist_ok=True)

    checksums: dict[str, str] = {}
    contenido: list[str] = ["db"]
    total_assets = 0

    with tempfile.TemporaryDirectory(prefix="nbsound_backup_") as td:
        tmp = Path(td)
        db_tmp = tmp / NOMBRE_DB_EN_ZIP
        _exportar_db_consistente(db_tmp)
        checksums[NOMBRE_DB_EN_ZIP] = _sha256_archivo(db_tmp)

        assets_dir = _dir_assets() if incluir_assets else None

        # Escritura atomica: construir en un .tmp y renombrar al final.
        zip_tmp = destino.with_name(destino.name + ".tmp")
        if zip_tmp.exists():
            zip_tmp.unlink()
        with zipfile.ZipFile(zip_tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(db_tmp, NOMBRE_DB_EN_ZIP)
            if assets_dir is not None:
                for archivo in sorted(assets_dir.rglob("*")):
                    if not archivo.is_file():
                        continue
                    rel = archivo.relative_to(assets_dir).as_posix()
                    arcname = PREFIJO_ASSETS + rel
                    zf.write(archivo, arcname)
                    checksums[arcname] = _sha256_archivo(archivo)
                    total_assets += 1
                if total_assets:
                    contenido.append("assets")

            manifest = {
                "formato": FORMATO,
                "version_app": APP_VERSION,
                "creado_en": _ahora_iso(),
                "contenido": contenido,
                "total_assets": total_assets,
                "checksums": checksums,
            }
            zf.writestr(NOMBRE_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))

        zip_tmp.replace(destino)

    tamano = destino.stat().st_size
    _log.info("Backup creado: %s (%d bytes, %d assets)", destino, tamano, total_assets)
    return {
        "ok": True,
        "ruta": str(destino),
        "tamano_bytes": tamano,
        "total_assets": total_assets,
        "contenido": contenido,
    }


# -----------------------------------------------------------------------------
# Validacion
# -----------------------------------------------------------------------------

def validar_backup(ruta: Path) -> dict:
    """Valida estructura, manifest y checksums de un backup SIN restaurar."""
    ruta = Path(ruta)
    if not ruta.is_file():
        return {"ok": False, "error": "El archivo de backup no existe."}
    try:
        with zipfile.ZipFile(ruta, "r") as zf:
            nombres = set(zf.namelist())
            if NOMBRE_MANIFEST not in nombres or NOMBRE_DB_EN_ZIP not in nombres:
                return {"ok": False, "error": "Backup incompleto (falta db o manifest)."}
            manifest = json.loads(zf.read(NOMBRE_MANIFEST).decode("utf-8"))
            if manifest.get("formato") != FORMATO:
                return {"ok": False, "error": "Formato de backup no reconocido."}
            checksums = manifest.get("checksums", {})
            errores = []
            for arcname, esperado in checksums.items():
                if arcname not in nombres:
                    errores.append(f"falta {arcname}")
                    continue
                real = _sha256_bytes(zf.read(arcname))
                if real != esperado:
                    errores.append(f"checksum no coincide en {arcname}")
            if errores:
                return {"ok": False, "error": "; ".join(errores[:5]), "manifest": manifest}
            return {"ok": True, "manifest": manifest}
    except zipfile.BadZipFile:
        return {"ok": False, "error": "El archivo no es un ZIP válido."}
    except Exception as exc:
        return {"ok": False, "error": f"No se pudo validar el backup: {exc}"}


def _integridad_sqlite(ruta: Path) -> bool:
    """True si `ruta` es una BD SQLite integra con tablas esperadas."""
    try:
        con = sqlite3.connect(str(ruta))
        try:
            estado = con.execute("PRAGMA integrity_check").fetchone()
            if not estado or str(estado[0]).lower() != "ok":
                return False
            # Comprobacion minima de esquema: debe tener la tabla de pistas.
            fila = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='pistas'"
            ).fetchone()
            return fila is not None
        finally:
            con.close()
    except sqlite3.DatabaseError:
        return False


# -----------------------------------------------------------------------------
# Restauracion
# -----------------------------------------------------------------------------

def restaurar_backup(
    ruta: Path,
    ruta_db_destino: Path,
    *,
    restaurar_assets: bool = True,
    assets_destino: Optional[Path] = None,
) -> dict:
    """Restaura un backup sobre `ruta_db_destino` de forma segura.

    Flujo (reutiliza la filosofia de recuperacion de db/conexion):
      1. Valida manifest + checksums del ZIP.
      2. Extrae la BD a un archivo temporal junto al destino.
      3. Valida integridad SQLite del temporal (PRAGMA integrity_check + tabla
         pistas). Si falla, aborta sin tocar la BD viva.
      4. Cierra la conexion activa si apunta al destino.
      5. Reemplaza atomicamente (os.replace) y elimina WAL/SHM huerfanos.
      6. Restaura los assets (opcional).
    """
    ruta = Path(ruta)
    ruta_db_destino = Path(ruta_db_destino)

    validacion = validar_backup(ruta)
    if not validacion.get("ok"):
        return {"ok": False, "error": validacion.get("error", "Backup inválido.")}

    ruta_db_destino.parent.mkdir(parents=True, exist_ok=True)
    tmp_db = ruta_db_destino.with_name(ruta_db_destino.name + ".restore_tmp")

    try:
        with zipfile.ZipFile(ruta, "r") as zf:
            with zf.open(NOMBRE_DB_EN_ZIP) as src, tmp_db.open("wb") as dst:
                shutil.copyfileobj(src, dst)

            if not _integridad_sqlite(tmp_db):
                tmp_db.unlink(missing_ok=True)
                return {"ok": False, "error": "La BD del backup no pasó la verificación de integridad."}

            # Cerrar la conexion activa si es la del destino, para poder
            # reemplazar el archivo (Windows bloquea archivos abiertos).
            try:
                from db.conexion import cerrar_db, ruta_db_actual
                actual = ruta_db_actual()
                if actual is not None and Path(actual).resolve() == ruta_db_destino.resolve():
                    cerrar_db()
            except Exception as exc:
                _log.debug("No se pudo cerrar la BD activa antes de restaurar: %s", exc)

            # Reemplazo atomico + limpieza de WAL/SHM del destino.
            tmp_db.replace(ruta_db_destino)
            for extra in ("-wal", "-shm"):
                colateral = Path(str(ruta_db_destino) + extra)
                if colateral.exists():
                    try:
                        colateral.unlink()
                    except OSError:
                        pass

            assets_restaurados = 0
            if restaurar_assets:
                destino_assets = assets_destino or _dir_assets()
                if destino_assets is not None:
                    destino_assets = Path(destino_assets)
                    destino_assets.mkdir(parents=True, exist_ok=True)
                    for arcname in zf.namelist():
                        if not arcname.startswith(PREFIJO_ASSETS) or arcname.endswith("/"):
                            continue
                        rel = arcname[len(PREFIJO_ASSETS):]
                        salida = destino_assets / rel
                        salida.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(arcname) as src, salida.open("wb") as dst:
                            shutil.copyfileobj(src, dst)
                        assets_restaurados += 1

        _log.info("Backup restaurado en %s (%d assets)", ruta_db_destino, assets_restaurados)
        return {
            "ok": True,
            "ruta_db": str(ruta_db_destino),
            "assets_restaurados": assets_restaurados,
            "manifest": validacion.get("manifest", {}),
        }
    except Exception as exc:
        tmp_db.unlink(missing_ok=True)
        _log.error("Fallo al restaurar backup: %s", exc)
        return {"ok": False, "error": f"No se pudo restaurar: {exc}"}
