import sys
from types import SimpleNamespace

from backend.app.extraction import ai_data_to_text, classify_document, extraction_result_from_ai_data, extract_financial_fields, extract_text_from_pdf, find_amount, find_date, find_invoice_buyer, find_invoice_seller, find_named_value, find_pan, find_payer, normalize_date, parse_ai_json, parse_amount


def test_classifies_salary_text():
    text = "Employee payslip gross pay 100000 net pay 85000 salary"
    assert classify_document(text) == "salary"


def test_classifies_invoice_text():
    text = "Invoice bill to Client amount due 50000 consulting freelance"
    assert classify_document(text) == "freelance_invoice"


def test_finds_pan():
    assert find_pan("PAN ABCDE1234F") == "ABCDE1234F"


def test_parse_amount_with_commas():
    assert parse_amount("1,23,456.78") == 123456.78


def test_local_ai_json_is_translated_to_parseable_text():
    text = ai_data_to_text(
        {
            "document_type": "freelance_invoice",
            "name": "Akshay Bhatnagar",
            "pan": "ABCDE1234F",
            "payer": "Acme Pvt Ltd",
            "record_date": "2026-05-31",
            "gross_amount": 100000,
            "net_amount": 90000,
            "tds_amount": 10000,
        }
    )
    assert classify_document(text) == "freelance_invoice"
    assert find_pan(text) == "ABCDE1234F"
    assert find_amount(text, "invoice_amount") == 0
    assert find_amount(text, "gross_amount") == 100000
    assert find_amount(text, "tds_amount") == 10000


def test_parse_ai_json_accepts_fenced_json():
    assert parse_ai_json('```json\n{"gross_amount": 50000}\n```') == {"gross_amount": 50000}


def test_ai_invoice_schema_maps_to_review_form_fields():
    result = extraction_result_from_ai_data(
        {
            "extraction_date": "2026-06-07",
            "source_document_type": "Invoice",
            "metadata": {
                "invoice_number": "INV-1",
                "reference_no": None,
                "billable_period": "May 2026",
                "date_issued": None,
            },
            "invoice_details": {
                "seller_name": "Devlina Consulting",
                "seller_gstin": "07ABCDE1234F1Z5",
                "buyer_name": "Acme Pvt Ltd",
                "buyer_gstin": None,
                "total_chargeable_value": "100000.00",
                "grand_total_amount": "118000.00",
                "taxation": {
                    "cgst": {"rate": 9, "amount": 9000},
                    "sgst_or_utgst": {"rate": 9, "amount": 9000},
                    "other_taxes": {},
                },
            },
            "payroll_data": {},
        },
        [],
    )
    assert result.document_type == "freelance_invoice"
    assert result.name == "Devlina Consulting"
    assert result.payer == "Acme Pvt Ltd"
    assert result.record_date == "2026-05-01"
    assert result.pan == "ABCDE1234F"
    assert result.gross_amount == 100000
    assert result.net_amount == 118000


def test_ai_payroll_schema_maps_to_review_form_fields():
    result = extraction_result_from_ai_data(
        {
            "source_document_type": "Salary Slip",
            "metadata": {"billable_period": "April 2026", "date_issued": None},
            "invoice_details": {"seller_name": "Terafina Software Solutions Pvt Ltd"},
            "payroll_data": {
                "period_start_date": "2026-04-01",
                "period_end_date": "2026-04-30",
                "employee_name": "Bhatnagar Akshay",
                "designation": "Engineer",
                "earnings": {"gross_salary": 134189.14, "basic_salary": 50517, "hra": None, "other_earnings": []},
                "deductions": {
                    "pf_employee": 6062,
                    "vpf_employee": 9093,
                    "tax_tds": 6884,
                    "gst_deduction": None,
                    "other_deductions": [],
                },
                "net_pay": {"final_salary_after_deductions": 112151},
            },
        },
        [],
    )
    assert result.document_type == "salary"
    assert result.name == "Bhatnagar Akshay"
    assert result.payer == "Terafina Software Solutions Pvt Ltd"
    assert result.record_date == "2026-04-30"
    assert result.gross_amount == 134189.14
    assert result.net_amount == 112151
    assert result.tds_amount == 6884
    assert result.deductions_amount == 0


