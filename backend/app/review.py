from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .database import get_connection, row_to_dict
from .financial_year import financial_year_for, parse_date_strict
from .repositories import dashboard_data, list_documents
from .tax_reconciliation import tax_reconciliation_findings


def _json_loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def _document_year(doc: dict) -> str | None:
    extracted = doc.get("extracted") or {}
    if extracted.get("financial_year"):
        return extracted["financial_year"]
    record_date = extracted.get("record_date")
    if not record_date:
        return None
    try:
        return financial_year_for(parse_date_strict(record_date))
    except ValueError:
        return None


def _document_matches(doc: dict, user_id: str | None, financial_year: str | None) -> bool:
    extracted = doc.get("extracted") or {}
    if user_id and user_id != "all":
        doc_user = doc.get("detected_user_id") or extracted.get("user_id")
        if str(doc_user or "") != str(user_id):
            return False
    if financial_year:
        doc_year = _document_year(doc)
        if doc_year and doc_year != financial_year:
            return False
    return True


def list_audit_events(
    user_id: str | None = None,
    document_id: int | None = None,
    event_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    clauses: list[str] = []
    params: list[Any] = []
    if user_id and user_id != "all":
        clauses.append("a.user_id = ?")
        params.append(int(user_id))
    if document_id is not None:
        clauses.append("a.document_id = ?")
        params.append(int(document_id))
    if event_type:
        clauses.append("a.event_type = ?")
        params.append(event_type)
    if date_from:
        clauses.append("date(a.created_at) >= date(?)")
        params.append(date_from)
    if date_to:
        clauses.append("date(a.created_at) <= date(?)")
        params.append(date_to)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    safe_limit = min(max(int(limit or 100), 1), 500)
    safe_offset = max(int(offset or 0), 0)
    with get_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS count FROM audit_events a {where}", params).fetchone()["count"]
        rows = conn.execute(
            f"""
            SELECT a.*, u.name AS user_name, d.original_name AS document_name
            FROM audit_events a
            LEFT JOIN users u ON u.id = a.user_id
            LEFT JOIN documents d ON d.id = a.document_id
            {where}
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, safe_limit, safe_offset],
        ).fetchall()

    events = []
    for row in rows:
        item = row_to_dict(row)
        item["before"] = _json_loads(item.pop("before_json", "{}"), {})
        item["after"] = _json_loads(item.pop("after_json", "{}"), {})
        events.append(item)
    return {"items": events, "total": int(total), "limit": safe_limit, "offset": safe_offset}


def reconciliation_report(user_id: str | None = None, financial_year: str | None = None) -> dict:
    documents = list_documents()
    documents = [doc for doc in documents if _document_matches(doc, user_id, financial_year)]

    with get_connection() as conn:
        record_rows = conn.execute("SELECT id, user_id, document_id, financial_year FROM income_records WHERE document_id IS NOT NULL").fetchall()
        expense_rows = conn.execute("SELECT id, user_id, financial_year FROM freelance_expenses").fetchall()
        tax_rows = conn.execute("SELECT id, user_id, document_id, financial_year FROM tax_documents").fetchall()

    record_by_doc = {
        int(row["document_id"]): row_to_dict(row)
        for row in record_rows
        if row["document_id"] is not None and (not financial_year or row["financial_year"] == financial_year)
    }
    expense_by_id = {
        int(row["id"]): row_to_dict(row)
        for row in expense_rows
        if not financial_year or row["financial_year"] == financial_year
    }
    tax_by_doc = {
        int(row["document_id"]): row_to_dict(row)
        for row in tax_rows
        if row["document_id"] is not None and (not financial_year or row["financial_year"] == financial_year)
    }

    needs_review = []
    missing_files = []
    linked_documents = []
    unlinked_documents = []
    duplicate_documents = []
    seen_hashes: dict[str, dict] = {}

    for doc in documents:
        extracted = doc.get("extracted") or {}
        expense_id = extracted.get("expense_id")
        record = record_by_doc.get(int(doc["id"]))
        expense = expense_by_id.get(int(expense_id)) if expense_id else None
        tax_document = tax_by_doc.get(int(doc["id"]))
        if doc.get("status") != "confirmed":
            needs_review.append(doc)
        if doc.get("stored_path") and not Path(doc["stored_path"]).exists():
            missing_files.append(doc)
        if record or expense or tax_document:
            linked_documents.append({**doc, "linked_record": record, "linked_expense": expense, "linked_tax_document": tax_document})
        else:
            unlinked_documents.append(doc)
        file_hash = doc.get("file_hash")
        if file_hash and file_hash in seen_hashes:
            duplicate_documents.append({"document": doc, "duplicate_of": seen_hashes[file_hash]})
        elif file_hash:
            seen_hashes[file_hash] = doc

    return {
        "summary": {
            "needs_review": len(needs_review),
            "missing_files": len(missing_files),
            "linked_documents": len(linked_documents),
            "unlinked_documents": len(unlinked_documents),
            "duplicate_documents": len(duplicate_documents),
        },
        "needs_review": needs_review,
        "missing_files": missing_files,
        "linked_documents": linked_documents,
        "unlinked_documents": unlinked_documents,
        "duplicate_documents": duplicate_documents,
    }


def validation_report(user_id: str, financial_year: str) -> dict:
    data = dashboard_data(user_id, financial_year)
    findings: list[dict] = []

    seen_income_keys: dict[tuple, dict] = {}
    for record in data["records"]:
        metadata = record.get("metadata") or {}
        record_ref = {"record_id": record["id"], "record_date": record["record_date"], "payer": record.get("payer")}
        gross = float(record.get("gross_amount") or 0)
        net = float(record.get("net_amount") or 0)
        tds = float(record.get("tds_amount") or 0)
        gst = float(record.get("gst_amount") or 0)
        if record["income_type"] == "freelance_invoice":
            if gst <= 0:
                findings.append({"severity": "warning", "type": "freelance_missing_gst", "message": "Freelance invoice has no GST recorded.", **record_ref})
            if gross > 0 and abs(tds - round(gross * 0.10, 2)) > max(10, gross * 0.02):
                findings.append({"severity": "warning", "type": "freelance_tds_variance", "message": "TDS is far from expected 10% for this freelance invoice.", **record_ref})
            if "invoice_number" in metadata and not metadata.get("invoice_number"):
                findings.append({"severity": "info", "type": "missing_invoice_number", "message": "Invoice number is missing.", **record_ref})
        if net > gross and record["income_type"] != "purchase_expense":
            findings.append({"severity": "warning", "type": "net_greater_than_gross", "message": "Net amount is greater than gross amount.", **record_ref})

        duplicate_key = (record.get("payer") or "", record.get("record_date"), round(gross, 2), record["income_type"])
        if duplicate_key in seen_income_keys:
            findings.append({"severity": "warning", "type": "duplicate_income", "message": "Duplicate payer/date/amount income combination found.", **record_ref})
        else:
            seen_income_keys[duplicate_key] = record

        for warning in record.get("validation_warnings") or []:
            findings.append({"severity": "info", "type": "stored_validation_warning", "message": str(warning), **record_ref})

    linked_expense_ids = set()
    for doc in [item for item in list_documents() if _document_matches(item, user_id, financial_year)]:
        extracted = doc.get("extracted") or {}
        if extracted.get("expense_id"):
            linked_expense_ids.add(int(extracted["expense_id"]))
        if doc.get("status") == "needs_review":
            findings.append({"severity": "warning", "type": "document_needs_review", "message": "Document is waiting for review.", "document_id": doc["id"], "document_name": doc["original_name"]})
        if doc.get("stored_path") and not Path(doc["stored_path"]).exists():
            findings.append({"severity": "warning", "type": "missing_source_pdf", "message": "Source PDF file is missing from disk.", "document_id": doc["id"], "document_name": doc["original_name"]})

    for expense in data["expenses"]:
        if int(expense["id"]) not in linked_expense_ids:
            findings.append({"severity": "info", "type": "expense_without_document", "message": "Expense has no linked source document.", "expense_id": expense["id"], "expense_date": expense["expense_date"], "category": expense["category"]})

    if user_id and user_id != "all":
        findings.extend(tax_reconciliation_findings(user_id, financial_year))

    return {
        "financial_year": financial_year,
        "user_id": user_id,
        "summary": {
            "total": len(findings),
            "warnings": sum(1 for item in findings if item["severity"] == "warning"),
            "info": sum(1 for item in findings if item["severity"] == "info"),
        },
        "findings": findings,
    }
