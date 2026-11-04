"""Tiny synthetic controller checks only; never load evaluation cases."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

module_spec = importlib.util.spec_from_file_location(
    'control_packet', Path(__file__).with_name('create_control_packet.py'))
c = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(c)


def refresh(values):
    selected, control, left, right, review = values
    for packet, report in [(left, selected), (right, control)]:
        packet['structural_success_count'] = sum(c.structural(row) for row in report['cases'])
        for item, row in zip(packet['cases'], report['cases']):
            item['output_sha256'] = c.output_sha(row)
            item['case_structural_sha256'] = c.digest_case(row)
            item['structural_success'] = c.structural(row)
            item['actual_pair'] = {key: row[key] for key in c.PAIR_FIELDS}
    for judgment, row in zip(review['cases'], selected['cases']):
        judgment['output_sha256'] = c.output_sha(row)
        judgment['case_structural_sha256'] = c.digest_case(row)
    review['counts'] = {'total': len(review['cases'])}
    review['counts'].update({key: sum(row[key] is True for row in review['cases'])
                            for key in ['semantic_faithful', 'clean_usable', 'critical_error',
                                        'structural_success', 'joint_success']})
    return values


def fixture(count=1):
    row = {'id': 'synthetic-one', 'split': 'all', 'input': 'Uh, keep this.',
           'normalized_input': 'Uh, keep this.', 'cleanup_input': 'Uh, keep this.',
           'candidate_text': 'Keep this.', 'output': 'Keep this.', 'cleanup_status': 'Applied',
           'error': None, 'insertion_count': 1, 'delivered_count': 1,
           'delivery_outcome': 'Delivered', 'dictation_outcome': 'Success',
           'normalized_targets': ['Identity-only synthetic diagnostic.'],
           'normalized_checks': {'extra': [True, 1, 1.0, None], 'ordered': [1, 2]}}
    rows = [dict(copy.deepcopy(row), id='synthetic-' + str(index)) for index in range(count)]
    selected = {'incomplete': False, 'metadata': {'corpus_sha256': c.FROZEN_CORPUS_SHA256},
                'cases': rows}
    control = copy.deepcopy(selected)
    context = {'schema_version': 1, 'frozen_corpus_sha256': c.FROZEN_CORPUS_SHA256,
               'total': count, 'mode': 'Synthetic fresh review', 'policy': 'Synthetic policy',
               'reference_targets_and_assertion_results_omitted': True, 'required_selected_joint': count}
    left = dict(copy.deepcopy(context), role='selected',
                source_report_sha256=c.SOURCES['selected_report'][1], cases=[])
    right = dict(copy.deepcopy(context), role='original-control',
                 source_report_sha256=c.SOURCES['control_report'][1], cases=[])
    review = {'role': 'selected', 'results_sha256': c.SOURCES['selected_report'][1],
              'packet_sha256': c.SOURCES['selected_packet'][1],
              'frozen_corpus_sha256': c.FROZEN_CORPUS_SHA256, 'all500_personally_read': True,
              'development_judgment_inheritance_count': 0, 'cases': []}
    for position, source in enumerate(rows, 1):
        packet_row = {'position_one_based': position, 'case_id': source['id'], 'category': 'synthetic',
                      'frozen_author_notes': 'Preserve intended statement.',
                      'author_needs_cleanup_flag': True, 'author_critical_probe_flag': False,
                      'new_semantic_judgment': None}
        left['cases'].append(copy.deepcopy(packet_row))
        right['cases'].append(copy.deepcopy(packet_row))
        review['cases'].append({'position_one_based': position, 'case_id': source['id'],
            'structural_success': True, 'semantic_faithful': True, 'clean_usable': True,
            'critical_error': False, 'joint_success': True, 'reason': 'Synthetic prior judgment.',
            'review_mode': 'personally_read_no_inheritance'})
    return refresh([selected, control, left, right, review])


def build(values):
    return c.build_packet(*values, expected_count=len(values[0]['cases']))


class ControllerChecks(unittest.TestCase):
    def test_identical_success_is_reused_without_new_semantic_grading(self):
        result = build(fixture())
        self.assertEqual((result['inheritance_count'], result['personal_read_required']), (1, 0))
        self.assertEqual(result['new_semantic_judgments_assigned'], 0)

    def test_true_one_numeric_types_nested_order_and_signed_zero_differ(self):
        for left, right in [(True, 1), (1, 1.0), (-0.0, 0.0), ([1, 2], [2, 1]),
                            ({'nested': [True]}, {'nested': [1]})]:
            self.assertFalse(c.typed_equal(left, right))
        self.assertTrue(c.typed_equal({'b': [], 'a': 1}, {'a': 1, 'b': []}))
        values = fixture()
        values[1]['cases'][0]['normalized_checks']['extra'][0] = 1
        result = build(refresh(values))
        self.assertEqual(result['inheritance_count'], 0)
        self.assertFalse(result['cases'][0]['exact_fields_equal']['normalized_checks'])

    def test_changed_output_requires_actual_personal_read(self):
        values = fixture()
        values[1]['cases'][0]['output'] = 'Changed synthetic output.'
        result = build(refresh(values))
        self.assertEqual(result['personal_read_required'], 1)
        self.assertEqual(result['cases'][0]['actual_pair']['output'], 'Changed synthetic output.')

    def test_prior_failure_is_never_inherited_even_if_identical(self):
        values = fixture()
        values[4]['cases'][0].update(semantic_faithful=False, clean_usable=False,
                                   critical_error=True, joint_success=False)
        result = build(refresh(values))
        self.assertEqual(result['inheritance_count'], 0)
        self.assertNotIn('inherited_selected_judgment', result['cases'][0])

    def test_provider_failure_gets_zero_joint_credit_and_requires_read(self):
        values = fixture()
        values[1]['cases'][0].update(cleanup_status='Failed', error='Synthetic provider failure')
        result = build(refresh(values))
        self.assertEqual((result['inheritance_count'], result['forced_zero_joint_credit_count']), (0, 1))
        self.assertFalse(result['cases'][0]['joint_credit_allowed_after_personal_review'])
        self.assertTrue(result['cases'][0]['forced_joint_success_false'])
        self.assertIsNone(result['cases'][0]['new_semantic_judgment'])

    def test_all_thirteen_fields_are_required(self):
        for field in c.FIELDS:
            values = fixture()
            del values[1]['cases'][0][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                build(values)

    def test_target_checks_are_identity_only_and_omitted_from_manual_pair(self):
        for field, value in [('normalized_targets', ['Different synthetic diagnostic.']),
                             ('normalized_checks', {'ordered': [2, 1]})]:
            values = fixture()
            values[1]['cases'][0][field] = value
            result = build(refresh(values))
            self.assertEqual(result['inheritance_count'], 0)
            pair = result['cases'][0]['actual_pair']
            self.assertEqual(set(pair), set(c.PAIR_FIELDS))
            self.assertNotIn('normalized_targets', pair)
            self.assertNotIn('normalized_checks', pair)

    def test_frozen_notes_context_or_global_corpus_mismatch_rejected(self):
        for mutate in [
            lambda v: v[3]['cases'][0].update(frozen_author_notes='Changed synthetic context'),
            lambda v: v[3].update(policy='Changed policy'),
            lambda v: v[1]['metadata'].update(corpus_sha256='0' * 64),
        ]:
            values = fixture()
            mutate(values)
            with self.assertRaises(ValueError):
                build(values)

    def test_completeness_duplicate_reordered_and_packet_binding_rejected(self):
        for mutate in [
            lambda v: v[1].update(incomplete=True),
            lambda v: v[1].pop('incomplete'),
            lambda v: v[1]['cases'][1].update(id=v[1]['cases'][0]['id']),
            lambda v: v[1]['cases'].reverse(),
            lambda v: v[3]['cases'][0].update(output_sha256='wrong'),
            lambda v: v[4]['cases'][0].update(case_structural_sha256='wrong'),
        ]:
            values = fixture(2)
            mutate(values)
            with self.assertRaises(ValueError):
                build(values)

    def test_no_development_inheritance_or_numeric_boolean_flags(self):
        for mutate in [
            lambda v: v[4].update(development_judgment_inheritance_count=1),
            lambda v: v[4].update(all500_personally_read=False),
            lambda v: v[4]['cases'][0].update(joint_success=1),
        ]:
            values = fixture()
            mutate(values)
            with self.assertRaises(ValueError):
                build(values)
        values = fixture()
        values[1]['cases'][0]['delivered_count'] = True
        result = build(refresh(values))
        self.assertEqual(result['inheritance_count'], 0)
        self.assertFalse(result['cases'][0]['structural_success'])

    def test_duplicate_json_keys_nonfinite_or_wrong_pin_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.json'
            for raw in [b'{"a":1,"a":2}', b'{"a":NaN}']:
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    c.load_pinned(path, c.sha(raw))
            path.write_bytes(b'{}')
            with self.assertRaises(ValueError):
                c.load_pinned(path, '0' * 64)


if __name__ == '__main__':
    unittest.main()

