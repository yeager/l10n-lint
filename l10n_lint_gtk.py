#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# l10n-lint-gtk - GTK interface for l10n-lint
# Copyright (C) 2026 Daniel Nylander <daniel@danielnylander.se>
"""
l10n-lint-gtk - GTK4 graphical interface for l10n-lint

A graphical frontend for the l10n-lint localization file linter.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gio, GLib, Adw, Pango, Gdk

import gettext
import json
import locale
import os
import re
import sys
import threading
from pathlib import Path
from datetime import datetime

# Import l10n-lint core functionality
# Try multiple locations: site-packages, same directory, /usr/lib/python3/dist-packages
_script_dir = Path(__file__).resolve().parent
_possible_module_paths = [
    _script_dir,  # Same directory as this script
    Path("/usr/share/l10n-lint"),  # Debian package location
    Path("/usr/lib/python3/dist-packages"),  # Debian/Ubuntu standard
    Path("/usr/local/lib/python3/dist-packages"),  # Local installs
]

# Add paths to sys.path if module not already importable
try:
    from l10n_lint import (
        L10nLinter, LintResult, LintIssue, Severity,
        find_l10n_files, fetch_url_file, is_url,
        __version__ as LINT_VERSION
    )
except ImportError:
    for path in _possible_module_paths:
        if path.exists() and str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from l10n_lint import (
        L10nLinter, LintResult, LintIssue, Severity,
        find_l10n_files, fetch_url_file, is_url,
        __version__ as LINT_VERSION
    )

__version__ = "1.3.0"
APP_ID = "se.danielnylander.l10n-lint"

# Translation setup - use same domain and locale as CLI
DOMAIN = "l10n-lint"
_possible_locale_dirs = [
    Path("/usr/share/l10n-lint/locale"),
    Path(__file__).parent / "locale",
]
LOCALE_DIR = None
for _dir in _possible_locale_dirs:
    if _dir.is_dir() and (list(_dir.glob("*/LC_MESSAGES")) or list(_dir.glob("*.pot"))):
        LOCALE_DIR = _dir
        break

_system_lang = (
    os.environ.get("LANGUAGE", "").split(":")[0] or
    os.environ.get("LC_ALL", "") or
    os.environ.get("LC_MESSAGES", "") or
    os.environ.get("LANG", "") or
    locale.getlocale()[0] or
    "en"
)
_lang_code = _system_lang.split("_")[0].split(".")[0] if _system_lang else "en"

try:
    if LOCALE_DIR:
        translation = gettext.translation(DOMAIN, LOCALE_DIR, languages=[_lang_code], fallback=True)
    else:
        translation = gettext.NullTranslations()
    _ = translation.gettext
except Exception:
    def _(s): return s


# All available lint rules with descriptions
LINT_RULES = {
    "missing-translation": (_("Missing translations"), _("Check for empty msgstr/unfinished translations"), True),
    "fuzzy": (_("Fuzzy entries"), _("Flag entries marked as fuzzy/needs review"), True),
    "placeholder": (_("Placeholder mismatch"), _("Check %s, %d, {0}, {name} consistency"), True),
    "length": (_("Length ratio"), _("Warn if translation is much longer/shorter than source"), True),
    "punctuation": (_("Punctuation"), _("Check ending punctuation matches"), False),
    "capitalization": (_("Capitalization"), _("Check initial letter case matches"), False),
    "whitespace": (_("Whitespace"), _("Check leading/trailing whitespace"), True),
    "quotes": (_("Quote consistency"), _("Check quote characters are consistent"), False),
    "html-tags": (_("HTML tags"), _("Verify HTML tags match between source and translation"), True),
    "escapes": (_("Escape sequences"), _("Check \\n, \\t, etc. are preserved"), True),
    "accelerators": (_("Accelerators"), _("Check &amp; keyboard accelerators"), False),
    "numerics": (_("Numeric values"), _("Check numbers are preserved"), False),
    "untranslated": (_("Untranslated words"), _("Detect English words left in translation"), False),
    "repeated-words": (_("Repeated words"), _("Find duplicated words like 'the the'"), False),
    "source-equals-translation": (_("Same as source"), _("Warn if translation equals source"), False),
    "option-values": (_("Option values"), _("Check option/parameter values preserved"), False),
    "duplicate": (_("Duplicate entries"), _("Find duplicate msgids"), True),
}


def load_settings():
    """Load user settings from config file."""
    config_file = Path.home() / ".config" / "l10n-lint" / "settings.json"
    defaults = {
        "enabled_rules": [rule for rule, (name, desc, default) in LINT_RULES.items() if default],
        "max_length_ratio": 3.0,
        "recursive": True,
        "strict_mode": False,
    }
    if config_file.exists():
        try:
            data = json.loads(config_file.read_text())
            defaults.update(data)
        except Exception:
            pass
    return defaults


def save_settings(settings):
    """Save settings to config file."""
    config_file = Path.home() / ".config" / "l10n-lint" / "settings.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(settings, indent=2))


class FileMetadata:
    """Extract and hold metadata from .po or .ts files."""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.file_type = None
        self.language = None
        self.last_translator = None
        self.revision_date = None
        self.creation_date = None
        self.project = None
        self.team = None
        self.total_entries = 0
        self.translated = 0
        self.untranslated = 0
        self.fuzzy = 0
        self.file_size = 0
        self._extract()
    
    def _extract(self):
        p = Path(self.filepath)
        if not p.exists():
            return
        
        self.file_size = p.stat().st_size
        ext = p.suffix.lower()
        
        try:
            content = p.read_text(encoding='utf-8')
        except Exception:
            try:
                content = p.read_text(encoding='latin-1')
            except Exception:
                return
        
        if ext == '.po':
            self.file_type = "GNU gettext (.po)"
            self._extract_po(content)
        elif ext == '.ts':
            self.file_type = "Qt Linguist (.ts)"
            self._extract_ts(content)
    
    def _extract_po(self, content: str):
        """Extract metadata from PO file header."""
        # Find header entry (msgid "" followed by msgstr with continuation lines)
        header_match = re.search(
            r'msgid\s+""\s*\nmsgstr\s+"((?:[^"\\]|\\.)*)"\s*\n((?:\s*"(?:[^"\\]|\\.)*"\s*\n)*)',
            content, re.MULTILINE
        )
        if header_match:
            # Combine the first msgstr line and all continuation lines
            header = header_match.group(1)
            continuation = header_match.group(2)
            if continuation:
                for line_match in re.finditer(r'"((?:[^"\\]|\\.)*)"', continuation):
                    header += line_match.group(1)
            header = header.replace('\\n', '\n')
            
            # Extract fields
            for line in header.split('\n'):
                if ':' in line:
                    key, _, value = line.partition(':')
                    key = key.strip().lower()
                    value = value.strip()
                    
                    if key == 'language':
                        self.language = value
                    elif key == 'last-translator':
                        self.last_translator = value
                    elif key == 'po-revision-date':
                        self.revision_date = value
                    elif key == 'pot-creation-date':
                        self.creation_date = value
                    elif key == 'project-id-version':
                        self.project = value
                    elif key == 'language-team':
                        self.team = value
        
        # Count entries
        entries = re.findall(r'^msgid\s+"(.+)"', content, re.MULTILINE)
        self.total_entries = len(entries)
        
        # Count translated (non-empty msgstr)
        for match in re.finditer(r'msgid\s+"(.+)"\s*\n(?:msgid_plural[^\n]*\n)?msgstr(?:\[\d+\])?\s+"([^"]*)"', content):
            if match.group(2):
                self.translated += 1
            else:
                self.untranslated += 1
        
        # Count fuzzy
        self.fuzzy = len(re.findall(r'^#,.*fuzzy', content, re.MULTILINE))
        
        # Adjust counts
        if self.translated + self.untranslated == 0:
            self.untranslated = self.total_entries
    
    def _extract_ts(self, content: str):
        """Extract metadata from TS file."""
        # Language attribute
        lang_match = re.search(r'<TS[^>]*language="([^"]+)"', content)
        if lang_match:
            self.language = lang_match.group(1)
        
        # Count messages
        sources = re.findall(r'<source>([^<]*)</source>', content)
        self.total_entries = len(sources)
        
        # Count translated
        translations = re.findall(r'<translation(?:\s+type="([^"]*)")?[^>]*>([^<]*)</translation>', content)
        for trans_type, trans_text in translations:
            if trans_type == 'unfinished' or not trans_text:
                self.untranslated += 1
            else:
                self.translated += 1
        
        # Adjust
        if self.translated + self.untranslated == 0:
            self.untranslated = self.total_entries


class MetadataPanel(Gtk.Box):
    """Panel showing file metadata."""
    
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("card")
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.set_margin_top(8)
        
        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_start(12)
        header.set_margin_end(12)
        header.set_margin_top(12)
        
        self.file_icon = Gtk.Image.new_from_icon_name("text-x-generic-symbolic")
        self.file_icon.set_pixel_size(32)
        header.append(self.file_icon)
        
        header_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.filename_label = Gtk.Label(label=_("No file selected"))
        self.filename_label.set_xalign(0)
        self.filename_label.add_css_class("title-3")
        header_text.append(self.filename_label)
        
        self.filetype_label = Gtk.Label()
        self.filetype_label.set_xalign(0)
        self.filetype_label.add_css_class("dim-label")
        header_text.append(self.filetype_label)
        
        header.append(header_text)
        self.append(header)
        
        # Metadata grid
        self.grid = Gtk.Grid()
        self.grid.set_column_spacing(16)
        self.grid.set_row_spacing(4)
        self.grid.set_margin_start(12)
        self.grid.set_margin_end(12)
        self.grid.set_margin_bottom(12)
        
        self.meta_labels = {}
        row = 0
        for key, label_text in [
            ("language", _("Language")),
            ("translator", _("Last Translator")),
            ("revision", _("Revision Date")),
            ("project", _("Project")),
            ("team", _("Language Team")),
        ]:
            label = Gtk.Label(label=label_text + ":")
            label.set_xalign(1)
            label.add_css_class("dim-label")
            self.grid.attach(label, 0, row, 1, 1)
            
            value = Gtk.Label()
            value.set_xalign(0)
            value.set_hexpand(True)
            value.set_ellipsize(Pango.EllipsizeMode.END)
            value.set_selectable(True)
            self.grid.attach(value, 1, row, 1, 1)
            self.meta_labels[key] = value
            row += 1
        
        self.append(self.grid)
        
        # Stats row
        self.stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.stats_box.set_halign(Gtk.Align.CENTER)
        self.stats_box.set_margin_bottom(12)
        
        self.stat_labels = {}
        for name, label, color in [
            ("total", _("Entries"), "#9b59b6"),
            ("translated", _("Translated"), "#27ae60"),
            ("untranslated", _("Untranslated"), "#e74c3c"),
            ("fuzzy", _("Fuzzy"), "#f39c12"),
        ]:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            
            value_label = Gtk.Label()
            value_label.set_markup(f"<span foreground='{color}' weight='bold' size='large'>0</span>")
            box.append(value_label)
            
            name_label = Gtk.Label(label=label)
            name_label.add_css_class("caption")
            name_label.add_css_class("dim-label")
            box.append(name_label)
            
            self.stat_labels[name] = (value_label, color)
            self.stats_box.append(box)
        
        self.append(self.stats_box)
    
    def update(self, metadata: FileMetadata):
        """Update panel with metadata."""
        self.filename_label.set_text(Path(metadata.filepath).name)
        self.filetype_label.set_text(metadata.file_type or _("Unknown"))
        
        # Set appropriate icon
        if metadata.file_type and ".po" in metadata.file_type:
            self.file_icon.set_from_icon_name("text-x-gettext-translation-symbolic")
        elif metadata.file_type and ".ts" in metadata.file_type:
            self.file_icon.set_from_icon_name("text-x-qt-linguist-symbolic")
        else:
            self.file_icon.set_from_icon_name("text-x-generic-symbolic")
        
        # Update metadata fields
        self.meta_labels["language"].set_text(metadata.language or "—")
        self.meta_labels["translator"].set_text(metadata.last_translator or "—")
        self.meta_labels["revision"].set_text(metadata.revision_date or "—")
        self.meta_labels["project"].set_text(metadata.project or "—")
        self.meta_labels["team"].set_text(metadata.team or "—")
        
        # Update stats
        stats = {
            "total": metadata.total_entries,
            "translated": metadata.translated,
            "untranslated": metadata.untranslated,
            "fuzzy": metadata.fuzzy,
        }
        for name, value in stats.items():
            label, color = self.stat_labels[name]
            label.set_markup(f"<span foreground='{color}' weight='bold' size='large'>{value}</span>")
    
    def clear(self):
        """Clear the panel."""
        self.filename_label.set_text(_("No file selected"))
        self.filetype_label.set_text("")
        self.file_icon.set_from_icon_name("text-x-generic-symbolic")
        
        for key in self.meta_labels:
            self.meta_labels[key].set_text("—")
        
        for name in self.stat_labels:
            label, color = self.stat_labels[name]
            label.set_markup(f"<span foreground='{color}' weight='bold' size='large'>0</span>")


class LintRow(Gtk.Box):
    """A row displaying a lint issue."""
    
    def __init__(self, issue: LintIssue, on_click=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.issue = issue
        self.add_css_class("lint-row")
        self.add_css_class("card")
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.set_margin_top(4)
        self.set_margin_bottom(4)
        
        # Make clickable
        if on_click:
            gesture = Gtk.GestureClick()
            gesture.connect("released", lambda g, n, x, y: on_click(issue))
            self.add_controller(gesture)
            self.set_cursor(Gdk.Cursor.new_from_name("pointer", None))
        
        # Severity colors
        severity_colors = {
            Severity.ERROR: "#e74c3c",
            Severity.WARNING: "#f39c12", 
            Severity.INFO: "#3498db",
        }
        severity_icons = {
            Severity.ERROR: "dialog-error-symbolic",
            Severity.WARNING: "dialog-warning-symbolic",
            Severity.INFO: "dialog-information-symbolic",
        }
        color = severity_colors.get(issue.severity, "#666")
        icon = severity_icons.get(issue.severity, "dialog-question-symbolic")
        
        # Header: severity icon + file:line + rule
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_start(8)
        header.set_margin_end(8)
        header.set_margin_top(8)
        
        # Severity icon
        severity_icon = Gtk.Image.new_from_icon_name(icon)
        severity_icon.add_css_class("error" if issue.severity == Severity.ERROR else 
                                    "warning" if issue.severity == Severity.WARNING else "accent")
        header.append(severity_icon)
        
        # Severity text
        severity_label = Gtk.Label()
        severity_label.set_markup(
            f"<span foreground='{color}' weight='bold'>{issue.severity.value.upper()}</span>"
        )
        header.append(severity_label)
        
        # Location
        location = Gtk.Label(label=f"{Path(issue.file).name}:{issue.line}")
        location.add_css_class("dim-label")
        location.set_hexpand(True)
        location.set_xalign(0)
        location.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        header.append(location)
        
        # Rule badge
        rule_box = Gtk.Box()
        rule_box.add_css_class("pill")
        rule_label = Gtk.Label(label=issue.rule)
        rule_label.add_css_class("caption")
        rule_box.append(rule_label)
        header.append(rule_box)
        
        self.append(header)
        
        # Message
        message_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        message_box.set_margin_start(8)
        message_box.set_margin_end(8)
        message_box.set_margin_bottom(8)
        
        message_label = Gtk.Label(label=issue.message)
        message_label.set_xalign(0)
        message_label.set_wrap(True)
        message_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        message_box.append(message_label)
        self.append(message_box)
        
        # Context (if present)
        if issue.context:
            context_box = Gtk.Box()
            context_box.set_margin_start(8)
            context_box.set_margin_end(8)
            context_box.set_margin_bottom(8)
            context_box.add_css_class("view")
            
            context_label = Gtk.Label()
            context_label.set_markup(f"<tt>{GLib.markup_escape_text(issue.context)}</tt>")
            context_label.set_xalign(0)
            context_label.set_margin_start(8)
            context_label.set_margin_end(8)
            context_label.set_margin_top(4)
            context_label.set_margin_bottom(4)
            context_label.set_selectable(True)
            context_box.append(context_label)
            self.append(context_box)


class FilterBar(Gtk.Box):
    """Filter bar for issue list."""
    
    def __init__(self, on_filter_changed):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.on_filter_changed = on_filter_changed
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.set_margin_top(8)
        
        # Filter label
        label = Gtk.Label(label=_("Filter:"))
        self.append(label)
        
        # Severity toggles
        self.error_toggle = Gtk.ToggleButton(label=_("Errors"))
        self.error_toggle.set_active(True)
        self.error_toggle.add_css_class("error")
        self.error_toggle.connect("toggled", self._on_toggled)
        self.append(self.error_toggle)
        
        self.warning_toggle = Gtk.ToggleButton(label=_("Warnings"))
        self.warning_toggle.set_active(True)
        self.warning_toggle.add_css_class("warning")
        self.warning_toggle.connect("toggled", self._on_toggled)
        self.append(self.warning_toggle)
        
        self.info_toggle = Gtk.ToggleButton(label=_("Info"))
        self.info_toggle.set_active(True)
        self.info_toggle.add_css_class("accent")
        self.info_toggle.connect("toggled", self._on_toggled)
        self.append(self.info_toggle)
        
        # Rule filter dropdown
        self.rule_dropdown = Gtk.DropDown()
        self.rule_model = Gtk.StringList()
        self.rule_model.append(_("All rules"))
        self.rule_dropdown.set_model(self.rule_model)
        self.rule_dropdown.connect("notify::selected", self._on_rule_changed)
        self.append(self.rule_dropdown)
        
        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.append(spacer)
        
        # Search entry
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Search issues..."))
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.append(self.search_entry)
    
    def _on_toggled(self, button):
        self.on_filter_changed()
    
    def _on_rule_changed(self, dropdown, param):
        self.on_filter_changed()
    
    def _on_search_changed(self, entry):
        self.on_filter_changed()
    
    def update_rules(self, rules: list):
        """Update rule dropdown with found rules."""
        # Clear and rebuild
        while self.rule_model.get_n_items() > 1:
            self.rule_model.remove(1)
        for rule in sorted(set(rules)):
            self.rule_model.append(rule)
    
    def get_filters(self):
        selected = self.rule_dropdown.get_selected()
        selected_rule = None
        if selected > 0:
            selected_rule = self.rule_model.get_string(selected)
        
        return {
            "errors": self.error_toggle.get_active(),
            "warnings": self.warning_toggle.get_active(),
            "info": self.info_toggle.get_active(),
            "rule": selected_rule,
            "search": self.search_entry.get_text().lower(),
        }


class L10nLintWindow(Adw.ApplicationWindow):
    """Main application window."""
    
    def __init__(self, app):
        super().__init__(application=app, title="l10n-lint")
        self.set_default_size(1100, 850)
        
        self.settings = load_settings()
        self.current_result = None
        self.all_issues = []
        self.history = []
        self._setup_ui()
        self._load_history()
    
    def _setup_ui(self):
        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Header bar
        header = Adw.HeaderBar()
        
        # Open file button
        open_btn = Gtk.Button(icon_name="document-open-symbolic")
        open_btn.set_tooltip_text(_("Open file"))
        open_btn.connect("clicked", self._on_open_clicked)
        header.pack_start(open_btn)
        
        # Open folder button
        folder_btn = Gtk.Button(icon_name="folder-open-symbolic")
        folder_btn.set_tooltip_text(_("Open directory"))
        folder_btn.connect("clicked", self._on_open_folder_clicked)
        header.pack_start(folder_btn)
        
        # Lint button
        self.lint_btn = Gtk.Button(label=_("Lint"))
        self.lint_btn.add_css_class("suggested-action")
        self.lint_btn.set_tooltip_text(_("Run linter (Ctrl+Return)"))
        self.lint_btn.connect("clicked", self._on_lint_clicked)
        self.lint_btn.set_sensitive(False)
        header.pack_start(self.lint_btn)
        
        # Export button
        export_btn = Gtk.Button(icon_name="document-save-symbolic")
        export_btn.set_tooltip_text(_("Export report"))
        export_btn.connect("clicked", self._on_export_clicked)
        header.pack_end(export_btn)
        
        # Menu button
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_btn.set_primary(True)
        menu = Gio.Menu()
        menu.append(_("Preferences"), "app.preferences")
        menu.append(_("Keyboard Shortcuts"), "app.shortcuts")
        menu.append(_("About"), "app.about")
        menu.append(_("Quit"), "app.quit")
        menu_btn.set_menu_model(menu)
        header.pack_end(menu_btn)
        self.menu_button = menu_btn  # Keep reference
        
        main_box.append(header)
        
        # Content with sidebar
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(250)
        
        # Sidebar - history
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.set_size_request(200, -1)
        
        sidebar_header = Gtk.Label(label=_("Recent"))
        sidebar_header.add_css_class("heading")
        sidebar_header.set_margin_top(12)
        sidebar_header.set_margin_bottom(8)
        sidebar.append(sidebar_header)
        
        scrolled_sidebar = Gtk.ScrolledWindow()
        scrolled_sidebar.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_sidebar.set_vexpand(True)
        
        self.history_list = Gtk.ListBox()
        self.history_list.add_css_class("navigation-sidebar")
        self.history_list.connect("row-activated", self._on_history_activated)
        scrolled_sidebar.set_child(self.history_list)
        sidebar.append(scrolled_sidebar)
        
        # Clear history button
        clear_btn = Gtk.Button(label=_("Clear History"))
        clear_btn.set_margin_start(8)
        clear_btn.set_margin_end(8)
        clear_btn.set_margin_bottom(8)
        clear_btn.connect("clicked", self._on_clear_history)
        sidebar.append(clear_btn)
        
        paned.set_start_child(sidebar)
        
        # Main content
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        
        # Path entry row
        path_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        path_box.set_margin_start(8)
        path_box.set_margin_end(8)
        path_box.set_margin_top(8)
        
        path_label = Gtk.Label(label=_("Path:"))
        path_box.append(path_label)
        
        self.path_entry = Gtk.Entry()
        self.path_entry.set_hexpand(True)
        self.path_entry.set_placeholder_text(_("File, directory, URL, or GitHub repo (owner/repo)..."))
        self.path_entry.connect("changed", self._on_path_changed)
        self.path_entry.connect("activate", lambda e: self._on_lint_clicked(None))
        path_box.append(self.path_entry)
        
        browse_btn = Gtk.Button(icon_name="folder-symbolic")
        browse_btn.set_tooltip_text(_("Browse..."))
        browse_btn.connect("clicked", self._on_open_clicked)
        path_box.append(browse_btn)
        
        content.append(path_box)
        
        # Metadata panel
        self.metadata_panel = MetadataPanel()
        self.metadata_panel.set_visible(False)
        content.append(self.metadata_panel)
        
        # Filter bar
        self.filter_bar = FilterBar(self._apply_filters)
        self.filter_bar.set_visible(False)
        content.append(self.filter_bar)
        
        # Status bar
        self.status_label = Gtk.Label(label=_("Select a file or directory to lint. You can also drag and drop files here."))
        self.status_label.set_xalign(0)
        self.status_label.set_margin_start(8)
        self.status_label.add_css_class("dim-label")
        content.append(self.status_label)
        
        # Progress bar (hidden by default)
        self.progress = Gtk.ProgressBar()
        self.progress.set_margin_start(8)
        self.progress.set_margin_end(8)
        self.progress.set_visible(False)
        content.append(self.progress)
        
        # Results area
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        
        self.results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scrolled.set_child(self.results_box)
        
        content.append(scrolled)
        
        # Summary bar
        summary_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        summary_box.set_margin_start(8)
        summary_box.set_margin_end(8)
        summary_box.set_margin_bottom(8)
        
        self.summary_label = Gtk.Label()
        self.summary_label.set_xalign(0)
        self.summary_label.set_hexpand(True)
        summary_box.append(self.summary_label)
        
        self.count_label = Gtk.Label()
        self.count_label.add_css_class("dim-label")
        summary_box.append(self.count_label)
        
        content.append(summary_box)
        
        paned.set_end_child(content)
        main_box.append(paned)
        
        self.set_content(main_box)
        
        # Drag and drop support
        self._setup_drop_target()
        
        # Keyboard shortcuts
        self._setup_shortcuts()
    
    def _setup_shortcuts(self):
        controller = Gtk.ShortcutController()
        controller.set_scope(Gtk.ShortcutScope.GLOBAL)
        
        # Ctrl+O - Open
        controller.add_shortcut(Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("<Control>o"),
            Gtk.CallbackAction.new(lambda *args: self._on_open_clicked(None))
        ))
        
        # Ctrl+Return - Lint
        controller.add_shortcut(Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("<Control>Return"),
            Gtk.CallbackAction.new(lambda *args: self._on_lint_clicked(None) if self.lint_btn.get_sensitive() else None)
        ))
        
        # Ctrl+E - Export
        controller.add_shortcut(Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("<Control>e"),
            Gtk.CallbackAction.new(lambda *args: self._on_export_clicked(None))
        ))
        
        self.add_controller(controller)
    
    def _setup_drop_target(self):
        """Set up drag and drop support for files."""
        drop_target = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop_target.connect("drop", self._on_drop)
        drop_target.connect("enter", self._on_drop_enter)
        drop_target.connect("leave", self._on_drop_leave)
        self.add_controller(drop_target)
    
    def _on_drop_enter(self, drop_target, x, y):
        """Visual feedback when dragging over window."""
        self.add_css_class("drop-target")
        self.status_label.set_text(_("Drop file to lint..."))
        return Gdk.DragAction.COPY
    
    def _on_drop_leave(self, drop_target):
        """Remove visual feedback when leaving."""
        self.remove_css_class("drop-target")
        if not self.path_entry.get_text():
            self.status_label.set_text(_("Select a file or directory to lint. You can also drag and drop files here."))
    
    def _on_drop(self, drop_target, value, x, y):
        """Handle dropped file - set path and auto-lint."""
        if isinstance(value, Gio.File):
            path = value.get_path()
            if path:
                # Check if it's a supported file type
                if path.endswith(('.po', '.ts')) or os.path.isdir(path):
                    self.path_entry.set_text(path)
                    self.remove_css_class("drop-target")
                    # Show metadata immediately
                    if not os.path.isdir(path):
                        metadata = FileMetadata(path)
                        self.metadata_panel.update(metadata)
                        self.metadata_panel.set_visible(True)
                    # Auto-start lint
                    GLib.idle_add(self._on_lint_clicked, None)
                    return True
                else:
                    self.status_label.set_text(_("Unsupported file type. Use .po or .ts files."))
                    self.remove_css_class("drop-target")
        return False
    
    def _load_history(self):
        history_file = Path.home() / ".config" / "l10n-lint" / "history.json"
        if history_file.exists():
            try:
                self.history = json.loads(history_file.read_text())[:20]
                self._update_history_list()
            except Exception:
                pass
    
    def _save_history(self):
        history_file = Path.home() / ".config" / "l10n-lint" / "history.json"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history_file.write_text(json.dumps(self.history[:20]))
    
    def _add_to_history(self, path):
        # Remove if exists
        self.history = [h for h in self.history if h["path"] != path]
        # Add to front
        self.history.insert(0, {
            "path": path,
            "timestamp": datetime.now().isoformat(),
        })
        self.history = self.history[:20]
        self._save_history()
        self._update_history_list()
    
    def _update_history_list(self):
        while child := self.history_list.get_first_child():
            self.history_list.remove(child)
        
        for item in self.history:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_margin_start(8)
            box.set_margin_end(8)
            box.set_margin_top(4)
            box.set_margin_bottom(4)
            
            path_label = Gtk.Label(label=Path(item["path"]).name or item["path"])
            path_label.set_xalign(0)
            path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            box.append(path_label)
            
            full_path = Gtk.Label(label=item["path"])
            full_path.set_xalign(0)
            full_path.add_css_class("dim-label")
            full_path.add_css_class("caption")
            full_path.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            box.append(full_path)
            
            row.set_child(box)
            row.path = item["path"]
            self.history_list.append(row)
    
    def _on_history_activated(self, listbox, row):
        self.path_entry.set_text(row.path)
        self._on_lint_clicked(None)
    
    def _on_clear_history(self, button):
        self.history = []
        self._save_history()
        self._update_history_list()
    
    def _on_path_changed(self, entry):
        path = entry.get_text()
        valid = bool(path) and (
            Path(path).exists() or 
            path.startswith("http") or
            "/" in path  # GitHub repo
        )
        self.lint_btn.set_sensitive(valid)
        
        # Show metadata for single file
        if valid and Path(path).is_file():
            metadata = FileMetadata(path)
            self.metadata_panel.update(metadata)
            self.metadata_panel.set_visible(True)
        elif not valid or Path(path).is_dir():
            self.metadata_panel.set_visible(False)
    
    def _on_open_clicked(self, button):
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Select file"))
        
        # File filter
        filter_store = Gio.ListStore.new(Gtk.FileFilter)
        
        l10n_filter = Gtk.FileFilter()
        l10n_filter.set_name(_("Localization files (*.po, *.ts)"))
        l10n_filter.add_pattern("*.po")
        l10n_filter.add_pattern("*.ts")
        filter_store.append(l10n_filter)
        
        all_filter = Gtk.FileFilter()
        all_filter.set_name(_("All files"))
        all_filter.add_pattern("*")
        filter_store.append(all_filter)
        
        dialog.set_filters(filter_store)
        dialog.open(self, None, self._on_file_selected)
    
    def _on_open_folder_clicked(self, button):
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Select directory"))
        dialog.select_folder(self, None, self._on_folder_selected)
    
    def _on_file_selected(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                self.path_entry.set_text(file.get_path())
        except GLib.Error:
            pass
    
    def _on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                self.path_entry.set_text(folder.get_path())
        except GLib.Error:
            pass
    
    def _on_lint_clicked(self, button):
        path = self.path_entry.get_text()
        if not path:
            return
        
        self.lint_btn.set_sensitive(False)
        self.progress.set_visible(True)
        self.progress.set_fraction(0)
        self.status_label.set_text(_("Linting {path}...").format(path=path))
        self.filter_bar.set_visible(False)
        
        # Show metadata panel
        p = Path(path)
        if p.is_file():
            metadata = FileMetadata(path)
            self.metadata_panel.update(metadata)
            self.metadata_panel.set_visible(True)
        elif p.is_dir():
            self.metadata_panel.set_visible(False)
        
        # Clear previous results
        while child := self.results_box.get_first_child():
            self.results_box.remove(child)
        
        # Add to history
        self._add_to_history(path)
        
        # Run lint in background thread
        thread = threading.Thread(target=self._run_lint, args=(path,))
        thread.daemon = True
        thread.start()
        
        # Pulse progress while running
        GLib.timeout_add(100, self._pulse_progress)
    
    def _pulse_progress(self):
        if self.progress.get_visible():
            self.progress.pulse()
            return True
        return False
    
    def _run_lint(self, path):
        try:
            linter = L10nLinter()
            result = LintResult()
            
            # Set linter options based on settings
            enabled_rules = set(self.settings.get("enabled_rules", []))
            
            p = Path(path)
            if p.is_dir():
                files = list(find_l10n_files(path, recursive=self.settings.get("recursive", True)))
                total = len(files)
                for i, file_path in enumerate(files):
                    file_result = linter.lint_file(file_path)
                    # Filter issues by enabled rules
                    for issue in file_result.issues:
                        if issue.rule in enabled_rules or not enabled_rules:
                            result.issues.append(issue)
                    result.files_checked += file_result.files_checked
                    GLib.idle_add(self._update_progress, (i + 1) / total, file_path)
            elif p.is_file():
                file_result = linter.lint_file(path)
                # Filter issues by enabled rules
                for issue in file_result.issues:
                    if issue.rule in enabled_rules or not enabled_rules:
                        result.issues.append(issue)
                result.files_checked = file_result.files_checked
            elif is_url(path):
                temp_path, content = fetch_url_file(path)
                file_result = linter.lint_file(temp_path)
                for issue in file_result.issues:
                    issue.file = path
                    if issue.rule in enabled_rules or not enabled_rules:
                        result.issues.append(issue)
            elif "/" in path and not path.startswith("/"):
                # GitHub repo
                GLib.idle_add(self.status_label.set_text, _("Fetching from GitHub..."))
                from l10n_lint import lint_github_repo
                github_result = lint_github_repo(path, "")
                for issue in github_result.issues:
                    if issue.rule in enabled_rules or not enabled_rules:
                        result.issues.append(issue)
                result.files_checked = github_result.files_checked
            else:
                result.issues.append(LintIssue(
                    file=path, line=0, severity=Severity.ERROR,
                    rule="path", message=_("Path not found: {path}").format(path=path)
                ))
            
            GLib.idle_add(self._show_results, result)
        except Exception as e:
            result = LintResult()
            result.issues.append(LintIssue(
                file=path, line=0, severity=Severity.ERROR,
                rule="error", message=str(e)
            ))
            GLib.idle_add(self._show_results, result)
    
    def _update_progress(self, fraction, current_file):
        self.progress.set_fraction(fraction)
        self.status_label.set_text(_("Linting {path}...").format(path=Path(current_file).name))
        return False
    
    def _show_results(self, result: LintResult):
        self.current_result = result
        self.all_issues = result.issues.copy()
        self.progress.set_visible(False)
        self.lint_btn.set_sensitive(True)
        
        # Update filter bar with found rules
        found_rules = [issue.rule for issue in result.issues]
        self.filter_bar.update_rules(found_rules)
        
        # Show filter bar if there are issues
        self.filter_bar.set_visible(bool(result.issues))
        
        self._display_issues(result.issues)
        return False
    
    def _apply_filters(self):
        if not self.all_issues:
            return
        
        filters = self.filter_bar.get_filters()
        filtered = []
        
        for issue in self.all_issues:
            # Severity filter
            if issue.severity == Severity.ERROR and not filters["errors"]:
                continue
            if issue.severity == Severity.WARNING and not filters["warnings"]:
                continue
            if issue.severity == Severity.INFO and not filters["info"]:
                continue
            
            # Rule filter
            if filters["rule"] and issue.rule != filters["rule"]:
                continue
            
            # Search filter
            if filters["search"]:
                search = filters["search"]
                if (search not in issue.message.lower() and
                    search not in issue.file.lower() and
                    search not in issue.rule.lower()):
                    continue
            
            filtered.append(issue)
        
        self._display_issues(filtered)
    
    def _display_issues(self, issues):
        # Clear previous
        while child := self.results_box.get_first_child():
            self.results_box.remove(child)
        
        # Count by severity
        errors = sum(1 for i in issues if i.severity == Severity.ERROR)
        warnings = sum(1 for i in issues if i.severity == Severity.WARNING)
        infos = sum(1 for i in issues if i.severity == Severity.INFO)
        
        if issues:
            for issue in issues:
                row = LintRow(issue, self._on_issue_clicked)
                self.results_box.append(row)
            
            self.status_label.set_text(_("Found {count} issue(s)").format(count=len(self.all_issues)))
            self.summary_label.set_markup(
                f"<span foreground='#e74c3c'>{errors} " + _("errors") + "</span> · "
                f"<span foreground='#f39c12'>{warnings} " + _("warnings") + "</span> · "
                f"<span foreground='#3498db'>{infos} " + _("info") + "</span>"
            )
            self.count_label.set_text(_("Showing {shown} of {total}").format(
                shown=len(issues), total=len(self.all_issues)
            ))
        else:
            if self.all_issues:
                # Filtered to zero
                no_match = Gtk.Label(label=_("No issues match the current filter"))
                no_match.add_css_class("dim-label")
                self.results_box.append(no_match)
            else:
                success_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                success_box.set_valign(Gtk.Align.CENTER)
                success_box.set_vexpand(True)
                
                success_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                success_icon.set_pixel_size(64)
                success_icon.add_css_class("success")
                success_box.append(success_icon)
                
                success_label = Gtk.Label()
                success_label.set_markup("<span size='large' weight='bold'>" + _("No issues found!") + "</span>")
                success_box.append(success_label)
                
                self.results_box.append(success_box)
                self.status_label.set_text(_("Lint completed successfully"))
            
            self.summary_label.set_text("")
            self.count_label.set_text("")
    
    def _on_issue_clicked(self, issue):
        # Show issue details dialog
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=f"{issue.severity.value.upper()}: {issue.rule}",
            body=f"{issue.file}:{issue.line}\n\n{issue.message}"
        )
        if issue.context:
            dialog.set_body(f"{issue.file}:{issue.line}\n\n{issue.message}\n\n{issue.context}")
        dialog.add_response("close", _("Close"))
        dialog.add_response("copy", _("Copy"))
        dialog.set_response_appearance("copy", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_issue_dialog_response, issue)
        dialog.present()
    
    def _on_issue_dialog_response(self, dialog, response, issue):
        if response == "copy":
            clipboard = Gdk.Display.get_default().get_clipboard()
            text = f"{issue.file}:{issue.line}: {issue.severity.value}: [{issue.rule}] {issue.message}"
            clipboard.set(text)
    
    def _on_export_clicked(self, button):
        if not self.current_result:
            return
        
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Export report"))
        dialog.set_initial_name("l10n-lint-report.html")
        
        filters = Gio.ListStore.new(Gtk.FileFilter)
        
        html_filter = Gtk.FileFilter()
        html_filter.set_name("HTML")
        html_filter.add_pattern("*.html")
        filters.append(html_filter)
        
        json_filter = Gtk.FileFilter()
        json_filter.set_name("JSON")
        json_filter.add_pattern("*.json")
        filters.append(json_filter)
        
        text_filter = Gtk.FileFilter()
        text_filter.set_name(_("Plain text"))
        text_filter.add_pattern("*.txt")
        filters.append(text_filter)
        
        dialog.set_filters(filters)
        dialog.save(self, None, self._on_export_save)
    
    def _on_export_save(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            if file:
                path = file.get_path()
                if path.endswith(".json"):
                    self._export_json(path)
                elif path.endswith(".html"):
                    self._export_html(path)
                else:
                    self._export_text(path)
        except GLib.Error:
            pass
    
    def _export_json(self, path):
        data = {
            "timestamp": datetime.now().isoformat(),
            "files_checked": self.current_result.files_checked,
            "issues": [
                {
                    "file": i.file,
                    "line": i.line,
                    "severity": i.severity.value,
                    "rule": i.rule,
                    "message": i.message,
                    "context": i.context,
                }
                for i in self.current_result.issues
            ]
        }
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))
    
    def _export_html(self, path):
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>l10n-lint Report</title>
<style>
body {{ font-family: system-ui; max-width: 1200px; margin: 0 auto; padding: 20px; }}
.stats {{ display: flex; gap: 20px; margin-bottom: 20px; }}
.stat {{ background: #f5f5f5; padding: 15px; border-radius: 8px; text-align: center; }}
.stat-value {{ font-size: 24px; font-weight: bold; }}
.issue {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin-bottom: 8px; }}
.error {{ border-left: 4px solid #e74c3c; }}
.warning {{ border-left: 4px solid #f39c12; }}
.info {{ border-left: 4px solid #3498db; }}
.severity {{ font-weight: bold; text-transform: uppercase; }}
.location {{ color: #666; }}
.rule {{ background: #eee; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
.context {{ background: #f9f9f9; padding: 8px; margin-top: 8px; font-family: monospace; }}
</style>
</head>
<body>
<h1>l10n-lint Report</h1>
<p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>

<div class="stats">
<div class="stat"><div class="stat-value">{self.current_result.files_checked}</div>Files</div>
<div class="stat"><div class="stat-value">{len(self.current_result.issues)}</div>Issues</div>
<div class="stat"><div class="stat-value" style="color:#e74c3c">{self.current_result.error_count}</div>Errors</div>
<div class="stat"><div class="stat-value" style="color:#f39c12">{self.current_result.warning_count}</div>Warnings</div>
</div>

<h2>Issues ({len(self.current_result.issues)})</h2>
"""
        for issue in self.current_result.issues:
            html += f"""<div class="issue {issue.severity.value}">
<span class="severity" style="color:{'#e74c3c' if issue.severity == Severity.ERROR else '#f39c12' if issue.severity == Severity.WARNING else '#3498db'}">{issue.severity.value}</span>
<span class="location">{issue.file}:{issue.line}</span>
<span class="rule">{issue.rule}</span>
<p>{issue.message}</p>
{"<div class='context'>" + issue.context + "</div>" if issue.context else ""}
</div>
"""
        html += "</body></html>"
        Path(path).write_text(html)
    
    def _export_text(self, path):
        lines = [
            f"l10n-lint Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Files: {self.current_result.files_checked}",
            "",
            f"Issues: {len(self.current_result.issues)}",
            "-" * 60,
        ]
        for issue in self.current_result.issues:
            lines.append(f"{issue.file}:{issue.line}: {issue.severity.value}: [{issue.rule}] {issue.message}")
        Path(path).write_text("\n".join(lines))


