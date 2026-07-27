# Income Ledger

**Version 0.3.0**

Income Ledger is a local-first finance workspace for Indian salaried and freelance professionals. It brings income records, source PDFs, TDS/GST checks, tax planning, expenses, reconciliation, and GST service invoices into one application.

Financial data stays on the user's computer by default. The application uses a FastAPI API, SQLite database, and React/Vite interface, with optional local OCR/AI and optional user-configured cloud AI.

## What is included

### Income and source documents

- Upload salary slips, freelance invoices, Form 16 Part A/B, and Form 26AS PDFs.
- Extract embedded PDF text first, with optional OCR and local AI fallback for difficult documents.
- Review extracted values before saving them to the ledger.
- Track gross and net income, TDS, PF, VPF, GST, deductions, payer/client, dates, and source files.
- Detect missing PDFs, unlinked documents, validation problems, and record/document mismatches.
- Preserve audit events for important changes.

### Form 16 and Form 26AS reconciliation

- Store Form 16 documents from multiple employers in the same financial year.
- Keep one active Form 26AS per user and financial year while retaining superseded statements for audit.
- Compare employer salary and TDS totals across Form 16, Form 26AS, and ledger records.
- Review month-level salary mismatches and freelance/professional TDS differences.
- Open the affected record for manual review and run reconciliation again.
- Keep reconciliation advisory-only: tax documents never silently overwrite ledger income.

### Tax planning

- Work with Indian financial years from April 1 to March 31.
- Compare estimated old- and new-regime income tax.
- Project year-end income using elapsed financial-year months.
- Plan advance-tax payments and edit planning assumptions.
- Use the optional AI Advisor with structured ledger data; deterministic tax calculations remain in the backend.

### Expenses and workbooks

- Create, edit, filter, and delete expenses.
- Calculate expense GST and track payment methods.
- Export multi-sheet Excel workbooks containing income, expenses, tax summaries, tax documents, reconciliation findings, invoice metadata, and audit data.
- Import supported structured workbook data.

### GST service invoices

Version 0.3.0 adds a complete preview-first invoice workflow:

- Maintain reusable seller profiles and bill-to clients.
- Create invoice drafts with bill-to/ship-to details, place of supply, payment terms, billable period, references, and delivery information.
- Add service lines with particulars, HSN/SAC, quantity, unit, GST rate, and a separate taxable amount.
- Treat `Rate` as the total GST slab—for example, `18%`—rather than the service price.
- For same-state supplies, show the GST deduction as separate CGST and SGST components, including each component's rate and amount. An 18% slab is shown as 9% CGST plus 9% SGST.
- For inter-state supplies, calculate and show IGST separately; no-GST treatment is also supported.
- Enter Expected TDS as a percentage and calculate it on taxable value before GST.
- Show taxable value, each GST component, grand total, expected TDS amount, and net receivable.
- Save a draft and inspect the print-accurate PDF with a visible `DRAFT` watermark before printing, exporting, or issuing it.
- Generate the final non-watermarked PDF through the same renderer used by the preview.
- Lock normal edits after issue and preserve issued/cancelled PDFs and audit history.
- Optionally create a linked freelance-income record using taxable service value before GST as gross income.
- Include generated invoice PDFs in local backups and invoice metadata in workbook exports.
- Migrate older fixed-TDS and unit-rate invoice drafts to the current percentage/amount model.

The PDF layout is based on the supplied Gen Aquarius service-invoice example. This release does not generate e-invoice IRNs or integrate with the GST portal.

### Local operation and security

- Protect the application with a local PIN and session lock.
- Remember default user, financial year, theme, and local AI preferences.
- Create and restore ZIP backups containing the database, uploaded documents, and generated invoice PDFs.
- Continue restoring older backups by running the required database migrations afterward.

## Architecture

```text
React + Vite browser UI
          |
          v
      FastAPI API
          |
          +-- SQLite ledger
          +-- Uploaded source documents
          +-- Generated invoice PDFs
          +-- Local ZIP backups
```

## Technology

- Python 3.12+, FastAPI, Pydantic, SQLite
- React, Vite, Bootstrap, Lucide, Recharts
- pypdf, PyMuPDF, optional Tesseract OCR
- ReportLab for deterministic invoice PDFs
- OpenPyXL for Excel import/export
- pytest for backend and PDF regression coverage

