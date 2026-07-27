import json

import pytest


class FakeRow(dict):
    def keys(self):
        return super().keys()

    def __getitem__(self, key):
        return dict.__getitem__(self, key)


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


def test_update_expense_updates_row_document_link_and_audit(monkeypatch):
    from backend.app.repositories import update_expense

    class ExpenseConnection:
        def __init__(self):
            self.expense = FakeRow({
                "id": 5,
                "user_id": 1,
                "financial_year": "FY 2026-27",
                "expense_date": "2026-05-20",
                "category": "Software",
                "amount": 1000.0,
                "gst_amount": 180.0,
                "payment_method": "Cash",
                "notes": "Old note",
                "created_at": "2026-05-20 10:00:00",
            })
            self.document_json = json.dumps({
                "expense_id": 5,
                "document_id": 9,
                "category": "Software",
                "amount": 1000.0,
            })
            self.document_update = None
            self.audit_event = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=()):
            if "SELECT * FROM freelance_expenses WHERE id = ?" in query:
                return FakeCursor([self.expense])
            if "UPDATE freelance_expenses" in query:
                (
                    user_id,
                    financial_year,
                    expense_date,
                    category,
                    amount,
                    gst_amount,
                    payment_method,
                    notes,
                    expense_id,
                ) = params
                assert expense_id == 5
                self.expense = FakeRow({
                    **self.expense,
                    "user_id": user_id,
                    "financial_year": financial_year,
                    "expense_date": expense_date,
                    "category": category,
                    "amount": amount,
                    "gst_amount": gst_amount,
                    "payment_method": payment_method,
                    "notes": notes,
                })
                return FakeCursor()
            if "SELECT id, extracted_json FROM documents WHERE document_type = 'purchase_expense'" in query:
                return FakeCursor([FakeRow({"id": 9, "extracted_json": self.document_json})])
            if "UPDATE documents SET detected_user_id = ?" in query:
                self.document_update = params
                return FakeCursor()
            if "INSERT INTO audit_events" in query:
                self.audit_event = params
                return FakeCursor()
            return FakeCursor()

        def commit(self):
            pass

    conn = ExpenseConnection()
    monkeypatch.setattr("backend.app.repositories.get_connection", lambda: conn)

    row = update_expense(5, {
        "user_id": 2,
        "expense_date": "2027-04-01",
        "category": "Travel",
        "amount": 2000.0,
        "gst_amount": 0.0,
        "payment_method": "Credit Card",
        "notes": "New note",
    })

    assert row["user_id"] == 2
    assert row["financial_year"] == "FY 2027-28"
    assert row["expense_date"] == "2027-04-01"
    assert row["category"] == "Travel"
    assert row["amount"] == 2000.0
    assert row["payment_method"] == "Credit Card"

    detected_user_id, updated_json, document_id = conn.document_update
    assert detected_user_id == 2
    assert document_id == 9
    updated_document = json.loads(updated_json)
    assert updated_document["expense_id"] == 5
    assert updated_document["document_id"] == 9
    assert updated_document["document_type"] == "purchase_expense"
    assert updated_document["expense_date"] == "2027-04-01"
    assert updated_document["category"] == "Travel"
    assert updated_document["amount"] == 2000.0
    assert updated_document["payment_method"] == "Credit Card"
    assert updated_document["notes"] == "New note"

    document_id, user_id, before_json, after_json = conn.audit_event
    assert document_id == 9
    assert user_id == 2
    assert json.loads(before_json)["category"] == "Software"
    assert json.loads(after_json)["category"] == "Travel"


def test_update_expense_missing_raises_key_error(monkeypatch):
    from backend.app.repositories import update_expense

    class EmptyConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args):
            return FakeCursor()

    monkeypatch.setattr("backend.app.repositories.get_connection", lambda: EmptyConnection())

    with pytest.raises(KeyError, match="Expense not found"):
        update_expense(55, {
            "user_id": 1,
            "expense_date": "2026-05-01",
            "category": "Software",
            "amount": 100.0,
            "gst_amount": 0.0,
            "payment_method": "Cash",
            "notes": "",
        })
