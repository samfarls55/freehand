"""Individually authored reserved predicate-preservation contrasts; no evaluation input."""
from pathlib import Path
import collections
import hashlib
import json
import sys
import unicodedata

ROOT = Path('/workspace/freehand')
HERE = Path(__file__).resolve().parent
TRAINING = HERE.parent / 'v9-positive-curriculum/positive-3394-proposed.jsonl'
TRAINING_SHA = 'a10667ecb58077b159542291a13cbe6c178896cb24edb7ce612a326247ebe98e'
sys.path.insert(0, str(ROOT / 'tools/Freehand.Cleanup.Evaluation'))
from specialist_literal_protection import SpecialistLiteralMask, PROTOCOL

CASES = [
    ("Please lay the linen runner lengthways, no, crossways, so the embroidered edge stays visible.",
     "Please lay the linen runner crossways, so the embroidered edge stays visible.",
     'The fragment crossways replaces lengthways only; keep lay, the linen runner, courtesy and the embroidered-edge purpose.'),
    ("I would like the recipe read silently, no, aloud, because Deni cannot see the card.",
     "I would like the recipe read aloud, because Deni cannot see the card.",
     'Aloud is an attribute fragment, not a new speech act; keep would-like, recipe/read and the complete negative causal fact.'),
    ("Can you display the itinerary as a grid, no, as a timeline, for the school secretary?",
     "Can you display the itinerary as a timeline for the school secretary?",
     'The format correction does not restate display or itinerary; preserve both, the modal question and the secretary recipient.'),
    ("We should store the saffron in the cupboard, correction, in the freezer; the kitchen will be closed tomorrow.",
     "We should store the saffron in the freezer; the kitchen will be closed tomorrow.",
     'Replace only the storage location; keep we/should/store/saffron and the independent tomorrow closure fact.'),
    ("Ask Elina to send the sketches by courier, I mean, by email; the originals must stay here.",
     "Ask Elina to send the sketches by email; the originals must stay here.",
     'By-email corrects the delivery method only; preserve the outer ask, Elina as actor, send/sketches and the originals constraint.'),
    ("The tiles need to be arranged in a circle, no, in straight rows, before the guests arrive.",
     "The tiles need to be arranged in straight rows before the guests arrive.",
     'Keep tiles and the full need-to-be-arranged passive frame; replace only circle layout and retain the arrival deadline.'),
    ("I planned to trim the hedge from the street side, no, from the courtyard side, after the rain stops.",
     "I planned to trim the hedge from the courtyard side after the rain stops.",
     'The side fragment corrects the past plan attribute; preserve I planned, trim/hedge and the rain condition without making an imperative.'),
    ("Please position the cello case upright, no, flat, because the shelf above it is low.",
     "Please position the cello case flat, because the shelf above it is low.",
     'Flat replaces upright only; retain position, cello case, courtesy and the low-shelf explanation with its noun anchor.'),
    ("Matan should have the portrait copied in charcoal, no, in ink; the frame is already paid for.",
     "Matan should have the portrait copied in ink; the frame is already paid for.",
     'Replace only the copying medium; retain Matan, should-have, portrait/copied and the separate already-paid frame fact.'),
    ("Could you seat the seminar group near the entrance, make that near the garden, without moving the lectern?",
     "Could you seat the seminar group near the garden without moving the lectern?",
     'The location fragment needs seat and seminar group from the first clause; preserve the modal question and no-lectern-movement constraint.'),
    ("I'd rather rehearse the duet with a metronome, no, without a metronome, while Sefa checks the microphones.",
     "I'd rather rehearse the duet without a metronome while Sefa checks the microphones.",
     'Without-a-metronome corrects accompaniment only; retain conditional preference, rehearse/duet and Sefa\'s unaffected checking action.'),
    ("Send the field summary on paper, sorry, as an audio note; Harun cannot use the printed copy.",
     "Send the field summary as an audio note; Harun cannot use the printed copy.",
     'The output-format fragment does not cancel sending the field summary; retain send/object and Harun\'s negative accessibility explanation.'),
    ("Place one lamp low on the bookcase and the other high on the stair landing.",
     "Place one lamp low on the bookcase and the other high on the stair landing.",
     'Clean contrast assigns different heights and locations to two lamps; the second complement is legitimate ellipsis, not a correction.'),
    ("I'd prefer the lesson recorded indoors rather than outdoors, because the courtyard is noisy.",
     "I'd prefer the lesson recorded indoors rather than outdoors, because the courtyard is noisy.",
     'The complete grammatical preference already contrasts locations; preserve prefer, recorded lesson and the causal noise fact.'),
    ("Read the tide chart aloud to the crew but silently during your own check.",
     "Read the tide chart aloud to the crew but silently during your own check.",
     'Both reading methods apply in distinct contexts; do not treat the second contextual complement as a retraction.'),
    ("The folders belong beside the copier, not beneath it; the shelves underneath hold blank paper.",
     "The folders belong beside the copier, not beneath it; the shelves underneath hold blank paper.",
     'Already-clean negative spatial contrast and independent shelf fact; preserve all noun anchors, locations and objects.'),
    ("Please send the invitations electronically while keeping a paper copy for the ledger.",
     "Please send the invitations electronically while keeping a paper copy for the ledger.",
     'Electronic sending and paper retention are compatible distinct actions; preserve both objects, the ledger purpose and courtesy.'),
    ("I expected the badges to face inward; Tova expected them to face outward.",
     "I expected the badges to face inward; Tova expected them to face outward.",
     'Two actors have contrasting past expectations; neither orientation retracts the other actor\'s complete statement.'),
    ("The solo sounds gentler with a mute than without one, and the conductor prefers that gentler sound.",
     "The solo sounds gentler with a mute than without one, and the conductor prefers that gentler sound.",
     'This is a grammatical sound comparison and preference fact, not a request or spoken-method repair; retain every clause.'),
    ("Arrange the lanterns along the path rather than across the steps, so visitors have a clear route.",
     "Arrange the lanterns along the path rather than across the steps, so visitors have a clear route.",
     'The clean rather-than location contrast is already complete; retain arrange/lanterns, the excluded location and the purpose.'),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def th(value):
    return hashlib.sha256(value.encode()).hexdigest()


def norm(value):
    return ' '.join(unicodedata.normalize('NFC', value).split()).strip().casefold()


def main():
    assert sha(TRAINING) == TRAINING_SHA
    previous = [json.loads(line) for line in TRAINING.read_text().splitlines()]
    old_inputs, old_targets = {norm(r['input']) for r in previous}, {norm(r['target']) for r in previous}
    old_pairs = {(norm(r['input']), norm(r['target'])) for r in previous}
    rows, audit = [], []
    forbidden = ('bolt', 'tighten', 'clockwise', 'counterclockwise', 'reverse thread')
    for position, (source, target, reason) in enumerate(CASES, 1):
        case_id = f'scribe-reserved-predicate-{position:03d}'
        assert 9 <= len(source.split()) <= 30
        assert all(word not in (source + ' ' + target).casefold() for word in forbidden)
        assert norm(source) not in old_inputs and norm(target) not in old_targets
        assert (norm(source), norm(target)) not in old_pairs
        mask = SpecialistLiteralMask.create(source)
        assert not mask.tokens and not mask.legacy.blocks
        assert mask.restore(target) == target
        row = {'id': case_id, 'input': source, 'target': target,
            'family': 'attribute_fragment_correction_preserves_governing_predicate_object',
            'needs_cleanup': position <= 12, 'notes': reason, 'semantic_label_reason': reason,
            'author_provenance': {'author': 'editing_architectures', 'method': 'Individually authored controlled synthetic taxonomy contrast.',
                'basis': 'Root predicate-omission taxonomy request only, 2026-11-04; no evaluation cases or outputs.',
                'source_script': Path(__file__).name, 'source_script_sha256': sha(Path(__file__)), 'draft_version': 'v1'}}
        assert row['needs_cleanup'] == (source != target)
        rows.append(row)
        audit.append({'id': case_id, 'input_sha256': th(source), 'target_sha256': th(target),
            'author_semantic_decision': 'PASS', 'rationale': reason,
            'predicate_and_object_kept': True, 'voice_modality_courtesy_independent_facts_kept': True,
            'input_words': len(source.split()), 'needs_cleanup': row['needs_cleanup'],
            'quoted_payloads': 0, 'protected_literal_roundtrip': True})
    assert len(rows) == len({norm(r['input']) for r in rows}) == len({norm(r['target']) for r in rows}) == 20
    output = HERE / 'train-20-v1.jsonl'
    with output.open('x') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    record = {'schema_version': 1, 'status': 'RESERVED_UNUSED_AUTHOR_REVIEW_ONLY_PENDING_ALL20_INDEPENDENT_SEMANTIC_REVIEWS',
        'source_path': output.name, 'source_sha256': sha(output), 'rows': 20, 'cleanup_pairs': 12,
        'clean_controls': 8, 'source_word_range': [min(c['input_words'] for c in audit), max(c['input_words'] for c in audit)],
        'source_copy_target_policy': 'Only an explicit local attribute correction removes old attribute/cue; governing predicate/object, frame and facts remain.',
        'literal_protocol': PROTOCOL, 'quoted_payloads': 0, 'all_literal_roundtrips': 20,
        'approved_training_sha256': TRAINING_SHA, 'training_exposures': len(previous),
        'training_duplicate_check': {'normalization': 'NFC, whitespace collapse, casefold', 'input_overlap': 0, 'target_overlap': 0, 'pair_overlap': 0},
        'casewise_author_review': audit, 'no_Core_tokenizer_model_native_build_training_or_evaluation_reads': True,
        'source_and_active_models_or_parent_UL_binding_changed': False}
    with (HERE / 'author-review-v1.json').open('x') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    assert sha(TRAINING) == TRAINING_SHA and 'torch' not in sys.modules
    print(json.dumps({'path': str(output), 'sha256': sha(output), 'rows': 20, 'cleanup': 12,
        'controls': 8, 'word_range': record['source_word_range'],
        'author_review_sha256': sha(HERE / 'author-review-v1.json')}), flush=True)


if __name__ == '__main__':
    main()
