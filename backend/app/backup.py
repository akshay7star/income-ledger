from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import database


BACKUP_FORMAT_VERSION = 1


def backup_dir() -> Path:
    path = database.DATA_DIR / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


import uuid
def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def _copy_database(snapshot_path: Path) -> None:
    source = sqlite3.connect(database.DB_PATH)
    try:
        destination = sqlite3.connect(snapshot_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()


def create_backup() -> dict:
    database.ensure_data_dirs()
    target_dir = backup_dir()
    stamp = _utc_stamp()
    backup_path = target_dir / f"income-ledger-backup-{stamp}.zip"
    created_at = datetime.now(timezone.utc).isoformat()
    uploads = [path for path in database.UPLOAD_DIR.rglob("*") if path.is_file()]
    manifest = {
        "app": "Income Ledger",
        "format_version": BACKUP_FORMAT_VERSION,
        "created_at": created_at,
        "database": "database/income_ledger.sqlite3",
        "uploads_dir": "uploads",
        "upload_count": len(uploads),
    }

    with tempfile.TemporaryDirectory(dir=target_dir) as tmp:
        snapshot_path = Path(tmp) / "income_ledger.sqlite3"
        _copy_database(snapshot_path)
        with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            archive.write(snapshot_path, "database/income_ledger.sqlite3")
            for upload in uploads:
                archive.write(upload, Path("uploads") / upload.relative_to(database.UPLOAD_DIR))

    return {
        "path": backup_path,
        "filename": backup_path.name,
        "created_at": created_at,
        "size_bytes": backup_path.stat().st_size,
        "upload_count": len(uploads),
        "format_version": BACKUP_FORMAT_VERSION,
    }


def _safe_member_path(root: Path, member: str) -> Path:
    target = (root / member).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise ValueError("Backup ZIP contains an unsafe path.")
    return target


def validate_backup(zip_path: Path) -> dict:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = set(archive.namelist())
            if "manifest.json" not in names:
                raise ValueError("Backup manifest is missing.")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if manifest.get("app") != "Income Ledger":
                raise ValueError("Backup is not an Income Ledger backup.")
            if int(manifest.get("format_version") or 0) != BACKUP_FORMAT_VERSION:
                raise ValueError("Backup format version is not supported.")
            db_member = manifest.get("database")
            if db_member != "database/income_ledger.sqlite3" or db_member not in names:
                raise ValueError("Backup database file is missing.")
            for name in names:
                if name.endswith("/"):
                    continue
                if name not in {"manifest.json", "database/income_ledger.sqlite3"} and not name.startswith("uploads/"):
                    raise ValueError(f"Unexpected backup entry: {name}")
            return manifest
    except zipfile.BadZipFile as exc:
        raise ValueError("Backup file is not a valid ZIP.") from exc


def restore_backup(zip_path: Path) -> dict:
    manifest = validate_backup(zip_path)
    safety_backup = create_backup()
    database.ensure_data_dirs()

    with tempfile.TemporaryDirectory(dir=backup_dir()) as tmp:
        extract_root = Path(tmp)
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.namelist():
                if member.endswith("/"):
                    continue
                target = _safe_member_path(extract_root, member)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)

        restored_db = extract_root / "database" / "income_ledger.sqlite3"
        restored_uploads = extract_root / "uploads"
        if not restored_db.exists():
            raise ValueError("Extracted backup database is missing.")

        for suffix in ["", "-wal", "-shm"]:
            db_file = database.DB_PATH.with_name(database.DB_PATH.name + suffix)
            if db_file.exists():
                db_file.unlink()
        shutil.copy2(restored_db, database.DB_PATH)

        if database.UPLOAD_DIR.exists():
            shutil.rmtree(database.UPLOAD_DIR)
        database.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        if restored_uploads.exists():
            for path in restored_uploads.rglob("*"):
                if path.is_file():
                    target = database.UPLOAD_DIR / path.relative_to(restored_uploads)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)

    return {
        "restored": True,
        "manifest": manifest,
        "safety_backup": {
            "filename": safety_backup["filename"],
            "path": str(safety_backup["path"]),
        },
    }


def list_backup_history(limit: int = 20) -> list[dict]:
    items: list[dict] = []
    for path in sorted(backup_dir().glob("income-ledger-backup-*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
        manifest = {}
        try:
            with zipfile.ZipFile(path) as archive:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except Exception:
            manifest = {}
        stat = path.stat()
        items.append(
            {
                "filename": path.name,
                "path": str(path),
                "created_at": manifest.get("created_at") or datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "size_bytes": stat.st_size,
                "upload_count": int(manifest.get("upload_count") or 0),
                "format_version": int(manifest.get("format_version") or 0),
            }
        )
        if len(items) >= limit:
            break
    return items
