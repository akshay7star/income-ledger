from pathlib import Path


def setup_review_db(tmp_path, monkeypatch):
    from backend.app import database

    data_dir = tmp_path / "data"
    upload_dir = data_dir / "uploads"
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(database, "DB_PATH", data_dir / "income_ledger.sqlite3")
    database.init_db()
    upload_dir.mkdir(parents=True, exist_ok=True)
    return database, upload_dir


def test_audit_events_parse_json_and_filter_user(tmp_path, monkeypatch):
    database, _upload_dir = setup_review_db(tmp_path, monkeypatch)
    from backend.app.review import list_audit_events

    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (id, name, aliases, profile_hints) VALUES (1, 'User', '', '')")
        conn.execute(
            """
            INSERT INTO audit_events (user_id, event_type, before_json, after_json)
            VALUES (1, 'add_income_record_manual', '{}', '{"gross_amount": 100}')
            """
        )

    report = list_audit_events(user_id="1")

    assert report["total"] == 1
    assert report["items"][0]["event_type"] == "add_income_record_manual"
    assert report["items"][0]["after"]["gross_amount"] == 100
    assert report["items"][0]["user_name"] == "User"


def test_reconciliation_reports_unlinked_needs_review_and_missing_files(tmp_path, monkeypatch):
    database, upload_dir = setup_review_db(tmp_path, monkeypatch)
    from backend.app.review import reconciliation_report

    existing_pdf = upload_dir / "existing.pdf"
    existing_pdf.write_bytes(b"%PDF-1.4")
    missing_pdf = upload_dir / "missing.pdf"
    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (id, name, aliases, profile_hints) VALUES (1, 'User', '', '')")
        conn.execute(
            """
            INSERT INTO documents
                (id, original_name, stored_path, file_hash, document_type, status, extracted_json, detected_user_id)
            VALUES
                (1, 'existing.pdf', ?, 'hash1', 'salary', 'confirmed', '{"record_date": "2026-04-01"}', 1),
                (2, 'missing.pdf', ?, 'hash2', 'unknown', 'needs_review', '{}', 1)
            """,
            (str(existing_pdf), str(missing_pdf)),
        )
        conn.execute(
            """
            INSERT INTO income_records
                (id, user_id, document_id, financial_year, record_date, period_label, income_type, gross_amount, net_amount)
            VALUES (1, 1, 1, 'FY 2026-27', '2026-04-01', 'Apr 2026', 'salary', 100, 90)
            """
        )

    report = reconciliation_report(user_id="1", financial_year="FY 2026-27")

    assert report["summary"]["linked_documents"] == 1
    assert report["summary"]["unlinked_documents"] == 1
    assert report["summary"]["needs_review"] == 1
    assert report["summary"]["missing_files"] == 1


def test_validation_report_flags_advisory_findings(tmp_path, monkeypatch):
    database, upload_dir = setup_review_db(tmp_path, monkeypatch)
    from backend.app.review import validation_report

    pdf = upload_dir / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (id, name, aliases, profile_hints) VALUES (1, 'User', '', '')")
        conn.execute(
            """
            INSERT INTO income_records
                (id, user_id, financial_year, record_date, period_label, income_type, payer,
                 gross_amount, net_amount, tds_amount, metadata_json)
            VALUES
                (1, 1, 'FY 2026-27', '2026-04-01', 'Apr 2026', 'freelance_invoice', 'Client',
                 100000, 100000, 0, '{"gst_amount": 0}')
            """
        )
        conn.execute(
            """
            INSERT INTO freelance_expenses
                (id, user_id, financial_year, expense_date, category, amount, gst_amount, notes)
            VALUES (1, 1, 'FY 2026-27', '2026-04-02', 'Software', 1000, 180, '')
            """
        )
        conn.execute(
            """
            INSERT INTO documents
                (id, original_name, stored_path, file_hash, document_type, status, extracted_json, detected_user_id)
            VALUES (1, 'invoice.pdf', ?, 'hash1', 'unknown', 'needs_review', '{}', 1)
            """,
            (str(pdf),),
        )

    report = validation_report("1", "FY 2026-27")
    finding_types = {item["type"] for item in report["findings"]}

    assert "freelance_missing_gst" in finding_types
    assert "freelance_tds_variance" in finding_types
    assert "document_needs_review" in finding_types
    assert "expense_without_document" in finding_types
    assert report["summary"]["total"] >= 4
