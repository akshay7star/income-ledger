from __future__ import annotations

import json
from difflib import SequenceMatcher
import sqlite3
from pathlib import Path

from .database import get_connection, row_to_dict
from .financial_year import financial_year_for, month_label, parse_date, parse_date_strict
from .tax import standard_deduction_for


TAX_DOCUMENT_TYPES = {"form16_part_a", "form16_part_b", "form26as", "tax_statement_unknown"}


def list_users() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
    return [row_to_dict(row) for row in rows]


def get_user(user_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    return row_to_dict(row)


def create_user(payload: dict) -> dict:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (name, pan, aliases, profile_hints) VALUES (?, ?, ?, ?)",
            (
                payload["name"].strip(),
                (payload.get("pan") or "").upper().strip() or None,
                payload.get("aliases", "").strip(),
                payload.get("profile_hints", "").strip(),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row)


def update_user(user_id: int, payload: dict) -> dict:
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
        if not existing:
            raise KeyError("User not found")
        
        conn.execute(
            """
            UPDATE users
            SET name = ?, pan = ?, aliases = ?, profile_hints = ?
            WHERE id = ?
            """,
            (
                payload["name"].strip(),
                (payload.get("pan") or "").upper().strip() or None,
                payload.get("aliases", "").strip(),
                payload.get("profile_hints", "").strip(),
                int(user_id),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    return row_to_dict(row)


def delete_user(user_id: int) -> dict:
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
        if not existing:
            raise KeyError("User not found")
        
        # 1. Update audit_events to disassociate user_id
        conn.execute("UPDATE audit_events SET user_id = NULL WHERE user_id = ?", (int(user_id),))
        
        # 2. Find all documents associated with this user
        docs = conn.execute("SELECT id FROM documents WHERE detected_user_id = ?", (int(user_id),)).fetchall()
        doc_ids = [row["id"] for row in docs]
        
    # 3. Delete each document (unlinks file and cleans database records)
    for doc_id in doc_ids:
        try:
            delete_document(doc_id)
        except Exception:
            pass
            
    # 4. Delete the user (income_records and freelance_expenses cascade delete)
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (int(user_id),))
        conn.commit()
        
    return {"deleted": True, "id": int(user_id)}



def get_or_create_user_for_extraction(extraction: dict) -> tuple[int | None, float]:
    if extraction.get("document_type") == "purchase_expense":
        return None, 0.0

    matched_user_id, confidence = find_user_match(extraction)
    if matched_user_id:
        return matched_user_id, confidence

    name = (extraction.get("name") or "").strip()
    pan = (extraction.get("pan") or "").upper().strip()
    if not name and not pan:
        return None, 0.0

    if not name:
        name = pan

    with get_connection() as conn:
        existing = None
        if pan:
            existing = conn.execute("SELECT * FROM users WHERE UPPER(pan) = ?", (pan,)).fetchone()
        if existing:
            return existing["id"], 0.95
        cursor = conn.execute(
            "INSERT INTO users (name, pan, aliases, profile_hints) VALUES (?, ?, '', ?)",
            (name[:120], pan or None, (extraction.get("payer") or "")[:240]),
        )
        conn.commit()
    return int(cursor.lastrowid), 0.75


def normalize_person_name(value: str | None) -> str:
    text = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in str(value or ""))
    return " ".join(text.split())


def name_tokens(value: str | None) -> list[str]:
    return [token for token in normalize_person_name(value).split() if len(token) > 1]


def name_similarity(left: str | None, right: str | None) -> float:
    left_norm = normalize_person_name(left)
    right_norm = normalize_person_name(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0

    left_tokens = name_tokens(left_norm)
    right_tokens = name_tokens(right_norm)
    if not left_tokens or not right_tokens:
        return SequenceMatcher(None, left_norm, right_norm).ratio()

    left_sorted = " ".join(sorted(left_tokens))
    right_sorted = " ".join(sorted(right_tokens))
    sorted_ratio = SequenceMatcher(None, left_sorted, right_sorted).ratio()

    matched = 0
    for left_token in left_tokens:
        if any(SequenceMatcher(None, left_token, right_token).ratio() >= 0.84 for right_token in right_tokens):
            matched += 1
    token_ratio = matched / max(len(left_tokens), len(right_tokens))
    direct_ratio = SequenceMatcher(None, left_norm, right_norm).ratio()
    return max(direct_ratio, sorted_ratio, token_ratio)


def candidate_names(user: dict) -> list[str]:
    return [
        user["name"],
        *[item.strip() for item in (user.get("aliases") or "").split(",") if item.strip()],
    ]


def find_user_match(extraction: dict) -> tuple[int | None, float]:
    users = list_users()
    if not users:
        return None, 0.0
    best_id: int | None = None
    best_score = 0.0
    text = " ".join(str(extraction.get(key) or "") for key in ["name", "pan", "payer", "extracted_text"])
    normalized_text = normalize_person_name(text)
    pan = (extraction.get("pan") or "").upper().strip()
    extracted_name = extraction.get("name") or ""
    for user in users:
        score = 0.0
        user_pan = (user.get("pan") or "").upper().strip()
        if user_pan and pan and user_pan == pan:
            return user["id"], 0.98

        best_name_score = 0.0
        for name in candidate_names(user):
            normalized_name = normalize_person_name(name)
            if normalized_name and normalized_name in normalized_text:
                best_name_score = max(best_name_score, 1.0)
            best_name_score = max(best_name_score, name_similarity(extracted_name, name))
        if best_name_score >= 0.92:
            score += 0.55
        elif best_name_score >= 0.84:
            score += 0.42
        elif best_name_score >= 0.74:
            score += 0.28

        hints = [item.strip() for item in (user.get("profile_hints") or "").split(",") if item.strip()]
        if any(normalize_person_name(hint) in normalized_text for hint in hints if normalize_person_name(hint)):
            score += 0.1
        if score > best_score:
            best_id = user["id"]
            best_score = score
    if best_score < 0.42:
        return None, 0.0
    return best_id, round(min(best_score, 0.95), 2)


def create_document(
    original_name: str,
    stored_path: Path,
    file_hash: str,
    extraction: dict,
    detected_user_id: int | None,
    confidence: float,
) -> dict:
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM documents WHERE file_hash = ?", (file_hash,)).fetchone()
        if existing:
            if existing["status"] == "confirmed":
                existing_dict = row_to_dict(existing)
                existing_dict["duplicate"] = True
                return existing_dict
            conn.execute(
                """
                UPDATE documents
                SET document_type = ?, status = 'needs_review', extracted_text = ?, extracted_json = ?,
                    detected_user_id = ?, confidence = ?, warnings = ?
                WHERE id = ?
                """,
                (
                    extraction["document_type"],
                    extraction.get("extracted_text", ""),
                    json.dumps(extraction),
                    detected_user_id,
                    confidence,
                    json.dumps(extraction.get("warnings", [])),
                    existing["id"],
                ),
            )
            conn.commit()
            refreshed = conn.execute("SELECT * FROM documents WHERE id = ?", (existing["id"],)).fetchone()
            existing_dict = row_to_dict(refreshed)
            existing_dict["duplicate"] = True
            return existing_dict
        cursor = conn.execute(
            """
            INSERT INTO documents
                (original_name, stored_path, file_hash, document_type, status, extracted_text,
                 extracted_json, detected_user_id, confidence, warnings)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                original_name,
                str(stored_path),
                file_hash,
                extraction["document_type"],
                "needs_review",
                extraction.get("extracted_text", ""),
                json.dumps(extraction),
                detected_user_id,
                confidence,
                json.dumps(extraction.get("warnings", [])),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row)


def list_documents() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT d.*, u.name AS detected_user_name
            FROM documents d
            LEFT JOIN users u ON u.id = d.detected_user_id
            ORDER BY d.uploaded_at DESC
            """
        ).fetchall()
    items = []
    for row in rows:
        item = row_to_dict(row)
        extracted = json.loads(item.pop("extracted_json") or "{}")
        item["extracted"] = extracted
        warnings = json.loads(item.get("warnings") or "[]")
        validation_warns = extracted.get("validation_warnings", [])
        item["warnings"] = list(set(warnings + validation_warns))
        items.append(item)
    return items


def get_document(document_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT d.*, u.name AS detected_user_name
            FROM documents d
            LEFT JOIN users u ON u.id = d.detected_user_id
            WHERE d.id = ?
            """,
            (int(document_id),),
        ).fetchone()
    if not row:
        return None
    item = row_to_dict(row)
    extracted = json.loads(item.pop("extracted_json") or "{}")
    item["extracted"] = extracted
    warnings = json.loads(item.get("warnings") or "[]")
    validation_warns = extracted.get("validation_warnings", [])
    item["warnings"] = list(set(warnings + validation_warns))
    return item


def delete_income_record(record_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM income_records WHERE id = ?", (record_id,)).fetchone()
        if not row:
            raise KeyError("Income record not found")
        document_id = row["document_id"]
        conn.execute("DELETE FROM income_records WHERE id = ?", (record_id,))
        if document_id:
            conn.execute("UPDATE documents SET status = 'needs_review' WHERE id = ?", (document_id,))
        conn.execute(
            """
            INSERT INTO audit_events (document_id, user_id, event_type, before_json, after_json)
            VALUES (?, ?, 'delete_income_record', ?, '{}')
            """,
            (document_id, row["user_id"], json.dumps(row_to_dict(row))),
        )
        conn.commit()
    return {"deleted": True, "id": record_id}


def delete_document(document_id: int) -> dict:
    with get_connection() as conn:
        document = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not document:
            raise KeyError("Document not found")
        is_tax_document = (document["document_type"] or "") in TAX_DOCUMENT_TYPES
        
        if not is_tax_document:
            # Delete any linked freelance expenses if this document was a purchase expense
            try:
                extracted = json.loads(document["extracted_json"] or "{}")
                expense_id = extracted.get("expense_id")
                if expense_id:
                    conn.execute("DELETE FROM freelance_expenses WHERE id = ?", (int(expense_id),))
            except Exception:
                pass

        conn.execute("UPDATE audit_events SET document_id = NULL WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM tax_documents WHERE document_id = ?", (document_id,))
        if not is_tax_document:
            conn.execute("DELETE FROM income_records WHERE document_id = ?", (document_id,))
        conn.execute(
            """
            INSERT INTO audit_events (event_type, before_json, after_json)
            VALUES ('delete_document', ?, '{}')
            """,
            (json.dumps(row_to_dict(document)),),
        )
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        conn.commit()
    path = Path(document["stored_path"])
    path.unlink(missing_ok=True)
    return {"deleted": True, "id": document_id}


def validation_warnings(conn: sqlite3.Connection, user_id: int, payload: dict, financial_year: str, period: str, exclude_record_id: int | None = None) -> list[str]:
    warnings: list[str] = []
    
    # Check duplicate only if it is salary or freelance_invoice (income records)
    if payload.get("income_type") in ("salary", "freelance_invoice"):
        existing = conn.execute(
            """
            SELECT id FROM income_records
            WHERE user_id = ? AND financial_year = ? AND period_label = ? AND income_type = ?
              AND (? IS NULL OR document_id IS NULL OR document_id != ?)
              AND (? IS NULL OR id != ?)
            """,
            (
                user_id,
                financial_year,
                period,
                payload["income_type"],
                payload.get("document_id"),
                payload.get("document_id"),
                exclude_record_id,
                exclude_record_id,
            ),
        ).fetchone()
        if existing:
            warnings.append(f"Another {payload['income_type']} record already exists for {period}.")

    gross = float(payload.get("gross_amount") or 0)
    net = float(payload.get("net_amount") or 0)
    other_deductions = float(payload.get("deductions_amount") or 0)
    tds = float(payload.get("tds_amount") or 0)
    pf = float(payload.get("pf_amount") or 0)
    vpf = float(payload.get("vpf_amount") or 0)
    gst = float(payload.get("gst_amount") or 0)

    if payload["income_type"] == "salary" and gross > 0:
        expected_net = gross - (pf + vpf + tds + other_deductions)
        if abs(expected_net - net) > 10.0:
            warnings.append("Gross salary minus deductions and taxes does not closely match net amount.")

    if payload["income_type"] == "freelance_invoice" and gross > 0:
        expected_net = gross - tds
        if abs(expected_net - net) > 10.0:
            warnings.append("Gross freelance income minus TDS does not closely match net amount.")
        if tds == 0:
            warnings.append("No TDS was recorded for this freelance invoice.")

    if payload["income_type"] == "purchase_expense" and gross > 0:
        expected_net = gross + gst
        if abs(expected_net - net) > 10.0:
            warnings.append("Gross amount plus GST does not closely match net amount.")

    return warnings


def confirm_extraction(document_id: int, payload: dict) -> dict:
    record_date = parse_date_strict(payload.get("record_date"))
    financial_year = financial_year_for(record_date)
    period = month_label(record_date)
    user_id = int(payload["user_id"])
    income_type = payload["income_type"]

    if income_type == "purchase_expense":
        with get_connection() as conn:
            warnings = validation_warnings(conn, user_id, payload, financial_year, period)
        expense_payload = {
            "user_id": user_id,
            "expense_date": record_date.isoformat(),
            "category": payload.get("category") or "Others",
            "amount": float(payload.get("net_amount") or payload.get("gross_amount") or 0),
            "gst_amount": float(payload.get("gst_amount") or 0),
            "notes": payload.get("notes") or f"{payload.get('payer') or 'Vendor invoice'}",
            "validation_warnings": warnings
        }
        row = add_document_expense(document_id, expense_payload)
        return row

    if income_type == "freelance_invoice":
        gross = float(payload.get("gross_amount") or 0)
        tds = float(payload.get("tds_amount") or 0)
        gst = float(payload.get("gst_amount") or 0)
        payload["net_amount"] = round(gross - tds, 2)
        payload["gst_amount"] = gst

    with get_connection() as conn:
        document = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not document:
            raise KeyError("Document not found")
        before_json = document["extracted_json"]
        payload["document_id"] = document_id
        conn.execute("DELETE FROM income_records WHERE document_id = ?", (document_id,))
        warnings = validation_warnings(conn, user_id, payload, financial_year, period)
        payload_with_warnings = {**payload, "validation_warnings": warnings}
        after_json = json.dumps(payload_with_warnings)
        cursor = conn.execute(
            """
            INSERT INTO income_records
                (user_id, document_id, financial_year, record_date, period_label, income_type,
                 payer, gross_amount, net_amount, tds_amount, deductions_amount, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                document_id,
                financial_year,
                record_date.isoformat(),
                period,
                income_type,
                payload.get("payer"),
                float(payload.get("gross_amount") or 0),
                float(payload.get("net_amount") or 0),
                float(payload.get("tds_amount") or 0),
                float(payload.get("deductions_amount") or 0),
                after_json,
            ),
        )
        conn.execute(
            "UPDATE documents SET status = 'confirmed', detected_user_id = ?, extracted_json = ? WHERE id = ?",
            (user_id, after_json, document_id),
        )
        conn.execute(
            """
            INSERT INTO audit_events (document_id, user_id, event_type, before_json, after_json)
            VALUES (?, ?, 'confirm_extraction', ?, ?)
            """,
            (document_id, user_id, before_json, after_json),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM income_records WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row)


def add_income_record(payload: dict) -> dict:
    record_date = parse_date_strict(payload.get("record_date"))
    financial_year = financial_year_for(record_date)
    period = month_label(record_date)
    user_id = int(payload["user_id"])
    income_type = payload["income_type"]

    gross = float(payload.get("gross_amount") or 0)
    tds = float(payload.get("tds_amount") or 0)
    gst = float(payload.get("gst_amount") or 0)

    if income_type == "freelance_invoice":
        payload["net_amount"] = round(gross - tds, 2)
        payload["gst_amount"] = gst

    with get_connection() as conn:
        warnings = validation_warnings(conn, user_id, payload, financial_year, period)
        payload_with_warnings = {**payload, "validation_warnings": warnings}
        after_json = json.dumps(payload_with_warnings)

        cursor = conn.execute(
            """
            INSERT INTO income_records
                (user_id, document_id, financial_year, record_date, period_label, income_type,
                 payer, gross_amount, net_amount, tds_amount, deductions_amount, metadata_json)
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                financial_year,
                record_date.isoformat(),
                period,
                income_type,
                payload.get("payer"),
                float(payload.get("gross_amount") or 0),
                float(payload.get("net_amount") or 0),
                float(payload.get("tds_amount") or 0),
                float(payload.get("deductions_amount") or 0),
                after_json,
            ),
        )

        # Insert audit event
        conn.execute(
            """
            INSERT INTO audit_events (document_id, user_id, event_type, before_json, after_json)
            VALUES (NULL, ?, 'add_income_record_manual', '{}', ?)
            """,
            (user_id, after_json),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM income_records WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row)


def add_expense(payload: dict) -> dict:
    expense_date = parse_date_strict(payload.get("expense_date"))
    financial_year = financial_year_for(expense_date)
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO freelance_expenses (user_id, financial_year, expense_date, category, amount, gst_amount, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(payload["user_id"]),
                financial_year,
                expense_date.isoformat(),
                payload["category"].strip(),
                float(payload["amount"]),
                float(payload.get("gst_amount") or 0),
                payload.get("notes", ""),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM freelance_expenses WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row)


def add_document_expense(document_id: int, payload: dict) -> dict:
    with get_connection() as conn:
        document = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not document:
            raise KeyError("Document not found")
        expense_date = parse_date_strict(payload.get("expense_date"))
        financial_year = financial_year_for(expense_date)
        cursor = conn.execute(
            """
            INSERT INTO freelance_expenses (user_id, financial_year, expense_date, category, amount, gst_amount, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(payload["user_id"]),
                financial_year,
                expense_date.isoformat(),
                payload["category"].strip(),
                float(payload["amount"]),
                float(payload.get("gst_amount") or 0),
                payload.get("notes", ""),
            ),
        )
        row = conn.execute("SELECT * FROM freelance_expenses WHERE id = ?", (cursor.lastrowid,)).fetchone()
        row_dict = row_to_dict(row)
        after_json = {
            **payload,
            "expense_id": row_dict["id"],
            "document_id": document_id,
            "document_flow": "purchase_expense",
        }
        conn.execute("DELETE FROM income_records WHERE document_id = ?", (document_id,))
        conn.execute(
            "UPDATE documents SET status = 'confirmed', document_type = 'purchase_expense', detected_user_id = ?, extracted_json = ? WHERE id = ?",
            (int(payload["user_id"]), json.dumps(after_json), document_id),
        )
        conn.execute(
            """
            INSERT INTO audit_events (document_id, user_id, event_type, before_json, after_json)
            VALUES (?, ?, 'confirm_purchase_expense', ?, ?)
            """,
            (document_id, int(payload["user_id"]), document["extracted_json"], json.dumps(after_json)),
        )
        conn.commit()
    return row_dict


def delete_expense(expense_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM freelance_expenses WHERE id = ?", (expense_id,)).fetchone()
        if not row:
            raise KeyError("Expense not found")
        conn.execute("DELETE FROM freelance_expenses WHERE id = ?", (expense_id,))
        conn.execute(
            """
            INSERT INTO audit_events (user_id, event_type, before_json, after_json)
            VALUES (?, 'delete_expense', ?, '{}')
            """,
            (row["user_id"], json.dumps(row_to_dict(row))),
        )
        # Cascade expense deletion to documents
        docs = conn.execute("SELECT id, extracted_json FROM documents WHERE document_type = 'purchase_expense'").fetchall()
        for doc in docs:
            try:
                ext = json.loads(doc["extracted_json"] or "{}")
                if ext.get("expense_id") == expense_id:
                    ext.pop("expense_id", None)
                    conn.execute(
                        "UPDATE documents SET status = 'needs_review', extracted_json = ? WHERE id = ?",
                        (json.dumps(ext), doc["id"])
                    )
            except Exception:
                pass
        conn.commit()
    return {"deleted": True, "id": expense_id}


def list_financial_years(user_id: str | None = None) -> list[str]:
    query = """
        SELECT financial_year FROM income_records
        UNION
        SELECT financial_year FROM freelance_expenses
        UNION
        SELECT financial_year FROM tax_documents
        ORDER BY financial_year DESC
    """
    params = []
    if user_id and user_id != "all":
        query = """
            SELECT financial_year FROM income_records WHERE user_id = ?
            UNION
            SELECT financial_year FROM freelance_expenses WHERE user_id = ?
            UNION
            SELECT financial_year FROM tax_documents WHERE user_id = ?
            ORDER BY financial_year DESC
        """
        params = [int(user_id), int(user_id), int(user_id)]

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [row["financial_year"] for row in rows] or [financial_year_for(None)]


def dashboard_data(user_id: str, financial_year: str) -> dict:
    params: list[object] = [financial_year]
    user_clause = ""
    if user_id != "all":
        user_clause = "AND user_id = ?"
        params.append(int(user_id))

    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM income_records WHERE financial_year = ? {user_clause} ORDER BY record_date",
            params,
        ).fetchall()
        expenses = conn.execute(
            f"SELECT * FROM freelance_expenses WHERE financial_year = ? {user_clause}",
            params,
        ).fetchall()

    records = []
    for row in rows:
        item = row_to_dict(row)
        metadata = json.loads(item.get("metadata_json") or "{}")
        item["metadata"] = metadata
        item["validation_warnings"] = metadata.get("validation_warnings", [])
        item["pf_amount"] = float(metadata.get("pf_amount") or 0)
        item["vpf_amount"] = float(metadata.get("vpf_amount") or 0)
        item["gst_amount"] = float(metadata.get("gst_amount") or 0)
        records.append(item)
    expense_items = [row_to_dict(row) for row in expenses]
    salary_income = sum(row["gross_amount"] for row in records if row["income_type"] == "salary")
    freelance_income = sum(row["gross_amount"] for row in records if row["income_type"] == "freelance_invoice")
    freelance_expenses = sum(row["amount"] for row in expense_items)
    expense_gst_claims = sum(row.get("gst_amount") or 0 for row in expense_items)
    freelance_gst_collected = sum(row["gst_amount"] for row in records if row["income_type"] == "freelance_invoice")
    tds_paid = sum(row["tds_amount"] for row in records)
    deductions = sum(row["deductions_amount"] for row in records)
    pf_total = sum(row["pf_amount"] for row in records if row["income_type"] == "salary")
    vpf_total = sum(row["vpf_amount"] for row in records if row["income_type"] == "salary")
    net_income = sum(row["net_amount"] for row in records)
    from datetime import datetime
    ym_set = set()
    for row in records:
        try:
            ym_set.add(parse_date(row["record_date"]).strftime("%Y-%m"))
        except Exception:
            pass
    for row in expense_items:
        try:
            ym_set.add(parse_date(row["expense_date"]).strftime("%Y-%m"))
        except Exception:
            pass

    sorted_yms = sorted(ym_set)
    monthly = []
    for ym in sorted_yms:
        try:
            dt = datetime.strptime(ym, "%Y-%m").date()
            label = month_label(dt)
        except Exception:
            continue
        label_records = [
            row for row in records
            if parse_date(row["record_date"]).strftime("%Y-%m") == ym
        ]
        label_expenses = [
            row for row in expense_items
            if parse_date(row["expense_date"]).strftime("%Y-%m") == ym
        ]
        monthly.append(
            {
                "month": label,
                "salary": sum(row["gross_amount"] for row in label_records if row["income_type"] == "salary"),
                "freelance": sum(row["gross_amount"] for row in label_records if row["income_type"] == "freelance_invoice"),
                "expenses": sum(row["amount"] for row in label_expenses),
                "expense_gst": sum(row.get("gst_amount") or 0 for row in label_expenses),
                "tds": sum(row["tds_amount"] for row in label_records),
                "net": sum(row["net_amount"] for row in label_records),
                "pf": sum(row["pf_amount"] for row in label_records),
                "vpf": sum(row["vpf_amount"] for row in label_records),
                "gst": sum(row["gst_amount"] for row in label_records),
            }
        )

    expenses_excluding_gst = max(0.0, freelance_expenses - expense_gst_claims)
    freelance_profit = max(0.0, freelance_income - expenses_excluding_gst)
    try:
        standard_deduction = standard_deduction_for(financial_year, "auto", salary_income)
    except KeyError:
        standard_deduction = 0.0
    taxable_income = max(0.0, salary_income - standard_deduction + freelance_profit)
    return {
        "financial_year": financial_year,
        "summary": {
            "salary_income": round(salary_income, 2),
            "freelance_income": round(freelance_income, 2),
            "total_income": round(salary_income + freelance_income, 2),
            "freelance_expenses": round(freelance_expenses, 2),
            "total_expenses": round(freelance_expenses, 2),
            "expense_gst_claims": round(expense_gst_claims, 2),
            "freelance_gst_collected": round(freelance_gst_collected, 2),
            "expenses_excluding_gst": round(expenses_excluding_gst, 2),
            "freelance_profit": round(freelance_profit, 2),
            "salary_standard_deduction": round(standard_deduction, 2),
            "taxable_income": round(taxable_income, 2),
            "tds_paid": round(tds_paid, 2),
            "deductions": round(deductions, 2),
            "pf_total": round(pf_total, 2),
            "vpf_total": round(vpf_total, 2),
            "provident_fund_total": round(pf_total + vpf_total, 2),
            "net_income": round(net_income, 2),
            "record_count": len(records),
            "months_observed": len(monthly),
        },
        "monthly": monthly,
        "records": records,
        "expenses": expense_items,
    }
