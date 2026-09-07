import json


def _entry(entry_id="mobile-1", user_id=1):
    return {
        "entry_id": entry_id,
        "user_id": user_id,
        "expense_date": "2026-09-07",
        "category": "Software",
        "amount": 1180,
        "gst_amount": 180,
        "payment_method": "UPI",
        "notes": "Mobile entry",
    }


def _init_database(tmp_path, monkeypatch):
    from backend.app import database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "mobile-sync.sqlite3")
    database.init_db()
    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (id, name, aliases, profile_hints) VALUES (1, 'Akshay', '', '')")
    return database


def test_mobile_expense_import_is_idempotent(tmp_path, monkeypatch):
    from backend.app.mobile_sync import import_mobile_expense

    database = _init_database(tmp_path, monkeypatch)
    first = import_mobile_expense(_entry())
    second = import_mobile_expense(_entry())

    assert first["duplicate"] is False
    assert second == {"entry_id": "mobile-1", "expense_id": first["expense_id"], "duplicate": True}
    with database.get_connection() as conn:
        expenses = conn.execute("SELECT * FROM freelance_expenses").fetchall()
        mapping = conn.execute("SELECT * FROM mobile_expense_sync").fetchone()
        audit = conn.execute("SELECT * FROM audit_events WHERE event_type = 'sync_mobile_expense'").fetchall()
    assert len(expenses) == 1
    assert expenses[0]["financial_year"] == "FY 2026-27"
    assert expenses[0]["amount"] == 1180
    assert expenses[0]["gst_amount"] == 180
    assert mapping["entry_id"] == "mobile-1"
    assert len(audit) == 1


def test_google_sheet_sync_imports_and_marks_rows(tmp_path, monkeypatch):
    from backend.app import mobile_sync

    database = _init_database(tmp_path, monkeypatch)
    calls = []

    monkeypatch.setattr(
        mobile_sync,
        "get_settings",
        lambda: {
            "google_sheet_sync_enabled": "true",
            "google_apps_script_url": "https://script.google.com/macros/s/deployment/exec",
        },
    )
    monkeypatch.setattr(mobile_sync, "get_secret_setting", lambda _key: "private-key")

    def fake_call(_url, _secret, action, payload=None):
        calls.append((action, payload))
        if action == "list_pending":
            return {"ok": True, "entries": [_entry()]}
        return {"ok": True}

    monkeypatch.setattr(mobile_sync, "_call_apps_script", fake_call)
    result = mobile_sync.sync_google_sheet_expenses()

    assert result["status"] == "success"
    assert result["imported_count"] == 1
    assert calls[0][0] == "sync_users"
    assert calls[0][1]["users"] == [{"id": 1, "name": "Akshay"}]
    assert calls[1][0] == "list_pending"
    assert calls[2][0] == "mark_results"
    assert calls[2][1]["results"][0]["status"] == "SYNCED"
    with database.get_connection() as conn:
        run = conn.execute("SELECT * FROM mobile_sync_runs ORDER BY id DESC LIMIT 1").fetchone()
    assert run["status"] == "success"
    assert run["imported_count"] == 1


def test_google_sheet_sync_marks_invalid_user_as_error(tmp_path, monkeypatch):
    from backend.app import mobile_sync

    _init_database(tmp_path, monkeypatch)
    marked = []
    monkeypatch.setattr(
        mobile_sync,
        "get_settings",
        lambda: {
            "google_sheet_sync_enabled": "true",
            "google_apps_script_url": "https://script.google.com/macros/s/deployment/exec",
        },
    )
    monkeypatch.setattr(mobile_sync, "get_secret_setting", lambda _key: "private-key")

    def fake_call(_url, _secret, action, payload=None):
        if action == "list_pending":
            return {"ok": True, "entries": [_entry(user_id=999)]}
        if action == "mark_results":
            marked.extend(payload["results"])
        return {"ok": True}

    monkeypatch.setattr(mobile_sync, "_call_apps_script", fake_call)
    result = mobile_sync.sync_google_sheet_expenses()

    assert result["status"] == "partial"
    assert result["error_count"] == 1
    assert marked[0]["status"] == "ERROR"
    assert "does not exist" in marked[0]["sync_error"]


def test_mobile_sync_secret_is_not_returned_by_settings(tmp_path, monkeypatch):
    from backend.app import database
    from backend.app.settings import get_secret_setting, get_settings, update_settings

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "mobile-settings.sqlite3")
    database.init_db()
    updated = update_settings(
        {
            "google_sheet_sync_enabled": True,
            "google_apps_script_url": "https://script.google.com/macros/s/deployment/exec",
            "google_sheet_sync_secret": "private-key",
        }
    )

    assert updated["google_sheet_sync_enabled"] == "true"
    assert updated["google_sheet_sync_secret_set"] == "true"
    assert "google_sheet_sync_secret" not in get_settings()
    assert get_secret_setting("google_sheet_sync_secret") == "private-key"

    cleared = update_settings({"clear_google_sheet_sync_secret": True})
    assert cleared["google_sheet_sync_secret_set"] == "false"
