# l10n-lint

Lint and validate translation files (`.po`, `.ts`, `.xliff`) — CLI and GTK4/Adwaita interfaces.

![Screenshot](data/screenshots/screenshot-01.png)

## Features

- Missing translations, fuzzy entries, placeholder mismatches
- Typography checks: punctuation, capitalization, whitespace, quotes
- HTML tag and escape sequence validation
- Keyboard accelerator and numeric mismatch detection
- Quality checks: untranslated words, repeated words, suspicious length
- GTK4/Adwaita GUI with drag & drop, filtering, and report export
- CLI with JSON/GitHub Actions output formats
- GitHub repo scanning without cloning
- Localized output in 45+ languages

## Installation

### Debian/Ubuntu

```bash
# Add repository
curl -fsSL https://yeager.github.io/debian-repo/KEY.gpg | sudo gpg --dearmor -o /usr/share/keyrings/yeager-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/yeager-archive-keyring.gpg] https://yeager.github.io/debian-repo stable main" | sudo tee /etc/apt/sources.list.d/yeager.list
sudo apt update
sudo apt install l10n-lint-gtk
```

### Fedora/RHEL

```bash
sudo dnf config-manager --add-repo https://yeager.github.io/rpm-repo/yeager.repo
sudo dnf install l10n-lint
```

### From source

```bash
pip install .
l10n-lint
```

## 🌍 Contributing Translations

This app is translated via Transifex. Help translate it into your language!

**[→ Translate on Transifex](https://app.transifex.com/danielnylander/l10n-lint/)**

Currently supported: Swedish (sv). More languages welcome!

### For Translators
1. Create a free account at [Transifex](https://www.transifex.com)
2. Join the [danielnylander](https://app.transifex.com/danielnylander/) organization
3. Start translating!

Translations are automatically synced via GitHub Actions.
## License

GPL-3.0-or-later — Daniel Nylander <daniel@danielnylander.se>
