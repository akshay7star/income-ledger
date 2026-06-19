# Income Ledger

Income Ledger is a local-first finance dashboard for Indian salaried and freelance professionals. It helps parse salary slips, freelance invoices, Form 16 Part A/B, and Form 26AS; reconcile records against source documents; estimate tax; and export clean workbook data without sending private financial documents to a third-party service by default.

The app runs on your machine with a FastAPI backend, SQLite database, and React/Vite frontend.

## Features

- **PDF income extraction**: Upload salary slips and freelance invoices to extract gross, net, TDS, PF, VPF, GST, deductions, payer/client, and date fields.
- **Manual review before save**: Extracted income data is reviewed and confirmed by the user before it becomes ledger data.
- **Form 16 and 26AS reconciliation**:
  - Upload multiple Form 16 Part A/B documents for multiple employers in the same financial year.
  - Keep one active Form 26AS per user and financial year, with superseded statements preserved until deleted.
  - Compare employer salary totals, TDS, Form 16 totals, 26AS section 192 rows, and ledger salary records.
  - Show month-level mismatch details so the user can see exactly which month differs from 26AS.
  - Keep reconciliation advisory-only. The app suggests what to review but does not auto-update salary records from 26AS.
  - Delete Form 16/26AS documents from Reconcile without deleting salary or freelance records.
- **Freelance and professional TDS checks**: Compare ledger freelance receipts/TDS against 26AS professional/contract sections where available.
- **Validation and audit tools**: Missing PDF checks, linked/unlinked document reports, validation findings, and audit history.
- **Tax planner**: Indian FY tax estimates, regime comparison, advance-tax planning, and editable planning inputs.
- **AI Advisor**: Optional cloud/custom AI advisory chat using structured app data. Deterministic tax calculations remain in the backend.
- **Excel import/export**: Export multi-sheet workbooks with records, expenses, tax summaries, tax documents, tax reconciliation, and findings. Import structured workbook data.
- **Backup and restore**: Local ZIP backups include database and uploaded documents.
- **App lock and settings**: Local PIN/session lock, default user/FY preferences, local AI settings, and optional cloud AI settings.

## Tech Stack

- **Backend**: FastAPI, Python 3.12+, SQLite
- **PDF/OCR**: `pypdf`, PyMuPDF, optional Tesseract OCR
- **Frontend**: React, Vite, Bootstrap, custom CSS
- **Charts**: Recharts
- **Workbook support**: OpenPyXL

## Quick Start on Windows

Run the launcher from the project root:

```powershell
.\Start-IncomeLedger.ps1
```

Or double-click:

```text
Start-IncomeLedger.bat
```

The startup script:

1. Creates or reuses `.venv`.
2. Installs backend dependencies from `requirements.txt`.
3. Installs frontend dependencies from `frontend/package.json`.
4. Starts the backend at `http://127.0.0.1:8001`.
5. Starts the frontend at `http://127.0.0.1:5173`.
6. Opens the app in your browser.

## Manual Development Commands

Backend:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Frontend:

```powershell
cd frontend
npm.cmd run dev
```

Build frontend:

```powershell
cd frontend
npm.cmd run build
```

Focused tax-document tests:

```powershell
C:\Users\aksha\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests\test_tax_documents.py -q --basetemp C:\tmp\income-ledger-pytest
```

## Configuration

The app reads `.env` from the project tree and also supports changing most settings from the Settings screen.

Local AI extraction fallback:

```env
LOCAL_AI_BASE_URL=http://127.0.0.1:1234/v1
LOCAL_AI_API_KEY=lm-studio
LOCAL_AI_MODEL=google/gemma-4-e4b
LOCAL_AI_TIMEOUT_SECONDS=120
LOCAL_AI_RENDERED_PAGES=1
```

Optional cloud/custom AI Advisor:

```env
CLOUD_AI_BASE_URL=https://api.openai.com/v1
CLOUD_AI_MODEL=
```

The cloud AI API key is stored through the app Settings screen and is not required for local extraction or tax calculations.

## OCR Requirements

Digital PDFs are parsed from embedded text first. For scanned or image-only PDFs, install:

- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
- [Poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases/) if your OCR path needs PDF image conversion

## Form 16 and 26AS Workflow

1. Upload salary slips, Form 16 Part A/B, and Form 26AS PDFs.
2. Open Reconcile for a specific user and financial year.
3. Review employer totals, active 26AS status, monthly mismatch rows, and tax findings.
4. If a mismatch points to one payslip, use `Open review` to manually correct and confirm that source document.
5. Press `Recheck` to refresh the reconciliation report.

Tax documents never silently rewrite ledger income. They provide evidence and warnings only.

## Notes

- Financial years follow the Indian FY calendar: April 1 to March 31.
- Form 16 Part A/B supports multiple employers per FY.
- Form 26AS is treated as one annual government-side statement per user/FY.
- Superseded 26AS documents are kept for audit/history until deleted.
