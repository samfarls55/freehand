"""Bind explicit independent judgments to thirteen personally read actual pairs."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

QUAL = Path('/workspace/freehand/work/cleanup-scribekey-training-2026-11-03/final-qualification')
OWN = Path(__file__).resolve().parent
MANUAL = QUAL / 'control-review-preparation/personal-read-required.json'
LAST_REVIEW = QUAL / 'reviews-primary500/original-control/manual-last76/casewise-reviewed.json'
FIRST_REVIEW = QUAL / 'reviews-primary500/original-control/manual-first76/casewise-reviewed.json'
REPORT = QUAL / 'paired-primary500-01/paired-baseline/core-results.json'
PINS = {
    MANUAL: '877182cfe47ab2b493659da3e6fadde7b536b55093683c52d37af4e1affc73c5',
    LAST_REVIEW: 'f7dbce8ca9884c0edf0625a838ca2e4dba7528ae4e6c3eb08c61d9fa36eb70be',
    FIRST_REVIEW: '240199146df87c0f5542027d2d33331cee93394577ff052228564926c7f959b9',
    REPORT: 'bcf172dc16d50e461f026617ced47bfea9817805cadc553776e6c4aa8bb48933',
}
sha = lambda raw: hashlib.sha256(raw).hexdigest()
canonical = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
for path, expected in PINS.items():
    assert sha(path.read_bytes()) == expected, str(path)
# Do not parse the full report or any corpus/target/check fields.
manual = json.loads(MANUAL.read_text())
last_review = json.loads(LAST_REVIEW.read_text())
first_review = json.loads(FIRST_REVIEW.read_text())
assert last_review['source_report_sha256'] == PINS[REPORT]
assert last_review['manual_packet_sha256'] == PINS[MANUAL]
decisions = json.loads((OWN / 'independent-decisions.json').read_text())
assert len(decisions) == 13
source_by_position = {row['position_one_based']: row for row in manual['cases']}
last_bindings = {row['position_one_based']: row for row in last_review['cases']}
records = []
receipts = []
for position, case_id, faithful, clean, critical, reason, critical_reason in decisions:
    source = source_by_position[position]
    original = last_bindings[position]
    assert all(type(flag) is bool for flag in [faithful, clean, critical])
    for key in ['case_id', 'output_sha256', 'case_structural_sha256']:
        assert source[key] == original[key]
    assert source['case_id'] == case_id
    actual = source['actual_pair']
    assert set(actual) == set(manual['manual_pair_fields'])
    assert sha(actual['output'].encode()) == source['output_sha256']
    records.append({
        'position_one_based': position, 'case_id': case_id,
        'output_sha256': source['output_sha256'],
        'case_structural_sha256': source['case_structural_sha256'],
        'actual_pair_sha256': sha(canonical(actual).encode()),
        'structural_success': source['structural_success'],
        'semantic_faithful': faithful, 'clean_usable': clean, 'critical_error': critical,
        'joint_success': faithful and clean and not critical and source['structural_success'],
        'reason': reason, 'critical_judgment_reason': critical_reason,
        'review_mode': 'independent_personal_read_actual_control_pair_and_frozen_notes_no_oracle',
    })
    receipts.append({
        'position_one_based': position, 'case_id': case_id, 'personally_read': True,
        'frozen_author_notes': source['frozen_author_notes'], 'category': source['category'],
        'actual_pair': actual, 'output_sha256': source['output_sha256'],
        'case_structural_sha256': source['case_structural_sha256'],
        'actual_pair_sha256': sha(canonical(actual).encode()),
        'read_fields': ['normalized_input', 'candidate_text', 'output', 'frozen_author_notes',
                        'cleanup_status', 'structural_success',
                        'raw input and cleanup input when distinct from normalized input'],
    })
assert len({row['case_id'] for row in records}) == 13
b079 = source_by_position[246]
prior_b079 = next(row for row in first_review['cases'] if row['case_id'] == 'r2-b-079')
assert b079['case_id'] == prior_b079['case_id'] == 'r2-b-079'
assert b079['output_sha256'] == prior_b079['output_sha256']
assert b079['case_structural_sha256'] == prior_b079['case_structural_sha256']
supplement = {
    'position_one_based': 246, 'case_id': 'r2-b-079',
    'output_sha256': b079['output_sha256'],
    'case_structural_sha256': b079['case_structural_sha256'],
    'semantic_faithful': False, 'clean_usable': True, 'critical_error': True,
    'structural_success': b079['structural_success'], 'joint_success': False,
    'prior_first76_critical_error': prior_b079['critical_error'],
    'original_receipt_changed': False,
    'reason': (
        "I agree with a critical overlay: 'Keep those tickets and cancel the walking tour' "
        "drops the museum identity, leaving only generic tickets and another distinct booking. "
        "No retained noun identifies the museum booking. This differs from position 437, "
        "whose retained 'book' supplies the same mailing object's identity."),
}
counts = {'reviewed_case_count': len(records)}
counts.update({key: sum(row[key] is True for row in records) for key in [
    'semantic_faithful', 'clean_usable', 'critical_error', 'structural_success', 'joint_success']})
common = {
    'schema_version': 1, 'reviewer': '/root/literal_policy_adjudication (assistant, independent cross-review)',
    'utc': datetime.now(timezone.utc).isoformat(),
    'source_report_sha256': PINS[REPORT], 'manual_packet_sha256': PINS[MANUAL],
    'last76_review_sha256': PINS[LAST_REVIEW], 'first76_review_sha256': PINS[FIRST_REVIEW],
    'frozen_corpus_sha256': manual['frozen_corpus_sha256'],
    'targets_or_checks_used_as_oracles': False,
}
doc = {
    **common, 'scope': 'Exactly thirteen root-flagged last76 cases, plus a separate b079 criticalness supplement.',
    'all13_actual_pairs_personally_read': True,
    'policy_basis': 'Fixed minimal editing policy; preserve substantive facts, negation, uncertainty, voice and deliberate repetition; resolve explicit corrections; valid semantic alternate wording allowed.',
    'cleanup_axis': 'Clean usability is assessed separately from fidelity; fluent text can fail joint success through lost meaning.',
    'counts_for_thirteen_only': counts,
    'cases': records, 'separate_first76_supplement_not_in_counts': supplement,
    'interpretive_limit': (
        'Position 437 uses book as the in-text identity of the same mailing object. '
        'If external context distinguished parcel from book, a different judgment could follow; '
        'the actual pair gives no such distinction. Position 272 fails independently of '
        'how the superseded single-quoted string is protected, because subject-line placement is lost.'),
    'original_reviews_modified': False,
}
def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
write_new(OWN / 'independent-adjudication.json', doc)
write_new(OWN / 'actual-read-receipts.json', {
    **common, 'no_reference_targets_or_checks': True, 'cases': receipts})
for path, expected in PINS.items():
    assert sha(path.read_bytes()) == expected, str(path)
integrity = {
    'all13_case_bindings_match_manual_and_last76_review': True,
    'all13_unique_actual_pairs_personally_read': True,
    'all_original_source_pins_unchanged': True,
    'no_original_review_overwrite': True, 'no_target_check_oracles': True,
    'source_pins': {str(path): digest for path, digest in PINS.items()},
    'artifact_pins': {path.name: sha(path.read_bytes()) for path in OWN.iterdir() if path.is_file()},
}
write_new(OWN / 'integrity.json', integrity)
print(json.dumps({'counts_for_thirteen_only': counts,
                  'joint_success_positions': [row['position_one_based'] for row in records if row['joint_success']],
                  'critical_positions': [row['position_one_based'] for row in records if row['critical_error']],
                  'supplement_b079_critical': True}, indent=2))

