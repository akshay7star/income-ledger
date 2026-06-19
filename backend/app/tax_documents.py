from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from .database import get_connection, row_to_dict
from .repositories import get_user, list_users


TAX_DOCUMENT_TYPES = {"form16_part_a", "form16_part_b", "form26as", "tax_statement_unknown"}
TAN_RE = re.compile(r"\b[A-Z]{4}\d{5}[A-Z]\b")
PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
AMOUNT_RE = re.compile(r"\d[\d,]*(?:\.\d{1,2})")
DATE_RE = re.compile(r"\b\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}\b|\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b")


@dataclass
class TaxSummary:
    source_type: str
    income_bucket: str = "salary"
    tan: str | None = None
    deductor_name: str | None = None
    gross_salary: float = 0.0
    salary_17_1: float = 0.0
    perquisites_17_2: float = 0.0
    profit_in_lieu_17_3: float = 0.0
    exempt_allowances_10: float = 0.0
    standard_deduction_16ia: float = 0.0
    professional_tax_16iii: float = 0.0
    income_chargeable_salary: float = 0.0
    other_income_reported: float = 0.0
    chapter_via_deductions: float = 0.0
    taxable_income: float = 0.0
    tax_payable: float = 0.0
    tds_deducted: float = 0.0
    tds_deposited: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaxEntry:
    source_type: str
    section: str | None = None
    income_bucket: str = "other"
    transaction_date: str | None = None
    booking_date: str | None = None
    booking_status: str | None = None
    quarter: str | None = None
    tan: str | None = None
    deductor_name: str | None = None
    amount_paid: float = 0.0
    tax_deducted: float = 0.0
    tax_deposited: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedTaxDocument:
    source_type: str
    financial_year: str
    assessment_year: str
    pan: str | None = None
    tan: str | None = None
    deductor_name: str | None = None
    certificate_number: str | None = None
    period_from: str | None = None
    period_to: str | None = None
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    summaries: list[TaxSummary] = field(default_factory=list)
    entries: list[TaxEntry] = field(default_factory=list)


def normalize_tax_text(text: str | None) -> str:
    return (text or "").replace("\xa0", " ").replace("\u200b", " ")


def detect_tax_document_type(text: str | None) -> str | None:
    normalized = normalize_tax_text(text)
    lower = normalized.lower()
    if "annual tax statement" in lower and "form 26as" in lower or "part-i - details of tax deducted at source" in lower:
        return "form26as"
    if "form no. 16" not in lower:
        return None
    if "summary of amount paid/credited" in lower or "details of tax deducted and deposited" in lower:
        return "form16_part_a"
    if "part b" in lower or "details of salary paid" in lower or "annexure" in lower:
        return "form16_part_b"
    if "part a" in lower or "summary of amount paid/credited" in lower:
        return "form16_part_a"
    return "tax_statement_unknown"


def parse_tax_statement_text(text: str, warnings: list[str] | None = None) -> ParsedTaxDocument | None:
    text = normalize_tax_text(text)
    source_type = detect_tax_document_type(text)
    if not source_type:
        return None
    parser_warnings = list(warnings or [])
    if source_type == "form26as":
        return _parse_26as(text, parser_warnings)
    if source_type == "form16_part_a":
        return _parse_form16_part_a(text, parser_warnings)
    if source_type == "form16_part_b":
        return _parse_form16_part_b(text, parser_warnings)
    parsed = _base_tax_document(text, source_type, parser_warnings)
    parsed.warnings.append("Tax statement type was detected, but the exact form layout needs review.")
    return parsed


def is_tax_statement_text(text: str | None) -> bool:
    return detect_tax_document_type(text) is not None


def build_tax_extraction(parsed: ParsedTaxDocument, warnings: list[str] | None = None, tax_document_id: int | None = None, user_id: int | None = None) -> dict:
    combined_warnings = [*list(warnings or []), *parsed.warnings]
    return {
        "document_type": parsed.source_type,
        "source_type": parsed.source_type,
        "tax_document_id": tax_document_id,
        "user_id": user_id,
        "financial_year": parsed.financial_year,
        "assessment_year": parsed.assessment_year,
        "pan": parsed.pan,
        "tan": parsed.tan,
        "deductor_name": parsed.deductor_name,
        "payer": parsed.deductor_name,
        "certificate_number": parsed.certificate_number,
        "period_from": parsed.period_from,
        "period_to": parsed.period_to,
        "confidence": parsed.confidence,
        "warnings": sorted(set(item for item in combined_warnings if item)),
        "summary_count": len(parsed.summaries),
        "entry_count": len(parsed.entries),
        "summaries": [_summary_to_public(item) for item in parsed.summaries],
    }


