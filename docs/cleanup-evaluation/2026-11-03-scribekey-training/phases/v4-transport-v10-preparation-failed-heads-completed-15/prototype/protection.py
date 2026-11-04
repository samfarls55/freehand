"""Adapter to the separately owned literal protocol. No quote parser lives here."""
from __future__ import annotations

from dataclasses import dataclass
import builtins
import hashlib
from pathlib import Path
import sys
import types
from typing import Any

from editor_core import EditorError, ProtectedSpan, SourceAtom, SourceDocument, tokenize_source

ROOT = Path('/workspace/freehand')
HELPER = ROOT / 'tools/Freehand.Cleanup.Evaluation/specialist_literal_protection.py'
PROTOCOL = 'specialist-compact-v4'
DEPENDENCY_SHA256 = {
    'literal_protection': '5f70868a4cfe6ae59d9eb56faefcb5aef3a050fb214f8bf40d98e33cb19309dc',
    'specialist_literal_word_ranges': '8d3e4b053be74326530914610c5e592d8a00d5870eba68a65da403845b70c42e',
}


class ProtectionError(EditorError):
    """An unsupported source/target contract, never an implicit target repair."""

    def __init__(self, message: str):
        super().__init__('literal_protection', message)


@dataclass(frozen=True)
class LiteralInterval:
    id: str
    payload: str
    raw_start: int
    raw_end: int
    model_start: int
    model_end: int


@dataclass(frozen=True)
class ProtectedInput:
    raw_source: str
    model_text: str
    literals: tuple[LiteralInterval, ...]
    document: SourceDocument
    protocol: str
    helper_sha256: str

    def model_interval(self, atom: SourceAtom) -> tuple[int, int]:
        if atom.protected_id is not None:
            literal = next(item for item in self.literals if item.id == atom.protected_id)
            if (atom.start, atom.end) != (literal.raw_start, literal.raw_end):
                raise ProtectionError('Protected atom boundaries changed')
            return literal.model_start, literal.model_end
        shift = sum((item.model_end - item.model_start) - (item.raw_end - item.raw_start)
            for item in self.literals if item.raw_end <= atom.start)
        start, end = atom.start + shift, atom.end + shift
        if self.model_text[start:end] != atom.text:
            raise ProtectionError('Raw/model ordinary-atom offset mapping failed')
        return start, end

    def mask_target(self, target: str) -> tuple[str, tuple[ProtectedSpan, ...]]:
        """Require the complete raw payload inventory in source order, including repeats."""
        at, pieces, spans = 0, [], []
        for item in self.literals:
            found = target.find(item.payload, at)
            if found < 0:
                raise ProtectionError('Target changes protected-payload order')
            pieces.extend((target[at:found], item.id))
            spans.append(ProtectedSpan(item.id, found, found + len(item.payload)))
            at = found + len(item.payload)
        pieces.append(target[at:])
        # A payload can occur inside another opaque payload. Count selected
        # disjoint spans, not raw substring occurrences hidden inside them.
        ordinary = []
        previous = 0
        for span in spans:
            ordinary.append(target[previous:span.start])
            previous = span.end
        ordinary.append(target[previous:])
        if any(item.payload in part for item in self.literals for part in ordinary):
            raise ProtectionError('Target duplicates a protected payload outside its inventory')
        return ''.join(pieces), tuple(spans)


