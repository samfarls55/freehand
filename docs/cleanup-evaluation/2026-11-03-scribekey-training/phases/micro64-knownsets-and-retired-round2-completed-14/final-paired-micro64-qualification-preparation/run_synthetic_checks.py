"""Run only synthetic paired tests, denying actual private/model/native I/O."""
from pathlib import Path
from unittest.mock import patch
import builtins
import io
import json
import os
import unittest

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
ROOT = TASK.parents[1]
FORBIDDEN = (
    str(TASK / 'blind-round'), str(TASK / 'blind-final'),
    str(TASK / 'data') + '/', str(TASK / 'pipeline') + '/', str(TASK / 'evaluation') + '/',
    '/tmp/freehand-scribekey-original-control-IQ4_XS/',
    str(ROOT / 'work/cleanup-poc/runtime') + '/',
    str(ROOT / 'work/cleanup-small-models-2026-11-03/scribe-precision-source/original-model') + '/',
)
attempts = []


def guarded(function, name):
    def invoke(path, *args, **kwargs):
        if isinstance(path, (str, bytes, os.PathLike)):
            value = os.fsdecode(path)
            if any(value.startswith(prefix) for prefix in FORBIDDEN):
                attempts.append({'operation': name, 'path': value})
                raise AssertionError('Forbidden real input/model/native access in synthetic test: ' + name)
        return function(path, *args, **kwargs)
    return invoke


buffer = io.StringIO()
with patch.object(builtins, 'open', guarded(builtins.open, 'builtins.open')), \
     patch.object(io, 'open', guarded(io.open, 'io.open')), \
     patch.object(os, 'open', guarded(os.open, 'os.open')), \
     patch.object(os, 'stat', guarded(os.stat, 'os.stat')), \
     patch.object(os, 'lstat', guarded(os.lstat, 'os.lstat')):
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern='test_runner.py')
    result = unittest.TextTestRunner(stream=buffer, verbosity=2).run(suite)
require_success = result.wasSuccessful() and result.testsRun == 15 and not attempts
with (HERE / 'synthetic-tests.log').open('x') as stream:
    stream.write(buffer.getvalue())
with (HERE / 'synthetic-access-proof.json').open('x') as stream:
    json.dump({'schema_version': 1, 'passed': result.testsRun - len(result.errors) - len(result.failures),
        'failed': len(result.errors) + len(result.failures), 'forbidden_access_attempts': attempts,
        'real_private_model_native_roots_denied_for_open_read_stat': list(FORBIDDEN),
        'actual_freeze_pair_or_authorized_pair_invoked': False,
        'test_inputs': 'New temporary synthetic500 corpus/commitment/consumed lock/reports and placeholder native only',
        'real_source_context_check_only': '42 versus45 small code-source hashes; no actual candidate freeze or model'}, stream, indent=2)
    stream.write('\n')
print(buffer.getvalue())
raise SystemExit(0 if require_success else 1)
