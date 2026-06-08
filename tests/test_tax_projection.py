from datetime import date

from backend.app.tax import elapsed_financial_year_months, estimate_year_end


def test_elapsed_financial_year_months_uses_elapsed_months_for_current_year():
    assert elapsed_financial_year_months("FY 2026-27", today=date(2026, 6, 9)) == 3


def test_elapsed_financial_year_months_caps_completed_years_at_twelve():
    assert elapsed_financial_year_months("FY 2025-26", today=date(2026, 6, 9)) == 12


def test_estimate_year_end_projects_using_elapsed_months():
    assert estimate_year_end(748861, 3) == 2995444.0
