# Changelog

## [1.11.0] - 2026-02-05

### Added
- **GTK graphical interface** (`l10n-lint-gtk`):
  - Modern GTK4/libadwaita interface
  - File browser for selecting files/directories
  - Real-time linting with progress indicator
  - Color-coded issue display (errors, warnings, info)
  - Summary statistics
  - About dialog with version info
  - Run with: `python3 l10n_lint_gtk.py`

## [1.10.0] - 2026-02-05

### Added
- **URL support**: Lint files directly from HTTP(S) URLs
  - Auto-detects URLs in path arguments
  - Supports both `.po` and `.ts` files
  - Example: `l10n-lint https://example.com/locale/sv.po`
- Verbose mode shows fetch timing for URL files

## [1.9.0] - 2026-02-05

### Added
- **Enhanced verbose mode** (`-V/--verbose`):
  - Entry count per file
  - Issue breakdown by rule (top 10)
  - Processing speed (files/sec, entries/sec)
  - Info-level issue count
- `entries_checked` tracking in LintResult
- `issues_by_rule()` method for rule statistics
- `info_count` property in LintResult

## [1.8.0] - 2026-02-04

### Added
- Test suite with test files for all 22 lint rules
- tests/test_all_rules.po - PO file testing all rules
- tests/test_vanished.ts - TS file testing vanished rule

### Fixed
- escaped-chars-mismatch now counts actual newlines/tabs after parsing
- Expanded COMMON_ENGLISH with UI words (click, button, save, etc.)

### Changed
- escape-chars check now reports count differences (e.g., "\n: 2→1")

## [1.7.0] - 2026-02-04

### Added
- HTML report output (`-f html`)
- JSON report output (`-f json`)
- Output to file (`-o/--output FILE`)
- 45 language translations

### Changed
- Improved Swedish translations

## [1.6.0] - 2026-02-04

### Added
- 16 new lint rules including:
  - inconsistent-punctuation
  - inconsistent-capitalization
  - trailing-whitespace
  - double-spaces
  - mixed-quotes
  - html-tag-mismatch
  - escaped-chars-mismatch
  - keyboard-shortcut-missing
  - nordic-accelerator
  - numeric-mismatch
  - untranslated-words
  - repeated-words
  - source-equals-translation
  - option-value-missing
