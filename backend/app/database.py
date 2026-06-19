from contextlib import contextmanager
import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "income_ledger.sqlite3"


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)


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
