import json
import unittest

import benchmark
from literal_protection import LiteralProtectionMask


def block(key, value):
    return f'[[FREEHAND_LITERAL_{key}_START]]{value}[[FREEHAND_LITERAL_{key}_END]]'


class LiteralProtectionTests(unittest.TestCase):
    def test_same_utf8_golden_vectors_as_managed_adapter(self):
        for value, digest in [('  Acme\tLabs  ', 'e772fedf3921e34f0f37d0bbe6231d4f'),
                              ('  café\tΔ🙂  ', '1584b4413f918ffffe43d6b47fd6798e')]:
            original = 'Before ' + block('01', value) + ' after.'
            mask = LiteralProtectionMask.create(original)
            self.assertEqual(f'Before FREEHAND_LITERAL_TOKEN_{digest}_0_END after.', mask.masked_text)
            self.assertEqual(original, mask.restore(mask.masked_text))

    def test_general_request_hides_literal_bytes_and_restores_after_editing(self):
        original = 'Uh, keep ' + block('01', '  v2::Thing<T>\n  value\t ') + ' exactly.'
        mask = LiteralProtectionMask.create(original)
        _, request = benchmark.make_request({'style': 'chat'}, original, 'Policy', 128)
        content = json.loads(request['messages'][1]['content'])['transcript']
        self.assertEqual(mask.masked_text, content)
        self.assertNotIn('Thing<T>', content)
        self.assertEqual(original.removeprefix('Uh, '), mask.restore(content.removeprefix('Uh, ')))

    def test_twelve_adjacent_and_repeated_values_remain_independent(self):
        original = ''.join(block(f'{i:02x}', 'same\tvalue\r\n') for i in range(12))
        mask = LiteralProtectionMask.create(original)
        self.assertEqual(12, len(mask.blocks))
        self.assertEqual(original, mask.restore(mask.masked_text))

    def test_missing_duplicate_unknown_reordered_and_changed_identifiers_fail(self):
        mask = LiteralProtectionMask.create(block('01', 'first') + ' ' + block('02', 'second'))
        first, second = mask.masked_text.split(' ')
        for edited in [first, first + ' ' + first + ' ' + second, second + ' ' + first,
                       mask.masked_text.replace('_0_END', '_00_END'), mask.masked_text.upper(),
                       mask.masked_text + ' FREEHAND_LITERAL_TOKEN_unknown_3_END',
                       mask.masked_text + block('03', 'invented')]:
            with self.subTest(edited=edited), self.assertRaises(ValueError):
                mask.restore(edited)

    def test_ambiguous_malformed_and_reserved_source_text_falls_back(self):
        for text in ['[[FREEHAND_LITERAL_01_START]]unclosed', '[[FREEHAND_LITERAL_01_END]]',
                     block('01', block('02', 'nested')), block('01', 'a') + block('01', 'b'),
                     '[[FREEHAND_LITERAL_01_START]]a[[FREEHAND_LITERAL_02_END]]',
                     block('abcd_0', 'invalid Core key'), 'FREEHAND_LITERAL_TOKEN_reserved_0_END']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                LiteralProtectionMask.create(text)


if __name__ == '__main__':
    unittest.main()
