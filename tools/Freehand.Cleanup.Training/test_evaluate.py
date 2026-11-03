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


class ProfileTests(unittest.TestCase):
    def test_lookup24_changes_only_the_bounded_draft_length_and_native_flags(self):
        expected = evaluate.runtime_profile()
        expected["promptLookupTokens"] = 24
        profile = evaluate.runtime_profile(24)
        self.assertEqual(expected, json.loads(json.dumps(profile)))
        flags = evaluate.native_server_arguments(profile)
        self.assertEqual("24", flags[flags.index("--spec-ngram-map-k-size-m") + 1])
        self.assertEqual("3", flags[flags.index("--spec-ngram-map-k-size-n") + 1])
        self.assertNotIn("--spec-type", evaluate.native_server_arguments(evaluate.runtime_profile(0)))

    def test_lookup_length_cannot_reach_logical_batch_or_use_nonintegers(self):
        for invalid in [-1, 64, 65, True, 24.5, "24", None]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                evaluate.runtime_profile(invalid)
        self.assertEqual(63, evaluate.runtime_profile(63)["promptLookupTokens"])

    def test_lookup24_freeze_serializes_selected_value_and_rejects_profile_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {}
            for name in ["model", "runtime", "runtime_inventory", "probe"]:
                paths[name] = root / name
                paths[name].write_text("fixture " + name)
            args = argparse.Namespace(**paths, output=root / "freeze.json", adapter_config=None,
                                      prompt_lookup_tokens=24)
            with patch("evaluate.source_files", return_value={}), patch("evaluate.managed_files", return_value=[]), \
                    patch("evaluate.small_models.verify_runtime_inventory", return_value={}), patch("builtins.print"):
                evaluate.freeze(args)
                value = json.loads(args.output.read_text())
                self.assertEqual(24, value["profile"]["promptLookupTokens"])
                evaluate.verify_freeze(args.output)
                frozen_identity = evaluate.artifact(args.output)
                value["profile"]["threads"] = 8
                args.output.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "Runtime profile drift"):
                    evaluate.verify_freeze(args.output)
                value["profile"] = evaluate.runtime_profile(25)
                args.output.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "Artifact drift"):
                    evaluate.verify_artifact(frozen_identity)


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