def test_flat_local_ai_schema_maps_to_review_form_fields():
    result = extraction_result_from_ai_data(
        {
            "document_type": "freelance_invoice",
            "name": "Devlina Consulting",
            "pan": "ABCDE1234F",
            "payer": "Acme Pvt Ltd",
            "record_date": "2026-05-31",
            "gross_amount": "100000",
            "net_amount": "90000",
            "tds_amount": "10000",
            "gst_amount": "18000",
        },
        [],
    )
    assert result.document_type == "freelance_invoice"
    assert result.name == "Devlina Consulting"
    assert result.payer == "Acme Pvt Ltd"
    assert result.record_date == "2026-05-31"
    assert result.pan == "ABCDE1234F"
    assert result.gross_amount == 100000
    assert result.net_amount == 90000
    assert result.tds_amount == 10000
    assert result.gst_amount == 18000


def test_nested_local_ai_salary_aliases_map_to_review_fields():
    result = extraction_result_from_ai_data(
        {
            "type": "salary slip",
            "employee": {
                "employee_name": "Bhatnagar Akshay",
                "pan_number": "BPLPB7839D",
                "employer": "Terafina Software Solutions Pvt Ltd",
            },
            "salary_details": {
                "pay_date": "30.04.2024",
                "total_gross": "108,860.71",
                "total_net_pay": "89,403.00",
                "income_tax": "6,158.00",
                "employee_pf": "5,320.00",
                "employee_vpf": "7,980.00",
                "less_deductions": "13,300.10",
            },
        },
        [],
    )
    assert result.document_type == "salary"
    assert result.name == "Bhatnagar Akshay"
    assert result.payer == "Terafina Software Solutions Pvt Ltd"
    assert result.record_date == "2024-04-30"
    assert result.gross_amount == 108860.71
    assert result.net_amount == 89403
    assert result.tds_amount == 6158
    assert result.pf_amount == 5320
    assert result.vpf_amount == 7980


def test_tax_invoice_text_fields_are_detected_without_ocr():
    text = """
Tax Invoice
DEVLINA BHATNAGAR(FY-2026-27)
G/CA-508, City Apartments,
GST No. 09CPIPP9940K1Z1
Buyer (Bill to)
Gen Aquarius Private Limited
A-8,Sector-23, Noida
GST No. 09AALCG7851K1ZX
Invoice No.
002/2026-27
Dated
27-May-26
1 Professional Charges for the M/o May,2026 2,74,194.00998314
Output- CGST-9% 24,677.46%9
Output-SGST-9% 24,677.46%9
Total ī  3,23,548.92
"""
    assert classify_document(text) == "freelance_invoice"
    assert find_invoice_seller(text) == "DEVLINA BHATNAGAR(FY-2026-27)"
    assert find_invoice_buyer(text) == "Gen Aquarius Private Limited"
    assert find_payer(text) == "Gen Aquarius Private Limited"
    assert normalize_date(find_date(text)) == "2026-05-27"
    assert find_amount(text, "gross_amount") == 274194.00
    assert find_amount(text, "invoice_amount") == 323548.92


def test_ocr_fallback_runs_when_pdf_has_no_embedded_text(tmp_path, monkeypatch):
    class EmptyPage:
        def extract_text(self):
            return ""

    class FakePdfReader:
        pages = [EmptyPage()]

    fake_pypdf = SimpleNamespace(PdfReader=lambda _: FakePdfReader())
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

    # Mock fitz
    class FakePixmap:
        def tobytes(self, fmt="png"):
            return b"fake_png"

    class FakePage:
        def get_pixmap(self, dpi=220):
            return FakePixmap()

    class FakeDocument:
        def __init__(self, *args, **kwargs):
            self.pages = [FakePage()]
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def __iter__(self):
            return iter(self.pages)
        def __len__(self):
            return len(self.pages)

    fake_fitz = SimpleNamespace(open=FakeDocument)
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)

    # Mock PIL
    import PIL.Image
    monkeypatch.setattr(PIL.Image, "open", lambda _io: "image")

    fake_tesseract = SimpleNamespace(image_to_string=lambda _image: "Invoice amount 50,000 client: Acme")
    monkeypatch.setitem(sys.modules, "pytesseract", fake_tesseract)

    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    text, warnings = extract_text_from_pdf(pdf)

    assert "Invoice amount" in text
    assert "Text was extracted using OCR fallback." in warnings


