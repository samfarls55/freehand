"""A bounded, executable copy/edit contract. This module makes no semantic claim.

Offsets are Python Unicode-string offsets, not UTF-8 bytes or native token IDs.
Protected spans are supplied by a caller; this module does not parse quotations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence
from types import MappingProxyType
import hashlib
import json
import re


class EditorError(ValueError):
    """Explicit invalid-program/unsupported-render error, never a clean fallback."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


CONTRACT_VERSION = "source-anchored-editor-v2"
# Finite grammatical/relation words are model-selected, including polarity and
# pronouns. Their role/meaning is NOT guaranteed by the executor. Names, number
# surfaces and arbitrary lexical replacements are still unavailable as literals.
FUNCTION_WORDS = frozenset({
    "a", "an", "the", "to", "of", "for", "in", "on", "at", "by", "with",
    "from", "as", "be", "am", "is", "are", "was", "were", "been", "being",
    "do", "does", "did", "have", "has", "had",
    "instead", "not", "but", "and", "after", "until", "rather", "than", "only",
    "still", "also", "then", "it", "them", "there",
})
PUNCTUATION = frozenset(".,!?;:()[]{}\"'“”‘’…—–-/")
CASE_MODES = frozenset({"keep", "lower", "upper", "initial_upper", "title"})
_NUMBER = r"(?:[+-]?[$€£]?|[$€£][+-]?)\d+(?:[.,:/-]\d+)*(?:[%°])?"
_WORD = r"(?:[^\W\d]|_)\w*(?:['’]\w+)*|\d+[^\W\d_]\w*(?:['’]\w+)*"
_TOKEN = re.compile(f"(?:{_WORD})|(?:{_NUMBER})|[^\\s]", re.UNICODE)
_IS_NUMBER = re.compile(f"(?:{_NUMBER})\\Z", re.UNICODE)
_IS_WORD = re.compile(f"(?:{_WORD})\\Z", re.UNICODE)
_SPACE = re.compile(r"[ \t\r\n]{1,8}\Z")


def _case(text: str, mode: str) -> str:
    if mode not in CASE_MODES:
        raise EditorError("invalid_case", f"Unknown case transform {mode!r}")
    if mode == "keep":
        return text
    if mode == "lower":
        return text.lower()
    if mode == "upper":
        return text.upper()
    if mode == "initial_upper":
        return text[:1].upper() + text[1:]
    return text[:1].upper() + text[1:].lower()


# Every group is finite. No arbitrary suffix/stem operation is available at
# execution time: an anchored source and requested output must share a group.
_IRREGULAR = (
    ("be", "am", "is", "are", "was", "were", "been", "being"),
    ("have", "has", "had", "having"), ("do", "does", "did", "done", "doing"),
    ("go", "goes", "went", "gone", "going"),
    ("send", "sends", "sent", "sending"), ("make", "makes", "made", "making"),
    ("say", "says", "said", "saying"), ("meet", "meets", "met", "meeting"),
    ("run", "runs", "ran", "running"), ("take", "takes", "took", "taken", "taking"),
    ("write", "writes", "wrote", "written", "writing"),
    ("leave", "leaves", "left", "leaving"), ("get", "gets", "got", "gotten", "getting"),
    ("set", "sets", "setting"), ("let", "lets", "letting"),
    ("put", "puts", "putting"), ("read", "reads", "reading"),
    ("know", "knows", "knew", "known", "knowing"),
    ("tell", "tells", "told", "telling"),
    ("keep", "keeps", "kept", "keeping"),
    ("show", "shows", "showed", "shown", "showing"),
    ("cancel", "cancels", "canceled", "cancelled", "canceling", "cancelling"),
    ("plan", "plans", "planned", "planning"),
    ("stop", "stops", "stopped", "stopping"),
    ("submit", "submits", "submitted", "submitting"),
    ("prefer", "prefers", "preferred", "preferring"),
    ("defer", "defers", "deferred", "deferring"),
    ("format", "formats", "formatted", "formatting"),
    ("label", "labels", "labeled", "labelled", "labeling", "labelling"),
    ("tag", "tags", "tagged", "tagging"),
    ("catalog", "catalogs", "cataloged", "cataloging", "catalogue", "catalogues", "catalogued", "cataloguing"),
)
_REGULAR_BASES = (
    "accept", "add", "adjust", "answer", "apply", "approve", "archive", "arrive",
    "ask", "assign", "attach", "book", "call", "change", "check", "clean", "close",
    "confirm", "contact", "copy", "correct", "create", "delay", "delete", "deliver",
    "describe", "discuss", "draft", "edit", "email", "enable", "expect", "explain",
    "finish", "fix", "follow", "include", "insert", "intend", "invite",
    "like", "link", "list", "look", "mention", "move", "need", "notify", "open",
    "order", "pause", "post", "prepare", "preserve", "process", "protect",
    "publish", "receive", "record", "release", "remember", "remove", "repeat",
    "replace", "reply", "report", "request", "resolve", "restore", "return", "review",
    "save", "schedule", "share", "sign", "start", "stay", "switch", "talk",
    "test", "thank", "try", "turn", "update", "use", "wait", "want", "work",
    "address", "route", "print", "place", "connect", "rename", "migrate", "convert",
    "compare", "manage", "match", "select", "sort", "group", "name",
    "reference", "retain", "carry", "describe", "identify", "handle",
)

