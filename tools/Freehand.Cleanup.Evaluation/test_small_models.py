"""Offline regression checks for native replay's completeness and BOS boundary."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from small_models import literal_mask_protocol, replay, selected_asset, verify_runtime_inventory
from literal_protection import LiteralProtectionMask
from specialist_literal_protection import SpecialistLiteralMask


class FakeServer:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, endpoint, payload, deadline):
        self.calls.append((endpoint, copy.deepcopy(payload), deadline))
        return next(self.responses), .01


class SmallModelReplayTests(unittest.TestCase):
    def setUp(self):
        self.arguments = argparse.Namespace(context=2048, max_output=512, request_timeout=10)
        self.exported = {
            "fixture": {"id": "test-1", "input": "um can you send it", "split": "development", "category": "question"},
            "normalized_input": "um can you send it", "normalized_targets": ["Can you send it?"],
            "normalized_checks": {"include": ["send it"], "exclude": ["um"]},
            "completion": {"text": "<|startoftext|>trained prompt", "stop": ["###"],
                           "temperature": 0, "repeat_penalty": 1, "seed": 0, "add_special": False},
            "messages": None,
        }

    def test_native_generation_receives_validated_token_array_with_exact_bos_setting(self):
        server = FakeServer([{"tokens": [1, 2, 3]}, {"content": "Can you send it?", "stop_type": "eos"}])
        row = replay(server, self.exported, self.arguments)
        self.assertEqual("completed", row["status"])
        self.assertEqual("/tokenize", server.calls[0][0])
        self.assertFalse(server.calls[0][1]["add_special"])
        self.assertEqual([1, 2, 3], server.calls[1][1]["prompt"])
        self.assertTrue(row["grade"]["normalized_target_match"])

    def test_oversized_input_is_rejected_before_inference(self):
        server = FakeServer([{"tokens": [1] * 1537}])
        row = replay(server, self.exported, self.arguments)
        self.assertEqual("failed", row["status"])
        self.assertIn("refusing truncation", row["error"])
        self.assertEqual(1, len(server.calls))

    def test_length_limited_response_remains_available_without_being_counted_completed(self):
        response = {"content": "Can you send", "stop_type": "limit", "stopped_limit": True}
        server = FakeServer([{"tokens": [1]}, response])
        row = replay(server, self.exported, self.arguments)
        self.assertEqual("failed", row["status"])
        self.assertEqual(response, row["raw_response"])
        self.assertEqual("Can you send", row["raw_model_output"])

    def test_quality_failure_is_retained_as_completed_for_semantic_review(self):
        server = FakeServer([{"tokens": [1]}, {"content": "Yes, I can.", "stop_type": "eos"}])
        row = replay(server, self.exported, self.arguments)
        self.assertEqual("completed", row["status"])
        self.assertEqual("known_failure", row["grade"]["quality_status"])
        self.assertEqual("Yes, I can.", row["output"])

    def test_generic_model_uses_its_embedded_template_and_exported_messages(self):
        exported = copy.deepcopy(self.exported)
        exported["completion"] = None
        exported["messages"] = [{"role": "system", "content": "exact policy"}, {"role": "user", "content": "exact data"}]
        server = FakeServer([{"prompt": "model-rendered template"}, {"tokens": [1, 2]},
                             {"choices": [{"finish_reason": "stop", "message": {"content": "Can you send it?"}}]}])
        row = replay(server, exported, self.arguments)
        self.assertEqual("completed", row["status"])
        self.assertEqual("/apply-template", server.calls[0][0])
        self.assertEqual("model-rendered template", server.calls[1][1]["content"])
        self.assertEqual("/v1/chat/completions", server.calls[2][0])
        self.assertEqual(exported["messages"], server.calls[2][1]["messages"])

    def test_opt_in_native_mask_restores_exact_literal_bytes(self):
        exported = copy.deepcopy(self.exported)
        text = "Keep [[FREEHAND_LITERAL_01_START]] C:\\Acme\tLabs\r\n [[FREEHAND_LITERAL_01_END]] exactly."
        exported["fixture"]["input"] = text
        exported["normalized_input"] = text
        exported["normalized_targets"] = [text]
        exported["normalized_checks"] = {"literals": [" C:\\Acme\tLabs\r\n "]}
        exported["mask_literals"] = True
        server = FakeServer([{"tokens": [1]}, {"content": LiteralProtectionMask.create(text).masked_text, "stop_type": "eos"}])

        row = replay(server, exported, self.arguments)

        self.assertEqual("completed", row["status"])
        self.assertEqual(text, row["output"])
        self.assertNotIn("C:\\Acme", row["raw_model_output"])
        self.assertTrue(row["mask_literals"])

    def test_opt_in_native_mask_rejects_missing_identifier(self):
        exported = copy.deepcopy(self.exported)
        exported["normalized_input"] = "Keep [[FREEHAND_LITERAL_01_START]] Acme [[FREEHAND_LITERAL_01_END]] exactly."
        exported["mask_literals"] = True
        server = FakeServer([{"tokens": [1]}, {"content": "Keep Acme exactly.", "stop_type": "eos"}])

        row = replay(server, exported, self.arguments)

        self.assertEqual("failed", row["status"])
        self.assertEqual("Keep Acme exactly.", row["raw_model_output"])

    def test_compact_specialist_protocol_preserves_quotes_and_literal_bytes_together(self):
        exported = copy.deepcopy(self.exported)
        text = 'Keep "very, very small" and [[FREEHAND_LITERAL_01_START]]  café\tΔ🙂  [[FREEHAND_LITERAL_01_END]] exactly.'
        exported.update(normalized_input=text, normalized_targets=[text], mask_literals=True,
                        literal_mask_protocol="specialist-compact-v2")
        mask = SpecialistLiteralMask.create(text)
        exported["model_input_sha256"] = hashlib.sha256(mask.masked_text.encode("utf-8")).hexdigest()
        server = FakeServer([{"tokens": [1]}, {"content": mask.masked_text, "stop_type": "eos"}])

        row = replay(server, exported, self.arguments)

        self.assertEqual("completed", row["status"])
        self.assertEqual(text, row["output"])
        self.assertNotIn("very, very small", row["raw_model_output"])
        self.assertNotIn("café", row["raw_model_output"])
        self.assertEqual("specialist-compact-v2", row["literal_mask_protocol"])

    def test_managed_python_mask_difference_fails_before_server_call(self):
        exported = copy.deepcopy(self.exported)
        exported.update(mask_literals=True, literal_mask_protocol="specialist-compact-v2", model_input_sha256="0" * 64)
        server = FakeServer([])

        row = replay(server, exported, self.arguments)

        self.assertEqual("failed", row["status"])
        self.assertIn("differs from the exported managed", row["error"])
        self.assertEqual([], server.calls)

    def test_frozen_native_legacy_exports_without_protocol_remain_legacy(self):
        self.assertEqual("literal-token-v1", literal_mask_protocol({"mask_literals": True}, False))
        self.assertEqual("literal-token-v1", literal_mask_protocol({}, True))
        self.assertEqual("none", literal_mask_protocol({}, False))

    def test_unknown_or_inconsistent_protocols_fail_closed(self):
        for exported, general in [({"mask_literals": True, "literal_mask_protocol": "unknown"}, False),
                                  ({"mask_literals": False, "literal_mask_protocol": "specialist-compact-v2"}, False),
                                  ({"mask_literals": True, "literal_mask_protocol": "none"}, False),
                                  ({"mask_literals": True, "literal_mask_protocol": "specialist-compact-v2"}, True),
                                  ({"mask_literals": "true"}, False)]:
            with self.subTest(exported=exported, general=general), self.assertRaises(ValueError):
                literal_mask_protocol(exported, general)

    def test_v2_and_v3_replay_apply_only_their_versioned_quote_period_rule(self):
        text = 'She said "Go."'
        masked = SpecialistLiteralMask.create(text).masked_text
        for protocol, expected in [("specialist-compact-v2", text + "."), ("specialist-compact-v3", text)]:
            with self.subTest(protocol=protocol):
                exported = copy.deepcopy(self.exported)
                exported.update(normalized_input=text, normalized_targets=[expected], mask_literals=True,
                                literal_mask_protocol=protocol)
                exported["model_input_sha256"] = hashlib.sha256(masked.encode("utf-8")).hexdigest()
                server = FakeServer([{"tokens": [1]}, {"content": masked + ".", "stop_type": "eos"}])

                row = replay(server, exported, self.arguments)

                self.assertEqual("completed", row["status"])
                self.assertEqual(expected, row["output"])
                self.assertEqual(protocol, row["literal_mask_protocol"])

    def test_ambiguous_or_unverified_asset_selection_is_rejected(self):
        with self.assertRaises(ValueError):
            selected_asset({"assets": [{"id": "model-a", "verified": True}, {"id": "model-b", "verified": True}]}, "model")
        with self.assertRaises(ValueError):
            selected_asset({"assets": [{"id": "model-a", "verified": False}]}, "model-a")

    def test_complete_runtime_inventory_detects_a_changed_shared_library(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "runtime"
            directory.mkdir()
            runtime = directory / "llama-server"
            runtime.write_bytes(b"launcher")
            library = directory / "libllama.so"
            library.write_bytes(b"library")
            inventory = Path(temporary) / "index.json"
            inventory.write_text(json.dumps({"directory": str(directory), "files": [
                {"name": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                for path in (runtime, library)]}))
            self.assertEqual(2, verify_runtime_inventory(inventory, runtime)["verified_file_count"])
            library.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verify_runtime_inventory(inventory, runtime)


if __name__ == "__main__":
    unittest.main()