def test_terafina_two_column_payslip_amounts_are_detected():
    text = """
Terafina Software Solutions Pvt Ltd
|Employee Name : Bhatnagar Akshay                 DOJ               : 21.01.2019 |
|Global ID     : 41477041095                       Pay Period       : April 2026 |
|PAN           : BPLPB7839D                        UAN               : 101485688625 |
| Monthly Base Salary                   50,517.00 | Ee PF contribution                     6,062.00  |
|*Overtime                               3,850.00 | Ee VPF contribution                    9,093.00  |
|*Roster Allowance                       8,250.00 | Income Tax                             6,884.00  |
|Total Earnings                      134,189.14    |Total Deductions                       22,039.00   |
|        A.NET SALARY                                                                   112,151.00  |
|        TOTAL NET PAY(A+B)                                                             112,151.00  |
"""
    assert find_named_value(text, ["employee name"]) == "Bhatnagar Akshay"
    assert normalize_date(find_date(text)) == "2026-04-01"
    assert find_amount(text, "gross_amount") == 134189.14
    assert find_amount(text, "net_amount") == 112151.00
    assert find_amount(text, "tds_amount") == 6884.00
    assert find_amount(text, "deductions_amount") == 22039.00
    assert find_amount(text, "pf_amount") == 6062.00
    assert find_amount(text, "vpf_amount") == 9093.00


def test_terafina_old_salary_slip_extracts_totals_and_validates():
    from backend.app.extraction import run_local_parser, validate_local_extraction
    text = """
--------------------------------------------------------------------------------
|                           Terafina Software Solutions Pvt Ltd                |
| Employee ID  :50038885                 Pay Period    :01.04.24  -30.04.24    |
| Employee Name:Bhatnagar Akshay         Pay Date      :30.04.2024             |
| Designation  :                         PAN           :BPLPB7839D             |
| EARNINGS & ALLOWANCES      UNITS          INR| DEDUCTIONS                INR |
| Monthly Base Salary                 44,331.00| Income Tax           6,158.00 |
|*Overtime                             4,950.00| Ee PF contribut      5,320.00 |
|*Roster Allowance                     8,050.00| Ee VPF contribu      7,980.00 |
|*Call Out Allowance                   3,600.00|*Current Month E          0.39 |
| House Rent Allowance                20,150.00| Current Month E          0.29-|
| Taxable Allowance                   27,779.71|                               |
| Other details                                | Total Gross        108,860.71 |
|                                              | Less: Tax            6,158.00 |
|                                              | Less: Dedns         13,300.10 |
|ANNUAL LEAVE (DAYS)                  63.00    | NET PAY             89,403.00 |
"""
    data = run_local_parser(text)
    assert data["document_type"] == "salary"
    assert data["name"] == "Bhatnagar Akshay"
    assert data["payer"] == "Terafina Software Solutions Pvt Ltd"
    assert data["record_date"] == "2024-04-30"
    assert data["gross_amount"] == 108860.71
    assert data["net_amount"] == 89403
    assert data["tds_amount"] == 6158
    assert data["pf_amount"] == 5320
    assert data["vpf_amount"] == 7980
    assert data["deductions_amount"] == 0.1
    assert validate_local_extraction(data) is True


def test_exoedge_total_earnings_payslip_amounts_are_detected():
    text = """
EXO EDGE ADVANTAGE INDIA PVT LTD
Payslip for the month of December 2025
Permanent Account
Number
CPIPP9940K
Basic Salary 95,968.00
Profession Tax 200.00
Provident Fund 11,516.00
Total Earnings 180,419.00 Total Deductions 11,716.00
In words ( ) : One Lakh Sixty Eight Thousand Seven Hundred Three Only Net Salary : 168,703.00
"""
    assert find_amount(text, "gross_amount") == 180419.00
    assert find_amount(text, "net_amount") == 168703.00
    assert find_amount(text, "deductions_amount") == 11716.00
    assert find_amount(text, "pf_amount") == 11516.00
    assert find_amount(text, "vpf_amount") == 0


