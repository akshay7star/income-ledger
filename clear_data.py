import sqlite3
import os
import shutil
from pathlib import Path

# Paths relative to the project root
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "income_ledger.sqlite3"

def clear_all_data():
    print("Starting cleanup of local Income Ledger data...")
    
    # 1. Clear database tables
    if DB_PATH.exists():
        try:
            print(f"Connecting to database at {DB_PATH}...")
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Disable foreign key constraints temporarily to avoid deletion order issues
            cursor.execute("PRAGMA foreign_keys = OFF")
            
            # List of tables to clear
            tables = ["audit_events", "income_records", "freelance_expenses", "documents", "users"]
            for table in tables:
                # Check if table exists before trying to clear it
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                if cursor.fetchone():
                    cursor.execute(f"DELETE FROM {table}")
                    print(f"  - Cleared table: {table}")
            
            # Reset autoincrement sequences
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
            if cursor.fetchone():
                cursor.execute("DELETE FROM sqlite_sequence")
                print("  - Reset auto-increment sequences")
                
            conn.commit()
            cursor.execute("PRAGMA foreign_keys = ON")
            conn.close()
            print("Database tables cleared successfully.")
        except Exception as e:
            print(f"Error clearing database tables: {e}")
    else:
        print(f"Database not found at {DB_PATH}. Skipping database clear.")

    # 2. Clear uploaded files
    if UPLOAD_DIR.exists():
        try:
            print(f"Clearing files in uploads directory: {UPLOAD_DIR}...")
            count = 0
            for item in UPLOAD_DIR.iterdir():
                if item.is_file():
                    # Keep temporary upload files or placeholders if any, but clear PDFs
                    item.unlink()
                    count += 1
            print(f"  - Deleted {count} file(s) from uploads directory.")
        except Exception as e:
            print(f"Error clearing upload files: {e}")
    else:
        print(f"Uploads directory not found at {UPLOAD_DIR}. Skipping file cleanup.")

    print("Cleanup complete. Your local dashboard should now be completely empty!")

if __name__ == "__main__":
    clear_all_data()
