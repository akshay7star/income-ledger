import pytest

from backend.app.tax import calculate_quarterly_advance_tax, calculate_tax_for_financial_year, calculate_tax_options, estimate_year_end, get_tax_rule, tax_slabs_catalog


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


def test_new_regime_marginal_relief_caps_tax_just_above_rebate_threshold():
    result = calculate_tax_for_financial_year("FY 2025-26", 1285000, 0, "new")
    assert result["taxable_income"] == 1210000
    assert result["total_tax"] == 10000
    assert result["marginal_relief"] > 0


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
    assert catalog["FY 2017-18"]["old"]["source_note"]
    assert catalog["FY 2026-27"]["new"]["source_note"]


def test_older_year_does_not_offer_new_regime_before_it_existed():
    catalog = tax_slabs_catalog()
    assert set(catalog["FY 2019-20"]) == {"old"}
    with pytest.raises(KeyError):
        get_tax_rule("FY 2019-20", "new")


def test_unknown_financial_year_does_not_fallback_to_current_slabs():
    with pytest.raises(KeyError):
        calculate_tax_for_financial_year("FY 2016-17", 600000, 0, "old")


def test_fy_2024_new_regime_uses_budget_2024_slab_shape():
    result = calculate_tax_for_financial_year("FY 2024-25", 1000000, 0, "new")
    assert result["taxable_income"] == 925000
    assert result["base_tax"] == 42500


def test_year_end_prediction_uses_observed_months():
    assert estimate_year_end(300000, 3) == 1200000


def test_quarterly_advance_tax_uses_statutory_installments():
    result = calculate_quarterly_advance_tax(113100)
    assert result["per_quarter"] == 28275
    assert result["schedule"] == [
        {"quarter": 1, "due_date": "15 Jun", "amount": 16965},
        {"quarter": 2, "due_date": "15 Sep", "amount": 33930},
        {"quarter": 3, "due_date": "15 Dec", "amount": 33930},
        {"quarter": 4, "due_date": "15 Mar", "amount": 28275},
    ]
