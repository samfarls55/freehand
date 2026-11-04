#!/usr/bin/env python3
"""Apply the root-authorized bounded V7 evidence append; no model/build/native jobs."""
from pathlib import Path, PurePosixPath
import copy
import datetime
import hashlib
import json
import os
import tarfile

REPO = Path('/workspace/freehand')
TASK = REPO / 'work/cleanup-scribekey-training-2026-11-03'
CURATED = REPO / 'docs/cleanup-evaluation/2026-11-03-scribekey-training'
OUT = Path(__file__).resolve().parent
PLAN = OUT / 'selection-size-plan-v2.json'
EXPECTED = 'bf9212b5ae7e5d7889027c8d41d7508ca7de8e2aa3b91bfb0f02fed8094b5873'
DERIVED = ('README.md', 'collection-manifest.json', 'evidence-files-sha256.json')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def safe(name):
    path = PurePosixPath(name)
    assert not path.is_absolute() and '..' not in path.parts
    return name


def tree_files():
    return {p.relative_to(CURATED).as_posix(): p for p in CURATED.rglob('*') if p.is_file() or p.is_symlink()}


plan = json.loads(PLAN.read_bytes())
assert plan['within_budget_before_pending_finalization'] is True
assert plan['projected_new_growth_bytes'] <= 20_000_000
phase = plan['phase']; phase_root = CURATED / phase
assert not phase_root.exists(), 'Preserve all existing phase outputs; this append never overwrites a phase'
old = {name: (CURATED / name).read_bytes() for name in DERIVED}
assert digest(old['evidence-files-sha256.json']) == EXPECTED
old_index = json.loads(old['evidence-files-sha256.json'])
old_manifest = json.loads(old['collection-manifest.json'])
before_files = tree_files()
assert len(before_files) == 940 and set(before_files) == set(old_index['files']) | {'evidence-files-sha256.json'}
assert sum(path.stat().st_size for path in before_files.values()) == 47_179_924
for name, entry in old_index['files'].items():
    path = before_files[name]
    assert not path.is_symlink()
    data = path.read_bytes()
    assert len(data) == entry['bytes'] and digest(data) == entry['sha256'], name

payloads = {}
records = {}
archive_cache = {}
for row in plan['selected_files']:
    destination = safe(row['path'])
    assert destination.startswith(phase + '/') and not (CURATED / destination).exists()
    if row.get('source_kind') == 'text_source_archive_member':
        source = Path(row['source_archive'])
        archive_bytes = source.read_bytes()
        assert digest(archive_bytes) == row['source_archive_sha256']
        with tarfile.open(source) as bundle:
            member = bundle.getmember(row['archive_member'])
            assert member.isfile()
            data = bundle.extractfile(member).read()
    else:
        source = Path(row['source_path'])
        assert source.is_file() and not source.is_symlink()
        data = source.read_bytes()
    assert len(data) == row['bytes'] and digest(data) == row['sha256'], row['source_path']
    payloads[destination] = data; records[destination] = row
for row in plan['historical_previous940_snapshots']:
    name = Path(row['source_path']).name; data = old[name]
    assert len(data) == row['bytes'] and digest(data) == row['sha256']
    payloads[row['destination']] = data
    records[row['destination']] = {'source_path': str(CURATED / name), 'reason': 'Exact previous940 derived snapshot before this append', 'source_kind': 'historical_derived_snapshot'}

# Validate the sole binary archive exception: original frozen source archives, all40 members textual.
for archive in plan['audited_original_source_archives']:
    data = payloads[archive['path']]
    assert digest(data) == archive['sha256']
    source = next(Path(row['source_path']) for row in plan['selected_files'] if row['path'] == archive['path'])
    with tarfile.open(source) as bundle:
        assert len(bundle.getmembers()) == 40
        for member in bundle.getmembers():
            safe(member.name); assert member.isfile()
            raw = bundle.extractfile(member).read(); raw.decode('utf-8-sig')
            assert not raw.startswith((b'\x7fELF', b'MZ', b'GGUF', b'PK\x03\x04'))

final_key = phase + '/data/positive/positive-2754-final.jsonl'
prefix = payloads[final_key][:4_138_815]
assert digest(payloads[final_key]) == 'fa18dfcd5faf4c5a7a20f8e9b669caaa2ec3c8e098b27b17a25128eda1d592a6'
assert digest(prefix) == '8e31598f65e695001b37d8920e44b93f6e6fb2a24ae6d0cf8e8387dd1b4a51a9'
assert len(prefix.splitlines()) == 2554 and len(payloads[final_key].splitlines()) == 2754
for row in plan['existing_curated_history_references']:
    data = (CURATED / row['existing_curated_path']).read_bytes()
    assert len(data) == row['bytes'] and digest(data) == row['sha256']

stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
summaries = {arm: json.loads(payloads[phase + '/reviews/' + arm + '-retired500/canonical-semantic-summary.json']) for arm in ('sft', 'ul')}
assert summaries['sft']['faithful_and_clean_usable'] == 482 and summaries['ul']['faithful_and_clean_usable'] == 483
assert all(value['case_count'] == 500 and value['quality_gate_passed'] is False and value['critical_errors'] == 10 for value in summaries.values())
phase_readme = '''# Completed V7 SFT control and UL arm

This phase records the actual same-positive two-arm comparison: source8c609, positive2754/fa18, canonical32 used negatives, all64 disclosed mappings, V6 initialization parent157af, original IQ4 numerical base82ab, rank8/alpha16 and external native adapter scale1. No base merge or requantization occurred. All model/adapter/optimizer/RNG binaries remain outside this text evidence collection; their exact identities remain in receipts.

Both arms completed345 optimizer updates and689 microbatches. The SFT canonical log is original1–192 plus resumed193–345; the UL canonical log is original1–32 plus resumed33–345. All15 discarded/replayed nonelapsed records in each recovery match exactly. Raw prefix/suffix/canonical logs and checkpoint inventories are retained separately. Actual durable RNG checkpoint336 is documented; final345 RNG serialization is not claimed. Source-validated64 event mappings plus logged total64 are not mislabeled as direct per-ID logs.

| Retired500 development arm | Faithful and clean | Critical errors | Provider failures | Quality gate |
| --- | ---: | ---: | ---: | --- |
| SFT eta0 | 482/500 (96.4%) | 10 | 0 | Fail (requires495) |
| UL eta1 | 483/500 (96.6%) | 10 | 0 | Fail (requires495) |

Every actual input/output and provider outcome remains in each complete ordered500 report. Canonical reviews, all three range decisions, strict inheritance proofs, personal read records, and the root20-pair UL cross-review are included. These are retired synthetic development observations, not fresh/population accuracy or Windows/whole-app SLA qualification. No new broad546/hard80 or performance inference is implied.

`data/positive/positive-2754-final.jsonl` contains the entire byte-exact2554 prefix. `prefix-lineage-proof.json` records its offset/count/hash, so the4.1MB provisional payload is not duplicated. All actually used270 and100 raw gold data, Core-normalized derivatives, reviews and builders are retained; the2014 history and its raw derivation are referenced by exact existing curated paths/hashes.

The two original candidate-freeze source archives are the only compressed payload exception. Each contains39 verified source files plus its textual hash manifest, no weights or executable binaries. `source-lineage-map.json` identifies every actual source body, reusing byte-identical old/new text files and extracting every missing body directly from the frozen archive. Current work-repo edits are not substituted for executed source. Unused reserved240, fresh2 contents and earlier unused negative drafts are excluded.

The historical previous940 README, collection manifest and index are preserved byte-for-byte under `historical/`. Existing raw evidence remains unchanged. `selection-plan.json`, the collector source and provenance maps document this append; the root summary README is extended with an explicit development-only failure qualification.
'''.encode('utf-8')
auxiliary = {
    'README.md': phase_readme,
    'selection-plan.json': PLAN.read_bytes(),
    'collector-source.py': Path(__file__).read_bytes(),
    'inventory-plan-source.py': (OUT / 'inventory_plan_complete.py').read_bytes(),
    'source-lineage-map.json': encode({'schema_version': 1, 'archives': plan['audited_original_source_archives'], 'members': plan['source_archive_members_and_reuse_map'], 'existing2014_history': plan['existing_curated_history_references']}),
    'prefix-lineage-proof.json': encode({'schema_version': 1, **plan['prefix_lineage_without_duplicate_payload'], 'actual_prefix_sha_verified': True, 'actual_prefix_rows_verified': 2554, 'actual_final_rows_verified': 2754}),
    'previous940-preservation.json': encode({'schema_version': 1, 'old_index_sha256': EXPECTED, 'old_file_count': 940, 'old_total_bytes': 47179924, 'old_raw937_size_and_sha_verified_before_copy': True, 'historical_derived_snapshots': plan['historical_previous940_snapshots']}),
    'scope-and-exclusions.json': encode({'schema_version': 1, 'used_data': ['actual2754 positive file', 'raw/Core270 and100 gold sources', 'actual canonical32-v4 and bound32 events'], 'excluded': plan['excluded'], 'source_archives_only_binary_exception': plan['audited_original_source_archives'], 'fresh_or_unused_reserved_data_collected': False, 'model_or_native_jobs_run': False})}
