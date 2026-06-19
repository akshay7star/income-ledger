from __future__ import annotations

import hashlib
import base64
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


AMOUNT_PATTERNS = {
    "gross_amount": [
        r"(?:gross\s+(?:pay|salary|amount|earnings|earning)|total\s+earnings|total\s+earning)\D{0,80}([\d,]+(?:\.\d{1,2})?)",
    ],
    "net_amount": [
        r"(?:total\s+net\s+pay(?:\(a\+b\))?|a\.?\s*net\s+salary|net\s+(?:pay|salary|amount|payable))\D{0,80}([\d,]+(?:\.\d{1,2})?)",
    ],
    "tds_amount": [r"(?:tds|income\s*tax|tax\s+deducted)\D{0,80}([\d,]+(?:\.\d{1,2})?)"],
    "deductions_amount": [r"(?:total\s+deductions|total\s+deduction)\D{0,80}([\d,]+(?:\.\d{1,2})?)"],
    "invoice_amount": [r"(?:invoice\s+amount|total\s+amount|amount\s+due)\D{0,80}([\d,]+(?:\.\d{1,2})?)"],
}

AMOUNT_RE = re.compile(r"\d[\d,]*(?:\.\d{1,2})?")
CURRENCY_AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?")

def _load_env_file():
    curr = Path(__file__).resolve().parent
    for _ in range(4):
        env_path = curr / ".env"
        if env_path.is_file():
            try:
                with env_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k:
                                os.environ[k] = v
            except Exception:
                pass
            break
        curr = curr.parent

_load_env_file()

LOCAL_AI_MODEL = os.getenv("LOCAL_AI_MODEL", "google/gemma-4-e4b")
LOCAL_AI_TIMEOUT_SECONDS = float(os.getenv("LOCAL_AI_TIMEOUT_SECONDS", "120"))
LOCAL_AI_API_KEY = os.getenv("LOCAL_AI_API_KEY", "")
LOCAL_AI_BASE_URLS = [
    item.rstrip("/")
    for item in os.getenv("LOCAL_AI_BASE_URL", "http://127.0.0.1:1234/v1").split(",")
    if item.strip()
]
LOCAL_AI_RENDERED_PAGES = max(1, int(os.getenv("LOCAL_AI_RENDERED_PAGES", "1")))

LOCAL_AI_EXTRACTION_PROMPT = (
    "You are an expert Indian Financial Data Extractor. Your task is to analyze the provided financial document (Invoice, Payslip, or Receipt) and return a strictly structured JSON response.\n\n"
    "### GUIDELINES FOR ACCURACY:\n"
    "1. Entity Roles:\n"
    "   - For Invoices: 'seller_name' is the party issuing the invoice (providing services). 'buyer_name' is the client paying the invoice.\n"
    "   - For Payslips: 'seller_name' is the Employer/Company. 'employee_name' is the Employee.\n"
    "2. Numeric Values:\n"
    "   - Extract raw numeric numbers only. Strip currency symbols (₹, Rs, USD) and commas before outputting.\n"
    "   - Ensure 'total_chargeable_value' is the subtotal (before tax) and 'grand_total_amount' is the final payable value (including tax).\n"
    "3. Indian Tax Identifiers:\n"
    "   - Extract 15-character GSTINs (e.g., 07AAAAA1111A1Z1).\n"
    "   - If a GSTIN is found, extract the 10-character PAN from it (chars 3 to 12) and map it as needed.\n"
    "4. Date Formats:\n"
    "   - Normalize all extracted dates to YYYY-MM-DD format.\n\n"
    "### OUTPUT FORMAT:\n"
    "Return ONLY valid JSON. Do not include markdown code block formatting (like ```json), commentary, or extra text. If a field is missing or cannot be found, set its value to null.\n\n"
    "### SCHEMA:\n"
    "{\n"
    "  \"extraction_date\": \"YYYY-MM-DD\",\n"
    "  \"source_document_type\": \"Invoice|Salary Slip|Payment Receipt|Bank Statement|Unknown\",\n"
    "  \"metadata\": {\n"
    "    \"invoice_number\": null,\n"
    "    \"reference_no\": null,\n"
    "    \"billable_period\": null,\n"
    "    \"date_issued\": null\n"
    "  },\n"
    "  \"invoice_details\": {\n"
    "    \"seller_name\": null,\n"
    "    \"seller_gstin\": null,\n"
    "    \"buyer_name\": null,\n"
    "    \"buyer_gstin\": null,\n"
    "    \"total_chargeable_value\": null,\n"
    "    \"grand_total_amount\": null,\n"
    "    \"taxation\": {\n"
    "      \"cgst\": {\n"
    "        \"rate\": null,\n"
    "        \"amount\": null\n"
    "      },\n"
    "      \"sgst_or_utgst\": {\n"
    "        \"rate\": null,\n"
    "        \"amount\": null\n"
    "      },\n"
    "      \"other_taxes\": {}\n"
    "    }\n"
    "  },\n"
    "  \"payroll_data\": {\n"
    "    \"period_start_date\": null,\n"
    "    \"period_end_date\": null,\n"
    "    \"employee_name\": null,\n"
    "    \"designation\": null,\n"
    "    \"earnings\": {\n"
    "      \"gross_salary\": null,\n"
    "      \"basic_salary\": null,\n"
    "      \"hra\": null,\n"
    "      \"other_earnings\": []\n"
    "    },\n"
    "    \"deductions\": {\n"
    "      \"pf_employee\": null,\n"
    "      \"vpf_employee\": null,\n"
    "      \"tax_tds\": null,\n"
    "      \"gst_deduction\": null,\n"
    "      \"other_deductions\": []\n"
    "    },\n"
    "    \"net_pay\": {\n"
    "      \"final_salary_after_deductions\": null\n"
    "    }\n"
    "  }\n"
    "}"
)


