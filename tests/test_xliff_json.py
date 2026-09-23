"""XLIFF and JSON catalog parsing, linting and input discovery."""
import json
from pathlib import Path

import pytest

from l10n_lint import AndroidXMLParser, JSONParser, L10nLinter, PropertiesParser, XLIFFParser, find_l10n_files, lint_inputs


XLIFF_12 = '''<?xml version="1.0" encoding="UTF-8"?>
<xliff version="1.2">
  <file source-language="en" target-language="sv" original="app">
    <body>
      <trans-unit id="save" resname="menu.save"><source>Save %s</source><target>Spara %s</target></trans-unit>
      <trans-unit id="empty"><source>Cancel</source><target/></trans-unit>
      <trans-unit id="skip" translate="no"><source>Internal</source><target/></trans-unit>
      <trans-unit id="inline"><source>Open <ph id="1" equiv-text="%d"/> file</source><target>Öppna <ph id="1" equiv-text="%d"/> fil</target></trans-unit>
    </body>
  </file>
</xliff>'''

XLIFF_20 = '''<?xml version="1.0" encoding="UTF-8"?>
<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0" version="2.0" srcLang="en" trgLang="sv">
  <file id="f">
    <unit id="welcome" name="home"><segment id="1"><source>Welcome {name}</source><target>Välkommen {name}</target></segment></unit>
    <unit id="missing"><segment id="1"><source>Close</source></segment></unit>
    <unit id="hidden" translate="no"><segment id="1"><source>Hidden</source><target/></segment></unit>
  </file>
</xliff>'''


def rules(result):
    return [issue.rule for issue in result.issues]


def test_android_xml_parses_strings_plurals_and_skips_internal_resources():
    content = '''<resources>
      <string name="save">Spara</string>
      <string name="internal" translatable="false"/>
      <plurals name="files"><item quantity="one">en fil</item><item quantity="other">%d filer</item></plurals>
      <string name="missing"></string>
    </resources>'''
    parser = AndroidXMLParser(content, 'values-sv.xml')
    assert [entry['_id'] for entry in parser.entries] == ['save', 'files', 'missing']
    assert parser.entries[1]['_translations'] == ['en fil', '%d filer']
    result = L10nLinter({'language': 'sv'}).lint_file('values-sv.xml', content)
    assert result.entries_checked == 3
    assert rules(result) == ['missing-translation']


def test_xliff_12_parses_languages_context_inline_codes_and_nontranslatable_units():
    parser = XLIFFParser(XLIFF_12, 'sv.xlf')
    assert parser.language == 'sv'
    assert len(parser.entries) == 3
    assert parser.entries[0]['_context'] == 'menu.save'
    assert parser.entries[-1]['source'] == 'Open %d file'


def test_xliff_12_runs_existing_checks_and_reports_empty_targets():
    result = L10nLinter().lint_file('sv.xlf', XLIFF_12)
    assert result.entries_checked == 3
    assert rules(result) == ['missing-translation']


def test_xliff_12_keeps_line_numbers_when_a_whole_file_is_not_translatable():
    content = '''<xliff version="1.2">
      <file translate="no"><body><trans-unit id="hidden"><source>Hidden</source></trans-unit></body></file>
      <file><body><trans-unit id="visible"><source>Visible</source></trans-unit></body></file>
    </xliff>'''
    entry = XLIFFParser(content).entries[0]
    assert entry['_id'] == 'visible'
    assert entry['_line'] == 3


def test_xliff_20_parses_segments_and_uses_target_language():
    parser = XLIFFParser(XLIFF_20, 'sv.xliff')
    assert parser.language == 'sv'
    assert [entry['_id'] for entry in parser.entries] == ['welcome:1', 'missing:1']
    result = L10nLinter().lint_file('sv.xliff', XLIFF_20)
    assert result.entries_checked == 2
    assert rules(result) == ['missing-translation']


