# Income Ledger 🪙


![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![React](https://img.shields.io/badge/react-18-blue)
![FastAPI](https://img.shields.io/badge/fastapi-0.115-blue)

**Income Ledger** is a lightning-fast, privacy-first, locally hosted dashboard designed to help Indian freelancers and salaried professionals manage their finances, estimate taxes, and keep track of documents without handing their personal data over to third-party cloud services. 

I built this tool because I needed a simple way to automatically parse my salary slips and freelance invoices, map them to the correct Indian Financial Year (April 1 – March 31), and instantly know how much Advance Tax I owe.

Everything runs 100% locally on your machine. Your financial data stays yours. 🔒

---

## ✨ Features

- **🧾 Automated PDF Extraction:** Upload your salary slips and freelance invoices. The built-in extraction engine automatically pulls Basic, Gross, Net, TDS, PF, VPF, GST, and standard deductions.
- **🇮🇳 Indian Tax Regimes (Old vs. New):** Side-by-side comparison of your tax liability under both the Old and New tax regimes (fully updated for the Budget 2024 slabs).
- **📅 Advance Tax Scheduler:** Never miss an advance tax deadline again. The dashboard estimates your projected annual income and provides an exact quarterly payment schedule.
- **💼 Freelance Expense Tracking:** Easily log your business expenses and GST inputs to correctly offset your taxable freelance profits.
- **📊 Comprehensive Data Exports:** Need to send data to your CA? Export your entire ledger into a beautifully formatted, multi-year Excel Workbook, complete with a generated Balance Sheet.
- **🛡️ Secure Backup & Restore:** Generate complete ZIP backups of your database and uploaded documents in one click. 
- **🔎 Built-in Audit & Validation:** Keep your books clean with automated data validation reports, activity logs, and missing PDF reconciliation.

---

## 🛠️ Tech Stack

* **Backend:** [FastAPI](https://fastapi.tiangolo.com/) powered by Python, using `pypdf` and `pytesseract` for heavy lifting and document parsing.
* **Database:** SQLite (Requires zero configuration, stored entirely locally).
* **Frontend:** [React](https://reactjs.org/) + [Vite](https://vitejs.dev/), styled beautifully with modern glassmorphism, responsive data tables, and dynamic dark mode support.
* **Charts:** `Recharts` for visualizing monthly income trends and tax projections.

---

## 🚀 Quick Start (Windows)

You can get the entire suite up and running locally in under a minute. 

Just double-click the `Start-IncomeLedger.bat` file in the root directory, or run it via PowerShell:

```powershell
.\Start-IncomeLedger.ps1
```

**What the startup script handles for you:**
1. Creates a local Python virtual environment (`.venv`).
2. Installs all required backend (`requirements.txt`) and frontend (`package.json`) dependencies.
3. Fires up the FastAPI backend on `http://127.0.0.1:8001`.
4. Boots the Vite React frontend on `http://127.0.0.1:5173` and automatically opens your web browser.

---

## 🧠 Smart Extraction & OCR Configuration

The application uses an intelligent fallback system to extract data from your documents:
1. **Direct Parsing:** Reads embedded text straight from digital PDFs.
2. **Local OCR (Optional):** If a document is scanned, the app can fall back to Tesseract OCR to read the image text.

### How to Enable OCR for Scanned Documents:
If you plan to upload scanned images or flattened PDFs, you will need to install two standard open-source tools:
- **[Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)**: Install and add its path to your system environment variables.
- **[Poppler](https://github.com/oschwartz10612/poppler-windows/releases/)**: Install and add the `/bin` directory to your system environment variables.

### Local Privacy-First LM Studio Fallback
If the standard parsers fail to confidently read a complex invoice, the app can optionally connect to a local **LM Studio** instance running on your machine to do heavy-lifting extraction—ensuring your sensitive financial data never hits the public internet.

To configure local or custom service providers, create a `.env` file in your project root:

```env
# Example local LM Studio configuration
LOCAL_API_BASE_URL=http://127.0.0.1:1234/v1
LOCAL_API_KEY=lm-studio
LOCAL_MODEL=google/gemma-4-e4b
```

---

## 🤝 Contributing

This is a personal project, but I am completely open to pull requests! If you find a bug with the tax calculations, want to add support for a new type of salary slip, or improve the React frontend, feel free to open an issue or submit a PR.

