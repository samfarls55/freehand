#!/usr/bin/env python3
"""Completed-V8 curation inventory only; no curated copy or index mutation."""
from pathlib import Path, PurePosixPath
import datetime
import hashlib
import json
import tarfile

REPO = Path('/workspace/freehand')
TASK = REPO / 'work/cleanup-scribekey-training-2026-11-03'
CURATED = REPO / 'docs/cleanup-evaluation/2026-11-03-scribekey-training'
OUT = Path(__file__).resolve().parent
PHASE = 'phases/v8-completed-10'
EXPECTED_INDEX = '50dc19d32898207cd8812d4eb4b72a56052f43e397347e622fdb019da19f6c53'
ALLOWED = {'.py', '.json', '.jsonl', '.md', '.txt', '.log', '.cs', '.csproj', '.props', '.config', '.ps1'}
selected = {}
known = {}
bytes_hashed_now = 0


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_metadata(path):
    assert path.stat().st_size <= 65536, str(path)
    return json.loads(path.read_bytes())


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
assert len(old_index['files']) + 1 == 1300
old_by_sha = {}
for name, entry in old_index['files'].items():
    old_by_sha.setdefault(entry['sha256'], name)

roots = [TASK / rel for rel in (
    'pipeline/v8-01', 'native-lora-v8-01-export',
    'evaluation/v8-01-native-LoRA-F32-retired-primary500-core',
    'reviews-v8-01-native-LoRA-retired500', 'v8-native-export-preparation',
    'audit/v8-reserved-curriculum', 'audit/v8-unlikelihood-reserved')]
# Narrow positive prefix deliberately excludes unused3394 and current interpolation.
small_json = [p for root in roots for p in root.rglob('*.json') if p.is_file() and p.stat().st_size <= 65536]
small_json += [p for p in (TASK / 'audit/v8-positive-curriculum').glob('positive-3234*.json')
               if p.stat().st_size <= 65536]
small_json += [TASK / 'evaluation/v8-01-native-LoRA-F32-freeze.json',
               TASK / 'pipeline/v8-01-prelaunch.json', TASK / 'pipeline/v8-01-activation.json']
for path in small_json:
    record_pins(read_metadata(path))


def add(source, relative, group, reason):
    global bytes_hashed_now
    source = Path(source)
    assert source.is_file() and not source.is_symlink(), str(source)
    relative_path = PurePosixPath(relative)
    assert not relative_path.is_absolute() and '..' not in relative_path.parts
    assert not any(word in relative.casefold() for word in ('fresh', 'reserved', 'blind'))
    assert source.suffix.lower() in ALLOWED or source.name.endswith('.source-snapshot.tar.gz'), str(source)
    assert not any(word in source.name.casefold() for word in ('3394', 'interpolat'))
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


def tree(root, destination, group, reason, aliases=None):
    for path in sorted(Path(root).rglob('*')):
        if path.is_file() and path.suffix.lower() in ALLOWED:
            relative = path.relative_to(root).as_posix()
            if aliases:
                relative = aliases.get(relative, relative)
            add(path, destination + '/' + relative, group, reason)


# The full actual3234 bytes, full count/provenance/token ledgers and all240 source/review
# lineage fit within the bound; no reconstruction or lossy summarization is planned.
for path in sorted((TASK / 'audit/v8-positive-curriculum').glob('positive-3234*')):
    if path.is_file() and path.suffix in ALLOWED:
        add(path, 'data/positive3234/' + path.name, 'actual3234_and_full_ledgers',
            'Actual completed training dataset2fdab and full structural, count, source exposure, token and lineage ledgers; historical proposed statuses remain verbatim and activation is separately retained')
tree(TASK / 'audit/v8-reserved-curriculum', 'data/used-240', 'actual240_raw_core_author_lineage',
     'All actually used240 raw author parts, historical revisions, overlays, reviews, Core normalization input/export/row maps and approved labels; drafts are lineage, not extra trained rows',
     {'CURRENT-RESERVED-STATUS.md': 'historical-authoring-status.md',
      'root-opaque-fresh2-final-normalized-overlap.json': 'root-opaque-overlap-attestation.json'})