@dataclass
class ExtractionResult:
    document_type: str
    name: str | None
    pan: str | None
    payer: str | None
    record_date: str | None
    gross_amount: float
    net_amount: float
    tds_amount: float
    deductions_amount: float
    pf_amount: float
    vpf_amount: float
    gst_amount: float
    confidence: float
    warnings: list[str]
    extracted_text: str

    def to_dict(self) -> dict:
        return asdict(self)


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_text_from_pdf(path: Path, ai_provider: str = "local") -> tuple[str, list[str]]:
    warnings: list[str] = []

    text, text_warnings = extract_embedded_pdf_text(path)
    warnings.extend(text_warnings)
    if text:
        return text, warnings

    warnings.append("No embedded PDF text found. Trying local AI PDF analysis.")
    ai_text, ai_warnings = extract_text_with_local_ai(path, ai_provider)
    warnings.extend(ai_warnings)
    if ai_text:
        return ai_text, warnings

    try:
        import fitz
        from PIL import Image
        import io
        import pytesseract

        ocr_lines = []
        with fitz.open(path) as doc:
            for page in doc:
                pix = page.get_pixmap(dpi=220)
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                ocr_lines.append(pytesseract.image_to_string(img))
        ocr_text = "\n".join(ocr_lines).strip()
        if ocr_text:
            warnings.append("Text was extracted using OCR fallback.")
            return ocr_text, warnings
        warnings.append("OCR ran, but no readable text was found.")
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            "OCR fallback is available but could not run. Install Tesseract, "
            f"then retry scanned PDFs. Details: {exc}"
        )
    return "", warnings


def extract_embedded_pdf_text(path: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if text:
            return text, warnings
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"PDF text extraction failed: {exc}")
    try:
        import fitz

        with fitz.open(path) as document:
            text = "\n".join(page.get_text("text") or "" for page in document).strip()
        if text:
            warnings.append("Text was extracted using PyMuPDF fallback.")
            return text, warnings
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"PyMuPDF text extraction failed: {exc}")
    return "", warnings


def extract_text_with_local_ai(path: Path, ai_provider: str = "local") -> tuple[str, list[str]]:
    warnings: list[str] = []
    api_urls = LOCAL_AI_BASE_URLS
    api_key = LOCAL_AI_API_KEY
    model_name = LOCAL_AI_MODEL

    if not api_urls:
        return "", ["Local AI analysis is disabled because LOCAL_AI_BASE_URL is empty."]

    image_urls = render_pdf_pages_for_ai(path, warnings)
    if not image_urls:
        return "", warnings

    prompt = (
        "Read this Indian payslip or invoice PDF image and extract all useful financial details. "
        "Return only compact JSON with these keys: document_type, name, pan, payer, record_date, "
        "gross_amount, net_amount, tds_amount, deductions_amount, pf_amount, vpf_amount, notes. "
        "Use document_type salary, freelance_invoice, or unknown. Use ISO date when possible. "
        "Use numeric amounts only, with no currency symbols."
    )
    content = [{"type": "text", "text": prompt}]
    content.extend({"type": "image_url", "image_url": {"url": image_url}} for image_url in image_urls)
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": content}],
        "temperature": 1.0 if "gemma-4" in model_name else 0,
        "max_tokens": 8192 if "gemma-4" in model_name else 900,
    }
    
    if "gemma-4" in model_name:
        payload["top_p"] = 0.95
        payload["chat_template_kwargs"] = {"enable_thinking": True}

    for base_url in api_urls:
        try:
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            
            request = urllib.request.Request(
                f"{base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=LOCAL_AI_TIMEOUT_SECONDS) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                
            message = res_data["choices"][0]["message"]["content"]
            data = parse_ai_json(message)
            if data:
                warnings.append(f"Local AI analysis used model {model_name}.")
                return ai_data_to_text(data), warnings
            warnings.append("AI returned a response, but no JSON could be parsed.")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Local AI analysis failed at {base_url}: {exc}")
    return "", warnings


def extract_structured_data_with_ai(path: Path, embedded_text: str = "", ai_provider: str = "local") -> tuple[dict, list[str]]:
    warnings: list[str] = []
    api_urls = LOCAL_AI_BASE_URLS
    api_key = LOCAL_AI_API_KEY
    model_name = LOCAL_AI_MODEL

    if not api_urls:
        return {}, ["Local AI analysis is disabled because LOCAL_AI_BASE_URL is empty."]

    image_urls = [] if embedded_text else render_pdf_pages_for_ai(path, warnings)
    if not embedded_text and not image_urls:
        return {}, warnings

    prompt = LOCAL_AI_EXTRACTION_PROMPT
    if embedded_text:
        prompt += "\n\nPDF text extracted without OCR. Parse this document text:\n" + embedded_text[:12000]
    content = [{"type": "text", "text": prompt}]
    content.extend({"type": "image_url", "image_url": {"url": image_url}} for image_url in image_urls)
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": content}],
        "temperature": 1.0 if "gemma-4" in model_name else 0,
        "max_tokens": 8192 if "gemma-4" in model_name else 1800,
    }
    
    if "gemma-4" in model_name:
        payload["top_p"] = 0.95
        payload["chat_template_kwargs"] = {"enable_thinking": True}

    for base_url in api_urls:
        try:
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            
            request = urllib.request.Request(
                f"{base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=LOCAL_AI_TIMEOUT_SECONDS) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                
            message = res_data["choices"][0]["message"]["content"]
            data = parse_ai_json(message)
            if data:
                warnings.append(f"Local AI analysis used model {model_name}.")
                return data, warnings
            warnings.append("AI returned a response, but no JSON could be parsed.")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Local AI analysis failed at {base_url}: {exc}")
    return {}, warnings


def render_pdf_pages_for_ai(path: Path, warnings: list[str]) -> list[str]:
    try:
        import io
        import fitz

        image_urls = []
        with fitz.open(path) as doc:
            num_pages = min(len(doc), LOCAL_AI_RENDERED_PAGES)
            for i in range(num_pages):
                page = doc.load_page(i)
                pix = page.get_pixmap(dpi=170)
                png_data = pix.tobytes("png")
                encoded = base64.b64encode(png_data).decode("ascii")
                image_urls.append(f"data:image/png;base64,{encoded}")
        return image_urls
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Could not render PDF pages for local AI analysis: {exc}")
        return []


def post_local_ai_json(url: str, payload: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    if LOCAL_AI_API_KEY:
        headers["Authorization"] = f"Bearer {LOCAL_AI_API_KEY}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=LOCAL_AI_TIMEOUT_SECONDS) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:300]}") from exc


def parse_ai_json(content: str) -> dict:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}


