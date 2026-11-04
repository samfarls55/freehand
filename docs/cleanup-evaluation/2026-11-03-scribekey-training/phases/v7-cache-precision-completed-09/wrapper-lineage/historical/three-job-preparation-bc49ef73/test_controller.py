"""Tiny pure-Python controller checks; no model/Probe/evaluation imports."""
from pathlib import Path
from copy import deepcopy
import importlib.util
import tempfile
import json
import os
import sys
import unittest

spec = importlib.util.spec_from_file_location('f32_controller', Path(__file__).with_name('run.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def profile():
    return {'cacheTypeK': 'f16', 'cacheTypeV': 'f16', 'promptLookupTokens': 16,
        'contextSize': 1024, 'adapterPath': '/tmp/adapter.gguf', 'adapterSha256': 'a'*64, 'adapterScale': 1}


def argv():
    output = [str(c.RUNTIME)]
    for name, value in c.expected_native_options(Path('/tmp/adapter.gguf')).items():
        output.extend([name, value])
    return output + ['--no-repack', '--no-context-shift', '--no-jinja', '--offline']


class ControllerTests(unittest.TestCase):
    def test_only_two_cache_fields_change(self):
        old = profile()
        new = dict(old, cacheTypeK='f32', cacheTypeV='f32')
        c.verify_profile_change(old, new)
        new['promptLookupTokens'] = 24
        with self.assertRaisesRegex(ValueError, 'besides'):
            c.verify_profile_change(old, new)

    def test_mixed_precision_or_relabelled_history_rejected(self):
        old = profile()
        with self.assertRaisesRegex(ValueError, 'Both'):
            c.verify_profile_change(old, dict(old, cacheTypeK='f32'))
        with self.assertRaisesRegex(ValueError, 'Historical'):
            c.verify_profile_change(dict(old, cacheTypeK='f32', cacheTypeV='f32'), dict(old, cacheTypeK='f32', cacheTypeV='f32'))

    def test_actual_fixed_f32_unit_argv_accepted(self):
        c.verify_native_arguments(argv(), Path('/tmp/adapter.gguf'))

    def test_cache_drift_and_duplicate_flags_rejected(self):
        values = argv()
        values[values.index('--cache-type-v') + 1] = 'f16'
        with self.assertRaisesRegex(ValueError, 'cache-type-v'):
            c.verify_native_arguments(values, Path('/tmp/adapter.gguf'))
        with self.assertRaisesRegex(ValueError, 'cache-type-k'):
            c.verify_native_arguments(argv()+['--cache-type-k', 'f32'], Path('/tmp/adapter.gguf'))

    def test_adapter_scale_or_weight_identity_cannot_drift(self):
        with self.assertRaisesRegex(ValueError, 'scaled twice'):
            c.verify_native_arguments(argv()+['--lora-scaled', '/tmp/adapter.gguf:2'], Path('/tmp/adapter.gguf'))
        with self.assertRaisesRegex(ValueError, 'lora'):
            c.verify_native_arguments(argv(), Path('/tmp/other.gguf'))

    def test_fixed_mode_flags_required(self):
        values = argv()
        values.remove('--no-repack')
        with self.assertRaisesRegex(ValueError, 'mode'):
            c.verify_native_arguments(values, Path('/tmp/adapter.gguf'))

    def test_artifact_hash_and_size_are_both_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'artifact'
            path.write_bytes(b'known bytes')
            entry = c.artifact(path)
            self.assertEqual(c.pinned(path, entry['sha256'], entry['bytes']), entry)
            with self.assertRaisesRegex(ValueError, 'drift'):
                c.pinned(path, entry['sha256'], entry['bytes']+1)
            path.write_bytes(b'other bytes')
            with self.assertRaisesRegex(ValueError, 'drift'):
                c.pinned(path, entry['sha256'], entry['bytes'])

    def test_f16_bridge_retains_exact_profile_and_native_default_auto(self):
        old = profile()
        c.verify_profile_change(old, old, 'f16')
        values = argv()
        for name in ['--cache-type-k', '--cache-type-v']:
            values[values.index(name)+1] = 'f16'
        c.verify_native_arguments(values, Path('/tmp/adapter.gguf'), 'f16')
        with self.assertRaisesRegex(ValueError, 'Flash attention'):
            c.verify_native_arguments(values+['--flash-attn', 'off'], Path('/tmp/adapter.gguf'), 'f16')

    def literal_row(self, nonce='a'*32):
        marked = 'Please [[FREEHAND_LITERAL_' + nonce + '_0_START]]Alpha Harbor[[FREEHAND_LITERAL_' + nonce + '_0_END]].'
        return {'id':'fixture', 'input':'Please custom replacement.', 'normalized_input':'Please Alpha Harbor.',
            'cleanup_input':marked, 'candidate_text':marked, 'output':'Please Alpha Harbor.',
            'cleanup_status':'Applied', 'error':None, 'insertion_count':1, 'delivered_count':1,
            'delivery_outcome':'Delivered', 'dictation_outcome':'Inserted', 'normalized_targets':['Please Alpha Harbor.'],
            'normalized_checks': {'literals':['Alpha Harbor']}}

    def test_nonce_adjustment_changes_only_exact_guid_inside_valid_markers(self):
        left, _ = c.nonce_adjusted_fields(self.literal_row())
        right, _ = c.nonce_adjusted_fields(self.literal_row('b'*32))
        self.assertEqual(left, right)
        self.assertIn('Alpha Harbor', left['cleanup_input'])
        self.assertIn('_0_START]]', left['cleanup_input'])
        row = self.literal_row()
        row['output'] = 'Please Alpha Harbour.'
        changed, _ = c.nonce_adjusted_fields(row)
        self.assertNotEqual(left['output'], changed['output'])

    def test_nonce_pair_payload_and_consistency_must_validate(self):
        for field, old, new in [('candidate_text', '_0_END', '_1_END'),
                ('candidate_text', 'a'*32, 'b'*32), ('cleanup_input', 'Alpha Harbor', 'Wrong Payload')]:
            row = self.literal_row()
            row[field] = row[field].replace(old, new)
            with self.subTest(field=field, old=old), self.assertRaises(ValueError):
                c.nonce_adjusted_fields(row)

    def test_full_bridge500_proof_has13_fields_and_no_semantic_credit(self):
        reference = []
        actual = []
        for index in range(500):
            old = self.literal_row()
            old['id'] = str(index)
            new = self.literal_row('b'*32)
            new['id'] = str(index)
            reference.append(old)
            actual.append(new)
        proof = c.compare_thirteen_fields(reference, actual)
        self.assertEqual(len(proof['compared_fields']), 13)
        self.assertEqual(proof['raw_all13_equal_count'], 0)
        self.assertEqual(proof['nonce_adjusted_all13_equal_count'], 500)
        self.assertFalse(proof['semantic_credit_assigned'])
        actual[0]['output'] = 'Wrong restored output.'
        proof = c.compare_thirteen_fields(reference, actual)
        self.assertEqual(proof['nonce_adjusted_all13_equal_count'], 499)
        self.assertFalse(proof['all500_full13_equal_after_nonce_only_adjustment'])

    def test_owned_group_timeout_preserves_receipt_and_reaps_child(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory)/'timeout.log'
            result = c.execute([sys.executable, '-c', 'import time;time.sleep(5)'], log,
                dict(os.environ), timeout_seconds=.05)
            self.assertEqual(result['termination_reason'], 'bounded_controller_timeout')
            self.assertTrue(result['owned_process_group_cleanup_completed'])
            self.assertTrue(log.with_suffix('.command-receipt.json').is_file())
            self.assertEqual(json.loads(log.with_suffix('.command-receipt.json').read_text())['pid'], result['pid'])
            with self.assertRaises(ProcessLookupError):
                os.killpg(result['owned_process_group'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
