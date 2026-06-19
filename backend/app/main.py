from __future__ import annotations

import shutil
import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .auth import change_pin, is_pin_configured, is_token_valid, login, logout, setup_pin, verify_app_pin
from .backup import create_backup, list_backup_history, restore_backup
from .database import DATA_DIR, UPLOAD_DIR, init_db, get_connection
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
    add_income_record,
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
from .tax import calculate_quarterly_advance_tax, calculate_tax_for_financial_year, calculate_tax_options, completed_financial_year_months, estimate_year_end, tax_slabs_catalog
from .financial_year import parse_date_strict
from .settings import get_settings, update_settings
from .review import list_audit_events, reconciliation_report, validation_report
from .tax_documents import (
    activate_tax_document,
    build_tax_extraction,
    list_tax_documents,
    parse_tax_statement_text,
    resolve_tax_document_user,
    save_tax_document_parse,
)
from .tax_reconciliation import tax_statement_report
from .tax_planning import cloud_ai_analysis, cloud_ai_chat, tax_planning_report, update_planning_inputs
from .tax_rule_updates import apply_tax_rule_update, draft_tax_rule_update
from .workbook import create_import_template, create_workbook_export, import_workbook


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
    gross_amount: float = Field(default=0.0, ge=0.0)
    net_amount: float = Field(default=0.0, ge=0.0)
    tds_amount: float = Field(default=0.0, ge=0.0)
    deductions_amount: float = Field(default=0.0, ge=0.0)
    pf_amount: float = Field(default=0.0, ge=0.0)
    vpf_amount: float = Field(default=0.0, ge=0.0)
    gst_amount: float = Field(default=0.0, ge=0.0)
    category: str | None = None
    notes: str | None = None


class ExpenseCreate(BaseModel):
    user_id: int
    expense_date: str
    category: str
    amount: float = Field(..., gt=0.0)
    gst_amount: float = Field(default=0.0, ge=0.0)
    notes: str = ""


class IncomeRecordCreate(BaseModel):
    user_id: int
    income_type: str
    record_date: str
    payer: str | None = None
    gross_amount: float = Field(default=0.0, ge=0.0)
    net_amount: float = Field(default=0.0, ge=0.0)
    tds_amount: float = Field(default=0.0, ge=0.0)
    deductions_amount: float = Field(default=0.0, ge=0.0)
    pf_amount: float = Field(default=0.0, ge=0.0)
    vpf_amount: float = Field(default=0.0, ge=0.0)
    gst_amount: float = Field(default=0.0, ge=0.0)


class AuthPin(BaseModel):
    pin: str = Field(min_length=4, max_length=128)


class ChangePin(BaseModel):
    current_pin: str = Field(min_length=4, max_length=128)
    new_pin: str = Field(min_length=4, max_length=128)


class SettingsUpdate(BaseModel):
    default_user_id: str | None = None
    default_financial_year: str | None = None
    local_ai_base_url: str | None = None
    local_ai_model: str | None = None
    local_ai_timeout_seconds: int | None = None
    local_ai_rendered_pages: int | None = None
    cloud_ai_base_url: str | None = None
    cloud_ai_model: str | None = None
    cloud_ai_api_key: str | None = None
    clear_cloud_ai_api_key: bool | None = None


class TaxPlanningInputs(BaseModel):
    freelance_method: str | None = None
    advance_tax_paid: float | None = None
    employer_nps_enabled: bool | None = None
    employer_nps_amount: float | None = None
    basic_da_salary: float | None = None
    let_out_property_interest: float | None = None
    let_out_property_rent: float | None = None


class CloudAIMessage(BaseModel):
    role: str
    content: str


class CloudAIChatRequest(BaseModel):
    messages: list[CloudAIMessage] = []
    total_tokens: int = 0


class TaxRuleDraftRequest(BaseModel):
    financial_year: str = Field(min_length=1)


class TaxRuleApplyRequest(BaseModel):
    draft: dict
    app_pin: str = Field(min_length=4, max_length=128)


PUBLIC_API_PATHS = {
    "/api/health",
    "/api/auth/status",
    "/api/auth/setup",
    "/api/auth/login",
}


@app.middleware("http")
async def require_auth_token(request: Request, call_next):
    if request.method == "OPTIONS" or request.url.path in PUBLIC_API_PATHS:
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        token = request.headers.get("X-Income-Ledger-Token")
        if not is_token_valid(token):
            return JSONResponse({"detail": "Unlock Income Ledger to continue."}, status_code=401)
    return await call_next(request)