def ai_data_to_text(data: dict) -> str:
    document_type = str(data.get("document_type") or "unknown").lower()
    heading = "salary payslip" if document_type == "salary" else "freelance consulting invoice"
    lines = [f"Local AI extracted {heading} financial document fields:"]
    labels = {
        "name": "Employee Name",
        "pan": "PAN",
        "payer": "Client" if document_type == "freelance_invoice" else "Employer",
        "record_date": "Date",
        "gross_amount": "Gross Amount",
        "net_amount": "Net Pay",
        "tds_amount": "TDS",
        "deductions_amount": "Total Deductions",
        "pf_amount": "PF Contribution",
        "vpf_amount": "VPF Contribution",
        "notes": "Notes",
    }
    for key, label in labels.items():
        value = data.get(key)
        if value not in (None, ""):
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def coerce_float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        match = AMOUNT_RE.search(value.replace("₹", ""))
        return parse_amount(match.group(0)) if match else 0.0
    return 0.0


def find_ai_value(data: object, aliases: set[str]) -> object:
    if isinstance(data, dict):
        normalized = {str(key).lower().replace(" ", "_").replace("-", "_"): value for key, value in data.items()}
        for alias in aliases:
            if alias in normalized and normalized[alias] not in (None, ""):
                return normalized[alias]
        for value in data.values():
            found = find_ai_value(value, aliases)
            if found not in (None, ""):
                return found
    if isinstance(data, list):
        for item in data:
            found = find_ai_value(item, aliases)
            if found not in (None, ""):
                return found
    return None


def compact_ai_data(data: dict) -> dict:
    invoice = data.get("invoice_details") if isinstance(data.get("invoice_details"), dict) else {}
    payroll = data.get("payroll_data") if isinstance(data.get("payroll_data"), dict) else {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    earnings = payroll.get("earnings") if isinstance(payroll.get("earnings"), dict) else {}
    deductions = payroll.get("deductions") if isinstance(payroll.get("deductions"), dict) else {}
    net_pay = payroll.get("net_pay") if isinstance(payroll.get("net_pay"), dict) else {}
    return {
        "document_type": data.get("document_type") or data.get("source_document_type") or data.get("type") or find_ai_value(data, {"document_type", "source_document_type", "type"}),
        "name": data.get("name") or data.get("employee_name") or payroll.get("employee_name") or invoice.get("seller_name") or find_ai_value(data, {"employee_name", "name", "seller_name", "consultant_name"}),
        "pan": data.get("pan") or data.get("pan_number") or gstin_to_pan(invoice.get("seller_gstin")) or gstin_to_pan(invoice.get("buyer_gstin")) or find_ai_value(data, {"pan", "pan_number"}),
        "payer": data.get("payer") or data.get("employer") or data.get("company") or data.get("company_name") or invoice.get("buyer_name") or invoice.get("seller_name") or find_ai_value(data, {"payer", "employer", "company", "company_name", "buyer_name", "client"}),
        "record_date": data.get("record_date") or data.get("pay_date") or data.get("payment_date") or data.get("invoice_date") or metadata.get("date_issued") or find_ai_value(data, {"record_date", "pay_date", "payment_date", "invoice_date", "date_issued", "period_end_date"}),
        "gross_amount": data.get("gross_amount") or data.get("gross_salary") or data.get("gross_pay") or data.get("gross_earnings") or data.get("total_gross") or earnings.get("gross_salary") or invoice.get("total_chargeable_value") or find_ai_value(data, {"gross_amount", "gross_salary", "gross_pay", "gross_earnings", "total_gross", "total_earnings"}),
        "net_amount": data.get("net_amount") or data.get("net_pay") or data.get("net_salary") or data.get("net_payable") or data.get("total_net_pay") or net_pay.get("final_salary_after_deductions") or invoice.get("grand_total_amount") or find_ai_value(data, {"net_amount", "net_pay", "net_salary", "net_payable", "total_net_pay", "final_salary_after_deductions"}),
        "tds_amount": data.get("tds_amount") or data.get("income_tax") or data.get("tds") or data.get("tax_deducted") or deductions.get("tax_tds") or find_ai_value(data, {"tds_amount", "tax_tds", "income_tax", "tds", "tax_deducted"}),
        "deductions_amount": data.get("deductions_amount") or data.get("less_deductions") or deductions.get("other_deductions") or find_ai_value(data, {"deductions_amount", "other_deductions", "less_deductions"}),
        "pf_amount": data.get("pf_amount") or data.get("employee_pf") or data.get("epf") or data.get("epf_contribution") or deductions.get("pf_employee") or find_ai_value(data, {"pf_amount", "pf_employee", "employee_pf", "epf", "epf_contribution"}),
        "vpf_amount": data.get("vpf_amount") or data.get("employee_vpf") or data.get("vpf") or deductions.get("vpf_employee") or find_ai_value(data, {"vpf_amount", "vpf_employee", "employee_vpf", "vpf"}),
        "gst_amount": data.get("gst_amount") or data.get("gst") or data.get("tax_amount") or deductions.get("gst_deduction") or find_ai_value(data, {"gst_amount", "gst", "cgst_sgst", "tax_amount"}),
    }


def sum_money_values(value: object) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, list):
        return sum(sum_money_values(item) for item in value)
    if isinstance(value, dict):
        if "amount" in value:
            return coerce_float(value.get("amount"))
        return sum(sum_money_values(item) for item in value.values())
    return coerce_float(value)


def first_text(*values: object) -> str | None:
    for value in values:
        if value not in (None, ""):
            return str(value).strip()[:120]
    return None


