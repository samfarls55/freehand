"""Meaningful graph invariants on synthetic examples; no corpus/Torch calls."""
import copy
import math
import unittest

from editor_core import EditorError, ProtectedSpan, tokenize_source
from source_tag_contract import (IGNORE_INDEX, MAX_INSERTIONS, MAX_VISITS, TAG_KEYS,
    TagVocabulary, build_tag_label, decode_tag_scores, execute_tag_labels)


def scores_for(document, labels=None):
    vocabulary = TagVocabulary.current()
    nodes = len(document.atoms)+1
    def logits(size, winner=0):
        return [10.0 if index == winner else -10.0 for index in range(size)]
    scores = {'count': [logits(vocabulary.size('count'), 1) for _ in range(nodes)]}
    for name in TAG_KEYS[1:]:
        if name == 'insert':
            scores[name] = [[[logits(vocabulary.size(name)) for _ in range(MAX_INSERTIONS)]
                for _ in range(MAX_VISITS)] for _ in range(nodes)]
        else:
            size = nodes if name == 'pointer' else vocabulary.size(name)
            scores[name] = [[logits(size) for _ in range(MAX_VISITS)] for _ in range(nodes)]
    if labels is not None:
        for node in range(nodes):
            value = labels['count'][node]
            if value != IGNORE_INDEX:
                scores['count'][node] = logits(vocabulary.size('count'), value)
            for occurrence in range(MAX_VISITS):
                for name in TAG_KEYS[1:]:
                    if name == 'insert':
                        for position in range(MAX_INSERTIONS):
                            value = labels[name][node][occurrence][position]
                            if value != IGNORE_INDEX:
                                scores[name][node][occurrence][position] = logits(vocabulary.size(name), value)
                    else:
                        value = labels[name][node][occurrence]
                        if value != IGNORE_INDEX:
                            size = nodes if name == 'pointer' else vocabulary.size(name)
                            scores[name][node][occurrence] = logits(size, value)
    return scores


