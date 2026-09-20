#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# l10n-lint - Linter for localization files
# Copyright (C) 2026 Daniel Nylander <daniel@danielnylander.se>
"""
l10n-lint - Linter for localization files (.po, .ts, .xlf/.xliff, .json)

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

# Keep shared data classes identical when invoked as a script.
if __name__ == '__main__':
    sys.modules.setdefault('l10n_lint', sys.modules[__name__])

__version__ = "1.21.4"
L10N_EXTENSIONS = frozenset({'.po', '.ts', '.xlf', '.xliff', '.json', '.rc', '.properties', '.xml'})

# Translation setup
DOMAIN = "l10n-lint"

# Look for locale in multiple places
_possible_locale_dirs = [
    Path(__file__).parent / "locale",  # Development / pip install -e
    Path("/usr/share/l10n-lint/locale"),  # System install (Debian)
    Path("/usr/share/locale"),  # Standard system locale (RPM/Fedora)
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
    disabled_rules: set = field(default_factory=set)
    severity_overrides: dict = field(default_factory=dict)
    
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
        if issue.rule in self.disabled_rules and issue.rule not in OPERATIONAL_RULES:
            return
        if issue.rule not in OPERATIONAL_RULES and issue.rule in self.severity_overrides:
            issue.severity = Severity(self.severity_overrides[issue.rule])
        self.issues.append(issue)




@dataclass(frozen=True)
class RuleSpec:
    method: str
    severity: str
    language: str = ""
    description: str = ""
    default: bool = True


RULES = {
    'placeholder-mismatch': RuleSpec('_check_placeholders', 'error', '', 'Placeholder mismatch'),
    'too-long': RuleSpec('_check_length', 'warning', '', 'Too long'),
    'length-ratio': RuleSpec('_check_length', 'info', '', 'Length ratio'),
    'suspicious-length': RuleSpec('_check_length', 'warning', '', 'Suspicious length'),
    'inconsistent-punctuation': RuleSpec('_check_punctuation', 'info', '', 'Inconsistent punctuation'),
    'inconsistent-capitalization': RuleSpec('_check_capitalization', 'warning', '', 'Inconsistent capitalization'),
    'trailing-whitespace': RuleSpec('_check_whitespace', 'warning', '', 'Trailing whitespace'),
    'missing-trailing-space': RuleSpec('_check_whitespace', 'warning', '', 'Missing trailing space'),
    'missing-leading-space': RuleSpec('_check_whitespace', 'warning', '', 'Missing leading space'),
    'double-spaces': RuleSpec('_check_whitespace', 'info', '', 'Double spaces'),
    'mixed-quotes': RuleSpec('_check_quotes', 'info', '', 'Mixed quotes'),
    'html-tag-mismatch': RuleSpec('_check_html_tags', 'error', '', 'Html tag mismatch'),
    'escaped-chars-mismatch': RuleSpec('_check_escapes', 'error', '', 'Escaped chars mismatch'),
    'keyboard-shortcut-missing': RuleSpec('_check_accelerators', 'warning', '', 'Keyboard shortcut missing'),
    'nordic-accelerator': RuleSpec('_check_accelerators', 'error', '', 'Nordic accelerator'),
    'numeric-mismatch': RuleSpec('_check_numerics', 'info', '', 'Numeric mismatch'),
    'untranslated-words': RuleSpec('_check_untranslated', 'warning', '', 'Untranslated words'),
    'repeated-words': RuleSpec('_check_repeated_words', 'warning', '', 'Repeated words'),
    'cross-newline-duplicate': RuleSpec('_check_cross_newline_duplicates', 'warning', '', 'Cross newline duplicate'),
    'source-equals-translation': RuleSpec('_check_source_equals_translation', 'warning', '', 'Source equals translation'),
    'option-value-missing': RuleSpec('_check_option_values', 'warning', '', 'Option value missing'),
    'number-localization': RuleSpec('_check_number_localization', 'info', 'sv', 'Number localization'),
    'decimal-separator': RuleSpec('_check_decimal_separator', 'warning', 'sv', 'Decimal separator'),
    'currency-localization': RuleSpec('_check_currency_localization', 'info', 'sv', 'Currency localization'),
    'date-format': RuleSpec('_check_date_format', 'warning', 'sv', 'Date format'),
    'newline-mismatch': RuleSpec('_check_newline_mismatch', 'warning', '', 'Newline mismatch'),
    'python-format': RuleSpec('_check_placeholders', 'error', '', 'Python format'),
    'terminology': RuleSpec('_check_terminology', 'warning', 'sv', 'Terminology'),
    'domain-terminology': RuleSpec('_check_domain_terminology', 'warning', 'sv', 'Domain terminology'),
    'false-friends': RuleSpec('_check_false_friends', 'warning', 'sv', 'False friends'),
    'consistency': RuleSpec('_check_consistency', 'info', '', 'Consistency'),
    'typo': RuleSpec('_check_typos', 'warning', 'sv', 'Typo'),
    'plural-header-missing': RuleSpec('_check_plural_forms', 'error', '', 'Plural header missing'),
    'plural-header-wrong': RuleSpec('_check_plural_forms', 'error', '', 'Plural header wrong'),
    'plural-forms-missing': RuleSpec('_check_plural_forms', 'error', '', 'Plural forms missing'),
    'plural-form-empty': RuleSpec('_check_plural_forms', 'error', '', 'Plural form empty'),
    'plural-formula-suspicious': RuleSpec('_check_plural_forms', 'warning', '', 'Plural formula suspicious'),
    'plural-forms-extra': RuleSpec('_check_plural_forms', 'warning', '', 'Plural forms extra'),
    'zero-width-space': RuleSpec('_check_zero_width_space', 'warning', '', 'Zero width space'),
    'end-stop-mismatch': RuleSpec('_check_end_stop_mismatch', 'warning', '', 'End stop mismatch'),
    'ellipsis': RuleSpec('_check_ellipsis', 'info', '', 'Ellipsis'),
    'xml-tags-mismatch': RuleSpec('_check_xml_tags_mismatch', 'warning', '', 'Xml tags mismatch'),
    'duplicate-words': RuleSpec('_check_duplicate_words', 'warning', '', 'Duplicate words'),
    'same-plurals': RuleSpec('_check_same_plurals', 'warning', '', 'Same plurals'),
    'punctuation-mismatch': RuleSpec('_check_punctuation_mismatch', 'warning', '', 'Punctuation mismatch'),
    'url-preservation': RuleSpec('_check_url_preservation', 'warning', '', 'Url preservation'),
    'escaped-newline-count': RuleSpec('_check_escaped_newline_count', 'warning', '', 'Escaped newline count'),
    'max-length-ratio': RuleSpec('_check_max_length_ratio', 'warning', '', 'Max length ratio'),
    'bidi-control': RuleSpec('_check_unicode_integrity', 'warning', '', 'Bidirectional control character'),
    'unicode-normalization': RuleSpec('_check_unicode_integrity', 'warning', '', 'Unicode normalization'),
    'required-term-missing': RuleSpec('_check_project_terms', 'error', '', 'Required term missing'),
    'forbidden-term': RuleSpec('_check_project_terms', 'warning', '', 'Forbidden term'),
    'cldr-plural-missing': RuleSpec('', 'error', '', 'CLDR plural form missing'),
    'missing-translation': RuleSpec('', 'error', '', 'Missing translation'),
    'fuzzy': RuleSpec('', 'warning', '', 'Fuzzy'),
    'duplicate': RuleSpec('', 'warning', '', 'Duplicate'),
    'vanished': RuleSpec('', 'info', '', 'Vanished'),
    'glossary': RuleSpec('', 'warning', '', 'Glossary'),
    'catalog-missing': RuleSpec('', 'error', '', 'Catalog missing'),
    'catalog-obsolete': RuleSpec('', 'warning', '', 'Catalog obsolete'),
    'catalog-plural-changed': RuleSpec('', 'error', '', 'Catalog plural changed'),
}
# Failures to inspect input cannot be hidden by rule selection or baselines.
OPERATIONAL_RULES = {"syntax-error", "file-read-error", "path-error", "no-files",
                     "url-fetch-error", "github-fetch-error", "reference-error", "unknown-format"}
RULE_ALIASES = {}
for _rule_id, _spec in RULES.items():
    if _spec.method:
        RULE_ALIASES.setdefault(_spec.method.removeprefix("_check_").replace("_", "-"), set()).add(_rule_id)
RULE_ALIASES["placeholder"] = RULE_ALIASES["placeholders"]
RULE_ALIASES["plural-placeholder-mismatch"] = {"placeholder-mismatch"}
RULE_ALIASES["plural-forms"].add("same-plurals")


def resolve_rules(names):
    if isinstance(names, str):
        names = names.split(",")
    resolved = set()
    for name in names:
        name = name.strip()
        if name in RULE_ALIASES:
            resolved.update(RULE_ALIASES[name])
        elif name in RULES:
            resolved.add(name)
        elif name:
            raise ValueError(f"Unknown rule: {name}")
    return resolved


class POParser:
    """Parse .po (gettext) files."""
    
    def __init__(self, content: str, filename: str = "<unknown>"):
        self.content = content
        self.filename = filename
        self.entries = []
        self._parse()
    
    def _parse(self):
        """Parse PO directives strictly, preserving physical spans for edits."""
        current, key = {}, None
        token = re.compile(r'(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+("(?:[^"\\]|\\.)*")\s*\Z')
        quoted = re.compile(r'"(?:[^"\\]|\\.)*"\s*\Z')

        def finish():
            nonlocal current, key
            if 'msgid' in current:
                plural = 'msgid_plural' in current
                translations = [k for k in current if k.startswith('msgstr')]
                if not translations or (plural and 'msgstr' in current) or (not plural and 'msgstr' not in current):
                    raise ValueError(f"Line {current['_line']}: invalid or missing msgstr directive")
                self.entries.append(current)
            elif any(not k.startswith('_') for k in current):
                raise ValueError(f"Line {current['_line']}: missing msgid")
            current, key = {}, None

        for number, raw in enumerate(self.content.lstrip('\ufeff').splitlines(), 1):
            line = raw.strip()
            if not line:
                finish()
                continue
            if line.startswith('#'):
                if any(k.startswith('msgstr') for k in current):
                    finish()
                if line.startswith('#,'):
                    current.setdefault('_flags', []).extend(f.strip() for f in line[2:].split(','))
                continue
            match = token.fullmatch(line)
            if match:
                name, value = match.groups()
                if name in ('msgctxt', 'msgid') and 'msgid' in current:
                    finish()
                if name in current:
                    raise ValueError(f"Line {number}: duplicate {name}")
                if name == 'msgid_plural' and ('msgid' not in current or any(k.startswith('msgstr') for k in current)):
                    raise ValueError(f"Line {number}: misplaced msgid_plural")
                if name.startswith('msgstr') and 'msgid' not in current:
                    raise ValueError(f"Line {number}: msgstr before msgid")
                current.setdefault('_line', number)
                current[name] = self._unescape(value[1:-1])
                current.setdefault('_spans', {})[name] = [number - 1, number]
                key = name
            elif quoted.fullmatch(line) and key:
                current[key] += self._unescape(line[1:-1])
                current['_spans'][key][1] = number
            else:
                raise ValueError(f"Line {number}: invalid PO syntax")
        finish()
        if not self.entries:
            raise ValueError("No PO entries found")

    def _unescape(self, s: str) -> str:
        escapes = {'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f',
                   'v': '\v', 'a': '\a', '"': '"', '\\': '\\'}
        def decode(match):
            code = match.group(1)
            if code not in escapes:
                raise ValueError(f"Invalid PO escape: \\{code}")
            return escapes[code]
        return re.sub(r'\\(.)', decode, s)


class RCParser:
    """Extract user-visible strings from Windows resource scripts.

    A localized ``.rc`` file carries target text only, so source-dependent
    checks intentionally receive an empty source.  This still lets the linter
    catch malformed quoting, Swedish spelling, ellipses, invisible controls,
    and duplicated words without pretending that the target is its source.
    """

    _STRING_CONTROLS = frozenset({
        'CAPTION', 'LTEXT', 'RTEXT', 'CTEXT', 'PUSHBUTTON', 'DEFPUSHBUTTON',
        'CHECKBOX', 'AUTOCHECKBOX', 'RADIOBUTTON', 'AUTORADIOBUTTON',
        'GROUPBOX', 'MENUITEM', 'POPUP', 'CONTROL',
    })
    _QUOTED = re.compile(r'^(?P<control>[A-Z]+)\s+"(?P<text>(?:[^"\\\\]|\\\\.)*)"')

    def __init__(self, content: str, filename: str = '<unknown>'):
        self.content = content
        self.filename = filename
        self.language = 'sv' if re.search(r'[-_.]s(?:v|e)(?:[-_.]|$)', filename, re.IGNORECASE) else ''
        self.entries = []
        self._parse()

    def _parse(self):
        for line_number, raw in enumerate(self.content.splitlines(), 1):
            match = self._QUOTED.match(raw.lstrip())
            if not match or match.group('control') not in self._STRING_CONTROLS:
                continue
            text = match.group('text')
            # RC uses C-style escaping in quoted resource values.
            text = re.sub(r'\\\\([\\\\"nrt])', lambda item: {
                '\\\\': '\\\\', '"': '"', 'n': '\\n', 'r': '\\r', 't': '\\t',
            }[item.group(1)], text)
            self.entries.append({
                '_line': line_number,
                '_context': match.group('control'),
                'source': '',
                'translation': text,
                '_translations': [text],
                '_type': '',
            })
        if not self.entries:
            raise ValueError('No Windows RC UI strings found')


class AndroidXMLParser:
    """Extract target-only strings from an Android ``res/values`` XML file.

    Android resource files do not include English source text.  Treat their
    resource names as context and deliberately restrict source-dependent
    checks, just as the RC and properties parsers do.  ``string`` values and
    all plural ``item`` values are user-facing; ``translatable=false`` values
    are intentionally excluded.
    """

    def __init__(self, content: str, filename: str = '<unknown>'):
        self.content = content
        self.filename = filename
        self.language = 'sv' if re.search(r'[-_.]s(?:v|e)(?:[-_.]|$)', filename, re.IGNORECASE) else ''
        self.entries = []
        self._parse()

    def _parse(self):
        import xml.etree.ElementTree as ET
        from xml.parsers import expat
        root = ET.fromstring(self.content)
        if root.tag != 'resources':
            raise ValueError('Expected an Android resources document')
        lines = []
        parser = expat.ParserCreate()
        def start(name, attrs):
            if name in ('string', 'plurals'):
                lines.append(parser.CurrentLineNumber)
        parser.StartElementHandler = start
        parser.Parse(self.content, True)
        line_iter = iter(lines)
        for node in root:
            if node.tag not in ('string', 'plurals'):
                continue
            line = next(line_iter, 1)
            if node.get('translatable') == 'false':
                continue
            name = node.get('name')
            if not name:
                raise ValueError(f'Line {line}: Android resource without name')
            values = ([''.join(node.itertext())] if node.tag == 'string'
                      else [''.join(item.itertext()) for item in node.findall('item')])
            self.entries.append({
                '_context': name,
                '_id': name,
                '_line': line,
                'source': '',
                'translation': values[0] if values else '',
                '_translations': values or [''],
                '_source_is_key': True,
                '_type': '',
            })
        if not self.entries:
            raise ValueError('No Android UI strings found')


class TSParser:
    """Parse Qt .ts (XML) files."""
    
    def __init__(self, content: str, filename: str = "<unknown>"):
        self.content = content
        self.filename = filename
        self.entries = []
        self._parse()
    
    def _parse(self):
        """Read Qt plural/length variants and actual XML line numbers."""
        import xml.etree.ElementTree as ET
        from xml.parsers import expat
        root = ET.fromstring(self.content)
        if root.tag != 'TS':
            raise ValueError("Expected a Qt TS document")
        self.language = root.get('language', '')
        lines = []
        xml_parser = expat.ParserCreate()
        def start(name, attrs):
            if name == 'message':
                lines.append(xml_parser.CurrentLineNumber)
        xml_parser.StartElementHandler = start
        xml_parser.Parse(self.content, True)
        line_iter = iter(lines)
        for context in root.findall('context'):
            for message in context.findall('message'):
                source = message.find('source')
                if source is None:
                    raise ValueError("TS message is missing its source")
                translation = message.find('translation')
                forms = []
                if translation is not None:
                    nodes = translation.findall('numerusform') if message.get('numerus') == 'yes' else [translation]
                    for node in nodes:
                        variants = node.findall('lengthvariant')
                        forms.extend(''.join(v.itertext()) for v in (variants or [node]))
                self.entries.append({
                    '_context': context.findtext('name', '') + '\x04' + message.findtext('comment', ''),
                    '_id': message.get('id', ''),
                    '_line': next(line_iter, 1),
                    'source': ''.join(source.itertext()),
                    'translation': forms[0] if forms else '',
                    '_translations': forms or [''],
                    '_numerus': message.get('numerus') == 'yes',
                    '_type': translation.get('type', '') if translation is not None else 'unfinished',
                })


class XLIFFParser:
    """Parse translatable units from XLIFF 1.2 and 2.x documents."""

    _INLINE_CODES = frozenset({'ph', 'x', 'bx', 'ex', 'bpt', 'ept', 'it', 'sc', 'ec', 'cp'})

    def __init__(self, content: str, filename: str = '<unknown>'):
        self.content = content
        self.filename = filename
        self.entries = []
        self.language = ''
        self._parse()

    @staticmethod
    def _name(tag):
        return tag.rsplit('}', 1)[-1].rsplit(':', 1)[-1]

    @classmethod
    def _child(cls, element, name):
        return next((child for child in element if cls._name(child.tag) == name), None)

    @classmethod
    def _text(cls, element):
        """Keep visible text and an inline code's explicit equivalent text."""
        if element is None:
            return ''
        parts = []

        def visit(node):
            if node.text:
                parts.append(node.text)
            for child in node:
                name = cls._name(child.tag)
                equivalent = child.get('equiv-text') or child.get('equiv')
                if name in cls._INLINE_CODES and equivalent:
                    parts.append(equivalent)
                else:
                    visit(child)
                if child.tail:
                    parts.append(child.tail)

        visit(element)
        return ''.join(parts)

    def _parse(self):
        import xml.etree.ElementTree as ET
        from xml.parsers import expat
        try:
            root = ET.fromstring(self.content)
        except ET.ParseError as exc:
            raise ValueError(f'Line {exc.position[0]}: invalid XLIFF XML: {exc}') from exc
        if self._name(root.tag) != 'xliff':
            raise ValueError('Expected an XLIFF document')
        version = root.get('version', '')
        if version.startswith('1.'):
            self._parse_12(root)
        elif version.startswith('2.'):
            if not root.tag.startswith('{urn:oasis:names:tc:xliff:document:2.0}'):
                raise ValueError('XLIFF 2.x documents must use the official 2.0 namespace')
            self._parse_2(root)
        else:
            raise ValueError(f'Unsupported XLIFF version: {version or "missing"}')

    def _element_lines(self, names):
        from xml.parsers import expat
        lines = []
        parser = expat.ParserCreate(namespace_separator=' ')

        def start(name, attrs):
            if name.rsplit(' ', 1)[-1].rsplit(':', 1)[-1] in names:
                lines.append(parser.CurrentLineNumber)

        parser.StartElementHandler = start
        parser.Parse(self.content, True)
        return iter(lines)

    def _parse_12(self, root):
        lines = self._element_lines({'trans-unit'})
        units = [element for element in root.iter() if self._name(element.tag) == 'trans-unit']
        unit_lines = {id(unit): next(lines, 1) for unit in units}
        for file_element in (element for element in root.iter() if self._name(element.tag) == 'file'):
            if file_element.get('translate', '').lower() == 'no':
                continue
            language = file_element.get('target-language', '') or root.get('target-language', '')
            self.language = self.language or language
            for unit in (element for element in file_element.iter() if self._name(element.tag) == 'trans-unit'):
                line = unit_lines[id(unit)]
                if unit.get('translate', '').lower() == 'no':
                    continue
                source = self._child(unit, 'source')
                if source is None:
                    raise ValueError(f'Line {line}: XLIFF trans-unit is missing source')
                target = self._child(unit, 'target')
                context = unit.get('resname', '') or unit.get('id', '')
                self.entries.append({
                    '_id': unit.get('id', ''), '_context': context, '_line': line,
                    '_language': language, 'source': self._text(source),
                    'translation': self._text(target),
                    '_translations': [self._text(target)], '_type': unit.get('state', ''),
                })

    def _parse_2(self, root):
        lines = self._element_lines({'segment'})
        segment_lines = {}
        for segment in (element for element in root.iter() if self._name(element.tag) == 'segment'):
            segment_lines[id(segment)] = next(lines, 1)
        language = root.get('trgLang', '')
        self.language = language
        for unit in (element for element in root.iter() if self._name(element.tag) == 'unit'):
            if unit.get('translate', '').lower() == 'no':
                continue
            context = unit.get('name', '') or unit.get('id', '')
            for segment in (element for element in unit if self._name(element.tag) == 'segment'):
                line = segment_lines[id(segment)]
                source = self._child(segment, 'source')
                if source is None:
                    raise ValueError(f'Line {line}: XLIFF segment is missing source')
                target = self._child(segment, 'target')
                segment_id = segment.get('id', '')
                unit_id = unit.get('id', '')
                self.entries.append({
                    '_id': f'{unit_id}:{segment_id}' if segment_id else unit_id,
                    '_context': context, '_line': line, '_language': language,
                    'source': self._text(source), 'translation': self._text(target),
                    '_translations': [self._text(target)], '_type': segment.get('state', ''),
                })


