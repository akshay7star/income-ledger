from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .database import UPLOAD_DIR, init_db
from .extraction import extract_financial_fields, file_sha256
from .repositories import (
    add_expense,
    add_document_expense,
    confirm_extraction,
    create_document,
    create_user,
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
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
    if not selected_user or extraction.get("document_type") != "freelance_invoice":
        return False
    seller_name = extraction.get("name")
    seller_pan = (extraction.get("pan") or "").upper().strip()
    user_pan = (selected_user.get("pan") or "").upper().strip()
    if user_pan and seller_pan == user_pan:
        return False
    if _contains_name(seller_name, selected_user.get("name")):
        return False
    buyer_text = " ".join(str(extraction.get(key) or "") for key in ["payer", "extracted_text"])
    return _contains_name(buyer_text, selected_user.get("name")) or bool(seller_name or seller_pan)


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


@app.post("/api/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    user_id: int | None = Form(None),
    ai_provider: str | None = Form(None)
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

    extraction = extract_financial_fields(stored_path, ai_provider or "nvidia").to_dict()
    selected_user = get_user(user_id) if user_id else None
    if user_id and not selected_user:
        raise HTTPException(status_code=404, detail="Selected user was not found.")

    if selected_user and should_save_invoice_as_expense(extraction, selected_user):
        detected_user_id, match_confidence = int(selected_user["id"]), 0.9
    else:
        detected_user_id, match_confidence = get_or_create_user_for_extraction(extraction)
    confidence = round((extraction["confidence"] + match_confidence) / 2, 2) if detected_user_id else extraction["confidence"]
    document = create_document(safe_name, stored_path, digest, extraction, detected_user_id, confidence)
    if selected_user and should_save_invoice_as_expense(extraction, selected_user) and extraction.get("record_date"):
        amount = extraction.get("net_amount") or extraction.get("gross_amount") or 0
        payload = {
            "user_id": int(selected_user["id"]),
            "expense_date": extraction.get("record_date"),
            "category": "Purchase invoice",
            "amount": amount,
            "gst_amount": extraction.get("gst_amount") or 0,
            "notes": f"{safe_name}: {extraction.get('name') or 'Vendor invoice'}",
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
def financial_years() -> list[str]:
    return list_financial_years()


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
