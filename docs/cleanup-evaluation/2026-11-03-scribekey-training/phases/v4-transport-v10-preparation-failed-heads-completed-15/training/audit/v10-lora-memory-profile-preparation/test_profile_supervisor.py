"""Tiny fake-monitor tests; no child, real /proc/cgroup read, or core-limit edit."""
import contextlib
import io
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import profile_supervisor as supervisor


class FakeProcess:
    pid = 424242

    def __init__(self):
        self.returncode = None
        self.wait_outcomes = []
        self.wait_calls = []
        self.terminate = Mock()
        self.kill = Mock()

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.wait_calls.append(timeout)
        if self.wait_outcomes:
            value = self.wait_outcomes.pop(0)
            if isinstance(value, BaseException):
                raise value
            self.returncode = value
        elif self.returncode is None:
            self.returncode = -signal.SIGTERM
        return self.returncode


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(patch.stopall)
        self.root = Path(self.temp.name)
        self.output = self.root / 'output'
        self.output.mkdir()
        self.cgroup = self.root / 'fake-cgroup'
        self.cgroup.mkdir()
        (self.cgroup / 'memory.current').write_text('100000\n')
        (self.cgroup / 'memory.peak').write_text('900000\n')
        self.set_events(oom=2, killed=1)
        self.process = FakeProcess()
        self.now = 0.
        self.sleeps = []
        self.after_sleep = lambda: setattr(self.process, 'returncode', 0)
        self.after_launch = lambda: None
        self.status = ('Name:\tfake-worker\nPid:\t424242\n'
                       'VmRSS:\t20 kB\nVmHWM:\t30 kB\nVmSize:\t50 kB\n')
        self.proc_reads = []
        self.events = io.StringIO()
        self.launch = patch.object(supervisor.subprocess, 'Popen', side_effect=self.fake_launch).start()
        self.pgid = patch.object(supervisor.os, 'getpgid', return_value=self.process.pid).start()
        patch.object(supervisor.os, 'getsid', return_value=self.process.pid).start()
        self.signals = patch.object(supervisor.os, 'killpg', side_effect=self.fake_signal).start()
        self.core_limit = patch.object(supervisor.resource, 'setrlimit').start()
        patch.object(supervisor.time, 'monotonic', side_effect=lambda: self.now).start()
        patch.object(supervisor.time, 'sleep', side_effect=self.fake_sleep).start()
        original = supervisor._read_text
        def fake_read(path):
            path = Path(path)
            if str(path).startswith('/proc/'):
                self.assertEqual(Path('/proc/424242/status'), path)
                self.proc_reads.append(path)
                return self.status
            self.assertTrue(path.is_relative_to(self.cgroup))
            return original(path)
        patch.object(supervisor, '_read_text', side_effect=fake_read).start()

    def set_events(self, oom, killed):
        (self.cgroup / 'memory.events').write_text(
            f'low 0\nhigh 0\nmax 4\noom {oom}\noom_kill {killed}\n')

    def fake_launch(self, *args, **kwargs):
        self.after_launch()
        return self.process

    def fake_sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds
        self.after_sleep()

    @staticmethod
    def fake_signal(pid, sig):
        if sig == 0:
            raise ProcessLookupError

    def run_guard(self, **overrides):
        args = {'cwd': self.root, 'env': {'SYNTHETIC': 'only'}, 'max_seconds': 1.,
            'memory_cap_bytes': 500000, 'poll_seconds': .05, 'cgroup_dir': self.cgroup}
        args.update(overrides)
        with contextlib.redirect_stdout(self.events):
            return supervisor.supervise(['synthetic-never-executed'], self.output, **args)

    def assert_release(self, report, expected=True):
        release = json.loads((self.output / 'cpu-release.json').read_text())
        stored = json.loads((self.output / 'supervisor.json').read_text())
        self.assertEqual(report, stored)
        self.assertEqual(expected, report['cpu_release'])
        self.assertEqual(expected, release['released'])
        self.assertTrue(report['sampled_memory_guard_only'])
        self.assertFalse(report['oom_avoidance_guaranteed'])

    def test_normal_profile_streams_owned_rss_and_labels_historical_cgroup_peak(self):
        before = {path.name: path.read_bytes() for path in self.cgroup.iterdir()}
        report = self.run_guard()
        self.assertEqual('completed', report['reason'])
        self.assertTrue(report['measurement_complete'])
        self.assertEqual(1, report['sample_count'])
        self.assertEqual(900000, report['observed_peaks']['cgroup_peak_bytes'])
        self.assertEqual(20 * 1024, report['observed_peaks']['owned_rss_bytes'])
        rows = [json.loads(line) for line in (self.output / 'samples.jsonl').read_text().splitlines()]
        self.assertEqual(report['sample_count'], len(rows))
        self.assertEqual(0, rows[0]['memory_event_delta']['oom'])
        self.assertEqual(0, rows[0]['memory_event_delta']['oom_kill'])
        self.assertEqual(424242, rows[0]['owned_process']['pid'])
        self.assertEqual(1, len(self.proc_reads))
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.cgroup.iterdir()})
        self.assert_release(report)

    def test_pid_event_precedes_ownership_checks_and_owned_file_is_pinned_to_child(self):
        def getpgid(pid):
            self.assertIn('PROFILE_CHILD_STARTED', self.events.getvalue())
            return pid
        self.pgid.side_effect = getpgid
        report = self.run_guard()
        owned = json.loads((self.output / 'owned-process.json').read_text())
        self.assertEqual((424242, 424242, 424242),
            (owned['owned_pid'], owned['owned_process_group'], owned['owned_session']))
        self.assertTrue(owned['ownership_confirmed'])
        self.assertTrue(self.launch.call_args.kwargs['start_new_session'])
        self.assertEqual(subprocess.DEVNULL, self.launch.call_args.kwargs['stdin'])
        self.assertEqual({'SYNTHETIC': 'only'}, self.launch.call_args.kwargs['env'])
        self.assertEqual(supervisor._disable_core_dumps, self.launch.call_args.kwargs['preexec_fn'])
        self.core_limit.assert_not_called()
        self.assert_release(report)

    def test_core_dumps_are_disabled_only_by_the_child_preexec_function(self):
        supervisor._disable_core_dumps()
        self.core_limit.assert_called_once_with(supervisor.resource.RLIMIT_CORE, (0, 0))
        self.launch.assert_not_called()

    def test_memory_cap_at_preflight_refuses_to_launch(self):
        (self.cgroup / 'memory.current').write_text('500000\n')
        report = self.run_guard()
        self.assertEqual('memory_cap_before_launch', report['reason'])
        self.assertEqual(500000, report['observed_peaks']['cgroup_current_bytes'])
        self.assertFalse(report['measurement_complete'])
        self.launch.assert_not_called()
        self.assert_release(report)

    def test_sampled_cap_stops_only_owned_group_and_retains_trigger_sample(self):
        self.after_launch = lambda: (self.cgroup / 'memory.current').write_text('750000\n')
        report = self.run_guard()
        self.assertEqual('memory_cap', report['reason'])
        self.assertFalse(report['measurement_complete'])
        self.assertEqual(1, report['sample_count'])
        self.assertIn((424242, signal.SIGTERM), [call.args for call in self.signals.call_args_list])
        self.assertEqual([1.], self.process.wait_calls)
        self.assert_release(report)

    def test_deadline_stops_live_child_without_a_profile_claim(self):
        self.after_sleep = lambda: None
        report = self.run_guard(max_seconds=.1)
        self.assertEqual('deadline', report['reason'])
        self.assertFalse(report['measurement_complete'])
        self.assertTrue(all(0 <= value <= .05 for value in self.sleeps))
        self.assert_release(report)

    def test_missing_cgroup_monitor_before_launch_fails_closed(self):
        (self.cgroup / 'memory.peak').unlink()
        report = self.run_guard()
        self.assertEqual('missing_monitor', report['reason'])
        self.assertFalse(report['measurement_complete'])
        self.launch.assert_not_called()
        self.assert_release(report)

    def test_missing_cgroup_monitor_after_launch_stops_child(self):
        self.after_launch = lambda: (self.cgroup / 'memory.events').unlink()
        report = self.run_guard()
        self.assertEqual('missing_monitor', report['reason'])
        self.assertIn((424242, signal.SIGTERM), [call.args for call in self.signals.call_args_list])
        self.assert_release(report)

    def test_missing_owned_status_never_causes_other_proc_reads(self):
        self.status = 'Name:\tfake\nPid:\t424242\n'
        report = self.run_guard()
        self.assertEqual('missing_monitor', report['reason'])
        self.assertEqual([Path('/proc/424242/status')], self.proc_reads)
        self.assert_release(report)

    def test_new_oom_event_and_counter_reset_stop_without_success_claim(self):
        self.after_launch = lambda: self.set_events(oom=3, killed=1)
        report = self.run_guard()
        self.assertEqual('cgroup_oom_event', report['reason'])
        self.assertFalse(report['measurement_complete'])
        self.assertEqual(1, report['final_memory_event_delta']['oom'])
        self.assert_release(report)

    def test_decreased_event_counter_is_monitor_failure(self):
        self.after_launch = lambda: self.set_events(oom=0, killed=0)
        report = self.run_guard()
        self.assertEqual('missing_monitor', report['reason'])
        self.assertFalse(report['measurement_complete'])
        self.assert_release(report)

    def test_final_oom_observation_cannot_report_a_completed_profile(self):
        def finish_with_oom():
            self.process.returncode = 0
            self.set_events(oom=3, killed=2)
        self.after_sleep = finish_with_oom
        report = self.run_guard()
        self.assertEqual(0, report['returncode'])
        self.assertEqual('cgroup_oom_event', report['reason'])
        self.assertFalse(report['measurement_complete'])
        self.assert_release(report)

    def test_final_cap_observation_cannot_report_a_completed_profile(self):
        def finish_at_cap():
            self.process.returncode = 0
            (self.cgroup / 'memory.current').write_text('500000\n')
        self.after_sleep = finish_at_cap
        report = self.run_guard()
        self.assertEqual('memory_cap_after_exit', report['reason'])
        self.assertFalse(report['measurement_complete'])
        self.assert_release(report)

    def test_term_timeout_escalates_to_owned_group_kill_and_wait(self):
        self.after_launch = lambda: (self.cgroup / 'memory.current').write_text('750000\n')
        self.process.wait_outcomes = [subprocess.TimeoutExpired('synthetic', 1), -9]
        report = self.run_guard()
        signals = [call.args for call in self.signals.call_args_list if call.args[1] != 0]
        self.assertEqual([(424242, signal.SIGTERM), (424242, signal.SIGKILL)], signals)
        self.assertEqual([1., 1.], self.process.wait_calls)
        self.assertEqual(-9, report['returncode'])
        self.assert_release(report)

    def test_exit_signal_race_still_reaps_owned_child(self):
        self.after_launch = lambda: (self.cgroup / 'memory.current').write_text('750000\n')
        self.pgid.side_effect = [424242, ProcessLookupError()]
        report = self.run_guard()
        self.assertEqual([1.], self.process.wait_calls)
        self.assert_release(report)

    def test_foreign_group_is_not_signaled_or_falsely_released(self):
        self.pgid.return_value = 999
        report = self.run_guard()
        self.assertEqual('ownership_error', report['reason'])
        self.process.terminate.assert_called_once_with()
        self.signals.assert_not_called()
        self.assertTrue(report['owned_process_reaped'])
        self.assert_release(report, expected=False)

    def test_surviving_group_blocks_cpu_release_after_bounded_cleanup(self):
        self.signals.side_effect = None
        report = self.run_guard()
        self.assertFalse(report['measurement_complete'])
        self.assertIn((424242, signal.SIGKILL), [call.args for call in self.signals.call_args_list])
        self.assertLessEqual(report['elapsed_seconds_including_cleanup'], 1.1)
        self.assert_release(report, expected=False)

    def test_launch_error_and_interruption_produce_explicit_nonclaim(self):
        self.launch.side_effect = OSError('synthetic spawn failure')
        report = self.run_guard()
        self.assertEqual('launch_error', report['reason'])
        self.assertIsNone(report['owned_pid'])
        self.assertFalse(report['measurement_complete'])
        self.assert_release(report)

    def test_interruption_stops_and_reaps_before_release(self):
        def interrupted():
            raise KeyboardInterrupt
        self.after_sleep = interrupted
        report = self.run_guard()
        self.assertEqual('interrupted', report['reason'])
        self.assertEqual('KeyboardInterrupt', report['error']['type'])
        self.assertFalse(report['measurement_complete'])
        self.assert_release(report)

    def test_existing_output_and_invalid_bounds_are_rejected_before_spawn(self):
        for options in ({'max_seconds': float('inf')}, {'max_seconds': True},
                        {'poll_seconds': 0}, {'poll_seconds': 2}, {'memory_cap_bytes': True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.run_guard(**options)
        existing = self.output / 'owned-process.json'
        existing.write_text('keep-existing')
        with self.assertRaisesRegex(ValueError, 'Preserve'):
            self.run_guard()
        self.assertEqual('keep-existing', existing.read_text())
        self.launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
