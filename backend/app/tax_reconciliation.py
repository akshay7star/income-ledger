from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any

from .database import get_connection, row_to_dict
from .repositories import dashboard_data


TOTAL_TOLERANCE = 1.0
MONTHLY_TOLERANCE = 100.0


def tax_statement_report(user_id: str, financial_year: str) -> dict:
    if not user_id or user_id == "all":
        return {
            "user_id": user_id,
            "financial_year": financial_year,
            "summary": {
                "active_26as": 0,
                "form16_employers": 0,
                "employer_mismatches": 0,
                "monthly_salary_mismatches": 0,
                "freelance_mismatches": 0,
                "findings": 1,
                "warnings": 1,
                "info": 0,
            },
            "active_26as": None,
            "superseded_26as": [],
            "form16_sets": [],
            "employer_comparisons": [],
            "monthly_salary_comparisons": [],
            "freelance_comparisons": [],
            "findings": [{
                "severity": "warning",
                "type": "specific_user_required",
                "message": "Select a specific user to reconcile Form 16 and 26AS documents.",
            }],
            "tax_documents": [],
        }

    data = dashboard_data(user_id, financial_year)
    tax_data = _load_tax_data(int(user_id), financial_year)
    findings: list[dict] = []

    active_26as_docs = [doc for doc in tax_data["documents"] if doc["source_type"] == "form26as" and int(doc.get("is_active") or 0) == 1]
    superseded_26as = [doc for doc in tax_data["documents"] if doc["source_type"] == "form26as" and int(doc.get("is_active") or 0) == 0]
    active_26as = active_26as_docs[0] if active_26as_docs else None
    if len(active_26as_docs) > 1:
        findings.append({
            "severity": "warning",
            "type": "multiple_active_26as",
            "message": "More than one active 26AS exists for this user and financial year. Activate only one statement.",
        })
    if not active_26as:
        findings.append({
            "severity": "warning",
            "type": "form26as_missing",
            "message": "No active Form 26AS is available for this user and financial year.",
        })

    form16_sets = _build_form16_sets(tax_data)
    employer_comparisons, monthly_salary_comparisons = _salary_comparisons(form16_sets, active_26as, tax_data, data["records"], findings)
    freelance_comparisons = _freelance_comparisons(active_26as, tax_data, data["records"], findings)

    for entry in tax_data["entries"]:
        if entry["source_type"] == "form26as" and entry.get("booking_status") and entry["booking_status"] not in {"F", "M"}:
            findings.append({
                "severity": "warning",
                "type": "tds_booking_not_final",
                "message": f"26AS TDS booking status is {entry['booking_status']} for section {entry.get('section') or 'unknown'}.",
                "tax_document_id": entry["tax_document_id"],
                "transaction_date": entry.get("transaction_date"),
                "deductor_name": entry.get("deductor_name"),
            })

    return {
        "user_id": user_id,
        "financial_year": financial_year,
        "summary": {
            "active_26as": 1 if active_26as else 0,
            "superseded_26as": len(superseded_26as),
            "form16_employers": len(form16_sets),
            "employer_mismatches": sum(1 for item in employer_comparisons if item["status"] != "matched"),
            "monthly_salary_mismatches": sum(1 for item in monthly_salary_comparisons if item["status"] != "matched"),
            "freelance_mismatches": sum(1 for item in freelance_comparisons if item["status"] != "matched"),
            "findings": len(findings),
            "warnings": sum(1 for item in findings if item["severity"] == "warning"),
            "info": sum(1 for item in findings if item["severity"] == "info"),
        },
        "active_26as": active_26as,
        "superseded_26as": superseded_26as,
        "form16_sets": form16_sets,
        "employer_comparisons": employer_comparisons,
        "monthly_salary_comparisons": monthly_salary_comparisons,
        "freelance_comparisons": freelance_comparisons,
        "findings": findings,
        "tax_documents": tax_data["documents"],
    }


def tax_reconciliation_findings(user_id: str, financial_year: str) -> list[dict]:
    report = tax_statement_report(user_id, financial_year)
    return [
        {
            **finding,
            "source": "tax_reconciliation",
        }
        for finding in report.get("findings", [])
    ]


