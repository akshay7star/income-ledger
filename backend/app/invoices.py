from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from .database import GENERATED_INVOICE_DIR, ensure_data_dirs, get_connection, row_to_dict
from .financial_year import financial_year_for, month_label, parse_date_strict


MONEY = Decimal("0.01")
GSTIN_PATTERN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_PATTERN = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")
STATE_CODE_PATTERN = re.compile(r"^\d{2}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INVOICE_STATUSES = {"draft", "issued", "cancelled"}
GST_TREATMENTS = {"same_state", "inter_state", "no_gst"}


class InvoiceConflictError(ValueError):
    pass


PROFILE_FIELDS = [
    "display_name",
    "legal_name",
    "address_line1",
    "address_line2",
    "city",
    "state_name",
    "state_code",
    "postal_code",
    "email",
    "phone",
    "gstin",
    "pan",
    "bank_name",
    "bank_account_name",
    "bank_account_number",
    "bank_ifsc",
    "signature_label",
]

CLIENT_FIELDS = [
    "client_name",
    "legal_name",
    "address_line1",
    "address_line2",
    "city",
    "state_name",
    "state_code",
    "postal_code",
    "email",
    "phone",
    "gstin",
    "pan",
]

INVOICE_TEXT_FIELDS = [
    "invoice_number",
    "billable_period",
    "place_of_supply",
    "payment_terms",
    "delivery_note",
    "reference_number",
    "other_references",
    "buyer_order_number",
    "dispatch_document_number",
    "dispatched_through",
    "destination",
    "terms_of_delivery",
    "ship_to_name",
    "ship_to_address_line1",
    "ship_to_address_line2",
    "ship_to_city",
    "ship_to_state_name",
    "ship_to_state_code",
    "ship_to_postal_code",
    "ship_to_gstin",
    "notes",
]

OPTIONAL_DATE_FIELDS = [
    "due_date",
    "reference_date",
    "buyer_order_date",
    "delivery_note_date",
]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value if value not in (None, "") else 0))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a valid number.") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be a finite number.")
    return result


def _money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _float(value: Decimal | float | int | str) -> float:
    return float(_money(value))


def _validate_identifier_fields(payload: dict, *, require_state: bool = False) -> None:
    gstin = _clean(payload.get("gstin")).upper()
    pan = _clean(payload.get("pan")).upper()
    state_code = _clean(payload.get("state_code"))
    email = _clean(payload.get("email"))
    if gstin and not GSTIN_PATTERN.fullmatch(gstin):
        raise ValueError("GSTIN must be a valid 15-character Indian GSTIN.")
    if pan and not PAN_PATTERN.fullmatch(pan):
        raise ValueError("PAN must use the format AAAAA9999A.")
    if (require_state or state_code) and not STATE_CODE_PATTERN.fullmatch(state_code):
        raise ValueError("State code must contain exactly two digits.")
    if email and not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Email address is not valid.")


def _normalize_profile(payload: dict) -> dict:
    normalized = {field: _clean(payload.get(field)) for field in PROFILE_FIELDS}
    normalized["display_name"] = normalized["display_name"] or normalized["legal_name"]
    if not normalized["display_name"]:
        raise ValueError("Seller display name is required.")
    normalized["legal_name"] = normalized["legal_name"] or normalized["display_name"]
    normalized["gstin"] = normalized["gstin"].upper()
    normalized["pan"] = normalized["pan"].upper()
    normalized["signature_label"] = normalized["signature_label"] or "Authorised Signatory"
    normalized["is_default"] = 1 if bool(payload.get("is_default")) else 0
    _validate_identifier_fields(normalized)
    return normalized


def _normalize_client(payload: dict) -> dict:
    normalized = {field: _clean(payload.get(field)) for field in CLIENT_FIELDS}
    normalized["client_name"] = normalized["client_name"] or normalized["legal_name"]
    if not normalized["client_name"]:
        raise ValueError("Client name is required.")
    normalized["legal_name"] = normalized["legal_name"] or normalized["client_name"]
    normalized["gstin"] = normalized["gstin"].upper()
    normalized["pan"] = normalized["pan"].upper()
    _validate_identifier_fields(normalized)
    return normalized


def sanitize_invoice_filename(invoice_number: str, invoice_id: int | None = None) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", _clean(invoice_number)).strip("._-")
    safe = safe[:80] or "invoice"
    prefix = f"{int(invoice_id)}-" if invoice_id is not None else ""
    return f"{prefix}{safe}.pdf"


def _safe_generated_path(filename: str) -> Path:
    ensure_data_dirs()
    base = GENERATED_INVOICE_DIR.resolve()
    target = (base / Path(filename).name).resolve()
    if target.parent != base:
        raise ValueError("Generated invoice path is unsafe.")
    return target


def _draft_pdf_path(invoice_id: int, invoice_number: str) -> Path:
    return _safe_generated_path(f"draft-{sanitize_invoice_filename(invoice_number, invoice_id)}")


def _issued_pdf_path(invoice_id: int, invoice_number: str) -> Path:
    return _safe_generated_path(sanitize_invoice_filename(invoice_number, invoice_id))


def _remove_draft_preview(invoice_id: int, invoice_number: str) -> None:
    path = _draft_pdf_path(invoice_id, invoice_number)
    if path.exists():
        path.unlink()


