#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# l10n-lint - Linter for localization files
# Copyright (C) 2026 Daniel Nylander <daniel@danielnylander.se>
"""
l10n-lint - Linter for localization files (.po, .ts)

Checks for:
- Missing translations (empty msgstr)
- Fuzzy entries
- Placeholder mismatches (%s, %d, {0}, {1}, etc.)
- String length issues
- Duplicate entries
- Invalid syntax
"""

import argparse
import gettext
import json
import locale
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Generator, Optional
from urllib.parse import urlparse

__version__ = "1.3.1"

# Translation setup
DOMAIN = "l10n-lint"

# Look for locale in multiple places
_possible_locale_dirs = [
    Path(__file__).parent / "locale",  # Development
    Path("/usr/share/l10n-lint/locale"),  # System install
    Path("/usr/local/share/l10n-lint/locale"),  # Local install
]
LOCALE_DIR = None
for _dir in _possible_locale_dirs:
    if _dir.exists():
        LOCALE_DIR = _dir
        break

# Initialize gettext - detect language
# Priority: LANGUAGE > LC_ALL > LC_MESSAGES > LANG > locale.getlocale()
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


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class LintIssue:
    file: str
    line: int
    severity: Severity
    rule: str
    message: str
    context: str = ""
    
    def to_dict(self):
        return {
            "file": self.file,
            "line": self.line,
            "severity": self.severity.value,
            "rule": self.rule,
            "message": self.message,
            "context": self.context,
        }


@dataclass
class LintResult:
    issues: list = field(default_factory=list)
    files_checked: int = 0
    
    @property
    def error_count(self):
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)
    
    @property
    def warning_count(self):
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)
    
    def add(self, issue: LintIssue):
        self.issues.append(issue)


class POParser:
    """Parse .po (gettext) files."""
    
    def __init__(self, content: str, filename: str = "<unknown>"):
        self.content = content
        self.filename = filename
        self.entries = []
        self._parse()
    
    def _parse(self):
        """Parse PO file into entries."""
        lines = self.content.split('\n')
        current_entry = {}
        current_key = None
        entry_start_line = 1
        
        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()
            
            # Empty line = end of entry
            if not line_stripped:
                if current_entry:
                    current_entry['_line'] = entry_start_line
                    self.entries.append(current_entry)
                    current_entry = {}
                    current_key = None
                continue
            
            # Comment lines
            if line_stripped.startswith('#'):
                if not current_entry:
                    entry_start_line = i
                if line_stripped.startswith('#,'):
                    # Flags (fuzzy, etc.)
                    flags = line_stripped[2:].strip().split(',')
                    current_entry['_flags'] = [f.strip() for f in flags]
                elif line_stripped.startswith('#:'):
                    # Source reference
                    current_entry['_source'] = line_stripped[2:].strip()
                continue
            
            # msgctxt, msgid, msgstr (check longer keys first to avoid prefix matching issues)
            for key in ['msgctxt', 'msgid_plural', 'msgid', 'msgstr']:
                if line_stripped.startswith(key):
                    if not current_entry:
                        entry_start_line = i
                    # Handle msgstr[N] for plurals
                    match = re.match(rf'{key}(\[\d+\])?\s+"(.*)"', line_stripped)
                    if match:
                        suffix = match.group(1) or ''
                        value = match.group(2)
                        full_key = key + suffix
                        current_entry[full_key] = self._unescape(value)
                        current_key = full_key
                    break
            else:
                # Continuation line (starts with ")
                if line_stripped.startswith('"') and current_key:
                    match = re.match(r'"(.*)"', line_stripped)
                    if match:
                        current_entry[current_key] += self._unescape(match.group(1))
        
        # Don't forget last entry
        if current_entry:
            current_entry['_line'] = entry_start_line
            self.entries.append(current_entry)
    
    def _unescape(self, s: str) -> str:
        """Unescape PO string."""
        return s.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')