tree(TASK / 'audit/v8-unlikelihood-reserved', 'data/used-ul32', 'actual32_bound_events',
     'Exact32 used events bound to completed3234,64 exposures, approved canonical32/mapping ancestry and independent binding review',
     {'events-32-reserved-3234.jsonl': 'events-32-bound-3234.jsonl',
      'reserved-binding-receipt.json': 'binding-receipt.json'})

# Copy every extant small checkpoint state, but reuse exact source/config bodies.
training_root = TASK / 'pipeline/v8-01'
for path in sorted(training_root.iterdir()):
    if path.is_file() and path.suffix in ALLOWED:
        add(path, 'training/completed-v8-01/' + path.name, 'completed_training',
            'Actual completed405-step training sources, full raw and canonical logs, config, provenance, final result and verifier; no weight, optimizer or RNG binaries')
checkpoint_reuse = []
for area in ('checkpoints', 'snapshots'):
    for state_path in sorted((training_root / area).glob('*/resume-state.json')):
        state = read_metadata(state_path)
        add(state_path, 'training/completed-v8-01/' + state_path.relative_to(training_root).as_posix(),
            'checkpoint_metadata', 'Every surviving checkpoint/snapshot resume state; last durable400 RNG is recorded, final405 RNG capture is explicitly not claimed')
        for name in ('adapter-config.json', 'training-source.py'):
            original = state_path.parent / name
            pin = state['files'][name]
            assert original.is_file() and original.stat().st_size == pin['bytes']
            reference = PHASE + '/training/completed-v8-01/' + name
            expected = '2637946ed089eb5c1b53371def45af9b67380c7a2089d40f2bb29cca8ff1cdb9' if name.endswith('.json') else '8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad'
            assert pin['sha256'] == expected
            checkpoint_reuse.append({'original_source_path': str(original), 'bytes': pin['bytes'],
                'sha256': pin['sha256'], 'available_payload_path': reference,
                'resume_state_path': PHASE + '/training/completed-v8-01/' + state_path.relative_to(training_root).as_posix(),
                'verification_stage': 'resume-state pins/size checked during plan; exact original and shared body bytes must be verified before apply'})

for source, destination, group in (
    ('pipeline/v8-01-prelaunch.json', 'training/activation/v8-01-prelaunch.json', 'activation_and_launch'),
    ('pipeline/v8-01-activation.json', 'training/activation/v8-01-activation.json', 'activation_and_launch'),
    ('pipeline/v8-01-launch.json', 'training/activation/v8-01-launch.json', 'activation_and_launch'),
    ('pipeline/v8-01-console.log', 'training/outer-console/v8-01-console.log', 'completed_training_console'),
    ('pipeline/verify-v8-complete.py', 'training/source/verify-v8-complete.py', 'training_verifier_source'),
    ('pipeline/prepare-v8-reserved-ul.py', 'training/source/prepare-v8-ul.py', 'binding_activation_source'),
    ('audit/build_positive_3234_reserved.py', 'data/source/build_positive_3234.py', 'dataset_builder_source')):
    add(TASK / source, destination, group,
        'Actual V8 activation/launch, completed console, exact verifierca604, binding source or dataset builder316c; no current/future recipe substitution')

tree(TASK / 'native-lora-v8-01-export', 'native-export', 'native_export_and_owned_execution',
     'Exact executed184-F32 PEFT-to-GGUF source and conversion trace, legal notices, actual optimizer digest captured at export preflight, owned command/argv journals and deployment postverification; no GGUF or weights')
tree(TASK / 'evaluation/v8-01-native-LoRA-F32-retired-primary500-core', 'retired500-core', 'actual_full500_core',
     'Complete original retired500 ordered corpus and full Core output, actualF16 cache profile, deployment identity and full execution log; all500 delivered once, no Failed')
tree(TASK / 'reviews-v8-01-native-LoRA-retired500', 'semantic-reviews', 'all_semantic_reviews',
     'Canonical492/500 joint score, all range/read/inheritance records, root28 actual crosspairs and independentC076/C112 review with original moderate-scope limitation; no99percent claim')
tree(TASK / 'v8-native-export-preparation', 'controller-lineage', 'controller_source_tests_and_audits',
     'Original prelaunch historical source/audit and actual optimizer-schema fix,11 guards, independent initial/metadata/delta audits; historical status remains verbatim')
