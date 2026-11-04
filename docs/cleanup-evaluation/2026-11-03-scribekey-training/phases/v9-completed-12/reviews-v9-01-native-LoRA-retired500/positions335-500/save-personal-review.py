"""Persist root's six actual judgments and transparent prior-pass inheritance."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
raw = (ROOT / 'comparison-and-inheritance-packet.json').read_bytes()
packet = json.loads(raw)
assert packet['source_report_sha256'] == 'd59ff5167f5c1df224f060c62fea144403425503b9fc1b0ebe6b02dcc18e0089'
personal = {
    'blind-c-021': (True, False, False, 'Returns the complete source including Uh unchanged. Exact refund quote and clarification are faithful, but the removable hesitation remains; no successful-cleanup credit.'),
    'blind-c-029': (True, True, False, 'Removes the accidental initial I, I while preserving the request and exact quoted response opening.'),
    'blind-c-031': (True, True, False, 'The instead-of frame preserves both exact status literals while clearly canceling on hold and retaining awaiting parts. Repeated instead is stylistically redundant but grammatical and directly usable; it does not reactivate the canceled change.'),
    'blind-c-034': (True, False, False, 'Exact regex and speaker uncertainty survive, but the accidental I, I remains unchanged and uncleaned.'),
    'blind-c-064': (True, True, False, 'Preserves the technical distinction LoRa radio versus LoRA model adapters and removes uh. The contrast is clear without an optional comma.'),
    'blind-c-072': (True, True, False, 'Clearly cancels the upstairs-room request and preserves the plan to join remotely.'),
}
cases = []
proofs = []
read = []
for item in packet['cases'][334:500]:
    inherited = item['inherit_successful_prior_joint_pass']
    if inherited:
        prior = item['prior_review']
        flags = (prior['semantic_faithful'], prior['clean_usable'], prior['critical_error'], prior['reason'])
        assert flags[:3] == (True, True, False)
    else:
        flags = personal[item['case_id']]
        read.append({'case_id': item['case_id'], 'position_one_based': item['position_one_based'],
                     'actual_pair': item['actual_pair'], 'judgment': flags,
                     'personal_read': True})
    cases.append({'case_id': item['case_id'], 'position_one_based': item['position_one_based'],
                  'output_sha256': item['output_sha256'], 'case_structural_sha256': item['case_structural_sha256'],
                  'semantic_faithful': flags[0], 'clean_usable': flags[1], 'critical_error': flags[2],
                  'reason': flags[3], 'review_mode': item['review_mode'] if inherited else 'personally_read_actual_pair',
                  'structural_success': True})
    proofs.append({key: item[key] for key in ('case_id', 'position_one_based', 'output_sha256',
                                            'case_structural_sha256', 'exact_fields_equal',
                                            'inherit_successful_prior_joint_pass')})
assert len(cases) == 166 and len(read) == 6
assert {item['case_id'] for item in read} == set(personal)
common = {'schema_version': 1, 'reviewer': 'Codex assistant /root',
          'results_sha256': packet['source_report_sha256'],
          'prior_canonical_review_sha256': packet['prior_canonical_review_sha256'],
          'packet_sha256': hashlib.sha256(raw).hexdigest()}
outputs = {
    'casewise-reviewed.json': {**common, 'cases': cases},
    'personal-read-record.json': {**common, 'scope': 'Six actual original/normalized/cleanup-input/candidate/delivered pairs personally read; no target oracle. Remaining160 cases inherit prior successful judgments under exact typed13-field equality.', 'cases': read},
    'inheritance-proof.json': {**common, 'exact_fields': packet['exact_fields'], 'typed_json_equality': True, 'cases': proofs},
    'summary.json': {**common, 'cases': len(cases), 'faithful': sum(item['semantic_faithful'] for item in cases),
                     'clean': sum(item['clean_usable'] for item in cases),
                     'joint': sum(item['semantic_faithful'] and item['clean_usable'] for item in cases),
                     'critical': sum(item['critical_error'] for item in cases),
                     'personal_reads': len(read), 'inherited': len(cases) - len(read)},
}
for name, body in outputs.items():
    target = HERE / name
    with target.open('x') as f:
        json.dump(body, f, ensure_ascii=False, indent=2)
        f.write('\n')
print(json.dumps(outputs['summary.json']))
