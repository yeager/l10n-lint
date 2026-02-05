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
from gi.repository import Gtk, Gio, GLib, Adw, Pango

import os
import sys
import threading
from pathlib import Path

# Import l10n-lint core functionality
from l10n_lint import (
    L10nLinter, LintResult, LintIssue, Severity,
    find_l10n_files, fetch_url_file, is_url,
    __version__ as LINT_VERSION
)

__version__ = "1.0.0"
APP_ID = "se.danielnylander.l10n-lint"


class LintRow(Gtk.Box):
    """A row displaying a lint issue."""
    
    def __init__(self, issue: LintIssue):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("lint-row")
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        
        # Severity colors
        severity_colors = {
            Severity.ERROR: "#e74c3c",
            Severity.WARNING: "#f39c12", 
            Severity.INFO: "#3498db",
        }
        color = severity_colors.get(issue.severity, "#666")
        
        # Header: severity icon + file:line + rule
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        # Severity badge
        severity_label = Gtk.Label()
        severity_label.set_markup(
            f"<span foreground='{color}' weight='bold'>{issue.severity.value.upper()}</span>"
        )
        header.append(severity_label)
        
        # Location
        location = Gtk.Label(label=f"{issue.file}:{issue.line}")
        location.add_css_class("dim-label")
        location.set_hexpand(True)
        location.set_xalign(0)
        header.append(location)
        
        # Rule
        rule_label = Gtk.Label(label=f"[{issue.rule}]")
        rule_label.add_css_class("dim-label")
        header.append(rule_label)
        
        self.append(header)
        
        # Message
        message_label = Gtk.Label(label=issue.message)
        message_label.set_xalign(0)
        message_label.set_wrap(True)
        message_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.append(message_label)
        
        # Context (if present)
        if issue.context:
            context_label = Gtk.Label()
            context_label.set_markup(f"<tt>{GLib.markup_escape_text(issue.context)}</tt>")
            context_label.set_xalign(0)
            context_label.add_css_class("dim-label")
            self.append(context_label)


