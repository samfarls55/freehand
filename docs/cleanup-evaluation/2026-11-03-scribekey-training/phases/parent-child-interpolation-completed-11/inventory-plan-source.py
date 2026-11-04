#!/usr/bin/env python3
"""Plan-only inventory of completed parent-child factor interpolation evidence."""
from pathlib import Path, PurePosixPath
import datetime
import hashlib
import json
import tarfile

REPO = Path('/workspace/freehand')
TASK = REPO / 'work/cleanup-scribekey-training-2026-11-03'
CURATED = REPO / 'docs/cleanup-evaluation/2026-11-03-scribekey-training'
OUT = Path(__file__).resolve().parent
PHASE = 'phases/parent-child-interpolation-completed-11'
EXPECTED_INDEX = '1726e30eebd6ba5b2a96c5ae08e8ad54238250b8c4e42d98f53f113b6d0c5f86'
EXPERIMENT = TASK / 'parent-child-interpolation'
DERIVE = TASK / 'adapter-average-preparation'
WRAPPER = TASK / 'parent-child-conversion-preparation'
ALLOWED = {'.py', '.json', '.jsonl', '.md', '.txt', '.log', '.cs', '.csproj', '.props', '.config', '.ps1'}
SPECIAL_TEXT_NAMES = {'LICENSE', 'NOTICE'}
LABELS = {'t050': .5, 't075': .75, 't0875': .875}
selected = {}
known = {}
bytes_hashed_now = 0


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_metadata(path):
    assert path.stat().st_size <= 65536
    return json.loads(path.read_bytes())


def allowed(path):
    return path.suffix.lower() in ALLOWED or path.name in SPECIAL_TEXT_NAMES or path.name.endswith('.source-snapshot.tar.gz')


def record_pins(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str) and len(value['sha256']) == 64:
            size = value.get('bytes', value.get('size'))
            if type(size) is int:
                known.setdefault(value['path'], []).append({'bytes': size, 'sha256': value['sha256']})
        for child in value.values():
            record_pins(child)
    elif isinstance(value, list):
        for child in value:
            record_pins(child)


index_bytes = (CURATED / 'evidence-files-sha256.json').read_bytes()
assert digest(index_bytes) == EXPECTED_INDEX
old_index = json.loads(index_bytes)
assert len(old_index['files']) + 1 == 1476
old_by_sha = {}
for name, entry in old_index['files'].items():
    old_by_sha.setdefault(entry['sha256'], name)
for root in (EXPERIMENT, DERIVE, WRAPPER):
    for path in root.rglob('*.json'):
        if path.is_file() and path.stat().st_size <= 65536:
            record_pins(read_metadata(path))


def add(source, relative, group, reason):
    global bytes_hashed_now
    source = Path(source)
    assert source.is_file() and not source.is_symlink()
    name = PurePosixPath(relative)
    assert not name.is_absolute() and '..' not in name.parts
    assert not any(word in relative.casefold() for word in ('fresh', 'reserved', 'blind'))
    assert allowed(source), str(source)
    assert not any(word in str(source).casefold() for word in ('v9-', '3394', 'reserved80', 'additional-100'))
    size = source.stat().st_size
    expected = None
    status = 'deferred_full_text_hash_until_authorized_copy'
    if size <= 65536:
        raw = source.read_bytes()
        expected = digest(raw)
        bytes_hashed_now += len(raw)
        status = 'small_source_or_metadata_hashed_now'
    else:
        matches = known.get(str(source), [])
        if not matches:
            matches = [item for path, entries in known.items() if Path(path).name == source.name
                       for item in entries if item['bytes'] == size]
        hashes = {item['sha256'] for item in matches if item['bytes'] == size}
        if len(hashes) == 1:
            expected = next(iter(hashes))
            status = 'expected_pin_from_completed_small_receipt_not_rehashed_now'
    key = PHASE + '/' + relative
    assert key not in selected
    selected[key] = {'path': key, 'source_path': str(source), 'bytes': size,
        'expected_sha256': expected, 'hash_status': status, 'group': group, 'reason': reason}
    return key


