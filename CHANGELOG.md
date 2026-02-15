# Changelog

## [1.15.4] - 2026-02-15

### Fixed
- Fixed false trailing-whitespace warnings on strings ending with `\n` (now only flags actual spaces/tabs)
- Fixed CLI translations not loading on Fedora/RPM installs (added `/usr/share/locale` to search paths)
- Removed stray `.po` and `.po~` files from locale directory — only `.mo` files are now shipped in packages

## [1.14.9] - 2026-02-07

### Fixed
- **l10n-lint-gtk 1.2.9** - Metadata parsing fix
  - Last-Translator and PO-Revision-Date now display correctly in the GTK interface

## [1.14.8] - 2026-02-06

### Fixed
- **l10n-lint-gtk 1.2.8** - Menu and translation improvements
  - Set menu button as primary for better popover behavior
  - Keep menu button reference to prevent GC issues
  - Translated missing "HTML tags mismatch" string to Swedish

## [1.14.7] - 2026-02-06

### Fixed
- **l10n-lint-gtk 1.2.7** - Critical fixes
  - Fixed "L10nLinter has no attribute 'lint'" - method is lint_file()
  - Fixed ampersand markup error in Swedish translation
  - About dialog already exists with full project info and copyright

## [1.14.6] - 2026-02-06

### Fixed
- **l10n-lint-gtk 1.2.6** - Fix gettext function shadowing
  - Fixed "UnboundLocalError: cannot access local variable '_'" in PreferencesWindow
  - Variable `_` used to ignore tuple values was shadowing gettext function

## [1.14.5] - 2026-02-06

### Fixed
- **l10n-lint-gtk 1.2.5** - Module import fix
  - Fixed "ModuleNotFoundError: No module named 'l10n_lint'" when installed via deb package
  - l10n-lint now also installed as Python module in /usr/share/l10n-lint/
  - Added /usr/share/l10n-lint to module search path

## [1.14.4] - 2026-02-06

### Fixed
- **l10n-lint-gtk 1.2.4** - Complete Swedish translation
  - All menu items translated (Preferences, About, Quit, Keyboard Shortcuts)
  - All GTK interface strings translated (170+ strings)
  - All lint rule names and descriptions translated
  - All error messages and status texts translated

## [1.14.3] - 2026-02-06

### Added
- **l10n-lint-gtk 1.2.3** - Major feature update:
  - **Lint rule preferences** - Choose which checks to run (Preferences → Lint Rules)
  - **File metadata panel** - Shows language, last translator, revision date, project info
  - **Statistics display** - Entries, translated, untranslated, fuzzy counts
  - **Rule filter dropdown** - Filter issues by specific rule type
  - **Quick actions** - Enable all / Disable all / Reset defaults buttons
  - **Better file type detection** - Distinguishes between .po and .ts files
  - **Settings persistence** - Saves configuration to ~/.config/l10n-lint/settings.json
  - **Improved drag & drop** - Shows metadata immediately when file is dropped

### Changed
- Preferences window redesigned with grouped lint rule toggles
- File filter in open dialog now defaults to localization files (*.po, *.ts)

## [1.14.2] - 2026-02-06

### Added
- **l10n-lint-gtk 1.2.2** - Drag and drop support
  - Drop .po or .ts files directly onto window to lint them
  - Auto-starts linting when file is dropped
  - Visual feedback during drag operation
  - Also accepts directories

## [1.14.1] - 2026-02-06

### Fixed
- **l10n-lint-gtk 1.2.1** - Fixed ModuleNotFoundError when running installed package
  - GTK interface now searches multiple paths for l10n_lint module
  - Works with both system packages and local development installs

## [1.14.0] - 2026-02-05

### Added
- **l10n-lint-gtk 1.2.0** - Major GTK interface improvements:
  - Sidebar with recent files history
  - Filter bar (filter by severity, search issues)
  - Statistics panel (files, entries, translated, untranslated, fuzzy)
  - Export reports (HTML, JSON, plain text)
  - Preferences dialog
  - Keyboard shortcuts (Ctrl+O, Ctrl+Return, Ctrl+E, Ctrl+Q)
  - Clickable issues with copy-to-clipboard
  - Progress indicator with file names
  - GitHub repository support directly in GUI
  - Full i18n support (47 languages)

### Changed
- GTK interface now available as separate `l10n-lint-gtk` package

## [1.13.1] - 2026-02-05

### Fixed
- Fixed xgettext warning about embedded URL in translatable string
- Epilog examples are now properly separated from translatable text

## [1.13.0] - 2026-02-05

### Added
- **GTK launch flag** (`-G/--gtk`): Launch graphical interface from CLI
  - `l10n-lint -G` starts the GTK interface
  - `l10n-lint -G file.po` starts GTK with file pre-loaded
  - Works with both local dev and system-installed versions

## [1.12.0] - 2026-02-05

### Added
- **GTK translations** – Full i18n support for GTK interface
  - 47 languages supported (same as CLI)
  - Gettext integration with shared .po/.mo files

### Changed
- GTK version bumped to 1.1.0

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
