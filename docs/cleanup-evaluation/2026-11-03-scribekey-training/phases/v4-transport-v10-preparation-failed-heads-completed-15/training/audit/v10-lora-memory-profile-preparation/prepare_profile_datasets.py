"""Author controlled profile repeats from pinned approved600; no tokenizer/model."""
from __future__ import annotations
import copy
import json
from pathlib import Path
from profile_common import HERE, DATA, DATA_SHA, EXPERIMENT, PIPELINE, PIPELINE_SHA, sha, canonical_sha, write_json


def prepare():
    if sha(DATA) != DATA_SHA:
        raise ValueError('Approved600 data changed')
    rows = [json.loads(line) for line in DATA.read_text().splitlines() if line]
    check_path = EXPERIMENT/'data-600-v1/final600-v4-checks.jsonl'
    checks = {row['id']: row for row in (json.loads(line) for line in check_path.read_text().splitlines() if line)}
    assert len(rows) == len(checks) == 600 and len({row['id'] for row in rows}) == 600
    worst = next(row for row in rows if row['id'] == 'scribe-scope-copy-v10-b-088')
    assert checks[worst['id']]['complete_tokens'] == max(row['complete_tokens'] for row in checks.values()) == 239
    short = min(enumerate(rows), key=lambda pair: (checks[pair[1]['id']]['complete_tokens'], pair[0]))[1]
    target = HERE/'datasets'; target.mkdir(exist_ok=False)
    result = {}
    for kind, original in [('worst239', worst), ('short', short)]:
        evidence = checks[original['id']]
        for field in ('input', 'target'):
            assert evidence[field+'_sha256'] == __import__('hashlib').sha256(original[field].encode()).hexdigest()
        copies = []
        for index in range(8):
            row = copy.deepcopy(original)
            row['id'] = f'v10-profile-{kind}-repeat-{index+1:02d}'
            row['profile_controlled_repeat'] = {'profile_only': True, 'canonical_source_id': original['id'],
                'approved600_sha256': DATA_SHA, 'copy_ordinal': index+1,
                'not_new_training_data': True, 'candidate_eligible': False}
            copies.append(row)
        path = target/(kind+'-eight-v1.jsonl')
        with path.open('x') as stream:
            for row in copies:
                stream.write(json.dumps(row, ensure_ascii=False, separators=(',', ':'))+'\n')
        assert len({row['id'] for row in copies}) == 8
        assert all(row['input'] == original['input'] and row['target'] == original['target'] for row in copies)
        result[kind] = {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size,
            'canonical_source_id': original['id'], 'input_sha256': evidence['input_sha256'],
            'target_sha256': evidence['target_sha256'], 'complete_tokens': evidence['complete_tokens'],
            'assistant_tokens_per_copy': evidence['assistant_tokens'], 'rows': 8,
            'controlled_repeats_not_new_training_data': True}
    write_json(HERE/'profile-datasets.json', {'schema_version': 1, 'status': 'FILE_ONLY_PROFILE_REPEATS_NOT_EXECUTED',
        'approved600': {'path': str(DATA), 'sha256': DATA_SHA},
        'prior_actual_trainer_token_checks': {'path': str(check_path), 'sha256': sha(check_path)},
        'datasets': result, 'model_or_tokenizer_executed': False})
    base = '/workspace/freehand/work/cleanup-small-models-2026-11-03/scribe-precision-source/original-model'
    shared = {'pipeline_path': str(PIPELINE), 'pipeline_sha256': PIPELINE_SHA,
        'base_directory': base, 'gguf_base': '/tmp/freehand-scribekey-original-control-IQ4_XS/ScribeKey-Fast-v1.1-Freehand-original-control-IQ4_XS.gguf',
        'native_runtime': '/workspace/freehand/work/cleanup-poc/runtime/llama-b12015',
        'profile_only': True, 'candidate_eligible': False, 'rows': 8, 'epochs': 1, 'batch_size': 1,
        'gradient_accumulation': 8, 'max_steps': 1, 'checkpoint_every': 0, 'warmup_steps': 0,
        'schedule_total_optimizer_steps': 1, 'effective_warmup_steps': 0,
        'optimizer_initialization': 'fresh AdamW, not inherited', 'seed': 42, 'learning_rate': .00002,
        'full_base_write': False, 'use_for150_training': False}
    profiles = {name: {**shared, 'dataset': result[kind], 'gradient_checkpointing': gc}
        for name, kind, gc in [('worst239_gc_on', 'worst239', True), ('short_gc_off', 'short', False), ('short_gc_on', 'short', True)]}
    write_json(HERE/'profile-recipes.json', {'schema_version': 1, 'status': 'PREPARED_NOT_EXECUTED_PROFILE_ONLY',
        'profiles': profiles, 'priority': ['worst239_gc_on', 'short_gc_off', 'short_gc_on'],
        'short_controls_only_difference': 'gradient_checkpointing flag and separately owned output; source/data/seed/warmstart/schedule identical',
        'profile_schedule_not150_schedule': True})


if __name__ == '__main__':
    prepare()
