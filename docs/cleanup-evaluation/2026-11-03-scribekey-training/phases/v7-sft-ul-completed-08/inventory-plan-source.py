#!/usr/bin/env python3
"""Plan only: select completed V7 text evidence, never modify the curated tree."""
from pathlib import Path
import datetime
import hashlib
import json
import tarfile
from pathlib import PurePosixPath

REPO = Path('/workspace/freehand')
TASK = REPO / 'work/cleanup-scribekey-training-2026-11-03'
CURATED = REPO / 'docs/cleanup-evaluation/2026-11-03-scribekey-training'
OUT = Path(__file__).resolve().parent
PHASE = 'phases/v7-sft-ul-completed-08'
EXPECTED_INDEX = 'bf9212b5ae7e5d7889027c8d41d7508ca7de8e2aa3b91bfb0f02fed8094b5873'
ALLOWED = {'.json', '.jsonl', '.md', '.py', '.txt', '.log', '.sha256', '.tsv', '.trx', '.ps1', '.cs', '.csproj', '.props', '.config', '.h'}
selected = {}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def add(relative, destination, group, reason):
    source = TASK / relative
    assert source.is_file() and not source.is_symlink(), str(source)
    assert source.suffix.lower() in ALLOWED or source.name in ('LICENSE', 'NOTICE'), str(source)
    assert not any(value in destination.casefold() for value in ('fresh', 'reserved', 'blind'))
    assert not any(value in source.parts for value in ('fresh2', 'reserved240'))
    dest = PHASE + '/' + destination
    assert dest not in selected, dest
    selected[dest] = {'path': dest, 'source_path': str(source), 'bytes': source.stat().st_size,
                      'sha256': sha(source), 'group': group, 'reason': reason}


def tree(relative, destination, group, reason):
    source = TASK / relative
    assert source.is_dir(), str(source)
    for path in sorted(source.rglob('*')):
        if path.is_file() and (path.suffix.lower() in ALLOWED or path.name in ('LICENSE', 'NOTICE')):
            add(str(path.relative_to(TASK)), destination + '/' + path.relative_to(source).as_posix(), group, reason)


assert sha(CURATED / 'evidence-files-sha256.json') == EXPECTED_INDEX
old_manifest = json.loads((CURATED / 'collection-manifest.json').read_text())
old_index = json.loads((CURATED / 'evidence-files-sha256.json').read_text())
old_by_source = {row.get('source_path_historical'): row for row in old_manifest['files']}

for name in ('positive-2754-final.jsonl', 'positive-2754-final-manifest.json', 'positive-2754-provenance.jsonl',
             'positive-2754-source-exposures.json', 'positive-2754-content-hashes.json',
             'positive-2754-token-checks.jsonl', 'positive-2754-disclosed-duplicates.json',
             'positive-2754-input-target-conflicts.json', 'positive-2754-independent-structural-review.json',
             'positive-2754-normalized-hash-collision-clarification.json'):
    add('audit/v7-positive-curriculum/' + name, 'data/positive/' + name, 'positive2754', 'Actual shared positive file and complete source/exposure/tokenization/duplicate/independent-review derivation')
# Opaque metadata only; contains no fresh-case text or identifiers, and is not a data source.
add('audit/v7-positive-curriculum/root-opaque-round2-final-positive-and-ul-overlap.json',
    'data/positive/root-opaque-overlap-attestation.json', 'positive2754', 'Root overlap attestation metadata; no private corpus is collected')

for source_root, dest_root, files in (
    ('audit/v6-future-contrasts', 'data/used-270', ('train-270-v1.jsonl', 'manifest-v1.json', 'independent-review-rollup-v1.json',
       'core-normalization-v1/train-270-core-normalized-v1.jsonl', 'core-normalization-v1/manifest.json',
       'core-normalization-v1/normalization-cleanup-pipeline-independent-zero-delta-review.json')),
    ('audit/v7-additional-100', 'data/used-100', ('train-100-v1.jsonl', 'manifest-v1.json', 'root-independent-rollup-v1.json',
       'core-normalization-v1/train-100-core-normalized-v1.jsonl', 'core-normalization-v1/manifest.json',
       'core-normalization-v1/normalization-cleanup-pipeline-independent-zero-delta-review.json'))):
    for name in files:
        add(source_root + '/' + name, dest_root + '/' + name, 'positive_sources', 'Actually used raw gold + Core-normalized derivative, manifests and independent semantic/normalization review')
for name in ('contrast-32-v4.jsonl', 'root-independent-v4-review.json', 'manifest-v4.json'):
    add('audit/v7-reserved-unlikelihood/' + name, 'data/used-ul32/canonical/' + name, 'used32', 'Only the explicitly approved32 used events; unused reserved240 and earlier negative drafts excluded')
