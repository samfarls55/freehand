"""Prepare development-only review inheritance; never assign new semantic passes."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_REPORT = ROOT / 'evaluation/v8-01-native-LoRA-F32-retired-primary500-core/core-results.json'
OLD_REVIEW = ROOT / 'reviews-v8-01-native-LoRA-retired500/canonical-reviewed.json'
OLD_REPORT_SHA = '7d492ecb55fb7dc1ef537f1b7c575fece3aad838ac5fff7ca17a2214ed6c3a70'
OLD_REVIEW_SHA = 'fe07736284eda5a8b8425c90b537f217e7c984d94b7e2420d375c8c5e1bfdae7'
FIELDS = ['input', 'normalized_input', 'cleanup_input', 'candidate_text', 'output',
          'cleanup_status', 'error', 'insertion_count', 'delivered_count',
          'delivery_outcome', 'dictation_outcome', 'normalized_targets', 'normalized_checks']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_pinned(path, expected):
    raw = path.read_bytes()
    if sha(raw) != expected:
        raise ValueError('Pinned source digest mismatch: ' + str(path))
    return json.loads(raw)


def structural(case):
    return (case['cleanup_status'] in ('Applied', 'Unchanged') and case['error'] is None
            and type(case['insertion_count']) is int and case['insertion_count'] == 1
            and type(case['delivered_count']) is int and case['delivered_count'] == 1
            and case['delivery_outcome'] == 'Delivered' and case['dictation_outcome'] == 'Success')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--report-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    old = load_pinned(OLD_REPORT, OLD_REPORT_SHA)
    prior = load_pinned(OLD_REVIEW, OLD_REVIEW_SHA)
    new = load_pinned(args.report, args.report_sha256)
    if prior['results_sha256'] != OLD_REPORT_SHA:
        raise ValueError('Prior semantic review is bound to a different report')
    if new.get('incomplete') is not False or old.get('incomplete') is not False:
        raise ValueError('A partial report cannot be used for a complete-cohort comparison')
    if not all(len(doc['cases']) == 500 for doc in (old, prior, new)):
        raise ValueError('Exactly 500 cases required in all sources')
    ids = [case['id'] for case in old['cases']]
    if len(set(ids)) != 500 or [case['id'] for case in new['cases']] != ids:
        raise ValueError('The full ordered development inventory must remain identical')
    if [case['case_id'] for case in prior['cases']] != ids:
        raise ValueError('The prior review inventory is not aligned')
    result = []
    for pos, (before, review, after) in enumerate(zip(old['cases'], prior['cases'], new['cases']), 1):
        if review['output_sha256'] != sha(before['output'].encode()):
            raise ValueError('Prior judgment has incorrect output binding')
        comparisons = {key: before[key] == after[key] for key in FIELDS}
        inherit = (all(comparisons.values()) and structural(before) and structural(after)
                   and review['semantic_faithful'] is True and review['clean_usable'] is True
                   and review['critical_error'] is False)
        item = {'position_one_based': pos, 'case_id': after['id'],
                'output_sha256': sha(after['output'].encode()),
                'case_structural_sha256': sha(json.dumps(after, sort_keys=True, ensure_ascii=False).encode()),
                'exact_fields_equal': comparisons, 'inherit_successful_prior_joint_pass': inherit,
                'prior_review': review,
                'review_mode': 'strict_13_field_successful_prior_joint_pass_inheritance' if inherit else 'needs_personal_read'}
        if not inherit:
            item['actual_pair'] = {key: after[key] for key in ['input', 'normalized_input', 'cleanup_input',
                                                            'output', 'candidate_text', 'cleanup_status', 'error',
                                                            'insertion_count', 'delivered_count', 'delivery_outcome',
                                                            'dictation_outcome']}
            item['previous_output'] = before['output']
        result.append(item)
    packet = {'schema_version': 1, 'purpose': 'Retired development comparison only; new judgments require actual reading.',
              'source_report_sha256': args.report_sha256, 'prior_report_sha256': OLD_REPORT_SHA,
              'prior_canonical_review_sha256': OLD_REVIEW_SHA, 'exact_fields': FIELDS,
              'inheritance_count': sum(row['inherit_successful_prior_joint_pass'] for row in result),
              'personal_read_required': sum(not row['inherit_successful_prior_joint_pass'] for row in result),
              'cases': result}
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'comparison-and-inheritance-packet.json').write_text(json.dumps(packet, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: packet[key] for key in ('inheritance_count', 'personal_read_required')}))


if __name__ == '__main__':
    main()
