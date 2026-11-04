"""Tiny stochastic optimizer-continuation checks; no real model or dataset is read."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
from pathlib import Path
import random
import tempfile
import unittest


spec = importlib.util.spec_from_file_location("resume_training_pipeline", Path(__file__).with_name("pipeline.py"))
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)

try:
    import torch
    import safetensors.torch  # noqa: F401 - required by the checkpoint implementation
except ImportError:
    torch = None


@unittest.skipIf(torch is None, "Use the pinned training environment for optimizer-resume tensor checks")
class OptimizerResumeTests(unittest.TestCase):
    # Position-dependent rates make restarting the schedule observable.
    learning_rates = (.03, .06, .04, .02)

    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def seed(self, value):
        random.seed(value)
        torch.manual_seed(value)

    def make_model(self):
        class LoRALinear(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.register_buffer("base", torch.arange(32, dtype=torch.float32).reshape(4, 8) / 64)
                self.lora_A = torch.nn.Parameter(torch.randn(2, 8) * .1)
                self.lora_B = torch.nn.Parameter(torch.randn(4, 2) * .1)
                self.dropout = torch.nn.Dropout(.25)

            def forward(self, values):
                return values @ self.base.T + self.dropout(values) @ self.lora_A.T @ self.lora_B.T

        class TinyModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.projection = LoRALinear()

            def forward(self, values):
                return self.projection(values)

        return TinyModel().train()

    def make_optimizer(self, model, learning_rate=.06):
        return torch.optim.AdamW(model.parameters(), lr=learning_rate, betas=(.8, .95), weight_decay=.01)

    def update_steps(self, model, optimizer, first, count):
        losses, rates = [], []
        for position in range(first, first + count):
            # Exercise both RNGs, stochastic model state and AdamW momentum.
            offset = random.uniform(-.2, .2)
            values = torch.randn(3, 8) * .2 + offset
            target = torch.randn(3, 4) * .1
            optimizer.zero_grad(set_to_none=True)
            loss = torch.nn.functional.mse_loss(model(values), target)
            loss.backward()
            learning_rate = self.learning_rates[position]
            for group in optimizer.param_groups:
                group["lr"] = learning_rate
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            losses.append(loss.detach().item())
            rates.append(learning_rate)
        return losses, rates

    def config(self, output):
        source = b"# synthetic optimizer-resume unit-test source\n"
        (output / "training-source.py").write_bytes(source)
        return {
            "schema_version": 1,
            "base_model_sha256": pipeline.SOURCE_WEIGHT_SHA,
            "rank": 2,
            "alpha": 2,
            "scaling": 1,
            "target_modules": ["projection"],
            "seed": 1729,
            "train_sha256": hashlib.sha256(b"synthetic training rows only").hexdigest(),
            "train_rows": 12,
            "epochs": 1,
            "batch_size": 3,
            "gradient_accumulation": 1,
            "learning_rate": .06,
            "max_tokens": 16,
            "threads": 1,
            "warmup_steps": 2,
            "effective_warmup_steps": 2,
            "schedule_total_optimizer_steps": 4,
            "training_source_sha256": hashlib.sha256(source).hexdigest(),
        }

    def event(self):
        return {"step": 2, "microbatch": 2, "epoch": 1, "assistant_tokens": 24,
                "seconds": .125, "lr": self.learning_rates[1]}

    def assert_nested_equal(self, expected, actual):
        if isinstance(expected, torch.Tensor):
            self.assertIsInstance(actual, torch.Tensor)
            self.assertEqual(expected.dtype, actual.dtype)
            self.assertTrue(torch.equal(expected, actual), "Checkpoint continuation changed an adapter or optimizer tensor")
        elif isinstance(expected, dict):
            self.assertEqual(expected.keys(), actual.keys())
            for key in expected:
                self.assert_nested_equal(expected[key], actual[key])
        elif isinstance(expected, (list, tuple)):
            self.assertEqual(type(expected), type(actual))
            self.assertEqual(len(expected), len(actual))
            for left, right in zip(expected, actual):
                self.assert_nested_equal(left, right)
        else:
            self.assertEqual(expected, actual)

    def test_save_reload_matches_uninterrupted_updates_optimizer_rng_and_schedule_position(self):
        self.seed(1729)
        uninterrupted = self.make_model()
        uninterrupted_optimizer = self.make_optimizer(uninterrupted)
        expected_losses, expected_rates = self.update_steps(uninterrupted, uninterrupted_optimizer, 0, 4)
        expected_adapters = {name: value.clone() for name, value in pipeline.adapter_state(uninterrupted).items()}
        expected_optimizer = copy.deepcopy(uninterrupted_optimizer.state_dict())
        expected_torch_rng = torch.get_rng_state().clone()
        expected_python_rng = random.getstate()

        self.seed(1729)
        interrupted = self.make_model()
        interrupted_optimizer = self.make_optimizer(interrupted)
        first_losses, first_rates = self.update_steps(interrupted, interrupted_optimizer, 0, 2)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            config = self.config(output)
            checkpoint = pipeline.save_resume_checkpoint(interrupted, interrupted_optimizer, torch, output, config, self.event())

            # Fresh initialization must not accidentally preserve parameters or RNG.
            self.seed(98765)
            resumed = self.make_model()
            resumed_optimizer = self.make_optimizer(resumed, learning_rate=.5)
            torch.rand(5)
            random.random()
            state = pipeline.load_resume_checkpoint(resumed, resumed_optimizer, torch, checkpoint, config)
            self.assertEqual(2, state["global_step"])
            self.assertEqual(2, state["global_microbatch"])
            self.assertEqual(1, state["epoch"])
            self.assertEqual(24, state["assistant_tokens"])
            self.assertEqual(.125, state["elapsed_seconds"])
            self.assertEqual(self.learning_rates[1], resumed_optimizer.param_groups[0]["lr"])
            remaining_losses, remaining_rates = self.update_steps(resumed, resumed_optimizer, state["global_step"], 2)

        self.assertEqual(expected_losses, first_losses + remaining_losses)
        self.assertEqual(expected_rates, first_rates + remaining_rates)
        self.assert_nested_equal(expected_adapters, pipeline.adapter_state(resumed))
        self.assert_nested_equal(expected_optimizer, resumed_optimizer.state_dict())
        self.assertTrue(torch.equal(expected_torch_rng, torch.get_rng_state()))
        self.assertEqual(expected_python_rng, random.getstate())
        self.assertTrue(all(int(value["step"].item()) == 4 for value in resumed_optimizer.state.values()))

    def test_resume_rejects_different_training_data_or_optimization_contract(self):
        self.seed(1729)
        model = self.make_model()
        optimizer = self.make_optimizer(model)
        self.update_steps(model, optimizer, 0, 2)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            config = self.config(output)
            checkpoint = pipeline.save_resume_checkpoint(model, optimizer, torch, output, config, self.event())
            for field, changed in (("train_sha256", "f" * 64), ("learning_rate", .09),
                                   ("rank", 3), ("schedule_total_optimizer_steps", 8)):
                with self.subTest(field=field):
                    expected_config = {**config, field: changed}
                    fresh = self.make_model()
                    fresh_optimizer = self.make_optimizer(fresh)
                    before_adapters = {name: value.clone() for name, value in pipeline.adapter_state(fresh).items()}
                    before_optimizer = copy.deepcopy(fresh_optimizer.state_dict())
                    with self.assertRaises(ValueError):
                        pipeline.load_resume_checkpoint(fresh, fresh_optimizer, torch, checkpoint, expected_config)
                    self.assert_nested_equal(before_adapters, pipeline.adapter_state(fresh))
                    self.assert_nested_equal(before_optimizer, fresh_optimizer.state_dict())


if __name__ == "__main__":
    unittest.main()
