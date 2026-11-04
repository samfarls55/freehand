#!/usr/bin/env python3
"""ScribeKey-only local supervised LoRA training; no remote model code or downloads.

This tool trains on the production specialist prompt and literal protocol. It
never reads a blind evaluation corpus. Adapter weights are the only train-time
checkpoint; merge writes a separate, full BF16 derivative when explicitly asked.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import resource
import shutil
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/Freehand.Cleanup.Evaluation"))
from specialist_literal_protection import SpecialistLiteralMask, PROTOCOL

BOS = "<|startoftext|>"
PREFIX = BOS + "### Input:\n[Styling: semi-casual] [Structure: prose] [Context: general]\n"
SUFFIX = "\n\n### Output:\n"
SOURCE_WEIGHT_SHA = "1a9ab3fcd2384f9c4053f4b55d5e0f40de195487853fdd006b1fa810cd69e16a"
SOURCE_GGUF_SHA = "82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174"
TRAINING_MODE_GGUF = "original-iq4-dequantized-fp32-v1"
SOURCE_Q8_CPU_SHA = "37c755982f13955f7b95c5521f1d1a3fa34f2f27568ba60b97351484007550a5"
SOURCE_Q8_BASE_SHA = "3b311170ea4a999a9d9dac18561eda8830a2c938398cb4bbed41d6a2af443abb"
UNLIKELIHOOD_SCHEMA = "freehand-unlikelihood-token-events-v1"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def write_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def protected_pair(source: str, target: str) -> tuple[str, str, SpecialistLiteralMask]:
    """Use input-derived tokens on both sides, then prove exact target restoration."""
    mask = SpecialistLiteralMask.create(source)
    masked_target = target
    for ordinal, block in enumerate(mask.legacy.blocks):
        if masked_target.count(block) != 1:
            raise ValueError("Target must retain every exact dictionary block once")
        masked_target = masked_target.replace(block, mask.legacy.token_prefix + str(ordinal) + "_END", 1)
    output = []
    at = 0
    for token, payload in zip(mask.tokens, mask.payloads):
        found = masked_target.find(payload, at)
        if found < 0:
            raise ValueError("Target must retain exact quoted/dictionary payloads in input order")
        output.extend([masked_target[at:found], token])
        at = found + len(payload)
    output.append(masked_target[at:])
    masked_target = "".join(output)
    if mask.restore(masked_target) != target:
        raise ValueError("Literal target round-trip failed")
    return PREFIX + mask.masked_text + SUFFIX, masked_target, mask


def load_data(path: Path):
    rows = []
    ids = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row.get("id"), str) or row["id"] in ids:
            raise ValueError(f"Missing/duplicate id at line {line_number}")
        ids.add(row["id"])
        if not isinstance(row.get("input"), str) or not isinstance(row.get("target"), str):
            raise ValueError(f"Missing input/target at line {line_number}")
        for value in [row["input"], row["target"]]:
            if not value or any(control in value for control in ["<|", "###", "\x00"]):
                raise ValueError(f"Empty/reserved control input at line {line_number}")
        prompt, target, mask = protected_pair(row["input"], row["target"])
        rows.append({**row, "prompt": prompt, "masked_target": target, "literal_count": len(mask.tokens)})
    if not rows:
        raise ValueError("Dataset is empty")
    return rows


def imports(threads: int):
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    import torch
    from safetensors.torch import load_file, save_file
    from transformers import AutoModelForCausalLM, PreTrainedTokenizerFast
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    return torch, load_file, save_file, AutoModelForCausalLM, PreTrainedTokenizerFast


def base_model(base: Path, threads: int):
    torch, load_file, save_file, AutoModel, Tokenizer = imports(threads)
    if sha(base / "model.safetensors") != SOURCE_WEIGHT_SHA:
        raise ValueError("This experiment requires the pinned original ScribeKey v1.1 BF16 weights")
    tokenizer = Tokenizer(tokenizer_file=str(base / "tokenizer.json"), bos_token=BOS,
                          eos_token="<|im_end|>", pad_token="<|pad|>", clean_up_tokenization_spaces=False)
    model, loading = AutoModel.from_pretrained(base, torch_dtype=torch.float32, local_files_only=True,
                                              trust_remote_code=False, attn_implementation="sdpa",
                                              output_loading_info=True)
    if loading["missing_keys"] or loading["unexpected_keys"] or loading["mismatched_keys"]:
        raise ValueError("Checkpoint/model implementation keys do not match: " + repr(loading))
    model.config.use_cache = False
    return torch, load_file, save_file, tokenizer, model


def validate_gguf_base_identity(base: Path, path: Path):
    """Verify both immutable sources before constructing or decoding a model."""
    if sha(base / "model.safetensors") != SOURCE_WEIGHT_SHA:
        raise ValueError("Quantized training requires the pinned original BF16 provenance")
    if sha(path) != SOURCE_GGUF_SHA:
        raise ValueError("Quantized training requires the exact original IQ4 control GGUF")
    return {"training_base_mode": TRAINING_MODE_GGUF, "frozen_base_sha256": SOURCE_GGUF_SHA,
            "original_bf16_sha256": SOURCE_WEIGHT_SHA, "base_config_sha256": sha(base / "config.json"),
            "tokenizer_sha256": sha(base / "tokenizer.json"), "quantized_training_source_sha256": sha(Path(__file__))}


def gguf_tensor_mapping(header, tensors, name_map, expected_count=148):
    """Invert the pinned LFM2 name/conv transformation, with complete coverage."""
    by_name = {tensor.name: tensor for tensor in tensors}
    if len(by_name) != len(tensors) or len(header) != expected_count or len(tensors) != expected_count:
        raise ValueError("GGUF/HF tensor inventory must be complete and unique")
    mapped = {}
    used = set()
    for name, info in header.items():
        other = name_map.get_name(name, try_suffixes=(".weight", ".bias"))
        if not other or other not in by_name or other in used:
            raise ValueError("GGUF tensor mapping is missing or not bijective: " + name)
        shape = list(info["shape"])
        if "conv.conv" in name:
            if len(shape) != 3 or shape[1] != 1:
                raise ValueError("Unexpected HF short-convolution shape")
            shape.pop(1)
        tensor = by_name[other]
        if shape != list(reversed(tensor.shape.tolist())):
            raise ValueError("GGUF tensor shape differs from original HF: " + name)
        mapped[name] = tensor
        used.add(other)
    return mapped


def inverse_gguf_tensor(name, tensor, dequantizer):
    import numpy as np
    # GGUFReader already presents row-major NumPy dimensions; do not transpose.
    array = dequantizer(tensor.data, tensor.tensor_type)
    array = array.reshape(tuple(reversed(tensor.shape.tolist())))
    if "conv.conv" in name:
        array = np.expand_dims(array, axis=1)
    if array.dtype != np.float32 or not np.isfinite(array).all():
        raise ValueError("GGUF decoding must produce finite FP32 values: " + name)
    return array


def quantized_base_model(base: Path, gguf_path: Path, threads: int):
    """Decode the exact native base into FP32 RAM, without a base serialization."""
    identity = validate_gguf_base_identity(base, gguf_path)
    torch, load_file, save_file, AutoModel, Tokenizer = imports(threads)
    import gguf
    import numpy as np
    from gguf.quants import dequantize
    from transformers import AutoConfig
    if importlib.metadata.version("gguf") != "0.19.0":
        raise ValueError("This proved inverse requires the pinned gguf 0.19.0 implementation")
    with (base / "model.safetensors").open("rb") as stream:
        length = int.from_bytes(stream.read(8), "little")
        header = {key: value for key, value in json.loads(stream.read(length)).items() if key != "__metadata__"}
    if any(value["dtype"] != "BF16" for value in header.values()):
        raise ValueError("Original HF tensor precision differs")
    reader = gguf.GGUFReader(str(gguf_path), "r")
    mapped = gguf_tensor_mapping(header, reader.tensors, gguf.get_tensor_name_map(gguf.MODEL_ARCH.LFM2, 16))
    config = AutoConfig.from_pretrained(base, local_files_only=True, trust_remote_code=False)
    config.rope_theta = float(config.rope_parameters["rope_theta"])
    config._attn_implementation = "sdpa"
    model = AutoModel.from_config(config, torch_dtype=torch.float32, trust_remote_code=False)
    if set(dict(model.named_parameters())) != set(header):
        raise ValueError("HF architecture does not match all original unique parameters")
    types = {}
    with torch.no_grad():
        for name, tensor in mapped.items():
            array = inverse_gguf_tensor(name, tensor, dequantize)
            parameter = model.get_parameter(name)
            if list(parameter.shape) != header[name]["shape"] or parameter.dtype != torch.float32:
                raise ValueError("Recovered HF parameter shape/dtype mismatch")
            parameter.copy_(torch.from_numpy(np.array(array, dtype=np.float32, copy=True)))
            types[tensor.tensor_type.name] = types.get(tensor.tensor_type.name, 0) + 1
    model.tie_weights()
    if model.lm_head.weight.data_ptr() != model.model.embed_tokens.weight.data_ptr():
        raise ValueError("Recovered HF output head is not tied to its embedding")
    model.config.use_cache = False
    identity.update(gguf_dequantizer_sha256=sha(Path(gguf.quants.__file__)),
                    gguf_mapping_sha256=sha(Path(gguf.tensor_mapping.__file__)))
    model._freehand_base_identity = identity
    quantized_types = {gguf.GGMLQuantizationType.IQ4_XS, gguf.GGMLQuantizationType.Q5_K, gguf.GGMLQuantizationType.Q6_K}
    model._freehand_quantized_linear_types = {name.removesuffix(".weight"): tensor.tensor_type.name
        for name, tensor in mapped.items() if tensor.tensor_type in quantized_types and name.startswith("model.layers.")}
    # The tied embedding is also the native quantized output matmul, not a lookup-only tensor.
    if mapped["model.embed_tokens.weight"].tensor_type in quantized_types:
        model._freehand_quantized_linear_types["lm_head"] = mapped["model.embed_tokens.weight"].tensor_type.name
    model._freehand_base_receipt = {**identity, "tensor_count": len(mapped), "tensor_types": types,
        "conv_singleton_restorations": sum("conv.conv" in name for name in mapped),
        "all_base_parameters_dtype": "float32", "tied_head_verified": True,
        "base_serialized": False, "native_forward_equivalence_claimed": False,
        "known_numerical_differences": ["Native quantized matmul uses Q8_K activations",
            "HF stores K/V in FP32; optional emulation rounds their values through F16"]}
    tokenizer = Tokenizer(tokenizer_file=str(base / "tokenizer.json"), bos_token=BOS,
                         eos_token="<|im_end|>", pad_token="<|pad|>", clean_up_tokenization_spaces=False)
    return torch, load_file, save_file, tokenizer, model


def expand_adapter_state(state, parent_rank, parent_alpha, new_rank, new_alpha, seed, torch):
    """Preserve the old function while giving the additional rank a live gradient."""
    if (type(parent_rank) is not int or type(new_rank) is not int or type(seed) is not int
            or not 1 <= parent_rank < new_rank <= 64
            or not math.isfinite(parent_alpha) or not math.isfinite(new_alpha) or min(parent_alpha, new_alpha) <= 0
            or not math.isclose(parent_alpha / parent_rank, new_alpha / new_rank, rel_tol=0, abs_tol=1e-12)):
        raise ValueError("Rank expansion requires increased rank and unchanged alpha/rank")
    prefixes = {key.rsplit(".", 1)[0] for key in state}
    expected = {prefix + suffix for prefix in prefixes for suffix in (".lora_A", ".lora_B")}
    if not state or set(state) != expected:
        raise ValueError("Rank expansion requires exact paired LoRA A/B tensors")
    generator = torch.Generator(device="cpu").manual_seed(seed)
    result = {}
    maximum = 0.0
    for prefix in sorted(prefixes):
        a, b = state[prefix + ".lora_A"], state[prefix + ".lora_B"]
        if (a.ndim != 2 or b.ndim != 2 or a.shape[0] != parent_rank or b.shape[1] != parent_rank
                or a.dtype != torch.float32 or b.dtype != torch.float32
                or not torch.isfinite(a).all() or not torch.isfinite(b).all()):
            raise ValueError("Parent adapter shape/dtype/values differ")
        expanded_a = torch.empty((new_rank, a.shape[1]), dtype=torch.float32)
        torch.nn.init.kaiming_uniform_(expanded_a, a=math.sqrt(5), generator=generator)
        expanded_b = torch.zeros((b.shape[0], new_rank), dtype=torch.float32)
        expanded_a[:parent_rank].copy_(a)
        expanded_b[:, :parent_rank].copy_(b)
        old_delta = (b @ a) * (parent_alpha / parent_rank)
        new_delta = (expanded_b @ expanded_a) * (new_alpha / new_rank)
        difference = float((new_delta - old_delta).abs().max())
        if not torch.allclose(old_delta, new_delta, atol=1e-6, rtol=1e-6):
            raise ValueError("Expanded adapter delta exceeds FP32 tolerance")
        maximum = max(maximum, difference)
        result[prefix + ".lora_A"] = expanded_a
        result[prefix + ".lora_B"] = expanded_b
    return result, {"parent_rank": parent_rank, "parent_alpha": parent_alpha,
                    "rank": new_rank, "alpha": new_alpha, "seed": seed,
                    "new_a_initialization": "seeded_kaiming_uniform_local_generator", "new_b_initialization": "zero",
                    "maximum_delta_absolute_difference": maximum, "delta_atol": 1e-6, "delta_rtol": 1e-6}


def fp16_roundtrip_ste(tensor, torch):
    class Roundtrip(torch.autograd.Function):
        @staticmethod
        def forward(ctx, value):
            return value.to(torch.float16).to(value.dtype)

        @staticmethod
        def backward(ctx, gradient):
            return gradient

    return Roundtrip.apply(tensor)


class NativeQ8KQuantizer:
    """Pinned native 256-value Q8_K quantization/dequantization on CPU FP32."""
    def __init__(self, runtime):
        import ctypes
        self.cpu_path = Path(runtime) / "libggml-cpu-haswell.so"
        self.base_path = Path(runtime) / "libggml-base.so"
        if sha(self.cpu_path) != SOURCE_Q8_CPU_SHA or sha(self.base_path) != SOURCE_Q8_BASE_SHA:
            raise ValueError("Native activation quantizer libraries differ from the proved pinned backend")
        self.cpu = ctypes.CDLL(str(self.cpu_path))
        self.base = ctypes.CDLL(str(self.base_path))
        self.quantize = self.cpu.quantize_row_q8_K
        self.dequantize = self.base.dequantize_row_q8_K
        for function in (self.quantize, self.dequantize):
            function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64]
            function.restype = None

    def roundtrip(self, array):
        import numpy as np
        if (not isinstance(array, np.ndarray) or array.dtype != np.float32 or not array.flags.c_contiguous
                or array.ndim < 1 or array.size == 0 or array.shape[-1] <= 0
                or array.shape[-1] % 256 or not np.isfinite(array).all()):
            raise ValueError("Native Q8_K requires finite contiguous CPU FP32 rows divisible by256")
        packed = np.zeros((array.size // 256, 292), dtype=np.uint8)
        output = np.empty_like(array)
        self.quantize(array.ctypes.data, packed.ctypes.data, array.size)
        self.dequantize(packed.ctypes.data, output.ctypes.data, array.size)
        if not np.isfinite(output).all():
            raise ValueError("Native Q8_K activation roundtrip became non-finite")
        return output


def native_q8_roundtrip_ste(tensor, torch, quantizer):
    class Roundtrip(torch.autograd.Function):
        @staticmethod
        def forward(ctx, value):
            if value.device.type != "cpu" or value.dtype != torch.float32:
                raise ValueError("Native Q8_K activation emulation requires CPU FP32")
            return torch.from_numpy(quantizer.roundtrip(value.detach().contiguous().numpy()))

        @staticmethod
        def backward(ctx, gradient):
            return gradient

    return Roundtrip.apply(tensor)


def install_native_q8_activation(model, torch, runtime):
    """Hook original frozen Linear inputs; LoRA's parallel path retains raw x."""
    quantizer = NativeQ8KQuantizer(runtime)
    inventory = []
    types = getattr(model, "_freehand_quantized_linear_types", {})
    if not types:
        raise ValueError("Q8_K activation emulation requires the proved quantized-base tensor inventory")
    for name, kind in sorted(types.items()):
        linear = model.get_submodule(name)
        if not isinstance(linear, torch.nn.Linear) or linear.in_features % 256 or getattr(linear, "_freehand_q8_input", False):
            raise ValueError("Q8_K hooks must be installed on unwrapped original Linear modules")
        def prehook(module, args):
            return (native_q8_roundtrip_ste(args[0], torch, quantizer), *args[1:])
        linear.register_forward_pre_hook(prehook)
        linear._freehand_q8_input = True
        inventory.append({"name": name, "weight_type": kind, "input_width": linear.in_features})
    receipt = {"activation_quantization_mode": "native-q8-k-ste-v1",
        "activation_cpu_library_sha256": sha(quantizer.cpu_path), "activation_base_library_sha256": sha(quantizer.base_path),
        "activation_linear_inventory_sha256": hashlib.sha256(json.dumps(inventory, sort_keys=True).encode("utf-8")).hexdigest(),
        "linears": inventory, "lora_input_rounded": False, "includes_tied_output_matmul": any(r["name"] == "lm_head" for r in inventory),
        "quantizer_symbol": "quantize_row_q8_K", "dequantizer_symbol": "dequantize_row_q8_K",
        "values_per_block": 256, "bytes_per_block": 292, "native_forward_equivalence_claimed": False}
    return receipt


