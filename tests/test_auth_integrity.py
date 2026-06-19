from pathlib import Path
from types import SimpleNamespace

import pytest
def test_auth_setup_login_and_token_validation(tmp_path, monkeypatch):
    from backend.app import auth, database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "auth.sqlite3")
    auth._sessions.clear()
    database.init_db()

    assert auth.is_pin_configured() is False
    auth.setup_pin("1234")
    assert auth.is_pin_configured() is True
    with pytest.raises(ValueError):
        auth.login("0000")
    token = auth.login("1234")
    assert auth.is_token_valid(token) is True
    auth.logout(token)
    assert auth.is_token_valid(token) is False


def test_change_pin_requires_current_pin_and_invalidates_sessions(tmp_path, monkeypatch):
    from backend.app import auth, database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "change-pin.sqlite3")
    auth._sessions.clear()
    database.init_db()
    auth.setup_pin("1234")
    token = auth.login("1234")

    with pytest.raises(ValueError):
        auth.change_pin("0000", "5678")

    auth.change_pin("1234", "5678")
    assert auth.is_token_valid(token) is False
    with pytest.raises(ValueError):
        auth.login("1234")
    assert auth.is_token_valid(auth.login("5678")) is True


def test_protected_endpoint_rejects_missing_token(tmp_path, monkeypatch):
    pytest.importorskip("python_multipart")
    from fastapi.testclient import TestClient
    from backend.app import auth, database
    from backend.app.main import app

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "auth-api.sqlite3")
    auth._sessions.clear()
    database.init_db()
    auth.setup_pin("1234")

    client = TestClient(app)
    assert client.get("/api/users").status_code == 401
    token = auth.login("1234")
    assert client.get("/api/users", headers={"X-Income-Ledger-Token": token}).status_code == 200


def test_manual_income_rejects_invalid_date():
    from backend.app.repositories import add_income_record

    with pytest.raises(ValueError):
        add_income_record(
            {
                "user_id": 1,
                "income_type": "salary",
                "record_date": "not-a-date",
                "gross_amount": 100,
                "net_amount": 100,
            }
        )


def test_expense_rejects_missing_date():
    from backend.app.repositories import add_expense

    with pytest.raises(ValueError):
        add_expense({"user_id": 1, "expense_date": "", "category": "Other", "amount": 100})


def test_duplicate_confirmed_upload_returns_existing_without_confirm(monkeypatch, tmp_path):
    pytest.importorskip("python_multipart")
    from backend.app import main

    existing = {
        "id": 99,
        "status": "confirmed",
        "duplicate": True,
        "original_name": "existing.pdf",
        "document_type": "freelance_invoice",
        "confidence": 0.95,
        "extracted": {"record_date": "2026-04-01"},
        "warnings": [],
    }
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(main, "file_sha256", lambda _path: "a" * 64)
    monkeypatch.setattr(main, "extract_financial_fields", lambda *_args: SimpleNamespace(to_dict=lambda: {"document_type": "unknown", "confidence": 0.1}))
    monkeypatch.setattr(main, "create_document", lambda *_args, **_kwargs: existing)
    monkeypatch.setattr(main, "get_document", lambda _id: existing)

    def fail_confirm(*_args, **_kwargs):
        raise AssertionError("duplicate confirmed upload should not confirm again")

    monkeypatch.setattr(main, "save_and_confirm_extraction", fail_confirm)
    response = main.upload_document(SimpleNamespace(filename="invoice.pdf", file=pdf.open("rb")), user_id=None, ai_provider=None, stage=None)
    assert response["duplicate"] is True
    assert response["reason"] == "duplicate_confirmed"
    assert response["document"]["id"] == 99