class SourceTagContractTests(unittest.TestCase):
    def assert_roundtrip(self, source, target, spans=()):
        document = tokenize_source(source, spans)
        label = build_tag_label(document, target)
        self.assertTrue(label.supported, label.reasons)
        self.assertEqual(execute_tag_labels(document, label.labels).text, target)
        decoded = decode_tag_scores(document, scores_for(document, label.labels))
        self.assertTrue(decoded.accepted, decoded.reasons)
        self.assertEqual(decoded.execution.text, target)
        self.assertFalse(decoded.diagnostics['gold_or_target_used'])
        return document, label

    def test_identity_is_default_without_target(self):
        for source in ('Ada sent the parcel.', 'Use PN-83 at 7:30.', 'No extra straw goes under the jars.',
                       'The pantry had had mice.', "'Cause the hinge is stiff, hold it."):
            document = tokenize_source(source)
            result = decode_tag_scores(document, scores_for(document))
            self.assertTrue(result.accepted, result.reasons)
            self.assertEqual(result.execution.text, source)

    def test_identity_labels_copy_all_original_punctuation(self):
        for source in ('Ada report.', 'Use PN-83 at 7:30.', 'The pantry had had mice.'):
            document, label = self.assert_roundtrip(source, source)
            self.assertEqual(label.labels['count'][1:], [1]*len(document.atoms))
            for name in ('case', 'form', 'repair', 'insert_count'):
                self.assertTrue(all(value in (IGNORE_INDEX, 0)
                    for row in label.labels[name] for value in row))
            self.assertTrue(all(value == IGNORE_INDEX for row in label.labels['pointer'] for value in row))

    def test_local_delete_and_case(self):
        self.assert_roundtrip('Um, send the parcel.', 'Send the parcel.')

    def test_compound_hyphen_and_source_present_id_spacing(self):
        self.assert_roundtrip('The silver, um, the silver-lined tray is ready.',
                              'The silver-lined tray is ready.')
        self.assert_roundtrip('Mark HX-21, no, HX-81.', 'Mark HX-81.')

    def test_cannot_recombine_an_unseen_identifier(self):
        label = build_tag_label(tokenize_source('Mark HX-21 and WX-91.'), 'Mark HX-91.')
        self.assertFalse(label.supported)

    def test_noun_binding_reorder(self):
        document, label = self.assert_roundtrip('Could you send the parcel, actually, have Neri inspect it.',
                                               'Have Neri inspect the parcel.')
        self.assertTrue(any(value == 1 for row in label.labels['repair'] for value in row))

    def test_bounded_noun_and_function_reuse(self):
        _, label = self.assert_roundtrip('Pack the crate and label it.', 'Pack the crate and label the crate.')
        self.assertEqual(max(label.labels['count']), 2)

    def test_finite_morphology(self):
        _, label = self.assert_roundtrip('Format the file.', 'Formatted the file.')
        self.assertTrue(any(value > 0 for row in label.labels['form'] for value in row))

    def test_protected_negative_context_order(self):
        source = 'Use old, no new.'
        spans = (ProtectedSpan('opaque-old', source.index('old'), source.index('old')+3),
                 ProtectedSpan('opaque-new', source.index('new'), source.index('new')+3))
        _, label = self.assert_roundtrip(source, 'Instead of old, use new.', spans)
        self.assertTrue(any(value > 0 for row in label.labels['insert_count'] for value in row))

    def test_protected_count_is_forced_at_inference(self):
        source = 'Keep exact.'
        document = tokenize_source(source, (ProtectedSpan('opaque', 5, 10),))
        scores = scores_for(document)
        node = next(atom.index+1 for atom in document.atoms if atom.kind == 'protected')
        scores['count'][node] = [100.0, -100.0, -100.0, -100.0]
        result = decode_tag_scores(document, scores)
        self.assertTrue(result.accepted, result.reasons)
        self.assertEqual(result.execution.text, source)

    def test_protected_mutation_and_deletion_are_unsupported(self):
        document = tokenize_source('Keep exact.', (ProtectedSpan('opaque', 5, 10),))
        for target in ('Keep other.', 'Keep.'):
            self.assertFalse(build_tag_label(document, target).supported)

    def test_protected_reorder_is_rejected(self):
        source = 'First second.'
        document = tokenize_source(source, (ProtectedSpan('a', 0, 5), ProtectedSpan('b', 6, 12)))
        label = build_tag_label(document, source)
        altered = copy.deepcopy(label.labels)
        altered['repair'][0][0] = 1
        altered['pointer'][0][0] = 2
        altered['repair'][2][0] = 1
        altered['pointer'][2][0] = 1
        with self.assertRaises(EditorError):
            execute_tag_labels(document, altered)

    def test_unknown_lexical_and_numeric_values_unavailable(self):
        document = tokenize_source('Move 17 crates.')
        for target in ('Move 18 crates.', 'Move 17 helmets.'):
            self.assertFalse(build_tag_label(document, target).supported)

    def test_early_END_cannot_drop_predicted_kept_fact(self):
        document = tokenize_source('Ada mailed parcels.')
        label = build_tag_label(document, document.text)
        labels = copy.deepcopy(label.labels)
        labels['repair'][0][0], labels['pointer'][0][0] = 1, 0
        with self.assertRaisesRegex(EditorError, 'tag_early_END'):
            execute_tag_labels(document, labels)

    def test_repair_cycle_cannot_exceed_visit_budget(self):
        document = tokenize_source('Ada mailed parcels.')
        label = build_tag_label(document, document.text)
        labels = copy.deepcopy(label.labels)
        labels['repair'][1][0], labels['pointer'][1][0] = 1, 1
        with self.assertRaisesRegex(EditorError, 'tag_cycle'):
            execute_tag_labels(document, labels)

    def test_excess_reuse_and_insertions_stay_unsupported(self):
        document = tokenize_source('crate.')
        label = build_tag_label(document, 'Crate crate crate crate.')
        self.assertFalse(label.supported)
        self.assertTrue(any('reuse_capacity' in reason for reason in label.reasons))
        label = build_tag_label(document, 'Instead instead instead instead instead crate.')
        self.assertFalse(label.supported)
        self.assertTrue(any('insert_capacity' in reason for reason in label.reasons))

    def test_gold_whitespace_not_silently_repaired(self):
        label = build_tag_label(tokenize_source('My book.'), 'My  book.')
        self.assertFalse(label.supported)
        self.assertTrue(any('spacing_not_expressible' in reason for reason in label.reasons))

    def test_empty_and_capacity_sources_are_unsupported(self):
        self.assertFalse(build_tag_label(tokenize_source(''), 'The').supported)
        self.assertFalse(build_tag_label(tokenize_source(' '.join(['word']*513)), 'word').supported)

    def test_malformed_scores_and_vocabulary_fail(self):
        document = tokenize_source('Ada mailed parcels.')
        for bad in (float('nan'), math.inf):
            scores = scores_for(document)
            scores['count'][1][0] = bad
            self.assertFalse(decode_tag_scores(document, scores).accepted)
        scores = scores_for(document)
        scores.pop('pointer')
        self.assertFalse(decode_tag_scores(document, scores).accepted)
        value = TagVocabulary.current().to_dict()
        value['unexpected'] = True
        with self.assertRaises(EditorError):
            TagVocabulary.from_dict(value)


if __name__ == '__main__':
    unittest.main()
