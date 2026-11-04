"""Cross-language contract and corruption checks for compact-v2/v3."""
import unittest

from literal_protection import LiteralProtectionMask
from specialist_literal_protection import SpecialistLiteralMask


def block(key, value):
    return f"[[FREEHAND_LITERAL_{key}_START]]{value}[[FREEHAND_LITERAL_{key}_END]]"


class SpecialistLiteralProtectionTests(unittest.TestCase):
    def test_managed_utf8_golden_vectors(self):
        for original, masked in [
            ("Before " + block("01", "  Acme\tLabs  ") + " after.", "Before FHX_45a27cf4 after."),
            ("Before " + block("01", "  café\tΔ🙂  ") + " after.", "Before FHX_a4400b44 after."),
            ('Keep "very, very small" and “like, like” exactly.', "Keep FHX_8cd46b56 and FHX_2e5722a9 exactly."),
            ('Keep "' + block("01", "  café\tΔ🙂  ") + '" exactly.', "Keep FHX_f5929d80 exactly."),
        ]:
            with self.subTest(original=original):
                protection = SpecialistLiteralMask.create(original)
                self.assertEqual(masked, protection.masked_text)
                self.assertEqual(original, protection.restore(masked))

    def test_twelve_adjacent_equal_values_have_distinct_short_identifiers(self):
        original = "".join(block(f"{index:02x}", "same\tvalue\r\n") for index in range(12))
        protection = SpecialistLiteralMask.create(original)

        self.assertEqual(12, len(protection.tokens))
        self.assertEqual(12, len(set(protection.tokens)))
        self.assertTrue(all(len(token) == 12 for token in protection.tokens))
        self.assertNotIn("FREEHAND_LITERAL_TOKEN_", protection.masked_text)
        self.assertEqual(original, protection.restore(protection.masked_text))

    def test_repeated_quoted_phrases_stay_independent(self):
        original = 'Keep "same" and "same" with “same” unchanged.'
        protection = SpecialistLiteralMask.create(original)

        self.assertEqual(3, len(set(protection.tokens)))
        self.assertNotIn("same", protection.masked_text)
        self.assertEqual(original, protection.restore(protection.masked_text))

    def test_escaped_inner_quotes_are_part_of_one_outer_span(self):
        original = 'Keep "say \\"hello\\" twice" and \\"not a span\\".'
        protection = SpecialistLiteralMask.create(original)

        self.assertEqual(1, len(protection.tokens))
        self.assertEqual('"say \\"hello\\" twice"', protection.payloads[0])
        self.assertIn('\\"not a span\\"', protection.masked_text)
        self.assertEqual(original, protection.restore(protection.masked_text))

    def test_even_backslashes_do_not_escape_a_closing_quote(self):
        original = 'Keep "path \\\\" then continue.'
        protection = SpecialistLiteralMask.create(original)

        self.assertEqual(1, len(protection.tokens))
        self.assertEqual(original, protection.restore(protection.masked_text))

    def test_unbalanced_opening_does_not_reinterpret_nested_other_quote_types(self):
        original = 'Unclosed “outer with "inner" and ' + block("01", "literal")
        protection = SpecialistLiteralMask.create(original)

        self.assertEqual(1, len(protection.tokens), "only the Core literal is protected")
        self.assertIn('“outer with "inner"', protection.masked_text)
        self.assertEqual(original, protection.restore(protection.masked_text))

    def test_apostrophes_and_unpaired_straight_quotes_remain_ordinary_text(self):
        original = 'Don\'t change Sam\'s wording or this unpaired "quote.'
        protection = SpecialistLiteralMask.create(original)

        self.assertEqual((), protection.tokens)
        self.assertEqual(original, protection.masked_text)
        self.assertEqual(original, protection.restore(original))

    def test_missing_duplicate_unknown_reordered_or_modified_identifiers_fail(self):
        protection = SpecialistLiteralMask.create('Keep "first" and ' + block("01", "second"))
        first, second = protection.tokens
        for edited in [first, second + " " + first, first + " " + first + " " + second,
                       protection.masked_text + " FHX_deadbeef", protection.masked_text.replace(first, first.upper()),
                       protection.masked_text.replace(second, second[:-1]),
                       protection.masked_text + block("02", "invented")]:
            with self.subTest(edited=edited), self.assertRaises(ValueError):
                protection.restore(edited)

    def test_identifier_can_be_adjacent_to_ordinary_text_without_adding_boundaries(self):
        original = 'a"quoted"b'
        protection = SpecialistLiteralMask.create(original)
        self.assertEqual(original, protection.restore(protection.masked_text))

    def test_reserved_families_and_malformed_core_blocks_fail_before_masking(self):
        for original in ["FHX_reserved", 'Keep "FHX_reserved".', "FREEHAND_LITERAL_TOKEN_reserved_0_END",
                         "[[FREEHAND_LITERAL_01_START]]unclosed", block("01", block("02", "nested"))]:
            with self.subTest(original=original), self.assertRaises(ValueError):
                SpecialistLiteralMask.create(original)

    def test_general_model_mask_keeps_legacy_quoted_text_behavior(self):
        original = 'Keep "very, very small" unchanged.'
        self.assertEqual(original, LiteralProtectionMask.create(original).masked_text)
        self.assertNotEqual(original, SpecialistLiteralMask.create(original).masked_text)

    def test_v3_removes_one_added_period_after_original_terminal_punctuated_quote(self):
        for original in ['She said "Go."', 'He asked “Why?”', 'They shouted "Stop!"', 'She said "Go." \t\n']:
            with self.subTest(original=original):
                protection = SpecialistLiteralMask.create(original)
                edited = protection.masked_text.rstrip() + ". \t\n"
                self.assertEqual(original.rstrip() + " \t\n", protection.restore(edited))

    def test_v2_and_v3_keep_identical_identifiers_but_different_terminal_period_replay(self):
        original = 'She said "Go."'
        legacy = SpecialistLiteralMask.create(original, remove_added_quote_period=False)
        current = SpecialistLiteralMask.create(original)

        self.assertEqual(legacy.masked_text, current.masked_text)
        self.assertEqual(original + ".", legacy.restore(legacy.masked_text + "."))
        self.assertEqual(original, current.restore(current.masked_text + "."))

    def test_v3_preserves_original_outside_punctuation_and_unpunctuated_quotes(self):
        for original in ['She said "Go.".', 'She said "Go."...', 'She said "Go"', 'She said “Maybe”']:
            with self.subTest(original=original):
                protection = SpecialistLiteralMask.create(original)
                self.assertEqual(original + ".", protection.restore(protection.masked_text + "."))

    def test_v3_preserves_ellipsis_extra_words_and_other_outside_punctuation(self):
        original = 'She said "Go."'
        protection = SpecialistLiteralMask.create(original)
        for suffix in ["..", "...", ". extra words", "?", "!", ".x"]:
            with self.subTest(suffix=suffix):
                self.assertEqual(original + suffix, protection.restore(protection.masked_text + suffix))
        ellipsis = SpecialistLiteralMask.create('She said "Wait..."')
        self.assertEqual('She said "Wait...".', ellipsis.restore(ellipsis.masked_text + "."))

    def test_v3_never_removes_a_period_after_a_mid_sentence_quoted_span(self):
        original = 'She said "Go." and left.'
        protection = SpecialistLiteralMask.create(original)
        edited = protection.masked_text.replace(protection.tokens[0], protection.tokens[0] + ".")
        self.assertEqual('She said "Go.". and left.', protection.restore(edited))

    def test_v3_period_rule_does_not_bypass_identifier_validation(self):
        protection = SpecialistLiteralMask.create('Keep "first" then "last."')
        for edited in [protection.tokens[1] + ".", protection.tokens[0] + " " + protection.tokens[1] + " " + protection.tokens[1] + "."]:
            with self.subTest(edited=edited), self.assertRaises(ValueError):
                protection.restore(edited)


if __name__ == "__main__":
    unittest.main()
