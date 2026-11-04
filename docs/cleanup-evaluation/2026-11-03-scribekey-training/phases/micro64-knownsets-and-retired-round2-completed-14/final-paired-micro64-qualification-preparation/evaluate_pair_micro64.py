#!/usr/bin/env python3
"""Micro64 paired Core epoch: unchanged qualified42 sources plus three pair files.

Import/configuration reads only pinned source. No model, corpus, commitment,
consumed lock, author, review or private-path status is inspected here.
"""
from pathlib import Path
import hashlib
import importlib.util

ROOT = Path('/workspace/freehand')
HERE = Path(__file__).resolve().parent
QUALIFICATION_ENTRY = ROOT / 'work/cleanup-scribekey-training-2026-11-03/micro64-qualification-preparation/evaluate_micro64.py'
QUALIFICATION_SHA256 = '5e14b82b546ebbb23220476b69ff6fe30fafc68f293cd16f81f9208ecceb450a'
PAIR_SOURCES = (Path(__file__).resolve(), HERE / 'run.py', HERE / 'paired_owned_execution.py')
_engine = None


def qualification_evaluator():
    if hashlib.sha256(QUALIFICATION_ENTRY.read_bytes()).hexdigest() != QUALIFICATION_SHA256:
        raise ValueError('Held micro64 qualification wrapper source drift')
    spec = importlib.util.spec_from_file_location('freehand_final_pair_qualified_micro64_context', QUALIFICATION_ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.configure_evaluator()


def configure_evaluator():
    global _engine
    if _engine is None:
        value = qualification_evaluator()
        qualified_sources = value.source_files

        def source_files():
            captured = qualified_sources()
            for path in PAIR_SOURCES:
                captured[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
            return captured

        value.source_files = source_files
        _engine = value
    return _engine


def __getattr__(name):
    return getattr(configure_evaluator(), name)


if __name__ == '__main__':
    raise SystemExit(configure_evaluator().main())