def resolve_tax_document_user(parsed: ParsedTaxDocument, selected_user_id: int | None) -> tuple[int | None, list[str]]:
    warnings: list[str] = []
    parsed_pan = (parsed.pan or "").upper().strip()
    if selected_user_id:
        selected = get_user(int(selected_user_id))
        if not selected:
            warnings.append("Selected user was not found.")
            return None, warnings
        user_pan = (selected.get("pan") or "").upper().strip()
        if parsed_pan and user_pan and parsed_pan != user_pan:
            warnings.append("Tax document PAN does not match the selected user PAN.")
        return int(selected["id"]), warnings

    if parsed_pan:
        for user in list_users():
            if (user.get("pan") or "").upper().strip() == parsed_pan:
                return int(user["id"]), warnings
    warnings.append("Tax document could not be matched to a saved user by PAN.")
    return None, warnings


def save_tax_document_parse(document_id: int, parsed: ParsedTaxDocument, user_id: int | None, warnings: list[str] | None = None) -> dict:
    extraction = build_tax_extraction(parsed, warnings, user_id=user_id)
    status = "confirmed" if user_id and parsed.confidence >= 0.7 and not any("PAN does not match" in item for item in extraction["warnings"]) else "needs_review"
    is_active = 1 if parsed.source_type != "form26as" or (status == "confirmed" and user_id) else 0

    with get_connection() as conn:
        document = conn.execute("SELECT * FROM documents WHERE id = ?", (int(document_id),)).fetchone()
        if not document:
            raise KeyError("Document not found")

        previous_tax_docs = conn.execute("SELECT id FROM tax_documents WHERE document_id = ?", (int(document_id),)).fetchall()
        for row in previous_tax_docs:
            conn.execute("DELETE FROM tax_documents WHERE id = ?", (row["id"],))

        cursor = conn.execute(
            """
            INSERT INTO tax_documents
                (document_id, user_id, financial_year, assessment_year, source_type, pan, tan,
                 deductor_name, certificate_number, period_from, period_to, is_active, confidence, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(document_id),
                user_id,
                parsed.financial_year,
                parsed.assessment_year,
                parsed.source_type,
                parsed.pan,
                parsed.tan,
                parsed.deductor_name,
                parsed.certificate_number,
                parsed.period_from,
                parsed.period_to,
                is_active,
                parsed.confidence,
                json.dumps(_parsed_to_raw(parsed)),
            ),
        )
        tax_document_id = int(cursor.lastrowid)

        if parsed.source_type == "form26as" and is_active and user_id:
            old_rows = conn.execute(
                """
                SELECT id FROM tax_documents
                WHERE user_id = ? AND financial_year = ? AND source_type = 'form26as'
                  AND is_active = 1 AND id != ?
                """,
                (user_id, parsed.financial_year, tax_document_id),
            ).fetchall()
            for old in old_rows:
                conn.execute(
                    "UPDATE tax_documents SET is_active = 0, superseded_by_tax_document_id = ? WHERE id = ?",
                    (tax_document_id, old["id"]),
                )

        for summary in parsed.summaries:
            conn.execute(
                """
                INSERT INTO tax_statement_summaries
                    (tax_document_id, user_id, financial_year, assessment_year, source_type, income_bucket,
                     tan, deductor_name, gross_salary, salary_17_1, perquisites_17_2, profit_in_lieu_17_3,
                     exempt_allowances_10, standard_deduction_16ia, professional_tax_16iii,
                     income_chargeable_salary, other_income_reported, chapter_via_deductions,
                     taxable_income, tax_payable, tds_deducted, tds_deposited, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tax_document_id,
                    user_id,
                    parsed.financial_year,
                    parsed.assessment_year,
                    parsed.source_type,
                    summary.income_bucket,
                    summary.tan,
                    summary.deductor_name,
                    summary.gross_salary,
                    summary.salary_17_1,
                    summary.perquisites_17_2,
                    summary.profit_in_lieu_17_3,
                    summary.exempt_allowances_10,
                    summary.standard_deduction_16ia,
                    summary.professional_tax_16iii,
                    summary.income_chargeable_salary,
                    summary.other_income_reported,
                    summary.chapter_via_deductions,
                    summary.taxable_income,
                    summary.tax_payable,
                    summary.tds_deducted,
                    summary.tds_deposited,
                    json.dumps(summary.metadata),
                ),
            )

        for entry in parsed.entries:
            conn.execute(
                """
                INSERT INTO tax_statement_entries
                    (tax_document_id, user_id, financial_year, assessment_year, source_type, section,
                     income_bucket, transaction_date, booking_date, booking_status, quarter, tan,
                     deductor_name, amount_paid, tax_deducted, tax_deposited, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tax_document_id,
                    user_id,
                    parsed.financial_year,
                    parsed.assessment_year,
                    parsed.source_type,
                    entry.section,
                    entry.income_bucket,
                    entry.transaction_date,
                    entry.booking_date,
                    entry.booking_status,
                    entry.quarter,
                    entry.tan,
                    entry.deductor_name,
                    entry.amount_paid,
                    entry.tax_deducted,
                    entry.tax_deposited,
                    json.dumps(entry.metadata),
                ),
            )

        extraction = build_tax_extraction(parsed, warnings, tax_document_id, user_id)
        conn.execute(
            """
            UPDATE documents
            SET document_type = ?, status = ?, extracted_json = ?, extracted_text = ?,
                detected_user_id = ?, confidence = ?, warnings = ?
            WHERE id = ?
            """,
            (
                parsed.source_type,
                status,
                json.dumps(extraction),
                document["extracted_text"],
                user_id,
                parsed.confidence,
                json.dumps(extraction["warnings"]),
                int(document_id),
            ),
        )
        conn.execute(
            """
            INSERT INTO audit_events (document_id, user_id, event_type, before_json, after_json)
            VALUES (?, ?, 'save_tax_document', ?, ?)
            """,
            (int(document_id), user_id, document["extracted_json"], json.dumps(extraction)),
        )
        conn.commit()

    from .repositories import get_document

    return get_document(int(document_id)) or {}


def list_tax_documents(user_id: str | None = None, financial_year: str | None = None) -> dict:
    clauses: list[str] = []
    params: list[Any] = []
    if user_id and user_id != "all":
        clauses.append("td.user_id = ?")
        params.append(int(user_id))
    if financial_year:
        clauses.append("td.financial_year = ?")
        params.append(financial_year)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT td.*, d.original_name AS document_name, d.status AS document_status,
                   u.name AS user_name
            FROM tax_documents td
            LEFT JOIN documents d ON d.id = td.document_id
            LEFT JOIN users u ON u.id = td.user_id
            {where}
            ORDER BY td.financial_year DESC, td.source_type, td.created_at DESC
            """,
            params,
        ).fetchall()
        summaries = conn.execute(
            f"""
            SELECT s.*
            FROM tax_statement_summaries s
            JOIN tax_documents td ON td.id = s.tax_document_id
            {where}
            ORDER BY s.deductor_name, s.income_bucket
            """,
            params,
        ).fetchall()
    items = []
    for row in rows:
        item = row_to_dict(row)
        item["raw"] = _json_loads(item.pop("raw_json", "{}"), {})
        item["summaries"] = [
            _row_with_metadata(summary)
            for summary in summaries
            if int(summary["tax_document_id"]) == int(item["id"])
        ]
        items.append(item)
    return {"items": items}


