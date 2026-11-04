"""Source-indexed bounded edit graph; stdlib only, no quotation parser/model.

Node0 is BEGIN; nodej copies/morphs source atomj-1. A node may be visited at
most three times. Identity edges advance to the next not-yet-emitted kept
source atom; explicit repair edges allow bounded reorder/reuse. END requires
all predicted counts consumed. Source text, never gold, determines rendering.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache, cached_property
import hashlib
import json
import math
import re
from typing import Any, Mapping

from editor_core import EditorError, Operation, Program, SourceDocument, align_gold, execute
from editor_core.core import _emit, contract_metadata, morphology_outputs
from editor_core.head_contract import HeadVocabulary

MAX_VISITS = 3
MAX_INSERTIONS = 4
MAX_SOURCE_ATOMS = 512
IGNORE_INDEX = -100
TAG_KEYS = ('count', 'case', 'form', 'repair', 'pointer', 'insert_count', 'insert')
CONTRACT_VERSION = 'source-indexed-bounded-edit-graph-v1'


@dataclass(frozen=True)
class TagVocabulary:
    cases: tuple[str, ...]
    form_values: tuple[str, ...]
    insert_values: tuple[tuple[str, str, str] | None, ...]
    editor_contract_sha256: str

    @classmethod
    @lru_cache(maxsize=1)
    def current(cls):
        old = HeadVocabulary.current()
        inserts = tuple(('function', value, case) for value in old.function_values
            for case in ('keep', 'initial_upper', 'upper')) + tuple(
                ('punct', value, 'keep') for value in old.punct_values)
        return cls(old.cases, ('COPY', *old.morph_values), (None, *inserts),
            contract_metadata()['sha256'])

    def size(self, name):
        return {'count': MAX_VISITS+1, 'case': len(self.cases),
            'form': len(self.form_values), 'repair': 2,
            'insert_count': MAX_INSERTIONS+1, 'insert': len(self.insert_values)}[name]

    def to_dict(self):
        return {'contract_version': CONTRACT_VERSION, 'max_visits': MAX_VISITS,
            'max_insertions': MAX_INSERTIONS, 'cases': list(self.cases),
            'form_values': list(self.form_values),
            'insert_values': [list(value) if value is not None else None for value in self.insert_values],
            'editor_contract_sha256': self.editor_contract_sha256}

    @classmethod
    def from_dict(cls, value):
        if value != cls.current().to_dict():
            raise EditorError('tag_vocabulary_mismatch', 'Unexpected source-tag vocabulary or schema')
        return cls.current()

    @cached_property
    def sha256(self):
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True,
            ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True)
class TagLabel:
    supported: bool
    reasons: tuple[str, ...]
    labels: Mapping[str, Any]
    vocabulary_sha256: str
    program: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class TagDecodeResult:
    accepted: bool
    program: Program | None
    execution: Any
    reasons: tuple[str, ...]
    diagnostics: Mapping[str, Any]


def _insert_operation(index, vocabulary):
    if type(index) is not int or not 0 < index < len(vocabulary.insert_values):
        raise EditorError('tag_insert', 'An active insertion needs a finite non-NONE class')
    kind, value, case = vocabulary.insert_values[index]
    return Operation(kind, value=value, case=case)


def _source_operation(document, node, case, form, vocabulary):
    if type(node) is not int or not 1 <= node <= len(document.atoms):
        raise EditorError('tag_pointer', 'Source node is out of range')
    if type(case) is not int or not 0 <= case < len(vocabulary.cases):
        raise EditorError('tag_case', 'Case class is invalid')
    if type(form) is not int or not 0 <= form < len(vocabulary.form_values):
        raise EditorError('tag_form', 'Form class is invalid')
    op = Operation('copy' if form == 0 else 'morph', source_index=node-1,
        value=None if form == 0 else vocabulary.form_values[form], case=vocabulary.cases[case])
    _emit(document, op)
    return op


def _default_next(node, counts, visits):
    return next((candidate for candidate in range(node+1, len(counts))
                 if visits[candidate] < counts[candidate]), 0)


def render_emissions(document, emissions):
    """Preserve original adjacent gaps; otherwise use fixed ordinary punctuation.

    The old executor remains the authority for protected order, numeric/lexical
    joins and exact provenance. Spacing never reads a target or model score.
    """
    result = []
    previous = None
    previous_text = None
    for op in emissions:
        text, _ = _emit(document, op)
        gap = ''
        if previous is not None:
            if (previous.source_index is not None and op.source_index is not None
                    and op.source_index == previous.source_index+1):
                a = document.atoms[previous.source_index]
                b = document.atoms[op.source_index]
                gap = document.text[a.end:b.start]
                if any(not value.isspace() for value in gap):
                    raise EditorError('tag_gap', 'Adjacent original source gap contains unaccounted content')
            elif text in {'.', ',', '!', '?', ';', ':', ')', ']', '}'}:
                gap = ''
            elif previous_text in {'(', '[', '{'}:
                gap = ''
            elif text == '-' or previous_text == '-':
                # Ordinary compound hyphenation; discourse-hyphen gaps are
                # preserved above when their original adjacent atoms survive.
                gap = ''
            elif (previous.source_index is not None and op.source_index is not None
                    and document.atoms[previous.source_index].kind == 'word'
                    and document.atoms[op.source_index].kind == 'number'
                    and text.startswith(('-', '+'))
                    and re.search(r"(?<![\w'’])" + re.escape(previous_text+text)
                                  + r"(?![\w'’])", document.text)):
                # A letter-plus-signed-number ID may be assembled only when
                # the complete surface already occurs in this source. Do not
                # create HX-91 by combining HX-21 with a different WX-91.
                gap = ''
            else:
                gap = ' '
        if gap:
            result.append(Operation('space', value=gap))
        result.append(op)
        previous, previous_text = op, text
    return Program(tuple(result))


def _validate_counts(document, counts):
    if len(counts) != len(document.atoms)+1 or counts[0] not in (0, IGNORE_INDEX):
        raise EditorError('tag_count', 'Counts must contain one BEGIN and all source nodes')
    for node, count in enumerate(counts[1:], 1):
        if type(count) is not int or not 0 <= count <= MAX_VISITS:
            raise EditorError('tag_count', 'Source visit count outside bounded range')
        if document.atoms[node-1].kind == 'protected' and count != 1:
            raise EditorError('protected_count', 'Protected atoms require exactly one visit')


def _run_graph(document, counts, choose, vocabulary):
    _validate_counts(document, counts)
    visits = [0] * len(counts)
    node, occurrence = 0, 0
    emitted = []
    transitions = []
    for step in range(sum(counts[1:])+1):
        state = choose(node, occurrence, counts, visits)
        if node:
            if visits[node] >= counts[node]:
                raise EditorError('tag_cycle', 'Source node visit budget exhausted')
            emitted.append(_source_operation(document, node, state['case'], state['form'], vocabulary))
            visits[node] += 1
        inserted = state['insert']
        if not isinstance(inserted, (list, tuple)) or len(inserted) > MAX_INSERTIONS:
            raise EditorError('tag_insert', 'Finite insertion run exceeds capacity')
        emitted.extend(_insert_operation(index, vocabulary) for index in inserted)
        repair = state['repair']
        if type(repair) is not int or repair not in (0, 1):
            raise EditorError('tag_repair', 'Repair flag must be0 or1')
        following = state['pointer'] if repair else _default_next(node, counts, visits)
        if type(following) is not int or not 0 <= following < len(counts):
            raise EditorError('tag_pointer', 'Next source/END pointer is invalid')
        transitions.append({'node': node, 'occurrence': occurrence, 'repair': repair,
            'next_node': following, 'insert_count': len(inserted)})
        if following == 0:
            if any(visits[index] != counts[index] for index in range(1, len(counts))):
                raise EditorError('tag_early_END', 'END would omit a predicted kept/reused source atom')
            program = render_emissions(document, emitted)
            execution = execute(document, program)
            return program, execution, transitions
        if visits[following] >= counts[following]:
            raise EditorError('tag_cycle', 'Next source node has no remaining visits')
        node, occurrence = following, visits[following]
    raise EditorError('tag_transition_capacity', 'Graph failed to terminate within visit budget')


def execute_tag_labels(document, labels, vocabulary=None):
    vocabulary = vocabulary or TagVocabulary.current()
    if set(labels) != set(TAG_KEYS):
        raise EditorError('tag_schema', 'All frozen tag label fields are required')
    def choose(node, occurrence, counts, visits):
        count = labels['insert_count'][node][occurrence]
        if type(count) is not int or not 0 <= count <= MAX_INSERTIONS:
            raise EditorError('tag_insert', 'Insertion count is invalid')
        return {'case': labels['case'][node][occurrence],
            'form': labels['form'][node][occurrence],
            'repair': labels['repair'][node][occurrence],
            'pointer': labels['pointer'][node][occurrence],
            'insert': labels['insert'][node][occurrence][:count]}
    return _run_graph(document, labels['count'], choose, vocabulary)[1]


def _blank_labels(nodes):
    return {'count': [IGNORE_INDEX] + [0] * (nodes-1),
        **{name: [[IGNORE_INDEX]*MAX_VISITS for _ in range(nodes)]
           for name in ('case', 'form', 'repair', 'pointer', 'insert_count')},
        'insert': [[[IGNORE_INDEX]*MAX_INSERTIONS for _ in range(MAX_VISITS)] for _ in range(nodes)]}


def build_tag_label(document, target, *, program=None, target_protected_spans=None, vocabulary=None):
    vocabulary = vocabulary or TagVocabulary.current()
    try:
        TagVocabulary.from_dict(vocabulary.to_dict())
        if not 1 <= len(document.atoms) <= MAX_SOURCE_ATOMS:
            raise EditorError('tag_source_capacity', 'Head needs1..512 source atoms')
        if program is None:
            alignment = align_gold(document, target, target_protected_spans=target_protected_spans)
            if not alignment.supported:
                return TagLabel(False, alignment.reasons, {}, vocabulary.sha256)
            program = alignment.program
        if execute(document, program).text != target:
            raise EditorError('tag_gold_program', 'Supplied old program must exactly execute to canonical gold')
        if target == document.text:
            # A clean identity target must supervise identity, including its
            # original punctuation. The general aligner may choose a tied
            # DELETE-punctuation/INSERT-identical-punctuation representation.
            # Canonicalize only exact source==target; edited golds keep their
            # original executed program and are never silently rewritten.
            program = render_emissions(document,
                [Operation('copy', source_index=atom.index) for atom in document.atoms])
            if execute(document, program).text != target:
                raise EditorError('tag_identity_spacing', 'Exact identity source cannot use a different render')
        # Collect the finite additions after each anchored occurrence, including
        # BEGIN additions. Gold only determines labels, never inference choices.
        states = [{'node': 0, 'occurrence': 0, 'case': IGNORE_INDEX, 'form': IGNORE_INDEX, 'insert': []}]
        counts = Counter()
        for op in program.operations:
            if op.kind in ('space', 'delete'):
                continue
            if op.kind in ('copy', 'morph'):
                node = op.source_index+1
                occurrence = counts[node]
                counts[node] += 1
                if counts[node] > MAX_VISITS:
                    raise EditorError('tag_reuse_capacity', 'Gold exceeds bounded source reuse')
                states.append({'node': node, 'occurrence': occurrence,
                    'case': vocabulary.cases.index(op.case),
                    'form': 0 if op.kind == 'copy' else vocabulary.form_values.index(op.value), 'insert': []})
            else:
                desired, _ = _emit(document, op)
                candidates = [index for index in range(1, len(vocabulary.insert_values))
                    if _emit(document, _insert_operation(index, vocabulary))[0] == desired
                    and vocabulary.insert_values[index][0] == op.kind]
                if not candidates:
                    raise EditorError('tag_insert_inventory', 'Gold finite insertion has no tag class')
                states[-1]['insert'].append(candidates[0])
                if len(states[-1]['insert']) > MAX_INSERTIONS:
                    raise EditorError('tag_insert_capacity', 'Gold finite insertion run exceeds bounded capacity')
        labels = _blank_labels(len(document.atoms)+1)
        for node, count in counts.items():
            labels['count'][node] = count
        visits = [0] * len(labels['count'])
        for index, state in enumerate(states):
            node, occurrence = state['node'], state['occurrence']
            if node:
                labels['case'][node][occurrence] = state['case']
                labels['form'][node][occurrence] = state['form']
                visits[node] += 1
            actual_next = states[index+1]['node'] if index+1 < len(states) else 0
            default_next = _default_next(node, labels['count'], visits)
            repair = int(actual_next != default_next)
            labels['repair'][node][occurrence] = repair
            labels['pointer'][node][occurrence] = actual_next if repair else IGNORE_INDEX
            labels['insert_count'][node][occurrence] = len(state['insert'])
            labels['insert'][node][occurrence][:len(state['insert'])] = state['insert']
        result = execute_tag_labels(document, labels, vocabulary)
        if result.text != target:
            raise EditorError('tag_spacing_not_expressible', 'Deterministic source-based spacing differs from canonical gold')
        graph = {'contract_version': CONTRACT_VERSION, 'counts': labels['count'], 'states': states}
        return TagLabel(True, (), labels, vocabulary.sha256, graph)
    except EditorError as error:
        return TagLabel(False, (str(error),), {}, vocabulary.sha256)


def _argmax(values, expected, name, allowed=None):
    if not isinstance(values, (tuple, list)) or len(values) != expected:
        raise EditorError('tag_score_shape', f'Unexpected {name} score shape')
    if any(type(value) not in (int, float) or math.isnan(value) or value == math.inf for value in values):
        raise EditorError('tag_score_nonfinite', f'Invalid {name} score')
    valid = list(range(expected) if allowed is None else allowed)
    valid = [index for index in valid if values[index] > -math.inf]
    if not valid:
        raise EditorError('tag_score_masked', f'No admissible {name} class')
    return max(valid, key=lambda index: (values[index], -index))


def decode_tag_scores(document, scores, *, vocabulary=None):
    vocabulary = vocabulary or TagVocabulary.current()
    diagnostics = {'vocabulary_sha256': vocabulary.sha256, 'source_atoms': len(document.atoms),
        'max_visits': MAX_VISITS, 'max_insertions': MAX_INSERTIONS,
        'fallback_success_credit': False, 'gold_or_target_used': False}
    try:
        nodes = len(document.atoms)+1
        if not 1 < nodes <= MAX_SOURCE_ATOMS+1 or set(scores) != set(TAG_KEYS):
            raise EditorError('tag_score_schema', 'Invalid source capacity or score schema')
        if any(not isinstance(scores[name], (tuple, list)) or len(scores[name]) != nodes for name in TAG_KEYS):
            raise EditorError('tag_score_shape', 'Every score head needs BEGIN plus all source nodes')
        counts = [0] + [_argmax(scores['count'][node], MAX_VISITS+1, 'count')
            for node in range(1, nodes)]
        for node, atom in enumerate(document.atoms, 1):
            if atom.kind == 'protected':
                counts[node] = 1
        def choose(node, occurrence, counts, visits):
            for name in TAG_KEYS[1:]:
                if not isinstance(scores[name][node], (tuple, list)) or len(scores[name][node]) != MAX_VISITS:
                    raise EditorError('tag_score_shape', 'Occurrence axis differs from frozen capacity')
            case = form = 0
            if node:
                atom = document.atoms[node-1]
                if atom.kind == 'word':
                    case = _argmax(scores['case'][node][occurrence], vocabulary.size('case'), 'case')
                    available = morphology_outputs(atom.text)
                    allowed = [0] + [index for index, value in enumerate(vocabulary.form_values)
                        if index and value in available]
                    form = _argmax(scores['form'][node][occurrence], vocabulary.size('form'), 'form', allowed)
            repair = _argmax(scores['repair'][node][occurrence], 2, 'repair')
            pointer = 0
            if repair:
                # Current node consumes one visit before its outgoing edge.
                after = list(visits)
                if node:
                    after[node] += 1
                allowed = [candidate for candidate in range(1, nodes) if after[candidate] < counts[candidate]]
                if all(after[index] == counts[index] for index in range(1, nodes)):
                    allowed.append(0)
                pointer = _argmax(scores['pointer'][node][occurrence], nodes, 'pointer', allowed)
            count = _argmax(scores['insert_count'][node][occurrence], MAX_INSERTIONS+1, 'insert_count')
            values = scores['insert'][node][occurrence]
            if not isinstance(values, (tuple, list)) or len(values) != MAX_INSERTIONS:
                raise EditorError('tag_score_shape', 'Insertion-position axis differs')
            inserted = [_argmax(values[index], vocabulary.size('insert'), 'insert',
                range(1, vocabulary.size('insert'))) for index in range(count)]
            return {'case': case, 'form': form, 'repair': repair, 'pointer': pointer, 'insert': inserted}
        program, result, trace = _run_graph(document, counts, choose, vocabulary)
        diagnostics['transitions'] = trace
        diagnostics['predicted_counts'] = counts
        return TagDecodeResult(True, program, result, (), diagnostics)
    except (EditorError, IndexError, TypeError) as error:
        return TagDecodeResult(False, None, None, (str(error),), diagnostics)
