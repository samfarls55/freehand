#!/usr/bin/env python3
"""Freeze real Core normalization for approved NEW training rows only; no inference."""
from pathlib import Path
import collections
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import time

ROOT = Path('/workspace/freehand')
WORK = ROOT / 'work/cleanup-scribekey-training-2026-11-03'
OUTPUT = WORK / 'data-v5-candidate'
SOURCES = [
    (WORK / 'audit/v5-correction-curriculum/train-240-v3.jsonl', '639707f47876fba10f44263105e57663317c77f6e4eb7b771840bb6f2fb29689', 240),
    (WORK / 'audit/v5-literal-scope-curriculum/train-180-v1.jsonl', '4a1b524a16075d931a68610d885008856141f3411beae26bac68ed03d6e0ce0e', 180),
]
REPLAY_PARENT = WORK / 'data-v4-candidate/focused-repair-replay-1150.jsonl'
REPLAY_SHA = '463edcfe52558dfb614741ce548cc7a7de9a2284ef91f6e372ef7fc44f93eff9'
PROBE_SOURCE = ROOT / 'tools/Freehand.Cleanup.Probe/bin/Release/net10.0'
MANAGED = ['Freehand.Cleanup.Probe.dll', 'Freehand.Core.dll', 'Freehand.Cleanup.dll',
           'Freehand.Dictionary.dll', 'Freehand.Testing.dll', 'Freehand.Abstractions.dll']

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()

def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')

