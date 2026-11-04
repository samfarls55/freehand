#!/usr/bin/env python3
"""Prepare disclosed oversampling; no model/Torch import and no final data freeze."""
from pathlib import Path
import collections
import hashlib
import importlib.metadata
import importlib.util
import json
import sys
import unicodedata

ROOT = Path('/workspace/freehand')
WORK = ROOT / 'work/cleanup-scribekey-training-2026-11-03'
OUT = WORK / 'audit/v7-positive-curriculum'
SOURCES = [
    ('history2014', WORK / 'audit/v6-full-history-curriculum/full-history-candidate.jsonl',
     '919b5b5ecfe2878edf7075b800a7d39392fe5be215d23d1fb8cbd984c78a4015', 2014, 1),
    ('contrasts270', WORK / 'audit/v6-future-contrasts/core-normalization-v1/train-270-core-normalized-v1.jsonl',
     '39facec9907b15c7ea82319728c22701182a70769017dba6124324532fb05f12', 270, 2),
]
TOKENIZER = ROOT / 'work/cleanup-small-models-2026-11-03/scribe-precision-source/original-model/tokenizer.json'
TOKENIZER_SHA = 'df1d8d5ec5d091b460562ffd545e4a5e91d17d4a0db7ebe733be34ed374377bd'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def opaque_hash(value):
    return text_sha(' '.join(unicodedata.normalize('NFC', value).split()).strip().casefold())


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def main():
    assert 'torch' not in sys.modules
    from tokenizers import Tokenizer
    assert sha(TOKENIZER) == TOKENIZER_SHA
    tokenizer = Tokenizer.from_file(str(TOKENIZER))
    assert tokenizer.token_to_id('<|startoftext|>') == 1
    assert tokenizer.token_to_id('<|im_end|>') == 7
    assert tokenizer.token_to_id('<|pad|>') == 0
    pipeline_path = ROOT / 'tools/Freehand.Cleanup.Training/pipeline.py'
    pipeline_sha = sha(pipeline_path)
    spec = importlib.util.spec_from_file_location('positive_corpus_literal_validation', pipeline_path)
    pipeline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)
    assert 'torch' not in sys.modules
    OUT.mkdir(exist_ok=True)
    destination = OUT / 'positive-2554-provisional.jsonl'
    rows, bindings, token_checks = [], [], []
    unique_pairs = collections.defaultdict(list)
    input_targets = collections.defaultdict(set)
    counts_by_source, unchanged_by_source = collections.Counter(), collections.Counter()
    family_effective, family_unique = collections.Counter(), collections.Counter()
    provenance_effective, provenance_unique = collections.Counter(), collections.Counter()
    legacy_unique, protected_count = 0, 0
    hashes = []
    for source_name, path, expected_sha, expected_count, copies in SOURCES:
        assert sha(path) == expected_sha
        originals = [json.loads(line) for line in path.read_text().splitlines()]
        assert len(originals) == expected_count and len({r['id'] for r in originals}) == expected_count
        for copy in range(1, copies + 1):
            for position, original in enumerate(originals):
                pair = original['input'], original['target']
                legacy = any('[[FREEHAND_LITERAL_' in value for value in pair)
                new_id = f'positive-v7-{source_name}-{position:04d}-copy{copy}'
                provenance = {'source_name': source_name, 'source_path': str(path),
                    'source_file_sha256': expected_sha, 'source_position_zero_based': position,
                    'source_id': original['id'], 'copy_one_based': copy,
                    'total_exposures_for_source_row': copies,
                    'is_disclosed_oversampling_copy': copy > 1,
                    'input_target_bytes_unchanged': True}
                result = {**original, 'id': new_id, 'positive_replay_instance': provenance}
                assert (result['input'], result['target']) == pair
                assert all(result[k] == v for k, v in original.items() if k != 'id')
                prompt, masked_target, mask = pipeline.protected_pair(*pair)
                assert mask.restore(masked_target) == original['target']
                prompt_ids = tokenizer.encode(prompt, add_special_tokens=False).ids
                target_ids = tokenizer.encode(masked_target, add_special_tokens=False).ids + [7]
                assert prompt_ids[0] == 1 and prompt_ids.count(1) == 1
                assert len(prompt_ids) + len(target_ids) <= 1024
                assert original.get('split', 'train') == 'train'
                rows.append(result)
                binding = {**provenance, 'id': new_id, 'pair_sha256': text_sha(pair[0] + '\x00' + pair[1]),
                    'legacy_framed_row_preserved': legacy}
                bindings.append(binding)
                token_checks.append({'id': new_id, 'prompt_tokens': len(prompt_ids),
                    'assistant_tokens_including_eos': len(target_ids),
                    'total_tokens': len(prompt_ids) + len(target_ids),
                    'complete_prompt_sha256': text_sha(prompt), 'masked_target_sha256': text_sha(masked_target),
                    'literal_count': len(mask.tokens), 'input_derived_literal_roundtrip_exact': True,
                    'leading_bos1_exactly_once': True, 'assistant_eos7_appended': True,
                    'truncated': False})
                first_pair = pair not in unique_pairs
                unique_pairs[pair].append(new_id)
                input_targets[pair[0]].add(pair[1])
                counts_by_source[source_name] += 1
                unchanged_by_source[source_name] += pair[0] == pair[1]
                family_effective[original['family']] += 1
                provenance_class = original.get('provenance_class', 'individually_authored_controlled_contrast')
                provenance_effective[provenance_class] += 1
                protected_count += len(mask.tokens)
                if first_pair:
                    family_unique[original['family']] += 1
                    provenance_unique[provenance_class] += 1
                    legacy_unique += legacy
                    hashes.append({'source_id': original['id'], 'source_name': source_name,
                        'normalized_input_sha256': opaque_hash(pair[0]),
                        'normalized_target_sha256': opaque_hash(pair[1])})
    assert len(rows) == 2554 and len(unique_pairs) == 2284 and legacy_unique == 57
    assert len({row['id'] for row in rows}) == len(rows)
    conflicts = [{'input': source, 'targets': sorted(targets)} for source, targets in input_targets.items()
        if len(targets) > 1]
    assert not conflicts
    with destination.open('x', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    assert len(pipeline.load_data(destination)) == 2554
    with (OUT / 'positive-2554-provenance.jsonl').open('x') as stream:
        for row in bindings:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    with (OUT / 'positive-2554-token-checks.jsonl').open('x') as stream:
        for row in token_checks:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    duplicate_groups = [{'pair_sha256': text_sha(pair[0] + '\x00' + pair[1]), 'instance_ids': ids}
        for pair, ids in unique_pairs.items() if len(ids) > 1]
    assert len(duplicate_groups) == 270 and all(len(d['instance_ids']) == 2 for d in duplicate_groups)
    write_json(OUT / 'positive-2554-disclosed-duplicates.json', {'groups': duplicate_groups,
        'reason': 'Exactly two intended exposures for each approved270 contrast row; not additional unique examples.'})
    write_json(OUT / 'positive-2554-input-target-conflicts.json', {'conflicts': conflicts})
    write_json(OUT / 'positive-2554-content-hashes.json', {'dataset_sha256': sha(destination),
        'normalization': 'Unicode NFC, whitespace collapse and strip, casefold, UTF8 SHA256',
        'unique_pairs': 2284, 'rows': hashes})
    manifest = {'schema_version': 1,
        'status': 'PROVISIONAL_PREPARATION_ONLY_NOT_FINAL_FROZEN_DATA_NOT_TRAINING_APPROVAL',
        'dataset_path': str(destination), 'dataset_sha256': sha(destination),
        'builder_path': str(Path(__file__)), 'builder_sha256': sha(Path(__file__)),
        'source_files': [{'name': n, 'path': str(p), 'sha256': h, 'unique_source_rows': count, 'exposures': copies}
            for n, p, h, count, copies in SOURCES],
        'effective_rows': len(rows), 'unique_exact_pairs': len(unique_pairs),
        'disclosed_oversampling_added_rows': 270, 'disclosed_duplicate_groups': len(duplicate_groups),
        'same_input_different_target_conflicts': len(conflicts), 'unique_instance_ids': len(rows),
        'effective_rows_by_source': dict(counts_by_source),
        'unchanged_effective_rows_by_source': dict(unchanged_by_source),
        'unchanged_effective_rows': sum(unchanged_by_source.values()),
        'unchanged_unique_pairs': sum(source == target for source, target in unique_pairs),
        'family_effective_counts': dict(family_effective), 'family_unique_counts': dict(family_unique),
        'provenance_effective_counts': dict(provenance_effective), 'provenance_unique_counts': dict(provenance_unique),
        'all_original_row_fields_preserved_except_instance_id': True,
        'input_target_bytes_unchanged': True, 'legacy57_unique_rows_preserved_once': legacy_unique,
        'literal_roundtrips_passed': len(rows), 'protected_spans_effective': protected_count,
        'tokenizer': {'path': str(TOKENIZER), 'sha256': TOKENIZER_SHA,
            'tokenizers_version': importlib.metadata.version('tokenizers'),
            'max_total_tokens': max(r['total_tokens'] for r in token_checks),
            'token_cap': 1024, 'whole_examples_truncated': 0,
            'leading_bos1_exactly_once_all_rows': True, 'assistant_eos7_appended_all_rows': True},
        'pipeline_loader_rows_passed': len(rows), 'pipeline_source_sha256_used': pipeline_sha,
        'literal_protocol': pipeline.PROTOCOL,
        'positive_file_eta0_eta1_requirement': 'Use the same exact final positive file bytes for both later conditions; this provisional2554 file is not final until pending100 are approved/normalized and appended with disclosed exposures.',
        'pending_additional_unique_examples': 100, 'pending_additional_exposures_each': 2,
        'expected_final_effective_rows_if_no_overlap': 2754,
        'expected_final_unique_pairs_if_no_overlap': 2384,
        'no_torch_imported': 'torch' not in sys.modules,
        'no_model_or_inference_or_training_run': True,
        'fresh_round2_content_accessed': False,
        'controller_opaque_final_overlap': 'Deferred to root after final100 approval/normalization; no fresh set opened here.'}
    assert manifest['no_torch_imported'] and sha(pipeline_path) == pipeline_sha
    for _, p, h, _, _ in SOURCES:
        assert sha(p) == h
    write_json(OUT / 'positive-2554-provisional-manifest.json', manifest)
    print(json.dumps({k: manifest[k] for k in ('dataset_path', 'dataset_sha256', 'effective_rows',
        'unique_exact_pairs', 'unchanged_effective_rows', 'unchanged_unique_pairs',
        'legacy57_unique_rows_preserved_once', 'no_torch_imported', 'tokenizer')}))


if __name__ == '__main__':
    main()
