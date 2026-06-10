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
    "deductions_amount": [r"(?:total\s+deductions|total\s+deduction|deductions)\D{0,80}([\d,]+(?:\.\d{1,2})?)"],
    "invoice_amount": [r"(?:invoice\s+amount|total\s+amount|amount\s+due)\D{0,80}([\d,]+(?:\.\d{1,2})?)"],
}

AMOUNT_RE = re.compile(r"[\d,]+(?:\.\d{1,2})?")
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
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_OCR_API_URL = os.getenv("NVIDIA_OCR_API_URL", "https://ai.api.nvidia.com/v1/cv/nvidia/nemotron-ocr-v1")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

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


def extract_text_from_pdf(path: Path, ai_provider: str = "nvidia") -> tuple[str, list[str]]:
    warnings: list[str] = []
    
    if ai_provider == "nvidia" and NVIDIA_API_KEY:
        warnings.append("Trying NVIDIA OCR API first.")
        nvidia_text, nvidia_warnings = extract_text_with_nvidia_ocr(path)
        warnings.extend(nvidia_warnings)
        if nvidia_text:
            return nvidia_text, warnings

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
        from pdf2image import convert_from_path
        import pytesseract

        images = convert_from_path(str(path), dpi=220)
        ocr_text = "\n".join(pytesseract.image_to_string(image) for image in images).strip()
        if ocr_text:
            warnings.append("Text was extracted using OCR fallback.")
            return ocr_text, warnings
        warnings.append("OCR ran, but no readable text was found.")
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            "OCR fallback is available but could not run. Install Tesseract and Poppler, "
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
    return "", warnings


def extract_text_with_local_ai(path: Path, ai_provider: str = "nvidia") -> tuple[str, list[str]]:
    warnings: list[str] = []

    # Map variables based on the provider selection
    if ai_provider == "nvidia":
        api_urls = ["https://integrate.api.nvidia.com/v1"]
        api_key = NVIDIA_API_KEY
        model_name = "meta/llama-3.3-70b-instruct"
    elif ai_provider == "google":
        api_urls = ["https://integrate.api.nvidia.com/v1"]
        api_key = GOOGLE_API_KEY
        model_name = "google/gemma-4-31b-it"
    else:  # local AI
        api_urls = LOCAL_AI_BASE_URLS
        api_key = LOCAL_AI_API_KEY
        model_name = LOCAL_AI_MODEL

    if not api_urls:
        return "", [f"AI analysis is disabled because base URL is empty for provider: {ai_provider}."]

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
                is_cloud = "127.0.0.1" not in base_url and "localhost" not in base_url
                provider = "Cloud" if is_cloud else "Local"
                warnings.append(f"{provider} AI analysis used model {model_name}.")
                return ai_data_to_text(data), warnings
            warnings.append("AI returned a response, but no JSON could be parsed.")
        except Exception as exc:  # noqa: BLE001
            is_cloud = "127.0.0.1" not in base_url and "localhost" not in base_url
            provider = "Cloud" if is_cloud else "Local"
            warnings.append(f"{provider} AI analysis failed at {base_url}: {exc}")
    return "", warnings


