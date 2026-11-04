#!/usr/bin/env python3
"""Known consumed cohorts only: inherit exact prior successes; assign no new passes.

No default new report exists. Call only with a complete, postverified report and
its explicit SHA. Manual packets omit target/check fields; those compare solely
as part of strict typed identity. This helper executes no model or native worker.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

WORK = Path('/workspace/freehand/work/cleanup-scribekey-training-2026-11-03')
FIELDS = ['input', 'normalized_input', 'cleanup_input', 'candidate_text', 'output',
          'cleanup_status', 'error', 'insertion_count', 'delivered_count',
          'delivery_outcome', 'dictation_outcome', 'normalized_targets', 'normalized_checks']
PAIR_FIELDS = FIELDS[:11]
SPECS = {
    'development546': {
        'count': 546, 'expected_prior_joint': 545, 'expected_prior_critical': 0,
        'report_path': str(WORK / 'evaluation/v6-01-native-LoRA-F32-development546-core/core-results.json'),
        'report_sha256': 'ef31c0d71f0522f1dd0e2e2395c974691b85f5fd80a3d45802d658db452666a2',
        'review_path': str(WORK / 'reviews-v6-native-LoRA-development546/canonical-reviewed.json'),
        'review_sha256': 'f1e45ade9327d8eef10a6c80f69aa51a9f288f93fecc9702f22222b69cdbe207'},
    'hard80': {
        'count': 80, 'expected_prior_joint': 79, 'expected_prior_critical': 1,
        'report_path': str(WORK / 'evaluation/v6-01-native-LoRA-F32-hard80-core/core-results.json'),
        'report_sha256': 'f8de71c7f3fde2035dcda874a2c270046f2ef1030adfea6cf53abb448e3e99ae',
        'review_path': str(WORK / 'reviews-v6-01-native-LoRA-hard80/hard80-reviewed.json'),
        'review_sha256': '10c93fbf1f375f945f0570bd82e96684096f0aa0409f8843e330e5022294cee8'}
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def typed_equal(left, right):
    """Preserve nested JSON types, list order, numeric types and signed zero."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(typed_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(typed_equal(a, b) for a, b in zip(left, right))
    require(type(left) in (str, int, float, bool, type(None)), 'Only JSON values are supported')
    require(type(left) is not float or math.isfinite(left) and math.isfinite(right), 'Nonfinite JSON scalar')
    return canonical(left) == canonical(right)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def load_pinned(path, expected):
    raw = Path(path).read_bytes()
    require(sha(raw) == expected, 'Pinned source digest mismatch: ' + str(path))
    def invalid_constant(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def structural(case):
    return (case['cleanup_status'] in ('Applied', 'Unchanged') and case['error'] is None
            and type(case['insertion_count']) is int and case['insertion_count'] == 1
            and type(case['delivered_count']) is int and case['delivered_count'] == 1
            and case['delivery_outcome'] == 'Delivered' and case['dictation_outcome'] == 'Success')


def joint_success(review):
    return (review['semantic_faithful'] is True and review['clean_usable'] is True
            and review['critical_error'] is False)


def build_packet(old, prior, new, spec, new_report_sha):
    require(prior['results_sha256'] == spec['report_sha256'], 'Prior review binds a different report')
    require(old.get('incomplete') is False and new.get('incomplete') is False,
            'Incomplete or missing completeness marker cannot be compared')
    require(all(type(doc.get('cases')) is list and len(doc['cases']) == spec['count']
                for doc in (old, prior, new)), 'Exact complete denominator required')
    ids = [row['id'] for row in old['cases']]
    require(all(type(value) is str and value for value in ids) and len(set(ids)) == spec['count'],
            'Baseline IDs must be complete, nonempty and unique')
    require([row['id'] for row in new['cases']] == ids
            and [row['case_id'] for row in prior['cases']] == ids,
            'Exact ordered baseline/report/review IDs required')
    require(sum(joint_success(row) for row in prior['cases']) == spec['expected_prior_joint']
            and sum(row['critical_error'] is True for row in prior['cases']) == spec['expected_prior_critical'],
            'Prior canonical semantic totals differ')
    result = []
    for position, (before, review, after) in enumerate(zip(old['cases'], prior['cases'], new['cases']), 1):
        require(all(key in before and key in after for key in FIELDS), 'Missing one of the exact13 comparison fields')
        require(type(before['output']) is str and type(after['output']) is str, 'Actual output must be text')
        require(all(type(review.get(key)) is bool for key in ('semantic_faithful', 'clean_usable', 'critical_error')),
                'Prior semantic flags must be actual booleans')
        require(review['output_sha256'] == sha(before['output'].encode()), 'Prior judgment output binding differs')
        comparisons = {key: typed_equal(before[key], after[key]) for key in FIELDS}
        inherit = all(comparisons.values()) and structural(before) and structural(after) and joint_success(review)
        item = {'position_one_based': position, 'case_id': after['id'],
                'output_sha256': sha(after['output'].encode()),
                'case_structural_sha256': sha(canonical(after).encode()),
                'exact_fields_equal': comparisons, 'inherit_successful_prior_joint_pass': inherit,
                'prior_structural_success': structural(before), 'new_structural_success': structural(after),
                'prior_review': review,
                'review_mode': 'strict_typed_13_field_successful_prior_joint_pass_inheritance' if inherit else 'needs_personal_read'}
        if not inherit:
            item['actual_pair'] = {key: after[key] for key in PAIR_FIELDS}
            item['previous_output'] = before['output']
            item['new_semantic_judgment_assigned'] = False
        result.append(item)
    return {'schema_version': 1, 'purpose': 'Already consumed known-set regression review preparation only.',
            'source_report_sha256': new_report_sha, 'prior_report_sha256': spec['report_sha256'],
            'prior_canonical_review_sha256': spec['review_sha256'], 'case_count': spec['count'],
            'ordered_case_ids_sha256': sha(canonical(ids).encode()), 'exact_fields': FIELDS,
            'strict_nested_JSON_types_required': True, 'manual_pair_fields': PAIR_FIELDS,
            'target_check_fields_compared_for_identity_only': ['normalized_targets', 'normalized_checks'],
            'manual_pair_contains_target_or_check_oracle': False, 'new_semantic_passes_assigned': 0,
            'inheritance_count': sum(row['inherit_successful_prior_joint_pass'] for row in result),
            'personal_read_required': sum(not row['inherit_successful_prior_joint_pass'] for row in result),
            'cases': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', choices=tuple(SPECS), required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--report-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Create-only output; preserve previous packets')
    require(not any('blind' in part.casefold() for part in args.report.parts), 'Only consumed known-set reports are supported')
    spec = SPECS[args.cohort]
    old = load_pinned(spec['report_path'], spec['report_sha256'])
    prior = load_pinned(spec['review_path'], spec['review_sha256'])
    new = load_pinned(args.report, args.report_sha256)
    packet = build_packet(old, prior, new, spec, args.report_sha256)
    packet.update(cohort=args.cohort, helper_source_sha256=sha(Path(__file__).read_bytes()))
    args.output.mkdir(parents=True)
    target = args.output / 'comparison-and-inheritance-packet.json'
    with target.open('x') as stream:
        json.dump(packet, stream, indent=2, ensure_ascii=False, allow_nan=False); stream.write('\n')
    print(json.dumps({key: packet[key] for key in ('cohort', 'case_count', 'inheritance_count', 'personal_read_required')}))


if __name__ == '__main__':
    main()
