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
    def test_literal_v4_is_an_explicit_typed_profile_while_legacy_fields_stay_absent(self):
        baseline = evaluate.runtime_profile()
        self.assertNotIn("specialistLiteralProtocol", baseline)
        self.assertEqual("specialist-compact-v3", evaluate.frozen_specialist_literal_protocol({"profile": baseline}))
        current = evaluate.runtime_profile(literal_protocol="specialist-compact-v4")
        self.assertEqual({**baseline, "specialistLiteralProtocol": "CompactV4"}, current)
        self.assertEqual("specialist-compact-v4", evaluate.frozen_specialist_literal_protocol(
            {"profile": current, "specialist_literal_protocol": "specialist-compact-v4"}))
        for invalid in (None, True, 4, "CompactV4", "specialist-compact-v5"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                evaluate.runtime_profile(literal_protocol=invalid)
        for frozen in ({"profile": current}, {"profile": baseline, "specialist_literal_protocol": "specialist-compact-v4"},
                       {"profile": baseline, "specialist_literal_protocol": True}):
            with self.subTest(frozen=frozen), self.assertRaises(ValueError):
                evaluate.frozen_specialist_literal_protocol(frozen)

    def test_v4_freeze_manifest_export_and_actual_probe_protocol_are_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {}
            for name in ("model", "runtime", "runtime_inventory", "probe"):
                paths[name] = root / name
                paths[name].write_text("fixture " + name)
            dataset = root / "dataset.json"
            corpus = {"cases": [{"id": "fixture", "input": "Um, keep 'Uh, wait' here.", "targets": ["Keep 'Uh, wait' here."]}]}
            dataset.write_text(json.dumps(corpus))
            args = argparse.Namespace(**paths, output=root / "freeze.json", adapter_config=None,
                prompt_lookup_tokens=16, specialist_literal_protocol="specialist-compact-v4",
                dataset=dataset, phase="development", mode="native", blind_commitment=None, dotnet=root / "no-dotnet")
            with patch("evaluate.source_files", return_value={}), patch("evaluate.managed_files", return_value=[]), \
                    patch("evaluate.small_models.verify_runtime_inventory", return_value={}), patch("builtins.print"):
                evaluate.freeze(args)
                frozen = evaluate.verify_freeze(args.output)
                self.assertEqual("specialist-compact-v4", frozen["specialist_literal_protocol"])
                output = root / "evaluation"
                evaluate.prepare_evaluation(args, frozen, evaluate.artifact(args.output), corpus, output, "selected_primary", None)
                metadata = json.loads((output / "evaluation-pre-run-freeze.json").read_text())
                self.assertEqual("specialist-compact-v4", metadata["specialist_literal_protocol"])
                with patch("evaluate.invoke", return_value=1) as invoke:
                    evaluate.execute_evaluation(args, frozen, output)
                command = invoke.call_args.args[0]
                self.assertEqual("specialist-compact-v4", command[command.index("--specialist-literal-protocol") + 1])
                manifest_path = output / "cleanup-manifest.json"
                manifest = json.loads(manifest_path.read_text());manifest.pop("specialistLiteralProtocol")
                manifest_path.write_text(json.dumps(manifest))
                with patch("evaluate.invoke") as invoke, self.assertRaisesRegex(ValueError, "manifest specialist"):
                    evaluate.execute_evaluation(args, frozen, output)
                invoke.assert_not_called()

    def test_v4_requires_matching_typed_actual_probe_metadata_but_legacy_does_not(self):
        identity = {"base_sha256": "a" * 64, "base_bytes": 5, "runtime_adapter_sha256": None,
                    "runtime_adapter_bytes": None, "runtime_adapter_scale": None}
        metadata = {"model": {"expected_sha256": "a" * 64, "actual_sha256": "a" * 64}}
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "report.json"
            report.write_text(json.dumps({"metadata": metadata}))
            evaluate.verify_core_deployment(report, identity)
            for value in (None, True, 4, "specialist-compact-v3", "CompactV4"):
                report.write_text(json.dumps({"metadata": {**metadata, "specialist_literal_protocol": value}}))
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "literal protocol"):
                    evaluate.verify_core_deployment(report, identity, literal_protocol="specialist-compact-v4")
            report.write_text(json.dumps({"metadata": {**metadata, "specialist_literal_protocol": "specialist-compact-v4"}}))
            evaluate.verify_core_deployment(report, identity, literal_protocol="specialist-compact-v4")

    def test_cache_precision_is_explicit_typed_and_defaults_to_f16(self):
        baseline = evaluate.runtime_profile()
        self.assertEqual(("f16", "f16"), (baseline["cacheTypeK"], baseline["cacheTypeV"]))
        for key_type, value_type in (("f32", "f32"), ("f32", "f16"), ("f16", "f32")):
            profile = evaluate.runtime_profile(cache_type_k=key_type, cache_type_v=value_type)
            expected = {**baseline, "cacheTypeK": key_type, "cacheTypeV": value_type}
            self.assertEqual(expected, profile)
            flags = evaluate.native_server_arguments(profile)
            self.assertEqual(1, flags.count("--cache-type-k"))
            self.assertEqual(1, flags.count("--cache-type-v"))
            self.assertEqual(key_type, flags[flags.index("--cache-type-k") + 1])
            self.assertEqual(value_type, flags[flags.index("--cache-type-v") + 1])

    def test_cache_precision_rejects_wrong_types_and_unsupported_native_options(self):
        for invalid in (None, True, 32, "float32", "F32", "q8_0", "f32 --model another.gguf"):
            for field, argument in (("cacheTypeK", "cache_type_k"), ("cacheTypeV", "cache_type_v")):
                with self.subTest(invalid=invalid, field=field):
                    with self.assertRaisesRegex(ValueError, "cache precision"):
                        evaluate.runtime_profile(**{argument: invalid})
                    with self.assertRaisesRegex(ValueError, "cache precision"):
                        evaluate.native_server_arguments({**evaluate.runtime_profile(), field: invalid})

    def test_new_f32_freeze_binds_profile_native_args_and_core_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {}
            for name in ("model", "runtime", "runtime_inventory", "probe"):
                paths[name] = root / name
                paths[name].write_text("fixture " + name)
            dataset = root / "dataset.json"
            corpus = {"cases": [{"id": "fixture", "input": "um keep this", "targets": ["Keep this."]}]}
            dataset.write_text(json.dumps(corpus))
            args = argparse.Namespace(**paths, output=root / "freeze.json", adapter_config=None,
                                      prompt_lookup_tokens=16, cache_type_k="f32", cache_type_v="f32",
                                      dataset=dataset, phase="development", mode="core", blind_commitment=None)
            with patch("evaluate.source_files", return_value={}), patch("evaluate.managed_files", return_value=[]), \
                    patch("evaluate.small_models.verify_runtime_inventory", return_value={}), patch("builtins.print"):
                evaluate.freeze(args)
                frozen = evaluate.verify_freeze(args.output)
                self.assertEqual({"cacheTypeK": "f32", "cacheTypeV": "f32"}, frozen["cache_configuration"])
                output = root / "evaluation"
                evaluate.prepare_evaluation(args, frozen, evaluate.artifact(args.output), corpus, output, "selected_primary", None)
                preregistration = json.loads((output / "evaluation-pre-run-freeze.json").read_text())
                self.assertEqual(frozen["cache_configuration"], preregistration["cache_configuration"])
                manifest_path = output / "cleanup-manifest.json"
                manifest = json.loads(manifest_path.read_text())
                self.assertEqual(("f32", "f32"), (manifest["cacheTypeK"], manifest["cacheTypeV"]))
                manifest["cacheTypeV"] = "f16"
                manifest_path.write_text(json.dumps(manifest))
                with patch("evaluate.invoke") as invoke, self.assertRaisesRegex(ValueError, "manifest cache"):
                    evaluate.execute_evaluation(args, frozen, output)
                invoke.assert_not_called()
                edited = json.loads(args.output.read_text())
                edited["profile"]["cacheTypeV"] = "f16"
                args.output.write_text(json.dumps(edited))
                with self.assertRaisesRegex(ValueError, "cache profile"):
                    evaluate.verify_freeze(args.output)

    def test_explicit_cache_freeze_requires_matching_typed_actual_core_metadata(self):
        identity = {"base_sha256": "a" * 64, "base_bytes": 5, "runtime_adapter_sha256": None,
                    "runtime_adapter_bytes": None, "runtime_adapter_scale": None}
        metadata = {"model": {"expected_sha256": "a" * 64, "actual_sha256": "A" * 64},
                    "cache_type_k": "f32", "cache_type_v": "f32"}
        declared = {"cacheTypeK": "f32", "cacheTypeV": "f32"}
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "report.json"
            report.write_text(json.dumps({"metadata": metadata}))
            evaluate.verify_core_deployment(report, identity, declared)
            for field in ("cache_type_k", "cache_type_v"):
                for invalid in ("f16", "F32", "unknown", None, True, 32):
                    changed = {**metadata, field: invalid}
                    report.write_text(json.dumps({"metadata": changed}))
                    with self.subTest(field=field, value=invalid), self.assertRaisesRegex(ValueError, "cache precision"):
                        evaluate.verify_core_deployment(report, identity, declared)
                changed = {key: value for key, value in metadata.items() if key != field}
                report.write_text(json.dumps({"metadata": changed}))
                with self.assertRaisesRegex(ValueError, "cache precision"):
                    evaluate.verify_core_deployment(report, identity, declared)
            report.write_text(json.dumps({"metadata": {"model": metadata["model"]}}))
            evaluate.verify_core_deployment(report, identity)  # Unmodified legacy report remains compatible.
            with self.assertRaisesRegex(ValueError, "cache precision"):
                evaluate.verify_core_deployment(report, identity, {"cacheTypeK": "f16", "cacheTypeV": "f16"})

    def test_cache_metadata_failure_is_preserved_as_a_failed_deployment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "results"
            output.mkdir()
            profile = evaluate.runtime_profile(cache_type_k="f32", cache_type_v="f32")
            frozen = {"profile": profile, "cache_configuration": {"cacheTypeK": "f32", "cacheTypeV": "f32"},
                      "model": {"sha256": "a" * 64, "bytes": 5}, "probe": {"path": "fixture-probe.dll"}}
            (output / "cleanup-manifest.json").write_text(json.dumps(profile))
            def fake_probe(argv, log):
                (output / "core-results.json").write_text(json.dumps({"incomplete": False, "cases": [{"id": "kept"}],
                    "metadata": {"model": {"expected_sha256": "a" * 64, "actual_sha256": "a" * 64},
                                 "cache_type_k": "f16", "cache_type_v": "f16"}}))
                return 0
            args = argparse.Namespace(mode="core", dotnet=Path("fixture-dotnet"))
            with patch("evaluate.invoke", side_effect=fake_probe):
                codes = evaluate.execute_evaluation(args, frozen, output)
            self.assertEqual(1, codes["runtime_deployment"])
            receipt = json.loads((output / "runtime-deployment-verification.json").read_text())
            self.assertFalse(receipt["verified"])
            self.assertEqual(evaluate.artifact(output / "core-results.json"), receipt["report"])
            self.assertEqual([{"id": "kept"}], json.loads((output / "core-results.json").read_text())["cases"])

    def test_legacy_f16_freezes_remain_f16_and_cannot_be_silently_promoted(self):
        legacy = {"profile": evaluate.runtime_profile()}
        self.assertEqual({"cacheTypeK": "f16", "cacheTypeV": "f16"}, evaluate.frozen_cache_configuration(legacy))
        legacy["profile"]["cacheTypeK"] = "f32"
        with self.assertRaisesRegex(ValueError, "cache profile"):
            evaluate.frozen_cache_configuration(legacy)
        for malformed in (None, [], {}, {"cacheTypeK": "f32"}, {"cacheTypeK": "f16", "cacheTypeV": True},
                          {"cacheTypeK": "f16", "cacheTypeV": "f16", "extra": "f32"}):
            with self.subTest(configuration=malformed), self.assertRaises(ValueError):
                evaluate.frozen_cache_configuration({"profile": evaluate.runtime_profile(), "cache_configuration": malformed})

    def test_freeze_cli_cache_choices_are_explicit_and_keep_the_f16_default(self):
        arguments = ["evaluate.py", "freeze", "--model", "fixture.gguf", "--runtime", "fixture-server",
                     "--runtime-inventory", "fixture-index.json", "--probe", "fixture-probe.dll", "--output", "fixture-freeze.json"]
        for flags, expected in (([], "f16"), (["--cache-type-k", "f32", "--cache-type-v", "f32"], "f32")):
            with patch("sys.argv", arguments + flags), patch("evaluate.freeze", return_value=0) as freeze:
                self.assertEqual(0, evaluate.main())
                parsed = freeze.call_args.args[0]
                self.assertEqual((expected, expected), (parsed.cache_type_k, parsed.cache_type_v))
        with patch("sys.argv", arguments + ["--cache-type-k", "arbitrary"]), patch("sys.stderr"), \
                patch("evaluate.freeze") as freeze, self.assertRaises(SystemExit):
            evaluate.main()
        freeze.assert_not_called()

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
        return patch("evaluate.source_files", return_value={}), patch("evaluate.small_models.verify_runtime_inventory", return_value={})

    def deployed_fixture(self, root, selected, baseline):
        path = root / "deployed-native.gguf"
        path.write_text("native GGUF adapter fixture")
        selected["model"] = copy.deepcopy(baseline["model"])
        selected["runtime_adapter"] = evaluate.artifact(path)
        selected["profile"] = evaluate.runtime_profile(16, selected["runtime_adapter"], 1)
        return path

    def test_same_base_with_pinned_deployed_adapter_has_distinct_effective_pair_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, selected, baseline = self.fixtures(root)
            self.deployed_fixture(root, selected, baseline)
            evaluate.verify_pair(selected, baseline)
            self.assertNotEqual(evaluate.effective_model_identity(selected), evaluate.effective_model_identity(baseline))
            baseline["runtime_adapter"] = selected["runtime_adapter"]
            baseline["profile"] = selected["profile"]
            with self.assertRaisesRegex(ValueError, "deployed runtime adapter"):
                evaluate.verify_pair(selected, baseline)

    def test_deployed_adapter_drift_is_rejected_before_test_open(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args, selected, baseline = self.fixtures(root)
            path = self.deployed_fixture(root, selected, baseline)
            args.candidate_freeze.write_text(json.dumps(selected))
            path.write_text("changed deployed adapter")
            sources, runtime = self.patches()
            with sources, runtime, patch("evaluate.load_corpus") as loader:
                with self.assertRaisesRegex(ValueError, "Artifact drift"):
                    evaluate.native(args)
                loader.assert_not_called()
            self.assertFalse(args.blind_commitment.with_suffix(".consumed.json").exists())

    def test_runtime_scale_does_not_double_embedded_alpha_and_merged_base_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, selected, baseline = self.fixtures(root)
            original_merged = selected["model"]
            path = self.deployed_fixture(root, selected, baseline)
            profile = selected["profile"]
            self.assertEqual(1, profile["adapterScale"])
            flags = evaluate.native_server_arguments(profile)
            self.assertEqual(str(path), flags[flags.index("--lora") + 1])
            self.assertNotIn("--lora-scaled", flags)
            scaled = evaluate.native_server_arguments(evaluate.runtime_profile(16, selected["runtime_adapter"], .5))
            self.assertEqual(str(path) + ":0.5", scaled[-1])
            self.assertEqual("--lora-scaled", scaled[-2])
            for name in ("adapter,comma.gguf", "adapter:colon.gguf"):
                separator_adapter = {**selected["runtime_adapter"], "path": str(root / name)}
                if "," in name:
                    with self.assertRaisesRegex(ValueError, "commas"):
                        evaluate.runtime_profile(16, separator_adapter)
                    with self.assertRaisesRegex(ValueError, "commas"):
                        evaluate.native_server_arguments({**profile, "adapterPath": separator_adapter["path"]})
                else:
                    self.assertEqual(separator_adapter["path"], evaluate.native_server_arguments(evaluate.runtime_profile(16, separator_adapter))[-1])
                with self.assertRaisesRegex(ValueError, "commas.*colons"):
                    evaluate.runtime_profile(16, separator_adapter, .5)
                malformed_profile = {**profile, "adapterPath": separator_adapter["path"], "adapterScale": .5}
                with self.assertRaisesRegex(ValueError, "commas|colons"):
                    evaluate.native_server_arguments(malformed_profile)
            for invalid in (0, -1, 2, float("nan"), float("inf"), True):
                with self.subTest(scale=invalid), self.assertRaisesRegex(ValueError, "scale"):
                    evaluate.runtime_profile(16, selected["runtime_adapter"], invalid)
            selected["model"] = original_merged
            with self.assertRaisesRegex(ValueError, "do not apply it twice"):
                evaluate.verify_runtime_adapter(selected)

    def test_freeze_keeps_training_lineage_separate_and_emits_exact_deployed_core_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args, selected, baseline = self.fixtures(root)
            path = self.deployed_fixture(root, selected, baseline)
            train = root / "training"
            train.mkdir()
            (train / "adapter-config.json").write_text("{}")
            (train / "adapter.safetensors").write_text("training lineage, not deployed")
            frozen = root / "deployed-freeze.json"
            freeze_args = argparse.Namespace(model=Path(selected["model"]["path"]),
                runtime=Path(selected["runtime"]["path"]), runtime_inventory=Path(selected["runtime_inventory"]["path"]),
                probe=Path(selected["probe"]["path"]), output=frozen, adapter_config=train / "adapter-config.json",
                runtime_adapter=path, runtime_adapter_sha256=selected["runtime_adapter"]["sha256"],
                runtime_adapter_scale=1, prompt_lookup_tokens=16)
            sources, runtime = self.patches()
            with sources, runtime, patch("evaluate.managed_files", return_value=[]), patch("builtins.print"):
                evaluate.freeze(freeze_args)
                value = evaluate.verify_freeze(frozen)
            self.assertNotEqual(value["adapter"]["sha256"], value["runtime_adapter"]["sha256"])
            self.assertEqual(1, value["effective_model_identity"]["runtime_adapter_scale"])
            output = root / "deployment-preview"
            corpus = evaluate.load_corpus(args.dataset)
            evaluate.prepare_evaluation(args, value, evaluate.artifact(frozen), corpus, output, "selected_primary", None)
            manifest = json.loads((output / "cleanup-manifest.json").read_text())
            self.assertEqual(str(path), manifest["adapterPath"])
            self.assertEqual(selected["runtime_adapter"]["sha256"], manifest["adapterSha256"])
            self.assertEqual(1, manifest["adapterScale"])
            self.assertIn("native-lora-", manifest["modelId"])
            freeze_args.output = root / "orphan-freeze.json"
            freeze_args.runtime_adapter_sha256 = None
            with self.assertRaisesRegex(ValueError, "both path"):
                evaluate.freeze(freeze_args)

    def test_core_report_must_confirm_deployed_hash_and_external_scale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, selected, baseline = self.fixtures(root)
            path = self.deployed_fixture(root, selected, baseline)
            identity = evaluate.effective_model_identity(selected)
            report = root / "core.json"
            metadata = {"model": {"expected_sha256": identity["base_sha256"], "actual_sha256": identity["base_sha256"]},
                "runtime_adapter": {"path": str(path),
                "expected_sha256": selected["runtime_adapter"]["sha256"],
                "actual_sha256": selected["runtime_adapter"]["sha256"].upper()}, "adapter_scale": 1}
            report.write_text(json.dumps({"metadata": metadata}))
            evaluate.verify_core_deployment(report, identity)
            metadata["adapter_scale"] = 2
            report.write_text(json.dumps({"metadata": metadata}))
            with self.assertRaisesRegex(ValueError, "scale"):
                evaluate.verify_core_deployment(report, identity)
            report.write_text(json.dumps({"metadata": {}}))
            with self.assertRaisesRegex(ValueError, "frozen base model"):
                evaluate.verify_core_deployment(report, identity)

    def test_core_report_requires_typed_matching_base_hashes_for_both_roles(self):
        for with_adapter in (False, True):
            with self.subTest(with_adapter=with_adapter), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, selected, baseline = self.fixtures(root)
                if with_adapter:
                    self.deployed_fixture(root, selected, baseline)
                value = selected if with_adapter else baseline
                identity = evaluate.effective_model_identity(value)
                metadata = {"model": {"expected_sha256": identity["base_sha256"], "actual_sha256": identity["base_sha256"].upper()}}
                if with_adapter:
                    metadata.update(runtime_adapter={"expected_sha256": identity["runtime_adapter_sha256"],
                        "actual_sha256": identity["runtime_adapter_sha256"]}, adapter_scale=1)
                report = root / "core.json"
                report.write_text(json.dumps({"metadata": metadata}))
                evaluate.verify_core_deployment(report, identity)
                for key in ("expected_sha256", "actual_sha256"):
                    for invalid in ("0" * 64, None, True, 123):
                        changed = copy.deepcopy(metadata)
                        changed["model"][key] = invalid
                        report.write_text(json.dumps({"metadata": changed}))
                        with self.assertRaisesRegex(ValueError, "base model"):
                            evaluate.verify_core_deployment(report, identity)
                for invalid in (None, {}, {"expected_sha256": identity["base_sha256"]}):
                    changed = {**metadata, "model": invalid}
                    report.write_text(json.dumps({"metadata": changed}))
                    with self.assertRaisesRegex(ValueError, "base model"):
                        evaluate.verify_core_deployment(report, identity)
                for key in ("bytes", "expected_bytes", "actual_bytes"):
                    for invalid in (True, str(identity["base_bytes"]), float(identity["base_bytes"]), identity["base_bytes"] + 1):
                        changed = copy.deepcopy(metadata)
                        changed["model"][key] = invalid
                        report.write_text(json.dumps({"metadata": changed}))
                        with self.assertRaisesRegex(ValueError, "size"):
                            evaluate.verify_core_deployment(report, identity)

    def test_core_report_rejects_boolean_and_nonnumeric_external_scale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, selected, baseline = self.fixtures(root)
            self.deployed_fixture(root, selected, baseline)
            identity = evaluate.effective_model_identity(selected)
            metadata = {"model": {"expected_sha256": identity["base_sha256"], "actual_sha256": identity["base_sha256"]},
                "runtime_adapter": {"expected_sha256": identity["runtime_adapter_sha256"], "actual_sha256": identity["runtime_adapter_sha256"]}}
            report = root / "core.json"
            for scale in (True, False, "1", None, float("nan"), float("inf"), 2):
                report.write_text(json.dumps({"metadata": {**metadata, "adapter_scale": scale}}))
                with self.subTest(scale=scale), self.assertRaisesRegex(ValueError, "scale"):
                    evaluate.verify_core_deployment(report, identity)

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
                manifest = json.loads((output.parent / "cleanup-manifest.json").read_text())
                metadata = {"model": {"expected_sha256": manifest["modelSha256"], "actual_sha256": manifest["modelSha256"]}}
                output.write_text(json.dumps({"incomplete": False, "cases": cases, "metadata": metadata}))
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

    def completed_pair(self, root, malformed_selected=False, deployed_selected=False, deployment_defect=None):
        args, selected, baseline = self.fixtures(root)
        if deployed_selected:
            self.deployed_fixture(root, selected, baseline)
            args.candidate_freeze.write_text(json.dumps(selected))
        calls = []
        def fake_probe(argv, log):
            output = Path(argv[argv.index("--output") + 1])
            baseline = output.parent.name == "paired-baseline"
            calls.append(baseline)
            if malformed_selected and not baseline:
                output.write_text('{"incomplete":true,"cases":[')
                return 1
            if deployment_defect == "missing_report" and not baseline:
                return 1
            text = "Keep that." if baseline else "Keep it."
            cases = [{"id": str(index), "input": "um keep it", "output": text,
                      "normalized_targets": ["Keep it."], "cleanup_status": "Applied",
                      "candidate_text": text, "insertion_count": 1, "delivered_count": 1, "error": None}
                     for index in range(500)]
            manifest = json.loads((output.parent / "cleanup-manifest.json").read_text())
            metadata = {"model": {"expected_sha256": manifest["modelSha256"], "actual_sha256": manifest["modelSha256"]}}
            if deployed_selected and not baseline:
                sha = selected["runtime_adapter"]["sha256"]
                metadata.update(runtime_adapter={"expected_sha256": sha, "actual_sha256": sha}, adapter_scale=1)
                if deployment_defect == "missing_metadata":
                    metadata = {}
                elif deployment_defect == "wrong_hash":
                    metadata["runtime_adapter"]["actual_sha256"] = "0" * 64
                elif deployment_defect == "double_scale":
                    metadata["adapter_scale"] = 2
                elif deployment_defect == "bool_scale":
                    metadata["adapter_scale"] = True
            if deployment_defect == "wrong_base" and not baseline:
                metadata["model"]["actual_sha256"] = "0" * 64
            if deployment_defect == "wrong_control_base" and baseline:
                metadata["model"]["actual_sha256"] = "0" * 64
            output.write_text(json.dumps({"incomplete": False, "cases": cases, "metadata": metadata}))
            return 0
        sources, runtime = self.patches()
        with sources, runtime, patch("evaluate.invoke", side_effect=fake_probe), patch("builtins.print"):
            code = evaluate.native(args)
        self.assertEqual([False, True], calls)
        self.assertEqual(int(malformed_selected or bool(deployment_defect)), code)
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

    def test_deployed_malformed_selected_report_still_runs_full_registered_control(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.completed_pair(Path(directory), malformed_selected=True, deployed_selected=True)
            summary = json.loads((args.output / "paired-completion.json").read_text())
            deployment = json.loads((args.output / "runtime-deployment-verification.json").read_text())
            self.assertFalse(deployment["verified"])
            self.assertEqual(evaluate.artifact(args.output / "core-results.json"), deployment["report"])
            self.assertFalse(summary["both_complete_denominators"])
            self.assertFalse(summary["candidate_reports"]["selected_primary"]["runtime_deployment_verified"])
            self.assertEqual(500, summary["candidate_reports"]["original_control"]["observed_count"])

    def test_deployment_errors_preserve_counts_continue_control_and_forbid_pair_qualification(self):
        for defect in ("missing_report", "missing_metadata", "wrong_hash", "double_scale", "bool_scale", "wrong_base"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                args = self.completed_pair(Path(directory), deployed_selected=True, deployment_defect=defect)
                summary = json.loads((args.output / "paired-completion.json").read_text())
                deployment = json.loads((args.output / "runtime-deployment-verification.json").read_text())
                self.assertFalse(deployment["verified"])
                self.assertFalse(summary["both_complete_denominators"])
                self.assertEqual(1, summary["commands"]["selected_primary"]["runtime_deployment"])
                inventory = summary["candidate_reports"]["selected_primary"]
                self.assertFalse(inventory["complete"])
                if defect != "missing_report":
                    self.assertEqual(500, inventory["observed_count"])
                    self.assertTrue(inventory["case_inventory_complete"])
                    self.assertEqual(evaluate.artifact(args.output / "core-results.json"), deployment["report"])
                self.assertEqual(500, summary["candidate_reports"]["original_control"]["observed_count"])
                review_args = self.review_args(args.output / "paired-baseline/core-results.json")
                with self.assertRaisesRegex(ValueError, "Paired|frozen base model"):
                    evaluate.review(review_args)

    def test_wrong_base_receipts_unqualify_merged_selected_and_original_control(self):
        for defect, role in (("wrong_base", "selected_primary"), ("wrong_control_base", "original_control")):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory:
                args = self.completed_pair(Path(directory), deployment_defect=defect)
                summary = json.loads((args.output / "paired-completion.json").read_text())
                self.assertFalse(summary["both_complete_denominators"])
                self.assertEqual(1, summary["commands"][role]["runtime_deployment"])
                self.assertFalse(summary["candidate_reports"][role]["complete"])
                self.assertTrue(summary["candidate_reports"][role]["case_inventory_complete"])
                for inventory in summary["candidate_reports"].values():
                    self.assertEqual(500, inventory["observed_count"])

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
                with self.assertRaisesRegex(ValueError, "Paired|frozen base model"):
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
