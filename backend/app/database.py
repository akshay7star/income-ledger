from contextlib import contextmanager
import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
GENERATED_INVOICE_DIR = DATA_DIR / "generated_invoices"
DB_PATH = DATA_DIR / "income_ledger.sqlite3"


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    (DATA_DIR / GENERATED_INVOICE_DIR.name).mkdir(exist_ok=True)


@contextmanager
def get_connection():
    ensure_data_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def init_db() -> None:
    ensure_data_dirs()
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                pan TEXT,
                aliases TEXT NOT NULL DEFAULT '',
                profile_hints TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                file_hash TEXT NOT NULL UNIQUE,
                document_type TEXT NOT NULL,
                status TEXT NOT NULL,
                extracted_text TEXT NOT NULL DEFAULT '',
                extracted_json TEXT NOT NULL DEFAULT '{}',
                detected_user_id INTEGER,
                confidence REAL NOT NULL DEFAULT 0,
                warnings TEXT NOT NULL DEFAULT '[]',
                uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(detected_user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS income_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                document_id INTEGER,
                financial_year TEXT NOT NULL,
                record_date TEXT NOT NULL,
                period_label TEXT NOT NULL,
                income_type TEXT NOT NULL,
                payer TEXT,
                gross_amount REAL NOT NULL DEFAULT 0,
                net_amount REAL NOT NULL DEFAULT 0,
                tds_amount REAL NOT NULL DEFAULT 0,
                deductions_amount REAL NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS freelance_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                financial_year TEXT NOT NULL,
                expense_date TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                gst_amount REAL NOT NULL DEFAULT 0,
                payment_method TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER,
                user_id INTEGER,
                event_type TEXT NOT NULL,
                before_json TEXT NOT NULL DEFAULT '{}',
                after_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(document_id) REFERENCES documents(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS invoice_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT NOT NULL,
                legal_name TEXT NOT NULL DEFAULT '',
                address_line1 TEXT NOT NULL DEFAULT '',
                address_line2 TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                state_name TEXT NOT NULL DEFAULT '',
                state_code TEXT NOT NULL DEFAULT '',
                postal_code TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                gstin TEXT NOT NULL DEFAULT '',
                pan TEXT NOT NULL DEFAULT '',
                bank_name TEXT NOT NULL DEFAULT '',
                bank_account_name TEXT NOT NULL DEFAULT '',
                bank_account_number TEXT NOT NULL DEFAULT '',
                bank_ifsc TEXT NOT NULL DEFAULT '',
                signature_label TEXT NOT NULL DEFAULT 'Authorised Signatory',
                is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS invoice_clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                legal_name TEXT NOT NULL DEFAULT '',
                address_line1 TEXT NOT NULL DEFAULT '',
                address_line2 TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                state_name TEXT NOT NULL DEFAULT '',
                state_code TEXT NOT NULL DEFAULT '',
                postal_code TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                gstin TEXT NOT NULL DEFAULT '',
                pan TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS generated_invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT NOT NULL,
                invoice_date TEXT NOT NULL,
                financial_year TEXT NOT NULL,
                billable_period TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'issued', 'cancelled')),
                seller_profile_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,
                ledger_user_id INTEGER,
                place_of_supply TEXT NOT NULL DEFAULT '',
                gst_treatment TEXT NOT NULL DEFAULT 'same_state' CHECK (gst_treatment IN ('same_state', 'inter_state', 'no_gst')),
                payment_terms TEXT NOT NULL DEFAULT '',
                due_date TEXT,
                delivery_note TEXT NOT NULL DEFAULT '',
                reference_number TEXT NOT NULL DEFAULT '',
                reference_date TEXT,
                other_references TEXT NOT NULL DEFAULT '',
                buyer_order_number TEXT NOT NULL DEFAULT '',
                buyer_order_date TEXT,
                dispatch_document_number TEXT NOT NULL DEFAULT '',
                delivery_note_date TEXT,
                dispatched_through TEXT NOT NULL DEFAULT '',
                destination TEXT NOT NULL DEFAULT '',
                terms_of_delivery TEXT NOT NULL DEFAULT '',
                ship_to_same_as_bill_to INTEGER NOT NULL DEFAULT 1 CHECK (ship_to_same_as_bill_to IN (0, 1)),
                ship_to_name TEXT NOT NULL DEFAULT '',
                ship_to_address_line1 TEXT NOT NULL DEFAULT '',
                ship_to_address_line2 TEXT NOT NULL DEFAULT '',
                ship_to_city TEXT NOT NULL DEFAULT '',
                ship_to_state_name TEXT NOT NULL DEFAULT '',
                ship_to_state_code TEXT NOT NULL DEFAULT '',
                ship_to_postal_code TEXT NOT NULL DEFAULT '',
                ship_to_gstin TEXT NOT NULL DEFAULT '',
                subtotal_amount REAL NOT NULL DEFAULT 0,
                cgst_amount REAL NOT NULL DEFAULT 0,
                sgst_amount REAL NOT NULL DEFAULT 0,
                igst_amount REAL NOT NULL DEFAULT 0,
                gst_amount REAL NOT NULL DEFAULT 0,
                grand_total_amount REAL NOT NULL DEFAULT 0,
                tds_rate REAL NOT NULL DEFAULT 0,
                tds_amount REAL NOT NULL DEFAULT 0,
                net_receivable_amount REAL NOT NULL DEFAULT 0,
                amount_words TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                pdf_path TEXT NOT NULL DEFAULT '',
                income_record_id INTEGER,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                issued_at TEXT,
                FOREIGN KEY(seller_profile_id) REFERENCES invoice_profiles(id) ON DELETE RESTRICT,
                FOREIGN KEY(client_id) REFERENCES invoice_clients(id) ON DELETE RESTRICT,
                FOREIGN KEY(ledger_user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY(income_record_id) REFERENCES income_records(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS generated_invoice_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                line_number INTEGER NOT NULL,
                description TEXT NOT NULL,
                hsn_sac TEXT NOT NULL DEFAULT '',
                quantity REAL NOT NULL,
                unit TEXT NOT NULL DEFAULT '',
                rate REAL NOT NULL,
                taxable_amount REAL NOT NULL,
                gst_rate REAL NOT NULL DEFAULT 0,
                cgst_rate REAL NOT NULL DEFAULT 0,
                sgst_rate REAL NOT NULL DEFAULT 0,
                igst_rate REAL NOT NULL DEFAULT 0,
                cgst_amount REAL NOT NULL DEFAULT 0,
                sgst_amount REAL NOT NULL DEFAULT 0,
                igst_amount REAL NOT NULL DEFAULT 0,
                total_amount REAL NOT NULL,
                FOREIGN KEY(invoice_id) REFERENCES generated_invoices(id) ON DELETE CASCADE,
                UNIQUE(invoice_id, line_number)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_generated_invoices_fy_number
                ON generated_invoices(financial_year, invoice_number);
            CREATE INDEX IF NOT EXISTS idx_generated_invoices_status_date
                ON generated_invoices(status, invoice_date);
            CREATE INDEX IF NOT EXISTS idx_generated_invoices_seller
                ON generated_invoices(seller_profile_id);
            CREATE INDEX IF NOT EXISTS idx_generated_invoices_client
                ON generated_invoices(client_id);
            CREATE INDEX IF NOT EXISTS idx_generated_invoices_ledger_user
                ON generated_invoices(ledger_user_id);

            CREATE TABLE IF NOT EXISTS tax_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                user_id INTEGER,
                financial_year TEXT NOT NULL,
                assessment_year TEXT NOT NULL,
                source_type TEXT NOT NULL,
                pan TEXT,
                tan TEXT,
                deductor_name TEXT,
                certificate_number TEXT,
                period_from TEXT,
                period_to TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                superseded_by_tax_document_id INTEGER,
                confidence REAL NOT NULL DEFAULT 0,
                raw_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(superseded_by_tax_document_id) REFERENCES tax_documents(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS tax_statement_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tax_document_id INTEGER NOT NULL,
                user_id INTEGER,
                financial_year TEXT NOT NULL,
                assessment_year TEXT NOT NULL,
                source_type TEXT NOT NULL,
                section TEXT,
                income_bucket TEXT,
                transaction_date TEXT,
                booking_date TEXT,
                booking_status TEXT,
                quarter TEXT,
                tan TEXT,
                deductor_name TEXT,
                amount_paid REAL NOT NULL DEFAULT 0,
                tax_deducted REAL NOT NULL DEFAULT 0,
                tax_deposited REAL NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(tax_document_id) REFERENCES tax_documents(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tax_statement_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tax_document_id INTEGER NOT NULL,
                user_id INTEGER,
                financial_year TEXT NOT NULL,
                assessment_year TEXT NOT NULL,
                source_type TEXT NOT NULL,
                income_bucket TEXT,
                tan TEXT,
                deductor_name TEXT,
                gross_salary REAL NOT NULL DEFAULT 0,
                salary_17_1 REAL NOT NULL DEFAULT 0,
                perquisites_17_2 REAL NOT NULL DEFAULT 0,
                profit_in_lieu_17_3 REAL NOT NULL DEFAULT 0,
                exempt_allowances_10 REAL NOT NULL DEFAULT 0,
                standard_deduction_16ia REAL NOT NULL DEFAULT 0,
                professional_tax_16iii REAL NOT NULL DEFAULT 0,
                income_chargeable_salary REAL NOT NULL DEFAULT 0,
                other_income_reported REAL NOT NULL DEFAULT 0,
                chapter_via_deductions REAL NOT NULL DEFAULT 0,
                taxable_income REAL NOT NULL DEFAULT 0,
                tax_payable REAL NOT NULL DEFAULT 0,
                tds_deducted REAL NOT NULL DEFAULT 0,
                tds_deposited REAL NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(tax_document_id) REFERENCES tax_documents(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_tax_documents_user_fy_type
                ON tax_documents(user_id, financial_year, source_type, tan, certificate_number);
            CREATE INDEX IF NOT EXISTS idx_tax_entries_user_fy_bucket
                ON tax_statement_entries(user_id, financial_year, income_bucket, tan);
            CREATE INDEX IF NOT EXISTS idx_tax_summaries_user_fy_bucket
                ON tax_statement_summaries(user_id, financial_year, income_bucket, tan);
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(freelance_expenses)").fetchall()}
        if "gst_amount" not in columns:
            conn.execute("ALTER TABLE freelance_expenses ADD COLUMN gst_amount REAL NOT NULL DEFAULT 0")
            conn.commit()
        if "payment_method" not in columns:
            conn.execute("ALTER TABLE freelance_expenses ADD COLUMN payment_method TEXT NOT NULL DEFAULT ''")
            conn.commit()
        invoice_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(generated_invoices)").fetchall()
        }
        if "tds_rate" not in invoice_columns:
            conn.execute(
                "ALTER TABLE generated_invoices ADD COLUMN tds_rate REAL NOT NULL DEFAULT 0"
            )
            conn.execute(
                """
                UPDATE generated_invoices
                SET tds_rate = ROUND(tds_amount * 100.0 / subtotal_amount, 6)
                WHERE subtotal_amount > 0 AND tds_amount > 0
                """
            )
            conn.commit()
