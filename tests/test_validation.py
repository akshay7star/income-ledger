import json

from backend.app.repositories import validation_warnings
from backend.app.repositories import dashboard_data
from backend.app.repositories import confirm_extraction


class FakeConnection:
    def __init__(self, existing=None):
        self.existing = existing

    def execute(self, *_args):
        return self

    def fetchone(self):
        return self.existing


class FakeRow(dict):
    def keys(self):
        return super().keys()

    def __getitem__(self, key):
        return dict.__getitem__(self, key)


def test_validation_warns_for_duplicate_period():
    warnings = validation_warnings(
        FakeConnection(existing={"id": 1}),
        1,
        {"income_type": "salary", "gross_amount": 100, "net_amount": 90, "deductions_amount": 10, "tds_amount": 0},
        "FY 2026-27",
        "Apr 2026",
    )
    assert "Another salary record already exists for Apr 2026." in warnings


def test_validation_warns_for_missing_freelance_tds_only():
    warnings = validation_warnings(
        FakeConnection(),
        1,
        {
            "income_type": "freelance_invoice",
            "gross_amount": 100000,
            "net_amount": 99000,
            "deductions_amount": 10000,
            "tds_amount": 0,
        },
        "FY 2026-27",
        "Apr 2026",
    )
    assert "Gross minus deductions does not closely match net amount." not in warnings
    assert "No TDS was recorded for this freelance invoice." in warnings


def test_confirm_freelance_preserves_gst_metadata(monkeypatch):
    class FakeCursor:
        lastrowid = 7

        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class ConfirmConnection:
        def __init__(self):
            self.insert_params = None
            self.updated_json = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=()):
            if "SELECT * FROM documents" in query:
                return FakeCursor(FakeRow({
                    "id": 10,
                    "original_name": "invoice.pdf",
                    "stored_path": "data/uploads/invoice.pdf",
                    "file_hash": "hash",
                    "document_type": "freelance_invoice",
                    "status": "needs_review",
                    "extracted_text": "",
                    "extracted_json": "{}",
                    "detected_user_id": 1,
                    "confidence": 0.9,
                    "warnings": "[]",
                    "uploaded_at": "2026-04-29",
                }))
            if "INSERT INTO income_records" in query:
                self.insert_params = params
                return FakeCursor()
            if "UPDATE documents SET status = 'confirmed'" in query:
                self.updated_json = params[1]
                return FakeCursor()
            if "SELECT * FROM income_records" in query:
                return FakeCursor(FakeRow({
                    "id": 7,
                    "user_id": 1,
                    "document_id": 10,
                    "financial_year": "FY 2026-27",
                    "record_date": "2026-04-29",
                    "period_label": "Apr 2026",
                    "income_type": "freelance_invoice",
                    "payer": "Gen Aquarius Private Limited",
                    "gross_amount": 283333.0,
                    "net_amount": 254999.7,
                    "tds_amount": 28333.3,
                    "deductions_amount": 0.0,
                    "metadata_json": self.updated_json,
                    "created_at": "2026-04-29",
                }))
            return FakeCursor()

        def commit(self):
            pass

    conn = ConfirmConnection()
    monkeypatch.setattr("backend.app.repositories.get_connection", lambda: conn)
    row = confirm_extraction(10, {
        "user_id": 1,
        "income_type": "freelance_invoice",
        "record_date": "2026-04-29",
        "payer": "Gen Aquarius Private Limited",
        "gross_amount": 283333.0,
        "net_amount": 283333.0,
        "tds_amount": 28333.3,
        "gst_amount": 50999.94,
        "deductions_amount": 0,
    })

    metadata = json.loads(conn.updated_json)
    assert metadata["gst_amount"] == 50999.94
    assert metadata["net_amount"] == 254999.7
    assert row["metadata_json"] == conn.updated_json


def test_dashboard_sums_pf_and_vpf_from_record_metadata(monkeypatch):
    class FakeCursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, _params):
            if "income_records" in query:
                return FakeCursor([
                    FakeRow({
                        "id": 1,
                        "user_id": 1,
                        "document_id": 1,
                        "financial_year": "FY 2026-27",
                        "record_date": "2026-04-01",
                        "period_label": "Apr 2026",
                        "income_type": "salary",
                        "payer": "Terafina",
                        "gross_amount": 134189.14,
                        "net_amount": 112151.0,
                        "tds_amount": 6884.0,
                        "deductions_amount": 0.0,
                        "metadata_json": '{"pf_amount": 6062, "vpf_amount": 9093, "gst_amount": 0}',
                        "created_at": "2026-04-01",
                    })
                ])
            return FakeCursor([])

    monkeypatch.setattr("backend.app.repositories.get_connection", lambda: FakeConnection())
    data = dashboard_data("all", "FY 2026-27")
    assert data["summary"]["pf_total"] == 6062
    assert data["summary"]["vpf_total"] == 9093
    assert data["summary"]["provident_fund_total"] == 15155
    assert data["summary"]["total_income"] == 134189.14