class PreferencesWindow(Adw.PreferencesWindow):
    """Preferences window with lint rule selection."""
    
    def __init__(self, app):
        super().__init__(transient_for=app.props.active_window)
        self.set_title(_("Preferences"))
        self.settings = load_settings()
        
        page = Adw.PreferencesPage()
        
        # Lint rules group
        rules_group = Adw.PreferencesGroup(
            title=_("Lint Rules"),
            description=_("Select which checks to perform")
        )
        
        self.rule_switches = {}
        enabled_rules = set(self.settings.get("enabled_rules", []))
        
        for rule_id, (name, description, _default) in LINT_RULES.items():
            row = Adw.SwitchRow(title=name, subtitle=description)
            row.set_active(rule_id in enabled_rules)
            row.connect("notify::active", self._on_rule_toggled, rule_id)
            self.rule_switches[rule_id] = row
            rules_group.add(row)
        
        page.add(rules_group)
        
        # Options group
        options_group = Adw.PreferencesGroup(title=_("Options"))
        
        recursive_row = Adw.SwitchRow(
            title=_("Search subdirectories"),
            subtitle=_("Recursively search directories for l10n files")
        )
        recursive_row.set_active(self.settings.get("recursive", True))
        recursive_row.connect("notify::active", self._on_recursive_toggled)
        options_group.add(recursive_row)
        
        strict_row = Adw.SwitchRow(
            title=_("Strict mode"),
            subtitle=_("Treat warnings as errors")
        )
        strict_row.set_active(self.settings.get("strict_mode", False))
        strict_row.connect("notify::active", self._on_strict_toggled)
        options_group.add(strict_row)
        
        page.add(options_group)
        
        # Quick actions
        actions_group = Adw.PreferencesGroup(title=_("Quick Actions"))
        
        enable_all = Gtk.Button(label=_("Enable All Rules"))
        enable_all.connect("clicked", self._enable_all_rules)
        enable_all.add_css_class("pill")
        
        disable_all = Gtk.Button(label=_("Disable All Rules"))
        disable_all.connect("clicked", self._disable_all_rules)
        disable_all.add_css_class("pill")
        
        reset_defaults = Gtk.Button(label=_("Reset to Defaults"))
        reset_defaults.connect("clicked", self._reset_defaults)
        reset_defaults.add_css_class("pill")
        
        buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons_box.set_halign(Gtk.Align.CENTER)
        buttons_box.set_margin_top(12)
        buttons_box.append(enable_all)
        buttons_box.append(disable_all)
        buttons_box.append(reset_defaults)
        
        actions_row = Adw.PreferencesRow()
        actions_row.set_child(buttons_box)
        actions_group.add(actions_row)
        
        page.add(actions_group)
        
        self.add(page)
    
    def _on_rule_toggled(self, row, param, rule_id):
        enabled = set(self.settings.get("enabled_rules", []))
        if row.get_active():
            enabled.add(rule_id)
        else:
            enabled.discard(rule_id)
        self.settings["enabled_rules"] = list(enabled)
        save_settings(self.settings)
    
    def _on_recursive_toggled(self, row, param):
        self.settings["recursive"] = row.get_active()
        save_settings(self.settings)
    
    def _on_strict_toggled(self, row, param):
        self.settings["strict_mode"] = row.get_active()
        save_settings(self.settings)
    
    def _enable_all_rules(self, button):
        self.settings["enabled_rules"] = list(LINT_RULES.keys())
        for switch in self.rule_switches.values():
            switch.set_active(True)
        save_settings(self.settings)
    
    def _disable_all_rules(self, button):
        self.settings["enabled_rules"] = []
        for switch in self.rule_switches.values():
            switch.set_active(False)
        save_settings(self.settings)
    
    def _reset_defaults(self, button):
        default_rules = [rule for rule, (name, desc, default) in LINT_RULES.items() if default]
        self.settings["enabled_rules"] = default_rules
        for rule_id, switch in self.rule_switches.items():
            switch.set_active(rule_id in default_rules)
        save_settings(self.settings)


