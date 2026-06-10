# Project Code Backup & Version Memory

This file serves as a local backup memory of key sections of code that have been modified, so they can be easily restored/undone if issues arise.

## backup_history

### [2026-06-10] Update LOCAL_AI_EXTRACTION_PROMPT in extraction.py

#### Modified File
- File Path: [extraction.py](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/extraction.py)
- Section: `LOCAL_AI_EXTRACTION_PROMPT` (starting around Line 64)

#### Original Code (To Undo/Restore)
```python
LOCAL_AI_EXTRACTION_PROMPT = (
    "You are a highly accurate Financial Data Analyst and Structured Extractor. "
    "Return only raw JSON. Use null for every missing field. Schema: "
    '{"extraction_date":"YYYY-MM-DD","source_document_type":"Invoice|Salary Slip|Payment Receipt|Bank Statement|Unknown",'
    '"metadata":{"invoice_number":null,"reference_no":null,"billable_period":null,"date_issued":null},'
    '"invoice_details":{"seller_name":null,"seller_gstin":null,"buyer_name":null,"buyer_gstin":null,'
    '"total_chargeable_value":null,"grand_total_amount":null,'
    '"taxation":{"cgst":{"rate":null,"amount":null},"sgst_or_utgst":{"rate":null,"amount":null},"other_taxes":{}}},'
    '"payroll_data":{"period_start_date":null,"period_end_date":null,"employee_name":null,"designation":null,'
    '"earnings":{"gross_salary":null,"basic_salary":null,"hra":null,"other_earnings":[]},'
    '"deductions":{"pf_employee":null,"vpf_employee":null,"tax_tds":null,"gst_deduction":null,"other_deductions":[]},'
    '"net_pay":{"final_salary_after_deductions":null}}}'
)
```

#### New Code Applied
```python
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
```