class PairedBlindTests(unittest.TestCase):
    def setUp(self):
        # Unit fixtures stand in for the independently hashed211MB original artifact.
        for name, value in (("ORIGINAL_SCRIBE_IQ4_XS_SHA256", evaluate.output_sha("control weights")),
                            ("ORIGINAL_SCRIBE_IQ4_XS_BYTES", len(b"control weights"))):
            mock = patch("evaluate." + name, value)
            mock.start()
            self.addCleanup(mock.stop)

    def fixtures(self, root):
        shared = {}
        for key in ("runtime", "runtime_inventory", "probe"):
            path = root / key
            path.write_text(key)
            shared[key] = evaluate.artifact(path)
        shared.update(managed_assemblies=[], sources={}, profile=evaluate.runtime_profile(),
                      quality_target=evaluate.quality_target(500),
                      source_snapshot=evaluate.snapshot_sources(root / "sources.tar.gz", {}))
        selected = copy.deepcopy(shared)
        control = copy.deepcopy(shared)
        for role, value in (("selected", selected), ("control", control)):
            path = root / (role + ".gguf")
            path.write_text(role + " weights")
            value["model"] = evaluate.artifact(path)
        provenance = root / "original-control.json"
        provenance.write_text(json.dumps({"role": "original_scribekey_control",
            "source_repository": "scribekey/scribekey-cleanup-fast",
            "source_revision": "c484dad2d815bff83d376e46b25a11dbc820992a",
            "source_model_sha256": evaluate.ORIGINAL_SCRIBE_BF16_SHA256,
            "source_f16": {"sha256": evaluate.ORIGINAL_SCRIBE_F16_SHA256},
            "quantization": "IQ4_XS", "adapter_applied": False, "quantized": control["model"]}))
        control["original_control_provenance"] = evaluate.artifact(provenance)
        paths = []
        for role, value in (("selected", selected), ("control", control)):
            path = root / (role + "-freeze.json")
            path.write_text(json.dumps(value))
            paths.append(path)
        corpus = root / "unopened-corpus.json"
        corpus.write_text(json.dumps({"schema_version": 1, "cases": [
            {"id": str(index), "input": "um keep it", "targets": ["Keep it."]}
            for index in range(500)]}))
        commitment = root / "COMMITMENT.json"
        commitment.write_text(json.dumps({"case_count": 500, "corpus_sha256": evaluate.sha256_file(corpus)}))
        args = argparse.Namespace(candidate_freeze=paths[0], paired_baseline_freeze=paths[1],
            dataset=corpus, blind_commitment=commitment, dotnet=root / "dotnet", phase="blind-final",
            mode="core", output=root / "paired-results")
        return args, selected, control

    def patches(self):
        return patch("evaluate.source_files", return_value={}), patch("evaluate.small_models.verify_runtime_inventory")

    def test_pair_profile_source_and_runtime_mismatches_rejected_before_corpus_open(self):
        for mismatch in ("profile", "sources", "runtime", "managed_assemblies"):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as directory:
                args, selected, baseline = self.fixtures(Path(directory))
                changed = copy.deepcopy(baseline)
                if mismatch == "profile":
                    changed[mismatch] = evaluate.runtime_profile(24)
                elif mismatch == "sources":
                    changed[mismatch] = {"tool.py": "different"}
                elif mismatch == "runtime":
                    changed[mismatch]["sha256"] = "different"
                else:
                    changed[mismatch] = [{"path": "another.dll", "bytes": 1, "sha256": "different"}]
                with patch("evaluate.verify_freeze", side_effect=[selected, changed]), \
                        patch("evaluate.phase_gate") as gate, patch("evaluate.load_corpus") as loader:
                    with self.assertRaisesRegex(ValueError, "mismatch"):
                        evaluate.native(args)
                    gate.assert_not_called()
                    loader.assert_not_called()
                self.assertFalse(args.blind_commitment.with_suffix(".consumed.json").exists())

    def test_control_artifact_drift_rejected_before_corpus_open(self):
        with tempfile.TemporaryDirectory() as directory:
            args, _, baseline = self.fixtures(Path(directory))
            Path(baseline["model"]["path"]).write_text("changed control weights")
            sources, runtime = self.patches()
            with sources, runtime, patch("evaluate.load_corpus") as loader:
                with self.assertRaisesRegex(ValueError, "Artifact drift"):
                    evaluate.native(args)
                loader.assert_not_called()
            self.assertFalse(args.blind_commitment.with_suffix(".consumed.json").exists())

    def test_trained_or_unproven_control_cannot_be_relabelled_as_original(self):
        with tempfile.TemporaryDirectory() as directory:
            _, selected, baseline = self.fixtures(Path(directory))
            with self.assertRaisesRegex(ValueError, "export provenance"):
                evaluate.verify_pair(baseline, selected)
            baseline["adapter"] = selected["model"]
            with self.assertRaisesRegex(ValueError, "trained adapter"):
                evaluate.verify_pair(selected, baseline)

    def test_fabricated_original_provenance_cannot_label_another_model_as_control(self):
        with tempfile.TemporaryDirectory() as directory:
            _, selected, baseline = self.fixtures(Path(directory))
            baseline["model"] = selected["model"]
            provenance = Path(baseline["original_control_provenance"]["path"])
            fabricated = json.loads(provenance.read_text())
            fabricated["quantized"] = selected["model"]
            provenance.write_text(json.dumps(fabricated))
            baseline["original_control_provenance"] = evaluate.artifact(provenance)
            with self.assertRaisesRegex(ValueError, "verified original IQ4_XS bytes/hash"):
                evaluate.verify_original_control(baseline)

    def test_paired_mode_is_bounded_to_blind_core(self):
        for phase, mode in (("development", "core"), ("blind-final", "native"), ("blind-final", "both")):
            with self.subTest(phase=phase, mode=mode), tempfile.TemporaryDirectory() as directory:
                args, _, _ = self.fixtures(Path(directory))
                args.phase, args.mode = phase, mode
                with patch("evaluate.load_corpus") as loader, self.assertRaisesRegex(ValueError, "blind-final Core"):
                    evaluate.native(args)
                loader.assert_not_called()

    def test_one_lock_binds_both_before_parse_and_both_full_denominators_survive_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            args, _, _ = self.fixtures(Path(directory))
            real_loader = evaluate.load_corpus
            calls = []
            def guarded_loader(path):
                lock = json.loads(args.blind_commitment.with_suffix(".consumed.json").read_text())
                self.assertEqual(evaluate.artifact(args.candidate_freeze), lock["candidate_freeze"])
                self.assertEqual(evaluate.artifact(args.paired_baseline_freeze), lock["paired_baseline_freeze"])
                self.assertEqual(500, lock["case_count_per_candidate"])
                return real_loader(path)
            def fake_probe(argv, log):
                # The control's full pre-run registration must exist before selected inference starts.
                self.assertTrue((args.output / "paired-baseline/evaluation-pre-run-freeze.json").is_file())
                output = Path(argv[argv.index("--output") + 1])
                is_baseline = output.parent.name == "paired-baseline"
                calls.append("original_control" if is_baseline else "selected_primary")
                cases = [{"id": str(index), "cleanup_status": "Failed" if index == 0 else "Applied"}
                         for index in range(500)]
                output.write_text(json.dumps({"incomplete": False, "cases": cases}))
                return 1  # Provider failures must not skip the second complete500 run.
            sources, runtime = self.patches()
            with sources, runtime, patch("evaluate.load_corpus", side_effect=guarded_loader), \
                    patch("evaluate.invoke", side_effect=fake_probe), patch("builtins.print"):
                self.assertEqual(1, evaluate.native(args))
            self.assertEqual(["selected_primary", "original_control"], calls)
            summary = json.loads((args.output / "paired-completion.json").read_text())
            self.assertTrue(summary["both_complete_denominators"])
            self.assertEqual(495, summary["quality_target_each"]["required_pass_count"])
            for role, subfolder in (("selected_primary", args.output), ("original_control", args.output / "paired-baseline")):
                metadata = json.loads((subfolder / "evaluation-pre-run-freeze.json").read_text())
                self.assertEqual(500, metadata["case_count"])
                self.assertEqual(500, len(set(metadata["case_ids"])))
                self.assertEqual(role, metadata["semantic_role"])
                self.assertEqual(role == "selected_primary", metadata["primary_qualification_candidate"])
                self.assertEqual(500, summary["candidate_reports"][role]["observed_count"])
            # A third candidate cannot reuse the same consumed test, even in a new output folder.
            args.output = Path(directory) / "third-results"
            sources, runtime = self.patches()
            with sources, runtime, patch("evaluate.load_corpus") as loader:
                with self.assertRaisesRegex(ValueError, "already been consumed"):
                    evaluate.native(args)
                loader.assert_not_called()

    def test_missing_or_duplicate_cases_cannot_claim_complete_500(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partial.json"
            for ids, incomplete in ((list(range(499)), False), (list(range(499)) + [498], False),
                                    (list(range(500)), True)):
                path.write_text(json.dumps({"incomplete": incomplete, "cases": [{"id": str(i)} for i in ids]}))
                inventory = evaluate.complete_core_inventory(path, [str(i) for i in range(500)])
                self.assertEqual(500, inventory["expected_count"])
                self.assertFalse(inventory["complete"])

    def completed_pair(self, root, malformed_selected=False):
        args, _, _ = self.fixtures(root)
        calls = []
        def fake_probe(argv, log):
            output = Path(argv[argv.index("--output") + 1])
            baseline = output.parent.name == "paired-baseline"
            calls.append(baseline)
            if malformed_selected and not baseline:
                output.write_text('{"incomplete":true,"cases":[')
                return 1
            text = "Keep that." if baseline else "Keep it."
            cases = [{"id": str(index), "input": "um keep it", "output": text,
                      "normalized_targets": ["Keep it."], "cleanup_status": "Applied",
                      "candidate_text": text, "insertion_count": 1, "delivered_count": 1, "error": None}
                     for index in range(500)]
            output.write_text(json.dumps({"incomplete": False, "cases": cases}))
            return 0
        sources, runtime = self.patches()
        with sources, runtime, patch("evaluate.invoke", side_effect=fake_probe), patch("builtins.print"):
            code = evaluate.native(args)
        self.assertEqual([False, True], calls)
        self.assertEqual(int(malformed_selected), code)
        return args

    def review_args(self, results):
        judgments = results.parent / "reviewed.json"
        judgments.write_text(json.dumps({"reviewer": "fixture reviewer", "cases": [{
            "case_id": row["case_id"], "output_sha256": evaluate.output_sha(row["output"]),
            "semantic_faithful": True, "clean_usable": True, "critical_error": False}
            for row in evaluate.result_rows(results)]}))
        return argparse.Namespace(results=results, judgments=judgments, output=results.parent / "summary.json")

    def test_scored_summary_retains_role_and_control_cannot_replace_selected_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.completed_pair(Path(directory))
            for role, folder in (("selected_primary", args.output), ("original_control", args.output / "paired-baseline")):
                review_args = self.review_args(folder / "core-results.json")
                with patch("builtins.print"):
                    evaluate.review(review_args)
                summary = json.loads(review_args.output.read_text())
                self.assertEqual(500, summary["case_count"])
                self.assertTrue(summary["quality_gate_passed"])
                self.assertEqual(role, summary["semantic_role"])
                self.assertEqual(role == "selected_primary", summary["primary_qualification_candidate"])
                self.assertEqual(role == "selected_primary", summary["selected_primary_quality_gate_passed"])
                self.assertIn("original_control", summary["paired_evaluation"])
                self.assertEqual(evaluate.artifact(args.output / "paired-completion.json"), summary["paired_completion"])

    def test_malformed_selected_report_preserved_and_control_still_completes_500(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.completed_pair(Path(directory), malformed_selected=True)
            summary = json.loads((args.output / "paired-completion.json").read_text())
            self.assertFalse(summary["both_complete_denominators"])
            self.assertEqual(500, summary["candidate_reports"]["original_control"]["observed_count"])
            selected = summary["candidate_reports"]["selected_primary"]
            self.assertFalse(selected["complete"])
            self.assertEqual(evaluate.artifact(args.output / "core-results.json"), selected["report"])
            self.assertIn("Unusable", selected["error"])

    def test_paired_review_rejects_missing_failed_receipt_or_swapped_role_report(self):
        for defect in ("missing_completion", "post_run_failed", "control_incomplete", "swapped_report", "missing_control_metadata"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                args = self.completed_pair(Path(directory))
                results = args.output / "core-results.json"
                completion = args.output / "paired-completion.json"
                if defect == "missing_completion":
                    completion.unlink()
                elif defect in ("post_run_failed", "control_incomplete"):
                    value = json.loads(completion.read_text())
                    if defect == "post_run_failed":
                        value["post_run_identities_verified"] = False
                    else:
                        value["candidate_reports"]["original_control"]["complete"] = False
                    completion.write_text(json.dumps(value))
                elif defect == "swapped_report":
                    results.write_bytes((args.output / "paired-baseline/core-results.json").read_bytes())
                else:
                    results = args.output / "paired-baseline/core-results.json"
                    (results.parent / "evaluation-pre-run-freeze.json").unlink()
                review_args = self.review_args(results)
                with self.assertRaisesRegex(ValueError, "Paired"):
                    evaluate.review(review_args)
                self.assertFalse(review_args.output.exists())

    def test_full500_rows_marked_incomplete_cannot_be_scored(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.completed_pair(Path(directory))
            results = args.output / "core-results.json"
            value = json.loads(results.read_text())
            value["incomplete"] = True
            results.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "incomplete"):
                evaluate.result_rows(results)


if __name__ == "__main__":
    unittest.main()
