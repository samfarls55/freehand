#!/usr/bin/env python3
"""Apply the explicitly root-approved completed-V8 text/source evidence plan."""
from pathlib import Path, PurePosixPath
import copy
import datetime
import hashlib
import json
import os
import tarfile

REPO = Path('/workspace/freehand')
CURATED = REPO / 'docs/cleanup-evaluation/2026-11-03-scribekey-training'
OUT = Path(__file__).resolve().parent
PLAN = OUT / 'selection-size-plan.json'
PLAN_SHA = '57eab9f66d70cb23d0de1f5ec67e764c1d3b2cd0f0f5866e82369abca107e9e8'
OLD_SHA = '50dc19d32898207cd8812d4eb4b72a56052f43e397347e622fdb019da19f6c53'
OLD_COUNT = 1300
OLD_TOTAL = 79083660
DERIVED = ('README.md', 'collection-manifest.json', 'evidence-files-sha256.json')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def safe(name):
    path = PurePosixPath(name)
    assert not path.is_absolute() and '..' not in path.parts
    return name


def listing():
    return {p.relative_to(CURATED).as_posix(): p for p in CURATED.rglob('*') if p.is_file() or p.is_symlink()}


plan_bytes = PLAN.read_bytes()
assert digest(plan_bytes) == PLAN_SHA
plan = json.loads(plan_bytes)
phase = plan['phase']
assert phase == 'phases/v8-completed-10'
phase_root = CURATED / phase
assert not phase_root.exists(), 'Never overwrite a previous attempt or existing evidence phase'
assert plan['within_budget'] and plan['projected_new_growth_bytes'] <= 20000000
old_bytes = {name: (CURATED / name).read_bytes() for name in DERIVED}
assert digest(old_bytes['evidence-files-sha256.json']) == OLD_SHA
old_index = json.loads(old_bytes['evidence-files-sha256.json'])
old_manifest = json.loads(old_bytes['collection-manifest.json'])
old_files = listing()
assert len(old_files) == OLD_COUNT
assert set(old_files) == set(old_index['files']) | {'evidence-files-sha256.json'}
assert sum(p.stat().st_size for p in old_files.values()) == OLD_TOTAL
# All existing curated text/archive bytes are verified before any new copy.
for name, entry in old_index['files'].items():
    path = old_files[name]
    assert not path.is_symlink()
    raw = path.read_bytes()
    assert len(raw) == entry['bytes'] and digest(raw) == entry['sha256'], name

payloads = {}
sources = {}
source_hash_receipt = []
for row in plan['selected_files']:
    name = safe(row['path'])
    assert name.startswith(phase + '/') and not (CURATED / name).exists()
    if row.get('source_kind') == 'text_source_archive_member':
        archive = Path(row['source_archive'])
        assert digest(archive.read_bytes()) == row['source_archive_sha256']
        with tarfile.open(archive) as bundle:
            member = bundle.getmember(row['archive_member'])
            assert member.isfile()
            safe(member.name)
            raw = bundle.extractfile(member).read()
        source_name = str(archive) + '!' + row['archive_member']
        observation = {'archive_member_bytes': len(raw), 'complete_source_at_snapshot': True}
    else:
        path = Path(row['source_path'])
        assert path.is_file() and not path.is_symlink()
        assert path.suffix.lower() in {'.py', '.json', '.jsonl', '.md', '.txt', '.log', '.cs', '.csproj', '.props', '.config', '.ps1'} or path.name.endswith('.source-snapshot.tar.gz')
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
        assert (before.st_size, before.st_mtime_ns, before.st_ino) == (after.st_size, after.st_mtime_ns, after.st_ino)
        source_name = str(path)
        observation = {'source_size_before_read': before.st_size, 'source_size_after_read': after.st_size,
                       'source_mtime_ns_before_read': before.st_mtime_ns, 'source_mtime_ns_after_read': after.st_mtime_ns,
                       'captured_bytes': len(raw), 'complete_source_at_snapshot': True}
    value = digest(raw)
    assert len(raw) == row['bytes'], source_name
    if row['expected_sha256'] is not None:
        assert value == row['expected_sha256'], source_name
    if row['group'] != 'original_source_archive':
        raw.decode('utf-8-sig')
        assert not raw.startswith((b'\x7fELF', b'MZ', b'GGUF', b'PK\x03\x04'))
    payloads[name] = raw
    sources[name] = {'source_path': source_name, 'reason': row['reason'],
                     'source_kind': row.get('source_kind', 'completed_text_evidence'), 'observation': observation}
    source_hash_receipt.append({'path': name, 'bytes': len(raw), 'sha256': value, 'planned_hash_status': row['hash_status']})