def install_kv_roundtrip(model, torch):
    """Round only post-RoPE K and projected V before cache/attention, with STE."""
    import inspect
    import types
    from transformers.models.lfm2 import modeling_lfm2 as implementation
    if importlib.metadata.version("transformers") != "4.57.6":
        raise ValueError("KV emulation requires the pinned Transformers attention implementation")

    def rounded_forward(self, hidden_states, position_embeddings, attention_mask,
                        past_key_values=None, cache_position=None, **kwargs):
        input_shape = hidden_states.shape[:-1]
        hidden_shape = (*input_shape, -1, self.head_dim)
        query = self.q_layernorm(self.q_proj(hidden_states).view(*hidden_shape)).transpose(1, 2)
        key = self.k_layernorm(self.k_proj(hidden_states).view(*hidden_shape)).transpose(1, 2)
        value = self.v_proj(hidden_states).view(*hidden_shape).transpose(1, 2)
        cos, sin = position_embeddings
        query, key = implementation.apply_rotary_pos_emb(query, key, cos, sin)
        key = fp16_roundtrip_ste(key, torch)
        value = fp16_roundtrip_ste(value, torch)
        if past_key_values is not None:
            key, value = past_key_values.update(key, value, self.layer_idx,
                {"sin": sin, "cos": cos, "cache_position": cache_position})
        interface = implementation.eager_attention_forward
        if self.config._attn_implementation != "eager":
            interface = implementation.ALL_ATTENTION_FUNCTIONS[self.config._attn_implementation]
        output, weights = interface(self, query, key, value, attention_mask,
            dropout=0.0, scaling=self.scaling, **kwargs)
        return self.out_proj(output.reshape(*input_shape, -1).contiguous()), weights

    count = 0
    for layer in model.model.layers:
        attention = getattr(layer, "self_attn", None)
        if attention is not None:
            if not isinstance(attention, implementation.Lfm2Attention) or getattr(attention, "_freehand_kv_roundtrip", False):
                raise ValueError("KV emulation requires an unmodified LFM2 attention module")
            attention.forward = types.MethodType(rounded_forward, attention)
            attention._freehand_kv_roundtrip = True
            count += 1
    if not count:
        raise ValueError("No LFM2 attention layers available for KV emulation")
    implementation_hash = sha(Path(implementation.__file__))
    wrapper_hash = hashlib.sha256(inspect.getsource(rounded_forward).encode("utf-8")).hexdigest()
    return {"kv_roundtrip_mode": "post-rope-f16-ste-v1", "attention_layers": count,
            "kv_attention_source_sha256": hashlib.sha256((implementation_hash + ":" + wrapper_hash).encode("ascii")).hexdigest(),
            "kv_upstream_source_sha256": implementation_hash, "kv_wrapper_source_sha256": wrapper_hash,
            "query_rounded": False, "lora_input_rounded": False, "native_forward_equivalence_claimed": False}


