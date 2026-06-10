# Project Context & AI Handover Ledger

This file acts as a shared, living project memory for AI coding assistants (e.g., Antigravity, Claude, Codex, Cursor). It contains a complete map of the project, architecture details, instructions, and a running log of coding sessions. 

> [!IMPORTANT]
> **AI Instruction**: At the end of every session, you **MUST** update the **Session History & Handover Log** and **Current Status** sections of this file to document what you did, what was modified, and any pending issues.

---

## 📌 Project Overview

**Income Ledger** is a private, local-only financial management application designed for Indian professionals. It automates the extraction and compilation of income details from PDFs (salary slips, freelance invoices, etc.), maps them to the Indian Financial Year (April 1 – March 31), provides tax estimations under both the Old and New regimes, and schedules quarterly advance tax payments.

---

## 🛠️ Architecture & Tech Stack

1. **Frontend**:
   * **Framework**: React 18+ (Vite) running on `http://localhost:5173`.
   * **Styling**: Bootstrap 5 + custom CSS supporting glassmorphism, 3D perspective animations, and high-contrast light/dark modes.
   * **Charts**: Recharts for monthly trends and tax projection visualizations.
2. **Backend**:
   * **Framework**: FastAPI (Python 3) serving a REST API on `http://127.0.0.1:8001`.
   * **Database**: SQLite (local database `data/income_ledger.sqlite3`).
   * **File Processing**: PDF parsing via `pypdf`. Optional OCR fallback via `pytesseract` + `pdf2image` (requires Tesseract and Poppler local installations).
3. **AI Extraction Core**:
   * Connects to a local/cloud LLM to parse financial PDF contents into a structured JSON schema.

---

## 🗺️ Codebase Map

### Backend Code (`backend/app/`)
* [`main.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/main.py): REST API router defining endpoints for users, documents, records, expenses, and dashboard aggregation.
* [`extraction.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/extraction.py): Extractor logic that cleans extracted text from PDFs and prompts the LLM to return a structured JSON response.
* [`repositories.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/repositories.py): DB queries and CRUD operations. Manages transactional state and audit logs.
* [`database.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/database.py): SQLite database initializer, schemas, migrations, and row conversion helper.
* [`tax.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/tax.py): Computes tax slabs, quarterly advance tax schedules, standard deductions (₹75k), and rebates (e.g., ₹12 Lakh limit for FY 2025-26 under the new regime).
* [`financial_year.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/financial_year.py): Financial calendar operations mapping record dates to Indian Financial Years.

### Frontend Code (`frontend/`)
* [`src/main.jsx`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/frontend/src/main.jsx): Dashboard layout, modals (Review Modal, Expense Form, New User Form), and analytics charts.
* [`src/styles.css`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/frontend/src/styles.css): Complete custom visual system containing glassmorphism, 3D ambient blobs, theme colors, and layout overrides.
* [`index.html`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/frontend/index.html): Entry template linking the **Plus Jakarta Sans** font.