for row in plan['historical_previous1300_snapshots']:
    name = Path(row['source_path']).name
    raw = old_bytes[name]
    assert len(raw) == row['bytes'] and digest(raw) == row['sha256']
    payloads[row['destination']] = raw
    sources[row['destination']] = {'source_path': str(CURATED / name), 'reason': 'Exact previous1300 derived-document epoch before append',
        'source_kind': 'historical_derived_snapshot', 'observation': {'captured_bytes': len(raw), 'complete_source_at_snapshot': True}}

duplicate_receipt = []
for row in plan['checkpoint_source_config_identical_payload_references']:
    path = Path(row['original_source_path'])
    assert path.is_file() and not path.is_symlink()
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    assert len(raw) == row['bytes'] and digest(raw) == row['sha256']
    assert raw == payloads[row['available_payload_path']]
    duplicate_receipt.append({**row, 'verification_stage': 'Actual original source and selected shared payload compared byte for byte before copy',
                              'source_size': after.st_size, 'byte_identical': True})
assert len(duplicate_receipt) == 10
for row in plan['prior_curated_history_references']:
    raw = (CURATED / row['available_payload_path']).read_bytes()
    assert len(raw) == row['bytes'] and digest(raw) == row['sha256']

def get(relative):
    return payloads[phase + '/' + relative]


# Verify full actual data and the exact preexisting2754 byte prefix without using Torch/tokenizers.
data = get('data/positive3234/positive-3234-proposed.jsonl')
prefix_ref = next(row for row in plan['prior_curated_history_references'] if row['purpose'] == 'full2754_prefix')
prefix = (CURATED / prefix_ref['available_payload_path']).read_bytes()
assert data.startswith(prefix)
positive_rows = [json.loads(line) for line in data.splitlines()]
core240_bytes = get('data/used-240/core-normalization-v1/train-240-core-normalized-v1.jsonl')
core240 = [json.loads(line) for line in core240_bytes.splitlines()]
raw240 = [json.loads(line) for line in get('data/used-240/train-240-v1.jsonl').splitlines()]
assert len(positive_rows) == 3234 and len({row['id'] for row in positive_rows}) == 3234
assert len(core240) == len(raw240) == 240
assert [row['id'] for row in core240] == [row['id'] for row in raw240]
for copy_number in (1, 2):
    for offset, source in enumerate(core240):
        row = positive_rows[2754 + (copy_number - 1) * 240 + offset]
        replay = row['positive_replay_instance']
        assert replay['source_name'] == 'additional240'
        assert replay['source_position_zero_based'] == offset
        assert replay['source_id'] == source['id'] and replay['copy_one_based'] == copy_number
        assert replay['source_file_sha256'] == digest(core240_bytes)
        assert {key: value for key, value in row.items() if key not in ('id', 'positive_replay_instance')} == {key: value for key, value in source.items() if key != 'id'}
assert sum(row['input'] == row['target'] for row in positive_rows) == 1048
lineage_receipt = {'schema_version': 1, 'actual3234_dataset_sha256': digest(data), 'actual3234_rows': len(positive_rows),
    'full_original2754_prefix': prefix_ref, 'prefix_bytes': len(prefix), 'prefix_exact_bytes': True,
    'raw240_sha256': digest(get('data/used-240/train-240-v1.jsonl')), 'core240_sha256': digest(core240_bytes),
    'all480_source_rows_fields_and_order_except_instance_id_exact': True,
    'source240_two_exposures_and_3234_unique_instance_ids': True,
    'saved_full_token_provenance_and_hash_ledgers_retained': True,
    'tokenizer_model_or_new_Core_export_run_by_collector': False,
    'older_history_references': plan['prior_curated_history_references']}

