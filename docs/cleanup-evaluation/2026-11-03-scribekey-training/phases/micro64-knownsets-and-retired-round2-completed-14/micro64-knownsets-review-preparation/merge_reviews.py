"""Merge completed named development reviews without changing their judgments."""
import argparse
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parents[1]
SPECS = {
    'development546': ('c29d3a46e442abed06c7d0c33241bf064a167e084e7f733cdd0afc01472faa1c', 546,
                       [('positions001-182/reviewed.json', 1, 182), ('positions183-364/reviewed.json', 183, 364),
                        ('positions365-546/casewise-reviewed.json', 365, 546)], 34),
    'hard80': ('9441d00099b24df72416b4f542e7a974d0f35148056eed2c3d9590539868d83d', 80,
               [('owner-review/reviewed.json', 1, 80)], 2),
}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def structural(case):
    return (case['cleanup_status'] in ('Applied', 'Unchanged') and case['error'] is None
            and type(case['insertion_count']) is int and case['insertion_count'] == 1
            and type(case['delivered_count']) is int and case['delivered_count'] == 1
            and case['delivery_outcome'] == 'Delivered' and case['dictation_outcome'] == 'Success')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cohort', choices=SPECS)
    args = parser.parse_args()
    expected, count, shards, read_count = SPECS[args.cohort]
    root = WORK / ('reviews-t050-micro64-' + args.cohort)
    report_path = WORK / ('evaluation/t050-micro64-quality-1126-run01/' + args.cohort + '-core/core-results.json')
    assert sha(report_path.read_bytes()) == expected
    report = json.loads(report_path.read_text())
    packet_path = root / 'comparison-and-inheritance-packet.json'
    packet = json.loads(packet_path.read_text())
    assert report['incomplete'] is False and len(report['cases']) == count
    assert packet['source_report_sha256'] == expected and len(packet['cases']) == count
    cases, sources = [], []
    for name, start, end in shards:
        path = root / name
        review = json.loads(path.read_text())
        assert review['results_sha256'] == expected and len(review['cases']) == end - start + 1
        sources.append({'path': str(path.relative_to(WORK)), 'sha256': sha(path.read_bytes()),
                        'reviewer': review['reviewer'], 'positions_one_based': [start, end]})
        for pos, case in enumerate(review['cases'], start):
            actual, proof = report['cases'][pos - 1], packet['cases'][pos - 1]
            assert case['position_one_based'] == pos and case['case_id'] == actual['id'] == proof['case_id']
            assert case['output_sha256'] == proof['output_sha256'] == sha(actual['output'].encode())
            assert case['case_structural_sha256'] == proof['case_structural_sha256']
            assert all(type(case[key]) is bool for key in ('semantic_faithful', 'clean_usable', 'critical_error'))
            cases.append({**case, 'structural_success': structural(actual)})
    assert len(cases) == len({case['case_id'] for case in cases}) == count
    summary = {'schema_version': 1, 'results_sha256': expected, 'total': count,
               'faithful': sum(case['semantic_faithful'] for case in cases),
               'clean': sum(case['clean_usable'] for case in cases),
               'joint': sum(case['semantic_faithful'] and case['clean_usable'] and case['structural_success'] for case in cases),
               'critical': sum(case['critical_error'] for case in cases),
               'failed_structural': sum(not case['structural_success'] for case in cases),
               'scope': 'Consumed development/regression diagnostic. No perfect-hard80 gate, fresh/population or Windows qualification is inferred.'}
    cross = {'schema_version': 1, 'reviewer': 'Codex assistant /root', 'results_sha256': expected,
             'scope': 'Personally cross-read all required normalized-input/delivered-output pairs without target oracles. Original-input and raw-candidate bindings remain in the packet; root separately agrees with both hard80 critical judgments.',
             'cases': [{'case_id': item['case_id'], 'position_one_based': item['position_one_based'],
                        'output_sha256': item['output_sha256'], 'judgment_agreed': True}
                       for item in packet['cases'] if not item['inherit_successful_prior_joint_pass']]}
    assert len(cross['cases']) == read_count
    changes = {'fixed_prior_failures': [], 'new_joint_failures': [], 'remaining_prior_failures': []}
    for before, after in zip(packet['cases'], cases):
        prior = before['prior_review']
        was = prior['semantic_faithful'] and prior['clean_usable']
        now = after['semantic_faithful'] and after['clean_usable'] and after['structural_success']
        if not was and now: changes['fixed_prior_failures'].append(after['case_id'])
        if was and not now: changes['new_joint_failures'].append(after['case_id'])
        if not was and not now: changes['remaining_prior_failures'].append(after['case_id'])
    canonical = {'schema_version': 1, 'reviewer': 'Named assistant shards plus root cross-review',
                 'results_sha256': expected, 'review_sources': sources,
                 'prior_canonical_review_sha256': packet['prior_canonical_review_sha256'],
                 'qualification': summary['scope'], 'cases': cases}
    for name, body in [('canonical-reviewed.json', canonical), ('canonical-semantic-summary.json', summary),
                       ('root-cross-review-read-record.json', cross), ('comparison-vs-v6.json', changes)]:
        with (root / name).open('x') as file:
            json.dump(body, file, ensure_ascii=False, indent=2)
            file.write('\n')
    print(json.dumps(summary))

if __name__ == '__main__':
    main()