class L10nLintWindow(Adw.ApplicationWindow):
    """Main application window."""
    
    def __init__(self, app):
        super().__init__(application=app, title="l10n-lint")
        self.set_default_size(900, 700)
        
        self.current_result = None
        self._setup_ui()
    
    def _setup_ui(self):
        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Header bar
        header = Adw.HeaderBar()
        
        # Open file button
        open_btn = Gtk.Button(icon_name="document-open-symbolic")
        open_btn.set_tooltip_text("Open file or directory")
        open_btn.connect("clicked", self._on_open_clicked)
        header.pack_start(open_btn)
        
        # Lint button
        self.lint_btn = Gtk.Button(label="Lint")
        self.lint_btn.add_css_class("suggested-action")
        self.lint_btn.set_tooltip_text("Run linter")
        self.lint_btn.connect("clicked", self._on_lint_clicked)
        self.lint_btn.set_sensitive(False)
        header.pack_start(self.lint_btn)
        
        # Menu button
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu = Gio.Menu()
        menu.append("About", "app.about")
        menu.append("Quit", "app.quit")
        menu_btn.set_menu_model(menu)
        header.pack_end(menu_btn)
        
        main_box.append(header)
        
        # Content
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(12)
        content.set_margin_end(12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        
        # Path entry
        path_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        path_label = Gtk.Label(label="Path:")
        path_box.append(path_label)
        
        self.path_entry = Gtk.Entry()
        self.path_entry.set_hexpand(True)
        self.path_entry.set_placeholder_text("Select a .po or .ts file, or directory...")
        self.path_entry.connect("changed", self._on_path_changed)
        path_box.append(self.path_entry)
        
        browse_btn = Gtk.Button(label="Browse...")
        browse_btn.connect("clicked", self._on_open_clicked)
        path_box.append(browse_btn)
        
        content.append(path_box)
        
        # Status bar
        self.status_label = Gtk.Label(label="Select a file or directory to lint")
        self.status_label.set_xalign(0)
        self.status_label.add_css_class("dim-label")
        content.append(self.status_label)
        
        # Progress bar (hidden by default)
        self.progress = Gtk.ProgressBar()
        self.progress.set_visible(False)
        content.append(self.progress)
        
        # Results area
        results_frame = Gtk.Frame()
        results_frame.set_vexpand(True)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self.results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scrolled.set_child(self.results_box)
        results_frame.set_child(scrolled)
        
        content.append(results_frame)
        
        # Summary bar
        self.summary_label = Gtk.Label()
        self.summary_label.set_xalign(0)
        content.append(self.summary_label)
        
        main_box.append(content)
        self.set_content(main_box)
    
    def _on_path_changed(self, entry):
        path = entry.get_text()
        self.lint_btn.set_sensitive(bool(path) and (Path(path).exists() or path.startswith("http")))
    
    def _on_open_clicked(self, button):
        dialog = Gtk.FileDialog()
        dialog.set_title("Select file or directory")
        
        # Allow both files and folders
        dialog.open(self, None, self._on_file_selected)
    
    def _on_file_selected(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                self.path_entry.set_text(file.get_path())
        except GLib.Error:
            pass
    
    def _on_lint_clicked(self, button):
        path = self.path_entry.get_text()
        if not path:
            return
        
        self.lint_btn.set_sensitive(False)
        self.progress.set_visible(True)
        self.progress.pulse()
        self.status_label.set_text(f"Linting {path}...")
        
        # Clear previous results
        while child := self.results_box.get_first_child():
            self.results_box.remove(child)
        
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
            
            p = Path(path)
            if p.is_dir():
                # Lint all files in directory
                for file_path in find_l10n_files(path, recursive=True):
                    file_result = linter.lint(file_path)
                    result.issues.extend(file_result.issues)
                    result.files_checked += file_result.files_checked
                    result.total_entries += file_result.total_entries
                    result.translated += file_result.translated
                    result.untranslated += file_result.untranslated
                    result.fuzzy += file_result.fuzzy
            elif p.is_file():
                result = linter.lint(path)
            elif is_url(path):
                # Fetch URL and lint
                temp_path, content = fetch_url_file(path)
                result = linter.lint(temp_path)
                # Update file name in issues
                for issue in result.issues:
                    issue.file = path
            else:
                result.issues.append(LintIssue(
                    file=path, line=0, severity=Severity.ERROR,
                    rule="path", message=f"Path not found: {path}"
                ))
            
            # Update UI in main thread
            GLib.idle_add(self._show_results, result)
        except Exception as e:
            result = LintResult()
            result.issues.append(LintIssue(
                file=path, line=0, severity=Severity.ERROR,
                rule="error", message=str(e)
            ))
            GLib.idle_add(self._show_results, result)
    
    def _show_results(self, result: LintResult):
        self.current_result = result
        self.progress.set_visible(False)
        self.lint_btn.set_sensitive(True)
        
        # Clear previous
        while child := self.results_box.get_first_child():
            self.results_box.remove(child)
        
        # Count by severity
        errors = sum(1 for i in result.issues if i.severity == Severity.ERROR)
        warnings = sum(1 for i in result.issues if i.severity == Severity.WARNING)
        infos = sum(1 for i in result.issues if i.severity == Severity.INFO)
        
        if result.issues:
            for issue in result.issues:
                row = LintRow(issue)
                self.results_box.append(row)
            
            self.status_label.set_text(f"Found {len(result.issues)} issue(s)")
            self.summary_label.set_markup(
                f"<span foreground='#e74c3c'>{errors} errors</span> · "
                f"<span foreground='#f39c12'>{warnings} warnings</span> · "
                f"<span foreground='#3498db'>{infos} info</span>"
            )
        else:
            success_label = Gtk.Label()
            success_label.set_markup("<span foreground='#27ae60' size='large'>✓ No issues found!</span>")
            self.results_box.append(success_label)
            self.status_label.set_text("Lint completed successfully")
            self.summary_label.set_text("")
        
        return False


class L10nLintApp(Adw.Application):
    """Main GTK application."""
    
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )
        
        # Actions
        self.create_action("quit", self.on_quit)
        self.create_action("about", self.on_about)
    
    def create_action(self, name, callback):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
    
    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = L10nLintWindow(self)
        win.present()
    
    def on_quit(self, action, param):
        self.quit()
    
    def on_about(self, action, param):
        about = Adw.AboutWindow(
            transient_for=self.props.active_window,
            application_name="l10n-lint",
            application_icon=APP_ID,
            developer_name="Daniel Nylander",
            version=f"GTK {__version__} (lint {LINT_VERSION})",
            website="https://github.com/yeager/l10n-lint",
            issue_url="https://github.com/yeager/l10n-lint/issues",
            license_type=Gtk.License.GPL_3_0,
            copyright="© 2026 Daniel Nylander",
            developers=["Daniel Nylander <daniel@danielnylander.se>"],
            comments="Linter for localization files (.po, .ts)"
        )
        about.present()


def main():
    app = L10nLintApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