def _load_tax_data(user_id: int, financial_year: str) -> dict:
    with get_connection() as conn:
        doc_rows = conn.execute(
            """
            SELECT td.*, d.original_name AS document_name, d.status AS document_status,
                   d.uploaded_at AS uploaded_at
            FROM tax_documents td
            LEFT JOIN documents d ON d.id = td.document_id
            WHERE td.user_id = ? AND td.financial_year = ?
            ORDER BY td.source_type, td.created_at DESC, td.id DESC
            """,
            (user_id, financial_year),
        ).fetchall()
        summary_rows = conn.execute(
            """
            SELECT s.*
            FROM tax_statement_summaries s
            JOIN tax_documents td ON td.id = s.tax_document_id
            WHERE td.user_id = ? AND td.financial_year = ?
            """,
            (user_id, financial_year),
        ).fetchall()
        entry_rows = conn.execute(
            """
            SELECT e.*
            FROM tax_statement_entries e
            JOIN tax_documents td ON td.id = e.tax_document_id
            WHERE td.user_id = ? AND td.financial_year = ?
            """,
            (user_id, financial_year),
        ).fetchall()

    documents = []
    for row in doc_rows:
        item = row_to_dict(row)
        item["raw"] = _json_loads(item.pop("raw_json", "{}"), {})
        documents.append(item)
    summaries = [_row_with_metadata(row) for row in summary_rows]
    entries = [_row_with_metadata(row) for row in entry_rows]
    return {"documents": documents, "summaries": summaries, "entries": entries}


def _build_form16_sets(tax_data: dict) -> list[dict]:
    grouped: dict[tuple[str, str], dict] = {}
    summaries_by_doc = _summaries_by_doc(tax_data["summaries"])
    for doc in tax_data["documents"]:
        if doc["source_type"] not in {"form16_part_a", "form16_part_b"}:
            continue
        summary = (summaries_by_doc.get(int(doc["id"])) or [{}])[0]
        key = (
            (doc.get("tan") or summary.get("tan") or _normalize_name(doc.get("deductor_name")) or str(doc["id"])).upper(),
            (doc.get("certificate_number") or doc.get("period_from") or "").upper(),
        )
        if key not in grouped:
            grouped[key] = {
                "key": "|".join(key),
                "tan": doc.get("tan") or summary.get("tan"),
                "deductor_name": doc.get("deductor_name") or summary.get("deductor_name"),
                "certificate_number": doc.get("certificate_number"),
                "period_from": doc.get("period_from"),
                "period_to": doc.get("period_to"),
                "part_a": None,
                "part_b": None,
                "part_a_summary": None,
                "part_b_summary": None,
            }
        target = "part_a" if doc["source_type"] == "form16_part_a" else "part_b"
        grouped[key][target] = _doc_public(doc)
        grouped[key][f"{target}_summary"] = summary
        grouped[key]["deductor_name"] = grouped[key]["deductor_name"] or doc.get("deductor_name") or summary.get("deductor_name")
        grouped[key]["tan"] = grouped[key]["tan"] or doc.get("tan") or summary.get("tan")
        grouped[key]["certificate_number"] = grouped[key]["certificate_number"] or doc.get("certificate_number")
    return list(grouped.values())