ONES = [
    "Zero",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _under_hundred(value: int) -> str:
    if value < 20:
        return ONES[value]
    return " ".join(part for part in [TENS[value // 10], ONES[value % 10] if value % 10 else ""] if part)


def _integer_words(value: int) -> str:
    if value == 0:
        return ONES[0]
    if value < 0:
        return f"Minus {_integer_words(abs(value))}"
    parts: list[str] = []
    for unit_value, unit_name in [
        (10_000_000, "Crore"),
        (100_000, "Lakh"),
        (1_000, "Thousand"),
        (100, "Hundred"),
    ]:
        if value >= unit_value:
            count, value = divmod(value, unit_value)
            parts.append(f"{_integer_words(count)} {unit_name}")
    if value:
        parts.append(_under_hundred(value))
    return " ".join(parts)


def amount_in_words(value: Any) -> str:
    amount = _money(_decimal(value, "Amount"))
    rupees = int(amount)
    paise = int((amount - Decimal(rupees)) * 100)
    words = f"INR {_integer_words(rupees)}"
    if paise:
        words += f" and {_integer_words(paise)} Paise"
    return f"{words} Only"


def _normalize_invoice_payload(payload: dict) -> dict:
    result = {field: _clean(payload.get(field)) for field in INVOICE_TEXT_FIELDS}
    result["invoice_number"] = result["invoice_number"]
    if not result["invoice_number"]:
        raise ValueError("Invoice number is required.")
    invoice_date = parse_date_strict(payload.get("invoice_date"))
    result["invoice_date"] = invoice_date.isoformat()
    result["financial_year"] = financial_year_for(invoice_date)
    for field in OPTIONAL_DATE_FIELDS:
        value = _clean(payload.get(field))
        result[field] = parse_date_strict(value).isoformat() if value else None
    result["seller_profile_id"] = int(payload.get("seller_profile_id") or 0)
    result["client_id"] = int(payload.get("client_id") or 0)
    if result["seller_profile_id"] <= 0:
        raise ValueError("Seller profile is required.")
    if result["client_id"] <= 0:
        raise ValueError("Client is required.")
    ledger_user_id = payload.get("ledger_user_id")
    result["ledger_user_id"] = int(ledger_user_id) if ledger_user_id not in (None, "", 0, "0") else None
    result["ship_to_same_as_bill_to"] = 1 if payload.get("ship_to_same_as_bill_to", True) else 0
    requested_treatment = _clean(payload.get("gst_treatment") or "same_state")
    if requested_treatment not in GST_TREATMENTS | {"auto"}:
        raise ValueError("GST treatment must be same_state, inter_state, no_gst, or auto.")
    result["gst_treatment"] = requested_treatment
    raw_tds_rate = payload.get("tds_rate")
    if raw_tds_rate not in (None, ""):
        tds_rate = _decimal(raw_tds_rate, "TDS rate")
        if tds_rate < 0 or tds_rate > 100:
            raise ValueError("TDS rate must be between 0% and 100%.")
        result["tds_rate"] = _float(tds_rate)
    else:
        result["tds_rate"] = None
    result["tds_amount"] = _float(_decimal(payload.get("tds_amount"), "TDS amount"))
    if result["tds_amount"] < 0:
        raise ValueError("TDS amount cannot be negative.")
    if not result["ship_to_same_as_bill_to"]:
        ship_payload = {
            "gstin": result["ship_to_gstin"],
            "state_code": result["ship_to_state_code"],
        }
        _validate_identifier_fields(ship_payload, require_state=requested_treatment != "no_gst")
        if not result["ship_to_name"]:
            raise ValueError("Ship To name is required when it differs from Bill To.")
    return result


def calculate_invoice(payload: dict, seller: dict, client: dict) -> dict:
    normalized = _normalize_invoice_payload(payload)
    raw_items = payload.get("items") or []
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("At least one invoice line item is required.")

    supply_state_code = (
        _clean(normalized.get("ship_to_state_code"))
        if not normalized["ship_to_same_as_bill_to"]
        else _clean(client.get("state_code"))
    )
    seller_state_code = _clean(seller.get("state_code"))
    requested_treatment = normalized["gst_treatment"]
    if requested_treatment == "no_gst":
        treatment = "no_gst"
    else:
        if not STATE_CODE_PATTERN.fullmatch(seller_state_code):
            raise ValueError("Seller state code is required for GST invoices.")
        if not STATE_CODE_PATTERN.fullmatch(supply_state_code):
            raise ValueError("Supply state code is required for GST invoices.")
        treatment = "same_state" if seller_state_code == supply_state_code else "inter_state"

    items: list[dict] = []
    subtotal = Decimal("0")
    cgst_total = Decimal("0")
    sgst_total = Decimal("0")
    igst_total = Decimal("0")
    for index, raw_item in enumerate(raw_items, start=1):
        description = _clean(raw_item.get("description"))
        if not description:
            raise ValueError(f"Line {index}: description is required.")
        quantity = _decimal(raw_item.get("quantity"), f"Line {index} quantity")
        if quantity <= 0:
            raise ValueError(f"Line {index}: quantity must be greater than zero.")
        has_amount = raw_item.get("amount") not in (None, "")
        if has_amount:
            taxable_input = _decimal(raw_item.get("amount"), f"Line {index} amount")
            gst_rate = _decimal(raw_item.get("rate"), f"Line {index} GST rate")
            if taxable_input < 0:
                raise ValueError(f"Line {index}: amount cannot be negative.")
            taxable = _money(taxable_input)
        else:
            # Compatibility for drafts/API clients created before Amount became
            # explicit: rate was the unit price and gst_rate held the GST percent.
            legacy_unit_rate = _decimal(raw_item.get("rate"), f"Line {index} rate")
            gst_rate = _decimal(raw_item.get("gst_rate"), f"Line {index} GST rate")
            if legacy_unit_rate < 0:
                raise ValueError(f"Line {index}: rate cannot be negative.")
            taxable = _money(quantity * legacy_unit_rate)
        if gst_rate < 0 or gst_rate > 100:
            raise ValueError(f"Line {index}: GST rate must be between 0% and 100%.")
        if treatment == "same_state":
            cgst_rate = gst_rate / Decimal("2")
            sgst_rate = gst_rate / Decimal("2")
            igst_rate = Decimal("0")
            cgst = _money(taxable * cgst_rate / Decimal("100"))
            sgst = _money(taxable * sgst_rate / Decimal("100"))
            igst = Decimal("0")
        elif treatment == "inter_state":
            cgst_rate = Decimal("0")
            sgst_rate = Decimal("0")
            igst_rate = gst_rate
            cgst = Decimal("0")
            sgst = Decimal("0")
            igst = _money(taxable * igst_rate / Decimal("100"))
        else:
            gst_rate = Decimal("0")
            cgst_rate = Decimal("0")
            sgst_rate = Decimal("0")
            igst_rate = Decimal("0")
            cgst = Decimal("0")
            sgst = Decimal("0")
            igst = Decimal("0")
        total = _money(taxable + cgst + sgst + igst)
        item = {
            "line_number": index,
            "description": description,
            "hsn_sac": _clean(raw_item.get("hsn_sac")),
            "quantity": float(quantity),
            "unit": _clean(raw_item.get("unit") or "Nos"),
            "rate": _float(gst_rate),
            "amount": _float(taxable),
            "taxable_amount": _float(taxable),
            "gst_rate": _float(gst_rate),
            "cgst_rate": _float(cgst_rate),
            "sgst_rate": _float(sgst_rate),
            "igst_rate": _float(igst_rate),
            "cgst_amount": _float(cgst),
            "sgst_amount": _float(sgst),
            "igst_amount": _float(igst),
            "total_amount": _float(total),
        }
        items.append(item)
        subtotal += taxable
        cgst_total += cgst
        sgst_total += sgst
        igst_total += igst

    subtotal = _money(subtotal)
    cgst_total = _money(cgst_total)
    sgst_total = _money(sgst_total)
    igst_total = _money(igst_total)
    gst_total = _money(cgst_total + sgst_total + igst_total)
    grand_total = _money(subtotal + gst_total)
    if normalized["tds_rate"] is None:
        tds = _money(normalized["tds_amount"])
        if tds > subtotal:
            raise ValueError("TDS amount cannot exceed the taxable service value.")
        tds_rate = (
            (tds * Decimal("100") / subtotal)
            if subtotal
            else Decimal("0")
        )
    else:
        tds_rate = _decimal(normalized["tds_rate"], "TDS rate")
        tds = _money(subtotal * tds_rate / Decimal("100"))
    net_receivable = _money(grand_total - tds)
    return {
        **normalized,
        "gst_treatment": treatment,
        "items": items,
        "subtotal_amount": _float(subtotal),
        "cgst_amount": _float(cgst_total),
        "sgst_amount": _float(sgst_total),
        "igst_amount": _float(igst_total),
        "gst_amount": _float(gst_total),
        "grand_total_amount": _float(grand_total),
        "tds_rate": _float(tds_rate),
        "tds_amount": _float(tds),
        "net_receivable_amount": _float(net_receivable),
        "amount_words": amount_in_words(grand_total),
    }


def list_invoice_profiles() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM invoice_profiles ORDER BY is_default DESC, display_name COLLATE NOCASE, id"
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def create_invoice_profile(payload: dict) -> dict:
    data = _normalize_profile(payload)
    with get_connection() as conn:
        if data["is_default"]:
            conn.execute("UPDATE invoice_profiles SET is_default = 0, updated_at = CURRENT_TIMESTAMP")
        cursor = conn.execute(
            f"""
            INSERT INTO invoice_profiles ({", ".join(PROFILE_FIELDS)}, is_default)
            VALUES ({", ".join("?" for _ in PROFILE_FIELDS)}, ?)
            """,
            tuple(data[field] for field in PROFILE_FIELDS) + (data["is_default"],),
        )
        row = conn.execute("SELECT * FROM invoice_profiles WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row)


def update_invoice_profile(profile_id: int, payload: dict) -> dict:
    data = _normalize_profile(payload)
    with get_connection() as conn:
        if not conn.execute("SELECT id FROM invoice_profiles WHERE id = ?", (profile_id,)).fetchone():
            raise KeyError("Seller profile not found")
        if data["is_default"]:
            conn.execute(
                "UPDATE invoice_profiles SET is_default = 0, updated_at = CURRENT_TIMESTAMP WHERE id <> ?",
                (profile_id,),
            )
        assignments = ", ".join(f"{field} = ?" for field in PROFILE_FIELDS)
        conn.execute(
            f"UPDATE invoice_profiles SET {assignments}, is_default = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            tuple(data[field] for field in PROFILE_FIELDS) + (data["is_default"], profile_id),
        )
        row = conn.execute("SELECT * FROM invoice_profiles WHERE id = ?", (profile_id,)).fetchone()
    return row_to_dict(row)


def delete_invoice_profile(profile_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM invoice_profiles WHERE id = ?", (profile_id,)).fetchone()
        if not row:
            raise KeyError("Seller profile not found")
        used = conn.execute(
            "SELECT 1 FROM generated_invoices WHERE seller_profile_id = ? LIMIT 1", (profile_id,)
        ).fetchone()
        if used:
            raise InvoiceConflictError("Seller profile is already used by an invoice and cannot be deleted.")
        conn.execute("DELETE FROM invoice_profiles WHERE id = ?", (profile_id,))
    return {"deleted": True, "id": profile_id}


def list_invoice_clients() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM invoice_clients ORDER BY client_name COLLATE NOCASE, id"
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def create_invoice_client(payload: dict) -> dict:
    data = _normalize_client(payload)
    with get_connection() as conn:
        cursor = conn.execute(
            f"""
            INSERT INTO invoice_clients ({", ".join(CLIENT_FIELDS)})
            VALUES ({", ".join("?" for _ in CLIENT_FIELDS)})
            """,
            tuple(data[field] for field in CLIENT_FIELDS),
        )
        row = conn.execute("SELECT * FROM invoice_clients WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row)


def update_invoice_client(client_id: int, payload: dict) -> dict:
    data = _normalize_client(payload)
    with get_connection() as conn:
        if not conn.execute("SELECT id FROM invoice_clients WHERE id = ?", (client_id,)).fetchone():
            raise KeyError("Invoice client not found")
        assignments = ", ".join(f"{field} = ?" for field in CLIENT_FIELDS)
        conn.execute(
            f"UPDATE invoice_clients SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            tuple(data[field] for field in CLIENT_FIELDS) + (client_id,),
        )
        row = conn.execute("SELECT * FROM invoice_clients WHERE id = ?", (client_id,)).fetchone()
    return row_to_dict(row)


def delete_invoice_client(client_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM invoice_clients WHERE id = ?", (client_id,)).fetchone()
        if not row:
            raise KeyError("Invoice client not found")
        used = conn.execute(
            "SELECT 1 FROM generated_invoices WHERE client_id = ? LIMIT 1", (client_id,)
        ).fetchone()
        if used:
            raise InvoiceConflictError("Client is already used by an invoice and cannot be deleted.")
        conn.execute("DELETE FROM invoice_clients WHERE id = ?", (client_id,))
    return {"deleted": True, "id": client_id}


def _load_parties(conn, seller_profile_id: int, client_id: int) -> tuple[dict, dict]:
    seller = conn.execute(
        "SELECT * FROM invoice_profiles WHERE id = ?", (seller_profile_id,)
    ).fetchone()
    client = conn.execute("SELECT * FROM invoice_clients WHERE id = ?", (client_id,)).fetchone()
    if not seller:
        raise ValueError("Seller profile does not exist.")
    if not client:
        raise ValueError("Invoice client does not exist.")
    return row_to_dict(seller), row_to_dict(client)


def _insert_items(conn, invoice_id: int, items: list[dict]) -> None:
    for item in items:
        conn.execute(
            """
            INSERT INTO generated_invoice_items (
                invoice_id, line_number, description, hsn_sac, quantity, unit, rate,
                taxable_amount, gst_rate, cgst_rate, sgst_rate, igst_rate,
                cgst_amount, sgst_amount, igst_amount, total_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_id,
                item["line_number"],
                item["description"],
                item["hsn_sac"],
                item["quantity"],
                item["unit"],
                item["rate"],
                item["taxable_amount"],
                item["gst_rate"],
                item["cgst_rate"],
                item["sgst_rate"],
                item["igst_rate"],
                item["cgst_amount"],
                item["sgst_amount"],
                item["igst_amount"],
                item["total_amount"],
            ),
        )


def _invoice_header_values(data: dict) -> tuple:
    return (
        data["invoice_number"],
        data["invoice_date"],
        data["financial_year"],
        data["billable_period"],
        data["seller_profile_id"],
        data["client_id"],
        data["ledger_user_id"],
        data["place_of_supply"],
        data["gst_treatment"],
        data["payment_terms"],
        data["due_date"],
        data["delivery_note"],
        data["reference_number"],
        data["reference_date"],
        data["other_references"],
        data["buyer_order_number"],
        data["buyer_order_date"],
        data["dispatch_document_number"],
        data["delivery_note_date"],
        data["dispatched_through"],
        data["destination"],
        data["terms_of_delivery"],
        data["ship_to_same_as_bill_to"],
        data["ship_to_name"],
        data["ship_to_address_line1"],
        data["ship_to_address_line2"],
        data["ship_to_city"],
        data["ship_to_state_name"],
        data["ship_to_state_code"],
        data["ship_to_postal_code"],
        data["ship_to_gstin"],
        data["subtotal_amount"],
        data["cgst_amount"],
        data["sgst_amount"],
        data["igst_amount"],
        data["gst_amount"],
        data["grand_total_amount"],
        data["tds_rate"],
        data["tds_amount"],
        data["net_receivable_amount"],
        data["amount_words"],
        data["notes"],
    )


INVOICE_HEADER_COLUMNS = [
    "invoice_number",
    "invoice_date",
    "financial_year",
    "billable_period",
    "seller_profile_id",
    "client_id",
    "ledger_user_id",
    "place_of_supply",
    "gst_treatment",
    "payment_terms",
    "due_date",
    "delivery_note",
    "reference_number",
    "reference_date",
    "other_references",
    "buyer_order_number",
    "buyer_order_date",
    "dispatch_document_number",
    "delivery_note_date",
    "dispatched_through",
    "destination",
    "terms_of_delivery",
    "ship_to_same_as_bill_to",
    "ship_to_name",
    "ship_to_address_line1",
    "ship_to_address_line2",
    "ship_to_city",
    "ship_to_state_name",
    "ship_to_state_code",
    "ship_to_postal_code",
    "ship_to_gstin",
    "subtotal_amount",
    "cgst_amount",
    "sgst_amount",
    "igst_amount",
    "gst_amount",
    "grand_total_amount",
    "tds_rate",
    "tds_amount",
    "net_receivable_amount",
    "amount_words",
    "notes",
]


def create_invoice_draft(payload: dict) -> dict:
    with get_connection() as conn:
        seller, client = _load_parties(
            conn, int(payload.get("seller_profile_id") or 0), int(payload.get("client_id") or 0)
        )
        data = calculate_invoice(payload, seller, client)
        try:
            cursor = conn.execute(
                f"""
                INSERT INTO generated_invoices ({", ".join(INVOICE_HEADER_COLUMNS)})
                VALUES ({", ".join("?" for _ in INVOICE_HEADER_COLUMNS)})
                """,
                _invoice_header_values(data),
            )
        except sqlite3.IntegrityError as exc:
            if "generated_invoices.financial_year, generated_invoices.invoice_number" in str(exc):
                raise InvoiceConflictError(
                    "Invoice number already exists in this financial year."
                ) from exc
            raise
        invoice_id = int(cursor.lastrowid)
        _insert_items(conn, invoice_id, data["items"])
        after_json = json.dumps(
            {
                "generated_invoice_id": invoice_id,
                "invoice_number": data["invoice_number"],
                "status": "draft",
                "totals": {
                    "subtotal_amount": data["subtotal_amount"],
                    "gst_amount": data["gst_amount"],
                    "grand_total_amount": data["grand_total_amount"],
                },
            }
        )
        conn.execute(
            """
            INSERT INTO audit_events (document_id, user_id, event_type, before_json, after_json)
            VALUES (NULL, ?, 'create_invoice_draft', '{}', ?)
            """,
            (data["ledger_user_id"], after_json),
        )
    return get_invoice(invoice_id)


def _invoice_detail(conn, invoice_id: int) -> dict:
    row = conn.execute(
        """
        SELECT gi.*, ip.display_name AS seller_name, ic.client_name AS client_name
        FROM generated_invoices gi
        JOIN invoice_profiles ip ON ip.id = gi.seller_profile_id
        JOIN invoice_clients ic ON ic.id = gi.client_id
        WHERE gi.id = ?
        """,
        (invoice_id,),
    ).fetchone()
    if not row:
        raise KeyError("Invoice not found")
    invoice = row_to_dict(row)
    items = conn.execute(
        "SELECT * FROM generated_invoice_items WHERE invoice_id = ? ORDER BY line_number, id",
        (invoice_id,),
    ).fetchall()
    seller = conn.execute(
        "SELECT * FROM invoice_profiles WHERE id = ?", (invoice["seller_profile_id"],)
    ).fetchone()
    client = conn.execute(
        "SELECT * FROM invoice_clients WHERE id = ?", (invoice["client_id"],)
    ).fetchone()
    try:
        metadata = json.loads(invoice.get("metadata_json") or "{}")
    except json.JSONDecodeError:
        metadata = {}
    public = {
        key: value
        for key, value in invoice.items()
        if key not in {"metadata_json", "pdf_path"}
    }
    public["metadata"] = metadata
    public_items = []
    for item in items:
        public_item = row_to_dict(item)
        public_item["amount"] = public_item["taxable_amount"]
        public_item["rate"] = public_item["gst_rate"]
        public_items.append(public_item)
    public["items"] = public_items
    if not public.get("tds_rate") and public.get("tds_amount") and public.get("subtotal_amount"):
        public["tds_rate"] = round(
            public["tds_amount"] * 100 / public["subtotal_amount"], 6
        )
    public["seller"] = row_to_dict(seller)
    public["client"] = row_to_dict(client)
    pdf_path = _safe_generated_path(Path(invoice.get("pdf_path") or "").name) if invoice.get("pdf_path") else None
    if invoice["status"] == "draft":
        preview_path = _draft_pdf_path(invoice_id, invoice["invoice_number"])
        public["pdf_available"] = preview_path.exists()
        public["pdf_filename"] = preview_path.name if preview_path.exists() else ""
    else:
        public["pdf_available"] = bool(pdf_path and pdf_path.exists())
        public["pdf_filename"] = pdf_path.name if pdf_path else ""
    public["linked_income"] = bool(invoice.get("income_record_id"))
    return public


def get_invoice(invoice_id: int) -> dict:
    with get_connection() as conn:
        return _invoice_detail(conn, invoice_id)


def list_generated_invoices(
    financial_year: str | None = None,
    status: str | None = None,
    client_id: int | None = None,
    ledger_user_id: int | None = None,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if financial_year:
        clauses.append("gi.financial_year = ?")
        params.append(financial_year)
    if status:
        if status not in INVOICE_STATUSES:
            raise ValueError("Invoice status is invalid.")
        clauses.append("gi.status = ?")
        params.append(status)
    if client_id:
        clauses.append("gi.client_id = ?")
        params.append(int(client_id))
    if ledger_user_id:
        clauses.append("gi.ledger_user_id = ?")
        params.append(int(ledger_user_id))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT gi.id, gi.invoice_number, gi.invoice_date, gi.financial_year,
                   gi.billable_period, gi.status, gi.seller_profile_id, gi.client_id,
                   gi.ledger_user_id, gi.subtotal_amount, gi.cgst_amount, gi.sgst_amount,
                   gi.igst_amount, gi.gst_amount, gi.grand_total_amount, gi.tds_rate,
                   gi.tds_amount,
                   gi.net_receivable_amount, gi.income_record_id, gi.pdf_path,
                   gi.created_at, gi.updated_at, gi.issued_at,
                   ip.display_name AS seller_name, ic.client_name AS client_name
            FROM generated_invoices gi
            JOIN invoice_profiles ip ON ip.id = gi.seller_profile_id
            JOIN invoice_clients ic ON ic.id = gi.client_id
            {where}
            ORDER BY gi.invoice_date DESC, gi.id DESC
            """,
            params,
        ).fetchall()
    result = []
    for row in rows:
        item = row_to_dict(row)
        if item["status"] == "draft":
            path = _draft_pdf_path(item["id"], item["invoice_number"])
        else:
            path = _safe_generated_path(Path(item.get("pdf_path") or "").name) if item.get("pdf_path") else None
        item["pdf_available"] = bool(path and path.exists())
        item["pdf_filename"] = path.name if path else ""
        item["linked_income"] = bool(item.get("income_record_id"))
        item.pop("pdf_path", None)
        result.append(item)
    return result


def update_invoice_draft(invoice_id: int, payload: dict) -> dict:
    old_number = ""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM generated_invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        if not existing:
            raise KeyError("Invoice not found")
        existing_dict = row_to_dict(existing)
        old_number = existing_dict["invoice_number"]
        if existing_dict["status"] != "draft":
            raise InvoiceConflictError("Only draft invoices can be edited.")
        seller, client = _load_parties(
            conn, int(payload.get("seller_profile_id") or 0), int(payload.get("client_id") or 0)
        )
        data = calculate_invoice(payload, seller, client)
        assignments = ", ".join(f"{column} = ?" for column in INVOICE_HEADER_COLUMNS)
        try:
            conn.execute(
                f"""
                UPDATE generated_invoices
                SET {assignments}, pdf_path = '', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                _invoice_header_values(data) + (invoice_id,),
            )
        except sqlite3.IntegrityError as exc:
            if "generated_invoices.financial_year, generated_invoices.invoice_number" in str(exc):
                raise InvoiceConflictError(
                    "Invoice number already exists in this financial year."
                ) from exc
            raise
        conn.execute("DELETE FROM generated_invoice_items WHERE invoice_id = ?", (invoice_id,))
        _insert_items(conn, invoice_id, data["items"])
        before_json = json.dumps(
            {
                "generated_invoice_id": invoice_id,
                "invoice_number": old_number,
                "status": existing_dict["status"],
                "subtotal_amount": existing_dict["subtotal_amount"],
                "gst_amount": existing_dict["gst_amount"],
                "grand_total_amount": existing_dict["grand_total_amount"],
            }
        )
        after_json = json.dumps(
            {
                "generated_invoice_id": invoice_id,
                "invoice_number": data["invoice_number"],
                "status": "draft",
                "subtotal_amount": data["subtotal_amount"],
                "gst_amount": data["gst_amount"],
                "grand_total_amount": data["grand_total_amount"],
            }
        )
        conn.execute(
            """
            INSERT INTO audit_events (document_id, user_id, event_type, before_json, after_json)
            VALUES (NULL, ?, 'update_invoice_draft', ?, ?)
            """,
            (data["ledger_user_id"], before_json, after_json),
        )
    _remove_draft_preview(invoice_id, old_number)
    if old_number != _clean(payload.get("invoice_number")):
        _remove_draft_preview(invoice_id, _clean(payload.get("invoice_number")))
    return get_invoice(invoice_id)


def delete_invoice_draft(invoice_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM generated_invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        if not row:
            raise KeyError("Invoice not found")
        invoice = row_to_dict(row)
        if invoice["status"] != "draft":
            raise InvoiceConflictError("Only draft invoices can be deleted.")
        before_json = json.dumps(
            {
                "generated_invoice_id": invoice_id,
                "invoice_number": invoice["invoice_number"],
                "status": invoice["status"],
            }
        )
        conn.execute("DELETE FROM generated_invoices WHERE id = ?", (invoice_id,))
        conn.execute(
            """
            INSERT INTO audit_events (document_id, user_id, event_type, before_json, after_json)
            VALUES (NULL, ?, 'delete_invoice_draft', ?, '{}')
            """,
            (invoice.get("ledger_user_id"), before_json),
        )
    _remove_draft_preview(invoice_id, invoice["invoice_number"])
    return {"deleted": True, "id": invoice_id}


def _reportlab():
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError("ReportLab is required to generate invoice PDFs.") from exc
    return letter, stringWidth, canvas


def _format_money(value: Any) -> str:
    amount = _money(_decimal(value, "Amount"))
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    integer, fraction = f"{amount:.2f}".split(".")
    if len(integer) > 3:
        last_three = integer[-3:]
        remaining = integer[:-3]
        pairs = []
        while remaining:
            pairs.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        integer = ",".join([*pairs, last_three])
    return f"{sign}{integer}.{fraction}"


def _wrap_text(text: Any, width: float, size: float, font: str = "Helvetica") -> list[str]:
    _letter, string_width, _canvas = _reportlab()
    words = _clean(text).split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if string_width(candidate, font, size) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _party_lines(party: dict, *, ship_to: bool = False) -> list[str]:
    prefix = "ship_to_" if ship_to else ""
    name = _clean(party.get(f"{prefix}legal_name") or party.get(f"{prefix}name"))
    if not name:
        name = _clean(party.get("legal_name") or party.get("client_name") or party.get("display_name"))
    address_line1 = _clean(party.get(f"{prefix}address_line1"))
    address_line2 = _clean(party.get(f"{prefix}address_line2"))
    city = _clean(party.get(f"{prefix}city"))
    state = _clean(party.get(f"{prefix}state_name"))
    postal_code = _clean(party.get(f"{prefix}postal_code"))
    location = ", ".join(part for part in [city, state] if part)
    if postal_code:
        location = f"{location} - {postal_code}" if location else postal_code
    lines = [name, *[part for part in [address_line1, address_line2, location] if part]]
    email = _clean(party.get(f"{prefix}email") or party.get("email"))
    phone = _clean(party.get(f"{prefix}phone") or party.get("phone"))
    contact = " | ".join(part for part in [email, phone] if part)
    if contact:
        lines.append(contact)
    gstin = _clean(party.get(f"{prefix}gstin") or party.get("gstin"))
    state_name = _clean(party.get(f"{prefix}state_name") or party.get("state_name"))
    state_code = _clean(party.get(f"{prefix}state_code") or party.get("state_code"))
    if gstin:
        lines.append(f"GSTIN/UIN: {gstin}")
    if state_name or state_code:
        lines.append(f"State Name: {state_name}, Code: {state_code}".strip(", "))
    return lines


def _draw_text(c, text: Any, x: float, top: float, size: float = 8.5, font: str = "Helvetica") -> None:
    c.setFont(font, size)
    c.drawString(x, 792 - top - size, _clean(text))


def _draw_right(c, text: Any, right: float, top: float, size: float = 8.5, font: str = "Helvetica") -> None:
    c.setFont(font, size)
    c.drawRightString(right, 792 - top - size, _clean(text))


def _draw_center(c, text: Any, center: float, top: float, size: float = 8.5, font: str = "Helvetica") -> None:
    c.setFont(font, size)
    c.drawCentredString(center, 792 - top - size, _clean(text))


def _line(c, x1: float, top1: float, x2: float, top2: float, width: float = 0.375) -> None:
    c.setLineWidth(width)
    c.line(x1, 792 - top1, x2, 792 - top2)


def _rect(c, x: float, top: float, width: float, height: float, stroke: float = 0.375) -> None:
    c.setLineWidth(stroke)
    c.rect(x, 792 - top - height, width, height, stroke=1, fill=0)


def _draw_wrapped(
    c,
    text: Any,
    x: float,
    top: float,
    width: float,
    size: float = 8.5,
    font: str = "Helvetica",
    leading: float | None = None,
    max_lines: int | None = None,
) -> float:
    leading = leading or size + 1.5
    lines = _wrap_text(text, width, size, font)
    if max_lines:
        lines = lines[:max_lines]
    for index, line in enumerate(lines):
        _draw_text(c, line, x, top + index * leading, size, font)
    return top + len(lines) * leading


def _display_date(value: Any) -> str:
    if not value:
        return ""
    try:
        return parse_date_strict(value).strftime("%d-%b-%y")
    except ValueError:
        return _clean(value)


def _draw_party_block(c, label: str, party: dict, top: float, bottom: float) -> None:
    _draw_text(c, label, 38.75, top + 2, 8.5)
    lines = _party_lines(party)
    cursor = top + 14
    for index, line_text in enumerate(lines):
        font = "Helvetica-Bold" if index == 0 else "Helvetica"
        size = 8.8 if index == 0 else 7.4
        cursor = _draw_wrapped(c, line_text, 38.75, cursor, 231, size, font, size + 0.8, 1)
        if cursor > bottom - 7:
            break


def _ship_to_party(invoice: dict) -> dict:
    if invoice.get("ship_to_same_as_bill_to"):
        return invoice["client"]
    return {
        "legal_name": invoice.get("ship_to_name"),
        "address_line1": invoice.get("ship_to_address_line1"),
        "address_line2": invoice.get("ship_to_address_line2"),
        "city": invoice.get("ship_to_city"),
        "state_name": invoice.get("ship_to_state_name"),
        "state_code": invoice.get("ship_to_state_code"),
        "postal_code": invoice.get("ship_to_postal_code"),
        "gstin": invoice.get("ship_to_gstin"),
    }


def _draw_header(c, invoice: dict, page_number: int, page_count: int) -> None:
    _draw_center(c, "Tax Invoice", 270, 18, 12, "Helvetica-Bold")
    _rect(c, 36, 44, 468, 272)
    _line(c, 274, 44, 274, 316)
    _line(c, 36, 120, 274, 120)
    _line(c, 36, 218, 274, 218)
    _draw_party_block(c, "", invoice["seller"], 44, 120)
    _draw_party_block(c, "Consignee (Ship to)", _ship_to_party(invoice), 120, 218)
    _draw_party_block(c, "Buyer (Bill to)", invoice["client"], 218, 316)

    split = 389
    _line(c, split, 44, split, 197)
    right_rows = [44, 69.5, 95, 120.5, 146, 171.5, 197]
    for top in right_rows[1:]:
        _line(c, 274, top, 504, top)
    cells = [
        ("Invoice No.", invoice["invoice_number"], "Dated", _display_date(invoice["invoice_date"])),
        ("Delivery Note", invoice.get("delivery_note"), "Mode/Terms of Payment", invoice.get("payment_terms")),
        (
            "Reference No. & Date.",
            " / ".join(part for part in [invoice.get("reference_number"), _display_date(invoice.get("reference_date"))] if part),
            "Other References",
            invoice.get("other_references"),
        ),
        (
            "Buyer's Order No.",
            invoice.get("buyer_order_number"),
            "Dated",
            _display_date(invoice.get("buyer_order_date")),
        ),
        (
            "Dispatch Doc No.",
            invoice.get("dispatch_document_number"),
            "Delivery Note Date",
            _display_date(invoice.get("delivery_note_date")),
        ),
        (
            "Dispatched through",
            invoice.get("dispatched_through"),
            "Destination",
            invoice.get("destination"),
        ),
    ]
    for index, (left_label, left_value, right_label, right_value) in enumerate(cells):
        top = right_rows[index]
        _draw_text(c, left_label, 277, top + 2, 7.2)
        _draw_wrapped(c, left_value, 277, top + 12, 108, 8.2, "Helvetica-Bold", 9, 1)
        _draw_text(c, right_label, 392, top + 2, 7.2)
        _draw_wrapped(c, right_value, 392, top + 12, 108, 8.2, "Helvetica-Bold", 9, 1)
    _draw_text(c, "Terms of Delivery", 277, 200, 7.5)
    _draw_wrapped(c, invoice.get("terms_of_delivery"), 277, 212, 222, 8.2, "Helvetica", 10, 8)
    if page_count > 1:
        _draw_right(c, f"Page {page_number} of {page_count}", 501, 302, 7.5)


ITEM_COLUMNS = [36, 50.16, 273.36, 320.52, 367.68, 414.84, 435.6, 504]


def _item_height(item: dict) -> float:
    lines = _wrap_text(item.get("description"), ITEM_COLUMNS[2] - ITEM_COLUMNS[1] - 8, 8.5, "Helvetica-Bold")
    return max(22, len(lines) * 10 + 8)


def _paginate_items(items: list[dict]) -> list[list[dict]]:
    if sum(_item_height(item) for item in items) <= 96:
        return [items]
    pages: list[list[dict]] = []
    remaining = list(items)
    while sum(_item_height(item) for item in remaining) > 96:
        page: list[dict] = []
        used = 0.0
        while remaining and used + _item_height(remaining[0]) <= 310:
            item = remaining.pop(0)
            page.append(item)
            used += _item_height(item)
            if sum(_item_height(candidate) for candidate in remaining) <= 96:
                break
        if not page:
            page.append(remaining.pop(0))
        pages.append(page)
    if remaining:
        pages.append(remaining)
    return pages


def _draw_item_table(c, invoice: dict, items: list[dict], final_page: bool) -> None:
    top = 316
    header_bottom = 345
    bottom = 471 if final_page else 668
    _rect(c, 36, top, 468, bottom - top)
    _line(c, 36, header_bottom, 504, header_bottom)
    for x in ITEM_COLUMNS[1:-1]:
        _line(c, x, top, x, bottom)
    headers = [
        ("Sl.\nNo.", 43),
        ("Particulars", (50.16 + 273.36) / 2),
        ("HSN/SAC", (273.36 + 320.52) / 2),
        ("Quantity", (320.52 + 367.68) / 2),
        ("Rate", (367.68 + 414.84) / 2),
        ("per", (414.84 + 435.6) / 2),
        ("Amount", (435.6 + 504) / 2),
    ]
    for text, center in headers:
        for line_index, line_text in enumerate(text.splitlines()):
            _draw_center(c, line_text, center, 319 + line_index * 9, 8)

    cursor = header_bottom + 4
    for item in items:
        height = _item_height(item)
        _draw_text(c, item["line_number"], 39, cursor, 8.5)
        _draw_wrapped(
            c,
            item["description"],
            54,
            cursor,
            215,
            8.5,
            "Helvetica-Bold",
            10,
        )
        _draw_text(c, item.get("hsn_sac"), 277, cursor, 8.2)
        _draw_right(c, f'{item["quantity"]:g}', 364, cursor, 8.2)
        _draw_center(c, item.get("unit") or "", 425, cursor, 8.0)
        _draw_right(c, _format_money(item["taxable_amount"]), 501, cursor, 8.5, "Helvetica-Bold")
        cursor += height
        if cursor < bottom - 2:
            _line(c, 36, cursor - 2, 504, cursor - 2, 0.2)

    if final_page and invoice.get("gst_amount"):
        grouped_taxes: dict[tuple[str, float], Decimal] = {}
        if invoice["gst_treatment"] == "same_state":
            for item in invoice["items"]:
                for tax, rate_field, amount_field in [
                    ("CGST", "cgst_rate", "cgst_amount"),
                    ("SGST", "sgst_rate", "sgst_amount"),
                ]:
                    rate = float(item.get(rate_field) or 0)
                    key = (tax, rate)
                    grouped_taxes[key] = grouped_taxes.get(key, Decimal("0")) + Decimal(
                        str(item.get(amount_field) or 0)
                    )
        elif invoice["gst_treatment"] == "inter_state":
            for item in invoice["items"]:
                rate = float(item.get("igst_rate") or 0)
                key = ("IGST", rate)
                grouped_taxes[key] = grouped_taxes.get(key, Decimal("0")) + Decimal(
                    str(item.get("igst_amount") or 0)
                )
        for (tax, rate), amount in grouped_taxes.items():
            if cursor + 10 >= bottom:
                break
            _draw_right(c, f"Output-{tax}-{rate:g}%", 270, cursor, 8.5, "Helvetica-Bold")
            _draw_right(c, f"{rate:g}", 412, cursor, 8.5, "Helvetica-Bold")
            _draw_center(c, "%", 425, cursor, 8.5, "Helvetica-Bold")
            _draw_right(c, _format_money(amount), 501, cursor, 8.5, "Helvetica-Bold")
            cursor += 10


def _draw_final_summary(c, invoice: dict) -> None:
    _rect(c, 36, 471, 468, 14.3)
    _draw_right(c, "Total", 270, 473, 8.5)
    _draw_right(c, f'INR {_format_money(invoice["grand_total_amount"])}', 501, 472, 10, "Helvetica-Bold")

    _rect(c, 36, 485.3, 468, 27.7)
    _draw_text(c, "Amount Chargeable (in words)", 39, 487, 7.5)
    _draw_right(c, "E. & O.E", 501, 487, 8, "Helvetica-Oblique")
    _draw_wrapped(c, invoice["amount_words"], 39, 498, 455, 8.8, "Helvetica-Bold", 10, 2)

    summary_top = 513
    summary_bottom = 555.3
    _rect(c, 36, summary_top, 468, summary_bottom - summary_top)
    hsn_values = sorted({_clean(item.get("hsn_sac")) for item in invoice["items"] if _clean(item.get("hsn_sac"))})
    hsn_label = ", ".join(hsn_values) or "-"
    if invoice["gst_treatment"] == "same_state":
        columns = [36, 231.24, 283.68, 315.24, 367.56, 399, 451.44, 504]
        for x in columns[1:-1]:
            _line(c, x, summary_top, x, summary_bottom)
        _line(c, 283.68, 523.4, 367.56, 523.4)
        _line(c, 367.56, 523.4, 451.44, 523.4)
        _draw_center(c, "HSN/SAC", 133.5, 515, 8)
        _draw_center(c, "Taxable", 257.5, 515, 7.5)
        _draw_center(c, "CGST", 325.5, 515, 8)
        _draw_center(c, "SGST/UTGST", 409.5, 515, 8)
        _draw_center(c, "Total Tax", 477.5, 515, 7.5)
        for label, center in [("Rate", 299.5), ("Amount", 341.5), ("Rate", 383.3), ("Amount", 425.2)]:
            _draw_center(c, label, center, 525, 7.2)
        rate = max((float(item.get("cgst_rate") or 0) for item in invoice["items"]), default=0)
        values = [
            (hsn_label, 39),
            (_format_money(invoice["subtotal_amount"]), 280),
            (f"{rate:g}%", 312),
            (_format_money(invoice["cgst_amount"]), 365),
            (f"{rate:g}%", 396),
            (_format_money(invoice["sgst_amount"]), 449),
            (_format_money(invoice["gst_amount"]), 501),
        ]
        _draw_text(c, values[0][0], values[0][1], 537, 7.8)
        for value, right in values[1:]:
            _draw_right(c, value, right, 537, 7.8, "Helvetica-Bold" if right in {280, 365, 449, 501} else "Helvetica")
    elif invoice["gst_treatment"] == "inter_state":
        columns = [36, 231.24, 315.24, 399, 504]
        for x in columns[1:-1]:
            _line(c, x, summary_top, x, summary_bottom)
        _draw_center(c, "HSN/SAC", 133.5, 515, 8)
        _draw_center(c, "Taxable Value", 273, 515, 8)
        _draw_center(c, "IGST Rate", 357, 515, 8)
        _draw_center(c, "IGST Amount", 451.5, 515, 8)
        rate = max((float(item.get("igst_rate") or 0) for item in invoice["items"]), default=0)
        _draw_text(c, hsn_label, 39, 537, 8)
        _draw_right(c, _format_money(invoice["subtotal_amount"]), 312, 537, 8, "Helvetica-Bold")
        _draw_right(c, f"{rate:g}%", 396, 537, 8)
        _draw_right(c, _format_money(invoice["igst_amount"]), 501, 537, 8, "Helvetica-Bold")
    else:
        _line(c, 300, summary_top, 300, summary_bottom)
        _draw_center(c, "HSN/SAC", 168, 515, 8)
        _draw_center(c, "Taxable Value (No GST)", 402, 515, 8)
        _draw_text(c, hsn_label, 39, 537, 8)
        _draw_right(c, _format_money(invoice["subtotal_amount"]), 501, 537, 8, "Helvetica-Bold")

    _rect(c, 36, 555.3, 468, 17.6)
    _draw_text(c, "Tax Amount (in words):", 39, 558, 7.5)
    _draw_wrapped(c, amount_in_words(invoice["gst_amount"]), 130, 558, 370, 8.2, "Helvetica-Bold", 9, 1)

    _rect(c, 36, 572.9, 468, 113)
    _line(c, 270, 643.4, 504, 643.4)
    _line(c, 270, 643.4, 270, 685.9)
    seller_name = _clean(invoice["seller"].get("legal_name") or invoice["seller"].get("display_name"))
    _draw_right(c, f"for {seller_name}", 501, 646, 8.2, "Helvetica-Bold")
    _draw_right(
        c,
        invoice["seller"].get("signature_label") or "Authorised Signatory",
        501,
        674,
        8,
    )
    notes = _clean(invoice.get("notes"))
    if notes:
        _draw_text(c, "Notes:", 39, 578, 7.5, "Helvetica-Bold")
        _draw_wrapped(c, notes, 39, 589, 225, 7.5, "Helvetica", 9, 5)
    bank = invoice["seller"]
    bank_lines = [
        _clean(bank.get("bank_name")),
        _clean(bank.get("bank_account_name")),
        _clean(bank.get("bank_account_number")),
        _clean(bank.get("bank_ifsc")),
    ]
    bank_lines = [line for line in bank_lines if line]
    if bank_lines:
        _draw_text(c, "Bank details:", 39, 626, 7.3, "Helvetica-Bold")
        _draw_wrapped(c, " | ".join(bank_lines), 39, 637, 225, 7.2, "Helvetica", 8.5, 4)
    _draw_center(c, "This is a Computer Generated Invoice", 270, 691.5, 8.5)


def render_invoice_pdf(invoice: dict, target_path: Path, *, draft: bool) -> Path:
    letter, _string_width, canvas_module = _reportlab()
    ensure_data_dirs()
    target_path = _safe_generated_path(target_path.name)
    pages = _paginate_items(invoice["items"])
    temp_handle = tempfile.NamedTemporaryFile(
        prefix="invoice-", suffix=".pdf", dir=GENERATED_INVOICE_DIR, delete=False
    )
    temp_path = Path(temp_handle.name)
    temp_handle.close()
    try:
        c = canvas_module.Canvas(str(temp_path), pagesize=letter, pageCompression=1)
        c.setTitle(f"Invoice {invoice['invoice_number']}")
        c.setAuthor(_clean(invoice["seller"].get("display_name")))
        for page_index, page_items in enumerate(pages, start=1):
            final_page = page_index == len(pages)
            _draw_header(c, invoice, page_index, len(pages))
            _draw_item_table(c, invoice, page_items, final_page)
            if final_page:
                _draw_final_summary(c, invoice)
            else:
                _draw_center(c, "Continued on next page", 270, 678, 8, "Helvetica-Oblique")
            if draft:
                c.saveState()
                c.setFillColorRGB(0.45, 0.45, 0.45)
                if hasattr(c, "setFillAlpha"):
                    c.setFillAlpha(0.16)
                c.setFont("Helvetica-Bold", 54)
                c.translate(306, 396)
                c.rotate(35)
                c.drawCentredString(0, 0, "DRAFT")
                c.restoreState()
            c.showPage()
        c.save()
        os.replace(temp_path, target_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
    return target_path


def preview_invoice(invoice_id: int) -> Path:
    invoice = get_invoice(invoice_id)
    if invoice["status"] != "draft":
        raise InvoiceConflictError("Only draft invoices use the draft preview endpoint.")
    path = _draft_pdf_path(invoice_id, invoice["invoice_number"])
    return render_invoice_pdf(invoice, path, draft=True)


def invoice_pdf_file(invoice_id: int) -> Path:
    invoice = get_invoice(invoice_id)
    if invoice["status"] == "draft":
        path = _draft_pdf_path(invoice_id, invoice["invoice_number"])
        if not path.exists():
            raise InvoiceConflictError("Preview the draft before downloading it.")
        return path
    filename = invoice.get("pdf_filename")
    if not filename:
        raise FileNotFoundError("Invoice PDF has not been generated.")
    path = _safe_generated_path(filename)
    if not path.exists():
        raise FileNotFoundError("Generated invoice PDF was not found.")
    return path


def _issue_snapshot(invoice: dict, pdf_filename: str) -> dict:
    return {
        "generated_invoice_id": invoice["id"],
        "invoice_number": invoice["invoice_number"],
        "invoice_date": invoice["invoice_date"],
        "financial_year": invoice["financial_year"],
        "billable_period": invoice["billable_period"],
        "seller": invoice["seller"],
        "client": invoice["client"],
        "ship_to": _ship_to_party(invoice),
        "items": invoice["items"],
        "gst_treatment": invoice["gst_treatment"],
        "subtotal_amount": invoice["subtotal_amount"],
        "cgst_amount": invoice["cgst_amount"],
        "sgst_amount": invoice["sgst_amount"],
        "igst_amount": invoice["igst_amount"],
        "gst_amount": invoice["gst_amount"],
        "grand_total_amount": invoice["grand_total_amount"],
        "tds_rate": invoice["tds_rate"],
        "tds_amount": invoice["tds_amount"],
        "net_receivable_amount": invoice["net_receivable_amount"],
        "amount_words": invoice["amount_words"],
        "pdf_path": pdf_filename,
    }


def issue_invoice(
    invoice_id: int,
    *,
    create_income_record: bool = False,
    ledger_user_id: int | None = None,
) -> dict:
    invoice = get_invoice(invoice_id)
    if invoice["status"] != "draft":
        raise InvoiceConflictError("Only draft invoices can be issued.")
    if create_income_record and not ledger_user_id:
        raise ValueError("Select a ledger user before creating the linked income record.")
    final_path = _issued_pdf_path(invoice_id, invoice["invoice_number"])
    render_invoice_pdf(invoice, final_path, draft=False)
    try:
        with get_connection() as conn:
            current = conn.execute(
                "SELECT * FROM generated_invoices WHERE id = ?", (invoice_id,)
            ).fetchone()
            if not current:
                raise KeyError("Invoice not found")
            current_dict = row_to_dict(current)
            if current_dict["status"] != "draft":
                raise InvoiceConflictError("Invoice was already issued or cancelled.")
            linked_income_id = None
            selected_user_id = int(ledger_user_id) if create_income_record else current_dict.get("ledger_user_id")
            if create_income_record:
                user = conn.execute("SELECT id FROM users WHERE id = ?", (selected_user_id,)).fetchone()
                if not user:
                    raise ValueError("Selected ledger user does not exist.")
                metadata = {
                    "generated_invoice_id": invoice_id,
                    "invoice_number": invoice["invoice_number"],
                    "billable_period": invoice["billable_period"],
                    "client_gstin": invoice["client"].get("gstin") or "",
                    "seller_gstin": invoice["seller"].get("gstin") or "",
                    "gst_treatment": invoice["gst_treatment"],
                    "gst_amount": invoice["gst_amount"],
                    "tds_rate": invoice["tds_rate"],
                    "pdf_path": final_path.name,
                }
                record_date = parse_date_strict(invoice["invoice_date"])
                cursor = conn.execute(
                    """
                    INSERT INTO income_records (
                        user_id, document_id, financial_year, record_date, period_label,
                        income_type, payer, gross_amount, net_amount, tds_amount,
                        deductions_amount, metadata_json
                    ) VALUES (?, NULL, ?, ?, ?, 'freelance_invoice', ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        selected_user_id,
                        invoice["financial_year"],
                        record_date.isoformat(),
                        month_label(record_date),
                        invoice["client"].get("legal_name") or invoice["client"].get("client_name"),
                        invoice["subtotal_amount"],
                        round(invoice["subtotal_amount"] - invoice["tds_amount"], 2),
                        invoice["tds_amount"],
                        json.dumps(metadata),
                    ),
                )
                linked_income_id = int(cursor.lastrowid)
                conn.execute(
                    """
                    INSERT INTO audit_events (document_id, user_id, event_type, before_json, after_json)
                    VALUES (NULL, ?, 'create_invoice_income_record', '{}', ?)
                    """,
                    (
                        selected_user_id,
                        json.dumps(
                            {
                                "generated_invoice_id": invoice_id,
                                "income_record_id": linked_income_id,
                                **metadata,
                            }
                        ),
                    ),
                )
            snapshot = _issue_snapshot(invoice, final_path.name)
            metadata = dict(invoice.get("metadata") or {})
            metadata["issue_snapshot"] = snapshot
            issued_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                UPDATE generated_invoices
                SET status = 'issued', ledger_user_id = ?, pdf_path = ?,
                    income_record_id = ?, metadata_json = ?, issued_at = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    selected_user_id,
                    final_path.name,
                    linked_income_id,
                    json.dumps(metadata),
                    issued_at,
                    invoice_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO audit_events (document_id, user_id, event_type, before_json, after_json)
                VALUES (NULL, ?, 'issue_invoice', ?, ?)
                """,
                (
                    selected_user_id,
                    json.dumps(
                        {
                            "generated_invoice_id": invoice_id,
                            "status": "draft",
                            "invoice_number": invoice["invoice_number"],
                        }
                    ),
                    json.dumps(
                        {
                            "generated_invoice_id": invoice_id,
                            "status": "issued",
                            "invoice_number": invoice["invoice_number"],
                            "pdf_path": final_path.name,
                            "income_record_id": linked_income_id,
                            "issued_at": issued_at,
                        }
                    ),
                ),
            )
    except Exception:
        if final_path.exists():
            final_path.unlink()
        raise
    _remove_draft_preview(invoice_id, invoice["invoice_number"])
    return get_invoice(invoice_id)


def cancel_invoice(invoice_id: int, reason: str) -> dict:
    reason = _clean(reason)
    if not reason:
        raise ValueError("Cancellation reason is required.")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM generated_invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        if not row:
            raise KeyError("Invoice not found")
        invoice = row_to_dict(row)
        if invoice["status"] != "issued":
            raise InvoiceConflictError("Only issued invoices can be cancelled.")
        try:
            metadata = json.loads(invoice.get("metadata_json") or "{}")
        except json.JSONDecodeError:
            metadata = {}
        cancelled_at = datetime.now(timezone.utc).isoformat()
        metadata["cancellation"] = {"reason": reason, "cancelled_at": cancelled_at}
        conn.execute(
            """
            UPDATE generated_invoices
            SET status = 'cancelled', metadata_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (json.dumps(metadata), invoice_id),
        )
        conn.execute(
            """
            INSERT INTO audit_events (document_id, user_id, event_type, before_json, after_json)
            VALUES (NULL, ?, 'cancel_invoice', ?, ?)
            """,
            (
                invoice.get("ledger_user_id"),
                json.dumps(
                    {
                        "generated_invoice_id": invoice_id,
                        "status": "issued",
                        "income_record_id": invoice.get("income_record_id"),
                    }
                ),
                json.dumps(
                    {
                        "generated_invoice_id": invoice_id,
                        "status": "cancelled",
                        "reason": reason,
                        "cancelled_at": cancelled_at,
                        "income_record_id": invoice.get("income_record_id"),
                    }
                ),
            ),
        )
    return get_invoice(invoice_id)
