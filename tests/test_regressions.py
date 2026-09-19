"""Regression tests through parsers, input collection, CLI and packaging APIs."""
import ast
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch
import urllib.error

import pytest
import l10n_lint as core
from l10n_lint import L10nLinter, POParser, LintIssue, LintResult, Severity, RULES, resolve_rules, lint_inputs
from l10n_project import (placeholder_signature, preview_fixes, apply_fixes, write_baseline,
                          filter_baseline, sarif_report)

ROOT = Path(__file__).resolve().parents[1]
HEADER = 'msgid ""\nmsgstr "Language: sv\\nPlural-Forms: nplurals=2; plural=(n != 1);\\n"\n\n'


def po(source='Hello', translation='Hej', flags=''):
    return HEADER + (f'#, {flags}\n' if flags else '') + f'msgid {json.dumps(source, ensure_ascii=False)}\nmsgstr {json.dumps(translation, ensure_ascii=False)}\n'


def lint(content, name='sv.po', checks=None, config=None):
    disabled = set(RULES) - resolve_rules(checks) if checks is not None else set()
    return L10nLinter(config, disabled).lint_file(name, content)


def cli(tmp_path, *args):
    return subprocess.run([sys.executable, str(ROOT / 'l10n_lint.py'), *map(str, args)],
                          cwd=tmp_path, capture_output=True, text=True)


@pytest.mark.parametrize('content,name', [
    ('garbage', 'broken.po'), ('<TS><context>', 'broken.ts'),
    ('<html/>', 'wrong.ts'), ('msgid "x\nmsgstr "y"', 'broken.po'),
    ('msgid "x"\nmsgstr "y" trailing', 'broken.po'),
    ('msgid "x"\nmsgstr "bad\\q"', 'broken.po'),
    ('msgstr "y"', 'broken.po'), ('msgid "x"', 'broken.po'),
])
def test_invalid_files_always_report_errors(content, name):
    result = lint(content, name, checks=[])
    assert result.error_count == 1
    assert result.issues[0].rule == 'syntax-error'


def test_po_no_blank_lines_escapes_context_and_obsolete():
    text = 'msgctxt "menu"\nmsgid "one"\nmsgstr "ett"\nmsgid "two"\nmsgstr "två\\\\n"\n\n#~ msgid "old"\n#~ msgstr "gammal"\n'
    entries = POParser(text).entries
    assert len(entries) == 2
    assert entries[0]['msgctxt'] == 'menu'
    assert entries[1]['msgstr'] == 'två\\n'
    assert entries[1]['_line'] == 4


@pytest.mark.parametrize('source,target,flags,trigger', [
    ('%1$s', '%1$d', 'c-format', True),
    ('Hello', 'Hej %s', 'c-format', True),
    ('%s %d', '%d %s', 'c-format', True),
    ('%s %d', '%2$d %1$s', 'c-format', False),
    ('%1$s %2$d', '%2$d %1$s', 'c-format', False),
    ('%s %s', '%s', 'c-format', True),
    ('%lld', '%d', 'c-format', True),
    ('%*.*f', '%f', 'c-format', True),
    ('%*.*f', '%3$*1$.*2$f', 'c-format', False),
    ('%%s', '%%d', 'c-format', False),
    ('%<PRIu64>', '%<PRIu32>', 'c-format', True),
    ('%<PRIu64>', '%<PRId64>', 'c-format', True),
    ('%<PRId64>', '%<PRIi64>', 'c-format', False),
    ('%<PRIu64>', '%u', 'c-format', True),
    ('%<PRIu64>', 'antal', 'c-format', True),
    ('%<PRIu64> %s', '%s %<PRIu64>', 'c-format', True),
    ('%<PRIu64> %s', '%2$s %1$<PRIu64>', 'c-format', False),
    ('%4<PRIu64> %s', '%4<PRIu64> %s', 'c-format', False),
    ('%*.*<PRIxMAX>', '%3$*1$.*2$<PRIxMAX>', 'c-format', False),
    ('%<PRIdFAST16>', '%<PRIdLEAST16>', 'c-format', True),
    ('%<PRIuPTR>', 'värde', 'c-format', True),
    ('%%<PRIu64>', '%%<PRIu32>', 'c-format', False),
    ('{name}', '{other}', 'python-brace-format', True),
    ('{value:.2f}', '{value:.2d}', 'python-brace-format', True),
    ('{value:{width}}', '{value:{height}}', 'python-brace-format', True),
    ('{{name}}', '{{other}}', 'python-brace-format', False),
    ('{a} {b}', '{b} {a}', 'python-brace-format', False),
    ('%(name)s', '%(name)d', 'python-format', True),
    ('%L1 %n', '%1 %n', 'qt-format', True),
    ('%1 %2', '%2 %1', 'qt-format', False),
])
def test_format_arguments(source, target, flags, trigger):
    result = lint(po(source, target, flags), checks=['placeholders'])
    assert bool(result.error_count) == trigger, result.issues