def test_exoedge_gross_earnings_payslip_amounts_are_detected():
    text = """
EXO EDGE ADVANTAGE INDIA PVT LTD
Payslip for the month of February 2026
Gross Earnings 275,847.00 Total Deductions 17,200.00
Net Salary : 258,647.00
"""
    assert find_amount(text, "gross_amount") == 275847.00
    assert find_amount(text, "net_amount") == 258647.00


def test_exoedge_april_2026_layout_parses_and_validates():
    from backend.app.extraction import run_local_parser, validate_local_extraction
    text = """
:
:
EXO Edge Advantage India Private Limited
A 10 Ground Floor,Bestech Business Tower Sec-66, Mohali S.A.S.Nagar
Punjab 160066 India
Payslip For the Month
April 2026
EMPLOYEE SUMMARY
Employee Name Devlina Bhatnagar
Designation Senior Software Engineer
Employee ID EEA2590
Pay Period April 2026
Pay Date 30/04/2026
₹2,04,388.00
Total Net Pay
Paid Days 30
PAN CPIPP9940K
EARNINGS AMOUNT YTD
Basic ₹1,41,667.00 ₹1,41,667.00
House Rent Allowance ₹56,667.00 ₹56,667.00
Special Allowance ₹67,000.00 ₹67,000.00
DEDUCTIONS AMOUNT YTD
EPF Contribution ₹17,000.00 ₹17,000.00
Income Tax ₹44,746.00 ₹44,746.00
Professional Tax ₹200.00 ₹200.00
Gross Earnings ₹2,66,334.00 Total Deductions ₹61,946.00
TOTAL NET PAYABLE
Gross Earnings - Total Deductions ₹2,04,388.00
BENEFITS EMPLOYEE
CONTRIBUTION EMPLOYEE YTD EMPLOYER
CONTRIBUTION EMPLOYER YTD
"""
    data = run_local_parser(text)
    assert data["document_type"] == "salary"
    assert data["name"] == "Devlina Bhatnagar"
    assert data["payer"] == "EXO Edge Advantage India Private Limited"
    assert data["pan"] == "CPIPP9940K"
    assert data["gross_amount"] == 266334
    assert data["net_amount"] == 204388
    assert data["tds_amount"] == 44746
    assert data["deductions_amount"] == 200
    assert data["pf_amount"] == 17000
    assert data["gst_amount"] == 0
    assert validate_local_extraction(data) is True


def test_extract_structured_data_uses_only_local_lm_studio(monkeypatch):
    import json
    from pathlib import Path
    from backend.app import extraction

    monkeypatch.setattr(extraction, "LOCAL_AI_BASE_URLS", ["http://localhost:1234/v1"])

    captured_requests = []

    class FakeResponse:
        def read(self):
            return json.dumps({
                "choices": [
                    {
                        "message": {
                            "content": '{"source_document_type": "Salary Slip"}'
                        }
                    }
                ]
            }).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_urlopen(req, timeout=None):
        data = req.data
        if data:
            captured_requests.append((req.full_url, json.loads(data.decode("utf-8")), req.headers))
        return FakeResponse()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    data, warnings = extraction.extract_structured_data_with_ai(Path("dummy.pdf"), "embedded", "local")
    assert data == {"source_document_type": "Salary Slip"}
    assert "Local AI analysis used model google/gemma-4-e4b." in warnings

    assert len(captured_requests) == 1
    url, payload, headers = captured_requests[0]
    assert url == "http://localhost:1234/v1/chat/completions"
    assert payload["model"] == "google/gemma-4-e4b"
    assert headers.get("Authorization") is None or "Bearer" not in headers.get("Authorization", "")


def test_classify_document_expense():
    text = "Payment receipt from Amazon Web Services for software cloud hosting bill"
    assert classify_document(text) == "purchase_expense"


