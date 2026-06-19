FORM16_PART_A_TEXT = """
FORM NO. 16
Name and address of the Employer/Specified Bank
TERAFINA SOFTWARE SOLUTIONS PRIVATE LIMITED
PAN of the Deductor
AAGCT8085R
TAN of the Deductor
MUMT22660B
PAN of the Employee/Specified senior citizen
BPLPB7839D
Assessment Year
2025-26
Period with the Employer
To
31-Mar-2025
From
01-Apr-2024
Summary of amount paid/credited and tax deducted at source thereon in respect of the employee
Q1 QVTXYOPG 19462.00 19462.00338883.00
Q2 QVWAOSCC 26294.00 26294.00384058.00
Q3 QVXFKODB 30047.00 30047.00368883.00
Q4 QVYJLTQE 51583.00 51583.00395610.00
Total (Rs.) 127386.00 127386.001487434.00
PART A
Certificate No. FTGRXYA
"""


FORM16_PART_B_TEXT = """
FORM NO. 16
Name and address of the Employer/Specified Bank
TERAFINA SOFTWARE SOLUTIONS PRIVATE LIMITED
PAN of the Employee/Specified senior citizen
BPLPB7839D
TAN of Employer: MUMT22660B PAN of Employee: BPLPB7839D Assessment Year: 2025-26
Certificate Number: FTGRXYA
PART B
Details of Salary Paid and any other income and tax deducted
Salary as per provisions contained in section 17(1)(a) 1485804.00
(b) 1630.00
(c) Profits in lieu of salary under section 17(3) 0.00
(d) Total 1487434.00
Income chargeable under the head "Salaries" [(3+1(e)-5]
1412434.00Gross total income
1412434.00Total taxable income (9-11)
Net tax payable (17-18-19-20)21. 127386.00
"""


FORM26AS_TEXT = """
Annual Tax Statement
Permanent Account Number (PAN) BPLPB7839D Current Status of PAN Active and Operative Financial Year 2024-25 Assessment Year 2025-26
Name of Assessee AKSHAY BHATNAGAR
PART-I - Details of Tax Deducted at Source
1 TERAFINA SOFTWARE SOLUTIONS PRIVATE LIMITED MUMT22660B 1487434.00 127386.00 127386.00
1 192 31-Mar-2025 F 08-May-2025 - 155858.00 25720.00 25720.00
2 GENAQ PRIVATE LIMITED MRTG15889G 919637.00 91964.00 91964.00
1 194J 31-Mar-2025 F 08-May-2025 - 919637.00 91964.00 91964.00
"""


def setup_tax_db(tmp_path, monkeypatch):
    from backend.app import database

    data_dir = tmp_path / "data"
    upload_dir = data_dir / "uploads"
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(database, "DB_PATH", data_dir / "income_ledger.sqlite3")
    database.init_db()
    upload_dir.mkdir(parents=True, exist_ok=True)
    return database, upload_dir


def test_parse_form16_part_a_totals():
    from backend.app.tax_documents import parse_tax_statement_text

    parsed = parse_tax_statement_text(FORM16_PART_A_TEXT, [])

    assert parsed.source_type == "form16_part_a"
    assert parsed.financial_year == "FY 2024-25"
    assert parsed.pan == "BPLPB7839D"
    assert parsed.tan == "MUMT22660B"
    assert parsed.summaries[0].gross_salary == 1487434
    assert parsed.summaries[0].tds_deducted == 127386
    assert len(parsed.entries) == 4


def test_parse_form16_part_b_salary_computation():
    from backend.app.tax_documents import parse_tax_statement_text

    parsed = parse_tax_statement_text(FORM16_PART_B_TEXT, [])
    summary = parsed.summaries[0]

    assert parsed.source_type == "form16_part_b"
    assert parsed.certificate_number == "FTGRXYA"
    assert summary.gross_salary == 1487434
    assert summary.perquisites_17_2 == 1630
    assert summary.income_chargeable_salary == 1412434
    assert summary.tds_deducted == 127386


def test_parse_26as_salary_and_freelance_buckets():
    from backend.app.tax_documents import parse_tax_statement_text

    parsed = parse_tax_statement_text(FORM26AS_TEXT, [])

    assert parsed.source_type == "form26as"
    assert parsed.financial_year == "FY 2024-25"
    assert {entry.income_bucket for entry in parsed.entries} == {"salary", "freelance"}
    assert sum(entry.tax_deducted for entry in parsed.entries if entry.income_bucket == "freelance") == 91964


