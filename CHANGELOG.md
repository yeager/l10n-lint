# Changelog

All notable changes to l10n-lint will be documented in this file.

## [1.3.6] - 2026-02-04

### Added
- **Enhanced verbose mode** (`--verbose` / `-V`):
  - Timing information for each file and total elapsed time
  - File size display
  - Detailed issue breakdown (fuzzy, missing, placeholder mismatches)
  - Locale detection info (shows detected language and locale directory)
  - Scan timing for directory operations
  - Per-file parsing time

### Fixed
- **fuzzy_count bug**: Fixed reference to undefined `result.fuzzy_count` 
  (now correctly uses local variable and matches by rule name)

## [1.3.4] - 2026-02-04

### Added
- **Translated man pages**: Man pages now available in 45 languages
  - Section headers translated (NAME, DESCRIPTION, OPTIONS, etc.)
  - Installed to `/usr/share/man/<lang>/man1/`

## [1.3.3] - 2026-02-04

### Added
- **Man page**: `man l10n-lint` now available
  - Installed to `/usr/share/man/man1/l10n-lint.1.gz`

## [1.3.2] - 2026-02-04

### Changed
- **Debian policy compliance**: Packages now follow Debian packaging guidelines
  - Locale files installed to `/usr/share/l10n-lint/locale/`
  - Added `/usr/share/doc/l10n-lint/copyright`
  - Fixed locale lookup path in script

### Fixed
- **Debian package**: Rebuilt with correct ar format and structure

## [1.3.1] - 2026-02-04

### Fixed
- **Debian package**: Rebuilt with correct ar format (was using macOS BSD format)
  - Package now installs correctly on Debian/Ubuntu systems

## [1.3.0] - 2026-02-04

### Fixed
- **Plural forms**: msgstr[0]/msgstr[1] now correctly detected as translations
  - Parser was matching `msgid` before `msgid_plural` due to prefix matching
- **length-ratio**: Increased default from 2x to 3x to avoid false positives
  - Compound words like "Förhandsgranskning" for "Preview" no longer trigger warnings
- **too-long**: Now compares with source length (only warns if >1.5x source AND >500 chars)
  - Long translations matching long sources no longer trigger warnings

## [1.2.1] - 2026-02-03

### Fixed
- Language detection now properly reads environment variables
- Priority order: `LANGUAGE` > `LC_ALL` > `LC_MESSAGES` > `LANG` > `locale.getlocale()`
- Fixed Japanese translation (was malformed)
- Fixed Chinese translation (was missing)

## [1.2.0] - 2026-02-03

### Added
- Localized output in 45+ languages
- Translations for: Afrikaans, Arabic, Bulgarian, Catalan, Czech, Danish, German, Greek, Spanish, Estonian, Basque, Persian, Finnish, French, Galician, Hebrew, Hindi, Croatian, Hungarian, Indonesian, Italian, Japanese, Georgian, Korean, Lithuanian, Latvian, Macedonian, Malay, Norwegian Bokmål, Dutch, Norwegian Nynorsk, Polish, Portuguese, Romanian, Russian, Slovak, Slovenian, Albanian, Serbian, Swedish, Thai, Turkish, Ukrainian, Vietnamese, Chinese

## [1.1.0] - 2026-02-03

### Added
- Localization support with Swedish translation

## [1.0.0] - 2026-02-03

### Added
- Initial release
- Lint `.po` (gettext) and `.ts` (Qt) files
- Check for missing translations, fuzzy entries, placeholder mismatches
- Length warnings for suspiciously long translations
- Duplicate entry detection
- GitHub repository support (lint without cloning)
- Multiple output formats: text, JSON, GitHub Actions
- Recursive directory scanning
- Strict mode (treat warnings as errors)