def activate_tax_document(document_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM tax_documents WHERE document_id = ? AND source_type = 'form26as'",
            (int(document_id),),
        ).fetchone()
        if not row:
            raise KeyError("Form 26AS tax document not found")
        if not row["user_id"]:
            raise ValueError("Cannot activate a 26AS document until it is matched to a user.")
        conn.execute(
            """
            UPDATE tax_documents
            SET is_active = 0, superseded_by_tax_document_id = ?
            WHERE user_id = ? AND financial_year = ? AND source_type = 'form26as' AND id != ?
            """,
            (row["id"], row["user_id"], row["financial_year"], row["id"]),
        )
        conn.execute("UPDATE tax_documents SET is_active = 1, superseded_by_tax_document_id = NULL WHERE id = ?", (row["id"],))
        conn.commit()
    from .repositories import get_document

    return get_document(int(document_id)) or {}


def section_income_bucket(section: str | None) -> str:
    normalized = str(section or "").upper().strip()
    if normalized == "192":
        return "salary"
    if normalized in {"194J", "194JA", "194JB", "194C", "194H", "194M", "194O", "194R"}:
        return "freelance"
    if normalized in {"194A"}:
        return "interest"
    if normalized in {"194I", "194IB"}:
        return "rent"
    return "other"


def _parse_26as(text: str, warnings: list[str]) -> ParsedTaxDocument:
    parsed = _base_tax_document(text, "form26as", warnings)
    parsed.deductor_name = None
    current_summary: TaxSummary | None = None

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        summary = _parse_26as_summary_line(line)
        if summary:
            parsed.summaries.append(summary)
            current_summary = summary
            continue
        entry = _parse_26as_entry_line(line, current_summary)
        if entry:
            parsed.entries.append(entry)

    if parsed.summaries:
        parsed.confidence = max(parsed.confidence, 0.92)
    else:
        parsed.warnings.append("Could not extract 26AS deductor summaries.")
        parsed.confidence = min(parsed.confidence, 0.45)
    return parsed


