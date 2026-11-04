"""Torch loss definitions only; imported by an explicitly granted child worker."""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping
import torch
from torch import Tensor
from torch.nn import functional as F

COEFFICIENTS = MappingProxyType({"length": 1.0, "kind": 1.0, "pointer": 1.0,
    "case": 0.25, "morph": 0.5, "function": 0.5, "punct": 0.25, "space": 0.25})


def masked_cross_entropy(logits: Tensor, labels: Tensor, ignore_index: int = -100) -> Tensor:
    if logits.shape[:-1] != labels.shape:
        raise ValueError("Loss logits/labels shape mismatch")
    flat = logits.reshape(-1, logits.shape[-1])
    targets = labels.reshape(-1)
    valid = targets != ignore_index
    if not bool(valid.any()):
        # Empty-view sum is differentiable finite zero even when every pointer
        # logit is -inf. Never multiply masked infinities by zero.
        return logits.reshape(-1)[:0].sum()
    return F.cross_entropy(flat[valid], targets[valid])


def head_loss(logits: Mapping[str, Tensor], labels: Mapping[str, Tensor]) -> tuple[Tensor, dict[str, Tensor]]:
    if set(logits) != set(COEFFICIENTS) or set(labels) != set(COEFFICIENTS):
        raise ValueError("Expected the eight frozen head loss fields")
    components = {name: masked_cross_entropy(logits[name], labels[name]) for name in COEFFICIENTS}
    total = sum(COEFFICIENTS[name] * value for name, value in components.items())
    return total, components
