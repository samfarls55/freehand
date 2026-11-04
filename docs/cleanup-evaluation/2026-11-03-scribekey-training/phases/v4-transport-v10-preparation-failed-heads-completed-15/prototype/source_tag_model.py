"""Source edit-graph head definitions; import/run only under a root CPU grant.

No target text, output prefix, global output queries or output-length prediction
enters this model. The external contract supplies labels and safe graph decode.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from types import MappingProxyType
from typing import Any, Mapping
import math

import torch
from torch import Tensor, nn
from torch.nn import functional as F

from source_tag_contract import (
    IGNORE_INDEX, MAX_INSERTIONS, MAX_VISITS, TAG_KEYS, TagVocabulary, decode_tag_scores,
)


TAG_LOSS_COEFFICIENTS = MappingProxyType({"count": 1.0, "case": 0.25, "form": 0.5,
    "repair": 1.0, "pointer": 1.0, "insert_count": 0.5, "insert": 0.5})


@dataclass(frozen=True)
class TagHeadConfig:
    feature_dim: int = 1024
    model_dim: int = 128
    context_layers: int = 2
    attention_heads: int = 4
    feedforward_dim: int = 256
    dropout: float = 0.1
    max_source_atoms: int = 512
    max_visits: int = MAX_VISITS
    max_insertions: int = MAX_INSERTIONS
    copy_logit_bias: float = 4.0
    vocabulary_sha256: str = ""

    def __post_init__(self):
        vocabulary = TagVocabulary.current()
        if not self.vocabulary_sha256:
            object.__setattr__(self, "vocabulary_sha256", vocabulary.sha256)
        for name in ("feature_dim", "model_dim", "attention_heads", "feedforward_dim", "max_source_atoms"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.context_layers) is not int or self.context_layers < 0:
            raise ValueError("context_layers must be a nonnegative integer")
        if self.model_dim % self.attention_heads or not 0 <= self.dropout < 1:
            raise ValueError("Invalid attention divisibility or dropout")
        if not math.isfinite(self.copy_logit_bias) or self.copy_logit_bias <= 0:
            raise ValueError("copy_logit_bias must be finite and positive")
        if self.max_visits != MAX_VISITS or self.max_insertions != MAX_INSERTIONS:
            raise ValueError("Graph visit/insertion capacities differ from the frozen contract")
        if self.vocabulary_sha256 != vocabulary.sha256:
            raise ValueError("Source-tag vocabulary fingerprint mismatch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TagHeadConfig":
        if not isinstance(value, Mapping) or set(value) != {field.name for field in fields(cls)}:
            raise ValueError("Checkpoint must contain the complete exact source-tag config")
        return cls(**value)


class CopySourceTagHead(nn.Module):
    """Source-aligned graph logits with an internal virtual BEGIN node.

    features: float[B,S,1024], one row per canonical source atom.
    padding: bool[B,S], True only for trailing padding. The graph has N=S+1
    nodes, with BEGIN at0 and source atom i at node i+1.
    """

    def __init__(self, config: TagHeadConfig | None = None, vocabulary: TagVocabulary | None = None):
        super().__init__()
        self.config = config or TagHeadConfig()
        self.vocabulary = vocabulary or TagVocabulary.current()
        TagVocabulary.from_dict(self.vocabulary.to_dict())
        if self.vocabulary.sha256 != self.config.vocabulary_sha256:
            raise ValueError("Config/source-tag vocabulary mismatch")
        cfg = self.config
        self.source_projection = nn.Sequential(nn.Linear(cfg.feature_dim, cfg.model_dim), nn.LayerNorm(cfg.model_dim))
        self.source_positions = nn.Embedding(cfg.max_source_atoms + 1, cfg.model_dim)
        self.begin_node = nn.Parameter(torch.zeros(1, 1, cfg.model_dim))
        if cfg.context_layers:
            layer = nn.TransformerEncoderLayer(d_model=cfg.model_dim, nhead=cfg.attention_heads,
                dim_feedforward=cfg.feedforward_dim, dropout=cfg.dropout, activation="gelu",
                batch_first=True, norm_first=True)
            self.context = nn.TransformerEncoder(layer, cfg.context_layers, enable_nested_tensor=False)
        else:
            self.context = nn.Identity()
        self.output_norm = nn.LayerNorm(cfg.model_dim)
        self.occurrence_positions = nn.Embedding(cfg.max_visits, cfg.model_dim)
        self.insertion_positions = nn.Embedding(cfg.max_insertions, cfg.model_dim)
        self.count_head = nn.Linear(cfg.model_dim, self.vocabulary.size("count"))
        self.case_head = nn.Linear(cfg.model_dim, self.vocabulary.size("case"))
        self.form_head = nn.Linear(cfg.model_dim, self.vocabulary.size("form"))
        self.repair_head = nn.Linear(cfg.model_dim, self.vocabulary.size("repair"))
        self.insert_count_head = nn.Linear(cfg.model_dim, self.vocabulary.size("insert_count"))
        self.insert_head = nn.Linear(cfg.model_dim, self.vocabulary.size("insert"))
        self.pointer_query = nn.Linear(cfg.model_dim, cfg.model_dim, bias=False)
        self.pointer_key = nn.Linear(cfg.model_dim, cfg.model_dim, bias=False)
        # Exact identity argmax independent of random input/encoder activations.
        # Pointer scores are irrelevant until the independently trained ON gate.
        keep_case = self.vocabulary.cases.index("keep")
        for head, default in ((self.count_head, 1), (self.case_head, keep_case),
                (self.form_head, 0), (self.repair_head, 0),
                (self.insert_count_head, 0), (self.insert_head, 0)):
            nn.init.zeros_(head.weight)
            nn.init.constant_(head.bias, -cfg.copy_logit_bias)
            with torch.no_grad():
                head.bias[default] = cfg.copy_logit_bias

    def forward(self, features: Tensor, padding: Tensor | None = None) -> dict[str, Tensor]:
        cfg = self.config
        if features.ndim != 3 or features.shape[-1] != cfg.feature_dim or not features.is_floating_point():
            raise ValueError("Expected floating [batch,source_atoms,feature_dim] features")
        batch, count, _ = features.shape
        if batch < 1 or not 1 <= count <= cfg.max_source_atoms:
            raise ValueError("Invalid source feature capacity")
        if padding is None:
            padding = torch.zeros((batch, count), dtype=torch.bool, device=features.device)
        if padding.shape != (batch, count) or padding.dtype != torch.bool or padding.device != features.device:
            raise ValueError("Expected a colocated bool source-padding mask")
        lengths = (~padding).sum(dim=1)
        expected = torch.arange(count, device=features.device).unsqueeze(0) >= lengths.unsqueeze(1)
        if bool((lengths == 0).any()) or not torch.equal(padding, expected):
            raise ValueError("Source rows must be nonempty, contiguous, and right padded")
        source = self.source_projection(features)
        nodes = torch.cat((self.begin_node.expand(batch, -1, -1), source), dim=1)
        node_padding = torch.cat((torch.zeros((batch, 1), dtype=torch.bool, device=features.device), padding), dim=1)
        positions = torch.arange(count + 1, device=features.device)
        nodes = nodes + self.source_positions(positions).unsqueeze(0)
        if cfg.context_layers:
            nodes = self.context(nodes, src_key_padding_mask=node_padding, is_causal=False)
        nodes = self.output_norm(nodes)
        occurrences = nodes.unsqueeze(2) + self.occurrence_positions.weight.view(1, 1, cfg.max_visits, cfg.model_dim)
        insertions = occurrences.unsqueeze(3) + self.insertion_positions.weight.view(1, 1, 1, cfg.max_insertions, cfg.model_dim)
        pointer = torch.einsum("bnrd,bmd->bnrm", self.pointer_query(occurrences), self.pointer_key(nodes)) / math.sqrt(cfg.model_dim)
        # Key0 is END and always available; BEGIN's contextual representation is
        # the key vector for it. Source keys1..S retain the exact source mapping.
        pointer = pointer.masked_fill(node_padding[:, None, None, :], float("-inf"))
        return {"count": self.count_head(nodes), "case": self.case_head(occurrences),
            "form": self.form_head(occurrences), "repair": self.repair_head(occurrences),
            "pointer": pointer, "insert_count": self.insert_count_head(occurrences),
            "insert": self.insert_head(insertions)}

    def checkpoint_payload(self) -> dict[str, Any]:
        return {"schema_version": 1, "config": self.config.to_dict(),
            "vocabulary": self.vocabulary.to_dict(), "state_dict": self.state_dict()}

    @classmethod
    def from_checkpoint_payload(cls, payload: Mapping[str, Any]) -> "CopySourceTagHead":
        if (not isinstance(payload, Mapping) or set(payload) != {"schema_version", "config", "vocabulary", "state_dict"}
                or type(payload["schema_version"]) is not int or payload["schema_version"] != 1):
            raise ValueError("Unexpected source-tag checkpoint schema/fields")
        model = cls(TagHeadConfig.from_dict(payload["config"]), TagVocabulary.from_dict(payload["vocabulary"]))
        model.load_state_dict(payload["state_dict"], strict=True)
        return model

    def decode_sample(self, document, logits: Mapping[str, Tensor], *, sample_index: int = 0, **options):
        valid_nodes = len(document.atoms) + 1
        scores = {name: value[sample_index, :valid_nodes].detach().cpu().tolist() for name, value in logits.items()}
        scores["pointer"] = [[row[:valid_nodes] for row in visits] for visits in scores["pointer"]]
        return decode_tag_scores(document, scores, **options)


def _masked_ce(logits: Tensor, labels: Tensor) -> Tensor:
    if logits.shape[:-1] != labels.shape:
        raise ValueError("Source-tag loss shape mismatch")
    valid = labels.reshape(-1) != IGNORE_INDEX
    if not bool(valid.any()):
        return logits.reshape(-1)[:0].sum()
    return F.cross_entropy(logits.reshape(-1, logits.shape[-1])[valid], labels.reshape(-1)[valid])


def source_tag_loss(logits: Mapping[str, Tensor], labels: Mapping[str, Tensor]) -> tuple[Tensor, dict[str, Tensor]]:
    """Gold graph-branch masks; no loss on inactive visits, fields or padding."""
    if set(logits) != set(TAG_KEYS) or set(labels) != set(TAG_KEYS):
        raise ValueError("Expected exactly the seven source-tag heads")
    targets = {name: value.clone() for name, value in labels.items()}
    counts = targets["count"]
    if counts.ndim != 2 or counts.shape[1] < 2:
        raise ValueError("Expected [batch,BEGIN+source] count labels")
    if any(value.dtype != torch.long for value in targets.values()):
        raise ValueError("Source-tag targets must be long integer classes")
    visits = logits["case"].shape[2]
    if visits != MAX_VISITS:
        raise ValueError("Visit axis differs from frozen source-tag contract")
    visit_ids = torch.arange(visits, device=counts.device).view(1, 1, -1)
    source_active = visit_ids < counts.clamp_min(0).unsqueeze(-1)
    source_active[:, 0, :] = False
    graph_active = source_active.clone()
    # BEGIN occurrence0 is real only when some source count is supervised. In
    # an all-ignored batch it must not create accidental auxiliary loss.
    graph_active[:, 0, 0] = (counts[:, 1:] != IGNORE_INDEX).any(dim=1)
    targets["count"][:, 0] = IGNORE_INDEX
    for name in ("case", "form"):
        targets[name] = targets[name].masked_fill(~source_active, IGNORE_INDEX)
    for name in ("repair", "insert_count"):
        targets[name] = targets[name].masked_fill(~graph_active, IGNORE_INDEX)
    pointer_active = graph_active & (targets["repair"] == 1)
    targets["pointer"] = targets["pointer"].masked_fill(~pointer_active, IGNORE_INDEX)
    insert_ids = torch.arange(MAX_INSERTIONS, device=counts.device).view(1, 1, 1, -1)
    insert_active = graph_active.unsqueeze(-1) & (insert_ids < targets["insert_count"].clamp_min(0).unsqueeze(-1))
    targets["insert"] = targets["insert"].masked_fill(~insert_active, IGNORE_INDEX)
    components = {name: _masked_ce(logits[name], targets[name]) for name in TAG_KEYS}
    total = sum(TAG_LOSS_COEFFICIENTS[name] * value for name, value in components.items())
    return total, components