def test_classify_expense_category():
    from backend.app.extraction import classify_expense_category
    assert classify_expense_category("Uber taxi ride to office") == "Travel"
    assert classify_expense_category("AWS cloud web server domain renewal") == "Software"
    assert classify_expense_category("Apple MacBook keyboard repair receipt") == "Hardware"
    assert classify_expense_category("Bescom electricity bill payment") == "Utilities"
    assert classify_expense_category("A4 paper packets and ball pens invoice") == "Office Supplies"
    assert classify_expense_category("Legal advice consulting fees from counsel") == "Professional Fees"
    assert classify_expense_category("Office coworking rent wework invoice") == "Rent"
    assert classify_expense_category("Lunch at Zomato restaurant meals bill") == "Meals"
    assert classify_expense_category("Unclassified general purchase") == "Others"


def test_run_local_parser_and_validate_expense():
    from backend.app.extraction import run_local_parser, validate_local_extraction
    text = """
    TAX RECEIPT
    Vendor: DigitalOcean Inc.
    Date: 2026-06-01
    Gross Amount: 1,000.00
    GST: 180.00
    Total Amount Paid: 1,180.00
    """
    data = run_local_parser(text)
    assert data["document_type"] == "purchase_expense"
    assert data["gross_amount"] == 1000.0
    assert data["net_amount"] == 1180.0
    assert data["gst_amount"] == 180.0
    assert data["record_date"] == "2026-06-01"
    
    assert validate_local_extraction(data) is True


def test_run_local_parser_validates_gst_freelance_invoice():
    from backend.app.extraction import run_local_parser, validate_local_extraction
    text = """
    Tax Invoice
    Devlina Consulting
    Bill To: Acme Pvt Ltd
    Dated
    31-May-2026
    Professional Charges 1,00,000.00
    CGST 9,000.00
    SGST 9,000.00
    Grand Total 1,18,000.00
    """
    data = run_local_parser(text)
    assert data["document_type"] == "freelance_invoice"
    assert data["gross_amount"] == 100000
    assert data["gst_amount"] == 18000
    assert data["tds_amount"] == 10000
    assert data["net_amount"] == 90000
    assert data["record_date"] == "2026-05-31"
    assert validate_local_extraction(data) is True


def test_run_local_parser_reads_gst_from_tally_style_freelance_invoice():
    from backend.app.extraction import run_local_parser, validate_local_extraction
    text = """
    INVOICE
    DEVLINA BHATNAGAR
    09CPIPP9940K1Z1
    Buyer
    Gen Aquarius Private Limited
    Invoice No.
    001/2026-27
    Dated
    29-Apr-2026
    1 Professional Charges for the M/o April,2026 2,83,333.00
    2 Output-CGST-9% 25,499.97%9
    3 Output-SGST-9% 25,499.97%9
    Total INR 3,34,332.94
    """
    data = run_local_parser(text)
    assert data["document_type"] == "freelance_invoice"
    assert data["name"] == "DEVLINA BHATNAGAR"
    assert data["pan"] == "CPIPP9940K"
    assert data["payer"] == "Gen Aquarius Private Limited"
    assert data["record_date"] == "2026-04-29"
    assert data["gross_amount"] == 283333
    assert data["gst_amount"] == 50999.94
    assert data["tds_amount"] == 28333.3
    assert data["net_amount"] == 254999.7
    assert validate_local_extraction(data) is True


def test_local_parser_fallback_pipeline(monkeypatch, tmp_path):
    from backend.app import extraction
    
    # Mock extract_embedded_pdf_text
    monkeypatch.setattr(extraction, "extract_embedded_pdf_text", lambda _p: (
        "TAX RECEIPT\nVendor: AWS\nDate: 2026-06-01\nGross Amount: 1000\nGST: 180\nTotal Amount Paid: 1180\n",
        []
    ))
    
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    
    res = extraction.extract_financial_fields(pdf, "local")
    assert res.document_type == "purchase_expense"
    assert res.confidence == 0.95
    assert "Successfully extracted details using Local Python Parser." in res.warnings