for name in ('v8-01-native-export-controller.log', 'v8-01-native-export-controller-retry1.log'):
    add(TASK / name, 'controller-lineage/outer-console/' + name, 'controller_failure_and_success',
        'Original schema preflight failure before model/Torch/conversion/native, followed by actual successful fixed export/Core run; failure is not hidden')
freeze_path = TASK / 'evaluation/v8-01-native-LoRA-F32-freeze.json'
add(freeze_path, 'retired500-freeze/candidate-freeze.json', 'candidate_freeze',
    'Actual pre-inference source/model/adapter/managed/runtime/profile pins, native adapter external scale1 andF16 KV, without copying executable/model bytes')
freeze = read_metadata(freeze_path)
entry = freeze['source_snapshot']
archive = Path(entry['path'])
archive_dest = add(archive, 'retired500-freeze/candidate-freeze.source-snapshot.tar.gz', 'original_source_archive',
    'Original exact V8 frozen source archive, independently retained even though source bodies match older curated epoch')
raw = archive.read_bytes()
bytes_hashed_now += len(raw)
assert len(raw) == entry['bytes'] == 157798
assert digest(raw) == entry['sha256'] == '69a97570b7cf646387112f537fbdf1fae7425e1ed5ac47b15826c8931963eb30'
selected[archive_dest]['expected_sha256'] = entry['sha256']
selected[archive_dest]['hash_status'] = 'small_text_source_archive_hashed_now'
source_members = []
selected_by_sha = {row['expected_sha256']: row['path'] for row in selected.values() if row.get('expected_sha256')}
with tarfile.open(archive) as bundle:
    members = bundle.getmembers()
    assert len(members) == 40
    assert {m.name for m in members} == set(freeze['sources']) | {'source-files-sha256.json'}
    for member in members:
        relative = PurePosixPath(member.name)
        assert member.isfile() and not relative.is_absolute() and '..' not in relative.parts
        data = bundle.extractfile(member).read()
        data.decode('utf-8-sig')
        assert not data.startswith((b'\x7fELF', b'MZ', b'GGUF', b'PK\x03\x04'))
        sha = digest(data)
        if member.name == 'source-files-sha256.json':
            assert json.loads(data)['files'] == freeze['sources']
        else:
            assert sha == freeze['sources'][member.name]
        if sha in old_by_sha:
            destination, reuse = old_by_sha[sha], 'existing1300_identical_payload'
        elif sha in selected_by_sha:
            destination, reuse = selected_by_sha[sha], 'new_selected_identical_payload'
        else:
            destination, reuse = PHASE + '/source/executed-missing-text/' + member.name, 'new_archive_member_text'
            selected[destination] = {'path': destination, 'source_kind': 'text_source_archive_member',
                'source_archive': str(archive), 'source_archive_sha256': entry['sha256'], 'archive_member': member.name,
                'bytes': len(data), 'expected_sha256': sha, 'hash_status': 'small_archived_source_text_validated_now',
                'group': 'missing_source_text', 'reason': 'Exact frozen source text; never substituted current work repository source'}
            selected_by_sha[sha] = destination
        source_members.append({'archive': archive_dest, 'member': member.name, 'bytes': len(data),
                               'sha256': sha, 'available_payload_path': destination, 'reuse': reuse})
assert freeze['sources']['tools/Freehand.Cleanup.Training/pipeline.py'] == '8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad'

# Reuse earlier curated2754/2014/raw270/normalized270/100/approved32 histories by exact pins.
lineage = read_metadata(TASK / 'audit/v8-positive-curriculum/positive-3234-lineage.json')
history_references = []
for label, pin in [('full2754_prefix', lineage['preserved_prefix']),
                   ('2754_independent_structure', lineage['prior_independent_structure_review']),
                   *list(lineage['old_training_sources'].items())]:
    assert pin['sha256'] in old_by_sha, (label, pin)
    destination = old_by_sha[pin['sha256']]
    assert old_index['files'][destination]['bytes'] == pin['bytes']
    history_references.append({'purpose': label, 'original_source_path': pin['path'],
        'available_payload_path': destination, 'bytes': pin['bytes'], 'sha256': pin['sha256']})
