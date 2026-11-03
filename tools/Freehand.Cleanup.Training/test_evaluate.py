"""Cheap checks for evaluation identity and semantic-review integrity."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import patch

import evaluate


class ReviewTests(unittest.TestCase):
    def rows(self, count=100):
        return [{"case_id": str(index), "input": "um keep it", "output": "Keep it.",
                 "targets": ["Keep it."], "structural_success": True} for index in range(count)]

    def judgments(self, rows):
        return {"reviewer": "test reviewer", "cases": [{"case_id": row["case_id"],
                "output_sha256": evaluate.output_sha(row["output"]), "semantic_faithful": True,
                "clean_usable": True, "critical_error": False} for row in rows]}

    def test_exact_targets_without_explicit_semantic_review_do_not_pass(self):
        rows = self.rows(1)
        review = self.judgments(rows)
        review["cases"][0]["semantic_faithful"] = None
        with self.assertRaisesRegex(ValueError, "Explicit boolean"):
            evaluate.score_review(rows, review)

    def test_matching_target_does_not_override_semantic_failure(self):
        rows = self.rows(100)
        review = self.judgments(rows)
        for item in review["cases"][:3]:
            item["semantic_faithful"] = False
        score = evaluate.score_review(rows, review)
        self.assertEqual(100, score["exact_target_matches_diagnostic_only"])
        self.assertEqual(.97, score["joint_accuracy"])
        self.assertFalse(score["quality_gate_passed"])

    def test_490_of_500_joint_successes_fail_the_current_99_percent_target(self):
        rows = self.rows(500)
        review = self.judgments(rows)
        for item in review["cases"][:5]:
            item["semantic_faithful"] = False
        for item in review["cases"][5:10]:
            item["clean_usable"] = False
        score = evaluate.score_review(rows, review)
        self.assertEqual(.98, score["joint_accuracy"])
        self.assertEqual(.99, score["minimum_joint_accuracy"])
        self.assertEqual(495, score["required_pass_count"])
        self.assertFalse(score["quality_gate_passed"])

    def test_495_of_500_joint_successes_pass_the_current_99_percent_target(self):
        rows = self.rows(500)
        review = self.judgments(rows)
        for item in review["cases"][:3]:
            item["semantic_faithful"] = False
        for item in review["cases"][3:5]:
            item["clean_usable"] = False
        score = evaluate.score_review(rows, review)
        self.assertEqual(.99, score["joint_accuracy"])
        self.assertEqual(495, score["faithful_and_clean_usable"])
        self.assertTrue(score["quality_gate_passed"])

    def test_six_structural_failures_remain_in_the_500_case_denominator(self):
        rows = self.rows(500)
        review = self.judgments(rows)
        for row in rows[:6]:
            row["structural_success"] = False
        score = evaluate.score_review(rows, review)
        self.assertEqual(500, score["case_count"])
        self.assertEqual(494, score["faithful_and_clean_usable"])
        self.assertEqual(6, score["failed_or_unusable_cases"])
        self.assertFalse(score["quality_gate_passed"])

    def test_missing_final_case_is_not_removed_from_the_denominator(self):
        rows = self.rows(499)
        review = self.judgments(rows)
        with self.assertRaisesRegex(ValueError, "pre-run case inventory"):
            evaluate.score_review(rows, review, expected_ids={str(index) for index in range(500)})

    def test_critical_errors_are_failed_cases_and_explicitly_reported(self):
        rows = self.rows(100)
        review = self.judgments(rows)
        review["cases"][0]["critical_error"] = True
        score = evaluate.score_review(rows, review)
        self.assertEqual(.99, score["joint_accuracy"])
        self.assertEqual(1, score["critical_errors"])
        self.assertTrue(score["quality_gate_passed"])
        self.assertFalse(score["zero_observed_critical_errors"])

    def test_structural_failure_or_fallback_cannot_earn_model_accuracy(self):
        rows = self.rows(100)
        review = self.judgments(rows)
        for row in rows[:3]:
            row["structural_success"] = False
        score = evaluate.score_review(rows, review)
        self.assertFalse(score["quality_gate_passed"])
        self.assertEqual(97, score["faithful_and_clean_usable"])

    def test_missing_duplicate_unknown_cases_are_rejected(self):
        rows = self.rows(2)
        review = self.judgments(rows)
        with self.assertRaises(ValueError):
            evaluate.score_review(rows, {"cases": review["cases"][:1]})
        duplicate = copy.deepcopy(review)
        duplicate["cases"][1]["case_id"] = "0"
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            evaluate.score_review(rows, duplicate)
        unknown = copy.deepcopy(review)
        unknown["cases"][1]["case_id"] = "unobserved"
        with self.assertRaisesRegex(ValueError, "IDs differ"):
            evaluate.score_review(rows, unknown)

    def test_review_is_bound_to_exact_delivered_bytes(self):
        rows = self.rows(1)
        review = self.judgments(rows)
        rows[0]["output"] = "Do not keep it."
        with self.assertRaisesRegex(ValueError, "exact output bytes"):
            evaluate.score_review(rows, review)

    def test_partial_result_denominator_is_rejected(self):
        rows = self.rows(1)
        with self.assertRaisesRegex(ValueError, "pre-run case inventory"):
            evaluate.score_review(rows, self.judgments(rows), expected_ids={"0", "1"})

    def test_semantic_review_requires_named_reviewer(self):
        rows = self.rows(1)
        review = self.judgments(rows)
        review["reviewer"] = ""
        with self.assertRaisesRegex(ValueError, "Name the semantic reviewer"):
            evaluate.score_review(rows, review)


class CorpusTests(unittest.TestCase):
    def test_pre_run_snapshot_preserves_exact_source_after_later_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "tool.py"
            original = b"print('original source')\n"
            script.write_bytes(original)
            archive = root / "source-snapshot.tar.gz"
            with patch("evaluate.ROOT", root):
                value = evaluate.snapshot_sources(archive, {"tool.py": evaluate.sha256_file(script)})
            script.write_text("print('later changed source')\n")
            with tarfile.open(archive, "r:gz") as saved:
                self.assertEqual(original, saved.extractfile("tool.py").read())
            self.assertTrue(value["exact_archived_bytes_verified"])
            self.assertEqual(1, value["source_file_count"])
            self.assertEqual("new_candidate_freeze_before_inference", value["capture_stage"])

    def test_optional_adapter_is_rechecked_after_candidate_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entries = {}
            for key in ("model", "runtime", "runtime_inventory", "probe", "adapter", "adapter_config"):
                path = root / key
                path.write_text("original " + key)
                entries[key] = evaluate.artifact(path)
            value = {**entries, "managed_assemblies": [], "sources": {}, "profile": evaluate.runtime_profile(),
                     "quality_target": evaluate.quality_target(500),
                     "source_snapshot": evaluate.snapshot_sources(root / "source-snapshot.tar.gz", {})}
            frozen = root / "freeze.json"
            frozen.write_text(json.dumps(value))
            with patch("evaluate.source_files", return_value={}), patch("evaluate.small_models.verify_runtime_inventory"):
                evaluate.verify_freeze(frozen)
                (root / "adapter").write_text("changed weights")
                with self.assertRaisesRegex(ValueError, "Artifact drift"):
                    evaluate.verify_freeze(frozen)

    def test_jsonl_conversion_retains_minimal_targets_and_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "development.jsonl"
            path.write_text(json.dumps({"id": "dev1", "input": "um keep it", "target": "Keep it.",
                                        "family": "fillers"}) + "\n", encoding="utf-8")
            case = evaluate.load_corpus(path)["cases"][0]
            self.assertEqual("dev1", case["id"])
            self.assertEqual(["Keep it."], case["targets"])
            self.assertEqual("fillers", case["category"])

    def test_duplicate_case_ids_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            row = {"id": "same", "input": "Hello.", "targets": ["Hello."]}
            path.write_text(json.dumps({"cases": [row, row]}))
            with self.assertRaisesRegex(ValueError, "unique"):
                evaluate.load_corpus(path)

    def test_blind_paths_cannot_be_opened_as_development(self):
        args = argparse.Namespace(phase="development", dataset=Path("work/blind-final/corpus.json"))
        with self.assertRaisesRegex(ValueError, "Blind corpus"):
            evaluate.phase_gate(args, {})

    def test_blind_requires_prior_commitment(self):
        args = argparse.Namespace(phase="blind-final", dataset=Path("unopened.json"), blind_commitment=None)
        with self.assertRaisesRegex(ValueError, "prior independent"):
            evaluate.phase_gate(args, {})


if __name__ == "__main__":
    unittest.main()
