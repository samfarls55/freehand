#!/usr/bin/env python3
"""Append root-approved100 twice, preserving the exact provisional2554 bytes."""
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
PREFIX_FILE = OUT / 'positive-2554-provisional.jsonl'
PREFIX_SHA = '8e31598f65e695001b37d8920e44b93f6e6fb2a24ae6d0cf8e8387dd1b4a51a9'
ADDITIONAL = WORK / 'audit/v7-additional-100/core-normalization-v1/train-100-core-normalized-v1.jsonl'
ADDITIONAL_SHA = 'b6d6bd277febb06125c3b49851c24d813d1efb4a7cdc98820ee4508c946366dc'
TOKENIZER = ROOT / 'work/cleanup-small-models-2026-11-03/scribe-precision-source/original-model/tokenizer.json'
TOKENIZER_SHA = 'df1d8d5ec5d091b460562ffd545e4a5e91d17d4a0db7ebe733be34ed374377bd'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def th(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def opaque(text):
    return th(' '.join(unicodedata.normalize('NFC', text).split()).strip().casefold())


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def write_rows(path, rows):
    with path.open('x', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def main():
    assert 'torch' not in sys.modules
    from tokenizers import Tokenizer
    assert sha(PREFIX_FILE) == PREFIX_SHA and sha(ADDITIONAL) == ADDITIONAL_SHA
    assert sha(TOKENIZER) == TOKENIZER_SHA
    tokenizer = Tokenizer.from_file(str(TOKENIZER))
    assert tokenizer.token_to_id('<|startoftext|>') == 1 and tokenizer.token_to_id('<|im_end|>') == 7
    pipeline_path = ROOT / 'tools/Freehand.Cleanup.Training/pipeline.py'
    pipeline_sha = sha(pipeline_path)
    spec = importlib.util.spec_from_file_location('positive_final_literal_validation', pipeline_path)
    pipeline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)
    prefix_bytes = PREFIX_FILE.read_bytes()
    assert prefix_bytes.endswith(b'\n')
    old = [json.loads(line) for line in prefix_bytes.splitlines()]
    extra = [json.loads(line) for line in ADDITIONAL.read_text().splitlines()]
    assert len(old) == 2554 and len(extra) == 100
    original_pairs = {(r['input'], r['target']) for r in old}
    assert not original_pairs.intersection((r['input'], r['target']) for r in extra), 'Disclose/review overlap before assembly'
    appended = []
    for copy in (1, 2):
        for position, original in enumerate(extra):
            provenance = {'source_name': 'additional100', 'source_path': str(ADDITIONAL),
                'source_file_sha256': ADDITIONAL_SHA, 'source_position_zero_based': position,
                'source_id': original['id'], 'copy_one_based': copy,
                'total_exposures_for_source_row': 2, 'is_disclosed_oversampling_copy': copy > 1,
                'input_target_bytes_unchanged': True}
            row = {**original, 'id': f'positive-v7-additional100-{position:04d}-copy{copy}',
                'positive_replay_instance': provenance}
            assert all(row[key] == value for key, value in original.items() if key != 'id')
            appended.append(row)
    rows = old + appended
    assert len(rows) == 2754 and len({r['id'] for r in rows}) == 2754
    pairs = collections.defaultdict(list)
    targets_by_input = collections.defaultdict(set)
    normalized_targets = collections.defaultdict(set)
    exposures = {}
    family_effective = collections.Counter()
    source_effective = collections.Counter()
    checks, hashes = [], []
    for row in rows:
        source, target = row['input'], row['target']
        prompt, masked_target, mask = pipeline.protected_pair(source, target)
        assert mask.restore(masked_target) == target
        prompt_ids = tokenizer.encode(prompt, add_special_tokens=False).ids
        target_ids = tokenizer.encode(masked_target, add_special_tokens=False).ids + [7]
        assert prompt_ids[0] == 1 and prompt_ids.count(1) == 1
        assert len(prompt_ids) + len(target_ids) <= 1024
        checks.append({'id': row['id'], 'prompt_tokens': len(prompt_ids),
            'assistant_tokens_including_eos': len(target_ids), 'total_tokens': len(prompt_ids) + len(target_ids),
            'leading_bos1_exactly_once': True, 'assistant_eos7_appended': True,
            'literal_roundtrip_exact': True, 'literal_count': len(mask.tokens),
            'complete_prompt_sha256': th(prompt), 'masked_target_sha256': th(masked_target), 'truncated': False})
        key = source, target
        first = key not in pairs
        pairs[key].append(row['id'])
        targets_by_input[source].add(target)
        normalized_targets[opaque(source)].add(opaque(target))
        provenance = row['positive_replay_instance']
        source_key = provenance['source_name'], provenance['source_id']
        entry = exposures.setdefault(source_key, {'source_name': source_key[0], 'source_id': source_key[1],
            'source_file_sha256': provenance['source_file_sha256'], 'input_sha256': th(source),
            'target_sha256': th(target), 'positive_row_ids': []})
        assert entry['input_sha256'] == th(source) and entry['target_sha256'] == th(target)
        entry['positive_row_ids'].append(row['id'])
        source_effective[provenance['source_name']] += 1
        family_effective[row['family']] += 1
        if first:
            hashes.append({'source_name': source_key[0], 'source_id': source_key[1],
                'normalized_input_sha256': opaque(source), 'normalized_target_sha256': opaque(target)})
    conflicts = [{'input': source, 'targets': sorted(targets)} for source, targets in targets_by_input.items() if len(targets) > 1]
    norm_conflicts = [source_hash for source_hash, targets in normalized_targets.items() if len(targets) > 1]
    assert not conflicts and not norm_conflicts
    assert len(pairs) == len(exposures) == 2384
    assert source_effective == {'history2014': 2014, 'contrasts270': 540, 'additional100': 200}
    assert all(len(v['positive_row_ids']) == (1 if v['source_name'] == 'history2014' else 2) for v in exposures.values())
    duplicates = [{'pair_sha256': th(source + '\x00' + target), 'instance_ids': ids}
        for (source, target), ids in pairs.items() if len(ids) > 1]
    assert len(duplicates) == 370 and all(len(v['instance_ids']) == 2 for v in duplicates)
    legacy = [r for r in rows if '[[FREEHAND_LITERAL_' in r['input'] or '[[FREEHAND_LITERAL_' in r['target']]
    assert len(legacy) == 57
    destination = OUT / 'positive-2754-final.jsonl'
    with destination.open('xb') as stream:
        stream.write(prefix_bytes)
        for row in appended:
            stream.write((json.dumps(row, ensure_ascii=False) + '\n').encode('utf-8'))
    assert destination.read_bytes()[:len(prefix_bytes)] == prefix_bytes
    assert len(pipeline.load_data(destination)) == 2754
    dataset_sha = sha(destination)
    write_rows(OUT / 'positive-2754-token-checks.jsonl', checks)
    write_rows(OUT / 'positive-2754-provenance.jsonl', [{'id': row['id'], **row['positive_replay_instance']} for row in rows])
    write_json(OUT / 'positive-2754-source-exposures.json', {'positive_artifact_sha256': dataset_sha,
        'sources': list(exposures.values()), 'requirement': 'Bind all listed instances of each selected source to the same UL event; eta0/eta1 must use these exact positive bytes.'})
    write_json(OUT / 'positive-2754-content-hashes.json', {'dataset_sha256': dataset_sha,
        'normalization': 'Unicode NFC, whitespace collapse and strip, casefold, UTF8 SHA256', 'unique_pairs': len(pairs), 'rows': hashes})
    write_json(OUT / 'positive-2754-disclosed-duplicates.json', {'groups': duplicates,
        'reason': 'Approved270 and approved100 each exposed twice; history2014 once. Added370 exposures are not additional unique authoring.'})
    write_json(OUT / 'positive-2754-input-target-conflicts.json', {'exact_input_conflicts': conflicts,
        'normalized_input_hash_conflicts': norm_conflicts})
    manifest = {'schema_version': 1, 'status': 'FINAL_POSITIVE_CANDIDATE_PENDING_ROOT_OPAQUE_OVERLAP_AND_TRAINING_APPROVAL',
        'dataset_path': str(destination), 'dataset_sha256': dataset_sha,
        'preserved_prefix_path': str(PREFIX_FILE), 'preserved_prefix_sha256': PREFIX_SHA,
        'preserved2554_prefix_exact_bytes': True, 'added100_normalized_path': str(ADDITIONAL),
        'added100_normalized_sha256': ADDITIONAL_SHA, 'effective_rows': len(rows), 'unique_exact_pairs': len(pairs),
        'disclosed_oversampling_added_rows': 370, 'duplicate_groups': len(duplicates),
        'source_effective_rows': dict(source_effective), 'family_effective_counts': dict(family_effective),
        'unchanged_effective_rows': sum(r['input'] == r['target'] for r in rows),
        'unchanged_unique_pairs': sum(source == target for source, target in pairs),
        'all_source_fields_preserved_except_instance_id': True, 'all_input_target_bytes_unchanged': True,
        'legacy57_rows_preserved_once': len(legacy), 'exact_input_label_conflicts': len(conflicts),
        'normalized_input_label_conflicts': len(norm_conflicts), 'all2754_literal_roundtrips_pass': True,
        'pipeline_loader_rows': 2754, 'tokenizer_sha256': TOKENIZER_SHA,
        'tokenizers_version': importlib.metadata.version('tokenizers'), 'maximum_complete_tokens': max(c['total_tokens'] for c in checks),
        'token_cap': 1024, 'truncated_examples': 0, 'leading_bos1_once_and_eos7_all': True,
        'pipeline_source_sha256_used': pipeline_sha, 'literal_protocol': pipeline.PROTOCOL,
        'builder_sha256': sha(Path(__file__)),
        'source_exposures_sha256': sha(OUT / 'positive-2754-source-exposures.json'),
        'opaque_content_index_sha256': sha(OUT / 'positive-2754-content-hashes.json'),
        'eta0_eta1_same_positive_file_required': True, 'no_torch_imported': 'torch' not in sys.modules,
        'no_model_native_inference_or_training_jobs': True, 'fresh_round2_content_accessed': False,
        'opaque_final_overlap': 'Root controller only, pending; no fresh data accessed here.',
        'independent_normalization_and_structure_review': 'Pending separate immutable review receipts; no new labels authored in assembly.'}
    assert manifest['no_torch_imported'] and sha(pipeline_path) == pipeline_sha
    assert sha(PREFIX_FILE) == PREFIX_SHA and sha(ADDITIONAL) == ADDITIONAL_SHA
    write_json(OUT / 'positive-2754-final-manifest.json', manifest)
    print(json.dumps({k: manifest[k] for k in ('dataset_path', 'dataset_sha256', 'effective_rows',
        'unique_exact_pairs', 'unchanged_effective_rows', 'unchanged_unique_pairs',
        'maximum_complete_tokens', 'source_exposures_sha256', 'opaque_content_index_sha256', 'no_torch_imported')}))


if __name__ == '__main__':
    main()