for label, sha in (
    ('canonical_approved32_v4', '5994352434684c3811305d2a63397cf177d42266c68a1b0332138d657d4ecb69'),
    ('canonical32_root_independent_review', '121391d3cab56c22be9fd7376eb4e65b0857decb4547c184615e4de794d2253f'),
    ('parent_V7_UL_report', 'a17350154d4553514b3e67d14df6f7f7e3e1af49c890e682edc872699fa34b82')):
    assert sha in old_by_sha, label
    name = old_by_sha[sha]
    history_references.append({'purpose': label, 'available_payload_path': name,
        'bytes': old_index['files'][name]['bytes'], 'sha256': sha})

for relative, expected in {
    'data/positive3234/positive-3234-proposed.jsonl': '2fdab6a16b7c47a7e2bffd2d60208ad0b5ea9804048d28f2f184468fe33e757c',
    'training/completed-v8-01/adapter-config.json': '2637946ed089eb5c1b53371def45af9b67380c7a2089d40f2bb29cca8ff1cdb9',
    'controller-lineage/run.py': '8ad3f4553e9c730c83e00b8e3926de6bd8632eed68b1017d6926e0937579f576',
    'training/source/verify-v8-complete.py': 'ca6043b692697cdb9b93d1ac0e45bcd0edef4a047efba681e903d09e5faf3cbf',
    'data/source/build_positive_3234.py': '316c677c8b97376b93809f97e0d121d68d1d4f278fade8ec55f2a18a6bae0ecb',
}.items():
    assert selected[PHASE + '/' + relative]['expected_sha256'] == expected, relative
# Review/report expected pins are supplied by the completed handoff, full rehash deferred.
for relative, expected in {
    'semantic-reviews/canonical-reviewed.json': 'fe07736284eda5a8b8425c90b537f217e7c984d94b7e2420d375c8c5e1bfdae7',
    'retired500-core/core-results.json': '7d492ecb55fb7dc1ef537f1b7c575fece3aad838ac5fff7ca17a2214ed6c3a70',
}.items():
    row = selected[PHASE + '/' + relative]
    assert row['expected_sha256'] in (None, expected)
    row['expected_sha256'] = expected
    row['hash_status'] = 'completed_handoff_expected_pin_not_rehashed_now'

snapshots = []
for name in ('README.md', 'collection-manifest.json', 'evidence-files-sha256.json'):
    pin = {'bytes': len(index_bytes), 'sha256': EXPECTED_INDEX} if name == 'evidence-files-sha256.json' else old_index['files'][name]
    snapshots.append({'source_path': str(CURATED / name), 'destination': PHASE + '/historical/previous1300-' + name,
                      **pin, 'hash_status': 'expected_current_index_epoch_pin_no_full_curated_rehash_now'})
raw_total = sum(row['bytes'] for row in selected.values())
snapshot_total = sum(row['bytes'] for row in snapshots)
reserve = 750000
groups = {}
for row in selected.values():
    group = groups.setdefault(row['group'], {'files': 0, 'bytes': 0})
    group['files'] += 1
    group['bytes'] += row['bytes']
