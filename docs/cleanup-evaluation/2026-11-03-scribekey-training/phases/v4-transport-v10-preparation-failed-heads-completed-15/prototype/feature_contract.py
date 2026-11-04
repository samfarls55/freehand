"""Pinned token/offset contract and capacity checks; no model or Torch calls."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Sequence

from editor_core import EditorError, SourceDocument
from protection import ProtectedInput

CONTRACT_VERSION = 'scribekey-official-input-forced-source-copy-v1'
PREFIX = '<|startoftext|>### Input:\n[Styling: semi-casual] [Structure: prose] [Context: general]\n'
SUFFIX = '\n\n### Output:\n'
FEATURE_WIDTH = 1024


class FeatureContractError(EditorError):
    pass


@dataclass(frozen=True)
class FeatureCapacity:
    context_tokens: int = 1024
    logical_batch_tokens: int = 256
    physical_batch_tokens: int = 256
    max_source_atoms: int = 512

    def check(self, count: int, atoms: int) -> None:
        if count > self.context_tokens:
            raise FeatureContractError('context_capacity', f'{count} tokens exceed {self.context_tokens}; no truncation')
        # b12015 HTTP pooling-NONE task.can_split() is false. Each HTTP request
        # needs to fit both capacities; sending HTTP chunks resets the sequence.
        if count > min(self.logical_batch_tokens, self.physical_batch_tokens):
            raise FeatureContractError('http_embedding_capacity',
                f'{count} tokens exceed b/u={self.logical_batch_tokens}/{self.physical_batch_tokens}; '
                'requires a separately qualified larger profile or stateful C API, never HTTP chunk truncation')
        if not 1 <= atoms <= self.max_source_atoms:
            raise FeatureContractError('source_atom_capacity', f'{atoms} source atoms exceed {self.max_source_atoms}')


@dataclass(frozen=True)
class EncoderContract:
    model_text: str
    official_prompt: str
    prompt_ids: tuple[int, ...]
    copy_ids: tuple[int, ...]
    model_ids: tuple[int, ...]
    copy_offsets: tuple[tuple[int, int], ...]
    second_copy_first_row: int
    atom_copy_rows: tuple[int, ...]
    atom_model_intervals: tuple[tuple[int, int], ...]
    feature_width: int = FEATURE_WIDTH
    version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {'version': self.version, 'feature_width': self.feature_width,
            'model_text': self.model_text, 'model_text_sha256': hashlib.sha256(self.model_text.encode()).hexdigest(),
            'official_prompt': self.official_prompt, 'prompt_ids': list(self.prompt_ids),
            'copy_ids': list(self.copy_ids), 'model_ids': list(self.model_ids),
            'copy_offsets': [list(pair) for pair in self.copy_offsets],
            'second_copy_first_row': self.second_copy_first_row, 'atom_copy_rows': list(self.atom_copy_rows),
            'atom_model_intervals': [list(pair) for pair in self.atom_model_intervals]}

    @property
    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()


def _covering_row(offsets: Sequence[tuple[int, int]], start: int, end: int) -> int:
    covering = [(index, a, b) for index, (a, b) in enumerate(offsets) if a < end and b > start]
    if not covering:
        raise FeatureContractError('offset_alignment', 'Source atom has no second-copy BPE row')
    at = start
    for _, a, b in sorted(covering, key=lambda row: (row[1], row[2])):
        if a > at:
            raise FeatureContractError('offset_alignment', 'BPE offsets leave a source-atom gap')
        at = max(at, b)
    if at < end:
        raise FeatureContractError('offset_alignment', 'BPE offsets do not cover source-atom end')
    # Frozen representation: final native state covering the atom, not an
    # invented average or a feature from the first, only-left-context copy.
    return max(row[0] for row in covering)


def build_encoder_contract(protected: ProtectedInput, tokenizer: Any,
                           capacity: FeatureCapacity = FeatureCapacity()) -> EncoderContract:
    if any(control in protected.raw_source for control in ('<|', '###', '\x00')):
        raise FeatureContractError('reserved_input', 'Source contains reserved specialist controls')
    prompt = PREFIX + protected.model_text + SUFFIX
    first = tokenizer.encode(prompt, add_special_tokens=False)
    second = tokenizer.encode(protected.model_text, add_special_tokens=False)
    model_ids = tuple(first.ids) + tuple(second.ids)
    if not model_ids or model_ids[0] != 1 or model_ids.count(1) != 1:
        raise FeatureContractError('BOS_contract', 'Exactly one explicit BOS1 required')
    offsets = tuple(tuple(pair) for pair in second.offsets)
    if len(second.ids) != len(offsets):
        raise FeatureContractError('offset_alignment', 'Tokenizer IDs/offset counts differ')
    intervals = tuple(protected.model_interval(atom) for atom in protected.document.atoms)
    atom_rows = tuple(_covering_row(offsets, start, end) for start, end in intervals)
    capacity.check(len(model_ids), len(atom_rows))
    return EncoderContract(protected.model_text, prompt, tuple(first.ids), tuple(second.ids), model_ids,
        offsets, len(first.ids), atom_rows, intervals)


def select_atom_features(all_rows: Any, contract: EncoderContract, document: SourceDocument):
    """Accept array-like FP32 data later; importing this module needs no NumPy."""
    if getattr(all_rows, 'shape', None) != (len(contract.model_ids), contract.feature_width):
        raise FeatureContractError('native_row_shape', 'Native all-token rows must exactly match input IDs and width')
    if len(document.atoms) != len(contract.atom_copy_rows):
        raise FeatureContractError('atom_feature_shape', 'Canonical source atom count changed')
    indices = [contract.second_copy_first_row + index for index in contract.atom_copy_rows]
    return all_rows[indices].copy()


def stateful_c_api_chunk_plan(contract: EncoderContract, max_chunk: int = 64) -> dict[str, Any]:
    """A source-verified plan only, NOT implemented transport or a passed proof."""
    if max_chunk < 1:
        raise FeatureContractError('chunk_capacity', 'Positive C API chunk capacity required')
    return {'status': 'PLAN_ONLY_NOT_EXECUTED', 'transport': 'direct-C-API-not-stateless-HTTP',
        'same_hybrid_context_sequence_id_required': True, 'positions_never_reset_between_chunks': True,
        'copy_embedding_rows_before_next_decode': True, 'no_pooling': True,
        'chunks': [{'start': start, 'end': min(start + max_chunk, len(contract.model_ids))}
            for start in range(0, len(contract.model_ids), max_chunk)],
        'required_proof': 'Exact native reset/order/numerics and resource qualification for chunked extraction before use.'}
