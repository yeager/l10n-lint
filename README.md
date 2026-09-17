# l10n-lint

![Version](https://img.shields.io/badge/version-1.20.1-blue)
![License](https://img.shields.io/badge/license-GPL--3.0-green)
![Python](https://img.shields.io/badge/python-3.9+-blue)

## Description

A comprehensive linter for localization files (`.po`, `.ts`). Finds missing translations, placeholder mismatches, terminology errors, and 20+ other common issues.

Built with Python as part of the professional L10n Tool Suite, l10n-lint provides essential quality assurance for translation projects, helping maintain consistency and accuracy across multilingual applications.

## Features

- **A shared registry of built-in checks** covering placeholders, formatting, terminology, consistency, and more
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

Install the repository's current public key and scope it to this source:

```bash
key_file=$(mktemp)
curl -fsSL https://yeager.github.io/debian-repo/yeager-repo-key.asc -o "$key_file" &&
  sudo install -D -m 0644 "$key_file" /etc/apt/keyrings/yeager-l10n.asc
rm -f "$key_file"
echo "deb [signed-by=/etc/apt/keyrings/yeager-l10n.asc] https://yeager.github.io/debian-repo ./" | sudo tee /etc/apt/sources.list.d/yeager-l10n.list
sudo apt update
sudo apt install l10n-lint
```

This replaces the earlier `stable main` entry in `yeager-l10n.list`. If you put
that entry in another file, replace it there instead; keep only one Yeager
source definition. The obsolete `yeager-l10n.gpg` URL no longer exists.
The current key's primary fingerprint is
`7CEE83C9C621B18667DD1BFECAED4975DAB053A8`; its signing subkey is
`37986EFBED62D629C0CF268EE318C7DE3DA87C5B` (the key reported in issue #2).

The APT index may lag GitHub releases. To install the latest published version,
download its `.deb` from [Releases](https://github.com/yeager/l10n-lint/releases)
and run `sudo apt install ./l10n-lint_VERSION-1_all.deb`.

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

- **1.20.1**: Fix false format errors in percentage prose and reST documentation; repair APT setup
- **1.20.0**: Reliable parsing, shared rules, project configuration, baselines, catalog comparison, previewed fixes and SARIF
- **1.19.0**: Enhanced check accuracy
- **1.17.0**: Added terminology intelligence, domain-specific rules, false friends detection
- **1.16.0**: 76% reduction in false positives (26,576 → 6,308 issues)
- **1.15.x**: GTK4 GUI, GitHub integration, custom glossaries
- **1.14.x**: Multiple output formats, CI integration

## License

GPL-3.0-or-later

## Author

Daniel Nylander (daniel@danielnylander.se)
## Project configuration and rule selection

The CLI reads `[tool.l10n-lint]` from the nearest `pyproject.toml`, searching
from the current working directory upwards. Use `--config FILE` to select one
explicitly. Command-line values override configuration values. Paths in the
configuration are relative to that TOML file; command-line paths are relative
to the working directory.

```toml
[tool.l10n-lint]
language = "sv"
checks = ["placeholders", "whitespace", "terminology", "glossary"]
exclude = ["vendor/**", "generated/**"]
glossary = "translations/glossary.tsv"
max-length = 500
length-ratio = 3.0
max-errors = 0
max-warnings = 0
strict = true

[tool.l10n-lint.severity]
terminology = "warning"
glossary = "error"
```

`--list-rules` prints all diagnostic IDs, default severities and language scopes.
`--checks` selects only the listed rules or groups. Groups include
`placeholders`, `length`, `whitespace`, `plural-forms` and `accelerators`.
`--disable` and `--skip-checks` accept the same names. Unknown names are errors.
Operational errors (invalid syntax, unreadable/missing paths, incomplete
network fetches and invalid references) cannot be disabled. An empty scan also
fails, including when exclusions remove every input. Repeated local paths are
deduplicated. Directory discovery accepts `.po` and `.ts` case-insensitively.

A glossary contains two or three tab-separated fields per line:
`wrong<TAB>correct[<TAB>context]`. Blank lines and lines beginning with `#` are
ignored. Matching is case-insensitive at word boundaries; context is explanatory
text in the diagnostic. Missing or malformed glossary files fail the command.
Custom glossaries apply to every target language; built-in Swedish terminology
and spelling checks run only for Swedish.

Exit codes: **0** when findings are within the configured thresholds, **1** when
warnings exceed `--max-warnings`, **2** when errors exceed `--max-errors` or an
operational error occurs. `--strict` makes excess warnings return **2** as well.
Informational findings do not fail a run. `--check` suppresses normal output.
Invalid options/configuration still produce an error on stderr. `--skip-fuzzy`
suppresses the fuzzy diagnostic; it does not skip validation of those entries.

## Baselines: report only new findings

```sh
# Save existing findings. This command still returns the normal lint exit code.
l10n-lint --write-baseline l10n-baseline.json translations/

# Fail only for findings exceeding the recorded baseline.
l10n-lint --baseline l10n-baseline.json translations/
```

Baselines include project-relative file identity, rule, severity, diagnostic
message and context, with occurrence counts. They ignore physical line numbers,
so moving an unchanged entry normally preserves its baseline. New duplicate
occurrences remain visible. Changes to diagnostic text, severity, translation
context or UI language may require baseline regeneration. Use the same project
root and UI language in developer and CI runs. Syntax/read/network failures are
never baselined. Commit the baseline for review; do not regenerate it on every
CI run. `baseline = "l10n-baseline.json"` is also supported in configuration.

## Compare translations with a source catalog

```sh
l10n-lint --reference messages.pot po/sv.po
l10n-lint --reference source.ts translations/sv.ts
```

PO comparison keys include `msgctxt` and `msgid`; Qt keys use explicit IDs or
context, disambiguation comment and source text. Missing entries, entries absent
from the reference, and changed plural/source definitions are reported separately.
Obsolete PO and vanished/obsolete Qt entries are excluded. One reference applies
to every input in the command; use separate runs for different domains. Reference
and target formats must match (`.pot`/`.po` or `.ts`).

## Preview and apply conservative fixes

```sh
# Print a unified diff on stderr without changing files.
l10n-lint --fix whitespace,ellipsis po/sv.po

# Print the diff, write the changes, and lint the resulting files.
l10n-lint --fix whitespace,ellipsis --apply po/sv.po
```

Fixes currently support **local UTF-8 PO files**. They touch translation fields
only, skip headers and fuzzy/obsolete entries, and preserve unrelated comments,
source strings, newline style and file permissions. Whitespace fixes remove
extra boundary spaces/tabs only when the source has no boundary whitespace.
Ellipsis fixes convert a trailing `...` to `…` only when the source also ends in
an ellipsis. Interior spaces and meaningful source boundary whitespace are
preserved. Multiline translation fields that change may be serialized onto one
line. Each write is atomic; changed files and symlinks are rejected. Multi-file
application is not a transaction, so review the preview before `--apply`.

## SARIF and CI

```sh
l10n-lint -f sarif -o l10n-results.sarif translations/
```

SARIF 2.1.0 reports include diagnostic rule IDs, severity and source locations.
Text, JSON, HTML, GNU and GitHub Actions output remain available. GitHub annotation
properties and messages are escaped; informational findings use `notice`.

GitHub repository scans discover the repository's actual default branch and
fetch all files from the same tree revision. Download failures and truncated
GitHub trees fail the scan instead of silently producing partial success.

The GTK frontend uses the same input pipeline and rule IDs as the CLI, including
URL/GitHub loading, plural checks and operational errors. CLI project baselines,
reference comparison, SARIF export and fix commands are currently CLI workflows;
GTK retains its own preferences.

## Development and verification

```sh
python -m pip install '.[test]'
python -m pytest -q
python -m build
```

CI runs regression tests on Python 3.9, 3.11 and 3.14 and installs the built wheel
into a fresh environment for a CLI smoke test outside the checkout. GTK worker logic is covered by regression tests, and a separate Xvfb job opens
the window/preferences and displays a URL lint result. Manually check desktop
integration when changing widgets.

### Format flags and documentation text

Explicit `c-format` and `python-format` flags enable full printf validation,
including space flags such as `% d`. Without those flags, only clear conversion
syntax is inferred: prose such as `100% coverage` or `50 % anger` is not a
printf argument. Real `%s`, positional/named arguments and width/precision
specifications are still checked. Use an explicit flag for ambiguous cases
such as `%dpx` or a conversion immediately after a numeric literal.

Python-format checks ignore reST `:math:` roles (including suffix role syntax)
and inline literal brace delimiters such as ` ``{`` ` and ` ``}`` `. Complete
fields such as ` ``{name}`` ` and real placeholders outside those constructs
remain checked, even in a message that also contains mathematics. These
exclusions affect format parsing only; the original text is retained for
other checks and reports.
