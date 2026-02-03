# l10n-lint

🔍 Linter for localization files (`.po`, `.ts`)

Check your translation files for common issues like missing translations, fuzzy entries, placeholder mismatches, and more.

## Features

- **Missing translations** – Find empty `msgstr` entries
- **Fuzzy entries** – Flag translations needing review
- **Placeholder mismatches** – Detect `%s`, `{0}`, `%1` inconsistencies
- **Length warnings** – Catch translations that are suspiciously long
- **Duplicate entries** – Find repeated `msgid` entries
- **GitHub support** – Lint repos directly without cloning

## Installation

### Debian/Ubuntu

```bash
wget https://github.com/yeager/l10n-lint/releases/download/v1.0.0/l10n-lint_1.0.0_all.deb
sudo dpkg -i l10n-lint_1.0.0_all.deb
```

### Fedora/RHEL/openSUSE

```bash
wget https://github.com/yeager/l10n-lint/releases/download/v1.0.0/l10n-lint-1.0.0-1.noarch.rpm
sudo rpm -i l10n-lint-1.0.0-1.noarch.rpm
```

### Arch Linux

```bash
wget https://github.com/yeager/l10n-lint/releases/download/v1.0.0/l10n-lint-1.0.0.pkg.tar.zst
sudo pacman -U l10n-lint-1.0.0.pkg.tar.zst
```

### Universal (tar.gz)

```bash
wget https://github.com/yeager/l10n-lint/releases/download/v1.0.0/l10n-lint-1.0.0.tar.gz
tar xzf l10n-lint-1.0.0.tar.gz -C /usr/local
```

### Windows/macOS (zip)

Download [l10n-lint-1.0.0.zip](https://github.com/yeager/l10n-lint/releases/download/v1.0.0/l10n-lint-1.0.0.zip), extract, and add to PATH.

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
