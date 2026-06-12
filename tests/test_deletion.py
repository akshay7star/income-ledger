import json
from backend.app.repositories import delete_document

class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

class FakeConnection:
    def __init__(self):
        self.executed_queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=()):
        self.executed_queries.append((query, params))
        if "SELECT * FROM documents" in query:
            return FakeCursor([{
                "id": 42,
                "original_name": "expense_invoice.pdf",
                "stored_path": "data/uploads/fake.pdf",
                "file_hash": "hash123",
                "document_type": "purchase_expense",
                "status": "confirmed",
                "extracted_text": "",
                "extracted_json": '{"expense_id": 99}',
                "detected_user_id": 1,
                "confidence": 0.9,
                "warnings": "[]",
                "uploaded_at": "2026-06-08"
            }])
        return FakeCursor([])
        
    def commit(self):
        pass

def test_delete_document_deletes_linked_expense(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr("backend.app.repositories.get_connection", lambda: conn)
    
    unlinked = False
    class FakePath:
        def __init__(self, path_str):
            pass
        def unlink(self, missing_ok=True):
            nonlocal unlinked
            unlinked = True
    monkeypatch.setattr("backend.app.repositories.Path", FakePath)

    res = delete_document(42)
    assert res == {"deleted": True, "id": 42}
    assert unlinked
    
    queries = [q for q, _ in conn.executed_queries]
    assert "DELETE FROM freelance_expenses WHERE id = ?" in queries
    assert "DELETE FROM documents WHERE id = ?" in queries
    
    expense_delete_call = [p for q, p in conn.executed_queries if "DELETE FROM freelance_expenses" in q]
    assert len(expense_delete_call) == 1
    assert expense_delete_call[0] == (99,)


def test_update_user(monkeypatch):
    from backend.app.repositories import update_user
    
    updated_payload = None
    class FakeCursorUpdate:
        def __init__(self, query, params):
            nonlocal updated_payload
            if "UPDATE users" in query:
                updated_payload = params
        def fetchone(self):
            return {
                "id": 1,
                "name": "Updated User",
                "pan": "UPDATEDPAN",
                "aliases": "alias1",
                "profile_hints": "hint1"
            }
            
    class FakeConnectionUpdate:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, query, params=()):
            return FakeCursorUpdate(query, params)
        def commit(self):
            pass
            
    monkeypatch.setattr("backend.app.repositories.get_connection", lambda: FakeConnectionUpdate())
    
    res = update_user(1, {"name": "Updated User", "pan": "UPDATEDPAN", "aliases": "alias1", "profile_hints": "hint1"})
    assert res["name"] == "Updated User"
    assert res["pan"] == "UPDATEDPAN"
    assert updated_payload == ("Updated User", "UPDATEDPAN", "alias1", "hint1", 1)


def test_delete_user(monkeypatch):
    from backend.app.repositories import delete_user
    
    deleted_user_id = None
    audit_events_updated = False
    
    class FakeCursorDelete:
        def __init__(self, query, params):
            pass
        def fetchall(self):
            # Return one associated document
            return [{"id": 101}]
        def fetchone(self):
            return {"id": 1, "name": "User To Delete"}
            
    class FakeConnectionDelete:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, query, params=()):
            nonlocal deleted_user_id, audit_events_updated
            if "DELETE FROM users" in query:
                deleted_user_id = params[0]
            elif "UPDATE audit_events SET user_id = NULL" in query:
                audit_events_updated = True
            return FakeCursorDelete(query, params)
        def commit(self):
            pass
            
    monkeypatch.setattr("backend.app.repositories.get_connection", lambda: FakeConnectionDelete())
    
    # Mock delete_document since delete_user calls it
    delete_doc_called = []
    monkeypatch.setattr("backend.app.repositories.delete_document", lambda doc_id: delete_doc_called.append(doc_id))
    
    res = delete_user(1)
    assert res == {"deleted": True, "id": 1}
    assert deleted_user_id == 1
    assert audit_events_updated
    assert delete_doc_called == [101]