class TSParser:
    """Parse Qt .ts (XML) files."""
    
    def __init__(self, content: str, filename: str = "<unknown>"):
        self.content = content
        self.filename = filename
        self.entries = []
        self._parse()
    
    def _parse(self):
        """Parse TS file into entries."""
        import xml.etree.ElementTree as ET
        
        try:
            root = ET.fromstring(self.content)
        except ET.ParseError:
            return
        
        for context in root.findall('.//context'):
            context_name = context.findtext('name', '')
            
            for message in context.findall('message'):
                entry = {
                    '_context': context_name,
                    '_line': 1,  # XML doesn't give us line numbers easily
                }
                
                source = message.find('source')
                if source is not None:
                    entry['source'] = source.text or ''
                
                translation = message.find('translation')
                if translation is not None:
                    entry['translation'] = translation.text or ''
                    entry['_type'] = translation.get('type', '')  # unfinished, vanished, etc.
                
                self.entries.append(entry)


class L10nLinter:
    """Main linter class."""
    
    # Regex patterns for placeholder detection
    PRINTF_PATTERN = re.compile(r'%[-+0 #]*\d*\.?\d*[hlL]?[diouxXeEfFgGaAcspn%]')
    PYTHON_FORMAT = re.compile(r'\{(\d+|[a-zA-Z_][a-zA-Z0-9_]*)?(?:![rsa])?(?::[^}]*)?\}')
    QT_PATTERN = re.compile(r'%\d+')
    
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.max_length = self.config.get('max_length', 500)
        self.length_ratio = self.config.get('length_ratio', 3.0)  # Translation shouldn't be 3x longer (compounds like "Förhandsgranskning")
    
    def lint_file(self, filepath: str, content: Optional[str] = None) -> LintResult:
        """Lint a single file."""
        result = LintResult()
        result.files_checked = 1
        
        if content is None:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                result.add(LintIssue(
                    file=filepath,
                    line=0,
                    severity=Severity.ERROR,
                    rule="file-read-error",
                    message=_("Could not read file: {error}").format(error=e)
                ))
                return result
        
        # Determine file type
        ext = Path(filepath).suffix.lower()
        
        if ext == '.po':
            self._lint_po(filepath, content, result)
        elif ext == '.ts':
            self._lint_ts(filepath, content, result)
        else:
            result.add(LintIssue(
                file=filepath,
                line=0,
                severity=Severity.WARNING,
                rule="unknown-format",
                message=_("Unknown file format: {ext}").format(ext=ext)
            ))
        
        return result
    
    def _lint_po(self, filepath: str, content: str, result: LintResult):
        """Lint a .po file."""
        parser = POParser(content, filepath)
        seen_msgids = {}
        
        for entry in parser.entries:
            line = entry.get('_line', 0)
            msgid = entry.get('msgid', '')
            msgid_plural = entry.get('msgid_plural', '')
            msgstr = entry.get('msgstr', '')
            flags = entry.get('_flags', [])
            
            # Skip header entry
            if not msgid:
                continue
            
            # Check: Missing translation (handle plural forms)
            if msgid_plural:
                # Plural form: check msgstr[0], msgstr[1], etc.
                has_translation = False
                for key in entry:
                    if key.startswith('msgstr[') and entry[key]:
                        has_translation = True
                        break
                if not has_translation:
                    result.add(LintIssue(
                        file=filepath,
                        line=line,
                        severity=Severity.ERROR,
                        rule="missing-translation",
                        message=_("Missing translation (empty msgstr)"),
                        context=msgid[:50]
                    ))
                # Use msgstr[0] for further checks
                msgstr = entry.get('msgstr[0]', '')
            elif not msgstr:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.ERROR,
                    rule="missing-translation",
                    message=_("Missing translation (empty msgstr)"),
                    context=msgid[:50]
                ))
            
            # Check: Fuzzy
            if 'fuzzy' in flags:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.WARNING,
                    rule="fuzzy",
                    message=_("Fuzzy translation needs review"),
                    context=msgid[:50]
                ))
            
            # Check: Placeholder mismatch
            if msgstr:
                self._check_placeholders(filepath, line, msgid, msgstr, result)
            
            # Check: Length
            if msgstr:
                self._check_length(filepath, line, msgid, msgstr, result)
            
            # Check: Duplicates
            if msgid in seen_msgids:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.WARNING,
                    rule="duplicate",
                    message=_("Duplicate msgid (first seen at line {line})").format(line=seen_msgids[msgid]),
                    context=msgid[:50]
                ))
            else:
                seen_msgids[msgid] = line
    
    def _lint_ts(self, filepath: str, content: str, result: LintResult):
        """Lint a .ts file."""
        parser = TSParser(content, filepath)
        
        for entry in parser.entries:
            line = entry.get('_line', 0)
            source = entry.get('source', '')
            translation = entry.get('translation', '')
            trans_type = entry.get('_type', '')
            
            # Check: Unfinished
            if trans_type == 'unfinished' or not translation:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.ERROR,
                    rule="missing-translation",
                    message=_("Unfinished/missing translation"),
                    context=source[:50]
                ))
            
            # Check: Vanished
            if trans_type == 'vanished':
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.INFO,
                    rule="vanished",
                    message=_("Vanished translation (source removed)"),
                    context=source[:50]
                ))
            
            # Check: Placeholders
            if translation:
                self._check_placeholders(filepath, line, source, translation, result)
            
            # Check: Length
            if translation:
                self._check_length(filepath, line, source, translation, result)
    
    def _check_placeholders(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for placeholder mismatches."""
        # Find all placeholders in source and translation
        for name, pattern in [
            ('printf', self.PRINTF_PATTERN),
            ('python-format', self.PYTHON_FORMAT),
            ('qt-format', self.QT_PATTERN),
        ]:
            source_matches = sorted(pattern.findall(source))
            trans_matches = sorted(pattern.findall(translation))
            
            if source_matches != trans_matches and source_matches:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.ERROR,
                    rule="placeholder-mismatch",
                    message=_("Placeholder mismatch ({name}): source has {source}, translation has {trans}").format(
                        name=name, source=source_matches, trans=trans_matches
                    ),
                    context=source[:50]
                ))
    
    def _check_length(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for length issues."""
        # Only warn about too-long if translation is significantly longer than source
        if len(translation) > self.max_length and len(translation) > len(source) * 1.5:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="too-long",
                message=_("Translation is very long ({length} chars, max {max})").format(
                    length=len(translation), max=self.max_length
                ),
                context=source[:50]
            ))
        
        if source and len(translation) > len(source) * self.length_ratio:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.INFO,
                rule="length-ratio",
                message=_("Translation is {ratio:.1f}x longer than source").format(
                    ratio=len(translation)/len(source)
                ),
                context=source[:50]
            ))