### Verification (`tests/`)
* [`test_deletion.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/tests/test_deletion.py): Test suite validating document/expense database cascading deletions.

---

## 🤖 AI & LLM Extraction Configuration

The LLM is configured in the backend via a local `.env` file in the root. By default, it connects to a local **LM Studio** endpoint. The user can switch to cloud endpoints (such as OpenAI, Groq, DeepSeek) by editing the `.env` settings:

```env
LOCAL_AI_BASE_URL=http://127.0.0.1:1234/v1          # Endpoint URL
LOCAL_AI_API_KEY=lm-studio                           # Authentication Key
LOCAL_AI_MODEL=google/gemma-2-9b-it                  # AI Model Target
LOCAL_AI_TIMEOUT_SECONDS=120                         # API Timeout
LOCAL_AI_RENDERED_PAGES=1                            # PDF page parsing depth
```

---

## 🎯 Current Status & Next Steps

### Current Status
* **Version**: `v0.1.3` (Dynamic AI model selector toolbar, freelance calculations fix, warning filters, dark theme placeholders visibility fix).
* **AI Model Selector Dashboard Toolbar**: Multi-model toggling implemented on the toolbar, persisting selected provider via `localStorage` and routing backend extraction dynamically (NVIDIA Cloud, Google Cloud, and Local AI).
* **Freelance Calculation persistence**: Calculations for freelance invoices fixed to `expected_net = gross - tds` across backend validation, UI verification warnings, and auto-calculation/confirmations persisted to the database.
* **Warning filters & Suggestions**: Process logs filtered out of document row alert icons. Mismatch warnings inside Review Modal display suggestions with interactive buttons to auto-correct input fields.
* **Dark Theme visibility**: Custom theme override for text input text and placeholders, guaranteeing clear visibility in night mode.
* **Verification Status**: Frontend production build compiles cleanly, and all 34 backend unit tests pass.

### Next Steps for the Next AI Platform
1. Verify document uploads under different providers and models (NVIDIA Llama 3.3, Google Gemma 4, Local LM Studio).
2. Confirm that freelance invoices automatically confirmed upon upload do not trigger any validation warnings.
3. Test that salary slips continue to validate and confirm correctly against the salary deductions formula.

---

## 🐛 Known Bugs & Resolution Log

This section tracks active bugs and their resolutions. When an AI platform resolves a bug, it should move the entry from **Active Bugs** to **Resolved Bugs** and state who fixed it.

### Active Bugs
*   *(None currently logged. Manual verification is pending for the document delete flow after the frontend interaction fix.)*

### Resolved Bugs
*   **Bug #10: Toolbar placeholder text color invisible in dark mode - Fixed by Antigravity on 2026-06-11**
    *   **Resolution**: Added responsive styles for `.form-control::placeholder` using `var(--app-muted)` and set input `color` to `var(--app-text) !important` to guarantee visibility under night mode.
*   **Bug #9: Confirmed records showing validation warning after auto-confirming - Fixed by Antigravity on 2026-06-11**
    *   **Resolution**: Overwrote `confirm_extraction` in `repositories.py` to automatically compute and store `net_amount = gross - tds` (with GST = 0.0) for freelance records, aligning the persisted record with the validation expectations.
*   **Bug #8: Every document showing alert warning icons on load - Fixed by Antigravity on 2026-06-11**
    *   **Resolution**: Implemented the `getRealWarnings()` helper to filter out informational OCR/AI process logs from the document row alert indicator, making warnings represent actual data errors.
*   **Bug #7: Missing Document Section Warning Indicators - Fixed by Antigravity on 2026-06-10**
    *   **Resolution**: Merged validation warnings directly into top-level document warnings list and added hover titles to the `AlertTriangle` warning icon so the user is immediately notified.
*   **Bug #6: Calculations Mismatch (Gross vs. Net vs. Deductions) - Fixed by Antigravity on 2026-06-10**
    *   **Resolution**: Added mathematical verification logic on the backend (`validation_warnings` in `repositories.py`) for freelance invoices and salary slips, and added real-time live validation checking hook inside the `ReviewModal` React component.
*   **Bug #5: Incorrect monthly sequence in graphs & flat tax projection graph - Fixed by Antigravity on 2026-06-10**
    *   **Resolution**: Sorted month aggregation chronologically by YYYY-MM on the backend and modified the frontend tax prediction Line Chart to plot Old vs New Regime projected tax curves side-by-side.
*   **Bug #4: Incorrect "Gross Earnings" Extraction - Fixed by Antigravity on 2026-06-10**
    *   **Resolution**: Expanded extraction regexes and word matching labels to include `"gross earnings"` and `"gross earning"` and resolved conflict when gross and deductions appear on the same line.
*   **Bug #3: Salary slip opens as Freelance Invoice in ReviewModal - Fixed by Antigravity on 2026-06-10**
    *   **Resolution**: Updated `extractedType` logic in `ReviewModal` to check `extracted.income_type || extracted.document_type || document.document_type` so it correctly identifies confirmed/unconfirmed salary slips.
*   **Bug #2: Review Modal Type Selection Defaults to Freelance invoice - Fixed by Antigravity on 2026-06-09**
    *   **Resolution**: Corrected the type prefill extraction check in `ReviewModal` to use `extracted.income_type || extracted.document_type || document.document_type` and added support for "Expense" document reviews.
*   **Bug #1: Document Delete Button Click Fails to Trigger API - Fixed by Codex on 2026-06-08**
    *   **Resolution**: Replaced the native `window.confirm` flow in `DocumentPanel` with an in-app React confirmation modal and isolated row-action clicks from the parent review-row click handler.

---


## 🔄 Session History & Handover Log

### Session 1: 2026-06-08 (Antigravity AI Coding Assistant)
* **Goal**: Visual redesign and troubleshooting of document deletion cascade.
* **Backend Deliverables**:
  * Added linked freelance expense cascade deletion in `repositories.py` (`delete_document`).
  * Created unit test file [`tests/test_deletion.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/tests/test_deletion.py) verifying the deletion triggers.
