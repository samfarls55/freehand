"""Stdlib-only grants and ownership for bounded400-case source-tag CPU workers (180seconds maximum).

Importing this module never imports Torch or starts a child process.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time

ROOT = Path(__file__).absolute().parent
ORIGINAL_PYTHON = "/workspace/freehand/work/cleanup-small-models-2026-11-03/scribe-precision-source/conversion-env/bin/python"
CORE_PINS = ("source_tag_contract.py", "source_tag_model.py", "source_tag_train400.py",
             "source_tag_runtime400.py", "editor_core/__init__.py", "editor_core/core.py",
             "editor_core/head_contract.py")
_CLEANUP_SECONDS = 1


def sha(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def write_json(path, value) -> None:
    payload = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


def required_pins(extra=()) -> dict[str, str]:
    pins = {}
    for item in (*CORE_PINS, *extra):
        name = str(item)
        path = Path(name)
        if (not name or path.is_absolute() or any(part in ("", ".", "..") for part in name.split("/"))
                or "\\" in name):
            raise ValueError("Source pins require explicit relative paths inside the prototype")
        pins[name] = sha(ROOT / path)
    return pins


def _seconds(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def validate_grant(path, operation, pins, seconds, settings=None, output_dir=None) -> dict:
    grant = json.loads(Path(path).read_text(encoding="utf-8"))
    if (not isinstance(grant, dict) or not isinstance(operation, str) or not operation
            or grant.get("operation") != operation or grant.get("cpu_granted") is not True
            or not _seconds(seconds) or not _seconds(grant.get("max_wall_seconds"))
            or seconds > grant["max_wall_seconds"]):
        raise ValueError("Missing/mismatched explicit CPU grant or finite time bound")
    supplied = grant.get("pins")
    if (not isinstance(pins, dict) or not pins or not isinstance(supplied, dict)
            or any(not isinstance(name, str) or not name or not isinstance(digest, str)
                   or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                   or supplied.get(name) != digest for name, digest in pins.items())):
        raise ValueError("CPU grant source/input pins do not match")
    if settings is not None and grant.get("settings_sha256") != canonical_sha(settings):
        raise ValueError("CPU grant settings digest does not match")
    if output_dir is not None and grant.get("output_dir") != str(Path(output_dir).absolute()):
        raise ValueError("CPU grant output directory does not match exactly")
    return grant


def supervise(command, directory, seconds) -> int:
    """Run one owned worker; seconds bounds work, with up to two seconds for reap.

    Existing evidence is preserved. Exceptions and interruption also enter owned
    child cleanup; a CPU release is reported only after reap and group release.
    """
    if not _seconds(seconds) or seconds > 180 or not isinstance(command, (list, tuple)) or not command:
        raise ValueError("An explicit command and finite positive worker timeout at most180seconds are required")
    directory = Path(directory).absolute()
    if not directory.is_dir() or any(path.is_symlink() for path in (directory, *directory.parents)):
        raise ValueError("Worker output must be an existing regular owned directory")
    for name in ("worker.stdout", "worker.stderr", "supervisor.json", "cpu-release.json"):
        path = directory / name
        if path.exists() or path.is_symlink():
            raise ValueError("Preserve existing worker output: " + name)
    started = time.monotonic()
    deadline = started + seconds
    process = None
    owned_pgid = owned_sid = None
    confirmed = False
    exited_before_inspection = False
    timed_out = False
    code = None
    failure = None
    cleanup_errors = []
    environment = dict(os.environ, OMP_NUM_THREADS="2", MKL_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2")

    def signal_child(sig):
        if process.poll() is not None:
            return
        try:
            if (confirmed and os.getpgid(process.pid) == process.pid
                    and os.getsid(process.pid) == process.pid):
                os.killpg(process.pid, sig)
            else:
                # Only the Popen-owned PID may be signaled if group ownership
                # cannot be confirmed; never signal a foreign process group.
                (process.terminate if sig == signal.SIGTERM else process.kill)()
        except ProcessLookupError:
            pass  # Exit raced the signal; wait below still reaps this child.
        except OSError:
            # Group inspection/signaling can fail independently of our direct
            # Popen-owned child. Keep cleanup restricted to that child PID.
            (process.terminate if sig == signal.SIGTERM else process.kill)()

    try:
        with (directory / "worker.stdout").open("x") as stdout, (directory / "worker.stderr").open("x") as stderr:
            try:
                process = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                    stdout=stdout, stderr=stderr, start_new_session=True)
                print(json.dumps({"event": "owned_worker_started", "owned_pid": process.pid,
                    "ownership_pending": True}), flush=True)
                try:
                    owned_pgid, owned_sid = os.getpgid(process.pid), os.getsid(process.pid)
                except ProcessLookupError:
                    if process.poll() is None:
                        raise
                    exited_before_inspection = True
                else:
                    confirmed = owned_pgid == process.pid and owned_sid == process.pid
                    if not confirmed:
                        raise RuntimeError("Worker did not acquire its own process group/session")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, seconds)
                code = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                timed_out = True
            except BaseException as exc:
                failure = exc
            finally:
                if process is not None:
                    try:
                        signal_child(signal.SIGTERM)
                    except BaseException as exc:
                        cleanup_errors.append({"type": type(exc).__name__, "message": str(exc)})
                    try:
                        code = process.wait(timeout=_CLEANUP_SECONDS)
                    except subprocess.TimeoutExpired:
                        try:
                            signal_child(signal.SIGKILL)
                        except BaseException as exc:
                            cleanup_errors.append({"type": type(exc).__name__, "message": str(exc)})
                        try:
                            code = process.wait(timeout=_CLEANUP_SECONDS)
                        except BaseException as exc:
                            cleanup_errors.append({"type": type(exc).__name__, "message": str(exc)})
                    except BaseException as exc:
                        cleanup_errors.append({"type": type(exc).__name__, "message": str(exc)})
    except BaseException as exc:
        failure = failure or exc

    reaped = process is None or process.poll() is not None
    group_released = process is None
    if process is not None and (confirmed or exited_before_inspection):
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            group_released = True
        except OSError as exc:
            cleanup_errors.append({"type": type(exc).__name__, "message": str(exc)})
        else:
            try:
                if confirmed:
                    os.killpg(process.pid, signal.SIGKILL)
                    os.killpg(process.pid, 0)
            except ProcessLookupError:
                group_released = True
            except OSError as exc:
                cleanup_errors.append({"type": type(exc).__name__, "message": str(exc)})
    report = {"owned_pid": process.pid if process is not None else None,
        "owned_process_group": owned_pgid, "owned_session": owned_sid,
        "ownership_confirmed": confirmed, "exited_before_ownership_inspection": exited_before_inspection,
        "returncode": code, "timed_out": timed_out,
        "worker_timeout_seconds": seconds, "cleanup_grace_seconds_maximum": 2 * _CLEANUP_SECONDS,
        "elapsed_seconds": time.monotonic() - started, "owned_process_reaped": reaped,
        "owned_group_released": group_released, "cpu_release": reaped and group_released,
        "error": {"type": type(failure).__name__, "message": str(failure)} if failure else None,
        "cleanup_errors": cleanup_errors}
    write_json(directory / "supervisor.json", report)
    write_json(directory / "cpu-release.json", {"event": "CPU_RELEASED", **report})
    print(json.dumps({"event": "CPU_RELEASED", **report}), flush=True)
    if failure is not None:
        raise failure
    if timed_out:
        return 124
    return code if code else (0 if report["cpu_release"] else 1)


def configure_torch(seed=20261104):
    import torch
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    return torch
