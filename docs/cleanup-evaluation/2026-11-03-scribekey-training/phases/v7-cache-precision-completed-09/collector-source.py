#!/usr/bin/env python3
"""Apply the root-approved completed cache-precision text/source evidence plan."""
from pathlib import Path, PurePosixPath
import copy
import datetime
import hashlib
import json
import os
import subprocess
import tarfile

REPO = Path('/workspace/freehand')
TASK = REPO / 'work/cleanup-scribekey-training-2026-11-03'
CURATED = REPO / 'docs/cleanup-evaluation/2026-11-03-scribekey-training'
OUT = Path(__file__).resolve().parent
PLAN = OUT / 'selection-size-plan-v2.json'
PLAN_SHA = 'ca08f54f13ded75465ba477b842a7c1100f8b8b95ca6ca5421e4b2c0ceeb9aee'
OLD_SHA = 'b24207c428c7f60811b03d7e4866b4092fa9a388793f2e8dc7647e2679b2cde7'
DERIVED = ('README.md', 'collection-manifest.json', 'evidence-files-sha256.json')


def digest(data): return hashlib.sha256(data).hexdigest()

def encode(value): return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')

def safe(name):
    value = PurePosixPath(name)
    assert not value.is_absolute() and '..' not in value.parts
    return name


def listing():
    return {path.relative_to(CURATED).as_posix(): path for path in CURATED.rglob('*') if path.is_file() or path.is_symlink()}


plan_bytes = PLAN.read_bytes(); assert digest(plan_bytes) == PLAN_SHA
plan = json.loads(plan_bytes); phase = plan['phase']; phase_root = CURATED / phase
assert plan['within_budget'] and plan['projected_new_growth_bytes'] <= 20_000_000
assert not phase_root.exists(), 'Preserve previous phase outputs; no automatic overwrite/retry'
old_bytes = {name: (CURATED / name).read_bytes() for name in DERIVED}
assert digest(old_bytes['evidence-files-sha256.json']) == OLD_SHA
old_index = json.loads(old_bytes['evidence-files-sha256.json']); old_manifest = json.loads(old_bytes['collection-manifest.json'])
old_files = listing(); assert len(old_files) == 1162
assert set(old_files) == set(old_index['files']) | {'evidence-files-sha256.json'}
assert sum(path.stat().st_size for path in old_files.values()) == 66_737_308
for name in ('README.md', 'collection-manifest.json'):
    assert {'bytes': len(old_bytes[name]), 'sha256': digest(old_bytes[name])} == old_index['files'][name]
# Prior raw bytes are not read again before copying. The trusted old index is the
# baseline, and one complete text/source-only post-pass verifies every old raw file.
payloads = {}; sources = {}; source_hash_receipt = []
for row in plan['selected_files']:
    name = safe(row['path']); assert name.startswith(phase + '/') and not (CURATED / name).exists()
    kind = row.get('source_kind')
    if kind == 'git_blob':
        raw = subprocess.check_output(['git', 'show', row['commit'] + ':' + row['repository_path']], cwd=REPO)
        source_name = 'git:' + row['commit'] + ':' + row['repository_path']
    elif kind == 'text_source_archive_member':
        archive = Path(row['source_archive']); archive_bytes = archive.read_bytes()
        assert digest(archive_bytes) == row['source_archive_sha256']
        with tarfile.open(archive) as bundle:
            member = bundle.getmember(row['archive_member']); assert member.isfile(); safe(member.name)
            raw = bundle.extractfile(member).read()
        source_name = str(archive) + '!' + row['archive_member']
    else:
        path = Path(row['source_path']); assert path.is_file() and not path.is_symlink()
        assert 'v8-' not in str(path).casefold()
        raw = path.read_bytes(); source_name = str(path)
    value = digest(raw)
    assert len(raw) == row['bytes'], source_name
    if row['expected_sha256'] is not None: assert value == row['expected_sha256'], source_name
    payloads[name] = raw
    sources[name] = {'source_path': source_name, 'reason': row['reason'], 'source_kind': kind or 'completed_text_evidence'}
    source_hash_receipt.append({'path': name, 'bytes': len(raw), 'sha256': value, 'planned_hash_status': row['hash_status']})
