#!/usr/bin/env python3
"""Bounded random-initialized copy-head pilot; source-feature-only model input."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time

from head_unit_smoke import ROOT, ORIGINAL_PYTHON, configure_torch, required_pins, sha, supervise, validate_grant, write_json


def canonical_sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def load_plan_cache(plan_path: Path, cache_path: Path, *, expected_count=64, expected_train=48, expected_dev=16):
    """Stdlib metadata/document validation; no model/native/file-feature load."""
    from editor_core import Program, ProtectedSpan, encode_program, execute, tokenize_source
    from editor_core.head_contract import HEAD_KEYS, HeadVocabulary
    plan = json.loads(plan_path.read_text())
    cache = json.loads(cache_path.read_text())
    rows = plan.get("cases")
    cached_rows = cache.get("cases")
    if not isinstance(rows, list) or not isinstance(cached_rows, list) or len(rows) != expected_count or len(cached_rows) != expected_count:
        raise ValueError("Plan/cache must retain every predetermined pilot case")
    if cache.get("plan_sha256") != sha(plan_path) or cache.get("owned_process_reaped") is not True or cache.get("cpu_release") is not True:
        raise ValueError("Cache plan pin or explicit native CPU release is missing")
    if Counter(row.get("split") for row in rows) != Counter({"train": expected_train, "development": expected_dev}):
        raise ValueError("Pilot split differs from the predetermined 48/16 plan")
    ids = [row["id"] for row in rows]
    if len(set(ids)) != len(ids) or len({row["id"] for row in cached_rows}) != len(cached_rows) or set(ids) != {row["id"] for row in cached_rows}:
        raise ValueError("Plan/cache IDs must be unique and identical")
    cache_by_id = {row["id"]: row for row in cached_rows}
    entries = []
    vocabulary = HeadVocabulary.current()
    for row in rows:
        cached = cache_by_id[row["id"]]
        if cached.get("source_id") != row.get("source_id") or cached.get("split") != row["split"]:
            raise ValueError("Cache source ID/split disagrees with the frozen plan")
        source, target = row["input"], row["target"]
        if row["source_sha256"] != hashlib.sha256(source.encode()).hexdigest() or row["target_sha256"] != hashlib.sha256(target.encode()).hexdigest():
            raise ValueError("Plan source/target hash mismatch")
        document = tokenize_source(source, [ProtectedSpan(**value) for value in row["protected_spans"]])
        if [asdict(atom) for atom in document.atoms] != row["source_atoms"]:
            raise ValueError("Frozen source atom metadata disagrees with canonical tokenization")
        entry = {"row": row, "cache": cached, "document": document, "feature_path": None,
            "label": None, "feature_status": cached.get("status", "error")}
        label = row["label"]
        if label.get("supported") is True:
            program = Program.from_dict(label["program"])
            encoded = encode_program(document, program)
            if not encoded.supported or execute(document, program).text != target or label.get("length") != encoded.length or label.get("vocabulary_sha256") != vocabulary.sha256:
                raise ValueError("Frozen supported label does not execute to canonical target")
            if set(label["labels"]) != set(HEAD_KEYS) - {"length"} or any(list(encoded.labels[name][:encoded.length]) != label["labels"][name] for name in label["labels"]):
                raise ValueError("Frozen ACTIVE-ONLY labels differ from the encoder contract")
            entry["label"] = encoded
        elif label.get("supported") is not False:
            raise ValueError("Every case needs an explicit supported/unsupported label")
        if cached.get("status") == "ok":
            if row.get("input_status") != "ready" or cached.get("source_sha256") != row["source_sha256"] or cached.get("encoder_contract_sha256") != canonical_sha(row["encoder_contract"]):
                raise ValueError("Cached feature source/encoder contract pin mismatch")
            if cached.get("shape") != [len(document.atoms), 1024] or cached.get("dtype") != "float32-le" or not document.atoms:
                raise ValueError("Cached feature shape/dtype differs from source atom contract")
            path = (cache_path.parent / cached["atom_features_path"]).resolve()
            if not path.is_relative_to(cache_path.parent.resolve()) or sha(path) != cached["atom_features_sha256"] or path.stat().st_size != len(document.atoms) * 1024 * 4:
                raise ValueError("Feature path/hash/byte count mismatch")
            entry["feature_path"] = path
        entries.append(entry)
    return plan, cache, entries


def load_features(entry, torch):
    import numpy as np
    matrix = np.fromfile(entry["feature_path"], dtype="<f4").reshape(len(entry["document"].atoms), 1024)
    if not np.isfinite(matrix).all():
        raise ValueError("Non-finite source atom features")
    return torch.from_numpy(matrix.copy())


def batch_inputs(entries, torch):
    count = max(len(entry["document"].atoms) for entry in entries)
    features = torch.zeros(len(entries), count, 1024, dtype=torch.float32)
    padding = torch.ones(len(entries), count, dtype=torch.bool)
    for index, entry in enumerate(entries):
        value = entry["features"]
        features[index, :len(value)] = value
        padding[index, :len(value)] = False
    return features, padding


def case_statuses(entries, used_ids):
    return [{"id": entry["row"]["id"], "split": entry["row"]["split"],
        "label_supported": entry["row"]["label"]["supported"], "label_reasons": entry["row"]["label"].get("reasons", []),
        "features_available": "features" in entry, "feature_status": entry["feature_status"],
        "used_for_ce": entry["row"]["id"] in used_ids} for entry in entries]


def evaluate_entries(model, entries, torch, *, deadline=None, stop_file=None):
    """Every dev row is retained; exact target matches are diagnostic only."""
    from editor_core.head_contract import decode_parallel_scores
    results = []
    model.eval()
    for entry in entries:
        row = entry["row"]
        result = {"id": row["id"], "source_id": row.get("source_id"), "split": row["split"],
            "label_supported": row["label"]["supported"], "status": "unavailable", "accepted": False,
            "exact_canonical": False, "fallback_success_credit": False}
        stopped = (deadline is not None and time.monotonic() >= deadline) or (stop_file is not None and stop_file.exists())
        if stopped:
            result["status"] = "not_attempted"
            result["error"] = "deadline_or_stop_file"
        elif "features" not in entry:
            result["error"] = entry["feature_status"]
        else:
            features, padding = batch_inputs([entry], torch)
            with torch.no_grad():
                logits = model(features, padding)
            # Bound search for the 120s pilot. This can reject a representable
            # program; bounded-search failure still counts in all-case metrics.
            decoded = model.decode_sample(entry["document"], logits, beam_width=2,
                length_candidates=1, kind_candidates=2, pointer_candidates=2,
                value_candidates=2, case_candidates=1)
            result["accepted"] = decoded.accepted
            result["status"] = "accepted" if decoded.accepted else "rejected"
            result["diagnostics"] = dict(decoded.diagnostics)
            if decoded.accepted:
                result["text"] = decoded.execution.text
                result["program"] = decoded.program.to_dict()
                result["trace"] = [asdict(step) for step in decoded.execution.trace]
                result["exact_canonical"] = decoded.execution.text == row["target"]
            else:
                result["errors"] = list(decoded.reasons)
        results.append(result)
    return results


def worker(args):
    torch = configure_torch(args.seed)
    import resource
    from editor_core.head_model import CopyEditHead, HeadConfig
    from editor_core.head_contract import HEAD_KEYS
    from head_loss import COEFFICIENTS, head_loss
    random.seed(args.seed)
    started = time.monotonic()
    deadline = started + args.worker_seconds
    plan, cache, entries = load_plan_cache(args.plan, args.cache)
    for entry in entries:
        if entry["feature_path"] is not None:
            entry["features"] = load_features(entry, torch)
    train_rows = [entry for entry in entries if entry["row"]["split"] == "train"]
    dev_rows = [entry for entry in entries if entry["row"]["split"] == "development"]
    supported_train = [entry for entry in train_rows if entry["label"] is not None and "features" in entry]
    model = CopyEditHead(HeadConfig())
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=0.01)
    steps = 0
    history = []
    stop_reason = "max_steps" if supported_train else "no_supported_training_labels"
    model.train()
    while supported_train and steps < args.steps:
        if time.monotonic() >= deadline - 25:
            stop_reason = "training_deadline_reserve_for_development"
            break
        if args.stop_file is not None and args.stop_file.exists():
            stop_reason = "stop_file"
            break
        selected = [supported_train[(steps * args.batch_size + index) % len(supported_train)] for index in range(args.batch_size)]
        features, padding = batch_inputs(selected, torch)
        labels = {name: torch.tensor([entry["label"].labels[name] for entry in selected], dtype=torch.long)
            for name in HEAD_KEYS if name != "length"}
        labels["length"] = torch.tensor([entry["label"].length for entry in selected], dtype=torch.long)
        optimizer.zero_grad(set_to_none=True)
        loss, components = head_loss(model(features, padding), labels)
        if not bool(torch.isfinite(loss)):
            raise ValueError("Non-finite training loss")
        loss.backward()
        if not all(parameter.grad is None or bool(torch.isfinite(parameter.grad).all()) for parameter in model.parameters()):
            raise ValueError("Non-finite training gradient")
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        steps += 1
        if steps == 1 or steps % 20 == 0:
            history.append({"step": steps, "loss": float(loss.detach()), "components": {name: float(value.detach()) for name, value in components.items()}})
    # Save only the new, small random-initialized research head, never base/adapters.
    model.eval()
    head_path = args.output_dir / "final-head.pt"
    torch.save(model.checkpoint_payload(), head_path)
    if head_path.stat().st_size >= 10_000_000:
        head_path.unlink()
        raise ValueError("Head artifact exceeded the explicit 10MB cap")
    development = evaluate_entries(model, dev_rows, torch, deadline=deadline, stop_file=args.stop_file)
    write_json(args.output_dir / "development.json", {"scope": "All16 development cases; exact canonical diagnostic only, no manual faithful/clean quality claim.",
        "case_count": len(development), "exact_canonical": sum(row["exact_canonical"] for row in development),
        "accepted": sum(row["accepted"] for row in development), "cases": development})
    used_ids = {entry["row"]["id"] for entry in supported_train}
    case_status = case_statuses(entries, used_ids)
    write_json(args.output_dir / "config.json", model.config.to_dict())
    write_json(args.output_dir / "vocabulary.json", model.vocabulary.to_dict())
    write_json(args.output_dir / "metrics.json", {"scope": "Research pilot; no heldout/manual quality or whole-app SLA claim.",
        "all_cases": len(entries), "train_denominator": len(train_rows), "development_denominator": len(dev_rows),
        "train_ce_cases": len(supported_train), "train_without_ce": len(train_rows) - len(supported_train),
        "steps": steps, "stop_reason": stop_reason, "history": history, "cases": case_status,
        "requested_steps": args.steps, "worker_seconds": args.worker_seconds, "optimizer": "AdamW", "weight_decay": 0.01,
        "seed": args.seed, "learning_rate": args.learning_rate, "batch_size": args.batch_size,
        "loss_coefficients": dict(COEFFICIENTS), "torch_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(), "elapsed_seconds": time.monotonic() - started,
        "parameters": sum(p.numel() for p in model.parameters()), "rss_max_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024})
    write_json(args.output_dir / "candidate-manifest.json", {"schema_version": 1,
        "kind": "new-random-initialized-research-copy-head-not-active", "plan_sha256": sha(args.plan),
        "cache_sha256": sha(args.cache), "feature_profile_sha256": cache.get("feature_profile_sha256"),
        "source_pins": required_pins(("train_pilot.py",)), "head_sha256": sha(head_path),
        "head_bytes": head_path.stat().st_size, "vocabulary_sha256": model.vocabulary.sha256,
        "base_or_adapter_copies_written": False})
    total_artifact_bytes = sum(path.stat().st_size for path in args.output_dir.iterdir() if path.is_file())
    if total_artifact_bytes >= 10_000_000:
        head_path.unlink()
        raise ValueError("Combined pilot artifacts exceeded10MB; candidate head removed")


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--plan", type=Path, required=True)
    value.add_argument("--cache", type=Path, required=True)
    value.add_argument("--output-dir", type=Path, required=True)
    value.add_argument("--cpu-grant", type=Path, required=True)
    value.add_argument("--python", default=ORIGINAL_PYTHON)
    value.add_argument("--steps", type=int, default=300)
    value.add_argument("--batch-size", type=int, default=4)
    value.add_argument("--learning-rate", type=float, default=0.001)
    value.add_argument("--seed", type=int, default=20261104)
    value.add_argument("--worker-seconds", type=float, default=110)
    value.add_argument("--stop-file", type=Path)
    value.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    return value


def main():
    args = parser().parse_args()
    if args.python != ORIGINAL_PYTHON or not 1 <= args.steps <= 300 or not 1 <= args.batch_size <= 8 or not 0 < args.worker_seconds <= 115 or not math.isfinite(args.learning_rate) or not 0 < args.learning_rate <= 0.01:
        raise ValueError("Original interpreter and bounded pilot settings are required")
    pins = {**required_pins(("train_pilot.py",)), "plan": sha(args.plan), "cache": sha(args.cache)}
    validate_grant(args.cpu_grant, "copy-editor-head-train64", pins, 120)
    if args.worker:
        worker(args)
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=False)
    command = [args.python, str(Path(__file__).absolute()), *sys.argv[1:], "--worker"]
    return supervise(command, args.output_dir, 120)


if __name__ == "__main__":
    raise SystemExit(main())
