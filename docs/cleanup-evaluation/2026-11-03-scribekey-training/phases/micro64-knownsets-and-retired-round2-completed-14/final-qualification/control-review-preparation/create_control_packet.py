#!/usr/bin/env python3
"""Prepare original-control review; reuse only identical successful fresh judgments.

Source-only controller. Targets/checks participate only in strict identity.
No model, worker, training, build, new semantic grading, or development review.
"""
import hashlib
import json
import math
from pathlib import Path

ROOT = Path('/workspace/freehand')
WORK = ROOT / 'work/cleanup-scribekey-training-2026-11-03'
QUAL = WORK / 'final-qualification'
OUT = QUAL / 'control-review-preparation'
FROZEN_CORPUS_SHA256 = '4f8ae77f163b9d8b81f2f6ce0b0f76c3c5d29a93a2965f204afa5c7535078419'
SOURCES = {
    'selected_report': (QUAL / 'paired-primary500-01/core-results.json',
        '6131fb7b6be2acb53b08f9da5a4a3a2fa2285edd5bdde1c3f45e02bab5847584'),
    'control_report': (QUAL / 'paired-primary500-01/paired-baseline/core-results.json',
        'bcf172dc16d50e461f026617ced47bfea9817805cadc553776e6c4aa8bb48933'),
    'selected_packet': (QUAL / 'reviews-primary500/selected/review-packet.json',
        'fbc52367faa4a67e7e43da1f3bde9278f2d19564df0038bfcef5297aa9c21b54'),
    'control_packet': (QUAL / 'reviews-primary500/original-control/review-packet.json',
        '65d71af17461cbb7641e281dfc202d09930ffa9e7f50f77961986e84d4d7a870'),
    'selected_review': (QUAL / 'reviews-primary500/selected/canonical-reviewed.json',
        '83adcdc233f9c59686c95ae4cf5562000e808f451becbfe535ef3d26a2f1bf90'),
}
FIELDS = ['input', 'normalized_input', 'cleanup_input', 'candidate_text', 'output',
          'cleanup_status', 'error', 'insertion_count', 'delivered_count',
          'delivery_outcome', 'dictation_outcome', 'normalized_targets', 'normalized_checks']
PAIR_FIELDS = FIELDS[:11]
CONTEXT_FIELDS = ['position_one_based', 'case_id', 'category', 'frozen_author_notes',
                  'author_needs_cleanup_flag', 'author_critical_probe_flag']
