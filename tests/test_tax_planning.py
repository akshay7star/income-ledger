def setup_planning_db(tmp_path, monkeypatch):
    from backend.app import database

    data_dir = tmp_path / "data"
    upload_dir = data_dir / "uploads"
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(database, "DB_PATH", data_dir / "income_ledger.sqlite3")
    database.init_db()
    upload_dir.mkdir(parents=True, exist_ok=True)
    return database


def test_tax_planning_does_not_apply_nps_without_opt_in(tmp_path, monkeypatch):
    database = setup_planning_db(tmp_path, monkeypatch)
    from backend.app.tax_planning import tax_planning_report

    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (id, name, aliases, profile_hints) VALUES (1, 'User', '', '')")
        conn.execute(
            """
            INSERT INTO income_records
                (user_id, financial_year, record_date, period_label, income_type, payer,
                 gross_amount, net_amount, tds_amount, metadata_json)
            VALUES (1, 'FY 2025-26', '2025-04-30', 'Apr 2025', 'salary', 'Employer',
                    1600000, 1500000, 100000, '{}')
            """
        )

    report = tax_planning_report("1", "FY 2025-26")

    assert report["breakdown"]["employer_nps_deduction"] == 0
    assert any(item["status"] == "possible" and "NPS" in item["title"] for item in report["recommendations"])


def test_tax_planning_applies_enabled_nps_with_cap(tmp_path, monkeypatch):
    database = setup_planning_db(tmp_path, monkeypatch)
    from backend.app.tax_planning import tax_planning_report, update_planning_inputs

    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (id, name, aliases, profile_hints) VALUES (1, 'User', '', '')")
        conn.execute(
            """
            INSERT INTO income_records
                (user_id, financial_year, record_date, period_label, income_type, payer,
                 gross_amount, net_amount, tds_amount, metadata_json)
            VALUES (1, 'FY 2025-26', '2025-04-30', 'Apr 2025', 'salary', 'Employer',
                    1600000, 1500000, 100000, '{}')
            """
        )
    update_planning_inputs("1", "FY 2025-26", {"employer_nps_enabled": True, "employer_nps_amount": 200000, "basic_da_salary": 1000000})

    report = tax_planning_report("1", "FY 2025-26")

    assert report["breakdown"]["employer_nps_deduction"] == 140000
    assert report["tax"]["taxable_income"] < report["base_tax_without_planning"]["taxable_income"]


def test_tax_planning_recommends_itr4_for_44ada(tmp_path, monkeypatch):
    database = setup_planning_db(tmp_path, monkeypatch)
    from backend.app.tax_planning import tax_planning_report, update_planning_inputs

    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (id, name, aliases, profile_hints) VALUES (1, 'User', '', '')")
        conn.execute(
            """
            INSERT INTO income_records
                (user_id, financial_year, record_date, period_label, income_type, payer,
                 gross_amount, net_amount, tds_amount, metadata_json)
            VALUES (1, 'FY 2025-26', '2025-05-01', 'May 2025', 'freelance_invoice', 'Client',
                    1000000, 900000, 100000, '{"gst_amount": 180000}')
            """
        )
    update_planning_inputs("1", "FY 2025-26", {"freelance_method": "44ADA"})

    report = tax_planning_report("1", "FY 2025-26")

    assert report["itr"]["suggested_form"] == "ITR-4"
    assert report["scenarios"]["presumptive_44ada"]["freelance_profit"] == 500000


def test_cloud_ai_analysis_requires_configured_key(tmp_path, monkeypatch):
    database = setup_planning_db(tmp_path, monkeypatch)
    from backend.app.settings import update_settings
    from backend.app.tax_planning import cloud_ai_analysis

    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (id, name, aliases, profile_hints) VALUES (1, 'User', '', '')")

    update_settings({"cloud_ai_model": "tax-model"})

    try:
        cloud_ai_analysis("1", "FY 2025-26")
    except ValueError as exc:
        assert "API key" in str(exc)
    else:
        raise AssertionError("Expected missing Cloud AI API key to fail")


def test_cloud_ai_root_base_url_prefers_openai_v1_chat_path():
    from backend.app.tax_planning import _cloud_chat_urls

    assert _cloud_chat_urls("http://192.168.1.10:1234") == [
        "http://192.168.1.10:1234/v1/chat/completions",
        "http://192.168.1.10:1234/chat/completions",
    ]
    assert _cloud_chat_urls("http://192.168.1.10:1234/v1") == [
        "http://192.168.1.10:1234/v1/chat/completions",
    ]


def test_cloud_ai_timeout_detection_handles_wrapped_reasons():
    from backend.app.tax_planning import _is_timeout_reason

    assert _is_timeout_reason(TimeoutError("timed out"))
    assert _is_timeout_reason("request timed out")
    assert not _is_timeout_reason("connection refused")
