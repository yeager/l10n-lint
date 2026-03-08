#!/usr/bin/env python3
"""
Tests for Weblate-inspired quality checks added in v1.19.0.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from l10n_lint import L10nLinter, LintResult, Severity

def test_check(check_method, test_cases, expected_rule):
    """Helper to test a check method with multiple test cases."""
    linter = L10nLinter()
    
    for i, (source, translation, should_trigger) in enumerate(test_cases):
        result = LintResult()
        check_method(linter, 'test.po', i+1, source, translation, result)
        
        issues = [issue for issue in result.issues if issue.rule == expected_rule]
        if should_trigger and not issues:
            print(f"❌ FAIL: {expected_rule} should trigger for: {repr(source)} -> {repr(translation)}")
            return False
        elif not should_trigger and issues:
            print(f"❌ FAIL: {expected_rule} should NOT trigger for: {repr(source)} -> {repr(translation)}")
            return False
        elif should_trigger:
            print(f"✅ PASS: {expected_rule} correctly triggered for: {repr(source)} -> {repr(translation)}")
        else:
            print(f"✅ PASS: {expected_rule} correctly did not trigger for: {repr(source)} -> {repr(translation)}")
    
    return True

def test_zero_width_space():
    """Test zero-width space detection."""
    test_cases = [
        # (source, translation, should_trigger)
        ("Normal text", "Normal text med\u200Bosynligt tecken", True),  # Zero-width space
        ("Text", "Text med\u200E\u200FLTR/RTL marks", True),  # LTR/RTL marks  
        ("Test", "\uFEFFText med BOM", True),  # BOM
        ("Normal text", "Normal text", False),  # No zero-width chars
        ("Text\u200B", "Text\u200B", False),  # Both have same zero-width char
    ]
    
    return test_check(L10nLinter._check_zero_width_space, test_cases, "zero-width-space")

def test_end_stop_mismatch():
    """Test end stop mismatch detection."""
    test_cases = [
        # (source, translation, should_trigger)
        ("Save the document.", "Spara dokumentet", True),  # Missing period
        ("Close window", "Stäng fönster.", True),  # Extra period
        ("OK.", "OK", False),  # Short string ignored
        ("Contact Mr. Johnson for details.", "Kontakta Mr. Johnson för detaljer", False),  # Abbreviation
        ("Loading...", "Laddar…", False),  # Ellipsis mapping allowed
        ("Save file.", "Spara fil.", False),  # Both have period
    ]
    
    return test_check(L10nLinter._check_end_stop_mismatch, test_cases, "end-stop-mismatch")

def test_ellipsis():
    """Test ellipsis style check."""
    test_cases = [
        # (source, translation, should_trigger)
        ("Please wait", "Vänta...", True),  # Three dots should be ellipsis
        ("Loading", "Laddar…", False),  # Already ellipsis
        ("Normal text", "Normal text", False),  # No ellipsis
    ]
    
    return test_check(L10nLinter._check_ellipsis, test_cases, "ellipsis")

def test_xml_tags_mismatch():
    """Test XML/HTML tags mismatch detection."""
    test_cases = [
        # (source, translation, should_trigger)
        ("This is <b>bold</b> text", "Detta är <b>fet text", True),  # Missing closing tag
        ("Simple text", "Enkel <b>text</b>", True),  # Extra tags
        ("<b>Bold</b> and <i>italic</i>", "<b>Fet</b> och <i>kursiv</i>", False),  # Perfect match
        ("Text with <B>bold</B>", "Text med <b>fet</b>", True),  # Case mismatch
    ]
    
    return test_check(L10nLinter._check_xml_tags_mismatch, test_cases, "xml-tags-mismatch")

def test_duplicate_words():
    """Test enhanced duplicate word detection."""
    test_cases = [
        # (source, translation, should_trigger)
        ("Single word", "samma samma samma ord", True),  # Triple words (always bad)
        ("The message", "ett ett meddelande", True),  # Regular duplicates
        ("Preposition test", "text med i i början", False),  # Swedish exception
        ("Another preposition", "text med på på slutet", False),  # Swedish exception
        ("Normal text", "normal text", False),  # No duplicates
    ]
    
    return test_check(L10nLinter._check_duplicate_words, test_cases, "duplicate-words")

def test_punctuation_mismatch():
    """Test punctuation mismatch detection."""
    test_cases = [
        # (source, translation, should_trigger)
        ("Select option:", "Välj alternativ", True),  # Missing colon
        ("Error!", "Fel", True),  # Missing exclamation
        ("Are you sure?", "Är du säker", True),  # Missing question mark
        ("First; second", "Första, andra", True),  # Missing semicolon
        ("Normal text", "Normal text", False),  # No punctuation
    ]
    
    return test_check(L10nLinter._check_punctuation_mismatch, test_cases, "punctuation-mismatch")

def test_url_preservation():
    """Test URL preservation check."""
    test_cases = [
        # (source, translation, should_trigger)
        ("Visit https://example.com for info", "Besök vår webbplats för info", True),  # Missing URL
        ("Download from https://original.com/file", "Ladda ner från https://different.com/file", True),  # Changed URL  
        ("Visit https://example.com", "Besök https://example.com", False),  # URL preserved
        ("No URLs here", "Inga URLer här", False),  # No URLs
    ]
    
    return test_check(L10nLinter._check_url_preservation, test_cases, "url-preservation")

def test_escaped_newline_count():
    """Test escaped newline count check."""
    test_cases = [
        # (source, translation, should_trigger)
        ("line1\\nline2\\nline3", "rad1\\nrad2", True),  # Different counts
        ("no newlines", "inga radbrytningar\\nmen här", True),  # Added newlines
        ("line1\\nline2", "rad1\\nrad2", False),  # Same counts
        ("no escapes", "inga escapes", False),  # No newlines
    ]
    
    return test_check(L10nLinter._check_escaped_newline_count, test_cases, "escaped-newline-count")

def test_max_length_ratio():
    """Test max length ratio check."""
    test_cases = [
        # (source, translation, should_trigger)
        ("Short text", "Detta är en mycket lång svensk översättning som är mer än tre gånger längre än källtexten", True),  # Too long
        ("Hi", "Hej då kompis", False),  # Short source ignored
        ("Reasonable length source", "Rimlig längd på måltext", False),  # Good ratio
    ]
    
    return test_check(L10nLinter._check_max_length_ratio, test_cases, "max-length-ratio")

def test_same_plurals():
    """Test same plurals check."""
    linter = L10nLinter()
    
    # Test case 1: Different source plurals, same translation plurals (should trigger)
    entry1 = {
        'msgstr[0]': 'Fil',
        'msgstr[1]': 'Fil'
    }
    result1 = LintResult()
    linter._check_same_plurals('test.po', 1, 'File', 'Files', entry1, result1)
    
    if not any(issue.rule == 'same-plurals' for issue in result1.issues):
        print("❌ FAIL: same-plurals should trigger when source plurals differ but translation plurals are identical")
        return False
    else:
        print("✅ PASS: same-plurals correctly triggered for different source, same translation")
    
    # Test case 2: Same source plurals, same translation plurals (should NOT trigger)
    entry2 = {
        'msgstr[0]': 'Får', 
        'msgstr[1]': 'Får'
    }
    result2 = LintResult()
    linter._check_same_plurals('test.po', 2, 'Sheep', 'Sheep', entry2, result2)
    
    if any(issue.rule == 'same-plurals' for issue in result2.issues):
        print("❌ FAIL: same-plurals should NOT trigger when both source and translation plurals are identical")
        return False
    else:
        print("✅ PASS: same-plurals correctly did not trigger for same source, same translation")
    
    return True

def run_all_tests():
    """Run all tests and report results."""
    print("🧪 Testing Weblate-inspired quality checks\n")
    
    tests = [
        ("Zero-width space detection", test_zero_width_space),
        ("End stop mismatch detection", test_end_stop_mismatch),
        ("Ellipsis style check", test_ellipsis),
        ("XML tags mismatch detection", test_xml_tags_mismatch),
        ("Duplicate words detection", test_duplicate_words),
        ("Punctuation mismatch detection", test_punctuation_mismatch),
        ("URL preservation check", test_url_preservation),
        ("Escaped newline count check", test_escaped_newline_count),
        ("Max length ratio check", test_max_length_ratio),
        ("Same plurals check", test_same_plurals),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        if test_func():
            passed += 1
            print(f"   ✅ PASSED\n")
        else:
            print(f"   ❌ FAILED\n")
    
    print(f"🏁 Results: {passed}/{total} tests passed")
    return passed == total

if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)