def find_l10n_files(path: str, recursive: bool = True) -> Generator[str, None, None]:
    """Find all .po and .ts files in path."""
    path = Path(path)
    
    if path.is_file():
        if path.suffix.lower() in ('.po', '.ts'):
            yield str(path)
        return
    
    pattern = '**/*' if recursive else '*'
    for ext in ('.po', '.ts'):
        for f in path.glob(f'{pattern}{ext}'):
            yield str(f)


def fetch_github_files(repo_url: str, path_filter: str = "") -> Generator[tuple[str, str], None, None]:
    """
    Fetch l10n files from a GitHub repository.
    
    Args:
        repo_url: GitHub URL (https://github.com/owner/repo) or owner/repo
        path_filter: Optional path filter within repo
    
    Yields:
        (filepath, content) tuples
    """
    import urllib.request
    
    # Parse repo URL
    if repo_url.startswith('https://github.com/'):
        parts = repo_url.replace('https://github.com/', '').strip('/').split('/')
    elif '/' in repo_url and not repo_url.startswith('http'):
        parts = repo_url.split('/')
    else:
        raise ValueError(f"Invalid GitHub URL: {repo_url}")
    
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub URL: {repo_url}")
    
    owner, repo = parts[0], parts[1]
    
    # Use GitHub API to get repository tree
    api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/main?recursive=1"
    
    try:
        # Try main branch
        req = urllib.request.Request(api_url, headers={'User-Agent': 'l10n-lint'})
        response = urllib.request.urlopen(req, timeout=30)
        data = json.loads(response.read().decode())
    except:
        # Try master branch
        api_url = api_url.replace('/main?', '/master?')
        req = urllib.request.Request(api_url, headers={'User-Agent': 'l10n-lint'})
        response = urllib.request.urlopen(req, timeout=30)
        data = json.loads(response.read().decode())
    
    # Find .po and .ts files
    for item in data.get('tree', []):
        filepath = item['path']
        
        if path_filter and not filepath.startswith(path_filter):
            continue
        
        if not (filepath.endswith('.po') or filepath.endswith('.ts')):
            continue
        
        # Fetch file content
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{filepath}"
        try:
            req = urllib.request.Request(raw_url, headers={'User-Agent': 'l10n-lint'})
            content_response = urllib.request.urlopen(req, timeout=30)
            content = content_response.read().decode('utf-8')
            yield (filepath, content)
        except Exception as e:
            print(_("Warning: Could not fetch {path}: {error}").format(path=filepath, error=e), file=sys.stderr)


