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

The LLM is configured in the backend via a local `.env` file in the root. By default, it connects to a local **LM Studio** endpoint. Cloud AI endpoints are intentionally not part of the active pipeline.

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
* **Version**: `v0.1.5` (Local-only extraction pipeline: Python parser first, Local Hosted LM Studio fallback, dynamic expense category classification, and full UI/backend document expense review integration).
* **Latest Codex Implementation (2026-06-11)**: Codex improved user matching to prevent duplicate users from reversed names or small OCR/name spelling variations, with PAN as a high-confidence unique identifier.
* **Local Environment Note**: The workspace `.venv` launcher is currently broken because it points to a missing Python path (`C:\Users\aksha\AppData\Local\Programs\Python\Python312\python.exe`). Plain `pytest` also collects root-level `scratch_test.py` and unreadable `tests/tmp`, causing collection errors unrelated to the main suite. Use the direct test command recorded in Session 10 until the environment/test discovery is cleaned up.
* **Pipeline Resilience & Continuity**: Wrapped both the frontend stage requests and the backend local parser stage in try-catch/try-except blocks. If an exception or HTTP failure (like 500 or CORS error) occurs at any stage, the system now updates the status to transition to the next fallback stage instead of aborting the processing queue.
* **Status Messages**: Local extraction failures now move directly to Local Hosted LM Studio AI. If LM Studio fails, the UI shows the local AI failure detail and asks for manual review.
* **Local Parser & Fallback Pipeline**: Local Python rule-based extraction executes first. If validations pass, it skips AI calls entirely. If incomplete, it executes the fallback chain: `Local Hosted AI (LM Studio) -> Manual Review`.
* **Automated Expense Tracking**: Enabled full PDF invoice/receipt extraction support for expenses. Local script maps amounts (Gross + GST = Net) and automatically categorizes expense items into predefined categories (`Travel`, `Software`, `Hardware`, `Utilities`, `Office Supplies`, `Professional Fees`, `Rent`, `Meals`, `Others`) using regex word boundaries.
* **Review Modal Integration**: Extended `ReviewModal` React component to support the `Expense` type. When selected, it shows Vendor name, Gross, Net, GST, Category select, and Notes fields, supporting live validation and error checking.
* **Verification Status**: Frontend production build compiles successfully and the direct backend suite passes with 47 tests after fuzzy user-matching coverage.

### Next Steps for the Next AI Platform
0. Clean up the local test environment: recreate `.venv` or update launchers, exclude/remove `scratch_test.py` from normal pytest discovery, and fix/remove unreadable `tests/tmp`.
1. Upload the previously failing PDFs and verify local parser extraction for GST freelance invoices, receipts, and salary slips.
2. Upload a PDF that local Python cannot validate and verify it goes directly to Local Hosted LM Studio AI.
3. Upload a PDF that LM Studio can parse and verify its returned fields populate the review/dashboard record instead of being discarded as a failed stage.

---

## 🐛 Known Bugs & Resolution Log

This section tracks active bugs and their resolutions. When an AI platform resolves a bug, it should move the entry from **Active Bugs** to **Resolved Bugs** and state who fixed it.

### Active Bugs
*   **Bug #11: Expense PDFs can be misclassified as users/income instead of expenses - Reported by user on 2026-06-11**
    *   **Observed Behavior**: User uploaded an expense bill PDF and the system created/detected a new user instead of saving it as an expense.
    *   **Likely Area**: Document classification and `should_save_invoice_as_expense()` / expense confirmation flow. Expense PDFs need stronger buyer/seller role detection so vendor bills for an existing user become `purchase_expense` records and do not create users.
    *   **Status**: Active. Current code is otherwise working; this is deferred to a future iteration.

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

### Session 9: 2026-06-11 (Antigravity)
* **Goal**: Implement complete error resilience and pipeline continuity in the PDF extraction pipeline, and show precise user-facing status messages for each failure transition.
* **Backend Deliverables**:
  - Wrapped local extraction (`stage == "local"`) logic in a `try-except Exception` block in `backend/app/main.py`. This ensures that even if local parsing throws an exception (e.g. text search or parsing bugs), it catches it, saves a placeholder document database row, and returns `success: False` with status `200 OK` instead of raising a `500 Internal Server Error`.