def verify_expanded_logits(model, torch, input_ids, parent_state):
    """Compare the actual parent-rank and expanded-rank functions on one input."""
    replacements = []
    try:
        for key, value in parent_state.items():
            name, child = key.rsplit(".", 1)
            owner = model.get_submodule(name)
            replacements.append((owner, child, getattr(owner, child)))
            setattr(owner, child, torch.nn.Parameter(value, requires_grad=False))
        with torch.inference_mode():
            reference = model(torch.tensor([input_ids]), use_cache=False).logits.clone()
    finally:
        for owner, child, parameter in replacements:
            setattr(owner, child, parameter)
    with torch.inference_mode():
        expanded = model(torch.tensor([input_ids]), use_cache=False).logits
    maximum = float((reference - expanded).abs().max())
    if not torch.allclose(reference, expanded, atol=5e-4, rtol=1e-5):
        raise ValueError("Rank expansion changed initial logits beyond FP32 tolerance; maximum absolute difference=" + repr(maximum))
    return {"maximum_logit_absolute_difference": maximum, "logit_atol": 5e-4, "logit_rtol": 1e-5}


def install_lora(model, torch, rank: int, alpha: float, names=None):
    class LoRALinear(torch.nn.Module):
        def __init__(self, linear):
            super().__init__()
            self.base = linear
            self.lora_A = torch.nn.Parameter(torch.empty(rank, linear.in_features, dtype=torch.float32))
            self.lora_B = torch.nn.Parameter(torch.zeros(linear.out_features, rank, dtype=torch.float32))
            torch.nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
            self.scaling = alpha / rank

        def forward(self, x):
            base = self.base(x)
            return base + torch.nn.functional.linear(torch.nn.functional.linear(x, self.lora_A), self.lora_B) * self.scaling

    for parameter in model.parameters():
        parameter.requires_grad_(False)
    selected = []
    for name, module in list(model.named_modules()):
        if isinstance(module, torch.nn.Linear) and name.startswith("model.layers.") and (names is None or name in names):
            parent, child = name.rsplit(".", 1)
            setattr(model.get_submodule(parent), child, LoRALinear(module))
            selected.append(name)
    if not selected or (names is not None and set(selected) != set(names)):
        raise ValueError("LoRA targets are absent or disagree with saved adapter")
    return selected


def encode_rows(rows, tokenizer, max_tokens):
    prepared = []
    for row in rows:
        prompt = tokenizer.encode(row["prompt"], add_special_tokens=False)
        target = tokenizer.encode(row["masked_target"], add_special_tokens=False) + [7]
        if prompt.count(1) != 1 or prompt[0] != 1:
            raise ValueError("Production ScribeKey prompt must contain exactly one leading BOS")
        if len(prompt) + len(target) > max_tokens:
            raise ValueError(f"Complete example {row['id']} needs {len(prompt) + len(target)} tokens; cap {max_tokens}. Refusing truncation.")
        prepared.append({**row, "input_ids": prompt + target, "labels": [-100] * len(prompt) + target})
    return prepared


def value_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_unlikelihood_events(path, positive_path, rows, tokenizer, tokenizer_path=None):
    """Validate token events against the exact positive file; never add examples."""
    positive_sha = sha(Path(positive_path))
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("Unlikelihood mapping requires unique positive instance IDs")
    output = [{**row, "_unlikelihood_events": []} for row in rows]
    annotated = {row["id"]: row for row in output}
    identifiers = set()
    source_ids = set()
    mapping = []
    records = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        raise ValueError("Unlikelihood event artifact is empty")
    for record in records:
        event_id = record.get("id")
        if not isinstance(event_id, str) or not event_id or event_id in identifiers:
            raise ValueError("Missing or duplicate unlikelihood event ID")
        identifiers.add(event_id)
        source_id = record.get("source_270_id")
        if not isinstance(source_id, str) or not source_id or source_id in source_ids:
            raise ValueError("Unlikelihood source IDs must be explicit and unique")
        source_ids.add(source_id)
        if record.get("positive_artifact_sha256") != positive_sha:
            raise ValueError("Unlikelihood events are bound to a different positive artifact")
        source, gold, bad = (record.get(key) for key in ("input", "gold", "bad"))
        if any(not isinstance(value, str) or not value or any(control in value for control in ("<|", "###", "\x00"))
               for value in (source, gold, bad)) or gold == bad:
            raise ValueError("Unlikelihood source/gold/bad strings are empty, equal or contain reserved controls")
        if record.get("source_input_sha256") != text_sha(source) or record.get("approved_gold_sha256") != text_sha(gold):
            raise ValueError("Unlikelihood source/gold hash mismatch")
        prompt, masked_gold, mask = protected_pair(source, gold)
        other_prompt, masked_bad, other_mask = protected_pair(source, bad)
        if prompt != other_prompt or mask.tokens != other_mask.tokens or mask.payloads != other_mask.payloads:
            raise ValueError("Gold/bad do not share the same source-derived literal mask")
        # Require the exact multiplicity of every protected payload, including repeated quotes.
        payload_counts = {}
        for payload in mask.payloads:
            raw_payload = payload
            for ordinal, block in enumerate(mask.legacy.blocks):
                raw_payload = raw_payload.replace(mask.legacy.token_prefix + str(ordinal) + "_END", block)
            payload_counts[raw_payload] = payload_counts.get(raw_payload, 0) + 1
        if any(gold.count(payload) != count or bad.count(payload) != count for payload, count in payload_counts.items()):
            raise ValueError("Gold/bad must retain each exact protected payload once per source occurrence")
        prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)
        gold_ids = tokenizer.encode(masked_gold, add_special_tokens=False) + [7]
        bad_ids = tokenizer.encode(masked_bad, add_special_tokens=False) + [7]
        event = record.get("event")
        if not isinstance(event, dict) or event.get("manual_semantic_branch_audited") is not True:
            raise ValueError("Unlikelihood event has no audited semantic branch")
        index = event.get("target_token_index_zero_based")
        if type(index) is not int or not 0 <= index < min(len(gold_ids), len(bad_ids)):
            raise ValueError("Unlikelihood target-token index is invalid")
        gold_id, bad_id = gold_ids[index], bad_ids[index]
        if (gold_ids[:index] != bad_ids[:index] or gold_id == bad_id
                or event.get("gold_next_token_id") != gold_id or event.get("bad_next_token_id") != bad_id
                or event.get("bad_id_differs_from_gold_id") is not True
                or event.get("common_prefix_is_maximal_token_prefix") is not True):
            raise ValueError("Unlikelihood prefix or gold/bad next token IDs differ")
        if event.get("type") != ("premature_eos" if bad_id == 7 else "token"):
            raise ValueError("Unlikelihood EOS/type mismatch")
        expected = {"shared_masked_target_prefix_token_ids": gold_ids[:index],
            "shared_prefix_token_ids_sha256": value_sha(gold_ids[:index]),
            "prompt_token_count": len(prompt_ids), "chosen_forward_predictor_position_zero_based": len(prompt_ids) + index - 1,
            "input_derived_literal_count": len(mask.tokens), "literal_mapping_sha256": value_sha(list(zip(mask.tokens, mask.payloads))),
            "source_derived_prompt_sha256": text_sha(prompt), "masked_gold_sha256": text_sha(masked_gold),
            "masked_bad_sha256": text_sha(masked_bad)}
        if any(event.get(key) != value for key, value in expected.items()):
            raise ValueError("Unlikelihood prompt/mask/prefix/index fingerprint differs")
        row_ids = record.get("positive_row_ids", [record.get("positive_row_id")])
        if (not isinstance(row_ids, list) or not row_ids
                or any(not isinstance(identity, str) or identity not in by_id for identity in row_ids)
                or len(set(row_ids)) != len(row_ids)):
            raise ValueError("Unlikelihood positive instance IDs are missing, duplicate or unknown")
        for identity in row_ids:
            row = annotated[identity]
            if row.get("positive_replay_instance", {}).get("source_id", source_id) != source_id:
                raise ValueError("Unlikelihood positive instance has a different disclosed source ID")
            if row["input"] != source or row["target"] != gold or row["prompt"] != prompt or row["masked_target"] != masked_gold:
                raise ValueError("Unlikelihood event text differs from its positive instance")
            if row["input_ids"] != prompt_ids + gold_ids or row["labels"] != [-100] * len(prompt_ids) + gold_ids:
                raise ValueError("Unlikelihood event tokenization differs from its positive instance")
            if row["_unlikelihood_events"]:
                raise ValueError("Multiple unlikelihood events mapped to one positive instance")
            mapped = {"target_token_index": index, "bad_token_id": bad_id, "gold_token_id": gold_id,
                "predictor_position": len(prompt_ids) + index - 1, "event_id": event_id, "source_id": source_id}
            row["_unlikelihood_events"].append(mapped)
            mapping.append({"positive_row_id": identity, **mapped})
    # All explicitly disclosed copies of a selected source must carry its event.
    for row in output:
        exposure = row.get("positive_replay_instance", {})
        if exposure.get("source_id") in source_ids and not row["_unlikelihood_events"]:
            raise ValueError("A scheduled exposure of a selected source lacks its unlikelihood event")
    tokenizer_identity = sha(Path(tokenizer_path)) if tokenizer_path else value_sha(tokenizer.get_vocab())
    identity = {"unlikelihood_schema": UNLIKELIHOOD_SCHEMA, "unlikelihood_events_sha256": sha(Path(path)),
        "unlikelihood_positive_sha256": positive_sha, "unlikelihood_tokenizer_sha256": tokenizer_identity,
        "unlikelihood_mapping_sha256": value_sha(sorted(mapping, key=lambda value: value["positive_row_id"])),
        "unlikelihood_source_sha256": sha(Path(__file__))}
    return output, identity