for name in ('events-32-bound.jsonl', 'binding-receipt.json', 'independent-binding-audit.json'):
    add('audit/v7-unlikelihood-bound/' + name, 'data/used-ul32/bound/' + name, 'used32', 'Exact actual32 events bound to all64 positive copies and source/mask/token mapping')

add('pipeline/v7-two-arm-preflight.json', 'training/two-arm-preflight.json', 'training', 'Preregistered same source/data/recipe except eta/output')
for arm, cut in (('sft', 192), ('ul', 32)):
    for version in ('01', '02'):
        run = 'v7-' + arm + '-' + version
        for name in ('adapter-config.json', 'training-source.py', 'training-log.jsonl', 'frozen-base-provenance.json',
                     'unlikelihood-provenance.json', 'latest-checkpoint.json'):
            add('pipeline/' + run + '/' + name, 'training/' + run + '/' + name, 'training', 'Raw per-run source/config/base/Q8/UL provenance and logs; no weight or optimizer/RNG binary')
        for name in ('launch.json', 'prelaunch.json'):
            add('pipeline/' + run + '-' + name, 'training/launch/' + run + '-' + name, 'training', 'Actual launch and cutoff/data/parent/source registration')
        if version == '02':
            for name in ('canonical-training-log.jsonl', 'overlap-replay-complete-proof.json', 'overlap-replay-initial-proof.json',
                         'final-verification.json', 'training-result.json'):
                add('pipeline/' + run + '/' + name, 'training/' + run + '/' + name, 'training', 'Completed345-step canonical lineage, preserved15 replay comparisons, final adapter identity')
        checkpoint = cut if version == '01' else 336
        for name in ('resume-state.json', 'adapter-config.json', 'training-source.py'):
            add('pipeline/' + run + '/checkpoints/step-' + str(checkpoint).zfill(6) + '/' + name,
                'training/' + run + '/checkpoints/step-' + str(checkpoint).zfill(6) + '/' + name,
                'training', 'Actual cutoff/RNG inventory metadata only; omitted binaries stay pinned by hash/size without final345 RNG claim')
    for name in ('first-observed-rng-step-000016.json', 'interrupted-status.json'):
        source = 'pipeline/v7-' + arm + '-01/' + name
        if (TASK / source).is_file():
            add(source, 'training/v7-' + arm + '-01/' + name, 'training', 'Original interrupted-run status remains historical and distinct from completed recovery')
    export_dir = 'native-lora-v7-' + arm + '-02-export'
    tree(export_dir, 'native/' + arm, 'native', 'Actual byte-identity conversion/controller/notices/native/runtime/managed pins and post-Core handoff; no weights copied')
    eval_root = 'evaluation/v7-' + arm + '-02-native-LoRA-F32'
    add(eval_root + '-freeze.json', 'evaluation/' + arm + '/candidate-freeze.json', 'core500', 'Actual model/adapter/runtime/six-DLL/source freeze; training and runtime bases remain distinct')
    tree(eval_root + '-retired-primary500-core', 'evaluation/' + arm + '/retired500', 'core500', 'Complete actual ordered500 Core inputs/outputs, all provider outcomes and deployment postchecks')

tree('reviews-v7-sft-02-native-LoRA-retired500', 'reviews/sft-retired500', 'sft_review', 'Entire completed500 canonical review and all raw range, inheritance, read-record and merge proofs')
tree('reviews-v7-ul-02-native-LoRA-retired500', 'reviews/ul-retired500', 'ul_review', 'Entire completed500 canonical review and all raw range, inheritance, root20 actual-pair cross-review, read-record and merge proofs')
for name in ('build_positive_2754_final.py', 'build_positive_2554_provisional.py'):
    add('audit/' + name, 'data/builders/' + name, 'data_builders', 'Actual final/preserved-prefix dataset builders, no unused provisional data duplication')
add('audit/v7-two-arm-training-comparison/training-metadata.json', 'training/two-arm-comparison.json', 'training', 'Final paired same-recipe training metadata and actual source/data/parent/eta lineage')
tree('v7-native-export-preparation/historical/sft-executed-54a7c62d', 'controller/historical/sft-executed-54a7c62d',
     'controller', 'Exact previously executed/audited SFT controller/tests/docs/audit snapshot preserved')
for name in ('run.py', 'test_controller.py', 'README.md', 'arm-recovery-preparation-status.json', 'arm-recovery-preparation-tests.log',
             'independent-ul32-preexecution-review-20261104T022326Z.json', 'independent-guard-tests-20261104T022113Z.json',
             'independent-guard-tests-20261104T022113Z.log'):
    source = 'v7-native-export-preparation/' + name
    if (TASK / source).is_file():
        add(source, 'controller/ul-current/' + name, 'controller', 'Exact current UL32 recovery guard source/test/docs/audit; source-only preparation not relabeled as prior SFT execution')
