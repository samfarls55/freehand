"""Tiny synthetic V7 objective checks; no original weights or real corpus data."""
from __future__ import annotations
import copy
from contextlib import redirect_stdout
import io
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = next(parent for parent in Path(__file__).resolve().parents if (parent / 'global.json').is_file() and (parent / 'src').is_dir())
STAGED = Path(__file__).with_name('pipeline.py')


def import_pipeline(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pipeline = import_pipeline('staged_unlikelihood_pipeline', STAGED)
ACTIVE = REPO / 'tools/Freehand.Cleanup.Training/pipeline.py'
BASELINE = REPO / 'work/cleanup-scribekey-training-2026-11-03/prototypes/v7-unlikelihood/legacy_pipeline_baseline.py'
LEGACY_SOURCE = Path(os.environ['FREEHAND_LEGACY_PIPELINE_BASELINE']) if os.environ.get('FREEHAND_LEGACY_PIPELINE_BASELINE') else (ACTIVE if STAGED.resolve() != ACTIVE.resolve() else BASELINE)
legacy = import_pipeline('untouched_legacy_pipeline', LEGACY_SOURCE) if LEGACY_SOURCE.is_file() and LEGACY_SOURCE.resolve() != STAGED.resolve() else None
try:
    import torch
    import safetensors.torch  # noqa: F401 - checkpoint serialization dependency
except ImportError:
    torch = None


def historical_mean_ce(model, rows, tensor_library):
    # Independent historical reference remains usable after the staged code is applied.
    ids, labels, attention = pipeline.batch_tensors(rows, tensor_library)
    hidden = model.model(input_ids=ids, attention_mask=attention, use_cache=False).last_hidden_state
    selected = labels[:, 1:] != -100
    logits = model.lm_head(hidden[:, :-1, :][selected])
    return tensor_library.nn.functional.cross_entropy(logits.float(), labels[:, 1:][selected]), int(selected.sum().item())


@unittest.skipIf(torch is None, 'Use the pinned training environment for tiny tensor checks')
class UnlikelihoodMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def rows(self):
        return [
            {'input_ids': [1, 8, 9, 10, 11, 7], 'labels': [-100, -100, -100, 10, 11, 7],
             '_unlikelihood_events': [{'target_token_index': 1, 'bad_token_id': 12, 'gold_token_id': 11,
                'predictor_position': 3, 'event_id': 'wrong-second-token'}]},
            {'input_ids': [1, 8, 13, 7], 'labels': [-100, -100, 13, 7],
             '_unlikelihood_events': [{'target_token_index': 1, 'bad_token_id': 14, 'gold_token_id': 7,
                'predictor_position': 2, 'event_id': 'continue-instead-of-EOS'}]},
        ]

    def tiny_model(self, dropout=0):
        class Hidden(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.embedding = torch.nn.Embedding(16, 5)
                self.dropout = torch.nn.Dropout(dropout)
                self.calls = 0

            def forward(self, input_ids, attention_mask=None, use_cache=False):
                self.calls += 1
                return SimpleNamespace(last_hidden_state=self.dropout(self.embedding(input_ids)))

        class Head(torch.nn.Linear):
            def __init__(self):
                super().__init__(5, 16, bias=False)
                self.calls = 0

            def forward(self, values):
                self.calls += 1
                return super().forward(values)

        class TinyModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.model = Hidden()
                self.lm_head = Head()

        return TinyModel().train()

    def test_overconfident_bad_token_remains_finite_with_correct_nonzero_gradient(self):
        for magnitude, tolerance in ((20., 1e-6), (1000., 3e-5)):
            with self.subTest(magnitude=magnitude):
                logits = torch.tensor([[magnitude, -magnitude, -magnitude - 1]], requires_grad=True)
                target = torch.tensor([1])
                loss = pipeline.chosen_token_loss(logits, target, [(0, 0)], 1., torch)
                expected_ul = 2 * magnitude - math.log1p(math.exp(-1))
                self.assertTrue(torch.isfinite(loss))
                self.assertAlmostEqual(2 * magnitude + expected_ul, loss.item(), delta=.0005)
                loss.backward()
                conditional = 1 / (1 + math.exp(-1))
                expected = torch.tensor([[2., -1 - conditional, -(1 - conditional)]])
                # F32 logsumexp backward at magnitude1000 loses a few1e-5 in exp(logit-LSE).
                torch.testing.assert_close(expected, logits.grad, rtol=1e-6, atol=tolerance)

    def test_ce_plus_event_penalties_is_divided_by_all_assistant_tokens(self):
        logits = torch.tensor([[.1, .7, -.3, .2], [1.1, -.2, .3, .6], [-.4, .2, .9, -.1]], requires_grad=True)
        targets = torch.tensor([1, 0, 2])
        events, eta = [(0, 3), (2, 1)], .4
        actual = pipeline.chosen_token_loss(logits, targets, events, eta, torch)
        ce = torch.nn.functional.cross_entropy(logits, targets, reduction='sum')
        penalties = sum(-torch.log1p(-torch.softmax(logits[index].double(), dim=-1)[bad]) for index, bad in events)
        expected = (ce.double() + eta * penalties) / 3
        torch.testing.assert_close(actual.double(), expected, rtol=1e-6, atol=1e-7)

    def test_shifted_assistant_mapping_includes_eos_and_excludes_prompt_and_padding(self):
        rows = self.rows()
        _, labels, _ = pipeline.batch_tensors(rows, torch)
        self.assertEqual([(1, 12), (4, 14)], pipeline.assistant_event_indices(rows, labels, torch))
        for kind in ('prompt', 'padding', 'gold', 'target_index'):
            malformed = copy.deepcopy(rows)
            if kind == 'prompt': malformed[0]['_unlikelihood_events'][0]['predictor_position'] = 0
            if kind == 'padding': malformed[1]['_unlikelihood_events'][0]['predictor_position'] = 4
            if kind == 'gold': malformed[0]['_unlikelihood_events'][0]['gold_token_id'] = 15
            if kind == 'target_index': malformed[0]['_unlikelihood_events'][0]['target_token_index'] = 3
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                pipeline.assistant_event_indices(malformed, labels, torch)

    def test_positive_eta_reuses_exactly_one_chosen_hidden_and_head_forward(self):
        torch.manual_seed(88)
        model = self.tiny_model()
        rows = self.rows()
        actual, tokens = pipeline.assistant_loss(model, rows, torch, unlikelihood_eta=.3)
        self.assertEqual(5, tokens)
        self.assertEqual((1, 1), (model.model.calls, model.lm_head.calls))
        ids, labels, attention = pipeline.batch_tensors(rows, torch)
        hidden = model.model(input_ids=ids, attention_mask=attention, use_cache=False).last_hidden_state
        selected = labels[:, 1:] != -100
        logits = model.lm_head(hidden[:, :-1][selected])
        expected = pipeline.chosen_token_loss(logits.float(), labels[:, 1:][selected], [(1, 12), (4, 14)], .3, torch)
        torch.testing.assert_close(expected, actual, rtol=0, atol=0)
        actual.backward()
        self.assertTrue(all(torch.isfinite(parameter.grad).all() for parameter in model.parameters()))

    def test_eta_zero_matches_untouched_legacy_forward_optimizer_and_rng_exactly(self):
        torch.manual_seed(1729)
        reference = self.tiny_model(dropout=.25)
        actual = copy.deepcopy(reference)
        reference_optimizer = torch.optim.AdamW(reference.parameters(), lr=.02, betas=(.8, .95), weight_decay=.01)
        actual_optimizer = torch.optim.AdamW(actual.parameters(), lr=.02, betas=(.8, .95), weight_decay=.01)
        for _ in range(3):
            before_rng = torch.get_rng_state().clone()
            expected_loss, expected_tokens = (legacy.assistant_loss if legacy is not None else historical_mean_ce)(reference, self.rows(), torch)
            expected_loss.backward()
            reference_optimizer.step()
            reference_optimizer.zero_grad(set_to_none=True)
            expected_rng = torch.get_rng_state().clone()
            torch.set_rng_state(before_rng)
            loss, tokens = pipeline.assistant_loss(actual, self.rows(), torch, unlikelihood_eta=0.)
            loss.backward()
            actual_optimizer.step()
            actual_optimizer.zero_grad(set_to_none=True)
            self.assertTrue(torch.equal(expected_loss.detach(), loss.detach()))
            self.assertEqual(expected_tokens, tokens)
            self.assertTrue(torch.equal(expected_rng, torch.get_rng_state()))
            for left, right in zip(reference.parameters(), actual.parameters()):
                self.assertTrue(torch.equal(left, right))
                for key, value in reference_optimizer.state[left].items():
                    other = actual_optimizer.state[right][key]
                    self.assertTrue(torch.equal(value, other) if isinstance(value, torch.Tensor) else value == other)
        self.assertEqual((3, 3), (actual.model.calls, actual.lm_head.calls))


class SyntheticEventArtifactTests(unittest.TestCase):
    def fixture(self, root, *, bad_eos=False, copies=2):
        source, gold, bad = 'alpha item', 'alpha beta', 'alpha' if bad_eos else 'alpha gamma'
        prompt, masked_gold, mask = pipeline.protected_pair(source, gold)
        _, masked_bad, _ = pipeline.protected_pair(source, bad)
        token_map = {prompt: [1, 8, 9], masked_gold: [10, 11], masked_bad: [10] if bad_eos else [10, 12]}

        class Tokenizer:
            def encode(self, text, add_special_tokens=False):
                if add_special_tokens:
                    raise AssertionError('Synthetic production prompt already contains its leading BOS')
                return token_map[text]

            def get_vocab(self):
                return {'BOS': 1, 'EOS': 7, 'alpha': 10, 'beta': 11, 'gamma': 12}

        text_sha = lambda value: hashlib.sha256(value.encode('utf-8')).hexdigest()
        value_sha = lambda value: text_sha(json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True))
        raw = [{'id': 'positive-' + str(index), 'input': source, 'target': gold,
                'positive_replay_instance': {'source_id': 'synthetic-source'}} for index in range(copies)]
        positive = root / 'positive.jsonl'
        positive.write_text(''.join(json.dumps(row) + '\n' for row in raw))
        positive_sha = hashlib.sha256(positive.read_bytes()).hexdigest()
        rows = [{**row, 'prompt': prompt, 'masked_target': masked_gold, 'input_ids': [1, 8, 9, 10, 11, 7],
                 'labels': [-100, -100, -100, 10, 11, 7]} for row in raw]
        record = {'id': 'synthetic-event', 'source_270_id': 'synthetic-source', 'input': source, 'gold': gold, 'bad': bad,
            'source_input_sha256': text_sha(source), 'approved_gold_sha256': text_sha(gold),
            'positive_artifact_sha256': positive_sha, 'positive_row_ids': [row['id'] for row in raw],
            'event': {'manual_semantic_branch_audited': True, 'type': 'premature_eos' if bad_eos else 'token',
                'target_token_index_zero_based': 1, 'shared_masked_target_prefix_token_ids': [10],
                'shared_prefix_token_ids_sha256': value_sha([10]), 'gold_next_token_id': 11,
                'bad_next_token_id': 7 if bad_eos else 12, 'bad_id_differs_from_gold_id': True,
                'common_prefix_is_maximal_token_prefix': True, 'prompt_token_count': 3,
                'chosen_forward_predictor_position_zero_based': 3, 'input_derived_literal_count': len(mask.tokens),
                'literal_mapping_sha256': value_sha(list(zip(mask.tokens, mask.payloads))),
                'source_derived_prompt_sha256': text_sha(prompt), 'masked_gold_sha256': text_sha(masked_gold),
                'masked_bad_sha256': text_sha(masked_bad)}}
        events = root / 'events.jsonl'
        events.write_text(json.dumps(record) + '\n')
        return positive, events, rows, record, Tokenizer()

    def test_loader_preserves_rows_and_maps_every_explicit_scheduled_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            positive, events, rows, _, tokenizer = self.fixture(Path(directory))
            before = copy.deepcopy(rows)
            annotated, identity = pipeline.load_unlikelihood_events(events, positive, rows, tokenizer)
            self.assertEqual(before, rows, 'Loader must not mutate caller-owned positive examples')
            self.assertEqual(2, len(annotated))
            self.assertEqual(['positive-0', 'positive-1'], [row['id'] for row in annotated])
            for row in annotated:
                self.assertEqual(1, len(row['_unlikelihood_events']))
                event = row['_unlikelihood_events'][0]
                self.assertEqual((1, 3, 11, 12), tuple(event[key] for key in
                    ('target_token_index', 'predictor_position', 'gold_token_id', 'bad_token_id')))
            self.assertEqual(hashlib.sha256(events.read_bytes()).hexdigest(), identity['unlikelihood_events_sha256'])
            self.assertEqual(hashlib.sha256(positive.read_bytes()).hexdigest(), identity['unlikelihood_positive_sha256'])
            self.assertEqual(hashlib.sha256(STAGED.read_bytes()).hexdigest(), identity['unlikelihood_source_sha256'])
            self.assertEqual(pipeline.UNLIKELIHOOD_SCHEMA, identity['unlikelihood_schema'])

    def test_loader_maps_premature_eos_to_existing_chosen_forward(self):
        with tempfile.TemporaryDirectory() as directory:
            positive, events, rows, _, tokenizer = self.fixture(Path(directory), bad_eos=True, copies=1)
            annotated, _ = pipeline.load_unlikelihood_events(events, positive, rows, tokenizer)
            event = annotated[0]['_unlikelihood_events'][0]
            self.assertEqual(7, event['bad_token_id'])
            self.assertEqual(11, event['gold_token_id'])
            self.assertEqual(3, event['predictor_position'])

    def test_loader_rejects_artifact_hash_fingerprint_index_and_exposure_drift(self):
        mutations = ('positive_hash', 'gold_hash', 'prefix_hash', 'prompt_hash', 'literal_hash', 'predictor',
                     'gold_token', 'bad_token', 'index', 'audit', 'missing_copy', 'unknown_copy', 'nonstring_copy',
                     'wrong_source_metadata', 'row_tokens')
        for kind in mutations:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                positive, events, rows, record, tokenizer = self.fixture(Path(directory))
                if kind == 'positive_hash': positive.write_bytes(positive.read_bytes() + b'\n')
                if kind == 'gold_hash': record['approved_gold_sha256'] = 'f' * 64
                for label, field in (('prefix_hash', 'shared_prefix_token_ids_sha256'),
                                     ('prompt_hash', 'source_derived_prompt_sha256'), ('literal_hash', 'literal_mapping_sha256')):
                    if kind == label: record['event'][field] = 'f' * 64
                if kind == 'predictor': record['event']['chosen_forward_predictor_position_zero_based'] = 2
                if kind == 'gold_token': record['event']['gold_next_token_id'] = 7
                if kind == 'bad_token': record['event']['bad_next_token_id'] = 11
                if kind == 'index': record['event']['target_token_index_zero_based'] = 2
                if kind == 'audit': record['event']['manual_semantic_branch_audited'] = False
                if kind == 'missing_copy': record['positive_row_ids'] = ['positive-0']
                if kind == 'unknown_copy': record['positive_row_ids'] = ['positive-0', 'other']
                if kind == 'nonstring_copy': record['positive_row_ids'] = [['invalid']]
                if kind == 'wrong_source_metadata': rows[0]['positive_replay_instance']['source_id'] = 'wrong-source'
                if kind == 'row_tokens': rows[0]['input_ids'][-1] = 12
                events.write_text(json.dumps(record) + '\n')
                with self.assertRaises(ValueError):
                    pipeline.load_unlikelihood_events(events, positive, rows, tokenizer)

    def test_loader_rejects_duplicate_source_events_and_duplicate_positive_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            positive, events, rows, record, tokenizer = self.fixture(Path(directory))
            second = {**record, 'id': 'second-event'}
            events.write_text(json.dumps(record) + '\n' + json.dumps(second) + '\n')
            with self.assertRaises(ValueError):
                pipeline.load_unlikelihood_events(events, positive, rows, tokenizer)
            events.write_text(json.dumps(record) + '\n')
            with self.assertRaises(ValueError):
                pipeline.load_unlikelihood_events(events, positive, [rows[0], rows[0]], tokenizer)


@unittest.skipIf(torch is None, 'Use the pinned training environment for optimizer checkpoint checks')
class UnlikelihoodResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def model(self):
        model = torch.nn.Module()
        model.projection = torch.nn.Module()
        model.projection.lora_A = torch.nn.Parameter(torch.arange(6, dtype=torch.float32).reshape(2, 3) / 10)
        model.projection.lora_B = torch.nn.Parameter(torch.ones(2, 2) / 10)
        return model

    def test_resume_binds_schema_event_positive_tokenizer_mapping_eta_and_source(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            source = b'# synthetic unlikelihood checkpoint fixture\n'
            (output / 'training-source.py').write_bytes(source)
            config = {'base_model_sha256': pipeline.SOURCE_WEIGHT_SHA, 'rank': 2, 'alpha': 4,
                'target_modules': ['projection'], 'seed': 1, 'train_sha256': '0' * 64, 'train_rows': 2,
                'epochs': 1, 'batch_size': 1, 'gradient_accumulation': 1, 'learning_rate': .01,
                'max_tokens': 16, 'threads': 1, 'warmup_steps': 0, 'effective_warmup_steps': 0,
                'schedule_total_optimizer_steps': 2, 'training_source_sha256': hashlib.sha256(source).hexdigest(),
                'unlikelihood_schema': pipeline.UNLIKELIHOOD_SCHEMA, 'unlikelihood_events_sha256': 'a' * 64,
                'unlikelihood_positive_sha256': 'b' * 64, 'unlikelihood_tokenizer_sha256': 'c' * 64,
                'unlikelihood_mapping_sha256': 'd' * 64, 'unlikelihood_eta': .3, 'unlikelihood_source_sha256': 'e' * 64}
            model = self.model()
            optimizer = torch.optim.AdamW(model.parameters(), lr=.01)
            sum(parameter.square().sum() for parameter in model.parameters()).backward()
            optimizer.step(); optimizer.zero_grad(set_to_none=True)
            checkpoint = pipeline.save_resume_checkpoint(model, optimizer, torch, output, config,
                {'step': 1, 'microbatch': 1, 'epoch': 1, 'assistant_tokens': 2, 'seconds': .1, 'lr': .01})
            for key in [key for key in config if key.startswith('unlikelihood_')]:
                changed = {**config, key: .4 if key == 'unlikelihood_eta' else 'different'}
                fresh = self.model()
                fresh_optimizer = torch.optim.AdamW(fresh.parameters(), lr=.4)
                before = {name: value.clone() for name, value in pipeline.adapter_state(fresh).items()}
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'configuration mismatch'):
                    pipeline.load_resume_checkpoint(fresh, fresh_optimizer, torch, checkpoint, changed)
                self.assertFalse(fresh_optimizer.state)
                self.assertTrue(all(torch.equal(value, pipeline.adapter_state(fresh)[name]) for name, value in before.items()))
            fresh = self.model(); fresh_optimizer = torch.optim.AdamW(fresh.parameters(), lr=.4)
            state = pipeline.load_resume_checkpoint(fresh, fresh_optimizer, torch, checkpoint, config)
            self.assertEqual(1, state['global_step'])
            self.assertEqual(.01, fresh_optimizer.param_groups[0]['lr'])
            self.assertTrue(all(torch.equal(value, pipeline.adapter_state(fresh)[name])
                for name, value in pipeline.adapter_state(model).items()))



@unittest.skipIf(torch is None, 'Use the pinned training environment for the two-step tiny CLI check')
class TinyTrainerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_eta_zero_full_cli_mapping_keeps_order_adapters_and_optimizer_exact(self):
        if legacy is None:
            self.skipTest('Full CLI identity needs the preserved legacy baseline; helper/math checks remain independent')
        from transformers import Lfm2Config, Lfm2ForCausalLM
        from safetensors.torch import load_file, save_file
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            positive, events, _, _, tokenizer = SyntheticEventArtifactTests().fixture(root)
            base = root / 'base'
            base.mkdir()
            (base / 'tokenizer.json').write_text('{"synthetic_unit_test_only":true}')
            torch.manual_seed(991)
            config = Lfm2Config(vocab_size=16, hidden_size=16, intermediate_size=32,
                num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=1,
                layer_types=['full_attention'], block_auto_adjust_ff_dim=False,
                eos_token_id=7, max_position_embeddings=64)
            config._attn_implementation = 'eager'
            template = Lfm2ForCausalLM(config).float()

            def fake_base(_path, _threads):
                return torch, load_file, save_file, tokenizer, copy.deepcopy(template)

            common = ['train', '--base', str(base), '--train', str(positive), '--threads', '1', '--seed', '321',
                      '--rank', '2', '--alpha', '4', '--learning-rate', '.01', '--epochs', '1', '--batch-size', '1',
                      '--gradient-accumulation', '1', '--max-tokens', '64', '--warmup-steps', '0',
                      '--max-steps', '2', '--checkpoint-every', '1']
            for module, name, extra in ((legacy, 'legacy', []),
                                       (pipeline, 'eta-zero', ['--unlikelihood-events', str(events), '--unlikelihood-eta', '0'])):
                with self.subTest(route=name), patch.object(module, 'base_model', side_effect=fake_base), redirect_stdout(io.StringIO()):
                    module.main(common + ['--output', str(root / name)] + extra)
            reference = load_file(str(root / 'legacy/adapter.safetensors'))
            actual = load_file(str(root / 'eta-zero/adapter.safetensors'))
            self.assertEqual(reference.keys(), actual.keys())
            self.assertTrue(all(torch.equal(value, actual[name]) for name, value in reference.items()))
            left = torch.load(root / 'legacy/checkpoints/step-000002/optimizer.pt', weights_only=True)
            right = torch.load(root / 'eta-zero/checkpoints/step-000002/optimizer.pt', weights_only=True)
            self.assertEqual(left['param_groups'], right['param_groups'])
            self.assertEqual(left['state'].keys(), right['state'].keys())
            for parameter, state in left['state'].items():
                for key, value in state.items():
                    other = right['state'][parameter][key]
                    self.assertTrue(torch.equal(value, other) if isinstance(value, torch.Tensor) else value == other)
            logs = [[json.loads(line) for line in (root / name / 'training-log.jsonl').read_text().splitlines()]
                    for name in ('legacy', 'eta-zero')]
            self.assertEqual([entry['loss'] for entry in logs[0]], [entry['loss'] for entry in logs[1]])
            self.assertEqual([entry['assistant_tokens'] for entry in logs[0]], [entry['assistant_tokens'] for entry in logs[1]])
            provenance = json.loads((root / 'eta-zero/unlikelihood-provenance.json').read_text())
            self.assertEqual(0, provenance['positive_rows_added'])
            self.assertEqual(2, provenance['positive_exposures_with_events'])



if __name__ == '__main__':
    unittest.main()