def batch_tensors(rows, torch):
    size = max(len(row["input_ids"]) for row in rows)
    ids = torch.zeros((len(rows), size), dtype=torch.long)
    labels = torch.full((len(rows), size), -100, dtype=torch.long)
    attention = torch.zeros_like(ids)
    for ordinal, row in enumerate(rows):
        length = len(row["input_ids"])
        ids[ordinal, :length] = torch.tensor(row["input_ids"])
        labels[ordinal, :length] = torch.tensor(row["labels"])
        attention[ordinal, :length] = 1
    return ids, labels, attention


def assistant_event_indices(rows, labels, torch):
    """Map target indices to the existing row-major selected-logit matrix."""
    events = []
    offset = 0
    for ordinal, row in enumerate(rows):
        positions = torch.nonzero(labels[ordinal, 1:] != -100, as_tuple=False).flatten().tolist()
        targets = labels[ordinal, 1:][labels[ordinal, 1:] != -100]
        for event in row.get("_unlikelihood_events", []):
            index = event["target_token_index"]
            if (type(index) is not int or not 0 <= index < len(positions)
                    or positions[index] != event["predictor_position"]
                    or int(targets[index]) != event["gold_token_id"]
                    or event["bad_token_id"] == event["gold_token_id"]):
                raise ValueError("Unlikelihood event does not point to its chosen assistant logit")
            events.append((offset + index, event["bad_token_id"]))
        offset += len(positions)
    return events


def chosen_token_loss(logits, targets, events, eta, torch, metrics=None):
    if not math.isfinite(eta) or not 0 <= eta <= 2:
        raise ValueError("Unlikelihood eta must be finite and between0and2")
    if logits.ndim != 2 or targets.ndim != 1 or logits.shape[0] != targets.numel() or not targets.numel():
        raise ValueError("Chosen assistant logits/targets have invalid shapes")
    tokens = targets.numel()
    # Keep this exact historical mean-CE operation for eta0 and unmarked batches.
    if eta == 0 or not events:
        loss = torch.nn.functional.cross_entropy(logits.float(), targets)
        if metrics is not None:
            metrics.update(assistant_tokens=tokens, event_count=len(events), eta=eta,
                ce_mean=float(loss.detach()), ul_sum=0.0, ul_evaluated=False)
        return loss
    indices, bad_ids = zip(*events)
    if (len(set(events)) != len(events) or any(type(i) is not int or not 0 <= i < tokens for i in indices)
            or any(type(i) is not int or not 0 <= i < logits.shape[1] for i in bad_ids)
            or any(int(targets[i]) == bad for i, bad in events)):
        raise ValueError("Unlikelihood selected-logit index or rejected token is invalid")
    marked = logits[list(indices)].float()
    if not torch.isfinite(marked).all():
        raise ValueError("Unlikelihood marked logits must be finite")
    excluded = marked.clone()
    excluded[torch.arange(len(events)), list(bad_ids)] = -torch.inf
    penalties = torch.logsumexp(marked, dim=-1) - torch.logsumexp(excluded, dim=-1)
    ce_sum = torch.nn.functional.cross_entropy(logits.float(), targets, reduction="sum")
    ul_sum = penalties.sum()
    loss = (ce_sum + eta * ul_sum) / tokens
    if not torch.isfinite(loss) or not torch.isfinite(penalties).all():
        raise ValueError("Unlikelihood objective is not finite")
    if metrics is not None:
        metrics.update(assistant_tokens=tokens, event_count=len(events), eta=eta,
            ce_sum=float(ce_sum.detach()), ul_sum=float(ul_sum.detach()), ul_evaluated=True)
    return loss


def assistant_loss(model, rows, torch, unlikelihood_eta=0.0, metrics=None):
    ids, labels, attention = batch_tensors(rows, torch)
    hidden = model.model(input_ids=ids, attention_mask=attention, use_cache=False).last_hidden_state
    selected = labels[:, 1:] != -100
    # Avoid allocating vocabulary logits for masked prompt/padding positions.
    logits = model.lm_head(hidden[:, :-1, :][selected])
    targets = labels[:, 1:][selected]
    events = assistant_event_indices(rows, labels, torch) if (unlikelihood_eta or metrics is not None) else []
    loss = chosen_token_loss(logits, targets, events, unlikelihood_eta, torch, metrics)
    return loss, int(selected.sum().item())


def adapter_state(model):
    return {key: value.detach().cpu().contiguous() for key, value in model.state_dict().items()
            if key.endswith((".lora_A", ".lora_B"))}


def packages():
    return {name: importlib.metadata.version(name) for name in ["torch", "transformers", "safetensors", "tokenizers"]}


