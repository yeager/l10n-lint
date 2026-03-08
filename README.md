# l10n-lint

![Version](https://img.shields.io/badge/version-1.19.0-blue)
![License](https://img.shields.io/badge/license-GPL--3.0-green)
![Python](https://img.shields.io/badge/python-3.9+-blue)

## Description

A comprehensive linter for localization files (`.po`, `.ts`). Finds missing translations, placeholder mismatches, terminology errors, and 20+ other common issues.

Built with Python as part of the professional L10n Tool Suite, l10n-lint provides essential quality assurance for translation projects, helping maintain consistency and accuracy across multilingual applications.

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

### APT (Debian/Ubuntu)
```bash
echo "deb https://yeager.github.io/debian-repo stable main" | sudo tee /etc/apt/sources.list.d/yeager-l10n.list
curl -fsSL https://yeager.github.io/debian-repo/yeager-l10n.gpg | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/yeager-l10n.gpg
sudo apt update && sudo apt install l10n-lint
```

### DNF (Fedora)
```bash
sudo dnf config-manager --add-repo https://yeager.github.io/rpm-repo/yeager-l10n.repo
sudo dnf install l10n-lint
```

### pip
```bash
pip install l10n-lint
```

## Building from source

```bash
git clone https://github.com/yeager/l10n-lint
cd l10n-lint
pip install -e .
```

## Usage

Basic usage:
```bash
# Lint a single file
l10n-lint translations/sv.po

# Lint a directory recursively
l10n-lint ./po/

# Lint a GitHub repository
l10n-lint --github yeager/l10n-lint
```

Advanced options:
```bash
# Generate HTML report
l10n-lint -f html -o report.html ./translations/

# JSON output for CI pipelines
l10n-lint -f json -o results.json .

# Run only specific checks
l10n-lint --checks terminology,false-friends,consistency sv.po

# CI mode (exit code only)
l10n-lint --check --strict .
```

See the manual for complete options:
```bash
man l10n-lint
l10n-lint --help
```

## Checks Available

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
| 20 | **`terminology`** | Swedish term consistency |
| 21 | **`domain-terminology`** | Domain-specific terms — music, web, mail |
| 22 | **`false-friends`** | Swedish–English false cognates |
| 23 | **`consistency`** | Same source → same translation within a file |

## Output Formats

| Format | Flag | Use case |
|--------|------|----------|
| `text` | `-f text` | Terminal output (default) |
| `json` | `-f json` | CI pipelines, integrations |
| `html` | `-f html` | Shareable reports |
| `gnu` | `-f gnu` | Emacs `compile-mode` compatible |
| `github` | `-f github` | GitHub Actions annotations |

## Translation

Translations are managed on Transifex: https://app.transifex.com/danielnylander/l10n-lint/

Currently supported: Swedish, Danish, German, Spanish, Finnish, French, Italian, Norwegian Bokmål, Dutch, Polish, Portuguese (Brazil)

Contributions welcome!

## Changelog

- **1.19.0**: Latest stable release with enhanced check accuracy
- **1.17.0**: Added terminology intelligence, domain-specific rules, false friends detection
- **1.16.0**: 76% reduction in false positives (26,576 → 6,308 issues)
- **1.15.x**: GTK4 GUI, GitHub integration, custom glossaries
- **1.14.x**: Multiple output formats, CI integration

## License

GPL-3.0-or-later

## Author

Daniel Nylander (daniel@danielnylander.se)