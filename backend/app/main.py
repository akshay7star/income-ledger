from __future__ import annotations

import shutil
import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .database import UPLOAD_DIR, init_db, get_connection
from .extraction import (
    extract_financial_fields,
    file_sha256,
    extract_embedded_pdf_text,
    run_local_parser,
    validate_local_extraction,
    classify_expense_category,
    extract_structured_data_with_ai,
    extraction_result_from_ai_data,
)
from .repositories import (
    add_expense,
    add_document_expense,
    confirm_extraction,
    create_document,
    create_user,
    update_user,
    delete_user,
    dashboard_data,
    delete_document,
    delete_expense,
    delete_income_record,
    get_document,
    get_user,
    get_or_create_user_for_extraction,
    list_documents,
    list_financial_years,
    list_users,
)
from .tax import calculate_quarterly_advance_tax, calculate_tax_for_financial_year, calculate_tax_options, elapsed_financial_year_months, estimate_year_end, tax_slabs_catalog


app = FastAPI(title="Income Ledger API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
        "http://localhost:5175", "http://127.0.0.1:5175"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UserCreate(BaseModel):
    name: str = Field(min_length=1)
    pan: str | None = None
    aliases: str = ""
    profile_hints: str = ""


class ConfirmExtraction(BaseModel):
    user_id: int
    income_type: str
    record_date: str | None = None
    payer: str | None = None
    gross_amount: float = 0
    net_amount: float = 0
    tds_amount: float = 0
    deductions_amount: float = 0
    pf_amount: float = 0
    vpf_amount: float = 0
    gst_amount: float = 0
    category: str | None = None
    notes: str | None = None


class ExpenseCreate(BaseModel):
    user_id: int
    expense_date: str
    category: str
    amount: float
    gst_amount: float = 0
    notes: str = ""


def _contains_name(text: str | None, name: str | None) -> bool:
    if not text or not name:
        return False
    normalized_text = " ".join(str(text).lower().split())
    normalized_name = " ".join(str(name).lower().split())
    return bool(normalized_name and normalized_name in normalized_text)


def should_save_invoice_as_expense(extraction: dict, selected_user: dict | None) -> bool:
    if not selected_user:
        return False
    doc_type = extraction.get("document_type")
    if doc_type == "salary":
        return False
    if doc_type == "purchase_expense":
        return True
    if doc_type != "freelance_invoice":
        return False

    seller_name = extraction.get("name")
    seller_pan = (extraction.get("pan") or "").upper().strip()
    user_pan = (selected_user.get("pan") or "").upper().strip()
    if user_pan and seller_pan == user_pan:
        return False

    from .repositories import name_similarity
    if seller_name and name_similarity(seller_name, selected_user.get("name")) >= 0.75:
        return False

    buyer_text = " ".join(str(extraction.get(key) or "") for key in ["payer", "extracted_text"])
    return _contains_name(buyer_text, selected_user.get("name")) or bool(seller_name or seller_pan)


def has_usable_extraction(extraction: dict) -> bool:
    if extraction.get("document_type") == "unknown":
        return False
    if extraction.get("record_date") and (float(extraction.get("gross_amount") or 0) > 0 or float(extraction.get("net_amount") or 0) > 0):
        return True
    return bool(extraction.get("name") or extraction.get("payer")) and (
        float(extraction.get("gross_amount") or 0) > 0 or float(extraction.get("net_amount") or 0) > 0
    )


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/users")
def users() -> list[dict]:
    return list_users()


@app.post("/api/users")
def users_create(payload: UserCreate) -> dict:
    return create_user(payload.model_dump())


@app.put("/api/users/{user_id}")
def users_update(user_id: int, payload: UserCreate) -> dict:
    try:
        return update_user(user_id, payload.model_dump())
    except KeyError:
        raise HTTPException(status_code=404, detail="User not found")


@app.delete("/api/users/{user_id}")
def users_delete(user_id: int) -> dict:
    try:
        return delete_user(user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="User not found")



def save_and_confirm_extraction(document_id: int, extraction: dict, selected_user_id: int | None, initial_confidence: float) -> dict:
    selected_user = get_user(selected_user_id) if selected_user_id else None
    if selected_user and should_save_invoice_as_expense(extraction, selected_user):
        detected_user_id, match_confidence = int(selected_user["id"]), 0.9
    else:
        detected_user_id, match_confidence = get_or_create_user_for_extraction(extraction)
        
    confidence = round((initial_confidence + match_confidence) / 2, 2) if detected_user_id else initial_confidence
    
    # Update document in DB with new extraction details
    with get_connection() as conn:
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
                document_id,
            ),
        )
        conn.commit()
        
    document = get_document(document_id)
    
    # Check if we can auto-confirm
    if selected_user and should_save_invoice_as_expense(extraction, selected_user) and extraction.get("record_date"):
        amount = extraction.get("net_amount") or extraction.get("gross_amount") or 0
        payload = {
            "user_id": int(selected_user["id"]),
            "expense_date": extraction.get("record_date"),
            "category": "Purchase invoice",
            "amount": amount,
            "gst_amount": extraction.get("gst_amount") or 0,
            "notes": f"{document['original_name']}: {extraction.get('name') or 'Vendor invoice'}",
        }
        add_document_expense(document["id"], payload)
        document = get_document(document["id"])
        extraction = {
            **extraction,
            "user_id": int(selected_user["id"]),
            "document_type": "purchase_expense",
            "expense_amount": amount,
        }
    elif detected_user_id and extraction.get("record_date") and extraction.get("document_type") != "unknown":
        income_type = "salary" if extraction["document_type"] == "salary" else "freelance_invoice"
        payload = {
            "user_id": detected_user_id,
            "income_type": income_type,
            "record_date": extraction.get("record_date"),
            "payer": extraction.get("payer"),
            "gross_amount": extraction.get("gross_amount") or 0,
            "net_amount": extraction.get("net_amount") or 0,
            "tds_amount": extraction.get("tds_amount") or 0,
            "deductions_amount": extraction.get("deductions_amount") or 0,
            "pf_amount": extraction.get("pf_amount") or 0,
            "vpf_amount": extraction.get("vpf_amount") or 0,
            "gst_amount": extraction.get("gst_amount") or 0,
        }
        confirm_extraction(document["id"], payload)
        document = get_document(document["id"])
        
    document["extracted"] = extraction
    document["detected_user_id"] = detected_user_id or document.get("detected_user_id")
    return document