def test_plural_all_forms_receive_shared_rules():
    text = HEADER + 'msgid "Visit https://example.org"\nmsgid_plural "Visit https://example.org"\nmsgstr[0] "Besök https://example.org"\nmsgstr[1] "Besök hemsidan"\n'
    assert any(i.rule == 'url-preservation' for i in lint(text).issues)


def test_plural_hole_is_reported():
    text = HEADER + 'msgid "File"\nmsgid_plural "Files"\nmsgstr[1] "Filer"\n'
    assert any(i.rule == 'plural-forms-missing' for i in lint(text).issues)


def test_icu_messageformat_is_not_parsed_as_python_and_variables_must_match():
    source = '{rating, plural, =0 {Star Rating} other {# Star Ratings}}. {label}'
    target = '{rating, plural, =0 {Stjärnbetyg} other {# Stjärnbetyg}}. {label}'
    assert not lint(po(source, target), checks=['placeholders']).issues
    changed = target.replace('{rating, plural', '{count, plural')
    issues = lint(po(source, changed), checks=['placeholders']).issues
    assert any(issue.rule == 'placeholder-mismatch' and '(icu)' in issue.message for issue in issues)


def test_project_memory_terms_and_unicode_integrity():
    config = {
        'translation_memory': {'Save document': 'Spara dokument'},
        'required_terms': [{'source': 'Save', 'target': 'Spara'}],
        'forbidden_terms': ['Dokumentera'],
    }
    result = lint(po('Save document', 'Dokumentera\u202e'), config=config)
    assert {'consistency', 'required-term-missing', 'forbidden-term', 'bidi-control'} <= {issue.rule for issue in result.issues}


def ts(translations, type_='', numerus=True):
    return '<TS language="sv"><context><name>App</name>\n<message' + (' numerus="yes"' if numerus else '') + '><source>%n file(s)</source>\n<translation type="' + type_ + '">' + translations + '</translation></message></context></TS>'


def test_ts_plurals_and_real_line_numbers():
    result = lint(ts('<numerusform>%n fil</numerusform><numerusform>%n filer</numerusform>'), 'sv.ts', ['missing-translation','placeholders'])
    assert result.entries_checked == 1 and not result.issues
    result = lint(ts('<numerusform>%n fil</numerusform><numerusform>filer</numerusform>'), 'sv.ts', ['placeholders'])
    assert result.error_count == 1 and result.issues[0].line == 2


@pytest.mark.parametrize('type_', ['vanished', 'obsolete'])
def test_removed_ts_messages_do_not_fail(type_):
    result = lint(ts('', type_), 'sv.ts')
    assert result.error_count == 0 and result.entries_checked == 0


def test_ts_empty_plural_fails():
    assert lint(ts('<numerusform>%n fil</numerusform><numerusform/>'), 'sv.ts').error_count > 0


def test_contexts_do_not_conflict():
    text = HEADER + 'msgctxt "a"\nmsgid "Open document"\nmsgstr "Öppna dokument"\n\nmsgctxt "b"\nmsgid "Open document"\nmsgstr "Öppet dokument"\n'
    assert not lint(text, checks=['consistency','duplicate']).issues