# Independently check completed log structure; preserve actual source-validated mapping scope.
canonical_bytes = get('training/completed-v8-01/canonical-training-log.jsonl')
assert canonical_bytes == get('training/completed-v8-01/training-log.jsonl')
events = [json.loads(line) for line in canonical_bytes.splitlines()]
assert [event['step'] for event in events] == list(range(1, 406))
assert events[-1]['microbatch'] == 809 and events[-1]['assistant_tokens'] == 55612
assert sum(len(event['objective_microbatches']) for event in events) == 809
assert sum(part['event_count'] for event in events for part in event['objective_microbatches']) == 64
final = json.loads(get('training/completed-v8-01/final-verification.json'))
assert final['steps'] == 405 and final['last_durable_step'] == 400 and final['final405_rng_capture_claimed'] is False
conversion = json.loads(get('native-export/conversion-report.json'))
assert conversion['actual_final_optimizer']['sha256'] == '1edba751cbae803bc49166a8cb3c40cbb49e0b801bd706538d33177af3682166'
assert conversion['actual_optimizer_counters']['all_actual_AdamW_state_counters'] == 405
assert conversion['v8_activation_and_training_lineage']['objective']['direct_per_exposure_ids_logged'] is False
assert 'final verifier supplied counters but no digest' in conversion['v8_activation_and_training_lineage']['optimizer_digest_capture_stage']

report_bytes = get('retired500-core/core-results.json')
report = json.loads(report_bytes)
summary = json.loads(get('semantic-reviews/canonical-semantic-summary.json'))
review = json.loads(get('semantic-reviews/canonical-reviewed.json'))
assert summary['results_sha256'] == digest(report_bytes) == review['results_sha256']
assert summary['canonical_review_sha256'] == digest(get('semantic-reviews/canonical-reviewed.json'))
assert report['incomplete'] is False and len(report['cases']) == 500
assert len({row['id'] for row in report['cases']}) == 500
assert [row['case_id'] for row in review['cases']] == [row['id'] for row in report['cases']]
for actual, judged in zip(report['cases'], review['cases']):
    assert actual['insertion_count'] == actual['delivered_count'] == 1
    assert actual['delivery_outcome'] == 'Delivered' and actual['error'] is None
    assert actual['cleanup_status'] in ('Applied', 'Unchanged')
    assert judged['output_sha256'] == digest(actual['output'].encode('utf-8'))
assert sum(row['semantic_faithful'] for row in review['cases']) == summary['faithful'] == 498
assert sum(row['clean_usable'] for row in review['cases']) == summary['clean_usable'] == 493
assert sum(row['semantic_faithful'] and row['clean_usable'] for row in review['cases']) == summary['faithful_and_clean_usable'] == 492
assert sum(row['critical_error'] for row in review['cases']) == summary['critical_errors'] == 1
assert summary['quality_gate_passed'] is False
freeze = json.loads(get('retired500-freeze/candidate-freeze.json'))
assert freeze['profile']['cacheTypeK'] == freeze['profile']['cacheTypeV'] == 'f16'
assert freeze['runtime_adapter']['sha256'] == '11ec6ac65c06205cabf8ed1fd41c3163658112f8f44a5062b9133c0e29ecf8e8'
assert freeze['effective_model_identity']['runtime_adapter_scale'] == 1
for member in plan['source_archive_members_and_reuse_map']:
    raw = payloads.get(member['available_payload_path'])
    if raw is None:
        raw = (CURATED / member['available_payload_path']).read_bytes()
    assert len(raw) == member['bytes'] and digest(raw) == member['sha256']