class PropertiesParser:
    """Parse Java ``.properties`` localization exports.

    Hosted Weblate can export a translated Java-properties catalog without the
    English source catalog.  In that form the key is useful as context, but
    must never be treated as source text for placeholder or terminology
    comparisons.  This parser deliberately validates the portable, one-line
    key/value subset used by Weblate exports and preserves line numbers for
    useful diagnostics.
    """

    def __init__(self, content: str, filename: str = '<unknown>'):
        self.entries = []
        self.language = ''
        for line_number, line in enumerate(content.splitlines(), 1):
            stripped = line.lstrip()
            if not stripped or stripped.startswith(('#', '!')):
                continue
            separator = next((index for index, char in enumerate(line)
                              if char in '=:'), None)
            if separator is None:
                raise ValueError(f'Line {line_number}: expected key/value separator')
            key, value = line[:separator].strip(), line[separator + 1:]
            if not key:
                raise ValueError(f'Line {line_number}: empty properties key')
            self.entries.append({
                '_id': key, '_context': key, '_line': line_number,
                '_language': '', '_source_is_key': True,
                'source': key, 'translation': value, '_translations': [value],
                '_plural_categories': (), '_type': '',
            })
        if not self.entries:
            raise ValueError('Properties catalog contains no translation entries')


class JSONParser:
    """Parse common JSON localization catalogs without third-party dependencies."""

    _METADATA = frozenset({'locale', 'language', 'targetlanguage', 'target_language', '$schema'})
    _PLURAL_FORMS = frozenset({'zero', 'one', 'two', 'few', 'many', 'other'})

    def __init__(self, content: str, filename: str = '<unknown>', format_: str = 'auto'):
        self.content = content
        self.filename = filename
        if format_ not in ('auto', 'nested', 'entries'):
            raise ValueError('JSON format must be auto, nested, or entries')
        self.format = format_
        self.entries = []
        self.language = ''
        self._parse()

    def _parse(self):
        try:
            document = json.loads(self.content)
        except json.JSONDecodeError as exc:
            raise ValueError(f'Line {exc.lineno}: invalid JSON: {exc.msg}') from exc
        if not isinstance(document, (dict, list)) or not document:
            raise ValueError('JSON catalog must contain an object or non-empty entry list')
        if isinstance(document, dict):
            self.language = str(document.get('@locale') or document.get('locale') or
                                document.get('targetLanguage') or document.get('target_language') or '')
        self._line_map = self._locations()
        self._walk(document, ())
        if not self.entries:
            raise ValueError('JSON catalog contains no translation entries')

    def _locations(self):
        """Map JSON member paths to source lines without another dependency."""
        positions, length = {}, len(self.content)

        def skip(index):
            while index < length and self.content[index].isspace():
                index += 1
            return index

        def string(index):
            start = index
            index += 1
            while index < length:
                if self.content[index] == '\\':
                    index += 2
                elif self.content[index] == '"':
                    return json.loads(self.content[start:index + 1]), index + 1
                else:
                    index += 1
            raise ValueError('invalid JSON string')

        def value(index, path):
            index = skip(index)
            if self.content[index] == '{':
                index = skip(index + 1)
                while self.content[index] != '}':
                    key_line = self.content.count('\n', 0, index) + 1
                    key, index = string(index)
                    child = path + (key,)
                    positions[child] = key_line
                    index = skip(index)
                    index = value(skip(index + 1), child)
                    index = skip(index)
                    if self.content[index] == ',':
                        index = skip(index + 1)
                    else:
                        break
                return index + 1
            if self.content[index] == '[':
                index = skip(index + 1)
                item = 0
                while self.content[index] != ']':
                    child = path + (str(item),)
                    positions[child] = self.content.count('\n', 0, index) + 1
                    index = value(index, child)
                    item += 1
                    index = skip(index)
                    if self.content[index] == ',':
                        index = skip(index + 1)
                    else:
                        break
                return index + 1
            if self.content[index] == '"':
                return string(index)[1]
            match = re.match(r'(?:true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)', self.content[index:])
            return index + len(match.group())

        value(skip(0), ())
        return positions

    def _append(self, source, translation, path, item=None, translations=None, plural_categories=(), source_is_key=False):
        item = item or {}
        translations = list(translations) if translations is not None else [translation]
        if not isinstance(source, str) or not all(isinstance(value, str) for value in translations):
            raise ValueError(f'JSON translation at {".".join(path) or "root"} must use string source and target values')
        if item.get('translate') is False or item.get('translatable') is False:
            return
        entry_id = str(item.get('id') or '.'.join(path))
        context = str(item.get('context') or '.'.join(path[:-1]))
        self.entries.append({
            '_id': entry_id, '_context': context,
            '_line': self._line_map.get(path + ('source',), self._line_map.get(path, 1)),
            '_language': str(item.get('targetLanguage') or item.get('target_language') or self.language),
            'source': source, 'translation': translations[0],
            '_source_is_key': source_is_key, '_translations': translations, '_plural_categories': tuple(plural_categories),
            '_type': str(item.get('state', '')),
        })

    def _walk(self, value, path):
        if isinstance(value, list):
            for index, item in enumerate(value):
                if not isinstance(item, dict):
                    raise ValueError(f'JSON catalog entry {index} must be an object')
                self._walk(item, path + (str(index),))
            return
        if not isinstance(value, dict):
            raise ValueError('JSON catalog root must be an object or entry list')
        # A nested catalog can legitimately have a translated key named
        # ``source`` (for example a UI label "Source" alongside other fields).
        # It is an explicit source/target entry only when it also declares a
        # recognized target member.
        if ('source' in value and any(key in value for key in ('target', 'translation', 'value'))
                and set(value) <= {'id', 'context', 'source', 'target', 'translation', 'value', 'targetLanguage',
                                   'target_language', 'state', 'translate', 'translatable', 'flags', 'note'}):
            if self.format == 'nested':
                raise ValueError('JSON format policy only allows nested catalogs')
            target_key = next((key for key in ('target', 'translation', 'value') if key in value), None)
            target = value.get(target_key, '')
            source = value['source']
            # Weblate's API export represents plural source and target strings as
            # parallel arrays.  Treat these as an explicit plural catalog rather
            # than rejecting a valid API response as malformed JSON.
            if isinstance(source, list) or isinstance(target, list):
                if not isinstance(source, list) or not isinstance(target, list):
                    raise ValueError(f'JSON translation at {".".join(path) or "root"} must use matching source and target arrays')
                if not source or len(source) != len(target):
                    raise ValueError(f'JSON translation at {".".join(path) or "root"} must use non-empty source and target arrays of equal length')
                self._append(source[0], '', path, value,
                             ['' if form is None else form for form in target])
            elif isinstance(target, dict) and target and set(target) <= self._PLURAL_FORMS:
                self._append(source, '', path, value,
                             ['' if form is None else form for form in target.values()], target.keys())
            else:
                self._append(source, '' if target is None else target, path, value)
            return
        for key, child in value.items():
            if key.startswith('@') or key.lower() in self._METADATA:
                continue
            child_path = path + (key,)
            if isinstance(child, str) or child is None:
                if self.format == 'entries':
                    raise ValueError('JSON format policy only allows explicit entries')
                self._append(key, child or '', child_path, source_is_key=True)
            elif isinstance(child, dict) and child and set(child) <= self._PLURAL_FORMS:
                if self.format == 'entries':
                    raise ValueError('JSON format policy only allows explicit entries')
                self._append(key, '', child_path, translations=['' if form is None else form for form in child.values()],
                             plural_categories=child.keys(), source_is_key=True)
            elif isinstance(child, (dict, list)):
                self._walk(child, child_path)
            else:
                raise ValueError(f'JSON translation at {".".join(child_path)} must be a string, object, or entry list')


