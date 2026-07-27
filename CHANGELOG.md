# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [v0.3.0] - 2026-07-27

### Added
- Added reusable seller profiles and invoice clients.
- Added draft, preview, issue, cancellation, and PDF download flows for GST service invoices.
- Added same-state CGST/SGST, inter-state IGST, no-GST, TDS, amount-in-words, shipping, payment, and Tally-style reference fields.
- Added preview-first printing/downloading with a print-accurate draft watermark.
- Added optional linked freelance income records for issued invoices.
- Added generated-invoice audit events, workbook export data, API coverage, and PDF regression tests.

### Changed
- Backups now include generated invoice PDFs while remaining compatible with older backups.
- Added the pinned ReportLab dependency for deterministic local PDF generation.
- Invoice service-line `Rate` now means GST percentage, with a separate taxable `Amount` field.
- Expected TDS is now entered as a percentage and calculated on taxable value; existing fixed-TDS drafts are migrated to the equivalent rate.
- Same-state invoice previews now show separate CGST and SGST rates and amounts (for example, 9% + 9%) instead of printing only the combined 18% rate.
- Reworked the GitHub README with the complete feature set, invoice workflow, architecture, setup, privacy, testing, and release information.

## [v0.2.0] - 2026-07-27

### Added
- Added editable expenses with automatic GST calculations, payment methods, and month/year filtering.
- Included expense payment methods in workbook imports/exports and AI tax-planning context.
- Added support for extracting payer, invoice totals, GST, TDS, and dates from compact Tally service invoices.
- Added regression coverage for expense updates, payment methods, backup migrations, workbook data, and compact invoice extraction.

### Fixed
- Run database migrations after restoring older backups so newly required expense fields are available.
- Persist and apply the selected theme before the React app renders.

## [v0.1.2] - 2026-06-09

### Added
- Added regression coverage in `tests/test_tax_projection.py` for elapsed financial-year projection behavior.

### Fixed
- Replaced the document delete browser confirm flow with an in-app confirmation modal so document deletion reliably triggers from the dashboard.
- Corrected dashboard tax prediction annualization to use elapsed financial-year months instead of only counting months with uploaded records.
- Aligned the tax comparison cards under the prediction chart with projected year-end old/new regime values.
- Preserved the active user selection across refreshes within the same browser session instead of resetting to `All users`.
- Cleaned up tax regime labels in the dashboard UI to display `Old regime` and `New regime (default)`.

## [v0.1.1] - 2026-06-08

### Added
- Implemented unit tests in `tests/test_deletion.py` verifying cascading document deletion functionality.

### Changed
- Upgraded frontend visual design with interactive 3D perspective hover cards, glassmorphism panels, and smooth floating ambient backdrop blobs.
- Improved dark mode contrast, readability, and theme compatibility for inputs, selects, and table rows.
- Polished layout and color schemes for income trend bar charts and tax prediction line charts.
- Updated database repository (`delete_document`) to automatically cascade and delete linked freelance expenses when a purchase invoice document is deleted.