RESUME_CONFIG_KEYS = ("base_model_sha256", "rank", "alpha", "target_modules", "seed", "train_sha256",
    "train_rows", "epochs", "batch_size", "gradient_accumulation", "learning_rate", "max_tokens", "threads",
    "warmup_steps", "effective_warmup_steps", "schedule_total_optimizer_steps",
    "training_base_mode", "frozen_base_sha256", "original_bf16_sha256", "base_config_sha256", "tokenizer_sha256",
    "gguf_dequantizer_sha256", "gguf_mapping_sha256", "parent_adapter_sha256", "parent_adapter_config_sha256",
    "rank_expansion", "kv_roundtrip_mode", "kv_attention_source_sha256", "quantized_training_source_sha256",
    "activation_quantization_mode", "activation_cpu_library_sha256", "activation_base_library_sha256",
    "activation_linear_inventory_sha256", "unlikelihood_schema", "unlikelihood_events_sha256",
    "unlikelihood_positive_sha256", "unlikelihood_tokenizer_sha256", "unlikelihood_mapping_sha256",
    "unlikelihood_eta", "unlikelihood_source_sha256")


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path, value):
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def save_resume_checkpoint(model, optimizer, torch, output, config, event):
    """Commit a complete checkpoint directory before updating its latest pointer."""
    from safetensors.torch import save_file
    step, micro = int(event["step"]), int(event["microbatch"])
    accumulation = config.get("gradient_accumulation", 1)
    total_micro = config.get("epochs", 1) * math.ceil(config.get("train_rows", micro) / config.get("batch_size", 1))
    if step < 1 or micro < step or (micro % accumulation and micro != total_micro):
        raise ValueError("Resume checkpoints require a complete optimizer-step boundary")
    output = Path(output)
    parent = output / "checkpoints"
    parent.mkdir(exist_ok=True)
    final = parent / f"step-{step:06d}"
    pending = parent / f"step-{step:06d}.partial"
    if final.exists() or pending.exists():
        raise ValueError("Preserve an existing checkpoint generation")
    pending.mkdir()
    state_tensors = adapter_state(model)
    if not state_tensors or not all(torch.isfinite(value).all() for value in state_tensors.values()):
        raise ValueError("Adapter checkpoint is empty or non-finite")
    save_file(state_tensors, str(pending / "adapter.safetensors"))
    torch.save(optimizer.state_dict(), pending / "optimizer.pt")
    torch.save({"torch_cpu": torch.get_rng_state(), "python_random": random.getstate()}, pending / "rng.pt")
    write_json(pending / "adapter-config.json", config)
    shutil.copyfile(output / "training-source.py", pending / "training-source.py")
    if sha(pending / "training-source.py") != config["training_source_sha256"]:
        raise ValueError("Executed source snapshot differs from checkpoint configuration")
    files = {}
    for name in ["adapter.safetensors", "optimizer.pt", "rng.pt", "adapter-config.json", "training-source.py"]:
        path = pending / name
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
        files[name] = {"bytes": path.stat().st_size, "sha256": sha(path)}
    state = {"schema_version": 1, "producer": "Freehand.Cleanup.Training.checkpoint.v1",
             "global_step": step, "global_microbatch": micro, "epoch": int(event["epoch"]),
             "assistant_tokens": int(event["assistant_tokens"]), "elapsed_seconds": float(event["seconds"]),
             "learning_rate": float(event["lr"]), "rng_states_stored": True, "files": files,
             "train_sha256": config["train_sha256"],
             "schedule_total_optimizer_steps": config.get("schedule_total_optimizer_steps"),
             "effective_warmup_steps": config.get("effective_warmup_steps")}
    _atomic_json(pending / "resume-state.json", state)
    os.replace(pending, final)
    _fsync_directory(parent)
    _atomic_json(output / "latest-checkpoint.json", {"directory": str(final.resolve()), "global_step": step,
                 "resume_state_sha256": sha(final / "resume-state.json")})
    # Convenient aliases are hardlinks; the directory/manifest remains the commit boundary.
    for source, name in [("adapter.safetensors", "checkpoint.safetensors"), ("optimizer.pt", "checkpoint.optimizer.pt")]:
        temporary = output / (name + ".partial")
        os.link(final / source, temporary)
        os.replace(temporary, output / name)
    if step % 128 == 0:
        snapshot = output / "snapshots" / f"step-{step:06d}"
        snapshot.mkdir(parents=True)
        for name in ["adapter.safetensors", "adapter-config.json", "training-source.py", "resume-state.json"]:
            os.link(final / name, snapshot / name)
        _fsync_directory(snapshot)
        _fsync_directory(snapshot.parent)
    # Keep two complete recovery generations; immutable adapter snapshots retain their inodes.
    generations = sorted(path for path in parent.glob("step-*") if path.is_dir() and not path.name.endswith(".partial"))
    for old in generations[:-2]:
        metadata = json.loads((old / "resume-state.json").read_text())
        if metadata.get("producer") != state["producer"]:
            raise ValueError("Refusing to expire an unowned checkpoint directory")
        shutil.rmtree(old)
    return final


def load_resume_checkpoint(model, optimizer, torch, path, expectedconfig, *, allow_legacy_rng=False):
    """Verify all saved bytes/config, then restore adapters, optimizer and RNG."""
    from safetensors.torch import load_file
    path = Path(path)
    state = json.loads((path / "resume-state.json").read_text())
    required = {"adapter.safetensors", "optimizer.pt", "adapter-config.json", "training-source.py"}
    if state.get("rng_states_stored"):
        required.add("rng.pt")
    elif not allow_legacy_rng or state.get("producer") != "freehand-training-legacy-recovery-v1":
        raise ValueError("Checkpoint has no saved RNG state; explicit deterministic legacy recovery is required")
    if set(state["files"]) != required:
        raise ValueError("Checkpoint file inventory differs")
    for name, entry in state["files"].items():
        item = path / name
        if item.stat().st_size != entry["bytes"] or sha(item) != entry["sha256"]:
            raise ValueError("Checkpoint byte hash mismatch: " + name)
    saved = json.loads((path / "adapter-config.json").read_text())
    if sha(path / "training-source.py") != saved["training_source_sha256"]:
        raise ValueError("Checkpoint source/configuration binding mismatch")
    for key in RESUME_CONFIG_KEYS:
        if key in expectedconfig or key in saved:
            if expectedconfig.get(key) != saved.get(key):
                raise ValueError("Checkpoint configuration mismatch: " + key)
    micro, step = int(state["global_microbatch"]), int(state["global_step"])
    accumulation = saved.get("gradient_accumulation", 1)
    total_micro = saved.get("epochs", 1) * math.ceil(saved.get("train_rows", micro) / saved.get("batch_size", 1))
    if micro < step or step < 1 or (micro % accumulation and micro != total_micro):
        raise ValueError("Checkpoint is not an optimizer-step boundary")
    if step != math.ceil(micro / accumulation):
        raise ValueError("Checkpoint global step/microbatch position mismatch")
    tensors = load_file(str(path / "adapter.safetensors"))
    parameters = dict(model.named_parameters())
    if set(tensors) != set(adapter_state(model)):
        raise ValueError("Resume adapter tensor inventory mismatch")
    with torch.no_grad():
        for key, value in tensors.items():
            if value.shape != parameters[key].shape or not torch.isfinite(value).all():
                raise ValueError("Resume adapter tensor shape/value mismatch")
            parameters[key].copy_(value)
    optimizer.load_state_dict(torch.load(path / "optimizer.pt", map_location="cpu", weights_only=True))
    optimizer_steps = [int(value["step"].item() if hasattr(value["step"], "item") else value["step"])
                       for value in optimizer.state.values() if "step" in value]
    if optimizer_steps and any(value != step for value in optimizer_steps):
        raise ValueError("Optimizer state/global step mismatch")
    if state.get("rng_states_stored"):
        rng = torch.load(path / "rng.pt", map_location="cpu", weights_only=True)
        torch.set_rng_state(rng["torch_cpu"])
        random.setstate(rng["python_random"])
        state["rng_restore_mode"] = "exact_saved_torch_cpu_and_python"
    else:
        # Legacy source is preserved; its model/optimizer contain no stochastic operations.
        # Epoch ordering is reconstructed by independent Random(seed+epoch) instances.
        state["rng_restore_mode"] = "legacy_deterministic_no_stochastic_training_operations"
    state["resume_state_sha256"] = sha(path / "resume-state.json")
    state["source_training_code_sha256"] = saved["training_source_sha256"]
    return state


