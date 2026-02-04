# Changelog

All notable changes to l10n-lint will be documented in this file.

## [1.5.0] - 2026-02-04
## [1.6.0] - 2026-02-04

### Added
- **option-value-missing** - Check for inconsistent option value placeholders
- Fully translated help text (positional arguments, options, -h, -v)

### Changed
- Custom TranslatedHelpFormatter for complete localization


### Added - 16 new lint rules!

**Typography & formatting:**
- **inconsistent-punctuation** - Ending punctuation missing or different from source
- **inconsistent-capitalization** - First letter case doesn't match source
- **trailing-whitespace** - Translation has trailing whitespace
- **double-spaces** - Double spaces in translation
- **mixed-quotes** - Mixed quote styles (`"` vs `"` vs `„`)

**Technical:**
- **html-tag-mismatch** - HTML tags don't match between source and translation
- **escaped-chars-mismatch** - `\n`, `\t`, `\\` don't match
- **keyboard-shortcut-missing** - Accelerator (`&File`) missing in translation
- **nordic-accelerator** - Nordic characters (å,ä,ö) used as keyboard accelerator
- **numeric-mismatch** - Numbers from source missing in translation

**Quality:**
- **untranslated-words** - Common English words left in translation
- **repeated-words** - Repeated words like "and and"
- **source-equals-translation** - Translation identical to source
- **suspicious-length** - Translation is very short compared to source (<0.2x)

## [1.4.0] - 2026-02-04

### Added
- **`-q/--quiet`**: Show only summary line (for large projects)
- **`--check`**: Exit code only, no output (for CI/pre-commit hooks)
- **`--skip-fuzzy`**: Ignore fuzzy warnings

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
