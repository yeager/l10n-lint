"""Project configuration, format parsing and reviewable lint workflows."""
# SPDX-License-Identifier: GPL-3.0-or-later
from collections import Counter
import difflib
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import string
import tempfile
from urllib.parse import quote


# Gettext represents portable <inttypes.h> conversions as %<PRIu64>,
# including widths/precision/argument positions before the macro.
PRINTF = re.compile(
    r'%(?:(?P<position>\d+)\$|\((?P<name>[^)]+)\))?[-+ #0\']*'
    r'(?P<width>\*(?:\d+\$)?|\d+)?(?:\.(?P<precision>\*(?:\d+\$)?|\d*))?'
    r'(?P<length>hh|ll|[hlLjzt])?'
    r'(?P<type>[diouxXfFeEgGaAcspn%]|<PRI[diouxX](?:(?:LEAST|FAST)?(?:8|16|32|64)|MAX|PTR)>)')


# reST math roles are literal mathematics, not str.format expressions. Both
# prefix and suffix role syntax are valid. Escaped backticks stay inside a role.
REST_MATH = re.compile(
    r'(?<![\w\\]):math:`(?:\\.|[^`])+`'
    r'|(?<![`\\])`(?:\\.|[^`])+`:math:(?!\w)')
REST_LITERAL = re.compile(r'(?<![`\\])``([^`]+)``(?!`)')


def python_format_text(text):
    """Mask only reST math and inline literal brace delimiters for format checks.

    Keep complete fields such as ``{name}`` visible: documentation markup can
    surround real runtime placeholders, and must not hide translation mistakes.
    Other lint rules continue to receive the original, unmodified message.
    """
    text = REST_MATH.sub(lambda match: ' ' * len(match.group()), text)
    def literal(match):
        body = match.group(1)
        if body.strip() and not body.strip(' {}\t\r\n') and '{}' not in body:
            return ' ' * len(match.group())
        return match.group()
    return REST_LITERAL.sub(literal, text)


def _unambiguous_printf(match, text):
    """Unflagged messages need stronger evidence than '% coverage' or '10%s'."""
    token = match.group()
    if any(char.isspace() for char in token):
        return False
    # Positional/named arguments and explicit width/precision are strong signals,
    # even when followed by a literal unit (e.g. %1$dpx or %.2fms).
    if match['position'] or match['name'] or match['width'] or match['precision'] is not None:
        return True
    if match.end() < len(text) and (text[match.end()].isalnum() or text[match.end()] == '_'):
        return False
    # A percent sign following a number is normally a prose percentage. An
    # explicit PO format flag opts into ambiguous conversions in these strings.
    previous = match.start() - 1
    while previous >= 0 and text[previous].isspace():
        previous -= 1
    if previous >= 0 and text[previous].isdigit():
        return False
    return True


def placeholder_signature(text, kind, *, explicit=True):
    """Compare argument identities/types/counts, allowing explicit reordering."""
    if kind == 'qt':
        return sorted(Counter(re.findall(r'%(?:L?(?:[1-9]\d?|n))', text)).items())
    if kind == 'printf':
        args, sequential = [], 1
        # %% consumes no argument and must not be reconsidered as a placeholder.
        for match in PRINTF.finditer(text):
            if match['type'] == '%' or (not explicit and not _unambiguous_printf(match, text)):
                continue
            for field in ('width', 'precision'):
                value = match[field] or ''
                if value.startswith('*'):
                    index = value[1:-1] if value.endswith('$') else str(sequential)
                    if not value.endswith('$'):
                        sequential += 1
                    args.append((index, 'int'))
            index = match['name'] or match['position'] or str(sequential)
            if not (match['name'] or match['position']):
                sequential += 1
            type_ = ('int' if match['type'] in 'di' else match['type'])
            if type_.startswith('<PRIi'):
                type_ = '<PRId' + type_[5:]  # PRIdN and PRIiN consume the same type.
            args.append((index, (match['length'] or '') + type_))
        return sorted(Counter(args).items())
    args, automatic = [], [0]
    def visit(value, depth=0):
        if depth > 10:
            raise ValueError('format specification is nested too deeply')
        for literal, name, spec, conversion in string.Formatter().parse(value):
            if name is None:
                continue
            if name == '':
                name = str(automatic[0]); automatic[0] += 1
            # Preserve conversion and static format spec; recursively inspect
            # dynamic width/precision arguments such as {value:{width}.2f}.
            args.append((name, conversion or '', re.sub(r'\{[^{}]*\}', '{}', spec)))
            if '{' in spec or '}' in spec:
                visit(spec, depth + 1)
    visit(text)
    return sorted(Counter(args).items())


