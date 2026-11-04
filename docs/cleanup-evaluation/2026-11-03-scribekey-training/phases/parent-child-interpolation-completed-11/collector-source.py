#!/usr/bin/env python3
"""Apply approved completed-interpolation text/source evidence plan, append only."""
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
PLAN_SHA = 'ab6c5ee61d8a6fd58b8ceeb8229d22f6e28ed2b4ad3843b0ba270d1f557779c2'
OLD_SHA = '1726e30eebd6ba5b2a96c5ae08e8ad54238250b8c4e42d98f53f113b6d0c5f86'
OLD_COUNT = 1476
OLD_TOTAL = 98610356
DERIVED = ('README.md', 'collection-manifest.json', 'evidence-files-sha256.json')
LABELS = {'t050': (.5, 487, 492, 494, 7), 't075': (.75, 489, 495, 493, 4), 't0875': (.875, 490, 497, 492, 2)}


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
assert phase == 'phases/parent-child-interpolation-completed-11'
phase_root = CURATED / phase
assert not phase_root.exists(), 'Never overwrite a previous collection or retry'
assert plan['within_budget'] and plan['projected_new_growth_bytes'] <= 20000000
old_bytes = {name: (CURATED / name).read_bytes() for name in DERIVED}
assert digest(old_bytes['evidence-files-sha256.json']) == OLD_SHA
old_index = json.loads(old_bytes['evidence-files-sha256.json'])
old_manifest = json.loads(old_bytes['collection-manifest.json'])
old_files = listing()
assert len(old_files) == OLD_COUNT
assert set(old_files) == set(old_index['files']) | {'evidence-files-sha256.json'}
assert sum(path.stat().st_size for path in old_files.values()) == OLD_TOTAL
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
        assert path.suffix.lower() in {'.py', '.json', '.jsonl', '.md', '.txt', '.log', '.cs', '.csproj', '.props', '.config', '.ps1'} or path.name in {'LICENSE', 'NOTICE'} or path.name.endswith('.source-snapshot.tar.gz')
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
    if not name.endswith('.source-snapshot.tar.gz'):
        raw.decode('utf-8-sig')
        assert not raw.startswith((b'\x7fELF', b'MZ', b'GGUF', b'PK\x03\x04'))
    payloads[name] = raw
    sources[name] = {'source_path': source_name, 'reason': row['reason'],
        'source_kind': row.get('source_kind', 'completed_text_evidence'), 'observation': observation}
    source_hash_receipt.append({'path': name, 'bytes': len(raw), 'sha256': value, 'planned_hash_status': row['hash_status']})
for row in plan['historical_previous1476_snapshots']:
    name = Path(row['source_path']).name
    raw = old_bytes[name]
    assert len(raw) == row['bytes'] and digest(raw) == row['sha256']
    payloads[row['destination']] = raw
    sources[row['destination']] = {'source_path': str(CURATED / name), 'reason': 'Exact previous1476 derived-document epoch before append',
        'source_kind': 'historical_derived_snapshot', 'observation': {'captured_bytes': len(raw), 'complete_source_at_snapshot': True}}


def payload(name):
    value = payloads.get(name)
    return value if value is not None else (CURATED / name).read_bytes()


for row in plan['endpoint_and_existing_V7_V8_history_references']:
    raw = payload(row['available_payload_path'])
    assert len(raw) == row['bytes'] and digest(raw) == row['sha256']
for row in plan['actual_small_external_dependency_references']:
    if row['available_payload_path'] is not None:
        raw = payload(row['available_payload_path'])
        assert len(raw) == row['bytes'] and digest(raw) == row['sha256']
    else:
        assert row['reuse'] == 'large_unchanged_original_tokenizer_hash_reference_only_not_read'


def get(relative):
    return payloads[phase + '/' + relative]


