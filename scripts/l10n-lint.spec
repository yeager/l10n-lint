Name:           l10n-lint
Version:        1.15.7
Release:        1%{?dist}
Summary:        Linter for localization files
License:        GPL-3.0-or-later
URL:            https://github.com/yeager/l10n-lint
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
Requires:       python3 >= 3.10
Requires:       python3-polib

%description
A comprehensive linter for PO and TS localization files that checks
for common translation errors, formatting issues, and consistency.

%prep
%setup -q

%install
mkdir -p %{buildroot}/usr/bin
install -m 755 l10n_lint.py %{buildroot}/usr/bin/l10n-lint
install -m 755 l10n_lint_gtk.py %{buildroot}/usr/bin/l10n-lint-gtk

mkdir -p %{buildroot}/usr/share/applications
install -m 644 io.github.yeager.l10n-lint.desktop %{buildroot}/usr/share/applications/

mkdir -p %{buildroot}/usr/share/man/man1
install -m 644 man/l10n-lint.1.gz %{buildroot}/usr/share/man/man1/

if [ -d locale ]; then
    cp -r locale %{buildroot}/usr/share/
fi

mkdir -p %{buildroot}/usr/share/doc/%{name}
install -m 644 README.md CHANGELOG.md %{buildroot}/usr/share/doc/%{name}/

%post
update-desktop-database /usr/share/applications 2>/dev/null || true

%postun
update-desktop-database /usr/share/applications 2>/dev/null || true

%files
/usr/bin/l10n-lint
/usr/bin/l10n-lint-gtk
/usr/share/applications/io.github.yeager.l10n-lint.desktop
/usr/share/man/man1/l10n-lint.1.gz
/usr/share/locale/
%doc /usr/share/doc/%{name}/README.md
%doc /usr/share/doc/%{name}/CHANGELOG.md
%license LICENSE

%changelog
* Mon Feb 16 2026 BOSSe Nylander <bosse@danielnylander.se> - 1.15.7-1
- Fix RPM file conflict with filesystem package on Fedora
- Remove ownership of /usr/share/metainfo directory

* Mon Feb 09 2026 Daniel Nylander <daniel@danielnylander.se> - 1.14.9-1
- Updated checks and improved linting accuracy
- GTK GUI improvements
