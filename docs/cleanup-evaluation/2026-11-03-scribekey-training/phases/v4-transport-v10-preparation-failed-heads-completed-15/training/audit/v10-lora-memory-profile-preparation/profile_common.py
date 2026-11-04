"""Pinned, source-only V10 profile contracts. Importing performs no heavy work."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
REPO = Path('/workspace/freehand')
PYTHON = '/workspace/freehand/work/cleanup-small-models-2026-11-03/scribe-precision-source/conversion-env/bin/python'
PIPELINE = REPO/'tools/Freehand.Cleanup.Training/pipeline.py'
PIPELINE_SHA = '27a2cd8de2ec90c3d78d50487d95f72d11537f61339f00b1e3fc33d7ebd619fb'
EXPERIMENT = HERE.parent/'v10-lora-experiment-preparation'
DATA = EXPERIMENT/'data-600-v1/positive-600-v1.jsonl'
DATA_SHA = '4fec04c191c8324a547050500ce691fd3bc9ae65f45637cb218641a8e768c697'
PARENT = Path('/tmp/freehand-v8-v9-factor-izdqupmr/t050')
PARENT_SHA = '5a525200352df9dd65a025d81f4988d7edb1694f3ef70d86fe7d88ceed8d9993'
PARENT_CONFIG_SHA = '41fbbef51f05142696ff8c3d8d764d5c787207dada7eaeca3de620780d2c5660'
DERIVATION_SHA = '187afb518ec4d43f1d812ebf9900e34ec6fe09a291ed8bfcc777ebae70ef624e'
BASE_SHA = '82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174'
MEMORY_CAP = 16_500_000_000
SOURCE_NAMES = ('profile_common.py', 'profile_controller.py', 'profile_worker.py',
                'profile_supervisor.py', 'safetensor_audit.py')


def require(test, message):
    if not test:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def source_pins():
    return {name: sha(HERE/name) for name in SOURCE_NAMES}


def validate_output(path):
    path = Path(path).absolute()
    require(path.is_relative_to(Path('/dev/shm')) and path != Path('/dev/shm'),
        'Profile artifacts must stay in a fresh owned /dev/shm directory')
    require(not path.exists() and not any(item.is_symlink() for item in (path, *path.parents)),
        'Profile output must be fresh and must not traverse symlinks')
    return path


def load_recipe(path, profile):
    value = json.loads(Path(path).read_text())
    require(value.get('schema_version') == 1 and value.get('status') == 'PREPARED_NOT_EXECUTED_PROFILE_ONLY',
        'Require the explicit non-candidate profile recipe')
    choices = value.get('profiles', {})
    require(profile in choices and profile in ('worst239_gc_on', 'short_gc_off', 'short_gc_on'),
        'Unknown prechosen profile')
    selected = choices[profile]
    require(selected.get('profile_only') is True and selected.get('candidate_eligible') is False,
        'Profile weights must never become a training candidate')
    require(selected.get('pipeline_sha256') == PIPELINE_SHA and selected.get('pipeline_path') == str(PIPELINE),
        'Only the applied, independently reviewed new main train CLI is supported')
    require(selected.get('gradient_checkpointing') is (profile != 'short_gc_off'), 'GC profile differs')
    require(selected.get('rows') == 8 and selected.get('epochs') == 1 and selected.get('batch_size') == 1
        and selected.get('gradient_accumulation') == 8 and selected.get('max_steps') == 1
        and selected.get('checkpoint_every') == 0 and selected.get('warmup_steps') == 0,
        'Profile must be eight controlled exposures and exactly one fresh update')
    return value, selected


def train_argv(profile, output):
    # Reuses the actual train parser and handler; no BF16 profile() shortcut.
    argv = ['train', '--base', profile['base_directory'], '--training-base-mode',
        'original-iq4-dequantized-fp32-v1', '--gguf-base', profile['gguf_base'],
        '--activation-quantization', 'native-q8-k', '--native-runtime', profile['native_runtime'],
        '--kv-roundtrip', 'none', '--specialist-literal-protocol', 'specialist-compact-v4',
        '--parent-adapter-sha256', PARENT_SHA, '--train', profile['dataset']['path'],
        '--threads', '4', '--seed', '42', '--rank', '8', '--alpha', '16',
        '--learning-rate', '0.00002', '--epochs', '1', '--batch-size', '1',
        '--gradient-accumulation', '8', '--warmup-steps', '0', '--checkpoint-every', '0',
        '--max-tokens', '256', '--resume-adapter', str(PARENT), '--max-steps', '1',
        '--output', str(output)]
    if profile['gradient_checkpointing']:
        argv.append('--gradient-checkpointing')
    return argv


def validate_grant(grant, recipe_path, profile_name, profile, output):
    require(grant.get('schema_version') == 1 and grant.get('authorized_by') == '/root'
        and grant.get('operation') == 'v10-matched-memory-profile' and grant.get('approved') is True,
        'An explicit ROOT matched-profile CPU grant is required')
    require(grant.get('profile') == profile_name and grant.get('output_directory') == str(output),
        'ROOT grant profile/output differs')
    require(grant.get('recipe_sha256') == sha(recipe_path) and grant.get('profile_sha256') == canonical_sha(profile),
        'ROOT grant recipe/profile pins differ')
    require(grant.get('source_pins') == source_pins(), 'ROOT grant controller/observer/supervisor source pins differ')
    require(grant.get('memory_cap_bytes') == MEMORY_CAP and type(grant.get('memory_cap_bytes')) is int,
        'ROOT grant must retain the16.5GB sampled memory stop')
    seconds = grant.get('max_wall_seconds')
    require(type(seconds) in (int, float) and math.isfinite(seconds) and 0 < seconds <= 300,
        'ROOT grant must bound one profile to at most300 work seconds')
    require(grant.get('exclusive_cpu_after_prior_release') is True and grant.get('profile_weights_are_not_candidates') is True,
        'ROOT must explicitly release prior work and forbid candidate reuse')
    return seconds


def verify_inputs(items):
    observed = []
    roles = set()
    for item in items:
        require(isinstance(item.get('role'), str) and item['role'] not in roles, 'Input roles must be explicit and unique')
        roles.add(item['role'])
        require(isinstance(item.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', item['sha256']),
            'Every immutable profile input needs a full expected SHA256')
        path = Path(item['path'])
        require(path.is_absolute() and path.is_file(), 'Profile input is not an explicit regular file')
        digest = sha(path)
        require(digest == item['sha256'], 'Immutable profile input changed: '+item['role'])
        require('bytes' not in item or path.stat().st_size == item['bytes'], 'Profile input size changed: '+item['role'])
        observed.append({**item, 'observed_sha256': digest, 'observed_bytes': path.stat().st_size,
            'resolved_path': str(path.resolve())})
    return observed