def extract_text_with_nvidia_ocr(path: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not NVIDIA_API_KEY:
        return "", ["NVIDIA OCR API key is empty."]

    # Render PDF pages to images
    img_bytes_list = []
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        pages_to_ocr = min(len(doc), LOCAL_AI_RENDERED_PAGES)
        for page_idx in range(pages_to_ocr):
            page = doc.load_page(page_idx)
            pix = page.get_pixmap(dpi=150)
            img_bytes_list.append(pix.tobytes("png"))
    except ImportError:
        # Fall back to pdf2image
        try:
            from pdf2image import convert_from_path
            import io
            images = convert_from_path(str(path), dpi=150, first_page=1, last_page=LOCAL_AI_RENDERED_PAGES)
            for img in images:
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format="PNG")
                img_bytes_list.append(img_byte_arr.getvalue())
        except Exception as exc:  # noqa: BLE001
            return "", [f"NVIDIA OCR failed: PyMuPDF import failed and pdf2image fallback could not render. Details: {exc}"]
    except Exception as exc:  # noqa: BLE001
        return "", [f"NVIDIA OCR failed to load PDF pages. Details: {exc}"]

    if not img_bytes_list:
        return "", ["No pages rendered for NVIDIA OCR."]

    all_texts = []
    for img_bytes in img_bytes_list:
        try:
            base64_image = base64.b64encode(img_bytes).decode("ascii")
            payload = {
                "input": [
                    {
                        "type": "image_url",
                        "url": f"data:image/png;base64,{base64_image}"
                    }
                ]
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {NVIDIA_API_KEY}",
                "Accept": "application/json"
            }
            req = urllib.request.Request(
                NVIDIA_OCR_API_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
                for item in result.get("data", []):
                    for detection in item.get("text_detections", []):
                        text = detection.get("text_prediction", {}).get("text", "")
                        if text:
                            all_texts.append(text)
        except urllib.error.HTTPError as he:
            err_msg = he.read().decode("utf-8", errors="replace")
            warnings.append(f"NVIDIA OCR API HTTP Error {he.code}: {err_msg[:200]}")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"NVIDIA OCR API error: {str(e)[:200]}")

    full_text = "\n".join(all_texts)
    if full_text:
        warnings.append("Text was successfully extracted using NVIDIA OCR API.")
        return full_text, warnings
    return "", warnings



def extract_structured_data_with_ai(path: Path, embedded_text: str = "", ai_provider: str = "nvidia") -> tuple[dict, list[str]]:
    warnings: list[str] = []

    # Map variables based on the provider selection
    if ai_provider == "nvidia":
        api_urls = ["https://integrate.api.nvidia.com/v1"]
        api_key = NVIDIA_API_KEY
        model_name = "meta/llama-3.3-70b-instruct"
    elif ai_provider == "google":
        api_urls = ["https://integrate.api.nvidia.com/v1"]
        api_key = GOOGLE_API_KEY
        model_name = "google/gemma-4-31b-it"
    else:  # local AI
        api_urls = LOCAL_AI_BASE_URLS
        api_key = LOCAL_AI_API_KEY
        model_name = LOCAL_AI_MODEL

    if not api_urls:
        return {}, [f"AI analysis is disabled because base URL is empty for provider: {ai_provider}."]

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
                is_cloud = "127.0.0.1" not in base_url and "localhost" not in base_url
                provider = "Cloud" if is_cloud else "Local"
                warnings.append(f"{provider} AI analysis used model {model_name}.")
                return data, warnings
            warnings.append("AI returned a response, but no JSON could be parsed.")
        except Exception as exc:  # noqa: BLE001
            is_cloud = "127.0.0.1" not in base_url and "localhost" not in base_url
            provider = "Cloud" if is_cloud else "Local"
            warnings.append(f"{provider} AI analysis failed at {base_url}: {exc}")
    return {}, warnings


def render_pdf_pages_for_ai(path: Path, warnings: list[str]) -> list[str]:
    try:
        from pdf2image import convert_from_path

        with tempfile.TemporaryDirectory() as temp_dir:
            images = convert_from_path(str(path), dpi=170, first_page=1, last_page=LOCAL_AI_RENDERED_PAGES, fmt="png", output_folder=temp_dir)
            image_urls = []
            for image in images:
                image_path = Path(temp_dir) / f"page-{len(image_urls) + 1}.png"
                image.save(image_path, "PNG")
                encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
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
    if "invoice" in text or "receipt" in text or "payment" in text:
        return "freelance_invoice"
    return "unknown"