base = 'completed-experiment/'
release = json.loads(get(base + 'derivation-release.json'))
selection = json.loads(get(base + 'reviewed-selection.json'))
upfront = json.loads(get(base + 'full500-run-01/all-three-frozen-before-inference.json'))
handoff = json.loads(get(base + 'full500-run-01/handoff-integrity.json'))
assert digest(get(base + 'derivation-release.json')) == '9774aad5ff40d30fccac4a8bb31eb3167ef1e55def12d712e76f5f9684f8a6ab'
assert digest(get(base + 'reviewed-selection.json')) == '3aeefbc199e63d1e754220f29e5d52193b03554da055cdca996c023cfee1db1f'
assert release['optimizer_steps_per_derivation'] == 0
assert handoff['all1500_cases_complete_and_delivered_once'] is True
assert handoff['all_source_derivation_history_model_runtime_cache_and_owned_argv_postchecks_passed'] is True
assert set(upfront) == set(LABELS)
baseline_ref = next(row for row in plan['endpoint_and_existing_V7_V8_history_references'] if row['purpose'] == 'selected_V8_baseline_full500')
baseline = json.loads(payload(baseline_ref['available_payload_path']))
baseline_cases = baseline['cases']
endpoint_hashes = {'parent': {'config': 'b86205448c05f0948da0e59f0c59818e338fce50f2ef56e1a78d92a05f09bfb6',
    'result': 'd3b8a8a14239b3d11aa80178d0213daf6a1dacc1b638a11a1d111e0750293523', 'steps': 345},
    'child': {'config': '2637946ed089eb5c1b53371def45af9b67380c7a2089d40f2bb29cca8ff1cdb9',
    'result': '5a0a23a2c52b12f9913a64e4dd0e18544bd1b0a763f50e1ae610f52eaf4db927', 'steps': 405}}
