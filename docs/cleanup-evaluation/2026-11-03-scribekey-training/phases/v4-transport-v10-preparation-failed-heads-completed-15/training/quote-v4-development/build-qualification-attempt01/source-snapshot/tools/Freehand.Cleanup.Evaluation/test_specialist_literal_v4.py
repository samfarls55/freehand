"""Offline policy-boundary and UTF8 parity vectors shared with managed tests."""
from pathlib import Path
import hashlib
import json
import re
import unittest

from specialist_literal_protection import SpecialistLiteralMask


V4 = "specialist-compact-v4"


class SpecialistLiteralV4Tests(unittest.TestCase):
    def test_frozen_word_intervals_match_managed_source_independent_of_runtime_unicode(self):
        from specialist_literal_word_ranges import BOUNDARIES, INTERVAL_SHA256, UNICODE_VERSION, is_word
        path = Path(__file__).resolve().parents[2] / "src/Freehand.Cleanup/SpecialistLiteralWordRanges.cs"
        source = path.read_text()
        section = source.split("// BEGIN FROZEN INTERVALS", 1)[1].split("// END FROZEN INTERVALS", 1)[0]
        managed = tuple(int(value, 16) for value in re.findall(r"0x([0-9A-F]+)", section))
        self.assertEqual(BOUNDARIES, managed)
        intervals = [list(BOUNDARIES[at:at + 2]) for at in range(0, len(BOUNDARIES), 2)]
        self.assertEqual(INTERVAL_SHA256, hashlib.sha256(json.dumps(intervals, separators=(",", ":")).encode()).hexdigest())
        self.assertIn('IntervalSha256 = "' + INTERVAL_SHA256 + '"', source)
        self.assertEqual("14.0.0", UNICODE_VERSION)
        self.assertTrue(is_word(0x10400))  # Astral Deseret letter.
        self.assertTrue(is_word(0x0301))  # Combining acute accent.
        self.assertFalse(is_word(0x1E4D0))  # Nag Mundari assigned in Unicode15, outside this frozen epoch.
        self.assertFalse(is_word(0x1FAE8))  # Unicode15 symbol is also outside the frozen word table.

    def test_shared_scalar_and_utf8_vectors(self):
        path = Path(__file__).resolve().parents[2] / "shared/specialist-literal-v4-vectors.json"
        vectors = json.loads(path.read_text())
        for vector in vectors["accepted"]:
            with self.subTest(vector=vector["id"]):
                mask = SpecialistLiteralMask.create(vector["text"], protocol=V4)
                self.assertEqual(vector["masked_text"], mask.masked_text)
                self.assertEqual(vector["text_utf8_sha256"], hashlib.sha256(vector["text"].encode()).hexdigest())
                self.assertEqual(vector["masked_utf8_sha256"], hashlib.sha256(mask.masked_text.encode()).hexdigest())
                self.assertEqual(len(vector["protected_payloads"]), len(mask.tokens))
                self.assertEqual(vector["text"].encode(), mask.restore(mask.masked_text).encode())
        for text in vectors["rejected"]:
            with self.subTest(rejected=text), self.assertRaises(ValueError):
                SpecialistLiteralMask.create(text, protocol=V4)

    def test_legacy_default_does_not_protect_single_quotes(self):
        text = "Keep 'Uh, wait here' and ‘ready later’ exactly."
        self.assertEqual(text, SpecialistLiteralMask.create(text).masked_text)
        self.assertNotIn("Uh", SpecialistLiteralMask.create(text, protocol=V4).masked_text)

    def test_dictionary_inside_quotes_has_exact_expanded_bytes_after_surrounding_cleanup(self):
        text = "Um, keep '[[FREEHAND_LITERAL_01_START]]  café\tΔ🙂\r\n  [[FREEHAND_LITERAL_01_END]]' and ‘Uh, wait.’"
        mask = SpecialistLiteralMask.create(text, protocol=V4)
        self.assertNotIn("café", mask.masked_text)
        self.assertNotIn("FREEHAND_LITERAL_TOKEN_", mask.masked_text)
        self.assertEqual(text.replace("Um, keep", "Keep"), mask.restore(mask.masked_text.replace("Um, keep", "Keep")))

    def test_missing_duplicate_reordered_or_unknown_spans_cannot_restore(self):
        mask = SpecialistLiteralMask.create("'same' ‘same’", protocol=V4)
        a, b = mask.tokens
        for edited in (a, a + " " + a + " " + b, b + " " + a, mask.masked_text + " FHX_deadbeef"):
            with self.subTest(edited=edited), self.assertRaises(ValueError):
                mask.restore(edited)

    def test_terminal_normalization_preserves_hidden_quote_bytes(self):
        text = "Keep 'Do not change.'\r\n  "
        mask = SpecialistLiteralMask.create(text, protocol=V4)
        end = len(mask.masked_text.rstrip())
        self.assertEqual(text, mask.restore(mask.masked_text[:end] + "." + mask.masked_text[end:]))

    def test_invalid_scalars_excessive_nesting_and_unknown_protocol_fail(self):
        for text in ("\ud800", "\udfff", '‘' * 65 + "word" + '’' * 65):
            with self.subTest(text=repr(text)), self.assertRaises(ValueError):
                SpecialistLiteralMask.create(text, protocol=V4)
        for protocol in (True, 4, None, "specialist-compact-v5"):
            with self.subTest(protocol=protocol), self.assertRaises(ValueError):
                SpecialistLiteralMask.create("text", protocol=protocol)
        with self.assertRaises(ValueError):
            SpecialistLiteralMask.create("'word'", remove_added_quote_period=False, protocol=V4)


if __name__ == "__main__":
    unittest.main()