def _salary_comparisons(form16_sets: list[dict], active_26as: dict | None, tax_data: dict, records: list[dict], findings: list[dict]) -> tuple[list[dict], list[dict]]:
    comparisons = []
    monthly_comparisons = []
    active_26as_id = int(active_26as["id"]) if active_26as else None
    salary_26as_summaries = [
        summary for summary in tax_data["summaries"]
        if summary["source_type"] == "form26as" and summary["income_bucket"] == "salary" and active_26as_id and int(summary["tax_document_id"]) == active_26as_id
    ]
    salary_26as_by_tan = {
        (summary.get("tan") or "").upper(): summary
        for summary in salary_26as_summaries
    }
    salary_entries = [
        entry for entry in tax_data["entries"]
        if entry["source_type"] == "form26as" and entry["income_bucket"] == "salary" and active_26as_id and int(entry["tax_document_id"]) == active_26as_id
    ]

    comparison_sets = list(form16_sets)
    form16_tans = {(item.get("tan") or "").upper() for item in form16_sets if item.get("tan")}
    for summary in salary_26as_summaries:
        summary_tan = (summary.get("tan") or "").upper()
        if summary_tan and summary_tan in form16_tans:
            continue
        comparison_sets.append({
            "key": f"26AS|{summary_tan or _normalize_name(summary.get('deductor_name'))}",
            "tan": summary.get("tan"),
            "deductor_name": summary.get("deductor_name"),
            "certificate_number": None,
            "period_from": None,
            "period_to": None,
            "part_a": None,
            "part_b": None,
            "part_a_summary": None,
            "part_b_summary": None,
            "source_basis": "26as_salary",
        })

    for form16 in comparison_sets:
        has_form16 = bool(form16.get("part_a") or form16.get("part_b"))
        if has_form16 and not form16.get("part_a"):
            findings.append(_finding("warning", "form16_missing", f"Form 16 Part A is missing for {form16.get('deductor_name') or 'an employer'}.", form16))
        if has_form16 and not form16.get("part_b"):
            findings.append(_finding("warning", "form16_missing", f"Form 16 Part B is missing for {form16.get('deductor_name') or 'an employer'}.", form16))

        tan = (form16.get("tan") or "").upper()
        part_a_summary = form16.get("part_a_summary") or {}
        part_b_summary = form16.get("part_b_summary") or {}
        form16_salary = _amount(part_b_summary.get("gross_salary")) or _amount(part_a_summary.get("gross_salary"))
        form16_tds = _amount(part_a_summary.get("tds_deducted")) or _amount(part_b_summary.get("tds_deducted"))
        as26 = salary_26as_by_tan.get(tan, {})
        ledger_records = _matching_records(records, "salary", form16.get("deductor_name"))
        ledger_salary = sum(_amount(row.get("gross_amount")) for row in ledger_records)
        ledger_tds = sum(_amount(row.get("tds_amount")) for row in ledger_records)
        as26_salary = _amount(as26.get("gross_salary"))
        as26_tds = _amount(as26.get("tds_deducted"))
        reference_salary = form16_salary if has_form16 else as26_salary
        salary_diff = round(reference_salary - ledger_salary, 2)
        tds_diff = round((as26_tds or form16_tds) - ledger_tds, 2)
        status = "matched"
        if abs(salary_diff) > TOTAL_TOLERANCE:
            status = "mismatch"
            source_label = "Form 16" if has_form16 else "26AS section 192"
            findings.append(_finding("warning", "salary_total_mismatch", f"Ledger salary differs from {source_label} for {form16.get('deductor_name') or tan} by {salary_diff:.2f}.", form16))
        if active_26as and has_form16 and abs(form16_salary - as26_salary) > TOTAL_TOLERANCE:
            status = "mismatch"
            findings.append(_finding("warning", "salary_total_mismatch", f"Form 16 salary differs from 26AS section 192 for {form16.get('deductor_name') or tan} by {form16_salary - as26_salary:.2f}.", form16))
        if abs(tds_diff) > TOTAL_TOLERANCE:
            status = "mismatch"
            findings.append(_finding("warning", "salary_tds_mismatch", f"Ledger salary TDS differs from Form 16/26AS for {form16.get('deductor_name') or tan} by {tds_diff:.2f}.", form16))

        monthly_rows = _monthly_salary_comparisons(form16, salary_entries, ledger_records, findings) if active_26as else []
        if any(row["status"] != "matched" for row in monthly_rows):
            status = "mismatch"
        monthly_comparisons.extend(monthly_rows)

        comparisons.append({
            "employer": form16.get("deductor_name"),
            "tan": tan,
            "ledger_salary": round(ledger_salary, 2),
            "form16_salary": round(form16_salary, 2),
            "form26as_amount": round(as26_salary, 2),
            "ledger_tds": round(ledger_tds, 2),
            "form16_tds": round(form16_tds, 2),
            "form26as_tds": round(as26_tds, 2),
            "salary_difference": salary_diff,
            "tds_difference": tds_diff,
            "status": status,
            "monthly_comparisons": monthly_rows,
        })
    return comparisons, monthly_comparisons