def write_rows(path, rows):
    with path.open('x', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')

assert not OUTPUT.exists(), 'Preserve existing normalization preparations'
assert sha(REPLAY_PARENT) == REPLAY_SHA
raw_rows = []
source_records = []
for path, expected, count in SOURCES:
    assert sha(path) == expected, path
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert len(rows) == count and all(row.get('split', 'train') == 'train' for row in rows)
    assert all('[[FREEHAND_LITERAL_' not in row['input'] and '[[FREEHAND_LITERAL_' not in row['target'] for row in rows), 'New rows must use real quoted text, not fake internal markers'
    raw_rows.extend(rows)
    source_records.append({'path': str(path), 'bytes': path.stat().st_size, 'sha256': expected, 'rows': count})
assert len(raw_rows) == 420 and len({row['id'] for row in raw_rows}) == 420
OUTPUT.mkdir()
frozen = OUTPUT / 'frozen-probe'
frozen.mkdir()
frozen_files = {}
for name in MANAGED + ['Freehand.Cleanup.Probe.runtimeconfig.json', 'Freehand.Cleanup.Probe.deps.json']:
    source = PROBE_SOURCE / name
    destination = frozen / name
    before = sha(source)
    shutil.copyfile(source, destination)
    assert sha(destination) == before
    frozen_files[name] = {'source_path': str(source), 'bytes': destination.stat().st_size, 'sha256': before}

source_snapshots = OUTPUT / 'source-snapshots'
source_snapshots.mkdir()
source_files = [ROOT / 'tools/Freehand.Cleanup.Probe/Program.cs',
    ROOT / 'tools/Freehand.Cleanup.Training/pipeline.py',
    ROOT / 'tools/Freehand.Cleanup.Evaluation/specialist_literal_protection.py',
    ROOT / 'tools/Freehand.Cleanup.Evaluation/literal_protection.py']
source_hashes = {}
for index, source in enumerate(source_files):
    destination = source_snapshots / (str(index) + '-' + source.name)
    shutil.copyfile(source, destination)
    source_hashes[str(source)] = {'sha256': sha(source), 'snapshot': str(destination)}
shutil.copyfile(Path(__file__), OUTPUT / 'preparation-source.py')

cases = []
for row in raw_rows:
    case = {'id': row['id'], 'input': row['input'], 'targets': [row['target']], 'split': 'development'}
    if row.get('dictionary'):
        case['dictionary'] = row['dictionary']
    cases.append(case)
fixture_path = OUTPUT / 'new-420-raw-core-fixtures.json'
write_json(fixture_path, {'schema_version': 1, 'purpose': 'Approved training normalization only; no model inference or quality evaluation', 'cases': cases})
export_path = OUTPUT / 'new-420-core-export.json'
argv = [str(ROOT / '.dotnet/dotnet'), str(frozen / 'Freehand.Cleanup.Probe.dll'), '--export-prompts',
        '--input', str(fixture_path), '--output', str(export_path), '--prompt-style', 'ScribeKeyFast',
        '--mask-specialist-literals', 'true']
write_json(OUTPUT / 'normalization-prepared.json', {'schema_version': 1, 'status': 'prepared',
    'argv': argv, 'inference_requested': False, 'sources': source_records, 'frozen_files': frozen_files,
    'source_snapshots': source_hashes, 'preparation_source_sha256': sha(Path(__file__))})
started = time.monotonic()
with (OUTPUT / 'core-export-console.log').open('xb') as stream:
    completed = subprocess.run(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False)
assert completed.returncode == 0, 'Real Core export failed; preserve output/log and inspect'
exported = json.loads(export_path.read_bytes())
assert exported['prompt_style'] == 'ScribeKeyFast' and len(exported['cases']) == 420
for name in MANAGED:
    assert exported['managed_assembly_sha256'][name].lower() == frozen_files[name]['sha256'], name
for name, item in frozen_files.items():
    assert sha(frozen / name) == item['sha256']
for path, expected, _ in SOURCES:
    assert sha(path) == expected
assert sha(REPLAY_PARENT) == REPLAY_SHA

spec = importlib.util.spec_from_file_location('pipeline', ROOT / 'tools/Freehand.Cleanup.Training/pipeline.py')
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)
by_id = {row['id']: row for row in raw_rows}
normalized, changes = [], []
for case in exported['cases']:
    original = by_id[case['fixture']['id']]
    assert len(case['normalized_targets']) == 1
    source, target = case['normalized_input'], case['normalized_targets'][0]
    prompt, masked_target, mask = pipeline.protected_pair(source, target)
    model_hash = hashlib.sha256(mask.masked_text.encode()).hexdigest()
    assert model_hash == case['model_input_sha256'], original['id']
    assert prompt == case['completion']['text'], original['id']
    assert mask.restore(masked_target) == target
    entry = {**original, 'id': original['id'] + '--core-normalized', 'input': source, 'target': target,
        'split': 'train', 'edit_needed': source != target,
        'raw_source_id': original['id'], 'raw_input': original['input'], 'raw_target': original['target'],
        'core_normalization': {'export_fixture_id': original['id'], 'export_sha256': sha(export_path),
            'model_input_sha256': model_hash, 'literal_protocol': case['literal_mask_protocol'],
            'specialist_output_normalization': case['specialist_output_normalization'],
            'production_prompt_exactly_equal': True, 'literal_roundtrip_exact': True}}
    normalized.append(entry)
    if source != original['input'] or target != original['target']:
        changes.append({'source_id': original['id'], 'raw_input': original['input'], 'normalized_input': source,
                        'raw_target': original['target'], 'normalized_target': target})
normalized_path = OUTPUT / 'new-420-core-normalized.jsonl'
write_rows(normalized_path, normalized)
write_json(OUTPUT / 'normalization-changes.json', changes)

replay_lines = REPLAY_PARENT.read_bytes().splitlines(keepends=True)[:480]
assert len(replay_lines) == 480
replay_bytes = b''.join(replay_lines)
replay = [json.loads(line) for line in replay_lines]
replay_path = OUTPUT / 'replay-480-exact.jsonl'
with replay_path.open('xb') as stream:
    stream.write(replay_bytes)
effective_new = []
for repeat in range(2):
    for row in normalized:
        effective_new.append({**row, 'id': row['id'] + '--oversample-' + str(repeat),
                              'sampling_repeat': repeat, 'oversampling_factor': 2})
