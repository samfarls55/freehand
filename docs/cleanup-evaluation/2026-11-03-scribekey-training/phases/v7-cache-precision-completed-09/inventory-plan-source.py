#!/usr/bin/env python3
"""Metadata/small-source-only plan for completed V7 cache precision evidence."""
from pathlib import Path, PurePosixPath
import datetime
import hashlib
import json
import subprocess
import tarfile

REPO = Path('/workspace/freehand')
TASK = REPO / 'work/cleanup-scribekey-training-2026-11-03'
CURATED = REPO / 'docs/cleanup-evaluation/2026-11-03-scribekey-training'
OUT = Path(__file__).resolve().parent
PHASE = 'phases/v7-cache-precision-completed-09'
EXPECTED_INDEX = 'b24207c428c7f60811b03d7e4866b4092fa9a388793f2e8dc7647e2679b2cde7'
EVAL = TASK / 'evaluation/v7-cache-precision-new-epoch-01'
BUILD = TASK / 'verification/f32-kv-build'
PREP = TASK / 'v7-f32-kv-diagnostic-preparation'
ALLOWED = {'.py', '.json', '.jsonl', '.md', '.txt', '.log', '.trx', '.cs', '.csproj', '.props', '.config', '.ps1'}
selected = {}; known = {}; bytes_hashed_now = 0


def digest(data):
    return hashlib.sha256(data).hexdigest()


def metadata(path):
    assert path.stat().st_size <= 65536
    return json.loads(path.read_bytes())


def record_pins(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str) and len(value['sha256']) == 64:
            size = value.get('bytes', value.get('size'))
            if type(size) is int:
                known.setdefault(value['path'], []).append({'bytes': size, 'sha256': value['sha256']})
        for child in value.values(): record_pins(child)
    elif isinstance(value, list):
        for child in value: record_pins(child)


for root in (EVAL, BUILD, PREP, TASK / 'audit/f32-cache-source-review'):
    for path in root.rglob('*.json'):
        if path.is_file() and path.stat().st_size <= 65536:
            record_pins(metadata(path))
index_bytes = (CURATED / 'evidence-files-sha256.json').read_bytes()
assert digest(index_bytes) == EXPECTED_INDEX
old_index = json.loads(index_bytes)
old_by_sha = {}
for name, entry in old_index['files'].items(): old_by_sha.setdefault(entry['sha256'], name)
assert len(old_index['files']) + 1 == 1162


def add(source, relative, group, reason):
    global bytes_hashed_now
    source = Path(source); assert source.is_file() and not source.is_symlink(), str(source)
    relative_path = PurePosixPath(relative)
    assert not relative_path.is_absolute() and '..' not in relative_path.parts
    assert not any(word in relative.casefold() for word in ('fresh', 'reserved', 'blind'))
    assert source.suffix.lower() in ALLOWED or source.name.endswith('.source-snapshot.tar.gz'), str(source)
    assert 'v8-' not in str(source).casefold(), 'Active V8 data/training must not enter this completed phase'
    size = source.stat().st_size
    expected = None; status = 'deferred_full_hash_until_authorized_copy'
    if size <= 65536:
        raw = source.read_bytes(); expected = digest(raw); bytes_hashed_now += len(raw)
        status = 'small_source_or_metadata_hashed_now'
    else:
        matches = known.get(str(source), [])
        if not matches:
            matches = [item for path, entries in known.items() if Path(path).name == source.name
                       for item in entries if item['bytes'] == size]
        hashes = {item['sha256'] for item in matches if item['bytes'] == size}
        if len(hashes) == 1:
            expected = next(iter(hashes)); status = 'expected_pin_from_completed_small_receipt_not_rehashed_now'
    key = PHASE + '/' + relative; assert key not in selected
    selected[key] = {'path': key, 'source_path': str(source), 'bytes': size, 'expected_sha256': expected,
                     'hash_status': status, 'group': group, 'reason': reason}


