#!/usr/bin/env python3
"""V8 owned execution; derived from audited e7f631 with durable observations."""

from __future__ import annotations

import argparse

from collections import Counter

import hashlib

import json

import os

import re

import signal

from pathlib import Path

import shutil

import subprocess

import sys

import time

ROOT = Path('/workspace/freehand')

BASE = Path('/tmp/freehand-scribekey-original-control-IQ4_XS/ScribeKey-Fast-v1.1-Freehand-original-control-IQ4_XS.gguf')

RUNTIME = ROOT / 'work/cleanup-poc/runtime/llama-b12015/llama-server'

def require(condition, message):
    if not condition:
        raise ValueError(message)

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')

def expected_native_options(adapter, cache_type='f16'):
    return {'--model': str(BASE), '--lora': str(adapter), '--ctx-size': '1024', '--threads': '4',
        '--threads-batch': '4', '--batch-size': '64', '--ubatch-size': '64',
        '--cache-type-k': cache_type, '--cache-type-v': cache_type, '--cache-ram': '0', '--ctx-checkpoints': '0',
        '--n-predict': '512', '--parallel': '1', '--n-gpu-layers': '0', '--fit': 'off', '--spec-type': 'ngram-map-k',
        '--spec-ngram-map-k-size-n': '3', '--spec-ngram-map-k-size-m': '16'}

def verify_native_arguments(argv, adapter, cache_type='f16'):
    require(Path(argv[0]).resolve() == RUNTIME.resolve(), 'Observed worker executable differs')
    for name, value in expected_native_options(adapter, cache_type).items():
        require(argv.count(name) == 1 and argv.index(name) + 1 < len(argv)
                and argv[argv.index(name) + 1] == value, 'Observed native flag differs: ' + name)
    require('--flash-attn' not in argv and '-fa' not in argv, 'Flash attention must retain unmodified runtime default auto')
    require('--lora-scaled' not in argv, 'Unit1 unmerged adapter must not be scaled twice')
    require(all(flag in argv for flag in ('--no-repack', '--no-context-shift', '--no-jinja', '--offline')),
            'Observed fixed native mode flags differ')

def live_owned_group_members(group_id, proc_root=Path('/proc')):
    members = []
    for directory in proc_root.glob('[0-9]*'):
        try:
            fields = (directory/'stat').read_text().rsplit(')', 1)[1].split()
            if fields[0] not in ('Z', 'X') and int(fields[2]) == group_id and int(fields[3]) == group_id:
                members.append(int(directory.name))
        except (OSError, ValueError, IndexError):
            pass
    return sorted(members)

def stop_owned_group(process):
    # start_new_session=True makes this exact child PID the owned group/session.
    # Dead Z/X records can remain under PID1; they are not live workers and
    # cannot be reaped by this controller. The immediate owned child is reaped.
    if live_owned_group_members(process.pid):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic()+2
    while time.monotonic() < deadline:
        process.poll()
        if not live_owned_group_members(process.pid):
            break
        time.sleep(.05)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    for _ in range(10):
        if not live_owned_group_members(process.pid):
            return True
        time.sleep(.05)
    return False

