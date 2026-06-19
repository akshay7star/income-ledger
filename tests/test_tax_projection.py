from datetime import date

from backend.app.tax import completed_financial_year_months, elapsed_financial_year_months, estimate_year_end


def test_elapsed_financial_year_months_uses_elapsed_months_for_current_year():
    assert elapsed_financial_year_months("FY 2026-27", today=date(2026, 6, 9)) == 3


def test_completed_financial_year_months_excludes_current_partial_month():
    assert completed_financial_year_months("FY 2026-27", today=date(2026, 6, 17)) == 2


def test_elapsed_financial_year_months_caps_completed_years_at_twelve():
    assert elapsed_financial_year_months("FY 2025-26", today=date(2026, 6, 9)) == 12


def test_completed_financial_year_months_caps_completed_years_at_twelve():
    assert completed_financial_year_months("FY 2025-26", today=date(2026, 6, 9)) == 12


def test_estimate_year_end_projects_using_completed_months():
    assert estimate_year_end(271778, 2) == 1630668.0


def test_dashboard_advance_tax_uses_projected_remaining_tax_after_tds(monkeypatch):
    from backend.app import main

    monkeypatch.setattr(main, "completed_financial_year_months", lambda _fy: 2)
    monkeypatch.setattr(main, "dashboard_data", lambda _user, _fy: {
        "summary": {
            "salary_income": 200000,
            "freelance_profit": 0,
            "tds_paid": 10000,
        },
        "records": [],
        "expenses": [],
        "monthly": [],
    })
    monkeypatch.setattr(main, "calculate_tax_options", lambda _fy, salary, _profit: {
        "selected": {
            "regime": "new",
            "total_tax": 0,
        },
        "options": {},
        "available_regimes": ["new"],
    })
    monkeypatch.setattr(main, "calculate_tax_for_financial_year", lambda _fy, _salary, _profit, _regime: {
        "taxable_income": 1000000,
        "total_tax": 120000,
    })

    data = main.dashboard("1", "FY 2026-27")

    assert data["tax"]["predicted_tds_paid"] == 60000
    assert data["tax"]["predicted_remaining_tax"] == 60000
    assert data["tax"]["quarterly_advance_tax"]["per_quarter"] == 15000