def load_config(filename=None, start=None):
    """Find nearest pyproject.toml; explicit config paths never silently fail."""
    import sys
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib
    if filename:
        path = Path(filename).resolve()
    else:
        start = Path(start or Path.cwd()).resolve()
        path = next((p / 'pyproject.toml' for p in (start, *start.parents)
                     if (p / 'pyproject.toml').is_file()), None)
    if path is None:
        return {}, Path(start or Path.cwd()).resolve()
    with path.open('rb') as stream:
        raw = tomllib.load(stream).get('tool', {}).get('l10n-lint', {})
    if not isinstance(raw, dict):
        raise ValueError('[tool.l10n-lint] must be a table')
    fields = {
        'language': str, 'checks': list, 'disable': list, 'exclude': list,
        'glossary': str, 'baseline': str, 'reference': str, 'format': str,
        'max-length': int, 'length-ratio': (int, float),
        'max-errors': int, 'max-warnings': int, 'strict': bool,
        'severity': dict,
    }
    for key, value in raw.items():
        if key not in fields:
            raise ValueError(f'Unknown configuration option: {key}')
        if not isinstance(value, fields[key]) or (isinstance(value, bool) and fields[key] != bool):
            raise ValueError(f'Invalid value for {key}')
        if isinstance(value, list) and not all(isinstance(v, str) for v in value):
            raise ValueError(f'{key} must contain strings')
        if key in ('max-length', 'length-ratio') and value <= 0:
            raise ValueError(f'{key} must be positive')
        if key in ('max-errors', 'max-warnings') and value < 0:
            raise ValueError(f'{key} cannot be negative')
    config = {k.replace('-', '_'): v for k, v in raw.items()}
    for key in ('glossary', 'baseline', 'reference'):
        if key in config:
            config[key] = str(path.parent / config[key])
    for key in ('checks', 'disable'):
        if key in config:
            config[key] = ','.join(config[key])
    return config, path.parent


def read_glossary(path):
    terms = []
    for number, line in enumerate(Path(path).read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        fields = line.split('\t')
        if len(fields) not in (2, 3) or not fields[0].strip() or not fields[1].strip():
            raise ValueError(f'{path}:{number}: expected wrong<TAB>correct[<TAB>context]')
        terms.append(tuple(v.strip() for v in fields) + (('',) if len(fields) == 2 else ()))
    return terms


def relative_path(file, root):
    if file.startswith(('http://', 'https://')):
        return file
    return os.path.relpath(Path(file).resolve(), Path(root).resolve()).replace(os.sep, '/')


def excluded(file, patterns, root):
    relative = relative_path(file, root)
    return any(fnmatch.fnmatchcase(relative, pattern) or
               (pattern.endswith('/**') and relative.startswith(pattern[:-2]))
               for pattern in patterns)


def fingerprint(issue, root):
    payload = [relative_path(issue.file, root), issue.rule, issue.severity.value,
               issue.context, issue.message]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def write_baseline(result, path, root):
    from l10n_lint import OPERATIONAL_RULES
    counts = Counter(fingerprint(i, root) for i in result.issues if i.rule not in OPERATIONAL_RULES)
    Path(path).write_text(json.dumps({'version': 1, 'issues': dict(sorted(counts.items()))}, indent=2) + '\n', encoding='utf-8')


def filter_baseline(result, path, root):
    from l10n_lint import OPERATIONAL_RULES
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('issues'), dict):
        raise ValueError('Unsupported baseline; generate one with --write-baseline')
    if any(not re.fullmatch(r'[0-9a-f]{64}', key) or type(value) is not int or value < 1
           for key, value in data['issues'].items()):
        raise ValueError('Invalid baseline issue counts')
    remaining = Counter(data['issues']); visible = []
    for issue in result.issues:
        key = fingerprint(issue, root)
        if issue.rule not in OPERATIONAL_RULES and remaining[key]:
            remaining[key] -= 1
        else:
            visible.append(issue)
    result.issues = visible


