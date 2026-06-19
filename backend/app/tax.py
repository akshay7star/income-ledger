from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date

from .database import get_connection


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
    source_note: str = ""
    marginal_relief: bool = False


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


def rule(
    financial_year: str,
    assessment_year: str,
    regime: str,
    slabs: tuple[tuple[float, float], ...],
    cess_rate: float,
    rebate_threshold: float,
    rebate_max: float,
    salary_standard_deduction: float,
    is_default: bool = False,
    source_note: str = "",
    marginal_relief: bool = False,
) -> TaxRule:
    return TaxRule(
        financial_year,
        assessment_year,
        regime,
        slabs,
        cess_rate,
        rebate_threshold,
        rebate_max,
        salary_standard_deduction,
        is_default,
        source_note,
        marginal_relief,
    )


# Keep this catalog as the single update point for tax-slab changes.
# Add the next financial year as a new key after the Finance Act / budget rules are known.
TAX_RULES: dict[str, dict[str, TaxRule]] = {
    "FY 2017-18": {
        "old": rule("FY 2017-18", "AY 2018-19", "old", OLD_2017_ONWARD, 0.03, 350000, 2500, 0, True, "Finance Act 2017: old regime only; first slab reduced to 5%."),
    },
    "FY 2018-19": {
        "old": rule("FY 2018-19", "AY 2019-20", "old", OLD_2017_ONWARD, 0.04, 350000, 2500, 40000, True, "Finance Act 2018: health and education cess 4%; standard deduction 40000."),
    },
    "FY 2019-20": {
        "old": rule("FY 2019-20", "AY 2020-21", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000, True, "Finance Act 2019: Section 87A rebate threshold 500000; standard deduction 50000."),
    },
    "FY 2020-21": {
        "old": rule("FY 2020-21", "AY 2021-22", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000, True, "Old regime retained."),
        "new": rule("FY 2020-21", "AY 2021-22", "new", NEW_2020, 0.04, 500000, 12500, 0, False, "Section 115BAC introduced as optional new regime."),
    },
    "FY 2021-22": {
        "old": rule("FY 2021-22", "AY 2022-23", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000, True, "No individual slab change from FY 2020-21."),
        "new": rule("FY 2021-22", "AY 2022-23", "new", NEW_2020, 0.04, 500000, 12500, 0, False, "No new-regime slab change from FY 2020-21."),
    },
    "FY 2022-23": {
        "old": rule("FY 2022-23", "AY 2023-24", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000, True, "No individual slab change from FY 2021-22."),
        "new": rule("FY 2022-23", "AY 2023-24", "new", NEW_2020, 0.04, 500000, 12500, 0, False, "No new-regime slab change from FY 2021-22."),
    },
    "FY 2023-24": {
        "old": rule("FY 2023-24", "AY 2024-25", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000, False, "Old regime retained."),
        "new": rule("FY 2023-24", "AY 2024-25", "new", NEW_2023, 0.04, 700000, 25000, 50000, True, "Budget 2023: new regime made default; rebate threshold 700000.", True),
    },
    "FY 2024-25": {
        "old": rule("FY 2024-25", "AY 2025-26", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000, False, "Old regime retained."),
        "new": rule("FY 2024-25", "AY 2025-26", "new", NEW_2024, 0.04, 700000, 25000, 75000, True, "Budget 2024: new-regime slabs revised; standard deduction 75000.", True),
    },
    "FY 2025-26": {
        "old": rule("FY 2025-26", "AY 2026-27", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000, False, "Old regime retained."),
        "new": rule("FY 2025-26", "AY 2026-27", "new", NEW_2025, 0.04, 1200000, 60000, 75000, True, "Budget 2025: new-regime slabs revised; rebate threshold 1200000.", True),
    },
    "FY 2026-27": {
        "old": rule("FY 2026-27", "Tax Year 2026-27", "old", OLD_2017_ONWARD, 0.04, 500000, 12500, 50000, False, "Budget 2026: no individual slab change from FY 2025-26."),
        "new": rule("FY 2026-27", "Tax Year 2026-27", "new", NEW_2025, 0.04, 1200000, 60000, 75000, True, "Budget 2026: no individual slab change from FY 2025-26.", True),
    },
}

SUPPORTED_TAX_YEARS = tuple(sorted(TAX_RULES.keys()))
TAX_RULE_OVERRIDES_KEY = "tax_rule_overrides"


def _rule_from_override(financial_year: str, regime: str, payload: dict) -> TaxRule:
    slabs_payload = payload.get("slabs") or []
    slabs = []
    for slab in slabs_payload:
        amount = slab.get("amount")
        if amount is None:
            slab_amount = float("inf")
        else:
            slab_amount = float(amount)
            if slab_amount <= 0:
                raise ValueError("Tax slab amounts must be positive.")
        rate = float(slab.get("rate") or 0)
        if rate < 0 or rate > 1:
            raise ValueError("Tax slab rates must be between 0 and 1.")
        slabs.append((slab_amount, rate))
    if not slabs or slabs[-1][0] != float("inf"):
        raise ValueError("Tax slabs must end with an unlimited slab.")
    cess_rate = float(payload.get("cess_rate") or 0)
    if cess_rate < 0 or cess_rate > 1:
        raise ValueError("Tax cess rate must be between 0 and 1.")
    return TaxRule(
        financial_year=financial_year,
        assessment_year=str(payload.get("assessment_year") or ""),
        regime=regime,
        slabs=tuple(slabs),
        cess_rate=cess_rate,
        rebate_threshold=float(payload.get("rebate_threshold") or 0),
        rebate_max=float(payload.get("rebate_max") or 0),
        salary_standard_deduction=float(payload.get("salary_standard_deduction") or 0),
        is_default=bool(payload.get("is_default")),
        source_note=str(payload.get("source_note") or "User-confirmed tax rule override."),
        marginal_relief=bool(payload.get("marginal_relief")),
    )


