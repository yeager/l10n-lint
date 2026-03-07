# l10n-lint

A comprehensive linter for localization files (`.po`, `.ts`). Finds missing translations, placeholder mismatches, terminology errors, and 20+ other common issues.

Built with Python. Part of the [Danne L10n Suite](https://github.com/yeager/).

![License](https://img.shields.io/badge/license-GPL--3.0-blue)
![Version](https://img.shields.io/badge/version-1.17.0-green)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

## Features

- **23 built-in checks** covering placeholders, formatting, terminology, consistency, and more
- **Swedish terminology validation** — catches common translation mistakes (e.g., "redaktör" → "redigerare")
- **Domain-specific rules** — music, web platform, and mail terminology
- **False friends detection** — flags Swedish–English false cognates
- **Consistency checking** — ensures the same source term gets the same translation
- **Multiple output formats** — text, JSON, HTML, GNU (Emacs-compatible), GitHub Actions
- **GTK4 GUI** — graphical interface for desktop use
- **GitHub integration** — lint repositories directly via `--github owner/repo`
- **Custom glossaries** — load your own term lists via `--glossary`
- **CI-friendly** — `--check` mode with exit codes, `--quiet` for summaries

## Installation

### Debian/Ubuntu

```bash
# Add the repository
curl -s https://yeager.github.io/debian-repo/KEY.gpg | sudo gpg --dearmor -o /usr/share/keyrings/yeager.gpg
echo "deb [signed-by=/usr/share/keyrings/yeager.gpg] https://yeager.github.io/debian-repo stable main" | sudo tee /etc/apt/sources.list.d/yeager.list
sudo apt update
sudo apt install l10n-lint
```

### Fedora/RPM

```bash
sudo dnf config-manager --add-repo https://yeager.github.io/rpm-repo/packages/yeager.repo
sudo dnf install l10n-lint
```

### pip

```bash
pip install l10n-lint
```

### From source

```bash
git clone https://github.com/yeager/l10n-lint.git
cd l10n-lint
pip install -e .
```

## Usage

```bash
# Lint a single file
l10n-lint translations/sv.po

# Lint a directory recursively
l10n-lint ./po/

# Lint a GitHub repository
l10n-lint --github yeager/l10n-lint

# Generate HTML report
l10n-lint -f html -o report.html ./translations/

# JSON output for CI pipelines
l10n-lint -f json -o results.json .

# Run only specific checks
l10n-lint --checks terminology,false-friends,consistency sv.po

# Skip noisy checks
l10n-lint --skip-checks source-equals-translation,length sv.po

# CI mode (exit code only)
l10n-lint --check --strict .

# Use custom glossary
l10n-lint --glossary my-terms.tsv sv.po
```

## Checks

| # | Check | Description |
|---|-------|-------------|
| 1 | `placeholders` | Format string mismatches (`%s`, `%d`, `{0}`, etc.) |
| 2 | `length` | Translations significantly longer/shorter than source |
| 3 | `punctuation` | Trailing punctuation differences |
| 4 | `capitalization` | Leading capitalization mismatches |
| 5 | `whitespace` | Leading/trailing whitespace, double spaces |
| 6 | `quotes` | Quote style consistency |
| 7 | `html-tags` | HTML tag mismatches between source and translation |
| 8 | `escapes` | Escape sequence mismatches (`\n`, `\t`, etc.) |
| 9 | `accelerators` | Keyboard accelerator (`&`, `_`) mismatches |
| 10 | `numerics` | Number changes between source and translation |
| 11 | `untranslated` | Empty or fuzzy translations |
| 12 | `repeated-words` | Repeated consecutive words |
| 13 | `source-equals-translation` | Translation identical to source (smart filtering) |
| 14 | `option-values` | CLI option/flag consistency |
| 15 | `number-localization` | Number format localization |
| 16 | `currency-localization` | Currency format issues |
| 17 | `date-format` | Date format localization |
| 18 | `newline-mismatch` | Newline count differences |
| 19 | `python-format` | Python-style format string validation |
| 20 | **`terminology`** | Swedish term consistency (new in 1.17) |
| 21 | **`domain-terminology`** | Domain-specific terms — music, web, mail (new in 1.17) |
| 22 | **`false-friends`** | Swedish–English false cognates (new in 1.17) |
| 23 | **`consistency`** | Same source → same translation within a file (new in 1.17) |

## What's New in 1.17.0

**Terminology intelligence** based on reviewing 143 Swedish PO files from the GNU Translation Project:

- **Terminology check** — flags common Swedish mistakes:
  - "redaktör" → "redigerare" (software editor)
  - "otydlig" → "luddig" (fuzzy, in translation context)
  - "öppen källa" → "öppen källkod" (open source)

- **Domain-specific rules** — auto-detects domain from source strings:
  - 🎵 Music: "personal" → "notsystem" (staff), "belopp" → "värde" (amount), "rörelse" → "sats" (movement)
  - 🌐 Web: "spårare" → "ärendehanterare" (issue tracker)

- **False friends** — catches Swedish–English false cognates:
  - actual ≠ aktuell, eventually ≠ eventuellt, billion ≠ biljon

- **Consistency** — flags when the same English phrase has different Swedish translations in one file

- **Smarter false-positive reduction** — URLs, format specifiers, and technical identifiers no longer flagged as "untranslated"

## What's New in 1.16.0

- 76% reduction in false positives (26,576 → 6,308 issues)
- `source-equals-translation`: -80% false positives
- `double-spaces`: -99.6%
- `html-tag-mismatch`: -98.7%
- `mixed-quotes`: -98%

## Output Formats

| Format | Flag | Use case |
|--------|------|----------|
| `text` | `-f text` | Terminal output (default) |
| `json` | `-f json` | CI pipelines, integrations |
| `html` | `-f html` | Shareable reports |
| `gnu` | `-f gnu` | Emacs `compile-mode` compatible |
| `github` | `-f github` | GitHub Actions annotations |

## Custom Glossary

Create a TSV file with terms to enforce:

```tsv
redaktör	redigerare	software editor context
spårare	ärendehanterare	issue tracker context
```

```bash
l10n-lint --glossary my-glossary.tsv sv.po
```

## GTK4 GUI

Launch the graphical interface:

```bash
l10n-lint --gtk
```

## Internationalization

l10n-lint is itself localized via Transifex. Currently available in Swedish, with more languages welcome.

## License

GPL-3.0

## Author

Daniel Nylander — [danielnylander.se](https://danielnylander.se)
