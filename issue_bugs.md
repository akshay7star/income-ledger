# Project Bug & Issue Report

This document audits the codebase of the **Income Ledger** project and outlines active bugs, logical inconsistencies, resource management issues, and performance bottlenecks, along with recommended fixes.

---

## 1. Asynchronous Upload Queue Race Condition (UX / Frontend)
* **File**: [main.jsx](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/frontend/src/main.jsx) (in `processUploadQueue` loop)
* **Observed Behavior**:
  When a user uploads a batch of multiple PDFs, the `processUploadQueue` function loops through all files asynchronously. If a file fails auto-confirmation, the code calls `setReviewDoc(doc)` immediately to open the `ReviewModal` and sets the status banner. However, the loop does **not** pause and wait for the user to complete their manual review. It continues processing subsequent files in the background. If another file in the same batch also needs review, it calls `setReviewDoc(doc)` again, abruptly switching the modal context under the user's nose.
* **Impact**:
  Severe user experience issue. If a user is in the middle of typing corrections or clicking fields in the `ReviewModal` for File 1, the modal will suddenly swap its inputs to File 2 as soon as the background parser completes. Any half-edited fields for File 1 are lost.
* **Recommended Fix**:
  Accumulate all documents that need review during queue processing into a temporary array (e.g., `needsReviewDocs`). Open the `ReviewModal` for the first document. In the modal's `onSaved` or `onClose` callback, pop/shift the next document from the queue and open it sequentially, rather than driving the modal state straight from the async loop.

---

## 2. Stale Document State on Linked Expense Deletion (Database / Backend)
* **File**: [repositories.py](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/repositories.py) (in `delete_expense`)
* **Observed Behavior**:
  When an income record is deleted in `delete_income_record`, the repository checks if it was created from an uploaded document. If so, it updates the document's status back to `'needs_review'` so it can be re-evaluated:
  ```python
  if document_id:
      conn.execute("UPDATE documents SET status = 'needs_review' WHERE id = ?", (document_id,))
  ```
  However, when deleting a freelance expense in `delete_expense`, the repository does **not** touch the associated document.
* **Impact**:
  If a user deletes an expense that was originally confirmed from a `purchase_expense` PDF, the PDF document status remains `'confirmed'` in the sidebar, but its associated record in the database is gone. The document's `extracted_json` metadata continues to point to a non-existent `expense_id`.
* **Recommended Fix**:
  Update `delete_expense` to find any document that references this expense in its `extracted_json` and update its status back to `'needs_review'` and clear the `expense_id` key:
  ```python
  # Find document referencing this expense_id
  # (or select all documents and parse extracted_json to match expense_id)
  # Update document status to 'needs_review'
  ```

---

## 3. GST Excluded from Freelance Invoice Mathematical Validation (Validation / Backend)
* **File**: [extraction.py](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/extraction.py) (in `validate_local_extraction`)
* **Observed Behavior**:
  The mathematical validation for freelance invoices is defined as:
  ```python
  if doc_type == "freelance_invoice":
      tds = data.get("tds_amount", 0.0)
      expected_net = gross - tds
      return abs(expected_net - net) <= 10.0
  ```
  However, freelance invoices often contain **GST** (Goods and Services Tax). In such cases, the invoice's grand total net amount is `gross + gst - tds` (or `gross + gst` if TDS is deducted post-facto on payment).
* **Impact**:
  For any freelance invoice containing a non-zero GST amount, `gross - tds` will fail to match the net total (by exactly the GST amount). The local parser will reject the extraction as failed validation, causing the system to fall back to the slow LM Studio Local AI stage, even when all fields were extracted 100% correctly by regex.
* **Recommended Fix**:
  Update the formula to account for optional GST:
  ```python
  if doc_type == "freelance_invoice":
      tds = data.get("tds_amount", 0.0)
      gst = data.get("gst_amount", 0.0)
      expected_net = gross + gst - tds
      # Or allow multiple valid layouts: gross - tds, gross + gst, or gross + gst - tds
      return (
          abs(gross - tds - net) <= 10.0 or
          abs(gross + gst - tds - net) <= 10.0 or
          abs(gross + gst - net) <= 10.0
      )
  ```

---

## 4. SQLite Connection Resource Leak (Resource Management / Backend)
* **File**: [database.py](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/database.py) (in `get_connection`) and usage across [repositories.py](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/repositories.py)
* **Observed Behavior**:
  Throughout the backend, database operations are run using the pattern:
  ```python
  with get_connection() as conn:
      conn.execute(...)
  ```
  In Python's standard library `sqlite3`, the connection's context manager **only** manages transaction boundaries (committing changes on success or rolling back on exception). It **does not close** the database connection.
