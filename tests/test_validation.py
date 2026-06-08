from backend.app.repositories import validation_warnings
from backend.app.repositories import dashboard_data


class FakeConnection:
    def __init__(self, existing=None):
        self.existing = existing

    def execute(self, *_args):
        return self

    def fetchone(self):
        return self.existing


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


def test_dashboard_sums_pf_and_vpf_from_record_metadata(monkeypatch):
    class FakeRow(dict):
        def keys(self):
            return super().keys()

        def __getitem__(self, key):
            return dict.__getitem__(self, key)

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