verification = {}
freezes = []
starts = []
for label, (fraction, joint, faithful, clean, critical) in LABELS.items():
    prefix = base + label + '/'
    derivation_bytes = get(prefix + 'derivation/DERIVATION.json')
    derivation = json.loads(derivation_bytes)
    config_bytes = get(prefix + 'derivation/minimal-derived-adapter-config.json')
    config = json.loads(config_bytes)
    assert derivation['kind'] == 'parent-child-factor-derivation-not-training'
    assert type(derivation['optimizer_steps_performed']) is int and derivation['optimizer_steps_performed'] == 0
    assert derivation['child_fraction'] == fraction and derivation['parent_fraction'] == 1 - fraction
    assert derivation['formula'] == 'A_t=(1-t)A_parent+tA_child; B_t=(1-t)B_parent+tB_child; delta=2B_tA_t'
    assert derivation['exact_delta_or_functional_averaging_claimed'] is False
    assert not set(config).intersection({'optimizer', 'steps', 'seed', 'epochs', 'planned_execution_steps', 'schedule_total_optimizer_steps', 'resume_optimizer', 'training_source_sha256'})
    assert config['artifact_kind'] == 'derived_lora_adapter_not_optimizer_checkpoint'
    assert config['rank'] == 8 and config['alpha'] == 16 and config['scaling'] == 2
    assert config['runtime_adapter_scale'] == 1 and len(config['target_modules']) == 92
    for role, expected in endpoint_hashes.items():
        original_config = get(prefix + 'derivation/' + role + '-adapter-config.json')
        original_result = get(prefix + 'derivation/' + role + '-historical-training-result.json')
        assert digest(original_config) == expected['config'] and digest(original_result) == expected['result']
        assert json.loads(original_result)['steps'] == expected['steps']
        history = next(row for row in derivation['endpoint_histories'] if row['role'] == role)
        assert history['declared_training_history'] == json.loads(original_config)
    for pin in derivation['inherited_notices']:
        raw = get(prefix + 'derivation/inherited-notices/' + Path(pin['path']).name)
        assert len(raw) == pin['bytes'] and digest(raw) == pin['sha256']
    conversion = json.loads(get(prefix + 'conversion/conversion-report.json'))
    assert conversion['optimizer_steps_performed'] == 0 and conversion['child_fraction'] == fraction
    assert conversion['derivation']['sha256'] == digest(derivation_bytes)
    assert conversion['minimal_config']['sha256'] == digest(config_bytes)
    assert conversion['all184_F32_bytes_identical'] is True
    assert conversion['embedded_alpha_div_rank'] == 2 and conversion['external_native_scale'] == 1
    assert conversion['merge_or_requantization_performed'] is False
    assert len(conversion['tensors']) == len(derivation['tensor_sha256']) == 184
    assert len({row['custom_key'] for row in conversion['tensors']}) == 184
    assert len({row['gguf_name'] for row in conversion['tensors']}) == 184
    for row in conversion['tensors']:
        assert row['dtype'] == 'F32' and row['custom_PEFT_GGUF_payloads_identical'] is True
        assert row['tensor_data_sha256'] == derivation['tensor_sha256'][row['custom_key']]
    report_bytes = get(prefix + 'core/core-results.json')
    report = json.loads(report_bytes)
    review_bytes = get(prefix + 'reviews/canonical-reviewed.json')
    review = json.loads(review_bytes)
    summary = json.loads(get(prefix + 'reviews/canonical-semantic-summary.json'))
    assert report['incomplete'] is False and len(report['cases']) == 500
    assert len({row['id'] for row in report['cases']}) == 500
    assert summary['results_sha256'] == digest(report_bytes) == review['results_sha256']
    assert summary['canonical_review_sha256'] == digest(review_bytes)
    assert handoff['candidates'][label]['report']['sha256'] == digest(report_bytes)
    assert [row['case_id'] for row in review['cases']] == [row['id'] for row in report['cases']] == [row['id'] for row in baseline_cases]
    for actual, judged, prior in zip(report['cases'], review['cases'], baseline_cases):
        assert actual['normalized_input'] == prior['normalized_input'] and actual['normalized_targets'] == prior['normalized_targets']
        assert actual['insertion_count'] == actual['delivered_count'] == 1
        assert actual['delivery_outcome'] == 'Delivered' and actual['error'] is None
        assert actual['cleanup_status'] in ('Applied', 'Unchanged')
        assert judged['output_sha256'] == digest(actual['output'].encode('utf-8'))
    assert sum(row['semantic_faithful'] for row in review['cases']) == summary['faithful'] == faithful
    assert sum(row['clean_usable'] for row in review['cases']) == summary['clean_usable'] == clean
    assert sum(row['semantic_faithful'] and row['clean_usable'] for row in review['cases']) == summary['faithful_and_clean_usable'] == joint
    assert sum(row['critical_error'] for row in review['cases']) == summary['critical_errors'] == critical
    assert summary['quality_gate_passed'] is False
    cross = json.loads(get(prefix + 'reviews/root-seven-middle-cross-read.json'))
    assert cross['results_sha256'] == digest(report_bytes) and cross['canonical_review_sha256'] == digest(review_bytes)
    assert len(cross['cases']) == 7
    by_id = {row['id']: row for row in report['cases']}
    for row in cross['cases']:
        actual = by_id[row['case_id']]
        assert row['normalized_input'] == actual['normalized_input'] and row['output'] == actual['output']
        assert row['candidate_text_equals_final_output'] is True and actual['candidate_text'] == actual['output']
        assert row['root_actually_read_source_and_output'] is True and row['root_agrees_with_canonical'] is True
    freeze_bytes = get(prefix + 'candidate-freeze.json')
    freeze = json.loads(freeze_bytes)
    assert upfront[label]['freeze']['sha256'] == digest(freeze_bytes)
    assert freeze['runtime_adapter'] == conversion['native_adapter'] == upfront[label]['native']
    assert freeze['profile']['cacheTypeK'] == freeze['profile']['cacheTypeV'] == 'f16'
    freezes.append(datetime.datetime.fromisoformat(freeze['created_utc'].replace('Z', '+00:00')))
    starts.append(datetime.datetime.fromisoformat(report['metadata']['started_at_utc'].replace('Z', '+00:00')))
    verification[label] = {'child_fraction': fraction, 'report_sha256': digest(report_bytes), 'canonical_review_sha256': digest(review_bytes),
        'joint': joint, 'faithful': faithful, 'clean': clean, 'critical_errors': critical, 'all500_delivered_once': True,
        'actual_F16_cache': True, 'zero_new_optimizer_steps': True, 'historical_parent_steps': 345, 'historical_child_steps': 405,
        'all184_conversion_value_hashes_match_derivation_receipt': True, 'collector_loaded_tensor_payloads': False,
        'root_seven_crosspairs_actual_bytes_match_report': True}