def execute(command, log_path, env, adapter=None, cache_type='f16', timeout_seconds=1200, report_path=None):
    journal = log_path.with_suffix('.observations.jsonl')
    with journal.open('xb'):
        pass
    append_observation(journal, {'event': 'command_declared', 'argv': command})
    observed = {}
    errors = []
    started = time.monotonic()
    process = None
    reason = None
    first_outcome_checked = False
    cleanup_verified = False
    prior_handlers = {}
    def interrupt(signum, _frame):
        raise KeyboardInterrupt('Owned diagnostic interrupted by signal ' + str(signum))
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            prior_handlers[signum] = signal.signal(signum, interrupt)
        with log_path.open('xb') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True)
            append_observation(journal, {'event': 'owned_process_started', 'pid': process.pid,
                'owned_group_and_session': process.pid,
                'start_ticks': int(Path('/proc', str(process.pid), 'stat').read_text().rsplit(')',1)[1].split()[19])})
            print(json.dumps({'stage': log_path.stem, 'pid': process.pid, 'owned_process_group': process.pid,
                'argv': command}), flush=True)
            while process.poll() is None:
                if time.monotonic()-started > timeout_seconds:
                    reason = 'bounded_controller_timeout'
                    break
                if adapter is not None:
                    for directory in Path('/proc').glob('[0-9]*'):
                        try:
                            name = (directory/'comm').read_text().strip()
                            if name not in ('llama-server', 'llama-server.ex', 'llama-server.exe'):
                                continue
                            pid = int(directory.name)
                            if pid in observed:
                                continue
                            stat = (directory/'stat').read_text().rsplit(')', 1)[1].split()
                            if stat[0] in ('Z', 'X'):
                                continue
                            owned = int(stat[2]) == process.pid and int(stat[3]) == process.pid
                            if not owned:
                                observed[pid] = {'pid': pid, 'name': name, 'owned_group': False,
                                    'full_arguments_read': False}
                                append_observation(journal, {'event': 'unexpected_native_worker', 'record': observed[pid]})
                                errors.append('Unexpected concurrent native worker PID ' + str(pid))
                                continue
                            # Inspect full argv only after proving the process is
                            # in this evaluation's dedicated session and group.
                            argv = [os.fsdecode(v) for v in (directory/'cmdline').read_bytes().split(b'\0') if v]
                            entry = {'pid': pid, 'start_ticks': int(stat[19]), 'argv': argv,
                                'owned_process_group': process.pid, 'owned_session': process.pid}
                            try:
                                verify_native_arguments(argv, adapter, cache_type)
                                entry['requested_fixed_cache_profile_verified'] = True
                            except ValueError as error:
                                entry['requested_fixed_cache_profile_verified'] = False
                                errors.append(str(error))
                            observed[pid] = entry
                            append_observation(journal, {'event': 'owned_native_worker_observed', 'record': entry})
                        except (OSError, ValueError, IndexError) as error:
                            if isinstance(error, ValueError):
                                errors.append(str(error))
                if report_path is not None and not first_outcome_checked and report_path.is_file():
                    try:
                        partial = read(report_path)
                        first = partial.get('cases', [None])[0] if partial.get('cases') else None
                        if first:
                            first_outcome_checked = True
                        if first and first.get('cleanup_status') == 'Failed' and any(message in (first.get('error') or '')
                                for message in ('The cleanup worker exited before its model was ready.',
                                                'The cleanup model did not become ready within its startup deadline.')):
                            reason = 'initial_native_startup_failure; inspect preserved first outcome/logs; cache unsupported is not inferred'
                            break
                    except (OSError, json.JSONDecodeError):
                        pass
                time.sleep(.25)
    except KeyboardInterrupt as error:
        reason = str(error)
    finally:
        if process is not None:
            # Preserve receipts/partial Core output even on interruption. Only
            # this session/group is terminated; unrelated jobs are never killed.
            cleanup_verified = stop_owned_group(process)
        for signum, handler in prior_handlers.items():
            signal.signal(signum, handler)
        result = {'argv': command, 'pid': process.pid if process else None,
            'owned_process_group': process.pid if process else None,
            'exit_code': process.returncode if process else None, 'termination_reason': reason,
            'timeout_seconds': timeout_seconds, 'wall_seconds_diagnostic_only': time.monotonic()-started,
            'observed_native_workers': list(observed.values()), 'native_argument_errors': sorted(set(errors)),
            'native_requested_cache_arguments_observed_and_verified': bool(observed) and not errors and reason is None,
            'owned_process_group_cleanup_completed': cleanup_verified,
            'cleanup_scope': 'no live owned group/session members; immediate owned child reaped; Z/X ignored'}
        append_observation(journal, {'event': 'command_finished', 'pid': result['pid'], 'exit_code': result['exit_code'],
            'termination_reason': reason, 'owned_process_group_cleanup_completed': cleanup_verified})
        result['durable_observation_journal'] = str(journal)
        write(log_path.with_suffix('.command-receipt.json'), result)
    return result


def append_observation(path, value):
    with path.open('ab') as stream:
        stream.write((json.dumps(value, ensure_ascii=False)+'\n').encode('utf-8'))
        stream.flush()
        os.fsync(stream.fileno())
