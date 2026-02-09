#!/bin/bash
set -euo pipefail

SRCDIR="$(cd "$(dirname "$0")/.." && pwd)"
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRCDIR/l10n_lint.py")
PKG="l10n-lint"
DEST="/tmp/${PKG}_${VER}_build"

echo "Building ${PKG} ${VER}..."

rm -rf "$DEST"
mkdir -p "$DEST/DEBIAN"
mkdir -p "$DEST/usr/bin"
mkdir -p "$DEST/usr/share/applications"
mkdir -p "$DEST/usr/share/doc/$PKG"
mkdir -p "$DEST/usr/share/man/man1"
mkdir -p "$DEST/usr/share/metainfo"

# Control
cat > "$DEST/DEBIAN/control" <<EOF
Package: $PKG
Version: $VER
Section: devel
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-polib
Recommends: python3-gi
Maintainer: Daniel Nylander <daniel@danielnylander.se>
Homepage: https://github.com/yeager/l10n-lint
Description: Linter for localization files
 A comprehensive linter for PO and TS localization files that checks
 for common translation errors, formatting issues, and consistency.
 Includes both CLI and GTK GUI interfaces.
EOF

install -m 755 "$SRCDIR/debian/postinst" "$DEST/DEBIAN/postinst"
install -m 755 "$SRCDIR/debian/prerm" "$DEST/DEBIAN/prerm"

# Binaries
install -m 755 "$SRCDIR/l10n_lint.py" "$DEST/usr/bin/l10n-lint"
install -m 755 "$SRCDIR/l10n_lint_gtk.py" "$DEST/usr/bin/l10n-lint-gtk"

# Desktop file
install -m 644 "$SRCDIR/io.github.yeager.l10n-lint.desktop" "$DEST/usr/share/applications/"

# Metainfo
if [ -f "$SRCDIR/io.github.yeager.l10n-lint.metainfo.xml" ]; then
    install -m 644 "$SRCDIR/io.github.yeager.l10n-lint.metainfo.xml" "$DEST/usr/share/metainfo/"
fi

# Locales
if [ -d "$SRCDIR/locale" ]; then
    cp -r "$SRCDIR/locale" "$DEST/usr/share/"
fi

# Copyright
install -m 644 "$SRCDIR/debian/copyright" "$DEST/usr/share/doc/$PKG/copyright"

# Changelog
gzip -9cn "$SRCDIR/debian/changelog" > "$DEST/usr/share/doc/$PKG/changelog.Debian.gz"

# Man page
gzip -9cn "$SRCDIR/l10n-lint.1" > "$DEST/usr/share/man/man1/l10n-lint.1.gz"

# Remove __pycache__
find "$DEST" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Build
OUTPUT="/tmp/${PKG}_${VER}_all.deb"
dpkg-deb --root-owner-group --build "$DEST" "$OUTPUT"

echo "Built: $OUTPUT"
echo "Size: $(du -h "$OUTPUT" | cut -f1)"

echo ""
echo "=== Lintian-style checks ==="
echo -n "copyright: "; [ -f "$DEST/usr/share/doc/$PKG/copyright" ] && echo "OK" || echo "MISSING"
echo -n "changelog: "; [ -f "$DEST/usr/share/doc/$PKG/changelog.Debian.gz" ] && echo "OK" || echo "MISSING"
echo -n "manpage: "; [ -f "$DEST/usr/share/man/man1/l10n-lint.1.gz" ] && echo "OK" || echo "MISSING"
echo -n "__pycache__: "; find "$DEST" -name __pycache__ -type d | grep -q . && echo "FOUND (BAD)" || echo "clean"
echo -n "postinst: "; [ -f "$DEST/DEBIAN/postinst" ] && echo "OK" || echo "MISSING"

rm -rf "$DEST"
