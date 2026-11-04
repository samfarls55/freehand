"""Transfer known judgments only through explicit case equality; no new manual-read claim."""
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path

REPO = Path('/workspace/freehand')
TASK = REPO / 'work/cleanup-scribekey-training-2026-11-03'
HERE = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

controller = module('cache_controller', TASK / 'v7-f32-kv-diagnostic-preparation/run.py')
evaluate = module('training_evaluate', REPO / 'tools/Freehand.Cleanup.Training/evaluate.py')
assert sha(TASK / 'v7-f32-kv-diagnostic-preparation/run.py') == 'e7f6316f0d5a779a93ea155f7a52cb9e027d25acebf034628f733f67774a4c4b'
assert sha(REPO / 'tools/Freehand.Cleanup.Training/evaluate.py') == '131d2db2d5c04d7cca42ece2211c6c0606b6b9380eef15ae2216f3a37de6c7ec'
plans = [
    ('sft-f16-bridge', 'sft', 'd1a60ad4fba3a0f79855dc904195ba567a38c1810a177ba4b135f1e3dc915703', 482),
    ('sft-f32', 'sft', '8d78d829d3833e757ce5f45241d7285839a168558f1a16176f5e7bc1a1f13c29', 482),
    ('ul-f32', 'ul', 'b965dd91df255a4970e57c86e9c66be0668394fdaafe6cd4ea6958e737b630f1', 483),
]
for label, arm, report_sha, expected in plans:
    old_report = TASK / f'evaluation/v7-{arm}-02-native-LoRA-F32-retired-primary500-core/core-results.json'
    old_review = TASK / f'reviews-v7-{arm}-02-native-LoRA-retired500/canonical-reviewed.json'
    expected_review = ('42c53d1befe421b5706c2e9c665aeff1f6a5f8d76723e473ef628ba266bfdcf6' if arm == 'sft'
                       else '6cdcec55744876c87d2dbc6fba613dee848a6c7d476eb36c98503b83401dd0d9')
    assert sha(old_review) == expected_review
    source = json.loads(old_review.read_text())
    assert source['results_sha256'] == sha(old_report)
    old_rows = json.loads(old_report.read_text())['cases']
    report = HERE / label / 'retired500-core/core-results.json'
    assert sha(report) == report_sha
    raw = json.loads(report.read_text())
    assert raw['incomplete'] is False and len(raw['cases']) == 500
    proof = controller.compare_thirteen_fields(old_rows, raw['cases'])
    assert proof['marker_validation_errors'] == []
    different = [row['position'] for row in proof['cases'] if not all(row['nonce_adjusted_equal'].values())]
    assert different == ([158] if label == 'sft-f16-bridge' else [])
    prior = {row['case_id']: row for row in source['cases']}
    rows = []
    for position, (before, after) in enumerate(zip(old_rows, raw['cases']), 1):
        assert before['id'] == after['id']
        previous = prior[after['id']]
        assert previous['output_sha256'] == hashlib.sha256(before['output'].encode()).hexdigest()
        keys = ('case_id', 'semantic_faithful', 'clean_usable', 'critical_error', 'reason')
        row = {key: previous[key] for key in keys}
        row['review_mode'] = 'known_judgment_transfer_under_nonce_validated_13_field_equality_not_new_manual_read'
        if position in different:
            manual = HERE / 'root-sft-f16-bridge-158-review.json'
            assert sha(manual) == '6d0103be1af0d0be45dff3aa542afdaaeb20ef2912d8da0fa2199dee76e1eed6'
            direct = json.loads(manual.read_text())
            assert direct['results_sha256'] == report_sha and direct['input'] == after['normalized_input'] and direct['output'] == after['output']
            row.update({key: direct[key] for key in keys})
            row['review_mode'] = 'root_personally_read_current_actual_pair'
        row.update(position_one_based=position, output_sha256=hashlib.sha256(after['output'].encode()).hexdigest())
        rows.append(row)
    output = HERE / label / 'semantic-judgment-transfer'
    output.mkdir(exist_ok=False)
    proof_path = output / 'case-equality-proof.json'
    proof_path.write_text(json.dumps(proof, indent=2) + '\n')
    canonical = {'schema_version': 1, 'reviewer': 'Codex assistant /root: explicit transfer of prior named semantic judgments under exact case equality; no new 500-case personal-read claim. Bridge158 separately personally read.',
        'results_sha256': report_sha, 'source_semantic_reviewer': source['reviewer'],
        'source_canonical_path': str(old_review), 'source_canonical_sha256': sha(old_review),
        'source_report_sha256': sha(old_report), 'case_equality_proof_sha256': sha(proof_path),
        'transfer_source_sha256': sha(Path(__file__)), 'qualification': 'retired development only', 'cases': rows}
    canonical_path = output / 'canonical-reviewed.json'
    canonical_path.write_text(json.dumps(canonical, indent=2, ensure_ascii=False) + '\n')
    score = evaluate.score_review(evaluate.result_rows(report), canonical, expected_ids={row['id'] for row in raw['cases']})
    assert score['faithful_and_clean_usable'] == expected
    score.update(schema_version=1, results_sha256=report_sha, canonical_review_sha256=sha(canonical_path),
        qualification='retired development only; no fresh or population qualification',
        fresh_qualification_claimed=False, interpretation='Cache precision did not improve joint quality.',
        infrastructure_limitation='UL original outer argv receipt was lost on infrastructure refresh; full original cohort completed without replay and options/deployment were verified.' if arm == 'ul' else None,
        utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (output / 'semantic-summary.json').write_text(json.dumps(score, indent=2) + '\n')
    print(label, score['faithful_and_clean_usable'], sha(canonical_path))
