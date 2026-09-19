# l10n-lint

[![Version](https://img.shields.io/badge/version-1.21.3-blue)](https://github.com/yeager/l10n-lint/releases/tag/v1.21.3)
![License](https://img.shields.io/badge/license-GPL--3.0-green)
![Python](https://img.shields.io/badge/python-3.9+-blue)

l10n-lint checks gettext PO, Qt TS, XLIFF 1.2/2.x and JSON translation catalogs for missing translations,
invalid syntax, placeholder mismatches, plural errors and inconsistent formatting.
Use the command line in CI or the GTK4 desktop interface for interactive review.
Swedish-specific checks cover spelling patterns, terminology and localization conventions.

[Download 1.21.3](https://github.com/yeager/l10n-lint/releases/tag/v1.21.3)
· [Changelog](CHANGELOG.md) · [Report a bug](https://github.com/yeager/l10n-lint/issues)

Version **1.21.3** reduces false positives in decompiled gettext catalogs and JSON
translations, including printf suffixes, plural headers and Swedish spelling checks.

## Features

- Validate PO/TS/XLIFF/JSON syntax, plural forms, printf/Python/Qt placeholders, tags, whitespace and URLs.
- Share diagnostic IDs and input handling between the CLI and GTK4 interface.
- Scan local files, directories, remote PO/TS/XLIFF/JSON URLs and GitHub repositories.
- Select individual rules or groups, configure severities and load custom TSV glossaries.
- Store project settings in `pyproject.toml` and baseline existing findings.
- Compare translations with a source catalog to find missing or obsolete entries.
- Preview and apply conservative whitespace and ellipsis fixes to local PO files.
- Export text, JSON, HTML, GNU, GitHub Actions annotations or SARIF 2.1.0.

## Installation

### Install the current release

Download the package for your system from [release 1.21.3](https://github.com/yeager/l10n-lint/releases/tag/v1.21.3).
The release includes `.deb`, `.rpm`, a Python wheel, a source archive and `SHA256SUMS`.

| System | Download | Install command |
|--------|----------|-----------------|
| Debian / Ubuntu | [Debian package](https://github.com/yeager/l10n-lint/releases/download/v1.21.3/l10n-lint_1.21.3-1_all.deb) | `sudo apt install ./l10n-lint_1.21.3-1_all.deb` |
| Fedora | [RPM package](https://github.com/yeager/l10n-lint/releases/download/v1.21.3/l10n-lint-1.21.3-1.noarch.rpm) | `sudo dnf install ./l10n-lint-1.21.3-1.noarch.rpm` |

For the Python CLI, download the [wheel](https://github.com/yeager/l10n-lint/releases/download/v1.21.3/l10n_lint-1.21.3-py3-none-any.whl)
and use Python 3.9 or newer in a virtual environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install ./l10n_lint-1.21.3-py3-none-any.whl
l10n-lint --version
```

The Python package installs both launchers. The GUI additionally needs PyGObject,
GTK4 and libadwaita from your system; launch it with `l10n-lint-gtk`.
The virtual-environment instructions above are sufficient for the CLI.

External APT/RPM repositories and PyPI may contain an older version. GitHub releases
provide the packages verified for the version shown here.

### APT repository (Debian/Ubuntu)

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

## Building from source

```bash
git clone https://github.com/yeager/l10n-lint
cd l10n-lint
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

## Usage

Basic usage:
```bash
# Lint a single file
l10n-lint translations/sv.po

# Lint a directory recursively
l10n-lint ./po/

# Open the GTK4 interface
l10n-lint-gtk

# Lint a GitHub repository
l10n-lint --github yeager/l10n-lint
```

Advanced options:
```bash
# Generate HTML report
l10n-lint -f html -o report.html ./translations/

# JSON output for CI pipelines
l10n-lint -f json -o results.json ./translations/

# SARIF output for code-scanning integrations
l10n-lint -f sarif -o results.sarif ./translations/

# Run only specific checks
l10n-lint --checks terminology,false-friends,consistency sv.po

# CI mode (exit code only)
l10n-lint --check --strict .
```

The target language is detected from PO metadata or Qt TS attributes, with a filename
fallback for PO files. Use `--language sv` to override detection when needed.

See the manual or CLI help for complete options:
```bash
man l10n-lint
l10n-lint --help
```

## Checks and rule selection

Use `l10n-lint --list-rules` for every diagnostic ID, default severity and language
scope. These are some useful rule groups and individual IDs:

| Rules or groups | What they check |
|-----------------|-----------------|
| `placeholders` | Typed printf arguments, Python fields and Qt placeholders |
| `plural-forms` | Plural headers, formulas and translation variants |
| `missing-translation`, `fuzzy` | Empty translations and entries awaiting review |
| `untranslated-words`, `source-equals-translation` | Possible untranslated text |
| `length`, `whitespace` | Length limits, missing boundary spaces and extra whitespace |
| `punctuation`, `capitalization`, `quotes` | Text formatting and consistency |
| `html-tags`, `xml-tags-mismatch`, `url-preservation` | Markup and URLs |
| `escapes`, `newline-mismatch`, `accelerators` | Escapes, newlines and shortcuts |
| `numerics`, `option-values` | Numbers and command-line option values |
| `typo`, `terminology`, `false-friends` | Swedish spelling patterns and word choices |
| `domain-terminology` | Swedish terminology for music and issue-tracking contexts |
| `date-format`, `number-localization`, `currency-localization` | Swedish formatting conventions |
| `consistency`, `duplicate` | Inconsistent translations and duplicate catalog entries |
| `glossary` | Project-specific TSV terminology |
| `catalog-missing`, `catalog-obsolete`, `catalog-plural-changed` | Differences from `--reference` |

### Format flags and documentation text

Explicit `c-format` and `python-format` flags enable full printf validation,
including space flags such as `% d`. Without those flags, only clear conversion
syntax is inferred: prose such as `100% coverage` or `50 % anger` is not a
printf argument. Real `%s`, positional/named arguments and width/precision
specifications are still checked. Use an explicit flag for ambiguous cases
such as a conversion immediately after a numeric literal. Attached integer time
units such as `%ds` are recognized. Other literal suffixes such as `%iHz` are
accepted when the complete typed argument contracts match on both sides.
Prose percentages such as `2% change` are ignored even with a `c-format` flag.
Standalone JSON keys are identifiers, so their spelling is not used as a source
placeholder contract; explicit JSON source/translation entries are still checked.

Python-format checks ignore reST `:math:` roles (including suffix role syntax)
and inline literal brace delimiters such as ` ``{`` ` and ` ``}`` `. Complete
fields such as ` ``{name}`` ` and real placeholders outside those constructs
remain checked, even in a message that also contains mathematics. These
exclusions affect format parsing only; the original text is retained for
other checks and reports.

### Swedish terminology sources

The built-in Swedish rules are deliberately conservative. For IT terms, curated
terms and recommendations use [Computer Swedens IT-ord](https://it-ord.computersweden.se/)
as the first reference source. [SAOL, SO and SAOB](https://svenska.se/),
[TEPA](https://termipankki.fi/tepa/sv/), [IATE](https://iate.europa.eu/home),
[Rikstermbanken](https://www.rikstermbanken.se/) and [ISOF's guidance on
fackspråk och terminologi](https://www.isof.se/svenska-spraket/facksprak-och-terminologi)
then support general Swedish, public-sector terminology and domains outside IT,
together with project documentation and the configured project glossary. These
sources guide human review; l10n-lint does not scrape or redistribute their data.

For Swedish compounds, three equal consecutive letters are flagged as a likely
spelling error. Normal Swedish spelling normally reduces the sequence to two, for
example `process + status` → `processtatus`. Intentional dialogue exclamations
and format tokens remain exempt.

### Context for Swedish checks

Date-format tokens such as `yyyy` in `dd/mm/yyyy` are excluded from spelling
heuristics. Date and placeholder checks still run on the original text.

The `View` → `Visa` menu recommendation requires an explicit `menu` or `menubar`
context in PO `msgctxt` or the Qt TS context/comment. Without that evidence, `View`
may be a noun, for example a color-management view translated as `Vy`.
The `linje` → `rad` recommendation requires a command-line or code/text-line
context; geometric lines and unrelated compounds such as `riktlinjer` are ignored.
Likewise, `File` → `Arkiv` applies only where PO `msgctxt` or Qt TS context/comment
identifies a menu. A label or command category may correctly use `Fil`. Empty Qt TS
source and translation pairs are structural keys and are ignored.

## Output Formats

| Format | Flag | Use case |
|--------|------|----------|
| `text` | `-f text` | Terminal output (default) |
| `json` | `-f json` | CI pipelines, integrations |
| `html` | `-f html` | Shareable reports |
| `gnu` | `-f gnu` | Emacs `compile-mode` compatible |
| `github` | `-f github` | GitHub Actions annotations |
| `sarif` | `-f sarif` | SARIF 2.1.0 code-scanning reports |

## Project configuration

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
translation-memory = "translations/memory.json"
forbidden-terms = ["Dokumentera"]
required-terms = [{ source = "Save", target = "Spara", context = "menu" }]
max-length = 500
length-ratio = 3.0
max-errors = 0
max-warnings = 0
strict = true
json-format = "auto"

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
deduplicated. Directory discovery accepts `.po`, `.ts`, `.xlf`, `.xliff` and `.json`
case-insensitively.

## XLIFF and JSON catalogs

XLIFF support covers XLIFF 1.2 `trans-unit` elements and XLIFF 2.x `unit`/`segment`
elements. The linter reads the target language, skips units marked `translate="no"`,
and preserves inline placeholders expressed through `equiv-text` or `equiv`.

JSON support accepts nested key/value catalogs, where the leaf key is the source text,
and explicit entries with `source` plus `target`, `translation`, or `value`. Use
`@locale`, `locale`, `targetLanguage`, or `target_language` for language metadata.
Entries marked `translate: false` or `translatable: false` are skipped.
Plural objects with CLDR forms such as `one` and `other` are validated form by form.

Set `json-format = "nested"` to allow only nested key/value catalogs, or
`json-format = "entries"` to allow only explicit `source`/`target` entries.
This policy is useful when a repository also contains non-localization JSON files.

```json
{
  "@locale": "sv",
  "menu": {"Save %s": "Spara %s"}
}
```

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

## Efficient review workflows

Use `--changed BASE` in a pull-request job to lint only localization files changed
since a Git revision, for example `l10n-lint --changed origin/main --format github`.
Use `translation-memory` for cross-catalog consistency, `required-terms` and
`forbidden-terms` for domain policy, and a JSON object of source-to-translation
string pairs for the memory file. The linter also reports introduced bidi controls,
non-NFC text, and missing CLDR plural categories in JSON plural objects.

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
l10n-lint --reference source.xlf translations/sv.xlf
```

PO comparison keys include `msgctxt` and `msgid`; Qt keys use explicit IDs or
context, disambiguation comment and source text. Missing entries, entries absent
from the reference, and changed plural/source definitions are reported separately.
Obsolete PO and vanished/obsolete Qt entries are excluded. One reference applies
to every input in the command; use separate runs for different domains. Reference
and target formats must match (`.pot`/`.po`, `.ts`, `.xlf`/`.xliff`, or `.json`).

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
into a fresh environment for CLI smoke tests outside the checkout. GNU gettext validates the documentation
fixtures. A separate Xvfb job opens the GTK window/preferences and displays a URL
lint result. Debian and RPM packages also pass CLI checks against the release source.

For local GTK verification, install the system GTK dependencies and Xvfb, then run:

```sh
xvfb-run -a /usr/bin/python3 tests/gtk_smoke.py
```

Check desktop integration when changing widgets.

## Translation

Translations are managed on Transifex: https://app.transifex.com/danielnylander/l10n-lint/

Currently supported: Swedish, Danish, German, Spanish, Finnish, French, Italian, Norwegian Bokmål, Dutch, Polish, Portuguese (Brazil)

Contributions welcome!

## Changelog

- **1.21.3**: Reduce gettext/JSON false positives and preserve real format and spelling checks
- **1.21.2**: Add incremental review, project policy and CLDR/Unicode validation
- **1.20.2**: Recognize year tokens in typo checks; require context for ambiguous Swedish terminology
- **1.20.1**: Fix false format errors in percentage prose and reST documentation; repair APT setup
- **1.20.0**: Reliable parsing, shared rules, project configuration, baselines, catalog comparison, previewed fixes and SARIF
- **1.19.0**: Enhanced check accuracy
- **1.17.0**: Added terminology intelligence, domain-specific rules, false friends detection
- **1.16.0**: 76% reduction in false positives (26,576 → 6,308 issues)
- **1.15.x**: GTK4 GUI, GitHub integration, custom glossaries
- **1.14.x**: Multiple output formats, CI integration

See [CHANGELOG.md](CHANGELOG.md) for the full release history.

## License

[GPL-3.0-or-later](LICENSE)

## Author

Daniel Nylander (daniel@danielnylander.se)
