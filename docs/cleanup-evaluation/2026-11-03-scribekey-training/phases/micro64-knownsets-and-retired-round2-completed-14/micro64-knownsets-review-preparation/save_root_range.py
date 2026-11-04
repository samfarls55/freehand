"""Persist supplied personal judgments and successful prior-pass inheritance."""
import argparse
import hashlib
import json
from pathlib import Path

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--report-sha256', required=True)
    parser.add_argument('--manual', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--start', type=int, default=335)
    parser.add_argument('--end', type=int, default=500)
    args = parser.parse_args()
    raw = args.packet.read_bytes()
    packet = json.loads(raw)
    assert packet['source_report_sha256'] == args.report_sha256
    assert len(packet['cases']) == packet['case_count'] and 1 <= args.start <= args.end <= packet['case_count']
    manual = json.loads(args.manual.read_text())
    selected = packet['cases'][args.start - 1:args.end]
    needed = {item['case_id'] for item in selected if not item['inherit_successful_prior_joint_pass']}
    assert set(manual) == needed
    cases, proofs, read = [], [], []
    for item in selected:
        inherited = item['inherit_successful_prior_joint_pass']
        decision = item['prior_review'] if inherited else manual[item['case_id']]
        assert all(type(decision[key]) is bool for key in ('semantic_faithful', 'clean_usable', 'critical_error'))
        assert type(decision['reason']) is str and decision['reason']
        if inherited:
            assert decision['semantic_faithful'] and decision['clean_usable'] and not decision['critical_error']
            structural = True
        else:
            actual = item['actual_pair']
            structural = (actual['cleanup_status'] in ('Applied', 'Unchanged') and actual['error'] is None
                          and type(actual['insertion_count']) is int and actual['insertion_count'] == 1
                          and type(actual['delivered_count']) is int and actual['delivered_count'] == 1
                          and actual['delivery_outcome'] == 'Delivered' and actual['dictation_outcome'] == 'Success')
            assert structural or not (decision['semantic_faithful'] and decision['clean_usable'])
            read.append({'case_id': item['case_id'], 'position_one_based': item['position_one_based'],
                         'actual_pair': actual, 'personal_judgment': decision})
        cases.append({**{key: item[key] for key in ('case_id', 'position_one_based', 'output_sha256', 'case_structural_sha256')},
                      **{key: decision[key] for key in ('semantic_faithful', 'clean_usable', 'critical_error', 'reason')},
                      'review_mode': item['review_mode'] if inherited else 'personally_read_actual_pair',
                      'structural_success': structural})
        proofs.append({key: item[key] for key in ('case_id', 'position_one_based', 'output_sha256',
                                                'case_structural_sha256', 'exact_fields_equal',
                                                'inherit_successful_prior_joint_pass')})
    common = {'schema_version': 1, 'reviewer': 'Codex assistant /root', 'results_sha256': args.report_sha256,
              'prior_canonical_review_sha256': packet['prior_canonical_review_sha256'],
              'packet_sha256': sha(raw), 'personal_judgments_sha256': sha(args.manual.read_bytes())}
    summary = {**common, 'cases': len(cases), 'joint': sum(c['semantic_faithful'] and c['clean_usable'] for c in cases),
               'faithful': sum(c['semantic_faithful'] for c in cases), 'clean': sum(c['clean_usable'] for c in cases),
               'critical': sum(c['critical_error'] for c in cases), 'personal_reads': len(read),
               'inherited': len(cases) - len(read)}
    args.output.mkdir(parents=True, exist_ok=False)
    for name, body in [('casewise-reviewed.json', {**common, 'cases': cases}),
                       ('personal-read-record.json', {**common, 'scope': 'Actual normalized input and delivered text personally read without a target oracle; raw candidate and delivery bindings retained for verification. Remaining cases inherit only proven identical successful judgments.', 'cases': read}),
                       ('inheritance-proof.json', {**common, 'typed_json_equality': True, 'exact_fields': packet['exact_fields'], 'cases': proofs}),
                       ('summary.json', summary)]:
        with (args.output / name).open('x') as file:
            json.dump(body, file, ensure_ascii=False, indent=2)
            file.write('\n')
    print(json.dumps(summary))

if __name__ == '__main__':
    main()
