import os
import sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from l10n_lint import RCParser

def test_extracts_visible_windows_resource_strings():
    parser = RCParser('CAPTION "Inställningar"\nPUSHBUTTON "Spara…", 1\n', 'dialog-sv.rc')
    assert parser.language == 'sv'
    assert [entry['translation'] for entry in parser.entries] == ['Inställningar', 'Spara…']

def test_ignores_resource_identifiers_without_visible_text():
    with pytest.raises(ValueError, match='No Windows RC UI strings found'):
        RCParser('EDITTEXT 42, 1, 1, 10, 10\n', 'dialog.rc')