def tree(root, destination, group, reason):
    for path in sorted(Path(root).rglob('*')):
        if path.is_file() and allowed(path):
            add(path, destination + '/' + path.relative_to(root).as_posix(), group, reason)


tree(EXPERIMENT, 'completed-experiment', 'completed_derivation_conversion_three500_and_reviews',
    'Complete actual three fixed factor derivations, zero-step histories/notices, exact184-F32 conversion traces, all first-only500 cases, owned argv journals, frozen sources, all three semantic shards/inheritance proofs and final selection')
tree(DERIVE, 'derivation-source-and-preexecution-chronology', 'derivation_sources_tests_superseded_plans',
    'Executed parent-child guard4baf and unchanged original matched-arm helper57c, schema/math/finite-value tiny tests and legal source pins; earlier matched-arm/subset proposals are unused history, superseded before any native inference by explicit full500 plan')
tree(WRAPPER, 'conversion-wrapper-source-tests-audit', 'wrapper_sources_tests_independent_audit',
    'Exact executed wrapper6770, nine synthetic guards, independent preexecution metadata/source review30bc and preparation trace; no active trainer source')
release = read_metadata(EXPERIMENT / 'derivation-release.json')
assert release['optimizer_steps_per_derivation'] == 0
assert release['all_184_F32_payloads_finite_shape_hash_verified'] is True
assert digest((EXPERIMENT / 'derivation-release.json').read_bytes()) == '9774aad5ff40d30fccac4a8bb31eb3167ef1e55def12d712e76f5f9684f8a6ab'
for item in release['candidates']:
    assert LABELS[item['label']] == item['child_fraction']
    path = Path(item['config']['path'])
    key = add(path, 'completed-experiment/' + item['label'] + '/derivation/minimal-derived-adapter-config.json',
        'actual_minimal_zero_step_configs',
        'Actual minimal derived-adapter config used by conversion/freeze, forbids invented optimizer/training counters; endpoint345/405 histories are separate')
    assert selected[key]['expected_sha256'] == item['config']['sha256']

# Resolve all actual small external pre-run dependencies to archived bodies where possible.
# No weight, tokenizer, DLL, native executable or original adapter bytes are read.
dependency_refs = []
pre_run = read_metadata(EXPERIMENT / 'full500-run-01/pre-run.json')
selected_by_sha = {row['expected_sha256']: row['path'] for row in selected.values() if row.get('expected_sha256')}
for pin in pre_run['pins']:
    path = Path(pin['path'])
    if path.suffix.lower() not in ALLOWED and path.name not in SPECIAL_TEXT_NAMES:
        continue
    if pin['sha256'] in old_by_sha:
        destination, reuse = old_by_sha[pin['sha256']], 'existing1476_identical_payload'
    elif pin['sha256'] in selected_by_sha:
        destination, reuse = selected_by_sha[pin['sha256']], 'new_selected_identical_payload'
    elif pin['bytes'] <= 65536:
        destination = add(path, 'shared-small-conversion-dependencies/' + path.name,
            'small_exact_conversion_dependency_sources',
            'Actual pre-run pinned small source/metadata dependency absent from prior curated payloads; no changing or unpinned source substitution')
        assert selected[destination]['expected_sha256'] == pin['sha256']
        selected_by_sha[pin['sha256']] = destination
        reuse = 'new_small_exact_pre_run_dependency'
    else:
        # The original tokenizer is a hash-only external dependency, not a newly authored corpus.
        assert path.name == 'tokenizer.json' and pin['bytes'] == 4733389
        destination, reuse = None, 'large_unchanged_original_tokenizer_hash_reference_only_not_read'
    dependency_refs.append({**pin, 'available_payload_path': destination, 'reuse': reuse})