def tree(root, destination, group, reason):
    for path in sorted(Path(root).rglob('*')):
        if path.is_file() and (path.suffix.lower() in ALLOWED or path.name.endswith('.source-snapshot.tar.gz')):
            add(path, destination + '/' + path.relative_to(root).as_posix(), group, reason)


tree(EVAL, 'completed-three-job-diagnostic', 'three_full500',
     'All three original ordered500 jobs, up-front freezes, command receipts, comparisons, exact judgment-transfer proofs and honest original-UL continuation')
tree(BUILD, 'qualified-build', 'qualified_build',
     'Actual qualified source/build receipt, all logs/TRX, no-space failure/recovery,24 old DLL preservation and six immutable source snapshots; no DLL bytes')
for name in ('v7-cache-precision-new-epoch-01-controller.log', 'v7-cache-precision-new-epoch-01-post-reset-verification.log'):
    add(TASK / name, 'completed-three-job-diagnostic/outer-controller-trace/' + name, 'controller_console_trace',
        'Actual outer controller trace and later original-cohort verifier output, not a fabricated UL argv or replay')
tree(PREP, 'wrapper-lineage', 'wrapper_lineage',
     'Exact executed/current/historical wrappers and tests, original audit and up-front-three-freeze delta; historical preparations not relabeled as executions')
tree(TASK / 'audit/f32-cache-source-review', 'qualified-source-audit', 'source_audit',
     'Independent qualified F32 source audit5013 and build supplementde9c')
add(TASK / 'storage/completed-build-dedup-v3-v4-summary.json', 'storage/completed-build-dedup-v3-v4-summary.json',
    'storage_summary_only', 'Compact root summary hashes raw ignored ledgers and preserves6800 file/mode/owner identities; multi-MB ledgers intentionally not copied')

# Optional source/receipt-only preview preparation: never a model result or a built bundle.
preview = REPO / 'work/v7-trained-scribe-preview-builder'
for name in ('README.md', 'PREVIEW-README.template.md', 'make_preview.py', 'run-preview.ps1',
             'test_make_preview.py', 'test_bundle_clone.ps1', 'candidate-freeze.example.json', 'copied-builder-origin.json',
             'latest-targeted-verification.json', 'ready-gates.json', 'preparation-plan-cache-profiles-verified.json',
             'synthetic-tests-cache-profiles-16.log', 'synthetic-powershell-cache-profiles-6.log',
             'synthetic-powershell-cache-profiles-resource.json'):
    add(preview / name, 'preview-preparation-only/' + name, 'preview_prepared_only',
        'Optional tiny-tested builder source/receipts only; no Windows run, model selection, publish, bundle, ZIP or app performance qualification')

# Pin the committed qualified guide rather than changing work-tree source.
guide_path = 'tools/Freehand.Cleanup.Training/EXPORT-EVALUATE.md'
guide = subprocess.check_output(['git', 'show', '8b059f2:' + guide_path], cwd=REPO)
key = PHASE + '/qualified-source-guide/EXPORT-EVALUATE.md'
selected[key] = {'path': key, 'source_kind': 'git_blob', 'repository_path': guide_path, 'commit': '8b059f2',
    'bytes': len(guide), 'expected_sha256': digest(guide), 'hash_status': 'small_committed_guide_hashed_now',
    'group': 'qualified_guide', 'reason': 'Committed qualified F32 source guide; not an active V8 training artifact'}
bytes_hashed_now += len(guide)

