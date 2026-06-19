from __future__ import annotations

import json
import urllib.error
import urllib.request

from .database import get_connection
from .repositories import dashboard_data
from .settings import get_secret_setting, get_settings
from .tax import calculate_tax_for_financial_year, calculate_tax_options, get_tax_rule, tax_slabs_catalog
from .tax_reconciliation import tax_statement_report


def _settings_key(user_id: str, financial_year: str) -> str:
    return f"tax_planning:{user_id}:{financial_year}"


def get_planning_inputs(user_id: str, financial_year: str) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (_settings_key(user_id, financial_year),)).fetchone()
    if not row:
        return {
            "freelance_method": "actual",
            "advance_tax_paid": 0,
            "employer_nps_enabled": False,
            "employer_nps_amount": 0,
            "basic_da_salary": 0,
            "let_out_property_interest": 0,
            "let_out_property_rent": 0,
        }
    try:
        return json.loads(row["value"])
    except Exception:
        return {}


def update_planning_inputs(user_id: str, financial_year: str, payload: dict) -> dict:
    allowed = {
        "freelance_method",
        "advance_tax_paid",
        "employer_nps_enabled",
        "employer_nps_amount",
        "basic_da_salary",
        "let_out_property_interest",
        "let_out_property_rent",
    }
    cleaned = {key: payload[key] for key in payload if key in allowed}
    if cleaned.get("freelance_method") not in (None, "actual", "44ADA"):
        raise ValueError("freelance_method must be actual or 44ADA.")
    for key in ["advance_tax_paid", "employer_nps_amount", "basic_da_salary", "let_out_property_interest", "let_out_property_rent"]:
        if key in cleaned:
            cleaned[key] = max(0.0, float(cleaned.get(key) or 0))
    if "employer_nps_enabled" in cleaned:
        cleaned["employer_nps_enabled"] = bool(cleaned["employer_nps_enabled"])

    current = get_planning_inputs(user_id, financial_year)
    current.update(cleaned)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (_settings_key(user_id, financial_year), json.dumps(current)),
        )
    return current


def _metadata_nps(records: list[dict]) -> float:
    total = 0.0
    for record in records:
        metadata = record.get("metadata") or {}
        for key in ("employer_nps_amount", "nps_employer", "employer_nps"):
            if metadata.get(key):
                total += float(metadata.get(key) or 0)
    return total