final_path = OUTPUT / 'focused-correction-replay-1320.jsonl'
with final_path.open('xb') as stream:
    stream.write(replay_bytes)
    for row in effective_new:
        stream.write((json.dumps(row, ensure_ascii=False) + '\n').encode())
assert final_path.read_bytes().startswith(replay_bytes)
final_rows = pipeline.load_data(final_path)
assert len(final_rows) == 1320 and len({row['id'] for row in final_rows}) == 1320
targets_by_input = collections.defaultdict(set)
for row in final_rows:
    targets_by_input[row['input']].add(row['target'])
conflicts = [source for source, targets in targets_by_input.items() if len(targets) > 1]
assert not conflicts, 'Identical training input has contradictory targets'
from tokenizers import Tokenizer
tokenizer_path = ROOT / 'work/cleanup-small-models-2026-11-03/scribe-precision-source/original-model/tokenizer.json'
tokenizer = Tokenizer.from_file(str(tokenizer_path))
token_lengths = []
for row in final_rows:
    prompt = tokenizer.encode(row['prompt'], add_special_tokens=False).ids
    answer = tokenizer.encode(row['masked_target'], add_special_tokens=False).ids + [7]
    assert prompt[0] == 1 and prompt.count(1) == 1 and len(prompt) + len(answer) <= 1024
    token_lengths.append(len(prompt) + len(answer))
for source, item in source_hashes.items():
    assert sha(Path(source)) == item['sha256'], 'Preparation source changed during export'
manifest = {'schema_version': 1, 'status': 'prepared_for_root_overlap_and_training_approval_NOT_TRAINED',
    'sources': source_records, 'normalization': {'argv': argv, 'exit_code': completed.returncode,
       'seconds': time.monotonic() - started, 'model_inference': False, 'rows': 420,
       'input_changes': sum(r['input'] != r['raw_input'] for r in normalized),
       'target_changes': sum(r['target'] != r['raw_target'] for r in normalized),
       'changed_rows': len(changes), 'normalized_inputs_targets_used_not_compact_prompt_strings': True,
       'all_model_input_hashes_match_real_Core_export': True, 'all_complete_prompt_bytes_match': True,
       'all_literal_target_roundtrips_exact': True, 'frozen_files': frozen_files, 'source_snapshots': source_hashes,
       'export_sha256': sha(export_path)},
    'replay': {'source': str(REPLAY_PARENT), 'source_sha256': REPLAY_SHA, 'prefix_rows': 480,
       'prefix_bytes_sha256': hashlib.sha256(replay_bytes).hexdigest(), 'bytes_unchanged': True},
    'effective_rows': len(final_rows), 'unique_input_target_pairs': len({(r['input'], r['target']) for r in final_rows}),
    'unchanged_rows': sum(r['input'] == r['target'] for r in final_rows),
    'unchanged_fraction': sum(r['input'] == r['target'] for r in final_rows) / len(final_rows),
    'complete_token_range': [min(token_lengths), max(token_lengths)],
    'new_rows_oversampling_factor': 2, 'family_counts': dict(collections.Counter(r['family'] for r in final_rows)),
    'raw_source_files_changed': False, 'fresh_blind_data_read': False, 'actual_model_training_started': False,
    'files': {p.name: {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in
              [normalized_path, replay_path, final_path, fixture_path, export_path]}}
write_json(OUTPUT / 'manifest.json', manifest)
print(json.dumps({'prepared': str(final_path), 'sha256': sha(final_path),
    'effective_rows': len(final_rows), 'unique_pairs': manifest['unique_input_target_pairs'],
    'unchanged_rows': manifest['unchanged_rows'], 'max_tokens': max(token_lengths),
    'core_input_changes': manifest['normalization']['input_changes'], 'core_target_changes': manifest['normalization']['target_changes'],
    'model_training_started': False}, indent=2))