for name in ('pipeline.py', 'test_unlikelihood.py', 'legacy_pipeline_baseline.py', 'actual-legacy-oracle-test-snapshot.py',
             'tiny-tests-20261104T010414Z.json', 'tiny-tests-20261104T010414Z.log',
             'portable-tiny-tests-20261104T010531Z.json', 'portable-tiny-tests-20261104T010531Z.log',
             'independent-postapply-byte-confirmation-20261104T011150Z.json'):
    add('prototypes/v7-unlikelihood/' + name, 'source/ul-objective/' + name, 'source_tests', 'Actual approvedUL source and independent math/index/no-extra-forward/eta0 identity/resume/API and apply provenance')

# Preserve both exact original pre-run source archives, and make missing text bodies readable.
# Reuse already-curated/selected identical byte payloads rather than duplicating unchanged sources.
source_members = []
archive_records = []
old_content = {}
for name, entry in old_index['files'].items():
    old_content.setdefault(entry['sha256'], name)
for arm in ('sft', 'ul'):
    freeze_path = TASK / ('evaluation/v7-' + arm + '-02-native-LoRA-F32-freeze.json')
    freeze_data = json.loads(freeze_path.read_text())
    archive_entry = freeze_data['source_snapshot']
    archive = Path(archive_entry['path'])
    assert archive.stat().st_size == archive_entry['bytes'] and sha(archive) == archive_entry['sha256']
    archive_dest = PHASE + '/source/frozen-code-archives/' + arm + '.source-snapshot.tar.gz'
    selected[archive_dest] = {'path': archive_dest, 'source_path': str(archive), 'bytes': archive.stat().st_size,
        'sha256': sha(archive), 'group': 'source_archives', 'source_kind': 'audited_source_archive',
        'reason': 'Exact original candidate-freeze source archive; strict40 textual members only, no model/native/cache files'}
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        assert len(members) == 40
        names = {member.name for member in members}
        assert names == set(freeze_data['sources']) | {'source-files-sha256.json'}
        for member in members:
            relative = PurePosixPath(member.name)
            assert member.isfile() and not relative.is_absolute() and '..' not in relative.parts
            assert Path(member.name).suffix in ALLOWED
            data = bundle.extractfile(member).read()
            data.decode('utf-8-sig')
            assert not data.startswith((b'\x7fELF', b'MZ', b'GGUF', b'PK\x03\x04'))
            digest = hashlib.sha256(data).hexdigest()
            if member.name == 'source-files-sha256.json':
                assert json.loads(data)['files'] == freeze_data['sources']
            else:
                assert digest == freeze_data['sources'][member.name]
            existing_selected = next((value['path'] for value in selected.values() if value['sha256'] == digest), None)
            if digest in old_content:
                target, reuse = old_content[digest], 'previous940_byte_identical'
            elif existing_selected:
                target, reuse = existing_selected, 'newphase_byte_identical'
            else:
                target, reuse = PHASE + '/source/frozen-missing-text/' + member.name, 'new_archive_member_payload'
                selected[target] = {'path': target, 'source_path': str(archive) + '!' + member.name,
                    'source_archive': str(archive), 'source_archive_sha256': sha(archive),
                    'archive_member': member.name, 'source_kind': 'text_source_archive_member',
                    'bytes': len(data), 'sha256': digest, 'group': 'missing_source_text',
                    'reason': 'Exact executed pre-run source bytes extracted from immutable source snapshot, never current work-repo bytes'}
            source_members.append({'arm': arm, 'archive_path': archive_dest, 'member': member.name,
                'bytes': len(data), 'sha256': digest, 'available_payload_path': target, 'reuse': reuse})
    archive_records.append({'arm': arm, 'path': archive_dest, 'bytes': archive.stat().st_size,
        'sha256': sha(archive), 'all40_members_text_only': True, 'code_source_count': 39})
for key, expected in (
    ('evaluation/sft/retired500/core-results.json', '4700963b733ea1bf9239d1a463b1d9fa230b96a48705bea87737bca87369cb8f'),
    ('evaluation/ul/retired500/core-results.json', 'a17350154d4553514b3e67d14df6f7f7e3e1af49c890e682edc872699fa34b82'),
    ('reviews/sft-retired500/canonical-reviewed.json', '42c53d1befe421b5706c2e9c665aeff1f6a5f8d76723e473ef628ba266bfdcf6'),
    ('reviews/ul-retired500/canonical-reviewed.json', '6cdcec55744876c87d2dbc6fba613dee848a6c7d476eb36c98503b83401dd0d9')):
    assert selected[PHASE + '/' + key]['sha256'] == expected
assert selected[PHASE + '/reviews/ul-retired500/root-cross-review-read-record.json']['sha256'].startswith('b61bf21e')