def test_save_26as_keeps_one_active_statement(tmp_path, monkeypatch):
    database, upload_dir = setup_tax_db(tmp_path, monkeypatch)
    from backend.app.tax_documents import parse_tax_statement_text, save_tax_document_parse

    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (id, name, pan, aliases, profile_hints) VALUES (1, 'Akshay', 'BPLPB7839D', '', '')")
        conn.execute(
            """
            INSERT INTO documents (id, original_name, stored_path, file_hash, document_type, status, extracted_json, detected_user_id)
            VALUES
                (1, '26AS-old.pdf', ?, 'hash-old', 'form26as', 'needs_review', '{}', 1),
                (2, '26AS-new.pdf', ?, 'hash-new', 'form26as', 'needs_review', '{}', 1)
            """,
            (str(upload_dir / "old.pdf"), str(upload_dir / "new.pdf")),
        )

    parsed = parse_tax_statement_text(FORM26AS_TEXT, [])
    save_tax_document_parse(1, parsed, 1, [])
    save_tax_document_parse(2, parsed, 1, [])

    with database.get_connection() as conn:
        rows = conn.execute("SELECT id, document_id, is_active, superseded_by_tax_document_id FROM tax_documents ORDER BY document_id").fetchall()

    assert [row["is_active"] for row in rows] == [0, 1]
    assert rows[0]["superseded_by_tax_document_id"] == rows[1]["id"]


def test_multiple_form16_employers_same_financial_year(tmp_path, monkeypatch):
    database, upload_dir = setup_tax_db(tmp_path, monkeypatch)
    from backend.app.tax_documents import parse_tax_statement_text, save_tax_document_parse
    from backend.app.tax_reconciliation import tax_statement_report

    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (id, name, pan, aliases, profile_hints) VALUES (1, 'Akshay', 'BPLPB7839D', '', '')")
        conn.executemany(
            """
            INSERT INTO documents (id, original_name, stored_path, file_hash, document_type, status, extracted_json, detected_user_id)
            VALUES (?, ?, ?, ?, ?, 'needs_review', '{}', 1)
            """,
            [
                (1, "Form16A-1.pdf", str(upload_dir / "a1.pdf"), "hash-a1", "form16_part_a"),
                (2, "Form16B-1.pdf", str(upload_dir / "b1.pdf"), "hash-b1", "form16_part_b"),
                (3, "Form16A-2.pdf", str(upload_dir / "a2.pdf"), "hash-a2", "form16_part_a"),
                (4, "Form16B-2.pdf", str(upload_dir / "b2.pdf"), "hash-b2", "form16_part_b"),
            ],
        )

    second_part_a = (
        FORM16_PART_A_TEXT
        .replace("TERAFINA SOFTWARE SOLUTIONS PRIVATE LIMITED", "SECOND EMPLOYER PRIVATE LIMITED")
        .replace("MUMT22660B", "DELS12345C")
        .replace("FTGRXYA", "SECOND1")
    )
    second_part_b = (
        FORM16_PART_B_TEXT
        .replace("TERAFINA SOFTWARE SOLUTIONS PRIVATE LIMITED", "SECOND EMPLOYER PRIVATE LIMITED")
        .replace("MUMT22660B", "DELS12345C")
        .replace("FTGRXYA", "SECOND1")
    )

    for document_id, text in [
        (1, FORM16_PART_A_TEXT),
        (2, FORM16_PART_B_TEXT),
        (3, second_part_a),
        (4, second_part_b),
    ]:
        save_tax_document_parse(document_id, parse_tax_statement_text(text, []), 1, [])

    report = tax_statement_report("1", "FY 2024-25")
    tans = {item["tan"] for item in report["form16_sets"]}

    assert report["summary"]["form16_employers"] == 2
    assert tans == {"MUMT22660B", "DELS12345C"}
    assert all(item["part_a"] and item["part_b"] for item in report["form16_sets"])