def extraction_result_from_ai_data(data: dict, warnings: list[str], source_text: str = "") -> ExtractionResult:
    invoice = data.get("invoice_details") if isinstance(data.get("invoice_details"), dict) else {}
    payroll = data.get("payroll_data") if isinstance(data.get("payroll_data"), dict) else {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    earnings = payroll.get("earnings") if isinstance(payroll.get("earnings"), dict) else {}
    deductions = payroll.get("deductions") if isinstance(payroll.get("deductions"), dict) else {}
    net_pay = payroll.get("net_pay") if isinstance(payroll.get("net_pay"), dict) else {}

    document_type = normalize_ai_document_type(data.get("source_document_type"))
    invoice_gross = coerce_float(invoice.get("total_chargeable_value"))
    invoice_net = coerce_float(invoice.get("grand_total_amount"))
    salary_gross = coerce_float(earnings.get("gross_salary"))
    salary_net = coerce_float(net_pay.get("final_salary_after_deductions"))
    pf_amount = coerce_float(deductions.get("pf_employee"))
    vpf_amount = coerce_float(deductions.get("vpf_employee"))
    tds_amount = coerce_float(deductions.get("tax_tds"))
    deductions_amount = sum_money_values(deductions.get("other_deductions"))

    if document_type == "unknown":
        document_type = "salary" if salary_gross or salary_net else "freelance_invoice" if invoice_gross or invoice_net else "unknown"

    if document_type == "salary":
        gross_amount = salary_gross
        net_amount = salary_net or gross_amount
        name = first_text(payroll.get("employee_name"))
        payer = first_text(invoice.get("seller_name"), invoice.get("buyer_name")) or find_salary_employer(source_text)
        record_date = normalize_date(first_text(payroll.get("period_end_date"), payroll.get("period_start_date"), metadata.get("date_issued"), metadata.get("billable_period"))) or normalize_date(find_date(source_text))
        if source_text:
            gross_amount = gross_amount or find_amount(source_text, "gross_amount")
            net_amount = net_amount or find_amount(source_text, "net_amount") or gross_amount
            tds_amount = tds_amount or find_amount(source_text, "tds_amount")
            pf_amount = pf_amount or find_amount(source_text, "pf_amount")
            vpf_amount = vpf_amount or find_amount(source_text, "vpf_amount")
            total_deductions = find_amount(source_text, "deductions_amount")
            if not deductions_amount and total_deductions:
                deductions_amount = round(max(0.0, total_deductions - pf_amount - vpf_amount - tds_amount), 2)
    else:
        gross_amount = invoice_gross or invoice_net
        net_amount = invoice_net or gross_amount
        name = first_text(invoice.get("seller_name"))
        payer = first_text(invoice.get("buyer_name"))
        record_date = normalize_date(first_text(metadata.get("date_issued"), metadata.get("billable_period"), data.get("extraction_date")))

    gst_deduction = coerce_float(deductions.get("gst_deduction"))
    taxation = invoice.get("taxation") if isinstance(invoice.get("taxation"), dict) else {}
    cgst = taxation.get("cgst") if isinstance(taxation.get("cgst"), dict) else {}
    sgst = taxation.get("sgst_or_utgst") if isinstance(taxation.get("sgst_or_utgst"), dict) else {}
    gst_amount = coerce_float(cgst.get("amount")) + coerce_float(sgst.get("amount"))
    if document_type == "freelance_invoice" and gst_amount == 0 and net_amount > gross_amount:
        gst_amount = round(net_amount - gross_amount, 2)
    if document_type == "freelance_invoice" and tds_amount == 0 and gross_amount > 0:
        tds_amount = round(gross_amount * 0.10, 2)
    pan = gstin_to_pan(invoice.get("seller_gstin")) or gstin_to_pan(invoice.get("buyer_gstin")) or find_pan(source_text)

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
    salary_score = sum(token in lowered for token in ["salary", "payslip", "pay slip", "employee", "gross pay", "net pay"])
    invoice_score = sum(token in lowered for token in ["invoice", "bill to", "client", "amount due", "freelance", "consulting"])
    if salary_score >= 2 and salary_score >= invoice_score:
        return "salary"
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


def find_amount(text: str, key: str) -> float:
    labels_by_key = {
        "gross_amount": ["gross pay", "gross salary", "gross earnings", "gross earning", "total earnings", "total earning"],
        "net_amount": ["total net pay", "a.net salary", "net salary", "net pay", "net payable"],
        "tds_amount": ["tds", "income tax", "tax deducted"],
        "deductions_amount": ["total deductions", "total deduction"],
        "pf_amount": ["ee pf contribution", "employee pf contribution", "provident fund", "pf contribution"],
        "vpf_amount": ["ee vpf contribution", "employee vpf contribution", "voluntary provident fund", "vpf contribution"],
        "invoice_amount": ["invoice amount", "total amount", "amount due"],
    }
    for line in text.splitlines():
        normalized = re.sub(r"\s+", " ", line.lower())
        if key == "pf_amount" and "vpf" in normalized:
            continue
        if key == "gross_amount" and "professional charges" in normalized:
            amounts = extract_currency_amounts_from_line(line)
            if amounts:
                return amounts[0]
        if key == "invoice_amount" and normalized.startswith("total "):
            amounts = extract_currency_amounts_from_line(line)
            if len(amounts) == 1:
                return amounts[0]
        if any(label in normalized for label in labels_by_key.get(key, [])):
            amounts = extract_amounts_from_line(line)
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
        pattern = rf"{label}\s*[:\-]\s*([A-Za-z][A-Za-z .&]+?)(?:\s{{2,}}|[|]|\n|$)"
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
    lines = [line.strip(" |") for line in text.splitlines()]
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
    for line in lines[:12]:
        cleaned = re.sub(r"\s+", " ", line).strip()
        if not cleaned or len(cleaned) < 3:
            continue
        lowered = cleaned.lower()
        if any(token in lowered for token in skip_tokens):
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
    return None


def find_invoice_buyer(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines[:-1]):
        lowered = line.lower()
        if "buyer" in lowered and "bill to" in lowered:
            return next_meaningful_line(lines, index + 1)
        if "bill to" in lowered:
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


def extract_financial_fields(path: Path, ai_provider: str = "nvidia") -> ExtractionResult:
    # Try NVIDIA OCR first if key is present and provider is nvidia
    nvidia_text = ""
    nvidia_warnings = []
    if ai_provider == "nvidia" and NVIDIA_API_KEY:
        nvidia_text, nvidia_warnings = extract_text_with_nvidia_ocr(path)

    if nvidia_text:
        embedded_text = nvidia_text
        embedded_warnings = nvidia_warnings
    else:
        embedded_text, embedded_warnings = extract_embedded_pdf_text(path)
        if ai_provider == "nvidia" and NVIDIA_API_KEY:
            embedded_warnings = [*nvidia_warnings, *embedded_warnings]

    ai_data, ai_warnings = extract_structured_data_with_ai(path, embedded_text, ai_provider)
    if ai_data:
        return extraction_result_from_ai_data(ai_data, [*embedded_warnings, *ai_warnings], embedded_text)

    if embedded_text:
        text = embedded_text
        warnings = [*embedded_warnings, *ai_warnings]
    else:
        text, warnings = extract_text_from_pdf(path, ai_provider)
        warnings = [*embedded_warnings, *ai_warnings, *warnings]
    document_type = classify_document(text)
    invoice_amount = find_amount(text, "invoice_amount")
    gross_amount = find_amount(text, "gross_amount") or invoice_amount
    net_amount = find_amount(text, "net_amount") or (invoice_amount if document_type == "freelance_invoice" else gross_amount)
    tds_amount = find_amount(text, "tds_amount")
    total_deductions_amount = find_amount(text, "deductions_amount")
    vpf_amount = find_amount(text, "vpf_amount")
    pf_amount = find_amount(text, "pf_amount")
    deductions_amount = total_deductions_amount
    if document_type == "salary" and total_deductions_amount > 0:
        deductions_amount = round(max(0.0, total_deductions_amount - pf_amount - vpf_amount - tds_amount), 2)
    gst_amount = round(max(0.0, net_amount - gross_amount), 2) if document_type == "freelance_invoice" else 0.0
    if document_type == "freelance_invoice" and tds_amount == 0 and gross_amount > 0:
        tds_amount = round(gross_amount * 0.10, 2)
    pan = find_pan(text) or gstin_to_pan(text)
    name = find_named_value(text, ["employee name", "name", "consultant", "freelancer"]) or find_invoice_seller(text)
    payer = find_payer(text)
    record_date = normalize_date(find_date(text))

    confidence = 0.25
    confidence += 0.2 if document_type != "unknown" else 0
    confidence += 0.2 if gross_amount > 0 else 0
    confidence += 0.15 if net_amount > 0 else 0
    confidence += 0.1 if pan else 0
    confidence += 0.1 if record_date else 0
    confidence = min(confidence, 0.95)

    if gross_amount == 0:
        warnings.append("Gross amount could not be extracted.")
    if document_type != "freelance_invoice" and net_amount > gross_amount and gross_amount > 0:
        warnings.append("Net amount is greater than gross amount.")
    if not pan:
        warnings.append("PAN was not found in the document.")
    if document_type == "unknown":
        warnings.append("Document type could not be classified confidently.")

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
        extracted_text=text[:20000],
    )
