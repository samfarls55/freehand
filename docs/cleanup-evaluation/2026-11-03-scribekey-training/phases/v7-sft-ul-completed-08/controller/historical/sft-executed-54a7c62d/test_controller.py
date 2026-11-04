"""Small source-only checks. No Torch, converter, native runtime or corpus load."""
from copy import deepcopy
from pathlib import Path
import importlib.util
import unittest
import json
import hashlib
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('v7_export_controller', Path(__file__).with_name('run.py'))
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def fixture(eta=0):
    config = {'seed': 42, 'train_rows': 2754, 'epochs': 1, 'batch_size': 4,
        'gradient_accumulation': 2, 'learning_rate': .00003, 'threads': 4, 'max_tokens': 1024,
        'rank': 8, 'alpha': 16, 'scaling': 2, 'dtype': 'float32', 'optimizer': 'AdamW', 'weight_decay': 0,
        'effective_warmup_steps': 34, 'schedule_total_optimizer_steps': 345, 'planned_execution_steps': 345,
        'full_examples_truncated': 0, 'checkpoint_every_steps': 16, 'rank_expansion': None,
        'train_sha256': controller.V7_DATA_SHA, 'training_source_sha256': controller.V7_SOURCE_SHA,
        'quantized_training_source_sha256': controller.V7_SOURCE_SHA, 'parent_adapter_sha256': controller.PARENT_SHA,
        'parent_adapter_config_sha256': '1a159297809162e628c7b3b44079b832a10d78f63a881d2902777aaa5797c490',
        'unlikelihood_schema': 'freehand-unlikelihood-token-events-v1',
        'unlikelihood_events_sha256': controller.V7_EVENTS_SHA,
        'unlikelihood_positive_sha256': controller.V7_DATA_SHA,
        'unlikelihood_tokenizer_sha256': controller.V7_TOKENIZER_SHA,
        'unlikelihood_mapping_sha256': controller.V7_MAPPING_SHA,
        'unlikelihood_source_sha256': controller.V7_SOURCE_SHA,
        'unlikelihood_eta': eta, 'blind_evaluation_read': False, 'resume_optimizer': False,
        'resume_adapter_sha256': controller.PARENT_SHA}
    result = {'completed': True, 'max_steps_limited': False, 'steps': 345, 'microbatches': 689}
    return config, result


def objective_fixture(eta=0):
    rows = []
    micro = 0
    for step in range(1, 346):
        parts = []
        for _ in range(2 if step < 345 else 1):
            count = int(micro < 64)
            evaluated = eta == 1 and count > 0
            part = {'event_count': count, 'assistant_tokens': 2, 'eta': eta,
                'ul_evaluated': evaluated, 'ul_sum': .2 if evaluated else 0}
            part['ce_sum' if evaluated else 'ce_mean'] = 1 if evaluated else .5
            parts.append(part)
            micro += 1
        rows.append({'step': step, 'microbatch': micro, 'unlikelihood_eta': eta,
            'objective_microbatches': parts,
            'loss': sum((v.get('ce_sum', 1) + eta*v['ul_sum'])/2 for v in parts)/len(parts), 'seconds': step})
    return rows, {'assistant_tokens': 1378}