def test_dashboard_freelance_profit_excludes_gst_input_from_expenses(monkeypatch):
    class FakeCursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, _params):
            if "income_records" in query:
                return FakeCursor([
                    FakeRow({
                        "id": 1,
                        "user_id": 1,
                        "document_id": 1,
                        "financial_year": "FY 2026-27",
                        "record_date": "2026-04-01",
                        "period_label": "Apr 2026",
                        "income_type": "freelance_invoice",
                        "payer": "Client",
                        "gross_amount": 100000.0,
                        "net_amount": 90000.0,
                        "tds_amount": 10000.0,
                        "deductions_amount": 0.0,
                        "metadata_json": '{"gst_amount": 18000}',
                        "created_at": "2026-04-01",
                    })
                ])
            if "freelance_expenses" in query:
                return FakeCursor([
                    FakeRow({
                        "id": 1,
                        "user_id": 1,
                        "financial_year": "FY 2026-27",
                        "expense_date": "2026-04-02",
                        "category": "Software",
                        "amount": 11800.0,
                        "gst_amount": 1800.0,
                        "notes": "Tool",
                    })
                ])
            return FakeCursor([])

    monkeypatch.setattr("backend.app.repositories.get_connection", lambda: FakeConnection())
    data = dashboard_data("all", "FY 2026-27")
    assert data["summary"]["total_expenses"] == 11800
    assert data["summary"]["expenses_excluding_gst"] == 10000
    assert data["summary"]["freelance_profit"] == 90000


def test_validation_freelance_mismatch_warns():
    warnings = validation_warnings(
        FakeConnection(),
        1,
        {
            "income_type": "freelance_invoice",
            "gross_amount": 100000,
            "net_amount": 100000,
            "tds_amount": 10000,
            "gst_amount": 0,
        },
        "FY 2026-27",
        "Apr 2026",
    )
    assert "Gross freelance income minus TDS does not closely match net amount." in warnings


def test_validation_salary_mismatch_warns():
    warnings = validation_warnings(
        FakeConnection(),
        1,
        {
            "income_type": "salary",
            "gross_amount": 100000,
            "net_amount": 90000,
            "pf_amount": 5000,
            "vpf_amount": 0,
            "tds_amount": 2000,
            "deductions_amount": 0,
        },
        "FY 2026-27",
        "Apr 2026",
    )
    assert "Gross salary minus deductions and taxes does not closely match net amount." in warnings


def test_validation_expense_mismatch_warns():
    warnings = validation_warnings(
        FakeConnection(),
        1,
        {
            "income_type": "purchase_expense",
            "gross_amount": 1000,
            "net_amount": 1180,
            "gst_amount": 180,
        },
        "FY 2026-27",
        "Apr 2026",
    )
    assert not warnings  # 1000 + 180 = 1180 matches net, no warnings

    warnings = validation_warnings(
        FakeConnection(),
        1,
        {
            "income_type": "purchase_expense",
            "gross_amount": 1000,
            "net_amount": 1000,
            "gst_amount": 180,
        },
        "FY 2026-27",
        "Apr 2026",
    )
    assert "Gross amount plus GST does not closely match net amount." in warnings


def test_add_income_record_manual(monkeypatch):
    class FakeCursor:
        lastrowid = 15
        def __init__(self, row=None):
            self.row = row
        def fetchone(self):
            return self.row

    class AddConnection:
        def __init__(self):
            self.inserted = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=()):
            if "INSERT INTO income_records" in query:
                self.inserted = params
                return FakeCursor()
            if "SELECT * FROM income_records" in query:
                return FakeCursor(FakeRow({
                    "id": 15,
                    "user_id": 1,
                    "document_id": None,
                    "financial_year": "FY 2026-27",
                    "record_date": "2026-05-31",
                    "period_label": "May 2026",
                    "income_type": "freelance_invoice",
                    "payer": "Manual Client",
                    "gross_amount": 50000.0,
                    "net_amount": 45000.0,
                    "tds_amount": 5000.0,
                    "deductions_amount": 0.0,
                    "metadata_json": "{}",
                }))
            return FakeCursor()

        def commit(self):
            pass

    conn = AddConnection()
    monkeypatch.setattr("backend.app.repositories.get_connection", lambda: conn)

    from backend.app.repositories import add_income_record
    row = add_income_record({
        "user_id": 1,
        "income_type": "freelance_invoice",
        "record_date": "2026-05-31",
        "payer": "Manual Client",
        "gross_amount": 50000.0,
        "net_amount": 50000.0,
        "tds_amount": 5000.0,
        "gst_amount": 0.0,
    })

    assert row["id"] == 15
    assert row["payer"] == "Manual Client"
    assert row["gross_amount"] == 50000.0
    assert row["net_amount"] == 45000.0
    assert row["document_id"] is None

