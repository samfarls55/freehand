"""Tiny stdlib-only guards; fake execution only, no real cohorts/models/jobs."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main, mock
import copy
import hashlib
import importlib.util
import json
import os
import tempfile

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('selected_knownsets_controller_test_subject', HERE / 'run.py')
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)
REFERENCE = C.read(HERE / 'source-reference.json')


def fixture():
    frozen = {key: copy.deepcopy(REFERENCE[key]) for key in ('model', 'runtime', 'runtime_inventory', 'probe', 'managed_assemblies', 'sources')}
    pin = {'path': '/tmp/tiny-test-only/adapter.gguf', 'bytes': 12006240, 'sha256': 'a' * 64}
    config = {'path': '/tmp/tiny-test-only/adapter-config.json', 'bytes': 5, 'sha256': 'b' * 64}
    frozen['sources'] = C.expected_source_epoch(REFERENCE)
    frozen.update(runtime_adapter=pin, adapter_config=config, cache_configuration=dict(C.CACHES),
        source_snapshot={'path': '/tmp/tiny-test-only/source.tar.gz', 'bytes': 9, 'sha256': 'c' * 64},
        profile={**REFERENCE['common_profile'], 'adapterPath': pin['path'], 'adapterSha256': pin['sha256'], 'adapterScale': 1.0})
    performance = {'adapter': pin, 'base': frozen['model'], 'external_scale': 1, 'tensor_precision': 'F32', 'tensor_count': 184,
        'training_config': config, 'training_receipt': config, 'export_receipt': config}
    conversion = {'gguf': pin, 'adapter_config': config, 'rank': 8, 'alpha': 16, 'embedded_alpha_div_rank': 2,
        'external_native_scale': 1, 'base_merge_performed': False, 'requantization_performed': False,
        'all184_custom_peft_gguf_bytes_identical': True,
        'tensors': [{'custom_key': 'module' + str(i), 'dtype': 'F32', 'gguf_value_bytes_identical': True} for i in range(184)]}
    return frozen, performance, conversion


def core_case(identity, status='Unchanged'):
    return {'id': identity, 'cleanup_status': status, 'insertion_count': 1, 'delivered_count': 1, 'delivery_outcome': 'Delivered'}


class ControllerGuards(TestCase):
    def test_candidate_fixed_epoch_and_F16_profile(self):
        frozen, performance, _ = fixture()
        C.validate_candidate(frozen, performance, REFERENCE)
        mutations = [lambda f: f['cache_configuration'].update(cacheTypeV='f32'),
            lambda f: f['profile'].update(promptLookupTokens=8), lambda f: f['profile'].update(threads=True),
            lambda f: f['profile'].update(adapterScale=True), lambda f: f['profile'].update(extra='silent override'),
            lambda f: f['managed_assemblies'][0].update(sha256='0' * 64), lambda f: f['sources'].update(unknown='0' * 64)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                bad = copy.deepcopy(frozen)
                mutate(bad)
                with self.assertRaises(ValueError): C.validate_candidate(bad, performance, REFERENCE)

    def test_performance_identity_precision_typed_count_and_unit_scale(self):
        frozen, performance, _ = fixture()
        for key, value in [('tensor_count', True), ('tensor_count', 183), ('tensor_precision', 'F16'), ('external_scale', True), ('external_scale', .5)]:
            bad = copy.deepcopy(performance); bad[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): C.validate_candidate(frozen, bad, REFERENCE)
        bad = copy.deepcopy(performance); bad['adapter']['sha256'] = 'f' * 64
        with self.assertRaises(ValueError): C.validate_candidate(frozen, bad, REFERENCE)

    def test_conversion_unmerged184_F32_unit_scaling(self):
        frozen, performance, conversion = fixture()
        C.validate_conversion(conversion, frozen, performance)
        for key, value in [('base_merge_performed', True), ('requantization_performed', True), ('external_native_scale', True), ('all184_custom_peft_gguf_bytes_identical', False)]:
            bad = copy.deepcopy(conversion); bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): C.validate_conversion(bad, frozen, performance)
        bad = copy.deepcopy(conversion); bad['tensors'][50]['dtype'] = 'F16'
        with self.assertRaises(ValueError): C.validate_conversion(bad, frozen, performance)

    def test_full_dictionary_inventory_no_subset_or_duplicate(self):
        spec = {'count': 2, 'dictionary_count': 1}
        corpus = {'cases': [{'id': 'a', 'dictionary': [{'hear': 'x', 'write': 'Y'}]}, {'id': 'b'}]}
        self.assertEqual(C.inventory(corpus, spec), ['a', 'b'])
        for rows in [corpus['cases'][:1], [corpus['cases'][0], corpus['cases'][0]], [{'id': 'a'}, {'id': 'b'}]]:
            with self.assertRaises(ValueError): C.inventory({'cases': rows}, spec)

    def test_failed_provider_case_is_retained_without_credit(self):
        report = {'incomplete': False, 'cases': [core_case('a'), core_case('b', 'Failed')]}
        value = C.validate_report(report, ['a', 'b'])
        self.assertEqual(value['case_count'], 2)
        self.assertEqual(value['provider_failures'], 1)
        self.assertFalse(value['fallback_gets_quality_credit'])

    def test_incomplete_reordered_duplicate_or_double_delivery_rejected(self):
        report = {'incomplete': False, 'cases': [core_case('a'), core_case('b')]}
        for mutate in [lambda r: r.update(incomplete=True), lambda r: r['cases'].reverse(),
            lambda r: r['cases'][1].update(id='a'), lambda r: r['cases'][0].update(insertion_count=2),
            lambda r: r['cases'][0].update(delivered_count=True)]:
            bad = copy.deepcopy(report); mutate(bad)
            with self.assertRaises(ValueError): C.validate_report(bad, ['a', 'b'])

    def test_command_retains_exit1_but_requires_real_owned_argv_cleanup(self):
        receipt = {'termination_reason': None, 'owned_process_group_cleanup_completed': True,
            'native_requested_cache_arguments_observed_and_verified': True, 'native_argument_errors': [], 'exit_code': 1}
        C.validate_command(receipt, {'core': 1})
        for key, value in [('exit_code', True), ('exit_code', 0), ('owned_process_group_cleanup_completed', False),
            ('native_requested_cache_arguments_observed_and_verified', False), ('termination_reason', 'timeout')]:
            bad = {**receipt, key: value}
            with self.assertRaises(ValueError): C.validate_command(bad, {'core': 1})

    def test_tiny_pin_drift_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'corpus.json'; p.write_text('{}')
            pin = C.artifact(p); C.verify(pin)
            p.write_text('{"changed":true}')
            with self.assertRaises(ValueError): C.verify(pin)

    def test_environment_is_scoped_and_tiering_override_removed(self):
        with mock.patch.dict(os.environ, {'DOTNET_TieredPGO': '1', 'DOTNET_TieredCompilation': '0', 'COMPlus_TieredCompilation': '0'}):
            value = C.environment()
            self.assertEqual(value['DOTNET_TieredPGO'], '0')
            self.assertNotIn('DOTNET_TieredCompilation', value)
            self.assertNotIn('COMPlus_TieredCompilation', value)
            self.assertEqual(os.environ['DOTNET_TieredPGO'], '1')

    def test_no_execute_or_existing_output_fails_before_artifact_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(execute=False, candidate='V9', freeze_sha256='a' * 64,
                performance_sha256='b' * 64, output=Path(directory))
            with mock.patch.object(C, 'artifact', side_effect=AssertionError('must not read pins')):
                with self.assertRaises(ValueError): C.run(args)
                args.execute = True
                with self.assertRaises(ValueError): C.run(args)

    def test_Z_records_do_not_block_but_live_foreign_worker_does(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); p = root / '123'; p.mkdir(); (p / 'comm').write_text('llama-server')
            (p / 'stat').write_text('123 (llama-server) Z 1 1 1')
            C.native_idle(root)
            (p / 'stat').write_text('123 (llama-server) S 1 1 1')
            with self.assertRaises(ValueError): C.native_idle(root)

    def test_fake_three_cohort_run_continues_after_complete_provider_failure(self):
        # Exercise the real outer freeze/postcheck/persistence loop. Only execution
        # and heavyweight evaluator verification are fake, with tiny fixture bytes.
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory); (task / 'evaluation').mkdir(); source = task / 'source'; source.mkdir()
            def put(name, value):
                p = source / name; C.write(p, value); return C.artifact(p)
            frozen, performance, conversion = fixture()
            performance['training_config'] = put('config.json', {'train': 'tiny'})
            frozen['adapter_config'] = performance['training_config']
            performance['training_receipt'] = put('training.json', {'steps': 4})
            conversion['adapter_config'] = performance['training_config']
            performance['export_receipt'] = put('conversion.json', conversion)
            freeze_pin = put('freeze.json', frozen); perf_pin = put('performance.json', performance)
            reference_pin = put('source-reference.json', REFERENCE)
            evaluator_pin = put('evaluate.py', {'fake': 'evaluator'})
            helper_pin = put('owned_execution.py', {'fake': 'owned'})
            manifest_pin = put('dictionary-manifest.json', {'dictionary_fixtures': 1})
            specs = []
            for label, rows in [('retired500', [{'id': 'a'}, {'id': 'b'}]), ('development546', [{'id': 'c'}]), ('hard80', [{'id': 'd'}])]:
                pin = put(label + '.json', {'cases': rows})
                specs.append({**pin, 'label': label, 'count': len(rows), 'dictionary_count': None})
            args = SimpleNamespace(execute=True, candidate='V9', candidate_freeze=Path(freeze_pin['path']),
                freeze_sha256=freeze_pin['sha256'], performance_input=Path(perf_pin['path']),
                performance_sha256=perf_pin['sha256'], output=task / 'evaluation' / 'tiny-owned-run')
            seen = []
            def fake_run(evaluate, owned, frozen, freeze_pin, spec, ids, output, env):
                seen.append((spec['label'], ids))
                return {'case_count': len(ids), 'provider_failures': 1 if len(seen) == 1 else 0,
                        'command_exit_code': 1 if len(seen) == 1 else 0}
            fake_eval = SimpleNamespace(verify_freeze=lambda p: frozen, load_corpus=C.read)
            with mock.patch.multiple(C, TASK=task, HERE=source, EVALUATOR=Path(evaluator_pin['path']),
                    EVALUATOR_SHA=evaluator_pin['sha256'], HELPER_SHA=helper_pin['sha256'], REFERENCE_SHA=reference_pin['sha256'],
                    COHORTS=tuple(specs), DICTIONARY_MANIFEST=manifest_pin), \
                 mock.patch.object(C, 'native_idle'), mock.patch.object(C, 'import_path', return_value=fake_eval), \
                 mock.patch.object(C, 'run_cohort', side_effect=fake_run):
                self.assertEqual(C.run(args), 1)
            self.assertEqual(seen, [('retired500', ['a', 'b']), ('development546', ['c']), ('hard80', ['d'])])
            result = C.read(args.output / 'completion.json')
            self.assertEqual(len(result['cohorts']), 3)
            self.assertIsNone(result['quality_gate_passed'])
            self.assertFalse(result['resource_windows_whole_app_qualified'])


if __name__ == '__main__':
    main()
