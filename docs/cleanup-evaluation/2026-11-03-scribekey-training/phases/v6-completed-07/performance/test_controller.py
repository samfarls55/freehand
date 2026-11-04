"""Small report/environment fixtures only: no real artifacts, models or subprocesses."""
import copy
import importlib.util
import os
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('v6_performance_controller', Path(__file__).with_name('controller.py'))
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


class ReportAssessmentTests(unittest.TestCase):
    def report(self):
        text = 'Ask what you can do for your country.'
        memory = {'PeakSummedWorkingSetBytes': 690000000,
            'PeakHostWorkingSetBytes': 220000000, 'PeakSpeechWorkingSetBytes': 260000000,
            'PeakCleanupWorkingSetBytes': 250000000,
            'AtSummedWorkingSetPeak': {'HostWorkingSetBytes': 200000000,
                'SpeechWorkingSetBytes': 240000000, 'CleanupWorkingSetBytes': 250000000}}
        trial = {'Id': 'public-jfk-10s', 'Gain': 1, 'AudioSeconds': 10,
            'TranscriptMilliseconds': 700, 'CountingInjectorCompleteMilliseconds': 701, 'CleanupMilliseconds': 250,
            'CleanupOutcome': 'Unchanged', 'ProviderFailureCode': None, 'DeliveryCalls': 1,
            'RawText': text, 'NormalizedOriginalText': text, 'ProviderInput': text, 'ProviderOutput': text,
            'FinalText': text, 'Memory': memory}
        return {'Trials': [{**copy.deepcopy(trial), 'Repeat': repeat} for repeat in range(10)],
                'Failures': [], 'Memory': copy.deepcopy(memory)}

    def test_complete_replay_uses_simultaneous_sum_and_never_certifies_quality_or_windows(self):
        result = controller.assess_report(self.report())
        self.assertTrue(result['linux_partial_resource_passed'])
        self.assertEqual(690000000, result['simultaneous_peak']['PeakSummedWorkingSetBytes'])
        self.assertEqual('CountingInjectorCompleteMilliseconds', result['latency_gate_field'])
        self.assertTrue(result['semantic_quality_unknown'])
        self.assertFalse(result['whole_app_or_windows_qualified'])

    def test_first_trial_complete_delivery_latency_is_retained_and_gates(self):
        report = self.report()
        report['Trials'][0]['CountingInjectorCompleteMilliseconds'] = 806
        result = controller.assess_report(report)
        self.assertTrue(result['structural_complete_delivery_passed'])
        self.assertEqual(806, result['metrics']['CountingInjectorCompleteMilliseconds']['p95'])
        self.assertFalse(result['latency_passed'])
        self.assertFalse(result['linux_partial_resource_passed'])

    def test_fast_transcript_ready_cannot_hide_slow_complete_delivery(self):
        report = self.report()
        report['Trials'][5]['CountingInjectorCompleteMilliseconds'] = 900
        result = controller.assess_report(report)
        self.assertEqual(700, result['metrics']['TranscriptMilliseconds']['max'])
        self.assertFalse(result['linux_partial_resource_passed'])

    def test_fallback_split_delivery_missing_repetition_or_shortening_never_qualifies(self):
        for kind in ('fallback', 'split', 'missing', 'short', 'empty', 'failure'):
            report = self.report()
            if kind == 'fallback': report['Trials'][0]['CleanupOutcome'] = 'Rejected'
            if kind == 'split': report['Trials'][0]['DeliveryCalls'] = 2
            if kind == 'missing': report['Trials'].pop(0)
            if kind == 'short':
                report['Trials'][0]['ProviderOutput'] = report['Trials'][0]['FinalText'] = 'Ask what you can do.'
            if kind == 'empty': report['Trials'][0]['ProviderOutput'] = ''
            if kind == 'failure': report['Trials'][0]['ProviderFailureCode'] = 'IncompleteNativeResponse'
            with self.subTest(kind=kind):
                result = controller.assess_report(report)
                self.assertFalse(result['structural_complete_delivery_passed'])
                self.assertFalse(result['linux_partial_resource_passed'])

    def test_incoherent_or_missing_component_at_simultaneous_peak_is_rejected(self):
        for kind in ('bad_sum', 'zero_cleanup'):
            report = self.report()
            if kind == 'bad_sum': report['Trials'][0]['Memory']['PeakSummedWorkingSetBytes'] += 1
            else: report['Trials'][0]['Memory']['AtSummedWorkingSetPeak']['CleanupWorkingSetBytes'] = 0
            with self.subTest(kind=kind):
                self.assertFalse(controller.assess_report(report)['linux_partial_resource_passed'])

    def test_cancel_during_initial_wait_preserves_receipt_with_empty_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            frozen = {'command': ['never-executed'], 'report': str(out / 'report.json'), 'log': str(out / 'child.log')}
            plan = {'environment_overrides': {}}
            (out / 'frozen.json').write_text(json.dumps(frozen))
            (out / 'plan.json').write_text(json.dumps(plan))
            child = SimpleNamespace(pid=1234, poll=lambda: None, wait=lambda **kwargs: -15)
            args = SimpleNamespace(cpu_release_confirmed=True, semantic_priority_cleared=True)
            with patch.object(controller, 'OUT', out), patch.object(controller, 'assert_idle'), \
                    patch.object(controller, 'verify_frozen'), patch.object(controller, 'clean_environment', return_value=({}, [])), \
                    patch.object(controller.subprocess, 'Popen', return_value=child), \
                    patch.object(controller.time, 'sleep', side_effect=KeyboardInterrupt), \
                    patch.object(controller.os, 'killpg') as kill, patch.object(controller, 'analyze'):
                with self.assertRaisesRegex(ValueError, 'N10 child failed'):
                    controller.run(args)
            receipt = json.loads((out / 'run-receipt.json').read_text())
            self.assertEqual([], receipt['observed_environment'])
            self.assertEqual(-2, receipt['return_code'])
            self.assertTrue(receipt['artifacts_before_after_verified'])
            kill.assert_called_once_with(1234, controller.signal.SIGTERM)

    def test_expensive_phases_reject_without_release_before_reading_or_hashing_artifacts(self):
        args = SimpleNamespace(cpu_release_confirmed=False, semantic_priority_cleared=False)
        with patch.object(controller, 'read', side_effect=AssertionError('No artifact reads before release')) as read:
            for phase in (controller.build, controller.freeze, controller.run):
                with self.subTest(phase=phase.__name__), self.assertRaises(ValueError):
                    phase(args)
            read.assert_not_called()

    def test_scoped_environment_clears_inherited_tiering_and_native_model_overrides(self):
        environment = {'DOTNET_TieredCompilation': '0', 'COMPlus_TieredPGO': '1',
                       'LLAMA_ARG_MODEL': 'wrong', 'DOTNET_TieredPGO': '1', 'UNRELATED': 'preserve'}
        plan = {'environment_removals': ['DOTNET_TieredCompilation', 'COMPlus_TieredPGO'],
                'environment_overrides': {'DOTNET_TieredPGO': '0', 'LLAMA_ARG_DEVICE': 'none'}}
        with patch.dict(os.environ, environment, clear=True):
            actual, removed = controller.clean_environment(plan)
        self.assertEqual('0', actual['DOTNET_TieredPGO'])
        self.assertEqual('none', actual['LLAMA_ARG_DEVICE'])
        self.assertEqual('preserve', actual['UNRELATED'])
        self.assertFalse(any(key in actual for key in ('DOTNET_TieredCompilation', 'COMPlus_TieredPGO', 'LLAMA_ARG_MODEL')))
        self.assertIn('LLAMA_ARG_MODEL', removed)


if __name__ == '__main__':
    unittest.main()
