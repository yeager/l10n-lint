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
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Generator, Optional
from urllib.parse import urlparse

__version__ = "1.13.0"

# Translation setup
DOMAIN = "l10n-lint"

# Look for locale in multiple places
_possible_locale_dirs = [
    Path("/usr/share/l10n-lint/locale"),  # System install (Debian)
    Path(__file__).parent / "locale",  # Development
]
LOCALE_DIR = None
for _dir in _possible_locale_dirs:
    # Check it's a real locale dir (has LC_MESSAGES subdir or .pot file)
    if _dir.is_dir() and (list(_dir.glob("*/LC_MESSAGES")) or list(_dir.glob("*.pot"))):
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
    entries_checked: int = 0
    
    @property
    def error_count(self):
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)
    
    @property
    def warning_count(self):
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)
    
    @property
    def info_count(self):
        return sum(1 for i in self.issues if i.severity == Severity.INFO)
    
    def issues_by_rule(self) -> dict:
        """Group issues by rule name."""
        by_rule = {}
        for issue in self.issues:
            by_rule[issue.rule] = by_rule.get(issue.rule, 0) + 1
        return dict(sorted(by_rule.items(), key=lambda x: -x[1]))
    
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
    
    # HTML tag pattern
    HTML_TAG_PATTERN = re.compile(r'<[^>]+>')
    
    # Keyboard accelerator patterns (&File, _File) - include unicode letters
    ACCELERATOR_PATTERN = re.compile(r'[&_](\w)', re.UNICODE)
    
    # Escaped characters
    ESCAPE_PATTERN = re.compile(r'\\[nrt\\"]')
    
    # Common English words (for untranslated detection)
    COMMON_ENGLISH = {
        # Articles and prepositions
        'the', 'a', 'an', 'and', 'or', 'of', 'to', 'in', 'on', 'at', 'by', 'for',
        'with', 'from', 'into', 'over', 'after', 'before', 'between', 'under',
        # Pronouns
        'you', 'your', 'they', 'their', 'there', 'here', 'this', 'that', 'these', 'those',
        'it', 'its', 'we', 'our', 'he', 'she', 'him', 'her', 'them',
        # Verbs (common)
        'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
        'do', 'does', 'did', 'will', 'would', 'could', 'should', 'can', 'may', 'might',
        # Question words
        'when', 'where', 'what', 'which', 'who', 'how', 'why',
        # Adjectives/Adverbs
        'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some',
        'such', 'than', 'too', 'very', 'just', 'also', 'only', 'not', 'no', 'yes',
        # Common UI words (often left untranslated by mistake)
        'click', 'button', 'file', 'open', 'save', 'close', 'new', 'edit', 'view',
        'help', 'window', 'menu', 'options', 'settings', 'please', 'continue',
        'cancel', 'ok', 'error', 'warning', 'select', 'selected', 'delete',
        'remove', 'add', 'create', 'update', 'enable', 'disable', 'loading',
        'failed', 'success', 'download', 'upload', 'search', 'find', 'copy', 'paste',
        'undo', 'redo', 'print', 'exit', 'quit', 'about', 'preferences',
    }
    
    # Swedish special characters that shouldn't be accelerators
    NORDIC_CHARS = set('åäöÅÄÖæøÆØ')
    
    # Option value pattern (--option=VALUE or --option VALUE)
    OPTION_VALUE_PATTERN = re.compile(r'--?\w+[=\s]([A-Z][A-Z0-9_]+)')
    
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.max_length = self.config.get('max_length', 500)
        self.length_ratio = self.config.get('length_ratio', 3.0)  # Translation shouldn't be 3x longer
    
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
        entries_count = 0
        
        for entry in parser.entries:
            line = entry.get('_line', 0)
            msgid = entry.get('msgid', '')
            msgid_plural = entry.get('msgid_plural', '')
            msgstr = entry.get('msgstr', '')
            flags = entry.get('_flags', [])
            
            # Skip header entry
            if not msgid:
                continue
            
            entries_count += 1
            
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
            
            # Check: Punctuation
            if msgstr:
                self._check_punctuation(filepath, line, msgid, msgstr, result)
            
            # Check: Capitalization
            if msgstr:
                self._check_capitalization(filepath, line, msgid, msgstr, result)
            
            # Check: Whitespace issues
            if msgstr:
                self._check_whitespace(filepath, line, msgid, msgstr, result)
            
            # Check: Quote consistency
            if msgstr:
                self._check_quotes(filepath, line, msgid, msgstr, result)
            
            # Check: HTML tags
            if msgstr:
                self._check_html_tags(filepath, line, msgid, msgstr, result)
            
            # Check: Escaped characters
            if msgstr:
                self._check_escapes(filepath, line, msgid, msgstr, result)
            
            # Check: Keyboard accelerators
            if msgstr:
                self._check_accelerators(filepath, line, msgid, msgstr, result)
            
            # Check: Numeric values
            if msgstr:
                self._check_numerics(filepath, line, msgid, msgstr, result)
            
            # Check: Untranslated English words
            if msgstr:
                self._check_untranslated(filepath, line, msgid, msgstr, result)
            
            # Check: Repeated words
            if msgstr:
                self._check_repeated_words(filepath, line, msgid, msgstr, result)
            
            # Check: Source equals translation
            if msgstr:
                self._check_source_equals_translation(filepath, line, msgid, msgstr, result)
            
            # Check: Option value consistency
            if msgstr:
                self._check_option_values(filepath, line, msgid, msgstr, result)
            
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
        
        result.entries_checked += entries_count
    
    def _lint_ts(self, filepath: str, content: str, result: LintResult):
        """Lint a .ts file."""
        parser = TSParser(content, filepath)
        entries_count = 0
        
        for entry in parser.entries:
            entries_count += 1
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
        
        result.entries_checked += entries_count
    
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
        
        # Check for suspiciously short translation
        if source and len(source) > 10 and len(translation) < len(source) * 0.2:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="suspicious-length",
                message=_("Translation is suspiciously short ({ratio:.1f}x of source)").format(
                    ratio=len(translation)/len(source)
                ),
                context=source[:50]
            ))
    
    def _check_punctuation(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for punctuation mismatches."""
        if not source or not translation:
            return
        
        # Check ending punctuation
        end_punct = '.!?:;'
        source_end = source.rstrip()[-1] if source.rstrip() else ''
        trans_end = translation.rstrip()[-1] if translation.rstrip() else ''
        
        if source_end in end_punct and trans_end not in end_punct:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="inconsistent-punctuation",
                message=_("Missing ending punctuation (source ends with '{char}')").format(char=source_end),
                context=source[:50]
            ))
        elif source_end not in end_punct and trans_end in end_punct:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.INFO,
                rule="inconsistent-punctuation",
                message=_("Extra ending punctuation (source has none)"),
                context=source[:50]
            ))
    
    def _check_capitalization(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for capitalization mismatches."""
        if not source or not translation:
            return
        
        # Get first letter of each
        source_first = next((c for c in source if c.isalpha()), None)
        trans_first = next((c for c in translation if c.isalpha()), None)
        
        if source_first and trans_first:
            if source_first.isupper() and trans_first.islower():
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.WARNING,
                    rule="inconsistent-capitalization",
                    message=_("Source starts with uppercase, translation with lowercase"),
                    context=source[:50]
                ))
    
    def _check_whitespace(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for whitespace issues."""
        # Trailing whitespace
        if translation != translation.rstrip():
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="trailing-whitespace",
                message=_("Translation has trailing whitespace"),
                context=source[:50]
            ))
        
        # Double spaces (but not at line breaks)
        if '  ' in translation.replace('\n ', '\n'):
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.INFO,
                rule="double-spaces",
                message=_("Translation contains double spaces"),
                context=source[:50]
            ))
    
    def _check_quotes(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for quote consistency."""
        # Detect mixed quote styles
        straight_quotes = translation.count('"') + translation.count("'")
        curly_quotes = translation.count('"') + translation.count('"') + translation.count(''') + translation.count(''')
        german_quotes = translation.count('„') + translation.count('"')
        
        quote_styles = sum(1 for c in [straight_quotes, curly_quotes, german_quotes] if c > 0)
        if quote_styles > 1:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.INFO,
                rule="mixed-quotes",
                message=_("Translation has mixed quote styles"),
                context=source[:50]
            ))
    
    def _check_html_tags(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for HTML tag mismatches."""
        source_tags = sorted(self.HTML_TAG_PATTERN.findall(source))
        trans_tags = sorted(self.HTML_TAG_PATTERN.findall(translation))
        
        if source_tags != trans_tags and source_tags:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.ERROR,
                rule="html-tag-mismatch",
                message=_("HTML tags mismatch: source has {source}, translation has {trans}").format(
                    source=source_tags, trans=trans_tags
                ),
                context=source[:50]
            ))
    
    def _check_escapes(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for escaped character mismatches (newlines, tabs, etc.)."""
        # Count actual escape characters (after unescape has been applied)
        escape_chars = {'\n': '\\n', '\t': '\\t', '\r': '\\r'}
        
        source_counts = {char: source.count(char) for char in escape_chars}
        trans_counts = {char: translation.count(char) for char in escape_chars}
        
        # Find mismatches
        mismatches = []
        for char, name in escape_chars.items():
            src_count = source_counts[char]
            trans_count = trans_counts[char]
            if src_count != trans_count and src_count > 0:
                mismatches.append(f"{name}: {src_count}→{trans_count}")
        
        if mismatches:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.ERROR,
                rule="escaped-chars-mismatch",
                message=_("Escape character count mismatch: {details}").format(
                    details=", ".join(mismatches)
                ),
                context=source[:50].replace('\n', '\\n')
            ))
    
    def _check_accelerators(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check keyboard accelerator consistency."""
        source_accels = self.ACCELERATOR_PATTERN.findall(source)
        trans_accels = self.ACCELERATOR_PATTERN.findall(translation)
        
        # Check if accelerator exists in source but not translation
        if source_accels and not trans_accels:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="keyboard-shortcut-missing",
                message=_("Keyboard accelerator missing in translation"),
                context=source[:50]
            ))
        
        # Check for Nordic chars as accelerators
        for accel in trans_accels:
            if accel in self.NORDIC_CHARS:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.ERROR,
                    rule="nordic-accelerator",
                    message=_("Nordic character '{char}' used as keyboard accelerator").format(char=accel),
                    context=source[:50]
                ))
    
    def _check_numerics(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check that numbers in source appear in translation."""
        # Find all numbers in source
        source_nums = set(re.findall(r'\b\d+(?:\.\d+)?\b', source))
        trans_nums = set(re.findall(r'\b\d+(?:\.\d+)?\b', translation))
        
        # Numbers in source but not in translation
        missing = source_nums - trans_nums
        if missing and len(source_nums) <= 3:  # Only warn for few numbers
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="numeric-mismatch",
                message=_("Numbers {nums} from source missing in translation").format(nums=missing),
                context=source[:50]
            ))
    
    def _check_untranslated(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for common English words left in translation."""
        # Only check if source looks English
        if not any(w in source.lower() for w in ['the', 'and', 'is', 'are']):
            return
        
        trans_words = set(re.findall(r'\b[a-zA-Z]+\b', translation.lower()))
        found_english = trans_words & self.COMMON_ENGLISH
        
        # Remove words that also appear in source (might be intentional)
        source_words = set(re.findall(r'\b[a-zA-Z]+\b', source.lower()))
        suspicious = found_english - source_words
        
        # Also check if translation contains source words
        if len(suspicious) >= 3:  # Only warn if multiple common words
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="untranslated-words",
                message=_("Translation may contain untranslated English: {words}").format(
                    words=list(suspicious)[:5]
                ),
                context=source[:50]
            ))
    
    def _check_repeated_words(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for repeated words."""
        words = re.findall(r'\b(\w+)\s+\1\b', translation, re.IGNORECASE)
        if words:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="repeated-words",
                message=_("Repeated word: '{word}'").format(word=words[0]),
                context=source[:50]
            ))
    
    def _check_source_equals_translation(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check if translation is identical to source."""
        # Skip short strings and strings with only special chars/numbers
        if len(source) < 5 or not any(c.isalpha() for c in source):
            return
        
        if source == translation:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.INFO,
                rule="source-equals-translation",
                message=_("Translation is identical to source (possibly untranslated)"),
                context=source[:50]
            ))
    
    def _check_option_values(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for inconsistent option value placeholders."""
        # Find option values like --option=VALUE or --option VALUE
        source_values = set(self.OPTION_VALUE_PATTERN.findall(source))
        
        if not source_values:
            return
        
        # Check if these values appear in translation
        for value in source_values:
            # Value should either be kept as-is or translated consistently
            # Check if the value is missing entirely (not even translated)
            value_lower = value.lower()
            trans_lower = translation.lower()
            
            # Look for the value in translation (case-insensitive)
            if value not in translation and value_lower not in trans_lower:
                # Check if there's a similar uppercase word that might be the translation
                trans_upper_words = re.findall(r'\b[A-ZÅÄÖ][A-ZÅÄÖ0-9_]+\b', translation)
                if not trans_upper_words:
                    result.add(LintIssue(
                        file=filepath,
                        line=line,
                        severity=Severity.WARNING,
                        rule="option-value-missing",
                        message=_("Option value '{value}' from source not found in translation").format(value=value),
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


def fetch_url_file(url: str) -> tuple[str, str]:
    """
    Fetch a single l10n file from a URL.
    
    Args:
        url: HTTP(S) URL to a .po or .ts file
    
    Returns:
        (filename, content) tuple
    """
    import urllib.request
    
    # Validate URL
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(_("Invalid URL scheme: {scheme}").format(scheme=parsed.scheme))
    
    # Get filename from URL
    filename = Path(parsed.path).name or "remote.po"
    
    # Validate file extension
    ext = Path(filename).suffix.lower()
    if ext not in ('.po', '.ts'):
        raise ValueError(_("URL must point to a .po or .ts file, got: {ext}").format(ext=ext))
    
    # Fetch content
    req = urllib.request.Request(url, headers={
        'User-Agent': f'l10n-lint/{__version__}',
        'Accept': 'text/plain, application/octet-stream, */*',
    })
    
    response = urllib.request.urlopen(req, timeout=30)
    content = response.read().decode('utf-8')
    
    return (filename, content)


def is_url(path: str) -> bool:
    """Check if a path is an HTTP(S) URL."""
    return path.startswith('http://') or path.startswith('https://')


def generate_html_report(result: LintResult, title: str = "l10n-lint Report") -> str:
    """Generate a detailed HTML report."""
    # Count issues by rule
    rule_counts = {}
    for issue in result.issues:
        rule_counts[issue.rule] = rule_counts.get(issue.rule, 0) + 1
    
    # Count issues by file
    file_counts = {}
    for issue in result.issues:
        file_counts[issue.file] = file_counts.get(issue.file, 0) + 1
    
    # Count by severity
    errors = result.error_count
    warnings = result.warning_count
    info = sum(1 for i in result.issues if i.severity == Severity.INFO)
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        :root {{
            --bg: #1a1a2e;
            --card: #16213e;
            --text: #eee;
            --error: #e74c3c;
            --warning: #f39c12;
            --info: #3498db;
            --success: #2ecc71;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: var(--text); border-bottom: 2px solid var(--info); padding-bottom: 10px; }}
        h2 {{ color: var(--info); margin-top: 30px; }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .stat {{
            background: var(--card);
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }}
        .stat-value {{ font-size: 2em; font-weight: bold; }}
        .stat-label {{ opacity: 0.8; font-size: 0.9em; }}
        .stat.error .stat-value {{ color: var(--error); }}
        .stat.warning .stat-value {{ color: var(--warning); }}
        .stat.info .stat-value {{ color: var(--info); }}
        .stat.success .stat-value {{ color: var(--success); }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            background: var(--card);
            border-radius: 10px;
            overflow: hidden;
        }}
        th, td {{ padding: 12px 15px; text-align: left; }}
        th {{ background: rgba(52, 152, 219, 0.2); }}
        tr:nth-child(even) {{ background: rgba(255,255,255,0.05); }}
        .severity-error {{ color: var(--error); }}
        .severity-warning {{ color: var(--warning); }}
        .severity-info {{ color: var(--info); }}
        .issue-context {{
            font-family: monospace;
            background: rgba(0,0,0,0.3);
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 0.9em;
        }}
        .chart {{ margin: 20px 0; }}
        .bar {{
            height: 25px;
            margin: 5px 0;
            border-radius: 5px;
            display: flex;
            align-items: center;
            padding: 0 10px;
            font-size: 0.9em;
        }}
        .bar-error {{ background: var(--error); }}
        .bar-warning {{ background: var(--warning); }}
        .bar-info {{ background: var(--info); }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 {title}</h1>
        <p>Generated: {time.strftime("%Y-%m-%d %H:%M")}</p>
        
        <div class="summary">
            <div class="stat success">
                <div class="stat-value">{result.files_checked}</div>
                <div class="stat-label">Files checked</div>
            </div>
            <div class="stat error">
                <div class="stat-value">{errors}</div>
                <div class="stat-label">Errors</div>
            </div>
            <div class="stat warning">
                <div class="stat-value">{warnings}</div>
                <div class="stat-label">Warnings</div>
            </div>
            <div class="stat info">
                <div class="stat-value">{info}</div>
                <div class="stat-label">Info</div>
            </div>
        </div>
'''
    
    # Issues by rule
    if rule_counts:
        html += '''
        <h2>📊 Issues by Rule</h2>
        <table>
            <tr><th>Rule</th><th>Count</th><th>%</th></tr>
'''
        total = len(result.issues)
        for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
            pct = (count / total * 100) if total > 0 else 0
            html += f'            <tr><td>{rule}</td><td>{count}</td><td>{pct:.1f}%</td></tr>\n'
        html += '        </table>\n'
    
    # Issues by file
    if file_counts:
        html += '''
        <h2>📁 Issues by File</h2>
        <table>
            <tr><th>File</th><th>Issues</th></tr>
'''
        for filepath, count in sorted(file_counts.items(), key=lambda x: -x[1])[:20]:
            html += f'            <tr><td>{filepath}</td><td>{count}</td></tr>\n'
        html += '        </table>\n'
    
    # All issues
    if result.issues:
        html += '''
        <h2>📋 All Issues</h2>
        <table>
            <tr><th>File</th><th>Line</th><th>Severity</th><th>Rule</th><th>Message</th></tr>
'''
        for issue in sorted(result.issues, key=lambda x: (x.file, x.line)):
            sev_class = f"severity-{issue.severity.value}"
            sev_icon = "❌" if issue.severity == Severity.ERROR else "⚠️" if issue.severity == Severity.WARNING else "ℹ️"
            ctx = f'<br><span class="issue-context">{issue.context}...</span>' if issue.context else ''
            html += f'''            <tr>
                <td>{issue.file}</td>
                <td>{issue.line}</td>
                <td class="{sev_class}">{sev_icon} {issue.severity.value}</td>
                <td>{issue.rule}</td>
                <td>{issue.message}{ctx}</td>
            </tr>
'''
        html += '        </table>\n'
    else:
        html += '<p style="color: var(--success); font-size: 1.2em;">✅ No issues found!</p>\n'
    
    html += '''
    </div>
</body>
</html>'''
    
    return html


def format_output(result: LintResult, format_type: str = "text") -> str:
    """Format lint results."""
    if format_type == "json":
        return json.dumps({
            "files_checked": result.files_checked,
            "errors": result.error_count,
            "warnings": result.warning_count,
            "issues": [i.to_dict() for i in result.issues]
        }, indent=2)
    
    elif format_type == "html":
        return generate_html_report(result)
    
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


class TranslatedHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom formatter that translates argparse default strings."""
    
    def start_section(self, heading):
        # Translate section headings
        translations = {
            'positional arguments': _('positional arguments'),
            'options': _('options'),
            'optional arguments': _('options'),
        }
        heading = translations.get(heading, heading)
        super().start_section(heading)


def main():
    parser = argparse.ArgumentParser(
        description=_('l10n-lint - Linter for localization files (.po, .ts)'),
        formatter_class=TranslatedHelpFormatter,
        add_help=False,
        epilog=_("""
Examples:
  l10n-lint ./translations/           # Lint local directory
  l10n-lint file.po                   # Lint single file
  l10n-lint https://example.com/sv.po # Lint file from URL
  l10n-lint --github owner/repo       # Lint GitHub repository
  l10n-lint -f html -o report.html .  # Generate HTML report
  l10n-lint -f json -o results.json . # Generate JSON report
        """)
    )
    
    parser.add_argument('paths', nargs='*', help=_('Files or directories to lint'))
    parser.add_argument('--github', '-g', metavar='REPO', help=_('GitHub repository (owner/repo or URL)'))
    parser.add_argument('--path', '-p', metavar='PATH', default='', help=_('Path filter for GitHub repos'))
    parser.add_argument('--format', '-f', choices=['text', 'json', 'html', 'github'], default='text', help=_('Output format'))
    parser.add_argument('--output', '-o', metavar='FILE', help=_('Save report to file'))
    parser.add_argument('--max-length', type=int, default=500, help=_('Max translation length (default: 500)'))
    parser.add_argument('--no-recursive', action='store_true', help=_("Don't search subdirectories"))
    parser.add_argument('--strict', action='store_true', help=_('Treat warnings as errors'))
    parser.add_argument('--quiet', '-q', action='store_true', help=_('Show only summary'))
    parser.add_argument('--check', action='store_true', help=_('Exit code only, no output (for CI)'))
    parser.add_argument('--skip-fuzzy', action='store_true', help=_('Ignore fuzzy warnings'))
    parser.add_argument('--verbose', '-V', action='store_true', help=_('Show detailed progress'))
    parser.add_argument('--gtk', '-G', action='store_true', help=_('Launch GTK graphical interface'))
    parser.add_argument('-h', '--help', action='help', help=_('Show this help message and exit'))
    parser.add_argument('-v', '--version', action='version', version=f'%(prog)s {__version__}',
                        help=_('Show version number and exit'))
    
    args = parser.parse_args()
    
    # Launch GTK interface if requested
    if args.gtk:
        try:
            # Try to import and run GTK interface
            gtk_script = Path(__file__).parent / "l10n_lint_gtk.py"
            if gtk_script.exists():
                import subprocess
                cmd = [sys.executable, str(gtk_script)]
                if args.paths:
                    cmd.extend(args.paths)
                sys.exit(subprocess.call(cmd))
            else:
                # Try system-installed version
                import shutil
                gtk_cmd = shutil.which("l10n-lint-gtk")
                if gtk_cmd:
                    import subprocess
                    cmd = [gtk_cmd]
                    if args.paths:
                        cmd.extend(args.paths)
                    sys.exit(subprocess.call(cmd))
                else:
                    print(_("Error: GTK interface not found. Install l10n-lint-gtk or run from source directory."), file=sys.stderr)
                    sys.exit(1)
        except Exception as e:
            print(_("Error launching GTK interface: {error}").format(error=e), file=sys.stderr)
            sys.exit(1)
    
    if not args.paths and not args.github:
        parser.print_help()
        sys.exit(1)
    
    verbose = args.verbose
    start_time = time.time()
    
    def vprint(msg):
        """Print if verbose mode is enabled."""
        if verbose:
            print(msg, file=sys.stderr)
    
    def vprint_elapsed():
        """Print elapsed time."""
        elapsed = time.time() - start_time
        vprint(_("⏱️  Elapsed time: {elapsed:.2f}s").format(elapsed=elapsed))
    
    vprint(_("🔧 l10n-lint {version} starting...").format(version=__version__))
    vprint(_("   Max length: {max}").format(max=args.max_length))
    vprint(_("   Length ratio: {ratio}x").format(ratio=3.0))
    vprint(_("   Strict mode: {strict}").format(strict=args.strict))
    vprint(_("   Output format: {fmt}").format(fmt=args.format))
    vprint(_("   Recursive: {rec}").format(rec=not args.no_recursive))
    if LOCALE_DIR:
        vprint(_("   Locale dir: {dir}").format(dir=LOCALE_DIR))
        vprint(_("   Language: {lang}").format(lang=_lang_code))
    else:
        vprint(_("   Locale: not found (using English)"))
    vprint("")
    
    linter = L10nLinter(config={
        'max_length': args.max_length,
    })
    
    result = LintResult()
    
    # Lint GitHub repo
    if args.github:
        vprint(_("🌐 GitHub mode"))
        print(_("🔍 Fetching from GitHub: {repo}").format(repo=args.github), file=sys.stderr)
        if args.path:
            vprint(_("   Path filter: {path}").format(path=args.path))
        try:
            fetch_start = time.time()
            vprint(_("   Connecting to GitHub API..."))
            files_found = 0
            for filepath, content in fetch_github_files(args.github, args.path):
                files_found += 1
                file_start = time.time()
                vprint(_("  [{n}] {path}").format(n=files_found, path=filepath))
                vprint(_("       Size: {size} bytes").format(size=len(content)))
                file_result = linter.lint_file(filepath, content)
                file_elapsed = time.time() - file_start
                result.files_checked += file_result.files_checked
                result.entries_checked += file_result.entries_checked
                result.issues.extend(file_result.issues)
                vprint(_("       Entries: {count}").format(count=file_result.entries_checked))
                vprint(_("       Parsed in {elapsed:.3f}s").format(elapsed=file_elapsed))
                if file_result.issues:
                    vprint(_("       ⚠️  Found {count} issue(s)").format(count=len(file_result.issues)))
                else:
                    vprint(_("       ✓ No issues"))
            fetch_elapsed = time.time() - fetch_start
            vprint(_("   Fetched {count} file(s) in {elapsed:.2f}s").format(
                count=files_found, elapsed=fetch_elapsed))
        except Exception as e:
            print(_("❌ GitHub error: {error}").format(error=e), file=sys.stderr)
            sys.exit(1)
    
    # Lint local files and URLs
    if args.paths:
        # Separate URLs from local paths
        url_paths = [p for p in args.paths if is_url(p)]
        local_paths = [p for p in args.paths if not is_url(p)]
        
        # Process URLs
        if url_paths:
            vprint(_("🌐 URL mode"))
            url_files = 0
            for url in url_paths:
                url_files += 1
                file_start = time.time()
                vprint(_("  [{n}] {url}").format(n=url_files, url=url))
                try:
                    filename, content = fetch_url_file(url)
                    fetch_elapsed = time.time() - file_start
                    vprint(_("       Fetched: {name} ({size} bytes) in {elapsed:.3f}s").format(
                        name=filename, size=len(content), elapsed=fetch_elapsed))
                    
                    lint_start = time.time()
                    file_result = linter.lint_file(filename, content)
                    lint_elapsed = time.time() - lint_start
                    result.files_checked += file_result.files_checked
                    result.entries_checked += file_result.entries_checked
                    result.issues.extend(file_result.issues)
                    vprint(_("       Entries: {count}").format(count=file_result.entries_checked))
                    vprint(_("       Parsed in {elapsed:.3f}s").format(elapsed=lint_elapsed))
                    if file_result.issues:
                        vprint(_("       ⚠️  Found {count} issue(s)").format(count=len(file_result.issues)))
                    else:
                        vprint(_("       ✓ No issues"))
                except Exception as e:
                    print(_("❌ URL error for {url}: {error}").format(url=url, error=e), file=sys.stderr)
                    result.add(LintIssue(
                        file=url,
                        line=0,
                        severity=Severity.ERROR,
                        rule="url-fetch-error",
                        message=_("Could not fetch URL: {error}").format(error=e)
                    ))
                    result.files_checked += 1
            
            vprint(_("   Total URL files: {count}").format(count=url_files))
        
        # Process local paths
        if local_paths:
            vprint(_("📁 Local mode"))
            local_files = 0
            for path in local_paths:
                vprint(_("📂 Scanning: {path}").format(path=path))
                scan_start = time.time()
                path_files = list(find_l10n_files(path, recursive=not args.no_recursive))
                scan_elapsed = time.time() - scan_start
                vprint(_("   Found {count} file(s) in {elapsed:.3f}s").format(
                    count=len(path_files), elapsed=scan_elapsed))
                
                for filepath in path_files:
                    local_files += 1
                    file_start = time.time()
                    file_size = Path(filepath).stat().st_size
                    vprint(_("  [{n}] {path}").format(n=local_files, path=filepath))
                    vprint(_("       Size: {size} bytes").format(size=file_size))
                    file_result = linter.lint_file(filepath)
                    file_elapsed = time.time() - file_start
                    result.files_checked += file_result.files_checked
                    result.entries_checked += file_result.entries_checked
                    result.issues.extend(file_result.issues)
                    vprint(_("       Entries: {count}").format(count=file_result.entries_checked))
                    vprint(_("       Parsed in {elapsed:.3f}s").format(elapsed=file_elapsed))
                    if file_result.issues:
                        vprint(_("       ⚠️  Found {count} issue(s)").format(count=len(file_result.issues)))
                    else:
                        vprint(_("       ✓ No issues"))
            
            vprint(_("   Total local files: {count}").format(count=local_files))
    
    # Filter out fuzzy if requested
    if args.skip_fuzzy:
        result.issues = [i for i in result.issues if i.rule != 'fuzzy']
    
    # Verbose summary
    elapsed = time.time() - start_time
    vprint("")
    vprint(_("📊 Summary:"))
    vprint(_("   Files checked: {count}").format(count=result.files_checked))
    vprint(_("   Entries checked: {count}").format(count=result.entries_checked))
    vprint(_("   Errors: {count}").format(count=result.error_count))
    vprint(_("   Warnings: {count}").format(count=result.warning_count))
    vprint(_("   Info: {count}").format(count=result.info_count))
    
    # Issue breakdown by rule
    issues_by_rule = result.issues_by_rule()
    if issues_by_rule:
        vprint(_("   Issues by rule:"))
        for rule, count in list(issues_by_rule.items())[:10]:
            vprint(_("     - {rule}: {count}").format(rule=rule, count=count))
        if len(issues_by_rule) > 10:
            vprint(_("     ... and {more} more rules").format(more=len(issues_by_rule) - 10))
    
    # Processing speed
    if elapsed > 0:
        files_per_sec = result.files_checked / elapsed
        entries_per_sec = result.entries_checked / elapsed if result.entries_checked > 0 else 0
        vprint(_("   Processing speed:"))
        vprint(_("     - {speed:.1f} files/sec").format(speed=files_per_sec))
        if entries_per_sec > 0:
            vprint(_("     - {speed:.1f} entries/sec").format(speed=entries_per_sec))
    
    vprint_elapsed()
    vprint("")
    
    # Output (unless --check mode)
    if not args.check:
        if args.quiet:
            # Just summary line
            print(_("📊 {files} file(s), {errors} error(s), {warnings} warning(s)").format(
                files=result.files_checked, errors=result.error_count, warnings=result.warning_count))
        else:
            output = format_output(result, args.format)
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(output)
                print(_("📄 Report saved to: {file}").format(file=args.output))
            else:
                print(output)
    
    # Exit code
    if args.strict:
        sys.exit(1 if result.issues else 0)
    else:
        sys.exit(1 if result.error_count > 0 else 0)


if __name__ == '__main__':
    main()