_NOUN_PAIRS = (
    ("report", "reports"), ("label", "labels"), ("address", "addresses"),
    ("route", "routes"), ("tag", "tags"), ("file", "files"), ("name", "names"),
    ("number", "numbers"), ("request", "requests"), ("action", "actions"),
    ("check", "checks"), ("task", "tasks"), ("word", "words"), ("slot", "slots"),
    ("row", "rows"), ("change", "changes"), ("case", "cases"), ("test", "tests"),
    ("note", "notes"), ("message", "messages"), ("email", "emails"),
    ("owner", "owners"), ("meeting", "meetings"), ("invoice", "invoices"),
    ("ticket", "tickets"), ("document", "documents"), ("record", "records"),
    ("box", "boxes"), ("copy", "copies"), ("policy", "policies"),
    ("category", "categories"), ("city", "cities"), ("person", "people"),
    ("child", "children"),
)
MORPH_RULES = frozenset({"@possessive_s", "@possessive_apostrophe", "@unpossessive"})


def _regular_forms(base: str) -> frozenset[str]:
    if base.endswith("y") and base[-2:] not in {"ay", "ey", "iy", "oy", "uy"}:
        return frozenset((base, base[:-1] + "ies", base[:-1] + "ied", base + "ing"))
    plural = base + ("es" if base.endswith(("s", "x", "z", "ch", "sh")) else "s")
    past = base + ("d" if base.endswith("e") else "ed")
    ing = (base[:-1] if base.endswith("e") and not base.endswith("ee") else base) + "ing"
    return frozenset((base, plural, past, ing))


_PARADIGMS = tuple(frozenset(p) for p in (*_IRREGULAR, *_NOUN_PAIRS)) + tuple(
    _regular_forms(base) for base in _REGULAR_BASES
)
MORPH_FORMS: dict[str, frozenset[str]] = {}
for _group in _PARADIGMS:
    for _form in _group:
        MORPH_FORMS[_form] = MORPH_FORMS.get(_form, frozenset()) | _group
MORPH_FORMS = MappingProxyType(MORPH_FORMS)


def morphology_outputs(source_text: str) -> dict[str, str]:
    """Finite operation values -> anchored surface; never arbitrary replacement."""
    normalized = source_text.lower().replace("’", "'")
    output = {value: value for value in MORPH_FORMS.get(source_text.lower(), ())
        if value != source_text.lower()}
    if "'" not in normalized:
        output["@possessive_s"] = source_text + "'s"
        if normalized.endswith("s"):
            output["@possessive_apostrophe"] = source_text + "'"
    elif normalized.endswith("'s") and normalized[:-2] not in {
            "it", "he", "she", "there", "that", "here", "what", "who", "where", "when", "how", "let"}:
        output["@unpossessive"] = source_text[:-2]
    return output


def contract_metadata() -> dict[str, Any]:
    """Serializable immutable vocabulary description to freeze with trained heads."""
    value = {"version": CONTRACT_VERSION, "function_words": sorted(FUNCTION_WORDS),
        "punctuation": sorted(PUNCTUATION), "case_modes": sorted(CASE_MODES),
        "morph_forms": {key: sorted(values) for key, values in sorted(MORPH_FORMS.items())},
        "morph_rules": sorted(MORPH_RULES)}
    value["sha256"] = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    return value


@dataclass(frozen=True)
class ProtectedSpan:
    id: str
    start: int
    end: int


@dataclass(frozen=True)
class SourceAtom:
    index: int
    start: int
    end: int
    text: str
    kind: str  # word, number, punct, protected
    protected_id: str | None = None