class ControllerGuardTests(unittest.TestCase):
    def test_both_preregistered_arms_accepted(self):
        for arm, eta in [('sft', 0), ('ul', 1)]:
            self.assertEqual(controller.verify_v7_config(*fixture(eta), arm), eta)

    def test_eta_cannot_relabel_other_arm(self):
        for arm, eta in [('sft', 1), ('ul', 0)]:
            with self.assertRaisesRegex(ValueError, 'unlikelihood_eta'):
                controller.verify_v7_config(*fixture(eta), arm)

    def test_bool_eta_rejected_even_when_equal_zero_or_one(self):
        for arm, eta in [('sft', False), ('ul', True)]:
            with self.assertRaisesRegex(ValueError, 'unlikelihood_eta'):
                controller.verify_v7_config(*fixture(eta), arm)

    def test_original_v5_parent_rejected(self):
        config, result = fixture()
        config['parent_adapter_sha256'] = '741826d27bf20da1c59eebc5d397f0a7de972ef1f566ce7e04abbf8abc0cf961'
        with self.assertRaisesRegex(ValueError, 'parent_adapter_sha256'):
            controller.verify_v7_config(config, result, 'sft')

    def test_preregistered_hyperparameters_cannot_drift(self):
        for key, changed in [('seed', 43), ('train_rows', 2014), ('epochs', 2),
                ('learning_rate', .00005), ('rank', 16), ('unlikelihood_mapping_sha256', 'a'*64),
                ('train_sha256', 'b'*64), ('training_source_sha256', 'c'*64)]:
            config, result = fixture()
            config[key] = changed
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, key):
                controller.verify_v7_config(config, result, 'sft')

    def test_partial_or_limited_training_cannot_export(self):
        for key, changed in [('completed', False), ('max_steps_limited', True), ('steps', 344), ('microbatches', 688)]:
            config, result = fixture()
            result[key] = changed
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, '345'):
                controller.verify_v7_config(config, result, 'sft')

    def test_recovery_requires_exact_rng_and_source(self):
        config, result = fixture()
        config.update(resume_optimizer=True, resume_rng_restore_mode='exact_saved_torch_cpu_and_python',
            resume_source_training_code_sha256=controller.V7_SOURCE_SHA)
        self.assertEqual(controller.verify_v7_config(config, result, 'sft'), 0)
        for key, changed in [('resume_rng_restore_mode', 'legacy'), ('resume_source_training_code_sha256', 'd'*64)]:
            changed_config = deepcopy(config)
            changed_config[key] = changed
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'RNG'):
                controller.verify_v7_config(changed_config, result, 'sft')

    def test_blind_read_and_missing_parent_config_rejected(self):
        config, result = fixture()
        config['blind_evaluation_read'] = True
        with self.assertRaisesRegex(ValueError, 'blind'):
            controller.verify_v7_config(config, result, 'sft')
        config, result = fixture()
        del config['parent_adapter_config_sha256']
        with self.assertRaisesRegex(ValueError, 'parent_adapter_config_sha256'):
            controller.verify_v7_config(config, result, 'sft')

    def test_resume_flag_is_strict_boolean(self):
        for value in [1, 0, 'true', None]:
            config, result = fixture()
            config['resume_optimizer'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'JSON boolean'):
                controller.verify_v7_config(config, result, 'sft')

    def test_objective_arithmetic_both_arms_and_total_exposures(self):
        for eta in [0, 1]:
            rows, result = objective_fixture(eta)
            proof = controller.verify_objective_log(rows, result, eta)
            self.assertTrue(proof['all345_step_losses_recomputed_from_microbatches'])
            self.assertTrue(proof['per_exposure_ids_not_recorded_by_trainer'])
            rows[0]['loss'] += .1
            with self.assertRaisesRegex(ValueError, 'arithmetic'):
                controller.verify_objective_log(rows, result, eta)

    def test_objective_missing_exposure_and_wrong_eta_path_rejected(self):
        rows, result = objective_fixture()
        rows[0]['objective_microbatches'][0]['event_count'] = 0
        with self.assertRaisesRegex(ValueError, '64 total'):
            controller.verify_objective_log(rows, result, 0)
        rows, result = objective_fixture(1)
        rows[0]['objective_microbatches'][0]['ul_evaluated'] = False
        with self.assertRaisesRegex(ValueError, 'evaluation path'):
            controller.verify_objective_log(rows, result, 1)

    def test_canonical_recovery_combines_prefix_and_replayed_suffix_once(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            initial = task/'pipeline/v7-sft-01'
            resumed = task/'pipeline/v7-sft-02'
            checkpoint = initial/'checkpoints/step-000192'
            checkpoint.mkdir(parents=True)
            resumed.mkdir()
            dump = lambda path, value: path.write_text(json.dumps(value))
            art = lambda path: {'path': str(path), 'bytes': path.stat().st_size,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            initial_config, result = fixture()
            dump(initial/'adapter-config.json', initial_config)
            for name in ['adapter.safetensors', 'optimizer.pt', 'rng.pt']:
                (checkpoint/name).write_bytes(name.encode())
            (checkpoint/'adapter-config.json').write_bytes((initial/'adapter-config.json').read_bytes())
            (checkpoint/'training-source.py').write_text('source')
            state = {'rng_states_stored': True, 'global_step': 192, 'global_microbatch': 384,
                'train_sha256': controller.V7_DATA_SHA, 'files': {}}
            for path in checkpoint.iterdir():
                state['files'][path.name] = art(path)
            state['files']['training-source.py']['sha256'] = controller.V7_SOURCE_SHA
            dump(checkpoint/'resume-state.json', state)
            rows, _ = objective_fixture()
            (initial/'training-log.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in rows[:207]))
            (resumed/'training-log.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in rows[192:]))
            canonical = resumed/'canonical-training-log.jsonl'
            canonical.write_text(''.join(json.dumps(v)+'\n' for v in rows))
            dump(resumed/'overlap-replay-complete-proof.json', {'all_nonelapsed_fields_bit_exact': True,
                'replayed_steps': list(range(193,208)), 'actual_saved_rng': True})
            dump(task/'pipeline/v7-sft-01-prelaunch.json', {})
            config = dict(initial_config, resume_optimizer=True, resume_global_step=192,
                resume_global_microbatch=384, resume_checkpoint=str(checkpoint),
                resume_checkpoint_state_sha256=art(checkpoint/'resume-state.json')['sha256'],
                resume_rng_restore_mode='exact_saved_torch_cpu_and_python')
            actual_art = lambda path: dict(art(path), sha256=controller.V7_SOURCE_SHA) if path.name=='training-source.py' else art(path)
            with patch.object(controller, 'TASK', task), patch.object(controller, 'V7_RECOVERY_STATE_SHA', config['resume_checkpoint_state_sha256']):
                combined, artifacts, proof = controller.training_log_lineage(
                    SimpleNamespace(run_dir=resumed, arm='sft'), config, result, actual_art)
                self.assertEqual(combined, rows)
                self.assertEqual(proof['logical_microbatches_counted_once'], 689)
                self.assertTrue(any(v['path']==str(canonical) for v in artifacts))
                canonical.write_text(''.join(json.dumps(v)+'\n' for v in rows[192:]))
                with self.assertRaisesRegex(ValueError, 'Canonical log'):
                    controller.training_log_lineage(SimpleNamespace(run_dir=resumed, arm='sft'), config, result, actual_art)


if __name__ == '__main__':
    unittest.main(verbosity=2)
