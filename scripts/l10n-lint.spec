Name:           l10n-lint
Version:        1.21.3
Release:        1%{?dist}
Summary:        Linter for localization files
License:        GPL-3.0-or-later
URL:            https://github.com/yeager/l10n-lint
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  gettext
Requires:       python3 >= 3.9
Requires:       python3-tomli
Recommends:     python3-gobject
Recommends:     gtk4
Recommends:     libadwaita

%description
A linter for PO, Qt TS, XLIFF and JSON localization files with project configuration,
baselines, source catalog comparison, previewed fixes and SARIF reports.
Includes command-line and GTK interfaces.

%prep
%setup -q

%build
for po in po/*.po; do
    [ -f "$po" ] || continue
    lang=$(basename "$po" .po)
    mkdir -p locale/$lang/LC_MESSAGES
    msgfmt -o locale/$lang/LC_MESSAGES/l10n-lint.mo "$po"
done
gzip -9cn l10n-lint.1 > l10n-lint.1.gz

%install
# Private modules avoid binding a noarch package to the build host's Python minor.
mkdir -p %{buildroot}%{_datadir}/%{name}
install -m 644 l10n_lint.py l10n_project.py l10n_lint_gtk.py print_helper.py %{buildroot}%{_datadir}/%{name}/
mkdir -p %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/l10n-lint <<'WRAPPER'
#!/bin/sh
exec /usr/bin/python3 /usr/share/l10n-lint/l10n_lint.py "$@"
WRAPPER
cat > %{buildroot}%{_bindir}/l10n-lint-gtk <<'WRAPPER'
#!/bin/sh
exec /usr/bin/python3 /usr/share/l10n-lint/l10n_lint_gtk.py "$@"
WRAPPER
chmod 755 %{buildroot}%{_bindir}/l10n-lint*

mkdir -p %{buildroot}%{_datadir}/applications
install -m 644 io.github.yeager.l10n-lint.desktop %{buildroot}%{_datadir}/applications/
mkdir -p %{buildroot}%{_datadir}/metainfo
install -m 644 io.github.yeager.l10n-lint.metainfo.xml %{buildroot}%{_datadir}/metainfo/
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
install -m 644 data/icons/hicolor/scalable/apps/*.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/
mkdir -p %{buildroot}%{_mandir}/man1
install -m 644 l10n-lint.1.gz %{buildroot}%{_mandir}/man1/
cp -r locale %{buildroot}%{_datadir}/%{name}/

%post
update-desktop-database /usr/share/applications 2>/dev/null || true

%postun
update-desktop-database /usr/share/applications 2>/dev/null || true

%files
%{_bindir}/l10n-lint
%{_bindir}/l10n-lint-gtk
%{_datadir}/%{name}/
%{_datadir}/applications/io.github.yeager.l10n-lint.desktop
%{_datadir}/metainfo/io.github.yeager.l10n-lint.metainfo.xml
%{_datadir}/icons/hicolor/scalable/apps/*.svg
%{_mandir}/man1/l10n-lint.1.gz
%doc README.md CHANGELOG.md
%license LICENSE

%changelog
* Sat Sep 19 2026 Daniel Nylander <daniel@danielnylander.se> - 1.21.3-1
- Reduce false positives in gettext, JSON and Swedish writing checks.

* Sat Sep 19 2026 Daniel Nylander <daniel@danielnylander.se> - 1.21.1-1
- Add incremental review and project policy checks.

* Sat Sep 19 2026 Daniel Nylander <daniel@danielnylander.se> - 1.21.0-1
- Add XLIFF/JSON catalogs, ICU MessageFormat and portable integer placeholders.

* Thu Sep 17 2026 Daniel Nylander <daniel@danielnylander.se> - 1.20.3-1
- Ignore intentionally empty Qt TS keys and contextualize File menu checks.

* Thu Sep 17 2026 Daniel Nylander <daniel@danielnylander.se> - 1.20.2-1
- Fix date-token typo warnings and contextual Swedish terminology checks.

* Thu Sep 17 2026 Daniel Nylander <daniel@danielnylander.se> - 1.20.1-1
- Fix prose percentage and reST format false positives; update APT documentation.

* Thu Sep 17 2026 Daniel Nylander <daniel@danielnylander.se> - 1.20.0-1
- Validate syntax and placeholders; add project workflows and SARIF.
- Install private Python modules and compiled translations.

* Mon Feb 16 2026 BOSSe Nylander <bosse@danielnylander.se> - 1.15.7-1
- Fix RPM file conflict with filesystem package on Fedora.