def _monthly_salary_comparisons(form16: dict, salary_entries: list[dict], ledger_records: list[dict], findings: list[dict]) -> list[dict]:
    tan = (form16.get("tan") or "").upper()
    employer = form16.get("deductor_name")
    matched_entries = [
        entry for entry in salary_entries
        if _entry_matches_salary_candidate(entry, tan, employer)
    ]
    entries_by_month = _group_by_month(matched_entries, "transaction_date")
    records_by_month = _group_by_month(ledger_records, "record_date")
    rows = []

    for month in sorted(set(entries_by_month) | set(records_by_month)):
        month_entries = entries_by_month.get(month, [])
        month_records = records_by_month.get(month, [])
        ledger_salary = sum(_amount(row.get("gross_amount")) for row in month_records)
        ledger_tds = sum(_amount(row.get("tds_amount")) for row in month_records)
        as26_amount = sum(_amount(row.get("amount_paid")) for row in month_entries)
        as26_tds = sum(_amount(row.get("tax_deducted")) for row in month_entries)
        amount_difference = round(as26_amount - ledger_salary, 2)
        tds_difference = round(as26_tds - ledger_tds, 2)
        amount_tolerance = max(MONTHLY_TOLERANCE, as26_amount * 0.01)
        issues: list[str] = []
        status = "matched"

        if month_entries and not month_records:
            status = "missing_salary_slip"
            issues.append("missing_salary_slip")
            findings.append(_month_finding(
                "salary_slip_missing_for_26as_month",
                f"26AS has salary TDS for {month}, but no matching salary slip record was found.",
                form16,
                month,
                ledger_salary,
                as26_amount,
                ledger_tds,
                as26_tds,
            ))
        elif month_records and not month_entries:
            status = "missing_26as"
            issues.append("missing_26as")
            findings.append(_month_finding(
                "salary_26as_missing_for_salary_month",
                f"Salary slip exists for {month}, but no matching 26AS section 192 row was found.",
                form16,
                month,
                ledger_salary,
                as26_amount,
                ledger_tds,
                as26_tds,
            ))
        else:
            if abs(amount_difference) > amount_tolerance:
                status = "mismatch"
                issues.append("amount_mismatch")
                findings.append(_month_finding(
                    "salary_month_amount_mismatch",
                    f"Salary amount differs between salary slip and 26AS for {month} by {amount_difference:.2f}.",
                    form16,
                    month,
                    ledger_salary,
                    as26_amount,
                    ledger_tds,
                    as26_tds,
                ))
            if abs(tds_difference) > TOTAL_TOLERANCE:
                status = "mismatch"
                issues.append("tds_mismatch")
                findings.append(_month_finding(
                    "salary_month_tds_mismatch",
                    f"Salary TDS differs between salary slip and 26AS for {month} by {tds_difference:.2f}.",
                    form16,
                    month,
                    ledger_salary,
                    as26_amount,
                    ledger_tds,
                    as26_tds,
                ))

        rows.append({
            "month": month,
            "employer": employer,
            "tan": tan,
            "record_id": int(month_records[0]["id"]) if len(month_records) == 1 else None,
            "record_ids": [int(row["id"]) for row in month_records if row.get("id")],
            "document_ids": [int(row["document_id"]) for row in month_records if row.get("document_id")],
            "ledger_salary": round(ledger_salary, 2),
            "form26as_amount": round(as26_amount, 2),
            "ledger_tds": round(ledger_tds, 2),
            "form26as_tds": round(as26_tds, 2),
            "amount_difference": amount_difference,
            "tds_difference": tds_difference,
            "status": status,
            "issues": issues,
        })
    return rows


def _freelance_comparisons(active_26as: dict | None, tax_data: dict, records: list[dict], findings: list[dict]) -> list[dict]:
    if not active_26as:
        return []
    active_26as_id = int(active_26as["id"])
    entries = [
        entry for entry in tax_data["entries"]
        if entry["source_type"] == "form26as" and entry["income_bucket"] == "freelance" and int(entry["tax_document_id"]) == active_26as_id
    ]
    grouped: dict[str, dict] = {}
    for entry in entries:
        key = (entry.get("tan") or _normalize_name(entry.get("deductor_name")) or str(entry["id"])).upper()
        if key not in grouped:
            grouped[key] = {
                "deductor_name": entry.get("deductor_name"),
                "tan": entry.get("tan"),
                "sections": set(),
                "amount": 0.0,
                "tds": 0.0,
            }
        grouped[key]["sections"].add(entry.get("section"))
        grouped[key]["amount"] += _amount(entry.get("amount_paid"))
        grouped[key]["tds"] += _amount(entry.get("tax_deducted"))

    comparisons = []
    matched_record_ids: set[int] = set()
    for group in grouped.values():
        ledger_records = _matching_records(records, "freelance_invoice", group.get("deductor_name"))
        for row in ledger_records:
            matched_record_ids.add(int(row["id"]))
        ledger_amount = sum(_amount(row.get("gross_amount")) for row in ledger_records)
        ledger_tds = sum(_amount(row.get("tds_amount")) for row in ledger_records)
        amount_diff = round(group["amount"] - ledger_amount, 2)
        tds_diff = round(group["tds"] - ledger_tds, 2)
        status = "matched"
        if not ledger_records:
            status = "mismatch"
            findings.append({
                "severity": "warning",
                "type": "freelance_26as_missing",
                "message": f"26AS has freelance/professional TDS from {group.get('deductor_name') or group.get('tan')}, but no matching freelance invoice was found.",
                "deductor_name": group.get("deductor_name"),
                "tan": group.get("tan"),
            })
        elif abs(amount_diff) > max(MONTHLY_TOLERANCE, group["amount"] * 0.01):
            status = "mismatch"
            findings.append({
                "severity": "warning",
                "type": "freelance_receipt_mismatch",
                "message": f"Freelance receipts differ from 26AS for {group.get('deductor_name') or group.get('tan')} by {amount_diff:.2f}.",
                "deductor_name": group.get("deductor_name"),
                "tan": group.get("tan"),
            })
        if abs(tds_diff) > TOTAL_TOLERANCE:
            status = "mismatch"
            findings.append({
                "severity": "warning",
                "type": "freelance_tds_mismatch",
                "message": f"Freelance TDS differs from 26AS for {group.get('deductor_name') or group.get('tan')} by {tds_diff:.2f}.",
                "deductor_name": group.get("deductor_name"),
                "tan": group.get("tan"),
            })
        comparisons.append({
            "deductor_name": group.get("deductor_name"),
            "tan": group.get("tan"),
            "sections": sorted(item for item in group["sections"] if item),
            "ledger_receipts": round(ledger_amount, 2),
            "form26as_amount": round(group["amount"], 2),
            "ledger_tds": round(ledger_tds, 2),
            "form26as_tds": round(group["tds"], 2),
            "receipt_difference": amount_diff,
            "tds_difference": tds_diff,
            "status": status,
        })

    for record in [row for row in records if row["income_type"] == "freelance_invoice"]:
        if int(record["id"]) not in matched_record_ids and _amount(record.get("tds_amount")) > 0:
            findings.append({
                "severity": "warning",
                "type": "freelance_tds_mismatch",
                "message": f"Freelance invoice TDS for {record.get('payer') or record.get('record_date')} is not visible in active 26AS.",
                "record_id": record["id"],
                "record_date": record.get("record_date"),
                "payer": record.get("payer"),
            })
    return comparisons


