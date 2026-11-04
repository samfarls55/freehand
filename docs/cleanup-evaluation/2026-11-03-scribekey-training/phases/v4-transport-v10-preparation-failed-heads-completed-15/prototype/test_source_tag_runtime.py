"""Tiny stdlib/mock runtime tests; never start a worker or import real Torch."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import source_tag_runtime as runtime


class RuntimeFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_import_is_torch_free_and_original_interpreter_spelling_is_fixed(self):
        self.assertNotIn('torch', sys.modules)
        self.assertEqual('/workspace/freehand/work/cleanup-small-models-2026-11-03/'
            'scribe-precision-source/conversion-env/bin/python', runtime.ORIGINAL_PYTHON)

    def test_sha_canonical_digest_and_create_only_json(self):
        path = self.root / 'tiny.json'
        runtime.write_json(path, {'b': 2, 'a': 'Ada'})
        before = path.read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(), runtime.sha(path))
        self.assertEqual(runtime.canonical_sha({'a': 1, 'b': 2}), runtime.canonical_sha({'b': 2, 'a': 1}))
        with self.assertRaises(FileExistsError):
            runtime.write_json(path, {'replacement': True})
        self.assertEqual(before, path.read_bytes())
        invalid = self.root / 'invalid.json'
        with self.assertRaises(ValueError):
            runtime.write_json(invalid, {'value': float('nan')})
        self.assertFalse(invalid.exists())

    def test_required_pins_cover_exact_runtime_sources_and_explicit_extra(self):
        expected = {'source_tag_contract.py', 'source_tag_model.py', 'source_tag_train.py',
            'source_tag_unit.py', 'source_tag_runtime.py', 'editor_core/__init__.py', 'editor_core/core.py',
            'editor_core/head_contract.py'}
        self.assertEqual(expected, set(runtime.CORE_PINS))
        for name in expected | {'extra.py'}:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name)
        with patch.object(runtime, 'ROOT', self.root):
            pins = runtime.required_pins(('extra.py',))
            self.assertEqual(expected | {'extra.py'}, set(pins))
            self.assertTrue(all(pins[name] == runtime.sha(self.root / name) for name in pins))
            for name in ('../foreign.py', '/foreign.py', 'a//b.py', 'a\\b.py'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    runtime.required_pins((name,))

    def test_grant_requires_typed_approval_exact_operation_and_all_requested_pins(self):
        path = self.root / 'grant.json'
        pins = {'source.py': 'a' * 64}
        grant = {'operation': 'source-tag-synthetic', 'cpu_granted': True,
                 'max_wall_seconds': 20, 'pins': pins}
        path.write_text(json.dumps(grant))
        self.assertEqual(grant, runtime.validate_grant(path, grant['operation'], pins, 20))
        mutations = [{'cpu_granted': 1}, {'cpu_granted': False}, {'operation': 'another'},
            {'pins': {}}, {'pins': {'source.py': 'b' * 64}}, {'pins': []}]
        for changes in mutations:
            path.write_text(json.dumps({**grant, **changes}))
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                runtime.validate_grant(path, grant['operation'], pins, 20)

    def test_grant_rejects_nonfinite_bool_zero_and_excessive_time_bounds(self):
        path = self.root / 'grant.json'
        pins = {'source.py': 'a' * 64}
        grant = {'operation': 'synthetic', 'cpu_granted': True, 'max_wall_seconds': 20, 'pins': pins}
        for value in (True, False, 0, -1, float('nan'), float('inf'), '20', 21):
            path.write_text(json.dumps(grant))
            with self.subTest(seconds=repr(value)), self.assertRaises(ValueError):
                runtime.validate_grant(path, 'synthetic', pins, value)
        for value in (True, 0, float('nan'), float('inf'), '20'):
            path.write_text(json.dumps({**grant, 'max_wall_seconds': value}))
            with self.subTest(maximum=repr(value)), self.assertRaises(ValueError):
                runtime.validate_grant(path, 'synthetic', pins, 1)

    def test_optional_settings_and_output_are_exactly_pinned(self):
        path = self.root / 'grant.json'
        pins = {'source.py': 'a' * 64}
        settings = {'steps': 2, 'seed': 3}
        output = self.root / 'owned-output'
        grant = {'operation': 'synthetic', 'cpu_granted': True, 'max_wall_seconds': 20, 'pins': pins,
            'settings_sha256': runtime.canonical_sha(settings), 'output_dir': str(output.absolute())}
        path.write_text(json.dumps(grant))
        runtime.validate_grant(path, 'synthetic', pins, 20, settings=settings, output_dir=output)
        with self.assertRaisesRegex(ValueError, 'settings'):
            runtime.validate_grant(path, 'synthetic', pins, 20, settings={'steps': 3})
        with self.assertRaisesRegex(ValueError, 'output'):
            runtime.validate_grant(path, 'synthetic', pins, 20, output_dir=self.root / 'another')

    def test_configure_torch_uses_only_explicit_mock_on_call(self):
        fake = Mock()
        with patch.dict(sys.modules, {'torch': fake}):
            self.assertIs(fake, runtime.configure_torch(seed=17))
        fake.set_num_threads.assert_called_once_with(2)
        fake.set_num_interop_threads.assert_called_once_with(1)
        fake.manual_seed.assert_called_once_with(17)
        fake.use_deterministic_algorithms.assert_called_once_with(True)
        self.assertNotIn('torch', sys.modules)


class FakeProcess:
    pid = 424242

    def __init__(self, outcomes=(0,)):
        self.returncode = None
        self.outcomes = list(outcomes)
        self.wait_calls = []
        self.terminate = Mock()
        self.kill = Mock()

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.wait_calls.append(timeout)
        result = self.outcomes.pop(0) if self.outcomes else self.returncode
        if isinstance(result, BaseException):
            raise result
        self.returncode = result
        return result


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(patch.stopall)
        self.process = FakeProcess()
        self.launch = patch.object(runtime.subprocess, 'Popen', return_value=self.process).start()
        self.pgid = patch.object(runtime.os, 'getpgid', return_value=self.process.pid).start()
        patch.object(runtime.os, 'getsid', return_value=self.process.pid).start()
        self.signals = patch.object(runtime.os, 'killpg', side_effect=self.signal_group).start()
        patch.object(runtime.time, 'monotonic', return_value=0).start()
        self.stdout = io.StringIO()

    @staticmethod
    def signal_group(pid, sig):
        if sig == 0:
            raise ProcessLookupError

    def run_worker(self):
        with contextlib.redirect_stdout(self.stdout):
            return runtime.supervise(['synthetic-worker-never-executed'], self.root, 10)

    def report(self):
        report = json.loads((self.root / 'supervisor.json').read_text())
        release = json.loads((self.root / 'cpu-release.json').read_text())
        self.assertEqual(report['cpu_release'], release['cpu_release'])
        return report

    def test_success_emits_pid_before_ownership_then_records_reap_and_release(self):
        def pgid(pid):
            self.assertIn('owned_worker_started', self.stdout.getvalue())
            return pid
        self.pgid.side_effect = pgid
        self.assertEqual(0, self.run_worker())
        self.assertTrue(self.launch.call_args.kwargs['start_new_session'])
        self.assertEqual(subprocess.DEVNULL, self.launch.call_args.kwargs['stdin'])
        environment = self.launch.call_args.kwargs['env']
        for name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS'):
            self.assertEqual('2', environment[name])
        report = self.report()
        self.assertTrue(report['ownership_confirmed'])
        self.assertTrue(report['owned_process_reaped'])
        self.assertTrue(report['owned_group_released'])
        self.assertTrue(report['cpu_release'])
        self.assertEqual(self.process.pid, report['owned_process_group'])
        self.assertEqual(self.process.pid, report['owned_session'])

    def test_timeout_terms_owned_group_and_waits(self):
        self.process.outcomes = [subprocess.TimeoutExpired('synthetic', 10), 0]
        self.assertEqual(124, self.run_worker())
        self.assertIn((self.process.pid, signal.SIGTERM), [call.args for call in self.signals.call_args_list])
        self.assertEqual([10, 1], self.process.wait_calls)
        self.assertTrue(self.report()['timed_out'])
        self.assertTrue(self.report()['cpu_release'])

    def test_timeout_escalates_to_kill_and_reaps(self):
        timeout = subprocess.TimeoutExpired('synthetic', 1)
        self.process.outcomes = [timeout, timeout, -9]
        self.assertEqual(124, self.run_worker())
        signals = [call.args for call in self.signals.call_args_list if call.args[1] != 0]
        self.assertEqual([(self.process.pid, signal.SIGTERM), (self.process.pid, signal.SIGKILL)], signals)
        self.assertEqual([10, 1, 1], self.process.wait_calls)
        self.assertTrue(self.report()['owned_process_reaped'])

    def test_interrupt_still_cleans_up_then_reraises(self):
        self.process.outcomes = [KeyboardInterrupt(), 0]
        with self.assertRaises(KeyboardInterrupt):
            self.run_worker()
        self.assertTrue(self.report()['cpu_release'])
        self.assertEqual('KeyboardInterrupt', self.report()['error']['type'])

    def test_exit_signal_race_still_waits(self):
        self.process.outcomes = [subprocess.TimeoutExpired('synthetic', 10), 0]
        self.pgid.side_effect = [self.process.pid, ProcessLookupError()]
        self.assertEqual(124, self.run_worker())
        self.assertEqual([10, 1], self.process.wait_calls)
        self.assertTrue(self.report()['cpu_release'])

    def test_child_exited_before_ownership_inspection_is_reaped_without_signaling(self):
        self.process.returncode = 0
        self.pgid.side_effect = ProcessLookupError
        self.assertEqual(0, self.run_worker())
        report = self.report()
        self.assertTrue(report['exited_before_ownership_inspection'])
        self.assertFalse(report['ownership_confirmed'])
        self.assertTrue(report['cpu_release'])
        self.assertTrue(all(call.args[1] == 0 for call in self.signals.call_args_list))

    def test_group_signal_failure_uses_owned_pid_and_still_reaps(self):
        self.process.outcomes = [subprocess.TimeoutExpired('synthetic', 10), 0]
        def failed_group(pid, sig):
            if sig == 0:
                raise ProcessLookupError
            raise PermissionError('synthetic group signal failure')
        self.signals.side_effect = failed_group
        self.assertEqual(124, self.run_worker())
        self.process.terminate.assert_called_once_with()
        self.assertEqual([10, 1], self.process.wait_calls)
        self.assertTrue(self.report()['owned_process_reaped'])

    def test_unconfirmed_group_uses_only_owned_pid_and_reports_no_release(self):
        self.pgid.return_value = 99
        with self.assertRaisesRegex(RuntimeError, 'group/session'):
            self.run_worker()
        self.process.terminate.assert_called_once_with()
        self.signals.assert_not_called()
        self.assertTrue(self.report()['owned_process_reaped'])
        self.assertFalse(self.report()['cpu_release'])

    def test_surviving_owned_group_is_killed_without_false_release(self):
        self.signals.side_effect = None
        self.assertEqual(1, self.run_worker())
        self.assertIn((self.process.pid, signal.SIGKILL), [call.args for call in self.signals.call_args_list])
        self.assertFalse(self.report()['owned_group_released'])
        self.assertFalse(self.report()['cpu_release'])

    def test_popen_failure_reports_no_child_and_reraises(self):
        self.launch.side_effect = OSError('synthetic spawn failure')
        with self.assertRaises(OSError):
            self.run_worker()
        self.assertIsNone(self.report()['owned_pid'])
        self.assertTrue(self.report()['cpu_release'])
        self.signals.assert_not_called()

    def test_existing_evidence_is_preserved_before_any_process(self):
        path = self.root / 'supervisor.json'
        path.write_text('keep-existing')
        with self.assertRaisesRegex(ValueError, 'Preserve existing'):
            self.run_worker()
        self.assertEqual('keep-existing', path.read_text())
        self.launch.assert_not_called()

    def test_nonzero_worker_code_is_propagated(self):
        self.process.outcomes = [7]
        self.assertEqual(7, self.run_worker())
        self.assertEqual(7, self.report()['returncode'])


if __name__ == '__main__':
    unittest.main()