def test_add_document_expense_rolls_back_when_document_update_fails(tmp_path, monkeypatch):
    from backend.app import database
    from backend.app.repositories import add_document_expense

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "rollback.sqlite3")
    database.init_db()

    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (id, name, aliases, profile_hints) VALUES (1, 'User', '', '')")
        conn.execute(
            """
            INSERT INTO documents
                (id, original_name, stored_path, file_hash, document_type, status, extracted_json)
            VALUES (10, 'invoice.pdf', ?, 'hash', 'purchase_expense', 'needs_review', '{}')
            """,
            (str(Path("invoice.pdf")),),
        )
        conn.execute("DROP TABLE audit_events")

    with pytest.raises(Exception):
        add_document_expense(
            10,
            {
                "user_id": 1,
                "expense_date": "2026-04-01",
                "category": "Purchase invoice",
                "amount": 100,
                "gst_amount": 18,
                "notes": "rollback check",
            },
        )

    with database.get_connection() as conn:
        expenses = conn.execute("SELECT * FROM freelance_expenses").fetchall()
        document = conn.execute("SELECT status FROM documents WHERE id = 10").fetchone()
    assert expenses == []
    assert document["status"] == "needs_review"


def test_settings_persist_public_values(tmp_path, monkeypatch):
    from backend.app import database
    from backend.app.settings import get_secret_setting, get_settings, update_settings

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "settings.sqlite3")
    database.init_db()

    updated = update_settings(
        {
            "default_user_id": "7",
            "default_financial_year": "FY 2026-27",
            "local_ai_timeout_seconds": 90,
        }
    )

    assert updated["default_user_id"] == "7"
    assert updated["default_financial_year"] == "FY 2026-27"
    assert updated["local_ai_timeout_seconds"] == "90"
    assert get_settings()["local_ai_timeout_seconds"] == "90"

    updated = update_settings({"cloud_ai_api_key": "secret", "cloud_ai_model": "tax-model"})
    assert updated["cloud_ai_api_key_set"] == "true"
    assert "cloud_ai_api_key" not in updated
    assert get_secret_setting("cloud_ai_api_key") == "secret"

    updated = update_settings({"clear_cloud_ai_api_key": True})
    assert updated["cloud_ai_api_key_set"] == "false"
    assert get_secret_setting("cloud_ai_api_key") == ""


def test_backup_export_contains_database_uploads_and_manifest(tmp_path, monkeypatch):
    import json
    import zipfile

    from backend.app import backup, database

    data_dir = tmp_path / "data"
    upload_dir = data_dir / "uploads"
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(database, "DB_PATH", data_dir / "income_ledger.sqlite3")
    database.init_db()
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "sample.pdf").write_bytes(b"%PDF-1.4")

    created = backup.create_backup()

    with zipfile.ZipFile(created["path"]) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert "database/income_ledger.sqlite3" in names
    assert "uploads/sample.pdf" in names
    assert manifest["format_version"] == 1
    assert manifest["upload_count"] == 1
    assert backup.list_backup_history()[0]["filename"] == created["filename"]


def test_backup_restore_rejects_invalid_zip(tmp_path, monkeypatch):
    from backend.app import backup, database

    data_dir = tmp_path / "data"
    upload_dir = data_dir / "uploads"
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(database, "DB_PATH", data_dir / "income_ledger.sqlite3")
    database.init_db()
    invalid = tmp_path / "invalid.zip"
    invalid.write_text("not a zip")

    with pytest.raises(ValueError):
        backup.restore_backup(invalid)


def test_backup_restore_replaces_database_and_uploads(tmp_path, monkeypatch):
    from backend.app import backup, database

    data_dir = tmp_path / "data"
    upload_dir = data_dir / "uploads"
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(database, "DB_PATH", data_dir / "income_ledger.sqlite3")
    database.init_db()
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "before.pdf").write_bytes(b"before")
    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (name, aliases, profile_hints) VALUES ('Before', '', '')")
    created = backup.create_backup()

    with database.get_connection() as conn:
        conn.execute("DELETE FROM users")
    (upload_dir / "before.pdf").unlink()

    result = backup.restore_backup(created["path"])

    with database.get_connection() as conn:
        row = conn.execute("SELECT name FROM users").fetchone()
    assert result["restored"] is True
    assert row["name"] == "Before"
    assert (upload_dir / "before.pdf").exists()
