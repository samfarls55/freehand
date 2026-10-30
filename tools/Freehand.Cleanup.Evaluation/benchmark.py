#!/usr/bin/env python3
"""Quality-first transcript-cleanup replay. No audio capture or text insertion.

The automatic checks are diagnostics. Passing them does not prove equivalent
meaning; every completed output remains available for blind human review.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import secrets
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
QUILL_SYSTEM_PROMPT = "You clean up dictated text."
DEFAULT_SERVER_ARGS = ["--ctx-size", "8192", "--parallel", "1", "--threads", "4", "--n-gpu-layers", "0",
                       "--fit", "off", "--no-context-shift", "--no-webui", "--no-slots", "--no-mmproj", "--offline", "--log-disable"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def canonical(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).replace("’", "'").replace("“", '"').replace("”", '"').split()).casefold()


def words(text: str) -> list[str]:
    return re.findall(r"\w+(?:['-]\w+)*", canonical(text))


def distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for i, item in enumerate(left, 1):
        current = [i]
        for j, other in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (item != other)))
        previous = current
    return previous[-1]


def contains_phrase(text: str, phrase: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(canonical(phrase)) + r"(?!\w)", canonical(text)) is not None


def grade(case: dict, output: str) -> dict:
    """Score known assertions and target similarity; do not infer semantic truth."""
    failures = []
    checks = case.get("checks", {})
    for phrase in checks.get("include", []):
        if not contains_phrase(output, phrase):
            failures.append({"check": "include", "value": phrase})
    for phrase in checks.get("exclude", []):
        if contains_phrase(output, phrase):
            failures.append({"check": "exclude", "value": phrase})
    for literal in checks.get("literals", []):
        if literal not in output:
            failures.append({"check": "literal", "value": literal})
    for options in checks.get("any_of", []):
        if not any(contains_phrase(output, option) for option in options):
            failures.append({"check": "any_of", "value": options})
    for pattern in checks.get("exclude_regex", []):
        if re.search(pattern, output, re.IGNORECASE):
            failures.append({"check": "exclude_regex", "value": pattern})
    for sequence in checks.get("ordered", []):
        at = 0
        for phrase in sequence:
            found = canonical(output).find(canonical(phrase), at)
            if found < 0:
                failures.append({"check": "ordered", "value": sequence})
                break
            at = found + len(canonical(phrase))
    format_issues = []
    if not output.strip():
        format_issues.append("empty_output")
    if re.search(r"</?(?:think|analysis)>|<\|(?:im_start|im_end|assistant|end|eot_id)\|>", output, re.IGNORECASE):
        format_issues.append("reasoning_or_template_tokens")
    if re.match(r"\s*(?:here(?:'s| is) (?:the|your)|sure[,!]|cleaned (?:text|transcript):)", output, re.IGNORECASE):
        format_issues.append("assistant_commentary")
    targets = case["targets"]
    token_distances = [(distance(words(target), words(output)), max(1, len(words(target)))) for target in targets]
    closest_distance, closest_length = min(token_distances, key=lambda pair: pair[0] / pair[1])
    target_match = any(canonical(output) == canonical(target) for target in targets)
    return {
        "assertions_pass": not failures,
        "assertion_failures": failures,
        "format_contract_pass": not format_issues,
        "format_issues": format_issues,
        "normalized_target_match": target_match,
        "exact_target_match": output in targets,
        "target_token_edit_distance": closest_distance,
        "target_token_error_ratio": closest_distance / closest_length,
        "unchanged": output == case["input"],
        "quality_status": "known_failure" if failures or format_issues else "target_match" if target_match else "review_required",
        "human_review_required": True,
    }


def load_corpus(path: Path) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
    seen = set()
    for case in cases:
        if case["id"] in seen:
            raise ValueError(f"Duplicate fixture ID: {case['id']}")
        seen.add(case["id"])
        if case["split"] not in ("development", "heldout") or not case["targets"]:
            raise ValueError(f"Invalid fixture: {case['id']}")
        for target in case["targets"]:
            result = grade(case, target)
            if not result["assertions_pass"] or not result["format_contract_pass"]:
                raise ValueError(f"Fixture target contradicts its checks: {case['id']}: {result}")
    return cases


def apply_normalization(cases: list[dict], normalization: dict) -> list[dict]:
    """Use actual Core preprocessing rather than crediting it to cleanup."""
    mapped = {row["id"]: row for row in normalization["cases"]}
    result = []
    for case in cases:
        row = mapped[case["id"]]
        if row["input"] != case["input"]:
            raise ValueError(f"Normalization report has a different source input: {case['id']}")
        copy = dict(case)
        copy["fixture_input"] = case["input"]
        copy["input"] = row["normalized_input"]
        if "normalized_targets" in row:
            copy["targets"] = row["normalized_targets"]
        if "normalized_checks" in row:
            copy["checks"] = row["normalized_checks"]
        copy["needs_cleanup"] = copy["input"] not in copy["targets"]
        for target in copy["targets"]:
            checked = grade(copy, target)
            if not checked["assertions_pass"] or not checked["format_contract_pass"]:
                raise ValueError(f"Normalized target contradicts checks: {case['id']}")
        result.append(copy)
    return result


def linux_tree_memory(pid: int) -> dict | None:
    records = {}
    for directory in Path("/proc").iterdir():
        if not directory.name.isdigit():
            continue
        try:
            data = (directory / "stat").read_text()
            fields = data[data.rfind(")") + 2:].split()
            records[int(directory.name)] = (int(fields[1]), int(fields[21]) * os.sysconf("SC_PAGE_SIZE"))
        except (OSError, ValueError, IndexError):
            pass
    if pid not in records:
        return None
    owned = {pid}
    while True:
        next_owned = owned | {child for child, (parent, _) in records.items() if parent in owned}
        if next_owned == owned:
            break
        owned = next_owned
    private_total = 0
    private_available = True
    for child in owned:
        try:
            lines = Path(f"/proc/{child}/smaps_rollup").read_text().splitlines()
            private_total += sum(int(line.split()[1]) * 1024 for line in lines if line.startswith(("Private_Clean:", "Private_Dirty:", "Private_Hugetlb:")))
        except (OSError, ValueError):
            private_available = False
    return {"working_set_bytes": sum(records[child][1] for child in owned),
            "private_resident_bytes": private_total if private_available else None,
            "private_commit_bytes": None, "process_count": len(owned)}


def windows_tree_memory(pid: int) -> dict | None:
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    class MemoryCounters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return None
    parents = {}
    entry = ProcessEntry()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        success = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while success:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            success = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    if pid not in parents:
        return None
    owned = {pid}
    while True:
        following = owned | {child for child, parent in parents.items() if parent in owned}
        if following == owned:
            break
        owned = following
    resident = commit = 0
    for child in owned:
        handle = kernel.OpenProcess(0x0400 | 0x0010, False, child)
        if not handle:
            return None
        try:
            counters = MemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return None
            resident += counters.WorkingSetSize
            commit += counters.PrivateUsage
        finally:
            kernel.CloseHandle(handle)
    return {"working_set_bytes": resident, "private_commit_bytes": commit,
            "private_resident_bytes": None, "process_count": len(owned)}


class MemorySampler:
    def __init__(self, pid: int, interval: float = 0.1):
        self.pid = pid
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.samples = []
        self.errors = 0

    def start(self):
        self.thread.start()

    def _run(self):
        while not self.stop_event.is_set():
            try:
                sample = windows_tree_memory(self.pid) if os.name == "nt" else linux_tree_memory(self.pid) if sys.platform.startswith("linux") else None
                if sample:
                    self.samples.append(sample)
                else:
                    self.errors += 1
            except (OSError, ValueError):
                self.errors += 1
            self.stop_event.wait(self.interval)

    def finish(self) -> dict:
        self.stop_event.set()
        self.thread.join(timeout=max(2, self.interval * 3))
        def maximum(key):
            values = [sample[key] for sample in self.samples if sample[key] is not None]
            return max(values) if values else None
        return {"scope": "owned_cleanup_server_process_tree_only", "sample_interval_seconds": self.interval,
                "sample_count": len(self.samples), "unavailable_samples": self.errors,
                "peak_working_set_bytes": maximum("working_set_bytes"),
                "peak_private_resident_bytes": maximum("private_resident_bytes"),
                "peak_private_commit_bytes": maximum("private_commit_bytes"),
                "peak_process_count": maximum("process_count"),
                "notes": "Sampled simultaneous process-tree sums; shared pages may be counted twice. Linux private resident memory differs from Windows private commit. GPU memory and the Freehand desktop/ASR worker are excluded. Sampling can affect timing."}


def local_request(port: int, key: str, endpoint: str, payload: dict | None, timeout: float) -> dict:
    # Explicitly avoid routing loopback IPC through inherited external proxies.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}{endpoint}", data=data,
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with opener.open(request, timeout=timeout) as response:
        data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("Cleanup response exceeds the provider's 2 MiB limit")
        return json.loads(data)


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class OwnedServer:
    def __init__(self, runtime: Path, model: Path, args: list[str], log: Path, startup_timeout: float, interval: float):
        for forbidden in ("-m", "--model", "--host", "--port", "--api-key", "--api-key-file"):
            if any(arg == forbidden or arg.startswith(forbidden + "=") for arg in args):
                raise ValueError(f"Server argument is controlled by the harness: {forbidden}")
        self.key = secrets.token_hex(24)
        self.port = free_port()
        self.command = [str(runtime), "--model", str(model), "--host", "127.0.0.1", "--port", str(self.port), *args]
        self.public_command = self.command
        self.log_file = log.open("wb")
        started = time.perf_counter()
        try:
            child_environment = dict(os.environ)
            child_environment["LLAMA_API_KEY"] = self.key
            self.process = subprocess.Popen(self.command, stdout=self.log_file, stderr=subprocess.STDOUT,
                                            env=child_environment, start_new_session=os.name != "nt")
        except BaseException:
            self.log_file.close()
            raise
        self.sampler = MemorySampler(self.process.pid, interval)
        self.sampler.start()
        self.memory = None
        try:
            while True:
                if self.process.poll() is not None:
                    raise RuntimeError(f"Server exited during startup ({self.process.returncode}); see {log}")
                if time.perf_counter() - started >= startup_timeout:
                    raise TimeoutError("Server readiness deadline exceeded")
                try:
                    result = local_request(self.port, self.key, "/health", None, min(0.5, startup_timeout))
                    if result.get("status") == "ok":
                        break
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                    pass
                time.sleep(0.05)
            self.startup_seconds = time.perf_counter() - started
        except BaseException:
            self.close()
            raise

    def request(self, endpoint: str, payload: dict, deadline: float) -> tuple[dict, float]:
        result = {}
        done = threading.Event()
        started = time.perf_counter()

        def execute():
            try:
                result["value"] = local_request(self.port, self.key, endpoint, payload, deadline)
            except BaseException as error:
                result["error"] = error
            finally:
                done.set()

        threading.Thread(target=execute, daemon=True).start()
        if not done.wait(deadline):
            self.close()
            raise TimeoutError("Complete-response deadline exceeded; owned server stopped and remaining jobs aborted")
        elapsed = time.perf_counter() - started
        if "error" in result:
            error = result["error"]
            self.close()
            reason = error.reason if isinstance(error, urllib.error.URLError) else error
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise TimeoutError("Complete-response deadline exceeded; owned server stopped") from error
            raise error
        return result["value"], elapsed

    def close(self):
        if self.process.poll() is None:
            # llama-server is the only launched executable. Terminate its owned
            # process tree so late inference cannot overlap another candidate.
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=5)
            else:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    self.process.kill()
                else:
                    try:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                self.process.wait(timeout=5)
        if self.memory is None:
            self.memory = self.sampler.finish()
        if not self.log_file.closed:
            self.log_file.close()


def make_request(candidate: dict, text: str, system_prompt: str, max_tokens: int) -> tuple[str, dict]:
    common = {"temperature": 0, "seed": 0, "stream": False}
    if candidate.get("style", "chat") == "quill_chatml":
        if "<|im_start|>" in text or "<|im_end|>" in text:
            raise ValueError("Transcript contains unsupported model control tokens")
        prompt = "<|im_start|>system\n" + QUILL_SYSTEM_PROMPT + "<|im_end|>\n<|im_start|>user\n" + text + "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
        return "/completion", {**common, "prompt": prompt, "n_predict": max_tokens,
                               "stop": ["<|im_end|>", "<|im_start|>"]}
    if candidate.get("style", "chat") != "chat":
        raise ValueError(f"Unknown candidate style: {candidate['style']}")
    return "/v1/chat/completions", {**common, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": text}],
                                     "max_tokens": max_tokens,
                                     "chat_template_kwargs": candidate.get("chat_template_kwargs", {"enable_thinking": False})}


def read_completion(candidate: dict, response: dict) -> tuple[str, dict]:
    if candidate.get("style", "chat") == "quill_chatml":
        stopped = response.get("stop_type") in ("eos", "word") if "stop_type" in response else response.get("stopped_eos") is True or response.get("stopped_word") is True
        if not stopped or response.get("truncated") is True or response.get("stopped_limit") is True:
            raise ValueError("Incomplete completion: output/context limit reached")
        output = response.get("content")
        metadata = {key: response.get(key) for key in ("timings", "tokens_predicted", "tokens_evaluated", "stop_type", "stopped_eos", "stopped_word")}
    else:
        choices = response.get("choices")
        if response.get("truncated") is True or not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("Cleanup did not return exactly one complete response")
        choice = choices[0]
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            raise ValueError("Cleanup did not return a text message")
        if choice.get("finish_reason") != "stop":
            raise ValueError(f"Incomplete completion: finish_reason={choice.get('finish_reason')}")
        reasoning = choice["message"].get("reasoning_content")
        if reasoning is not None and (not isinstance(reasoning, str) or reasoning.strip()):
            raise ValueError("Cleanup returned unexpected reasoning output")
        output = choice["message"].get("content")
        metadata = {"usage": response.get("usage"), "timings": response.get("timings"),
                    "finish_reason": choice.get("finish_reason"), "returned_model": response.get("model")}
    if not isinstance(output, str) or not output.strip():
        raise ValueError("Empty or non-text completion")
    if "<think>" in output.lower() or "</think>" in output.lower() or any(control in output for control in ("<|im_start|>", "<|im_end|>", "<|channel>", "<start_of_turn>")):
        raise ValueError("Cleanup returned model control output")
    return output, metadata


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def summarize(rows: list[dict]) -> dict:
    completed = [row for row in rows if row["status"] == "completed"]
    attempted = [row for row in rows if row["status"] != "not_attempted"]
    times = [row["complete_response_seconds"] for row in completed]
    result = {"row_count": len(rows), "attempt_count": len(attempted), "not_attempted_count": len(rows) - len(attempted), "completed_count": len(completed),
              "operational_failures": len(attempted) - len(completed),
              "known_quality_failures": sum(row["grade"]["quality_status"] == "known_failure" for row in completed),
              "target_matches": sum(row["grade"]["normalized_target_match"] for row in completed),
              "review_required_nonmatches": sum(row["grade"]["quality_status"] == "review_required" for row in completed),
              "complete_response_seconds": {"median": statistics.median(times) if times else None,
                                            "p95_nearest_rank": percentile(times, .95),
                                            "maximum": max(times) if times else None, "sample_count": len(times)}}
    result["by_category"] = {}
    for category in sorted({row["category"] for row in rows}):
        group = [row for row in completed if row["category"] == category]
        result["by_category"][category] = {"completed": len(group),
            "known_quality_failures": sum(row["grade"]["quality_status"] == "known_failure" for row in group),
            "target_matches": sum(row["grade"]["normalized_target_match"] for row in group)}
    return result


def persist(output: Path, report: dict, rows: list[dict], cases: list[dict]):
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "outputs.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    # Candidate identities are separately keyed so this file can be reviewed blind.
    names = list(dict.fromkeys(row["candidate"] for row in rows))
    aliases = {name: f"Candidate {index + 1}" for index, name in enumerate(names)}
    lines = ["# Cleanup output review", "", "Synthetic fixture replay; every output requires human review. This is not a Windows application benchmark.", "", "Judge final intended facts, correction handling, voice and readable formatting before checking the identity key.", ""]
    for case in cases:
        lines += [f"## {case['id']} ({case['category']})", "", "Input:", "", "```text", case["input"], "```", ""]
        for row in (row for row in rows if row["case_id"] == case["id"]):
            lines += [f"### {aliases[row['candidate']]} / repetition {row['repetition']}", "", "```text", row.get("output", "[" + row["status"] + "]"), "```", ""]
    (output / "review.md").write_text("\n".join(lines), encoding="utf-8")
    (output / "review-key.json").write_text(json.dumps({alias: name for name, alias in aliases.items()}, indent=2) + "\n", encoding="utf-8")


def run(arguments: argparse.Namespace) -> int:
    cases = load_corpus(arguments.corpus)
    if arguments.split != "all":
        cases = [case for case in cases if case["split"] == arguments.split]
    if arguments.ids:
        wanted = set(arguments.ids.split(","))
        if wanted - {case["id"] for case in cases}:
            raise ValueError("Requested IDs are absent from the selected split")
        cases = [case for case in cases if case["id"] in wanted]
    if arguments.limit:
        cases = cases[:arguments.limit]
    if not cases:
        raise ValueError("No selected fixtures")
    if arguments.normalization_report:
        cases = apply_normalization(cases, json.loads(arguments.normalization_report.read_text(encoding="utf-8")))
    arguments.output.mkdir(parents=True, exist_ok=False)
    snapshots = {"corpus": "source-corpus.json", "prompt": "source-prompt.txt"}
    (arguments.output / snapshots["corpus"]).write_bytes(arguments.corpus.read_bytes())
    (arguments.output / snapshots["prompt"]).write_bytes(arguments.prompt.read_bytes())
    if arguments.normalization_report:
        snapshots["normalization_report"] = "source-normalization-report.json"
        (arguments.output / snapshots["normalization_report"]).write_bytes(arguments.normalization_report.read_bytes())
    if arguments.config:
        snapshots["configuration"] = "source-configuration.json"
        (arguments.output / snapshots["configuration"]).write_bytes(arguments.config.read_bytes())
    prompt = arguments.prompt.read_text(encoding="utf-8").rstrip("\r\n")
    configuration = json.loads(arguments.config.read_text(encoding="utf-8")) if arguments.config else {"candidates": []}
    report = {"schema_version": 1, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "priority": "Meaning preservation and useful cleanup first; performance is descriptive.",
              "platform": {"system": platform.platform(), "python": platform.python_version(), "logical_cpus": os.cpu_count()},
              "fixture_sha256": sha256_file(arguments.corpus), "prompt_sha256": sha256_file(arguments.prompt),
              "configuration_sha256": sha256_file(arguments.config) if arguments.config else None,
              "normalization_report_sha256": sha256_file(arguments.normalization_report) if arguments.normalization_report else None,
              "baseline_input_stage": "Core dictionary/number-normalized" if arguments.normalization_report else "Provided synthetic transcript; production normalization not verified",
              "harness_sha256": sha256_file(Path(__file__)),
              "selected_case_ids": [case["id"] for case in cases], "split": arguments.split,
              "repetitions": arguments.repetitions, "request_deadline_seconds": arguments.request_timeout,
              "max_output_tokens": arguments.max_tokens, "candidates": [],
              "input_snapshots": snapshots,
              "limits": ["Public synthetic fixtures have not established real dictation performance.",
                         "Automatic content checks and target similarity do not prove semantic equivalence.",
                         "Latency is isolated server complete-response time, excluding audio, recognition, and text delivery.",
                         "Memory excludes Freehand and GPU allocations. Low trial counts do not establish reliable tail percentiles.",
                         "Quill uses its published minimal system prompt/raw ChatML; other models use the shared cleanup policy."]}
    rows = []
    for repetition in range(1, arguments.repetitions + 1):
        for case in cases:
            rows.append({"candidate": "no-cleanup", "case_id": case["id"], "category": case["category"],
                         "split": case["split"], "repetition": repetition, "status": "completed", "output": case["input"],
                         "complete_response_seconds": 0.0, "grade": grade(case, case["input"])})
    report["candidates"].append({"id": "no-cleanup", "summary": summarize(rows),
                                  "memory": {"scope": "no cleanup subprocess; not complete Freehand memory"},
                                  "timing_note": "Zero cleanup-model cost by definition, not a measured application delivery time."})
    persist(arguments.output, report, rows, cases)
    candidate_ids = {"no-cleanup"}
    failures = False
    for candidate in configuration.get("candidates", []):
        name = candidate["id"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in candidate_ids:
            raise ValueError("Candidate IDs must be unique safe filenames")
        candidate_ids.add(name)
        entry = {"id": name, "style": candidate.get("style", "chat"), "status": "preparing"}
        report["candidates"].append(entry)
        server = None
        candidate_rows = []
        try:
            runtime = Path(candidate.get("runtime_path", configuration.get("runtime_path", ""))).resolve(strict=True)
            model = Path(candidate["model_path"]).resolve(strict=True)
            runtime_hash, model_hash = sha256_file(runtime), sha256_file(model)
            for label, actual in (("runtime", runtime_hash), ("model", model_hash)):
                expected = candidate.get(label + "_sha256", configuration.get(label + "_sha256"))
                if expected and expected.lower() != actual:
                    raise ValueError(f"{label} SHA256 mismatch")
            entry.update({"runtime_path": str(runtime), "runtime_sha256": runtime_hash,
                          "model_path": str(model), "model_sha256": model_hash,
                          "source": candidate.get("source"), "revision": candidate.get("revision"),
                          "candidate_config_sha256": fingerprint(candidate),
                          "system_prompt": QUILL_SYSTEM_PROMPT if entry["style"] == "quill_chatml" else prompt,
                          "request_example_sha256": fingerprint(make_request(candidate, cases[0]["input"], prompt, arguments.max_tokens))})
            server_args = list(candidate.get("server_args", configuration.get("server_args", DEFAULT_SERVER_ARGS)))
            if not any(argument in ("--jinja", "--no-jinja") for argument in server_args):
                server_args.append("--no-jinja" if entry["style"] == "quill_chatml" else "--jinja")
            server = OwnedServer(runtime, model, server_args,
                                 arguments.output / (name + ".server.log"), arguments.startup_timeout, arguments.memory_interval)
            entry.update({"startup_to_health_seconds": server.startup_seconds, "server_command": server.public_command,
                          "chat_template_kwargs": candidate.get("chat_template_kwargs", {"enable_thinking": False})})
            for repetition in range(1, arguments.repetitions + 1):
                for case in cases:
                    row = {"candidate": name, "case_id": case["id"], "category": case["category"],
                           "split": case["split"], "repetition": repetition}
                    endpoint, payload = make_request(candidate, case["input"], prompt, arguments.max_tokens)
                    row["request_sha256"] = fingerprint({"endpoint": endpoint, "payload": payload})
                    started = time.perf_counter()
                    try:
                        response, elapsed = server.request(endpoint, payload, arguments.request_timeout)
                        row["raw_response"] = response
                        output, metadata = read_completion(candidate, response)
                        row.update({"status": "completed", "output": output, "complete_response_seconds": elapsed,
                                    "provider_metadata": metadata, "grade": grade(case, output)})
                    except Exception as error:
                        row.update({"status": "timeout" if isinstance(error, TimeoutError) else "failed",
                                    "elapsed_seconds": time.perf_counter() - started, "error": f"{type(error).__name__}: {error}"})
                        failures = True
                    rows.append(row)
                    candidate_rows.append(row)
                    entry["summary"] = summarize(candidate_rows)
                    persist(arguments.output, report, rows, cases)
                    print(json.dumps({"candidate": name, "case": case["id"], "status": row["status"],
                                      "seconds": row.get("complete_response_seconds", row.get("elapsed_seconds")),
                                      "quality": row.get("grade", {}).get("quality_status")}), flush=True)
                    if row["status"] == "timeout" or server.process.poll() is not None:
                        raise RuntimeError("Candidate stopped; remaining fixtures were not run")
            entry["status"] = "completed"
        except Exception as error:
            failures = True
            entry.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        finally:
            if server:
                server.close()
                entry["memory"] = server.memory
            entry["summary"] = summarize(candidate_rows)
            entry["not_run_count"] = len(cases) * arguments.repetitions - len(candidate_rows)
            persist(arguments.output, report, rows, cases)
    report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    persist(arguments.output, report, rows, cases)
    print(json.dumps({"output": str(arguments.output.resolve()), "candidate_count": len(report["candidates"]),
                      "operational_failure": failures}), flush=True)
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Local runtime/model configuration. Omit for no-cleanup baseline only.")
    parser.add_argument("--corpus", type=Path, default=HERE / "fixtures.json")
    parser.add_argument("--prompt", type=Path, default=HERE.parents[1] / "shared" / "transcript-cleanup-prompt.txt")
    parser.add_argument("--normalization-report", type=Path, help="Core probe baseline report supplying normalized_input and optionally normalized_targets/checks.")
    parser.add_argument("--output", type=Path, required=True, help="New report directory; existing directories are rejected.")
    parser.add_argument("--split", choices=("development", "heldout", "all"), default="development")
    parser.add_argument("--ids", help="Comma-separated IDs within the selected split")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--request-timeout", type=float, default=120)
    parser.add_argument("--startup-timeout", type=float, default=180)
    parser.add_argument("--memory-interval", type=float, default=.1)
    parser.add_argument("--max-tokens", type=int, default=2048)
    arguments = parser.parse_args()
    for name in ("repetitions", "request_timeout", "startup_timeout", "memory_interval", "max_tokens"):
        if getattr(arguments, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if arguments.limit is not None and arguments.limit <= 0:
        parser.error("--limit must be positive")
    try:
        return run(arguments)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"Evaluation error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