def test_salary_slip_vs_26as_monthly_mismatch_is_reported(tmp_path, monkeypatch):
    database, upload_dir = setup_tax_db(tmp_path, monkeypatch)
    from backend.app.tax_documents import parse_tax_statement_text, save_tax_document_parse
    from backend.app.tax_reconciliation import tax_statement_report

    form26as_monthly_text = """
Annual Tax Statement
Permanent Account Number (PAN) BPLPB7839D Current Status of PAN Active and Operative Financial Year 2024-25 Assessment Year 2025-26
Name of Assessee AKSHAY BHATNAGAR
PART-I - Details of Tax Deducted at Source
1 TERAFINA SOFTWARE SOLUTIONS PRIVATE LIMITED MUMT22660B 300000.00 30000.00 30000.00
1 192 30-Apr-2024 F 08-May-2024 - 100000.00 10000.00 10000.00
2 192 31-May-2024 F 08-Jun-2024 - 200000.00 20000.00 20000.00
"""

    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (id, name, pan, aliases, profile_hints) VALUES (1, 'Akshay', 'BPLPB7839D', '', '')")
        conn.execute(
            """
            INSERT INTO documents (id, original_name, stored_path, file_hash, document_type, status, extracted_json, detected_user_id)
            VALUES (1, '26AS.pdf', ?, 'hash-26as-monthly', 'form26as', 'needs_review', '{}', 1)
            """,
            (str(upload_dir / "26as.pdf"),),
        )
        conn.executemany(
            """
            INSERT INTO income_records
                (user_id, financial_year, record_date, period_label, income_type, payer, gross_amount, net_amount, tds_amount, deductions_amount)
            VALUES (1, 'FY 2024-25', ?, ?, 'salary', 'Terafina Software Solutions Pvt Ltd', ?, ?, ?, 0)
            """,
            [
                ("2024-04-30", "Apr 2024", 100000, 90000, 10000),
                ("2024-05-31", "May 2024", 190000, 171000, 19000),
            ],
        )

    parsed = parse_tax_statement_text(form26as_monthly_text, [])
    save_tax_document_parse(1, parsed, 1, [])

    report = tax_statement_report("1", "FY 2024-25")
    mismatches = [row for row in report["monthly_salary_comparisons"] if row["status"] != "matched"]

    assert report["summary"]["monthly_salary_mismatches"] == 1
    assert mismatches[0]["month"] == "2024-05"
    assert mismatches[0]["amount_difference"] == 10000
    assert mismatches[0]["tds_difference"] == 1000
    assert {finding["type"] for finding in report["findings"]} >= {"salary_month_amount_mismatch", "salary_month_tds_mismatch"}


def test_delete_tax_document_clears_tax_rows_without_touching_salary_records(tmp_path, monkeypatch):
    database, upload_dir = setup_tax_db(tmp_path, monkeypatch)
    from backend.app.repositories import delete_document
    from backend.app.tax_documents import parse_tax_statement_text, save_tax_document_parse
    from backend.app.tax_reconciliation import tax_statement_report

    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (id, name, pan, aliases, profile_hints) VALUES (1, 'Akshay', 'BPLPB7839D', '', '')")
        conn.executemany(
            """
            INSERT INTO documents (id, original_name, stored_path, file_hash, document_type, status, extracted_json, detected_user_id)
            VALUES (?, ?, ?, ?, ?, 'confirmed', '{}', 1)
            """,
            [
                (1, "26AS.pdf", str(upload_dir / "26as.pdf"), "hash-26as-delete", "form26as"),
                (2, "Aug Payslip.pdf", str(upload_dir / "aug.pdf"), "hash-aug", "salary"),
            ],
        )
        conn.execute(
            """
            INSERT INTO income_records
                (id, user_id, document_id, financial_year, record_date, period_label, income_type,
                 payer, gross_amount, net_amount, tds_amount, deductions_amount, metadata_json)
            VALUES (1, 1, 2, 'FY 2024-25', '2024-08-31', 'Aug 2024', 'salary',
                    'Terafina Software Solutions Pvt Ltd', 121956, 84956, 9700, 14000, '{}')
            """,
        )

    parsed = parse_tax_statement_text(FORM26AS_TEXT, [])
    save_tax_document_parse(1, parsed, 1, [])

    assert tax_statement_report("1", "FY 2024-25")["summary"]["active_26as"] == 1

    deleted = delete_document(1)

    assert deleted == {"deleted": True, "id": 1}
    with database.get_connection() as conn:
        salary_row = conn.execute("SELECT * FROM income_records WHERE id = 1").fetchone()
        tax_doc_count = conn.execute("SELECT COUNT(*) AS count FROM tax_documents").fetchone()["count"]
        entry_count = conn.execute("SELECT COUNT(*) AS count FROM tax_statement_entries").fetchone()["count"]
        summary_count = conn.execute("SELECT COUNT(*) AS count FROM tax_statement_summaries").fetchone()["count"]

    assert salary_row["gross_amount"] == 121956
    assert salary_row["document_id"] == 2
    assert tax_doc_count == 0
    assert entry_count == 0
    assert summary_count == 0
    assert tax_statement_report("1", "FY 2024-25")["summary"]["active_26as"] == 0
