from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class TaxRule:
    financial_year: str
    assessment_year: str
    regime: str
    slabs: tuple[tuple[float, float], ...]
    cess_rate: float
    rebate_threshold: float
    rebate_max: float
    salary_standard_deduction: float
    is_default: bool = False


OLD_PRE_2017 = ((250000, 0.0), (250000, 0.10), (500000, 0.20), (float("inf"), 0.30))
OLD_2017_ONWARD = ((250000, 0.0), (250000, 0.05), (500000, 0.20), (float("inf"), 0.30))
NEW_2020 = (
    (250000, 0.0),
    (250000, 0.05),
    (250000, 0.10),
    (250000, 0.15),
    (250000, 0.20),
    (250000, 0.25),
    (float("inf"), 0.30),
)
NEW_2023 = ((300000, 0.0), (300000, 0.05), (300000, 0.10), (300000, 0.15), (300000, 0.20), (float("inf"), 0.30))
NEW_2024 = ((300000, 0.0), (400000, 0.05), (300000, 0.10), (200000, 0.15), (300000, 0.20), (float("inf"), 0.30))
NEW_2025 = (
    (400000, 0.0),
    (400000, 0.05),
    (400000, 0.10),
    (400000, 0.15),
    (400000, 0.20),
    (400000, 0.25),
    (float("inf"), 0.30),
)


TAX_RULES: dict[str, dict[str, TaxRule]] = {
    "FY 2017-18": {
        "old": TaxRule("FY 2017-18", "AY 2018-19", "old", OLD_2017_ONWARD, 0.03, 350000, 2500, 0, True),
    },
    "FY 2018-19": {
        "old": TaxRule("FY 2018-19", "AY 2019-20", "old", OLD_2017_ONWARD, 0.04, 350000, 2500, 40000, True),
    },
    "FY 2019-20": {
        "old": TaxRule("FY 2019-20", "AY 2020-21", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000, True),
    },
    "FY 2020-21": {
        "old": TaxRule("FY 2020-21", "AY 2021-22", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000, True),
        "new": TaxRule("FY 2020-21", "AY 2021-22", "new", NEW_2020, 0.04, 500000, 12500, 0),
    },
    "FY 2021-22": {
        "old": TaxRule("FY 2021-22", "AY 2022-23", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000, True),
        "new": TaxRule("FY 2021-22", "AY 2022-23", "new", NEW_2020, 0.04, 500000, 12500, 0),
    },
    "FY 2022-23": {
        "old": TaxRule("FY 2022-23", "AY 2023-24", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000, True),
        "new": TaxRule("FY 2022-23", "AY 2023-24", "new", NEW_2020, 0.04, 500000, 12500, 0),
    },
    "FY 2023-24": {
        "old": TaxRule("FY 2023-24", "AY 2024-25", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000),
        "new": TaxRule("FY 2023-24", "AY 2024-25", "new", NEW_2023, 0.04, 700000, 25000, 50000, True),
    },
    "FY 2024-25": {
        "old": TaxRule("FY 2024-25", "AY 2025-26", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000),
        "new": TaxRule("FY 2024-25", "AY 2025-26", "new", NEW_2024, 0.04, 700000, 25000, 75000, True),
    },
    "FY 2025-26": {
        "old": TaxRule("FY 2025-26", "AY 2026-27", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000),
        "new": TaxRule("FY 2025-26", "AY 2026-27", "new", NEW_2025, 0.04, 1200000, 60000, 75000, True),
    },
    "FY 2026-27": {
        "old": TaxRule("FY 2026-27", "Tax Year 2026-27", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000),
        "new": TaxRule("FY 2026-27", "Tax Year 2026-27", "new", NEW_2025, 0.04, 1200000, 60000, 75000, True),
    },
}


def available_financial_years() -> list[str]:
    return sorted(TAX_RULES.keys(), reverse=True)


def tax_slabs_catalog() -> dict:
    return {
        fy: {
            regime: {
                "assessment_year": rule.assessment_year,
                "is_default": rule.is_default,
                "cess_rate": rule.cess_rate,
                "rebate_threshold": rule.rebate_threshold,
                "rebate_max": rule.rebate_max,
                "salary_standard_deduction": rule.salary_standard_deduction,
                "slabs": [
                    {"amount": amount if amount != float("inf") else None, "rate": rate}
                    for amount, rate in rule.slabs
                ],
            }
            for regime, rule in regimes.items()
        }
        for fy, regimes in TAX_RULES.items()
    }


