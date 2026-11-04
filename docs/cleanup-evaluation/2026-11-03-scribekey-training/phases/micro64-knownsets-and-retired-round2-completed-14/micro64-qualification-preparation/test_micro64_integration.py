"""Real evaluator freeze/paired flow, synthetic files and mocked Probe only."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main, mock
import hashlib
import importlib.util
import json
import tempfile

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('micro64_integration_subject', HERE / 'evaluate_micro64.py')
W = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(W)
E = W.configure_evaluator()


class Micro64Integration(TestCase):
    def test_only_profile_field_changes_and_all_work_sources_are_archived(self):
        before = W.original_profile()
        after = E.runtime_profile()
        self.assertEqual({key for key in before if before[key] != after[key]}, {'microBatchSize'})
        self.assertEqual((before['microBatchSize'], after['microBatchSize']), (32, 64))
        sources = E.source_files()
        for name in ('evaluate_micro64.py', 'run.py', 'owned_execution.py'):
            p = HERE / name
            self.assertEqual(sources[str(p.relative_to(E.ROOT))], hashlib.sha256(p.read_bytes()).hexdigest())
        with self.assertRaises(ValueError):
            E.runtime_profile(True)

    def test_noncore_rejected_before_any_candidate_or_corpus_access(self):
        for mode in ('native', 'both'):
            with mock.patch.object(E, 'artifact', side_effect=AssertionError('No artifact access')):
                with self.assertRaisesRegex(ValueError, 'Core only'):
                    E.native(SimpleNamespace(mode=mode))

    def test_real_new_freezes_and_paired_core_continue_after_malformed_selected(self):
        with tempfile.TemporaryDirectory(prefix='micro64-synthetic-') as directory:
            root = Path(directory)
            def put(name, raw):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
                return p
            model = put('toy-model', b'synthetic base')
            runtime = put('toy-runtime', b'no executable')
            inventory = put('toy-runtime-index.json', b'{}')
            adapter = put('toy-adapter', b'synthetic adapter')
            names = ('Freehand.Cleanup.Probe.dll', 'Freehand.Cleanup.dll', 'Freehand.Core.dll',
                     'Freehand.Dictionary.dll', 'Freehand.Abstractions.dll', 'Freehand.Testing.dll')
            for name in names:
                put('probe/' + name, ('synthetic ' + name).encode())
            provenance = root / 'toy-control-provenance.json'
            provenance.write_text(json.dumps({'role': 'original_scribekey_control',
                'source_repository': 'scribekey/scribekey-cleanup-fast',
                'source_revision': 'c484dad2d815bff83d376e46b25a11dbc820992a',
                'source_model_sha256': E.ORIGINAL_SCRIBE_BF16_SHA256,
                'source_f16': {'sha256': E.ORIGINAL_SCRIBE_F16_SHA256},
                'adapter_applied': False, 'quantization': 'IQ4_XS', 'quantized': E.artifact(model)}))
            def freeze_args(output, selected):
                return SimpleNamespace(model=model, runtime=runtime, runtime_inventory=inventory,
                    probe=root / 'probe' / names[0], output=output, adapter_config=None,
                    runtime_adapter=adapter if selected else None,
                    runtime_adapter_sha256=E.sha256_file(adapter) if selected else None,
                    runtime_adapter_scale=1, prompt_lookup_tokens=16, cache_type_k='f16', cache_type_v='f16',
                    original_control_provenance=None if selected else provenance)
            selected_path, control_path = root / 'selected.json', root / 'control.json'
            with mock.patch.object(E.small_models, 'verify_runtime_inventory', return_value={'synthetic': True}), \
                 mock.patch.object(E, 'ORIGINAL_SCRIBE_IQ4_XS_SHA256', E.sha256_file(model)), \
                 mock.patch.object(E, 'ORIGINAL_SCRIBE_IQ4_XS_BYTES', model.stat().st_size):
                E.freeze(freeze_args(selected_path, True))
                E.freeze(freeze_args(control_path, False))
                selected, control = E.verify_freeze(selected_path), E.verify_freeze(control_path)
                E.verify_pair(selected, control)
                self.assertEqual(selected['profile']['microBatchSize'], 64)
                corpus = root / 'toy-corpus.json'
                corpus.write_text(json.dumps({'schema_version': 1, 'cases': [
                    {'id': 'synthetic-' + str(i), 'input': 'Keep this.', 'targets': ['Keep this.']}
                    for i in range(500)]}))
                commitment = root / 'toy-commitment.json'
                commitment.write_text(json.dumps({'corpus_sha256': E.sha256_file(corpus), 'case_count': 500}))
                output = root / 'paired-output'
                args = SimpleNamespace(mode='core', phase='blind-final', dataset=corpus,
                    blind_commitment=commitment, candidate_freeze=selected_path,
                    paired_baseline_freeze=control_path, output=output, dotnet=root / 'no-dotnet')
                calls = []
                def fake_probe(argv, log):
                    self.assertTrue((output / 'evaluation-pre-run-freeze.json').is_file())
                    self.assertTrue((output / 'paired-baseline/evaluation-pre-run-freeze.json').is_file())
                    manifest = json.loads(Path(argv[argv.index('--manifest') + 1]).read_text())
                    self.assertEqual(manifest['microBatchSize'], 64)
                    report = Path(argv[argv.index('--output') + 1])
                    calls.append(report.parent.name)
                    log.write_text('synthetic Probe; no process launched')
                    if len(calls) == 1:
                        report.write_text('{truncated synthetic report')
                        return 1
                    rows = json.loads(Path(argv[argv.index('--input') + 1]).read_text())['cases']
                    report.write_text(json.dumps({'incomplete': False, 'metadata': {
                        'model': {'expected_sha256': manifest['modelSha256'], 'actual_sha256': manifest['modelSha256']},
                        'runtime_adapter': None, 'adapter_scale': None, 'cache_type_k': 'f16', 'cache_type_v': 'f16'},
                        'cases': [{'id': row['id']} for row in rows]}))
                    return 0
                with mock.patch.object(E, 'invoke', side_effect=fake_probe):
                    self.assertEqual(E.native(args), 1)
                    with self.assertRaisesRegex(ValueError, 'already exists'):
                        E.native(args)
                self.assertEqual(calls, ['paired-output', 'paired-baseline'])
                done = json.loads((output / 'paired-completion.json').read_text())
                self.assertFalse(done['both_complete_denominators'])
                self.assertEqual(done['candidate_reports']['original_control']['observed_count'], 500)
                self.assertTrue(done['post_run_identities_verified'])
                self.assertTrue(commitment.with_suffix('.consumed.json').exists())


if __name__ == '__main__':
    main()
