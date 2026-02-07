# l10n-lint

🔍 Linter for localization files (`.po`, `.ts`) — CLI and GTK interfaces

Check your translation files for common issues like missing translations, fuzzy entries, placeholder mismatches, and more.

**Version:** 1.14.9 (CLI) / 1.2.9 (GTK)

## Features

### Core checks
- **Missing translations** – Find empty `msgstr` entries
- **Fuzzy entries** – Flag translations needing review
- **Placeholder mismatches** – Detect `%s`, `{0}`, `%1` inconsistencies
- **Duplicate entries** – Find repeated `msgid` entries

### Typography & formatting
- **Inconsistent punctuation** – Missing or mismatched ending punctuation
- **Inconsistent capitalization** – First letter case mismatch
- **Whitespace issues** – Trailing spaces, double spaces
- **Mixed quotes** – Inconsistent quote styles (`"` vs `"` vs `„`)

### Technical
- **HTML tag mismatch** – `<b>`, `<a href>` tags don't match
- **Escaped chars mismatch** – `\n`, `\t`, `\\` inconsistencies
- **Keyboard accelerators** – Missing or mismatched `&` shortcuts
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

## GTK Interface (l10n-lint-gtk)

Modern GTK4/libadwaita graphical interface with:

- 🎛️ **Lint rule preferences** – Enable/disable individual checks
- 📋 **File metadata panel** – Language, translator, revision date, project info
- 📊 **Statistics** – Entries, translated, untranslated, fuzzy counts
- 🔍 **Filter & search** – By severity, rule type, or text
- 🖱️ **Drag & drop** – Drop files to lint automatically
- 📤 **Export reports** – HTML, JSON, or plain text
- ⌨️ **Keyboard shortcuts** – Ctrl+O, Ctrl+Return, Ctrl+E
- 🌍 **Localized** – 45+ languages

![l10n-lint-gtk screenshot](docs/screenshot-gtk.png)

## Installation

### Debian/Ubuntu (APT)

```bash
# Add GPG key
curl -fsSL https://yeager.github.io/debian-repo/yeager.gpg | sudo gpg --dearmor -o /usr/share/keyrings/yeager.gpg

# Add repository
echo 'deb [signed-by=/usr/share/keyrings/yeager.gpg] https://yeager.github.io/debian-repo stable main' | sudo tee /etc/apt/sources.list.d/yeager.list

# Install
sudo apt update
sudo apt install l10n-lint        # CLI only
sudo apt install l10n-lint-gtk    # GTK interface (includes CLI)
```

### Fedora/RHEL (DNF)

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
chmod +x l10n_lint.py l10n_lint_gtk.py

# CLI
ln -s $(pwd)/l10n_lint.py ~/.local/bin/l10n-lint

# GTK (requires: python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1)
ln -s $(pwd)/l10n_lint_gtk.py ~/.local/bin/l10n-lint-gtk
```

## Usage

### CLI

```bash
# Lint a directory
l10n-lint ./translations/

# Lint a single file
l10n-lint messages.po

# GitHub repository
l10n-lint --github owner/repo

# JSON output
l10n-lint --format json ./translations/

# GitHub Actions annotations
l10n-lint --format github --strict ./translations/
```

### GTK

```bash
l10n-lint-gtk                    # Launch GUI
l10n-lint-gtk messages.po        # Open file directly
```

Or drag and drop files onto the window!

### Options

| Option | Description |
|--------|-------------|
| `--github`, `-g` | GitHub repository (owner/repo or URL) |
| `--path`, `-p` | Path filter for GitHub repos |
| `--format`, `-f` | Output format: `text`, `json`, `github` |
| `--max-length` | Max translation length (default: 500) |
| `--no-recursive` | Don't search subdirectories |
| `--strict` | Treat warnings as errors |
| `-q`, `--quiet` | Summary only |

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
| `placeholder` | ❌ Error | Placeholder mismatch (`%s`, `{0}`, etc.) |
| `duplicate` | ⚠️ Warning | Duplicate `msgid` entry |
| `length` | ⚠️ Warning | Translation length ratio too high |
| `punctuation` | ℹ️ Info | Ending punctuation mismatch |
| `capitalization` | ℹ️ Info | Initial letter case mismatch |
| `whitespace` | ⚠️ Warning | Leading/trailing whitespace issues |
| `html-tags` | ❌ Error | HTML tags don't match |
| `escapes` | ❌ Error | Escape sequences mismatch |
| `accelerators` | ⚠️ Warning | Keyboard accelerator issues |
| `numerics` | ℹ️ Info | Numbers not preserved |
| `untranslated` | ℹ️ Info | English words in translation |
| `repeated-words` | ℹ️ Info | Duplicated words |
| `source-equals-translation` | ℹ️ Info | Translation same as source |

## Examples

### CI/CD Integration

```yaml
# GitHub Actions
- name: Lint translations
  run: |
    pip install l10n-lint
    l10n-lint --format github --strict ./translations/
```

### Find specific issues

```bash
# Missing translations only
l10n-lint ./po/ | grep missing-translation

# JSON for scripting
l10n-lint --format json ./po/ | jq '.issues[] | select(.severity == "error")'
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | No errors (warnings allowed) |
| 1 | Errors found (or warnings with `--strict`) |

## Requirements

**CLI:**
- Python 3.8+
- No external dependencies (stdlib only)

**GTK:**
- Python 3.8+
- GTK 4.0, libadwaita 1.0
- PyGObject (`python3-gi`)

## License

GPL-3.0-or-later

## Author

**Daniel Nylander** ([@yeager](https://github.com/yeager))

---

*Part of [Yeager's Translation Tools](https://github.com/yeager/debian-repo)*