@app.get("/api/auth/status")
def auth_status() -> dict:
    return {"setup_required": not is_pin_configured()}


@app.post("/api/auth/setup")
def auth_setup(payload: AuthPin) -> dict:
    try:
        setup_pin(payload.pin)
        token = login(payload.pin)
        return {"token": token}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/login")
def auth_login(payload: AuthPin) -> dict:
    try:
        return {"token": login(payload.pin)}
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/api/auth/logout")
def auth_logout(request: Request) -> dict:
    logout(request.headers.get("X-Income-Ledger-Token"))
    return {"ok": True}


@app.post("/api/auth/change-pin")
def auth_change_pin(payload: ChangePin) -> dict:
    try:
        change_pin(payload.current_pin, payload.new_pin)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/settings")
def settings_get() -> dict:
    return get_settings()


@app.put("/api/settings")
def settings_put(payload: SettingsUpdate) -> dict:
    try:
        return update_settings(payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/backup/export")
def backup_export() -> FileResponse:
    backup = create_backup()
    return FileResponse(
        backup["path"],
        media_type="application/zip",
        filename=backup["filename"],
    )


@app.get("/api/backup/history")
def backup_history() -> list[dict]:
    return list_backup_history()


@app.post("/api/backup/restore")
def backup_restore(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only Income Ledger ZIP backups are supported.")
    safe_name = Path(file.filename).name
    temp_path = DATA_DIR / f"restore-{safe_name}"
    with temp_path.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)
    try:
        return restore_backup(temp_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)


@app.get("/api/export/workbook")
def workbook_export(
    user_id: str = "all",
    financial_year: str | None = None,
    user_ids: str | None = None,
    financial_years: str | None = None,
) -> FileResponse:
    if not (financial_years or financial_year):
        raise HTTPException(status_code=400, detail="financial_year is required")
    try:
        path = create_workbook_export(
            user_id=user_id,
            financial_year=financial_year,
            user_ids=user_ids,
            financial_years=financial_years,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="income-ledger-export.xlsx")


@app.get("/api/import/template")
def workbook_template() -> FileResponse:
    try:
        path = create_import_template()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="income-ledger-import-template.xlsx")


@app.post("/api/import/workbook")
def workbook_import(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx workbooks are supported.")
    temp_path = DATA_DIR / f"import-{Path(file.filename).name}"
    with temp_path.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)
    try:
        return import_workbook(temp_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)


