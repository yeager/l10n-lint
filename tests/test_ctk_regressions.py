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


def test_swedish_thousands_grouping_is_equivalent():
    assert not issues_for(L10nLinter._check_numerics, '1,400 cases', '1 400 lådor')


def test_forty_winks_is_equivalent_to_tupplur():
    assert not issues_for(L10nLinter._check_numerics, 'catch 40 winks', 'ta en tupplur')


def test_swedish_spelled_out_cardinal_is_equivalent():
    assert not issues_for(L10nLinter._check_numerics, 'at least 1 project', 'minst ett projekt')


def test_hyphenated_placeholder_is_not_an_html_tag():
    assert not issues_for(L10nLinter._check_xml_tags_mismatch, '<your-organization>', '<din-organisation>')


def test_triple_consonants_in_swedish_compounds_are_typos_except_known_words():
    assert not issues_for(L10nLinter._check_typos, 'Process Status', 'Processstatus')
    assert issues_for(L10nLinter._check_typos, 'Up arrow', 'upppil')


def test_angle_bracket_command_metavariables_can_be_translated():
    assert not issues_for(L10nLinter._check_xml_tags_mismatch, '<file> ...', '<fil> …')
    assert not issues_for(L10nLinter._check_xml_tags_mismatch, 'mail -s <subject> -c <cc> <to>', 'mail -s <ämne> -c <kopia> <till>')


def test_unicode_angle_bracket_sentinel_can_be_translated():
    assert not issues_for(L10nLinter._check_xml_tags_mismatch, '<Unknown user>', '<Okänd användare>')


def test_swedish_cardinals_through_twelve_are_equivalent():
    assert not issues_for(L10nLinter._check_numerics, '11 dollars', 'elva dollar')
    assert not issues_for(L10nLinter._check_numerics, '12 dollars', 'tolv dollar')


def test_english_time_colon_is_not_missing_in_swedish_clock():
    assert not issues_for(L10nLinter._check_punctuation_mismatch, 'Starts at 9:00 am.', 'Startar klockan 9.00.')
    assert not issues_for(L10nLinter._check_punctuation_mismatch, 'Ends at 4:30 pm.', 'Slutar klockan 16.30.')


def test_english_12_hour_times_match_swedish_24_hour_clock():
    assert not issues_for(L10nLinter._check_numerics, 'Starts at 9:00 am.', 'Startar klockan 9.00.')
    assert not issues_for(L10nLinter._check_numerics, 'Ends at 4:30 pm.', 'Slutar klockan 16.30.')
    assert not issues_for(L10nLinter._check_numerics, 'Opens at 0:00 am.', 'Öppnar klockan 0.00.')


def test_swedish_time_with_single_digit_hour_is_not_a_decimal():
    assert not issues_for(
        L10nLinter._check_decimal_separator,
        'The service opens at 9:00 am.',
        'Tjänsten öppnar klockan 9.00.',
    )


def test_swedish_decimal_with_two_digits_is_still_flagged():
    assert issues_for(
        L10nLinter._check_decimal_separator,
        'The result is 9.9.',
        'Resultatet är 9.99.',
    )