class L10nLinter:
    """Main linter class."""
    
    # Regex patterns for placeholder detection
    PRINTF_PATTERN = re.compile(r'%[-+0 #]*\d*\.?\d*[hlL]?[diouxXeEfFgGaAcspn%]')
    PYTHON_FORMAT = re.compile(r'\{(\d+|[a-zA-Z_][a-zA-Z0-9_]*)?(?:![rsa])?(?::[^}]*)?\}')
    PYTHON_NAMED = re.compile(r'%\([a-zA-Z_][a-zA-Z0-9_]*\)[sdfgiou]')  # %(name)s %(hotkey)s
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
    OPTION_VALUE_PATTERN = re.compile(r'(?<![\w-])--?[A-Za-z][\w-]*(?:=|\s+)([A-Z][A-Z0-9_]+)')
    
    # Number patterns for localization checks
    NUMBER_WITH_COMMAS = re.compile(r'\b\d{1,3}(,\d{3})+\b')  # e.g. 1,000 or 1,000,000
    
    # Currency patterns
    CURRENCY_PATTERN = re.compile(r'[\$€£¥]\s?\d|USD|EUR|GBP|JPY')
    # Pattern to strip printf positional args (%1$s, %2$d etc.) before currency check
    PRINTF_POSITIONAL = re.compile(r'%\d+\$[a-zA-Z]')
    
    # Date format patterns (common English formats)
    DATE_PATTERNS = [
        re.compile(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b'),
        re.compile(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b'),  # MM/DD/YYYY
        re.compile(r'\b\d{4}-\d{2}-\d{2}\b'),  # ISO format (usually OK)
    ]
    
    # Python brace format
    PYTHON_BRACE_FORMAT = re.compile(r'\{(\w*(?:\.\w+)*(?:\[[\w"\']+\])*)?(?:![rsa])?(?::[^}]*)?\}')
    
    # Newline pattern (literal \n in raw text before unescape)
    NEWLINE_LITERAL = re.compile(r'\\n')
    
    def __init__(self, config: Optional[dict] = None, disabled_rules: Optional[set] = None):
        self.config = config or {}
        self.disabled_rules = resolve_rules(disabled_rules or set())
        self.max_length = self.config.get('max_length', 500)
        self.length_ratio = self.config.get('length_ratio', 3.0)  # Translation shouldn't be 3x longer
        self.translation_memory = self.config.get('translation_memory', {})
        self._use_translation_memory = 'translation_memory' in self.config
    
    def lint_file(self, filepath: str, content: Optional[str] = None) -> LintResult:
        """Lint a single file."""
        result = LintResult(disabled_rules=self.disabled_rules, severity_overrides=self.config.get('severity', {}))
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
        
        if ext in L10N_EXTENSIONS:
            try:
                if ext == '.po':
                    self._lint_po(filepath, content, result)
                elif ext == '.ts':
                    self._lint_ts(filepath, content, result)
                elif ext == '.xml':
                    self._lint_android_xml(filepath, content, result)
                elif ext in ('.xlf', '.xliff'):
                    self._lint_xliff(filepath, content, result)
                elif ext == '.rc':
                    self._lint_rc(filepath, content, result)
                elif ext == '.properties':
                    self._lint_properties(filepath, content, result)
                else:
                    self._lint_json(filepath, content, result)
            except (ValueError, SyntaxError) as exc:
                match = re.search(r'[Ll]ine (\d+)', str(exc))
                result.add(LintIssue(filepath, int(match.group(1)) if match else 1,
                                     Severity.ERROR, 'syntax-error', str(exc)))
        else:
            result.add(LintIssue(
                file=filepath,
                line=0,
                severity=Severity.ERROR,
                rule="unknown-format",
                message=_("Unknown file format: {ext}").format(ext=ext)
            ))
        
        if self.config.get('reference') and not any(i.rule == 'syntax-error' for i in result.issues):
            from l10n_project import compare_catalog
            try:
                compare_catalog(filepath, content, self.config['reference'], result)
            except (OSError, ValueError, SyntaxError) as exc:
                result.add(LintIssue(filepath, 1, Severity.ERROR, 'reference-error', str(exc)))
        return result
    
    def _lint_po(self, filepath: str, content: str, result: LintResult):
        """Lint a .po file."""
        parser = POParser(content, filepath)
        self.po_parser = parser  # Store for access in check methods
        seen_msgids = {}
        entries_count = 0
        # Initialize consistency map for this file
        self.consistency_map = {}
        # Detect language for locale-specific checks
        self._current_lang = self.config.get('language') or self._detect_language_from_po(filepath, parser)
        
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
                
                # Check: Same plurals
                self._check_same_plurals(filepath, line, msgid, msgid_plural, entry, result)
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
            
            self._format_flags = set(flags)
            self._message_context = entry.get('msgctxt', '')
            forms = [(key, value) for key, value in entry.items() if key.startswith('msgstr[')] if msgid_plural else [('msgstr', msgstr)]
            for key, value in forms:
                if value:
                    source = msgid if key in ('msgstr', 'msgstr[0]') else msgid_plural
                    self._check_translation(filepath, line, source, value, result)

            # Check: Duplicates (use msgctxt+msgid as key to avoid false positives)
            msgctxt = entry.get('msgctxt', '')
            dup_key = (msgctxt, msgid)
            if dup_key in seen_msgids:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.WARNING,
                    rule="duplicate",
                    message=_("Duplicate msgid (first seen at line {line})").format(line=seen_msgids[dup_key]),
                    context=msgid[:50]
                ))
            else:
                seen_msgids[dup_key] = line
        
        # Check plural forms in header and entries
        self._check_plural_forms(filepath, parser, result)
        
        result.entries_checked += entries_count
    
    def _check_translation(self, filepath, line, source, translation, result):
        seen = set()
        # Target-only formats (nested JSON and Java properties exports) do not
        # carry English source text.  Their identifiers are context only, so
        # source/target comparisons would be fabricated diagnostics.
        target_only_methods = {
            '_check_typos', '_check_repeated_words', '_check_zero_width_space',
            '_check_unicode_integrity',
        }
        for rule, spec in RULES.items():
            if not spec.method or spec.method in ('_check_plural_forms', '_check_same_plurals'):
                continue
            if getattr(self, '_source_is_key', False) and spec.method not in target_only_methods:
                continue
            if rule in self.disabled_rules or spec.method in seen:
                continue
            if spec.language and getattr(self, '_current_lang', '').split('_')[0].split('-')[0] != spec.language:
                continue
            seen.add(spec.method)
            getattr(self, spec.method)(filepath, line, source, translation, result)
        for wrong, correct, context in self.config.get('glossary_terms', []):
            if re.search(r'(?<!\w)' + re.escape(wrong) + r'(?!\w)', translation, re.IGNORECASE):
                result.add(LintIssue(filepath, line, Severity.WARNING, 'glossary',
                    f"Prefer '{correct}' over '{wrong}'" + (f" ({context})" if context else ''), source))

    def _check_project_terms(self, filepath, line, source, translation, result):
        """Apply project-specific required and forbidden terminology."""
        context = getattr(self, '_message_context', '')
        for item in self.config.get('required_terms', []):
            if not isinstance(item, dict) or not item.get('source') or not item.get('target'):
                continue
            if item['source'].casefold() in source.casefold() and item['target'].casefold() not in translation.casefold():
                scope = item.get('context', '')
                if not scope or scope == context:
                    result.add(LintIssue(filepath, line, Severity.ERROR, 'required-term-missing',
                        f"Required term '{item['target']}' is missing", source))
        for term in self.config.get('forbidden_terms', []):
            if isinstance(term, str) and re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', translation, re.IGNORECASE):
                result.add(LintIssue(filepath, line, Severity.WARNING, 'forbidden-term',
                    f"Forbidden term '{term}'", source))

    def _check_unicode_integrity(self, filepath, line, source, translation, result):
        """Expose invisible direction controls and non-normalized text to reviewers."""
        import unicodedata
        controls = set('\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069')
        introduced = sorted(set(translation) - set(source))
        found = [f'U+{ord(char):04X}' for char in introduced if char in controls]
        if found:
            result.add(LintIssue(filepath, line, Severity.WARNING, 'bidi-control',
                'Translation introduces bidirectional control character(s): ' + ', '.join(found), source))
        if translation != unicodedata.normalize('NFC', translation):
            result.add(LintIssue(filepath, line, Severity.WARNING, 'unicode-normalization',
                'Translation is not normalized as Unicode NFC', source))

    def _lint_ts(self, filepath: str, content: str, result: LintResult):
        parser = TSParser(content, filepath)
        self._current_lang = self.config.get('language') or parser.language
        self.po_parser = None
        self.consistency_map = {}
        self._format_flags = {'qt-format'}
        for entry in parser.entries:
            line, source = entry['_line'], entry['source']
            if entry['_type'] in ('vanished', 'obsolete'):
                result.add(LintIssue(filepath, line, Severity.INFO, 'vanished',
                                     'Translation source was removed', source))
                continue
            # Qt catalogs can contain structural keys with no source or target
            # text. They are not translatable messages and must not be reported
            # as missing translations.
            if not source.strip() and all(not value.strip() for value in entry['_translations']):
                continue
            result.entries_checked += 1
            self._message_context = entry['_context']
            if entry['_type'] == 'unfinished' or any(not value.strip() for value in entry['_translations']):
                result.add(LintIssue(filepath, line, Severity.ERROR, 'missing-translation',
                                     'Unfinished/missing translation', source))
            for value in entry['_translations']:
                if value.strip():
                    self._check_translation(filepath, line, source, value, result)

    def _lint_android_xml(self, filepath: str, content: str, result: LintResult):
        self._lint_external_entries(filepath, AndroidXMLParser(content, filepath), result)

    def _lint_xliff(self, filepath: str, content: str, result: LintResult):
        self._lint_external_entries(filepath, XLIFFParser(content, filepath), result)

    def _lint_json(self, filepath: str, content: str, result: LintResult):
        self._lint_external_entries(filepath, JSONParser(content, filepath, self.config.get('json_format', 'auto')), result)

    def _lint_rc(self, filepath: str, content: str, result: LintResult):
        self._lint_external_entries(filepath, RCParser(content, filepath), result)

    def _lint_properties(self, filepath: str, content: str, result: LintResult):
        self._lint_external_entries(filepath, PropertiesParser(content, filepath), result)

    def _lint_external_entries(self, filepath, parser, result):
        """Run the shared checks for XLIFF and JSON source/target entries."""
        self.po_parser = None
        self.consistency_map = {}
        self._format_flags = set()
        default_language = self.config.get('language') or parser.language
        for entry in parser.entries:
            source = entry['source']
            translations = entry['_translations']
            if (not entry.get('_source_is_key', False)
                    and not source.strip()
                    and all(not value.strip() for value in translations)):
                continue
            result.entries_checked += 1
            self._current_lang = self.config.get('language') or entry.get('_language') or default_language
            self._message_context = entry.get('_context', '')
            line = entry['_line']
            previous_source_is_key = getattr(self, '_source_is_key', False)
            self._source_is_key = entry.get('_source_is_key', False)
            self._check_cldr_plural_categories(filepath, line, entry, result)
            if any(not value.strip() for value in translations):
                result.add(LintIssue(filepath, line, Severity.ERROR, 'missing-translation',
                                     'Unfinished/missing translation', source))
            # Plural variants are alternative forms of one entry, so they must
            # not be compared with each other by the cross-entry consistency rule.
            previous_skip = getattr(self, '_skip_consistency', False)
            self._skip_consistency = len(translations) > 1
            try:
                for value in translations:
                    if value.strip():
                        self._check_translation(filepath, line, source, value, result)
            finally:
                self._skip_consistency = previous_skip
                self._source_is_key = previous_source_is_key

    def _check_cldr_plural_categories(self, filepath, line, entry, result):
        """Require the core CLDR categories for JSON plural objects when known."""
        categories = set(entry.get('_plural_categories', ()))
        if not categories:
            return
        language = (self._current_lang or '').replace('_', '-').split('-')[0]
        expected = {
            'ar': {'zero', 'one', 'two', 'few', 'many', 'other'},
            'ru': {'one', 'few', 'many', 'other'},
            'pl': {'one', 'few', 'many', 'other'},
            'cs': {'one', 'few', 'many', 'other'},
            'ja': {'other'}, 'ko': {'other'}, 'zh': {'other'},
        }.get(language, {'one', 'other'})
        missing = expected - categories
        if missing:
            result.add(LintIssue(filepath, line, Severity.ERROR, 'cldr-plural-missing',
                'Missing CLDR plural form(s): ' + ', '.join(sorted(missing)), entry['source']))

    def _check_placeholders(self, filepath, line, source, translation, result):
        # Nested JSON exports contain only target strings. Their dotted key is
        # useful context, but is not source text and cannot define placeholders.
        if getattr(self, '_source_is_key', False):
            return
        from l10n_project import icu_signature, placeholder_signature, python_format_text
        python_source = python_format_text(source)
        python_translation = python_format_text(translation)
        flags = getattr(self, '_format_flags', set())
        icu_before = icu_signature(source)
        icu_after = icu_signature(translation)
        if icu_before or icu_after:
            if icu_before != icu_after:
                result.add(LintIssue(filepath, line, Severity.ERROR, 'placeholder-mismatch',
                    f"Placeholder mismatch (icu): source has {icu_before}, translation has {icu_after}", source))
        if 'qt-format' in flags:
            kinds = ['qt']
        elif 'c-format' in flags or 'python-format' in flags:
            kinds = ['printf']
        elif 'python-brace-format' in flags:
            kinds = ['python']
        else:
            kinds = ['printf']
            if self.PYTHON_BRACE_FORMAT.search(python_source) or self.PYTHON_BRACE_FORMAT.search(python_translation):
                kinds.append('python')
            if re.search(r'%L?(?:[1-9]\d?|n)(?![\w.$])', source + ' ' + translation):
                kinds.append('qt')
        if ('no-c-format' in flags or 'no-python-format' in flags) and 'printf' in kinds:
            kinds.remove('printf')
        if 'no-python-brace-format' in flags and 'python' in kinds:
            kinds.remove('python')
        for kind in kinds:
            rule = 'python-format' if kind == 'python' else 'placeholder-mismatch'
            try:
                explicit = bool(flags & {'c-format', 'python-format'})
                before = placeholder_signature(python_source if kind == 'python' else source, kind, explicit=explicit)
                after = placeholder_signature(python_translation if kind == 'python' else translation, kind, explicit=explicit)
                if kind == 'printf' and not explicit and before != after:
                    # msgunfmt usually loses format flags. Literal suffixes
                    # such as %iHz, %uth and Swedish %ss (genitive) can then
                    # hide one side of an otherwise identical contract. Only
                    # suppress the mismatch when BOTH complete signatures
                    # agree; retain the safeguards for prose percentages and
                    # whitespace after %. Explicit format checks stay strict.
                    suffixed_before = placeholder_signature(source, kind, explicit=False, allow_suffix=True)
                    suffixed_after = placeholder_signature(translation, kind, explicit=False, allow_suffix=True)
                    if suffixed_before and suffixed_before == suffixed_after:
                        before, after = suffixed_before, suffixed_after
            except ValueError as exc:
                result.add(LintIssue(filepath, line, Severity.ERROR, rule,
                                     f"Invalid {kind} format: {exc}", source))
                continue
            if before != after:
                result.add(LintIssue(filepath, line, Severity.ERROR, rule,
                    f"Placeholder mismatch ({kind}): source has {before}, translation has {after}", source))

    # Msgids where length checks are meaningless (translators put their own info)
    LENGTH_SKIP_MSGIDS = frozenset([
        'translator-credits', 'translator_credits',
        'translation-credits', 'translation_credits',
    ])

    def _check_length(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for length issues."""
        # Skip meta-strings where translators write their own content
        if source.strip() in self.LENGTH_SKIP_MSGIDS:
            return
        
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
        
        # Treat '...' and '…' (U+2026) as equivalent
        source_stripped = source.rstrip()
        trans_stripped = translation.rstrip()
        if (source_stripped.endswith('...') and trans_stripped.endswith('\u2026')) or \
           (source_stripped.endswith('\u2026') and trans_stripped.endswith('...')):
            return
        
        # Check ending punctuation
        end_punct = '.!?:;'
        source_end = source_stripped[-1] if source_stripped else ''
        trans_end = trans_stripped[-1] if trans_stripped else ''
        
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
        # Trailing whitespace (only spaces/tabs, not newlines)
        # Don't flag if source also has trailing whitespace
        if translation != translation.rstrip(' \t') and source == source.rstrip(' \t'):
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="trailing-whitespace",
                message=_("Translation has trailing whitespace"),
                context=source[:50]
            ))
        
        # Missing trailing space: source ends with space but translation doesn't
        if source.endswith(' ') and not translation.endswith(' ') and translation:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="missing-trailing-space",
                message=_("Source ends with space but translation does not"),
                context=translation[-50:]
            ))
        
        # Missing leading space: source starts with space but translation doesn't
        if source.startswith(' ') and not translation.startswith(' ') and translation:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="missing-leading-space",
                message=_("Source starts with space but translation does not"),
                context=translation[:50]
            ))
        
        # Double spaces — only between words (not leading indentation)
        # Skip when source also has double spaces (intentional formatting)
        has_double = False
        if '  ' not in source:
            for tline in translation.split('\n'):
                stripped = tline.lstrip()
                if '  ' in stripped:
                    if re.search(r'\w  +\w', stripped):
                        has_double = True
                        break
        if has_double:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.INFO,
                rule="double-spaces",
                message=_("Translation contains double spaces between words"),
                context=source[:50]
            ))
    
    def _check_quotes(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for quote consistency."""
        # Skip strings containing HTML attributes (href="...", src="...", etc.)
        # where straight quotes inside tags are expected alongside typographic quotes in text
        if re.search(r'<[^>]+="[^"]*"', translation):
            return
        
        # Programming examples such as Texture("name", index) must retain
        # straight quotes even when surrounding Swedish prose uses ”…”.
        prose = re.sub(r'\b[A-Za-z_]\w*\([^\n]*?"[^\n]*?"[^\n]*?\)', '', translation)
        # Detect mixed quote styles in prose.
        straight_quotes = prose.count('"') + prose.count("'")
        curly_quotes = prose.count('\u201c') + prose.count('\u201d') + prose.count('\u2018') + prose.count('\u2019')
        german_quotes = translation.count('\u201e')  # Only „ (U+201E), don't re-count chars in curly_quotes
        
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
    
    # Real HTML tags only (exclude man page B<>, I<>, shell redirects, math comparisons)
    _REAL_HTML_TAG = re.compile(
        r'</?(?:a|b|i|u|p|br|hr|em|tt|li|ul|ol|dl|dt|dd|td|th|tr|div|span|pre|code|strong|'
        r'table|thead|tbody|img|font|center|blockquote|h[1-6]|sup|sub|small|big|'
        r'input|select|option|form|label|textarea|button)(?:\s[^>]*)?>',
        re.IGNORECASE
    )

    def _check_html_tags(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for HTML tag mismatches.
        
        Only flags when both source and translation contain HTML-like tags,
        to avoid false positives where <option> in source is descriptive
        text translated to <flagga> in Swedish (not actual HTML).
        """
        # Attributes may be serialized with different quote styles by Qt/PO
        # tooling (for example href='…' becomes href="…").  Structural tag
        # comparison must not report that benign normalization as an error.
        canonical = lambda value: re.sub(r'\s+[^>]*', '', value).lower()
        source_tags = sorted(canonical(tag) for tag in self._REAL_HTML_TAG.findall(source))
        trans_tags = sorted(canonical(tag) for tag in self._REAL_HTML_TAG.findall(translation))
        
        # Skip if translation has no HTML tags at all — source tags are likely
        # descriptive terms (e.g., <option> → <flagga>) not actual markup
        if source_tags != trans_tags and source_tags and trans_tags:
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
    
    @staticmethod
    def _strip_html_entities(text: str) -> str:
        """Remove HTML entities like &amp; &lt; &gt; &quot; to avoid false accelerator matches."""
        return re.sub(r'&[a-zA-Z]+;', '', text)

    def _check_accelerators(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check keyboard accelerator consistency."""
        # Strip HTML entities before checking — &amp; is not an accelerator
        source_clean = self._strip_html_entities(source)
        trans_clean = self._strip_html_entities(translation)
        source_accels = self.ACCELERATOR_PATTERN.findall(source_clean)
        trans_accels = self.ACCELERATOR_PATTERN.findall(trans_clean)
        
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
        # Swedish decimal separators normally use a comma, while source text
        # commonly uses a decimal point.  Compare a normalized representation
        # so that 0.5 → 0,5 does not become a false positive.
        source_nums = {number.replace(',', '.') for number in re.findall(r'\b\d+(?:[.,]\d+)?\b', source)}
        trans_nums = {number.replace(',', '.') for number in re.findall(r'\b\d+(?:[.,]\d+)?\b', translation)}
        
        # Numbers in source but not in translation
        missing = source_nums - trans_nums
        if missing and len(source_nums) <= 3:  # Only inform for few numbers
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.INFO,
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
    
    def _check_cross_newline_duplicates(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for words duplicated across newline boundaries (e.g. 'word\\nword')."""
        lines = translation.split('\n')
        for i in range(len(lines) - 1):
            end_words = lines[i].rstrip().split()
            start_words = lines[i + 1].lstrip().split()
            if not end_words or not start_words:
                continue
            end_word = end_words[-1].strip('.,;:!?"\'()[]{}')
            start_word = start_words[0].strip('.,;:!?"\'()[]{}')
            # Skip short words (prepositions etc.), markdown headers, list markers, digits
            if (len(end_word) < 3 or len(start_word) < 3
                    or end_word.startswith('#') or end_word.startswith('-')
                    or end_word.startswith('*') or end_word.startswith('>')
                    or end_word.isdigit()):
                continue
            if end_word.lower() == start_word.lower():
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.WARNING,
                    rule="cross-newline-duplicate",
                    message=_("Word '{word}' duplicated across line break").format(word=end_word),
                    context=source[:50]
                ))
                break  # One report per entry is enough
    
    # Patterns for false positive detection in source-equals-translation
    _CAMELCASE_RE = re.compile(r'^[A-Z][a-z]+(?:[A-Z][a-z]+)+$')
    _ALLCAPS_RE = re.compile(r'^[A-Z][A-Z0-9_\-./: ]{0,60}$')
    _IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.\-]+$')
    _FORMAT_ONLY_RE = re.compile(r'^[%\-\d.#+ *]*[sdifcpxXeEgGulLhq]+$')
    _PATH_RE = re.compile(r'^[/~]|^[a-z]+://')
    # Enhanced false positive detection patterns
    _EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    _URL_RE = re.compile(r'^https?://[^\s]+$')
    _FILEPATH_RE = re.compile(r'^[/\\]|^[a-zA-Z]:[/\\]|^\./|^\.\./|^~/')
    _FORMAT_SPECIFIER_RE = re.compile(r'^%[sd%]$|^%\d*\.\d*[sd]$|^%\d+\$[sd]$')
    _PROGRAMMING_KEYWORD_RE = re.compile(r'^(null|true|false|void|int|str|string|bool|boolean|float|double|long|short|char|byte|const|static|public|private|protected|if|else|for|while|switch|case|break|continue|return|import|from|class|def|function|var|let|const)$', re.IGNORECASE)
    _BRAND_WORDS = {
        'canon', 'epson', 'hp', 'nikon', 'sony', 'samsung', 'fuji', 'fujifilm',
        'kodak', 'olympus', 'pentax', 'panasonic', 'leica', 'ricoh', 'sigma',
    }
    _COMMON_ENGLISH_SRC_EQ = {
        'the', 'is', 'are', 'was', 'were', 'been', 'have', 'has', 'had',
        'this', 'that', 'will', 'would', 'could', 'should', 'for', 'with',
        'from', 'into', 'your', 'you', 'can', 'not', 'and', 'but', 'which',
        'when', 'where', 'what', 'how', 'why', 'also', 'only', 'must', 'may',
    }

    def _is_likely_false_positive_src_eq(self, source: str) -> bool:
        """Check if source-equals-translation is likely a false positive."""
        s = source.strip()
        if len(s) <= 3:
            return True
        if not any(c.isalpha() for c in s):
            return True
        if self._FORMAT_ONLY_RE.match(s):
            return True
        if self._PATH_RE.match(s):
            return True
        if self._CAMELCASE_RE.match(s):
            return True
        if self._ALLCAPS_RE.match(s) and len(s) <= 30:
            return True
        if self._IDENTIFIER_RE.match(s) and ' ' not in s:
            return True
        # Enhanced false positive detection (from task requirements)
        if self._EMAIL_RE.match(s):
            return True
        if self._URL_RE.match(s):
            return True
        if self._FILEPATH_RE.match(s):
            return True
        if self._FORMAT_SPECIFIER_RE.match(s):
            return True
        if self._PROGRAMMING_KEYWORD_RE.match(s):
            return True
        words = s.split()
        if words and words[0].startswith('-'):
            return True
        if len(words) == 1:
            if s[0].isupper():
                return True
            if s.islower() and len(s) <= 15 and s.lower() not in self._COMMON_ENGLISH_SRC_EQ:
                return True
        if len(words) == 2 and all(w[0].isupper() for w in words if w):
            return True
        if any(w.lower() in self._BRAND_WORDS for w in words):
            return True
        special_chars = sum(1 for c in s if c in '=|<>[]{}()@#$')
        if special_chars >= 2:
            return True
        placeholders = self.PRINTF_PATTERN.findall(s)
        alpha_len = sum(1 for c in s if c.isalpha())
        if placeholders and alpha_len < 10:
            return True
        if re.match(r'^[\d.,x\u00d7X\s]+(?:DPI|dpi|mm|cm|in|pt|px|lpi)\b', s):
            return True
        if re.match(r'^[\d.,xX\u00d7\s\-]+(?:\s+(?:in|mm|cm))?\s*(?:label|sheet)?$', s.strip()):
            return True
        paper_keywords = {'iso', 'jis', 'ansi', 'letter', 'legal', 'tabloid', 'executive', 'super', 'folio'}
        if len(words) <= 4 and any(w.lower() in paper_keywords for w in words):
            return True
        if re.search(r'version\s+[\d.]+', s, re.IGNORECASE):
            return True
        if alpha_len < len(s) * 0.3 and len(s) > 3:
            return True
        if '@' in s or '${' in s:
            return True
        if re.match(r'^(?:Extra|Channel|Slot|Tray|Bin|Mode|Type|Level)\s+\d+$', s):
            return True
        return False

    def _check_source_equals_translation(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check if translation is identical to source."""
        if len(source) < 5 or not any(c.isalpha() for c in source):
            return
        if source == translation:
            if self._is_likely_false_positive_src_eq(source):
                return
            words = set(w.lower() for w in re.findall(r'[a-zA-Z]+', source))
            has_english = bool(words & self._COMMON_ENGLISH_SRC_EQ)
            severity = Severity.WARNING if len(source) > 30 and has_english else Severity.INFO
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=severity,
                rule="source-equals-translation",
                message=_("Translation is identical to source (possibly untranslated)"),
                context=source[:80]
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


    def _check_number_localization(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check that numbers use localized formatting (e.g. 1,000 → 1 000 in Swedish)."""
        # Find comma-separated numbers in translation that look like English formatting
        english_nums = self.NUMBER_WITH_COMMAS.findall(translation)
        if english_nums:
            # Check if source also has them (might be intentional)
            source_nums = self.NUMBER_WITH_COMMAS.findall(source)
            if english_nums and source_nums:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.INFO,
                    rule="number-localization",
                    message=_("Number formatting may not be localized (e.g. 1,000 should be 1 000 in some locales)"),
                    context=source[:50]
                ))

    def _check_decimal_separator(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check that decimal points in numbers are localized to commas in Swedish.
        
        English: 1.5, 3.14, 0.001
        Swedish: 1,5  3,14  0,001
        
        Skip: version numbers (2.0.1), IP addresses, filenames, format strings,
              numbers identical in source and translation (likely intentional).
        """
        target_lang = getattr(self, '_current_lang', 'sv').split('_')[0].split('-')[0]
        if not target_lang.startswith('sv'):
            return
        
        # Find decimal numbers in translation: digit(s).digit(s)
        # Must be preceded by space/start and followed by space/end/punctuation
        decimal_pattern = re.compile(r'(?:^|(?<=[\s(=:,]))(\d+\.\d+)(?=[\s).,;:!?\n]|$)')
        
        trans_decimals = decimal_pattern.findall(translation)
        if not trans_decimals:
            return
        
        # Get decimals from source too
        source_decimals = set(decimal_pattern.findall(source))
        
        for num in trans_decimals:
            # Skip if same number exists in source (likely intentional: version, constant)
            if num in source_decimals:
                continue
            
            # Skip time formats: HH.MM where both parts are exactly 2 digits
            # (00.00, 12.30, 23.59 — Swedish uses . for time)
            parts = num.split('.')
            if len(parts) == 2 and len(parts[0]) == 2 and len(parts[1]) == 2:
                try:
                    h, m = int(parts[0]), int(parts[1])
                    if 0 <= h <= 23 and 0 <= m <= 59:
                        continue
                except ValueError:
                    pass
            
            # Skip version-like numbers (more than one dot: 2.0.1, 3.14.1)
            # Check if this number is part of a longer dotted sequence
            ver_pattern = re.compile(re.escape(num) + r'\.\d')
            if ver_pattern.search(translation):
                continue
            
            # Skip if preceded by a dot (part of version: x.1.5)
            idx = translation.find(num)
            if idx > 0 and translation[idx-1] == '.':
                continue
            
            # Skip format strings (%.2f, %3.1f)
            if idx > 0 and translation[idx-1] == '%':
                continue
            
            # Skip IP-like patterns (four dot-separated groups)
            ip_pattern = re.compile(r'\d+\.\d+\.\d+\.\d+')
            if ip_pattern.search(translation):
                # Check if our number is part of it
                for m in ip_pattern.finditer(translation):
                    if m.start() <= idx < m.end():
                        break
                else:
                    # Not part of IP, flag it
                    result.add(LintIssue(
                        file=filepath,
                        line=line,
                        severity=Severity.WARNING,
                        rule="decimal-separator",
                        message=_("Decimal point «{num}» should use comma in Swedish (e.g. {fix})").format(
                            num=num, fix=num.replace('.', ',')),
                        context=source[:60],
                    ))
                continue
            
            # Skip filenames (word.ext pattern)
            if idx > 0:
                before = translation[:idx]
                if re.search(r'[a-zA-Z]$', before):
                    continue  # looks like filename.ext
            
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="decimal-separator",
                message=_("Decimal point «{num}» should use comma in Swedish (e.g. {fix})").format(
                    num=num, fix=num.replace('.', ',')),
                context=source[:60],
            ))

    def _check_currency_localization(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check currency format localization."""
        # Strip printf positional args (%1$s) before checking — $ there is not currency
        clean_source = self.PRINTF_POSITIONAL.sub('', source)
        clean_trans = self.PRINTF_POSITIONAL.sub('', translation)
        source_currencies = self.CURRENCY_PATTERN.findall(clean_source)
        if source_currencies:
            trans_currencies = self.CURRENCY_PATTERN.findall(clean_trans)
            # If source has currency symbols and translation has identical ones, might not be localized
            if source_currencies and source_currencies == trans_currencies:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.INFO,
                    rule="currency-localization",
                    message=_("Currency format may need localization"),
                    context=source[:50]
                ))

    def _check_date_format(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check date format localization."""
        for pattern in self.DATE_PATTERNS[:2]:  # Skip ISO format
            source_dates = pattern.findall(source)
            if source_dates:
                trans_dates = pattern.findall(translation)
                if trans_dates:
                    result.add(LintIssue(
                        file=filepath,
                        line=line,
                        severity=Severity.WARNING,
                        rule="date-format",
                        message=_("Date format may not be localized"),
                        context=source[:50]
                    ))
                    break

    def _check_newline_mismatch(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check that the number of newlines matches between source and translation."""
        source_newlines = source.count('\n')
        trans_newlines = translation.count('\n')
        if source_newlines != trans_newlines:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="newline-mismatch",
                message=_("Newline count mismatch: source has {src}, translation has {trans}").format(
                    src=source_newlines, trans=trans_newlines
                ),
                context=source[:50]
            ))

    def _detect_language_from_po(self, filepath: str, po_parser: 'POParser') -> str:
        """Detect target language from PO file header or filename."""
        # Check for Language header in PO file
        for entry in po_parser.entries[:5]:  # Check first few entries for header
            if 'msgid' in entry and entry['msgid'] == '':
                msgstr = entry.get('msgstr', '')
                # Look for Language: sv or similar
                if 'Language:' in msgstr:
                    lang_match = re.search(r'Language:\s*([a-z]{2,3})', msgstr)
                    if lang_match:
                        return lang_match.group(1)
        
        # Fall back to filename detection
        filename = Path(filepath).name.lower()
        if filename == 'sv.po' or '.sv.' in filename or filename.endswith('.sv.po'):
            return 'sv'
        # Add more languages as needed
        return ''

    def _detect_domain_from_content(self, source_text: str) -> str:
        """Detect domain from source text content."""
        source_lower = source_text.lower()
        
        # Music domain keywords
        music_keywords = {'staff', 'note', 'chord', 'tempo', 'clef', 'measure', 'bar', 'scale', 'key'}
        if any(keyword in source_lower for keyword in music_keywords):
            return 'music'
        
        # Web platform domain keywords
        web_keywords = {'tracker', 'repository', 'commit', 'merge', 'branch', 'pull request', 'issue'}
        if any(keyword in source_lower for keyword in web_keywords):
            return 'web'
        
        # Mail domain keywords
        mail_keywords = {'envelope', 'relay', 'bounce', 'smtp', 'pop3', 'imap', 'mailbox'}
        if any(keyword in source_lower for keyword in mail_keywords):
            return 'mail'
        
        return ''

    def _check_terminology(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for common Swedish terminology mistakes."""
        lang = getattr(self, '_current_lang', '').split('_')[0].split('-')[0]
        if lang != 'sv':
            return
        
        # Swedish terminology rules
        terminology_rules = {
            'redaktör': ('redigerare', 'editor in software context'),
            'otydlig': ('luddig', 'fuzzy translation term'),
            'öppen källa': ('öppen källkod', 'open source'),
            'repostera': ('skicka om', 'repost is not a Swedish word'),
            'reposta': ('skicka om', 'repost is not a Swedish word'),
        }
        
        # Check mixed usage of omfång/omfattning for "range/scope"
        if 'omfång' in translation.lower() and 'omfattning' not in translation.lower():
            pass  # OK, using one consistently
        # Flag "repostera/reposta" variants
        for anglicism in ['forwarda', 'patcha', 'committa', 'pusha', 'mergea', 'fetcha', 'brancha', 'deploya']:
            if anglicism in translation.lower():
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.WARNING,
                    rule="terminology",
                    message=_("Swedish: '{word}' is an anglicism, use Swedish equivalent").format(word=anglicism),
                    context=translation[:80]
                ))
        
        # Other menu term checks
        menu_terms = {
            'Edit': ('Redigera', 'Redigera'),
            'View': ('Visa', 'Visa'),
            'Tools': ('Verktyg', 'Verktyg'),
            'Help': ('Hjälp', 'Hjälp'),
            'Settings': ('Inställningar', 'Inställningar'),
            'Preferences': ('Inställningar', 'Inställningar'),
        }
        src_stripped = source.strip()
        tr_stripped = translation.strip()
        # "View" also names a viewport or color-management transform. Only
        # enforce the menu verb when the catalog explicitly identifies a menu.
        message_context = getattr(self, '_message_context', '').replace('_', ' ')
        menu_context = re.search(r'\b(?:menu|menubar)\b', message_context, re.IGNORECASE)
        # "File" is also a label and a command category. Require the same
        # explicit menu evidence as View before enforcing Arkiv.
        if source.strip() == 'File' and translation.strip() == 'Fil' and menu_context:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.ERROR,
                rule="terminology",
                message=_("Swedish menu: 'File' menu must be 'Arkiv', not 'Fil'"),
                context=translation[:80]
            ))
        if src_stripped in menu_terms and (src_stripped != 'View' or menu_context):
            expected, _desc = menu_terms[src_stripped]
            if tr_stripped and tr_stripped != expected and len(tr_stripped) < 30:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.WARNING,
                    rule="terminology",
                    message=_("Swedish menu: '{src}' should be '{expected}', got '{got}'").format(
                        src=src_stripped, expected=expected, got=tr_stripped),
                    context=translation[:80]
                ))

        # A geometric line is a "linje". Require evidence of a text/code line,
        # and do not mistake compounds such as "riktlinjer" for that term.
        code_line = re.search(
            r'\b(?:command[- ]lines?|lines? of (?:source )?code|(?:source|code)[- ]lines?)\b',
            source, re.IGNORECASE)
        code_context = re.search(
            r'\b(?:cli|terminal|console|shell|source[- ]code|'
            r'(?:code|text|script)[- ]editor|compiler|syntax error)\b',
            source + ' ' + message_context, re.IGNORECASE)
        plain_line = re.search(r'(?<![\w-])lines?(?![\w-])', source, re.IGNORECASE)
        translated_line = re.search(
            r'\b(?:kommando|kod|källkods)?linje(?:n|ns|r|rs|rna|rnas)?\b',
            translation, re.IGNORECASE)
        if translated_line and (code_line or (plain_line and code_context)):
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="terminology",
                message=_("Swedish terminology: prefer 'rad' over 'linje' in CLI/programming context"),
                context=translation[:80]
            ))
        
        # Check y/n → j/n
        
        if re.search(r'\by/n\b|\by/N\b|\bY/n\b|\bY/N\b', translation):
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="terminology",
                message=_("Swedish: 'y/n' should be 'j/n' (ja/nej)"),
                context=translation[:80]
            ))
        
        translation_lower = translation.lower()
        for wrong_term, (correct_term, context_note) in terminology_rules.items():
            if wrong_term in translation_lower:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.WARNING,
                    rule="terminology",
                    message=_("Swedish terminology: prefer '{correct}' over '{wrong}' ({context})").format(
                        correct=correct_term, wrong=wrong_term, context=context_note
                    ),
                    context=translation[:80]
                ))

    def _check_domain_terminology(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for domain-specific terminology mistakes."""
        lang = getattr(self, '_current_lang', '').split('_')[0].split('-')[0]
        if lang != 'sv':
            return
        
        domain = self._detect_domain_from_content(source)
        if not domain:
            return
        
        translation_lower = translation.lower()
        
        if domain == 'music':
            music_rules = {
                'personal': ('notsystem/notrad', 'staff (music)'),
                'belopp': ('värde', 'amount (music)'),
                'stoppning': ('utfyllnad', 'padding'),
                'rörelse': ('sats', 'movement (music)'),
                'röst': ('stämma', 'voice (music part)'),
                'slips': ('bindebåge', 'tie (music)'),
            }
            
            for wrong_term, (correct_term, context_note) in music_rules.items():
                if wrong_term in translation_lower:
                    result.add(LintIssue(
                        file=filepath,
                        line=line,
                        severity=Severity.WARNING,
                        rule="domain-terminology",
                        message=_("Music domain terminology: prefer '{correct}' over '{wrong}' ({context})").format(
                            correct=correct_term, wrong=wrong_term, context=context_note
                        ),
                        context=translation[:80]
                    ))
        
        elif domain == 'web':
            web_rules = {
                'spårare': ('ärendehanterare', 'tracker (issue)'),
            }
            
            for wrong_term, (correct_term, context_note) in web_rules.items():
                if wrong_term in translation_lower:
                    result.add(LintIssue(
                        file=filepath,
                        line=line,
                        severity=Severity.WARNING,
                        rule="domain-terminology",
                        message=_("Web platform terminology: prefer '{correct}' over '{wrong}' ({context})").format(
                            correct=correct_term, wrong=wrong_term, context=context_note
                        ),
                        context=translation[:80]
                    ))

    def _check_false_friends(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for Swedish-English false friends."""
        lang = getattr(self, '_current_lang', '').split('_')[0].split('-')[0]
        if lang != 'sv':
            return
        
        false_friends = {
            'actual': ('aktuell', 'faktisk/verklig'),
            'eventually': ('eventuellt', 'slutligen/till slut'),
            'patron': ('patron', 'kund/beskyddare'),
            'billion': ('biljon', 'miljard'),
            'chef': ('chef', 'kock'),  # Only in cooking context
        }
        
        source_lower = source.lower()
        translation_lower = translation.lower()
        
        for english_word, (wrong_swedish, correct_swedish) in false_friends.items():
            if english_word in source_lower and wrong_swedish in translation_lower:
                # Special handling for chef - only flag in cooking context.
                if english_word == 'chef' and not any(cook_word in source_lower for cook_word in ['cook', 'kitchen', 'recipe', 'food']):
                    continue
                # Capitalized subscription tiers and other product labels can be
                # intentionally preserved verbatim, e.g. "Patron".
                if english_word == 'patron' and re.search(r'\bPatron\b', source) and re.search(r'\bPatron\b', translation):
                    continue

                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.WARNING,
                    rule="false-friends",
                    message=_("False friend: '{english}' should be '{correct}', not '{wrong}'").format(
                        english=english_word, correct=correct_swedish, wrong=wrong_swedish
                    ),
                    context=f"{source[:40]} → {translation[:40]}"
                ))

    def _check_consistency(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check consistency within a file and against optional project memory."""
        if getattr(self, '_skip_consistency', False):
            return
        if not hasattr(self, 'consistency_map'):
            self.consistency_map = {}
        
        # Skip very short or technical strings
        if len(source) < 10 or not any(c.isalpha() for c in source):
            return
        
        # Use source as key, excluding msgctxt for now (could be enhanced)
        source_key = (getattr(self, '_message_context', ''), source.strip())
        
        if source_key in self.consistency_map:
            existing_translation = self.consistency_map[source_key]
            if existing_translation != translation and translation:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.INFO,
                    rule="consistency",
                    message=_("Inconsistent translation: same source has different translations"),
                    context=f"'{source[:40]}' → '{existing_translation[:30]}' vs '{translation[:30]}'"
                ))
        else:
            if translation:  # Only store non-empty translations
                self.consistency_map[source_key] = translation
        if self._use_translation_memory:
            memory_key = source.strip()
            remembered = self.translation_memory.get(memory_key)
            if remembered and remembered != translation:
                result.add(LintIssue(
                    file=filepath, line=line, severity=Severity.INFO, rule="consistency",
                    message=_('Translation differs from project translation memory'),
                    context=f"'{source[:40]}' → '{remembered[:30]}' vs '{translation[:30]}'"))
            elif translation:
                self.translation_memory[memory_key] = translation


    # Pattern-based typo detection (no external dictionary needed)
    # Swedish spelling normally reduces a compound boundary with three equal
    # consecutive letters to two (process + status → processtatus).  Treat all
    # triple-letter runs as suspicious; _check_typos exempts intentional
    # exclamations and format tokens before reporting them.
    _TYPO_DOUBLED_RE = re.compile(
        r'([a-zåäö])\1{2,}'
        r'|([^lnrstdgk])(\2)'  # Doubled consonants that are rare in Swedish (except l,n,r,s,t,d,g,k)
        , re.IGNORECASE
    )
    # Common Swedish misspelling patterns (curated, low false positive)
    _COMMON_TYPOS = {
        # Doubled characters
        'ogiltligt': 'ogiltigt', 'borttagninngsnivå': 'borttagningsnivå',
        'innget': 'inget', 'inngen': 'ingen', 'meedd': 'med',
        'fölljande': 'följande', 'tilllåta': 'tillåta', 'tilllåt': 'tillåt',
        'annvändare': 'användare', 'annvänds': 'används', 'annvända': 'använda',
        'innstallera': 'installera', 'elller': 'eller',
        # Transpositions / missing chars
        'defintions': 'definitions', 'definiton': 'definition',
        'destintation': 'destination', 'altenativ': 'alternativ',
        'kataolg': 'katalog', 'felakitg': 'felaktig', 'felaktgt': 'felaktigt',
        'tillåttet': 'tillåtet', 'filnamm': 'filnamn',
        'varabel': 'variabel', 'specifercera': 'specificera',
        'konfiguartion': 'konfiguration', 'proccess': 'process',
        'argumnet': 'argument', 'arguement': 'argument',
        'övversätt': 'översätt', 'reedan': 'redan',
        'inställnig': 'inställning', 'inställnignar': 'inställningar',
        'standdard': 'standard', 'verision': 'version',
        'kommmando': 'kommando', 'katalogg': 'katalog',
        'aktvieras': 'aktiveras', 'aktvierad': 'aktiverad',
        'uppkoplling': 'uppkoppling',
        'rättighetter': 'rättigheter', 'utskift': 'utskrift',
    }

    def _check_typos(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for typos in translation using pattern-based detection."""
        # Skip very short strings
        if len(translation) < 8 or not any(c.isalpha() for c in translation):
            return
        
        # Clean the translation
        clean = re.sub(r'%[sd\d$.#+ -]*[sdifcpxXeEgGulLhqn]', ' ', translation)
        clean = re.sub(r'<[^>]+>', ' ', clean)
        clean = re.sub(r'\\[nt"\\]', ' ', clean)
        clean = re.sub(r'\{[^}]+\}', ' ', clean)
        clean = re.sub(r'&\w+;', ' ', clean)
        
        typos_found = []
        
        # Check for known common typos
        words = re.findall(r'\b(\w+)\b', clean)
        for w in words:
            wl = w.lower()
            if wl in self._COMMON_TYPOS:
                typos_found.append(f"{w} → {self._COMMON_TYPOS[wl]}")
        
        # Swedish compounds normally reduce three equal consecutive letters to
        # two.  Flag triples, while retaining the narrowly scoped exemptions
        # required for intentional dialogue and format tokens.
        source_words = set(re.findall(r'\b\w+\b', source))
        for word in re.findall(r'\b[a-zåäö]+\b', clean, re.IGNORECASE):
            if not re.search(r'([a-zåäö])\1{2,}', word, re.IGNORECASE):
                continue
            # Unchanged source tokens (IEEE, PPP, pppd, III, www) are
            # technical names, not Swedish compounds. Curated typo checks
            # above still apply, including when the source repeats a typo.
            if word in source_words:
                continue
            # yyyy is a year token too; keep the exemption at word boundaries
            # so repeated letters inside actual words still receive diagnostics.
            if (word == 'Processstatus' or word.lower() in {'yyyy', 'upppil'}
                    or re.fullmatch(r'[åmdhs]+', word, re.IGNORECASE)):
                continue
            # Skip intentional exclamations in game/dialog text (neeeej, jooooo)
            if re.match(r'^[a-zåäö]{1,3}([a-zåäö])\1{3,}[a-zåäö]?$', word, re.IGNORECASE):
                continue
            # Skip format placeholders (uxxxx, etc.)
            if re.match(r'^[ux]+$', word, re.IGNORECASE):
                continue
            typos_found.append(word)
        
        # Specific doubled-error patterns (NOT valid compound boundaries)
        # "nng" at non-boundary (e.g., "borttagninngsnivå" but NOT "inngång")
        for m in re.finditer(r'\b([a-zåäö]*nng[a-zåäö]*)\b', clean):
            word = m.group(1)
            # Skip known valid: inngång → no, that's also wrong. "nng" is almost always a typo in Swedish
            if len(word) > 5:
                typos_found.append(word)
        
        if typos_found:
            # Deduplicate and report first 3
            unique = list(dict.fromkeys(typos_found))[:3]
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="typo",
                message=_("Possible typo(s): {words}").format(words=', '.join(unique)),
                context=source[:50]
            ))

    def _check_plural_forms(self, filepath: str, parser: 'POParser', result: LintResult):
        """Check plural forms in header and entries."""
        # Known correct plural forms per language
        KNOWN_PLURALS = {
            'sv': {'nplurals': 2, 'formula': '(n != 1)', 'desc': 'Swedish'},
            'da': {'nplurals': 2, 'formula': '(n != 1)', 'desc': 'Danish'},
            'de': {'nplurals': 2, 'formula': '(n != 1)', 'desc': 'German'},
            'en': {'nplurals': 2, 'formula': '(n != 1)', 'desc': 'English'},
            'es': {'nplurals': 2, 'formula': '(n != 1)', 'desc': 'Spanish'},
            'fi': {'nplurals': 2, 'formula': '(n != 1)', 'desc': 'Finnish'},
            'fr': {'nplurals': 2, 'formula': '(n > 1)', 'desc': 'French'},
            'it': {'nplurals': 2, 'formula': '(n != 1)', 'desc': 'Italian'},
            'nb': {'nplurals': 2, 'formula': '(n != 1)', 'desc': 'Norwegian Bokmål'},
            'nb_NO': {'nplurals': 2, 'formula': '(n != 1)', 'desc': 'Norwegian Bokmål'},
            'nl': {'nplurals': 2, 'formula': '(n != 1)', 'desc': 'Dutch'},
            'pt_BR': {'nplurals': 2, 'formula': '(n > 1)', 'desc': 'Brazilian Portuguese'},
            'pt': {'nplurals': 2, 'formula': '(n != 1)', 'desc': 'Portuguese'},
            'pl': {'nplurals': 3, 'formula': '(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)', 'desc': 'Polish'},
            'ru': {'nplurals': 3, 'formula': '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)', 'desc': 'Russian'},
            'ja': {'nplurals': 1, 'formula': '0', 'desc': 'Japanese'},
            'ko': {'nplurals': 1, 'formula': '0', 'desc': 'Korean'},
            'zh_CN': {'nplurals': 1, 'formula': '0', 'desc': 'Chinese Simplified'},
            'zh_TW': {'nplurals': 1, 'formula': '0', 'desc': 'Chinese Traditional'},
            'ar': {'nplurals': 6, 'formula': '(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5)', 'desc': 'Arabic'},
            'cs': {'nplurals': 3, 'formula': '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2', 'desc': 'Czech'},
            'hu': {'nplurals': 2, 'formula': '(n != 1)', 'desc': 'Hungarian'},
            'ro': {'nplurals': 3, 'formula': '(n==1 ? 0 : (n==0 || (n%100>0 && n%100<20)) ? 1 : 2)', 'desc': 'Romanian'},
            'tr': {'nplurals': 2, 'formula': '(n > 1)', 'desc': 'Turkish'},
        }

        # Step 1: Parse header for Plural-Forms
        header_nplurals = None
        header_plural_formula = None
        header_lang = None
        has_plural_header = False
        
        for entry in parser.entries[:5]:
            if 'msgid' in entry and entry['msgid'] == '':
                msgstr = entry.get('msgstr', '')
                has_plural_header = bool(re.search(r'^Plural-Forms:', msgstr, re.MULTILINE))
                # Extract Plural-Forms header
                plural_match = re.search(
                    r'Plural-Forms:\s*nplurals\s*=\s*(\d+)\s*;\s*plural\s*=\s*([^;\\]+)',
                    msgstr
                )
                if plural_match:
                    header_nplurals = int(plural_match.group(1))
                    header_plural_formula = plural_match.group(2).strip().rstrip(';').strip()
                
                # Extract Language header
                lang_match = re.search(r'Language:\s*([a-zA-Z_]+)', msgstr)
                if lang_match:
                    header_lang = lang_match.group(1)
                break
        
        # Detect language from filename if not in header
        if not header_lang:
            filename = Path(filepath).name.lower()
            lang_match = re.search(r'\.([a-z]{2}(?:_[A-Z]{2})?)\.po$', filepath)
            if lang_match:
                header_lang = lang_match.group(1)
        
        # Step 2: Validate header Plural-Forms
        if header_lang and header_lang in KNOWN_PLURALS:
            expected = KNOWN_PLURALS[header_lang]
            
            if header_nplurals is None and (has_plural_header or any('msgid_plural' in e for e in parser.entries)):
                result.add(LintIssue(
                    file=filepath,
                    line=1,
                    severity=Severity.ERROR,
                    rule="plural-header-missing",
                    message=_("Missing Plural-Forms header for {lang} (expected nplurals={n})").format(
                        lang=expected['desc'], n=expected['nplurals']
                    ),
                    context="Plural-Forms header"
                ))
            elif header_nplurals is not None and header_nplurals != expected['nplurals']:
                result.add(LintIssue(
                    file=filepath,
                    line=1,
                    severity=Severity.ERROR,
                    rule="plural-header-wrong",
                    message=_("Wrong nplurals={got} for {lang} (expected nplurals={expected})").format(
                        got=header_nplurals, lang=expected['desc'],
                        expected=expected['nplurals']
                    ),
                    context=f"Plural-Forms: nplurals={header_nplurals}"
                ))
            
            # Check formula for common languages
            if header_plural_formula and header_nplurals == expected['nplurals']:
                # Normalize whitespace for comparison
                norm_got = re.sub(r'\s+', '', header_plural_formula)
                norm_exp = re.sub(r'\s+', '', expected['formula'])
                # For simple 2-form languages, check the common patterns
                if expected['nplurals'] == 2:
                    valid_formulas = {
                        '(n!=1)', 'n!=1', '(n>1)', 'n>1',
                        '(n!=1);', 'n!=1;', '(n>1);', 'n>1;'
                    }
                    if header_lang in ('fr', 'pt_BR', 'tr'):
                        valid_formulas = {'(n>1)', 'n>1', '(n>1);', 'n>1;'}
                    else:
                        valid_formulas = {'(n!=1)', 'n!=1', '(n!=1);', 'n!=1;'}
                    
                    if norm_got.rstrip(';') not in {f.rstrip(';') for f in valid_formulas}:
                        result.add(LintIssue(
                            file=filepath,
                            line=1,
                            severity=Severity.WARNING,
                            rule="plural-formula-suspicious",
                            message=_("Suspicious plural formula for {lang}: got '{got}', expected '{exp}'").format(
                                lang=expected['desc'],
                                got=header_plural_formula,
                                exp=expected['formula']
                            ),
                            context="Plural-Forms"
                        ))
        
        # Step 3: Check individual plural entries
        expected_nplurals = header_nplurals or (
            KNOWN_PLURALS.get(header_lang, {}).get('nplurals') if header_lang else None
        )
        
        for entry in parser.entries:
            msgid = entry.get('msgid', '')
            msgid_plural = entry.get('msgid_plural', '')
            line = entry.get('_line', 0)
            flags = entry.get('_flags', [])
            
            if not msgid or not msgid_plural:
                continue
            
            if 'fuzzy' in flags:
                continue
            
            # Count msgstr[N] entries
            plural_forms = {}
            for key in entry:
                m = re.match(r'msgstr\[(\d+)\]', key)
                if m:
                    idx = int(m.group(1))
                    plural_forms[idx] = entry[key]
            
            if not plural_forms:
                continue
            
            # Check: correct number of plural forms
            if expected_nplurals:
                max_idx = max(plural_forms.keys()) + 1
                
                if set(range(expected_nplurals)) - plural_forms.keys():
                    result.add(LintIssue(
                        file=filepath,
                        line=line,
                        severity=Severity.ERROR,
                        rule="plural-forms-missing",
                        message=_("Missing plural forms: got {got}, expected {exp} (nplurals={n})").format(
                            got=len(plural_forms), exp=expected_nplurals, n=expected_nplurals
                        ),
                        context=msgid[:50]
                    ))
                elif max_idx > expected_nplurals:
                    result.add(LintIssue(
                        file=filepath,
                        line=line,
                        severity=Severity.WARNING,
                        rule="plural-forms-extra",
                        message=_("Extra plural forms: got {got}, expected {exp} (nplurals={n})").format(
                            got=len(plural_forms), exp=expected_nplurals, n=expected_nplurals
                        ),
                        context=msgid[:50]
                    ))
            
            # Check: empty plural forms (all should be filled)
            for idx in range(expected_nplurals or max(plural_forms.keys()) + 1):
                if idx in plural_forms and not plural_forms[idx]:
                    result.add(LintIssue(
                        file=filepath,
                        line=line,
                        severity=Severity.ERROR,
                        rule="plural-form-empty",
                        message=_("Empty msgstr[{idx}] in plural entry").format(idx=idx),
                        context=msgid[:50]
                    ))
            
    def _check_zero_width_space(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for zero-width Unicode characters in translations."""
        zero_width_chars = {
            '\u200B': 'Zero-width space',
            '\u200C': 'Zero-width non-joiner',
            '\u200D': 'Zero-width joiner',
            '\u200E': 'Left-to-right mark',
            '\u200F': 'Right-to-left mark',
            '\uFEFF': 'Byte order mark',
        }
        
        # Find zero-width characters in source and translation
        source_chars = {char: name for char, name in zero_width_chars.items() if char in source}
        trans_chars = {char: name for char, name in zero_width_chars.items() if char in translation}
        
        # If source doesn't have them but translation does -> warning
        extra_chars = {char: name for char, name in trans_chars.items() if char not in source_chars}
        if extra_chars:
            char_names = ', '.join(extra_chars.values())
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="zero-width-space",
                message=_("Translation contains zero-width characters not in source: {chars}").format(chars=char_names),
                context=translation[:50]
            ))

    def _check_end_stop_mismatch(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check that source and translation match end punctuation."""
        if not source or not translation:
            return
        
        # Ignore very short strings
        if len(source.strip()) <= 4:
            return
        
        source_clean = source.strip()
        trans_clean = translation.strip()
        
        # Skip if source contains common abbreviations  
        abbrev_patterns = [r'\b(Mr|Mrs|Ms|Dr|Prof|etc|vs|e\.g|i\.e)\.']
        for pattern in abbrev_patterns:
            if re.search(pattern, source_clean, re.IGNORECASE):
                return
        
        source_ends_dot = source_clean.endswith('.')
        trans_ends_dot = trans_clean.endswith('.')
        
        # Allow "..." → "…" mapping
        source_ends_ellipsis = source_clean.endswith('...')
        trans_ends_ellipsis = trans_clean.endswith('…') or trans_clean.endswith('...')
        
        if source_ends_ellipsis and trans_ends_ellipsis:
            return  # Both have ellipsis - OK
        
        if source_ends_dot and not trans_ends_dot:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="end-stop-mismatch",
                message=_("Source ends with period but translation does not"),
                context=source[:50]
            ))
        elif trans_ends_dot and not source_ends_dot and not source_ends_ellipsis:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="end-stop-mismatch",
                message=_("Translation ends with period but source does not"),
                context=source[:50]
            ))

    def _check_ellipsis(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check for proper ellipsis usage (... should be …)."""
        if '...' in translation:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.INFO,
                rule="ellipsis",
                message=_("Use typographic ellipsis (…) instead of three dots (...)"),
                context=translation[:50]
            ))

    def _check_xml_tags_mismatch(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check that XML/HTML tags match between source and translation."""
        # Combo-box sentinel values like <None> are visible text, not markup.
        sentinel = r'\s*<[A-Za-z][A-Za-z0-9 _-]*>\s*'
        if re.fullmatch(sentinel, source) and re.fullmatch(sentinel, translation):
            return
        # Extract all tags from both strings
        # Require a real tag delimiter after the tag name.  Without this,
        # placeholders such as <your-organization> are incorrectly parsed as
        # an HTML <your> tag.
        tag_pattern = r'<(/?)([a-zA-Z][a-zA-Z0-9]*)(?=[\s/>])[^>]*>'
        source_tags = re.findall(tag_pattern, source)
        trans_tags = re.findall(tag_pattern, translation)
        
        # Convert to sorted lists of (closing_slash, tag_name) pairs - keep case for comparison
        source_tag_list = sorted([(slash, tag) for slash, tag in source_tags])
        trans_tag_list = sorted([(slash, tag) for slash, tag in trans_tags])
        
        if source_tag_list != trans_tag_list:
            source_tag_names = [f"<{slash}{tag}>" for slash, tag in source_tag_list]
            trans_tag_names = [f"<{slash}{tag}>" for slash, tag in trans_tag_list]
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="xml-tags-mismatch",
                message=_("XML/HTML tags mismatch: source has {src}, translation has {trans}").format(
                    src=source_tag_names, trans=trans_tag_names
                ),
                context=source[:50]
            ))

    def _check_duplicate_words(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Enhanced check for duplicate words, with Swedish exceptions."""
        words = translation.lower().split()
        
        # Check for triple words (always wrong)
        for i in range(len(words) - 2):
            if words[i] == words[i + 1] == words[i + 2] and words[i].isalpha():
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.WARNING,
                    rule="duplicate-words",
                    message=_("Triple duplicate word: '{word}'").format(word=words[i]),
                    context=translation[:50]
                ))
        
        # Check for double words with Swedish exceptions
        swedish_ok_doubles = {'i i', 'på på', 'till till', 'om om'}
        for i in range(len(words) - 1):
            if words[i] == words[i + 1] and words[i].isalpha():
                double_phrase = f"{words[i]} {words[i + 1]}"
                if double_phrase not in swedish_ok_doubles:
                    result.add(LintIssue(
                        file=filepath,
                        line=line,
                        severity=Severity.WARNING,
                        rule="duplicate-words",
                        message=_("Duplicate word: '{word}'").format(word=words[i]),
                        context=translation[:50]
                    ))

    def _check_same_plurals(self, filepath: str, line: int, msgid: str, msgid_plural: str, entry: dict, result: LintResult):
        """Check that plural forms are different (not identical)."""
        if not msgid_plural:
            return
        
        # Get all msgstr[n] values
        msgstr_values = []
        for key in sorted(entry.keys()):
            if key.startswith('msgstr[') and entry[key]:
                msgstr_values.append(entry[key])
        
        if len(msgstr_values) < 2:
            return
        
        # Check if all plural forms are identical
        if len(set(msgstr_values)) == 1:
            # Exception: if source plural/singular are also identical
            if msgid != msgid_plural:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.WARNING,
                    rule="same-plurals",
                    message=_("All plural forms are identical, but source forms differ"),
                    context=msgid[:50]
                ))

    def _check_punctuation_mismatch(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Enhanced check for punctuation matching."""
        end_punctuation = {':', ';', '!', '?'}
        
        source_clean = source.strip()
        trans_clean = translation.strip()
        
        if not source_clean or not trans_clean:
            return
        
        source_end = source_clean[-1] if source_clean else ''
        trans_end = trans_clean[-1] if trans_clean else ''
        
        # Check each type of punctuation (both end and throughout text)
        for punct in end_punctuation:
            source_has_end = source_end == punct
            trans_has_end = trans_end == punct
            source_has_any = punct in source_clean
            trans_has_any = punct in trans_clean
            
            # Check end punctuation first
            if source_has_end and not trans_has_end:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.WARNING,
                    rule="punctuation-mismatch",
                    message=_("Source ends with '{punct}' but translation does not").format(punct=punct),
                    context=source[:50]
                ))
            elif trans_has_end and not source_has_end:
                # Less strict for translation having extra punctuation
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.INFO,
                    rule="punctuation-mismatch",
                    message=_("Translation ends with '{punct}' but source does not").format(punct=punct),
                    context=source[:50]
                ))
            # Check general presence for punctuation like semicolon
            elif punct in [';', ':'] and source_has_any and not trans_has_any:
                result.add(LintIssue(
                    file=filepath,
                    line=line,
                    severity=Severity.WARNING,
                    rule="punctuation-mismatch",
                    message=_("Source contains '{punct}' but translation does not").format(punct=punct),
                    context=source[:50]
                ))

    def _check_url_preservation(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check that URLs in source are preserved in translation."""
        url_pattern = r'https?://[^\s<>"\']+'
        source_urls = set(re.findall(url_pattern, source))
        trans_urls = set(re.findall(url_pattern, translation))
        
        missing_urls = source_urls - trans_urls
        if missing_urls:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="url-preservation",
                message=_("URLs missing in translation: {urls}").format(urls=list(missing_urls)),
                context=source[:50]
            ))

    def _check_escaped_newline_count(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check that the number of \\n in source and translation match."""
        source_count = source.count('\\n')
        trans_count = translation.count('\\n')
        
        if source_count != trans_count:
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="escaped-newline-count",
                message=_("Escaped newline count mismatch: source has {src}, translation has {trans}").format(
                    src=source_count, trans=trans_count
                ),
                context=source[:50]
            ))

    def _check_max_length_ratio(self, filepath: str, line: int, source: str, translation: str, result: LintResult):
        """Check that translation is not more than 3x source length."""
        if len(source.strip()) < 10:
            return  # Skip short strings
        
        if len(translation) > len(source) * self.length_ratio:
            ratio = len(translation) / len(source)
            result.add(LintIssue(
                file=filepath,
                line=line,
                severity=Severity.WARNING,
                rule="max-length-ratio",
                message=_("Translation is {ratio:.1f}x longer than source (max {maximum:g}x recommended)").format(ratio=ratio, maximum=self.length_ratio),
                context=source[:50]
            ))