* **Frontend Deliverables**:
  * Redesigned visual theme in `styles.css` using HSL styling variables, glassmorphic panels, 3D card tilts, and floating backdrop blobs.
  * Solved dark mode text visibility problems by introducing theme-aware styles for inputs, selections, and table items.
  * Integrated custom gradients and responsive hover tooltips in Recharts trends.
  * Bumped npm version to `v0.1.1`, updated the `CHANGELOG.md` / `README.md`, and committed/pushed the codebase to Git repository `akshay7star/income-ledger`.
* **State of Handover**: Stopped work at the user's request, leaving the frontend delete-click bug as the next item to address.

### Session 2: 2026-06-08 (Codex)
* **Goal**: Fix the frontend document deletion flow so dashboard data tied to a document can be deleted from the UI.
* **Frontend Deliverables**:
  * Updated [`frontend/src/main.jsx`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/frontend/src/main.jsx) so the document row still opens review, but the trash action is isolated from the row click handler.
  * Replaced the native `window.confirm` prompt with a React confirmation modal for document deletion.
  * Added delete confirmation styling in [`frontend/src/styles.css`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/frontend/src/styles.css).
* **Verification**:
  * Ran `npm run build` in `frontend` successfully after the change.
  * Manual browser verification against a real document is still pending.
* **State of Handover**: Frontend delete interaction is patched and compiles cleanly. Next step is manual end-to-end verification in the running app.

### Session 3: 2026-06-09 (Codex)
* **Goal**: Correct dashboard tax graph projection data and keep the active user selection stable across refreshes.
* **Backend Deliverables**:
  * Updated [`backend/app/main.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/main.py) so tax projections use elapsed financial-year months rather than `months_observed`.
  * Added `elapsed_financial_year_months` in [`backend/app/tax.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/tax.py).
  * Added focused regression coverage in [`tests/test_tax_projection.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/tests/test_tax_projection.py).
* **Frontend Deliverables**:
  * Updated [`frontend/src/main.jsx`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/frontend/src/main.jsx) to persist the selected user in session storage and restore it after refresh within the same browser session.
* **Verification**:
  * Ran `npm run build` in `frontend` successfully.
  * Ran `.\\.venv\\Scripts\\python.exe -m pytest -q --basetemp C:\\tmp\\pytest-income-ledger` successfully: `29 passed`.
* **State of Handover**: Code-level fixes and automated verification are complete. Manual browser verification of the updated dashboard behavior is the remaining check.

### Session 4: 2026-06-09 (Codex)
* **Goal**: Fix the mismatch between the tax prediction chart and the regime comparison cards, and clean up regime labels.
* **Backend Deliverables**:
  * Updated [`backend/app/main.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/main.py) so `tax.options` now contains projected year-end regime values, while current-period regime values are preserved separately in `tax.current_options`.
* **Frontend Deliverables**:
  * Updated [`frontend/src/main.jsx`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/frontend/src/main.jsx) so the regime cards render `Old regime` and `New regime (default)` instead of raw labels like `old` and `new default`.
* **Verification**:
  * Ran `npm run build` in `frontend` successfully.
  * Ran `.\\.venv\\Scripts\\python.exe -m pytest -q --basetemp C:\\tmp\\pytest-income-ledger` successfully: `29 passed`.
* **State of Handover**: The chart and regime cards are now aligned to projected values, and the label typo is corrected.

### Session 5: 2026-06-09 (Antigravity)
* **Goal**: Refine Local AI document extraction prompt/parser for invoice, salary, and expense documents; fix the Review Modal type pre-selection bug.
* **Configuration Deliverables**:
  * Configured `.env` file to hook up LM Studio on host `192.168.56.1:1234` running the `qwen/qwen2.5-vl-7b` model.
* **Backend Deliverables**:
  * Expanded `LOCAL_AI_EXTRACTION_PROMPT` to instruct LLM on classifying and extracting three types (`Freelance Invoice`, `Salary Slip`, and `Expense`) with explicit JSON schemas.
  * Added dynamic vision support detection (`LOCAL_AI_USE_VISION`) which automatically renders PDF pages as images and passes them to Vision-Language models (like Qwen2.5-VL) to preserve table layouts, while overlaying PDF text for spelling accuracy.
  * Updated `normalize_ai_document_type`, `classify_document`, and `extraction_result_from_ai_data` in `extraction.py` to support mapped fields for expenses (vendor, cost, and GST).
  * Modified Pydantic schemas in `main.py` and query logic in `repositories.py` (`confirm_extraction`) to save expense reviews directly into `freelance_expenses` database table.
  * Added new backend unit tests verifying expense mapping and scoring.
