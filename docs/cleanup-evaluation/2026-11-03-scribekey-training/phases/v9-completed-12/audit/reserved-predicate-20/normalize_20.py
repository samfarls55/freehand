#!/usr/bin/env python3
"""One immutable no-model40-case Core export for independently approved reserved20."""
from pathlib import Path
import collections
import datetime
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import unicodedata

ROOT = Path('/workspace/freehand')
HERE = Path(__file__).resolve().parent
OUT = HERE / 'core-normalization-v1'
PROBE = OUT / 'frozen-probe'
SOURCE_PROBE = HERE.parent / 'v9-reserved-curriculum/core-normalization-v1/frozen-probe'
SOURCE_PROBE_SHA = '6de0ab21b514990a2834c8af48636feda695c78b616267f70ab602a2e1324a66'
QUALIFICATION = HERE.parent / 'v9-reserved-curriculum/core-normalization-v1/pre-run-freeze.json'
QUALIFICATION_SHA = '349de923faae860367df51241f37cf90671c4e0f9e69b68a2f63f67e5fb2879b'
PIPELINE_SHA = '8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad'
DATA = HERE / 'train-20-v1.jsonl'
DATA_SHA = '112939ee9c522fca720652c489138d5cda24eeccec2c7b1ca8bd6028cc9f88bc'
FIXTURES = HERE / 'core-normalization-input-target-40.json'
FIXTURES_SHA = '6c7d55d562ce6027b75a6d57764d0174297805b0f752760a67545fd9b10468bd'
PROBE_NAMES = ['Freehand.Cleanup.Probe.dll', 'Freehand.Core.dll', 'Freehand.Cleanup.dll',
    'Freehand.Dictionary.dll', 'Freehand.Testing.dll', 'Freehand.Abstractions.dll',
    'Freehand.Cleanup.Probe.runtimeconfig.json', 'Freehand.Cleanup.Probe.deps.json']


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
    release_path = HERE / 'cpu-window-release.json'
    release = json.loads(release_path.read_text())
    assert release['released'] is True and release['source_agent'] == '/root/benchmark_assets'
    assert 'torch' not in sys.modules and not OUT.exists()
    assert sha(DATA) == DATA_SHA and sha(FIXTURES) == FIXTURES_SHA
    assert sha(QUALIFICATION) == QUALIFICATION_SHA
    assert sha(SOURCE_PROBE / 'Freehand.Cleanup.Probe.dll') == SOURCE_PROBE_SHA
    raw = [json.loads(line) for line in DATA.read_text().splitlines()]
    fixtures = json.loads(FIXTURES.read_text())
    assert len(raw) == 20 and len(fixtures['cases']) == 40
    assert fixtures['source_dataset_sha256'] == DATA_SHA
    fixture_map = []
    for position, row in enumerate(raw):
        for offset, side in enumerate(('input', 'target')):
            case = fixtures['cases'][position * 2 + offset]
            assert case['id'] == row['id'] + '/' + side
            assert case['input'] == row[side] and case['split'] == 'development'
        fixture_map.append({'position_zero_based': position, 'id': row['id'],
            'input_fixture_id': row['id'] + '/input', 'target_fixture_id': row['id'] + '/target'})
    OUT.mkdir()
    PROBE.mkdir()
    frozen = {}
    for name in PROBE_NAMES:
        source = SOURCE_PROBE / name
        entry = {'source_path': str(source), 'bytes': source.stat().st_size, 'sha256': sha(source)}
        shutil.copy2(source, PROBE / name)
        assert sha(PROBE / name) == entry['sha256']
        frozen[name] = entry

    def verify_sources():
        assert sha(DATA) == DATA_SHA and sha(FIXTURES) == FIXTURES_SHA
        assert sha(QUALIFICATION) == QUALIFICATION_SHA
        for name, entry in frozen.items():
            for path in (SOURCE_PROBE / name, PROBE / name):
                assert path.stat().st_size == entry['bytes'] and sha(path) == entry['sha256'], str(path)
        assert sha(ROOT / 'tools/Freehand.Cleanup.Training/pipeline.py') == PIPELINE_SHA
        assert 'torch' not in sys.modules

    verify_sources()
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
        'qualification_summary': {'path': str(QUALIFICATION), 'sha256': QUALIFICATION_SHA},
        'source_body_commit_reported_by_root': '8b; build summary historical f84; existing outputs only, no rebuild.',
        'argv': argv, 'nice': 19, 'DOTNET_PROCESSOR_COUNT': 1,
        'mode': 'Core export-prompts only; no model manifest, native worker, inference, training or build',
        'root_grant': 'Root approved all20; actual Core granted only after benchmark_assets explicit CPU release.',
        'cpu_release_receipt': {'path': str(release_path), 'sha256': sha(release_path)},
        'upstream_probe_qualification_sha256': 'd720b68c9004283061a73bc90844c391f788ff693589be753ab2b0e02b2187a6'})
    environment = dict(os.environ, DOTNET_PROCESSOR_COUNT='1')
    start = time.monotonic()
    with (OUT / 'core-export-console.log').open('x') as console:
        completed = subprocess.run(argv, cwd=ROOT, env=environment, preexec_fn=lambda: os.nice(19),
            stdout=console, stderr=subprocess.STDOUT, check=False)
    write_json(OUT / 'core-export-execution.json', {'argv': argv, 'returncode': completed.returncode,
        'seconds': time.monotonic() - start, 'nice': 19, 'DOTNET_PROCESSOR_COUNT': 1,
        'mode': 'no-inference Core preprocessing only; saved managed binaries, no build'})
    assert completed.returncode == 0
    verify_sources()
    return finish_export(raw, verify_sources)