@pytest.mark.parametrize('content', [
    '<xliff version="1.2"><file><body><trans-unit id="x"><target>x</target></trans-unit></body></file></xliff>',
    '<xliff version="3.0"/>',
    '<xliff version="2.0"><file id="f"/></xliff>',
    '<not-xliff/>',
])
def test_invalid_xliff_is_a_syntax_error(content):
    result = L10nLinter().lint_file('broken.xlf', content)
    assert rules(result) == ['syntax-error']


def test_json_parser_supports_nested_key_value_and_explicit_entries():
    content = json.dumps({
        '@locale': 'sv',
        'menu': {'Save %s': 'Spara %s', 'Cancel': ''},
        'entries': [{'id': 'welcome', 'context': 'home', 'source': 'Welcome', 'target': 'Välkommen'}],
    })
    parser = JSONParser(content, 'sv.json')
    assert parser.language == 'sv'
    assert {(entry['_id'], entry['source'], entry['translation']) for entry in parser.entries} == {
        ('menu.Save %s', 'Save %s', 'Spara %s'),
        ('menu.Cancel', 'Cancel', ''),
        ('welcome', 'Welcome', 'Välkommen'),
    }
    result = L10nLinter().lint_file('sv.json', content)
    assert result.entries_checked == 3
    assert rules(result) == ['missing-translation']


def test_json_nested_catalog_allows_source_as_a_regular_key():
    content = json.dumps({'common': {'source': 'Källa', 'target': 'Mål', 'other': 'Övrigt'}})
    result = L10nLinter().lint_file('sv.json', content)
    assert result.entries_checked == 3
    assert rules(result) == []


def test_json_placeholder_mismatch_and_nontranslatable_entry_are_handled():
    content = json.dumps([
        {'id': 'bad', 'source': 'Save %s', 'target': 'Spara %d'},
        {'id': 'skip', 'source': 'Internal', 'target': '', 'translate': False},
    ])
    result = L10nLinter().lint_file('sv.json', content)
    assert result.entries_checked == 1
    assert rules(result) == ['placeholder-mismatch']


def test_json_root_entry_allows_locale_metadata():
    content = json.dumps({'@locale': 'sv', 'source': 'Save %s', 'target': 'Spara %d'})
    result = L10nLinter().lint_file('sv.json', content)
    assert result.entries_checked == 1
    assert rules(result) == ['placeholder-mismatch']


def test_json_null_target_is_an_empty_translation():
    result = L10nLinter().lint_file('sv.json', json.dumps({'source': 'Save', 'target': None}))
    assert result.entries_checked == 1
    assert rules(result) == ['missing-translation']


def test_json_plural_forms_are_checked_and_keep_their_source_line():
    content = '''{
      "@locale": "sv",
      "{count} file": {"one": "{count} fil", "other": ""}
    }'''
    parser = JSONParser(content, 'sv.json')
    assert parser.entries[0]['_line'] == 3
    assert parser.entries[0]['_translations'] == ['{count} fil', '']
    result = L10nLinter().lint_file('sv.json', content)
    assert result.entries_checked == 1
    assert rules(result) == ['missing-translation']


def test_json_format_policy_rejects_other_catalog_shapes():
    nested = json.dumps({'Save': 'Spara'})
    explicit = json.dumps({'source': 'Save', 'target': 'Spara'})
    assert rules(L10nLinter({'json_format': 'entries'}).lint_file('sv.json', nested)) == ['syntax-error']
    assert rules(L10nLinter({'json_format': 'nested'}).lint_file('sv.json', explicit)) == ['syntax-error']


def test_json_plural_forms_follow_known_cldr_categories():
    content = json.dumps({'@locale': 'ar', 'Files': {'one': 'ملف', 'other': 'ملفات'}})
    result = L10nLinter().lint_file('ar.json', content)
    assert 'cldr-plural-missing' in rules(result)


@pytest.mark.parametrize('content', ['{', '[]', '{"message": 5}', '{"source": 7, "target": "Hej"}'])
def test_invalid_json_catalog_is_a_syntax_error(content):
    result = L10nLinter().lint_file('broken.json', content)
    assert rules(result) == ['syntax-error']