for row in plan['historical_previous1162_snapshots']:
    name = Path(row['source_path']).name; raw = old_bytes[name]
    assert len(raw) == row['bytes'] and digest(raw) == row['sha256']
    payloads[row['destination']] = raw
    sources[row['destination']] = {'source_path': str(CURATED / name), 'reason': 'Exact previous1162 derived-document epoch before append', 'source_kind': 'historical_derived_snapshot'}

base = phase + '/completed-three-job-diagnostic/'
continuation = json.loads(payloads[base + 'infrastructure-continuation/recovered-original-cohort-completion.json'])
assert digest(payloads[base + 'infrastructure-continuation/recovered-original-cohort-completion.json']) == '01f3712af8fcd8d1ae0b4a2999d2644801545768d91ba51e8ed39ae713e659b9'
assert continuation['no_new_inference_or_replay_performed'] is True
assert continuation['candidate_data_weights_runtime_profile_and_sources_changed'] is False
assert continuation['original_UL_evaluation_survived_outer_controller_exit_and_completed_same500'] is True
assert continuation['original_UL_outer_native_argv_receipt_lost_with_controller_memory'] is True
assert continuation['missing_UL_actual_argv_not_fabricated'] is True
assert continuation['actual_Probe_cache_configuration_still_verified'] is True
assert not any(name.startswith(base + 'ul-f32/') and name.endswith(('evaluation-command.json', 'core.command-receipt.json')) for name in payloads)
summaries = {}; ids = None
for arm, joint in (('sft-f16-bridge', 482), ('sft-f32', 482), ('ul-f32', 483)):
    summary = json.loads(payloads[base + arm + '/semantic-judgment-transfer/semantic-summary.json'])
    report_bytes = payloads[base + arm + '/retired500-core/core-results.json']
    review_bytes = payloads[base + arm + '/semantic-judgment-transfer/canonical-reviewed.json']
    assert digest(report_bytes) == summary['results_sha256']
    assert digest(review_bytes) == summary['canonical_review_sha256']
    assert summary['case_count'] == 500 and summary['faithful_and_clean_usable'] == joint
    assert summary['critical_errors'] == 10 and summary['quality_gate_passed'] is False
    report = json.loads(report_bytes); order = [row['id'] for row in report['cases']]
    assert report['incomplete'] is False and len(order) == len(set(order)) == 500
    if ids is None: ids = order
    else: assert order == ids
    summaries[arm] = summary
for archive in plan['audited_original_three_source_archives']:
    assert len(payloads[archive['path']]) == archive['bytes'] and digest(payloads[archive['path']]) == archive['sha256']

stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
readme = '''# Completed V7 cache-precision diagnostic and qualified-source epoch

This phase preserves the three actual original500-case jobs: new-epoch SFT F16 bridge, SFT F32 and UL F32. All three candidate/source freezes were written before inference. Their complete ordered inputs/outputs, deployment postchecks, exact original source archives, actual bridge/SFT process-argv receipts and source/managed/runtime pins remain available.

| Retired500 development job | Faithful and clean | Critical errors | Judgment method |
| --- | ---: | ---: | --- |
| New-epoch SFT F16 bridge | 482/500 | 10 | Prior semantic judgments transferred under full equality/nonce proofs; case158 optional comma personally read by root |
| SFT F32 | 482/500 | 10 | Exact prior judgment transfer with full13-field/equivalence proof |
| UL F32 | 483/500 | 10 | Exact prior judgment transfer with full13-field/equivalence proof |

These are transparent transfers of the earlier named semantic decisions, not three new personal reads of all500 cases. The transfer script and all raw equality proofs are included. Cache precision did not improve joint quality; all results still fail495/500 and retain critical errors. The qualified source epoch is not a pure isolated cache-causality claim, fresh/population accuracy claim, performance qualification, or Windows/whole-app result.

The outer controller reset after starting the original UL worker. That same worker survived and completed its original500 cases without replay or candidate/data/profile changes. The original UL native argv capture was lost and is explicitly absent; no replacement argv receipt is fabricated. Actual validated Probe options, frozen manifest and deployment/source verification remain distinct evidence. The limited backend-environment record observes only five named variables, not the ambient process environment.

The full qualified-build record includes the initial no-space failure, successful retry, logs/TRX, independent source/build audits and six frozen source/test snapshots. Receipts preserve all24 prior DLL identities plus the new six; no DLLs or model/adapter bytes are copied. Historical and executed wrapper versions, the original audit and up-front-freeze delta acknowledgment are preserved separately. The compact storage summary references raw ignored V3/V4 ledgers without duplicating their multi-megabyte inventories.

Three original source archives are retained separately despite identical bytes. Each contains39 source files plus a textual hash manifest. Source lineage reuses byte-identical old curated/build-snapshot bodies and extracts only missing text. The captured training-source epoch is8c609; active V8 data/training/source8c405 is excluded. No changing work-tree source substitutes for the executed snapshots.

The optional `preview-preparation-only` directory contains tiny-tested builder code and readiness/test receipts. It is not a model selection, real preview bundle/publish/ZIP, Windows run, GPU test or app resource result. Synthetic test RSS is not an app memory qualification.

All prior1162 raw evidence and the exact previous three derived-document snapshots remain preserved. No fresh2, unused reserved240, active V8 dataset/run/result, weights, optimizer/RNG cache or native executable is collected. This phase executes no model, converter, build or new inference and does not edit the root-owned main report.
'''.encode('utf-8')
auxiliary = {
    'README.md': readme,
    'selection-plan.json': plan_bytes,
    'collector-source.py': Path(__file__).read_bytes(),
    'inventory-plan-source.py': (OUT / 'prepare_plan_v2.py').read_bytes(),
    'source-lineage-map.json': encode({'schema_version': 1, 'archives': plan['audited_original_three_source_archives'], 'members': plan['source_archive_members_and_reuse_map'], 'captured_trainer_source': '8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad', 'active_V8_not_collected': True}),
    'previous1162-preservation.json': encode({'schema_version': 1, 'old_index_sha256': OLD_SHA, 'old_file_count': 1162, 'old_total_bytes': 66737308, 'historical_derived_snapshots': plan['historical_previous1162_snapshots']}),
    'authorized-source-hash-receipt.json': encode({'schema_version': 1, 'scope': 'Root-authorized completed text/source evidence only; no model/DLL/cache/activeV8 file read', 'files': source_hash_receipt}),
    'scope-and-exclusions.json': encode({'schema_version': 1, 'completed_jobs': ['sft-f16-bridge', 'sft-f32', 'ul-f32'], 'qualification': plan['required_factual_qualification'], 'excluded': plan['excluded'], 'model_native_build_or_torch_jobs_run': False, 'main_report_modified': False})}
generated = OUT / 'generated-payloads'; assert not generated.exists(); generated.mkdir()
for name, raw in auxiliary.items():
    with (generated / name).open('xb') as stream: stream.write(raw)
    key = phase + '/' + name; assert key not in payloads
    payloads[key] = raw
    sources[key] = {'source_path': str(generated / name), 'reason': 'Generated bounded selection, preservation, source-lineage and qualification metadata', 'source_kind': 'collection_generated_metadata'}

manifest = copy.deepcopy(old_manifest)
for name, raw in sorted(payloads.items()):
    source = sources[name]
    manifest['files'].append({'path': name, 'source_path_historical': source['source_path'], 'bytes': len(raw), 'sha256': digest(raw),
        'scope': source['reason'], 'source_kind': source['source_kind'],
        'observation': {'source_size_before_read': len(raw), 'source_size_after_read': len(raw), 'captured_bytes': len(raw), 'append_only_prefix_snapshot': False, 'complete_source_at_snapshot': True},
        'collection_phase': phase.rsplit('/', 1)[-1]})
