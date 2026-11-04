"""Persist benchmark_harness's actual first-shard V9 semantic review and proofs."""
from pathlib import Path
import datetime
import hashlib
import json
import re

TASK = Path('/workspace/freehand/work/cleanup-scribekey-training-2026-11-03')
REPORT_SHA = 'd59ff5167f5c1df224f060c62fea144403425503b9fc1b0ebe6b02dcc18e0089'
OLD_REPORT_SHA = '7d492ecb55fb7dc1ef537f1b7c575fece3aad838ac5fff7ca17a2214ed6c3a70'
OLD_REVIEW_SHA = 'fe07736284eda5a8b8425c90b537f217e7c984d94b7e2420d375c8c5e1bfdae7'
PACKET_SHA = 'd912d903b7702627676197c74afbc258145ed5c252cf8786f5f0a27e080ff5e5'
HELPER_SHA = '471772032b7d30d21de8119d1e6e1a8611307593e97964e2fe3a6cc1397f3b0a'
AUTHOR = '/root/benchmark_harness (Codex assistant semantic reviewer)'
FIELDS = ['input', 'normalized_input', 'cleanup_input', 'candidate_text', 'output',
          'cleanup_status', 'error', 'insertion_count', 'delivered_count',
          'delivery_outcome', 'dictation_outcome', 'normalized_targets', 'normalized_checks']
