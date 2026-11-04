"""Bind already authored personal judgments to the first 76 control manual pairs."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT = Path('/workspace/freehand')
QUAL = ROOT / 'work/cleanup-scribekey-training-2026-11-03/final-qualification'
OWN = Path(__file__).resolve().parent
MANUAL = QUAL / 'control-review-preparation/personal-read-required.json'
COMPARISON = QUAL / 'control-review-preparation/comparison-and-inheritance-packet.json'
REPORT = QUAL / 'paired-primary500-01/paired-baseline/core-results.json'
ORIGINAL_PACKET = QUAL / 'reviews-primary500/original-control/review-packet.json'
PINS = {
    MANUAL: '877182cfe47ab2b493659da3e6fadde7b536b55093683c52d37af4e1affc73c5',
    COMPARISON: '8fc25a9adf49f075a16813d3531f30563f3b478bf7e257d1cf7a790a7527877c',
    REPORT: 'bcf172dc16d50e461f026617ced47bfea9817805cadc553776e6c4aa8bb48933',
    ORIGINAL_PACKET: '65d71af17461cbb7641e281dfc202d09930ffa9e7f50f77961986e84d4d7a870',
}
sha = lambda raw: hashlib.sha256(raw).hexdigest()
canonical = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
for path, digest in PINS.items():
    assert sha(path.read_bytes()) == digest, str(path)
manual = json.loads(MANUAL.read_text())
comparison = json.loads(COMPARISON.read_text())
# No report/corpus targets or checks are parsed in this personal-review binder.
assigned = manual['cases'][:76]
decisions_path = OWN / 'personal-decisions.json'
decisions = json.loads(decisions_path.read_text())
assert len(manual['cases']) == 152 and len(comparison['cases']) == 500
assert len(assigned) == len(decisions) == 76
assert [item[0] for item in decisions] == [row['case_id'] for row in assigned]
assert len({row['case_id'] for row in assigned}) == 76

pins = {
    'results_sha256': PINS[REPORT], 'original_review_packet_sha256': PINS[ORIGINAL_PACKET],
    'comparison_packet_sha256': PINS[COMPARISON], 'manual_packet_sha256': PINS[MANUAL],
    'frozen_corpus_sha256': manual['frozen_corpus_sha256'],
}
reviewed = []
read_receipts = []
for manual_position, (source, decision) in enumerate(zip(assigned, decisions), 1):
    case_id, faithful, clean, critical, reason, *concerns = decision
    assert all(type(value) is bool for value in [faithful, clean, critical])
    actual = source['actual_pair']
    assert set(actual) == set(manual['manual_pair_fields'])
    assert sha(actual['output'].encode()) == source['output_sha256']
    structural = source['structural_success']
    assert type(structural) is bool
    joint = faithful and clean and structural and not critical
    if not structural:
        assert actual['cleanup_status'] == 'Failed'
        assert source['forced_joint_success_false'] and not source['joint_credit_allowed_after_personal_review']
        assert joint is False
    receipt = {
        'manual_position_one_based': manual_position,
        'position_one_based': source['position_one_based'], 'case_id': case_id,
        'personally_read': True,
        'read_fields': ['normalized_input', 'candidate_text', 'output', 'frozen_author_notes',
                        'cleanup_status', 'structural_success',
                        'input (same as normalized unless separately displayed)',
                        'cleanup_input (same as normalized unless separately displayed)'],
        'category': source['category'], 'frozen_author_notes': source['frozen_author_notes'],
        'author_needs_cleanup_flag': source['author_needs_cleanup_flag'],
        'author_critical_probe_flag': source['author_critical_probe_flag'],
        'actual_pair': actual,
        'actual_pair_sha256': sha(canonical(actual).encode()),
        'output_sha256': source['output_sha256'],
        'case_structural_sha256': source['case_structural_sha256'],
        'structural_success': structural,
        'read_receipt_source': 'Actual pair displayed without target/check values in four complete batches of nineteen.',
    }
    read_receipts.append(receipt)
    reviewed.append({
        'manual_position_one_based': manual_position,
        'position_one_based': source['position_one_based'], 'case_id': case_id,
        'output_sha256': source['output_sha256'],
        'case_structural_sha256': source['case_structural_sha256'],
        'actual_pair_sha256': receipt['actual_pair_sha256'],
        'structural_success': structural,
        'semantic_faithful': faithful, 'clean_usable': clean, 'critical_error': critical,
        'joint_success': joint, 'reason': reason,
        'root_adjudication_note': concerns[0] if concerns else None,
        'provider_failure_with_delivered_fallback': actual['cleanup_status'] == 'Failed',
        'review_mode': 'personally_read_actual_control_normalized_candidate_delivered_and_notes_no_inheritance',
    })
counts = {'total': len(reviewed)}
counts.update({key: sum(row[key] for row in reviewed) for key in [
    'semantic_faithful', 'clean_usable', 'critical_error', 'structural_success', 'joint_success']})
doc = {
    'schema_version': 1, 'role': 'original-control',
    'reviewer': '/root/literal_policy_adjudication (assistant)',
    'utc': datetime.now(timezone.utc).isoformat(),
    **pins,
    'scope': 'Exactly manual-packet positions 1 through 76, not the complete 500-control denominator.',
    'all_assigned_cases_personally_read': True, 'development_judgment_inheritance_count': 0,
    'selected_judgment_inheritance_count': 0, 'targets_or_checks_used_as_oracles': False,
    'policy': manual['policy'],
    'parent_policy_adjudication_applied': (
        'Ordinary unquoted identifiers may resolve to final corrected values; '
        'protected quotes/dictionary opaque identifiers must survive once in source order.'),
    'cleanup_axis': (
        'Clean usability assesses the delivered text form separately from fidelity; '
        'a fluent but unfaithful output can pass this axis while failing joint success.'),
    'counts': counts, 'cases': reviewed,
}
def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
write_new(OWN / 'casewise-reviewed.json', doc)
for start in range(0, 76, 19):
    stop = start + 19
    write_new(OWN / ('read-receipts-%03d-%03d.json' % (start + 1, stop)), {
        'schema_version': 1, 'reviewer': doc['reviewer'], **pins,
        'manual_start_one_based': start + 1, 'manual_end_one_based': stop,
        'no_reference_targets_or_checks': True, 'cases': read_receipts[start:stop]})
summary = {
    **pins, 'assigned_manual_start': 1, 'assigned_manual_end': 76,
    'all76_personally_read': True, 'counts': counts,
    'critical_case_ids': [row['case_id'] for row in reviewed if row['critical_error']],
    'root_adjudication_case_ids': [row['case_id'] for row in reviewed if row['root_adjudication_note']],
    'structural_failed_case_ids': [row['case_id'] for row in reviewed if not row['structural_success']],
    'failed_provider_joint_credit': 0,
    'limits': 'This shard does not finish original-control review or make any aggregate qualification claim.',
}
write_new(OWN / 'summary.json', summary)
for path, digest in PINS.items():
    assert sha(path.read_bytes()) == digest, str(path)
integrity = {
    'assigned_ids_exactly_first76_manual_packet_ids': True,
    'assigned_case_count': 76, 'unique_assigned_ids': 76,
    'all76_personally_read': True, 'all_output_and_pair_hashes_bound': True,
    'all_original_source_pins_unchanged': True,
    'new_semantic_flags_are_explicit_personal_decisions': True,
    'joint_formula': 'semantic_faithful AND clean_usable AND structural_success AND NOT critical_error',
    'all_failed_providers_forced_zero_joint_credit': True,
    'source_pins': {str(path): digest for path, digest in PINS.items()},
    'artifact_pins': {path.name: sha(path.read_bytes()) for path in OWN.iterdir() if path.is_file()},
}
write_new(OWN / 'review-integrity.json', integrity)
print(json.dumps(summary, indent=2))

