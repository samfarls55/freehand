#!/usr/bin/env python3
"""Run the unchanged frozen controller after excluding dead /proc native entries."""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('frozen_v6_controller', HERE / 'controller.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def blocks_native_slot(name, state):
    return name in ('llama-server', 'llama-bench', 'llama-cli') and state not in ('Z', 'X')


def assert_idle_live():
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            name = (path / 'comm').read_text().strip()
            state = next(line.split()[1] for line in (path / 'status').read_text().splitlines() if line.startswith('State:'))
            if blocks_native_slot(name, state):
                raise ValueError('Another live native workload is still running; retain priority')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass


if __name__ == '__main__':
    import sys
    if sys.argv[1:] != ['run', '--cpu-release-confirmed', '--semantic-priority-cleared']:
        raise ValueError('This correction entrypoint only accepts the explicitly released frozen run')
    frozen = controller.read(HERE / 'frozen.json')
    if any(Path(frozen[key]).exists() for key in ('report', 'log')):
        raise ValueError('Preserve all prior actual trials; this wrapper never repeats a cohort')
    controller.write(HERE / 'preflight-correction-receipt.json', {
        'schema_version': 1, 'created_utc': controller.now(), 'entrypoint': controller.pin(__file__),
        'original_controller': controller.pin(HERE / 'controller.py'), 'frozen': controller.pin(HERE / 'frozen.json'),
        'change': 'Only ignore dead Z/X process records in the preflight guard; live native workers still block.',
        'initial_preflight_failed_before_child_spawn': True, 'initial_excluded_dead_pids': [44005, 75049],
        'build_controller_frozen_profile_and_timed_evaluator_unchanged': True})
    controller.assert_idle = assert_idle_live
    controller.main()