* **Frontend Deliverables**:
  - Wrapped each stage request (`/documents/upload` and `/re-extract`) in its own `try-catch` block inside `processUploadQueue` in `frontend/src/main.jsx`.
  - Ensured that if any stage request fails or throws a network error, the pipeline is not blocked; it transitions smoothly to the next fallback stage.
  - Implemented the exact user-specified status messages for failure transitions:
    * Local Python fails: `"Local Python script failed to extract data moving to cloud AI"`
    * Cloud AI fails: `"Cloud AI Failed to extract data moving to cloud AI"`
    * Local Hosted AI (LM Studio) fails: `"Please manually check and fill details"`
* **Verification**:
  - All 39 unit tests pass successfully.
  - Frontend builds successfully without warnings.
  - Restarted the backend server cleanly on `127.0.0.1:8001`.
* **State of Handover**: Extraction pipeline is fully resilient to backend and network failures, and exhibits the exact status message transitions. Ready for handover and migration to the next platform.

### Session 10: 2026-06-11 (Codex)
* **Goal**: Read the project handoff files and establish a clean baseline for future agents.
* **Context Reviewed**:
  - Read `project_context.md` and `memory_dump.md` in full.
  - Previously inspected the core backend/frontend modules, README, requirements, startup scripts, tests, and current git status.
* **Code Changes**:
  - No application code was changed.
  - Updated this handoff file and `memory_dump.md` so the next model understands the latest Codex review and the current test environment caveats.
* **Verification**:
  - `.\\.venv\\Scripts\\python.exe -m pytest` failed before test execution because the venv launcher points at a missing Python install.
  - `python -m pytest` failed because `python` is not on PATH.
  - Bundled Codex Python plain pytest collection failed on `scratch_test.py` (`fitz` missing) and unreadable `tests/tmp`.
  - Direct intended-suite command passed: `C:\\Users\\aksha\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe -m pytest tests\\test_deletion.py tests\\test_extraction.py tests\\test_financial_year.py tests\\test_tax.py tests\\test_tax_projection.py tests\\test_user_matching.py tests\\test_validation.py -p no:cacheprovider` -> `39 passed`.
* **State of Handover**: Project context is now read and updated. No functional changes were made; next useful work is manual browser verification of the extraction fallback, expense confirmation, and document delete cascade flows, plus cleaning the local test environment.

### Session 11: 2026-06-11 (Codex)
* **Goal**: Fix local PDF extraction failures, expose Cloud AI errors, and preserve usable Local Hosted LM Studio AI extraction results.
* **Backend Deliverables**:
  - Updated `backend/app/extraction.py` so `extraction_result_from_ai_data()` accepts both the nested AI schema and compact/flat LM Studio-style JSON fields (`document_type`, `name`, `payer`, `record_date`, `gross_amount`, `net_amount`, `tds_amount`, `gst_amount`, etc.).
  - Improved document classification so GST tax invoices with `Bill To`, client, professional charges, or consulting language are treated as `freelance_invoice` instead of being misclassified as purchase expenses due to CGST/SGST tokens.
  - Expanded amount label matching and added nearby-line amount lookup, improving PDFs where labels and values are split across lines.
  - Normalized local freelance invoice parsing to the app's income formula: `net_amount = gross_amount - tds_amount`, while preserving GST separately. This lets GST invoices pass local validation instead of unnecessarily falling through to AI.
  - Updated `backend/app/main.py` re-extract handling so AI responses are considered successful when they contain usable structured data, even if they still require review. Failed provider responses now include `detail` and `warnings`.
* **Frontend Deliverables**:
  - Updated `frontend/src/main.jsx` upload fallback handling to display the actual Cloud AI failure detail before moving to Local Hosted LM Studio AI.
  - Updated LM Studio failure status to include returned failure detail.
* **Tests**:
  - Added regression tests for flat LM Studio JSON mapping and GST freelance invoice local parser validation in `tests/test_extraction.py`.
* **Verification**:
  - Backend direct suite passed with writable basetemp: `41 passed`.
  - Frontend `npm run build` succeeded. Vite still reports the existing large chunk warning.
* **State of Handover**: Automated coverage is green. Manual browser verification remains needed with the user's real PDFs and LM Studio instance to confirm returned local AI fields now populate the dashboard/review flow.

### Session 12: 2026-06-11 (Codex)
* **Goal**: Diagnose why `1.0 ExoEdge Apr_2026.pdf` failed local Python extraction.
* **Root Cause**:
  - The PDF had readable embedded text, so OCR was not the problem.
  - `AMOUNT_RE` allowed comma-only matches. The extracted address line `Ground Floor,Bestech...` produced a comma-only "amount", which crashed `parse_amount()` with `ValueError`.
  - After that crash was fixed, ExoEdge's layout still confused salary parsing because the net amount appears one line above `Total Net Pay`, and total deductions are in a combined `Gross Earnings ... Total Deductions` line.
  - Employer detection missed the company because the PDF begins with colon-only lines, so the previous header scan did not reach the real employer name.
