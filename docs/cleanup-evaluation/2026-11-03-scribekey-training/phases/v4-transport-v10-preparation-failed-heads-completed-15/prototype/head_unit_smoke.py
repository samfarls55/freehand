#!/usr/bin/env python3
"""Stdlib supervisor; Torch runs only in a granted, bounded owned child."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).absolute().parent
ORIGINAL_PYTHON = "/workspace/freehand/work/cleanup-small-models-2026-11-03/scribe-precision-source/conversion-env/bin/python"
CORE_PINS = ("editor_core/__init__.py", "editor_core/core.py", "editor_core/head_contract.py", "editor_core/head_model.py", "head_loss.py", "head_unit_smoke.py")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def required_pins(extra=()) -> dict[str, str]:
    return {name: sha(ROOT / name) for name in (*CORE_PINS, *extra)}


def validate_grant(path: Path, operation: str, pins: dict[str, str], seconds: float) -> dict:
    grant = json.loads(path.read_text())
    if (grant.get("operation") != operation or grant.get("cpu_granted") is not True
            or type(grant.get("max_wall_seconds")) not in (int, float)
            or not 0 < seconds <= grant["max_wall_seconds"]):
        raise ValueError("Missing/mismatched explicit CPU grant or time bound")
    supplied = grant.get("pins", {})
    if any(supplied.get(name) != digest for name, digest in pins.items()):
        raise ValueError("CPU grant source/input pins do not match")
    return grant


def supervise(command: list[str], directory: Path, seconds: float) -> int:
    started = time.monotonic()
    env = dict(os.environ, OMP_NUM_THREADS="2", MKL_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2")
    timed_out = False
    with (directory / "worker.stdout").open("x") as stdout, (directory / "worker.stderr").open("x") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
            stdout=stdout, stderr=stderr, start_new_session=True)
        print(json.dumps({"event": "owned_worker_started", "owned_pid": process.pid,
            "owned_process_group": process.pid, "owned_session": process.pid}), flush=True)
        try:
            code = process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                code = process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait(timeout=1)
    # Only this owned process group is inspected/terminated.
    try:
        os.killpg(process.pid, 0)
        os.killpg(process.pid, signal.SIGKILL)
        group_released = False
    except ProcessLookupError:
        group_released = True
    report = {"owned_pid": process.pid, "owned_process_group": process.pid,
        "returncode": code, "timed_out": timed_out, "elapsed_seconds": time.monotonic() - started,
        "owned_process_reaped": process.poll() is not None, "owned_group_released": group_released,
        "cpu_release": process.poll() is not None and group_released}
    write_json(directory / "supervisor.json", report)
    return 124 if timed_out else code if code else (0 if report["cpu_release"] else 1)


def configure_torch(seed=20261104):
    import torch
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    return torch


def worker(directory: Path) -> None:
    torch = configure_torch()
    import resource
    from editor_core import Operation, Program, ProtectedSpan, tokenize_source
    from editor_core.head_contract import HEAD_KEYS, IGNORE_INDEX, encode_program
    from editor_core.head_model import CopyEditHead, HeadConfig
    from head_loss import COEFFICIENTS, head_loss
    config = HeadConfig(dropout=0.0)
    model = CopyEditHead(config)
    docs = [tokenize_source("Ada report", [ProtectedSpan("person", 0, 3)]), tokenize_source("send report")]
    programs = [Program((Operation("copy", 0), Operation("space", value=" "), Operation("copy", 1))),
        Program((Operation("copy", 0), Operation("space", value=" "), Operation("copy", 1)))]
    encoded = [encode_program(doc, program, max_ops=config.max_ops, max_source_atoms=config.max_source_atoms) for doc, program in zip(docs, programs)]
    assert all(row.supported for row in encoded)
    features = torch.randn(2, 3, 1024)
    padding = torch.tensor([[False, False, True], [False, False, True]])
    labels = {name: torch.tensor([row.labels[name] for row in encoded], dtype=torch.long) for name in HEAD_KEYS if name != "length"}
    labels["length"] = torch.tensor([row.length for row in encoded])
    logits = model(features, padding)
    total, components = head_loss(logits, labels)
    assert bool(torch.isfinite(total))
    total.backward()
    grads = [p.grad for p in model.parameters() if p.grad is not None]
    assert grads and all(bool(torch.isfinite(grad).all()) for grad in grads)
    model.zero_grad(set_to_none=True)
    all_ignored = {name: torch.full_like(value, IGNORE_INDEX) for name, value in labels.items()}
    all_masked_loss, _ = head_loss(model(features, padding), all_ignored)
    assert float(all_masked_loss.detach()) == 0.0
    all_masked_loss.backward()
    assert all(p.grad is None or bool(torch.isfinite(p.grad).all()) for p in model.parameters())
    model.eval()
    with torch.no_grad():
        expected = model(features, padding)
    memory = io.BytesIO()
    torch.save(model.checkpoint_payload(), memory)
    memory.seek(0)
    payload = torch.load(memory, map_location="cpu", weights_only=True)
    restored = CopyEditHead.from_checkpoint_payload(payload).eval()
    with torch.no_grad():
        actual = restored(features, padding)
    assert all(torch.equal(expected[name], actual[name]) for name in HEAD_KEYS)
    bad_schema = dict(payload, schema_version=999)
    try:
        CopyEditHead.from_checkpoint_payload(bad_schema)
        raise AssertionError("Malformed schema accepted")
    except ValueError:
        pass
    bad_vocab = dict(payload, vocabulary=dict(payload["vocabulary"], function_values=["Mallory"]))
    try:
        CopyEditHead.from_checkpoint_payload(bad_vocab)
        raise AssertionError("Malformed vocabulary accepted")
    except ValueError:
        pass
    write_json(directory / "unit-result.json", {"status": "pass", "pid": os.getpid(),
        "parameters": sum(p.numel() for p in model.parameters()), "rss_max_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "shapes": {name: list(value.shape) for name, value in logits.items()},
        "loss": float(total.detach()), "components": {name: float(value.detach()) for name, value in components.items()},
        "all_ignored_loss": float(all_masked_loss.detach()), "finite_gradient_tensors": len(grads),
        "checkpoint_bytes_in_memory": memory.getbuffer().nbytes, "eval_roundtrip_bitwise": True,
        "optimizer_steps": 0, "coefficients": dict(COEFFICIENTS), "torch_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(), "no_candidate_weights_written": True})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cpu-grant", type=Path, required=True)
    parser.add_argument("--python", default=ORIGINAL_PYTHON)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    validate_grant(args.cpu_grant, "copy-editor-head-unit", required_pins(), 20)
    if args.python != ORIGINAL_PYTHON:
        raise ValueError("Use the original conversion-env Python spelling; do not resolve its symlink")
    if args.worker:
        worker(args.output_dir)
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=False)
    return supervise([args.python, str(Path(__file__).absolute()), "--worker", "--output-dir", str(args.output_dir),
        "--cpu-grant", str(args.cpu_grant), "--python", args.python], args.output_dir, 20)


if __name__ == "__main__":
    raise SystemExit(main())