def _parse_form16_part_a(text: str, warnings: list[str]) -> ParsedTaxDocument:
    parsed = _base_tax_document(text, "form16_part_a", warnings)
    total_paid = 0.0
    total_tds = 0.0
    total_deposited = 0.0

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        quarter_match = re.match(r"^(Q[1-4])\b", line)
        if quarter_match:
            amounts = _amounts(line)
            if len(amounts) >= 3:
                entry = TaxEntry(
                    source_type="form16_part_a",
                    income_bucket="salary",
                    quarter=quarter_match.group(1),
                    tan=parsed.tan,
                    deductor_name=parsed.deductor_name,
                    amount_paid=amounts[-1],
                    tax_deducted=amounts[-3],
                    tax_deposited=amounts[-2],
                    metadata={"line": line},
                )
                parsed.entries.append(entry)
        if line.lower().startswith("total (rs.)"):
            amounts = _amounts(line)
            if len(amounts) >= 3:
                total_tds = amounts[-3]
                total_deposited = amounts[-2]
                total_paid = amounts[-1]

    if not total_paid and parsed.entries:
        total_paid = sum(item.amount_paid for item in parsed.entries)
        total_tds = sum(item.tax_deducted for item in parsed.entries)
        total_deposited = sum(item.tax_deposited for item in parsed.entries)

    parsed.summaries.append(
        TaxSummary(
            source_type="form16_part_a",
            income_bucket="salary",
            tan=parsed.tan,
            deductor_name=parsed.deductor_name,
            gross_salary=total_paid,
            tds_deducted=total_tds,
            tds_deposited=total_deposited,
        )
    )
    parsed.confidence = 0.9 if total_paid and total_tds else 0.55
    if not total_paid:
        parsed.warnings.append("Could not extract Form 16 Part A total paid/credited.")
    return parsed


def _parse_form16_part_b(text: str, warnings: list[str]) -> ParsedTaxDocument:
    parsed = _base_tax_document(text, "form16_part_b", warnings)
    salary_17_1 = _first_amount_after(r"Salary as per provisions[^\n]*section 17\(1\)", text)
    perquisites = _first_amount_after(r"Value of perquisites[\s\S]{0,120}?\(b\)", text)
    profit_in_lieu = _first_amount_after(r"Profits in lieu of salary[\s\S]{0,120}?\(c\)", text)
    gross_salary = _first_amount_after(r"\(d\)\s*Total", text)
    standard_deduction = _first_amount_after(r"Standard deduction under section 16\(ia\)", text)
    professional_tax = _first_amount_after(r"Tax on employment under section 16\(iii\)", text)
    chargeable = _first_amount_before(r"Gross total income", text)
    taxable = _first_amount_before(r"Total taxable income", text)
    tax_payable = _first_amount_after(r"Tax on total income", text)
    net_tax = _first_amount_after(r"Net tax payable", text)

    if not gross_salary:
        gross_salary = salary_17_1 + perquisites + profit_in_lieu
    if gross_salary and salary_17_1 and not perquisites:
        perquisites = max(0.0, gross_salary - salary_17_1 - profit_in_lieu)
    if not chargeable and gross_salary:
        chargeable = max(0.0, gross_salary - standard_deduction - professional_tax)
    if gross_salary and chargeable and not standard_deduction:
        standard_deduction = max(0.0, gross_salary - chargeable - professional_tax)
    if not taxable:
        taxable = chargeable
    if not net_tax:
        net_tax = tax_payable
    if not tax_payable:
        tax_payable = net_tax

    parsed.summaries.append(
        TaxSummary(
            source_type="form16_part_b",
            income_bucket="salary",
            tan=parsed.tan,
            deductor_name=parsed.deductor_name,
            gross_salary=gross_salary,
            salary_17_1=salary_17_1,
            perquisites_17_2=perquisites,
            profit_in_lieu_17_3=profit_in_lieu,
            standard_deduction_16ia=standard_deduction,
            professional_tax_16iii=professional_tax,
            income_chargeable_salary=chargeable,
            taxable_income=taxable,
            tax_payable=tax_payable or net_tax,
            tds_deducted=net_tax,
            tds_deposited=net_tax,
        )
    )
    parsed.confidence = 0.9 if gross_salary and chargeable else 0.55
    if not gross_salary:
        parsed.warnings.append("Could not extract Form 16 Part B gross salary.")
    return parsed