inherit = []
for source in ('audit/v6-full-history-curriculum/full-history-candidate.jsonl',
               'audit/v6-full-history-curriculum/manifest.json',
               'audit/v6-full-history-curriculum/normalization-changes-cleanup-pipeline-semantic-review.json'):
    entry = old_by_source[str(TASK / source)]
    assert entry['sha256'] == old_index['files'][entry['path']]['sha256']
    inherit.append({'source_path': str(TASK / source), 'existing_curated_path': entry['path'],
                    'bytes': entry['bytes'], 'sha256': entry['sha256'], 'copied_again': False})

old_derived = [{'source_path': str(CURATED / name), 'destination': PHASE + '/historical/previous940-' + name,
                'bytes': (CURATED / name).stat().st_size, 'sha256': sha(CURATED / name)}
               for name in ('README.md', 'collection-manifest.json', 'evidence-files-sha256.json')]
groups = {}
for row in selected.values():
    group = groups.setdefault(row['group'], {'files': 0, 'bytes': 0})
    group['files'] += 1; group['bytes'] += row['bytes']
raw_total = sum(row['bytes'] for row in selected.values())
snapshots = sum(row['bytes'] for row in old_derived)
ul_review_reserve = 0
derived_growth_reserve = 500_000
projected = raw_total + snapshots + ul_review_reserve + derived_growth_reserve
plan = {'schema_version': 1, 'status': 'FINAL_SELECTION_PLAN_ONLY_ROOT_AUTHORIZES_APPLY_AFTER_EXACT_SIZE_CHECK',
    'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'phase': PHASE,
    'curated_precondition': {'file_count': 940, 'total_bytes': 47179924, 'index_sha256': EXPECTED_INDEX},
    'selected_file_count': len(selected), 'selected_bytes': raw_total, 'group_totals': groups,
    'selected_files': list(selected.values()), 'historical_previous940_snapshots': old_derived,
    'historical_snapshot_bytes': snapshots, 'existing_curated_history_references': inherit,
    'source_archive_members_and_reuse_map': source_members, 'audited_original_source_archives': archive_records,
    'unwritten_pending_items': [{'scope': 'New README qualification/table update, complete collection-manifest/index growth and collector/plan/reconstruction metadata',
                                 'estimated_max_net_bytes': derived_growth_reserve}],
    'projected_new_growth_bytes': projected, 'new_growth_cap_bytes': 20_000_000,
    'projected_headroom_bytes': 20_000_000 - projected, 'within_budget_before_pending_finalization': projected <= 20_000_000,
    'prefix_lineage_without_duplicate_payload': {'final_path': PHASE + '/data/positive/positive-2754-final.jsonl',
        'prefix_byte_range': [0, 4138815], 'prefix_sha256': '8e31598f65e695001b37d8920e44b93f6e6fb2a24ae6d0cf8e8387dd1b4a51a9',
        'prefix_rows': 2554, 'already_present_exactly_as_final_file_prefix': True,
        'separate_provisional2554_payload_not_copied': True, 'reason': 'All raw prefix bytes are present inside the final actually-trained file; range/hash and derivation remain explicit without duplicating4.1MB unused provisional artifact'},
    'excluded': ['adapter/base/PEFT/GGUF model weights', 'optimizer.pt/rng.pt and model cache binaries',
                 'unused reserved240 contents', 'fresh2 contents or future holdout authoring files',
                 'earlier unused negative drafts', 'unused2554 provisional payload copy (raw bytes preserved by final prefix)',
                 'unused provisional2554 derived reports (final2754 reports retained)', 'new broad546/hard80 not run for this arm'],
    'apply_preconditions': ['Root approves this size/selection plan', 'Actual UL500 reviews complete and receipt-bound (allcurrentreviewfilesselected)',
        'Rehash every source and verify expected core470096 and canonical42c53/current UL a173 inputs',
        'Capture previous940 three derived documents before any replacement',
        'Recompute exact added bytes including all derived net growth; never exceed20,000,000B',
        'Append newphase exclusively; verify old raw940 entries unchanged except snapshotted derived3',
        'Independent final current-index/full-tree/prefix/exclusion verification'],
    'mutated_curated_index_readme_report_or_existing_files': False, 'native_model_build_or_converter_jobs_run': False}
assert sha(CURATED / 'evidence-files-sha256.json') == EXPECTED_INDEX
path = OUT / 'selection-size-plan-v2.json'
with path.open('x') as stream:
    json.dump(plan, stream, indent=2); stream.write('\n')
print(json.dumps({key: plan[key] for key in ('status', 'selected_file_count', 'selected_bytes', 'group_totals',
    'historical_snapshot_bytes', 'projected_new_growth_bytes', 'projected_headroom_bytes', 'within_budget_before_pending_finalization')}, indent=2))
print(path)