readme = '''# Completed V8 training, native export and retired500 development review

V8 continued from the selected completed V7 UL parent raw adapter8855 with a fresh optimizer, rank8/alpha16, one epoch and eta1. The actual full3234-row dataset2fdab and all count, token, provenance and source-exposure ledgers are retained. Its exact2754-row prefix and older2014/270/100/approved32 histories remain available by byte-verified references to prior curated phases. The additional240 approved raw author parts, historical revisions/overlays, independent reviews, real Core export, normalization maps and approved Core labels are all preserved. Both240-row exposures are checked field for field against the complete saved dataset.

Some raw filenames/statuses still say proposed or reserved because those original authoring snapshots predate activation. Their bytes are preserved, alongside the actual explicit activation and completed-run records. These240 rows were used in V8; current interpolation, unused80/3394 and future work are excluded. Draft variants are authoring lineage, not additional trained labels.

Training completed405 optimizer updates,809 microbatches and55,612 assistant tokens with64 logged unlikelihood-event exposures. Full raw, canonical and outer-console logs, executed source8c609, config, verifier source and all surviving checkpoint/snapshot states are included. Ten identical checkpoint/snapshot source/config bodies are represented by exact shared-payload references; every original was compared byte for byte before collection. The last durable RNG checkpoint is400. No final405 RNG capture is claimed. Event mapping is source-validated; individual exposure IDs were not directly logged.

The original export preflight failed on a verifier/optimizer-schema expectation before Torch, model loading, conversion or native inference. That trace, historical source/audit and the corrected controller,11-test result and independent delta audit are retained. The actual final optimizer digest1edba was captured after training release at export preflight; the original final verifier supplied counters, not that digest. The completed184-F32 native adapter11ec is used unmerged at external scale1 on originalIQ4 base82ab. Weights, optimizer/RNG payloads, DLLs and native executables are not copied.

The complete original retired500 Core report, inputs, actualF16 KV profile, up-front freeze, durable owned process/argv journals, legal notices and deployment postverification remain available. All500 completed one delivery each with no provider Failed result. Semantic review records492/500 faithful-and-clean,498 faithful,493 clean and one critical error: below the495/500 gate. All range reviews, strict prior-pass inheritance proofs, root28 actual crosspairs and the independentC076/C112 adjudication are preserved. C076 retains its explicit moderate-confidence correction-scope ambiguity; this collection does not strengthen that judgment or claim500 newly personal reads.

The exact original V8 source archive69a975 is retained independently. All40 regular UTF8 members (39 source files plus the text hash manifest) are verified against the freeze; matching source bodies reuse already curated payloads by exact SHA. No changing repository source substitutes for the executed epoch.

This is retired development evidence, not99percent accuracy, population/fresh qualification, Windows/GPU/whole-app execution, or a new resource-SLA result. No model, binary, converter, native inference, Torch, build or training job is run by this collector. Every previous1300 file is preserved, with the prior three derived documents snapshotted exactly and the complete old README prefix retained. The root-owned main report is not edited.
'''.encode('utf-8')
stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
auxiliary = {
    'README.md': readme,
    'selection-plan.json': plan_bytes,
    'collector-source.py': Path(__file__).read_bytes(),
    'inventory-plan-source.py': (OUT / 'prepare_plan.py').read_bytes(),
    'source-lineage-map.json': encode({'schema_version': 1, 'archive': plan['source_archive'], 'members': plan['source_archive_members_and_reuse_map'],
        'captured_trainer_source': '8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad', 'current_repository_source_substituted': False}),
    'checkpoint-identical-payload-references.json': encode({'schema_version': 1, 'references': duplicate_receipt, 'all10_original_source_bodies_byte_verified': True}),
    'data-lineage-verification.json': encode(lineage_receipt),
    'previous1300-preservation.json': encode({'schema_version': 1, 'old_index_sha256': OLD_SHA, 'old_file_count': OLD_COUNT,
        'old_total_bytes': OLD_TOTAL, 'all_prior_hashes_verified_before_copy': True, 'historical_derived_snapshots': plan['historical_previous1300_snapshots']}),
    'authorized-source-hash-receipt.json': encode({'schema_version': 1, 'scope': 'Completed text/data/source evidence only; no model, binary, unused80/3394, current interpolation or future corpus read', 'files': source_hash_receipt}),
    'scope-and-exclusions.json': encode({'schema_version': 1, 'qualification': plan['factual_qualifications'], 'excluded': plan['excluded'],
        'source_validated_event_mapping_not_direct_per_exposure_ID_logs': True, 'quality_gate_passed': False,
        'model_native_build_or_torch_jobs_run': False, 'main_report_modified': False}),
}
generated = OUT / 'generated-payloads'
assert not generated.exists()
generated.mkdir()
for name, raw in auxiliary.items():
    with (generated / name).open('xb') as stream:
        stream.write(raw)
    key = phase + '/' + name
    assert key not in payloads
    payloads[key] = raw
    sources[key] = {'source_path': str(generated / name), 'reason': 'Generated bounded selection, exact preservation, data/source lineage and qualification metadata',
                    'source_kind': 'collection_generated_metadata', 'observation': {'captured_bytes': len(raw), 'complete_source_at_snapshot': True}}

manifest = copy.deepcopy(old_manifest)
for name, raw in sorted(payloads.items()):
    source = sources[name]
    manifest['files'].append({'path': name, 'source_path_historical': source['source_path'], 'bytes': len(raw), 'sha256': digest(raw),
        'scope': source['reason'], 'source_kind': source['source_kind'], 'observation': source['observation'],
        'collection_phase': phase.rsplit('/', 1)[-1]})