@dataclass(frozen=True)
class SourceDocument:
    text: str
    atoms: tuple[SourceAtom, ...]
    protected_spans: tuple[ProtectedSpan, ...] = ()


def _validate_spans(text: str, spans: Sequence[ProtectedSpan]) -> tuple[ProtectedSpan, ...]:
    try:
        provided = tuple(spans)
    except TypeError:
        raise EditorError("invalid_protected_span", "Expected a sequence of ProtectedSpan values") from None
    if not all(isinstance(span, ProtectedSpan) for span in provided):
        raise EditorError("invalid_protected_span", "Expected typed ProtectedSpan values")
    if any(type(span.start) is not int or type(span.end) is not int for span in provided):
        raise EditorError("invalid_protected_span", "Protected offsets must be integer string offsets")
    ordered = tuple(sorted(provided, key=lambda s: (s.start, s.end)))
    ids: set[str] = set()
    previous_end = 0
    for span in ordered:
        if not isinstance(span.id, str) or not span.id or span.id in ids:
            raise EditorError("invalid_protected_id", "Protected IDs must be nonempty and unique")
        if (type(span.start) is not int or type(span.end) is not int
                or not 0 <= span.start < span.end <= len(text) or span.start < previous_end):
            raise EditorError("invalid_protected_span", "Protected spans must be in range and disjoint")
        ids.add(span.id)
        previous_end = span.end
    return ordered


def tokenize_source(text: str, protected_spans: Sequence[ProtectedSpan] = ()) -> SourceDocument:
    """Tokenize exact source offsets; protected spans are atomic, no quote parsing."""
    if not isinstance(text, str):
        raise EditorError("invalid_text", "Source must be a string")
    ordered = _validate_spans(text, protected_spans)
    atoms: list[SourceAtom] = []

    def scan(start: int, end: int) -> None:
        for match in _TOKEN.finditer(text, start, end):
            value = match.group()
            kind = "number" if _IS_NUMBER.fullmatch(value) else "word" if _IS_WORD.fullmatch(value) else "punct"
            atoms.append(SourceAtom(len(atoms), match.start(), match.end(), value, kind))

    position = 0
    for span in ordered:
        scan(position, span.start)
        atoms.append(SourceAtom(len(atoms), span.start, span.end, text[span.start:span.end], "protected", span.id))
        position = span.end
    scan(position, len(text))
    return SourceDocument(text, tuple(atoms), ordered)


@dataclass(frozen=True)
class Operation:
    kind: str
    source_index: int | None = None
    value: str | None = None
    case: str = "keep"


@dataclass(frozen=True)
class Program:
    operations: tuple[Operation, ...]
    schema_version: int = 1
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        operations = []
        for op in self.operations:
            row: dict[str, Any] = {"kind": op.kind}
            if op.source_index is not None:
                row["source_index"] = op.source_index
            if op.value is not None:
                row["value"] = op.value
            if op.case != "keep":
                row["case"] = op.case
            operations.append(row)
        return {"schema_version": self.schema_version, "contract_version": self.contract_version, "operations": operations}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Program":
        if (not isinstance(value, Mapping) or set(value) != {"schema_version", "contract_version", "operations"}
                or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or value["contract_version"] != CONTRACT_VERSION):
            raise EditorError("invalid_program", "Expected schema1, the current vocabulary contract, and operations only")
        rows = value["operations"]
        if not isinstance(rows, list):
            raise EditorError("invalid_program", "operations must be an array")
        result = []
        for row in rows:
            if not isinstance(row, Mapping) or not {"kind"} <= set(row) <= {"kind", "source_index", "value", "case"}:
                raise EditorError("invalid_operation", "Unknown/missing operation fields")
            result.append(Operation(**row))
        return cls(tuple(result))


@dataclass(frozen=True)
class TraceStep:
    operation_index: int | None
    kind: str
    source_index: int | None
    source_start: int | None
    source_end: int | None
    output_start: int
    output_end: int
    text: str
    protected_id: str | None = None
    case: str = "keep"
    implicit: bool = False
    value: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    text: str
    trace: tuple[TraceStep, ...]
    deleted_atom_indices: tuple[int, ...]
    reused_atom_indices: tuple[int, ...]
    protected_ids: tuple[str, ...]


def _get_atom(document: SourceDocument, index: int | None) -> SourceAtom:
    if type(index) is not int or not 0 <= index < len(document.atoms):
        raise EditorError("invalid_pointer", f"Source atom pointer {index!r} is out of range")
    return document.atoms[index]


