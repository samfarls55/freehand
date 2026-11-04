"""Exercise real trainer ordering/schedule recovery with a tiny local LFM model."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("resume_cli_pipeline", Path(__file__).with_name("pipeline.py"))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

try:
    import torch
    from safetensors.torch import load_file, save_file
    from transformers import Lfm2Config, Lfm2ForCausalLM
except ImportError:
    torch = None


@unittest.skipIf(torch is None, "Requires the isolated pinned training environment")
class TrainerRecoveryTests(unittest.TestCase):
    def _compare(self, rows_count, epochs, accumulation, expected_steps, expected_microbatches):
        torch.set_num_threads(1)

        class Tokenizer:
            def encode(self, text, add_special_tokens):
                if text.startswith(p.BOS):
                    return [1] + [2 + ord(c) for c in text[len(p.BOS):]]
                return [2 + ord(c) for c in text]

        def tiny_base(base, threads):
            torch.manual_seed(19)
            config = Lfm2Config(vocab_size=256, hidden_size=16, intermediate_size=32,
                num_hidden_layers=2, num_attention_heads=2, num_key_value_heads=1,
                layer_types=["conv", "full_attention"], block_auto_adjust_ff_dim=False,
                eos_token_id=7, max_position_embeddings=1024)
            return torch, load_file, save_file, Tokenizer(), Lfm2ForCausalLM(config)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "train.jsonl"
            rows = [{"id": str(i), "input": source, "target": target, "split": "train"}
                for i, (source, target) in enumerate([
                    ("um send the paper", "Send the paper."),
                    ("uh open the window", "Open the window."),
                    ("um hold the box", "Hold the box."),
                    ("uh keep the key", "Keep the key.")])]
            data.write_text("\n".join(json.dumps(row) for row in rows[:rows_count]))
            common = ["train", "--base", str(root / "base"), "--train", str(data),
                "--epochs", str(epochs), "--batch-size", "1", "--gradient-accumulation", str(accumulation),
                "--rank", "2", "--alpha", "4", "--threads", "1", "--checkpoint-every", "2"]
            with patch.object(p, "base_model", tiny_base), contextlib.redirect_stdout(io.StringIO()):
                p.main(common + ["--output", str(root / "full")])
                p.main(common + ["--output", str(root / "part"), "--max-steps", "2"])
                p.main(common + ["--output", str(root / "resumed"), "--resume-checkpoint",
                    str(root / "part/checkpoints/step-000002")])
            full = load_file(str(root / "full/adapter.safetensors"))
            resumed = load_file(str(root / "resumed/adapter.safetensors"))
            self.assertEqual(set(full), set(resumed))
            self.assertTrue(all(torch.equal(full[key], resumed[key]) for key in full))
            reference = [json.loads(line) for line in (root / "full/training-log.jsonl").read_text().splitlines()]
            continuation = [json.loads(line) for line in (root / "resumed/training-log.jsonl").read_text().splitlines()]
            self.assertEqual(list(range(3, expected_steps + 1)), [row["step"] for row in continuation])
            for expected, actual in zip(reference[2:], continuation):
                for key in ["microbatch", "lr", "loss", "gradient_norm", "assistant_tokens"]:
                    self.assertEqual(expected[key], actual[key], key)
            report = json.loads((root / "resumed/training-result.json").read_text())
            self.assertEqual(expected_steps, report["steps"])
            self.assertEqual(expected_microbatches, report["microbatches"])
            config = json.loads((root / "resumed/adapter-config.json").read_text())
            self.assertEqual(2, config["resume_global_step"])
            self.assertEqual("exact_saved_torch_cpu_and_python", config["resume_rng_restore_mode"])

    def test_actual_trainer_skips_consumed_batches_and_preserves_schedule(self):
        self._compare(4, 1, 1, 4, 4)

    def test_recovery_crosses_epoch_and_finishes_partial_gradient_accumulation(self):
        self._compare(3, 3, 2, 5, 9)


if __name__ == "__main__":
    unittest.main()
