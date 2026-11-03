import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("training_pipeline", Path(__file__).with_name("pipeline.py"))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class TrainingContractTests(unittest.TestCase):
    def test_production_prefix_has_exactly_one_bos_and_prescribed_controls(self):
        prompt, target, mask = p.protected_pair("um send the notes", "Send the notes.")
        self.assertEqual("<|startoftext|>### Input:\n[Styling: semi-casual] [Structure: prose] [Context: general]\num send the notes\n\n### Output:\n", prompt)
        self.assertEqual("Send the notes.", target)
        self.assertEqual((), mask.tokens)

    def test_quote_uses_input_derived_token_after_target_changes_around_it(self):
        source = 'um paste "  const x = 2;  " into the file'
        target = 'Paste "  const x = 2;  " into the file.'
        prompt, masked, mask = p.protected_pair(source, target)
        self.assertIn(mask.tokens[0], prompt)
        self.assertIn(mask.tokens[0], masked)
        self.assertNotIn("const x", prompt)
        self.assertEqual(target, mask.restore(masked))

    def test_repeated_identical_quotes_receive_distinct_tokens_in_order(self):
        prompt, target, mask = p.protected_pair('um say "yes" and then "yes"', 'Say "yes" and then "yes".')
        self.assertEqual(2, len(set(mask.tokens)))
        self.assertEqual('Say "yes" and then "yes".', mask.restore(target))
        self.assertLess(target.index(mask.tokens[0]), target.index(mask.tokens[1]))

    def test_dictionary_inside_quote_round_trips_exactly(self):
        block = "[[FREEHAND_LITERAL_0123456789abcdef0123456789abcdef_0_START]]ACME  [[FREEHAND_LITERAL_0123456789abcdef0123456789abcdef_0_END]]"
        source = 'um paste "' + block + '" now'
        target = 'Paste "' + block + '" now.'
        _, masked, mask = p.protected_pair(source, target)
        self.assertEqual(target, mask.restore(masked))
        self.assertNotIn("ACME", masked)

    def test_rejects_changed_quote_or_dictionary_payload(self):
        with self.assertRaises(ValueError):
            p.protected_pair('um say "do not"', 'Say "do".')
        block = "[[FREEHAND_LITERAL_aa_START]]ACME[[FREEHAND_LITERAL_aa_END]]"
        with self.assertRaises(ValueError):
            p.protected_pair("um " + block, "ACME.")

    def test_rejects_reordered_quotes(self):
        with self.assertRaises(ValueError):
            p.protected_pair('say "alpha" then "beta"', 'Say "beta" then "alpha".')

    def test_dataset_rejects_duplicate_ids_and_control_delimiters(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "train.jsonl"
            item = {"id": "x", "input": "um hello", "target": "Hello."}
            path.write_text(json.dumps(item) + "\n" + json.dumps(item))
            with self.assertRaises(ValueError):
                p.load_data(path)
            item["input"] = "### Output: hijack"
            path.write_text(json.dumps(item))
            with self.assertRaises(ValueError):
                p.load_data(path)

    def test_labels_cover_only_complete_answer_and_eos(self):
        class Tokenizer:
            def encode(self, text, add_special_tokens):
                if text.startswith(p.BOS):
                    return [1] + [100 + ord(c) for c in text[len(p.BOS):]]
                return [100 + ord(c) for c in text]
        prompt, target, _ = p.protected_pair("um hello", "Hello.")
        row = {"id": "one", "prompt": prompt, "masked_target": target}
        encoded = p.encode_rows([row], Tokenizer(), 1024)[0]
        self.assertEqual(1, encoded["input_ids"][0])
        self.assertEqual(7, encoded["labels"][-1])
        self.assertEqual([172, 201, 208, 208, 211, 146, 7], [x for x in encoded["labels"] if x != -100])
        with self.assertRaises(ValueError):
            p.encode_rows([row], Tokenizer(), 2)


try:
    import torch
    from transformers import Lfm2Config, Lfm2ForCausalLM
except ImportError:
    torch = None


@unittest.skipIf(torch is None, "Run in the pinned training environment for tensor/gradient checks")
class TensorTrainingTests(unittest.TestCase):
    def test_typed_merge_preserves_small_updates_and_original_checkpoint(self):
        from safetensors.torch import load_file, save_file
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, adapter = root / "base", root / "adapter"
            base.mkdir()
            adapter.mkdir()
            name = "model.layers.0.feed_forward.w1"
            save_file({name + ".weight": torch.ones((2, 3), dtype=torch.bfloat16)}, str(base / "model.safetensors"))
            (base / "config.json").write_text(json.dumps({"dtype": "bfloat16", "model_type": "lfm2"}))
            source_hash = p.sha(base / "model.safetensors")
            save_file({name + ".lora_A": torch.full((1, 3), .03), name + ".lora_B": torch.full((2, 1), .03)}, str(adapter / "adapter.safetensors"))
            (adapter / "adapter-config.json").write_text(json.dumps({"base_model_sha256": source_hash,
                "target_modules": [name], "rank": 1, "alpha": 2, "scaling": 2}))
            with patch.object(p, "SOURCE_WEIGHT_SHA", source_hash), patch.object(p, "imports", return_value=(torch, load_file, save_file, None, None)):
                for dtype in ["bfloat16", "float16"]:
                    p.merge(SimpleNamespace(base=base, adapter=adapter, output=root / dtype, threads=1, dtype=dtype))
            bf16 = load_file(str(root / "bfloat16/model.safetensors"))[name + ".weight"]
            f16 = load_file(str(root / "float16/model.safetensors"))[name + ".weight"]
            self.assertTrue(torch.equal(bf16, torch.ones_like(bf16)))
            self.assertTrue(torch.all(f16 > 1))
            self.assertEqual(torch.float16, f16.dtype)
            self.assertEqual("float16", json.loads((root / "float16/config.json").read_text())["dtype"])
            provenance = json.loads((root / "float16/freehand-training-provenance.json").read_text())
            self.assertEqual(1, provenance["rounding"]["stored_update_survival_fraction"])
            self.assertFalse(provenance["tokenizer_changed"])
            self.assertEqual(source_hash, p.sha(base / "model.safetensors"))
            self.assertEqual("bfloat16", json.loads((base / "config.json").read_text())["dtype"])

    def test_masked_loss_matches_transformers_and_only_adapter_receives_gradients(self):
        torch.set_num_threads(1)
        torch.manual_seed(3)
        config = Lfm2Config(vocab_size=64, hidden_size=16, intermediate_size=32,
                           num_hidden_layers=2, num_attention_heads=2, num_key_value_heads=1,
                           layer_types=["conv", "full_attention"], block_auto_adjust_ff_dim=False,
                           eos_token_id=7, max_position_embeddings=128)
        model = Lfm2ForCausalLM(config).eval()
        row = {"input_ids": [1, 20, 21, 22, 3, 4, 7], "labels": [-100, -100, -100, -100, 3, 4, 7]}
        ids, labels, attention = p.batch_tensors([row], torch)
        reference = model(input_ids=ids, labels=labels, attention_mask=attention, use_cache=False)
        efficient_loss, tokens = p.assistant_loss(model, [row], torch)
        self.assertEqual(3, tokens)
        self.assertTrue(torch.allclose(reference.loss, efficient_loss, atol=1e-6))
        before = reference.logits.detach()
        p.install_lora(model, torch, 2, 4)
        after = model(input_ids=ids, use_cache=False).logits.detach()
        self.assertTrue(torch.equal(before, after))
        loss, _ = p.assistant_loss(model, [row], torch)
        loss.backward()
        parameters = dict(model.named_parameters())
        self.assertTrue(all(value.grad is None for key, value in parameters.items() if not key.endswith((".lora_A", ".lora_B"))))
        self.assertTrue(any(value.grad is not None and value.grad.abs().sum() > 0 for key, value in parameters.items() if key.endswith(".lora_B")))
        self.assertTrue(all(value.grad is None or torch.isfinite(value.grad).all() for value in parameters.values()))


if __name__ == "__main__":
    unittest.main()