generated = OUT / 'generated-payloads'; assert not generated.exists(); generated.mkdir()
for name, data in auxiliary.items():
    with (generated / name).open('xb') as stream: stream.write(data)
    key = phase + '/' + name; assert key not in payloads
    payloads[key] = data
    records[key] = {'source_path': str(generated / name), 'reason': 'Generated source/lineage/qualification metadata for the root-authorized append', 'source_kind': 'collection_generated_metadata'}

manifest = copy.deepcopy(old_manifest)
for name in sorted(payloads):
    data = payloads[name]; record = records[name]
    manifest['files'].append({'path': name, 'source_path_historical': record['source_path'], 'bytes': len(data), 'sha256': digest(data),
        'scope': record.get('reason', 'Completed V7 used evidence'), 'source_kind': record.get('source_kind', 'exact_completed_source_file'),
        'observation': {'source_size_before_read': len(data), 'source_size_after_read': len(data), 'captured_bytes': len(data), 'append_only_prefix_snapshot': False, 'complete_source_at_snapshot': True}, 'collection_phase': phase.rsplit('/', 1)[-1]})
manifest['phases'].append({'id': phase.rsplit('/', 1)[-1], 'captured_utc': stamp, 'source_files_collected': len(payloads), 'source_snapshot_bytes_added': sum(map(len, payloads.values())), 'qualification': 'Completed V7 SFT482/500 and UL483/500 retired development; both fail495/500 and retain10 critical errors. No fresh/Windows/whole-app qualification.'})
manifest['primary500_current_status'] = {'retired': True, 'cases': 500, 'joint': 483, 'required': 495, 'gate_passed': False, 'critical_errors': 10, 'latest_completed_arm': 'V7 UL eta1', 'comparison_sft_joint': 482, 'qualification': 'Retired development only; no model/default promotion implied'}
new_manifest = encode(manifest)
addition = b'\n\n## Completed V7 two-arm comparison\n\n' + b'The V7 SFT control and UL arm used the same actual2754-row positive data and exact source8c609 recipe, with eta0 versus eta1. Both completed345 updates/689 microbatches with preserved recovery prefix/suffix and15 exact replay records. Retired500 semantic results are482/500 (96.4%) for SFT and483/500 (96.6%) for UL; both retain10 critical errors and fail the required495/500 gate. All500 inputs/outputs, range reviews and inheritance/read proofs remain included. These are development results, not fresh/population accuracy, Windows, or whole-app qualification.\n\n' + ('See [' + phase + '/README.md](' + phase + '/README.md) for actual used2754/32 raw and derived lineage, source/adapter/runtime pins, full completed training/recovery history, original frozen source archives and missing text bodies. The existing2014 history and exact2554 prefix are reused without losing raw bytes. Unused reserved240, fresh2 contents, weights and optimizer/RNG binaries are excluded. The prior940-file derived README/manifest/index epoch is retained under the new phase historical directory; prior raw evidence is unchanged.\n').encode('utf-8')
new_readme = old['README.md'] + addition
prospective = {name: dict(entry) for name, entry in old_index['files'].items()}
for name, data in payloads.items():
    assert name not in prospective; prospective[name] = {'bytes': len(data), 'sha256': digest(data)}
prospective['README.md'] = {'bytes': len(new_readme), 'sha256': digest(new_readme)}
prospective['collection-manifest.json'] = {'bytes': len(new_manifest), 'sha256': digest(new_manifest)}
index = {**old_index, 'files': {name: prospective[name] for name in sorted(prospective)}}
new_index = encode(index)
growth = sum(map(len, payloads.values())) + len(new_readme) + len(new_manifest) + len(new_index) - sum(map(len, old.values()))
assert growth <= 20_000_000, ('Actual complete append exceeds root budget', growth)
assert digest((CURATED / 'evidence-files-sha256.json').read_bytes()) == EXPECTED
print(json.dumps({'precopy_exact_growth_bytes': growth, 'new_phase_files': len(payloads), 'old940_preserved_by_raw_or_exact_snapshot': True}), flush=True)

phase_root.mkdir(parents=True)
for name, data in sorted(payloads.items()):
    destination = CURATED / safe(name); destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream: stream.write(data)
