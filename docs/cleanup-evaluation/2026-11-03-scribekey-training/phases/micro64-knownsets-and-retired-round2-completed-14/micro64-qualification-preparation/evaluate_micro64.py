#!/usr/bin/env python3
"""Pinned upstream evaluator with one explicit work-only microbatch64 profile epoch."""
from pathlib import Path
import hashlib
import importlib.util
import sys

ROOT = Path('/workspace/freehand')
HERE = Path(__file__).resolve().parent
UPSTREAM = ROOT / 'tools/Freehand.Cleanup.Training/evaluate.py'
UPSTREAM_SHA256 = '131d2db2d5c04d7cca42ece2211c6c0606b6b9380eef15ae2216f3a37de6c7ec'
if hashlib.sha256(UPSTREAM.read_bytes()).hexdigest() != UPSTREAM_SHA256:
    raise ValueError('Pinned upstream evaluator source drift')
sys.path.insert(0, str(UPSTREAM.parent))
spec = importlib.util.spec_from_file_location('freehand_micro64_upstream_evaluate', UPSTREAM)
upstream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upstream)
original_profile = upstream.runtime_profile
original_sources = upstream.source_files
original_native = upstream.native

def runtime_profile(*args, **kwargs):
    value = original_profile(*args, **kwargs)
    if type(value.get('microBatchSize')) is not int or value['microBatchSize'] != 32 or value['batchSize'] != 64:
        raise ValueError('Upstream baseline profile changed; expected batch64/micro32')
    return {**value, 'microBatchSize': 64}

def source_files():
    value = original_sources()
    for path in (Path(__file__).resolve(), HERE / 'owned_execution.py', HERE / 'run.py'):
        value[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return value

def native(arguments):
    if arguments.mode != 'core':
        raise ValueError('Micro64 work epoch supports Core only; upstream native replay fixes microbatch32')
    return original_native(arguments)

def configure_evaluator():
    return upstream

upstream.native = native
upstream.runtime_profile = runtime_profile
upstream.source_files = source_files

def __getattr__(name):
    return getattr(upstream, name)

if __name__ == '__main__':
    raise SystemExit(upstream.main())
