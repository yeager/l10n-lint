#!/bin/bash
set -euo pipefail

SRCDIR="$(cd "$(dirname "$0")/.." && pwd)"
PKG="l10n-lint"
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRCDIR/l10n_lint.py")
RPM_WORKDIR=$(mktemp -d)
trap 'rm -rf "$RPM_WORKDIR"' EXIT
mkdir -p "$RPM_WORKDIR/source/${PKG}-${VER}" "$RPM_WORKDIR/rpm/SOURCES"
cp "$SRCDIR"/*.py "$SRCDIR/l10n-lint.1" "$SRCDIR/README.md" "$SRCDIR/CHANGELOG.md" "$SRCDIR/LICENSE" "$RPM_WORKDIR/source/${PKG}-${VER}/"
cp "$SRCDIR/io.github.yeager.l10n-lint.desktop" "$SRCDIR/io.github.yeager.l10n-lint.metainfo.xml" "$RPM_WORKDIR/source/${PKG}-${VER}/"
cp -r "$SRCDIR/po" "$SRCDIR/locale" "$SRCDIR/data" "$RPM_WORKDIR/source/${PKG}-${VER}/"
tar -czf "$RPM_WORKDIR/rpm/SOURCES/${PKG}-${VER}.tar.gz" -C "$RPM_WORKDIR/source" "${PKG}-${VER}"
rpmbuild --define "_topdir $RPM_WORKDIR/rpm" -bb "$SRCDIR/scripts/${PKG}.spec" "$@"
mkdir -p "$SRCDIR/dist"
cp "$RPM_WORKDIR/rpm/RPMS/noarch/"*.rpm "$SRCDIR/dist/"
echo "Built RPM packages in $SRCDIR/dist/"
