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
    fake_pdf2image = SimpleNamespace(convert_from_path=lambda *_args, **_kwargs: ["image"])
    fake_tesseract = SimpleNamespace(image_to_string=lambda _image: "Invoice amount 50,000 client: Acme")
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)
    monkeypatch.setitem(sys.modules, "pdf2image", fake_pdf2image)
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