def find_l10n_files(path: str, recursive: bool = True) -> Generator[str, None, None]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if path.is_file():
        if path.suffix.lower() not in L10N_EXTENSIONS:
            raise ValueError(f"Unsupported translation file: {path}")
        yield str(path)
        return
    if not path.is_dir():
        raise ValueError(f"Not a file or directory: {path}")
    files = sorted(p for p in (path.rglob('*') if recursive else path.glob('*'))
                   if p.is_file() and p.suffix.lower() in L10N_EXTENSIONS)
    yield from (str(p) for p in files)


def fetch_github_files(repo_url: str, path_filter: str = "") -> Generator[tuple[str, str], None, None]:
    """Fetch one immutable tree from the repository's actual default branch."""
    import urllib.request
    from urllib.parse import quote
    repo = repo_url.removeprefix('https://github.com/').strip('/').removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError(f"Invalid GitHub repository: {repo_url}")
    def fetch(url):
        req = urllib.request.Request(url, headers={'User-Agent': 'l10n-lint'})
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode('utf-8')
    metadata = json.loads(fetch(f'https://api.github.com/repos/{repo}'))
    branch = quote(metadata['default_branch'], safe='')
    data = json.loads(fetch(f'https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1'))
    if data.get('truncated'):
        raise ValueError('GitHub returned a truncated tree; lint a local checkout instead')
    revision = data['sha']
    for item in data.get('tree', []):
        filepath = item['path']
        if item.get('type') != 'blob' or Path(filepath).suffix.lower() not in L10N_EXTENSIONS:
            continue
        if path_filter and not (filepath == path_filter.rstrip('/') or filepath.startswith(path_filter.rstrip('/') + '/')):
            continue
        content = fetch(f'https://raw.githubusercontent.com/{repo}/{revision}/{quote(filepath, safe="/")}')
        yield filepath, content