@app.get("/api/audit-events")
def audit_events(
    user_id: str | None = None,
    document_id: int | None = None,
    event_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    return list_audit_events(user_id, document_id, event_type, date_from, date_to, limit, offset)


@app.get("/api/reconciliation")
def reconciliation(user_id: str | None = None, financial_year: str | None = None) -> dict:
    return reconciliation_report(user_id, financial_year)


@app.get("/api/validation-report")
def data_validation_report(user_id: str = "all", financial_year: str | None = None) -> dict:
    if not financial_year:
        raise HTTPException(status_code=400, detail="financial_year is required")
    return validation_report(user_id, financial_year)


@app.get("/api/tax-documents")
def tax_documents(user_id: str | None = None, financial_year: str | None = None) -> dict:
    return list_tax_documents(user_id, financial_year)


@app.post("/api/tax-documents/{document_id}/activate")
def tax_document_activate(document_id: int) -> dict:
    try:
        return activate_tax_document(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/tax-reconciliation/{user_id}/{financial_year}")
def tax_reconciliation(user_id: str, financial_year: str) -> dict:
    return tax_statement_report(user_id, financial_year)


@app.get("/api/tax-planning/{user_id}/{financial_year}")
def tax_planning(user_id: str, financial_year: str) -> dict:
    try:
        return tax_planning_report(user_id, financial_year)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/tax-planning/{user_id}/{financial_year}/inputs")
def tax_planning_inputs_update(user_id: str, financial_year: str, payload: TaxPlanningInputs) -> dict:
    try:
        return update_planning_inputs(user_id, financial_year, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/tax-planning/{user_id}/{financial_year}/ai-analysis")
def tax_planning_ai_analysis(user_id: str, financial_year: str) -> dict:
    try:
        return cloud_ai_analysis(user_id, financial_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/tax-planning/{user_id}/{financial_year}/ai-chat")
def tax_planning_ai_chat(user_id: str, financial_year: str, payload: CloudAIChatRequest) -> dict:
    try:
        return cloud_ai_chat(user_id, financial_year, [message.model_dump() for message in payload.messages], payload.total_tokens)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/tax-rules/ai-draft")
def tax_rule_ai_draft(payload: TaxRuleDraftRequest) -> dict:
    try:
        return draft_tax_rule_update(payload.financial_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/tax-rules/apply")
def tax_rule_apply(payload: TaxRuleApplyRequest) -> dict:
    if not verify_app_pin(payload.app_pin):
        raise HTTPException(status_code=403, detail="App PIN confirmation failed.")
    try:
        return apply_tax_rule_update(payload.draft)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


def has_valid_record_date(extraction: dict) -> bool:
    try:
        parse_date_strict(extraction.get("record_date"))
        return True
    except ValueError:
        return False


def duplicate_confirmed_response(document: dict) -> dict | None:
    if document.get("duplicate") and document.get("status") == "confirmed":
        existing = get_document(document["id"]) or document
        existing["duplicate"] = True
        return {
            "success": True,
            "duplicate": True,
            "reason": "duplicate_confirmed",
            "document": existing,
        }
    return None


def save_tax_statement_upload(
    safe_name: str,
    stored_path: Path,
    digest: str,
    embedded_text: str,
    warnings: list[str],
    selected_user_id: int | None,
) -> dict | None:
    parsed = parse_tax_statement_text(embedded_text, warnings)
    if not parsed:
        return None
    detected_user_id, user_warnings = resolve_tax_document_user(parsed, selected_user_id)
    combined_warnings = [*warnings, *user_warnings]
    extraction = build_tax_extraction(parsed, combined_warnings, user_id=detected_user_id)
    document = create_document(safe_name, stored_path, digest, extraction, detected_user_id, parsed.confidence)
    duplicate_response = duplicate_confirmed_response(document)
    if duplicate_response:
        duplicate_response["tax_statement"] = True
        return duplicate_response
    saved = save_tax_document_parse(document["id"], parsed, detected_user_id, combined_warnings)
    return {
        "success": saved.get("status") == "confirmed",
        "tax_statement": True,
        "document": saved,
        "warnings": saved.get("warnings", []),
    }


def save_existing_tax_statement(
    document_id: int,
    embedded_text: str,
    warnings: list[str],
    selected_user_id: int | None,
) -> dict | None:
    parsed = parse_tax_statement_text(embedded_text, warnings)
    if not parsed:
        return None
    detected_user_id, user_warnings = resolve_tax_document_user(parsed, selected_user_id)
    combined_warnings = [*warnings, *user_warnings]
    saved = save_tax_document_parse(document_id, parsed, detected_user_id, combined_warnings)
    return {
        "success": saved.get("status") == "confirmed",
        "tax_statement": True,
        "document": saved,
        "warnings": saved.get("warnings", []),
    }


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

    valid_record_date = has_valid_record_date(extraction)
    if extraction.get("record_date") and not valid_record_date:
        extraction["warnings"] = [
            *extraction.get("warnings", []),
            "The extracted date is invalid. Please check and update the date manually.",
        ]
    elif not extraction.get("record_date"):
        extraction["warnings"] = [
            *extraction.get("warnings", []),
            "No valid date was extracted. Please check and update the date manually.",
        ]
    
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
    if selected_user and should_save_invoice_as_expense(extraction, selected_user) and valid_record_date:
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
    elif detected_user_id and valid_record_date and extraction.get("document_type") != "unknown":
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
            is_scanned = not embedded_text
            
            if not embedded_text:
                try:
                    import fitz
                    from PIL import Image
                    import io
                    import pytesseract
                    ocr_lines = []
                    with fitz.open(stored_path) as doc:
                        for page in doc:
                            pix = page.get_pixmap(dpi=220)
                            img_data = pix.tobytes("png")
                            img = Image.open(io.BytesIO(img_data))
                            ocr_lines.append(pytesseract.image_to_string(img))
                    ocr_text = "\n".join(ocr_lines).strip()
                    if ocr_text:
                        embedded_text = ocr_text
                        warnings.append("Text was extracted using local OCR fallback.")
                except Exception as exc:
                    warnings.append(f"Local OCR fallback could not run: {exc}")

            if embedded_text:
                tax_response = save_tax_statement_upload(safe_name, stored_path, digest, embedded_text, warnings, user_id)
                if tax_response:
                    return tax_response
                    
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
                duplicate_response = duplicate_confirmed_response(document)
                if duplicate_response:
                    return duplicate_response
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
                duplicate_response = duplicate_confirmed_response(document)
                if duplicate_response:
                    return duplicate_response
                updated_doc = save_and_confirm_extraction(document["id"], extraction_dict, user_id, 0.25)
                return {"success": False, "reason": "local_failed", "is_scanned": is_scanned, "document": updated_doc}
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
            duplicate_response = duplicate_confirmed_response(document)
            if duplicate_response:
                return duplicate_response
            updated_doc = save_and_confirm_extraction(document["id"], extraction_dict, user_id, 0.0)
            return {"success": False, "reason": "local_failed", "is_scanned": True, "document": updated_doc}

    # Backward compatibility / synchronous fallback
    embedded_text, embedded_warnings = extract_embedded_pdf_text(stored_path)
    if embedded_text:
        tax_response = save_tax_statement_upload(safe_name, stored_path, digest, embedded_text, embedded_warnings, user_id)
        if tax_response:
            return tax_response

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
    duplicate_response = duplicate_confirmed_response(document)
    if duplicate_response:
        return duplicate_response
    
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
            import fitz
            from PIL import Image
            import io
            import pytesseract
            ocr_lines = []
            with fitz.open(stored_path) as doc:
                for page in doc:
                    pix = page.get_pixmap(dpi=220)
                    img_data = pix.tobytes("png")
                    img = Image.open(io.BytesIO(img_data))
                    ocr_lines.append(pytesseract.image_to_string(img))
            ocr_text = "\n".join(ocr_lines).strip()
            if ocr_text:
                embedded_text = ocr_text
                warnings.append("Text was extracted using local OCR fallback.")
        except Exception as exc:
            warnings.append(f"Local OCR fallback could not run: {exc}")

    if embedded_text:
        tax_response = save_existing_tax_statement(document_id, embedded_text, warnings, user_id)
        if tax_response:
            return tax_response
            
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/records/{record_id}")
def record_delete(record_id: int) -> dict:
    try:
        return delete_income_record(record_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/records")
def records_create(payload: IncomeRecordCreate) -> dict:
    try:
        return add_income_record(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/expenses")
def expense_create(payload: ExpenseCreate) -> dict:
    try:
        return add_expense(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    try:
        current_tax_options = calculate_tax_options(
            financial_year,
            data["summary"]["salary_income"],
            data["summary"]["freelance_profit"],
        )
        tax = current_tax_options["selected"]
        projection_months = completed_financial_year_months(financial_year)
        predicted_salary = estimate_year_end(data["summary"]["salary_income"], projection_months)
        predicted_freelance_profit = estimate_year_end(data["summary"]["freelance_profit"], projection_months)
        predicted_tds = estimate_year_end(data["summary"]["tds_paid"], projection_months)
        predicted_tax = calculate_tax_for_financial_year(financial_year, predicted_salary, predicted_freelance_profit, tax["regime"])
        predicted_tax_options = calculate_tax_options(financial_year, predicted_salary, predicted_freelance_profit)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    predicted_remaining_tax = round(max(0, predicted_tax["total_tax"] - predicted_tds), 2)
    quarterly_advance_tax = calculate_quarterly_advance_tax(predicted_remaining_tax)
    data["tax"] = {
        **tax,
        "options": predicted_tax_options["options"],
        "current_options": current_tax_options["options"],
        "available_regimes": predicted_tax_options["available_regimes"],
        "tds_paid": data["summary"]["tds_paid"],
        "remaining_tax": round(max(0, tax["total_tax"] - data["summary"]["tds_paid"]), 2),
        "predicted_salary_income": predicted_salary,
        "predicted_freelance_profit": predicted_freelance_profit,
        "predicted_tds_paid": predicted_tds,
        "predicted_annual_income": round(predicted_salary + predicted_freelance_profit, 2),
        "predicted_taxable_income": predicted_tax["taxable_income"],
        "predicted_total_tax": predicted_tax["total_tax"],
        "predicted_remaining_tax": predicted_remaining_tax,
        "projection_months": projection_months,
        "quarterly_advance_tax": quarterly_advance_tax,
    }
    return data


@app.get("/api/tax/{user_id}/{financial_year}")
def tax(user_id: str, financial_year: str, regime: str = "auto") -> dict:
    data = dashboard_data(user_id, financial_year)
    try:
        tax_data = calculate_tax_for_financial_year(
            financial_year,
            data["summary"]["salary_income"],
            data["summary"]["freelance_profit"],
            regime,
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        **tax_data,
        "tds_paid": data["summary"]["tds_paid"],
        "remaining_tax": round(max(0, tax_data["total_tax"] - data["summary"]["tds_paid"]), 2),
    }


@app.get("/api/tax-slabs")
def tax_slabs() -> dict:
    return tax_slabs_catalog()