manifest['phases'].append({'id': phase.rsplit('/', 1)[-1], 'captured_utc': stamp, 'source_files_collected': len(payloads),
    'source_snapshot_bytes_added': sum(map(len, payloads.values())),
    'qualification': 'Completed V8 source8c609/3234/405-step eta1, original184-F32 native adapter and originalF16 retired500:492 joint,498 faithful,493 clean,1 critical. Not99percent, fresh, Windows, whole-app or new resource qualification.'})
manifest['completed_v8_status'] = {'training_steps': 405, 'microbatches': 809, 'assistant_tokens': 55612,
    'canonical_event_exposures': 64, 'joint_count': 492, 'faithful_count': 498, 'clean_count': 493, 'critical_errors': 1,
    'quality_gate_passed': False, 'actual_cache_configuration': 'f16/f16', 'all500_delivered_once': True,
    'actual_optimizer_digest_captured_at_export_not_original_verifier': True,
    'current_interpolation_or_unused80_3394_collected': False, 'resource_windows_or_whole_app_qualified': False}
new_manifest = encode(manifest)
addition = ('\n\n## Completed V8 training and native development evaluation\n\n'
    'V8 completed405 updates/809 microbatches/55,612 assistant tokens on the full3234-row curriculum, continuing from V7 UL parent8855 with a fresh optimizer and eta1. Full data ledgers and approved240 raw/Core/author/review lineage are preserved, with exact older2754/2014/270/100/approved32 references. The original pre-model schema failure and corrected11-test export trace remain explicit; the optimizer digest was captured at export preflight.\n\n'
    'The unmerged184-F32 native adapter11ec at external scale1 completed all500 original retired-development Core cases once using actualF16 KV. Named semantic reviews record492/500 joint,498 faithful,493 clean and one critical error, below495/500. Root28 actual crosspairs and the independent moderate-scope C076/C112 adjudication are retained alongside strict prior-pass inheritance proofs. These are not500 new personal reads, fresh/population accuracy, Windows/whole-app execution or a new resource-SLA qualification. Current interpolation and unused80/3394 are excluded. See [' + phase + '/README.md](' + phase + '/README.md).\n').encode('utf-8')
new_readme = old_bytes['README.md'] + addition
entries = {name: dict(entry) for name, entry in old_index['files'].items()}
for name, raw in payloads.items():
    assert name not in entries
    entries[name] = {'bytes': len(raw), 'sha256': digest(raw)}
entries['README.md'] = {'bytes': len(new_readme), 'sha256': digest(new_readme)}
entries['collection-manifest.json'] = {'bytes': len(new_manifest), 'sha256': digest(new_manifest)}
new_index = encode({**old_index, 'files': {name: entries[name] for name in sorted(entries)}})
growth = sum(map(len, payloads.values())) + len(new_readme) + len(new_manifest) + len(new_index) - sum(map(len, old_bytes.values()))
# Root explicitly allows21MB rather than dropping essential evidence if overhead exceeds20MB.
assert growth <= 21000000, growth
for name, raw in old_bytes.items():
    assert (CURATED / name).read_bytes() == raw
