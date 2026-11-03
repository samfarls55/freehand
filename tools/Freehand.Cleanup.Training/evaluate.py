#!/usr/bin/env python3
"""Evaluate a frozen ScribeKey derivative through Freehand's actual contracts.

Native assertions and target matches are diagnostics. The current 99% gate requires a
separate, output-hash-bound semantic review of every case; it cannot be earned
by matching strings, rejecting candidates, or falling back to unchanged text.
At least 495 of the 500 final cases must be both faithful and clean/usable.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tarfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
EVALUATION = HERE.parent / "Freehand.Cleanup.Evaluation"
MINIMUM_JOINT_ACCURACY = .99
sys.path.insert(0, str(EVALUATION))
from benchmark import sha256_file  # noqa: E402
import small_models  # noqa: E402


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def artifact(path: Path) -> dict:
    path = path.resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Expected a regular artifact: {path}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def source_files() -> dict:
    selected = set(HERE.glob("*.py"))
    for folder in ("src/Freehand.Cleanup", "src/Freehand.Core", "tools/Freehand.Cleanup.Probe"):
        selected.update((ROOT / folder).glob("*.cs"))
    selected.update(EVALUATION.glob("*.py"))
    return {str(path.relative_to(ROOT)): artifact(path)["sha256"] for path in sorted(selected)}


def quality_target(case_count: int) -> dict:
    return {"semantic_metric": "faithful_and_clean_usable", "minimum_joint_accuracy": MINIMUM_JOINT_ACCURACY,
            "case_count": case_count, "required_pass_count": math.ceil(case_count * MINIMUM_JOINT_ACCURACY)}


def snapshot_sources(path: Path, sources: dict[str, str]) -> dict:
    """Preserve the exact bytes already hashed by this new pre-run freeze."""
    with path.open("xb") as destination, gzip.GzipFile(fileobj=destination, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for relative, expected in sorted(sources.items()):
                raw = (ROOT / relative).read_bytes()
                if hashlib.sha256(raw).hexdigest() != expected:
                    raise ValueError(f"Source changed while creating its pre-run snapshot: {relative}")
                entry = tarfile.TarInfo(relative)
                entry.size = len(raw)
                entry.mode = 0o644
                archive.addfile(entry, io.BytesIO(raw))
            manifest = json.dumps({"files": sources}, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
            entry = tarfile.TarInfo("source-files-sha256.json")
            entry.size = len(manifest)
            entry.mode = 0o644
            archive.addfile(entry, io.BytesIO(manifest))
    with tarfile.open(path, "r:gz") as archive:
        files = {entry.name for entry in archive.getmembers() if entry.isfile()}
        if files != set(sources) | {"source-files-sha256.json"}:
            raise ValueError("Source snapshot inventory mismatch")
        for relative, expected in sources.items():
            if hashlib.sha256(archive.extractfile(relative).read()).hexdigest() != expected:
                raise ValueError(f"Archived source bytes do not match the freeze: {relative}")
    return {**artifact(path), "source_file_count": len(sources), "exact_archived_bytes_verified": True,
            "capture_stage": "new_candidate_freeze_before_inference",
            "historical_scope": "This snapshot covers this new freeze only; earlier hash-only freezes were not retroactively snapshotted."}


def verify_artifact(entry: dict) -> Path:
    path = Path(entry["path"]).resolve(strict=True)
    if path.stat().st_size != entry["bytes"] or sha256_file(path) != entry["sha256"]:
        raise ValueError(f"Artifact drift: {path}")
    return path


def managed_files(probe: Path) -> list[dict]:
    names = ["Freehand.Cleanup.Probe.dll", "Freehand.Cleanup.dll", "Freehand.Core.dll",
             "Freehand.Dictionary.dll", "Freehand.Abstractions.dll", "Freehand.Testing.dll"]
    paths = [probe.parent / name for name in names]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError(f"Probe runtime assemblies are missing: {missing}")
    return [artifact(path) for path in paths]


def freeze(arguments) -> int:
    if arguments.output.exists():
        raise ValueError("Candidate freeze already exists; preserve it")
    runtime = artifact(arguments.runtime)
    inventory = small_models.verify_runtime_inventory(arguments.runtime_inventory, Path(runtime["path"]))
    value = {"schema_version": 1, "created_utc": utc(), "purpose": "candidate_frozen_before_final_test_opening",
             "model": artifact(arguments.model), "runtime": runtime,
             "runtime_inventory": artifact(arguments.runtime_inventory), "runtime_verification": inventory,
             "probe": artifact(arguments.probe), "managed_assemblies": managed_files(arguments.probe),
             "sources": source_files(), "git_head_historical": subprocess.check_output(
                 ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
             "profile": runtime_profile(), "quality_target": quality_target(500),
             "limitations": "A candidate freeze is identity evidence, not quality or performance qualification."}
    if arguments.adapter_config:
        value["adapter_config"] = artifact(arguments.adapter_config)
        adapter = arguments.adapter_config.with_name("adapter.safetensors")
        value["adapter"] = artifact(adapter)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    snapshot = arguments.output.with_name(arguments.output.stem + ".source-snapshot.tar.gz")
    value["source_snapshot"] = snapshot_sources(snapshot, value["sources"])
    write_new(arguments.output, value)
    print(json.dumps({"freeze": str(arguments.output), "sha256": sha256_file(arguments.output),
                      "model_sha256": value["model"]["sha256"]}))
    return 0


def verify_freeze(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    for key in ("model", "runtime", "runtime_inventory", "probe"):
        verify_artifact(value[key])
    for key in ("adapter", "adapter_config"):
        if key in value:
            verify_artifact(value[key])
    for item in value["managed_assemblies"]:
        verify_artifact(item)
    if "source_snapshot" not in value:
        raise ValueError("Historical hash-only freeze cannot start a new evaluation; create a new pre-run source snapshot")
    verify_artifact(value["source_snapshot"])
    if value["sources"] != source_files():
        raise ValueError("Evaluation/production source drift after candidate freeze")
    small_models.verify_runtime_inventory(Path(value["runtime_inventory"]["path"]), Path(value["runtime"]["path"]))
    if value["profile"] != runtime_profile():
        raise ValueError("Runtime profile drift after candidate freeze")
    if value.get("quality_target") != quality_target(500):
        raise ValueError("Candidate freeze does not record the current 99 percent acceptance target")
    return value


def runtime_profile() -> dict:
    return {"promptStyle": "ScribeKeyFast", "threads": 4, "contextSize": 1024,
            "maxOutputTokens": 512, "batchSize": 64, "microBatchSize": 32,
            "promptCacheMiB": 0, "contextCheckpoints": 0, "cacheTypeK": "f16", "cacheTypeV": "f16",
            "repack": False, "gpuLayers": 0, "startupTimeoutSeconds": 60, "idleTimeoutSeconds": 60,
            "maskSpecialistLiterals": True, "promptLookupTokens": 16, "promptLookupMatchTokens": 3}


def load_corpus(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        value = {"schema_version": 1, "cases": []}
        for row in rows:
            if not isinstance(row.get("input"), str) or not isinstance(row.get("target"), str):
                raise ValueError("Training JSONL requires string input/target fields")
            target = row["target"]
            case = {"id": row["id"], "input": row["input"], "targets": [target],
                    "split": "development", "category": row.get("category", row.get("family", "unspecified")),
                    "needs_cleanup": row.get("needs_cleanup", row["input"] != target),
                    "checks": row.get("checks", {})}
            if row.get("dictionary"):
                case["dictionary"] = row["dictionary"]
            value["cases"].append(case)
    else:
        value = json.loads(raw)
    rows = value.get("cases")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Corpus needs a nonempty cases array")
    identifiers = set()
    for row in rows:
        if not isinstance(row.get("id"), str) or row["id"] in identifiers:
            raise ValueError("Case IDs must be unique strings")
        identifiers.add(row["id"])
        if not isinstance(row.get("input"), str) or not row["input"].strip():
            raise ValueError("Each case requires nonempty input")
        targets = row.get("targets")
        if not isinstance(targets, list) or not targets or any(not isinstance(target, str) or not target.strip() for target in targets):
            raise ValueError("Each case requires nonempty string targets")
    return value


def phase_gate(arguments, freeze_value: dict) -> dict | None:
    if arguments.phase == "development":
        if any("blind" in part.casefold() for part in arguments.dataset.parts):
            raise ValueError("Blind corpus cannot be opened as development material")
        return None
    if not arguments.blind_commitment:
        raise ValueError("Blind final requires its prior independent corpus commitment")
    commitment = json.loads(arguments.blind_commitment.read_text(encoding="utf-8"))
    if commitment.get("corpus_sha256", "").lower() != sha256_file(arguments.dataset):
        raise ValueError("Blind corpus does not match its original commitment")
    if commitment.get("case_count") != 500:
        raise ValueError("The final qualification commitment must contain 500 cases")
    consumed = arguments.blind_commitment.with_suffix(".consumed.json")
    if consumed.exists():
        raise ValueError("Blind corpus has already been consumed; further tuning requires a new independent test")
    write_new(consumed, {"created_utc": utc(), "dataset_sha256": commitment["corpus_sha256"],
                        "candidate_freeze": artifact(arguments.candidate_freeze),
                        "model_sha256": freeze_value["model"]["sha256"],
                        "purpose": "one-time blind qualification; preserve even if inference fails"})
    return commitment


def invoke(argv: list[str], log: Path) -> int:
    with log.open("x", encoding="utf-8") as stream:
        result = subprocess.run(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, text=True, check=False)
    return result.returncode


def native(arguments) -> int:
    if arguments.output.exists():
        raise ValueError("Evaluation output already exists; use a fresh directory")
    frozen = verify_freeze(arguments.candidate_freeze)
    commitment = phase_gate(arguments, frozen)  # Do not parse test text before identity/commitment validation.
    corpus = load_corpus(arguments.dataset)
    if commitment is not None and len(corpus["cases"]) != commitment["case_count"]:
        raise ValueError("Blind corpus case count drift")
    arguments.output.mkdir(parents=True)
    corpus_path = arguments.output / "probe-corpus.json"
    write_new(corpus_path, corpus)
    write_new(arguments.output / "evaluation-pre-run-freeze.json", {
        "schema_version": 1, "created_utc": utc(), "phase": arguments.phase,
        "dataset": artifact(arguments.dataset), "candidate_freeze": artifact(arguments.candidate_freeze),
        "blind_commitment": artifact(arguments.blind_commitment) if arguments.blind_commitment else None,
        "case_count": len(corpus["cases"]), "case_ids": [row["id"] for row in corpus["cases"]], "mode": arguments.mode,
        "quality_target": quality_target(len(corpus["cases"])),
        "semantic_review_required": True, "windows_execution_tested": False, "whole_app_sla_qualified": False})
    profile = runtime_profile()
    manifest = {"runtimePath": frozen["runtime"]["path"], "runtimeSha256": frozen["runtime"]["sha256"],
                "modelPath": frozen["model"]["path"], "modelSha256": frozen["model"]["sha256"],
                "modelId": "ScribeKey-Freehand-" + ("trained-" if "adapter" in frozen else "baseline-")
                + frozen["model"]["sha256"][:12], **profile}
    manifest_path = arguments.output / "cleanup-manifest.json"
    write_new(manifest_path, manifest)
    codes = {}
    probe_argv = [str(arguments.dotnet), frozen["probe"]["path"]]
    if arguments.mode in ("native", "both"):
        prompts = arguments.output / "production-prompts.json"
        codes["export_prompts"] = invoke(probe_argv + ["--export-prompts", "--input", str(corpus_path),
            "--output", str(prompts), "--prompt-style", "ScribeKeyFast", "--mask-specialist-literals", "true"],
            arguments.output / "export-prompts.log")
        if codes["export_prompts"]:
            write_new(arguments.output / "command-results.json", codes)
            return 1
        index = {"runtime": frozen["runtime"], "assets": [{"id": manifest["modelId"],
                 "verified": True, **frozen["model"]}]}
        asset_index = arguments.output / "asset-index.json"
        write_new(asset_index, index)
        replay = argparse.Namespace(asset_index=asset_index, runtime_file_index=Path(frozen["runtime_inventory"]["path"]),
            candidate=manifest["modelId"], prompts=prompts, output=arguments.output / "native",
            split="all", ids=None, limit=None, threads=4, context=1024, max_output=512, batch=64,
            micro_batch=32, cache_ram=0, repeats=1, request_timeout=120, startup_timeout=180,
            memory_interval=.02, extra_server_arg=["--cache-type-k", "f16", "--cache-type-v", "f16",
                "--no-repack", "--spec-type", "ngram-map-k", "--spec-ngram-map-k-size-n", "3",
                "--spec-ngram-map-k-size-m", "16"])
        codes["native"] = small_models.run(replay)
    if arguments.mode in ("core", "both"):
        codes["core"] = invoke(probe_argv + ["--input", str(corpus_path), "--output",
            str(arguments.output / "core-results.json"), "--manifest", str(manifest_path),
            "--split", "all", "--cleanup-timeout-seconds", "120"], arguments.output / "core.log")
    verify_freeze(arguments.candidate_freeze)
    write_new(arguments.output / "command-results.json", codes)
    print(json.dumps({"output": str(arguments.output), "commands": codes,
                      "semantic_accuracy": "unreviewed; structural results are not accuracy"}))
    return 1 if any(codes.values()) else 0


def result_rows(path: Path) -> list[dict]:
    if path.suffix == ".jsonl":
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [{"case_id": row["case_id"], "input": row["input"], "output": row.get("output"),
                 "targets": row.get("targets", []), "structural_success": row.get("status") == "completed",
                 "source": row} for row in rows]
    report = json.loads(path.read_text(encoding="utf-8"))
    rows = report.get("cases", [])
    return [{"case_id": row["id"], "input": row["input"], "output": row.get("output"),
             "targets": row.get("normalized_targets", []), "structural_success":
             row.get("cleanup_status") in ("Applied", "Unchanged") and row.get("candidate_text") is not None
             and row.get("insertion_count") == 1 and row.get("delivered_count") == 1
             and row.get("error") is None, "source": row} for row in rows]


def output_sha(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def score_review(rows: list[dict], review: dict, minimum: float = MINIMUM_JOINT_ACCURACY,
                 expected_ids: set[str] | None = None) -> dict:
    if not rows or len({row["case_id"] for row in rows}) != len(rows):
        raise ValueError("Results must contain unique cases")
    if expected_ids is not None and {row["case_id"] for row in rows} != expected_ids:
        raise ValueError("Results do not cover the exact pre-run case inventory")
    if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
        raise ValueError("Name the semantic reviewer and preserve its actual review scope")
    judgments = review.get("cases")
    if not isinstance(judgments, list) or len(judgments) != len(rows):
        raise ValueError("A semantic review must cover every result exactly once")
    by_id = {}
    for item in judgments:
        identity = item.get("case_id", item.get("id"))
        if identity in by_id:
            raise ValueError("Duplicate semantic review case")
        by_id[identity] = item
    if set(by_id) != {row["case_id"] for row in rows}:
        raise ValueError("Review/result IDs differ")
    faithful = clean = joint = critical = structural = target_matches = 0
    for row in rows:
        item = by_id[row["case_id"]]
        if item.get("output_sha256") != output_sha(row["output"]):
            raise ValueError("Semantic review does not identify the exact output bytes")
        for key in ("semantic_faithful", "clean_usable", "critical_error"):
            if type(item.get(key)) is not bool:
                raise ValueError(f"Explicit boolean review judgment required: {key}")
        valid = row["structural_success"]
        structural += valid
        faithful += valid and item["semantic_faithful"] and not item["critical_error"]
        clean += valid and item["clean_usable"]
        joint += valid and item["semantic_faithful"] and item["clean_usable"] and not item["critical_error"]
        critical += item["critical_error"]
        target_matches += row["output"] in row["targets"]
    count = len(rows)
    required_pass_count = math.ceil(count * minimum)
    return {"case_count": count, "structural_success": structural, "faithful": faithful,
            "clean_usable": clean, "faithful_and_clean_usable": joint, "joint_accuracy": joint / count,
            "critical_errors": critical, "minimum_joint_accuracy": minimum,
            "required_pass_count": required_pass_count, "failed_or_unusable_cases": count - joint,
            "quality_gate_passed": joint >= required_pass_count,
            "zero_observed_critical_errors": critical == 0,
            "exact_target_matches_diagnostic_only": target_matches,
            "reviewer": review.get("reviewer", "unspecified"),
            "limitations": "Finite assistant-authored synthetic diagnostic corpus and named semantic reviewer; no population accuracy or Windows SLA claim."}


def review(arguments) -> int:
    rows = result_rows(arguments.results)
    metadata_paths = [parent / "evaluation-pre-run-freeze.json" for parent in
                      (arguments.results.parent, arguments.results.parent.parent)]
    metadata_path = next((path for path in metadata_paths if path.is_file()), None)
    if metadata_path is None:
        raise ValueError("Results need their pre-run evaluation metadata; partial denominators are forbidden")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if len(rows) != metadata["case_count"] or {row["case_id"] for row in rows} != set(metadata["case_ids"]):
        raise ValueError("Results do not cover the exact pre-run case inventory")
    if arguments.judgments:
        value = json.loads(arguments.judgments.read_text(encoding="utf-8"))
        value = {"schema_version": 1, "results": artifact(arguments.results),
                 "judgments": artifact(arguments.judgments), "evaluation_metadata": artifact(metadata_path),
                 "phase": metadata["phase"],
                 "pre_run_quality_target": metadata.get("quality_target", "not_recorded_in_historical_run"),
                 "current_quality_target": quality_target(len(rows)),
                 **score_review(rows, value, expected_ids=set(metadata["case_ids"]))}
    else:
        value = {"schema_version": 1, "results": artifact(arguments.results), "reviewer": None,
                 "current_quality_target": quality_target(len(rows)),
                 "cases": [{"case_id": row["case_id"], "input": row["input"], "output": row["output"],
                            "targets": row["targets"], "output_sha256": output_sha(row["output"]),
                            "structural_success": row["structural_success"], "semantic_faithful": None,
                            "clean_usable": None, "critical_error": None, "reason": ""} for row in rows]}
    write_new(arguments.output, value)
    print(json.dumps({"output": str(arguments.output), "quality_gate_passed": value.get("quality_gate_passed")}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    frozen = sub.add_parser("freeze")
    for name in ("model", "runtime", "runtime-inventory", "probe", "output"):
        frozen.add_argument("--" + name, type=Path, required=True)
    frozen.add_argument("--adapter-config", type=Path)
    native_parser = sub.add_parser("native")
    for name in ("dataset", "candidate-freeze", "dotnet", "output"):
        native_parser.add_argument("--" + name, type=Path, required=True)
    native_parser.add_argument("--phase", choices=("development", "blind-final"), required=True)
    native_parser.add_argument("--mode", choices=("native", "core", "both"), default="both")
    native_parser.add_argument("--blind-commitment", type=Path)
    reviews = sub.add_parser("review", description="Score the current 99% joint semantic-quality target: "
                            "at least 495/500 faithful and clean/usable final outputs. "
                            "Every result requires an explicit output-bound review.")
    reviews.add_argument("--results", type=Path, required=True)
    reviews.add_argument("--judgments", type=Path)
    reviews.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    try:
        return {"freeze": freeze, "native": native, "review": review}[args.command](args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"Evaluation error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