def get_tax_rule(financial_year: str, regime: str = "auto") -> TaxRule:
    rules = TAX_RULES.get(financial_year)
    if not rules:
        rules = TAX_RULES["FY 2026-27"]
    if regime == "auto":
        return next((rule for rule in rules.values() if rule.is_default), next(iter(rules.values())))
    if regime not in rules:
        raise KeyError(f"{regime} tax regime is not available for {financial_year}")
    return rules[regime]


def standard_deduction_for(financial_year: str, regime: str = "auto", salary_income: float = 0) -> float:
    rule = get_tax_rule(financial_year, regime)
    return min(float(salary_income or 0), rule.salary_standard_deduction)


def calculate_tax_for_financial_year(
    financial_year: str,
    salary_income: float,
    freelance_profit: float,
    regime: str = "auto",
) -> dict:
    rule = get_tax_rule(financial_year, regime)
    salary_income = max(0.0, float(salary_income or 0))
    freelance_profit = max(0.0, float(freelance_profit or 0))
    standard_deduction = min(salary_income, rule.salary_standard_deduction)
    taxable_income = max(0.0, salary_income - standard_deduction + freelance_profit)
    base_tax = calculate_slab_tax(taxable_income, rule.slabs)
    rebate = min(base_tax, rule.rebate_max) if taxable_income <= rule.rebate_threshold else 0.0
    tax_after_rebate = max(0.0, base_tax - rebate)
    cess = tax_after_rebate * rule.cess_rate
    return {
        "financial_year": rule.financial_year,
        "assessment_year": rule.assessment_year,
        "regime": rule.regime,
        "is_default_regime": rule.is_default,
        "salary_income": round(salary_income, 2),
        "freelance_profit": round(freelance_profit, 2),
        "salary_standard_deduction": round(standard_deduction, 2),
        "taxable_income": round(taxable_income, 2),
        "base_tax": round(base_tax, 2),
        "rebate": round(rebate, 2),
        "cess": round(cess, 2),
        "total_tax": round(tax_after_rebate + cess, 2),
        "rebate_applied": rebate > 0,
    }


def calculate_tax_options(financial_year: str, salary_income: float, freelance_profit: float) -> dict:
    rules = TAX_RULES.get(financial_year, TAX_RULES["FY 2026-27"])
    options = {
        regime: calculate_tax_for_financial_year(financial_year, salary_income, freelance_profit, regime)
        for regime in rules
    }
    selected = calculate_tax_for_financial_year(financial_year, salary_income, freelance_profit)
    return {"selected": selected, "options": options, "available_regimes": list(options.keys())}


def calculate_quarterly_advance_tax(total_annual_tax: float, quarters: int = 4) -> dict:
    quarters = max(1, int(quarters or 4))
    annual_tax = max(0.0, float(total_annual_tax or 0))
    per_quarter = round(annual_tax / quarters, 2)
    return {
        "total_annual_tax": round(annual_tax, 2),
        "quarters": quarters,
        "per_quarter": per_quarter,
        "schedule": [
            {"quarter": index, "amount": per_quarter}
            for index in range(1, quarters + 1)
        ],
    }


def calculate_slab_tax(taxable_income: float, slabs: tuple[tuple[float, float], ...]) -> float:
    remaining = max(0.0, float(taxable_income or 0))
    tax = 0.0
    for slab_amount, rate in slabs:
        if remaining <= 0:
            break
        amount = min(remaining, slab_amount)
        tax += amount * rate
        remaining -= amount
    return tax


def calculate_new_regime_tax(taxable_income: float) -> dict:
    return calculate_tax_for_financial_year("FY 2026-27", 0, taxable_income, "new")


def estimate_year_end(current_total: float, months_observed: int) -> float:
    months_observed = max(1, min(12, months_observed))
    return round((float(current_total or 0) / months_observed) * 12, 2)


def elapsed_financial_year_months(financial_year: str, today: date | None = None) -> int:
    today = today or date.today()
    try:
        start_year = int(str(financial_year).replace("FY ", "").split("-")[0])
    except (ValueError, IndexError):
        return 12

    current_start_year = today.year if today.month >= 4 else today.year - 1
    if start_year < current_start_year:
        return 12
    if start_year > current_start_year:
        return 1

    start_month_index = 4
    elapsed = (today.year - start_year) * 12 + (today.month - start_month_index) + 1
    return max(1, min(12, elapsed))
