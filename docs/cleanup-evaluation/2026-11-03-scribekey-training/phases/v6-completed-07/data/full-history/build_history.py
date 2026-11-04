#!/usr/bin/env python3
"""Prepare/finish an immutable union of approved training history, never a model run."""
from pathlib import Path
import argparse
import collections
import hashlib
import importlib.util
import json
import os
import time
import types

ROOT = Path('/workspace/freehand')
WORK = ROOT / 'work/cleanup-scribekey-training-2026-11-03'
OUT = Path(__file__).resolve().parent
SOURCES = [
    ('data-v3/combined-train-1364.jsonl', '502f7884a5b8be4db1a20a0154cfbc4b646168b4e1b812cddcad0fe6e7154b4d', 1364),
    ('audit/anaphora-curriculum/train-120-v3.jsonl', '6bd8efb9da8b3362d6275ea7389a049523c94f6d865dc551d4db4d1c33744472', 120),
    ('audit/development-repair-curriculum/train-90-v1.jsonl', '1f186a9dd5d796dbb4c61cd453f66669bfcb56ec09df6496ec020453167c981e', 90),
    ('audit/protected-correction-curriculum/train-20.jsonl', '4d92f682b278300a9d5d1974a830d9c84d5c5a7be50fef7768fb53ec1bf5e34e', 20),
    ('data-v5-candidate/new-420-core-normalized.jsonl', 'c63757913c476f98d8ce3d62b37d2a2ea0ed233c2ea6a1921971da9dc19804ec', 420),
]
MANAGED = ['Freehand.Cleanup.Probe.dll', 'Freehand.Core.dll', 'Freehand.Cleanup.dll',
           'Freehand.Dictionary.dll', 'Freehand.Testing.dll', 'Freehand.Abstractions.dll']

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()

def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n')

