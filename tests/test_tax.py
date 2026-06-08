from backend.app.tax import calculate_quarterly_advance_tax, calculate_tax_for_financial_year, calculate_tax_options, estimate_year_end, tax_slabs_catalog


def test_rebate_zeroes_tax_until_twelve_lakh():
    result = calculate_tax_for_financial_year("FY 2025-26", 1200000, 0, "new")
    assert result["total_tax"] == 0
    assert result["rebate_applied"] is True


def test_new_regime_tax_with_cess():
    result = calculate_tax_for_financial_year("FY 2025-26", 1600000, 0, "new")
    assert result["taxable_income"] == 1525000
    assert result["base_tax"] == 108750
    assert result["cess"] == 4350
    assert result["total_tax"] == 113100


def test_old_regime_2017_uses_five_percent_first_tax_slab():
    result = calculate_tax_for_financial_year("FY 2017-18", 600000, 0, "old")
    assert result["base_tax"] == 32500
    assert result["cess"] == 975
    assert result["total_tax"] == 33475


def test_new_regime_was_available_from_fy_2020_21_but_not_default():
    options = calculate_tax_options("FY 2020-21", 900000, 0)
    assert set(options["available_regimes"]) == {"old", "new"}
    assert options["selected"]["regime"] == "old"


def test_tax_slabs_catalog_keeps_last_ten_financial_years():
    catalog = tax_slabs_catalog()
    assert "FY 2017-18" in catalog
    assert "FY 2026-27" in catalog
    assert len(catalog) == 10


def test_year_end_prediction_uses_observed_months():
    assert estimate_year_end(300000, 3) == 1200000


def test_quarterly_advance_tax_splits_annual_tax_equally():
    result = calculate_quarterly_advance_tax(113100)
    assert result["per_quarter"] == 28275
    assert result["schedule"] == [
        {"quarter": 1, "amount": 28275},
        {"quarter": 2, "amount": 28275},
        {"quarter": 3, "amount": 28275},
        {"quarter": 4, "amount": 28275},
    ]
