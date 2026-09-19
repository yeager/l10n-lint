"""Regression cases from Swedish catalogs decompiled with msgunfmt."""
import json
import pytest
from l10n_lint import L10nLinter, RULES, resolve_rules


def lint(source, target, checks, header='Language: sv\n', flags=''):
    content = 'msgid ""\nmsgstr ' + json.dumps(header) + '\n\n'
    if flags:
        content += '#, ' + flags + '\n'
    content += 'msgid ' + json.dumps(source, ensure_ascii=False) + '\nmsgstr ' + json.dumps(target, ensure_ascii=False) + '\n'
    return L10nLinter(disabled_rules=set(RULES) - resolve_rules(checks)).lint_file('catalog.po', content)


def test_singular_catalog_does_not_need_plural_header():
    assert not lint('Hello', 'Hej', ['plural-forms']).issues


def test_missing_plural_header_still_reported_for_plural_entry():
    content = 'msgid ""\nmsgstr "Language: sv\\n"\n\nmsgid "File"\nmsgid_plural "Files"\nmsgstr[0] "Fil"\nmsgstr[1] "Filer"\n'
    assert any(i.rule == 'plural-header-missing' for i in L10nLinter().lint_file('catalog.po', content).issues)


def test_existing_invalid_plural_header_still_reported():
    result = lint('Hello', 'Hej', ['plural-forms'], 'Language: sv\nPlural-Forms: broken\n')
    assert any(i.rule == 'plural-header-missing' for i in result.issues)


@pytest.mark.parametrize('source,target', [
    ('invalid %uth argument to %s', 'ogiltigt %u:e argument till %s'),
    ('Rate set to %iHz', 'Frekvensen inställd till %i Hz'),
    ("%s's key", '%ss nyckel'),
    ('Image size %ux%u', 'Bildstorlek %u×%u'),
    ('Time %llums', 'Tid %llu ms'),
    ('File %s of %s at %sB/s', 'Fil %s av %s i %s B/s'),
])
def test_matching_printf_contract_with_literal_suffix(source, target):
    assert not lint(source, target, ['placeholders']).issues


@pytest.mark.parametrize('source,target,flags', [
    ('Name %s', 'Namn', ''),
    ('Name', 'Namn %s', ''),
    ('Count %d', 'Antal %s', ''),
    ('Count %dHz', 'Antal %s Hz', ''),
    ('%s %s', '%ss', ''),
    ('Value %s', '75%strong', ''),
    ('Count %dHz', 'Antal', 'c-format'),
])
def test_real_placeholder_changes_remain_errors(source, target, flags):
    assert lint(source, target, ['placeholders'], flags=flags).error_count


def test_prose_percentages_remain_unformatted():
    assert not lint('100% coverage', '100 % täckning', ['placeholders']).issues


@pytest.mark.parametrize('source,target', [
    ('A cross-platform GUI', 'Ett plattformsoberoende gränssnitt'),
    ('A mobile-friendly UI', 'Ett mobilvänligt gränssnitt'),
    ('Lock-on AF: Center', 'Låsbar autofokus: Centrum'),
    ('Official Aramaic (700-300 BCE)', 'Arameiska'),
])
def test_hyphenated_prose_is_not_an_option(source, target):
    assert not lint(source, target, ['option-values']).issues


@pytest.mark.parametrize('source', ['Use --output FILE', 'Use -o FILE', '(--output=FILE)'])
def test_missing_real_option_value_is_reported(source):
    assert any(i.rule == 'option-value-missing' for i in lint(source, 'Skriv ut', ['option-values']).issues)


@pytest.mark.parametrize('source,target', [
    ('IEEE 802.15.4 channel', 'IEEE 802.15.4-kanal'),
    ('PPP configuration', 'PPP-konfiguration'),
    ('Quake III Arena', 'Spela Quake III Arena'),
    ('Visit http://www.example.com', 'Besök http://www.example.com'),
    ('Cannot find pppd', 'Kunde inte hitta pppd'),
])
def test_preserved_technical_token_is_not_a_swedish_triple_letter_typo(source, target):
    assert not lint(source, target, ['typo']).issues


@pytest.mark.parametrize('source,target', [
    ('Invalid route type', 'Ogiltig rutttyp'),
    ('Failed to open file', 'Kunde inte öpppna filen'),
    ('ogiltligt värde', 'ogiltligt värde'),
])
def test_real_swedish_typos_remain_reported(source, target):
    assert any(i.rule == 'typo' for i in lint(source, target, ['typo']).issues)