def write_rows(path, rows):
    with path.open('x', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')

def provenance(source_index, row):
    if source_index in (1, 2, 4):
        return 'individually_authored_pair'
    if source_index == 3:
        return 'controlled_template_instantiation'
    family = row['family'];group = row.get('group_id', '')
    declaration = row.get('source', row.get('provenance', '')).casefold()
    if declaration.startswith('controlled concatenation'):
        return 'controlled_composition'
    if declaration.startswith('controlled leading'):
        return 'controlled_prefix_augmentation'
    if declaration.startswith('individually assistant'):
        return 'individually_authored_pair'
    if row['id'].startswith('scribekey-hard-synthetic-v2'):
        return ('controlled_derived_identity_or_filler' if family.endswith(('_with_filler', '_clean_target'))
                else 'individually_authored_pair')
    if group.startswith('authored-contrast-'):
        return 'controlled_prefix_augmentation' if family.endswith('_with_filler') else 'individually_authored_pair'
    if group.startswith('authored-content-'):
        return 'authored_text_identity_control' if family == 'clean_copy' else 'controlled_surface_corruption'
    if family in ('clean_multi_sentence', 'multi_sentence_fillers'):
        return 'controlled_composition'
    if family in ('explicit_recipient_correction', 'explicit_numeric_correction', 'clean_conditional_action',
                  'clean_numeric_instruction', 'explicit_action_backtrack', 'clean_recipient_instruction',
                  'quoted_literal_preservation', 'dictionary_literal_preservation'):
        return 'controlled_template_instantiation'
    raise ValueError('Unclassified original provenance: ' + row['id'])

def verify_sources():
    for relative, expected, count in SOURCES:
        path = WORK / relative
        assert sha(path) == expected, relative
        assert len(path.read_bytes().splitlines()) == count, relative

def verify_probe(prepared):
    for name, entry in prepared['frozen_probe_files'].items():
        path = WORK / 'data-v5-candidate/frozen-probe' / name
        assert sha(path) == entry['sha256'] and path.stat().st_size == entry['bytes'], name

def prepare():
    assert not (OUT / 'prepared.json').exists(), 'Preserve existing preparation'
    verify_sources()
    prior = json.loads((WORK / 'data-v5-candidate/normalization-prepared.json').read_text())
    records = [];fixtures = []
    for index, (relative, expected, count) in enumerate(SOURCES):
        rows = [json.loads(line) for line in (WORK / relative).read_text().splitlines()]
        for ordinal, row in enumerate(rows):
            assert row.get('split', 'train') == 'train'
            framed = '[[FREEHAND_LITERAL_' in row['input'] or '[[FREEHAND_LITERAL_' in row['target']
            mode = 'already_core_normalized_retained' if index == 4 else ('legacy_framed_retained' if framed else 'new_real_core_export')
            record_id = f'v6-source-{index:02d}-{ordinal:04d}'
            record = {'record_id': record_id, 'source_index': index, 'source_line_zero_based': ordinal,
                      'source_path': relative, 'source_file_sha256': expected, 'normalization_mode': mode,
                      'provenance_class': provenance(index, row), 'original_row': row}
            records.append(record)
            if mode == 'new_real_core_export':
                fixtures.append({'id': record_id, 'input': row['input'], 'targets': [row['target']],
                                 'split': 'development', 'references_are_normalized': False})
    assert len(records) == 2014 and len(fixtures) == 1537
    write_rows(OUT / 'source-records.jsonl', records)
    fixture_path = OUT / 'older-unframed-core-fixtures.json'
    write_json(fixture_path, {'schema_version': 1, 'purpose': 'Approved TRAINING text preprocessing only; no inference or evaluation', 'cases': fixtures})
    argv = [str(ROOT / '.dotnet/dotnet'), str(WORK / 'data-v5-candidate/frozen-probe/Freehand.Cleanup.Probe.dll'),
            '--export-prompts', '--input', str(fixture_path), '--output', str(OUT / 'older-unframed-core-export.json'),
            '--prompt-style', 'ScribeKeyFast', '--mask-specialist-literals', 'true']
    prepared = {'schema_version': 1, 'status': 'prepared_NO_MODEL_OR_TRAINING', 'argv': argv,
                'source_files': [{'path': relative, 'sha256': expected, 'rows': count} for relative, expected, count in SOURCES],
                'source_occurrences': len(records), 'new_core_export_rows': len(fixtures),
                'legacy_framed_rows_retained': sum(r['normalization_mode'] == 'legacy_framed_retained' for r in records),
                'already_core_normalized_rows_retained': 420, 'frozen_probe_files': prior['frozen_files'],
                'source_records_sha256': sha(OUT / 'source-records.jsonl'), 'fixture_sha256': sha(fixture_path),
                'provenance_occurrence_counts': dict(collections.Counter(r['provenance_class'] for r in records)),
                'builder_source_sha256': sha(Path(__file__)), 'blind_data_read': False}
    verify_probe(prepared)
    write_json(OUT / 'prepared.json', prepared)
    print(json.dumps({key: prepared[key] for key in ['source_occurrences', 'new_core_export_rows', 'legacy_framed_rows_retained', 'already_core_normalized_rows_retained', 'provenance_occurrence_counts']}, indent=2))

def finish():
    assert not (OUT / 'manifest.json').exists(), 'Preserve completed candidates'
    prepared = json.loads((OUT / 'prepared.json').read_text())
    verify_sources();verify_probe(prepared)
    assert sha(OUT / 'source-records.jsonl') == prepared['source_records_sha256']
    records = [json.loads(line) for line in (OUT / 'source-records.jsonl').read_text().splitlines()]
    export_path = OUT / 'older-unframed-core-export.json'
    exported = json.loads(export_path.read_text())
    assert exported['prompt_style'] == 'ScribeKeyFast' and len(exported['cases']) == 1537
    for name in MANAGED:
        assert exported['managed_assembly_sha256'][name].lower() == prepared['frozen_probe_files'][name]['sha256']
    new_cases = {case['fixture']['id']: case for case in exported['cases']}
    prior_export_path = WORK / 'data-v5-candidate/new-420-core-export.json'
    prior_export_sha = sha(prior_export_path)
    prior_export = json.loads(prior_export_path.read_text())
    prior_cases = {case['fixture']['id']: case for case in prior_export['cases']}
    assert len(new_cases) == 1537 and len(prior_cases) == 420
    snapshots = OUT / 'source-snapshots';snapshots.mkdir()
    pipeline_path = ROOT / 'tools/Freehand.Cleanup.Training/pipeline.py'
    pipeline_bytes = pipeline_path.read_bytes()
    (snapshots / 'pipeline-used.py').write_bytes(pipeline_bytes)
    # Execute exactly these saved bytes with the real source path so imports and
    # REPO resolution stay correct even if a concurrent training-proof edit occurs.
    pipeline = types.ModuleType('history_pipeline_snapshot');pipeline.__file__ = str(pipeline_path)
    exec(compile(pipeline_bytes, str(pipeline_path), 'exec'), pipeline.__dict__)
    helper_hashes = {}
    for name in ['specialist_literal_protection.py', 'literal_protection.py']:
        path = ROOT / 'tools/Freehand.Cleanup.Evaluation' / name
        raw = path.read_bytes();(snapshots / name).write_bytes(raw);helper_hashes[str(path)] = hashlib.sha256(raw).hexdigest()
    grouped = {};transforms = [];agreement = collections.Counter()
    for record in records:
        row = record['original_row'];mode = record['normalization_mode'];case = None
        source, target = row['input'], row['target']
        if mode == 'new_real_core_export':
            case = new_cases[record['record_id']]
            assert len(case['normalized_targets']) == 1
            source, target = case['normalized_input'], case['normalized_targets'][0]
        elif mode == 'already_core_normalized_retained':
            assert row['core_normalization']['export_sha256'] == prior_export_sha
            case = prior_cases[row['core_normalization']['export_fixture_id']]
            assert [source, target] == [case['normalized_input'], case['normalized_targets'][0]]
        prompt, masked_target, mask = pipeline.protected_pair(source, target)
        assert mask.restore(masked_target) == target
        prompt_sha = text_sha(prompt);model_input_sha = text_sha(mask.masked_text)
        if case is not None:
            assert case['model_input_sha256'] == model_input_sha, record['record_id']
            assert case['completion']['text'] == prompt, record['record_id']
            assert case['literal_mask_protocol'] == pipeline.PROTOCOL
            proof = 'real_Core_export_prompt_and_model_input_hash_exact'
        else:
            proof = 'legacy_framed_retained_verbatim_Python_literal_roundtrip_only_no_new_Core_export'
        agreement[proof] += 1
        pair_sha = text_sha(source + '\x00' + target)
        transform = {'record_id': record['record_id'], 'source_path': record['source_path'],
                     'source_line_zero_based': record['source_line_zero_based'], 'original_id': row['id'],
                     'family': row['family'], 'provenance_class': record['provenance_class'],
                     'normalization_mode': mode, 'raw_input': row['input'], 'raw_target': row['target'],
                     'input': source, 'target': target, 'input_changed': source != row['input'],
                     'target_changed': target != row['target'], 'normalized_pair_sha256': pair_sha,
                     'model_input_sha256': model_input_sha, 'complete_prompt_sha256': prompt_sha,
                     'prompt_mask_agreement': proof, 'literal_roundtrip_exact': True, 'protected_spans': len(mask.tokens)}
        transforms.append(transform)
        key = (source, target)
        origin = {'source_path': record['source_path'], 'source_file_sha256': record['source_file_sha256'],
                  'source_line_zero_based': record['source_line_zero_based'], 'original_id': row['id'],
                  'family': row['family'], 'provenance_class': record['provenance_class'],
                  'normalization_mode': mode, 'transform_record_id': record['record_id']}
        if key not in grouped:
            grouped[key] = {'id': 'full-history-v6-' + pair_sha[:24], 'input': source, 'target': target,
                            'family': row['family'], 'split': 'train', 'needs_cleanup': source != target,
                            'source_occurrences': [origin], 'normalized_pair_sha256': pair_sha}
        else:
            grouped[key]['source_occurrences'].append(origin)
    unique = list(grouped.values())
    assert len({row['id'] for row in unique}) == len(unique)
    targets_by_input = collections.defaultdict(list)
    for row in unique:
        classes = sorted({origin['provenance_class'] for origin in row['source_occurrences']})
        row['provenance_classes'] = classes
        row['provenance_class'] = classes[0] if len(classes) == 1 else 'mixed_exact_pair_origins'
        row['families'] = sorted({origin['family'] for origin in row['source_occurrences']})
        targets_by_input[row['input']].append(row)
    conflicts = [{'input_sha256': text_sha(source), 'input': source,
                  'variants': [{'id': row['id'], 'target': row['target'], 'origins': row['source_occurrences']} for row in variants]}
                 for source, variants in targets_by_input.items() if len(variants) > 1]
    conflict_ids = {variant['id'] for conflict in conflicts for variant in conflict['variants']}
    for row in unique:
        row['semantic_conflict_requires_review'] = row['id'] in conflict_ids
    write_rows(OUT / 'row-transforms.jsonl', transforms)
    write_json(OUT / 'same-input-different-target-conflicts.json', {'conflicting_inputs': len(conflicts), 'conflicts': conflicts,
               'policy': 'No target was automatically selected; all exact-pair variants remain in the full candidate, which is blocked pending semantic review if any conflict exists.'})
    candidate = OUT / 'full-history-candidate.jsonl'
    write_rows(candidate, unique)
    loaded = pipeline.load_data(candidate)
    assert len(loaded) == len(unique)
    for path, expected in helper_hashes.items():
        assert sha(Path(path)) == expected, 'Literal helper changed during preparation'
    verify_sources();verify_probe(prepared)
    duplicate_origins = [{'pair_id': row['id'], 'occurrences': row['source_occurrences']} for row in unique if len(row['source_occurrences']) > 1]
    write_json(OUT / 'exact-pair-deduplication.json', {'source_occurrences': 2014, 'unique_pairs': len(unique),
               'removed_duplicate_occurrences': 2014 - len(unique), 'duplicates': duplicate_origins,
               'equality': 'Exact input/target UTF-8 strings after the recorded Core alignment; no case/whitespace/semantic collapsing.'})
    manifest = {'schema_version': 1, 'status': 'prepared_dataset_NOT_TRAINING_APPROVAL',
                'candidate_path': str(candidate), 'candidate_sha256': sha(candidate),
                'source_files': prepared['source_files'], 'source_occurrences_before_deduplication': 2014,
                'unique_input_target_pairs': len(unique), 'effective_rows_one_unweighted_pass': len(unique),
                'additional_oversampling': False, 'duplicate_occurrences_removed': 2014-len(unique),
                'unique_input_count': len(targets_by_input), 'conflicting_input_count': len(conflicts),
                'semantic_conflict_variant_rows': len(conflict_ids), 'all_conflicts_retained_unresolved': True,
                'blocked_on_conflict_review': bool(conflicts),
                'unchanged_unique_rows': sum(row['input'] == row['target'] for row in unique),
                'unchanged_fraction': sum(row['input'] == row['target'] for row in unique)/len(unique),
                'family_counts_unique_rows_canonical_oldest_origin': dict(collections.Counter(row['family'] for row in unique)),
                'family_membership_counts_all_origins': dict(collections.Counter(origin['family'] for row in unique for origin in row['source_occurrences'])),
                'provenance_counts_source_occurrences': prepared['provenance_occurrence_counts'],
                'provenance_counts_unique_rows': dict(collections.Counter(row['provenance_class'] for row in unique)),
                'provenance_policy': 'Authored-pair versus authored-text identity control versus controlled prefix/surface/template/composition is derived from preserved source metadata and original generator/group rules. Synthetic correlated rows are not independent human observations.',
                'normalization': {'new_export_rows': 1537, 'prior_normalized_retained': 420, 'legacy_framed_verbatim_retained': 57,
                    'raw_input_changes': sum(t['input_changed'] for t in transforms),
                    'raw_target_changes': sum(t['target_changed'] for t in transforms),
                    'exact_prompt_mask_agreement_counts': dict(agreement),
                    'all_2014_literal_roundtrips_exact': True, 'loader_unique_rows': len(loaded),
                    'frozen_probe_files': prepared['frozen_probe_files'], 'new_export_sha256': sha(export_path),
                    'prior420_export_sha256': prior_export_sha,
                    'legacy_limitation': 'Already Core-framed rows were deliberately not sent through Core again. Their bytes and exact literal roundtrips are retained; a new C# prompt-equivalence claim is not made for those57rows.'},
                'exact_row_transforms_sha256': sha(OUT / 'row-transforms.jsonl'),
                'preserved_source_files_verified_after': True,
                'pipeline_snapshot_sha256': hashlib.sha256(pipeline_bytes).hexdigest(), 'literal_helper_source_hashes': helper_hashes,
                'builder_source_sha256': sha(Path(__file__)), 'new_authored_rows': 0,
                'retired500_training_rows_added': 0, 'blind_round2_read_or_listed': False,
                'model_native_or_training_jobs_run': False,
                'next_steps': 'Controller semantic-review any conflicts, then perform final opaque overlap audit and explicit training approval. This manifest authorizes no model training.'}
    write_json(OUT / 'manifest.json', manifest)
    print(json.dumps({key: manifest[key] for key in ['candidate_path','candidate_sha256','source_occurrences_before_deduplication','unique_input_target_pairs','effective_rows_one_unweighted_pass','duplicate_occurrences_removed','conflicting_input_count','unchanged_unique_rows','provenance_counts_unique_rows']}, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('phase', choices=['prepare','finish']);args = parser.parse_args()
    prepare() if args.phase == 'prepare' else finish()
