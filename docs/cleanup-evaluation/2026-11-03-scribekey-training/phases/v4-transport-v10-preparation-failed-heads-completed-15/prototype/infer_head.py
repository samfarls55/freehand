#!/usr/bin/env python3
"""Strict cached-feature inference for a small research head; never calls native."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

from head_unit_smoke import ORIGINAL_PYTHON, configure_torch, required_pins, sha, supervise, validate_grant, write_json
from train_pilot import evaluate_entries, load_features, load_plan_cache


def worker(args):
    torch = configure_torch(args.seed)
    from editor_core.head_model import CopyEditHead
    _, cache, entries = load_plan_cache(args.plan, args.cache)
    selected = [entry for entry in entries if (args.split == "all" or entry["row"]["split"] == args.split)
        and (not args.case_id or entry["row"]["id"] in args.case_id)]
    if args.case_id and set(args.case_id) != {entry["row"]["id"] for entry in selected}:
        raise ValueError("Unknown/mismatched requested case IDs")
    if args.checkpoint.stat().st_size >= 10_000_000:
        raise ValueError("Refusing checkpoint larger than the small-head artifact cap")
    payload = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    model = CopyEditHead.from_checkpoint_payload(payload).eval()
    for entry in selected:
        if entry["feature_path"] is not None:
            entry["features"] = load_features(entry, torch)
    started = time.monotonic()
    results = evaluate_entries(model, selected, torch, deadline=started + 110)
    write_json(args.output_dir / "inference.json", {"scope": "Cached source features only; exact canonical diagnostics, no manual faithful/clean or SLA claim.",
        "case_count": len(selected), "cases": results, "accepted": sum(row["accepted"] for row in results),
        "exact_canonical": sum(row["exact_canonical"] for row in results),
        "all_plan_cases": len(entries), "split": args.split, "elapsed_seconds": time.monotonic() - started,
        "checkpoint_sha256": sha(args.checkpoint), "plan_sha256": sha(args.plan), "cache_sha256": sha(args.cache),
        "feature_profile_sha256": cache.get("feature_profile_sha256"), "native_calls": 0, "fallback_success_credit": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "cache", "checkpoint", "output-dir", "cpu-grant"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--python", default=ORIGINAL_PYTHON)
    parser.add_argument("--split", choices=("train", "development", "all"), default="development")
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--seed", type=int, default=20261104)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.python != ORIGINAL_PYTHON:
        raise ValueError("Original conversion-env interpreter spelling is required")
    pins = {**required_pins(("train_pilot.py", "infer_head.py")), "plan": sha(args.plan), "cache": sha(args.cache), "checkpoint": sha(args.checkpoint)}
    validate_grant(args.cpu_grant, "copy-editor-head-infer64", pins, 120)
    if args.worker:
        worker(args)
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=False)
    return supervise([args.python, str(Path(__file__).absolute()), *sys.argv[1:], "--worker"], args.output_dir, 120)


if __name__ == "__main__":
    raise SystemExit(main())
