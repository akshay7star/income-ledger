# Income Ledger

Local-only dashboard for salary slips and freelance invoices. It extracts income data from PDFs, groups records by Indian financial year, and estimates new-regime income tax.

## Quick start

On Windows, run:

```powershell
.\Start-IncomeLedger.ps1
```

For double-click launch, use `Start-IncomeLedger.bat`. The launcher creates a Python virtual environment, installs backend dependencies, starts the API, starts the React dashboard, and opens the app in your browser. If the app is already running, it reuses the existing local servers.

## Project layout

- `backend/` - FastAPI API, SQLite storage, PDF extraction, tax logic.
- `frontend/` - React/Vite dashboard.
- `tests/` - Python unit tests for financial year, tax, extraction, and matching logic.
- `data/` - Runtime database and uploaded PDFs. This folder is created automatically and is ignored by Git.

## Notes

- Data stays local on this PC.
- OCR is optional. Text-based PDFs work with `pypdf`; scanned PDFs can use OCR if Tesseract and Poppler are installed locally.
- Tax calculation is India-focused and intended as an estimate, not filing advice.
- Tax slabs are stored for FY 2017-18 through FY 2026-27. Old-regime rates are available for all 10 years; new-regime rates are available from FY 2020-21 onward.
- The app selects the default regime for the selected financial year and also returns old/new comparisons where both regimes exist.
- Current-year constants use Income Tax Department / Income-tax Act 2025 material for the Rs 12 lakh new-regime rebate threshold, 4% cess, and Rs 75,000 salary standard deduction.
- Surcharge, senior-citizen slabs, special-rate income, and marginal relief are not yet modeled.
- Local ports: dashboard `http://127.0.0.1:5173`, API `http://127.0.0.1:8001`.