manifest['phases'].append({'id': phase.rsplit('/', 1)[-1], 'captured_utc': stamp, 'source_files_collected': len(payloads), 'source_snapshot_bytes_added': sum(map(len, payloads.values())),
    'qualification': 'Three completed cache-precision original500 jobs; judgments transparently transferred, bridge158 personally read. Same482/482/483 joint counts, no quality/resource/Windows advantage or new500-manual-read claim. UL original argv missing, no replay.'})
manifest['completed_cache_precision_status'] = {'jobs': ['sft-f16-bridge', 'sft-f32', 'ul-f32'], 'joint_counts': [482, 482, 483], 'critical_errors_each': 10, 'judgments_transferred_not_new500_reads': True, 'UL_original_worker_completed_no_replay': True, 'UL_argv_missing_explicit': True, 'resource_windows_or_whole_app_qualified': False}
new_manifest = encode(manifest)
addition = ('\n\n## Completed V7 cache-precision diagnostic\n\n'
    'The new-epoch SFT F16 bridge, SFT F32 and UL F32 each completed the original ordered500 Core cohort. Prior semantic decisions were transparently transferred under full13-field/literal-nonce proofs; root personally read the optional-comma bridge case158. These are not three new manual500-case reviews. Joint quality remains482/500,482/500 and483/500 respectively, with10 critical errors each; F32 did not improve this development gate. No fresh/population, resource, Windows or whole-app qualification is claimed.\n\n'
    'The original UL worker survived the outer-controller reset and finished without replay. Its native argv capture was lost and is explicitly missing, not recreated. Qualified source/build records retain the no-space failure and recovery, all logs/TRX/source snapshots, prior24-DLL/new-six preservation receipts and original source archives. The optional preview-builder material is PREPARATION ONLY, not a built or qualified bundle. Active V8 data/training, weights, caches, fresh2 and unused reserved240 are excluded. See [' + phase + '/README.md](' + phase + '/README.md).\n').encode('utf-8')
new_readme = old_bytes['README.md'] + addition
entries = {name: dict(entry) for name, entry in old_index['files'].items()}
for name, raw in payloads.items():
    assert name not in entries; entries[name] = {'bytes': len(raw), 'sha256': digest(raw)}
entries['README.md'] = {'bytes': len(new_readme), 'sha256': digest(new_readme)}
entries['collection-manifest.json'] = {'bytes': len(new_manifest), 'sha256': digest(new_manifest)}
new_index_object = {**old_index, 'files': {name: entries[name] for name in sorted(entries)}}
new_index = encode(new_index_object)
growth = sum(map(len, payloads.values())) + len(new_readme) + len(new_manifest) + len(new_index) - sum(map(len, old_bytes.values()))
assert growth <= 20_000_000 and growth <= plan['projected_new_growth_bytes'], growth
for name, raw in old_bytes.items(): assert (CURATED / name).read_bytes() == raw
print(json.dumps({'precopy_growth_bytes': growth, 'new_phase_files': len(payloads), 'old_index': OLD_SHA}), flush=True)
phase_root.mkdir(parents=True)
for name, raw in sorted(payloads.items()):
    destination = CURATED / safe(name); destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream: stream.write(raw)
for name, raw in old_bytes.items(): assert (CURATED / name).read_bytes() == raw
staging = OUT / 'derived-commit'; staging.mkdir()
for name, raw in (('README.md', new_readme), ('collection-manifest.json', new_manifest), ('evidence-files-sha256.json', new_index)):
    with (staging / name).open('xb') as stream: stream.write(raw)
    os.replace(staging / name, CURATED / name)

# Complete current index pass touches only curated text/source snapshots, never external models.
files = listing(); assert set(files) == set(entries) | {'evidence-files-sha256.json'}
for name, entry in entries.items():
    path = files[name]; assert not path.is_symlink()
    raw = path.read_bytes(); assert len(raw) == entry['bytes'] and digest(raw) == entry['sha256'], name
for name, entry in old_index['files'].items():
    if name not in DERIVED: assert entries[name] == entry
for name in DERIVED:
    saved = CURATED / phase / 'historical' / ('previous1162-' + name)
    assert saved.read_bytes() == old_bytes[name]