@app.post("/api/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    user_id: int | None = Form(None),
    ai_provider: str | None = Form(None),
    stage: str | None = Form(None)
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    safe_name = Path(file.filename).name
    temp_path = UPLOAD_DIR / f"tmp-{safe_name}"
    with temp_path.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)

    digest = file_sha256(temp_path)
    stored_path = UPLOAD_DIR / f"{digest[:16]}-{safe_name}"
    if not stored_path.exists():
        temp_path.replace(stored_path)
    else:
        temp_path.unlink(missing_ok=True)

    # Stage 1: Local parsing only
    if stage == "local":
        try:
            embedded_text, embedded_warnings = extract_embedded_pdf_text(stored_path)
            warnings = list(embedded_warnings)
            
            if not embedded_text:
                try:
                    from pdf2image import convert_from_path
                    import pytesseract
                    images = convert_from_path(str(stored_path), dpi=220)
                    ocr_text = "\n".join(pytesseract.image_to_string(image) for image in images).strip()
                    if ocr_text:
                        embedded_text = ocr_text
                        warnings.append("Text was extracted using local OCR fallback.")
                except Exception as exc:
                    warnings.append(f"Local OCR fallback could not run: {exc}")
                    
            local_data = {}
            local_success = False
            if embedded_text:
                local_data = run_local_parser(embedded_text)
                local_success = validate_local_extraction(local_data)
                
            if local_success:
                category = "Others"
                if local_data["document_type"] == "purchase_expense":
                    category = classify_expense_category(embedded_text)
                extraction_dict = {
                    "document_type": local_data["document_type"],
                    "name": local_data["name"],
                    "pan": local_data["pan"],
                    "payer": local_data["payer"],
                    "record_date": local_data["record_date"],
                    "gross_amount": local_data["gross_amount"],
                    "net_amount": local_data["net_amount"],
                    "tds_amount": local_data["tds_amount"],
                    "deductions_amount": local_data["deductions_amount"],
                    "pf_amount": local_data["pf_amount"],
                    "vpf_amount": local_data["vpf_amount"],
                    "gst_amount": local_data["gst_amount"],
                    "confidence": 0.95,
                    "warnings": warnings,
                    "extracted_text": json.dumps(local_data)
                }
                document = create_document(safe_name, stored_path, digest, extraction_dict, None, 0.95)
                confirmed_doc = save_and_confirm_extraction(document["id"], extraction_dict, user_id, 0.95)
                return {"success": True, "document": confirmed_doc}
            else:
                best_doc_type = local_data.get("document_type", "unknown") if local_data else "unknown"
                extraction_dict = {
                    "document_type": best_doc_type,
                    "name": local_data.get("name") if local_data else None,
                    "pan": local_data.get("pan") if local_data else None,
                    "payer": local_data.get("payer") if local_data else None,
                    "record_date": local_data.get("record_date") if local_data else None,
                    "gross_amount": local_data.get("gross_amount", 0.0) if local_data else 0.0,
                    "net_amount": local_data.get("net_amount", 0.0) if local_data else 0.0,
                    "tds_amount": local_data.get("tds_amount", 0.0) if local_data else 0.0,
                    "deductions_amount": local_data.get("deductions_amount", 0.0) if local_data else 0.0,
                    "pf_amount": local_data.get("pf_amount", 0.0) if local_data else 0.0,
                    "vpf_amount": local_data.get("vpf_amount", 0.0) if local_data else 0.0,
                    "gst_amount": local_data.get("gst_amount", 0.0) if local_data else 0.0,
                    "confidence": 0.25,
                    "warnings": warnings,
                    "extracted_text": json.dumps(local_data) if local_data else ""
                }
                document = create_document(safe_name, stored_path, digest, extraction_dict, None, 0.25)
                updated_doc = save_and_confirm_extraction(document["id"], extraction_dict, user_id, 0.25)
                return {"success": False, "reason": "local_failed", "document": updated_doc}
        except Exception as exc:
            extraction_dict = {
                "document_type": "unknown",
                "name": None,
                "pan": None,
                "payer": None,
                "record_date": None,
                "gross_amount": 0.0,
                "net_amount": 0.0,
                "tds_amount": 0.0,
                "deductions_amount": 0.0,
                "pf_amount": 0.0,
                "vpf_amount": 0.0,
                "gst_amount": 0.0,
                "confidence": 0.0,
                "warnings": [f"Local extraction crashed: {exc}"],
                "extracted_text": ""
            }
            document = create_document(safe_name, stored_path, digest, extraction_dict, None, 0.0)
            updated_doc = save_and_confirm_extraction(document["id"], extraction_dict, user_id, 0.0)
            return {"success": False, "reason": "local_failed", "document": updated_doc}

    # Backward compatibility / synchronous fallback
    extraction = extract_financial_fields(stored_path, "local").to_dict()
    selected_user = get_user(user_id) if user_id else None
    if user_id and not selected_user:
        raise HTTPException(status_code=404, detail="Selected user was not found.")

    if selected_user and should_save_invoice_as_expense(extraction, selected_user):
        detected_user_id, match_confidence = int(selected_user["id"]), 0.9
    else:
        detected_user_id, match_confidence = get_or_create_user_for_extraction(extraction)
    confidence = round((extraction["confidence"] + match_confidence) / 2, 2) if detected_user_id else extraction["confidence"]
    document = create_document(safe_name, stored_path, digest, extraction, detected_user_id, confidence)
    
    confirmed_doc = save_and_confirm_extraction(document["id"], extraction, user_id, extraction["confidence"])
    return confirmed_doc