def _emit(document: SourceDocument, op: Operation) -> tuple[str, SourceAtom | None]:
    if not isinstance(op, Operation) or not isinstance(op.kind, str):
        raise EditorError("invalid_operation", "Expected a typed operation")
    if not isinstance(op.case, str) or op.case not in CASE_MODES:
        raise EditorError("invalid_case", f"Unknown case transform {op.case!r}")
    if op.value is not None and not isinstance(op.value, str):
        raise EditorError("invalid_operation", "Operation values must be strings or null")
    if op.kind in {"copy", "morph", "delete"}:
        atom = _get_atom(document, op.source_index)
        if op.kind == "delete":
            if atom.kind == "protected":
                raise EditorError("protected_delete", f"Cannot delete {atom.protected_id}")
            if op.value is not None or op.case != "keep":
                raise EditorError("invalid_operation", "delete accepts only a source pointer")
            return "", atom
        if op.kind == "copy":
            if op.value is not None:
                raise EditorError("invalid_operation", "copy cannot contain literal replacement text")
            if atom.kind != "word" and op.case != "keep":
                raise EditorError("invalid_case", "Only unprotected words may change case")
            return _case(atom.text, op.case), atom
        if atom.kind != "word" or not isinstance(op.value, str):
            raise EditorError("invalid_morph", "Morphology needs an unprotected word and finite form")
        forms = morphology_outputs(atom.text)
        if op.value not in forms:
            raise EditorError("invalid_morph", f"No finite anchored form {op.value!r} for {atom.text!r}")
        return _case(forms[op.value], op.case), atom
    if op.source_index is not None:
        raise EditorError("invalid_operation", f"{op.kind} cannot carry a source pointer")
    if op.kind == "function":
        if op.value not in FUNCTION_WORDS:
            raise EditorError("content_invention", f"Word {op.value!r} is not an insertable function word")
        return _case(op.value, op.case), None
    if op.kind == "punct":
        if op.value not in PUNCTUATION or op.case != "keep":
            raise EditorError("invalid_punctuation", f"Unsupported punctuation {op.value!r}")
        return op.value, None
    if op.kind == "space":
        if not isinstance(op.value, str) or not _SPACE.fullmatch(op.value) or op.case != "keep":
            raise EditorError("invalid_spacing", "Whitespace must contain 1–8 plain spacing characters")
        return op.value, None
    raise EditorError("unknown_operation", f"Unknown operation {op.kind!r}")


