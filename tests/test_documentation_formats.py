"""Issues #3/#5: prose percentages; issue #4: reST math and literal braces."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from l10n_lint import L10nLinter, RULES, resolve_rules
from l10n_project import python_format_text

ROOT = Path(__file__).resolve().parents[1]
HEADER = ('msgid ""\nmsgstr "Language: sv\\nMIME-Version: 1.0\\n'
          'Content-Type: text/plain; charset=UTF-8\\nContent-Transfer-Encoding: 8bit\\n'
          'Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n\n')
PERCENT_CASES = [
    ('Build proxy at 100% resolution', 'Bygg proxy med upplösningen 100 %'),
    ('Build proxy at 100% resolution', 'Bygg proxy med 100 % upplösning'),
    ('We do not currently have 100% coverage.', 'Vi har för närvarande inte 100% täckning.'),
    ('To cut the displayed speed by 50%, enter 0.5.',
     'Om du vill minska den visade hastigheten med 50 % anger du 0,5.'),
    ('At 10% of the object size', 'Vid 10 % objektets storlek'),
    ('At 20% one-pixel width', 'Vid 20 % en bildpunkts bredd'),
    ('100%complete', '100%klart'),
    ('100 % coverage and 50% scale', '100 % täckning och 50 % skala'),
    ('100\u00a0% coverage', '100\u00a0% täckning'),
    ('100 %\ncoverage', '100 %\ntäckning'),
]
MATH_CASES = [r':math:`\frac{Pa\cdot s}{kg/m^{3}}`',
              r':math:`2^{steps -1}`', r':math:`1\over{\sqrt{x}}`',
              r'`\frac{Pa\cdot s}{kg/m^{3}}`:math:',
              r':math:`\frac{a}{b}` and :math:`\sqrt{x}`']


def catalog(source, target, flags=''):
    return HEADER + (f'#, {flags}\n' if flags else '') + 'msgid ' + json.dumps(source, ensure_ascii=False) + '\nmsgstr ' + json.dumps(target, ensure_ascii=False) + '\n'


def issues(source, target, flags=''):
    return L10nLinter(disabled_rules=set(RULES) - resolve_rules(['placeholders'])).lint_file(
        'sv.po', catalog(source, target, flags)).issues


@pytest.mark.parametrize('source,target', PERCENT_CASES)
def test_prose_percentages_have_no_format_diagnostics(source, target):
    assert not issues(source, target)


@pytest.mark.parametrize('source,target,flags', [
    ('Value: % d', 'Värde: % s', 'c-format'),
    ('Value: % d', 'Värde', 'python-format'),
    ('Value: % c', 'Värde', 'c-format'),
    ('Value: % a', 'Värde', 'c-format'),
    ('Value: % u', 'Värde', 'c-format'),
    ('Value: % o', 'Värde', 'c-format'),
    ('100%d', '100%s', 'c-format'),
    ('%dpx', '%spx', 'c-format'),
])
def test_explicit_flags_preserve_ambiguous_printf_checks(source, target, flags):
    assert any(i.rule == 'placeholder-mismatch' for i in issues(source, target, flags))


@pytest.mark.parametrize('source,target', [
    ('Hello %s', 'Hej'), ('Hello', 'Hej %s'),
    ('Value %1$dpx', 'Värde %1$spx'), ('Value %.2fms', 'Värde %.2dms'),
    ('Value %(count)d', 'Värde %(count)s'), ('Value %*.*f', 'Värde %f'),
    ('Progress %s: 100% complete', 'Förlopp: 100 % klart'),
])
def test_unflagged_clear_conversions_are_still_checked(source, target):
    assert any(i.rule == 'placeholder-mismatch' for i in issues(source, target))


def test_unflagged_printf_time_unit_can_be_spaced_in_swedish():
    assert not issues('Retry within %ds', 'Försök igen inom %d s')


def test_prose_does_not_shift_real_printf_argument_numbers():
    assert not issues('Progress %s: 100% complete', 'Förlopp %s: 100 % klart')
    assert not issues('At 10% coverage, %s needs %d files', 'Vid 10 % täckning behöver %1$s %2$d filer')


@pytest.mark.parametrize('formula', MATH_CASES)
@pytest.mark.parametrize('flags', ['', 'python-brace-format'])
def test_math_roles_are_not_python_format_fields(formula, flags):
    assert not issues('Formula ' + formula, 'Formel ' + formula, flags)


@pytest.mark.parametrize('flags', ['', 'python-brace-format'])
def test_literal_brace_code_spans_are_not_fields(flags):
    assert not issues('Use ``{`` and ``}`` as delimiters.',
                      'Använd ``{`` och ``}`` som avgränsare.', flags)
    assert not issues('A pair ``{ }``', 'Ett par ``{ }``', flags)


@pytest.mark.parametrize('literal', [MATH_CASES[0], MATH_CASES[2], '``{`` and ``}``'])
@pytest.mark.parametrize('flags', ['', 'python-brace-format'])
def test_markup_does_not_hide_real_fields_outside_it(literal, flags):
    assert any(i.rule == 'python-format' for i in issues(literal + ': {name}', literal + ': {other}', flags))


@pytest.mark.parametrize('flags', ['', 'python-brace-format'])
def test_complete_fields_inside_code_spans_are_checked(flags):
    assert any(i.rule == 'python-format' for i in issues('Value ``{name}``', 'Värde ``{other}``', flags))
    assert any(i.rule == 'python-format' for i in issues('Value ``{}``', 'Värde ``{name}``', flags))
    assert any(i.rule == 'python-format' for i in issues('Value ``{name:{width}}``', 'Värde ``{name:{height}}``', flags))


def test_markup_masking_is_narrow():
    literal = r'Example \:math:`\frac{a}{b}`'
    assert python_format_text(literal) == literal  # escaped role is not markup
    literal = '``{name}`` and :ref:`{section}`'
    assert python_format_text(literal) == literal


@pytest.mark.parametrize('flags', ['no-c-format', 'no-python-format'])
def test_no_format_flags_continue_to_disable_printf(flags):
    assert not issues('%s', '%d', flags)


def test_documentation_examples_pass_cli_check(tmp_path):
    texts = [(a, b, '') for a, b in PERCENT_CASES]
    texts += [('Formula ' + m, 'Formel ' + m, '') for m in MATH_CASES]
    texts += [('Use ``{`` and ``}``', 'Använd ``{`` och ``}``', 'python-brace-format')]
    for index, (source, target, flags) in enumerate(texts):
        (tmp_path / f'example-{index}.po').write_text(catalog(source, target, flags), encoding='utf-8')
    command = subprocess.run([sys.executable, str(ROOT / 'l10n_lint.py'), '--checks', 'placeholders', '--check', str(tmp_path)],
                             cwd=tmp_path, text=True, capture_output=True)
    assert command.returncode == 0, command.stderr
    assert command.stdout == ''


@pytest.mark.skipif(shutil.which('msgfmt') is None, reason='GNU gettext is optional')
def test_reported_examples_are_valid_gettext_catalogs(tmp_path):
    examples = [(a, b, '') for a, b in PERCENT_CASES]
    examples += [('Formula ' + m, 'Formel ' + m, '') for m in MATH_CASES]
    examples += [('Use ``{`` and ``}``', 'Använd ``{`` och ``}``', 'python-brace-format')]
    for index, (source, target, flags) in enumerate(examples):
        file = tmp_path / f'example-{index}.po'
        file.write_text(catalog(source, target, flags), encoding='utf-8')
        result = subprocess.run(['msgfmt', '--check', '--check-format', '-o', str(tmp_path/'out.mo'), str(file)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def test_reported_messages_have_no_errors_with_default_rules():
    examples = [(a, b, '') for a, b in PERCENT_CASES]
    examples += [('Formula ' + m, 'Formel ' + m, '') for m in MATH_CASES]
    examples += [('Use ``{`` and ``}``', 'Använd ``{`` och ``}``', 'python-brace-format')]
    for source, target, flags in examples:
        result = L10nLinter().lint_file('sv.po', catalog(source, target, flags))
        assert result.error_count == 0, result.issues


def test_explicit_c_format_ignores_percentage_prose_with_space_flag_shape():
    source = 'One unit is roughly a 2% change in camera distance.'
    target = 'En enhet motsvarar ungefär en ändring på 2 % av kamerans avstånd.'
    assert not issues(source, target, 'c-format')