assert (CURATED / 'README.md').read_bytes().startswith(old_bytes['README.md'])
assert len(manifest['files']) == len(entries) - 2
assert len({row['path'] for row in manifest['files']}) == len(manifest['files'])
assert {row['path'] for row in manifest['files']} == set(entries) - {'README.md', 'collection-manifest.json'}
for row in manifest['files']: assert {'bytes': row['bytes'], 'sha256': row['sha256']} == entries[row['path']]
for member in plan['source_archive_members_and_reuse_map']:
    raw = (CURATED / member['available_payload_path']).read_bytes()
    assert len(raw) == member['bytes'] and digest(raw) == member['sha256']
archives = {name for name in old_index['files'] if name.endswith('.source-snapshot.tar.gz')}
archives.update(row['path'] for row in plan['audited_original_three_source_archives'])
assert len(archives) == 5
for name, path in files.items():
    assert not any(word in name.lower() for word in ('fresh', 'reserved', 'blind')), name
    assert path.suffix.lower() not in {'.gguf','.safetensors','.onnx','.bin','.pt','.pth','.dll','.exe','.so','.zip','.whl','.pyc','.pdb','.nupkg'}, name
    if path.suffix.lower() == '.gz': assert name in archives
    raw = path.read_bytes(); assert not raw.startswith((b'\x7fELF', b'MZ', b'GGUF', b'PK\x03\x04')), name
    if name in archives:
        with tarfile.open(path) as bundle:
            assert len(bundle.getmembers()) == 40
            for info in bundle.getmembers():
                safe(info.name); assert info.isfile(); data = bundle.extractfile(info).read(); data.decode('utf-8-sig')
                assert not data.startswith((b'\x7fELF', b'MZ', b'GGUF', b'PK\x03\x04'))
new_total = sum(path.stat().st_size for path in files.values()); assert new_total - 66_737_308 == growth
receipt = {'schema_version': 1, 'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'status': 'COMPLETED_CACHE_PRECISION_APPEND_CURRENT_INDEX_SOURCE_LINEAGE_OLD1162_PRESERVATION_VERIFIED', 'phase': phase,
    'approved_plan_sha256': PLAN_SHA, 'collector_sha256': digest(Path(__file__).read_bytes()),
    'previous_index_sha256': OLD_SHA, 'new_index_sha256': digest(new_index),
    'previous_file_count': 1162, 'new_file_count': len(files), 'previous_bytes': 66737308, 'new_bytes': new_total,
    'growth_bytes': growth, 'growth_cap_bytes': 20000000, 'old_raw1159_unchanged': True,
    'previous_three_derived_snapshots_exact': True, 'readme_complete_previous_prefix_preserved': True,
    'all_current_index_manifest_hashes_verified': True, 'all120_source_member_payload_references_verified': True,
    'three_original_source_archives_retained': True, 'all_five_total_source_archives_text_only_verified': True,
    'all_three_original500_reports_and_transferred_judgments_retained': True,
    'semantic_transfer_not_new500_manual_review_claim': True, 'bridge158_personal_root_review_retained': True,
    'UL_original_cohort_survived_and_completed_without_replay': True, 'UL_argv_missing_not_fabricated': True,
    'qualified_build_failure_recovery_receipts_logs_trx_source6_preserved': True,
    'preview128KB_preparation_only_no_bundle_claim': True, 'raw_storage_ledgers_models_Dlls_or_activeV8_data_collected': False,
    'main_report_modified': False, 'model_native_build_converter_or_torch_jobs_run': False, 'git_commit_or_publication_performed': False}
with (OUT / 'application-receipt.json').open('x') as stream: json.dump(receipt, stream, indent=2); stream.write('\n')
with (OUT / 'force-add-paths.txt').open('x') as stream:
    for name in sorted(payloads): stream.write(str((CURATED / name).relative_to(REPO)) + '\n')
    for name in DERIVED: stream.write(str((CURATED / name).relative_to(REPO)) + '\n')
print(json.dumps(receipt, indent=2))