def execute(document: SourceDocument, program: Program, *, max_operations: int = 4096,
            max_output_characters: int = 100000, max_function_insertions: int = 32) -> ExecutionResult:
    """Validate and execute, or raise EditorError. No fallback is scored as clean."""
    if not isinstance(document, SourceDocument) or tokenize_source(document.text, document.protected_spans) != document:
        raise EditorError("invalid_document", "SourceDocument must match canonical source tokenization")
    if (not isinstance(program, Program) or type(program.schema_version) is not int or program.schema_version != 1
            or program.contract_version != CONTRACT_VERSION or not isinstance(program.operations, tuple)):
        raise EditorError("invalid_program", "Unsupported program schema")
    if len(program.operations) > max_operations:
        raise EditorError("operation_budget", "Program exceeds the explicit operation budget")
    chunks: list[str] = []
    trace: list[TraceStep] = []
    used: dict[int, int] = {}
    explicitly_deleted: set[int] = set()
    protected_ids: list[str] = []
    output_protected: list[ProtectedSpan] = []
    offset = 0
    inserted_functions = 0
    for op_index, op in enumerate(program.operations):
        text, atom = _emit(document, op)
        if op.kind == "delete":
            if atom.index in explicitly_deleted:
                raise EditorError("duplicate_delete", "A source atom cannot be explicitly deleted twice")
            explicitly_deleted.add(atom.index)
        else:
            if atom is not None:
                used[atom.index] = used.get(atom.index, 0) + 1
            if op.kind == "function":
                inserted_functions += 1
                if inserted_functions > max_function_insertions:
                    raise EditorError("insertion_budget", "Too many function-word insertions")
        if offset + len(text) > max_output_characters:
            raise EditorError("output_budget", "Program exceeds the explicit character budget")
        if atom is not None and atom.protected_id is not None:
            protected_ids.append(atom.protected_id)
            output_protected.append(ProtectedSpan(atom.protected_id, offset, offset + len(text)))
        trace.append(TraceStep(op_index, op.kind, atom.index if atom else None,
            atom.start if atom else None, atom.end if atom else None, offset, offset + len(text), text,
            atom.protected_id if atom else None, op.case, value=op.value))
        chunks.append(text)
        offset += len(text)
    if explicitly_deleted & set(used):
        raise EditorError("contradictory_delete", "A source atom is both copied and explicitly deleted")
    expected_ids = tuple(span.id for span in document.protected_spans)
    if tuple(protected_ids) != expected_ids:
        raise EditorError("protected_contract", f"Expected protected IDs exactly once/in source order: {expected_ids!r}; got {tuple(protected_ids)!r}")
    output = "".join(chunks)
    if not output or output != output.strip():
        raise EditorError("invalid_output", "Output must be nonempty and have no edge whitespace")
    # Exact payload bytes alone do not prevent appending a suffix/name/number
    # across a protected boundary (Ada + Bob -> AdaBob, Ada + 's -> Ada's).
    # Reject a lexical token that straddles either edge of a protected atom.
    for atom in tokenize_source(output).atoms:
        if atom.kind in {"word", "number"}:
            for span in output_protected:
                overlaps = atom.start < span.end and atom.end > span.start
                contained = span.start <= atom.start and atom.end <= span.end
                if overlaps and not contained:
                    raise EditorError("protected_boundary_merge", "A lexical surface crosses a protected payload boundary")
    # A program must not manufacture a new word or numeric surface by joining
    # independently copied fragments and punctuation. Each unprotected lexical
    # output atom must come wholly from one copy/morph/function operation.
    rendered = tokenize_source(output, output_protected)
    emitted_lexical = {(step.output_start, step.output_end): step for step in trace
        if step.kind in {"copy", "morph", "function"} and step.text}
    for atom in rendered.atoms:
        if atom.kind in {"word", "number"}:
            step = emitted_lexical.get((atom.start, atom.end))
            if step is None:
                step = next((candidate for candidate in trace if candidate.kind == "morph"
                    and candidate.output_start <= atom.start and atom.end <= candidate.output_end), None)
            if step is None:
                raise EditorError("unanchored_lexical_surface", f"Output lexical surface {atom.text!r} was assembled from fragments")
            if atom.kind == "number":
                source = _get_atom(document, step.source_index)
                if step.kind != "copy" or source.kind != "number" or atom.text != source.text:
                    raise EditorError("unanchored_number", "Every numeric surface must be an exact source-number copy")
    deleted = tuple(atom.index for atom in document.atoms if atom.index not in used)
    for index in deleted:
        if index not in explicitly_deleted:
            atom = document.atoms[index]
            trace.append(TraceStep(None, "delete", index, atom.start, atom.end, offset, offset, "", None, "keep", True))
    return ExecutionResult(output, tuple(trace), deleted,
        tuple(sorted(index for index, count in used.items() if count > 1)), tuple(protected_ids))


@dataclass(frozen=True)
class AlignmentResult:
    supported: bool
    program: Program | None
    reasons: tuple[str, ...] = ()
    strategy: str = "source-position-dp-v1"
    normalized_alignment_alternatives_cap2: int = 0


def _infer_target_spans(document: SourceDocument, target: str) -> tuple[ProtectedSpan, ...]:
    """Conservative convenience only; callers may supply explicit gold spans."""
    spans = document.protected_spans
    if not spans:
        return ()
    values = [document.text[span.start:span.end] for span in spans]
    # A protected string contained in another creates ambiguous string-only
    # annotation. Require caller-supplied target spans rather than guess.
    for i, value in enumerate(values):
        if any(i != j and value != other and value in other for j, other in enumerate(values)):
            raise EditorError("ambiguous_target_protection", "Overlapping protected payloads need explicit target spans")
    for value in set(values):
        if target.count(value) != values.count(value):
            raise EditorError("target_protected_count", f"Gold protected payload {value!r} is missing/duplicated or ambiguous")
    position = 0
    output = []
    for span, value in zip(spans, values):
        found = target.find(value, position)
        if found < 0:
            raise EditorError("target_protected_order", "Gold does not retain protected source order")
        output.append(ProtectedSpan(span.id, found, found + len(value)))
        position = found + len(value)
    return tuple(output)


