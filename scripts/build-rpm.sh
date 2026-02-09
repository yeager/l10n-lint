#!/bin/bash
set -euo pipefail

SRCDIR="$(cd "$(dirname "$0")/.." && pwd)"
PKG="l10n-lint"
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRCDIR/l10n_lint.py")
SSH_PASS=$(security find-generic-password -s "ssh-192.168.2.2" -w)
SERVER="yeager@192.168.2.2"

echo "Building ${PKG}-${VER} RPM on server..."

TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/${PKG}-${VER}/man"
cp "$SRCDIR/l10n_lint.py" "$SRCDIR/l10n_lint_gtk.py" "$SRCDIR/l10n-lint.1" "$TMPDIR/${PKG}-${VER}/"
cp "$SRCDIR/io.github.yeager.l10n-lint.desktop" "$TMPDIR/${PKG}-${VER}/"
cp "$SRCDIR/README.md" "$SRCDIR/CHANGELOG.md" "$SRCDIR/LICENSE" "$TMPDIR/${PKG}-${VER}/"
cp -r "$SRCDIR/locale" "$SRCDIR/debian" "$TMPDIR/${PKG}-${VER}/"
gzip -9c "$SRCDIR/l10n-lint.1" > "$TMPDIR/${PKG}-${VER}/man/l10n-lint.1.gz"
find "$TMPDIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
tar -czf "$TMPDIR/${PKG}-${VER}.tar.gz" -C "$TMPDIR" "${PKG}-${VER}"

sshpass -p "$SSH_PASS" ssh "$SERVER" "mkdir -p ~/rpmbuild/{SOURCES,SPECS,RPMS,BUILD,SRPMS}"
sshpass -p "$SSH_PASS" scp "$TMPDIR/${PKG}-${VER}.tar.gz" "$SERVER:~/rpmbuild/SOURCES/"
sshpass -p "$SSH_PASS" scp "$SRCDIR/scripts/${PKG}.spec" "$SERVER:~/rpmbuild/SPECS/"
sshpass -p "$SSH_PASS" ssh "$SERVER" "rpmbuild -bb ~/rpmbuild/SPECS/${PKG}.spec"

mkdir -p "$SRCDIR/dist"
sshpass -p "$SSH_PASS" scp "$SERVER:~/rpmbuild/RPMS/noarch/${PKG}-${VER}-1*.noarch.rpm" "$SRCDIR/dist/"

rm -rf "$TMPDIR"
echo "Built: $SRCDIR/dist/"