def train(args):
    if args.output.exists():
        raise ValueError("Output must be a fresh directory")
    args.output.mkdir(parents=True)
    shutil.copyfile(Path(__file__), args.output / "training-source.py")
    raw = load_data(args.train)
    if any(row.get("split") not in (None, "train") for row in raw):
        raise ValueError("Training file contains a non-training split")
    random.seed(args.seed)
    quantized = args.training_base_mode == TRAINING_MODE_GGUF
    if quantized:
        torch, _, save_file, tokenizer, model = quantized_base_model(args.base, args.gguf_base, args.threads)
    else:
        torch, _, save_file, tokenizer, model = base_model(args.base, args.threads)
    extra_config = dict(getattr(model, "_freehand_base_identity", {}))
    activation_receipt = None
    if args.activation_quantization == "native-q8-k":
        activation_receipt = install_native_q8_activation(model, torch, args.native_runtime)
        extra_config.update({key: activation_receipt[key] for key in ("activation_quantization_mode",
            "activation_cpu_library_sha256", "activation_base_library_sha256", "activation_linear_inventory_sha256")})
    elif quantized:
        extra_config["activation_quantization_mode"] = "none"
    kv_receipt = None
    if args.kv_roundtrip == "f16":
        kv_receipt = install_kv_roundtrip(model, torch)
        extra_config.update({key: kv_receipt[key] for key in ("kv_roundtrip_mode", "kv_attention_source_sha256")})
    elif quantized:
        extra_config["kv_roundtrip_mode"] = "none"
    if quantized:
        write_json(args.output / "frozen-base-provenance.json", {**model._freehand_base_receipt,
            "kv_roundtrip_mode": extra_config["kv_roundtrip_mode"], "kv_emulation_receipt": kv_receipt,
            "activation_emulation_receipt": activation_receipt})
    torch.manual_seed(args.seed)
    rows = encode_rows(raw, tokenizer, args.max_tokens)
    unlikelihood_config = {}
    if args.unlikelihood_events:
        rows, unlikelihood_config = load_unlikelihood_events(args.unlikelihood_events, args.train, rows, tokenizer,
                                                           args.base / "tokenizer.json")
        unlikelihood_config["unlikelihood_eta"] = args.unlikelihood_eta
        write_json(args.output / "unlikelihood-provenance.json", {**unlikelihood_config,
            "canonical_event_count": len({event["event_id"] for row in rows for event in row["_unlikelihood_events"]}),
            "positive_exposures_with_events": sum(bool(row["_unlikelihood_events"]) for row in rows),
            "positive_rows_added": 0, "loss": "(sum CE_assistant + eta * sum UL_events) / N_assistant",
            "same_chosen_forward": True, "extra_reference_or_rejected_forward": False,
            "gradient_accumulation_scope": "Unchanged per-microbatch normalization then existing accumulation divisor"})
    model.eval()
    with torch.inference_mode():
        before = model(torch.tensor([rows[0]["input_ids"]]), use_cache=False).logits.clone()
    targets = install_lora(model, torch, args.rank, args.alpha)
    with torch.inference_mode():
        after = model(torch.tensor([rows[0]["input_ids"]]), use_cache=False).logits
    if not torch.equal(before, after):
        raise ValueError("Zero-initialized LoRA changed baseline logits")
    del before, after
    resume_sha = None
    expansion = None
    if args.resume_adapter:
        old_config = json.loads((args.resume_adapter / "adapter-config.json").read_text())
        if (old_config["base_model_sha256"] != SOURCE_WEIGHT_SHA or old_config["target_modules"] != targets):
            raise ValueError("Resume adapter configuration differs from this run")
        if not quantized and old_config.get("training_base_mode", "original-bf16") != "original-bf16":
            raise ValueError("A quantized-base adapter cannot initialize the original BF16 training route")
        if quantized and old_config.get("training_base_mode", "original-bf16") not in ("original-bf16", TRAINING_MODE_GGUF):
            raise ValueError("Parent adapter training mode differs")
        if old_config.get("training_base_mode") == TRAINING_MODE_GGUF and old_config.get("frozen_base_sha256") != SOURCE_GGUF_SHA:
            raise ValueError("Parent adapter quantized base differs")
        resume_sha = sha(args.resume_adapter / "adapter.safetensors")
        if args.parent_adapter_sha256 and resume_sha != args.parent_adapter_sha256:
            raise ValueError("Parent adapter SHA256 differs from the explicitly selected parent")
        from safetensors.torch import load_file
        state = load_file(str(args.resume_adapter / "adapter.safetensors"))
        parent_state = state
        if args.expand_adapter_rank:
            state, expansion = expand_adapter_state(state, old_config["rank"], old_config["alpha"],
                                                    args.rank, args.alpha, args.seed, torch)
        elif old_config["rank"] != args.rank or old_config["alpha"] != args.alpha:
            raise ValueError("Parent rank/alpha differ; explicit rank expansion is required")
        expected = set(adapter_state(model))
        if set(state) != expected:
            raise ValueError("Resume adapter tensor keys differ")
        parameters = dict(model.named_parameters())
        with torch.no_grad():
            for key, value in state.items():
                if parameters[key].shape != value.shape or value.dtype != torch.float32 or not torch.isfinite(value).all():
                    raise ValueError("Parent adapter tensor shape/dtype/value differs")
                parameters[key].copy_(value)
        if expansion:
            expansion.update(verify_expanded_logits(model, torch, rows[0]["input_ids"], parent_state))
        if quantized:
            extra_config.update(parent_adapter_sha256=resume_sha,
                parent_adapter_config_sha256=sha(args.resume_adapter / "adapter-config.json"), rank_expansion=expansion)
    elif quantized and args.resume_checkpoint:
        saved_identity = json.loads((args.resume_checkpoint / "adapter-config.json").read_text())
        extra_config.update(parent_adapter_sha256=args.parent_adapter_sha256,
            parent_adapter_config_sha256=saved_identity.get("parent_adapter_config_sha256"),
            rank_expansion=saved_identity.get("rank_expansion"))
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    total_micro = args.epochs * math.ceil(len(rows) / args.batch_size)
    total_steps = math.ceil(total_micro / args.gradient_accumulation)
    warmup = min(args.warmup_steps, total_steps // 10)
    config = {"schema_version": 1, "base_path": str(args.base.resolve()), "base_model_sha256": SOURCE_WEIGHT_SHA,
              "rank": args.rank, "alpha": args.alpha, "scaling": args.alpha / args.rank,
              "target_modules": targets, "seed": args.seed, "train_sha256": sha(args.train),
              "train_rows": len(rows), "trainable_parameters": sum(p.numel() for p in trainable),
              "epochs": args.epochs, "batch_size": args.batch_size, "gradient_accumulation": args.gradient_accumulation,
              "learning_rate": args.learning_rate, "max_tokens": args.max_tokens, "threads": args.threads,
              "dtype": "float32", "packages": packages(), "literal_protocol": PROTOCOL,
              "assistant_only_loss": True, "zero_adapter_exact_logit_identity": True,
              "training_source_sha256": sha(Path(__file__)), "optimizer": "AdamW", "weight_decay": 0,
              "warmup_steps": args.warmup_steps, "checkpoint_every_steps": args.checkpoint_every,
              "effective_warmup_steps": warmup, "schedule_total_optimizer_steps": total_steps,
              "planned_execution_steps": min(total_steps, args.max_steps) if args.max_steps else total_steps,
              "learning_rate_schedule": "Linear warmup then linear decay, floored at0.1of initial learning rate; exact per-step values retained in log",
              "resume_adapter_sha256": resume_sha, "resume_optimizer": False,
              "full_examples_truncated": 0, "blind_evaluation_read": False, **extra_config, **unlikelihood_config}
    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate, weight_decay=0)
    resumed = None
    if args.resume_checkpoint:
        resumed = load_resume_checkpoint(model, optimizer, torch, args.resume_checkpoint, config,
                                          allow_legacy_rng=args.allow_deterministic_legacy_resume)
        config.update(resume_checkpoint=str(args.resume_checkpoint.resolve()),
                      resume_optimizer=True,
                      resume_checkpoint_state_sha256=resumed["resume_state_sha256"],
                      resume_global_step=resumed["global_step"],
                      resume_global_microbatch=resumed["global_microbatch"],
                      resume_rng_restore_mode=resumed["rng_restore_mode"],
                      resume_source_training_code_sha256=resumed["source_training_code_sha256"])
    write_json(args.output / "adapter-config.json", config)
    optimizer.zero_grad(set_to_none=True)
    start = time.monotonic()
    consumed_tokens = resumed["assistant_tokens"] if resumed else 0
    micro = resumed["global_microbatch"] if resumed else 0
    step = resumed["global_step"] if resumed else 0
    resumed_micro = micro
    resumed_seconds = resumed["elapsed_seconds"] if resumed else 0
    step_loss_sum = step_micro_count = 0
    step_objective_components = []
    model.train()
    with (args.output / "training-log.jsonl").open("x", encoding="utf-8", buffering=1) as log:
        for epoch in range(args.epochs):
            order = list(range(len(rows)))
            random.Random(args.seed + epoch).shuffle(order)
            # Sort small random buckets to reduce padding, while retaining epoch shuffling.
            bucketed = []
            for at in range(0, len(order), 64):
                bucketed.extend(sorted(order[at:at + 64], key=lambda i: len(rows[i]["input_ids"])))
            for at in range(0, len(bucketed), args.batch_size):
                ordinal_micro = epoch * math.ceil(len(rows) / args.batch_size) + at // args.batch_size
                if ordinal_micro < resumed_micro:
                    continue
                batch = [rows[i] for i in bucketed[at:at + args.batch_size]]
                if args.unlikelihood_events:
                    components = {}
                    loss, tokens = assistant_loss(model, batch, torch, args.unlikelihood_eta, components)
                    step_objective_components.append(components)
                else:
                    loss, tokens = assistant_loss(model, batch, torch)
                if not torch.isfinite(loss):
                    raise ValueError("Non-finite training loss")
                group_size = min(args.gradient_accumulation,
                                 total_micro - (micro // args.gradient_accumulation) * args.gradient_accumulation)
                (loss / group_size).backward()
                step_loss_sum += loss.item()
                step_micro_count += 1
                consumed_tokens += tokens
                micro += 1
                if micro % args.gradient_accumulation == 0 or micro == total_micro:
                    norm = torch.nn.utils.clip_grad_norm_(trainable, 1.0)
                    if not torch.isfinite(norm):
                        raise ValueError("Non-finite gradient norm")
                    step += 1
                    ratio = (step / warmup) if step <= warmup and warmup else max(0.1, (total_steps - step + 1) / max(1, total_steps - warmup))
                    for group in optimizer.param_groups:
                        group["lr"] = args.learning_rate * ratio
                    optimizer.step()
                    optimizer.zero_grad(set_to_none=True)
                    event = {"epoch": epoch + 1, "step": step, "microbatch": micro, "loss": step_loss_sum / step_micro_count,
                             "lr": optimizer.param_groups[0]["lr"], "gradient_norm": norm.item(),
                             "assistant_tokens": consumed_tokens, "seconds": resumed_seconds + time.monotonic() - start}
                    if args.unlikelihood_events:
                        event["objective_microbatches"] = step_objective_components
                        event["unlikelihood_eta"] = args.unlikelihood_eta
                    log.write(json.dumps(event) + "\n")
                    print(json.dumps(event), flush=True)
                    step_loss_sum = step_micro_count = 0
                    step_objective_components = []
                    if args.checkpoint_every and step % args.checkpoint_every == 0:
                        save_resume_checkpoint(model, optimizer, torch, args.output, config, event)
                    if args.max_steps and step >= args.max_steps:
                        break
            if args.max_steps and step >= args.max_steps:
                break
    save_file(adapter_state(model), str(args.output / "adapter.safetensors"), metadata={"base_sha256": SOURCE_WEIGHT_SHA})
    torch.save(optimizer.state_dict(), args.output / "optimizer.pt")
    write_json(args.output / "training-result.json", {"steps": step, "microbatches": micro,
               "assistant_tokens": consumed_tokens, "seconds": resumed_seconds + time.monotonic() - start,
               "session_seconds": time.monotonic() - start,
               "adapter_sha256": sha(args.output / "adapter.safetensors"), "completed": True,
               "max_steps_limited": bool(args.max_steps), "whole_app_sla_verified": False})


def merge(args):
    config = json.loads((args.adapter / "adapter-config.json").read_text())
    if config.get("training_base_mode", "original-bf16") != "original-bf16":
        raise ValueError("Quantized-base adapters require their exact unmerged native base; BF16 merge is invalid")
    if args.output.exists():
        raise ValueError("Merged output must be fresh")
    args.output.mkdir(parents=True)
    torch, load_file, save_file, _, _ = imports(args.threads)
    if sha(args.base / "model.safetensors") != config["base_model_sha256"] or config["base_model_sha256"] != SOURCE_WEIGHT_SHA:
        raise ValueError("Adapter base hash mismatch")
    adapters = load_file(str(args.adapter / "adapter.safetensors"))
    base = load_file(str(args.base / "model.safetensors"))
    output_dtype = {"bfloat16": torch.bfloat16, "float16": torch.float16}[args.dtype]
    used = set()
    rounding = {"updated_elements": 0, "nonzero_float32_updates": 0, "stored_elements_changed_from_base": 0}
    with torch.no_grad():
        for name in config["target_modules"]:
            a_key, b_key, weight = name + ".lora_A", name + ".lora_B", name + ".weight"
            a, b = adapters[a_key], adapters[b_key]
            if a.shape[0] != config["rank"] or b.shape[1] != config["rank"]:
                raise ValueError("Adapter rank mismatch")
            delta = (b.float() @ a.float()) * config["scaling"]
            if delta.shape != base[weight].shape or not torch.isfinite(delta).all():
                raise ValueError("Adapter shape/value mismatch")
            original = base[weight].float()
            stored = (original + delta).to(output_dtype).contiguous()
            if not torch.isfinite(stored).all():
                raise ValueError("Merged tensor is not finite at requested precision")
            rounding["updated_elements"] += delta.numel()
            rounding["nonzero_float32_updates"] += int(torch.count_nonzero(delta).item())
            rounding["stored_elements_changed_from_base"] += int(torch.count_nonzero(stored != original.to(output_dtype)).item())
            base[weight] = stored
            used.update([a_key, b_key])
    if set(adapters) != used:
        raise ValueError("Unused or missing adapter tensors")
    base = {key: value.to(output_dtype).contiguous() for key, value in base.items()}
    save_file(base, str(args.output / "model.safetensors"), metadata={"format": "pt"})
    for path in args.base.iterdir():
        if path.is_file() and path.name != "model.safetensors":
            shutil.copyfile(path, args.output / path.name)
    original_config = json.loads((args.base / "config.json").read_text())
    merged_config = dict(original_config)
    configuration_changes = {}
    if original_config.get("dtype") != args.dtype:
        configuration_changes["dtype"] = {"before": original_config.get("dtype"), "after": args.dtype}
        merged_config["dtype"] = args.dtype
    if "torch_dtype" in merged_config and merged_config["torch_dtype"] != args.dtype:
        configuration_changes["torch_dtype"] = {"before": merged_config["torch_dtype"], "after": args.dtype}
        merged_config["torch_dtype"] = args.dtype
    if configuration_changes:
        # Only this newly owned derivative config is replaced; original files stay untouched.
        (args.output / "config.json").write_text(json.dumps(merged_config, indent=2) + "\n")
    rounding["stored_update_survival_fraction"] = (rounding["stored_elements_changed_from_base"] /
             rounding["nonzero_float32_updates"]) if rounding["nonzero_float32_updates"] else None
    write_json(args.output / "freehand-training-provenance.json", {
        "base_model_sha256": SOURCE_WEIGHT_SHA, "adapter_sha256": sha(args.adapter / "adapter.safetensors"),
        "adapter_config_sha256": sha(args.adapter / "adapter-config.json"),
        "merged_model_sha256": sha(args.output / "model.safetensors"), "dtype": args.dtype,
        "source_code_sha256": sha(Path(__file__)), "merge_formula": "W + (B @ A) * alpha/rank",
        "tokenizer_and_configuration_changed": bool(configuration_changes),
        "tokenizer_changed": False, "configuration_changes": configuration_changes,
        "rounding": rounding,
        "display_credit": "Derived from ScribeKey Fast by ScribeKey"})
    print(json.dumps({"merged": str(args.output), "weights_sha256": sha(args.output / "model.safetensors")}))


def profile(args):
    """Probe exact known publisher case, zero-adapter identity and CPU backward cost."""
    if args.output.exists():
        raise ValueError("Profile output must be fresh")
    args.output.mkdir(parents=True)
    torch, _, _, tokenizer, model = base_model(args.base, args.threads)
    source = "um can you send the updated agenda before lunch"
    target = "Can you send the updated agenda before lunch?"
    prompt, masked_target, _ = protected_pair(source, target)
    prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)
    assert prompt_ids[0] == 1 and prompt_ids.count(1) == 1
    model.eval()
    inference_start = time.monotonic()
    with torch.inference_mode():
        generated = model.generate(input_ids=torch.tensor([prompt_ids]), max_new_tokens=64,
                                   do_sample=False, use_cache=True, eos_token_id=7, pad_token_id=0)
    result = tokenizer.decode(generated[0, len(prompt_ids):], skip_special_tokens=True,
                              clean_up_tokenization_spaces=False).split("###", 1)[0].strip()
    if result != target:
        write_json(args.output / "profile-failed.json", {"known_source": source, "expected": target,
                   "generated": result, "packages": packages(), "reason": "Original Transformers generation differs from known BF16/native case"})
        raise ValueError("Original checkpoint known-case generation mismatch: " + repr(result))
    row = encode_rows([{"id": "profile-001", "prompt": prompt, "masked_target": masked_target}], tokenizer, 1024)[0]
    with torch.inference_mode():
        before = model(torch.tensor([row["input_ids"]]), use_cache=False).logits.clone()
    torch.manual_seed(42)
    targets = install_lora(model, torch, args.rank, args.alpha)
    with torch.inference_mode():
        after = model(torch.tensor([row["input_ids"]]), use_cache=False).logits
    identical = torch.equal(before, after)
    if not identical:
        raise ValueError("Zero adapter changed baseline logits")
    del before, after
    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=0.0002, weight_decay=0)
    model.train()
    timings = []
    for ordinal in range(args.steps):
        start = time.monotonic()
        optimizer.zero_grad(set_to_none=True)
        loss, tokens = assistant_loss(model, [row], torch)
        loss.backward()
        gradient = torch.nn.utils.clip_grad_norm_(trainable, 1.0)
        optimizer.step()
        event = {"step": ordinal + 1, "seconds": time.monotonic() - start, "assistant_tokens": tokens,
                 "loss": loss.item(), "gradient_norm": gradient.item()}
        timings.append(event)
        print(json.dumps(event), flush=True)
    report = {"packages": packages(), "known_case": {"input": source, "expected": target, "generated": result},
              "zero_adapter_exact_logit_identity": identical, "training_dtype": "float32", "threads": args.threads,
              "target_modules": targets, "trainable_parameters": sum(p.numel() for p in trainable),
              "steps": timings, "max_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
              "profile_only": True, "training_adapter_retained": False}
    write_json(args.output / "profile-result.json", report)
    print(json.dumps(report), flush=True)