@app.post("/api/documents/{document_id}/re-extract")
def re_extract_document(
    document_id: int,
    ai_provider: str = Form("local"),
    user_id: int | None = Form(None)
) -> dict:
    document = get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
        
    stored_path = Path(document["stored_path"])
    if not stored_path.exists():
        raise HTTPException(status_code=404, detail="Stored PDF file not found")
        
    embedded_text, embedded_warnings = extract_embedded_pdf_text(stored_path)
    warnings = list(embedded_warnings)
    
    if not embedded_text:
        try:
            from pdf2image import convert_from_path
            import pytesseract
            images = convert_from_path(str(stored_path), dpi=220)
            ocr_text = "\n".join(pytesseract.image_to_string(image) for image in images).strip()
            if ocr_text:
                embedded_text = ocr_text
                warnings.append("Text was extracted using local OCR fallback.")
        except Exception as exc:
            warnings.append(f"Local OCR fallback could not run: {exc}")
            
    try:
        ai_data, ai_warnings = extract_structured_data_with_ai(stored_path, embedded_text, "local")
        warnings.extend(ai_warnings)
        if ai_data:
            result = extraction_result_from_ai_data(ai_data, warnings, embedded_text)
            extraction_dict = result.to_dict()
            success = has_usable_extraction(extraction_dict)
            if not validate_local_extraction(extraction_dict):
                extraction_dict["warnings"] = [
                    *extraction_dict.get("warnings", []),
                    "Local Hosted LM Studio AI returned structured data, but it still needs review before it can be auto-confirmed.",
                ]
            updated_doc = save_and_confirm_extraction(document_id, extraction_dict, user_id, extraction_dict["confidence"])
            return {"success": success, "document": updated_doc, "warnings": extraction_dict.get("warnings", [])}
    except Exception as exc:
        warnings.append(f"Local Hosted LM Studio AI extraction failed: {exc}")
        
    return {"success": False, "reason": "local_ai_failed", "detail": "; ".join(warnings[-3:]), "warnings": warnings, "document": document}