assert set(listing()) == set(old_files)
print(json.dumps({'precopy_growth_bytes': growth, 'new_phase_files': len(payloads), 'old_index': OLD_SHA}), flush=True)
phase_root.mkdir(parents=True)
for name, raw in sorted(payloads.items()):
    destination = CURATED / safe(name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(raw)
for name, raw in old_bytes.items():
    assert (CURATED / name).read_bytes() == raw
staging = OUT / 'derived-commit'
staging.mkdir()
for name, raw in (('README.md', new_readme), ('collection-manifest.json', new_manifest), ('evidence-files-sha256.json', new_index)):
    with (staging / name).open('xb') as stream:
        stream.write(raw)
    os.replace(staging / name, CURATED / name)

files = listing()
assert set(files) == set(entries) | {'evidence-files-sha256.json'}
for name, entry in entries.items():
    path = files[name]
    assert not path.is_symlink()
    raw = path.read_bytes()
    assert len(raw) == entry['bytes'] and digest(raw) == entry['sha256'], name
for name, entry in old_index['files'].items():
    if name not in DERIVED:
        assert entries[name] == entry
for name in DERIVED:
    assert (CURATED / phase / 'historical' / ('previous1300-' + name)).read_bytes() == old_bytes[name]
assert (CURATED / 'README.md').read_bytes().startswith(old_bytes['README.md'])
assert len(manifest['files']) == len(entries) - 2
assert len({row['path'] for row in manifest['files']}) == len(manifest['files'])
assert {row['path'] for row in manifest['files']} == set(entries) - {'README.md', 'collection-manifest.json'}
for row in manifest['files']:
    assert {'bytes': row['bytes'], 'sha256': row['sha256']} == entries[row['path']]
for member in plan['source_archive_members_and_reuse_map']:
    raw = (CURATED / member['available_payload_path']).read_bytes()
    assert len(raw) == member['bytes'] and digest(raw) == member['sha256']
archives = {name for name in old_index['files'] if name.endswith('.source-snapshot.tar.gz')}
archives.add(plan['source_archive']['path'])
assert len(archives) == 6
for name, path in files.items():
    assert not any(word in name.lower() for word in ('fresh', 'reserved', 'blind')), name
    assert path.suffix.lower() not in {'.gguf', '.safetensors', '.onnx', '.bin', '.pt', '.pth', '.dll', '.exe', '.so', '.zip', '.whl', '.pyc', '.pdb', '.nupkg'}, name
    if path.suffix.lower() == '.gz':
        assert name in archives
    raw = path.read_bytes()
    assert not raw.startswith((b'\x7fELF', b'MZ', b'GGUF', b'PK\x03\x04')), name
    if name in archives:
        with tarfile.open(path) as bundle:
            members = bundle.getmembers()
            assert len(members) == 40
            for member in members:
                safe(member.name)
                assert member.isfile()
                body = bundle.extractfile(member).read()
                body.decode('utf-8-sig')
                assert not body.startswith((b'\x7fELF', b'MZ', b'GGUF', b'PK\x03\x04'))
new_total = sum(path.stat().st_size for path in files.values())
assert new_total - OLD_TOTAL == growth
receipt = {'schema_version': 1, 'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'status': 'COMPLETED_V8_APPEND_CURRENT_INDEX_DATA_SOURCE_LINEAGE_OLD1300_PRESERVATION_VERIFIED', 'phase': phase,
    'approved_plan_sha256': PLAN_SHA, 'collector_sha256': digest(Path(__file__).read_bytes()),
    'previous_index_sha256': OLD_SHA, 'new_index_sha256': digest(new_index),
    'previous_file_count': OLD_COUNT, 'new_file_count': len(files), 'previous_bytes': OLD_TOTAL, 'new_bytes': new_total,
    'growth_bytes': growth, 'target_growth_cap_bytes': 20000000, 'authorized_contingency_growth_cap_bytes': 21000000,
    'target20MB_met': growth <= 20000000, 'old1297_raw_files_unchanged': True,
    'previous_three_derived_snapshots_exact': True, 'readme_complete_previous_prefix_preserved': True,
    'all_current_index_manifest_hashes_verified': True, 'all10_original_duplicate_source_config_bodies_byte_verified': True,
    'full_actual3234_and_exact_old2754_prefix_verified': True, 'all480_source240_exposure_rows_full_fields_order_verified': True,
    'all240_raw_core_author_review_lineage_retained': True, 'all40_new_source_member_payload_references_verified': True,
    'original_V8_archive69a975_retained': True, 'all_six_total_source_archives_text_only_verified': True,
    'full405_canonical_and_raw_logs_and_console_retained': True, 'last_durable400_rng_not_final405_claim': True,
    'optimizer1edba_capture_at_export_not_original_verifier_retained': True,
    'original_pre_model_failure_corrected11_test_export_retained': True,
    'all500_delivered_once_no_Failed_verified': True, 'joint492_faithful498_clean493_critical1_verified': True,
    'quality_gate_passed': False, 'root28_crosspairs_and_C076C112_moderate_scope_retained': True,
    'current_interpolation_unused80_3394_models_binaries_or_optimizer_RNG_bytes_collected': False,
    'main_report_modified': False, 'model_native_build_converter_or_torch_jobs_run': False,
    'git_commit_or_publication_performed': False}
with (OUT / 'application-receipt.json').open('x') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
with (OUT / 'force-add-paths.txt').open('x') as stream:
    for name in sorted(payloads):
        stream.write(str((CURATED / name).relative_to(REPO)) + '\n')
    for name in DERIVED:
        stream.write(str((CURATED / name).relative_to(REPO)) + '\n')
print(json.dumps(receipt, indent=2))