def generate(args):
    """Diagnostic Transformers generation, separate from production Core replay."""
    if args.adapter:
        adapter_config = json.loads((args.adapter / "adapter-config.json").read_text())
        if adapter_config.get("training_base_mode", "original-bf16") != "original-bf16":
            raise ValueError("This legacy HF generation command cannot reconstruct a quantized adapter base")
    if args.output.exists():
        raise ValueError("Generation output must be fresh")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    seen = set()
    for line in args.input.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if not isinstance(row.get("id"), str) or row["id"] in seen or not isinstance(row.get("input"), str):
                raise ValueError("Generation input requires unique ids and string inputs")
            seen.add(row["id"])
            # Targets/expected strings, if present in this file, are not used.
            rows.append({"id": row["id"], "input": row["input"]})
    torch, load_file, _, tokenizer, model = base_model(args.base, args.threads)
    adapter_sha = None
    if args.adapter:
        config = json.loads((args.adapter / "adapter-config.json").read_text())
        if config["base_model_sha256"] != SOURCE_WEIGHT_SHA:
            raise ValueError("Adapter was trained from a different base")
        install_lora(model, torch, config["rank"], config["alpha"], config["target_modules"])
        tensors = load_file(str(args.adapter / "adapter.safetensors"))
        if set(tensors) != set(adapter_state(model)):
            raise ValueError("Adapter tensor inventory mismatch")
        parameters = dict(model.named_parameters())
        with torch.no_grad():
            for key, value in tensors.items():
                if not torch.isfinite(value).all() or parameters[key].shape != value.shape:
                    raise ValueError("Adapter tensor shape/value mismatch")
                parameters[key].copy_(value)
        adapter_sha = sha(args.adapter / "adapter.safetensors")
    model.eval()
    failures = 0
    start = time.monotonic()
    with args.output.open("x", encoding="utf-8", buffering=1) as stream:
        for index, row in enumerate(rows):
            event = {**row, "runtime": "Transformers-research-not-Core", "raw_output": None,
                     "candidate": None, "selected_output": row["input"], "failed": False,
                     "literal_protocol": PROTOCOL, "reference_target_used": False}
            item_start = time.monotonic()
            try:
                mask = SpecialistLiteralMask.create(row["input"])
                prompt = PREFIX + mask.masked_text + SUFFIX
                ids = tokenizer.encode(prompt, add_special_tokens=False)
                if ids.count(1) != 1 or ids[0] != 1 or len(ids) + args.max_output > 1024:
                    raise ValueError("Complete prompt/output budget or leading BOS invalid")
                with torch.inference_mode():
                    generated = model.generate(input_ids=torch.tensor([ids]), do_sample=False,
                                               max_new_tokens=args.max_output, use_cache=True,
                                               eos_token_id=7, pad_token_id=0)
                tokens = generated[0, len(ids):].tolist()
                ended = bool(tokens and tokens[-1] == 7)
                if ended:
                    tokens = tokens[:-1]
                raw = tokenizer.decode(tokens, skip_special_tokens=False, clean_up_tokenization_spaces=False)
                event["raw_output"] = raw
                delimiter = raw.find("###")
                if delimiter >= 0:
                    raw = raw[:delimiter]
                    ended = True
                if not ended or not raw.strip() or "<|" in raw:
                    raise ValueError("Incomplete, empty or reserved-control generation")
                candidate = mask.restore(raw)
                event.update(candidate=candidate, selected_output=candidate, prompt_tokens=len(ids),
                             generated_tokens=len(tokens), complete=True)
            except (ValueError, RuntimeError) as error:
                event.update(failed=True, failure_code=type(error).__name__, failure_message=str(error), complete=False)
                failures += 1
            event["milliseconds"] = (time.monotonic() - item_start) * 1000
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            if (index + 1) % 25 == 0:
                print(json.dumps({"completed": index + 1, "failed": failures, "seconds": time.monotonic() - start}), flush=True)
    report = {"rows": len(rows), "failed": failures, "seconds": time.monotonic() - start,
              "input_sha256": sha(args.input), "output_sha256": sha(args.output),
              "base_sha256": SOURCE_WEIGHT_SHA, "adapter_sha256": adapter_sha,
              "source_sha256": sha(Path(__file__)), "packages": packages(),
              "scope": "Diagnostic Transformers generation; no Core/ASR/Windows delivery or semantic grading"}
    write_json(Path(str(args.output) + ".summary.json"), report)
    print(json.dumps(report), flush=True)
    if failures:
        raise SystemExit(1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    training = commands.add_parser("train")
    training.add_argument("--base", type=Path, required=True)
    training.add_argument("--train", type=Path, required=True)
    training.add_argument("--output", type=Path, required=True)
    training.add_argument("--threads", type=int, default=4)
    training.add_argument("--seed", type=int, default=42)
    training.add_argument("--rank", type=int, default=8)
    training.add_argument("--alpha", type=float, default=16)
    training.add_argument("--learning-rate", type=float, default=0.0002)
    training.add_argument("--epochs", type=int, default=2)
    training.add_argument("--batch-size", type=int, default=2)
    training.add_argument("--gradient-accumulation", type=int, default=4)
    training.add_argument("--max-tokens", type=int, default=1024)
    training.add_argument("--warmup-steps", type=int, default=50)
    training.add_argument("--max-steps", type=int, default=0)
    training.add_argument("--resume-adapter", type=Path)
    training.add_argument("--resume-checkpoint", type=Path)
    training.add_argument("--training-base-mode", choices=["original-bf16", TRAINING_MODE_GGUF], default="original-bf16")
    training.add_argument("--gguf-base", type=Path)
    training.add_argument("--parent-adapter-sha256")
    training.add_argument("--expand-adapter-rank", action="store_true")
    training.add_argument("--kv-roundtrip", choices=["none", "f16"], default="none")
    training.add_argument("--activation-quantization", choices=["none", "native-q8-k"], default="none")
    training.add_argument("--native-runtime", type=Path)
    training.add_argument("--unlikelihood-events", type=Path)
    training.add_argument("--unlikelihood-eta", type=float, default=0.0)
    training.add_argument("--allow-deterministic-legacy-resume", action="store_true")
    training.add_argument("--checkpoint-every", type=int, default=100)
    training.set_defaults(handler=train)
    merging = commands.add_parser("merge")
    merging.add_argument("--base", type=Path, required=True)
    merging.add_argument("--adapter", type=Path, required=True)
    merging.add_argument("--output", type=Path, required=True)
    merging.add_argument("--threads", type=int, default=4)
    merging.add_argument("--dtype", choices=["bfloat16", "float16"], default="bfloat16")
    merging.set_defaults(handler=merge)
    profiling = commands.add_parser("profile")
    profiling.add_argument("--base", type=Path, required=True)
    profiling.add_argument("--output", type=Path, required=True)
    profiling.add_argument("--threads", type=int, default=4)
    profiling.add_argument("--rank", type=int, default=8)
    profiling.add_argument("--alpha", type=float, default=16)
    profiling.add_argument("--steps", type=int, default=3)
    profiling.set_defaults(handler=profile)
    generation = commands.add_parser("generate")
    generation.add_argument("--base", type=Path, required=True)
    generation.add_argument("--adapter", type=Path)
    generation.add_argument("--input", type=Path, required=True)
    generation.add_argument("--output", type=Path, required=True)
    generation.add_argument("--threads", type=int, default=4)
    generation.add_argument("--max-output", type=int, default=512)
    generation.set_defaults(handler=generate)
    args = parser.parse_args(argv)
    if args.threads not in range(1, 9):
        parser.error("threads must be 1..8")
    if args.command == "train" and (not 1 <= args.rank <= 64 or args.alpha <= 0 or args.learning_rate <= 0
            or args.epochs < 1 or args.batch_size < 1 or args.gradient_accumulation < 1 or args.max_steps < 0
            or not 64 <= args.max_tokens <= 1024):
        parser.error("Invalid bounded training options")
    if args.command == "train" and (args.resume_adapter and args.resume_checkpoint):
        parser.error("Choose adapter initialization or exact checkpoint recovery, not both")
    if args.command == "train" and args.allow_deterministic_legacy_resume and not args.resume_checkpoint:
        parser.error("Legacy recovery requires --resume-checkpoint")
    if args.command == "train":
        if not math.isfinite(args.unlikelihood_eta) or not 0 <= args.unlikelihood_eta <= 2:
            parser.error("Unlikelihood eta must be finite and between0and2")
        if args.unlikelihood_eta and not args.unlikelihood_events:
            parser.error("A positive unlikelihood eta requires an explicit event artifact")
        quantized = args.training_base_mode == TRAINING_MODE_GGUF
        if quantized and (not args.gguf_base or not args.parent_adapter_sha256
                or not (args.resume_adapter or args.resume_checkpoint)):
            parser.error("Quantized mode requires --gguf-base, explicit parent SHA256, and adapter initialization or exact recovery")
        if args.parent_adapter_sha256 and (len(args.parent_adapter_sha256) != 64
                or any(c not in "0123456789abcdef" for c in args.parent_adapter_sha256)):
            parser.error("Parent SHA256 must be a complete lowercase SHA256")
        if not quantized and (args.gguf_base or args.kv_roundtrip != "none" or args.expand_adapter_rank
                or args.activation_quantization != "none" or args.native_runtime):
            parser.error("GGUF, rank expansion and KV emulation require the explicit quantized training mode")
        if (args.activation_quantization == "native-q8-k") != bool(args.native_runtime):
            parser.error("Native Q8_K activation emulation requires its explicit pinned --native-runtime directory")
        if args.expand_adapter_rank and not args.resume_adapter:
            parser.error("Rank expansion applies only to an explicit parent adapter, not exact checkpoint recovery")
    if args.command == "generate" and not 1 <= args.max_output <= 512:
        parser.error("max-output must be 1..512")
    args.handler(args)


if __name__ == "__main__":
    main()