def finish_export(raw, verify_sources):
    exported = json.loads((OUT / 'core-export.json').read_text())
    cases = {case['fixture']['id']: case for case in exported['cases']}
    assert len(cases) == len(exported['cases']) == 40 and exported['prompt_style'] == 'ScribeKeyFast'
    pipeline_path = ROOT / 'tools/Freehand.Cleanup.Training/pipeline.py'
    pipeline_sha = sha(pipeline_path)
    assert pipeline_sha == PIPELINE_SHA
    spec = importlib.util.spec_from_file_location('reserved20_pipeline_validation', pipeline_path)
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
    destination = OUT / 'train-20-core-normalized-v1.jsonl'
    write_rows(destination, rows)
    loaded = pipeline.load_data(destination)
    assert len(loaded) == 20 and sha(pipeline_path) == pipeline_sha
    conflicts = [{'input': source, 'rows': entries} for source, entries in by_input.items()
        if len({entry['target'] for entry in entries}) > 1]
    duplicates = [ids for ids in pairs.values() if len(ids) > 1]
    write_json(OUT / 'normalization-changes.json', {'source_dataset_sha256': DATA_SHA,
        'normalized_dataset_sha256': sha(destination), 'changes': changes})
    with (OUT / 'normalization-changes-readable.md').open('x') as stream:
        stream.write('Core normalization changes for reserved20 training pairs\n\n')
        for change in changes:
            stream.write(change['id'] + '\n\n')
            for key in ('original_input', 'normalized_input', 'original_target', 'normalized_target'):
                stream.write(key + ': ' + json.dumps(change[key], ensure_ascii=False) + '\n\n')
    write_rows(OUT / 'row-transforms.jsonl', transforms)
    write_json(OUT / 'exact-pair-duplicates.json', {'duplicates': duplicates, 'rows_retained': 20,
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
        'core_fixtures': 40, 'source_prompt_and_mask_exact_agreements': 20,
        'target_prompt_and_mask_exact_agreements': 20, 'literal_target_roundtrips_exact': 20,
        'protected_spans_preserved': literal_count, 'pipeline_loader_rows_passed': len(loaded),
        'pipeline_source_sha256_used_for_validation': pipeline_sha,
        'literal_protocol': pipeline.PROTOCOL, 'normalizer_source_sha256': sha(Path(__file__)),
        'export_sha256': sha(OUT / 'core-export.json'),
        'opaque_hash_index_sha256': sha(OUT / 'training-content-hashes.json'),
        'authoring_scope': '20 individually authored independently-approved synthetic training pairs; no extra rows or augmentation added during normalization.',
        'source_semantics_approval': 'All20 raw pairs each independently approved by root and training_audit; normalization deltas require review separately.',
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