def _matching_records(records: list[dict], income_type: str, name: str | None) -> list[dict]:
    if not name:
        return [row for row in records if row.get("income_type") == income_type]
    return [
        row for row in records
        if row.get("income_type") == income_type and _name_similarity(row.get("payer"), name) >= 0.55
    ]


def _summaries_by_doc(summaries: list[dict]) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for summary in summaries:
        grouped.setdefault(int(summary["tax_document_id"]), []).append(summary)
    return grouped


def _doc_public(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "document_id": doc["document_id"],
        "document_name": doc.get("document_name"),
        "source_type": doc["source_type"],
        "tan": doc.get("tan"),
        "deductor_name": doc.get("deductor_name"),
        "certificate_number": doc.get("certificate_number"),
        "period_from": doc.get("period_from"),
        "period_to": doc.get("period_to"),
    }


def _finding(severity: str, finding_type: str, message: str, form16: dict) -> dict:
    return {
        "severity": severity,
        "type": finding_type,
        "message": message,
        "tan": form16.get("tan"),
        "deductor_name": form16.get("deductor_name"),
        "certificate_number": form16.get("certificate_number"),
    }


def _month_finding(
    finding_type: str,
    message: str,
    form16: dict,
    month: str,
    ledger_salary: float,
    form26as_amount: float,
    ledger_tds: float,
    form26as_tds: float,
) -> dict:
    return {
        **_finding("warning", finding_type, message, form16),
        "month": month,
        "ledger_salary": round(ledger_salary, 2),
        "form26as_amount": round(form26as_amount, 2),
        "ledger_tds": round(ledger_tds, 2),
        "form26as_tds": round(form26as_tds, 2),
        "amount_difference": round(form26as_amount - ledger_salary, 2),
        "tds_difference": round(form26as_tds - ledger_tds, 2),
    }


def _row_with_metadata(row: Any) -> dict:
    item = row_to_dict(row)
    item["metadata"] = _json_loads(item.pop("metadata_json", "{}"), {})
    return item


def _json_loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def _amount(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _group_by_month(rows: list[dict], date_field: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        month = str(row.get(date_field) or "")[:7]
        if month:
            grouped.setdefault(month, []).append(row)
    return grouped


def _entry_matches_salary_candidate(entry: dict, tan: str, employer: str | None) -> bool:
    entry_tan = (entry.get("tan") or "").upper()
    if tan and entry_tan:
        return tan == entry_tan
    if employer:
        return _name_similarity(entry.get("deductor_name"), employer) >= 0.55
    return True


def _normalize_name(value: str | None) -> str:
    text = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in str(value or ""))
    ignored = {"private", "pvt", "limited", "ltd", "india", "the", "and"}
    return " ".join(token for token in text.split() if token not in ignored)


def _name_similarity(left: str | None, right: str | None) -> float:
    left_norm = _normalize_name(left)
    right_norm = _normalize_name(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if left_norm in right_norm or right_norm in left_norm:
        return 0.9
    return SequenceMatcher(None, left_norm, right_norm).ratio()
