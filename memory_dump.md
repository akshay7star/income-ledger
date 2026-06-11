# Project Handover & Memory Dump: Income Ledger

This document serves as a complete memory snapshot and project context to facilitate migrating development of the **Income Ledger** application to another platform.

---

## 📌 Executive Summary & Project State

* **App Name**: Income Ledger (Salary, Freelance Income, Expense & GST Tracking)
* **Stack**: FastAPI (Python 3.12) + SQLite (DB) | React 18 (Vite, JS) | Bootstrap 5 + Custom CSS
* **Current Version**: `v0.1.5`
* **Latest Codex Implementation (2026-06-11)**: Codex improved user matching to prevent duplicate users from reversed names and small spelling/OCR variations. The backend direct suite passes with 47 tests.
* **Key Achievements**:
  * **Resilient local-only fallback PDF extraction pipeline**: `Local Python Regex -> Local Hosted AI (LM Studio) -> Needs Review (Manual Form)`.
  * **Resilience fixes**: Both frontend fetch calls and backend endpoints are heavily guarded with try-catch/except blocks. Network/FastAPI failures in early stages do not break the chain; the pipeline proceeds to subsequent stages with clean, user-friendly feedback.
  * **Precise user-facing status messages**: Statuses progress step-by-step to show the exact state of fallback transitions.
  * **Expense tracking**: Extracted documents can be reviewed as expenses, classified into predefined categories using regex word boundaries, verified with math rules, and confirmed to the database.

---

## 🗺️ Tech Stack & Port Map

* **FastAPI Backend**: Runs on `http://127.0.0.1:8001` (dev task-261).
* **React Frontend**: Runs on `http://localhost:5173`.
* **Database File**: Mapped to [income_ledger.sqlite3](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/data/income_ledger.sqlite3).

---

## 📂 Active Core Codebase Map

### Backend (FastAPI, Python)
1. **[`backend/app/main.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/main.py)**:
   * REST endpoints (`/api/documents/upload`, `/api/documents/{id}/re-extract`, `/api/expenses`, `/api/health`).
   * **Stage 1 (Local stage)** is protected under a try-except block to return `success: false` and a fallback database document instead of raising a 500 server crash.
2. **[`backend/app/extraction.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/extraction.py)**:
   * PDF reading (`pypdf`), local OCR fallback (`pytesseract`), regex parsing, and AI model routing prompts.
   * `classify_expense_category()` maps expenses using word boundaries (e.g. `\bair\b` to category `Travel`).