def test_xliff_and_json_are_discovered_in_directories_and_by_input_pipeline(tmp_path):
    (tmp_path / 'sv.xlf').write_text(XLIFF_12, encoding='utf-8')
    (tmp_path / 'sv.xliff').write_text(XLIFF_20, encoding='utf-8')
    (tmp_path / 'sv.json').write_text(json.dumps({'Save': 'Spara'}), encoding='utf-8')
    found = {Path(path).name for path in find_l10n_files(tmp_path)}
    assert found == {'sv.xlf', 'sv.xliff', 'sv.json'}
    result = lint_inputs([str(tmp_path)])
    assert result.files_checked == 3
    assert result.entries_checked == 6
    assert rules(result).count('missing-translation') == 2


def test_xliff_and_json_catalog_comparison_uses_matching_formats(tmp_path):
    source = tmp_path / 'source.xlf'
    target = tmp_path / 'sv.xlf'
    source.write_text(XLIFF_12.replace('target-language="sv"', 'target-language="en"').replace('<target>Spara %s</target>', '<target>Save %s</target>').replace('<target/>', '<target>Cancel</target>'), encoding='utf-8')
    target.write_text(XLIFF_12, encoding='utf-8')
    result = L10nLinter({'reference': str(source)}).lint_file(str(target))
    assert not any(issue.rule.startswith('reference-error') for issue in result.issues)

def test_json_weblate_api_plural_arrays_are_supported():
    content = json.dumps([{
        'id': 1, 'context': 'bottles',
        'source': ['{{count}} bottle', '{{count}} bottles'],
        'target': ['{{count}} flaska', '{{count}} flaskor'],
        'state': 20,
    }])
    parser = JSONParser(content, 'sv.json')
    assert parser.entries[0]['source'] == '{{count}} bottle'
    assert parser.entries[0]['_translations'] == ['{{count}} flaska', '{{count}} flaskor']
    assert not L10nLinter().lint_file('sv.json', content).issues


def test_nested_json_does_not_compare_placeholders_against_key_names(tmp_path):
    path = tmp_path / 'sv.json'
    path.write_text('{"relativeTime": {"future": "i %s", "mm": "%d minuter"}}', encoding='utf-8')
    result = L10nLinter().lint_file(str(path), path.read_text(encoding='utf-8'))
    assert not [issue for issue in result.issues if issue.rule == 'placeholder-mismatch']


def test_properties_catalog_lints_values_without_treating_keys_as_source():
    content = 'menu.open=Öppna\nmenu.empty=\n'
    parser = PropertiesParser(content, 'sv.properties')
    assert [entry['_id'] for entry in parser.entries] == ['menu.open', 'menu.empty']
    result = L10nLinter().lint_file('sv.properties', content)
    assert result.entries_checked == 2
    assert rules(result) == ['missing-translation']


def test_properties_catalog_requires_key_value_separator():
    result = L10nLinter().lint_file('broken.properties', 'missing separator\n')
    assert rules(result) == ['syntax-error']

def test_xliff_context_prefix_leak_is_reported():
    content = '''<xliff version="1.2"><file target-language="sv"><body>
    <trans-unit id="x"><source>Security|Protect secrets</source><target>Security|Skydda hemligheter</target></trans-unit>
    </body></file></xliff>'''
    assert 'context-prefix-leak' in rules(L10nLinter().lint_file('sv.xlf', content))

def test_xliff_context_prefix_is_removed_before_source_checks():
    content = '''<xliff version="1.2"><file target-language="sv"><body>
    <trans-unit id="x"><source>hejpådig|Translate</source><target>Översätt</target></trans-unit>
    <trans-unit id="y"><source>hejpådig|Translate</source><target>hejpådig|Översätt</target></trans-unit>
    <trans-unit id="z"><source>%{reason_text} Manage notifications | Help: %{help_url}</source><target>%{reason_text} Hantera aviseringar | Hjälp: %{help_url}</target></trans-unit>
    </body></file></xliff>'''
    result = L10nLinter().lint_file('sv.xlf', content)
    assert [issue.rule for issue in result.issues].count('context-prefix-leak') == 1
    assert all(issue.rule != 'source-equals-translation' for issue in result.issues)
    assert all(issue.rule != 'python-format' for issue in result.issues)