def test_cli_missing_empty_paths_and_unknown_rule(tmp_path):
    assert cli(tmp_path, 'missing.po', '--check').returncode == 2
    assert cli(tmp_path, tmp_path, '--check').returncode == 2
    assert cli(tmp_path, '--checks', 'tyop', 'missing.po').returncode == 2


def test_cli_selection_and_glossary(tmp_path):
    p = tmp_path / 'sv.po'; p.write_text(po('Hello %s', 'Hej'))
    assert cli(tmp_path, '--checks', 'terminology', p, '--check').returncode == 0
    assert cli(tmp_path, '--checks', 'placeholders', p, '--check').returncode == 2
    assert cli(tmp_path, '--glossary', 'missing.tsv', p).returncode == 2
    glossary = tmp_path / 'words.tsv'; glossary.write_text('Hej\tGoddag\tFormal greeting\n')
    result = cli(tmp_path, '--checks', 'glossary', '--glossary', glossary, '-f', 'json', p)
    assert result.returncode == 1
    assert [i['rule'] for i in json.loads(result.stdout)['issues']] == ['glossary']


def test_config_relative_paths_severity_excludes_and_cli_override(tmp_path):
    (tmp_path / 'words.tsv').write_text('Hej\tGoddag\n')
    (tmp_path / 'pyproject.toml').write_text('''[tool.l10n-lint]
checks = ["glossary"]
glossary = "words.tsv"
exclude = ["generated/**"]
max-warnings = 0
[tool.l10n-lint.severity]
glossary = "error"
''')
    p = tmp_path / 'sv.po'; p.write_text(po())
    generated = tmp_path / 'generated'; generated.mkdir(); (generated / 'bad.po').write_text('broken')
    output = cli(tmp_path, '-f', 'json', tmp_path)
    assert output.returncode == 2
    data = json.loads(output.stdout)
    assert data['files_checked'] == 1 and data['errors'] == 1
    assert cli(tmp_path, '--checks', 'placeholders', p, '--check').returncode == 0
    assert cli(tmp_path, '--max-errors', '1', p, '--check').returncode == 0


@pytest.mark.parametrize('option', ['unknown = true', 'checks = [2]', 'max-errors = -1', 'max-length = false'])
def test_invalid_config(tmp_path, option):
    (tmp_path / 'pyproject.toml').write_text('[tool.l10n-lint]\n' + option)
    result = cli(tmp_path, 'missing.po')
    assert result.returncode == 2 and 'Traceback' not in result.stderr


def test_baseline_survives_line_shifts_preserves_counts_and_io_errors(tmp_path):
    p = tmp_path / 'sv.po'; p.write_text(po('Hello %s', 'Hej'))
    baseline = tmp_path / 'baseline.json'
    first = cli(tmp_path, '--checks', 'placeholders', '--write-baseline', baseline, p, '--check')
    assert first.returncode == 2
    p.write_text('\n\n' + p.read_text())
    assert cli(tmp_path, '--checks', 'placeholders', '--baseline', baseline, p, '--check').returncode == 0
    p.write_text(p.read_text() + '\nmsgid "Hello %s"\nmsgstr "Hej"\n')
    assert cli(tmp_path, '--checks', 'placeholders', '--baseline', baseline, p, '--check').returncode == 2
    assert cli(tmp_path, '--baseline', baseline, 'missing.po', '--max-errors', '100', '--check').returncode == 2


def test_catalog_comparison(tmp_path):
    reference = tmp_path / 'source.pot'
    reference.write_text('msgid "Hello"\nmsgstr ""\n\nmsgid "New"\nmsgstr ""\n')
    p = tmp_path / 'sv.po'; p.write_text(po() + '\nmsgid "Old"\nmsgstr "Gammal"\n')
    output = cli(tmp_path, '--checks', 'catalog-missing,catalog-obsolete', '--reference', reference, '-f', 'json', p)
    assert {i['rule'] for i in json.loads(output.stdout)['issues']} == {'catalog-missing', 'catalog-obsolete'}
    assert cli(tmp_path, '--reference', 'absent.pot', p, '--check').returncode == 2


