"""Pure Python source-anchored editor contract; no model/runtime dependencies."""

from .core import (
    CONTRACT_VERSION, contract_metadata,
    AlignmentResult, EditorError, ExecutionResult, Operation, Program,
    ProtectedSpan, SourceAtom, SourceDocument, TraceStep,
    align_gold, execute, tokenize_source,
)
from .head_contract import (
    EncodedProgram, HeadDecodeResult, HeadVocabulary,
    build_training_label, decode_parallel_scores, encode_program,
)

__all__ = [
    "AlignmentResult", "EditorError", "ExecutionResult", "Operation", "Program",
    "ProtectedSpan", "SourceAtom", "SourceDocument", "TraceStep",
    "align_gold", "execute", "tokenize_source",
    "CONTRACT_VERSION", "contract_metadata", "EncodedProgram", "HeadDecodeResult",
    "HeadVocabulary", "build_training_label", "decode_parallel_scores", "encode_program",
]
