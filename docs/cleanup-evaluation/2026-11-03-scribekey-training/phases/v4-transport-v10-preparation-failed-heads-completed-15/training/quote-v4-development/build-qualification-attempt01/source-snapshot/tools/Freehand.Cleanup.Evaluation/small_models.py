#!/usr/bin/env python3
"""Replay exported production cleanup contracts against one independently pinned GGUF.

This measures a local cleanup subprocess, not Freehand's whole-app SLA. All
completed text is retained for semantic review; automatic checks are diagnostics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

from benchmark import OwnedServer, fingerprint, grade, read_completion, sha256_file, summarize
from literal_protection import LiteralProtectionMask
from specialist_literal_protection import SpecialistLiteralMask


# System.Char.IsWhiteSpace / String.Trim: Python's default strip additionally
# removes U+001C through U+001F, which the production provider preserves.
DOTNET_WHITESPACE = "\t\n\v\f\r \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"


def specialist_output_normalization(exported: dict, general: bool) -> str:
    """Old exports keep their original output bytes unless they opt in explicitly."""
    protocol = exported.get("specialist_output_normalization", "none")
    if protocol not in ("none", "trim-v1"):
        raise ValueError("Unsupported specialist output normalization")
    if general and protocol != "none":
        raise ValueError("General-model contracts do not normalize exterior whitespace")
    return protocol


def normalize_specialist_output(text: str, protocol: str) -> str:
    if protocol == "trim-v1":
        return text.strip(DOTNET_WHITESPACE)
    if protocol == "none":
        return text
    raise ValueError("Unsupported specialist output normalization")


def selected_asset(index: dict, identity: str) -> dict:
    matches = [asset for asset in index["assets"] if asset["id"] == identity]
    if not matches:
        matches = [asset for asset in index["assets"] if identity.casefold() in asset["id"].casefold()]
    if len(matches) != 1:
        raise ValueError(f"Candidate must identify exactly one verified asset, found {len(matches)}: {identity}")
    asset = matches[0]
    if asset.get("verified") is not True:
        raise ValueError("Candidate is not independently verified")
    return asset


def verify_file(entry: dict) -> Path:
    path = Path(entry["path"]).resolve(strict=True)
    if path.stat().st_size != entry["bytes"] or sha256_file(path).lower() != entry["sha256"].lower():
        raise ValueError(f"Pinned artifact mismatch: {path}")
    return path


def verify_runtime_inventory(path: Path, runtime: Path) -> dict:
    inventory = json.loads(path.read_text(encoding="utf-8"))
    directory = Path(inventory["directory"]).resolve(strict=True)
    if directory != runtime.parent:
        raise ValueError("Runtime inventory must describe the selected executable's directory")
    known = set()
    files = links = 0
    for entry in inventory["files"]:
        name = entry["name"]
        if not name or name in (".", "..") or "/" in name or "\\" in name or name in known:
            raise ValueError("Runtime inventory names must be unique immediate children")
        known.add(name)
        item = directory / name
        if "symlink_target" in entry:
            if not item.is_symlink() or os.readlink(item) != entry["symlink_target"] or item.resolve(strict=True).parent != directory:
                raise ValueError(f"Runtime symlink mismatch: {name}")
            links += 1
        else:
            if item.is_symlink():
                raise ValueError(f"Runtime file unexpectedly became a symlink: {name}")
            verify_file({"path": str(item), "bytes": entry["bytes"], "sha256": entry["sha256"]})
            files += 1
    actual = {item.name for item in directory.iterdir() if item.is_file() or item.is_symlink()}
    if actual != known or runtime.name not in known:
        raise ValueError("Runtime inventory does not match the complete runtime directory")
    return {"path": str(path.resolve()), "sha256": sha256_file(path), "verified_file_count": files,
            "verified_symlink_count": links, "verification": "complete_file_hashes_sizes_and_local_symlink_targets"}


def assert_no_native_overlap() -> None:
    if sys.platform != "linux":
        return
    owned_pid = os.getpid()
    active = []
    for directory in Path("/proc").glob("[0-9]*"):
        if int(directory.name) == owned_pid:
            continue
        try:
            executable = (directory / "cmdline").read_bytes().split(b"\0", 1)[0]
            if Path(os.fsdecode(executable)).name in ("llama-server", "llama-server.exe"):
                active.append(int(directory.name))
        except (OSError, ValueError):
            pass
    if active:
        raise ValueError(f"Refusing overlapping native inference; active server PIDs: {active}")


def completion_payload(contract: dict, max_output: int) -> dict:
    return {"prompt": contract["text"], "n_predict": max_output, "stream": False,
            "temperature": contract["temperature"], "repeat_penalty": contract["repeat_penalty"],
            "seed": contract["seed"], "stop": contract["stop"], "cache_prompt": False,
            "add_special": contract["add_special"], "parse_special": True}


def normalized_fixture(row: dict) -> dict:
    fixture = dict(row["fixture"])
    fixture["fixture_input"] = fixture["input"]
    fixture["input"] = row["normalized_input"]
    fixture["targets"] = row["normalized_targets"]
    fixture["checks"] = row.get("normalized_checks") or {}
    fixture.setdefault("category", "unspecified")
    fixture.setdefault("split", "development")
    return fixture


def literal_mask_protocol(exported: dict, general: bool) -> str:
    """Read an explicit protocol, retaining replay support for frozen v1 exports."""
    masked = exported.get("mask_literals", general)
    if not isinstance(masked, bool):
        raise ValueError("mask_literals must be a boolean")
    # Initial specialist experiments deliberately reused the legacy general mask.
    # Their unchanged exports lack the protocol field and must remain legacy.
    protocol = exported.get("literal_mask_protocol", "literal-token-v1" if masked else "none")
    if protocol not in ("none", "literal-token-v1", "specialist-compact-v2", "specialist-compact-v3", "specialist-compact-v4"):
        raise ValueError("Unsupported literal mask protocol")
    if masked != (protocol != "none"):
        raise ValueError("Literal mask protocol disagrees with mask_literals")
    if general and protocol in ("specialist-compact-v2", "specialist-compact-v3", "specialist-compact-v4"):
        raise ValueError("General-model contracts retain the legacy literal mask")
    return protocol


def replay(server: OwnedServer, exported: dict, arguments: argparse.Namespace) -> dict:
    """Measure budget validation plus generation, preserving every raw response."""
    fixture = normalized_fixture(exported)
    row = {"case_id": fixture["id"], "category": fixture["category"], "split": fixture["split"],
           "input": fixture["input"], "targets": fixture["targets"], "checks": fixture["checks"]}
    started = time.perf_counter()
    try:
        contract = exported.get("completion")
        general = contract is None
        protocol = literal_mask_protocol(exported, general)
        normalization = specialist_output_normalization(exported, general)
        if protocol == "specialist-compact-v4" and any(control in fixture["input"] for control in (
                "<|im_start|>", "<|im_end|>", "<|channel>", "<start_of_turn>", "<end_of_turn>",
                "[INST]", "[/INST]", "[SYSTEM_PROMPT]", "[/SYSTEM_PROMPT]", "<|endoftext|>", "<|startoftext|>")):
            raise ValueError("Transcript contains unsupported model control tokens")
        protection = (SpecialistLiteralMask.create(fixture["input"], remove_added_quote_period=protocol != "specialist-compact-v2",
                                                 protocol="specialist-compact-v4" if protocol == "specialist-compact-v4" else "specialist-compact-v3")
                      if protocol in ("specialist-compact-v2", "specialist-compact-v3", "specialist-compact-v4")
                      else LiteralProtectionMask.create(fixture["input"]) if protocol == "literal-token-v1" else None)
        row["mask_literals"] = protocol != "none"
        row["literal_mask_protocol"] = protocol
        row["specialist_output_normalization"] = normalization
        model_text = protection.masked_text if protection is not None else fixture["input"]
        row["model_input_sha256"] = hashlib.sha256(model_text.encode("utf-8")).hexdigest()
        if (exported.get("model_input_sha256") is not None
                and exported["model_input_sha256"].lower() != row["model_input_sha256"]):
            raise ValueError("Python literal-mask output differs from the exported managed model-input hash")
        if general:
            payload = {"model": "local-cleanup", "messages": exported["messages"],
                       "max_tokens": arguments.max_output, "stream": False, "temperature": 0,
                       "seed": 0, "cache_prompt": False, "chat_template_kwargs": {"enable_thinking": False}}
            template, _ = server.request("/apply-template", payload, arguments.request_timeout)
            prompt = template.get("prompt")
            if not isinstance(prompt, str):
                raise ValueError("Runtime did not return the embedded chat template")
            add_special = True
            endpoint = "/v1/chat/completions"
        else:
            payload = completion_payload(contract, arguments.max_output)
            prompt = contract["text"]
            add_special = contract["add_special"]
            endpoint = "/completion"
        row["rendered_prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        tokens, _ = server.request("/tokenize", {"content": prompt, "add_special": add_special, "parse_special": True},
                                   arguments.request_timeout)
        if not isinstance(tokens.get("tokens"), list):
            raise ValueError("Runtime did not return the complete input token count")
        row["input_token_count"] = len(tokens["tokens"])
        row["input_tokens_sha256"] = fingerprint(tokens["tokens"])
        if len(tokens["tokens"]) > arguments.context - arguments.max_output:
            raise ValueError("Complete input and reserved output do not fit context; refusing truncation")
        if not general:
            # b12015's /completion string path always adds special tokens. An
            # integer token array preserves the exact validated BOS contract.
            payload["prompt"] = tokens["tokens"]
        row["request_sha256"] = fingerprint({"endpoint": endpoint, "payload": payload})
        response, generation_seconds = server.request(endpoint, payload, arguments.request_timeout)
        row["raw_response"] = response
        row["raw_model_output"] = response.get("content") if not general else None
        if general and isinstance(response.get("choices"), list) and response["choices"]:
            row["raw_model_output"] = response["choices"][0].get("message", {}).get("content")
        output, metadata = read_completion({"style": "chat" if general else "quill_chatml"}, response)
        if normalization != "none":
            output = normalize_specialist_output(output, normalization)
            row["normalized_model_output"] = output
        if protection is not None:
            output = protection.restore(output)
        row.update({"status": "completed", "output": output, "generation_seconds": generation_seconds,
                    "complete_response_seconds": time.perf_counter() - started,
                    "provider_metadata": metadata, "grade": grade(fixture, output)})
    except Exception as error:
        row.update({"status": "timeout" if isinstance(error, TimeoutError) else "failed",
                    "elapsed_seconds": time.perf_counter() - started, "error": f"{type(error).__name__}: {error}"})
    return row


def persist(directory: Path, report: dict, rows: list[dict]) -> None:
    for name, content in (("report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
                          ("outputs.jsonl", "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))):
        temporary = directory / (name + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(directory / name)


def run(arguments: argparse.Namespace) -> int:
    if arguments.output.exists():
        raise ValueError("Output directory already exists; prior evidence will not be overwritten")
    assert_no_native_overlap()
    index = json.loads(arguments.asset_index.read_text(encoding="utf-8"))
    asset = selected_asset(index, arguments.candidate)
    runtime = verify_file(index["runtime"])
    model = verify_file(asset)
    runtime_index = arguments.runtime_file_index or arguments.asset_index.with_name("runtime-file-index.json")
    runtime_inventory = verify_runtime_inventory(runtime_index, runtime) if runtime_index.exists() else None
    if arguments.runtime_file_index is not None and runtime_inventory is None:
        raise ValueError("Explicit runtime inventory is missing")
    exported = json.loads(arguments.prompts.read_text(encoding="utf-8"))
    selected = [row for row in exported["cases"] if arguments.split == "all" or row["fixture"].get("split", "development") == arguments.split]
    if arguments.ids:
        ids = set(arguments.ids.split(","))
        selected = [row for row in selected if row["fixture"]["id"] in ids]
        missing = ids - {row["fixture"]["id"] for row in selected}
        if missing:
            raise ValueError(f"Requested cases absent from selected split: {sorted(missing)}")
    if arguments.limit:
        selected = selected[:arguments.limit]
    if not selected:
        raise ValueError("No selected fixtures")
    general = selected[0].get("completion") is None
    if any((row.get("completion") is None) != general for row in selected):
        raise ValueError("Prompt export mixes native and chat request contracts")
    mask_protocol = literal_mask_protocol(exported, general)
    if any(literal_mask_protocol(row, general) != mask_protocol for row in selected):
        raise ValueError("Prompt export mixes literal mask protocols")
    normalization = specialist_output_normalization(exported, general)
    if any(specialist_output_normalization(row, general) != normalization for row in selected):
        raise ValueError("Prompt export mixes specialist output normalization protocols")
    arguments.output.mkdir(parents=True)
    server_args = ["--alias", "local-cleanup", "--ctx-size", str(arguments.context), "--parallel", "1",
                   "--threads", str(arguments.threads), "--threads-batch", str(arguments.threads),
                   "--batch-size", str(arguments.batch), "--ubatch-size", str(arguments.micro_batch),
                   "--cache-ram", str(arguments.cache_ram), "--ctx-checkpoints", "0", "--n-gpu-layers", "0",
                   "--n-predict", str(arguments.max_output), "--fit", "off", "--no-context-shift", "--no-webui",
                   "--no-slots", "--no-mmproj", "--offline", "--log-disable", "--jinja" if general else "--no-jinja",
                   *arguments.extra_server_arg]
    report = {"schema_version": 1, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "candidate": asset, "runtime": index["runtime"], "asset_index_sha256": sha256_file(arguments.asset_index),
              "runtime_file_index": runtime_inventory,
              "prompts_sha256": sha256_file(arguments.prompts), "prompt_style": exported["prompt_style"],
              "mask_literals": exported.get("mask_literals", general),
              "literal_mask_protocol": mask_protocol,
              "specialist_output_normalization": normalization,
              "managed_assembly_sha256": exported["managed_assembly_sha256"], "host": platform.platform(),
              "profile": {"context": arguments.context, "max_output": arguments.max_output, "threads": arguments.threads,
                          "batch": arguments.batch, "micro_batch": arguments.micro_batch, "cache_ram_mib": arguments.cache_ram,
                          "repeats": arguments.repeats, "extra_server_args": arguments.extra_server_arg}, "incomplete": True,
              "limitations": "Cleanup-server native replay only; no ASR, UI, real capture or Windows delivery. Artifact hashing warms OS pages before startup. First request is cold inference after server warmup, not a filesystem-cold model load. Memory excludes the Python harness and whole Freehand app; no whole-app SLA pass is claimed."}
    rows = []
    server = None
    persist(arguments.output, report, rows)
    try:
        server = OwnedServer(runtime, model, server_args, arguments.output / "server.log",
                             arguments.startup_timeout, arguments.memory_interval)
        report.update({"startup_to_health_seconds": server.startup_seconds, "server_command": server.public_command})
        for repetition in range(1, arguments.repeats + 1):
            for fixture in selected:
                row = replay(server, fixture, arguments)
                row.update({"candidate": asset["id"], "repetition": repetition, "first_request": len(rows) == 0})
                rows.append(row)
                report["summary"] = summarize(rows)
                report["warm_summary"] = summarize([item for item in rows if not item["first_request"]])
                persist(arguments.output, report, rows)
                print(json.dumps({"candidate": asset["id"], "case": row["case_id"], "repetition": repetition,
                                  "status": row["status"], "seconds": row.get("complete_response_seconds", row.get("elapsed_seconds")),
                                  "quality": row.get("grade", {}).get("quality_status")}), flush=True)
                if row["status"] == "timeout" or server.process.poll() is not None:
                    raise RuntimeError("Candidate stopped; no overlapping inference will be started")
        report["incomplete"] = False
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if server is not None:
            server.close()
            report["memory"] = server.memory
        report["summary"] = summarize(rows)
        report["warm_summary"] = summarize([item for item in rows if not item["first_request"]])
        report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        report["not_run_count"] = len(selected) * arguments.repeats - len(rows)
        persist(arguments.output, report, rows)
    return 1 if report["incomplete"] or any(row["status"] != "completed" for row in rows) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-index", type=Path, required=True)
    parser.add_argument("--runtime-file-index", type=Path, help="Complete runtime inventory; defaults to runtime-file-index.json beside the asset index when present")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--prompts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=("development", "heldout", "all"), default="development")
    parser.add_argument("--ids")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--context", type=int, default=2048)
    parser.add_argument("--max-output", type=int, default=512)
    parser.add_argument("--batch", type=int, default=128)
    parser.add_argument("--micro-batch", type=int, default=128)
    parser.add_argument("--cache-ram", type=int, default=0)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--request-timeout", type=float, default=120)
    parser.add_argument("--startup-timeout", type=float, default=180)
    parser.add_argument("--memory-interval", type=float, default=.02)
    parser.add_argument("--extra-server-arg", action="append", default=[],
                        help="Additional native flag/value; repeat, using = before values beginning with --")
    arguments = parser.parse_args()
    for name in ("threads", "context", "max_output", "batch", "micro_batch", "repeats", "request_timeout", "startup_timeout", "memory_interval"):
        if getattr(arguments, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if arguments.max_output >= arguments.context or arguments.micro_batch > arguments.batch or arguments.cache_ram < 0:
        parser.error("Output must be smaller than context, micro-batch <= batch, and cache RAM nonnegative")
    if arguments.limit is not None and arguments.limit <= 0:
        parser.error("--limit must be positive")
    try:
        return run(arguments)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"Small-model evaluation error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