def test_fix_preview_apply_preservation_and_idempotence(tmp_path):
    p = tmp_path / 'sv.po'
    original = po('Loading...', ' Laddar... ') + '\n# Translator note\n#, fuzzy\nmsgid "Wait..."\nmsgstr " Vänta... "\n'
    p.write_bytes(original.replace('\n', '\r\n').encode())
    p.chmod(0o640)
    before = p.read_bytes()
    preview = cli(tmp_path, '--fix', 'whitespace,ellipsis', p)
    assert '--- ' in preview.stderr and p.read_bytes() == before
    applied = cli(tmp_path, '--fix', 'whitespace,ellipsis', '--apply', p)
    assert '--- ' in applied.stderr
    data = p.read_bytes()
    assert b'\r\n' in data and b'msgstr "Laddar' in data and 'Laddar…'.encode() in data
    assert b'# Translator note' in data and b'msgstr " V' in data
    assert p.stat().st_mode & 0o777 == 0o640
    assert preview_fixes(p, {'whitespace','ellipsis'})[2] == ''


def test_apply_detects_changed_file(tmp_path):
    p = tmp_path / 'sv.po'; p.write_text(po('Hello', ' Hej '))
    original, updated, diff = preview_fixes(p, {'whitespace'})
    p.write_text('changed externally')
    with pytest.raises(ValueError):
        apply_fixes(p, original, updated)
    assert p.read_text() == 'changed externally'


def test_sarif_and_github_escaping(tmp_path):
    issue = LintIssue(str(tmp_path / 'a b,%.po'), 3, Severity.INFO, 'fuzzy', 'line\none%')
    result = LintResult(issues=[issue])
    data = json.loads(sarif_report(result, tmp_path))
    finding = data['runs'][0]['results'][0]
    assert data['version'] == '2.1.0' and finding['level'] == 'note'
    assert finding['locations'][0]['physicalLocation']['artifactLocation']['uri'] == 'a%20b%2C%25.po'
    annotation = core.format_output(result, 'github')
    assert annotation.startswith('::notice ') and '%0A' in annotation and '%2C' in annotation
    assert len(annotation.splitlines()) == 1


def test_url_content_is_linted_not_local_filename():
    with patch.object(core, 'fetch_url_file', return_value=('sv.po', po('Hello %s','Hej'))):
        result = lint_inputs(['https://example.org/sv.po'])
    assert result.files_checked == 1 and result.entries_checked == 1
    assert any(i.rule == 'placeholder-mismatch' and i.file.startswith('https://') for i in result.issues)
    assert not any(i.rule == 'file-read-error' for i in result.issues)


def test_github_default_branch_and_pinned_revision():
    requests = []
    def fetch(request, timeout):
        url = request.full_url; requests.append(url)
        if url.endswith('/repos/test/project'):
            return io.BytesIO(b'{"default_branch":"release/stable"}')
        if '/git/trees/' in url:
            return io.BytesIO(b'{"sha":"abc123", "tree":[{"type":"blob","path":"po/sv.po"}]}')
        assert '/abc123/po/sv.po' in url
        return io.BytesIO(po().encode())
    with patch('urllib.request.urlopen', side_effect=fetch):
        result = core.lint_github_repo('test/project')
    assert result.files_checked == 1
    assert '/release%2Fstable?' in requests[1]


def test_github_fetch_failure_cannot_pass():
    def failing(*args, **kwargs):
        yield 'sv.po', po()
        raise OSError('network unavailable')
    with patch.object(core, 'fetch_github_files', failing):
        result = lint_inputs(github='a/b', disabled_rules=set(RULES))
    assert result.error_count == 1 and result.issues[0].rule == 'github-fetch-error'


