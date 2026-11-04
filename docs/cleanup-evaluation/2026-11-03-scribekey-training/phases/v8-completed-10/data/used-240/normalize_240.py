#!/usr/bin/env python3
"""One immutable, no-inference Core alignment of the separately reserved240 pairs."""
from pathlib import Path
import collections
import datetime
import hashlib
import importlib.util
import json
import os
import subprocess
import time
import unicodedata

ROOT = Path('/workspace/freehand')
WORK = ROOT / 'work/cleanup-scribekey-training-2026-11-03'
HERE = Path(__file__).resolve().parent
OUT = HERE / 'core-normalization-v1'
DATA = HERE / 'train-240-v1.jsonl'
FIXTURES = HERE / 'core-normalization-input-target-480.json'
PROBE = WORK / 'data-v5-candidate/frozen-probe'
DATA_SHA = '922af3f8564703815e69eb7a3c49dbeb870cd560556485107ad4e14d45466829'
FIXTURES_SHA = '249947c2ac938835c0fcd6ebe6328aac7d6d838a01b00aa17bdf842ef5ef7c30'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def write_rows(path, rows):
    with path.open('x', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def opaque_hash(value):
    return text_sha(' '.join(unicodedata.normalize('NFC', value).split()).strip().casefold())


def main():
    assert sha(DATA) == DATA_SHA and sha(FIXTURES) == FIXTURES_SHA
    raw = [json.loads(line) for line in DATA.read_text().splitlines()]
    fixtures = json.loads(FIXTURES.read_text())
    assert len(raw) == 240 and len(fixtures['cases']) == 480
    assert fixtures['source_dataset_sha256'] == DATA_SHA
    assert len({row['id'] for row in raw}) == 240
    fixture_map = []
    for position, row in enumerate(raw):
        for offset, side in enumerate(('input', 'target')):
            case = fixtures['cases'][position * 2 + offset]
            assert case['id'] == row['id'] + '/' + side
            assert case['input'] == row[side] and case['split'] == 'development'
        fixture_map.append({'position_zero_based': position, 'id': row['id'],
            'input_fixture_id': row['id'] + '/input', 'target_fixture_id': row['id'] + '/target'})
    frozen = json.loads((WORK / 'data-v5-candidate/normalization-prepared.json').read_text())['frozen_files']

    def verify_sources():
        assert sha(DATA) == DATA_SHA and sha(FIXTURES) == FIXTURES_SHA
        for name, entry in frozen.items():
            path = PROBE / name
            assert path.stat().st_size == entry['bytes'] and sha(path) == entry['sha256'], name

    verify_sources()
    if OUT.exists():
        freeze = json.loads((OUT / 'pre-run-freeze.json').read_text())
        execution = json.loads((OUT / 'core-export-execution.json').read_text())
        assert freeze['source_dataset']['sha256'] == DATA_SHA and freeze['fixtures']['sha256'] == FIXTURES_SHA
        assert execution['returncode'] == 0 and not (OUT / 'manifest.json').exists()
        return finish_export(raw, verify_sources)
    OUT.mkdir()
    write_json(OUT / 'fixture-map.json', {'rows': fixture_map, 'source_dataset_sha256': DATA_SHA,
        'fixtures_sha256': FIXTURES_SHA, 'ordering': 'input then target for each source row'})
    argv = [str(ROOT / '.dotnet/dotnet'), str(PROBE / 'Freehand.Cleanup.Probe.dll'),
        '--export-prompts', '--input', str(FIXTURES), '--output', str(OUT / 'core-export.json'),
        '--prompt-style', 'ScribeKeyFast', '--mask-specialist-literals', 'true']
    write_json(OUT / 'pre-run-freeze.json', {'schema_version': 1,
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source_dataset': {'path': str(DATA), 'sha256': DATA_SHA},
        'fixtures': {'path': str(FIXTURES), 'sha256': FIXTURES_SHA},
        'frozen_probe_files': frozen, 'normalizer_source_sha256': sha(Path(__file__)),
        'argv': argv, 'nice': 19, 'DOTNET_PROCESSOR_COUNT': 1,
        'mode': 'Core export-prompts only; no model manifest, native worker, inference, or training',
        'reserved_core_export_authorized_by_root': True, 'active_training_data_not_opened': True})
    environment = dict(os.environ, DOTNET_PROCESSOR_COUNT='1')
    start = time.monotonic()
    with (OUT / 'core-export-console.log').open('x') as console:
        completed = subprocess.run(argv, cwd=ROOT, env=environment, preexec_fn=lambda: os.nice(19),
            stdout=console, stderr=subprocess.STDOUT, check=False)
    write_json(OUT / 'core-export-execution.json', {'argv': argv, 'returncode': completed.returncode,
        'seconds': time.monotonic() - start, 'nice': 19, 'DOTNET_PROCESSOR_COUNT': 1,
        'mode': 'no-inference Core preprocessing only'})
    assert completed.returncode == 0
    verify_sources()
    return finish_export(raw, verify_sources)


def finish_export(raw, verify_sources):
    exported = json.loads((OUT / 'core-export.json').read_text())
    cases = {case['fixture']['id']: case for case in exported['cases']}
    assert len(cases) == len(exported['cases']) == 480 and exported['prompt_style'] == 'ScribeKeyFast'
    pipeline_path = ROOT / 'tools/Freehand.Cleanup.Training/pipeline.py'
    pipeline_sha = sha(pipeline_path)
    spec = importlib.util.spec_from_file_location('reserved240_pipeline_validation', pipeline_path)
    pipeline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)
    rows, changes, transforms = [], [], []
    literal_count = 0
    pairs, by_input = collections.defaultdict(list), collections.defaultdict(list)
    hashes = []
    for position, original in enumerate(raw):
        source_case = cases[original['id'] + '/input']
        target_case = cases[original['id'] + '/target']
        source, target = source_case['normalized_input'], target_case['normalized_input']
        prompt, masked_target, mask = pipeline.protected_pair(source, target)
        assert source_case['completion']['text'] == prompt
        assert source_case['model_input_sha256'] == text_sha(mask.masked_text)
        assert mask.restore(masked_target) == target
        # Target fixture is independent Core preprocessing of the authored target.
        # Its token bytes must also equal the input-derived training target mask.
        assert target_case['completion']['text'] == pipeline.PREFIX + masked_target + pipeline.SUFFIX
        assert target_case['model_input_sha256'] == text_sha(masked_target)
        assert source_case['literal_mask_protocol'] == target_case['literal_mask_protocol'] == pipeline.PROTOCOL
        pair_sha = text_sha(source + '\x00' + target)
        result = {**original, 'input': source, 'target': target, 'needs_cleanup': source != target,
            'split': 'train', 'core_normalization': {'source_dataset_sha256': DATA_SHA,
            'export_sha256': sha(OUT / 'core-export.json'),
            'input_fixture_id': original['id'] + '/input', 'target_fixture_id': original['id'] + '/target',
            'prompt_sha256': text_sha(prompt), 'masked_input_sha256': text_sha(mask.masked_text),
            'masked_target_sha256': text_sha(masked_target), 'literal_protocol': pipeline.PROTOCOL,
            'source_prompt_and_mask_byte_agreement': True, 'target_prompt_and_mask_byte_agreement': True,
            'input_derived_target_literal_roundtrip': True}}
        rows.append(result)
        transform = {'position_zero_based': position, 'id': original['id'],
            'family': original['family'], 'original_input': original['input'], 'original_target': original['target'],
            'normalized_input': source, 'normalized_target': target,
            'input_changed': source != original['input'], 'target_changed': target != original['target'],
            'literal_count': len(mask.tokens), 'normalized_pair_sha256': pair_sha,
            'input_fixture_id': original['id'] + '/input', 'target_fixture_id': original['id'] + '/target',
            'complete_prompt_sha256': text_sha(prompt), 'masked_input_sha256': text_sha(mask.masked_text),
            'masked_target_sha256': text_sha(masked_target)}
        transforms.append(transform)
        if transform['input_changed'] or transform['target_changed']:
            changes.append(transform)
        literal_count += len(mask.tokens)
        pairs[pair_sha].append(original['id'])
        by_input[source].append({'id': original['id'], 'target': target})
        hashes.append({'id': original['id'], 'raw_input_sha256': opaque_hash(original['input']),
            'raw_target_sha256': opaque_hash(original['target']), 'normalized_input_sha256': opaque_hash(source),
            'normalized_target_sha256': opaque_hash(target)})
    destination = OUT / 'train-240-core-normalized-v1.jsonl'
    write_rows(destination, rows)
    loaded = pipeline.load_data(destination)
    assert len(loaded) == 240 and sha(pipeline_path) == pipeline_sha
    conflicts = [{'input': source, 'rows': entries} for source, entries in by_input.items()
        if len({entry['target'] for entry in entries}) > 1]
    duplicates = [ids for ids in pairs.values() if len(ids) > 1]
    write_json(OUT / 'normalization-changes.json', {'source_dataset_sha256': DATA_SHA,
        'normalized_dataset_sha256': sha(destination), 'changes': changes})
    with (OUT / 'normalization-changes-readable.md').open('x') as stream:
        stream.write('Core normalization changes for reserved240 training pairs\n\n')
        for change in changes:
            stream.write(change['id'] + '\n\n')
            for key in ('original_input', 'normalized_input', 'original_target', 'normalized_target'):
                stream.write(key + ': ' + json.dumps(change[key], ensure_ascii=False) + '\n\n')
    write_rows(OUT / 'row-transforms.jsonl', transforms)
    write_json(OUT / 'exact-pair-duplicates.json', {'duplicates': duplicates, 'rows_retained': 240,
        'selection': 'None; this export preserves every approved authored source row.'})
    write_json(OUT / 'same-input-different-target-conflicts.json', {'conflicts': conflicts})
    write_json(OUT / 'training-content-hashes.json', {'normalization': 'Unicode NFC, whitespace collapse and strip, casefold, UTF8 SHA256',
        'dataset_sha256': sha(destination), 'rows': hashes})
    manifest = {'schema_version': 1, 'status': 'RESERVED_NORMALIZED_CURRICULUM_NOT_ACTIVE_CONTROL_NOT_TRAINING_APPROVAL',
        'source_dataset_path': str(DATA), 'source_dataset_sha256': DATA_SHA,
        'normalized_dataset_path': str(destination), 'normalized_dataset_sha256': sha(destination),
        'rows': len(rows), 'unique_exact_pairs': len(pairs), 'effective_unweighted_rows': len(rows),
        'pair_duplicate_groups': len(duplicates), 'same_input_different_target_conflicts': len(conflicts),
        'cleanup_pairs': sum(row['needs_cleanup'] for row in rows),
        'unchanged_controls': sum(not row['needs_cleanup'] for row in rows),
        'family_counts': dict(collections.Counter(row['family'] for row in rows)),
        'changed_pairs': len(changes), 'input_changes': sum(c['input_changed'] for c in transforms),
        'target_changes': sum(c['target_changed'] for c in transforms),
        'core_fixtures': 480, 'source_prompt_and_mask_exact_agreements': 240,
        'target_prompt_and_mask_exact_agreements': 240, 'literal_target_roundtrips_exact': 240,
        'protected_spans_preserved': literal_count, 'pipeline_loader_rows_passed': len(loaded),
        'pipeline_source_sha256_used_for_validation': pipeline_sha,
        'literal_protocol': pipeline.PROTOCOL, 'normalizer_source_sha256': sha(Path(__file__)),
        'export_sha256': sha(OUT / 'core-export.json'),
        'opaque_hash_index_sha256': sha(OUT / 'training-content-hashes.json'),
        'authoring_scope': '240 individually authored independently-approved synthetic training pairs; no extra rows or augmentation added during normalization.',
        'source_semantics_approval': 'All240 raw pairs already independently approved: root families1/4, training_audit2/5, cleanup_pipeline_review3/6; normalization deltas require review separately.',
        'fresh_round2_overlap': 'Pending root opaque comparison; no fresh content opened here.',
        'source_files_preserved': True, 'frozen_probe_files_reverified_after': True,
        'model_native_or_training_runs': 0}
    write_json(OUT / 'manifest.json', manifest)
    verify_sources()
    print(json.dumps({key: manifest[key] for key in ('normalized_dataset_path', 'normalized_dataset_sha256',
        'rows', 'unique_exact_pairs', 'cleanup_pairs', 'unchanged_controls', 'changed_pairs',
        'pair_duplicate_groups', 'same_input_different_target_conflicts', 'opaque_hash_index_sha256')}), flush=True)


if __name__ == '__main__':
    main()
