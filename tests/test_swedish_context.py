"""Regressions for Swedish checks, including Qt keys and menu context."""
import json
from pathlib import Path
import subprocess
import sys
from xml.sax.saxutils import escape

import pytest

from l10n_lint import L10nLinter, RULES, resolve_rules


def catalog(source, translation, context='', kind='po'):
    if kind == 'ts':
        return ('<TS language="sv"><context><name>App</name><message><comment>'
                + escape(context) + '</comment><source>' + escape(source)
                + '</source><translation>' + escape(translation)
                + '</translation></message></context></TS>')
    return ('msgid ""\nmsgstr "Language: sv\\n"\n\n'
            + ('msgctxt ' + json.dumps(context, ensure_ascii=False) + '\n' if context else '')
            + 'msgid ' + json.dumps(source, ensure_ascii=False) + '\nmsgstr '
            + json.dumps(translation, ensure_ascii=False) + '\n')


def lint(source, translation, context='', kind='po', checks=('typo', 'terminology')):
    return L10nLinter(disabled_rules=set(RULES) - resolve_rules(checks)).lint_file(
        'sv.' + kind, catalog(source, translation, context, kind))


@pytest.mark.parametrize('fmt', [
    'dd/mm/yyyy', 'yyyy-mm-dd', 'dd.mm.yyyy', 'mm/dd/yyyy',
    'yyyy/mm/dd', 'dd/mm/yy', 'yy-mm-dd', 'YYYY-MM-DD',
    'åååå-mm-dd', 'dddd mmmm yyyy',
])
@pytest.mark.parametrize('kind', ['po', 'ts'])
def test_date_tokens_are_not_typos(fmt, kind):
    assert not lint('Date: ' + fmt, 'Datum: ' + fmt, kind=kind).issues


@pytest.mark.parametrize('word', ['kommmando', 'felyyyyaktig'])
def test_date_exception_does_not_hide_real_typos(word):
    result = lint('Date: yyyy-mm-dd', word + ' yyyy-mm-dd')
    assert [i.rule for i in result.issues] == ['typo']
    assert word in result.issues[0].message


def test_date_and_placeholder_validation_remains_active():
    assert any(i.rule == 'date-format' for i in lint(
        'Date: 09/17/2026', 'Datum: 09/17/2026', checks=('date-format',)).issues)
    assert any(i.rule == 'placeholder-mismatch' for i in lint(
        'Date: yyyy-mm-dd %s', 'Datum: yyyy-mm-dd %d', checks=('typo', 'placeholders')).issues)


@pytest.mark.parametrize('source,translation,context,warning', [
    ('View', 'Vy', 'Color Management', False),
    ('View', 'Vy', '', False),
    ('View', 'Vy', '3D View', False),
    ('View', 'Vy', 'menu', True),
    ('View', 'Vy', 'main_menu', True),
    ('View', 'Vy', 'Menu bar', True),
    ('View', 'Visa', 'menu', False),
    ('File', 'Fil', '', False),
    ('File', 'Fil', 'command category', False),
    ('File', 'Fil', 'menu', True),
    ('File', 'Fil', 'main_menu', True),
    ('File', 'Arkiv', 'menu', False),
    ('sweep-line solver', 'sveplinjelösaren', '', False),
    ('sweep-line solver', 'lösaren för svepande linjer', '', False),
    ('Draw lines', 'Rita linjer', '', False),
    ('Line number', 'Linjenummer', 'Geometry', False),
    ('A point on line A', 'En punkt på linje A', '', False),
    ('Command line', 'Kommandolinje', '', True),
    ('Command-line options', 'Alternativ för kommandolinjen', '', True),
    ('Lines of source code', 'Linjer med källkod', '', True),
    ('Source code line', 'Källkodslinje', '', True),
    ('Line', 'Linje', 'Code editor', True),
    ('Lines', 'Linjer', 'source_code', True),
    ('Insert a line', 'Infoga en linje', 'CLI', True),
    ('Syntax error on line 5', 'Syntaxfel på linje 5', '', True),
    ('Command line', 'Kommandorad', '', False),
    ('Command line guidelines', 'Riktlinjer för kommandoraden', '', False),
])
@pytest.mark.parametrize('kind', ['po', 'ts'])
def test_terminology_requires_relevant_context(source, translation, context, warning, kind):
    result = lint(source, translation, context, kind)
    assert [i.rule for i in result.issues] == (['terminology'] if warning else [])


def test_context_does_not_leak_between_entries():
    first = catalog('View', 'Vy', 'menu')
    second = 'msgid "View"\nmsgstr "Vy"\n'
    result = L10nLinter(disabled_rules=set(RULES) - {'terminology'}).lint_file(
        'sv.po', first + '\n' + second)
    assert len(result.issues) == 1


def test_empty_ts_key_is_not_a_missing_translation():
    text = ('<TS language="sv"><context><name>FreeCAD</name><message>'
            '<source></source><translation></translation></message></context></TS>')
    result = L10nLinter().lint_file('FreeCAD_sv.ts', text)
    assert result.entries_checked == 0
    assert not result.issues


def test_empty_ts_translation_for_real_source_is_still_reported():
    text = ('<TS language="sv"><context><name>FreeCAD</name><message>'
            '<source>File</source><translation></translation></message></context></TS>')
    result = L10nLinter().lint_file('FreeCAD_sv.ts', text)
    assert result.entries_checked == 1
    assert [issue.rule for issue in result.issues] == ['missing-translation']


def test_ts_context_name_identifies_a_file_menu():
    text = ('<TS language="sv"><context><name>Main Menu</name><message>'
            '<source>File</source><translation>Fil</translation>'
            '</message></context></TS>')
    result = L10nLinter(disabled_rules=set(RULES) - {'terminology'}).lint_file('FreeCAD_sv.ts', text)
    assert [issue.rule for issue in result.issues] == ['terminology']


def test_reported_examples_pass_strict_cli(tmp_path):
    for index, (source, translation, context) in enumerate([
        ('Date: dd/mm/yyyy', 'Datum: dd/mm/yyyy', ''),
        ('View', 'Vy', 'Color Management'),
        ('sweep-line solver', 'sveplinjelösaren', ''),
    ]):
        (tmp_path / f'sv-{index}.po').write_text(catalog(source, translation, context), encoding='utf-8')
    result = subprocess.run([
        sys.executable, str(Path(__file__).resolve().parents[1] / 'l10n_lint.py'),
        '--checks', 'typo,terminology', '--strict', '--check', str(tmp_path),
    ], cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_other_swedish_terminology_is_preserved():
    assert any(i.rule == 'terminology' for i in lint('Editor', 'Redaktör').issues)