MANUAL = {
    'blind-a-026': (True, False, False, 'The complete enjoyment statement and especially-the-ending emphasis remain, but the unchanged I, I is still an accidental pronoun stutter. Faithful content; not fully cleaned.'),
    'blind-a-098': (True, True, False, 'Removes um while keeping affirmative desire for feedback and excluding the live-presentation period. The contrastive just not adjunct remains readable without the prior optional pause comma; no fact or scope is lost.'),
    'blind-a-151': (True, True, False, 'Drops leading Um and preserves sending the photograph to the actual Core-normalized HarborDesk destination after lunch. Candidate protected block restores to that exact delivered name once.'),
    'blind-a-152': (True, True, False, 'Drops uh and its pause comma while keeping Please, the inquiry to NorthVale Support, and whether this cable is covered. The protected organization name is restored exactly once.'),
    'blind-a-153': (True, True, False, 'Drops um and preserves the first-person past saved-notes statement, exact Garden_Archive spelling, and shared-drive location. No outside content or literal bytes change.'),
    'blind-a-154': (True, True, False, 'Drops uh and its interruption punctuation; the replacement remains listed as exact CEDAR-X on the receipt. The hyphenated protected code is restored intact once.'),
    'blind-a-155': (True, True, False, 'Drops um and keeps the polite request for both attachments: exact copper.diagram.svg and the inspection summary. The conjunction and filename dots/extension are retained.'),
    'blind-a-156': (True, True, False, 'Removes the accidental repeated the while preserving the Could you package-placement question and beside-the-PrintRoom relation. The protected destination is exact.'),
    'blind-a-157': (True, True, False, 'Drops leading Um while preserving the first-person past conversation with exact accented Léona Ward and its workshop-venue topic.'),
    'blind-a-158': (True, True, False, 'Drops uh and preserves the label instruction and following-date order. Exact protected Keep  Upright retains its two interior spaces; the comma before followed by is usable optional pause punctuation.'),
    'blind-a-159': (True, True, False, 'Drops um and its pause comma while retaining We should contact, exact Fern & Co., and the before-scheduling-the-visit restriction. The name ampersand and final period remain protected.'),
    'blind-a-160': (True, True, False, 'Removes accidental the, the and preserves the first-person past use of the drawing from exact OAK_spec_revB for the mock-up. Source name case and underscores are intact.'),
    'blind-a-161': (True, True, False, 'Keeps the already-clean polite request to send exact Thanks, everyone! to the volunteer team. That internal punctuation belongs to the protected supplied payload and is preserved once.'),
    'blind-a-162': (True, True, False, 'Drops leading Um while preserving that this shortcut opens exact C:\\Pine\\Drafts on this machine. The protected path separators and case remain unchanged.'),
    'blind-a-163': (True, True, False, 'Drops uh and its pause comma while keeping the Could you footer-inclusion question and exact SPRUCE::view, including its case and double colon.'),
    'blind-a-164': (True, True, False, 'Drops um while preserving the file name Willow.vNext and the contrast with the older title. The retained optional pause comma does not impair the sentence.'),
    'blind-a-165': (True, True, False, 'Removes the repeated the while preserving the need for the service address associated with exact help@brook.example. The email punctuation and final sentence period are retained.'),
    'blind-a-166': (True, True, False, 'Drops uh and preserves the polite instruction to place the exact protected internal only note after the diagram. The payload has one leading and trailing space; the delivered double outside spaces arise from exact payload restoration and are not a new cleanup error.'),
    'blind-a-167': (True, True, False, 'Drops leading Um while preserving the small-room booking request for exact Juniper / West, including the slash and its spaces.'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, expected):
    raw = path.read_bytes()
    assert sha(raw) == expected, str(path)
    return json.loads(raw)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def structural(row):
    return (row['cleanup_status'] in ('Applied', 'Unchanged') and row['error'] is None
            and type(row['insertion_count']) is int and row['insertion_count'] == 1
            and type(row['delivered_count']) is int and row['delivered_count'] == 1
            and row['delivery_outcome'] == 'Delivered' and row['dictation_outcome'] == 'Success')


report = pinned(TASK / 'evaluation/v9-01-native-LoRA-F32-retired-primary500-core/core-results.json', REPORT_SHA)
old = pinned(TASK / 'evaluation/v8-01-native-LoRA-F32-retired-primary500-core/core-results.json', OLD_REPORT_SHA)
prior = pinned(TASK / 'reviews-v8-01-native-LoRA-retired500/canonical-reviewed.json', OLD_REVIEW_SHA)
review_root = TASK / 'reviews-v9-01-native-LoRA-retired500'
packet = pinned(review_root / 'comparison-and-inheritance-packet.json', PACKET_SHA)
helper = TASK / 'v9-review-preparation/create_packet.py'
assert sha(helper.read_bytes()) == HELPER_SHA
assert report['incomplete'] is old['incomplete'] is False
assert len(report['cases']) == len(old['cases']) == len(prior['cases']) == len(packet['cases']) == 500
ids = [row['id'] for row in report['cases']]
assert len(set(ids)) == 500 and ids == [row['id'] for row in old['cases']] == [row['case_id'] for row in prior['cases']]
assert packet['source_report_sha256'] == REPORT_SHA and packet['prior_report_sha256'] == OLD_REPORT_SHA
assert packet['prior_canonical_review_sha256'] == OLD_REVIEW_SHA and packet['exact_fields'] == FIELDS
global_inherited = 0
proofs = []
judgments = []
read_record = []
literal_pattern = re.compile(r'\[\[FREEHAND_LITERAL_([A-Za-z0-9_]+)_START\]\](.*?)\[\[FREEHAND_LITERAL_\1_END\]\]', re.S)
for pos, (before, previous, after, item) in enumerate(zip(old['cases'], prior['cases'], report['cases'], packet['cases']), 1):
    assert previous['output_sha256'] == sha(before['output'].encode())
    comparisons = {field: canonical(before[field]) == canonical(after[field]) for field in FIELDS}
    inherit = (all(comparisons.values()) and structural(before) and structural(after)
        and previous['semantic_faithful'] is True and previous['clean_usable'] is True and previous['critical_error'] is False)
    assert item['case_id'] == after['id'] and item['position_one_based'] == pos
    assert item['exact_fields_equal'] == comparisons and item['inherit_successful_prior_joint_pass'] is inherit
    assert item['output_sha256'] == sha(after['output'].encode())
    assert item['case_structural_sha256'] == sha(canonical(after).encode())
    global_inherited += inherit
    if pos > 167:
        continue
    proof = {'position_one_based': pos, 'case_id': after['id'], 'output_sha256': item['output_sha256'],
        'case_structural_sha256': item['case_structural_sha256'], 'typed_canonical_JSON_exact_fields_equal': comparisons,
        'old_structural_delivered_success': structural(before), 'new_structural_delivered_success': structural(after),
        'prior_joint_pass_critical_false': previous['semantic_faithful'] is True and previous['clean_usable'] is True and previous['critical_error'] is False,
        'inherited': inherit}
    proofs.append(proof)
    if inherit:
        faithful, clean, critical, reason = (previous['semantic_faithful'], previous['clean_usable'], previous['critical_error'], previous['reason'])
        mode = 'strict_13_field_successful_prior_joint_pass_inheritance'
    else:
        assert after['id'] in MANUAL and item['actual_pair'] == {key: after[key] for key in item['actual_pair']}
        faithful, clean, critical, reason = MANUAL[after['id']]
        mode = 'personally_read_actual_source_candidate_and_delivered_output'
        actual = {key: after[key] for key in ('input', 'normalized_input', 'cleanup_input', 'candidate_text', 'output',
            'cleanup_status', 'error', 'insertion_count', 'delivered_count', 'delivery_outcome', 'dictation_outcome')}
        record = {'position_one_based': pos, 'case_id': after['id'], 'actual_pair': actual,
            'output_sha256': item['output_sha256'], 'case_structural_sha256': item['case_structural_sha256'],
            'previous_output_for_comparison': before['output'], 'personally_read': True, 'targets_shown_or_used': False,
            'semantic_faithful': faithful, 'clean_usable': clean, 'critical_error': critical, 'reason': reason}
        literals = literal_pattern.findall(after['cleanup_input'])
        if literals:
            restored = literal_pattern.sub(lambda match: match.group(2), after['candidate_text'])
            assert restored == after['output']
            assert len(literals) == 1 and len(literal_pattern.findall(after['candidate_text'])) == 1
            assert literal_pattern.findall(after['candidate_text'])[0] == literals[0]
            record['literal_fidelity'] = {'protected_payloads': [text for _, text in literals],
                'candidate_Core_block_payloads_exact_once': True, 'Core_marker_removal_matches_delivered_bytes': True,
                'scope': 'Actual Core candidate and dictionary-delivered output; no raw pretrim/native emission claim'}
        read_record.append(record)
    judgments.append({'position_one_based': pos, 'case_id': after['id'], 'output_sha256': item['output_sha256'],
        'case_structural_sha256': item['case_structural_sha256'], 'semantic_faithful': faithful,
        'clean_usable': clean, 'critical_error': critical, 'reason': reason, 'review_mode': mode})
assert global_inherited == packet['inheritance_count'] == 462
assert packet['personal_read_required'] == 38
assert len(judgments) == 167 and len(read_record) == len(MANUAL) == 19
assert {row['case_id'] for row in read_record} == set(MANUAL)
assert sum(row['inherited'] for row in proofs) == 148
assert all(structural(row) for row in report['cases'][:167])
summary = {'schema_version': 1, 'reviewer': AUTHOR, 'results_sha256': REPORT_SHA,
    'prior_results_sha256': OLD_REPORT_SHA, 'prior_canonical_review_sha256': OLD_REVIEW_SHA,
    'packet_sha256': PACKET_SHA, 'helper_source_sha256': HELPER_SHA, 'positions_one_based': [1, 167],
    'case_count': 167, 'structural_success': 167, 'personally_read_required_and_completed': 19,
    'strict_typed_13_field_prior_joint_inherited': 148,
    'faithful': sum(row['semantic_faithful'] for row in judgments), 'clean_usable': sum(row['clean_usable'] for row in judgments),
    'faithful_and_clean_usable': sum(row['semantic_faithful'] and row['clean_usable'] and not row['critical_error'] for row in judgments),
    'critical_errors': sum(row['critical_error'] for row in judgments),
    'failed_joint_cases': [row['case_id'] for row in judgments if not (row['semantic_faithful'] and row['clean_usable'] and not row['critical_error'])],
    'targets_shown_or_used_for_manual_judgments': False,
    'scope': 'Retired development first167 only;19 actual pairs personally read,148 prior successful judgments transparently inherited; not167 new personal reads or a fresh/population/Windows/resource qualification.',
    'mainfinding': 'a026 remains faithful but retains the accidental I,I stutter. a098 optional comma omission is acceptable;151-167 exact Core literal payloads and outside content are preserved.',
    'utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
assert (summary['faithful'], summary['clean_usable'], summary['faithful_and_clean_usable'], summary['critical_errors']) == (167, 166, 166, 0)
destination = review_root / 'positions001-167'
destination.mkdir(exist_ok=False)
def write(name, value):
    with (destination / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
write('reviewed.json', {'schema_version': 1, 'reviewer': AUTHOR, 'results_sha256': REPORT_SHA,
    'prior_canonical_review_sha256': OLD_REVIEW_SHA, 'positions_one_based': [1,167], 'cases': judgments})
write('read-record.json', {'schema_version': 1, 'reviewer': AUTHOR, 'results_sha256': REPORT_SHA,
    'targets_shown_or_used': False, 'personal_read_count': 19, 'cases': read_record})
write('inheritance-proof.json', {'schema_version': 1, 'reviewer': AUTHOR, 'results_sha256': REPORT_SHA,
    'prior_results_sha256': OLD_REPORT_SHA, 'prior_canonical_review_sha256': OLD_REVIEW_SHA,
    'packet_sha256': PACKET_SHA, 'helper_source_sha256': HELPER_SHA, 'exact_fields': FIELDS,
    'global500_packet_mechanically_reverified': True, 'new_semantic_judgments_outside_first167': False,
    'inherited': 148, 'personal_read_required': 19, 'cases': proofs})
write('summary.json', summary)
write('review-helper-source-audit.json', {'schema_version': 1, 'reviewer': AUTHOR,
    'decision': 'PASS_AFTER_CANONICAL_JSON_TYPED_COMPARISON_FIX_BEFORE_V9_PACKET',
    'source_path': str(helper), 'source_sha256': HELPER_SHA, 'packet_sha256': PACKET_SHA,
    'old_report_and_review_pins_verified': True, 'all500_ordered_ids_output_bindings_and_inheritance_flags_mechanically_verified': True,
    'strict_13_field_typed_canonical_JSON_equivalence': True, 'structural_Delivered_Success_and_exact_integer_delivery_checks': True,
    'inherit_only_successful_prior_joint_pass_with_critical_false': True,
    'manual_pairs_include_no_target_oracle': True, 'no_new_semantic_pass_assigned_by_helper': True})
print(json.dumps(summary, indent=2))
for path in sorted(destination.iterdir()):
    raw = path.read_bytes()
    print(path.name, len(raw), sha(raw))
