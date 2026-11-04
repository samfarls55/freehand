"""Small deterministic quantized-base/rank-expansion checks; no real model is read."""
from __future__ import annotations

import copy
import ctypes
import hashlib
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location("quantized_training_pipeline", Path(__file__).with_name("pipeline.py"))
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)

try:
    import numpy as np
    import torch
    import safetensors.torch  # noqa: F401 - checkpoint tests require the serialization package
except ImportError:
    torch = None


@unittest.skipIf(torch is None, "Use the pinned training environment for tensor checks")
class RankExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def state(self):
        # Nonzero learned columns make accidentally discarding the old adapter visible.
        return {
            "model.layers.0.projection.lora_A": torch.arange(40, dtype=torch.float32).reshape(8, 5) / 80 - .25,
            "model.layers.0.projection.lora_B": torch.arange(24, dtype=torch.float32).reshape(3, 8) / 60 - .2,
        }

    def expand(self, state=None, **changes):
        options = dict(parent_rank=8, parent_alpha=16, new_rank=16, new_alpha=32, seed=991, torch=torch)
        options.update(changes)
        return pipeline.expand_adapter_state(self.state() if state is None else state, **options)

    def tiny_model(self, rank, alpha):
        class TinyModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.model = torch.nn.Module()
                self.model.layers = torch.nn.ModuleList([torch.nn.Module()])
                self.model.layers[0].projection = torch.nn.Linear(5, 3, bias=False)
                with torch.no_grad():
                    self.model.layers[0].projection.weight.copy_(torch.arange(15).reshape(3, 5) / 30)

            def forward(self, values):
                return self.model.layers[0].projection(values)

        model = TinyModel()
        pipeline.install_lora(model, torch, rank, alpha, ["model.layers.0.projection"])
        return model

    def copy_adapter(self, model, state):
        parameters = dict(model.named_parameters())
        with torch.no_grad():
            for name, value in state.items():
                parameters[name].copy_(value)

    def test_rank8_to16_preserves_learned_function_and_enables_new_columns(self):
        original = self.state()
        untouched = {name: value.clone() for name, value in original.items()}
        expanded, _ = self.expand(original)
        name_a, name_b = sorted(original)
        self.assertTrue(torch.equal(original[name_a], expanded[name_a][:8]))
        self.assertTrue(torch.equal(original[name_b], expanded[name_b][:, :8]))
        self.assertTrue(torch.equal(expanded[name_b][:, 8:], torch.zeros(3, 8)))
        self.assertGreater(torch.count_nonzero(expanded[name_a][8:]).item(), 0)
        for name in original:
            self.assertTrue(torch.equal(untouched[name], original[name]), "Expansion mutated its parent adapter")

        old, new = self.tiny_model(8, 16), self.tiny_model(16, 32)
        self.copy_adapter(old, original)
        self.copy_adapter(new, expanded)
        values = torch.tensor([[.1, -.3, .6, .2, -.8], [.7, .4, -.1, .3, .5]])
        torch.testing.assert_close(old(values), new(values), rtol=1e-6, atol=1e-7)
        optimizer = torch.optim.SGD((p for p in new.parameters() if p.requires_grad), lr=.1)
        parameters = dict(new.named_parameters())
        new(values).square().sum().backward()
        self.assertGreater(parameters[name_b].grad[:, 8:].abs().sum().item(), 0)
        self.assertEqual(0, parameters[name_a].grad[8:].abs().sum().item())
        self.assertTrue(all(p.grad is None for name, p in parameters.items() if not name.endswith((".lora_A", ".lora_B"))))
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        new(values).square().sum().backward()
        self.assertGreater(parameters[name_a].grad[8:].abs().sum().item(), 0)

    def test_expansion_logit_check_restores_expanded_parameters_and_detects_changes(self):
        inner = self.tiny_model(16, 32)

        class CausalTiny(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.model = inner.model

            def forward(self, ids, use_cache=False):
                values = torch.nn.functional.one_hot(ids, num_classes=5).to(torch.float32)
                return SimpleNamespace(logits=self.model.layers[0].projection(values))

        model = CausalTiny().eval()
        parent = self.state()
        expanded, _ = self.expand(parent)
        self.copy_adapter(model, expanded)
        parameters = dict(model.named_parameters())
        original_objects = {name: parameters[name] for name in expanded}
        receipt = pipeline.verify_expanded_logits(model, torch, [1, 2, 3], parent)
        self.assertLessEqual(receipt["maximum_logit_absolute_difference"], receipt["logit_atol"])
        self.assertTrue(all(dict(model.named_parameters())[name] is value for name, value in original_objects.items()))
        key = next(name for name in expanded if name.endswith(".lora_B"))
        with torch.no_grad():
            parameters[key][:, 8:].fill_(.5)
        with self.assertRaisesRegex(ValueError, "changed initial logits"):
            pipeline.verify_expanded_logits(model, torch, [1, 2, 3], parent)
        self.assertTrue(all(dict(model.named_parameters())[name] is value for name, value in original_objects.items()))

    def test_seeded_extension_is_repeatable_isolated_and_uses_seed(self):
        before = torch.get_rng_state().clone()
        first, _ = self.expand()
        self.assertTrue(torch.equal(before, torch.get_rng_state()))
        second, _ = self.expand()
        different, _ = self.expand(seed=992)
        for name in first:
            self.assertTrue(torch.equal(first[name], second[name]))
        name_a = next(name for name in first if name.endswith(".lora_A"))
        self.assertFalse(torch.equal(first[name_a][8:], different[name_a][8:]))

    def test_refuses_incompatible_rank_scale_pairing_shapes_and_nonfinite_weights(self):
        for options in ({"new_rank": 4, "new_alpha": 8}, {"new_alpha": 16},
                        {"parent_rank": 7, "parent_alpha": 14}, {"parent_alpha": float("nan")},
                        {"parent_alpha": 0, "new_alpha": 0}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.expand(**options)
        missing = self.state()
        del missing[next(name for name in missing if name.endswith(".lora_B"))]
        with self.assertRaises(ValueError):
            self.expand(missing)
        malformed = self.state()
        key = next(name for name in malformed if name.endswith(".lora_B"))
        malformed[key] = torch.zeros(3, 7)
        with self.assertRaises(ValueError):
            self.expand(malformed)
        nonfinite = self.state()
        nonfinite[key][0, 0] = float("inf")
        with self.assertRaises(ValueError):
            self.expand(nonfinite)


@unittest.skipIf(torch is None, "Use the pinned training environment for NumPy decoding checks")
class GgufFrozenBaseTests(unittest.TestCase):
    def fixture(self):
        # Full inventory size, but fewer than one thousand scalar values in total.
        header, tensors, names = {}, [], {}
        for ordinal in range(147):
            hf_name = f"model.layers.{ordinal}.projection.weight"
            gguf_name = f"blk.{ordinal}.projection.weight"
            header[hf_name] = {"dtype": "BF16", "shape": [2, 3]}
            names[hf_name] = gguf_name
            tensors.append(SimpleNamespace(name=gguf_name, shape=np.array([3, 2]),
                data=np.arange(6, dtype=np.float32).reshape(2, 3), tensor_type="F32"))
        hf_name, gguf_name = "model.layers.0.conv.conv.weight", "blk.0.ssm_conv1d.weight"
        header[hf_name] = {"dtype": "BF16", "shape": [4, 1, 3]}
        names[hf_name] = gguf_name
        tensors.append(SimpleNamespace(name=gguf_name, shape=np.array([3, 4]),
            data=np.arange(12, dtype=np.float32).reshape(4, 3), tensor_type="F32"))
        name_map = SimpleNamespace(get_name=lambda name, try_suffixes: names.get(name))
        return header, tensors, names, name_map

    def test_maps_all148_tensors_and_reconstructs_exact_row_major_conv_layout(self):
        header, tensors, _, name_map = self.fixture()
        mapped = pipeline.gguf_tensor_mapping(header, tensors, name_map)
        self.assertEqual(148, len(mapped))
        self.assertEqual({tensor.name for tensor in tensors}, {tensor.name for tensor in mapped.values()})
        self.assertEqual([4, 1, 3], header["model.layers.0.conv.conv.weight"]["shape"])
        for name in ["model.layers.0.projection.weight", "model.layers.0.conv.conv.weight"]:
            decoded = pipeline.inverse_gguf_tensor(name, mapped[name], lambda data, tensor_type: data.copy())
            expected = np.arange(np.prod(header[name]["shape"]), dtype=np.float32).reshape(header[name]["shape"])
            np.testing.assert_array_equal(expected, decoded)

    def test_rejects_missing_extra_duplicate_unmapped_and_shape_incompatible_tensors(self):
        header, tensors, names, name_map = self.fixture()
        cases = [(header, tensors[:-1], name_map), (header, tensors + [tensors[0]], name_map)]
        duplicate = copy.deepcopy(tensors)
        duplicate[-1].name = duplicate[0].name
        cases.append((header, duplicate, name_map))
        bad_shape = copy.deepcopy(tensors)
        bad_shape[0].shape = np.array([2, 3])
        cases.append((header, bad_shape, name_map))
        wrong_conv = copy.deepcopy(header)
        wrong_conv["model.layers.0.conv.conv.weight"]["shape"] = [4, 2, 3]
        cases.append((wrong_conv, tensors, name_map))
        missing_name = dict(names)
        del missing_name[next(iter(missing_name))]
        cases.append((header, tensors, SimpleNamespace(get_name=lambda name, try_suffixes: missing_name.get(name))))
        alias_name = dict(names)
        alias_name[list(alias_name)[1]] = alias_name[list(alias_name)[0]]
        cases.append((header, tensors, SimpleNamespace(get_name=lambda name, try_suffixes: alias_name.get(name))))
        for ordinal, (test_header, test_tensors, test_names) in enumerate(cases):
            with self.subTest(case=ordinal), self.assertRaises(ValueError):
                pipeline.gguf_tensor_mapping(test_header, test_tensors, test_names)

    def test_inverse_rejects_nonfinite_nonfp32_or_wrong_sized_decoding(self):
        _, tensors, _, _ = self.fixture()
        for decoded in [np.full((2, 3), np.nan, dtype=np.float32), np.zeros((2, 3), dtype=np.float16),
                        np.zeros(7, dtype=np.float32)]:
            with self.subTest(dtype=str(decoded.dtype), shape=decoded.shape), self.assertRaises(ValueError):
                pipeline.inverse_gguf_tensor("projection.weight", tensors[0], lambda data, tensor_type: decoded)

    def test_legacy_merge_and_generate_refuse_quantized_adapter_before_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter = root / "adapter"
            adapter.mkdir()
            (adapter / "adapter-config.json").write_text('{"training_base_mode":"original-iq4-dequantized-fp32-v1"}')
            with patch.object(pipeline, "imports", side_effect=AssertionError("Legacy routes must reject before model imports")) as imports:
                for name in ("merge", "generate"):
                    output = root / name
                    with self.subTest(command=name), self.assertRaises(ValueError):
                        getattr(pipeline, name)(SimpleNamespace(adapter=adapter, output=output))
                    self.assertFalse(output.exists())
                imports.assert_not_called()

    def test_source_hashes_are_checked_before_model_import_or_allocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base"
            base.mkdir()
            original, encoded = b"tiny original BF16 placeholder", b"tiny original IQ4 placeholder"
            (base / "model.safetensors").write_bytes(original)
            (base / "config.json").write_text('{"model_type":"synthetic"}')
            (base / "tokenizer.json").write_text('{"synthetic":true}')
            gguf = root / "original.gguf"
            gguf.write_bytes(encoded)
            original_sha, gguf_sha = hashlib.sha256(original).hexdigest(), hashlib.sha256(encoded).hexdigest()
            with patch.object(pipeline, "SOURCE_WEIGHT_SHA", original_sha), patch.object(pipeline, "SOURCE_GGUF_SHA", gguf_sha):
                receipt = pipeline.validate_gguf_base_identity(base, gguf)
                self.assertEqual(pipeline.TRAINING_MODE_GGUF, receipt["training_base_mode"])
                self.assertEqual(original_sha, receipt["original_bf16_sha256"])
                self.assertEqual(gguf_sha, receipt["frozen_base_sha256"])
                self.assertEqual(pipeline.sha(base / "config.json"), receipt["base_config_sha256"])
                self.assertEqual(pipeline.sha(base / "tokenizer.json"), receipt["tokenizer_sha256"])
                self.assertEqual(pipeline.sha(Path(pipeline.__file__)), receipt["quantized_training_source_sha256"])
                with patch.object(pipeline, "imports", side_effect=AssertionError("A bad source must not load a model")) as imports:
                    gguf.write_bytes(encoded + b"corrupt")
                    with self.assertRaises(ValueError):
                        pipeline.quantized_base_model(base, gguf, 1)
                    gguf.write_bytes(encoded)
                    (base / "model.safetensors").write_bytes(original + b"corrupt")
                    with self.assertRaises(ValueError):
                        pipeline.quantized_base_model(base, gguf, 1)
                    imports.assert_not_called()


@unittest.skipIf(torch is None, "Use the pinned training environment for STE checks")
class KvPrecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_fp16_roundtrip_forward_and_identity_backward_are_both_real(self):
        values = torch.tensor([.1234567, .49989, -1.0007, 3.14159, .00000013, 65500], requires_grad=True)
        expected = values.detach().to(torch.float16).to(torch.float32)
        actual = pipeline.fp16_roundtrip_ste(values, torch)
        self.assertEqual(torch.float32, actual.dtype)
        self.assertTrue(torch.equal(expected, actual))
        self.assertFalse(torch.equal(values.detach(), actual.detach()), "Test values must expose actual F16 rounding")
        upstream = torch.tensor([-.2, 1, 3, -4, .25, .75])
        actual.backward(upstream)
        self.assertTrue(torch.equal(upstream, values.grad), "STE must preserve the full upstream derivative")

    def test_tiny_lfm_rank8_to16_logit_check_with_f16_kv_enabled(self):
        from transformers import Lfm2Config, Lfm2ForCausalLM

        torch.manual_seed(17)
        config = Lfm2Config(vocab_size=32, hidden_size=16, intermediate_size=32,
            num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=1,
            layer_types=["full_attention"], block_auto_adjust_ff_dim=False,
            eos_token_id=7, max_position_embeddings=32)
        config._attn_implementation = "eager"
        model = Lfm2ForCausalLM(config).eval()
        pipeline.install_kv_roundtrip(model, torch)
        pipeline.install_lora(model, torch, 16, 32)
        parent = {}
        for name, value in pipeline.adapter_state(model).items():
            if name.endswith(".lora_A"):
                parent[name] = value[:8].clone()
            else:
                parent[name] = torch.linspace(-.01, .01, value.shape[0] * 8).reshape(value.shape[0], 8)
        expanded, _ = pipeline.expand_adapter_state(parent, 8, 16, 16, 32, 991, torch)
        parameters = dict(model.named_parameters())
        with torch.no_grad():
            for name, value in expanded.items():
                parameters[name].copy_(value)
        receipt = pipeline.verify_expanded_logits(model, torch, [1, 11, 4, 19, 7], parent)
        self.assertLessEqual(receipt["maximum_logit_absolute_difference"], 5e-4)
        self.assertTrue(all(dict(model.named_parameters())[name] is parameters[name] for name in expanded))

    def test_tiny_lfm_prefill_decode_and_teacher_force_share_rounded_kv_only(self):
        from transformers import Lfm2Config, Lfm2ForCausalLM
        from transformers.models.lfm2 import modeling_lfm2 as implementation

        torch.manual_seed(14)
        config = Lfm2Config(vocab_size=32, hidden_size=16, intermediate_size=32,
            num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=1,
            layer_types=["full_attention"], block_auto_adjust_ff_dim=False,
            eos_token_id=7, max_position_embeddings=32)
        config._attn_implementation = "eager"
        model = Lfm2ForCausalLM(config).eval()
        receipt = pipeline.install_kv_roundtrip(model, torch)
        self.assertEqual(1, receipt["attention_layers"])
        self.assertFalse(receipt["query_rounded"])
        self.assertEqual(64, len(receipt["kv_attention_source_sha256"]))
        interface = implementation.eager_attention_forward
        observed = []

        def attention(module, query, key, value, mask, **kwargs):
            observed.append(tuple(item.detach().clone() for item in (query, key, value)))
            return interface(module, query, key, value, mask, **kwargs)

        ids = torch.tensor([[1, 11, 4, 19, 7]])
        with torch.no_grad(), patch.object(implementation, "eager_attention_forward", side_effect=attention):
            full = model(ids, use_cache=False).logits
            prefill = model(ids[:, :4], use_cache=True)
            decoded = model(ids[:, 4:], use_cache=True, past_key_values=prefill.past_key_values)
        torch.testing.assert_close(full[:, :4], prefill.logits, rtol=1e-5, atol=1e-6)
        torch.testing.assert_close(full[:, 4:], decoded.logits, rtol=1e-5, atol=1e-6)
        self.assertEqual(3, len(observed))
        for query, key, value in observed:
            self.assertTrue(torch.equal(key, key.to(torch.float16).to(torch.float32)))
            self.assertTrue(torch.equal(value, value.to(torch.float16).to(torch.float32)))
            self.assertFalse(torch.equal(query, query.to(torch.float16).to(torch.float32)), "Queries must retain FP32 precision")
        cache = decoded.past_key_values
        self.assertEqual(5, cache.key_cache[0].shape[-2])
        for cached in (cache.key_cache[0], cache.value_cache[0]):
            self.assertTrue(torch.equal(cached, cached.to(torch.float16).to(torch.float32)))
        with self.assertRaises(ValueError):
            pipeline.install_kv_roundtrip(model, torch)


@unittest.skipIf(torch is None, "Use the pinned training environment for Q8 activation checks")
class NativeQ8ActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_pinned_native_blocks_match_reference_packed_bytes_and_manual_fp32_decode(self):
        runtime = pipeline.REPO / "work/cleanup-poc/runtime/llama-b12015"
        if not all((runtime / name).is_file() for name in ("libggml-cpu-haswell.so", "libggml-base.so")):
            self.skipTest("Pinned native runtime is an optional local fixture")
        quantizer = pipeline.NativeQ8KQuantizer(runtime)
        reference = quantizer.base.quantize_row_q8_K_ref
        reference.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64]
        reference.restype = None
        values = np.random.default_rng(2026).normal(size=(4, 256)).astype(np.float32)
        values[0] = 0
        values[1] = np.linspace(-128, 127, 256, dtype=np.float32)
        original = values.copy()
        packed, reference_packed = np.zeros((4, 292), dtype=np.uint8), np.zeros((4, 292), dtype=np.uint8)
        quantizer.quantize(values.ctypes.data, packed.ctypes.data, values.size)
        reference(values.ctypes.data, reference_packed.ctypes.data, values.size)
        np.testing.assert_array_equal(reference_packed, packed)
        manual = packed[:, :4].copy().view(np.float32) * packed[:, 4:260].view(np.int8).astype(np.float32)
        actual = quantizer.roundtrip(values)
        np.testing.assert_array_equal(manual, actual)
        np.testing.assert_array_equal(original, values)
        self.assertEqual(values.shape, actual.shape)
        self.assertEqual(np.float32, actual.dtype)
        self.assertFalse(np.shares_memory(values, actual))

    def test_hash_mismatch_rejects_before_any_native_library_load(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            cpu, base = runtime / "libggml-cpu-haswell.so", runtime / "libggml-base.so"
            cpu.write_bytes(b"synthetic CPU library")
            base.write_bytes(b"synthetic base library")
            correct_cpu, correct_base = pipeline.sha(cpu), pipeline.sha(base)
            for expected_cpu, expected_base in (("f" * 64, correct_base), (correct_cpu, "e" * 64)):
                with self.subTest(cpu=expected_cpu), patch.object(pipeline, "SOURCE_Q8_CPU_SHA", expected_cpu), \
                        patch.object(pipeline, "SOURCE_Q8_BASE_SHA", expected_base), \
                        patch.object(ctypes, "CDLL", side_effect=AssertionError("Bad pins must reject before loading")) as load:
                    with self.assertRaises(ValueError):
                        pipeline.NativeQ8KQuantizer(runtime)
                    load.assert_not_called()

    def test_invalid_width_dtype_layout_empty_or_nonfinite_reject_before_native_calls(self):
        quantizer = object.__new__(pipeline.NativeQ8KQuantizer)
        quantizer.quantize = Mock(side_effect=AssertionError("Invalid arrays must not enter native code"))
        quantizer.dequantize = Mock(side_effect=AssertionError("Invalid arrays must not enter native code"))
        invalid = [np.zeros(255, dtype=np.float32), np.zeros((2, 257), dtype=np.float32),
                   np.zeros(256, dtype=np.float64), np.zeros(256, dtype=np.complex64),
                   np.zeros((2, 512), dtype=np.float32)[:, ::2], np.array(0, dtype=np.float32),
                   np.zeros((1, 0), dtype=np.float32), np.zeros((0, 256), dtype=np.float32),
                   np.full(256, np.nan, dtype=np.float32), np.full(256, np.inf, dtype=np.float32), [0.0] * 256]
        for ordinal, values in enumerate(invalid):
            with self.subTest(case=ordinal), self.assertRaises(ValueError):
                quantizer.roundtrip(values)
        quantizer.quantize.assert_not_called()
        quantizer.dequantize.assert_not_called()

    def test_native_ste_uses_rounded_forward_but_identity_gradient_and_rejects_fp64(self):
        quantizer = Mock()
        quantizer.roundtrip.side_effect = lambda array: (np.round(array * np.float32(4)) / np.float32(4)).astype(np.float32)
        values = torch.linspace(-.3, .7, 256, requires_grad=True)
        expected = torch.round(values.detach() * 4) / 4
        rounded = pipeline.native_q8_roundtrip_ste(values, torch, quantizer)
        self.assertTrue(torch.equal(expected, rounded))
        self.assertFalse(torch.equal(values.detach(), rounded.detach()))
        gradient = torch.linspace(-2, 3, 256)
        rounded.backward(gradient)
        self.assertTrue(torch.equal(gradient, values.grad))
        quantizer.roundtrip.reset_mock()
        with self.assertRaises(ValueError):
            pipeline.native_q8_roundtrip_ste(values.detach().to(torch.float64), torch, quantizer)
        quantizer.roundtrip.assert_not_called()

    def test_original_linear_hook_rounds_base_input_while_lora_and_its_gradient_use_raw_input(self):
        class TinyModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.model = torch.nn.Module()
                self.model.layers = torch.nn.ModuleList([torch.nn.Module()])
                self.model.layers[0].projection = torch.nn.Linear(256, 2, bias=False)
                self.lm_head = torch.nn.Linear(256, 2, bias=False)
                self._freehand_quantized_linear_types = {"model.layers.0.projection": "IQ4_XS", "lm_head": "Q6_K"}

            def forward(self, values):
                return self.model.layers[0].projection(values)

        model = TinyModel()
        fake = Mock(cpu_path=Path("synthetic-cpu"), base_path=Path("synthetic-base"))
        fake.roundtrip.side_effect = lambda array: (np.round(array * np.float32(4)) / np.float32(4)).astype(np.float32)
        with patch.object(pipeline, "NativeQ8KQuantizer", return_value=fake), patch.object(pipeline, "sha", return_value="a" * 64):
            receipt = pipeline.install_native_q8_activation(model, torch, Path("unused"))
        self.assertTrue(receipt["includes_tied_output_matmul"])
        self.assertFalse(receipt["lora_input_rounded"])
        self.assertEqual({"model.layers.0.projection", "lm_head"}, {item["name"] for item in receipt["linears"]})
        pipeline.install_lora(model, torch, 2, 4, ["model.layers.0.projection"])
        projection = model.model.layers[0].projection
        with torch.no_grad():
            projection.base.weight.zero_()
            projection.base.weight[:, :2].copy_(torch.eye(2))
            projection.lora_A.zero_()
            projection.lora_A[:, :2].copy_(torch.eye(2))
            projection.lora_B.copy_(torch.eye(2) * .5)
        observed_base = []
        projection.base.register_forward_pre_hook(lambda module, args: observed_base.append(args[0].detach().clone()))
        values = torch.linspace(-.3, .7, 512).reshape(2, 256).requires_grad_()
        rounded = torch.round(values.detach() * 4) / 4
        expected = torch.nn.functional.linear(rounded, projection.base.weight) + \
            torch.nn.functional.linear(torch.nn.functional.linear(values, projection.lora_A), projection.lora_B) * 2
        actual = model(values)
        torch.testing.assert_close(expected, actual, rtol=0, atol=0)
        self.assertTrue(torch.equal(observed_base[0], rounded))
        wrongly_rounded_lora = torch.nn.functional.linear(rounded, projection.base.weight) + \
            torch.nn.functional.linear(torch.nn.functional.linear(rounded, projection.lora_A), projection.lora_B) * 2
        self.assertFalse(torch.equal(wrongly_rounded_lora, actual.detach()))
        actual.sum().backward()
        expected_gradient = projection.base.weight.sum(dim=0) + (projection.lora_B @ projection.lora_A * 2).sum(dim=0)
        torch.testing.assert_close(expected_gradient.expand_as(values), values.grad, rtol=0, atol=0)
        self.assertIsNone(projection.base.weight.grad)
        self.assertGreater(projection.lora_A.grad.abs().sum().item(), 0)
        self.assertGreater(projection.lora_B.grad.abs().sum().item(), 0)
        # The separate tied-head matmul is covered by the same original-linear hook inventory.
        model.lm_head(values.detach())
        self.assertEqual(2, fake.roundtrip.call_count)


@unittest.skipIf(torch is None, "Use the pinned training environment for checkpoint checks")
class QuantizedBaseResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def model(self):
        class TinyAdapter(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.projection = torch.nn.Module()
                self.projection.lora_A = torch.nn.Parameter(torch.arange(48, dtype=torch.float32).reshape(16, 3) / 100)
                self.projection.lora_B = torch.nn.Parameter(torch.ones(2, 16) / 20)

            def forward(self, values):
                return values @ self.projection.lora_A.T @ self.projection.lora_B.T * 2

        return TinyAdapter()

    def config(self, output):
        source = b"# synthetic quantized frozen-base resume test\n"
        (output / "training-source.py").write_bytes(source)
        return {
            "schema_version": 1, "base_model_sha256": pipeline.SOURCE_WEIGHT_SHA,
            "rank": 16, "alpha": 32, "scaling": 2, "target_modules": ["projection"],
            "seed": 991, "train_sha256": hashlib.sha256(b"tiny synthetic rows").hexdigest(),
            "train_rows": 2, "epochs": 1, "batch_size": 1, "gradient_accumulation": 1,
            "learning_rate": .01, "max_tokens": 16, "threads": 1, "warmup_steps": 0,
            "effective_warmup_steps": 0, "schedule_total_optimizer_steps": 2,
            "training_source_sha256": hashlib.sha256(source).hexdigest(),
            "training_base_mode": "original-iq4-dequantized-fp32-v1",
            "frozen_base_sha256": "1" * 64, "original_bf16_sha256": "2" * 64,
            "base_config_sha256": "3" * 64, "tokenizer_sha256": "4" * 64,
            "gguf_dequantizer_sha256": "5" * 64, "gguf_mapping_sha256": "6" * 64,
            "parent_adapter_sha256": "7" * 64, "parent_adapter_config_sha256": "8" * 64,
            "rank_expansion": {"parent_rank": 8, "new_rank": 16, "scaling": 2, "seed": 991},
            "kv_roundtrip_mode": "post-rope-f16-ste-v1", "kv_attention_source_sha256": "9" * 64,
            "quantized_training_source_sha256": "a" * 64,
            "activation_quantization_mode": "native-q8-k-ste-v1", "activation_cpu_library_sha256": "b" * 64,
            "activation_base_library_sha256": "c" * 64, "activation_linear_inventory_sha256": "d" * 64,
        }

    def test_resume_rejects_changed_frozen_base_parent_or_expansion_before_mutation(self):
        model = self.model()
        optimizer = torch.optim.AdamW(model.parameters(), lr=.01)
        model(torch.tensor([[.2, .4, -.1]])).square().sum().backward()
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            config = self.config(output)
            checkpoint = pipeline.save_resume_checkpoint(model, optimizer, torch, output, config,
                {"step": 1, "microbatch": 1, "epoch": 1, "assistant_tokens": 3, "seconds": .1, "lr": .01})
            contract = ["training_base_mode", "frozen_base_sha256", "original_bf16_sha256", "base_config_sha256",
                        "tokenizer_sha256", "gguf_dequantizer_sha256", "gguf_mapping_sha256",
                        "parent_adapter_sha256", "parent_adapter_config_sha256", "rank_expansion",
                        "kv_roundtrip_mode", "kv_attention_source_sha256", "quantized_training_source_sha256",
                        "activation_quantization_mode", "activation_cpu_library_sha256",
                        "activation_base_library_sha256", "activation_linear_inventory_sha256"]
            for key in contract:
                changed = copy.deepcopy(config)
                changed[key] = {**changed[key], "seed": 992} if key == "rank_expansion" else "different"
                fresh = self.model()
                fresh_optimizer = torch.optim.AdamW(fresh.parameters(), lr=.01)
                before = {name: tensor.clone() for name, tensor in pipeline.adapter_state(fresh).items()}
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, "configuration mismatch"):
                    pipeline.load_resume_checkpoint(fresh, fresh_optimizer, torch, checkpoint, changed)
                self.assertEqual({}, fresh_optimizer.state)
                self.assertTrue(all(torch.equal(value, pipeline.adapter_state(fresh)[name]) for name, value in before.items()))
            # The identical quantized contract must still allow an actual optimizer recovery.
            recovered = self.model()
            with torch.no_grad():
                for parameter in recovered.parameters():
                    parameter.zero_()
            recovered_optimizer = torch.optim.AdamW(recovered.parameters(), lr=.4)
            state = pipeline.load_resume_checkpoint(recovered, recovered_optimizer, torch, checkpoint, config)
            self.assertEqual(1, state["global_step"])
            self.assertEqual(.01, recovered_optimizer.param_groups[0]["lr"])
            self.assertTrue(all(torch.equal(value, pipeline.adapter_state(recovered)[name])
                                for name, value in pipeline.adapter_state(model).items()))
            for old_parameter, new_parameter in zip(model.parameters(), recovered.parameters()):
                self.assertEqual(optimizer.state[old_parameter].keys(), recovered_optimizer.state[new_parameter].keys())
                for key, value in optimizer.state[old_parameter].items():
                    self.assertTrue(torch.equal(value, recovered_optimizer.state[new_parameter][key]))


if __name__ == "__main__":
    unittest.main()
