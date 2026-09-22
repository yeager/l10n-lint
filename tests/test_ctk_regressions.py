#!/usr/bin/env python3
"""Regression checks found while reviewing 3D Slicer CTK."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from l10n_lint import L10nLinter, LintResult


def issues_for(method, source, target):
    result = LintResult()
    method(L10nLinter(), 'ctk.ts', 1, source, target, result)
    return result.issues


def test_swedish_decimal_separator_is_equivalent():
    assert not issues_for(L10nLinter._check_numerics, 'between 0.5 and 5', 'mellan 0,5 och 5')


def test_swedish_spelled_out_cardinal_is_equivalent():
    assert not issues_for(L10nLinter._check_numerics, 'at least 1 project', 'minst ett projekt')


def test_hyphenated_placeholder_is_not_an_html_tag():
    assert not issues_for(L10nLinter._check_xml_tags_mismatch, '<your-organization>', '<din-organisation>')


def test_triple_consonants_in_swedish_compounds_are_typos():
    assert issues_for(L10nLinter._check_typos, 'Process Status', 'Processstatus')
    assert issues_for(L10nLinter._check_typos, 'Up arrow', 'upppil')


def test_angle_bracket_command_metavariables_can_be_translated():
    assert not issues_for(L10nLinter._check_xml_tags_mismatch, '<file> ...', '<fil> …')
    assert not issues_for(L10nLinter._check_xml_tags_mismatch, 'mail -s <subject> -c <cc> <to>', 'mail -s <ämne> -c <kopia> <till>')


def test_unicode_angle_bracket_sentinel_can_be_translated():
    assert not issues_for(L10nLinter._check_xml_tags_mismatch, '<Unknown user>', '<Okänd användare>')