def _tax_rule_overrides() -> dict[str, dict[str, TaxRule]]:
    try:
        with get_connection() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (TAX_RULE_OVERRIDES_KEY,)).fetchone()
    except sqlite3.Error:
        return {}
    if not row:
        return {}
    try:
        raw = json.loads(row["value"] or "{}")
        parsed: dict[str, dict[str, TaxRule]] = {}
        for financial_year, regimes in raw.items():
            parsed[str(financial_year)] = {
                str(regime): _rule_from_override(str(financial_year), str(regime), payload)
                for regime, payload in (regimes or {}).items()
                if regime in {"old", "new"}
            }
        return {fy: regimes for fy, regimes in parsed.items() if regimes}
    except Exception:
        return {}


def _all_tax_rules() -> dict[str, dict[str, TaxRule]]:
    rules = {year: dict(regimes) for year, regimes in TAX_RULES.items()}
    for year, regimes in _tax_rule_overrides().items():
        rules[year] = regimes
    return rules


def available_financial_years() -> list[str]:
    return sorted(_all_tax_rules().keys(), reverse=True)


def tax_slabs_catalog() -> dict:
    rules = _all_tax_rules()
    return {
        fy: {
            regime: {
                "assessment_year": rule.assessment_year,
                "is_default": rule.is_default,
                "cess_rate": rule.cess_rate,
                "rebate_threshold": rule.rebate_threshold,
                "rebate_max": rule.rebate_max,
                "salary_standard_deduction": rule.salary_standard_deduction,
                "source_note": rule.source_note,
                "marginal_relief": rule.marginal_relief,
                "slabs": [
                    {"amount": amount if amount != float("inf") else None, "rate": rate}
                    for amount, rate in rule.slabs
                ],
            }
            for regime, rule in regimes.items()
        }
        for fy, regimes in rules.items()
    }


def calculate_slab_breakdown(taxable_income: float, slabs: tuple[tuple[float, float], ...]) -> list[dict]:
    remaining = max(0.0, float(taxable_income or 0))
    lower = 0.0
    rows = []
    for slab_amount, rate in slabs:
        upper = None if slab_amount == float("inf") else lower + slab_amount
        taxable_in_slab = min(remaining, slab_amount) if remaining > 0 else 0.0
        rows.append(
            {
                "from": round(lower, 2),
                "to": round(upper, 2) if upper is not None else None,
                "rate": rate,
                "taxable_amount": round(taxable_in_slab, 2),
                "tax": round(taxable_in_slab * rate, 2),
            }
        )
        remaining -= taxable_in_slab
        if upper is not None:
            lower = upper
    return rows


def get_tax_rule(financial_year: str, regime: str = "auto") -> TaxRule:
    all_rules = _all_tax_rules()
    rules = all_rules.get(financial_year)
    if not rules:
        supported = ", ".join(sorted(all_rules.keys()))
        raise KeyError(f"Tax slabs are not configured for {financial_year}. Supported years: {supported}")
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
    marginal_relief = 0.0
    if rule.marginal_relief and taxable_income > rule.rebate_threshold:
        max_total_tax = taxable_income - rule.rebate_threshold
        regular_total_tax = tax_after_rebate * (1 + rule.cess_rate)
        if regular_total_tax > max_total_tax:
            relieved_tax_before_cess = max_total_tax / (1 + rule.cess_rate)
            marginal_relief = max(0.0, tax_after_rebate - relieved_tax_before_cess)
            tax_after_rebate = relieved_tax_before_cess
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
        "marginal_relief": round(marginal_relief, 2),
        "cess": round(cess, 2),
        "total_tax": round(tax_after_rebate + cess, 2),
        "rebate_applied": rebate > 0,
        "slab_rows": calculate_slab_breakdown(taxable_income, rule.slabs),
        "source_note": rule.source_note,
    }


def calculate_tax_options(financial_year: str, salary_income: float, freelance_profit: float) -> dict:
    all_rules = _all_tax_rules()
    rules = all_rules.get(financial_year)
    if not rules:
        supported = ", ".join(sorted(all_rules.keys()))
        raise KeyError(f"Tax slabs are not configured for {financial_year}. Supported years: {supported}")
    options = {
        regime: calculate_tax_for_financial_year(financial_year, salary_income, freelance_profit, regime)
        for regime in rules
    }
    selected = calculate_tax_for_financial_year(financial_year, salary_income, freelance_profit)
    return {"selected": selected, "options": options, "available_regimes": list(options.keys())}


def calculate_quarterly_advance_tax(total_annual_tax: float, quarters: int = 4) -> dict:
    annual_tax = max(0.0, float(total_annual_tax or 0))
    statutory_installments = [
        (1, "15 Jun", 0.15),
        (2, "15 Sep", 0.30),
        (3, "15 Dec", 0.30),
        (4, "15 Mar", 0.25),
    ]
    schedule = []
    allocated = 0.0
    for quarter, due_date, share in statutory_installments:
        if quarter == 4:
            amount = round(annual_tax - allocated, 2)
        else:
            amount = round(annual_tax * share, 2)
            allocated += amount
        schedule.append({"quarter": quarter, "due_date": due_date, "amount": amount})
    return {
        "total_annual_tax": round(annual_tax, 2),
        "quarters": 4,
        "per_quarter": round(annual_tax / 4, 2),
        "schedule": schedule,
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


def completed_financial_year_months(financial_year: str, today: date | None = None) -> int:
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
    elapsed_including_current = (today.year - start_year) * 12 + (today.month - start_month_index) + 1
    completed_before_current = elapsed_including_current - 1
    return max(1, min(12, completed_before_current))