def gstin_to_pan(value: object) -> str | None:
    text = str(value or "").upper()
    match = re.search(r"\b\d{2}([A-Z]{5}[0-9]{4}[A-Z])[0-9A-Z]{3}\b", text)
    return match.group(1) if match else None


def normalize_ai_document_type(value: object) -> str:
    text = str(value or "").lower()
    if "salary" in text or "payroll" in text or "pay slip" in text or "payslip" in text:
        return "salary"
    if "receipt" in text or "expense" in text or "purchase" in text:
        return "purchase_expense"
    if "invoice" in text or "payment" in text:
        return "freelance_invoice"
    return "unknown"


def extraction_result_from_ai_data(data: dict, warnings: list[str], source_text: str = "") -> ExtractionResult:
    compact = compact_ai_data(data)
    invoice = data.get("invoice_details") if isinstance(data.get("invoice_details"), dict) else {}
    payroll = data.get("payroll_data") if isinstance(data.get("payroll_data"), dict) else {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    earnings = payroll.get("earnings") if isinstance(payroll.get("earnings"), dict) else {}
    deductions = payroll.get("deductions") if isinstance(payroll.get("deductions"), dict) else {}
    net_pay = payroll.get("net_pay") if isinstance(payroll.get("net_pay"), dict) else {}

    document_type = normalize_ai_document_type(compact.get("document_type"))
    invoice_gross = coerce_float(compact.get("gross_amount")) or coerce_float(invoice.get("total_chargeable_value"))
    invoice_net = coerce_float(compact.get("net_amount")) or coerce_float(invoice.get("grand_total_amount"))
    salary_gross = coerce_float(compact.get("gross_amount")) or coerce_float(earnings.get("gross_salary"))
    salary_net = coerce_float(compact.get("net_amount")) or coerce_float(net_pay.get("final_salary_after_deductions"))
    pf_amount = coerce_float(compact.get("pf_amount")) or coerce_float(deductions.get("pf_employee"))
    vpf_amount = coerce_float(compact.get("vpf_amount")) or coerce_float(deductions.get("vpf_employee"))
    tds_amount = coerce_float(compact.get("tds_amount")) or coerce_float(deductions.get("tax_tds"))
    deductions_amount = sum_money_values(compact.get("deductions_amount")) or sum_money_values(deductions.get("other_deductions"))

    if document_type == "unknown":
        document_type = "salary" if salary_gross or salary_net else "freelance_invoice" if invoice_gross or invoice_net else "unknown"

    if document_type == "salary":
        gross_amount = salary_gross
        net_amount = salary_net or gross_amount
        name = first_text(compact.get("name"), payroll.get("employee_name"))
        payer = first_text(compact.get("payer"), invoice.get("seller_name"), invoice.get("buyer_name")) or find_salary_employer(source_text)
        record_date = normalize_date(first_text(compact.get("record_date"), payroll.get("period_end_date"), payroll.get("period_start_date"), metadata.get("date_issued"), metadata.get("billable_period"), data.get("extraction_date"))) or normalize_date(find_date(source_text))
        if source_text:
            gross_amount = gross_amount or find_amount(source_text, "gross_amount")
            net_amount = net_amount or find_amount(source_text, "net_amount") or gross_amount
            tds_amount = tds_amount or find_amount(source_text, "tds_amount")
            pf_amount = pf_amount or find_amount(source_text, "pf_amount")
            vpf_amount = vpf_amount or find_amount(source_text, "vpf_amount")
            total_deductions = find_amount(source_text, "deductions_amount")
            if not deductions_amount and total_deductions:
                lowered_text = source_text.lower()
                if "less: dedns" in lowered_text or "less dedns" in lowered_text:
                    deductions_amount = round(max(0.0, total_deductions - pf_amount - vpf_amount), 2)
                else:
                    deductions_amount = round(max(0.0, total_deductions - pf_amount - vpf_amount - tds_amount), 2)
    elif document_type == "purchase_expense":
        gross_amount = invoice_gross or invoice_net
        net_amount = invoice_net or gross_amount
        name = first_text(compact.get("name"), invoice.get("seller_name"))
        payer = first_text(compact.get("payer"), invoice.get("buyer_name"))
        record_date = normalize_date(first_text(compact.get("record_date"), metadata.get("date_issued"), metadata.get("billable_period"), data.get("extraction_date")))
    else:
        gross_amount = invoice_gross or invoice_net
        net_amount = invoice_net or gross_amount
        name = first_text(compact.get("name"), invoice.get("seller_name"))
        payer = first_text(compact.get("payer"), invoice.get("buyer_name"))
        record_date = normalize_date(first_text(compact.get("record_date"), metadata.get("date_issued"), metadata.get("billable_period"), data.get("extraction_date")))

    gst_deduction = coerce_float(compact.get("gst_amount")) or coerce_float(deductions.get("gst_deduction"))
    taxation = invoice.get("taxation") if isinstance(invoice.get("taxation"), dict) else {}
    cgst = taxation.get("cgst") if isinstance(taxation.get("cgst"), dict) else {}
    sgst = taxation.get("sgst_or_utgst") if isinstance(taxation.get("sgst_or_utgst"), dict) else {}
    gst_amount = gst_deduction or coerce_float(cgst.get("amount")) + coerce_float(sgst.get("amount"))
    if document_type in ("freelance_invoice", "purchase_expense") and gst_amount == 0 and net_amount > gross_amount:
        gst_amount = round(net_amount - gross_amount, 2)
    if document_type == "freelance_invoice" and tds_amount == 0 and gross_amount > 0:
        tds_amount = round(gross_amount * 0.10, 2)
    pan = first_text(compact.get("pan")) or gstin_to_pan(invoice.get("seller_gstin")) or gstin_to_pan(invoice.get("buyer_gstin")) or find_pan(source_text)

    confidence = 0.55
    confidence += 0.15 if document_type != "unknown" else 0
    confidence += 0.15 if gross_amount > 0 else 0
    confidence += 0.1 if net_amount > 0 else 0
    confidence += 0.05 if record_date else 0
    confidence = min(confidence, 0.95)

    if gross_amount == 0:
        warnings.append("Gross amount could not be extracted from the AI response.")
    if document_type == "unknown":
        warnings.append("AI could not identify the document type confidently.")

    # Classify category and construct final JSON
    if document_type == "purchase_expense":
        data["category"] = classify_expense_category(source_text)
        data["notes"] = f"Vendor: {name or 'Unknown'}"

    extracted_text = json.dumps(data, ensure_ascii=True, indent=2)
    return ExtractionResult(
        document_type=document_type,
        name=name,
        pan=pan,
        payer=payer,
        record_date=record_date,
        gross_amount=gross_amount,
        net_amount=net_amount,
        tds_amount=tds_amount,
        deductions_amount=deductions_amount,
        pf_amount=pf_amount,
        vpf_amount=vpf_amount,
        gst_amount=gst_amount,
        confidence=round(confidence, 2),
        warnings=warnings,
        extracted_text=extracted_text[:20000],
    )


def classify_document(text: str) -> str:
    lowered = text.lower()
    salary_score = sum(token in lowered for token in ["salary", "payslip", "pay slip", "employee", "gross pay", "net pay", "provident fund", "pf contribution"])
    invoice_score = sum(token in lowered for token in ["invoice", "bill to", "buyer", "client", "amount due", "freelance", "consulting", "professional charges"])
    expense_score = sum(token in lowered for token in ["receipt", "payment receipt", "cash memo", "expense", "vendor", "sold by", "gstin", "igst", "cgst"])
    if salary_score >= 2 and salary_score >= invoice_score and salary_score >= expense_score:
        return "salary"
    if invoice_score >= 2 and any(token in lowered for token in ["bill to", "buyer", "client", "professional charges", "consulting"]):
        return "freelance_invoice"
    if expense_score >= 2 and expense_score >= invoice_score:
        return "purchase_expense"
    if invoice_score >= 2:
        return "freelance_invoice"
    return "unknown"


def parse_amount(value: str | None) -> float:
    if not value:
        return 0.0
    return float(value.replace(",", ""))


def extract_amounts_from_line(line: str) -> list[float]:
    return [parse_amount(match.group(0)) for match in AMOUNT_RE.finditer(line)]


def extract_currency_amounts_from_line(line: str) -> list[float]:
    matches = CURRENCY_AMOUNT_RE.findall(line)
    return [parse_amount(match) for match in matches]


def amounts_near_label(lines: list[str], index: int) -> list[float]:
    amounts: list[float] = []
    for nearby in lines[index:index + 3]:
        amounts.extend(extract_amounts_from_line(nearby))
        if amounts:
            break
    return amounts


def find_amount(text: str, key: str) -> float:
    # Handle GST sum logic
    if key == "gst_amount":
        total_gst = 0.0
        cgst_val = 0.0
        sgst_val = 0.0
        igst_val = 0.0
        for line in text.splitlines():
            normalized = line.lower()
            amounts = extract_amounts_from_line(line)
            if not amounts:
                continue
            if "cgst" in normalized:
                cgst_val = max(amounts)
            elif "sgst" in normalized:
                sgst_val = max(amounts)
            elif "igst" in normalized:
                igst_val = max(amounts)
            elif "gst" in normalized or "tax" in normalized:
                if not total_gst:
                    total_gst = max(amounts)
        extracted_gst = cgst_val + sgst_val + igst_val
        if extracted_gst > 0:
            return round(extracted_gst, 2)
        if total_gst > 0:
            return round(total_gst, 2)

    labels_by_key = {
        "gross_amount": ["gross pay", "gross salary", "gross earnings", "gross earning", "total gross", "total earnings", "total earning", "subtotal", "sub total", "taxable value", "chargeable value", "professional charges", "professional fees", "basic amount"],
        "net_amount": ["total net pay", "a.net salary", "net salary", "net pay", "net payable", "grand total", "total amount paid", "amount paid", "total amount", "net amount", "total payable", "payable amount", "amount payable"],
        "tds_amount": ["tds", "income tax", "tax deducted", "tax deduction"],
        "deductions_amount": ["total deductions", "total deduction", "deductions total", "less: dedns", "less dedns"],
        "pf_amount": ["ee pf contribution", "ee pf contribut", "employee pf contribution", "provident fund", "pf contribution"],
        "vpf_amount": ["ee vpf contribution", "ee vpf contribu", "employee vpf contribution", "voluntary provident fund", "vpf contribution"],
        "invoice_amount": ["invoice amount", "grand total", "total amount", "amount due", "amount payable", "total payable", "total amount paid"],
        "gst_amount": ["gst", "cgst", "sgst", "igst", "tax amount", "tax total", "gst amount", "service tax"],
    }
    lines = text.splitlines()
    if key == "net_amount":
        for index, line in enumerate(lines):
            normalized = re.sub(r"\s+", " ", line.lower())
            if "gross earnings" in normalized and "total deductions" in normalized and "-" in normalized:
                amounts = extract_amounts_from_line(line)
                if amounts:
                    return amounts[-1]
            if "total net pay" in normalized and not extract_amounts_from_line(line) and index > 0:
                previous_amounts = extract_amounts_from_line(lines[index - 1])
                if len(previous_amounts) == 1:
                    return previous_amounts[0]

    if key == "deductions_amount":
        for line in lines:
            normalized = re.sub(r"\s+", " ", line.lower())
            if "total deductions" in normalized or "less: dedns" in normalized or "less dedns" in normalized:
                amounts = extract_amounts_from_line(line)
                if amounts:
                    return amounts[-1]

    for index, line in enumerate(lines):
        normalized = re.sub(r"\s+", " ", line.lower())
        if key == "pf_amount" and "vpf" in normalized:
            continue
        if key == "gross_amount" and "professional charges" in normalized:
            amounts = extract_currency_amounts_from_line(line)
            if amounts:
                return amounts[0]
        if key == "invoice_amount" and normalized.strip().startswith("total "):
            amounts = extract_currency_amounts_from_line(line)
            if len(amounts) == 1:
                return amounts[0]
        if any(label in normalized for label in labels_by_key.get(key, [])):
            amounts = amounts_near_label(lines, index)
            if amounts:
                if key == "gross_amount" and any(e in normalized for e in ["earning", "salary", "pay"]) and "deduction" in normalized:
                    return amounts[0]
                if key == "deductions_amount" and any(e in normalized for e in ["earning", "salary", "pay"]) and "deduction" in normalized:
                    return amounts[-1]
                return amounts[-1]

    for pattern in AMOUNT_PATTERNS.get(key, []):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return parse_amount(match.group(1))
    return 0.0


def find_pan(text: str) -> str | None:
    match = re.search(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", text.upper())
    return match.group(0) if match else None


def find_date(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines()]
    label_patterns = [
        r"\b(?:pay\s+date|payment\s+date|invoice\s+date|date\s+issued|issue\s+date|bill\s+date)\s*[:\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        r"\b(?:pay\s+date|payment\s+date|invoice\s+date|date\s+issued|issue\s+date|bill\s+date)\s*[:\-]?\s*(\d{1,2}[-/](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-/]\d{2,4})",
        r"\b(?:pay\s+date|payment\s+date|invoice\s+date|date\s+issued|issue\s+date|bill\s+date)\s*[:\-]?\s*(\d{4}-\d{2}-\d{2})",
    ]
    for pattern in label_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    for index, line in enumerate(lines[:-1]):
        if line.lower() == "dated":
            next_line = lines[index + 1]
            if re.search(r"\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}", next_line):
                return next_line
    patterns = [
        r"pay\s+period\s*[:\-]?\s*((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
        r"\b(\d{4}-\d{2}-\d{2})\b",
        r"\b(\d{2}[/-]\d{2}[/-]\d{4})\b",
        r"\b(\d{1,2}[-/](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-/]\d{2,4})\b",
        r"\b(\d{2}\.\d{2}\.\d{4})\b",
        r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%b-%y", "%d-%B-%y", "%d-%b-%Y", "%d-%B-%Y", "%b %Y", "%B %Y"):
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt in ("%b %Y", "%B %Y"):
                parsed = parsed.replace(day=1)
            return parsed.date().isoformat()
        except ValueError:
            continue
    return value


def find_named_value(text: str, labels: list[str]) -> str | None:
    for label in labels:
        pattern = rf"{label}\s*[:\-]?\s*([A-Za-z][A-Za-z .&]+?)(?:\s{{2,}}|[|]|\n|$)"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()[:120]
    return None


def next_meaningful_line(lines: list[str], start_index: int) -> str | None:
    for line in lines[start_index:]:
        cleaned = line.strip(" |")
        if cleaned and cleaned.strip("-"):
            return cleaned[:120]
    return None


def find_salary_employer(text: str) -> str | None:
    lines = [line.strip(" |") for line in text.splitlines() if line.strip(" |:")]
    skip_tokens = [
        "payslip",
        "pay slip",
        "employee",
        "salary",
        "period",
        "pan",
        "uan",
        "global id",
        "confidential",
    ]
    for line in lines[:25]:
        cleaned = re.sub(r"\s+", " ", line).strip()
        if not cleaned or len(cleaned) < 3:
            continue
        lowered = cleaned.lower()
        if any(token in lowered for token in skip_tokens):
            continue
        if "contribution" in lowered or "benefit" in lowered:
            continue
        if any(token in lowered for token in ["pvt", "private", "limited", "solutions", "software", "edge", "technologies"]):
            return cleaned[:120]
        if cleaned.isupper() and len(cleaned.split()) >= 2:
            return cleaned.title()[:120]
    return None


def find_invoice_seller(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines[:-1]):
        if "tax invoice" in line.lower():
            return next_meaningful_line(lines, index + 1)
        if line.lower() == "invoice":
            return next_meaningful_line(lines, index + 1)
    return None


def find_invoice_buyer(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines[:-1]):
        lowered = line.lower()
        if "buyer" in lowered and "bill to" in lowered:
            return next_meaningful_line(lines, index + 1)
        if "bill to" in lowered:
            return next_meaningful_line(lines, index + 1)
        if lowered == "buyer":
            return next_meaningful_line(lines, index + 1)
    return None


def find_payer(text: str) -> str | None:
    if classify_document(text) == "salary":
        employer = find_salary_employer(text)
        if employer:
            return employer
    invoice_buyer = find_invoice_buyer(text)
    if invoice_buyer:
        return invoice_buyer
    named = find_named_value(text, ["employer", "company", "client", "bill to"])
    if named:
        return named
    for line in text.splitlines():
        cleaned = line.strip(" |")
        if not cleaned or set(cleaned) <= {"-"}:
            continue
        lowered = cleaned.lower()
        if any(token in lowered for token in ["pvt ltd", "private limited", "solutions", "technologies", "software"]):
            return cleaned[:120]
        if "payslip" not in lowered and len(cleaned.split()) >= 3:
            return cleaned[:120]
    return None


def classify_expense_category(text: str) -> str:
    lowered = text.lower()
    keywords = {
        "Travel": [r"\bcab\b", r"\btaxi\b", r"\buber\b", r"\bola\b", r"\bflight\b", r"\bindigo\b", r"\bair\b", r"\brailway\b", r"\birctc\b", r"\bhotel\b", r"\bstay\b", r"\btravel\b", r"\bconvoy\b", r"\bpetrol\b", r"\bfuel\b"],
        "Software": [r"\baws\b", r"\bazure\b", r"\bgithub\b", r"\bjetbrains\b", r"\bzoom\b", r"\bgoogle cloud\b", r"\bopenai\b", r"\bdigitalocean\b", r"\bsubscription\b", r"\bsoftware\b", r"\bsaas\b", r"\bcloud\b", r"\bslack\b", r"\bfigma\b", r"\bdomain\b", r"\bhosting\b"],
        "Hardware": [r"\bapple\b", r"\bdell\b", r"\bhp\b", r"\blenovo\b", r"\blaptop\b", r"\bkeyboard\b", r"\bmonitor\b", r"\bmouse\b", r"\bhardware\b", r"\bcroma\b", r"\breliance digital\b", r"\bcharger\b", r"\bssd\b", r"\bram\b"],
        "Utilities": [r"\belectricity\b", r"\bbescom\b", r"\bpower\b", r"\bbroadband\b", r"\bairtel\b", r"\bjio\b", r"\binternet\b", r"\bwater\b", r"\bgas\b", r"\brecharge\b", r"\bphone bill\b"],
        "Office Supplies": [r"\bstationery\b", r"\bpaper\b", r"\bprinter\b", r"\bpen\b", r"\bsupplies\b", r"\bstapler\b", r"\bdesk\b", r"\bchair\b", r"\boffice supplies\b"],
        "Professional Fees": [r"\blegal\b", r"\bconsulting\b", r"\baudit\b", r"\baccounting\b", r"\badvisory\b", r"\bfees\b", r"\blawyer\b", r"\bca fee\b"],
        "Rent": [r"\brent\b", r"\blandlord\b", r"\bdeposit\b", r"\boffice rent\b", r"\bco-working\b", r"\bwework\b"],
        "Meals": [r"\bzomato\b", r"\bswiggy\b", r"\brestaurant\b", r"\bhotel food\b", r"\bmeals\b", r"\bcafe\b", r"\bstarbucks\b", r"\blunch\b", r"\bdinner\b", r"\bbreakfast\b", r"\bfood\b", r"\bcatering\b"],
    }
    for category, patterns in keywords.items():
        for pattern in patterns:
            if re.search(pattern, lowered):
                return category
    return "Others"


def run_local_parser(text: str) -> dict:
    doc_type = classify_document(text)
    invoice_amount = find_amount(text, "invoice_amount")
    gross = find_amount(text, "gross_amount") or invoice_amount
    net = find_amount(text, "net_amount") or (invoice_amount if doc_type == "freelance_invoice" else gross)
    tds = find_amount(text, "tds_amount")
    total_deductions_amount = find_amount(text, "deductions_amount")
    vpf = find_amount(text, "vpf_amount")
    pf = find_amount(text, "pf_amount")
    
    deductions = total_deductions_amount
    if doc_type == "salary" and total_deductions_amount > 0:
        lowered_text = text.lower()
        if "less: dedns" in lowered_text or "less dedns" in lowered_text:
            deductions = round(max(0.0, total_deductions_amount - pf - vpf), 2)
        else:
            deductions = round(max(0.0, total_deductions_amount - pf - vpf - tds), 2)
        
    gst = find_amount(text, "gst_amount")
    if doc_type == "salary":
        gst = 0.0
    parsed_net = net
    if doc_type in ("freelance_invoice", "purchase_expense") and gst == 0 and net > gross:
        gst = round(net - gross, 2)
        
    if doc_type == "freelance_invoice" and tds == 0 and gross > 0:
        tds = round(gross * 0.10, 2)
    if doc_type == "freelance_invoice" and gross > 0:
        net = round(gross - tds, 2)
        
    pan = find_pan(text) or gstin_to_pan(text)
    name = find_named_value(text, ["employee name", "name", "consultant", "freelancer", "vendor", "seller"]) or find_invoice_seller(text)
    payer = find_payer(text)
    record_date = normalize_date(find_date(text))
    
    return {
        "document_type": doc_type,
        "name": name,
        "pan": pan,
        "payer": payer,
        "record_date": record_date,
        "gross_amount": gross,
        "net_amount": net,
        "parsed_net_amount": parsed_net,
        "tds_amount": tds,
        "deductions_amount": deductions,
        "pf_amount": pf,
        "vpf_amount": vpf,
        "gst_amount": gst,
    }


def validate_local_extraction(data: dict) -> bool:
    doc_type = data.get("document_type")
    if doc_type not in ("salary", "freelance_invoice", "purchase_expense"):
        return False
        
    gross = data.get("gross_amount", 0.0)
    net = data.get("net_amount", 0.0)
    if gross <= 0 or net <= 0:
        return False
        
    if not data.get("record_date"):
        return False
        
    if doc_type == "salary":
        pf = data.get("pf_amount", 0.0)
        vpf = data.get("vpf_amount", 0.0)
        tds = data.get("tds_amount", 0.0)
        deds = data.get("deductions_amount", 0.0)
        expected_net = gross - (pf + vpf + tds + deds)
        return abs(expected_net - net) <= 10.0
        
    if doc_type == "freelance_invoice":
        tds = data.get("tds_amount", 0.0)
        gst = data.get("gst_amount", 0.0)
        physical_net = data.get("parsed_net_amount", net)
        return (
            abs((gross - tds) - physical_net) <= 10.0 or
            abs((gross + gst - tds) - physical_net) <= 10.0 or
            abs((gross + gst) - physical_net) <= 10.0
        )
        
    if doc_type == "purchase_expense":
        gst = data.get("gst_amount", 0.0)
        expected_net = gross + gst
        return abs(expected_net - net) <= 10.0
        
    return False


def extract_financial_fields(path: Path, ai_provider: str = "local") -> ExtractionResult:
    warnings: list[str] = []
    
    # 1. Try to extract text using local PyPDF first
    embedded_text, embedded_warnings = extract_embedded_pdf_text(path)
    warnings.extend(embedded_warnings)
    
    # 2. If no embedded text found, run PyMuPDF/Pillow local OCR fallback
    if not embedded_text:
        try:
            import fitz
            from PIL import Image
            import io
            import pytesseract
            
            ocr_lines = []
            with fitz.open(path) as doc:
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
            
    # 3. Run Local Rule-Based Python parser on the text
    local_data = {}
    local_success = False
    
    if embedded_text:
        local_data = run_local_parser(embedded_text)
        local_success = validate_local_extraction(local_data)
        
    if local_success:
        warnings.append("Successfully extracted details using Local Python Parser.")
        category = "Others"
        if local_data["document_type"] == "purchase_expense":
            category = classify_expense_category(embedded_text)
            
        extracted_json_dict = {
            "source_document_type": local_data["document_type"],
            "invoice_details": {
                "seller_name": local_data["name"] if local_data["document_type"] in ("freelance_invoice", "purchase_expense") else None,
                "buyer_name": local_data["payer"] if local_data["document_type"] in ("freelance_invoice", "purchase_expense") else None,
                "total_chargeable_value": local_data["gross_amount"],
                "grand_total_amount": local_data["net_amount"],
                "taxation": {
                    "cgst": {"amount": local_data["gst_amount"] / 2.0 if local_data["gst_amount"] > 0 else 0.0},
                    "sgst_or_utgst": {"amount": local_data["gst_amount"] / 2.0 if local_data["gst_amount"] > 0 else 0.0}
                }
            },
            "payroll_data": {
                "employee_name": local_data["name"] if local_data["document_type"] == "salary" else None,
                "earnings": {"gross_salary": local_data["gross_amount"]},
                "deductions": {
                    "pf_employee": local_data["pf_amount"],
                    "vpf_employee": local_data["vpf_amount"],
                    "tax_tds": local_data["tds_amount"],
                    "other_deductions": [{"amount": local_data["deductions_amount"]}] if local_data["deductions_amount"] > 0 else []
                },
                "net_pay": {"final_salary_after_deductions": local_data["net_amount"]}
            },
            "metadata": {
                "date_issued": local_data["record_date"]
            },
            "category": category,
            "notes": local_data["payer"] or ""
        }
        
        return ExtractionResult(
            document_type=local_data["document_type"],
            name=local_data["name"],
            pan=local_data["pan"],
            payer=local_data["payer"],
            record_date=local_data["record_date"],
            gross_amount=local_data["gross_amount"],
            net_amount=local_data["net_amount"],
            tds_amount=local_data["tds_amount"],
            deductions_amount=local_data["deductions_amount"],
            pf_amount=local_data["pf_amount"],
            vpf_amount=local_data["vpf_amount"],
            gst_amount=local_data["gst_amount"],
            confidence=0.95,
            warnings=warnings,
            extracted_text=json.dumps(extracted_json_dict, indent=2)
        )
        
    # 4. Local parser failed/incomplete. Try Local Hosted AI (LM Studio).
    warnings.append("Local parser failed mathematical validation or completeness. Falling back to Local Hosted AI.")

    local_ai_data = {}
    local_ai_warnings = []
    try:
        local_ai_data, local_ai_warnings = extract_structured_data_with_ai(path, embedded_text, "local")
    except Exception as exc:
        warnings.append(f"Local Hosted AI failed: {exc}")
        
    if local_ai_data:
        all_warns = [*warnings, *local_ai_warnings]
        return extraction_result_from_ai_data(local_ai_data, all_warns, embedded_text)
        
    # 6. If all AI models failed, use the best effort local rule-based parsing results
    warnings.append("All AI models failed. Using best-effort Local Parser results.")
    
    category = "Others"
    best_doc_type = "unknown"
    if local_data:
        best_doc_type = local_data.get("document_type", "unknown")
        if best_doc_type == "purchase_expense":
            category = classify_expense_category(embedded_text)
            
    extracted_json_dict = {
        "source_document_type": best_doc_type,
        "invoice_details": {
            "seller_name": local_data.get("name") if local_data and best_doc_type in ("freelance_invoice", "purchase_expense") else None,
            "buyer_name": local_data.get("payer") if local_data and best_doc_type in ("freelance_invoice", "purchase_expense") else None,
            "total_chargeable_value": local_data.get("gross_amount", 0.0) if local_data else 0.0,
            "grand_total_amount": local_data.get("net_amount", 0.0) if local_data else 0.0,
            "taxation": {
                "cgst": {"amount": (local_data.get("gst_amount", 0.0) / 2.0) if local_data and local_data.get("gst_amount", 0.0) > 0 else 0.0},
                "sgst_or_utgst": {"amount": (local_data.get("gst_amount", 0.0) / 2.0) if local_data and local_data.get("gst_amount", 0.0) > 0 else 0.0}
            }
        },
        "payroll_data": {
            "employee_name": local_data.get("name") if local_data and best_doc_type == "salary" else None,
            "earnings": {"gross_salary": local_data.get("gross_amount", 0.0) if local_data else 0.0},
            "deductions": {
                "pf_employee": local_data.get("pf_amount", 0.0) if local_data else 0.0,
                "vpf_employee": local_data.get("vpf_amount", 0.0) if local_data else 0.0,
                "tax_tds": local_data.get("tds_amount", 0.0) if local_data else 0.0,
                "other_deductions": [{"amount": local_data.get("deductions_amount", 0.0)}] if local_data and local_data.get("deductions_amount", 0.0) > 0 else []
            },
            "net_pay": {"final_salary_after_deductions": local_data.get("net_amount", 0.0) if local_data else 0.0}
        },
        "metadata": {
            "date_issued": local_data.get("record_date") if local_data else None
        },
        "category": category,
        "notes": local_data.get("payer", "") if local_data else ""
    }
    
    return ExtractionResult(
        document_type=best_doc_type,
        name=local_data.get("name") if local_data else None,
        pan=local_data.get("pan") if local_data else None,
        payer=local_data.get("payer") if local_data else None,
        record_date=local_data.get("record_date") if local_data else None,
        gross_amount=local_data.get("gross_amount", 0.0) if local_data else 0.0,
        net_amount=local_data.get("net_amount", 0.0) if local_data else 0.0,
        tds_amount=local_data.get("tds_amount", 0.0) if local_data else 0.0,
        deductions_amount=local_data.get("deductions_amount", 0.0) if local_data else 0.0,
        pf_amount=local_data.get("pf_amount", 0.0) if local_data else 0.0,
        vpf_amount=local_data.get("vpf_amount", 0.0) if local_data else 0.0,
        gst_amount=local_data.get("gst_amount", 0.0) if local_data else 0.0,
        confidence=0.25,
        warnings=warnings,
        extracted_text=json.dumps(extracted_json_dict, indent=2)
    )