GLOBAL_CONTEXT = ['schema_version', 'frozen_corpus_sha256', 'total', 'mode',
                  'reference_targets_and_assertion_results_omitted', 'policy',
                  'required_selected_joint']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def typed_equal(left, right):
    """Audited knownsets logic: nested types, array order, numeric type/signed zero."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(typed_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(typed_equal(a, b) for a, b in zip(left, right))
    require(type(left) in (str, int, float, bool, type(None)), 'Only JSON values supported')
    require(type(left) is not float or math.isfinite(left) and math.isfinite(right),
            'Nonfinite JSON scalar')
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


def structural(row):
    return (type(row['cleanup_status']) is str and row['cleanup_status'] in ('Applied', 'Unchanged')
            and row['error'] is None
            and type(row['insertion_count']) is int and row['insertion_count'] == 1
            and type(row['delivered_count']) is int and row['delivered_count'] == 1
            and type(row['delivery_outcome']) is str and row['delivery_outcome'] == 'Delivered'
            and type(row['dictation_outcome']) is str and row['dictation_outcome'] == 'Success')


def digest_case(row):
    return sha(canonical(row).encode())


def output_sha(row):
    require(type(row['output']) is str, 'Actual output must be a string')
    return sha(row['output'].encode())


def require_fields(row, fields, label):
    require(type(row) is dict and all(key in row for key in fields), 'Missing field in ' + label)


def validate_report(report, count, label):
    require(report.get('incomplete') is False, 'Report must explicitly be complete: ' + label)
    require(type(report.get('cases')) is list and len(report['cases']) == count,
            'Complete exact denominator required: ' + label)
    require(type(report.get('metadata')) is dict, 'Missing report metadata')
    corpus_sha = report['metadata'].get('corpus_sha256')
    require(type(corpus_sha) is str and corpus_sha.lower() == FROZEN_CORPUS_SHA256,
            'Wrong frozen corpus: ' + label)
    ids = []
    for row in report['cases']:
        require_fields(row, ['id', 'split'] + FIELDS, label)
        require(type(row['id']) is str and bool(row['id']), 'Nonempty string case IDs required')
        output_sha(row)
        ids.append(row['id'])
    require(len(set(ids)) == count, 'Duplicate case IDs: ' + label)
    return ids


def bind_packet(packet, report, report_key, role, ids):
    count = len(ids)
    require(packet.get('role') == role, 'Wrong packet role')
    require(packet.get('source_report_sha256') == SOURCES[report_key][1], 'Packet/report pin mismatch')
    require(packet.get('frozen_corpus_sha256') == FROZEN_CORPUS_SHA256, 'Packet corpus pin mismatch')
    require(type(packet.get('total')) is int and packet['total'] == count, 'Packet denominator mismatch')
    require(packet.get('reference_targets_and_assertion_results_omitted') is True,
            'Review packet must omit oracle fields')
    require(type(packet.get('cases')) is list and len(packet['cases']) == count, 'Packet cases mismatch')
    require([row.get('case_id') for row in packet['cases']] == ids, 'Packet ordered IDs differ')
    for index, (item, row) in enumerate(zip(packet['cases'], report['cases']), 1):
        require_fields(item, CONTEXT_FIELDS + ['actual_pair', 'output_sha256',
                       'case_structural_sha256', 'structural_success', 'new_semantic_judgment'], role)
        require(type(item['position_one_based']) is int and item['position_one_based'] == index,
                'Packet position mismatch')
        require(item['output_sha256'] == output_sha(row)
                and item['case_structural_sha256'] == digest_case(row), 'Packet case binding differs')
        require(type(item['structural_success']) is bool and item['structural_success'] is structural(row),
                'Packet structural status differs')
        require(item['new_semantic_judgment'] is None, 'Original packet has already been graded')
        require(type(item['actual_pair']) is dict and set(item['actual_pair']) == set(PAIR_FIELDS),
                'Actual pair must contain exactly the eleven non-oracle fields')
        require(typed_equal(item['actual_pair'], {key: row[key] for key in PAIR_FIELDS}),
                'Packet actual pair differs from pinned report')
    require(type(packet.get('structural_success_count')) is int
            and packet['structural_success_count'] == sum(structural(row) for row in report['cases']),
            'Packet structural total differs')


def bind_review(review, selected, ids):
    require(review.get('role') == 'selected', 'Only selected fresh judgments can be reused')
    require(review.get('results_sha256') == SOURCES['selected_report'][1]
            and review.get('packet_sha256') == SOURCES['selected_packet'][1]
            and review.get('frozen_corpus_sha256') == FROZEN_CORPUS_SHA256, 'Review source binding differs')
    require(review.get('all500_personally_read') is True, 'All fresh source cases must have been personally read')
    require(type(review.get('development_judgment_inheritance_count')) is int
            and review['development_judgment_inheritance_count'] == 0, 'No development inheritance allowed')
    require(type(review.get('cases')) is list and len(review['cases']) == len(ids), 'Review denominator differs')
    require([row.get('case_id') for row in review['cases']] == ids, 'Review ordered IDs differ')
    for index, (judgment, row) in enumerate(zip(review['cases'], selected['cases']), 1):
        require_fields(judgment, ['position_one_based', 'output_sha256', 'case_structural_sha256',
            'structural_success', 'semantic_faithful', 'clean_usable', 'critical_error', 'joint_success',
            'reason', 'review_mode'], 'selected judgment')
        require(type(judgment['position_one_based']) is int and judgment['position_one_based'] == index,
                'Review position mismatch')
        require(all(type(judgment[key]) is bool for key in
                    ['structural_success', 'semantic_faithful', 'clean_usable', 'critical_error', 'joint_success']),
                'Review flags must be actual booleans')
        require(judgment['output_sha256'] == output_sha(row)
                and judgment['case_structural_sha256'] == digest_case(row), 'Review case binding differs')
        require(judgment['structural_success'] is structural(row), 'Review structural status differs')
        computed_joint = (structural(row) and judgment['semantic_faithful']
                          and judgment['clean_usable'] and not judgment['critical_error'])
        require(judgment['joint_success'] is computed_joint, 'Selected joint flag is inconsistent')
        require(type(judgment['reason']) is str and type(judgment['review_mode']) is str
                and 'personally_read' in judgment['review_mode']
                and 'no_inheritance' in judgment['review_mode'], 'Selected per-case fresh review evidence required')
    counts = review.get('counts')
    require(type(counts) is dict, 'Canonical review totals missing')
    expected = {'total': len(ids)}
    expected.update({key: sum(row[key] is True for row in review['cases'])
                     for key in ['semantic_faithful', 'clean_usable', 'critical_error',
                                 'structural_success', 'joint_success']})
    require(typed_equal(counts, expected), 'Canonical review totals inconsistent')


def build_packet(selected_report, control_report, selected_packet, control_packet, selected_review,
                 expected_count=500):
    """Inputs must first be loaded by load_pinned; count override is for synthetic checks only."""
    require(type(expected_count) is int and expected_count > 0, 'Invalid denominator')
    ids = validate_report(selected_report, expected_count, 'selected')
    control_ids = validate_report(control_report, expected_count, 'original-control')
    require(control_ids == ids, 'Exact complete ordered report IDs required')
    bind_packet(selected_packet, selected_report, 'selected_report', 'selected', ids)
    bind_packet(control_packet, control_report, 'control_report', 'original-control', ids)
    require_fields(selected_packet, GLOBAL_CONTEXT, 'selected global context')
    require_fields(control_packet, GLOBAL_CONTEXT, 'control global context')
    require(all(typed_equal(selected_packet[key], control_packet[key]) for key in GLOBAL_CONTEXT),
            'Global frozen review context differs')
    bind_review(selected_review, selected_report, ids)
    rows = []
    for position, (before, after, prior, left_context, right_context) in enumerate(zip(
            selected_report['cases'], control_report['cases'], selected_review['cases'],
            selected_packet['cases'], control_packet['cases']), 1):
        require(typed_equal(before['split'], after['split']), 'Report case split/context differs')
        require(all(typed_equal(left_context[key], right_context[key]) for key in CONTEXT_FIELDS),
                'Frozen per-case notes/context differ')
        comparisons = {key: typed_equal(before[key], after[key]) for key in FIELDS}
        selected_structure, control_structure = structural(before), structural(after)
        prior_pass = prior['joint_success'] is True and prior['critical_error'] is False
        inherit = all(comparisons.values()) and selected_structure and control_structure and prior_pass
        blockers = ['changed:' + key for key, equal in comparisons.items() if not equal]
        if not selected_structure:
            blockers.append('selected_structural_failure')
        if not control_structure:
            blockers.append('control_structural_failure')
        if not prior_pass:
            blockers.append('selected_judgment_not_successful_joint_pass')
        item = {key: right_context[key] for key in CONTEXT_FIELDS}
        item.update({
            'output_sha256': output_sha(after), 'case_structural_sha256': digest_case(after),
            'selected_output_sha256': output_sha(before),
            'selected_case_structural_sha256': digest_case(before),
            'exact_fields_equal': comparisons, 'same_frozen_notes_and_context': True,
            'selected_structural_success': selected_structure, 'structural_success': control_structure,
            'selected_prior_joint_success': prior['joint_success'],
            'selected_prior_critical_error': prior['critical_error'],
            'inherit_successful_fresh_selected_joint_pass': inherit,
            'new_semantic_judgment_assigned': False,
            'new_semantic_judgment': None,
            'joint_credit_allowed_after_personal_review': control_structure,
            'forced_joint_success_false': not control_structure,
            'reuse_blockers': blockers,
            'review_mode': ('strict_typed_13_field_same_fresh_selected_success_reuse'
                            if inherit else 'needs_personal_read_actual_control_pair'),
        })
        if inherit:
            item['inherited_selected_judgment'] = {
                key: prior[key] for key in ['semantic_faithful', 'clean_usable', 'critical_error',
                                           'joint_success', 'reason', 'review_mode']}
            item['inherited_source'] = {
                'canonical_review_sha256': SOURCES['selected_review'][1],
                'selected_report_sha256': SOURCES['selected_report'][1],
                'case_id': after['id'], 'position_one_based': position}
        else:
            item['actual_pair'] = {key: after[key] for key in PAIR_FIELDS}
        rows.append(item)
    return {
        'schema_version': 1, 'role': 'original-control',
        'purpose': 'Review preparation only; no new semantic grading.',
        'source_report_sha256': SOURCES['control_report'][1],
        'selected_report_sha256': SOURCES['selected_report'][1],
        'selected_canonical_review_sha256': SOURCES['selected_review'][1],
        'original_selected_packet_sha256': SOURCES['selected_packet'][1],
        'original_control_packet_sha256': SOURCES['control_packet'][1],
        'frozen_corpus_sha256': FROZEN_CORPUS_SHA256,
        'case_count': expected_count, 'ordered_case_ids_sha256': sha(canonical(ids).encode()),
        'exact_fields': FIELDS, 'strict_nested_JSON_types_required': True,
        'same_frozen_notes_and_context_required': True, 'manual_pair_fields': PAIR_FIELDS,
        'target_check_fields_compared_for_identity_only': FIELDS[11:],
        'target_or_check_values_exposed': False, 'development_judgment_reuse_count': 0,
        'new_semantic_judgments_assigned': 0, 'policy': control_packet['policy'],
        'inheritance_count': sum(row['inherit_successful_fresh_selected_joint_pass'] for row in rows),
        'personal_read_required': sum(not row['inherit_successful_fresh_selected_joint_pass'] for row in rows),
        'structural_success_count': sum(row['structural_success'] for row in rows),
        'forced_zero_joint_credit_count': sum(row['forced_joint_success_false'] for row in rows),
        'cases': rows,
    }


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def main():
    destinations = [OUT / name for name in
                    ['comparison-and-inheritance-packet.json', 'personal-read-required.json', 'preparation-receipt.json']]
    require(all(not path.exists() for path in destinations), 'Create-only artifacts; existing outputs preserved')
    docs = {key: load_pinned(path, digest) for key, (path, digest) in SOURCES.items()}
    # Corpus copies are hash-checked only, never parsed or exposed.
    corpus_copies = []
    for key in ['selected_report', 'control_report']:
        path = Path(docs[key]['metadata']['corpus_path'])
        expected_path = SOURCES[key][0].parent / 'probe-corpus.json'
        require(path == expected_path, 'Only this pinned run corpus copy may be hashed')
        require(sha(path.read_bytes()) == FROZEN_CORPUS_SHA256, 'Actual frozen corpus copy digest differs')
        corpus_copies.append({'path': str(path), 'sha256': FROZEN_CORPUS_SHA256})
    packet = build_packet(**docs)
    require(packet['forced_zero_joint_credit_count'] == 3, 'Expected three structural control failures')
    packet['controller_source_sha256'] = sha(Path(__file__).read_bytes())
    manual = {key: packet[key] for key in [
        'schema_version', 'role', 'source_report_sha256', 'frozen_corpus_sha256',
        'selected_canonical_review_sha256', 'policy', 'manual_pair_fields',
        'new_semantic_judgments_assigned', 'forced_zero_joint_credit_count']}
    manual.update(purpose='Every listed actual control pair needs personal semantic reading.',
                  case_count=packet['personal_read_required'],
                  cases=[row for row in packet['cases'] if not row['inherit_successful_fresh_selected_joint_pass']])
    write_new(destinations[0], packet)
    write_new(destinations[1], manual)
    receipt = {
        'purpose': 'Mechanical fresh-selected-success reuse preparation; no new semantic decisions.',
        'counts': {key: packet[key] for key in ['case_count', 'inheritance_count', 'personal_read_required',
                  'structural_success_count', 'forced_zero_joint_credit_count',
                  'development_judgment_reuse_count', 'new_semantic_judgments_assigned']},
        'sources': {key: {'path': str(path), 'sha256': digest} for key, (path, digest) in SOURCES.items()},
        'corpus_copies_hash_only': corpus_copies,
        'controller': {'path': str(Path(__file__)), 'sha256': packet['controller_source_sha256']},
        'adapted_equality_source': {
            'path': str(WORK / 'micro64-knownsets-review-preparation/create_packet.py'),
            'sha256': 'b2b7adba6ae1160509fea4f5a2ac084ee5126802221274fa6724bae769f98497'},
        'artifacts': {path.name: {'path': str(path), 'sha256': sha(path.read_bytes())}
                      for path in destinations[:2]},
        'original_source_pins_reverified_after_write': True,
    }
    for path, digest in SOURCES.values():
        require(sha(path.read_bytes()) == digest, 'Original artifact changed during preparation')
    write_new(destinations[2], receipt)
    print(json.dumps(receipt['counts'], sort_keys=True))


if __name__ == '__main__':
    main()

