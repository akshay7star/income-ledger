# Income Ledger 🪙

A private, local-only dashboard for managing salary slips, freelance invoices, expenses, and estimating Indian income tax. 

This tool automatically extracts income information from PDF documents (like salary slips or invoices), maps earnings to the Indian financial year (April 1 – March 31), provides automated tax slab estimations for both the Old and New regimes, and projects quarterly advance tax requirements.

---

## 🚀 Key Features

*   **Automated PDF Extraction**: Parses salary slips (extracting Basic, Gross, Net, TDS, PF, VPF, and other deductions) and freelance invoices (extracting Gross, Net, TDS, and GST).
*   **Intelligent OCR Capabilities**: Out-of-the-box support for text-based PDFs using `pypdf`, with optional local OCR support (via Tesseract & Poppler) for scanned or image-based PDFs.
*   **Indian Financial Year Grouping**: Automatically groups all income, deductions, and expenses into their respective Indian Financial Years (from FY 2017-18 to FY 2026-27).
*   **Dual Regime Tax Estimation**: Compares and calculates taxes under both the Old and New tax regimes based on current and projected annual income.
*   **Advance Tax Scheduler**: Estimates projected annual tax liability and provides an equal quarterly advance tax payment schedule (Q1–Q4).
*   **Expense & GST Input Tracking**: Allows manual logging of business expenses and GST inputs to offset freelance earnings.
*   **Data Portability**: Clean CSV export of compiled ledger records for direct use in Excel, Google Sheets, or for tax filing.
*   **Local-Only Privacy**: All documents, databases, and logs are kept strictly on your local machine.

---

## 🛠️ Architecture & Tech Stack

The application is structured into two main components:

1.  **Backend (FastAPI)**:
    *   **FastAPI**: Serves a local REST API on `http://127.0.0.1:8001`.
    *   **SQLite**: Local database storage using `sqlite3` (located in `data/income_ledger.sqlite3`).
    *   **PDF Processing**: Built on `pypdf` for parsing digital PDFs and `pytesseract` + `pdf2image` for OCR operations.
2.  **Frontend (React)**:
    *   **Vite**: Fast, modern frontend builds.
    *   **Bootstrap**: Clean, responsive styling with support for system-wide light/dark themes.
    *   **Recharts**: Visualizes monthly income trends, deductions, and projected tax-to-income comparisons.
    *   **Lucide Icons**: Modern SVG iconography.

---

## 📂 Project Layout

*   [`backend/app/`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app):
    *   [`main.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/main.py): REST API endpoints for user creation, document uploads, expenses, and dashboard metrics.
    *   [`extraction.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/extraction.py): Extractor regex patterns and parsing engines for salary slips and freelance invoices.
    *   [`tax.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/tax.py): Core mathematical modules implementing tax slabs, cess, standard deductions (₹75k), and rebates (e.g., ₹12 Lakh limit for FY 2025-26 under the new regime).
    *   [`database.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/database.py) & [`repositories.py`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/repositories.py): SQLite schemas, migrations, and CRUD helper repositories.
*   [`frontend/`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/frontend):
    *   [`src/main.jsx`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/frontend/src/main.jsx): Main dashboard React application, modals, forms, and charts.
    *   [`src/styles.css`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/frontend/src/styles.css): Custom CSS stylesheets supporting both light and dark modes.
*   [`tests/`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/tests): Python test suite validating calculations, financial date boundaries, and data validations.
*   [`data/`](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/data): *(Auto-generated, Git-ignored)* Local database, uploads, and application logs.

---

## ⚙️ Quick Start

Launch the entire suite on Windows with a single command:

```powershell
.\Start-IncomeLedger.ps1
```

*(Alternatively, double-click `Start-IncomeLedger.bat` to launch from file explorer.)*

### What this script does:
1.  Verifies/creates a local Python Virtual Environment (`.venv`).
2.  Installs all required backend libraries (`requirements.txt`).
3.  Installs all required React modules (`frontend/package.json`).
4.  Launches the FastAPI backend server on `http://127.0.0.1:8001`.
5.  Launches the Vite React frontend server on `http://127.0.0.1:5173`.
6.  Opens your web browser automatically to start managing your ledger.

---

## 🤖 Local AI Model Configuration

By default, the application connects to a local instance of **LM Studio** running on `http://127.0.0.1:1234/v1` using `google/gemma-4-e4b`.

The extraction pipeline is local-only:

1. Local Python parser reads embedded PDF text, PyMuPDF fallback text, and optional local OCR.
2. If the local parser cannot confidently validate the document, the app sends the document to your locally hosted LM Studio model.
3. If LM Studio also cannot produce usable fields, the document opens in manual review.

Cloud AI providers have intentionally been removed from the app.

### Setting up a `.env` file
Create a file named `.env` in the project root directory and add the following keys as needed:

```env
# URL for your local LM Studio server (comma-separated if using multiple local fallbacks)
LOCAL_AI_BASE_URL=http://127.0.0.1:1234/v1

# Optional local server API key, if your LM Studio setup requires one
LOCAL_AI_API_KEY=lm-studio

# The local LM Studio model name
LOCAL_AI_MODEL=google/gemma-4-e4b

# Timeout for API requests in seconds (default is 120)
LOCAL_AI_TIMEOUT_SECONDS=120

# Number of pages to render and send to the model for visual PDFs (default is 1)
LOCAL_AI_RENDERED_PAGES=1
```

---

## ⚠️ Notes & OCR Setup

*   **Privacy notice**: The app is intended to use only local Python extraction and a locally hosted LM Studio model. Do not configure cloud AI endpoints for this project.
*   **Optional OCR**: To process scanned documents:
    1.  Install **Tesseract OCR** on your PC and add its path to your system environment variables.
    2.  Install **Poppler** (for PDF-to-image conversion) and add its `/bin` directory to your system environment variables.

---

## 📜 Changelog

- **v0.1.2 (2026-06-09)**:
  * Replaced the document delete confirm flow with an in-app modal so dashboard deletions trigger reliably.
  * Corrected tax projection annualization to use elapsed financial-year months for partial-year data.
  * Kept the selected user stable across refreshes within the same browser session.
  * Aligned tax comparison cards with projected old/new regime values and cleaned up regime labels.

- **v0.1.1 (2026-06-08)**: 
  * Upgraded dashboard visual design (3D perspective hovers, glassmorphism panels, floating background blobs).
  * Improved dark mode text contrast and theme-aware inputs/tables.
  * Enhanced database deletion to cascade to freelance expenses on purchase document deletion.
  * Added unit test suite for document/expense deletion cascades.