* **Impact**:
  Connections remain open in memory until Python's garbage collector destroys the connection objects. Under high concurrent API load, this can lead to database file locks (throwing `sqlite3.OperationalError: database is locked`) or file descriptor exhaustion.
* **Recommended Fix**:
  Ensure connections are closed by wrapping them with `contextlib.closing` or explicitly calling `conn.close()` in `finally` blocks:
  ```python
  from contextlib import closing

  # Example helper:
  # def execute_query(query, params=()):
  #     with closing(get_connection()) as conn:
  #         return conn.execute(query, params).fetchall()
  ```

---

## 5. Overwriting Confirmed Records on Duplicate PDF Upload (Database State / Backend)
* **File**: [repositories.py](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/repositories.py) (in `create_document`)
* **Observed Behavior**:
  If a user uploads a document that has the exact same SHA-256 file hash as an existing database document, `create_document` locates the record and resets its fields:
  ```python
  if existing:
      conn.execute(
          """
          UPDATE documents
          SET document_type = ?, status = 'needs_review', extracted_text = ?, ...
          WHERE id = ?
          """,
          ...
      )
  ```
* **Impact**:
  If a user uploads a duplicate of an already confirmed and verified invoice, it will overwrite the confirmed state, change the status back to `'needs_review'`, delete or duplicate the associated `income_records`, and revert the document back to the default parsed extraction values, throwing away manual corrections.
* **Recommended Fix**:
  Check if the existing document is in a `'confirmed'` status. If so, return it immediately without altering its state or database records, or raise a warning to the user that a duplicate file was ignored.

---

## 6. Disk I/O Bottleneck in Base64 Encoding for AI (Performance / Backend)
* **File**: [extraction.py](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/extraction.py) (in `render_pdf_pages_for_ai`)
* **Observed Behavior**:
  To send PDF pages to a local vision model, the code renders the pages as PIL Image objects, writes them to temporary files on disk, reads them back as bytes, and base64-encodes them:
  ```python
  image_path = Path(temp_dir) / f"page-{len(image_urls) + 1}.png"
  image.save(image_path, "PNG")
  encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
  ```
* **Impact**:
  Slowing down the OCR/AI extraction phase with unnecessary disk writes and reads.
* **Recommended Fix**:
  Encode the PIL Image objects directly to base64 in memory using `io.BytesIO`:
  ```python
  import io

  buffer = io.BytesIO()
  image.save(buffer, format="PNG")
  encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
  image_urls.append(f"data:image/png;base64,{encoded}")
  ```

---

## 7. Lack of Positive Value Validation on Manual Input (Business Logic / API)
* **File**: [main.py](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/backend/app/main.py) (in `ExpenseCreate` schema)
* **Observed Behavior**:
  The `ExpenseCreate` Pydantic model does not enforce positive values for `amount` or `gst_amount`.
* **Impact**:
  Users can type negative numbers in the Expense form, which are saved in the SQLite database without validation warnings, potentially corrupting tax estimates and dashboard summaries.
* **Recommended Fix**:
  Add Pydantic field validators or use standard constraints:
  ```python
  amount: float = Field(..., gt=0)
  gst_amount: float = Field(0.0, ge=0)
  ```

---

## 8. Viewport Displacement & Positioning Clashes for Modals (CSS Class Collision)
* **File**: [styles.css](file:///c:/Users/aksha/OneDrive/Desktop/Learning/Project/Income%20Ledger/frontend/src/styles.css) (in `.modal` and `.modalBackdrop` classes)
* **Observed Behavior**:
  Both the extraction `ReviewModal` and `EditUserModal` use the CSS class name `.modal` for their dialog panels. However, the project also imports **Bootstrap CSS**, which reserves `.modal` as a global layout class (with its own `position: fixed`, `z-index`, `display`, etc.).
* **Impact**:
  A class collision occurs. The browser applies both Bootstrap's modal styles and our local glassmorphism overrides simultaneously, causing the modal to render at displaced coordinates (e.g., sticking to the top of the page height). If the user has scrolled down the dashboard, the modal opens off-screen, forcing the user to scroll up or search for it.
* **Recommended Fix**:
  Rename our custom classes in both `styles.css` and `main.jsx` to unique, non-colliding names, such as `.ledger-modal` and `.ledger-modal-backdrop`.