def lint_inputs(paths=(), github=None, path_filter='', config=None, disabled_rules=None,
                recursive=True, exclude=(), root=None, progress=None):
    """Shared desktop/CLI input pipeline; failures always become diagnostics."""
    from l10n_project import excluded
    config = config or {}
    linter = L10nLinter(config, disabled_rules)
    result = LintResult(disabled_rules=linter.disabled_rules, severity_overrides=config.get('severity', {}))
    seen = set()
    def add_file(path, content=None, identity=None):
        if excluded(path, exclude, root or Path.cwd()):
            return
        key = identity or (path if content is not None else str(Path(path).resolve()))
        if key in seen:
            return
        seen.add(key)
        file_result = linter.lint_file(path, content)
        result.files_checked += file_result.files_checked
        result.entries_checked += file_result.entries_checked
        result.issues.extend(file_result.issues)
        if progress:
            progress(path)
    if github:
        try:
            for filepath, content in fetch_github_files(github, path_filter):
                add_file(filepath, content)
        except Exception as exc:
            result.add(LintIssue(github, 0, Severity.ERROR, 'github-fetch-error', str(exc)))
    for path in paths:
        if is_url(path):
            try:
                filename, content = fetch_url_file(path)
                # Use URL identity for diagnostics but its decoded path for format detection.
                before = len(result.issues)
                add_file(filename, content, identity=path)
                for issue in result.issues[before:]:
                    issue.file = path
            except Exception as exc:
                result.add(LintIssue(path, 0, Severity.ERROR, 'url-fetch-error', str(exc)))
        else:
            try:
                found = list(find_l10n_files(path, recursive))
                if not found:
                    result.add(LintIssue(path, 0, Severity.ERROR, 'no-files', 'No translation files found'))
                for filepath in found:
                    add_file(filepath)
            except (OSError, ValueError) as exc:
                result.add(LintIssue(path, 0, Severity.ERROR, 'path-error', str(exc)))
    if not result.files_checked and not result.issues:
        result.add(LintIssue(str(root or '.'), 0, Severity.ERROR, 'no-files', 'No translation files checked'))
    return result


