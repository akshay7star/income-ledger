from datetime import date

from backend.app.financial_year import financial_year_for


def test_financial_year_starts_on_april_first():
    assert financial_year_for(date(2026, 3, 31)) == "FY 2025-26"
    assert financial_year_for(date(2026, 4, 1)) == "FY 2026-27"