def compare_catalog(filepath, content, reference_path, result):
    from l10n_lint import POParser, TSParser, LintIssue, Severity
    def entries(path, text):
        if Path(path).suffix.lower() in ('.po', '.pot'):
            return {('po', e.get('msgctxt', ''), e['msgid']): (e.get('msgid_plural', ''), e['_line'])
                    for e in POParser(text, path).entries if e.get('msgid')}
        if Path(path).suffix.lower() == '.ts':
            return {('ts', e['_id'] or e['_context'], '' if e['_id'] else e['source']):
                    ((e['source'], e['_numerus']), e['_line'])
                    for e in TSParser(text, path).entries if e['_type'] not in ('vanished', 'obsolete')}
        raise ValueError('Reference must be .pot, .po or .ts')
    if (Path(filepath).suffix.lower() == '.ts') != (Path(reference_path).suffix.lower() == '.ts'):
        raise ValueError('Reference and translation must use the same catalog format')
    source = entries(reference_path, Path(reference_path).read_text(encoding='utf-8-sig'))
    target = entries(filepath, content)
    for key in sorted(source.keys() - target.keys()):
        result.add(LintIssue(filepath, 1, Severity.ERROR, 'catalog-missing',
            f'Missing catalog entry: {key[-1] or key[1]}', repr(key)))
    for key in sorted(target.keys() - source.keys()):
        result.add(LintIssue(filepath, target[key][1], Severity.WARNING, 'catalog-obsolete',
            f'Entry is absent from reference: {key[-1] or key[1]}', repr(key)))
    for key in source.keys() & target.keys():
        if source[key][0] != target[key][0]:
            result.add(LintIssue(filepath, target[key][1], Severity.ERROR, 'catalog-plural-changed',
                'Source or plural definition differs from reference', repr(key)))


def preview_fixes(path, enabled):
    """Conservative PO edits only: preserve source, comments and unrelated bytes."""
    from l10n_lint import POParser
    path = Path(path)
    if path.suffix.lower() != '.po':
        raise ValueError('--fix currently supports local PO files only')
    if path.is_symlink():
        raise ValueError('Refusing to rewrite a symlink')
    original = path.read_bytes().decode('utf-8')
    parser = POParser(original, str(path))
    lines = original.splitlines(keepends=True)
    edits = []
    newline = '\r\n' if '\r\n' in original else '\n'
    for entry in parser.entries:
        if not entry.get('msgid') or 'fuzzy' in entry.get('_flags', []):
            continue
        for key, (start, end) in entry['_spans'].items():
            if not key.startswith('msgstr') or not entry[key]:
                continue
            source = entry.get('msgid_plural', entry['msgid']) if key not in ('msgstr', 'msgstr[0]') else entry['msgid']
            old, new = entry[key], entry[key]
            if 'whitespace' in enabled:
                if not source.startswith((' ', '\t', '\n', '\r')):
                    new = new.lstrip(' \t')
                if not source.endswith((' ', '\t', '\n', '\r')):
                    new = new.rstrip(' \t')
            if 'ellipsis' in enabled and source.endswith(('...', '…')) and new.endswith('...') and not new.endswith('....'):
                new = new[:-3] + '…'
            if new != old:
                suffix = newline if lines[end - 1].endswith(('\n', '\r')) else ''
                escapes = {'\\': r'\\', '"': r'\"', '\n': r'\n', '\r': r'\r',
                           '\t': r'\t', '\b': r'\b', '\f': r'\f', '\a': r'\a', '\v': r'\v'}
                encoded = '"' + ''.join(escapes.get(char, char) for char in new) + '"' 
                edits.append((start, end, key + ' ' + encoded + suffix))
    for start, end, value in reversed(edits):
        lines[start:end] = [value]
    updated = ''.join(lines)
    if original.startswith('\ufeff') and not updated.startswith('\ufeff'):
        updated = '\ufeff' + updated
    POParser(updated, str(path))
    diff = ''.join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True),
                                       fromfile=str(path), tofile=str(path)))
    return original, updated, diff


def apply_fixes(path, original, updated):
    path = Path(path)
    if path.is_symlink() or path.read_bytes() != original.encode('utf-8'):
        raise ValueError('File changed since fix preview; refusing to overwrite')
    if updated == original:
        return
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(updated.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sarif_report(result, root=None):
    from l10n_lint import RULES, __version__
    ids = sorted({i.rule for i in result.issues})
    rules = [{'id': rule, 'shortDescription': {'text': RULES[rule].description if rule in RULES else rule}}
             for rule in ids]
    findings = []
    for issue in result.issues:
        uri = issue.file if issue.file.startswith(('http://', 'https://')) else quote(relative_path(issue.file, root or Path.cwd()), safe='/')
        location = {'artifactLocation': {'uri': uri}}
        if issue.line > 0:
            location['region'] = {'startLine': issue.line}
        findings.append({'ruleId': issue.rule, 'ruleIndex': ids.index(issue.rule),
                         'level': {'error': 'error', 'warning': 'warning', 'info': 'note'}[issue.severity.value],
                         'message': {'text': issue.message}, 'locations': [{'physicalLocation': location}]})
    return json.dumps({'$schema': 'https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json', 'version': '2.1.0',
                       'runs': [{'tool': {'driver': {'name': 'l10n-lint', 'version': __version__, 'rules': rules}},
                                 'results': findings}]}, indent=2)
