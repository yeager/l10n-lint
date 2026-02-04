# l10n-lint

🔍 Linter for localization files (`.po`, `.ts`)

Check your translation files for common issues like missing translations, fuzzy entries, placeholder mismatches, and more.

## Features

### Core checks
- **Missing translations** – Find empty `msgstr` entries
- **Fuzzy entries** – Flag translations needing review
- **Placeholder mismatches** – Detect `%s`, `{0}`, `%1` inconsistencies
- **Duplicate entries** – Find repeated `msgid` entries

### Typography & formatting
- **Inconsistent punctuation** – Missing or mismatched ending punctuation
- **Inconsistent capitalization** – First letter case mismatch
- **Trailing whitespace** – Extra spaces at end of translation
- **Double spaces** – Multiple spaces in translation
- **Mixed quotes** – Inconsistent quote styles (`"` vs `"` vs `„`)

### Technical
- **HTML tag mismatch** – `<b>`, `<a href>` tags don't match
- **Escaped chars mismatch** – `\n`, `\t`, `\\` inconsistencies
- **Keyboard shortcut issues** – Missing accelerators (`&File`)
- **Nordic accelerators** – å,ä,ö used as keyboard accelerators (error)
- **Numeric mismatch** – Numbers from source missing in translation

### Quality
- **Untranslated words** – Common English words left in translation
- **Repeated words** – "and and", "the the"
- **Source equals translation** – Possibly forgotten to translate
- **Suspicious length** – Translation too short or too long

### Additional features
- **GitHub support** – Lint repos directly without cloning
- **Localized output** – Available in 45+ languages
- **CI mode** – Exit code only with `--check`
- **Quiet mode** – Summary only with `-q`

## Installation

### From APT repository (recommended)

```bash
# Add repository
echo "deb [trusted=yes] https://yeager.github.io/debian-repo stable main" | sudo tee /etc/apt/sources.list.d/yeager.list
sudo apt update
sudo apt install l10n-lint
```

### Fedora/RHEL (DNF repository)

```bash
sudo tee /etc/yum.repos.d/yeager.repo << 'EOF'
[yeager]
name=Yeager's Translation Tools
baseurl=https://yeager.github.io/rpm-repo
enabled=1
gpgcheck=0
EOF
sudo dnf install l10n-lint
```

### From source

```bash
git clone https://github.com/yeager/l10n-lint.git
cd l10n-lint
chmod +x l10n_lint.py
ln -s $(pwd)/l10n_lint.py /usr/local/bin/l10n-lint
```

## Usage

### Local files

```bash
# Lint a directory
l10n-lint ./translations/

# Lint a single file
l10n-lint messages.po

# Non-recursive
l10n-lint --no-recursive ./po/
```

### GitHub repositories

```bash
# Lint a GitHub repo
l10n-lint --github owner/repo

# Lint specific path in repo
l10n-lint --github owner/repo --path resources/language/

# Full URL also works
l10n-lint --github https://github.com/owner/repo
```

### Output formats

```bash
# Default: human-readable
l10n-lint ./translations/

# JSON (for scripting)
l10n-lint --format json ./translations/

# GitHub Actions annotations
l10n-lint --format github ./translations/
```

### Options

| Option | Description |
|--------|-------------|
| `--github`, `-g` | GitHub repository (owner/repo or URL) |
| `--path`, `-p` | Path filter for GitHub repos |
| `--format`, `-f` | Output format: `text`, `json`, `github` |
| `--max-length` | Max translation length (default: 500) |
| `--no-recursive` | Don't search subdirectories |
| `--strict` | Treat warnings as errors |

## Supported formats

| Format | Extension | Description |
|--------|-----------|-------------|
| gettext | `.po` | GNU gettext translation files |
| Qt | `.ts` | Qt Linguist translation files |

## Lint rules

| Rule | Severity | Description |
|------|----------|-------------|
| `missing-translation` | ❌ Error | Empty `msgstr` / unfinished translation |
| `fuzzy` | ⚠️ Warning | Translation flagged as fuzzy |
| `placeholder-mismatch` | ❌ Error | Source/translation placeholder mismatch |
| `duplicate` | ⚠️ Warning | Duplicate `msgid` entry |
| `too-long` | ⚠️ Warning | Translation exceeds max length |
| `length-ratio` | ℹ️ Info | Translation is 2x+ longer than source |
| `vanished` | ℹ️ Info | Source string was removed (Qt) |

## Examples

### Check before commit

```bash
# In CI
l10n-lint --format github --strict ./translations/
```

### Find untranslated strings

```bash
l10n-lint ./translations/ | grep missing-translation
```

### JSON output for scripting

```bash
l10n-lint --format json ./po/ | jq '.issues[] | select(.severity == "error")'
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | No errors (warnings allowed) |
| 1 | Errors found (or warnings with `--strict`) |

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)

## License

GPL-3.0

## Author

**Daniel Nylander** ([@yeager](https://github.com/yeager))
