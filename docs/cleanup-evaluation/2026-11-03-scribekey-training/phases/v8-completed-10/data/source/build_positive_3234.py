#!/usr/bin/env python3
"""Prepare only: preserve exact2754 bytes and append the approved normalized240 twice."""
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
OUT = WORK / 'audit/v8-positive-curriculum'
OLD = WORK / 'audit/v7-positive-curriculum'
PREFIX = OLD / 'positive-2754-final.jsonl'
PREFIX_SHA = 'fa18dfcd5faf4c5a7a20f8e9b669caaa2ec3c8e098b27b17a25128eda1d592a6'
EXTRA = WORK / 'audit/v8-reserved-curriculum/core-normalization-v1/train-240-core-normalized-v1.jsonl'
EXTRA_SHA = '0dfc50fe433bda477666fcad5a91bb3a4356e1ded50543c6ff818db9a4e645dc'
PIPELINE = ROOT / 'tools/Freehand.Cleanup.Training/pipeline.py'
PIPELINE_SHA = '8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad'
TOKENIZER = ROOT / 'work/cleanup-small-models-2026-11-03/scribe-precision-source/original-model/tokenizer.json'
TOKENIZER_SHA = 'df1d8d5ec5d091b460562ffd545e4a5e91d17d4a0db7ebe733be34ed374377bd'
CORE = EXTRA.parent / 'core-export.json'
CORE_SHA = '33591c19195329e9d0f1fb5ffae7ecbb6e8ba9580e86d185e637ea9c9199462b'
RAW_REVIEW = EXTRA.parent.parent / 'independent-review-rollup-v1.json'
RAW_REVIEW_SHA = 'db384700ad69d0993708b876c1abcf77def989305de561966e5260a54bacfdaf'
CORE_REVIEW = EXTRA.parent / 'normalization-cleanup-pipeline-independent-review.json'
CORE_REVIEW_SHA = '2fe246c2f909141a086f78ab5a134e0391db79b1f624bf81b0b6564b65061165'
FINAL_REVIEW = EXTRA.parent.parent / 'normalization-final-approval-v1.json'
FINAL_REVIEW_SHA = '14b533f80bbf5cb883d494f2e9aff6b54b6bcd1972b29238ae588ff900a086bc'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def th(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def opaque(value):
    return th(' '.join(unicodedata.normalize('NFC', value).split()).strip().casefold())


def write_json(name, value):
    with (OUT / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def write_rows(name, rows):
    with (OUT / name).open('x', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def ref(path):
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def main():
    assert 'torch' not in sys.modules
    from tokenizers import Tokenizer
    fixed = {PREFIX: PREFIX_SHA, EXTRA: EXTRA_SHA, PIPELINE: PIPELINE_SHA,
        TOKENIZER: TOKENIZER_SHA, CORE: CORE_SHA, RAW_REVIEW: RAW_REVIEW_SHA,
        CORE_REVIEW: CORE_REVIEW_SHA, FINAL_REVIEW: FINAL_REVIEW_SHA}
    assert all(sha(path) == digest for path, digest in fixed.items())
    prior_review_path = OLD / 'positive-2754-independent-structural-review.json'
    prior_review = json.loads(prior_review_path.read_text())
    assert prior_review['dataset']['sha256'] == PREFIX_SHA
    lineage = {}
    for name, entry in prior_review['source_datasets'].items():
        path = Path(entry['path'])
        if not path.is_absolute():
            path = ROOT / path
        assert sha(path) == entry['sha256']
        fixed[path] = entry['sha256']
        lineage[name] = {'path': path, 'sha256': entry['sha256'], 'rows': rows(path)}
    for key in ('exposure_map', 'provenance_ledger', 'opaque_content_index',
                'disclosed_duplicates', 'collision_clarification', 'token_ledger', 'manifest'):
        entry = prior_review[key]
        path = ROOT / entry['path'] if not Path(entry['path']).is_absolute() else Path(entry['path'])
        assert sha(path) == entry['sha256']
        fixed[path] = entry['sha256']
    old_checks = rows(OLD / 'positive-2754-token-checks.jsonl')
    old_exposures = json.loads((OLD / 'positive-2754-source-exposures.json').read_text())['sources']
    prefix_bytes = PREFIX.read_bytes()
    assert prefix_bytes.endswith(b'\n') and len(prefix_bytes) == 4503793
    old, extra = rows(PREFIX), rows(EXTRA)
    assert len(old) == 2754 and len(extra) == 240 and len(old_checks) == 2754
    original_pair_set = {(row['input'], row['target']) for row in old}
    assert not original_pair_set.intersection((row['input'], row['target']) for row in extra)
    old_opaque_inputs = {opaque(row['input']) for row in old}
    assert not old_opaque_inputs.intersection(opaque(row['input']) for row in extra)
    core_cases = {case['fixture']['id']: case for case in json.loads(CORE.read_text())['cases']}
    assert len(core_cases) == 480
    raw_review = json.loads(RAW_REVIEW.read_text())
    assert raw_review['approved'] == 240 and raw_review['remaining_issues'] == 0
    assert len({row['id'] for row in extra}) == 240
    for row in old:
        provenance = row['positive_replay_instance']
        source = lineage[provenance['source_name']]
        original = source['rows'][provenance['source_position_zero_based']]
        assert source['sha256'] == provenance['source_file_sha256']
        assert original['id'] == provenance['source_id']
        assert row == {**original, 'id': row['id'], 'positive_replay_instance': provenance}

    appended = []
    for copy in (1, 2):
        for position, original in enumerate(extra):
            provenance = {'source_name': 'additional240', 'source_path': str(EXTRA),
                'source_file_sha256': EXTRA_SHA, 'source_position_zero_based': position,
                'source_id': original['id'], 'copy_one_based': copy,
                'total_exposures_for_source_row': 2, 'is_disclosed_oversampling_copy': copy > 1,
                'input_target_bytes_unchanged': True}
            row = {**original, 'id': f'positive-v8-additional240-{position:04d}-copy{copy}',
                'positive_replay_instance': provenance}
            assert all(row[key] == value for key, value in original.items() if key != 'id')
            appended.append(row)
    combined = old + appended
    assert len(combined) == len({row['id'] for row in combined}) == 3234
    assert all(row['needs_cleanup'] == (row['input'] != row['target']) for row in combined)
    spec = importlib.util.spec_from_file_location('reserved_positive3234_pipeline_validation', PIPELINE)
    pipeline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)
    assert 'torch' not in sys.modules
    tokenizer = Tokenizer.from_file(str(TOKENIZER))
    assert tokenizer.token_to_id('<|startoftext|>') == 1
    assert tokenizer.token_to_id('<|im_end|>') == 7

    pair_instances = collections.defaultdict(list)
    normalized_pairs = collections.defaultdict(set)
    exact_targets = collections.defaultdict(set)
    normalized_targets = collections.defaultdict(set)
    source_ids = collections.defaultdict(set)
    instances, exposures, checks, hash_rows = [], {}, [], []
    source_effective, family_effective = collections.Counter(), collections.Counter()
    literal_spans = 0
    for position, row in enumerate(combined):
        source, target = row['input'], row['target']
        prompt, masked_target, mask = pipeline.protected_pair(source, target)
        assert mask.restore(masked_target) == target
        prompt_ids = tokenizer.encode(prompt, add_special_tokens=False).ids
        target_ids = tokenizer.encode(masked_target, add_special_tokens=False).ids + [7]
        assert prompt_ids[0] == 1 and prompt_ids.count(1) == 1
        assert len(prompt_ids) + len(target_ids) <= 1024
        check = {'id': row['id'], 'prompt_tokens': len(prompt_ids),
            'assistant_tokens_including_eos': len(target_ids), 'total_tokens': len(prompt_ids) + len(target_ids),
            'leading_bos1_exactly_once': True, 'assistant_eos7_appended': True,
            'literal_roundtrip_exact': True, 'literal_count': len(mask.tokens),
            'complete_prompt_sha256': th(prompt), 'masked_target_sha256': th(masked_target), 'truncated': False}
        if position < 2754:
            assert check == old_checks[position], 'Strict current loader changed frozen prior prompt/mask/token ledger'
        else:
            source_id = row['positive_replay_instance']['source_id']
            source_case = core_cases[source_id + '/input']
            target_case = core_cases[source_id + '/target']
            assert source == source_case['normalized_input'] and target == target_case['normalized_input']
            assert prompt == source_case['completion']['text']
            assert pipeline.PREFIX + masked_target + pipeline.SUFFIX == target_case['completion']['text']
            assert th(mask.masked_text) == source_case['model_input_sha256']
            assert th(masked_target) == target_case['model_input_sha256']
            assert row['core_normalization']['export_sha256'] == CORE_SHA
        checks.append(check)
        literal_spans += len(mask.tokens)
        key = source, target
        first = key not in pair_instances
        pair_instances[key].append(row['id'])
        normalized_pairs[(opaque(source), opaque(target))].add(key)
        exact_targets[source].add(target)
        normalized_targets[opaque(source)].add(opaque(target))
        provenance = row['positive_replay_instance']
        source_key = provenance['source_name'], provenance['source_id']
        source_ids[provenance['source_id']].add((provenance['source_file_sha256'], th(source), th(target)))
        entry = exposures.setdefault(source_key, {'source_name': source_key[0], 'source_id': source_key[1],
            'source_file_sha256': provenance['source_file_sha256'], 'input_sha256': th(source),
            'target_sha256': th(target), 'positive_row_ids': []})
        assert entry['input_sha256'] == th(source) and entry['target_sha256'] == th(target)
        entry['positive_row_ids'].append(row['id'])
        source_effective[provenance['source_name']] += 1
        family_effective[row['family']] += 1
        instances.append({'position_zero_based': position, 'id': row['id'], **provenance})
        if first:
            hash_rows.append({'source_name': source_key[0], 'source_id': source_key[1],
                'raw_input_sha256': th(source), 'raw_target_sha256': th(target),
                'normalized_input_sha256': opaque(source), 'normalized_target_sha256': opaque(target)})
    source_id_collisions = {key: sorted(values) for key, values in source_ids.items() if len(values) > 1}
    assert not source_id_collisions
    assert all(len(values) == 1 for values in exact_targets.values())
    assert all(len(values) == 1 for values in normalized_targets.values())
    assert len(pair_instances) == len(exposures) == 2624 and len(normalized_pairs) == 2620
    assert source_effective == {'history2014': 2014, 'contrasts270': 540, 'additional100': 200, 'additional240': 480}
    assert list(exposures.values())[:len(old_exposures)] == old_exposures
    assert all(len(entry['positive_row_ids']) == (1 if entry['source_name'] == 'history2014' else 2)
        for entry in exposures.values())
    duplicates = [{'raw_pair_sha256': th(source + '\x00' + target), 'instance_ids': ids}
        for (source, target), ids in pair_instances.items() if len(ids) > 1]
    assert len(duplicates) == 610 and all(len(entry['instance_ids']) == 2 for entry in duplicates)
    collisions = []
    for normalized_key, variants in normalized_pairs.items():
        if len(variants) > 1:
            assert len({target for source, target in variants}) == 1
            collisions.append({'normalized_input_sha256': normalized_key[0],
                'normalized_target_sha256': normalized_key[1],
                'raw_variants': [{'raw_input_sha256': th(source), 'raw_target_sha256': th(target),
                    'instance_ids': pair_instances[(source, target)]} for source, target in sorted(variants)],
                'exact_target_identical': True, 'origin': 'Pre-existing preserved history casefold collision, no deduplication.'})
    assert len(collisions) == 4
    legacy = [row for row in combined if '[[FREEHAND_LITERAL_' in row['input'] or '[[FREEHAND_LITERAL_' in row['target']]
    assert len(legacy) == 57
    assert sum(row['input'] == row['target'] for row in combined) == 1048
    assert sum(source == target for source, target in pair_instances) == 858
    OUT.mkdir()
    destination = OUT / 'positive-3234-proposed.jsonl'
    with destination.open('xb') as stream:
        stream.write(prefix_bytes)
        for row in appended:
            stream.write((json.dumps(row, ensure_ascii=False) + '\n').encode('utf-8'))
    assert destination.read_bytes()[:len(prefix_bytes)] == prefix_bytes
    assert len(pipeline.load_data(destination)) == 3234
    dataset_sha = sha(destination)
    write_rows('positive-3234-token-checks.jsonl', checks)
    write_rows('positive-3234-provenance.jsonl', instances)
    write_json('positive-3234-source-exposures.json', {'positive_artifact_sha256': dataset_sha,
        'sources': list(exposures.values()), 'scope': 'Positive exposures only; no new negative events or UL binding authorized.'})
    write_json('positive-3234-content-hashes.json', {'dataset_sha256': dataset_sha,
        'normalization': 'Unicode NFC, whitespace collapse and strip, casefold, UTF8 SHA256',
        'raw_unique_pairs': len(pair_instances), 'normalized_unique_hash_pairs': len(normalized_pairs), 'rows': hash_rows})
    write_json('positive-3234-disclosed-duplicates.json', {'dataset_sha256': dataset_sha, 'groups': duplicates,
        'new240_unique_pairs': 240, 'new240_total_exposures': 480, 'new240_extra_repeat_exposures': 240,
        'prior_extra_repeat_exposures': 370, 'total_extra_repeat_exposures': 610,
        'reason': 'Exact historical2754 preserved; approved normalized240 appended twice. No deduplication or relabeling.'})
    write_json('positive-3234-id-and-normalized-collisions.json', {'dataset_sha256': dataset_sha,
        'unique_instance_ids': 3234, 'unique_source_ids': len(source_ids), 'source_id_content_collisions': source_id_collisions,
        'normalized_casefold_collision_groups': collisions, 'exact_input_target_conflicts': 0,
        'normalized_input_target_conflicts': 0, 'no_deduplication_or_source_text_changes': True})
    write_json('positive-3234-lineage.json', {'dataset_sha256': dataset_sha,
        'preserved_prefix': ref(PREFIX), 'prior_independent_structure_review': ref(prior_review_path),
        'old_training_sources': {name: ref(entry['path']) for name, entry in lineage.items()},
        'old_source_rows_fields_and_order_reconstructed': 2754, 'legacy_dictionary_rows_once': 57,
        'appended_normalized240': ref(EXTRA), 'raw240_independent_review_rollup': ref(RAW_REVIEW),
        'actual_core_export': ref(CORE), 'core_normalization_independent_review': ref(CORE_REVIEW),
        'final_normalization_approval': ref(FINAL_REVIEW),
        'normalization': 'No new normalization; approved normalized240 copied exactly on both exposures.',
        'old_history_fields_and_original_source_bytes_unchanged': True})
    manifest = {'schema_version': 1, 'status': 'RESERVED_PROPOSED_POSITIVE_ONLY_NOT_SELECTED_NOT_ACTIVATED_NOT_TRAINING_APPROVAL',
        'dataset': ref(destination), 'preserved_prefix': ref(PREFIX), 'entire2754_prefix_exact_bytes': True,
        'appended_source': ref(EXTRA), 'append_order': 'copy1 of all240 in original order, then copy2 of all240 in original order',
        'effective_exposures': 3234, 'raw_unique_pairs': 2624, 'normalized_unique_hash_pairs': 2620,
        'cleanup_exposures': 2186, 'unchanged_control_exposures': 1048, 'unchanged_raw_unique_pairs': 858,
        'source_effective_exposures': dict(source_effective), 'family_effective_exposures': dict(family_effective),
        'new_source_unique_pairs': 240, 'new_source_total_exposures': 480, 'new_extra_repeat_exposures': 240,
        'old_extra_repeat_exposures': 370, 'total_extra_repeat_exposures': 610,
        'duplicate_pair_groups': 610, 'normalized_casefold_collision_groups': 4,
        'unique_instance_ids': 3234, 'unique_canonical_source_ids': 2624, 'source_id_content_collisions': 0,
        'exact_input_target_conflicts': 0, 'normalized_input_target_conflicts': 0,
        'needs_cleanup_flags_match_text_inequality': 3234, 'full_source_fields_preserved_except_unique_instance_ids': True,
        'old2754_token_prompt_mask_ledger_exact_matches_under_strict_loader': 2754,
        'new480_exposure_input_and_target_prompt_mask_matches_to_saved_core': 480,
        'literal_roundtrips': 3234, 'protected_span_exposures': literal_spans, 'legacy_dictionary_rows_preserved_once': 57,
        'pipeline_loader_rows_passed': 3234, 'pipeline_source_sha256_used': PIPELINE_SHA,
        'literal_protocol': pipeline.PROTOCOL, 'tokenizer': ref(TOKENIZER),
        'tokenizers_version': importlib.metadata.version('tokenizers'), 'token_cap': 1024,
        'maximum_complete_tokens': max(check['total_tokens'] for check in checks), 'truncated_examples': 0,
        'all_leading_bos1_once_and_eos7_appended': True,
        'no_new_normalization': True, 'builder_sha256': sha(Path(__file__)),
        'parent_model': 'UNSELECTED; pending root F32 comparison. No configuration or trainer updates.',
        'unlikelihood_events': 'No events created, rebound or modified. Existing approved32 and active files remain untouched.',
        'independent_structure_review': 'Pending separate immutable receipt; no activation implied.',
        'root_reported_opaque_overlap': 'Root reported receipt e0604102... all four fresh comparisons zero, old/new normalized-input overlap zero. No fresh content or opaque receipt was opened by this builder.',
        'source_exposure_map': ref(OUT / 'positive-3234-source-exposures.json'),
        'provenance': ref(OUT / 'positive-3234-provenance.jsonl'),
        'content_hash_index': ref(OUT / 'positive-3234-content-hashes.json'),
        'disclosed_duplicates': ref(OUT / 'positive-3234-disclosed-duplicates.json'),
        'collisions': ref(OUT / 'positive-3234-id-and-normalized-collisions.json'),
        'lineage': ref(OUT / 'positive-3234-lineage.json'),
        'token_checks': ref(OUT / 'positive-3234-token-checks.jsonl'),
        'no_torch_imported': 'torch' not in sys.modules,
        'no_model_native_build_inference_training_or_fresh_content_reads': True,
        'all_source_files_reverified_unchanged_after': all(sha(path) == digest for path, digest in fixed.items())}
    assert manifest['no_torch_imported'] and manifest['all_source_files_reverified_unchanged_after']
    write_json('positive-3234-proposed-manifest.json', manifest)
    print(json.dumps({key: manifest[key] for key in ('dataset', 'effective_exposures', 'raw_unique_pairs',
        'normalized_unique_hash_pairs', 'cleanup_exposures', 'unchanged_control_exposures',
        'maximum_complete_tokens', 'source_exposure_map', 'content_hash_index', 'no_torch_imported')}), flush=True)


if __name__ == '__main__':
    main()
