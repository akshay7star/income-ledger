# Create Invoice V1 Tasks

Source: `create_invoice_implementation_plan.md`

## Implementation Status - 2026-07-27

- INV-001 through INV-022: implemented and covered by automated tests.
- INV-023: frontend production build, API lifecycle, responsive code review, and rendered PDF QA completed. Interactive browser QA remains pending because no in-app browser backend was available in this session.
- INV-024: full regression suite, production build, visual PDF verification, and documentation completed.

## V1 Decisions Used by These Tasks

- Seller profiles remain independent from Income Ledger users.
- `generated_invoices` has an optional `ledger_user_id` so an issued invoice can be linked to the correct user's income ledger.
- Issuing does not silently create income. The issue request includes an explicit `create_income_record` choice, defaulting to `false`.
- A linked income record uses taxable service value as `gross_amount`; GST is stored separately in metadata and TDS reduces `net_amount`.
- Each service line stores an explicit taxable `Amount`; `Rate` is the total GST percentage (for example, 18%, which splits into 9% CGST and 9% SGST for same-state supply).
- Expected TDS is entered as a percentage and calculated on the taxable subtotal, never on GST or the grand total.
- Draft PDF preview is supported and carries a visible `DRAFT` watermark.
- The filled Gen Aquarius PDF is the canonical visual reference; follow `invoice_pdf_layout_spec.md`.
- Bill To and Ship To are separate invoice concepts, with `Ship To same as Bill To` enabled by default.
- Issued invoices are immutable through the normal update route. Corrections require cancellation and a new invoice.
- Manual invoice numbers are unique per financial year.
- Seller/client records referenced by an invoice cannot be deleted in V1.

## Phase 1 — Domain and Database Foundation

### INV-001: Add ReportLab and generated-invoice storage

Dependencies: none

- Add a pinned `reportlab` dependency to `requirements.txt`.
- Add `GENERATED_INVOICE_DIR = DATA_DIR / "generated_invoices"` in `backend/app/database.py`.
- Create the directory from `ensure_data_dirs()`.
- Add a filename-sanitization helper; generated paths must remain inside this directory.

Acceptance:

- A clean installation includes ReportLab.
- App startup creates `data/generated_invoices`.
- Invoice numbers containing `/`, `\`, spaces, or punctuation cannot escape the storage directory.

### INV-002: Add invoice tables, constraints, and indexes

Dependencies: INV-001

- Add `invoice_profiles`, `invoice_clients`, `generated_invoices`, and `generated_invoice_items` to `init_db()`.
- Add `ledger_user_id` as a nullable foreign key to `users`.
- Add foreign keys for seller, client, item, and linked income relationships.
- Add `ON DELETE CASCADE` from invoice to line items.
- Add a unique index on `(financial_year, invoice_number)`.
- Add indexes for invoice status/date, seller, client, and ledger user.
- Store timestamps consistently with the current SQLite schema.

Acceptance:

- Existing databases migrate without data loss.
- Re-running `init_db()` is idempotent.
- Duplicate invoice numbers in the same FY fail; the same number in another FY is allowed.
- Deleting a draft removes its line items.

### INV-003: Define invoice API models and DTO shape

Dependencies: INV-002

- Add Pydantic models for seller profiles, clients, line items, invoice drafts, issue requests, and cancel requests.
- Add optional Ship To fields and Tally-style delivery/reference fields defined in `invoice_pdf_layout_spec.md`.
- Define one stable invoice detail DTO containing header, seller, client, items, calculated totals, status, PDF availability, and ledger linkage.
- Normalize blank optional strings and numeric defaults.
- Keep database rows out of the public API response where internal paths or raw metadata should not be exposed.

Acceptance:

- Invalid required fields return HTTP 422 or a clear HTTP 400.
- API models support future invoice dates.
- The issue model exposes `create_income_record` and requires `ledger_user_id` only when that option is true.

### INV-004: Implement GST, totals, FY, and amount-in-words helpers

Dependencies: INV-003

- Create `backend/app/invoices.py`.
- Use each line's explicit amount as its taxable value; treat rate as the total GST percentage.
- Apply CGST/SGST for matching seller/client state codes.
- Apply IGST for different state codes.
- Support no-GST treatment.
- Round monetary values deterministically to two decimals.
- Calculate subtotal, GST components, grand total, TDS from the taxable subtotal, and net receivable.
- Reuse the existing financial-year helper.
- Convert the final invoice amount to Indian-numbering words.

Acceptance:

- 18% same-state GST splits into 9% CGST and 9% SGST.
- 18% inter-state GST becomes 18% IGST only.
- The editor and PDF show each applicable GST component rate and amount separately instead of presenting only the combined GST slab.
- No-GST invoices have zero GST components.
- Invoice totals equal the sum of persisted line totals.
- Negative amounts, quantities, GST rates, or TDS rates are rejected; percentage rates cannot exceed 100 and quantity must be greater than zero.

### INV-005: Implement seller-profile CRUD

Dependencies: INV-003

- Add list, create, update, and delete service functions in `backend/app/invoices.py`.
- Validate GSTIN, PAN, state code, email, and required names when supplied.
- Enforce at most one default seller profile transactionally.
- Reject deletion when the profile is referenced by an invoice.

Acceptance:

- Creating a new default clears the previous default.
- Invalid GSTIN/PAN/state codes return actionable errors.
- Referenced profiles return a conflict instead of being deleted.

### INV-006: Implement client CRUD

Dependencies: INV-003

- Add list, create, update, and delete service functions.
- Validate GSTIN, PAN, state code, email, and required names when supplied.
- Reject deletion when the client is referenced by an invoice.

Acceptance:

- Clients can be reused across drafts.
- Invalid identifiers return actionable errors.
- Referenced clients return a conflict instead of being deleted.

### INV-007: Implement invoice draft CRUD

Dependencies: INV-004, INV-005, INV-006

- Implement list and detail queries with filters for FY, status, client, and ledger user.
- Create drafts and their items in one transaction.
- Recalculate all totals on the server; never trust client-supplied totals.
- Update draft header/items atomically.
- Delete drafts and associated preview PDFs if present.
- Reject normal update/delete operations for issued or cancelled invoices.
- Record `create_invoice_draft`, `update_invoice_draft`, and `delete_invoice_draft` audit events.

Acceptance:

- A failed item insert rolls back the entire draft.
- Draft updates replace/resequence items without leaving orphan rows.
- Issued invoices return HTTP 409 for edit/delete attempts.
- List responses include client name, totals, status, PDF availability, and linked-record state.

## Phase 2 — Issue, Ledger, and PDF Flow

### INV-008: Implement deterministic invoice PDF rendering

Dependencies: INV-004, INV-007

- Build a ReportLab renderer matching the existing Gen Aquarius-style tax invoice.
- Follow the US Letter geometry, table bounds, column widths, GST summary, signature block, and typography in `invoice_pdf_layout_spec.md`.
- Render seller, buyer, invoice metadata, service table, GST summary, amount in words, bank/payment details, notes, and signature label.
- Support multi-page line-item tables with repeated headers.
- Render a visible `DRAFT` watermark for previews.
- Generate PDFs through a temporary file and atomically replace the destination.
- Store only a safe relative PDF path in the database.

Acceptance:

- Preview and issued PDFs contain the invoice number, seller, client, items, GST totals, and grand total.
- Long addresses and descriptions wrap without overlapping.
- Issued PDFs do not contain the draft watermark.
- Repeated generation does not leave partial files.

### INV-009: Implement draft preview and PDF download

Dependencies: INV-008

- Add a preview operation that renders current draft data without changing invoice status.
- Generate preview and final output through the same renderer; any draft edit invalidates the previous preview.
- Add a download operation for draft or issued PDFs.
- Use `FileResponse` with a safe filename and `application/pdf`.
- Regenerate a draft preview when draft data changes.
- Return 404 when a stored PDF is missing instead of exposing a filesystem error.

Acceptance:

- Users can preview and download a draft PDF.
- Updating a draft changes the next preview.
- Final print/download bytes match the final PDF displayed in preview.
- Print/download actions remain disabled until the preview loads successfully.
- Path traversal through invoice numbers or stored paths is impossible.

### INV-010: Implement transactional invoice issue flow

Dependencies: INV-008

- Revalidate the full invoice and invoice-number uniqueness at issue time.
- Capture an immutable issue snapshot of seller, client, item, totals, and tax fields in `metadata_json`.
- Generate the final PDF.
- Set status to `issued`, populate `issued_at`, and lock normal edits.
- Record an `issue_invoice` audit event.
- Make repeated issue requests idempotent or return a clear conflict without duplicating side effects.

Acceptance:

- An invoice is not marked issued if PDF generation fails.
- An issued invoice always has an issue timestamp, snapshot, and readable final PDF.
- Profile/client edits after issue do not alter the issued PDF or snapshot.

### INV-011: Add optional linked income-record creation

Dependencies: INV-010

- When `create_income_record` is true, require a valid `ledger_user_id`.
- Create one `freelance_invoice` income record in the same logical issue transaction.
- Set `gross_amount` to invoice subtotal, `gst_amount` to collected GST, `tds_amount` to expected TDS, and `net_amount` to subtotal minus TDS.
- Add generated invoice ID/number, billable period, GSTINs, GST treatment, and PDF path to income metadata.
- Store `income_record_id` on the invoice.
- Record `create_invoice_income_record`.
- Prevent duplicate linked income records on retries.

Acceptance:

- Issuing without linkage creates no income record.
- Issuing with linkage creates exactly one correctly valued income record.
- Dashboard and tax summaries count the new record using existing conventions.

### INV-012: Implement invoice cancellation

Dependencies: INV-010, INV-011

- Allow only issued invoices to be cancelled.
- Require and store a cancellation reason in metadata.
- Set status to `cancelled` and record `cancel_invoice`.
- Preserve the issued PDF and audit trail.
- Do not automatically delete the linked income record; return its ID so the UI can warn that ledger correction is separate.

Acceptance:

- Drafts cannot be cancelled.
- Cancelled invoices cannot be edited, issued again, or physically deleted.
- Cancellation never silently changes an existing ledger record.

## Phase 3 — API Surface

### INV-013: Add profile and client routes

Dependencies: INV-005, INV-006

- Add all planned `GET`, `POST`, `PUT`, and `DELETE` routes in `backend/app/main.py`.
- Map validation, not-found, duplicate, and reference-conflict errors to consistent status codes.
- Keep routes protected by the existing authentication middleware.

Acceptance:

- CRUD endpoints match the plan and return stable DTOs.
- Referenced-record deletion returns HTTP 409.
- Unauthenticated requests remain blocked.

### INV-014: Add invoice lifecycle routes

Dependencies: INV-009, INV-010, INV-011, INV-012

- Add list, detail, create, update, issue, cancel, PDF, preview, and draft-delete routes.
- Support list query filters without requiring a selected user.
- Stream PDF responses instead of loading files into JSON.

Acceptance:

- Every planned route has happy-path and error-path coverage.
- Lifecycle conflicts use HTTP 409.
- PDF responses include a safe download filename.

## Phase 4 — Frontend

### INV-015: Add invoice navigation and data state

Dependencies: INV-014

- Add an `Invoices` primary navigation button using `ReceiptText` or `FileText`.
- Add an `InvoicesView` branch to the current `activeView` rendering.
- Add API loading, refresh, error, and empty states for invoices, profiles, and clients.
- Preserve the selected financial year when entering the invoice view.

Acceptance:

- Invoice navigation works without disrupting existing views.
- Loading and API errors are visible and recoverable.
- `npm run build` passes.

### INV-016: Build seller-profile and client management UI

Dependencies: INV-015

- Add dense forms/modals for create and edit.
- Add selectors that can launch profile/client creation without losing draft input.
- Show default seller and GST/state details in selectors.
- Confirm deletion and display reference-conflict errors.

Acceptance:

- Newly created profiles/clients are immediately selectable.
- Editing refreshes selectors and the current draft.
- Referenced records cannot be deleted from the UI.

### INV-017: Build invoice editor with live calculations

Dependencies: INV-016

- Add invoice header, supply, payment, TDS percentage, notes, and billable-period fields.
- Add `Ship To same as Bill To` plus separate shipping fields when disabled.
- Add the optional delivery note, references, buyer order, dispatch, destination, and delivery-term fields from the PDF layout specification.
- Add an editable service-line table with GST Rate and taxable Amount as separate fields, plus add/remove/reorder support.
- Calculate a live preview of subtotal, GST components, expected TDS amount, grand total, and net receivable.
- Use server-returned totals as authoritative after save.
- Support save draft and update draft.
- Warn about duplicate-looking invoice-number patterns without blocking valid manual numbers.

Acceptance:

- Same-state, inter-state, and no-GST previews update as inputs change.
- At least one valid item is required.
- Future invoice dates can be saved.
- Server validation errors map to the relevant form area.

### INV-018: Build invoice list and lifecycle actions

Dependencies: INV-015, INV-017

- Show number, date, client, status, taxable amount, GST, grand total, PDF, and ledger linkage.
- Add FY/status/client filters.
- Allow edit/delete for drafts only.
- Add preview and download actions.
- Make preview the required gateway to app-level print/download actions.
- Add an issue confirmation that includes an optional ledger-link checkbox and ledger-user selector.
- Add cancellation confirmation with reason and linked-ledger warning.

Acceptance:

- Actions change appropriately for draft, issued, and cancelled states.
- Issue confirmation clearly states that normal editing will be locked.
- Successful actions refresh the list and open/download the expected PDF.

### INV-019: Add responsive invoice styling and accessibility

Dependencies: INV-016, INV-017, INV-018

- Add invoice-specific styles to `frontend/src/styles.css`.
- Keep the dense operational look consistent with current tables and modals.
- Make line-item editing usable on narrow screens.
- Add labels, accessible names, focus handling, keyboard dismissal, and status announcements.

Acceptance:

- Editor and list remain usable on desktop and mobile widths.
- Modals have sensible keyboard focus and do not rely on color alone for status.
- Light and dark themes remain readable.

## Phase 5 — Backup, Export, and Verification

### INV-020: Include generated PDFs in backup and restore

Dependencies: INV-001, INV-008

- Extend the backup manifest with a generated-invoice directory and file count.
- Include `data/generated_invoices` under a dedicated ZIP prefix.
- Update backup validation to allow only the declared safe prefixes.
- Restore generated PDFs and continue running database migrations afterward.
- Preserve compatibility with existing format-version-1 backups or explicitly bump the format with a compatibility path.

Acceptance:

- A backup/restore round trip preserves issued PDFs.
- Older backups without generated invoices still restore.
- Unexpected ZIP entries and path traversal remain rejected.

### INV-021: Add a Generated Invoices workbook sheet

Dependencies: INV-007, INV-011

- Add a `Generated Invoices` sheet to workbook export.
- Export number, status, client, date, taxable amount, GST components, grand total, linked user, and income record ID.
- Do not expose local absolute PDF paths.

Acceptance:

- The sheet works for single- and multi-year exports.
- Issued and cancelled invoices remain visible for audit.
- Existing workbook imports/exports continue passing.

### INV-022: Add backend unit and API tests

Dependencies: INV-014, INV-020, INV-021

- Create `tests/test_invoices.py`.
- Cover profile/client CRUD and validation.
- Cover draft CRUD, uniqueness, future dates, and lifecycle restrictions.
- Cover same-state, inter-state, no-GST, rounding, amount words, and invalid inputs.
- Cover preview/final PDF generation and expected extracted text.
- Assert the 612 x 792 point page size, key table labels, tax-summary variant, draft watermark, and final watermark removal.
- Cover optional ledger linkage, retry safety, cancellation, and audit events.
- Cover backup/restore and workbook export.

Acceptance:

- All cases listed in the source plan have automated coverage.
- Tests isolate database and generated-PDF directories with `tmp_path`.
- The full backend test suite passes.

### INV-023: Add frontend verification coverage

Dependencies: INV-019

- Add testable calculation helpers or component tests if a frontend test runner is introduced.
- At minimum, document and run checks for list rendering, editor rendering, line totals, draft save, preview invalidation, preview-first print/download gating, issue lock, PDF download, and status-specific actions.
- Verify no console errors during the complete workflow.

Acceptance:

- Production frontend build passes.
- Manual/browser QA evidence covers the complete create → preview → issue → download flow.
- Existing dashboard, upload, extraction, expense, tax, and reconciliation views still work.

### INV-024: Complete release regression and documentation

Dependencies: INV-022, INV-023

- Run the complete Python test suite and frontend production build.
- Perform an end-to-end invoice smoke test using temporary data.
- Update `README.md`, `CHANGELOG.md`, and dependency/setup documentation.
- Document V1 limitations: no IRN, GST portal, email, recurring invoices, multi-currency, inventory, or credit/debit notes.

Acceptance:

- V1 acceptance criteria from the source plan are all demonstrated.
- No uploaded PDFs, generated test PDFs, databases, backups, credentials, or environment files are staged in Git.
- Release notes identify schema, dependency, backup, and user-facing changes.

## Recommended Execution Order

1. INV-001 → INV-004
2. INV-005 and INV-006
3. INV-007
4. INV-008 → INV-012
5. INV-013 → INV-014
6. INV-015 → INV-019
7. INV-020 and INV-021
8. INV-022 → INV-024

## Definition of Done

- All INV-001 through INV-024 acceptance checks pass.
- The invoice lifecycle is transactional and auditable.
- Issued invoice totals, PDF content, and optional ledger record agree.
- Issued and cancelled invoices cannot be silently mutated or deleted.
- Generated PDFs survive backup/restore.
- Existing Income Ledger features pass regression testing.