def _base_tax_document(text: str, source_type: str, warnings: list[str]) -> ParsedTaxDocument:
    assessment_year = _extract_assessment_year(text)
    financial_year = _extract_financial_year(text) or _fy_from_assessment_year(assessment_year)
    pan = _extract_user_pan(text, source_type)
    tan = _extract_tan(text)
    deductor_name = _extract_deductor_name(text, source_type)
    certificate_number = _extract_certificate_number(text)
    period_from, period_to = _extract_period(text)
    confidence = 0.65 if financial_year and pan else 0.35
    return ParsedTaxDocument(
        source_type=source_type,
        financial_year=financial_year or "",
        assessment_year=assessment_year or "",
        pan=pan,
        tan=tan,
        deductor_name=deductor_name,
        certificate_number=certificate_number,
        period_from=period_from,
        period_to=period_to,
        confidence=confidence,
        warnings=warnings,
    )


def _parse_26as_summary_line(line: str) -> TaxSummary | None:
    match = re.match(
        r"^\d+\s+(.+?)\s+([A-Z]{4}\d{5}[A-Z])\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})$",
        line,
    )
    if not match:
        return None
    name, tan, amount_paid, tds, deposited = match.groups()
    return TaxSummary(
        source_type="form26as",
        income_bucket="salary",
        tan=tan,
        deductor_name=name.strip(),
        gross_salary=_to_amount(amount_paid),
        tds_deducted=_to_amount(tds),
        tds_deposited=_to_amount(deposited),
        metadata={"line": line},
    )


def _parse_26as_entry_line(line: str, current_summary: TaxSummary | None) -> TaxEntry | None:
    match = re.match(
        r"^\d+\s+([A-Z0-9]+)\s+(\d{1,2}-[A-Za-z]{3}-\d{4})\s+([A-Z])\s+(\d{1,2}-[A-Za-z]{3}-\d{4})\s+.*?\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})$",
        line,
    )
    if not match:
        return None
    section, transaction_date, status, booking_date, amount_paid, tds, deposited = match.groups()
    bucket = section_income_bucket(section)
    if current_summary and current_summary.income_bucket == "salary" and bucket != "salary":
        current_summary.income_bucket = bucket
    return TaxEntry(
        source_type="form26as",
        section=section,
        income_bucket=bucket,
        transaction_date=_normalize_date(transaction_date),
        booking_date=_normalize_date(booking_date),
        booking_status=status,
        tan=current_summary.tan if current_summary else None,
        deductor_name=current_summary.deductor_name if current_summary else None,
        amount_paid=_to_amount(amount_paid),
        tax_deducted=_to_amount(tds),
        tax_deposited=_to_amount(deposited),
        metadata={"line": line},
    )


def _extract_assessment_year(text: str) -> str:
    match = re.search(r"Assessment Year\s*:?\s*(?:\n|\s)*(\d{4}\s*-\s*\d{2,4})", text, re.IGNORECASE)
    return _normalize_year_token(match.group(1)) if match else ""


