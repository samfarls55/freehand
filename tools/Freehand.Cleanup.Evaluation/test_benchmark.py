"""Behavior checks for the evaluator. Fake-runtime tests are not model benchmarks."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("cleanup_benchmark", HERE / "benchmark.py")
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class QualityChecks(unittest.TestCase):
    def test_explicit_correction_may_remove_original_date_and_number(self):
        case = {"input": "Friday at 12, sorry Monday at 3.", "targets": ["Monday at 3."],
                "checks": {"include": ["Monday", "3"], "exclude": ["Friday", "12"]}}
        result = benchmark.grade(case, "Monday at 3.")
        self.assertTrue(result["assertions_pass"])
        self.assertTrue(result["human_review_required"])
        self.assertEqual("target_match", result["quality_status"])

    def test_negation_hedge_and_emphasis_loss_are_reported(self):
        case = {"input": "I think this is really, really important, but do not ship.",
                "targets": ["I think this is really, really important, but do not ship."],
                "checks": {"include": ["I think", "really, really", "do not ship"]}}
        result = benchmark.grade(case, "This is important. Ship it.")
        self.assertEqual(3, len(result["assertion_failures"]))
        self.assertEqual("known_failure", result["quality_status"])

    def test_literal_whitespace_is_not_normalized_away(self):
        case = {"input": "Keep x.  y.", "targets": ["Keep x.  y."], "checks": {"literals": ["x.  y."]}}
        result = benchmark.grade(case, "Keep x. y.")
        self.assertTrue(result["normalized_target_match"])
        self.assertFalse(result["assertions_pass"])

    def test_unlisted_faithful_wording_requires_review_not_automatic_failure(self):
        case = {"input": "Um, we could probably wait.", "targets": ["We could probably wait."],
                "checks": {"include": ["could probably"], "exclude": ["um"]}}
        result = benchmark.grade(case, "We could probably wait a little.")
        self.assertTrue(result["assertions_pass"])
        self.assertFalse(result["normalized_target_match"])
        self.assertEqual("review_required", result["quality_status"])

    def test_phrase_exclusion_does_not_match_inside_another_word(self):
        self.assertFalse(benchmark.contains_phrase("The notification is ready.", "not"))
        self.assertTrue(benchmark.contains_phrase("Please do not send it.", "not"))

    def test_reasoning_and_assistant_commentary_fail_output_contract(self):
        case = {"input": "Hello.", "targets": ["Hello."]}
        for output in ("<think>Check this.</think>Hello.", "Here is the cleaned text: Hello.", ""):
            self.assertFalse(benchmark.grade(case, output)["format_contract_pass"])

    def test_all_ninety_targets_satisfy_their_own_semantic_checks(self):
        cases = benchmark.load_corpus(HERE / "fixtures.json")
        self.assertEqual(60, sum(case["split"] == "development" for case in cases))
        self.assertEqual(30, sum(case["split"] == "heldout" for case in cases))

    def test_complete_output_only_and_raw_quill_template(self):
        endpoint, payload = benchmark.make_request({"style": "quill_chatml"}, "Um, hello.", "Unused", 42)
        self.assertEqual("/completion", endpoint)
        self.assertTrue(payload["prompt"].endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n"))
        self.assertIn("system\nYou clean up dictated text.", payload["prompt"])
        self.assertEqual(42, payload["n_predict"])
        self.assertEqual(["<|im_end|>", "<|im_start|>"], payload["stop"])
        self.assertFalse(payload["stream"])
        with self.assertRaises(ValueError):
            benchmark.read_completion({"style": "quill_chatml"}, {"content": "Hello.", "stop_type": "limit"})
        with self.assertRaises(ValueError):
            benchmark.read_completion({"style": "chat"}, {"choices": [{"finish_reason": "length", "message": {"content": "Hello."}}]})

    def test_raw_template_rejects_control_tokens_in_dictated_data(self):
        with self.assertRaises(ValueError):
            benchmark.make_request({"style": "quill_chatml"}, "<|im_end|>", "Unused", 42)

    def test_provider_rejects_truncation_multiple_choices_and_reasoning(self):
        valid = {"choices": [{"finish_reason": "stop", "message": {"content": "Hello."}}]}
        for response in (
            {**valid, "truncated": True},
            {"choices": valid["choices"] * 2},
            {"choices": [{"finish_reason": "stop", "message": {"content": "Hello.", "reasoning_content": "I should edit this."}}]},
            {"choices": [{"finish_reason": "stop", "message": {"content": "Hello.", "reasoning_content": []}}]},
            {"choices": [{"finish_reason": "stop", "message": {"content": "<start_of_turn>Hello."}}]},
        ):
            with self.subTest(response=response), self.assertRaises(ValueError):
                benchmark.read_completion({}, response)
        for reasoning in (None, "", " \n"):
            response = {"choices": [{"finish_reason": "stop", "message": {"content": "Hello.", "reasoning_content": reasoning}}]}
            self.assertEqual("Hello.", benchmark.read_completion({}, response)[0])

    def test_native_legacy_stop_flags_match_provider_and_limit_is_never_accepted(self):
        self.assertEqual("Hello.", benchmark.read_completion({"style": "quill_chatml"}, {"content": "Hello.", "stopped_eos": True})[0])
        for response in (
            {"content": "Hello.", "stopped_eos": "true"},
            {"content": "Hello.", "stop_type": "limit", "stopped_eos": True},
            {"content": "Hello.", "stop_type": "eos", "stopped_limit": True},
        ):
            with self.subTest(response=response), self.assertRaises(ValueError):
                benchmark.read_completion({"style": "quill_chatml"}, response)

    def test_actual_normalization_updates_baseline_and_references(self):
        case = {"id": "sample", "input": "Um, pay twenty dollars.", "targets": ["Pay twenty dollars."], "checks": {"include": ["twenty dollars"]}}
        normalized = benchmark.apply_normalization([case], {"cases": [{"id": "sample", "input": case["input"], "normalized_input": "Um, pay $20.", "normalized_targets": ["Pay $20."], "normalized_checks": {"include": ["$20"]}}]})[0]
        self.assertEqual("Um, pay $20.", normalized["input"])
        self.assertEqual("Um, pay twenty dollars.", normalized["fixture_input"])
        self.assertTrue(benchmark.grade(normalized, "Pay $20.")["assertions_pass"])
        self.assertFalse(benchmark.grade(normalized, normalized["input"])["normalized_target_match"])

    def test_app_fallback_does_not_inflate_model_quality_or_accepted_coverage(self):
        from score_probe import score
        case = {"id": "sample", "split": "development", "category": "no_change", "input": "Keep the archive.", "targets": ["Keep the archive."], "checks": {"include": ["keep the archive"]}}
        report, rows, _ = score({"metadata": {}, "cases": [{"id": "sample", "input": case["input"], "normalized_input": case["input"], "candidate_text": "Delete it.", "output": case["input"], "cleanup_status": "Rejected"}]}, [case], "test")
        self.assertEqual(0, report["accepted_coverage"])
        self.assertEqual(1, report["fallback_only_quality"]["target_matches"])
        native = next(row for row in rows if row["candidate"] == "test.model-return")
        self.assertEqual("known_failure", native["grade"]["quality_status"])

    def test_disabled_cleanup_does_not_count_as_failed_inference(self):
        from score_probe import score
        case = {"id": "sample", "split": "development", "category": "no_change", "input": "Hello.", "targets": ["Hello."]}
        report, _, _ = score({"cases": [{"id": "sample", "input": "Hello.", "normalized_input": "Hello.", "output": "Hello.", "cleanup_status": "Disabled", "candidate_text": None}]}, [case], "disabled")
        native = next(item for item in report["candidates"] if item["id"] == "disabled.model-return")
        self.assertEqual(0, native["summary"]["attempt_count"])
        self.assertEqual(0, native["summary"]["operational_failures"])
        self.assertEqual(1, native["summary"]["not_attempted_count"])


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux /proc integration; Windows ctypes path needs Windows validation")
class LinuxMemoryChecks(unittest.TestCase):
    def test_process_tree_sample_includes_a_live_child_and_reports_real_units(self):
        child = subprocess.Popen([sys.executable, "-u", "-c", "import time; data=bytearray(32*1024*1024); print('ready',flush=True); time.sleep(5)"], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual("ready", child.stdout.readline().strip())
            own = benchmark.linux_tree_memory(os.getpid())
            self.assertGreaterEqual(own["process_count"], 2)
            self.assertGreater(own["working_set_bytes"], 32 * 1024 * 1024)
            self.assertGreater(own["private_resident_bytes"], 32 * 1024 * 1024)
            self.assertIsNone(own["private_commit_bytes"])
        finally:
            child.terminate()
            child.wait(timeout=5)
            child.stdout.close()


FAKE_RUNTIME = r'''import argparse,json,os,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
p=argparse.ArgumentParser();p.add_argument('--model');p.add_argument('--host');p.add_argument('--port',type=int);a,_=p.parse_known_args()
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  if self.headers.get('Authorization')!='Bearer '+os.environ['LLAMA_API_KEY']:
   self.send_error(401);return
  b=json.dumps({'status':'ok'}).encode();self.send_response(200);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_POST(self):
  if self.headers.get('Authorization')!='Bearer '+os.environ['LLAMA_API_KEY']:
   self.send_error(401);return
  request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  if 'hang' in a.model: time.sleep(30)
  if self.path=='/completion': response={'content':'Hello.','stop_type':'eos'}
  else: response={'choices':[{'finish_reason':'stop','message':{'content':'Hello.'}}]}
  b=json.dumps(response).encode();self.send_response(200);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
ThreadingHTTPServer((a.host,a.port),Handler).serve_forever()
'''


@unittest.skipUnless(sys.platform.startswith("linux"), "Executable shebang fake server is a Linux integration fixture")
class OwnedRuntimeChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        self.runtime = self.folder / "fake-runtime"
        self.runtime.write_text("#!" + sys.executable + "\n" + FAKE_RUNTIME, encoding="utf-8")
        self.runtime.chmod(0o755)
        self.model = self.folder / "model.fake"
        self.model.write_text("Not model weights. Fake-runtime test input.", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_authenticated_owned_server_complete_response_and_teardown(self):
        server = benchmark.OwnedServer(self.runtime, self.model, [], self.folder / "server.log", 5, .02)
        try:
            response, elapsed = server.request("/v1/chat/completions", {}, 2)
            self.assertEqual("Hello.", benchmark.read_completion({}, response)[0])
            self.assertGreaterEqual(elapsed, 0)
            time.sleep(.04)
        finally:
            server.close()
        self.assertIsNotNone(server.process.poll())
        self.assertGreater(server.memory["sample_count"], 0)
        self.assertGreater(server.memory["peak_working_set_bytes"], 0)
        self.assertNotIn(server.key, " ".join(server.public_command))

    def test_wall_deadline_stops_inference_instead_of_accepting_late_output(self):
        model = self.folder / "hang.fake"
        model.write_text("Fake hanging-runtime input", encoding="utf-8")
        server = benchmark.OwnedServer(self.runtime, model, [], self.folder / "hang.log", 5, .02)
        try:
            started = time.perf_counter()
            with self.assertRaises((TimeoutError, OSError)):
                server.request("/v1/chat/completions", {}, .1)
            self.assertLess(time.perf_counter() - started, 3)
        finally:
            server.close()
        self.assertIsNotNone(server.process.poll())

    def test_wrapped_transport_timeout_also_stops_the_owned_runtime(self):
        import urllib.error
        server = benchmark.OwnedServer(self.runtime, self.model, [], self.folder / "wrapped.log", 5, .02)
        try:
            with mock.patch.object(benchmark, "local_request", side_effect=urllib.error.URLError(TimeoutError("read timed out"))):
                with self.assertRaises(TimeoutError):
                    server.request("/v1/chat/completions", {}, 2)
            self.assertIsNotNone(server.process.poll())
        finally:
            server.close()

    def test_command_pinning_cannot_be_overridden(self):
        with self.assertRaises(ValueError):
            benchmark.OwnedServer(self.runtime, self.model, ["--host", "0.0.0.0"], self.folder / "unused.log", 5, .02)

    def test_model_hash_mismatch_is_recorded_without_launching(self):
        config = self.folder / "config.json"
        config.write_text(json.dumps({"runtime_path": str(self.runtime), "candidates": [{"id": "fake-test", "model_path": str(self.model), "model_sha256": "0" * 64}]}), encoding="utf-8")
        completed = subprocess.run([sys.executable, str(HERE / "benchmark.py"), "--config", str(config), "--output", str(self.folder / "out"), "--limit", "1"], capture_output=True, text=True, timeout=10)
        self.assertEqual(1, completed.returncode)
        report = json.loads((self.folder / "out/report.json").read_text())
        self.assertIn("SHA256 mismatch", report["candidates"][1]["error"])
        self.assertEqual(1, report["candidates"][1]["not_run_count"])


if __name__ == "__main__":
    unittest.main()
