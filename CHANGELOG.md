# Changelog

All notable changes to l10n-lint will be documented in this file.

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