class L10nLintApp(Adw.Application):
    """Main GTK application."""
    
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN
        )
        
        # Actions
        self.create_action("quit", self.on_quit, ["<Control>q"])
        self.create_action("about", self.on_about)
        self.create_action("preferences", self.on_preferences, ["<Control>comma"])
        self.create_action("shortcuts", self.on_shortcuts, ["<Control>question"])
    
    def create_action(self, name, callback, shortcuts=None):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)
    
    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = L10nLintWindow(self)
        win.present()
    
    def do_open(self, files, n_files, hint):
        self.do_activate()
        if files:
            win = self.props.active_window
            win.path_entry.set_text(files[0].get_path())
            win._on_lint_clicked(None)
    
    def on_quit(self, action, param):
        self.quit()
    
    def on_preferences(self, action, param):
        prefs = PreferencesWindow(self)
        prefs.present()
    
    def on_shortcuts(self, action, param):
        builder = Gtk.Builder()
        builder.add_from_string("""
        <interface>
          <object class="GtkShortcutsWindow" id="shortcuts">
            <property name="modal">true</property>
            <child>
              <object class="GtkShortcutsSection">
                <property name="visible">true</property>
                <child>
                  <object class="GtkShortcutsGroup">
                    <property name="visible">true</property>
                    <property name="title">General</property>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="visible">true</property>
                        <property name="accelerator">&lt;Control&gt;o</property>
                        <property name="title">Open file</property>
                      </object>
                    </child>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="visible">true</property>
                        <property name="accelerator">&lt;Control&gt;Return</property>
                        <property name="title">Run linter</property>
                      </object>
                    </child>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="visible">true</property>
                        <property name="accelerator">&lt;Control&gt;e</property>
                        <property name="title">Export report</property>
                      </object>
                    </child>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="visible">true</property>
                        <property name="accelerator">&lt;Control&gt;comma</property>
                        <property name="title">Preferences</property>
                      </object>
                    </child>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="visible">true</property>
                        <property name="accelerator">&lt;Control&gt;q</property>
                        <property name="title">Quit</property>
                      </object>
                    </child>
                  </object>
                </child>
              </object>
            </child>
          </object>
        </interface>
        """)
        shortcuts = builder.get_object("shortcuts")
        shortcuts.set_transient_for(self.props.active_window)
        shortcuts.present()
    
    def on_about(self, action, param):
        about = Adw.AboutWindow(
            transient_for=self.props.active_window,
            application_name="l10n-lint",
            application_icon=APP_ID,
            developer_name="Daniel Nylander",
            version=f"GTK {__version__} (core {LINT_VERSION})",
            website="https://github.com/yeager/l10n-lint",
            issue_url="https://github.com/yeager/l10n-lint/issues",
            translate_url="https://app.transifex.com/danielnylander/l10n-lint/",
            license_type=Gtk.License.GPL_3_0,
            copyright="© 2026 Daniel Nylander",
            developers=["Daniel Nylander <daniel@danielnylander.se>"],
            comments=_("Graphical linter for localization files (.po, .ts)"),
            translator_credits=_("translator-credits"),
        )
        about.present()


def main():
    app = L10nLintApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