def test_gtk_runner_uses_shared_pipeline():
    """Execute the real worker method without requiring a display or GTK library."""
    tree = ast.parse((ROOT / 'l10n_lint_gtk.py').read_text())
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_run_lint')
    module = ast.Module(body=[method], type_ignores=[])
    namespace = vars(core).copy()
    namespace['GLib'] = SimpleNamespace(idle_add=lambda function, *args: function(*args))
    exec(compile(module, 'gtk_worker', 'exec'), namespace)
    received = []
    worker = SimpleNamespace(settings={'enabled_rules': ['placeholders']},
                             status_label=SimpleNamespace(set_text=lambda text: None),
                             _show_results=received.append)
    with patch.object(core, 'fetch_url_file', return_value=('sv.po', po('Hello %s','Hej'))):
        namespace['_run_lint'](worker, 'https://example.org/sv.po')
    assert received[0].files_checked == 1 and received[0].error_count == 1
    worker.settings['enabled_rules'] = []
    with patch.object(core, 'fetch_url_file', return_value=('sv.po', po('Hello %s','Hej'))):
        namespace['_run_lint'](worker, 'https://example.org/sv.po')
    assert received[-1].files_checked == 1 and not received[-1].issues


def test_python_only_selection_and_unmatched_literal_braces():
    assert lint(po('{name}', '{other}'), checks=['python-format']).error_count == 1
    assert not lint(po('Insert { here', 'Infoga { här'), checks=['placeholders']).issues
    assert lint(po('%1', '%2'), checks=['placeholders']).error_count == 1


def test_url_same_filename_different_origins_are_both_checked():
    with patch.object(core, 'fetch_url_file', return_value=('sv.po', po())):
        result = lint_inputs(['https://a.example/sv.po', 'https://b.example/sv.po'])
    assert result.files_checked == 2


def test_all_rules_fixture_parses():
    result = L10nLinter().lint_file(str(ROOT / 'tests/test_all_rules.po'))
    assert result.entries_checked > 10
    assert not any(i.rule == 'syntax-error' for i in result.issues)


def test_no_files_and_syntax_never_suppressed_by_rule_selection(tmp_path):
    p = tmp_path / 'bad.po'; p.write_text('garbage')
    assert cli(tmp_path, '--checks', 'terminology', '--max-errors', 999, p, '--check').returncode == 2


def test_check_mode_and_strict_thresholds(tmp_path):
    p = tmp_path / 'sv.po'; p.write_text(po('Hello', 'Hej '))
    result = cli(tmp_path, '--checks', 'whitespace', '--check', '--verbose', p)
    assert result.returncode == 1 and result.stdout == '' and result.stderr == ''
    assert cli(tmp_path, '--checks', 'whitespace', '--strict', p, '--check').returncode == 2
    assert cli(tmp_path, '--checks', 'whitespace', '--strict', '--max-warnings', 1, p, '--check').returncode == 0


def test_length_ratio_configuration():
    content = po('Long enough source', 'En ganska mycket längre översättning än originalet')
    assert not lint(content, checks=['length','max-length-ratio'], config={'length_ratio': 10}).issues


def test_fix_preserves_po_control_escapes(tmp_path):
    p = tmp_path / 'sv.po'
    p.write_text('msgid "Bell"\nmsgstr "Ring\\a\\v "\n')
    original, updated, diff = preview_fixes(p, {'whitespace'})
    assert POParser(updated).entries[0]['msgstr'] == 'Ring\a\v'
    assert '\\a\\v' in updated


def test_python_attribute_fields_without_flags():
    assert lint(po('{user.name}', '{user.id}'), checks=['placeholders']).error_count == 1


def test_gtk_cli_receives_only_paths(tmp_path, monkeypatch):
    received = []
    fake = SimpleNamespace(main=lambda argv: received.append(argv) or 0)
    monkeypatch.setitem(sys.modules, 'l10n_lint_gtk', fake)
    monkeypatch.setattr(sys, 'argv', ['l10n-lint', '--gtk', 'sv.po'])
    monkeypatch.chdir(tmp_path)
    assert core.main() == 0
    assert received == [['l10n-lint', 'sv.po']]


def test_false_friend_patron_allows_preserved_capitalized_tier_name():
    result = L10nLinter({'language': 'sv'}).lint_file('sv.json', json.dumps([{
        'source': 'Supporter, Patron and Benefactor',
        'target': 'Supporter, Patron och Benefactor',
    }]))
    assert not any(issue.rule == 'false-friends' for issue in result.issues)