def tax_planning_report(user_id: str, financial_year: str) -> dict:
    data = dashboard_data(user_id, financial_year)
    inputs = get_planning_inputs(user_id, financial_year)
    summary = data["summary"]
    salary = float(summary.get("salary_income") or 0)
    freelance_income = float(summary.get("freelance_income") or 0)
    actual_profit = float(summary.get("freelance_profit") or 0)
    tds_paid = float(summary.get("tds_paid") or 0)
    advance_tax_paid = float(inputs.get("advance_tax_paid") or 0)

    base_tax = calculate_tax_for_financial_year(financial_year, salary, actual_profit, "new")
    metadata_nps = _metadata_nps(data["records"])
    manual_nps = float(inputs.get("employer_nps_amount") or 0) if inputs.get("employer_nps_enabled") else 0.0
    basic_da = float(inputs.get("basic_da_salary") or 0)
    nps_cap = basic_da * 0.14 if basic_da > 0 else max(manual_nps, metadata_nps)
    nps_candidate = manual_nps or metadata_nps
    nps_deduction = min(nps_candidate, nps_cap) if nps_candidate > 0 else 0.0
    planned_tax = calculate_tax_for_financial_year(financial_year, max(0.0, salary - nps_deduction), actual_profit, "new")

    presumptive_profit = round(freelance_income * 0.5, 2)
    presumptive_tax = calculate_tax_for_financial_year(financial_year, salary, presumptive_profit, "new") if freelance_income else None
    remaining_after_credits = max(0.0, planned_tax["total_tax"] - tds_paid - advance_tax_paid)

    recommendations = []
    if nps_deduction > 0:
        recommendations.append({"status": "applied", "title": "Employer NPS under 80CCD(2)", "message": f"Applied employer NPS deduction of {nps_deduction:.2f} under New Regime."})
    else:
        recommendations.append({"status": "possible", "title": "Employer NPS under 80CCD(2)", "message": "If your employer offers NPS contribution, enter it here or confirm it appears in salary slips before applying it."})
    if freelance_income:
        if presumptive_profit < actual_profit:
            recommendations.append({"status": "possible", "title": "Evaluate 44ADA", "message": "Presumptive taxation may reduce taxable freelance profit if your IT consulting work is eligible. Verify eligibility before filing."})
        else:
            recommendations.append({"status": "info", "title": "Actual expenses look better", "message": "Current recorded expenses produce profit at or below the 44ADA presumptive level."})
    recommendations.append({"status": "info", "title": "Freelance expense hygiene", "message": "Keep invoices/proofs for software, hardware, subscriptions, internet, professional fees, office costs, and business travel."})

    itr_form = "ITR-4" if freelance_income and inputs.get("freelance_method") == "44ADA" else ("ITR-3" if freelance_income else "ITR-1")
    checklist = [
        "Form 16 from employer",
        "AIS and Form 26AS reconciliation",
        "Bank statements for income receipts",
        "Freelance invoices and TDS certificates",
        "GST collected/input records where applicable",
        "Expense invoices and payment proofs",
        "Advance-tax challans",
    ]
    if nps_deduction > 0:
        checklist.append("Employer NPS contribution proof")

    return {
        "financial_year": financial_year,
        "user_id": user_id,
        "inputs": inputs,
        "tax": planned_tax,
        "base_tax_without_planning": base_tax,
        "slab_rows": planned_tax["slab_rows"],
        "breakdown": {
            "salary_income": salary,
            "freelance_income": freelance_income,
            "actual_freelance_profit": actual_profit,
            "presumptive_44ada_profit": presumptive_profit,
            "employer_nps_deduction": nps_deduction,
            "tds_paid": tds_paid,
            "advance_tax_paid": advance_tax_paid,
            "remaining_tax_after_credits": round(remaining_after_credits, 2),
        },
        "scenarios": {
            "actual": base_tax,
            "with_nps": planned_tax,
            "presumptive_44ada": presumptive_tax,
        },
        "recommendations": recommendations,
        "itr": {"suggested_form": itr_form, "checklist": checklist},
        "missing_inputs": [
            item for item, missing in [
                ("basic_da_salary for NPS cap", nps_candidate > 0 and basic_da <= 0),
                ("advance_tax_paid", advance_tax_paid <= 0 and planned_tax["total_tax"] > tds_paid),
            ] if missing
        ],
        "rule": {
            "regime": get_tax_rule(financial_year, "new").regime,
            "source_note": get_tax_rule(financial_year, "new").source_note,
        },
    }


def _cloud_ai_settings() -> dict:
    settings = get_settings()
    api_key = get_secret_setting("cloud_ai_api_key")
    if not api_key:
        raise ValueError("Cloud AI API key is not configured in Settings.")
    model = (settings.get("cloud_ai_model") or "").strip()
    if not model:
        raise ValueError("Cloud AI model is not configured in Settings.")
    base_url = (settings.get("cloud_ai_base_url") or "").strip().rstrip("/")
    if not base_url:
        raise ValueError("Cloud AI base URL is not configured in Settings.")
    try:
        timeout_seconds = int(settings.get("local_ai_timeout_seconds") or 120)
    except ValueError:
        timeout_seconds = 120
    return {"api_key": api_key, "model": model, "base_url": base_url, "timeout_seconds": max(1, timeout_seconds)}


def _cloud_chat_urls(base_url: str) -> list[str]:
    cleaned = base_url.strip().rstrip("/")
    if cleaned.endswith("/chat/completions"):
        return [cleaned]
    if cleaned.endswith("/v1"):
        return [f"{cleaned}/chat/completions"]
    return [f"{cleaned}/v1/chat/completions", f"{cleaned}/chat/completions"]