def _candidate_operations(document: SourceDocument, target: SourceAtom) -> list[Operation]:
    choices: list[Operation] = []
    for source in document.atoms:
        if target.kind == "protected":
            if source.protected_id == target.protected_id and source.text == target.text:
                choices.append(Operation("copy", source.index))
            continue
        if source.kind == "protected":
            continue
        if source.kind == target.kind:
            for mode in ("keep", "initial_upper", "lower", "upper", "title") if source.kind == "word" else ("keep",):
                if _case(source.text, mode) == target.text:
                    choices.append(Operation("copy", source.index, case=mode))
                    break
        if source.kind == target.kind == "word":
            for value, surface in sorted(morphology_outputs(source.text).items()):
                for mode in ("keep", "initial_upper", "lower", "upper", "title"):
                    if _case(surface, mode) == target.text:
                        choices.append(Operation("morph", source.index, value, mode))
                        break
    if target.kind == "word":
        value = target.text.lower()
        if value in FUNCTION_WORDS:
            for mode in ("keep", "initial_upper", "upper", "title"):
                if _case(value, mode) == target.text:
                    choices.append(Operation("function", value=value, case=mode))
                    break
    if target.kind == "punct" and target.text in PUNCTUATION:
        choices.append(Operation("punct", value=target.text))
    return choices


def align_gold(document: SourceDocument, target: str, *,
               target_protected_spans: Sequence[ProtectedSpan] | None = None) -> AlignmentResult:
    """Find a deterministic executable gold program, or label it unsupported.

    This is representability of the exact supplied target, not semantic success.
    DP minimizes insertions, morphology, case changes, backwards/reused pointers,
    pointer jumps, then index sums. It is not a unique linguistic alignment.
    """
    try:
        if not isinstance(target, str):
            raise EditorError("invalid_text", "Target must be a string")
        spans = (_infer_target_spans(document, target) if target_protected_spans is None
                 else tuple(target_protected_spans))
        target_doc = tokenize_source(target, spans)
        expected = {span.id: document.text[span.start:span.end] for span in document.protected_spans}
        if tuple(span.id for span in target_doc.protected_spans) != tuple(span.id for span in document.protected_spans):
            raise EditorError("target_protected_order", "Explicit target IDs must be exactly once and source ordered")
        for span in target_doc.protected_spans:
            if target[span.start:span.end] != expected[span.id]:
                raise EditorError("target_protected_mutation", "Explicit target protected payload changed")
        # State is previous source pointer, not a used-word inventory: reuse is
        # intentionally expressible. Keep at most one minimum-score path/state.
        states: dict[int, tuple[tuple[int, ...], tuple[Operation, ...], int]] = {
            -1: ((0, 0, 0, 0, 0, 0), (), 1)
        }
        cursor = 0
        for atom in target_doc.atoms:
            gap = target[cursor:atom.start]
            if gap and not _SPACE.fullmatch(gap):
                raise EditorError("unsupported_spacing", "Gold spacing is outside the bounded contract")
            candidates = _candidate_operations(document, atom)
            if not candidates:
                raise EditorError("unsupported_target_atom", f"No anchored/finite operation for {atom.text!r} at target offset {atom.start}")
            next_states: dict[int, tuple[tuple[int, ...], tuple[Operation, ...], int]] = {}
            for previous, (score, path, count) in states.items():
                for op in candidates:
                    index = op.source_index
                    state = previous if index is None else index
                    delta = (int(op.kind == "function"), int(op.kind == "morph"),
                        int(op.case != "keep"), int(index is not None and index <= previous),
                        abs(index - previous - 1) if index is not None else 0,
                        index if index is not None else 0)
                    new_score = tuple(a + b for a, b in zip(score, delta))
                    new_path = path + ((Operation("space", value=gap),) if gap else ()) + (op,)
                    existing = next_states.get(state)
                    if existing is None or new_score < existing[0]:
                        next_states[state] = (new_score, new_path, count)
                    elif new_score == existing[0]:
                        next_states[state] = (existing[0], existing[1], min(2, existing[2] + count))
            states = next_states
            cursor = atom.end
        if cursor != len(target):
            raise EditorError("unsupported_spacing", "Gold has trailing whitespace")
        if not states:
            raise EditorError("unsupported_target", "No target program")
        best_score = min(state[0] for state in states.values())
        winners = [state for state in states.values() if state[0] == best_score]
        program = Program(winners[0][1])
        result = execute(document, program)
        if result.text != target:
            raise EditorError("alignment_render_mismatch", "Gold program did not reconstruct exact target")
        return AlignmentResult(True, program, normalized_alignment_alternatives_cap2=min(2, sum(s[2] for s in winners)))
    except EditorError as error:
        return AlignmentResult(False, None, (str(error),))