assert max(freezes) < min(starts)
assert selection['selected'] == 'V8' and selection['selected_joint'] == 492 and selection['qualified'] is False
for row in selection['derived_candidates']:
    verified = verification[row['label']]
    assert (row['child_fraction'], row['faithful_and_clean_usable'], row['faithful'], row['clean_usable'], row['critical_errors'], row['canonical_review_sha256']) == (
        verified['child_fraction'], verified['joint'], verified['faithful'], verified['clean'], verified['critical_errors'], verified['canonical_review_sha256'])
assert max(item['joint'] for item in verification.values()) < selection['baseline']['joint'] == 492
for member in plan['source_archive_members_and_reuse_map']:
    raw = payload(member['available_payload_path'])
    assert len(raw) == member['bytes'] and digest(raw) == member['sha256']

readme = '''# Completed parent-child factor interpolation

Three fixed child fractions0.5,0.75 and0.875 interpolate both rank8 LoRA factors between the completed V7 UL parent8855 and V8 child0ad0. These are F32 factor derivations with **zero new optimizer steps**. They are not exact update/function averaging: the factor product includes the recorded cross term. The actual parent345-step and child405-step training histories/configs/results remain separate, with direct byte-verified references to earlier curated V7/V8 evidence. Minimal derived configs do not inherit fabricated training, optimizer or RNG identity.

The complete derivation release9774, DERIVATION records, sources4baf/unchanged57c, deterministic F32/no-FMA math, schema/tiny-test traces, endpoint histories and original legal notices are retained. The reported independent math/guard PASS existed only in pre-execution collaborator messages. The owner's full500 plan91a998 records that report and is not an independently authored receipt; no independent guard-review file is invented. The formal independently authored wrapper/source/metadata audit30bc is preserved separately.

Earlier matched-arm and subset-screen plans are preserved as unused chronology. Root superseded them **before inference** with exactly three serial full retired500 Core runs. No subset ran and no additional coefficient search is represented. All three derived adapters were converted and frozen before the first native500 case. Conversion receipts bind all184 finite F32 custom/PEFT/native tensor-value hashes, rank8/alpha16/internal2/external1, originalIQ4 base82ab, no merge or requantization. The collector verifies those metadata bindings; it does not reread weight/tensor payloads.

All1500 original ordered cases, actualF16 cache profiles, full raw reports/logs, durable owned native-argv journals, upfront freezes, source/managed/runtime pins and deployment postchecks remain available. Every case delivered once with no provider Failed result. All three semantic-review shards, actual-read records, strict prior-pass inheritance proofs, root seven-middle-pair cross-read receipts and the predeclared final selection are retained.

| Child fraction | Faithful and clean | Faithful | Clean | Critical errors |
| --- | ---: | ---: | ---: | ---: |
|0.5|487/500|492|494|7|
|0.75|489/500|495|493|4|
|0.875|490/500|497|492|2|
|Original V8 baseline, selected|492/500|498|493|1|

The predeclared order is highest joint, fewer critical errors, higher faithful, higher clean, then higher child fraction. All interpolations lose to V8 and fail495/500. Exact prior-pass inheritance is transparent; these records are not a claim of1500 newly personal semantic reads. The root cross-read records keep the t0875b090 grammar/faithfulness nuance explicit without inventing a canonical override.

All three exact original source archives are retained separately even though their bytes match. Each has39 frozen source files plus a text hash manifest; all120 member references are byte-verified against available curated bodies. No changing source replaces the executed epoch8c609.

This phase makes no99percent, fresh/population, resource-SLA, Windows/GPU or whole-app qualification claim. Active V9, extra100/future training data, weights, DLLs/native binaries and optimizer/RNG caches are excluded. No model, native, conversion, training, Torch or build job is run. All prior1476 files are preserved, with exact prior derived snapshots and the complete previous README prefix. The root-owned main report is not edited.
'''.encode('utf-8')
stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
auxiliary = {
    'README.md': readme,
    'selection-plan.json': plan_bytes,
    'collector-source.py': Path(__file__).read_bytes(),
    'inventory-plan-source.py': (OUT / 'prepare_plan.py').read_bytes(),
    'source-lineage-map.json': encode({'schema_version': 1, 'archives': plan['original_three_source_archives'],
        'members': plan['source_archive_members_and_reuse_map'], 'captured_trainer_source': '8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad'}),
    'endpoint-history-and-conversion-dependency-references.json': encode({'schema_version': 1,
        'endpoints_and_prior_V7_V8': plan['endpoint_and_existing_V7_V8_history_references'],
        'dependencies': plan['actual_small_external_dependency_references'], 'all_available_payload_references_verified': True,
        'original_tokenizer_hash_only_not_reread': True}),
    'completed-three-cohort-and-selection-verification.json': encode({'schema_version': 1,
        'candidates': verification, 'all_three_frozen_before_any_case': True, 'all1500_delivered_once': True,
        'selected': selection['selected'], 'quality_gate_passed': False,
        'tensor_value_hashes_from_actual_execution_receipts_not_recomputed_from_weights_by_collector': True}),
    'chronology-and-assessment-provenance.json': encode({'schema_version': 1,
        'matched_arm_proposal_executed': False, 'subset_screen_executed': False,
        'full500_plan_superseded_subset_before_inference': True,
        'independent_math_guard_PASS': 'Reported only in pre-execution collaborator messages; owner plan91a998 is not independently authored; no saved independent guard receipt exists',
        'formal_saved_independent_wrapper_audit': 'conversion-wrapper-source-tests-audit/independent-preexecution-review.json',
        'no_additional_coefficient_search': True}),
    'previous1476-preservation.json': encode({'schema_version': 1, 'old_index_sha256': OLD_SHA, 'old_file_count': OLD_COUNT,
        'old_total_bytes': OLD_TOTAL, 'all_prior_hashes_verified_before_copy': True, 'historical_derived_snapshots': plan['historical_previous1476_snapshots']}),
    'authorized-source-hash-receipt.json': encode({'schema_version': 1, 'scope': 'Completed interpolation text/source/report evidence only; no model/binary, activeV9 or future-data reads', 'files': source_hash_receipt}),
    'scope-and-exclusions.json': encode({'schema_version': 1, 'qualification': plan['factual_qualifications'],
        'excluded': plan['excluded'], 'quality_gate_passed': False, 'model_native_build_or_torch_jobs_run': False, 'main_report_modified': False}),
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
    sources[key] = {'source_path': str(generated / name), 'reason': 'Generated bounded selection, honest chronology, exact old preservation, source/history lineage and qualification metadata',
        'source_kind': 'collection_generated_metadata', 'observation': {'captured_bytes': len(raw), 'complete_source_at_snapshot': True}}

manifest = copy.deepcopy(old_manifest)
for name, raw in sorted(payloads.items()):
    source = sources[name]
    manifest['files'].append({'path': name, 'source_path_historical': source['source_path'], 'bytes': len(raw), 'sha256': digest(raw),
        'scope': source['reason'], 'source_kind': source['source_kind'], 'observation': source['observation'], 'collection_phase': phase.rsplit('/', 1)[-1]})
manifest['phases'].append({'id': phase.rsplit('/', 1)[-1], 'captured_utc': stamp, 'source_files_collected': len(payloads),
    'source_snapshot_bytes_added': sum(map(len, payloads.values())),
    'qualification': 'Three zero-new-step factor derivations with full original500 each:487/489/490 joint and7/4/2 critical. V8 baseline492 remains selected. Subset proposal unused; guard PASS reported-only, formal wrapper audit saved. No accuracy/resource/Windows qualification.'})
manifest['completed_parent_child_interpolation_status'] = {'child_fractions': [.5, .75, .875], 'new_optimizer_steps_each': 0,
    'joint_counts': [487, 489, 490], 'critical_error_counts': [7, 4, 2], 'all1500_delivered_once': True,
    'selected': 'V8', 'selected_joint': 492, 'quality_gate_passed': False,
    'subset_screen_executed': False, 'guard_assessment_reported_only_no_saved_independent_guard_receipt': True,
    'formal_saved_independent_wrapper_audit_retained': True, 'activeV9_collected': False,
    'resource_windows_or_whole_app_qualified': False}
new_manifest = encode(manifest)
addition = ('\n\n## Completed parent-child factor interpolation\n\n'
    'Three fixed child fractions0.5/0.75/0.875 derived both rank8 factors from the completed V7 UL parent and V8 child with zero new optimizer steps. All three were converted/frozen before their serial full original500 Core runs; the earlier subset and matched-arm proposals remain unused chronology. Semantic results are487/489/490 joint with7/4/2 critical errors, so the predeclared selection retains V8 at492/500, below495/500. Full derivation/conversion/legal/source, all1500 actual outcomes, owned argv/postchecks, shard reviews/inheritance proofs and root cross-read records are preserved. The independent math-guard PASS was reported only in collaborator messages/owner plan; the distinct formal saved wrapper audit is retained. No new resource, Windows, whole-app or fresh/population qualification is claimed. See [' + phase + '/README.md](' + phase + '/README.md).\n').encode('utf-8')
new_readme = old_bytes['README.md'] + addition
entries = {name: dict(entry) for name, entry in old_index['files'].items()}
for name, raw in payloads.items():
    assert name not in entries
    entries[name] = {'bytes': len(raw), 'sha256': digest(raw)}
entries['README.md'] = {'bytes': len(new_readme), 'sha256': digest(new_readme)}
entries['collection-manifest.json'] = {'bytes': len(new_manifest), 'sha256': digest(new_manifest)}
new_index = encode({**old_index, 'files': {name: entries[name] for name in sorted(entries)}})
growth = sum(map(len, payloads.values())) + len(new_readme) + len(new_manifest) + len(new_index) - sum(map(len, old_bytes.values()))
assert growth <= 20000000 and growth <= plan['projected_new_growth_bytes'], growth
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
    assert (CURATED / phase / 'historical' / ('previous1476-' + name)).read_bytes() == old_bytes[name]
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
archives.update(row['path'] for row in plan['original_three_source_archives'])
assert len(archives) == 9
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
    'status': 'COMPLETED_INTERPOLATION_APPEND_CURRENT_INDEX_SOURCE_HISTORY_SEMANTIC_LINEAGE_OLD1476_PRESERVATION_VERIFIED',
    'phase': phase, 'approved_plan_sha256': PLAN_SHA, 'collector_sha256': digest(Path(__file__).read_bytes()),
    'previous_index_sha256': OLD_SHA, 'new_index_sha256': digest(new_index),
    'previous_file_count': OLD_COUNT, 'new_file_count': len(files), 'previous_bytes': OLD_TOTAL, 'new_bytes': new_total,
    'growth_bytes': growth, 'growth_cap_bytes': 20000000, 'old1473_raw_files_unchanged': True,
    'previous_three_derived_snapshots_exact': True, 'readme_complete_previous_prefix_preserved': True,
    'all_current_index_manifest_hashes_verified': True, 'all_endpoint_history_and_available_dependency_references_verified': True,
    'all_three_zero_new_step_derivations_true345_405_histories_and_original_notices_retained': True,
    'all184_value_hashes_per_conversion_match_derivation_execution_metadata': True, 'tensor_or_weight_payloads_rehashed_by_collector': False,
    'all_three_frozen_before_first_native_case_verified': True, 'all1500_full_ordered_cases_delivered_once_no_Failed_verified': True,
    'all_three_canonical_reviews_output_hash_counts_and_seven_actual_root_crosspairs_verified': True,
    'joint487_489_490_critical7_4_2_and_V8_selected492_verified': True,
    'matched_arm_and_subset_proposals_unused_no_replay_or_new_coefficient_search': True,
    'reported_only_guard_assessment_not_fabricated_independent_artifact': True,
    'formal_saved_independent_wrapper_audit_retained': True, 'all120_new_source_member_references_verified': True,
    'original_three_archives_preserved_and_all_nine_total_archives_text_only_verified': True,
    'quality_gate_passed': False, 'activeV9_extra100_models_binaries_optimizer_or_RNG_bytes_collected': False,
    'main_report_modified': False, 'model_native_build_converter_or_torch_jobs_run': False, 'git_commit_or_publication_performed': False}
with (OUT / 'application-receipt.json').open('x') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
with (OUT / 'force-add-paths.txt').open('x') as stream:
    for name in sorted(payloads):
        stream.write(str((CURATED / name).relative_to(REPO)) + '\n')
    for name in DERIVED:
        stream.write(str((CURATED / name).relative_to(REPO)) + '\n')
print(json.dumps(receipt, indent=2))
