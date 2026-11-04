"""Pure mode/identity regressions; no Torch, model, or training execution."""
import contextlib
import copy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pipeline


LEGACY_SOURCE = "8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad"
REGISTERED_HELPER = "9ee736685aab7decc213937ced67f7e37df65d4f5cad0240dd6e266002073561"
GC_SOURCES = (
    "gradient_checkpointing_model_source_sha256",
    "gradient_checkpointing_framework_source_sha256",
    "gradient_checkpointing_enable_source_sha256",
    "gradient_checkpointing_checkpoint_source_sha256",
)


def configuration(protocol="specialist-compact-v4", checkpointing=True):
    value = {
        "literal_protocol": protocol,
        "literal_helper_sha256": REGISTERED_HELPER,
        "literal_word_ranges_sha256": "b" * 64 if protocol.endswith("v4") else None,
        "gradient_checkpointing": checkpointing,
        "gradient_checkpointing_use_reentrant": False if checkpointing else None,
        "packages": {"torch": "fixture-torch", "transformers": "fixture-transformers"},
    }
    for ordinal, name in enumerate(GC_SOURCES, 1):
        value[name] = str(ordinal) * 64 if checkpointing else None
    return value


class TrainingModeTests(unittest.TestCase):
    def test_cli_default_retains_v3_and_no_checkpointing_without_training(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(pipeline, "train") as train:
            output = Path(directory) / "not-created"
            pipeline.main(["train", "--base", directory, "--train", "fixture.jsonl", "--output", str(output)])
            train.assert_called_once()
            args = train.call_args.args[0]
            self.assertEqual("specialist-compact-v3", args.specialist_literal_protocol)
            self.assertIs(False, args.gradient_checkpointing)
            self.assertFalse(output.exists())

    def test_cli_explicit_v4_gc_preserves_the_selected_quantized_recipe(self):
        with patch.object(pipeline, "train") as train:
            pipeline.main(["train", "--base", "fixture-base", "--train", "fixture.jsonl", "--output", "fixture-output",
                "--specialist-literal-protocol", "specialist-compact-v4", "--gradient-checkpointing",
                "--training-base-mode", pipeline.TRAINING_MODE_GGUF, "--gguf-base", "fixture.gguf",
                "--resume-adapter", "fixture-parent", "--parent-adapter-sha256", "a" * 64,
                "--activation-quantization", "native-q8-k", "--native-runtime", "fixture-runtime",
                "--rank", "8", "--alpha", "16", "--kv-roundtrip", "none"])
            train.assert_called_once()
            args = train.call_args.args[0]
            self.assertEqual("specialist-compact-v4", args.specialist_literal_protocol)
            self.assertIs(True, args.gradient_checkpointing)
            self.assertEqual((pipeline.TRAINING_MODE_GGUF, "native-q8-k", "none", 8, 16),
                             (args.training_base_mode, args.activation_quantization, args.kv_roundtrip, args.rank, args.alpha))
        with patch.object(pipeline, "train") as train, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                pipeline.main(["train", "--base", "fixture", "--train", "fixture", "--output", "fixture",
                               "--specialist-literal-protocol", "specialist-compact-v5"])
            train.assert_not_called()

    def test_v4_protects_single_nested_and_repeated_quotes_while_default_stays_v3(self):
        source = "Um, keep 'Uh, wait' and 'Uh, wait' exactly."
        target = "Keep 'Uh, wait' and 'Uh, wait' exactly."
        _, _, legacy = pipeline.protected_pair(source, target)
        self.assertEqual((), legacy.tokens)
        prompt, masked, current = pipeline.protected_pair(source, target, "specialist-compact-v4")
        self.assertEqual(2, len(set(current.tokens)))
        self.assertNotIn("Uh, wait", prompt)
        self.assertEqual(target.encode(), current.restore(masked).encode())
        source = 'Um, keep ‘She said "wait" quietly.’ here.'
        target = 'Keep ‘She said "wait" quietly.’ here.'
        prompt, masked, current = pipeline.protected_pair(source, target, "specialist-compact-v4")
        self.assertEqual(1, len(current.tokens))
        self.assertNotIn("She said", prompt)
        self.assertEqual(target.encode(), current.restore(masked).encode())

    def test_resume_cannot_switch_literal_or_checkpointing_modes_in_either_direction(self):
        current = configuration()
        variants = (configuration("specialist-compact-v3"), configuration(checkpointing=False))
        self.assertEqual([], pipeline.validate_resume_configuration(current, copy.deepcopy(current)))
        for other in variants:
            for saved, expected in ((current, other), (other, current)):
                with self.subTest(saved=saved["literal_protocol"], gc=saved["gradient_checkpointing"]), self.assertRaises(ValueError):
                    pipeline.validate_resume_configuration(saved, expected)

    def test_resume_binds_helper_table_every_gc_source_and_gc_package_versions(self):
        expected = configuration()
        for field in ("literal_helper_sha256", "literal_word_ranges_sha256", *GC_SOURCES):
            saved = copy.deepcopy(expected)
            saved[field] = "0" * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                pipeline.validate_resume_configuration(saved, expected)
        for package in ("torch", "transformers"):
            saved = copy.deepcopy(expected)
            saved["packages"][package] = "different"
            with self.subTest(package=package), self.assertRaises(ValueError):
                pipeline.validate_resume_configuration(saved, expected)

    def test_new_mode_requires_declared_fields_including_null_for_disabled_gc(self):
        for expected, fields in ((configuration(), ("literal_protocol", "literal_helper_sha256", "literal_word_ranges_sha256", "gradient_checkpointing")),
                                 (configuration(checkpointing=False), ("gradient_checkpointing_use_reentrant", *GC_SOURCES))):
            for field in fields:
                saved = copy.deepcopy(expected)
                del saved[field]
                with self.subTest(field=field), self.assertRaises(ValueError):
                    pipeline.validate_resume_configuration(saved, expected)
        expected = configuration(checkpointing=False)
        saved = {**expected, "gradient_checkpointing_use_reentrant": False}
        with self.assertRaisesRegex(ValueError, "gradient_checkpointing_use_reentrant"):
            pipeline.validate_resume_configuration(saved, expected)

    def test_resume_boolean_modes_cannot_be_replaced_by_equal_integers(self):
        expected = configuration()
        for field, number in (("gradient_checkpointing", 1), ("gradient_checkpointing_use_reentrant", 0)):
            saved = copy.deepcopy(expected)
            saved[field] = number
            with self.subTest(field=field), self.assertRaises(ValueError):
                pipeline.validate_resume_configuration(saved, expected)

    def test_registered_legacy_v3_reports_missing_identity_without_inventing_it(self):
        saved = {"schema_version": 1, "training_source_sha256": LEGACY_SOURCE, "literal_protocol": "specialist-compact-v3"}
        original = copy.deepcopy(saved)
        missing = pipeline.validate_resume_configuration(saved, configuration("specialist-compact-v3", False))
        self.assertEqual({"literal_helper_sha256", "literal_word_ranges_sha256", "gradient_checkpointing",
                          "gradient_checkpointing_use_reentrant", *GC_SOURCES}, set(missing))
        self.assertEqual(original, saved)
        self.assertNotIn("literal_helper_sha256", saved)

    def test_legacy_waiver_requires_registered_source_helper_and_integer_schema(self):
        saved = {"schema_version": 1, "training_source_sha256": LEGACY_SOURCE, "literal_protocol": "specialist-compact-v3"}
        expected = configuration("specialist-compact-v3", False)
        variants = (({**saved, "training_source_sha256": "f" * 64}, expected),
                    ({**saved, "schema_version": True}, expected), ({**saved, "schema_version": False}, expected),
                    (saved, {**expected, "literal_helper_sha256": "0" * 64}))
        for actual, requested in variants:
            with self.subTest(saved=actual), self.assertRaises(ValueError):
                pipeline.validate_resume_configuration(actual, requested)

    def test_legacy_optional_waiver_never_waives_quantized_training_source_identity(self):
        saved = {"schema_version": 1, "training_source_sha256": LEGACY_SOURCE, "literal_protocol": "specialist-compact-v3",
                 "quantized_training_source_sha256": "8" * 64}
        expected = {**configuration("specialist-compact-v3", False), "quantized_training_source_sha256": "9" * 64}
        with self.assertRaisesRegex(ValueError, "quantized_training_source_sha256"):
            pipeline.validate_resume_configuration(saved, expected)


if __name__ == "__main__":
    unittest.main()