# Source archives are small text-only source snapshots; reports/weights are not read here.
source_members = []; archives = []
selected_by_sha = {row['expected_sha256']: row['path'] for row in selected.values() if row.get('expected_sha256')}
for arm in ('sft-f16-bridge', 'sft-f32', 'ul-f32'):
    freeze = metadata(EVAL / arm / 'candidate-freeze.json')
    entry = freeze['source_snapshot']; archive = Path(entry['path'])
    raw = archive.read_bytes(); bytes_hashed_now += len(raw)
    assert len(raw) == entry['bytes'] and digest(raw) == entry['sha256']
    archive_dest = PHASE + '/completed-three-job-diagnostic/' + arm + '/candidate-freeze.source-snapshot.tar.gz'
    selected[archive_dest]['expected_sha256'] = entry['sha256']
    selected[archive_dest]['hash_status'] = 'small_text_source_archive_hashed_now'
    archives.append({'arm': arm, 'path': archive_dest, 'bytes': len(raw), 'sha256': entry['sha256'],
        '39_code_plus_one_text_hash_manifest': True})
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers(); assert len(members) == 40
        assert {member.name for member in members} == set(freeze['sources']) | {'source-files-sha256.json'}
        for member in members:
            relative = PurePosixPath(member.name)
            assert member.isfile() and not relative.is_absolute() and '..' not in relative.parts
            data = bundle.extractfile(member).read(); data.decode('utf-8-sig')
            assert not data.startswith((b'\x7fELF', b'MZ', b'GGUF', b'PK\x03\x04'))
            digest_value = digest(data)
            if member.name == 'source-files-sha256.json':
                assert json.loads(data)['files'] == freeze['sources']
            else:
                assert digest_value == freeze['sources'][member.name]
            if digest_value in old_by_sha:
                destination, kind = old_by_sha[digest_value], 'existing1162_identical_payload'
            elif digest_value in selected_by_sha:
                destination, kind = selected_by_sha[digest_value], 'new_qualified_build_or_source_identical_payload'
            else:
                destination, kind = PHASE + '/source/executed-missing-text/' + member.name, 'new_archive_member_text'
                selected[destination] = {'path': destination, 'source_kind': 'text_source_archive_member',
                    'source_archive': str(archive), 'source_archive_sha256': entry['sha256'], 'archive_member': member.name,
                    'bytes': len(data), 'expected_sha256': digest_value, 'hash_status': 'small_archived_source_text_validated_now',
                    'group': 'missing_source_text', 'reason': 'Executed frozen source text absent from older curated/build snapshot bodies; no live repo substitution'}
                selected_by_sha[digest_value] = destination
            source_members.append({'arm': arm, 'archive': archive_dest, 'member': member.name, 'bytes': len(data),
                'sha256': digest_value, 'available_payload_path': destination, 'reuse': kind})
    assert freeze['sources']['tools/Freehand.Cleanup.Training/pipeline.py'] == '8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad'

expected_small = {
    'completed-three-job-diagnostic/infrastructure-continuation/recovered-original-cohort-completion.json': '01f3712af8fcd8d1ae0b4a2999d2644801545768d91ba51e8ed39ae713e659b9',
    'qualified-source-audit/source-review-131d2d.json': '5013e96edde8c1b4350bdc5358f8e67286594025467906223582b1e37ea1ac37',
    'storage/completed-build-dedup-v3-v4-summary.json': '3b50c537f621b0dd2f3cccd086696887f52433ec75bfd402faba82828a392350'}
for relative, expected in expected_small.items(): assert selected[PHASE + '/' + relative]['expected_sha256'] == expected

snapshots = []
for name in ('README.md', 'collection-manifest.json', 'evidence-files-sha256.json'):
    if name == 'evidence-files-sha256.json': expected = {'bytes': len(index_bytes), 'sha256': EXPECTED_INDEX}
    else: expected = old_index['files'][name]
    snapshots.append({'source_path': str(CURATED / name), 'destination': PHASE + '/historical/previous1162-' + name,
        **expected, 'hash_status': 'expected_current_index_epoch_pin_no_full_curated_rehash_now'})
raw_total = sum(row['bytes'] for row in selected.values())
snapshot_total = sum(row['bytes'] for row in snapshots)
reserve = 750_000
projected = raw_total + snapshot_total + reserve
groups = {}
for row in selected.values():
    item = groups.setdefault(row['group'], {'files': 0, 'bytes': 0}); item['files'] += 1; item['bytes'] += row['bytes']