@app.get("/api/documents")
def documents() -> list[dict]:
    return list_documents()


@app.get("/api/documents/{document_id}/file")
def document_file(document_id: int) -> FileResponse:
    document = get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    path = Path(document["stored_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored PDF file not found")
    return FileResponse(path, media_type="application/pdf", filename=document["original_name"])


@app.delete("/api/documents/{document_id}")
def document_delete(document_id: int) -> dict:
    try:
        return delete_document(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/extractions/{document_id}/confirm")
def extraction_confirm(document_id: int, payload: ConfirmExtraction) -> dict:
    try:
        return confirm_extraction(document_id, payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/records/{record_id}")
def record_delete(record_id: int) -> dict:
    try:
        return delete_income_record(record_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/expenses")
def expense_create(payload: ExpenseCreate) -> dict:
    return add_expense(payload.model_dump())


@app.delete("/api/expenses/{expense_id}")
def expense_delete(expense_id: int) -> dict:
    try:
        return delete_expense(expense_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/financial-years")
def financial_years(user_id: str | None = None) -> list[str]:
    return list_financial_years(user_id)


@app.get("/api/dashboard/{user_id}/{financial_year}")
def dashboard(user_id: str, financial_year: str) -> dict:
    data = dashboard_data(user_id, financial_year)
    current_tax_options = calculate_tax_options(
        financial_year,
        data["summary"]["salary_income"],
        data["summary"]["freelance_profit"],
    )
    tax = current_tax_options["selected"]
    projection_months = elapsed_financial_year_months(financial_year)
    predicted_salary = estimate_year_end(data["summary"]["salary_income"], projection_months)
    predicted_freelance_profit = estimate_year_end(data["summary"]["freelance_profit"], projection_months)
    predicted_tax = calculate_tax_for_financial_year(financial_year, predicted_salary, predicted_freelance_profit, tax["regime"])
    predicted_tax_options = calculate_tax_options(financial_year, predicted_salary, predicted_freelance_profit)
    quarterly_advance_tax = calculate_quarterly_advance_tax(predicted_tax["total_tax"])
    data["tax"] = {
        **tax,
        "options": predicted_tax_options["options"],
        "current_options": current_tax_options["options"],
        "available_regimes": predicted_tax_options["available_regimes"],
        "tds_paid": data["summary"]["tds_paid"],
        "remaining_tax": round(max(0, tax["total_tax"] - data["summary"]["tds_paid"]), 2),
        "predicted_salary_income": predicted_salary,
        "predicted_freelance_profit": predicted_freelance_profit,
        "predicted_annual_income": round(predicted_salary + predicted_freelance_profit, 2),
        "predicted_taxable_income": predicted_tax["taxable_income"],
        "predicted_total_tax": predicted_tax["total_tax"],
        "projection_months": projection_months,
        "quarterly_advance_tax": quarterly_advance_tax,
    }
    return data


@app.get("/api/tax/{user_id}/{financial_year}")
def tax(user_id: str, financial_year: str, regime: str = "auto") -> dict:
    data = dashboard_data(user_id, financial_year)
    tax_data = calculate_tax_for_financial_year(
        financial_year,
        data["summary"]["salary_income"],
        data["summary"]["freelance_profit"],
        regime,
    )
    return {
        **tax_data,
        "tds_paid": data["summary"]["tds_paid"],
        "remaining_tax": round(max(0, tax_data["total_tax"] - data["summary"]["tds_paid"]), 2),
    }


@app.get("/api/tax-slabs")
def tax_slabs() -> dict:
    return tax_slabs_catalog()