def format_output(result: LintResult, format_type: str = "text") -> str:
    """Format lint results."""
    if format_type == "json":
        return json.dumps({
            "files_checked": result.files_checked,
            "errors": result.error_count,
            "warnings": result.warning_count,
            "issues": [i.to_dict() for i in result.issues]
        }, indent=2)
    
    elif format_type == "github":
        # GitHub Actions annotation format
        lines = []
        for issue in result.issues:
            level = "error" if issue.severity == Severity.ERROR else "warning"
            lines.append(f"::{level} file={issue.file},line={issue.line}::[{issue.rule}] {issue.message}")
        return '\n'.join(lines)
    
    else:  # text
        if not result.issues:
            return _("✅ {count} file(s) checked, no issues found.").format(count=result.files_checked)
        
        lines = []
        current_file = None
        
        for issue in sorted(result.issues, key=lambda x: (x.file, x.line)):
            if issue.file != current_file:
                current_file = issue.file
                lines.append(f"\n📁 {current_file}")
            
            icon = "❌" if issue.severity == Severity.ERROR else "⚠️" if issue.severity == Severity.WARNING else "ℹ️"
            lines.append(_("  {icon} Line {line}: [{rule}] {message}").format(
                icon=icon, line=issue.line, rule=issue.rule, message=issue.message
            ))
            if issue.context:
                lines.append(_("     Context: \"{context}...\"").format(context=issue.context))
        
        lines.append(_("\n📊 Summary: {files} file(s), {errors} error(s), {warnings} warning(s)").format(
            files=result.files_checked, errors=result.error_count, warnings=result.warning_count
        ))
        return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description=_('l10n-lint - Linter for localization files (.po, .ts)'),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_("""
Examples:
  l10n-lint ./translations/           # Lint local directory
  l10n-lint file.po                   # Lint single file
  l10n-lint --github owner/repo       # Lint GitHub repository
  l10n-lint --github https://github.com/owner/repo --path resources/language/
        """)
    )
    
    parser.add_argument('paths', nargs='*', help=_('Files or directories to lint'))
    parser.add_argument('--github', '-g', metavar='REPO', help=_('GitHub repository (owner/repo or URL)'))
    parser.add_argument('--path', '-p', metavar='PATH', default='', help=_('Path filter for GitHub repos'))
    parser.add_argument('--format', '-f', choices=['text', 'json', 'github'], default='text', help=_('Output format'))
    parser.add_argument('--max-length', type=int, default=500, help=_('Max translation length (default: 500)'))
    parser.add_argument('--no-recursive', action='store_true', help=_("Don't search subdirectories"))
    parser.add_argument('--strict', action='store_true', help=_('Treat warnings as errors'))
    parser.add_argument('-v', '--version', action='version', version=f'%(prog)s {__version__}')
    
    args = parser.parse_args()
    
    if not args.paths and not args.github:
        parser.print_help()
        sys.exit(1)
    
    linter = L10nLinter(config={
        'max_length': args.max_length,
    })
    
    result = LintResult()
    
    # Lint GitHub repo
    if args.github:
        print(_("🔍 Fetching from GitHub: {repo}").format(repo=args.github), file=sys.stderr)
        try:
            for filepath, content in fetch_github_files(args.github, args.path):
                print(_("  Checking: {path}").format(path=filepath), file=sys.stderr)
                file_result = linter.lint_file(filepath, content)
                result.files_checked += file_result.files_checked
                result.issues.extend(file_result.issues)
        except Exception as e:
            print(_("❌ GitHub error: {error}").format(error=e), file=sys.stderr)
            sys.exit(1)
    
    # Lint local files
    for path in args.paths:
        for filepath in find_l10n_files(path, recursive=not args.no_recursive):
            file_result = linter.lint_file(filepath)
            result.files_checked += file_result.files_checked
            result.issues.extend(file_result.issues)
    
    # Output
    print(format_output(result, args.format))
    
    # Exit code
    if args.strict:
        sys.exit(1 if result.issues else 0)
    else:
        sys.exit(1 if result.error_count > 0 else 0)


if __name__ == '__main__':
    main()