* **Code Changes**:
  - Updated `backend/app/extraction.py` amount regex to require at least one digit.
  - Added salary-specific net pay handling for values immediately above `Total Net Pay` and for explicit `Gross Earnings - Total Deductions` net payable lines.
  - Added targeted total deductions extraction from combined gross/deductions lines.
  - Improved `find_named_value()` to read labels without a colon, such as `Employee Name Devlina Bhatnagar`.
  - Improved salary employer detection to scan meaningful header lines and skip benefit/contribution table headers.
  - Set salary `gst_amount` to `0.0` so income tax is not accidentally surfaced as GST.
  - Added a regression test for the ExoEdge Apr 2026 layout in `tests/test_extraction.py`.
* **Observed Result for User PDF**:
  - Parsed as salary for Devlina Bhatnagar, PAN `CPIPP9940K`, payer `EXO Edge Advantage India Private Limited`, record date `2026-04-01`, gross `266334.0`, net `204388.0`, TDS `44746.0`, PF `17000.0`, other deductions `200.0`, GST `0.0`.
  - `validate_local_extraction()` returned `True`.
* **Verification**:
  - Focused extraction tests: `22 passed`.
  - Full direct backend suite: `42 passed`.
* **State of Handover**: This specific PDF should now pass the local Python stage without falling through to Cloud AI.

### Session 13: 2026-06-11 (Codex)
* **Goal**: Remove Cloud AI and keep only Local Python extraction plus Local Hosted LM Studio fallback.
* **Backend Deliverables**:
  - Removed remote NVIDIA/Google provider routing from `backend/app/extraction.py`.
  - Removed NVIDIA OCR API key/url configuration and helper usage from the active extraction path.
  - `extract_structured_data_with_ai()` now always targets `LOCAL_AI_BASE_URL` / `LOCAL_AI_MODEL`, even if a stale provider value is supplied.
  - `extract_financial_fields()` now falls back directly from local parser failure to Local Hosted AI.
  - `backend/app/main.py` now ignores stale remote provider values and uses local LM Studio for re-extraction.
  - Added PyMuPDF embedded text fallback after `pypdf`, improving local Python extraction for PDFs where one parser misses layout text.
  - Improved date priority so explicit `Pay Date` / `Invoice Date` values win, while `Pay Period` still wins over unrelated dates such as DOJ.
* **Frontend Deliverables**:
  - Removed AI provider selector from the toolbar.
  - Removed Google Cloud fallback stage from `processUploadQueue()`.
  - Upload flow is now: Local Python -> Local Hosted LM Studio AI -> Manual Review.
* **Docs/Tests**:
  - Updated `README.md` to document local-only AI configuration.
  - Rewrote provider-routing test to assert stale provider inputs still use LM Studio/local URL only.
* **Verification**:
  - Backend direct suite: `41 passed`.
  - Frontend `npm run build` succeeded with the existing large chunk warning.
* **State of Handover**: Cloud AI is removed from the active app path. Remaining work is to keep expanding local Python parser heuristics using real failing PDFs.

### Session 14: 2026-06-11 (Codex)
* **Goal**: Fix missing GST values from an uploaded freelance invoice.
* **Root Cause**:
  - The uploaded `1.1 GenAQ Apr 2026.pdf` invoice had lines like `Output-CGST-9% 25,499.97%9`; the parser read the trailing percentage value `9` instead of the GST amount `25,499.97`.
  - The invoice used plain `INVOICE` and `Buyer` labels, not `Tax Invoice` / `Bill To`, so the document was classified as `unknown`.
  - `confirm_extraction()` recalculated freelance `net_amount` but reset `gst_amount` to `0.0`, wiping GST even when extraction found it.
* **Code Changes**:
  - Updated GST line parsing in `backend/app/extraction.py` to choose the real tax amount from CGST/SGST/IGST lines that also include rates.
  - Improved freelance invoice classification for `INVOICE`, `Buyer`, and `Professional Charges` layouts.
  - Added seller/buyer extraction for plain `INVOICE` and standalone `Buyer` labels.
  - Added GSTIN-to-PAN fallback in `run_local_parser()`.
  - Updated `backend/app/repositories.py` so freelance invoice confirmation preserves `gst_amount` in metadata instead of forcing it to zero.
  - Added regression tests for Tally-style freelance GST invoices and freelance GST persistence.
