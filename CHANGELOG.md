# Changelog

All notable changes to this project will be documented in this file.

## [v0.1.1] - 2026-06-08

### Added
- Implemented unit tests in `tests/test_deletion.py` verifying cascading document deletion functionality.

### Changed
- Upgraded frontend visual design with interactive 3D perspective hover cards, glassmorphism panels, and smooth floating ambient backdrop blobs.
- Improved dark mode contrast, readability, and theme compatibility for inputs, selects, and table rows.
- Polished layout and color schemes for income trend bar charts and tax prediction line charts.
- Updated database repository (`delete_document`) to automatically cascade and delete linked freelance expenses when a purchase invoice document is deleted.