plan = {'schema_version': 1, 'status': 'PLAN_ONLY_NO_CURATED_COPY_OR_INDEX_MUTATION',
    'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'phase': PHASE,
    'curated_precondition': {'file_count': 1162, 'total_bytes': 66737308, 'index_sha256': EXPECTED_INDEX},
    'selected_file_count': len(selected), 'selected_bytes': raw_total, 'group_totals': groups,
    'selected_files': list(selected.values()), 'historical_previous1162_snapshots': snapshots,
    'historical_snapshot_bytes': snapshot_total, 'source_archive_members_and_reuse_map': source_members,
    'audited_original_three_source_archives': archives, 'planned_source_epoch_commit': '8b059f2',
    'selected_direct_small_source_bytes_hashed_now': bytes_hashed_now,
    'source_archive_member_bytes_validated_now': sum(row['bytes'] for row in source_members),
    'large_report_build_inventory_trx_full_hashes_deferred': True,
    'raw_datasets_weights_current_v8_or_old_full_curated_tree_hashed_now': False,
    'derived_index_collector_plan_lineage_readme_reserve_bytes': reserve,
    'projected_new_growth_bytes': projected, 'growth_cap_bytes': 20_000_000,
    'projected_headroom_bytes': 20_000_000 - projected, 'within_budget': projected <= 20_000_000,
    'required_factual_qualification': {
        'three_actual_original500_jobs_complete': True, 'semantic_decisions_transferred_not500_new_manual_reads': True,
        'bridge158_optional_comma_personally_read_by_root_receipt': True,
        'sft_f32_same_semantics482_ul_f32_same_semantics483': True,
        'qualified_code_and_new_epoch_not_pure_cache_causality_claim': True,
        'UL_original_worker_survived_outer_reset_and_completed_without_replay': True,
        'UL_proc_argv_missing_not_fabricated': True,
        'only_bridge_and_sft_f32_have_actual_proc_argv_receipts': True,
        'backend_env_observation_only_five_known_vars_not_ambient_env': True,
        'source_build_nospace_failure_and_recovery_remain_explicit': True,
        'prior24_DLLs_preserved_plus_new6_checks_are_receipt_claims_not_rehashed_models_here': True,
        'preview_is_tiny_tested_preparation_only_not_bundle_or_windows_execution': True,
        'not_windows_whole_app_resource_or99percent_quality_qualification': True},
    'excluded': ['all DLL/native executables/model or adapter weights/optimizer/RNG binaries',
        'ignored multi-MB V3/V4 raw storage ledgers (hash-referenced compact summary is retained)',
        'active V8 3234-row data, source8c405 training/run/result/curriculum artifacts',
        'fresh2 and unused reserved240 contents', 'actual preview bundle/publish/ZIP/model profile activation',
        'new inference, resource comparison, native, conversion or build work'],
    'apply_gates': ['Root approves this exact plan before any copy/index mutation',
        'Respect active V8 sole-heavy-owner schedule; no model/native/build jobs',
        'After explicit hashing/copy release, verify every selected source bytes+SHA and source archive/member pin',
        'Capture original1162 three derived snapshots before regeneration; preserve every old raw file',
        'Use source-snapshot/build bodies only; do not substitute current work-repo or active V8 files',
        'Calculate exact final net growth with all auxiliary and derived documents before mutation and enforce20MB',
        'Independent all-file index/source archive/old epoch preservation verification after append'],
    'curated_tree_or_main_report_modified': False, 'model_native_build_converter_or_torch_jobs_run': False}
assert plan['within_budget']
assert digest((CURATED / 'evidence-files-sha256.json').read_bytes()) == EXPECTED_INDEX
path = OUT / 'selection-size-plan-v2.json'
with path.open('x') as stream: json.dump(plan, stream, indent=2); stream.write('\n')
print(json.dumps({key: plan[key] for key in ('status', 'selected_file_count', 'selected_bytes', 'group_totals',
    'historical_snapshot_bytes', 'projected_new_growth_bytes', 'projected_headroom_bytes',
    'selected_direct_small_source_bytes_hashed_now', 'source_archive_member_bytes_validated_now', 'within_budget')}, indent=2))
print('plan', path); print('plan_sha256', digest(path.read_bytes()))