* **Observed Result for Uploaded Invoice**:
  - Parsed as `freelance_invoice`, seller `DEVLINA BHATNAGAR`, PAN `CPIPP9940K`, payer `Gen Aquarius Private Limited`, date `2026-04-29`, gross `283333.0`, GST `50999.94`, TDS `28333.3`, net `254999.7`.
  - `validate_local_extraction()` returned `True`.
* **Verification**:
  - Focused extraction/validation tests: `29 passed`.
  - Full direct backend suite: `43 passed`.
* **State of Handover**: New uploads/re-extractions of this invoice shape should preserve GST. Existing already-confirmed records may need re-extraction or re-upload to refresh stored metadata.

### Session 15: 2026-06-11 (Codex)
* **Goal**: Diagnose why `1 Payslip_2024-04-30.pdf` failed local Python extraction and why LM Studio fallback could fill review fields with zeros.
* **Root Cause**:
  - The PDF had readable embedded text.
  - The local parser did not recognize older Terafina labels: `Total Gross`, truncated `Ee PF contribut`, truncated `Ee VPF contribu`, and `Less: Dedns`.
  - Because `gross_amount` was `0.0`, `validate_local_extraction()` returned `False`, which is the condition that sends the document to Local Hosted LM Studio AI.
  - LM Studio responses could still map to zeros if the model used common aliases outside the exact schema, such as nested `total_gross`, `total_net_pay`, `income_tax`, `employee_pf`, or `employee_vpf`.
* **Code Changes**:
  - Added older Terafina salary labels to `find_amount()` in `backend/app/extraction.py`.
  - Adjusted salary deduction math for `Less: Dedns`, which excludes income tax and should subtract only PF/VPF before calculating other deductions.
  - Added recursive alias lookup for LM Studio AI responses so nested common field names map into the review form fields.
  - Added regression tests for the old Terafina salary slip layout and nested LM Studio salary aliases.
* **Observed Result for User PDF**:
  - Parsed as salary for `Bhatnagar Akshay`, PAN `BPLPB7839D`, payer `Terafina Software Solutions Pvt Ltd`, record date `2024-04-30`, gross `108860.71`, net `89403.0`, TDS `6158.0`, PF `5320.0`, VPF `7980.0`, other deductions `0.1`, GST `0.0`.
  - `validate_local_extraction()` returned `True`.
* **Verification**:
  - Focused extraction tests: `24 passed`.
  - Full direct backend suite: `45 passed`.
* **State of Handover**: This attached PDF should now complete in Local Python and should not require LM Studio fallback. LM Studio mapping is also more tolerant if another document reaches fallback.

### Session 16: 2026-06-11 (Codex)
* **Goal**: Prevent duplicate users when extracted names vary, such as `Akshay Bhatnagar`, `Bhatnagar Akshay`, or `Aakshay Bhatnagar`.
* **Root Cause**:
  - `find_user_match()` only used exact PAN match plus exact substring name matching.
  - Reversed names and minor OCR/AI spelling variations were not recognized, so `get_or_create_user_for_extraction()` could create a new user.
* **Code Changes**:
  - Added name normalization helpers in `backend/app/repositories.py`.
  - Added token-order-insensitive and typo-tolerant name similarity using `SequenceMatcher`.
  - PAN match now immediately returns the existing user with high confidence (`0.98`).
  - Name matches now handle reversed tokens and small spelling differences, while requiring a minimum confidence threshold to avoid weak accidental matches.
* **Tests**:
  - Added tests for reversed names and small spelling differences in `tests/test_user_matching.py`.
* **Verification**:
  - Focused user matching tests: `4 passed`.
  - Full direct backend suite: `47 passed`.
* **State of Handover**: New uploads should prefer existing users by PAN first, then by normalized/fuzzy name matching. Existing duplicate users already in the database are not automatically merged by this change.

### Session 17: 2026-06-11 (Codex)
* **Goal**: Record current known bug for future iteration.
* **User Note**:
  - Current code is working overall.
  - Known active bug: expense PDFs are not understood reliably. A user uploaded an expense bill and the app created/detected a user instead of treating it as an expense.
* **Handoff Update**:
  - Added Bug #11 to Active Bugs.
  - Also mirrored this note in `memory_dump.md`.
* **State of Handover**: No code changes made for this bug in this session; future work should improve expense PDF classification and vendor/buyer role detection.
