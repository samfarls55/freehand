#!/usr/bin/env python3
"""Observed400 extraction: active source closure plus historical certificates.

No Torch import, target use or added native forward. Does not freeze or execute
the mutable shared training pipeline or historical managed DLLs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal

import native400_cache as controller
import native400_client as native

ROOT = Path(__file__).absolute().parent
LIBRARY_INVENTORY = ROOT/'native-smoke-01/native-library-pins.json'
LIBRARY_INVENTORY_SHA = '8f84f760d780559ecbbcae4e3d70bb446ad0499bd661dba5d593b3c675fc5efe'
PLAN_SHA = 'a709c8d3fdb36ceedfc7cd4430d1e79a75e05b4608d4ffabad84bd992cad793e'
BINDING_SHA = '19aafec1b54b582872bdacda7a7e89fbcdfe8339c8263e0f460ae6b3f12af1ae'


def require(test, message):
    if not test:
        raise ValueError(message)


def add_pin(pins, path, expected, role):
    path = str(Path(path).absolute())
    if path in pins:
        require(pins[path]['expected_sha256'] == expected, 'Conflicting input pin')
        pins[path]['roles'].append(role)
    else:
        pins[path] = {'expected_sha256': expected, 'roles': [role]}


def inventory(plan, plan_path, grant_path):
    require(native.sha(plan_path) == PLAN_SHA, 'Use final compact400plan')
    pins = {}
    add_pin(pins, plan_path, PLAN_SHA, 'authorized-complete400-plan')
    add_pin(pins, grant_path, native.sha(grant_path), 'root-native-CPU-grant')
    # Exactly the project Python modules imported/executed by this native path.
    # Source-tag model/trainer and mutable shared pipeline are not dependencies.
    active_sources = ('native400_observed_cache.py', 'native400_cache.py', 'native400_client.py',
        'feature_contract.py', 'protection.py', 'editor_core/__init__.py',
        'editor_core/core.py', 'editor_core/head_contract.py')
    for name in active_sources:
        add_pin(pins, ROOT/name, native.sha(ROOT/name), 'active-native-extraction-source')
    for name, expected in plan['sources'].items():
        path = (ROOT/name).absolute()
        require(path.is_relative_to(ROOT), 'Plan code dependency escapes prototype')
        add_pin(pins, path, expected, 'plan-active-code-dependency')
    for path, expected, role in (
        (native.SERVER, native.SERVER_SHA, 'runtime-executable'),
        (native.BASE, native.BASE_SHA, 'original-IQ4-base-read-only'),
        (native.ADAPTER, native.ADAPTER_SHA, 't050-F32-adapter-read-only'),
        (plan['dataset']['path'], plan['dataset']['sha256'], 'approved-training-input-provenance'),
        (plan['tokenizer']['path'], plan['tokenizer']['sha256'], 'official-tokenizer-provenance')):
        add_pin(pins, path, expected, role)
    binding_path = plan_path.parent/'managed-qualification-binding-v2.json'
    require(native.sha(binding_path) == BINDING_SHA, 'Completed400 managed binding changed')
    binding = json.loads(binding_path.read_text())
    require(binding['plan']['sha256'] == PLAN_SHA and binding['checked_inputs'] == 400
        and binding['all_prompts_exact'] is True, 'Managed binding does not cover exact400source encoders')
    add_pin(pins, binding_path, BINDING_SHA, 'historical-managed-certificate-binding')
    for item in binding['pins'].values():
        add_pin(pins, item['path'], item['sha256'], 'historical-managed-certificate-body')
    historical = binding['historical_unused_pipeline']
    require(historical['current_live_pipeline_is_not_an_executed_cache_dependency'] is True,
        'Do not freeze an unused mutable live pipeline as historical8c')
    add_pin(pins, historical['preserved_body_path'], historical['historical_sha256'],
        'archived-historical8c-body-not-executed')
    add_pin(pins, historical['substitution_receipt_path'], historical['substitution_receipt_sha256'],
        'additive-historical8c-substitution-receipt')
    literal_archive = plan_path.parent/'literal-source-archive.json'
    archive = json.loads(literal_archive.read_text())
    require(archive['plan_sha256'] == PLAN_SHA, 'Literal preparation archive refers to another plan')
    add_pin(pins, literal_archive, native.sha(literal_archive), 'historical-literal-preparation-provenance')
    require(set(archive['sources']) == set(plan['literal']['executed_sources']), 'Incomplete literal preparation archive')
    for name, item in archive['sources'].items():
        require(item['sha256'] == plan['literal']['executed_sources'][name]['sha256'], 'Literal archive byte identity differs')
        add_pin(pins, item['preserved_body_path'], item['sha256'], 'archived-preparation-helper-not-executed')
    require(native.sha(LIBRARY_INVENTORY) == LIBRARY_INVENTORY_SHA, 'Historical native library pins changed')
    add_pin(pins, LIBRARY_INVENTORY, LIBRARY_INVENTORY_SHA, 'runtime-library-inventory')
    libraries = json.loads(LIBRARY_INVENTORY.read_text())
    require(len(libraries) == 7, 'Expected seven pinned native runtime libraries')
    for item in libraries:
        add_pin(pins, item['path'], item['sha256'], 'native-runtime-library')
    return pins, {item['path']: item['sha256'] for item in libraries}


def snapshot(pins, enforce=True):
    result = {}
    for path, item in pins.items():
        digest = native.sha(path)
        if enforce:
            require(digest == item['expected_sha256'], 'Held input changed: '+path)
        result[path] = {'sha256': digest, 'bytes': Path(path).stat().st_size, 'roles': item['roles']}
    return result


def proc_memory(pid):
    result = {}
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        key, _, value = line.partition(':')
        if key in ('VmRSS', 'VmHWM', 'Threads'):
            result[key] = value.strip()
    return result


def observed_server_factory(evidence, expected_libraries):
    class ObservedServer(native.OwnedServer):
        def start(self):
            client = super().start()
            pid = self.process.pid
            argv = Path(f'/proc/{pid}/cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
            require(argv == self.argv(int(self.origin.rsplit(':', 1)[-1])), 'Actual native command differs')
            mapped = set()
            for line in Path(f'/proc/{pid}/maps').read_text().splitlines():
                columns = line.split(None, 5)
                if len(columns) == 6 and columns[5].startswith('/') and Path(columns[5]).name.startswith(('libggml', 'libllama')):
                    mapped.add(columns[5])
            require(mapped == set(expected_libraries), 'Actual native mapped libraries differ')
            actual = {path: native.sha(path) for path in sorted(mapped)}
            require(actual == expected_libraries, 'Actual native library bytes differ')
            native.write_json(evidence/'actual-owned-native-process.json', {'pid': pid,
                'pgid': os.getpgid(pid), 'sid': os.getsid(pid), 'cmdline': argv,
                'mapped_native_library_sha256': actual, 'memory_at_ready': proc_memory(pid),
                'environment_not_recorded': True})
            return client

        def stop(self):
            if self.process is not None and self.process.poll() is None:
                try:
                    native.write_json(evidence/'native-memory-before-stop.json', {'pid': self.process.pid,
                        'memory': proc_memory(self.process.pid), 'scope': 'NativePID only;not whole-app resource qualification'})
                except OSError as error:
                    native.write_json(evidence/'native-memory-observation-error.json', {'type': type(error).__name__, 'message': str(error)})
            return super().stop()
    return ObservedServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('plan', 'grant', 'output', 'metadata-output', 'evidence'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.absolute()
    args.metadata_output = args.metadata_output.absolute()
    args.evidence = args.evidence.absolute()
    grant = json.loads(args.grant.read_text())
    controller.validate_grant(grant, args.plan, args.output, args.metadata_output)
    require(args.evidence.is_relative_to(ROOT) and args.evidence != ROOT and not args.evidence.exists()
        and not args.evidence.is_symlink() and not any(path.is_symlink() for path in args.evidence.parents),
        'Use a fresh regular owned evidence directory')
    require(args.evidence != args.metadata_output and not args.evidence.is_relative_to(args.metadata_output)
        and not args.metadata_output.is_relative_to(args.evidence), 'Metadata/evidence must be disjoint')
    require(grant.get('observer_source_sha256') == native.sha(Path(__file__)), 'Root grant must pin observer')
    require(grant.get('managed_binding_sha256') == BINDING_SHA, 'Root grant must pin final400managed binding')
    plan = json.loads(args.plan.read_text())
    pins, libraries = inventory(plan, args.plan, args.grant)
    before = snapshot(pins)
    args.evidence.mkdir()
    native.write_json(args.evidence/'closure-before.json', {'files': before,
        'active_shared_training_pipeline_frozen_or_executed': False,
        'historical_certificate_bodies_only': True, 'native_requests': 0})
    code = None
    def interrupted(signum, frame):
        raise controller.CacheInterrupted(f'Observed400 controller received signal{signum}')
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)
    try:
        code = controller.run(args.plan, args.grant, args.output,
            server_factory=observed_server_factory(args.evidence, libraries), metadata_output=args.metadata_output)
    finally:
        after = snapshot(pins, enforce=False)
        native.write_json(args.evidence/'closure-after.json', {'files': after,
            'all_prepost_bytes_exact': before == after, 'controller_returncode': code,
            'no_additional_embedding_requests': True,
            'active_shared_training_pipeline_frozen_or_executed': False})
    return code if before == after else 1


if __name__ == '__main__':
    raise SystemExit(main())