def lint_github_repo(repo, path_filter="", **kwargs):
    return lint_inputs(github=repo, path_filter=path_filter, **kwargs)


def fetch_url_file(url: str) -> tuple[str, str]:
    """
    Fetch a single l10n file from a URL.
    
    Args:
        url: HTTP(S) URL to a .po, .ts, .xlf/.xliff, or .json file
    
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
    if ext not in L10N_EXTENSIONS:
        raise ValueError(_("URL must point to a .po, .ts, .xlf/.xliff, or .json file, got: {ext}").format(ext=ext))
    
    # Fetch content
    req = urllib.request.Request(url, headers={
        'User-Agent': f'l10n-lint/{__version__}',
        'Accept': 'text/plain, application/octet-stream, */*',
    })
    
    with urllib.request.urlopen(req, timeout=30) as response:
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
    if format_type == 'sarif':
        from l10n_project import sarif_report
        return sarif_report(result)
    if format_type == "json":
        return json.dumps({
            "files_checked": result.files_checked,
            "entries_checked": result.entries_checked,
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
            level = {Severity.ERROR: 'error', Severity.WARNING: 'warning', Severity.INFO: 'notice'}[issue.severity]
            def escape(value, prop=False):
                value = value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
                return value.replace(':', '%3A').replace(',', '%2C') if prop else value
            lines.append(f"::{level} file={escape(issue.file, True)},line={max(1, issue.line)}::[{issue.rule}] {escape(issue.message)}")
        return '\n'.join(lines)
    
    elif format_type == "gnu":
        # GNU style — Emacs compilation-mode compatible
        # Format: file:line: severity: [rule] message
        lines = []
        for issue in sorted(result.issues, key=lambda x: (x.file, x.line)):
            severity = "error" if issue.severity == Severity.ERROR else "warning" if issue.severity == Severity.WARNING else "info"
            lines.append(f"{issue.file}:{issue.line}: {severity}: [{issue.rule}] {issue.message}")
        if lines:
            lines.append("")
            lines.append(f"{result.files_checked} file(s), {result.error_count} error(s), {result.warning_count} warning(s)")
        else:
            lines.append(f"{result.files_checked} file(s) checked, no issues found.")
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
    from l10n_project import (load_config, read_glossary, read_translation_memory, filter_baseline, write_baseline,
                              preview_fixes, apply_fixes, excluded)
    preliminary = argparse.ArgumentParser(add_help=False)
    preliminary.add_argument('--config')
    known, _unused = preliminary.parse_known_args()
    parser = argparse.ArgumentParser(description=_('Linter for PO, Qt TS, XLIFF, and JSON localization files'))
    parser.add_argument('paths', nargs='*')
    parser.add_argument('--config', help='Project TOML file (default: nearest pyproject.toml)')
    parser.add_argument('--github', '-g', metavar='REPO')
    parser.add_argument('--changed', metavar='BASE', help='Lint localization files changed since this Git revision')
    parser.add_argument('--path', '-p', default='', help='GitHub path filter')
    parser.add_argument('--format', '-f', choices=['text', 'json', 'html', 'github', 'gnu', 'sarif'], default='text')
    parser.add_argument('--output', '-o')
    parser.add_argument('--max-length', type=int, default=500)
    parser.add_argument('--length-ratio', type=float, default=3.0)
    parser.add_argument('--language', help='Override target language, e.g. sv or pt_BR')
    parser.add_argument('--json-format', choices=['auto', 'nested', 'entries'],
                        help='Allow automatic, nested-only, or explicit-entry JSON catalogs')
    parser.add_argument('--translation-memory', help='JSON source-to-translation memory for consistency checks')
    parser.add_argument('--no-recursive', action='store_true')
    parser.add_argument('--strict', action='store_true', help='Return error status for warnings over the threshold')
    parser.add_argument('--max-errors', type=int, default=0)
    parser.add_argument('--max-warnings', type=int, default=0)
    parser.add_argument('--quiet', '-q', action='store_true')
    parser.add_argument('--check', action='store_true', help='Exit status only')
    parser.add_argument('--skip-fuzzy', action='store_true', help='Suppress fuzzy warnings')
    parser.add_argument('--disable', default='')
    parser.add_argument('--checks', help='Run only these rules/groups (comma-separated)')
    parser.add_argument('--skip-checks', default='')
    parser.add_argument('--list-rules', action='store_true')
    parser.add_argument('--terminology', action='store_true', default=True)
    parser.add_argument('--no-terminology', action='store_false', dest='terminology')
    parser.add_argument('--glossary', help='TSV: wrong<TAB>correct[<TAB>context]')
    parser.add_argument('--exclude', action='append', default=[], help='Project-relative glob, repeatable')
    parser.add_argument('--baseline', help='Report only findings absent from this baseline')
    parser.add_argument('--write-baseline', metavar='FILE', help='Save current findings before baseline filtering')
    parser.add_argument('--reference', help='Compare with a .pot/.po, .ts, .xlf/.xliff, or .json source catalog')
    parser.add_argument('--fix', metavar='RULES', help='Preview local PO fixes: whitespace,ellipsis (diff on stderr)')
    parser.add_argument('--apply', action='store_true', help='Apply the fixes requested by --fix, then lint again')
    parser.add_argument('--verbose', '-V', action='store_true')
    parser.add_argument('--gtk', '-G', action='store_true')
    parser.add_argument('--version', '-v', action='version', version=f'%(prog)s {__version__}')
    try:
        defaults, root = load_config(known.config)
        severity = defaults.pop('severity', {})
        overrides = {}
        for rule, value in severity.items():
            if value not in ('error', 'warning', 'info'):
                raise ValueError(f'Invalid severity for {rule}: {value}')
            for rule_id in resolve_rules([rule]):
                overrides[rule_id] = value
        parser.set_defaults(**defaults)
        args = parser.parse_args()
        if args.format not in ('text', 'json', 'html', 'github', 'gnu', 'sarif'):
            raise ValueError('Unknown output format')
        if args.max_length <= 0 or args.length_ratio <= 0 or args.max_errors < 0 or args.max_warnings < 0:
            raise ValueError('Invalid length or diagnostic threshold')
        disabled = resolve_rules(args.disable) | resolve_rules(args.skip_checks)
        if args.checks is not None:
            disabled |= set(RULES) - resolve_rules(args.checks)
        if not args.terminology:
            disabled |= resolve_rules(['terminology', 'domain-terminology', 'false-friends', 'consistency'])
        if args.skip_fuzzy:
            disabled.add('fuzzy')
        config = {'max_length': args.max_length, 'length_ratio': args.length_ratio,
                  'language': args.language, 'severity': overrides, 'reference': args.reference,
                  'json_format': args.json_format or 'auto',
                  'required_terms': args.required_terms if hasattr(args, 'required_terms') else [],
                  'forbidden_terms': args.forbidden_terms if hasattr(args, 'forbidden_terms') else [],
                  'glossary_terms': read_glossary(args.glossary) if args.glossary else []}
        if args.translation_memory:
            config['translation_memory'] = read_translation_memory(args.translation_memory)
        if args.list_rules:
            for rule, spec in RULES.items():
                print(f'{rule:30} {spec.severity:8} {spec.language or "all":4} {spec.description}')
            return 0
        if args.gtk:
            try:
                from l10n_lint_gtk import main as gtk_main
            except (ImportError, ValueError) as exc:
                raise ValueError(f'GTK interface unavailable: {exc}') from exc
            return gtk_main([sys.argv[0], *args.paths])
        if args.changed:
            import subprocess
            try:
                changed = subprocess.check_output(
                    ['git', 'diff', '--name-only', f'{args.changed}...HEAD'], text=True, cwd=root).splitlines()
            except subprocess.CalledProcessError as exc:
                raise ValueError(f'Cannot determine changed files from {args.changed}: {exc}') from exc
            args.paths.extend(str(root / path) for path in changed if Path(path).suffix.lower() in L10N_EXTENSIONS)
            if not args.paths and not args.github:
                return 0
        if not args.paths and not args.github:
            parser.error('Specify translation files, directories or --github')
        if args.apply and not args.fix:
            raise ValueError('--apply requires --fix')
        if args.fix:
            fix_rules = set(args.fix.split(','))
            if not fix_rules or fix_rules - {'whitespace', 'ellipsis'}:
                raise ValueError('--fix accepts whitespace,ellipsis')
            if args.github or any(is_url(p) for p in args.paths):
                raise ValueError('--fix requires local PO files')
            previews = {}
            # Validate every input before applying any changes.
            for path in args.paths:
                for filename in find_l10n_files(path, not args.no_recursive):
                    if not excluded(filename, args.exclude, root):
                        previews[str(Path(filename).resolve())] = preview_fixes(filename, fix_rules)
            for filename, (original, updated, diff) in previews.items():
                if diff and not args.check:
                    print(diff, end='', file=sys.stderr)
            if args.apply:
                for filename, (original, updated, diff) in previews.items():
                    apply_fixes(filename, original, updated)
        start = time.monotonic()
        result = lint_inputs(args.paths, args.github, args.path, config, disabled,
                             not args.no_recursive, args.exclude, root,
                             (lambda path: print(f'Checked {path}', file=sys.stderr)) if args.verbose and not args.check else None)
        if args.write_baseline:
            write_baseline(result, args.write_baseline, root)
        if args.baseline:
            filter_baseline(result, args.baseline, root)
        if not args.check:
            output = (f'{result.files_checked} file(s), {result.error_count} error(s), {result.warning_count} warning(s)'
                      if args.quiet else format_output(result, args.format))
            if args.output:
                Path(args.output).write_text(output + '\n', encoding='utf-8')
            else:
                print(output)
            if args.verbose:
                print(f'{result.entries_checked} entries in {time.monotonic() - start:.2f}s', file=sys.stderr)
        if any(i.rule in OPERATIONAL_RULES for i in result.issues) or result.error_count > args.max_errors:
            return 2
        if result.warning_count > args.max_warnings:
            return 2 if args.strict else 1
        return 0
    except (OSError, ValueError, SyntaxError) as exc:
        print(f'l10n-lint: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
