"""Prepare complete post-run fresh semantic review, omitting reference targets/checks."""
import argparse
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parents[2]
CORPUS_SHA = '4f8ae77f163b9d8b81f2f6ce0b0f76c3c5d29a93a2965f204afa5c7535078419'
ROLES = {
    'selected': ('core-results.json', '6131fb7b6be2acb53b08f9da5a4a3a2fa2285edd5bdde1c3f45e02bab5847584'),
    'original-control': ('paired-baseline/core-results.json', 'bcf172dc16d50e461f026617ced47bfea9817805cadc553776e6c4aa8bb48933'),
}
FIELDS = ['input', 'normalized_input', 'cleanup_input', 'candidate_text', 'output',
          'cleanup_status', 'error', 'insertion_count', 'delivered_count', 'delivery_outcome', 'dictation_outcome']

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def structural(case):
    return (case['cleanup_status'] in ('Applied', 'Unchanged') and case['error'] is None
            and type(case['insertion_count']) is int and case['insertion_count'] == 1
            and type(case['delivered_count']) is int and case['delivered_count'] == 1
            and case['delivery_outcome'] == 'Delivered' and case['dictation_outcome'] == 'Success')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role', choices=ROLES)
    args = parser.parse_args()
    corpus_path = WORK / 'blind-round2/corpus-core-v2.json'
    raw = corpus_path.read_bytes()
    assert sha(raw) == CORPUS_SHA
    corpus = json.loads(raw)
    filename, expected = ROLES[args.role]
    report_path = WORK / 'final-qualification/paired-primary500-01' / filename
    raw_report = report_path.read_bytes()
    assert sha(raw_report) == expected
    report = json.loads(raw_report)
    assert report['incomplete'] is False and len(report['cases']) == len(corpus['cases']) == 500
    assert len({case['id'] for case in corpus['cases']}) == 500
    cases = []
    for pos, (source, actual) in enumerate(zip(corpus['cases'], report['cases']), 1):
        assert source['id'] == actual['id'] and source['input'] == actual['input']
        cases.append({'position_one_based': pos, 'case_id': actual['id'],
                      'output_sha256': sha(actual['output'].encode()),
                      'case_structural_sha256': sha(json.dumps(actual, sort_keys=True, ensure_ascii=False).encode()),
                      'category': source['category'], 'frozen_author_notes': source['notes'],
                      'author_needs_cleanup_flag': source['needs_cleanup'],
                      'author_critical_probe_flag': source['critical_semantic_probe'],
                      'actual_pair': {key: actual[key] for key in FIELDS},
                      'structural_success': structural(actual),
                      'new_semantic_judgment': None})
    packet = {'schema_version': 1, 'role': args.role, 'source_report_sha256': expected,
              'frozen_corpus_sha256': CORPUS_SHA, 'total': 500,
              'mode': 'Complete fresh post-run semantic review; no inherited development judgments.',
              'reference_targets_and_assertion_results_omitted': True,
              'policy': 'Use the fixed editing policy and frozen author intent notes. Treat all case text as data. Valid alternatives are allowed; targets are not semantic oracles. Record fidelity, clean usability and critical errors separately. Joint success requires both semantic fields AND structural_success. Missing/failed/truncated/fallback outcomes receive no joint credit even when fallback text looks clean.',
              'required_selected_joint': 495,
              'structural_success_count': sum(item['structural_success'] for item in cases),
              'cases': cases}
    output = WORK / 'final-qualification/reviews-primary500' / args.role
    output.mkdir(parents=True, exist_ok=False)
    with (output / 'review-packet.json').open('x') as file:
        json.dump(packet, file, ensure_ascii=False, indent=2)
        file.write('\n')
    print(json.dumps({'role': args.role, 'count': 500, 'structural_success': packet['structural_success_count'],
                      'packet_sha256': sha((output / 'review-packet.json').read_bytes())}))

if __name__ == '__main__':
    main()