3. **[`backend/app/repositories.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/repositories.py)**:
   * DB Operations. `confirm_extraction()` routes expense confirmation to freelance expenses. Aggregates monthly figures and runs math checks (`expected_net` vs `net`).

### Frontend (React, JS)
1. **[`frontend/src/main.jsx`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/frontend/src/main.jsx)**:
   * Dashboard charts (Recharts monthly trends and comparative tax regime line graphs).
   * **`processUploadQueue()`**: Orchestrates the extraction. Wrapped in modular try-catch blocks to run Stage 1 local Python, fallback to Local Hosted LM Studio AI, and finally show the manual review message.
2. **[`frontend/src/styles.css`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/frontend/src/styles.css)**:
   * Glassmorphism, 3D ambient blobs, layout styles, and theme variables (dark/light toggles).

---

## 🔄 The Progressive Extraction Pipeline Flow

When the user uploads a PDF document via the UI:

```mermaid
graph TD
    A[User Uploads PDF] --> B[Stage 1: Local Python Parser]
    B -- Success --> C[Auto-Confirm / Save]
    B -- Failure / Exception --> D[Show Status: 'Local Python extraction needs help. Moving to Local Hosted LM Studio AI.']
    D --> E[Stage 2: Local Hosted AI (LM Studio)]
    E -- Success --> C
    E -- Failure / Exception --> F[Show Status: 'Please manually check and fill details']
    F --> G[Open Manual Review Form]
```

### Exact Status Messages Mapped:
1. **Local Python failed**: `"Local Python extraction needs help. Moving to Local Hosted LM Studio AI."`
2. **Local Hosted AI (LM Studio) also failed**: `"Please manually check and fill details..."` with the local AI failure detail.

---

## 🛠️ Verification commands & Environment Setup

Run the following commands in the workspace root to check that everything compiles and passes clean:

> **Current local caveat (2026-06-11 Codex)**: The workspace `.venv` launcher currently points to a missing Python install, and plain `pytest` collection also hits root-level `scratch_test.py` plus unreadable `tests/tmp`. Until that is cleaned up, use the bundled Codex Python direct-suite command below for the reliable backend baseline.

### 1. Run Unit Tests (Backend)
Tests assert deletion cascades, regex extractions, tax brackets, and math warning triggers:
```bash
.\.venv\Scripts\python.exe -m pytest --basetemp .tmp_pytest
```
*Expected: 39 passed.*

Reliable fallback command used by Codex on 2026-06-11:
```bash
C:\Users\aksha\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_deletion.py tests\test_extraction.py tests\test_financial_year.py tests\test_tax.py tests\test_tax_projection.py tests\test_user_matching.py tests\test_validation.py -p no:cacheprovider
```
*Observed: 39 passed.*

Current direct-suite command after Session 11 changes:
```bash
C:\Users\aksha\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_deletion.py tests\test_extraction.py tests\test_financial_year.py tests\test_tax.py tests\test_tax_projection.py tests\test_user_matching.py tests\test_validation.py -p no:cacheprovider --basetemp C:\tmp\pytest-income-ledger
```
*Observed: 41 passed.*

Current direct-suite command after ExoEdge Apr 2026 parser fix:
```bash
C:\Users\aksha\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_deletion.py tests\test_extraction.py tests\test_financial_year.py tests\test_tax.py tests\test_tax_projection.py tests\test_user_matching.py tests\test_validation.py -p no:cacheprovider --basetemp C:\tmp\pytest-income-ledger
```
*Observed before Cloud AI removal: 42 passed.*

Current direct-suite command after Cloud AI removal:
```bash
C:\Users\aksha\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_deletion.py tests\test_extraction.py tests\test_financial_year.py tests\test_tax.py tests\test_tax_projection.py tests\test_user_matching.py tests\test_validation.py -p no:cacheprovider --basetemp C:\tmp\pytest-income-ledger
```
*Observed: 41 passed.*

Current direct-suite command after freelance GST fix:
```bash
C:\Users\aksha\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_deletion.py tests\test_extraction.py tests\test_financial_year.py tests\test_tax.py tests\test_tax_projection.py tests\test_user_matching.py tests\test_validation.py -p no:cacheprovider --basetemp C:\tmp\pytest-income-ledger
```
*Observed: 43 passed.*

Current direct-suite command after older Terafina salary slip fix:
```bash
C:\Users\aksha\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_deletion.py tests\test_extraction.py tests\test_financial_year.py tests\test_tax.py tests\test_tax_projection.py tests\test_user_matching.py tests\test_validation.py -p no:cacheprovider --basetemp C:\tmp\pytest-income-ledger
```
*Observed: 45 passed.*

Current direct-suite command after fuzzy user matching:
```bash
C:\Users\aksha\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_deletion.py tests\test_extraction.py tests\test_financial_year.py tests\test_tax.py tests\test_tax_projection.py tests\test_user_matching.py tests\test_validation.py -p no:cacheprovider --basetemp C:\tmp\pytest-income-ledger
```
*Observed: 47 passed.*

### 2. Build Frontend Check
Verifies React production bundle builds cleanly under Vite:
```bash
cd frontend
npm run build
```
*Expected: Builds successfully in <1s.*

### 3. Clear/Reset Data
Use this script if you need to wipe out the database and temporary uploads folder to start clean:
```bash
python clear_data.py
```

---

## 🚀 Key Context & Configurations

1. **LLM Connection Settings (.env)**:
   The backend connects to LLMs via standard `.env` variables located at the project root. Customize these parameters to point to LM Studio, OpenAI, or other providers:
   ```env
   LOCAL_AI_BASE_URL=http://127.0.0.1:1234/v1
   LOCAL_AI_API_KEY=lm-studio
   LOCAL_AI_MODEL=google/gemma-2-9b-it
   ```
2. **Cloud AI removed**:
   Remote AI providers are intentionally not part of the active pipeline. `ai_provider` values from stale clients are ignored and routed to Local Hosted LM Studio AI.

---

## 📋 Next Action Items for the Next Agent / Platform

0. **Active known bug: expense PDF misclassification**:
   The user reported that uploading an expense bill PDF created/detected a new user instead of saving it as an expense. Future work should improve expense PDF classification plus buyer/seller role detection so vendor bills for existing users become `purchase_expense` records.
0. **Clean local test discovery/environment**:
   Recreate or repair `.venv`, prevent `scratch_test.py` from being collected by default, and fix/remove unreadable `tests/tmp` so plain `pytest` can be trusted again.
1. **Pipeline Verification**:
   Upload the PDFs that previously failed local parsing and verify GST freelance invoices, receipts, and salary slips now populate extracted fields correctly.
2. **Expense Confirmations**:
   Verify details of an extracted invoice in the `ReviewModal` as type `Expense`, confirm, and check that the record enters the database table `freelance_expenses` and correctly recalculates the "Total Expenses" and "GST input claims" on the dashboard metrics.
3. **Verify delete cascading**:
   Delete a document from the Documents panel and confirm that its corresponding expense or salary records are deleted cleanly from the lists and graphs.
4. **LM Studio fallback verification**:
   Upload a PDF that local Python cannot validate and confirm it goes directly to Local Hosted LM Studio AI. Then verify LM Studio's returned fields populate the review/dashboard flow instead of being discarded as a failed stage.

---

## Latest Session Note: 2026-06-11 Codex

* Read `project_context.md` and `memory_dump.md` completely.
* Implemented extraction pipeline fixes in `backend/app/extraction.py`, `backend/app/main.py`, and `frontend/src/main.jsx`.
* Local parser improvements: broader label matching, nearby-line amount lookup, GST tax invoice classification, and freelance GST invoice normalization to `net = gross - TDS` with GST tracked separately.
* AI mapping improvement: LM Studio can return compact/flat JSON or the nested schema; both now map into review/dashboard fields.
* Cloud AI removal: frontend provider selector and Google fallback were removed; backend provider routing now always uses local LM Studio.
* Local extraction improvement: `extract_embedded_pdf_text()` now tries PyMuPDF after `pypdf`, and date detection prefers explicit Pay/Invoice dates while avoiding unrelated DOJ dates.
* ExoEdge Apr 2026 payslip fix: `AMOUNT_RE` now requires a digit, salary net pay supports the value-above-label layout, combined gross/deduction salary lines are handled, employee names without colon separators are parsed, employer detection scans meaningful header lines, and salary GST is forced to `0.0`.
* Freelance GST fix: Tally-style CGST/SGST lines such as `Output-CGST-9% 25,499.97%9` now parse the real GST amount, plain `INVOICE`/`Buyer` labels classify correctly, GSTIN is used to derive PAN, and `confirm_extraction()` preserves freelance `gst_amount` in metadata.
* Older Terafina salary slip fix: labels like `Total Gross`, `Ee PF contribut`, `Ee VPF contribu`, and `Less: Dedns` now parse correctly. `Less: Dedns` is treated as non-tax deductions, and LM Studio fallback mapping now accepts nested aliases such as `total_gross`, `total_net_pay`, `income_tax`, `employee_pf`, and `employee_vpf`.
* User matching fix: PAN now returns an existing user with high confidence, and normalized/fuzzy matching handles reversed names and small spelling differences such as `Akshay Bhatnagar`, `Bhatnagar Akshay`, and `Aakshay Bhatnagar`.
* Active known bug recorded: expense bill PDFs can be misclassified and create/detect a user instead of becoming an expense. Deferred to a future iteration.
* Current reliable automated baseline: direct intended test suite passes with bundled Codex Python (`47 passed`) and `npm run build` succeeds with the existing large chunk warning.
