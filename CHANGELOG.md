# Changelog

All notable changes to this project will be documented in this file.

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