# Explicit references bind the true endpoint histories and selected V8 baseline to old phases.
endpoint_refs = []
for label, sha in (
    ('V7_UL_parent_config_345_historical_steps', 'b86205448c05f0948da0e59f0c59818e338fce50f2ef56e1a78d92a05f09bfb6'),
    ('V7_UL_parent_historical_training_result', 'd3b8a8a14239b3d11aa80178d0213daf6a1dacc1b638a11a1d111e0750293523'),
    ('V8_child_config_405_historical_steps', '2637946ed089eb5c1b53371def45af9b67380c7a2089d40f2bb29cca8ff1cdb9'),
    ('V8_child_historical_training_result', '5a0a23a2c52b12f9913a64e4dd0e18544bd1b0a763f50e1ae610f52eaf4db927'),
    ('actual_training_source8c609', '8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad'),
    ('V7_UL_parent2754_dataset', 'fa18dfcd5faf4c5a7a20f8e9b669caaa2ec3c8e098b27b17a25128eda1d592a6'),
    ('V8_child3234_dataset', '2fdab6a16b7c47a7e2bffd2d60208ad0b5ea9804048d28f2f184468fe33e757c'),
    ('selected_V8_baseline_full500', '7d492ecb55fb7dc1ef537f1b7c575fece3aad838ac5fff7ca17a2214ed6c3a70'),
    ('selected_V8_baseline_canonical492', 'fe07736284eda5a8b8425c90b537f217e7c984d94b7e2420d375c8c5e1bfdae7')):
    assert sha in old_by_sha, label
    name = old_by_sha[sha]
    endpoint_refs.append({'purpose': label, 'available_payload_path': name,
        'bytes': old_index['files'][name]['bytes'], 'sha256': sha})
for pin in read_metadata(DERIVE / 'legal-notice-sources.json'):
    assert pin['sha256'] in old_by_sha
    name = old_by_sha[pin['sha256']]
    endpoint_refs.append({'purpose': 'original_inherited_legal_notice', 'source_path': pin['path'],
        'available_payload_path': name, 'bytes': pin['bytes'], 'sha256': pin['sha256']})

source_members = []
archives = []
selected_by_sha = {row['expected_sha256']: row['path'] for row in selected.values() if row.get('expected_sha256')}
for label in LABELS:
    freeze = read_metadata(EXPERIMENT / label / 'candidate-freeze.json')
    entry = freeze['source_snapshot']
    archive = Path(entry['path'])
    raw = archive.read_bytes()
    bytes_hashed_now += len(raw)
    assert len(raw) == entry['bytes'] == 157786
    assert digest(raw) == entry['sha256'] == '76737a31a8240351e0b2a63a3fcad5d96f2ebdc7a151fbb27e58e6bf953c171a'
    destination = PHASE + '/completed-experiment/' + label + '/candidate-freeze.source-snapshot.tar.gz'
    selected[destination]['expected_sha256'] = entry['sha256']
    selected[destination]['hash_status'] = 'small_original_text_source_archive_hashed_now'
    archives.append({'label': label, 'path': destination, 'bytes': len(raw), 'sha256': entry['sha256'],
                     'original_archive_retained_separately': True})
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        assert len(members) == 40
        assert {member.name for member in members} == set(freeze['sources']) | {'source-files-sha256.json'}
        for member in members:
            name = PurePosixPath(member.name)
            assert member.isfile() and not name.is_absolute() and '..' not in name.parts
            body = bundle.extractfile(member).read()
            body.decode('utf-8-sig')
            assert not body.startswith((b'\x7fELF', b'MZ', b'GGUF', b'PK\x03\x04'))
            sha = digest(body)
            if member.name == 'source-files-sha256.json':
                assert json.loads(body)['files'] == freeze['sources']
            else:
                assert sha == freeze['sources'][member.name]
            if sha in old_by_sha:
                target, reuse = old_by_sha[sha], 'existing1476_identical_payload'
            elif sha in selected_by_sha:
                target, reuse = selected_by_sha[sha], 'new_selected_identical_payload'
            else:
                target, reuse = PHASE + '/source/executed-missing-text/' + member.name, 'new_original_archive_member_text'
                selected[target] = {'path': target, 'source_kind': 'text_source_archive_member',
                    'source_archive': str(archive), 'source_archive_sha256': entry['sha256'], 'archive_member': member.name,
                    'bytes': len(body), 'expected_sha256': sha, 'hash_status': 'small_archived_source_text_validated_now',
                    'group': 'missing_source_text', 'reason': 'Original frozen exact source text absent from existing curated payload bodies'}
                selected_by_sha[sha] = target
            source_members.append({'label': label, 'archive': destination, 'member': member.name,
                'bytes': len(body), 'sha256': sha, 'available_payload_path': target, 'reuse': reuse})
    assert freeze['sources']['tools/Freehand.Cleanup.Training/pipeline.py'] == '8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad'
    assert freeze['profile']['cacheTypeK'] == freeze['profile']['cacheTypeV'] == 'f16'

