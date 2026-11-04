#!/usr/bin/env python3
"""Additive pre/post input closure and actual-process evidence for cache64.

Calls the held controller in-process. It makes no additional native requests,
imports no Torch, and records no process environment or unrelated process.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal

import native_cache as controller
import native_client as native

ROOT = Path(__file__).absolute().parent
LIBRARY_INVENTORY = ROOT / 'native-smoke-01/native-library-pins.json'
LIBRARY_INVENTORY_SHA = '8f84f760d780559ecbbcae4e3d70bb446ad0499bd661dba5d593b3c675fc5efe'


def require(test, message):
    if not test:
        raise ValueError(message)


def add_pin(pins, path, expected, role):
    path = Path(path).absolute()
    key = str(path)
    if key in pins:
        require(pins[key]['expected_sha256'] == expected, 'Conflicting closure input pin')
        pins[key]['roles'].append(role)
    else:
        pins[key] = {'expected_sha256': expected, 'roles': [role]}


def inventory(plan, plan_path, grant_path):
    """All values come from fixed pins or the root-authorized immutable plan."""
    pins = {}
    add_pin(pins, plan_path, native.sha(plan_path), 'root-authorized-pilot-plan')
    add_pin(pins, grant_path, native.sha(grant_path), 'root-native-CPU-grant')
    for name, expected in plan['sources'].items():
        path = (ROOT/name).absolute()
        require(path.is_relative_to(ROOT), 'Plan source escapes owned prototype')
        add_pin(pins, path, expected, 'plan-source')
    for path, expected, role in (
        (native.SERVER, native.SERVER_SHA, 'runtime-executable'),
        (native.BASE, native.BASE_SHA, 'read-only-original-IQ4-base'),
        (native.ADAPTER, native.ADAPTER_SHA, 'read-only-t050-F32-adapter'),
        (plan['dataset']['path'], plan['dataset']['sha256'], 'approved-training-source'),
        (plan['tokenizer']['path'], plan['tokenizer']['sha256'], 'official-tokenizer'),
        (plan['literal']['packet_path'], plan['literal']['packet_sha256'], 'held-v4-source-packet')):
        add_pin(pins, path, expected, role)
    for entry in plan['literal']['executed_sources'].values():
        add_pin(pins, entry['path'], entry['sha256'], 'actual-executed-literal-source')
    binding_path = plan_path.parent / 'managed-qualification-binding.json'
    binding = json.loads(binding_path.read_text())
    require(binding['plan']['sha256'] == native.sha(plan_path)
        and binding['checked_inputs'] == 64 and binding['all_prompts_exact'] is True,
        'Managed qualification binding does not cover exact plan64')
    add_pin(pins, binding_path, native.sha(binding_path), 'all64-qualified-managed-binding')
    for entry in binding['pins'].values():
        add_pin(pins, entry['path'], entry['sha256'], 'managed-qualification-evidence')
    # Fixed prior inventory establishes expected library bytes; actual loaded
    # paths are observed independently below and must match it exactly.
    require(native.sha(LIBRARY_INVENTORY) == LIBRARY_INVENTORY_SHA,
        'Historical native library inventory changed')
    add_pin(pins, LIBRARY_INVENTORY, LIBRARY_INVENTORY_SHA, 'prior-library-inventory')
    libraries = json.loads(LIBRARY_INVENTORY.read_text())
    require(len(libraries) == 7, 'Expected the seven pinned native runtime libraries')
    for entry in libraries:
        add_pin(pins, entry['path'], entry['sha256'], 'native-runtime-library')
    for name in ('native_cache.py', 'native_client.py', 'native_observed_cache.py',
                 'feature_contract.py'):
        add_pin(pins, ROOT/name, native.sha(ROOT/name), 'executed-cache-closure')
    return pins, {str(Path(entry['path']).absolute()): entry['sha256'] for entry in libraries}


def snapshot(pins, enforce=True):
    result = {}
    for path, item in pins.items():
        digest = native.sha(path)
        if enforce:
            require(digest == item['expected_sha256'], 'Held input changed: ' + path)
        result[path] = {'sha256': digest, 'bytes': Path(path).stat().st_size,
                        'roles': item['roles']}
    return result


def proc_memory(pid):
    values = {}
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        if line.split(':', 1)[0] in ('VmRSS', 'VmHWM', 'Threads'):
            key, value = line.split(':', 1)
            values[key] = value.strip()
    return values


def observed_server_factory(evidence, expected_libraries):
    class ObservedServer(native.OwnedServer):
        def start(self):
            client = super().start()
            pid = self.process.pid
            argv = Path(f'/proc/{pid}/cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
            require(argv == self.argv(int(self.origin.rsplit(':', 1)[-1])),
                'Actual owned native command differs from fixed profile')
            mappings = set()
            for line in Path(f'/proc/{pid}/maps').read_text().splitlines():
                columns = line.split(None, 5)
                if len(columns) == 6 and columns[5].startswith('/'):
                    path = columns[5]
                    if Path(path).name.startswith(('libggml', 'libllama')):
                        mappings.add(path)
            require(mappings == set(expected_libraries), 'Actual mapped native library inventory differs')
            actual = {path: native.sha(path) for path in sorted(mappings)}
            require(actual == expected_libraries, 'Actual mapped native library bytes differ')
            native.write_json(evidence/'actual-owned-native-process.json', {
                'pid': pid, 'pgid': os.getpgid(pid), 'sid': os.getsid(pid),
                'cmdline': argv, 'mapped_native_library_sha256': actual,
                'memory_at_ready': proc_memory(pid), 'environment_not_recorded': True})
            return client

        def stop(self):
            if self.process is not None and self.process.poll() is None:
                try:
                    native.write_json(evidence/'native-memory-before-stop.json', {
                        'pid': self.process.pid, 'memory': proc_memory(self.process.pid),
                        'interpretation': 'One native PID only; not whole-app SLA qualification'})
                except (OSError, ValueError) as error:
                    native.write_json(evidence/'native-memory-observation-error.json', {
                        'type': type(error).__name__, 'message': str(error)})
            return super().stop()
    return ObservedServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('plan', 'grant', 'output', 'evidence'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    for name in ('output', 'evidence'):
        path = getattr(args, name).absolute()
        require(path.is_relative_to(ROOT) and path != ROOT and not path.exists(),
            'Use fresh owned output/evidence paths')
        setattr(args, name, path)
    require(args.output != args.evidence, 'Evidence and native cache directories must differ')
    grant = json.loads(args.grant.read_text())
    controller.validate_grant(grant, args.plan, args.output)
    require(grant.get('observer_source_sha256') == native.sha(Path(__file__)),
        'Root grant must pin this additive observer')
    require(grant.get('managed_binding_sha256') == native.sha(args.plan.parent/'managed-qualification-binding.json'),
        'Root grant must pin completed all64 managed qualification binding')
    plan = json.loads(args.plan.read_text())
    pins, libraries = inventory(plan, args.plan, args.grant)
    before = snapshot(pins)
    args.evidence.mkdir()
    native.write_json(args.evidence/'closure-before.json', {'files': before,
        'observer_sha256': native.sha(Path(__file__)), 'native_requests': 0})
    code = None
    def interrupted(signum, frame):
        raise controller.CacheInterrupted(f'Observed cache controller received signal{signum}')
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)
    try:
        code = controller.run(args.plan, args.grant, args.output,
            server_factory=observed_server_factory(args.evidence, libraries))
    finally:
        # Even an extraction failure gets a fresh actual preservation check.
        after = snapshot(pins, enforce=False)
        native.write_json(args.evidence/'closure-after.json', {'files': after,
            'all_prepost_bytes_exact': before == after, 'controller_returncode': code,
            'no_additional_embedding_requests': True})
    return code if before == after else 1


if __name__ == '__main__':
    raise SystemExit(main())
