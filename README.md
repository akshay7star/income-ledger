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

## 🤖 Custom AI Model Configuration

By default, the application connects to a local instance of **LM Studio** running on `http://127.0.0.1:1234/v1` using `google/gemma-4-e4b`.

If you wish to configure a different local host, switch to a cloud service (e.g. OpenAI, Groq, DeepSeek, or any OpenAI-compatible provider), you can define these settings in a `.env` file in the root of the project.

### Setting up a `.env` file
Create a file named `.env` in the project root directory and add the following keys as needed:

```env
# URL for your AI provider (comma-separated if using multiple endpoints for fallbacks)
LOCAL_AI_BASE_URL=https://api.openai.com/v1

# The API key required by your cloud provider (e.g., OpenAI, Groq, etc.)
LOCAL_AI_API_KEY=your-actual-api-key-here

# The model name to target (e.g., gpt-4o-mini, llama3-70b-8192, etc.)
LOCAL_AI_MODEL=gpt-4o-mini

# Timeout for API requests in seconds (default is 120)
LOCAL_AI_TIMEOUT_SECONDS=120

# Number of pages to render and send to the model for visual PDFs (default is 1)
LOCAL_AI_RENDERED_PAGES=1
```

---

## ⚠️ Notes & OCR Setup

*   **Privacy notice**: If you configure a cloud AI endpoint (like OpenAI or Groq) in your `.env` file, the PDF document images/text will be sent to that provider for analysis. If you keep the default local settings (LM Studio), no data ever leaves your computer.
*   **Optional OCR**: To process scanned documents:
    1.  Install **Tesseract OCR** on your PC and add its path to your system environment variables.
    2.  Install **Poppler** (for PDF-to-image conversion) and add its `/bin` directory to your system environment variables.

---

## 📜 Changelog

- **v0.1.1 (2026-06-08)**: 
  * Upgraded dashboard visual design (3D perspective hovers, glassmorphism panels, floating background blobs).
  * Improved dark mode text contrast and theme-aware inputs/tables.
  * Enhanced database deletion to cascade to freelance expenses on purchase document deletion.
  * Added unit test suite for document/expense deletion cascades.

