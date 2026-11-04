"""Stdlib labels and constrained search for the parallel slot head.

No Torch import occurs here. Scores are ordinary nested lists of logits;
model inference/training and feature extraction are separate responsibilities.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
import hashlib
import json
import math
from functools import cached_property, lru_cache

from .core import (
    CASE_MODES, CONTRACT_VERSION, FUNCTION_WORDS, MORPH_FORMS, MORPH_RULES,
    PUNCTUATION, AlignmentResult, EditorError, ExecutionResult, Operation,
    Program, ProtectedSpan, SourceDocument, _emit, align_gold, contract_metadata,
    execute, morphology_outputs,
)


IGNORE_INDEX = -100
HEAD_KEYS = ("length", "kind", "pointer", "case", "morph", "function", "punct", "space")


@dataclass(frozen=True)
class HeadVocabulary:
    contract_version: str
    contract_sha256: str
    kinds: tuple[str, ...]
    cases: tuple[str, ...]
    morph_values: tuple[str, ...]
    function_values: tuple[str, ...]
    punct_values: tuple[str, ...]
    space_values: tuple[str, ...]

    @classmethod
    @lru_cache(maxsize=1)
    def current(cls) -> "HeadVocabulary":
        metadata = contract_metadata()
        return cls(CONTRACT_VERSION, metadata["sha256"],
            ("copy", "morph", "function", "punct", "space"),
            ("keep", "lower", "upper", "initial_upper", "title"),
            tuple(sorted(set(MORPH_FORMS) | set(MORPH_RULES))),
            tuple(sorted(FUNCTION_WORDS)), tuple(sorted(PUNCTUATION)),
            (" ", "  ", "\t", "\n", "\n\n", "\r\n", "\r\n\r\n"))

    def to_dict(self) -> dict[str, Any]:
        return {"contract_version": self.contract_version, "contract_sha256": self.contract_sha256,
            "kinds": list(self.kinds), "cases": list(self.cases),
            "morph_values": list(self.morph_values), "function_values": list(self.function_values),
            "punct_values": list(self.punct_values), "space_values": list(self.space_values)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HeadVocabulary":
        if not isinstance(value, Mapping) or set(value) != set(cls.current().to_dict()):
            raise EditorError("invalid_vocabulary", "Malformed frozen head vocabulary")
        try:
            result = cls(value["contract_version"], value["contract_sha256"],
                *(tuple(value[key]) for key in ("kinds", "cases", "morph_values", "function_values", "punct_values", "space_values")))
        except (KeyError, TypeError) as error:
            raise EditorError("invalid_vocabulary", "Malformed frozen head vocabulary") from error
        if result != cls.current():
            raise EditorError("vocabulary_mismatch", "Head vocabulary differs from the current reviewed contract")
        return result

    @cached_property
    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False,
            separators=(",", ":")).encode("utf-8")).hexdigest()

    def size(self, name: str) -> int:
        return len(self.kinds if name == "kind" else self.cases if name == "case" else getattr(self, name + "_values"))


@dataclass(frozen=True)
class EncodedProgram:
    supported: bool
    length: int | None
    labels: Mapping[str, tuple[int, ...]]
    reasons: tuple[str, ...]
    vocabulary_sha256: str
    program: Program | None = None


def encode_program(document: SourceDocument, program: Program, *, max_ops: int = 256,
                   max_source_atoms: int = 512, vocabulary: HeadVocabulary | None = None) -> EncodedProgram:
    """Encode exact emission-slot supervision; unsupported stays explicit.

    Each label array has max_ops entries, padded by -100. Pointer/case/value
    heads use -100 outside their applicable kinds. Length is a separate class.
    Deletion is implicit in the emission program and has no output slot.
    """
    vocabulary = vocabulary or HeadVocabulary.current()
    try:
        HeadVocabulary.from_dict(vocabulary.to_dict())
        if not document.atoms:
            raise EditorError("empty_source", "Head labels require at least one source feature atom")
        original = execute(document, program)
        operations = tuple(op for op in program.operations if op.kind != "delete")
        emission_program = Program(operations)
        if execute(document, emission_program).text != original.text:
            raise EditorError("delete_render_mismatch", "Removing zero-output delete instructions changed the render")
        if len(document.atoms) > max_source_atoms:
            raise EditorError("source_slot_capacity", "Source exceeds configured feature slots")
        if not 1 <= len(operations) <= max_ops:
            raise EditorError("output_slot_capacity", "Program exceeds configured emission slots")
        labels = {name: [IGNORE_INDEX] * max_ops for name in HEAD_KEYS if name != "length"}
        for slot, op in enumerate(operations):
            if op.kind not in vocabulary.kinds:
                raise EditorError("unsupported_head_kind", f"Head cannot emit {op.kind!r}")
            labels["kind"][slot] = vocabulary.kinds.index(op.kind)
            if op.kind in {"copy", "morph"}:
                labels["pointer"][slot] = op.source_index
            if op.kind in {"copy", "morph", "function"}:
                labels["case"][slot] = vocabulary.cases.index(op.case)
            if op.kind in {"morph", "function", "punct", "space"}:
                values = getattr(vocabulary, op.kind + "_values")
                if op.value not in values:
                    raise EditorError("unsupported_head_value", f"No finite {op.kind} class for {op.value!r}")
                labels[op.kind][slot] = values.index(op.value)
        return EncodedProgram(True, len(operations), {key: tuple(value) for key, value in labels.items()},
            (), vocabulary.sha256, emission_program)
    except EditorError as error:
        return EncodedProgram(False, None, {}, (str(error),), vocabulary.sha256)


def build_training_label(document: SourceDocument, target: str, *,
                         target_protected_spans: Sequence[ProtectedSpan] | None = None,
                         max_ops: int = 256, max_source_atoms: int = 512,
                         vocabulary: HeadVocabulary | None = None) -> EncodedProgram:
    vocabulary = vocabulary or HeadVocabulary.current()
    if not document.atoms:
        return EncodedProgram(False, None, {},
            ("empty_source: Head labels require at least one source feature atom",), vocabulary.sha256)
    alignment = align_gold(document, target, target_protected_spans=target_protected_spans)
    if not alignment.supported:
        return EncodedProgram(False, None, {}, alignment.reasons, vocabulary.sha256)
    return encode_program(document, alignment.program, max_ops=max_ops,
        max_source_atoms=max_source_atoms, vocabulary=vocabulary)


@dataclass(frozen=True)
class HeadDecodeResult:
    accepted: bool
    program: Program | None
    execution: ExecutionResult | None
    reasons: tuple[str, ...]
    diagnostics: Mapping[str, Any]


def _log_probs(values: Sequence[float], expected: int, name: str) -> tuple[float, ...]:
    if not isinstance(values, (list, tuple)) or len(values) != expected:
        raise EditorError("score_shape", f"{name} expected {expected} scores")
    try:
        numbers = tuple(float(value) for value in values)
    except (TypeError, ValueError, OverflowError) as error:
        raise EditorError("invalid_score", f"Non-numeric {name} score") from error
    if any(math.isnan(value) or value == math.inf for value in numbers) or all(value == -math.inf for value in numbers):
        raise EditorError("invalid_score", f"Non-finite/all-masked {name} scores")
    maximum = max(numbers)
    denominator = maximum + math.log(sum(math.exp(value - maximum) for value in numbers))
    return tuple(value - denominator for value in numbers)


def _top(values: Sequence[float], count: int, allowed: Sequence[int] | None = None) -> list[int]:
    indices = range(len(values)) if allowed is None else allowed
    return sorted((index for index in indices if values[index] > -math.inf), key=lambda index: (-values[index], index))[:count]


def _slot_candidates(document: SourceDocument, slot: Mapping[str, tuple[float, ...]],
                     vocabulary: HeadVocabulary, protected_cursor: int, protected_indices: tuple[int, ...],
                     *, kind_candidates: int, pointer_candidates: int, value_candidates: int,
                     case_candidates: int) -> list[tuple[float, Operation]]:
    candidates: dict[tuple[Any, ...], tuple[float, Operation]] = {}
    kinds = _top(slot["kind"], kind_candidates)
    if protected_cursor < len(protected_indices):
        copy_kind = vocabulary.kinds.index("copy")
        if copy_kind not in kinds:
            kinds.append(copy_kind)
    for kind_id in kinds:
        kind = vocabulary.kinds[kind_id]
        kind_score = slot["kind"][kind_id]
        if kind in {"copy", "morph"}:
            pointers = _top(slot["pointer"], pointer_candidates)
            if kind == "copy" and protected_cursor < len(protected_indices):
                required = protected_indices[protected_cursor]
                if required not in pointers:
                    pointers.append(required)
            for pointer in pointers:
                atom = document.atoms[pointer]
                if atom.kind == "protected" and (kind != "copy" or protected_cursor >= len(protected_indices)
                        or pointer != protected_indices[protected_cursor]):
                    continue
                if kind == "morph" and atom.kind != "word":
                    continue
                cases = _top(slot["case"], case_candidates) if atom.kind == "word" else [vocabulary.cases.index("keep")]
                values: list[str | None] = [None]
                if kind == "morph":
                    available = morphology_outputs(atom.text)
                    allowed = [i for i, value in enumerate(vocabulary.morph_values) if value in available]
                    values = [vocabulary.morph_values[i] for i in _top(slot["morph"], value_candidates, allowed)]
                for case_id in cases:
                    for value in values:
                        operation = Operation(kind, pointer, value, vocabulary.cases[case_id])
                        score = kind_score + slot["pointer"][pointer] + slot["case"][case_id]
                        if value is not None:
                            score += slot["morph"][vocabulary.morph_values.index(value)]
                        if score == -math.inf:
                            continue
                        try:
                            text, _ = _emit(document, operation)
                        except EditorError:
                            continue
                        key = (kind, pointer, value, text)
                        if key not in candidates or score > candidates[key][0]:
                            candidates[key] = (score, operation)
        elif kind in {"function", "punct", "space"}:
            values = getattr(vocabulary, kind + "_values")
            for value_id in _top(slot[kind], value_candidates):
                cases = _top(slot["case"], case_candidates) if kind == "function" else [vocabulary.cases.index("keep")]
                for case_id in cases:
                    operation = Operation(kind, value=values[value_id], case=vocabulary.cases[case_id])
                    score = kind_score + slot[kind][value_id]
                    if kind == "function":
                        score += slot["case"][case_id]
                    text, _ = _emit(document, operation)
                    key = (kind, None, values[value_id], text)
                    if key not in candidates or score > candidates[key][0]:
                        candidates[key] = (score, operation)
    return sorted(candidates.values(), key=lambda item: -item[0])


def decode_parallel_scores(document: SourceDocument, scores: Mapping[str, Any], *, max_ops: int = 256,
                           vocabulary: HeadVocabulary | None = None, beam_width: int = 8,
                           length_candidates: int = 3, kind_candidates: int = 3,
                           pointer_candidates: int = 4, value_candidates: int = 3,
                           case_candidates: int = 2) -> HeadDecodeResult:
    """Constrained ordered-protection beam; never emits arbitrary text/fallback.

    This search can explicitly reject a representable output when top-k/beam
    pruning misses it. Protected assignment constrains identities, not semantics.
    """
    vocabulary = vocabulary or HeadVocabulary.current()
    diagnostics: dict[str, Any] = {"vocabulary_sha256": vocabulary.sha256, "beam_width": beam_width,
        "protected_assignment": "ordered-cursor-with-required-candidate-injection",
        "fallback_success_credit": False}
    try:
        HeadVocabulary.from_dict(vocabulary.to_dict())
        if min(max_ops, beam_width, length_candidates, kind_candidates, pointer_candidates, value_candidates, case_candidates) < 1:
            raise EditorError("invalid_search_config", "Search capacities must be positive")
        if not document.atoms:
            raise EditorError("empty_source", "No source feature rows")
        if not isinstance(scores, Mapping) or set(scores) != set(HEAD_KEYS):
            raise EditorError("score_shape", "Expected only the eight parallel score heads")
        length_scores = _log_probs(scores["length"], max_ops + 1, "length")
        normalized: dict[str, list[tuple[float, ...]]] = {}
        for name in HEAD_KEYS[1:]:
            rows = scores[name]
            if not isinstance(rows, (list, tuple)) or len(rows) != max_ops:
                raise EditorError("score_shape", f"{name} must have max_ops rows")
            width = len(document.atoms) if name == "pointer" else vocabulary.size(name)
            normalized[name] = [_log_probs(row, width, name) for row in rows]
        protected_indices = tuple(atom.index for atom in document.atoms if atom.kind == "protected")
        lengths = _top(length_scores, length_candidates)
        failures: Counter[str] = Counter()
        accepted: list[tuple[float, Program, ExecutionResult]] = []
        attempted = []
        for length in lengths:
            if length == 0:
                failures["zero_length_prediction"] += 1
                continue
            if length < len(protected_indices):
                failures["protected_slot_capacity"] += 1
                continue
            attempted.append(length)
            # score, operations, ordered-protected cursor, function insertion count
            beam: list[tuple[float, tuple[Operation, ...], int, int]] = [(length_scores[length], (), 0, 0)]
            for position in range(length):
                next_beam = []
                slot = {name: normalized[name][position] for name in HEAD_KEYS[1:]}
                for score, operations, cursor, inserted in beam:
                    choices = _slot_candidates(document, slot, vocabulary, cursor, protected_indices,
                        kind_candidates=kind_candidates, pointer_candidates=pointer_candidates,
                        value_candidates=value_candidates, case_candidates=case_candidates)
                    for delta, operation in choices:
                        if operation.kind == "space" and (position == 0 or position == length - 1
                                or (operations and operations[-1].kind == "space")):
                            continue
                        next_cursor = cursor
                        if operation.kind == "copy" and document.atoms[operation.source_index].kind == "protected":
                            next_cursor += 1
                        if len(protected_indices) - next_cursor > length - position - 1:
                            continue
                        next_inserted = inserted + int(operation.kind == "function")
                        if next_inserted > 32:
                            continue
                        next_beam.append((score + delta, operations + (operation,), next_cursor, next_inserted))
                beam = sorted(next_beam, key=lambda item: -item[0])[:beam_width]
                if not beam:
                    failures["no_feasible_prefix"] += 1
                    break
            for score, operations, cursor, _ in beam:
                if cursor != len(protected_indices):
                    failures["protected_contract"] += 1
                    continue
                program = Program(operations)
                try:
                    result = execute(document, program)
                    accepted.append((score, program, result))
                except EditorError as error:
                    failures[error.code] += 1
        diagnostics["attempted_lengths"] = attempted
        diagnostics["rejected_candidate_counts"] = dict(failures)
        diagnostics["accepted_search_candidates"] = len(accepted)
        if not accepted:
            return HeadDecodeResult(False, None, None, ("constrained_decode_rejected: No executable candidate survived bounded search",), diagnostics)
        score, program, result = max(accepted, key=lambda item: item[0])
        diagnostics["joint_log_score"] = score
        diagnostics["selected_length"] = len(program.operations)
        return HeadDecodeResult(True, program, result, (), diagnostics)
    except EditorError as error:
        return HeadDecodeResult(False, None, None, (str(error),), diagnostics)
