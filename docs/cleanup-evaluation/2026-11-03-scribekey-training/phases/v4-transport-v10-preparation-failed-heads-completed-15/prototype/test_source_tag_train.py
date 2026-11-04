"""Tiny stdlib source-tag metadata/denominator tests; no Torch/features/model load."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from editor_core import Operation, Program, tokenize_source
import source_tag_train as train


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class NoGrad:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class MetadataTests(unittest.TestCase):
    def fixture(self, root):
        document = tokenize_source('send report')
        encoder = {'synthetic': 'source-only'}
        row = {'id': 'one', 'source_id': 'source-one', 'split': 'train',
            'input': document.text, 'target': document.text,
            'source_sha256': digest(document.text), 'target_sha256': digest(document.text),
            'protected_spans': [], 'source_atoms': [asdict(atom) for atom in document.atoms],
            'input_status': 'ready', 'encoder_contract': encoder, 'label': {'supported': False}}
        plan = {'cases': [row]}; plan_path = root/'plan.json'
        plan_path.write_text(json.dumps(plan))
        feature = root/'synthetic.f32'; feature.write_bytes(b'\0'*(len(document.atoms)*1024*4))
        cached = {'id': 'one', 'source_id': 'source-one', 'split': 'train', 'status': 'ok',
            'source_sha256': row['source_sha256'], 'encoder_contract_sha256': train.canonical_sha(encoder),
            'shape': [len(document.atoms), 1024], 'dtype': 'float32-le',
            'atom_features_path': feature.name, 'atom_features_sha256': train.sha(feature)}
        cache = {'plan_sha256': train.sha(plan_path), 'cases': [cached], 'owned_process_reaped': True, 'cpu_release': True}
        cache_path = root/'cache-manifest.json'; cache_path.write_text(json.dumps(cache))
        release_path = root/'cpu-release.json'
        release_path.write_text(json.dumps({'released': True, 'owned_process_reaped': True,
            'cache_manifest_sha256': train.sha(cache_path)}))
        return plan_path, cache_path, plan, cache

    def load(self, plan, cache):
        return train.load_plan_cache(plan, cache, expected_plan_sha=train.sha(plan),
            expected_count=1, expected_train=1, expected_dev=0)

    def rewrite(self, root, plan_path, cache_path, plan, cache):
        plan_path.write_text(json.dumps(plan)); cache['plan_sha256'] = train.sha(plan_path)
        cache_path.write_text(json.dumps(cache))
        (root/'cpu-release.json').write_text(json.dumps({'released': True, 'owned_process_reaped': True,
            'cache_manifest_sha256': train.sha(cache_path)}))

    def test_exact_metadata_and_released_native_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); p, c, plan, cache = self.fixture(root)
            _, _, entries = self.load(p, c)
            self.assertEqual(1, len(entries)); self.assertIsNotNone(entries[0]['feature_path'])
            cache['cpu_release'] = 1
            self.rewrite(root, p, c, plan, cache)
            with self.assertRaisesRegex(ValueError, 'explicit native'):
                self.load(p, c)

    def test_missing_release_binding_and_wrong_feature_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); p, c, plan, cache = self.fixture(root)
            release = root/'cpu-release.json'; release.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'release'):
                self.load(p, c)
            self.rewrite(root, p, c, plan, cache)
            (root/'synthetic.f32').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'Feature bytes'):
                self.load(p, c)

    def test_all_rows_retained_without_cached_features(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); p, c, plan, cache = self.fixture(root)
            cache['cases'][0]['status'] = 'input_unsupported'
            self.rewrite(root, p, c, plan, cache)
            _, _, entries = self.load(p, c)
            self.assertEqual(1, len(entries)); self.assertIsNone(entries[0]['feature_path'])
            self.assertEqual('input_unsupported', entries[0]['feature_status'])

    def test_wrong_source_contract_split_and_escaping_path_rejected(self):
        for field, value in (('source_sha256', 'f'*64), ('encoder_contract_sha256', 'f'*64),
                ('split', 'development'), ('atom_features_path', '../elsewhere.f32')):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); p, c, plan, cache = self.fixture(root)
                cache['cases'][0][field] = value
                self.rewrite(root, p, c, plan, cache)
                with self.assertRaises(ValueError):
                    self.load(p, c)

    def test_new_label_compiler_retains_supported_and_unsupported(self):
        entries = []
        for index, target in enumerate(('send report', 'Mallory')):
            doc = tokenize_source('send report')
            entries.append({'document': doc, 'row': {'id': str(index), 'split': 'train',
                'input': doc.text, 'target': target, 'source_sha256': digest(doc.text),
                'target_sha256': digest(target), 'label': {'supported': False}}})
        vocabulary, inventory = train.compile_labels(entries)
        self.assertEqual(2, len(inventory))
        self.assertTrue(inventory[0]['supported']); self.assertFalse(inventory[1]['supported'])
        self.assertEqual(vocabulary.sha256, inventory[0]['vocabulary_sha256'])

    def test_target_unsupported_still_forwarded_and_retained_at_evaluation(self):
        document = tokenize_source('send report')
        entry = {'document': document, 'features': object(), 'feature_status': 'ok',
            'label': SimpleNamespace(supported=False),
            'row': {'id': 'unsupported', 'source_id': 'one', 'split': 'development', 'target': 'sent report'}}
        inputs = []
        class Model:
            vocabulary = object()
            def eval(self):
                pass
            def __call__(self, features, padding):
                inputs.append((features, padding)); return {'source': 'logits'}
        execution = SimpleNamespace(text=document.text, trace=[])
        decoded = SimpleNamespace(accepted=True, execution=execution,
            program=Program((Operation('copy', 0),)), diagnostics={}, reasons=())
        with (patch.object(train, 'batch_inputs', return_value=('source-features', 'source-padding')),
                patch.object(train, 'sample_scores', return_value={}),
                patch('source_tag_contract.decode_tag_scores', return_value=decoded)):
            results = train.evaluate_entries(Model(), [entry], SimpleNamespace(no_grad=NoGrad), deadline=time.monotonic()+5)
        self.assertEqual([('source-features', 'source-padding')], inputs)
        self.assertEqual(1, len(results)); self.assertTrue(results[0]['accepted'])
        self.assertFalse(results[0]['exact_canonical']); self.assertFalse(results[0]['fallback_success_credit'])

    def test_deadline_preserves_every_evaluation_row_without_forward(self):
        entries = [{'row': {'id': str(i), 'split': 'development'},
            'label': SimpleNamespace(supported=False)} for i in range(16)]
        model = SimpleNamespace(eval=lambda: None)
        results = train.evaluate_entries(model, entries, object(), deadline=0)
        self.assertEqual(16, len(results))
        self.assertTrue(all(row['status'] == 'not_attempted' for row in results))

    def test_ce_eligibility_does_not_claim_actual_use(self):
        entries = [{'row': {'id': str(i), 'split': 'train'}, 'features': object(), 'feature_status': 'ok',
            'label': SimpleNamespace(supported=True, reasons=())} for i in range(2)]
        results = train.case_statuses(entries, {'0'})
        self.assertTrue(all(row['eligible_for_ce'] for row in results))
        self.assertTrue(results[0]['used_for_ce']); self.assertFalse(results[1]['used_for_ce'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