def _is_timeout_reason(reason) -> bool:
    return isinstance(reason, TimeoutError) or "timed out" in str(reason).lower()


def _amount(value: object) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _fy_start_year(financial_year: str) -> int | None:
    try:
        return int(str(financial_year).replace("FY ", "").split("-")[0])
    except (TypeError, ValueError, IndexError):
        return None


def _assessment_year_for(financial_year: str, fallback: str = "") -> str:
    start_year = _fy_start_year(financial_year)
    if start_year is None:
        return fallback
    return f"AY {start_year + 1}-{str(start_year + 2)[-2:]}"


def _fetch_taxpayer_profile(user_id: str) -> dict:
    if user_id == "all":
        with get_connection() as conn:
            rows = conn.execute("SELECT id, name, pan, aliases, profile_hints FROM users ORDER BY name").fetchall()
        return {
            "selection": "all",
            "name": "All users selected - combined ledger view, not a single taxpayer ITR",
            "users": [dict(row) for row in rows],
        }
    with get_connection() as conn:
        row = conn.execute("SELECT id, name, pan, aliases, profile_hints FROM users WHERE id = ?", (int(user_id),)).fetchone()
    return dict(row) if row else {"selection": user_id, "name": "Unknown user"}


def _expense_category_totals(expenses: list[dict]) -> dict:
    totals: dict[str, dict[str, float]] = {}
    for row in expenses:
        category = str(row.get("category") or "Others")
        entry = totals.setdefault(category, {"amount": 0.0, "gst_amount": 0.0, "count": 0})
        entry["amount"] += _amount(row.get("amount"))
        entry["gst_amount"] += _amount(row.get("gst_amount"))
        entry["count"] += 1
    return {
        category: {"amount": round(values["amount"], 2), "gst_amount": round(values["gst_amount"], 2), "count": values["count"]}
        for category, values in sorted(totals.items())
    }


def _category_total(category_totals: dict, *needles: str) -> float:
    total = 0.0
    lowered_needles = [needle.lower() for needle in needles]
    for category, values in category_totals.items():
        lowered_category = category.lower()
        if any(needle in lowered_category for needle in lowered_needles):
            total += _amount(values.get("amount"))
    return round(total, 2)


def _has_amount(value: object) -> bool:
    return _amount(value) > 0


def _compact_records(records: list[dict], income_type: str) -> list[dict]:
    rows = [row for row in records if row.get("income_type") == income_type]
    return [
        {
            "date": row.get("record_date"),
            "period": row.get("period_label"),
            "payer": row.get("payer"),
            "gross_amount": _amount(row.get("gross_amount")),
            "net_amount": _amount(row.get("net_amount")),
            "tds_amount": _amount(row.get("tds_amount")),
            "deductions_amount": _amount(row.get("deductions_amount")),
            "pf_amount": _amount(row.get("pf_amount")),
            "vpf_amount": _amount(row.get("vpf_amount")),
            "gst_amount": _amount(row.get("gst_amount")),
            "validation_warnings": row.get("validation_warnings") or [],
        }
        for row in rows[-36:]
    ]


def _compact_tax_document(document: dict | None) -> dict | None:
    if not document:
        return None
    return {
        "source_type": document.get("source_type"),
        "financial_year": document.get("financial_year"),
        "assessment_year": document.get("assessment_year"),
        "pan": document.get("pan"),
        "tan": document.get("tan"),
        "deductor_name": document.get("deductor_name"),
        "document_name": document.get("document_name"),
        "uploaded_at": document.get("uploaded_at"),
    }


