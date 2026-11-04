import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('knownsets_packet', Path(__file__).with_name('create_packet.py'))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


def fixture():
    row = {'id': 'one', 'input': 'Uh, keep this.', 'normalized_input': 'Uh, keep this.',
           'cleanup_input': 'Uh, keep this.', 'candidate_text': 'Keep this.', 'output': 'Keep this.',
           'cleanup_status': 'Applied', 'error': None, 'insertion_count': 1, 'delivered_count': 1,
           'delivery_outcome': 'Delivered', 'dictation_outcome': 'Success',
           'normalized_targets': ['Diagnostic only.'],
           'normalized_checks': {'ordered': [], 'extra': [True, 1, 1.0, None]}}
    two = copy.deepcopy(row); two['id'] = 'two'
    old = {'incomplete': False, 'cases': [row, two]}
    prior = {'results_sha256': 'a' * 64, 'cases': [
        {'case_id': 'one', 'output_sha256': c.sha(row['output'].encode()), 'semantic_faithful': True,
         'clean_usable': True, 'critical_error': False},
        {'case_id': 'two', 'output_sha256': c.sha(two['output'].encode()), 'semantic_faithful': False,
         'clean_usable': False, 'critical_error': True}]}
    spec = {'count': 2, 'expected_prior_joint': 1, 'expected_prior_critical': 1,
            'report_sha256': 'a' * 64, 'review_sha256': 'b' * 64}
    return old, prior, copy.deepcopy(old), spec, 'c' * 64


class PacketGuards(unittest.TestCase):
    def test_selfcomparison_inherits_success_only(self):
        packet = c.build_packet(*fixture())
        self.assertEqual((packet['inheritance_count'], packet['personal_read_required']), (1, 1))
        self.assertFalse(packet['cases'][1]['inherit_successful_prior_joint_pass'])
        self.assertEqual(packet['new_semantic_passes_assigned'], 0)

    def test_all13_fields_are_required_and_changes_force_read(self):
        for key in c.FIELDS:
            values = fixture(); values[2]['cases'][0].pop(key)
            with self.subTest(missing=key), self.assertRaises(ValueError): c.build_packet(*values)
        values = fixture(); values[2]['cases'][0]['candidate_text'] += ' Added.'
        self.assertEqual(c.build_packet(*values)['personal_read_required'], 2)

    def test_targets_and_checks_are_identity_only_not_manual_oracle(self):
        for key, value in [('normalized_targets', ['Different diagnostic']), ('normalized_checks', {'ordered': ['new']})]:
            values = fixture(); values[2]['cases'][0][key] = value
            packet = c.build_packet(*values)
            self.assertEqual(packet['personal_read_required'], 2)
            pair = packet['cases'][0]['actual_pair']
            self.assertNotIn('normalized_targets', pair); self.assertNotIn('normalized_checks', pair)

    def test_nested_JSON_bool_int_float_and_list_order_are_distinct(self):
        for left, right in [(True, 1), (1, 1.0), (-0.0, 0.0), ([1, 2], [2, 1]),
                            ({'a': [True]}, {'a': [1]}), (None, 'null')]:
            with self.subTest(left=left, right=right): self.assertFalse(c.typed_equal(left, right))
        self.assertTrue(c.typed_equal({'b': [], 'a': 1}, {'a': 1, 'b': []}))
        values = fixture(); values[2]['cases'][0]['normalized_checks']['extra'][0] = 1
        self.assertEqual(c.build_packet(*values)['inheritance_count'], 0)

    def test_structural_bool_float_count_or_failed_outcome_cannot_inherit(self):
        for key, value in [('delivered_count', True), ('insertion_count', 1.0),
                           ('delivery_outcome', 'Undelivered'), ('dictation_outcome', 'Failed'),
                           ('cleanup_status', 'Failed'), ('error', 'provider failure')]:
            values = fixture(); values[2]['cases'][0][key] = value
            with self.subTest(key=key): self.assertEqual(c.build_packet(*values)['inheritance_count'], 0)

    def test_changed_output_binding_does_not_create_pass(self):
        values = fixture(); values[2]['cases'][0]['output'] = 'Different actual output.'
        packet = c.build_packet(*values)
        self.assertEqual(packet['inheritance_count'], 0)
        self.assertEqual(packet['cases'][0]['actual_pair']['output'], 'Different actual output.')

    def test_partial_wrong_denominator_duplicate_or_reordered_IDS_rejected(self):
        mutators = [lambda v: v[2].update(incomplete=True), lambda v: v[2].pop('incomplete'),
                    lambda v: v[2]['cases'].pop(), lambda v: v[2]['cases'].reverse(),
                    lambda v: v[2]['cases'][1].update(id='one')]
        for mutate in mutators:
            values = fixture(); mutate(values)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): c.build_packet(*values)

    def test_prior_report_review_output_or_boolean_binding_rejected(self):
        mutators = [lambda v: v[1].update(results_sha256='wrong'),
                    lambda v: v[1]['cases'][0].update(output_sha256='wrong'),
                    lambda v: v[1]['cases'][0].update(semantic_faithful=1),
                    lambda v: v[1]['cases'].reverse()]
        for mutate in mutators:
            values = fixture(); mutate(values)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): c.build_packet(*values)

    def test_duplicate_JSON_keys_nonfinite_and_wrong_SHA_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.json'
            for data in (b'{"a":1,"a":2}', b'{"a":NaN}'):
                path.write_bytes(data)
                with self.assertRaises(ValueError): c.load_pinned(path, c.sha(data))
            path.write_text('{}')
            with self.assertRaises(ValueError): c.load_pinned(path, '0' * 64)


if __name__ == '__main__': unittest.main()