def _extract_financial_year(text: str) -> str:
    match = re.search(r"Financial Year\s*(?:\n|\s)*(\d{4}\s*-\s*\d{2,4})", text, re.IGNORECASE)
    if not match:
        return ""
    year = _normalize_year_token(match.group(1))
    return f"FY {year}"


def _fy_from_assessment_year(assessment_year: str) -> str:
    try:
        start = int(str(assessment_year).split("-")[0]) - 1
        return f"FY {start}-{str(start + 1)[-2:]}"
    except Exception:
        return ""


def _normalize_year_token(value: str) -> str:
    compact = re.sub(r"\s+", "", value)
    start, end = compact.split("-", 1)
    return f"{start}-{end[-2:]}"


def _extract_user_pan(text: str, source_type: str) -> str | None:
    if source_type == "form26as":
        match = re.search(r"Permanent Account Number \(PAN\)\s*([A-Z]{5}\d{4}[A-Z])", text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    patterns = [
        r"PAN of (?:the\s+)?Employee[^\n]*\n?([A-Z]{5}\d{4}[A-Z])",
        r"PAN of Employee/Specified senior citizen\s*([A-Z]{5}\d{4}[A-Z])",
        r"PAN of the\s*\n?Employee/Specified senior\s*\n?citizen\s*([A-Z]{5}\d{4}[A-Z])",
        r"PAN of Employee:\s*([A-Z]{5}\d{4}[A-Z])",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    pans = PAN_RE.findall(text)
    return pans[-1].upper() if pans else None


def _extract_tan(text: str) -> str | None:
    match = re.search(r"TAN of (?:the\s+)?(?:Deductor|Employer)[^\n]*\n?([A-Z]{4}\d{5}[A-Z])", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    tans = TAN_RE.findall(text)
    return tans[0].upper() if tans else None


def _extract_deductor_name(text: str, source_type: str) -> str | None:
    if source_type == "form26as":
        for line in text.splitlines():
            parsed = _parse_26as_summary_line(" ".join(line.split()))
            if parsed:
                return parsed.deductor_name
    match = re.search(r"Name and address of the Employer/Specified Bank\s*\n([^\n]+)", text, re.IGNORECASE)
    if match:
        return " ".join(match.group(1).split())
    return None


def _extract_certificate_number(text: str) -> str | None:
    match = re.search(r"Certificate Number:\s*([A-Z0-9]+)", text, re.IGNORECASE)
    if not match:
        match = re.search(r"Certificate No\.\s*(?!Last\b)([A-Z0-9]+)", text, re.IGNORECASE)
    return match.group(1).upper() if match else None


def _extract_period(text: str) -> tuple[str | None, str | None]:
    match = re.search(r"Period with the Employer[\s\S]{0,80}?To\s*\n?([^\n]+)[\s\S]{0,80}?From\s*\n?([^\n]+)", text, re.IGNORECASE)
    if not match:
        return None, None
    period_to = _normalize_date(match.group(1).strip())
    period_from = _normalize_date(match.group(2).strip())
    return period_from, period_to


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().replace("/", "-")
    cleaned = re.sub(r"\s+", "", cleaned)
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    match = DATE_RE.search(value)
    if match and match.group(0) != value:
        return _normalize_date(match.group(0))
    return None


def _amounts(value: str) -> list[float]:
    return [_to_amount(item) for item in AMOUNT_RE.findall(value or "")]


def _to_amount(value: str | float | int | None) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return 0.0


def _first_amount_after(pattern: str, text: str) -> float:
    match = re.search(pattern + r"[\s\S]{0,160}?([\d,]+\.\d{2})", text, re.IGNORECASE)
    return _to_amount(match.group(1)) if match else 0.0


def _first_amount_before(label_pattern: str, text: str) -> float:
    match = re.search(r"([\d,]+\.\d{2})\s*" + label_pattern, text, re.IGNORECASE)
    return _to_amount(match.group(1)) if match else 0.0


def _summary_to_public(summary: TaxSummary) -> dict:
    payload = asdict(summary)
    payload["metadata_json"] = payload.pop("metadata", {})
    return payload


def _parsed_to_raw(parsed: ParsedTaxDocument) -> dict:
    payload = asdict(parsed)
    return payload


def _row_with_metadata(row: Any) -> dict:
    item = row_to_dict(row)
    item["metadata"] = _json_loads(item.pop("metadata_json", "{}"), {})
    return item


def _json_loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return fallback