def _itr_analysis_context(user_id: str, financial_year: str) -> str:
    report = tax_planning_report(user_id, financial_year)
    data = dashboard_data(user_id, financial_year)
    summary = data["summary"]
    inputs = report["inputs"]
    tax = report["tax"]
    assessment_year = tax.get("assessment_year") or _assessment_year_for(financial_year)
    profile = _fetch_taxpayer_profile(user_id)
    expense_totals = _expense_category_totals(data["expenses"])
    tax_options = calculate_tax_options(
        financial_year,
        summary.get("salary_income") or 0,
        summary.get("freelance_profit") or 0,
    )
    tax_rules = tax_slabs_catalog().get(financial_year, {})
    rent_workspace = _category_total(expense_totals, "rent", "co-working", "coworking")
    internet_phone = _category_total(expense_totals, "internet", "phone", "telecom")
    travel = _category_total(expense_totals, "travel", "cab", "taxi", "flight", "hotel", "fuel")
    depreciation = _category_total(expense_totals, "depreciation")
    office_expenses = _category_total(expense_totals, "office", "software", "supplies", "subscription", "cloud")
    classified_business_expenses = rent_workspace + internet_phone + travel + depreciation + office_expenses
    other_business_exp = max(0.0, _amount(summary.get("expenses_excluding_gst")) - classified_business_expenses)
    salary_records = _compact_records(data["records"], "salary")
    freelance_records = _compact_records(data["records"], "freelance_invoice")
    salary_income = _amount(summary.get("salary_income"))
    freelance_income = _amount(summary.get("freelance_income"))
    freelance_profit = _amount(summary.get("freelance_profit"))
    gst_collected = _amount(summary.get("freelance_gst_collected"))
    gst_input = _amount(summary.get("expense_gst_claims"))
    taxable_income = _amount(summary.get("taxable_income"))
    pf_total = _amount(summary.get("pf_total"))
    vpf_total = _amount(summary.get("vpf_total"))
    employer_nps = _amount(report["breakdown"].get("employer_nps_deduction"))
    advance_tax_paid = _amount(inputs.get("advance_tax_paid"))
    salary_tds = _amount(sum(row.get("tds_amount") or 0 for row in data["records"] if row.get("income_type") == "salary"))
    total_tds = _amount(summary.get("tds_paid"))
    property_rent = _amount(inputs.get("let_out_property_rent"))
    property_interest = _amount(inputs.get("let_out_property_interest"))

    known_missing = list(report["missing_inputs"])
    if user_id == "all":
        known_missing.append("single taxpayer selection for final ITR filing; current view combines all selected users")
    if (gst_collected > 0 or gst_input > 0) and not any("GST payment" in item for item in known_missing):
        known_missing.append("GST payments already made are not captured in the ledger")
    if taxable_income > 5000000:
        known_missing.append("surcharge rates are not configured in the app tax-rule catalog")

    financial_details = {
        "taxpayer_profile": {
            "financial_year": financial_year,
            "assessment_year": assessment_year,
            "taxpayer": profile,
            "tax_regime_preference": "Auto-select best using supplied backend old/new regime comparison",
        },
        "tax_slabs_rules_supplied_by_backend": {
            "rules": tax_rules,
            "backend_tax_options": tax_options,
        },
    }

    if salary_income > 0 or salary_records:
        salary_section = {
            "gross_salary_from_ledger": salary_income,
            "salary_tds": salary_tds,
            "standard_deduction_applied_by_backend": _amount(summary.get("salary_standard_deduction")),
        }
        if _has_amount(inputs.get("basic_da_salary")):
            salary_section["basic_plus_da_from_tax_planner"] = _amount(inputs.get("basic_da_salary"))
        if pf_total > 0:
            salary_section["employee_pf"] = pf_total
        if vpf_total > 0:
            salary_section["employee_vpf"] = vpf_total
        if _has_amount(summary.get("deductions")):
            salary_section["other_salary_deductions_captured"] = _amount(summary.get("deductions"))
        if salary_records:
            salary_section["salary_records"] = salary_records
        financial_details["income_from_salary"] = salary_section

    if freelance_income > 0 or freelance_records or _has_amount(summary.get("expenses_excluding_gst")):
        expense_details = {
            key: value for key, value in {
                "workspace_rent": rent_workspace,
                "internet_phone": internet_phone,
                "travel_conveyance": travel,
                "depreciation": depreciation,
                "office_supplies_software": office_expenses,
                "other_direct_expenses": round(other_business_exp, 2),
            }.items()
            if value > 0
        }
        if expense_totals:
            expense_details["category_totals"] = expense_totals
        freelance_section = {
            "gross_receipts_turnover": freelance_income,
            "freelance_profit_used_by_backend": freelance_profit,
            "whether_opting_44ada": inputs.get("freelance_method") == "44ADA",
            "presumptive_44ada_profit_estimate": report["breakdown"].get("presumptive_44ada_profit"),
        }
        if expense_details:
            freelance_section["detailed_expenses_excluding_gst"] = expense_details
        if gst_collected > 0 or gst_input > 0:
            freelance_section["gst"] = {
                "gst_collected_on_services": gst_collected,
                "gst_input_tax_credit_available": gst_input,
            }
        if freelance_records:
            freelance_section["freelance_records"] = freelance_records
        financial_details["freelancing_business_income"] = freelance_section

    captured_deductions = {}
    if pf_total > 0 or vpf_total > 0:
        captured_deductions["pf_vpf_visible_in_salary_records"] = _amount(summary.get("provident_fund_total"))
    if employer_nps > 0:
        captured_deductions["section_80ccd_2_employer_nps_applied_by_backend"] = employer_nps
    if captured_deductions:
        financial_details["captured_deductions_or_contributions"] = captured_deductions

    if property_rent > 0 or property_interest > 0:
        house_property = {}
        if property_rent > 0:
            house_property["let_out_property_gross_rent"] = property_rent
        if property_interest > 0:
            house_property["let_out_property_interest"] = property_interest
        financial_details["house_property_income"] = house_property

    tax_statement_context = None
    if user_id != "all":
        tax_statement = tax_statement_report(user_id, financial_year)
        tax_statement_context = {
            "summary": tax_statement.get("summary", {}),
            "active_26as_available": bool(tax_statement.get("active_26as")),
            "active_26as": _compact_tax_document(tax_statement.get("active_26as")),
            "superseded_26as_count": len(tax_statement.get("superseded_26as") or []),
            "form16_employers": [
                {
                    "employer": item.get("deductor_name"),
                    "tan": item.get("tan"),
                    "certificate_number": item.get("certificate_number"),
                    "part_a_available": bool(item.get("part_a")),
                    "part_b_available": bool(item.get("part_b")),
                }
                for item in tax_statement.get("form16_sets", [])
            ],
            "salary_comparisons": [
                {
                    "employer": item.get("employer"),
                    "tan": item.get("tan"),
                    "ledger_salary": _amount(item.get("ledger_salary")),
                    "form16_salary": _amount(item.get("form16_salary")),
                    "form26as_amount": _amount(item.get("form26as_amount")),
                    "ledger_tds": _amount(item.get("ledger_tds")),
                    "form16_tds": _amount(item.get("form16_tds")),
                    "form26as_tds": _amount(item.get("form26as_tds")),
                    "status": item.get("status"),
                }
                for item in tax_statement.get("employer_comparisons", [])
            ],
            "monthly_salary_mismatches": [
                {
                    "month": item.get("month"),
                    "employer": item.get("employer"),
                    "tan": item.get("tan"),
                    "ledger_salary": _amount(item.get("ledger_salary")),
                    "form26as_amount": _amount(item.get("form26as_amount")),
                    "ledger_tds": _amount(item.get("ledger_tds")),
                    "form26as_tds": _amount(item.get("form26as_tds")),
                    "amount_difference": _amount(item.get("amount_difference")),
                    "tds_difference": _amount(item.get("tds_difference")),
                    "issues": item.get("issues") or [],
                    "status": item.get("status"),
                }
                for item in tax_statement.get("monthly_salary_comparisons", [])
                if item.get("status") != "matched"
            ],
            "freelance_tds_comparisons": [
                {
                    "deductor_name": item.get("deductor_name"),
                    "tan": item.get("tan"),
                    "sections": item.get("sections") or [],
                    "ledger_receipts": _amount(item.get("ledger_receipts")),
                    "form26as_amount": _amount(item.get("form26as_amount")),
                    "ledger_tds": _amount(item.get("ledger_tds")),
                    "form26as_tds": _amount(item.get("form26as_tds")),
                    "status": item.get("status"),
                }
                for item in tax_statement.get("freelance_comparisons", [])
            ],
            "findings": [
                {
                    "severity": item.get("severity"),
                    "type": item.get("type"),
                    "message": item.get("message"),
                    "tan": item.get("tan"),
                    "deductor_name": item.get("deductor_name"),
                }
                for item in (tax_statement.get("findings") or [])[:20]
            ],
        }
        if tax_statement_context["summary"].get("active_26as") or tax_statement_context["form16_employers"] or tax_statement_context["findings"]:
            financial_details["form16_26as_reconciliation"] = tax_statement_context
            if any(item.get("severity") in {"warning", "error"} for item in tax_statement.get("findings", [])):
                known_missing.append("review Form 16/26AS reconciliation findings before filing")

    deterministic_snapshot = {
        "summary": summary,
        "planner_inputs": inputs,
        "planned_tax": report["tax"],
        "base_tax_without_planning": report["base_tax_without_planning"],
        "scenarios": report["scenarios"],
        "itr": report["itr"],
        "tax_rule_source": report["rule"],
    }
    if data["monthly"]:
        deterministic_snapshot["monthly"] = data["monthly"]
    if tax_statement_context:
        deterministic_snapshot["tax_statement_reconciliation"] = tax_statement_context
    if known_missing:
        deterministic_snapshot["missing_inputs_from_app"] = known_missing

    required_output = [
        "Concise ITR readiness summary",
        "Regime comparison commentary using backend old/new tax outputs",
        "Advance tax/TDS shortfall actions",
        "Risks, assumptions, and records to collect before filing",
    ]
    if "income_from_salary" in financial_details:
        required_output.append("Salary review based only on supplied salary fields")
    if "freelancing_business_income" in financial_details:
        required_output.append("Freelance/business income review including 44ADA suitability")
    if gst_collected > 0 or gst_input > 0:
        required_output.append("GST review using supplied GST collected/input values")
    if captured_deductions:
        required_output.append("Captured deduction/contribution review")
    if "house_property_income" in financial_details:
        required_output.append("House-property review using supplied planner fields")
    if "form16_26as_reconciliation" in financial_details:
        required_output.append("Form 16/26AS reconciliation review using supplied structured findings")
    context = {
        "read_only_guardrails": [
            "Cloud AI is advisory only and cannot modify the ledger, database, settings, tax slabs, users, documents, income, or expenses.",
            "Use only values in this prompt. Do not invent missing facts.",
            "Backend deterministic tax outputs are the source of truth for numeric tax already calculated by the app.",
            "If a section is omitted from this JSON, the app has no relevant captured data for that section; do not analyze or ask about that section unless the user asks.",
            "If a supplied value is incomplete, list it as a missing data question.",
            "Any update must be performed manually by the user in the app after review and App PIN confirmation.",
        ],
        "financial_details_to_analyse": financial_details,
        "deterministic_backend_snapshot": deterministic_snapshot,
        "known_missing_data_questions": known_missing,
        "required_output": required_output,
    }
    return json.dumps(context, indent=2)