for name, previous in old.items(): assert (CURATED / name).read_bytes() == previous
staging = OUT / 'derived-commit'; staging.mkdir()
for name, data in (('README.md', new_readme), ('collection-manifest.json', new_manifest), ('evidence-files-sha256.json', new_index)):
    with (staging / name).open('xb') as stream: stream.write(data)
    os.replace(staging / name, CURATED / name)

files = tree_files(); assert set(files) == set(index['files']) | {'evidence-files-sha256.json'}
for name, entry in index['files'].items():
    path = files[name]; assert not path.is_symlink()
    data = path.read_bytes(); assert len(data) == entry['bytes'] and digest(data) == entry['sha256'], name
for name, entry in old_index['files'].items():
    if name not in DERIVED: assert index['files'][name] == entry
for name in DERIVED: assert payloads[phase + '/historical/previous940-' + name] == old[name]
assert (CURATED / 'README.md').read_bytes().startswith(old['README.md'])
assert len(manifest['files']) == len(index['files']) - 2
assert len({row['path'] for row in manifest['files']}) == len(manifest['files'])
assert {row['path'] for row in manifest['files']} == set(index['files']) - {'README.md', 'collection-manifest.json'}
for row in manifest['files']: assert {'bytes': row['bytes'], 'sha256': row['sha256']} == index['files'][row['path']]
for member in plan['source_archive_members_and_reuse_map']:
    data = (CURATED / member['available_payload_path']).read_bytes()
    assert len(data) == member['bytes'] and digest(data) == member['sha256']
archive_names = {row['path'] for row in plan['audited_original_source_archives']}
for name, path in files.items():
    assert not any(word in name.lower() for word in ('fresh', 'reserved', 'blind')), name
    assert path.suffix.lower() not in {'.gguf','.safetensors','.onnx','.bin','.pt','.pth','.dll','.exe','.so','.zip','.whl','.pyc','.pdb','.nupkg'}, name
    if path.suffix.lower() == '.gz': assert name in archive_names, name
    data = path.read_bytes(); assert not data.startswith((b'\x7fELF', b'MZ', b'GGUF', b'PK\x03\x04')), name
    if name in archive_names:
        with tarfile.open(path) as bundle:
            assert len(bundle.getmembers()) == 40
            for info in bundle.getmembers():
                safe(info.name); assert info.isfile(); bundle.extractfile(info).read().decode('utf-8-sig')
new_bytes = sum(path.stat().st_size for path in files.values())
assert new_bytes - 47_179_924 == growth
receipt = {'schema_version': 1, 'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'status': 'COMPLETED_V7_APPEND_FULL_INDEX_PRESERVATION_SOURCE_LINEAGE_VERIFIED', 'phase': phase,
    'plan': {'path': str(PLAN), 'bytes': PLAN.stat().st_size, 'sha256': digest(PLAN.read_bytes())},
    'collector_sha256': digest(Path(__file__).read_bytes()), 'previous_index_sha256': EXPECTED,
    'new_index_sha256': digest(new_index), 'previous_files': 940, 'new_files': len(files),
    'previous_bytes': 47179924, 'new_bytes': new_bytes, 'growth_bytes': growth, 'growth_cap_bytes': 20000000,
    'old_raw937_unchanged': True, 'previous_three_derived_snapshots_exact': True, 'readme_full_prefix_preserved': True,
    'all_current_index_and_manifest_file_hashes_verified': True, 'all80_source_archive_member_payload_refs_verified': True,
    'original_source_archives': plan['audited_original_source_archives'], 'source_archives_only_binary_exception_verified': True,
    'actual_positive2754_and_prefix2554_lineage_verified': True, 'both_full500_and_all_review_proofs_retained': True,
    'sft_joint': 482, 'ul_joint': 483, 'critical_errors_each': 10, 'quality_gate_passed': False,
    'fresh_or_unused_reserved_data_collected': False, 'main_report_modified': False,
    'model_native_build_or_converter_jobs_run': False, 'git_commit_or_publication_performed': False}
with (OUT / 'application-receipt.json').open('x') as stream: json.dump(receipt, stream, indent=2); stream.write('\n')
with (OUT / 'force-add-paths.txt').open('x') as stream:
    for name in sorted(payloads): stream.write(str((CURATED / name).relative_to(REPO)) + '\n')
    for name in DERIVED: stream.write(str((CURATED / name).relative_to(REPO)) + '\n')
print(json.dumps(receipt, indent=2))