def _bookends(source: str, masked: str, tokens: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    digest = hashlib.sha256(source.encode()).hexdigest()[:20]
    for attempt in range(128):
        pairs = tuple((f'\ue000COPYEDIT_{digest}_{attempt}_{ordinal}_OPEN\ue001',
                       f'\ue000COPYEDIT_{digest}_{attempt}_{ordinal}_CLOSE\ue001')
            for ordinal in range(len(tokens)))
        if all(opening not in source and closing not in source and opening not in masked and closing not in masked
               for opening, closing in pairs):
            return pairs
    raise ProtectionError('Cannot choose collision-free private bookends')


def from_public_mask(source: str, mask: Any, helper_sha256: str, protocol: str = PROTOCOL) -> ProtectedInput:
    """Use one complete decorated restore, including intermediate dictionary inventory."""
    model_text = mask.masked_text
    tokens = tuple(mask.tokens)
    if len(tokens) != len(set(tokens)) or any(model_text.count(token) != 1 for token in tokens):
        raise ProtectionError('Public mask token inventory is not unique/exact')
    ends = _bookends(source, model_text, tokens)
    decorated = model_text
    for token, (opening, closing) in zip(tokens, ends):
        decorated = decorated.replace(token, opening + token + closing, 1)
    try:
        expanded = mask.restore(decorated)
    except Exception as exc:
        raise ProtectionError('Complete decorated literal restoration failed') from exc
    raw_parts, intervals = [], []
    at = raw_length = 0
    for token, (opening, closing) in zip(tokens, ends):
        begin = expanded.find(opening, at)
        if begin < 0 or expanded.count(opening) != 1 or expanded.count(closing) != 1:
            raise ProtectionError('Decorated literal marker lost/duplicated')
        end = expanded.find(closing, begin + len(opening))
        if end < 0:
            raise ProtectionError('Decorated literal marker reordered')
        ordinary = expanded[at:begin]
        payload = expanded[begin + len(opening):end]
        if not payload:
            raise ProtectionError('Empty protected payload')
        raw_parts.extend((ordinary, payload))
        start = raw_length + len(ordinary)
        raw_length = start + len(payload)
        model_start = model_text.find(token)
        intervals.append(LiteralInterval(token, payload, start, raw_length, model_start, model_start + len(token)))
        at = end + len(closing)
    raw_parts.append(expanded[at:])
    if ''.join(raw_parts) != source:
        raise ProtectionError('Decorated restoration did not reproduce exact original source')
    if [item.model_start for item in intervals] != sorted(item.model_start for item in intervals):
        raise ProtectionError('Model tokens are not in source order')
    spans = tuple(ProtectedSpan(item.id, item.raw_start, item.raw_end) for item in intervals)
    document = tokenize_source(source, spans)
    result = ProtectedInput(source, model_text, tuple(intervals), document, protocol, helper_sha256)
    for atom in document.atoms:
        result.model_interval(atom)
    return result


class HeldProtector:
    """Requires the quote owner's frozen helper pin before real corpus use."""

    def __init__(self, expected_helper_sha256: str, protocol: str = PROTOCOL,
                 expected_dependency_sha256: dict[str, str] | None = None):
        if protocol != PROTOCOL:
            raise ProtectionError('Prototype must explicitly opt into held compact-v4')
        dependencies = dict(DEPENDENCY_SHA256 if expected_dependency_sha256 is None else expected_dependency_sha256)
        if set(dependencies) != set(DEPENDENCY_SHA256):
            raise ProtectionError('The complete explicit literal dependency inventory is required')
        paths = {'specialist_literal_protection': HELPER,
            **{name: HELPER.with_name(name + '.py') for name in dependencies}}
        expected = {'specialist_literal_protection': expected_helper_sha256, **dependencies}
        sources = {}
        for name, path in paths.items():
            data = path.read_bytes()
            if not expected[name] or hashlib.sha256(data).hexdigest() != expected[name]:
                raise ProtectionError(f'Literal source/dependency is not the held revision: {name}')
            sources[name] = data

        # Never reuse a public sys.modules entry. Compile exactly the verified
        # bytes in a fresh private namespace; explicit lazy v4 imports resolve
        # to the same privately loaded, byte-pinned dependencies as eager ones.
        namespace = f'_copyeditor_held_literals_{expected_helper_sha256[:16]}_{id(self):x}'
        loaded: dict[str, types.ModuleType] = {}
        original_import = builtins.__import__

        def held_import(name, globals=None, locals=None, fromlist=(), level=0):
            if level == 0 and name in sources:
                return load(name)
            return original_import(name, globals, locals, fromlist, level)

        def load(name):
            if name in loaded:
                return loaded[name]
            private_name = namespace + '.' + name
            module = types.ModuleType(private_name)
            module.__file__ = str(paths[name])
            module.__package__ = namespace
            private_builtins = dict(vars(builtins))
            private_builtins['__import__'] = held_import
            module.__dict__['__builtins__'] = private_builtins
            module.__dict__['__held_source_sha256__'] = expected[name]
            loaded[name] = module
            sys.modules[private_name] = module
            try:
                exec(compile(sources[name], str(paths[name]), 'exec', dont_inherit=True), module.__dict__)
            except Exception:
                if sys.modules.get(private_name) is module:
                    del sys.modules[private_name]
                raise
            return module

        try:
            self.module = load('specialist_literal_protection')
            # Force and pin both dependencies now; their public module cache is
            # irrelevant even when the helper later performs its lazy v4 import.
            for name in dependencies:
                load(name)
            self._create = self.module.SpecialistLiteralMask.create
        except Exception as exc:
            raise ProtectionError('Held literal source could not be executed in its private namespace') from exc
        self._executed_modules = loaded
        self.executed_source_pins = {name: {'path': str(paths[name]), 'sha256': expected[name]}
            for name in paths}
        self.helper_sha256 = expected_helper_sha256
        self.protocol = protocol

    def verify_source_identity(self) -> None:
        for item in self.executed_source_pins.values():
            if hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() != item['sha256']:
                raise ProtectionError('Held literal helper/dependency changed after construction')

    def source(self, source: str) -> ProtectedInput:
        self.verify_source_identity()
        try:
            mask = self._create(source, protocol=self.protocol)
        except Exception as exc:
            raise ProtectionError('Source rejected by held literal protocol') from exc
        return from_public_mask(source, mask, self.helper_sha256, self.protocol)

    def pair(self, source: str, target: str) -> tuple[ProtectedInput, tuple[ProtectedSpan, ...]]:
        protected = self.source(source)
        _, target_spans = protected.mask_target(target)
        return protected, target_spans

    def audit_callback(self, source: str, target: str):
        protected, target_spans = self.pair(source, target)
        return protected.document.protected_spans, target_spans