def _planner_system_prompt() -> str:
    return (
        "You are a senior Indian chartered accountant AI with deep expertise in income tax, GST, and "
        "financial planning. You are in read-only advisory mode for a local ledger app. You cannot modify "
        "ledger data, database records, tax slabs, settings, users, documents, income, expenses, or calculations. "
        "Use only the supplied JSON snapshot and tax rules. Do not invent missing facts. Treat backend "
        "deterministic tax values as the source of truth unless you clearly flag a possible data gap. "
        "If a supplied section has incomplete fields, ask a specific question instead of assuming a value. "
        "Do not analyze omitted sections; omitted sections mean the app has no relevant captured data for them. "
        "Provide advisory ITR readiness, legal tax-planning suggestions, GST review, missing-data questions, "
        "advance-tax/TDS actions, and recordkeeping steps. This is not legal certification or return filing."
    )


def _planner_context(user_id: str, financial_year: str) -> str:
    return _itr_analysis_context(user_id, financial_year)


def _call_cloud_chat(messages: list[dict]) -> dict:
    settings = _cloud_ai_settings()
    timeout_seconds = settings["timeout_seconds"]
    payload = {
        "model": settings["model"],
        "messages": messages,
        "temperature": 0.2,
    }
    errors = []

    for url in _cloud_chat_urls(settings["base_url"]):
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {settings['api_key']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            errors.append(f"{url} -> HTTP {exc.code}: {detail}")
            continue
        except urllib.error.URLError as exc:
            if _is_timeout_reason(exc.reason):
                raise RuntimeError(
                    f"Cloud AI request timed out after {timeout_seconds}s at {url}. "
                    "Increase AI timeout seconds in Settings or retry with a smaller selected scope."
                ) from exc
            errors.append(f"{url} -> {exc.reason}")
            continue
        except TimeoutError as exc:
            raise RuntimeError(
                f"Cloud AI request timed out after {timeout_seconds}s at {url}. "
                "Increase AI timeout seconds in Settings or retry with a smaller selected scope."
            ) from exc

        try:
            data = json.loads(body)
            message = data["choices"][0]["message"]["content"]
        except Exception:
            detail = body[:500] if body else "empty response"
            errors.append(f"{url} -> unexpected response: {detail}")
            continue
        usage = data.get("usage") or {}
        return {"message": message, "usage": usage, "raw_model": data.get("model")}

    detail = "; ".join(errors) if errors else "no response"
    raise RuntimeError(f"Cloud AI request failed. Tried OpenAI-compatible chat endpoints: {detail}")


def cloud_ai_analysis(user_id: str, financial_year: str) -> dict:
    context = _planner_context(user_id, financial_year)
    response = _call_cloud_chat(
        [
            {"role": "system", "content": _planner_system_prompt()},
            {
                "role": "user",
                "content": (
                    "Perform a complete read-only ITR analysis for the taxpayer and financial year in the supplied JSON. "
                    "Use the exact backend-supplied tax rules, slabs, cess, rebate, standard deduction, and deterministic "
                    "old/new regime tax outputs. Do not modify or propose modifying source data. Do not invent missing "
                    "values. Analyze only sections present in the JSON. If a supplied section is incomplete, list it as a specific missing-data question. "
                    "Include income-tax, GST, salary, freelance/business, deductions, house-property, ITR form readiness, "
                    "advance-tax/TDS shortfall, risks, assumptions, and next actions.\n\n"
                    f"{context}"
                ),
            },
        ]
    )
    usage = response.get("usage") or {}
    return {
        "analysis": response["message"],
        "usage": usage,
        "total_tokens": int(usage.get("total_tokens") or 0),
    }


def cloud_ai_chat(user_id: str, financial_year: str, messages: list[dict], total_tokens: int = 0) -> dict:
    context = _planner_context(user_id, financial_year)
    sanitized = [
        {"role": item.get("role") if item.get("role") in {"user", "assistant"} else "user", "content": str(item.get("content") or "")[:4000]}
        for item in messages[-12:]
        if str(item.get("content") or "").strip()
    ]
    response = _call_cloud_chat(
        [
            {"role": "system", "content": _planner_system_prompt()},
            {"role": "system", "content": f"Current read-only ITR analysis context from the ledger database:\n{context}"},
            *sanitized,
        ]
    )
    usage = response.get("usage") or {}
    turn_tokens = int(usage.get("total_tokens") or 0)
    return {
        "message": response["message"],
        "usage": usage,
        "total_tokens": int(total_tokens or 0) + turn_tokens,
    }