selection = read_metadata(EXPERIMENT / 'reviewed-selection.json')
assert selection['selected'] == 'V8' and selection['selected_joint'] == 492 and selection['qualified'] is False
assert digest((EXPERIMENT / 'reviewed-selection.json').read_bytes()) == '3aeefbc199e63d1e754220f29e5d52193b03554da055cdca996c023cfee1db1f'
for row in selection['derived_candidates']:
    assert LABELS[row['label']] == row['child_fraction']
    canonical = selected[PHASE + '/completed-experiment/' + row['label'] + '/reviews/canonical-reviewed.json']
    assert canonical['expected_sha256'] in (None, row['canonical_review_sha256'])
    canonical['expected_sha256'] = row['canonical_review_sha256']
    canonical['hash_status'] = 'completed_selection_expected_pin_not_rehashed_now'

snapshots = []
for name in ('README.md', 'collection-manifest.json', 'evidence-files-sha256.json'):
    pin = {'bytes': len(index_bytes), 'sha256': EXPECTED_INDEX} if name == 'evidence-files-sha256.json' else old_index['files'][name]
    snapshots.append({'source_path': str(CURATED / name), 'destination': PHASE + '/historical/previous1476-' + name,
        **pin, 'hash_status': 'current_index_epoch_pin_no_full_curated_rehash_during_plan'})
groups = {}
for row in selected.values():
    item = groups.setdefault(row['group'], {'files': 0, 'bytes': 0})
    item['files'] += 1
    item['bytes'] += row['bytes']