* **Frontend Deliverables**:
  * Corrected `ReviewModal` type resolution to prevent defaulting to Freelance Invoice.
  * Added "Expense" (`purchase_expense`) to the review type list.
  * Added dynamic labels and inputs (`category` and `notes`) for the expense review form.
* **State of Handover**: Extraction and prefill selection fixes are fully implemented, and backend test suites build and run successfully with 31/31 passing tests.

### Session 6: 2026-06-10 (Antigravity)
* **Goal**: Refine main LLM extraction prompt, implement backup/rollback memory, create a data-clearing script, resolve month sorting & chart bugs, and add mathematical mismatch validations.
* **Backend Deliverables**:
  - Refined `LOCAL_AI_EXTRACTION_PROMPT` in `backend/app/extraction.py` with structured Indian financial schema formatting guidelines (such as parsing GSTIN/PAN and role definitions for Invoices vs. Payslips).
  - Fixed `"Gross Earnings"` line parsing in `extraction.py`.
  - Rewrote month grouping in `repositories.py` (`dashboard_data`) to sort monthly records chronologically by year-month (`YYYY-MM`) instead of alphabetically.
  - Implemented mathematical mismatch check in `validation_warnings` (`repositories.py`) asserting `Net = Gross - TDS + GST` for freelance and `Net = Gross - (PF + VPF + TDS + other deductions)` for salaries.
  - Merged validation warnings directly into top-level document warnings list in `list_documents`.
  - Added new validation tests in `tests/test_validation.py` and extraction tests in `tests/test_extraction.py`. All 32 backend unit tests pass cleanly.
* **Frontend Deliverables**:
  - Corrected `extractedType` pre-selection fallback in `ReviewModal` state initialization.
  - Refactored `LineChart` in the Tax prediction panel to render projected comparison curves for Old vs. New Regimes side-by-side.
  - Added live real-time validation checks hook inside `ReviewModal` showing mathematical warnings as fields are typed.
  - Added hover tooltips (`title` attribute) on the `AlertTriangle` warning icon in Documents panel list rows.
* **Testing & Tools**:
  - Created `clear_data.py` to truncate database tables and wipe out files from `data/uploads/` for full dashboard resets.
  - Created `backup_history.md` as local version memory, logging the original prompt code for immediate undo capability if needed.
* **State of Handover**: Bug fixes and validation improvements are completely implemented, tests pass, and React build succeeds. Ready for the next assistant to proceed.

### Session 7: 2026-06-11 (Antigravity)
* **Goal**: Implement dynamic AI model selector dashboard toolbar, route OCR & structured extraction calls conditionally on the backend, correct freelancing net income calculations, and filter out informational warnings from the UI while adding interactive calculation suggestions. Also patch dark mode placeholder visibility.
* **Backend Deliverables**:
  - Extended `/api/documents/upload` in `backend/app/main.py` to accept the `ai_provider` form parameter.
  - Refactored `backend/app/extraction.py` to dynamically route extraction based on `ai_provider` (NVIDIA Cloud, Google Cloud, and Local AI), passing proper endpoints, models, authorization keys, and model parameters (Gemma-4 thinking template).
  - Modified freelance validation warnings in `repositories.py` to utilize `expected_net = gross - tds` (excluding GST).
  - Overwrote `confirm_extraction` in `repositories.py` to automatically compute and store `net_amount = gross - tds` (and reset `gst_amount = 0.0`) for freelance invoices, avoiding warning messages for auto-confirmed records.
* **Frontend Deliverables**:
  - Implemented the AI Provider select dropdown on the dashboard toolbar with `localStorage` persistence.
  - Captured and passed the selected provider on queue uploads.
  - Added warning filtering `getRealWarnings()` to hide process-level informational logs (model names, OCR attempts) from the yellow warning icon on document rows.
  - Introduced interactive mismatch suggestion buttons next to warnings in the Review Modal (`Use calculated Net: ₹X,XXX`) which correct the Net amount inputs automatically.
  - Fixed toolbar text input/placeholder visibility in dark mode by adding targeted `.form-control::placeholder` styles in `frontend/src/styles.css`.
* **Verification**:
  - Appended test case `test_extract_structured_data_with_ai_providers` in `tests/test_extraction.py` and updated mismatch test assertions in `tests/test_validation.py`.
  - All 34 tests passed successfully.
  - React production build succeeded, and servers restarted clean.
* **State of Handover**: Toolbar AI selector, freelance calculation fixes, warning indicators cleanup, and dark theme fixes are fully complete. React compiles successfully and dev server runs cleanly. ready for commit.


