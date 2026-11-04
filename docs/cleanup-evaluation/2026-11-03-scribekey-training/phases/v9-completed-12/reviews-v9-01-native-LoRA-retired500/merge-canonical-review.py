"""Merge three completed named reviews; require exact full report/output bindings."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
EXPECTED = 'd59ff5167f5c1df224f060c62fea144403425503b9fc1b0ebe6b02dcc18e0089'
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def load(path):
    return json.loads(path.read_text())
report_path = WORK / 'evaluation/v9-01-native-LoRA-F32-retired-primary500-core/core-results.json'
assert sha(report_path.read_bytes()) == EXPECTED
report = load(report_path)
assert report['incomplete'] is False and len(report['cases']) == 500
packet_path = HERE / 'comparison-and-inheritance-packet.json'
packet = load(packet_path)
sources = []
cases = []
for name, start, end in [('positions001-167/reviewed.json', 1, 167),
                         ('positions168-334/casewise-reviewed.json', 168, 334),
                         ('positions335-500/casewise-reviewed.json', 335, 500)]:
    path = HERE / name
    data = load(path)
    assert data['results_sha256'] == EXPECTED
    assert len(data['cases']) == end - start + 1
    sources.append({'path': str(path.relative_to(WORK)), 'sha256': sha(path.read_bytes()),
                    'reviewer': data['reviewer'], 'positions_one_based': [start, end]})
    for position, judgment in enumerate(data['cases'], start):
        actual = report['cases'][position - 1]
        assert judgment['position_one_based'] == position and judgment['case_id'] == actual['id']
        assert judgment['output_sha256'] == sha(actual['output'].encode())
        assert judgment['case_structural_sha256'] == sha(json.dumps(actual, sort_keys=True, ensure_ascii=False).encode())
        assert all(type(judgment[key]) is bool for key in ('semantic_faithful', 'clean_usable', 'critical_error'))
        assert not judgment['critical_error'] or not (judgment['semantic_faithful'] and judgment['clean_usable'])
        cases.append(judgment)
assert len(cases) == len({case['case_id'] for case in cases}) == 500
summary = {'schema_version': 1, 'results_sha256': EXPECTED, 'total': 500,
           'semantic_faithful': sum(case['semantic_faithful'] for case in cases),
           'clean_usable': sum(case['clean_usable'] for case in cases),
           'joint': sum(case['semantic_faithful'] and case['clean_usable'] for case in cases),
           'critical_error': sum(case['critical_error'] for case in cases),
           'required_joint': 495, 'scope': 'Retired development only; not fresh/population or resource qualification.'}
summary['meets_development_gate'] = summary['joint'] >= summary['required_joint']
summary['joint_failures'] = [case['case_id'] for case in cases if not (case['semantic_faithful'] and case['clean_usable'])]
prior = load(WORK / 'reviews-v8-01-native-LoRA-retired500/canonical-reviewed.json')
comparison = {'schema_version': 1, 'results_sha256': EXPECTED,
              'prior_canonical_sha256': sha((WORK / 'reviews-v8-01-native-LoRA-retired500/canonical-reviewed.json').read_bytes()),
              'fixed_joint_failures': [], 'new_joint_failures': [], 'remaining_prior_joint_failures': []}
for before, after in zip(prior['cases'], cases):
    assert before['case_id'] == after['case_id']
    was = before['semantic_faithful'] and before['clean_usable']
    now = after['semantic_faithful'] and after['clean_usable']
    if not was and now: comparison['fixed_joint_failures'].append(after['case_id'])
    if was and not now: comparison['new_joint_failures'].append(after['case_id'])
    if not was and not now: comparison['remaining_prior_joint_failures'].append(after['case_id'])
cross = {'schema_version': 1, 'reviewer': 'Codex assistant /root', 'results_sha256': EXPECTED,
         'scope': 'Personally cross-read original/normalized input and actual delivered outputs for all38 cases requiring new review, including all20 dictionary cases with changed nonce IDs. Opaque payload byte proofs belong to shard reviewers. No targets used as semantic oracles; no claim of500 new personal reads.',
         'cases': [{'case_id': item['case_id'], 'position_one_based': item['position_one_based'],
                    'output_sha256': item['output_sha256'], 'judgment_agreed': True}
                   for item in packet['cases'] if not item['inherit_successful_prior_joint_pass']]}
assert len(cross['cases']) == 38
canonical = {'schema_version': 1, 'reviewer': 'Three named Codex assistant reviews plus root38-pair cross-read',
             'results_sha256': EXPECTED, 'qualification': summary['scope'], 'review_sources': sources,
             'prior_canonical_review_sha256': comparison['prior_canonical_sha256'],
             'moderate_confidence_inherited_case': 'C076 retains the previously disclosed scope ambiguity under identical13field successful inheritance; no new adjudication or rubric change.',
             'cases': cases}
for name, body in [('canonical-reviewed.json', canonical), ('canonical-semantic-summary.json', summary),
                   ('comparison-vs-v8.json', comparison), ('root-cross-review-read-record.json', cross)]:
    with (HERE / name).open('x') as file:
        json.dump(body, file, ensure_ascii=False, indent=2)
        file.write('\n')
print(json.dumps(summary))
