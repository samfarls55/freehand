"""Parallel source-pointer/edit head definitions. Not imported/run in preparation.

Torch is required only when this module is explicitly imported after the CPU
grant. Package __init__ and head_contract never import this module implicitly.
No target text/tokens or teacher-forced output prefix enters forward().
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Mapping, Sequence
import math

import torch
from torch import Tensor, nn

from .core import CONTRACT_VERSION, EditorError, SourceDocument
from .head_contract import HeadDecodeResult, HeadVocabulary, decode_parallel_scores


@dataclass(frozen=True)
class HeadConfig:
    feature_dim: int = 1024
    model_dim: int = 128
    decoder_layers: int = 2
    attention_heads: int = 4
    feedforward_dim: int = 384
    dropout: float = 0.1
    max_ops: int = 256
    max_source_atoms: int = 512
    contract_version: str = CONTRACT_VERSION
    vocabulary_sha256: str = ""

    def __post_init__(self) -> None:
        vocabulary = HeadVocabulary.current()
        if not self.vocabulary_sha256:
            object.__setattr__(self, "vocabulary_sha256", vocabulary.sha256)
        for name in ("feature_dim", "model_dim", "decoder_layers", "attention_heads", "feedforward_dim", "max_ops", "max_source_atoms"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise EditorError("invalid_head_config", f"{name} must be a positive integer")
        if self.model_dim % self.attention_heads or not 0.0 <= self.dropout < 1.0:
            raise EditorError("invalid_head_config", "Invalid attention divisibility/dropout")
        if self.contract_version != CONTRACT_VERSION or self.vocabulary_sha256 != vocabulary.sha256:
            raise EditorError("vocabulary_mismatch", "Head config does not match the frozen editor contract")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HeadConfig":
        if not isinstance(value, Mapping) or set(value) != {field.name for field in fields(cls)}:
            raise EditorError("invalid_head_config", "Checkpoint must contain the complete exact head config")
        return cls(**value)


class CopyEditHead(nn.Module):
    """Nonautoregressive learned output slots attending to native source features.

    source_features: float [batch, source_atoms, feature_dim]. One feature row
    must map to exactly one SourceDocument atom; orchestration owns that mapping.
    source_padding_mask: bool [batch, source_atoms], True means padding.
    """

    def __init__(self, config: HeadConfig | None = None, vocabulary: HeadVocabulary | None = None):
        super().__init__()
        self.config = config or HeadConfig()
        self.vocabulary = vocabulary or HeadVocabulary.current()
        HeadVocabulary.from_dict(self.vocabulary.to_dict())
        if self.vocabulary.sha256 != self.config.vocabulary_sha256:
            raise EditorError("vocabulary_mismatch", "Head config/vocabulary mismatch")
        cfg = self.config
        self.source_projection = nn.Sequential(nn.Linear(cfg.feature_dim, cfg.model_dim), nn.LayerNorm(cfg.model_dim))
        self.source_positions = nn.Embedding(cfg.max_source_atoms, cfg.model_dim)
        self.slot_queries = nn.Embedding(cfg.max_ops, cfg.model_dim)
        layer = nn.TransformerDecoderLayer(d_model=cfg.model_dim, nhead=cfg.attention_heads,
            dim_feedforward=cfg.feedforward_dim, dropout=cfg.dropout, activation="gelu",
            batch_first=True, norm_first=True)
        self.decoder = nn.TransformerDecoder(layer, cfg.decoder_layers, norm=nn.LayerNorm(cfg.model_dim))
        self.length_head = nn.Sequential(nn.Linear(2 * cfg.model_dim, cfg.model_dim), nn.GELU(), nn.Linear(cfg.model_dim, cfg.max_ops + 1))
        self.kind_head = nn.Linear(cfg.model_dim, len(self.vocabulary.kinds))
        self.pointer_query = nn.Linear(cfg.model_dim, cfg.model_dim, bias=False)
        self.pointer_key = nn.Linear(cfg.model_dim, cfg.model_dim, bias=False)
        self.case_head = nn.Linear(cfg.model_dim, len(self.vocabulary.cases))
        self.morph_head = nn.Linear(cfg.model_dim, len(self.vocabulary.morph_values))
        self.function_head = nn.Linear(cfg.model_dim, len(self.vocabulary.function_values))
        self.punct_head = nn.Linear(cfg.model_dim, len(self.vocabulary.punct_values))
        self.space_head = nn.Linear(cfg.model_dim, len(self.vocabulary.space_values))

    def forward(self, source_features: Tensor, source_padding_mask: Tensor | None = None) -> dict[str, Tensor]:
        cfg = self.config
        if source_features.ndim != 3 or source_features.shape[-1] != cfg.feature_dim:
            raise EditorError("feature_shape", "Expected [batch,source_atoms,feature_dim]")
        batch, count, _ = source_features.shape
        if batch < 1 or not 1 <= count <= cfg.max_source_atoms or not source_features.is_floating_point():
            raise EditorError("feature_shape", "Invalid source feature count or dtype")
        if source_padding_mask is None:
            source_padding_mask = torch.zeros((batch, count), dtype=torch.bool, device=source_features.device)
        if (source_padding_mask.shape != (batch, count) or source_padding_mask.dtype != torch.bool
                or source_padding_mask.device != source_features.device):
            raise EditorError("feature_mask", "Expected a colocated bool [batch,source_atoms] mask")
        if bool(source_padding_mask.all(dim=1).any()):
            raise EditorError("feature_mask", "Every source needs at least one valid feature row")
        counts = (~source_padding_mask).sum(dim=1)
        expected_mask = torch.arange(count, device=source_features.device).unsqueeze(0) >= counts.unsqueeze(1)
        if not torch.equal(source_padding_mask, expected_mask):
            raise EditorError("feature_mask", "Feature rows must be contiguous source atoms with right padding only")
        memory = self.source_projection(source_features)
        positions = torch.arange(count, device=memory.device)
        memory = memory + self.source_positions(positions).unsqueeze(0)
        queries = self.slot_queries.weight.unsqueeze(0).expand(batch, -1, -1)
        # Explicitly noncausal: slots self-attend simultaneously, with no target
        # content, output prefix, causal mask, or target-padding supervision.
        slots = self.decoder(tgt=queries, memory=memory, tgt_mask=None,
            memory_key_padding_mask=source_padding_mask, tgt_is_causal=False,
            memory_is_causal=False)
        valid = (~source_padding_mask).unsqueeze(-1).to(memory.dtype)
        pooled_source = (memory * valid).sum(dim=1) / valid.sum(dim=1).clamp_min(1)
        length = self.length_head(torch.cat((pooled_source, slots.mean(dim=1)), dim=-1))
        pointer = torch.einsum("bod,bsd->bos", self.pointer_query(slots), self.pointer_key(memory)) / math.sqrt(cfg.model_dim)
        pointer = pointer.masked_fill(source_padding_mask.unsqueeze(1), float("-inf"))
        return {"length": length, "kind": self.kind_head(slots), "pointer": pointer,
            "case": self.case_head(slots), "morph": self.morph_head(slots),
            "function": self.function_head(slots), "punct": self.punct_head(slots), "space": self.space_head(slots)}

    def checkpoint_payload(self) -> dict[str, Any]:
        """Caller owns saving/freezing. No model/native feature artifact is embedded."""
        return {"schema_version": 1, "config": self.config.to_dict(),
            "vocabulary": self.vocabulary.to_dict(), "state_dict": self.state_dict()}

    @classmethod
    def from_checkpoint_payload(cls, payload: Mapping[str, Any]) -> "CopyEditHead":
        if (not isinstance(payload, Mapping) or set(payload) != {"schema_version", "config", "vocabulary", "state_dict"}
                or type(payload["schema_version"]) is not int or payload["schema_version"] != 1):
            raise EditorError("invalid_head_checkpoint", "Unexpected checkpoint schema/fields")
        model = cls(HeadConfig.from_dict(payload["config"]), HeadVocabulary.from_dict(payload["vocabulary"]))
        model.load_state_dict(payload["state_dict"], strict=True)
        return model

    def decode_sample(self, document: SourceDocument, logits: Mapping[str, Tensor], *, sample_index: int = 0,
                      **search_options: Any) -> HeadDecodeResult:
        """Decode already-computed logits; this method does not call forward()."""
        count = len(document.atoms)
        scores = {name: value[sample_index].detach().cpu().tolist() for name, value in logits.items()}
        scores["pointer"] = [row[:count] for row in scores["pointer"]]
        return decode_parallel_scores(document, scores, max_ops=self.config.max_ops,
            vocabulary=self.vocabulary, **search_options)