raw_total = sum(row['bytes'] for row in selected.values())
snapshot_total = sum(row['bytes'] for row in snapshots)
reserve = 750000
projected = raw_total + snapshot_total + reserve
plan = {'schema_version': 1, 'status': 'PLAN_ONLY_NO_CURATED_COPY_OR_INDEX_MUTATION',
    'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'phase': PHASE,
    'curated_precondition': {'file_count': 1476, 'total_bytes': 98610356, 'index_sha256': EXPECTED_INDEX},
    'selected_file_count': len(selected), 'selected_bytes': raw_total, 'selected_files': list(selected.values()),
    'group_totals': groups, 'historical_previous1476_snapshots': snapshots, 'historical_snapshot_bytes': snapshot_total,
    'original_three_source_archives': archives, 'source_archive_members_and_reuse_map': source_members,
    'endpoint_and_existing_V7_V8_history_references': endpoint_refs, 'actual_small_external_dependency_references': dependency_refs,
    'selected_direct_small_source_bytes_hashed_now': bytes_hashed_now,
    'source_archive_member_bytes_validated_now': sum(row['bytes'] for row in source_members),
    'large_reports_reviews_and_conversion_inventories_full_hashes_deferred': True,
    'derived_index_collector_plan_lineage_readme_reserve_bytes': reserve,
    'projected_new_growth_bytes': projected, 'growth_cap_bytes': 20000000,
    'projected_headroom_bytes': 20000000 - projected, 'within_budget': projected <= 20000000,
    'factual_qualifications': {
        'exact_fixed_child_fractions': LABELS,
        'zero_new_optimizer_steps_per_derived_artifact': True,
        'parent345_child405_are_actual_separate_historical_training_results': True,
        'factor_interpolation_contains_cross_term_not_functional_or_exact_delta_average': True,
        'IEEE754_F32_round_products_then_sum_noFMA_recorded': True,
        'all184_F32_values_preserved_custom_toPEFT_to_native_conversion_receipts': True,
        'rank8_alpha16_internal2_external1_originalIQ4_base_unmerged_unrequantized': True,
        'all_three_converted_and_frozen_before_any_native500_case': True,
        'full_first_only500_each_serial_no_subset_screen_or_coefficient_tuning': True,
        'old_subset_plan_superseded_before_inference_and_preserved_only_as_unused_history': True,
        'all1500_delivered_once_no_provider_Failed_with_durable_owned_argv_and_postpins': True,
        'actualF16_KV_common_managed_source_runtime_profile': True,
        'all_three_semantic_shards_actual_read_records_and_strict_prior_pass_inheritance_proofs_retained': True,
        'joint_counts_t050487_t075489_t0875490_with_critical7_4_2': True,
        'predeclared_selection_policy_keeps_V8_baseline492_with_critical1': True,
        'not495_of500_not99percent_not_fresh_population_or_resource_qualification': True,
        'no_activeV9_or_extra100_dataset_training_claim': True,
        'three_original_source_archives_preserved_despite_identical_bytes': True,
        'math_guard_independent_PASS_only_reported_in_messages_no_saved_independent_artifact': True,
        'owner_plan91a998_records_reported_guard_PASS_but_is_not_independently_authored': True,
        'formal_independent_wrapper_metadata_code_audit30bc_saved_separately': True,
        'root_seven_middle_actual_cross_read_receipts_each_retained_without_overrides': True,
        'previous1476_raw_bytes_and_derived_snapshots_preserved_on_apply': True},
    'excluded': ['all adapter/base/PEFT/native weights and optimizer/RNG caches',
        'DLLs/native executables/runtime archives and model or binary hashing',
        'active V9 dataset/training/config/results, extra100 and all future/unused corpora',
        'fresh2 contents or new semantic accuracy/resource/Windows/whole-app qualification',
        'large storage relocation ledgers (existing summary/hash references suffice)',
        'any new derivation, conversion, inference, native, Torch, training or build execution'],
    'apply_gates': ['Root approves this exact plan before copying or index mutation',
        'Verify current1476 index1726 and every old byte; snapshot previous three derived documents',
        'Verify all selected full text/source archive hashes and exact endpoint/config/result/notice references',
        'Verify zero-step minimal configs and factor-math provenance without loading tensor/weight files',
        'Verify all three original500 reports, canonical reviews/counts, first-only all-three-freeze and selection-policy lineage',
        'Verify all120 original archive members and shared curated source bodies',
        'Compute exact final growth including all derived/collector/lineage overhead and enforce20MB before mutation',
        'Append only; no main-report edits or activeV9 collection',
        'Independent curated-only index, old preservation, source archive and semantic-lineage verification after append'],
    'curated_tree_or_main_report_modified': False, 'model_binary_native_build_converter_or_torch_jobs_run': False}
assert plan['within_budget']
assert digest((CURATED / 'evidence-files-sha256.json').read_bytes()) == EXPECTED_INDEX
path = OUT / 'selection-size-plan.json'
with path.open('x') as stream:
    json.dump(plan, stream, indent=2)
    stream.write('\n')
print(json.dumps({key: plan[key] for key in ('status', 'selected_file_count', 'selected_bytes', 'group_totals',
    'historical_snapshot_bytes', 'projected_new_growth_bytes', 'projected_headroom_bytes', 'within_budget')}, indent=2))
print('plan', path)
print('plan_sha256', digest(path.read_bytes()))