projected = raw_total + snapshot_total + reserve
plan = {
    'schema_version': 1, 'status': 'PLAN_ONLY_NO_CURATED_COPY_OR_INDEX_MUTATION',
    'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'phase': PHASE,
    'curated_precondition': {'file_count': 1300, 'total_bytes': 79083660, 'index_sha256': EXPECTED_INDEX},
    'selected_file_count': len(selected), 'selected_bytes': raw_total, 'group_totals': groups,
    'selected_files': list(selected.values()), 'historical_previous1300_snapshots': snapshots,
    'historical_snapshot_bytes': snapshot_total, 'checkpoint_source_config_identical_payload_references': checkpoint_reuse,
    'checkpoint_duplicate_bytes_referenced_not_copied': sum(row['bytes'] for row in checkpoint_reuse),
    'prior_curated_history_references': history_references,
    'source_archive': {'path': archive_dest, 'bytes': entry['bytes'], 'sha256': entry['sha256'],
                       'source_file_count': 39, 'total_regular_utf8_members': 40},
    'source_archive_members_and_reuse_map': source_members,
    'selected_direct_small_source_bytes_hashed_now': bytes_hashed_now,
    'source_archive_member_bytes_validated_now': sum(row['bytes'] for row in source_members),
    'large_dataset_ledger_report_or_training_log_hashes_deferred': True,
    'derived_index_collector_plan_lineage_readme_reserve_bytes': reserve,
    'projected_new_growth_bytes': projected, 'growth_cap_bytes': 20000000,
    'projected_headroom_bytes': 20000000 - projected, 'within_budget': projected <= 20000000,
    'factual_qualifications': {
        'actual_full3234_dataset_and_full_ledgers_copied_not_only_summary_or_suffix': True,
        'old2754_prefix_and2014_270_100_histories_reused_by_exact_curated_hash': True,
        'all_used240_raw_core_author_parts_overlays_reviews_and_normalization_lineage': True,
        'historical_reserved_proposed_status_bytes_preserved_activation_separate': True,
        'training405_steps809_microbatches55612_assistant_tokens64_logged_event_exposures': True,
        'training_source_is8c609_not_current_or_future_source': True,
        'fresh_optimizer_from_parent885_not_optimizer_resume': True,
        'last_durable400_rng_only_no_final405_rng_claim': True,
        'actual_final_optimizer_digest_captured_at_export_preflight_not_original_final_verifier': True,
        'original_preflight_schema_failure_before_Torch_model_conversion_native_retained': True,
        'original184_F32_native_adapter_external_scale1_no_merged_weight_copy': True,
        'actualF16_cache_managed_epoch_and_durable_owned_argv_receipts': True,
        'original500_all_delivered_once_no_Failed': True,
        'joint492_faithful498_clean493_critical1_not99percent': True,
        'root28_actual_crosspairs_andC076C112_moderate_scope_review_retained_verbatim': True,
        'not_windows_whole_app_or_resource_qualification': True,
        'parent_child_interpolation_reserved80_and3394_not_V8_used_data': True,
    },
    'excluded': [
        'all model/adapter/optimizer/RNG weights, DLLs, executables and native archives',
        'current parent-child interpolation outputs, prepared unused80/3394 and future work',
        'fresh2 contents or other private/future evaluation corpora',
        'old already-curated full2754/2014/270/100/approved32 bodies duplicated again',
        'five exact saved checkpoint/snapshot source/config duplicate bodies (pin references retained)',
        'large storage ledgers, new build/inference/native/conversion/Torch/training jobs',
    ],
    'apply_gates': [
        'Root approves this exact plan before any curated copy/index mutation',
        'Reverify expected index50dc and all1300 old bytes; snapshot previous three derived documents',
        'Verify every selected full text/archive source pin and every checkpoint reuse source/config pin before copying',
        'Verify source archive40 UTF8 members and earlier curated exact payload references',
        'Verify3234 full dataset2fdab has exact already-curated2754 byte prefixfa18 and correct source240 exposure lineage',
        'Keep raw statuses and actual activation/failure/capture/review limitations explicit',
        'Compute exact serialized final growth including all new collector/plan/lineage/README/index/manifest bytes and enforce20MB before mutation',
        'Append only; preserve all old raw bytes and README prefix; no root main-report edits',
        'Independent full curated index, prior epoch preservation, archive/member and data-lineage verification after append',
    ],
    'curated_tree_or_main_report_modified': False,
    'model_weights_native_build_converter_or_torch_jobs_run': False,
}
assert plan['within_budget'], projected
assert digest((CURATED / 'evidence-files-sha256.json').read_bytes()) == EXPECTED_INDEX
path = OUT / 'selection-size-plan.json'
with path.open('x') as stream:
    json.dump(plan, stream, indent=2)
    stream.write('\n')
print(json.dumps({key: plan[key] for key in (
    'status', 'selected_file_count', 'selected_bytes', 'group_totals', 'historical_snapshot_bytes',
    'checkpoint_duplicate_bytes_referenced_not_copied', 'projected_new_growth_bytes',
    'projected_headroom_bytes', 'within_budget')}, indent=2))
print('plan', path)
print('plan_sha256', digest(path.read_bytes()))