## Quick start on Windows

Requirements:

- Python 3.12 or newer
- Node.js and npm
- Optional: Tesseract and Poppler for scanned/image-only PDFs

From the project root, run:

```powershell
.\Start-IncomeLedger.ps1
```

You can also double-click `Start-IncomeLedger.bat`.

The launcher creates or reuses `.venv`, installs the backend and frontend dependencies, starts both services, and opens the application:

- App: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8001`
- Interactive API docs: `http://127.0.0.1:8001/docs`

## Manual development

Install dependencies from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm.cmd install
```

Start the backend in one terminal:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Start the frontend in another terminal:

```powershell
cd frontend
npm.cmd run dev
```

## Configuration

The application reads `.env` settings from the project tree. Most AI-related preferences can also be changed in Settings.

Optional local AI extraction fallback:

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

The cloud API key is entered through Settings and is not required for normal ledger, invoice, reconciliation, or tax-calculation features.

### OCR for scanned PDFs

Digital PDFs are parsed from embedded text first. For scanned or image-only PDFs, install:

- [Tesseract OCR for Windows](https://github.com/UB-Mannheim/tesseract/wiki)
- [Poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases/) when PDF-to-image conversion is required

## Main workflows

### Review and reconcile tax documents

1. Upload income documents and confirm the extracted records.
2. Upload Form 16 Part A/B and Form 26AS for the relevant user and financial year.
3. Open Reconcile and inspect employer totals, active 26AS status, monthly mismatches, and findings.
4. Open the referenced record to correct source data when necessary.
5. Select `Recheck` to refresh the comparison.

### Create and issue an invoice

1. Open `Invoices` and select or create the seller and client.
2. Enter invoice details and service lines. Use `Rate` for the GST percentage and `Amount` for taxable service value.
3. Choose same-state CGST/SGST, inter-state IGST, or no GST.
4. Enter Expected TDS as a percentage of taxable value.
5. Save the draft and inspect the PDF preview.
6. Correct the draft if needed, then issue and download/print the final PDF.
7. Optionally create a linked freelance-income record.

### Back up local data

Use the in-app backup feature before moving machines or making major data changes. A backup contains the SQLite database, uploaded documents, and generated invoice PDFs.

## Data and privacy

Runtime financial data is kept under `data/` and is excluded from Git:

```text
data/
  income_ledger.sqlite3
  uploads/
  generated_invoices/
  backups/
```

Do not commit real tax documents, generated invoices, backups, `.env` files, or API keys. Cloud AI is optional and is used only when the user configures and invokes it.

## Tests and production build

Run the backend test suite from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp C:\tmp\income-ledger-pytest
```

Build the frontend:

```powershell
cd frontend
npm.cmd run build
```

Invoice coverage includes API lifecycle, GST/TDS calculations, migrations, backup/workbook integration, and generated-PDF regression checks.

## Project structure

```text
backend/app/                 FastAPI routes and domain services
frontend/src/                React views and application styles
tests/                       Backend and integration tests
data/                        Local runtime data (Git-ignored)
Start-IncomeLedger.ps1       Windows launcher
CHANGELOG.md                 Release history
```

## Current limitations

- Tax results are estimates and should be checked against the applicable law and a qualified tax professional.
- GST/HSN/SAC choices must be verified by the user; the application does not replace professional classification advice.
- There is no GST portal filing, e-invoice IRN generation, email delivery, payment link, recurring invoice, inventory, multi-currency, or credit/debit note integration yet.
- The bundled launcher targets Windows; the backend and frontend can be started manually on other operating systems.

## Release history

- **v0.3.0 — 2026-07-27:** Preview-first GST invoices, separate taxable amount and GST rate, split CGST/SGST display, percentage-based TDS, generated-PDF backups, workbook integration, and invoice regression coverage.
- **v0.2.0 — 2026-07-27:** Editable expenses, GST/payment tracking, improved compact Tally invoice extraction, theme persistence, and safer backup migrations.
- **v0.1.2 — 2026-06-09:** Improved document deletion and financial-year tax projection.
- **v0.1.1 — 2026-06-08:** Expense cascade tests and interface/theme improvements.

See [CHANGELOG.md](CHANGELOG.md) for complete release notes.
