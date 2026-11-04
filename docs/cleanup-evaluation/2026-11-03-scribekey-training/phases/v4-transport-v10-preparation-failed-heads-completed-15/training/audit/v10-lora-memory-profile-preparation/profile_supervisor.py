"""Sampled, read-only memory guard for one explicitly authorized owned worker.

Importing launches nothing. A sampled cap cannot prevent an allocation jump or
OOM between samples. Only the caller's grant authorizes actual execution.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import resource
import signal
import subprocess
import time

DEFAULT_MEMORY_CAP_BYTES = 16_500_000_000
_MONITOR_TEXT_LIMIT = 16_384
_TERM_SECONDS = 1.0
_KILL_SECONDS = 1.0
_GROUP_SECONDS = 1.0


class MonitorUnavailable(ValueError):
    pass


def _write_json(path, value):
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


def _read_text(path):
    try:
        with Path(path).open("r", encoding="ascii") as stream:
            value = stream.read(_MONITOR_TEXT_LIMIT + 1)
    except (OSError, UnicodeError) as exc:
        raise MonitorUnavailable("Required monitor is unreadable: " + str(path)) from exc
    if len(value) > _MONITOR_TEXT_LIMIT:
        raise MonitorUnavailable("Required monitor exceeds the bounded text limit: " + str(path))
    return value


def _nonnegative(value, label):
    if not value or not value.isascii() or not value.isdecimal():
        raise MonitorUnavailable("Invalid nonnegative monitor integer: " + label)
    return int(value)


def _cgroup_sample(directory):
    current = _nonnegative(_read_text(directory / "memory.current").strip(), "memory.current")
    peak = _nonnegative(_read_text(directory / "memory.peak").strip(), "memory.peak")
    events = {}
    for line in _read_text(directory / "memory.events").splitlines():
        parts = line.split()
        if len(parts) != 2 or parts[0] in events:
            raise MonitorUnavailable("Malformed or duplicate memory.events counter")
        events[parts[0]] = _nonnegative(parts[1], "memory.events:" + parts[0])
    if not {"oom", "oom_kill"}.issubset(events):
        raise MonitorUnavailable("Required cgroup OOM counters are missing")
    return {"current_bytes": current, "peak_bytes": peak, "events": events}


def _owned_status(pid):
    # Never enumerate /proc, descendants, or another process's status.
    fields = {}
    for line in _read_text(Path("/proc") / str(pid) / "status").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            if key in fields:
                raise MonitorUnavailable("Duplicate owned process status field")
            fields[key] = value.strip()
    if fields.get("Pid") != str(pid):
        raise MonitorUnavailable("Owned process status PID does not match")
    result = {"pid": pid}
    for key, name in (("VmRSS", "rss_bytes"), ("VmHWM", "rss_peak_bytes"),
                      ("VmSize", "virtual_bytes")):
        parts = fields.get(key, "").split()
        if len(parts) != 2 or parts[1] != "kB":
            raise MonitorUnavailable("Required owned process status field is missing: " + key)
        result[name] = _nonnegative(parts[0], key) * 1024
    return result


def _disable_core_dumps():
    # Executed only by Popen in the authorized child, never in the supervisor.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _positive_seconds(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def supervise(command, output_dir, *, cwd, env, max_seconds,
              memory_cap_bytes=DEFAULT_MEMORY_CAP_BYTES, poll_seconds=.05,
              cgroup_dir=Path("/sys/fs/cgroup")):
    """Return evidence for one owned process; no model or success claims implied.

    max_seconds bounds work. Cleanup has at most three additional seconds of
    TERM/KILL/reap/group-release grace. Cap comparisons use cgroup current bytes;
    historical cgroup peak and the owned PID's RSS are recorded separately.
    """
    if (not isinstance(command, (list, tuple)) or not command
            or any(not isinstance(value, str) or not value for value in command)
            or not _positive_seconds(max_seconds) or not _positive_seconds(poll_seconds)
            or poll_seconds > 1 or type(memory_cap_bytes) is not int or memory_cap_bytes < 1
            or not isinstance(env, dict) or any(not isinstance(key, str) or not isinstance(value, str)
                                               for key, value in env.items())):
        raise ValueError("Explicit command, environment, finite bounds and positive integer memory cap required")
    output_dir, cgroup_dir = Path(output_dir).absolute(), Path(cgroup_dir)
    if not output_dir.is_dir() or any(path.is_symlink() for path in (output_dir, *output_dir.parents)):
        raise ValueError("Output must be an existing owned directory without symlink ancestors")
    names = ("owned-process.json", "worker.stdout", "worker.stderr", "samples.jsonl",
             "supervisor.json", "cpu-release.json")
    if any((output_dir / name).exists() or (output_dir / name).is_symlink() for name in names):
        raise ValueError("Preserve all existing memory-profile evidence")

    started = time.monotonic()
    deadline = started + max_seconds
    process = None
    pgid = sid = None
    ownership_confirmed = False
    early_exit = False
    reason = "launch_error"
    error = None
    cleanup_errors = []
    sample_count = 0
    baseline = last_cgroup = None
    peaks = {"cgroup_current_bytes": 0, "cgroup_peak_bytes": 0,
             "owned_rss_bytes": 0, "owned_rss_peak_bytes": 0}

    def signal_owned(sig):
        if process.poll() is not None:
            return
        try:
            if (ownership_confirmed and os.getpgid(process.pid) == process.pid
                    and os.getsid(process.pid) == process.pid):
                os.killpg(process.pid, sig)
            else:
                # A startup ownership error never authorizes a foreign group.
                (process.terminate if sig == signal.SIGTERM else process.kill)()
        except ProcessLookupError:
            pass
        except OSError:
            (process.terminate if sig == signal.SIGTERM else process.kill)()

    try:
        with (output_dir / "worker.stdout").open("x") as stdout, \
                (output_dir / "worker.stderr").open("x") as stderr, \
                (output_dir / "samples.jsonl").open("x", encoding="utf-8") as samples:
            try:
                baseline = last_cgroup = _cgroup_sample(cgroup_dir)
                peaks["cgroup_current_bytes"] = baseline["current_bytes"]
                peaks["cgroup_peak_bytes"] = baseline["peak_bytes"]
                if baseline["current_bytes"] >= memory_cap_bytes:
                    reason = "memory_cap_before_launch"
                elif time.monotonic() >= deadline:
                    reason = "deadline_before_launch"
                else:
                    process = subprocess.Popen(list(command), cwd=cwd, env=dict(env),
                        stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                        start_new_session=True, preexec_fn=_disable_core_dumps)
                    print(json.dumps({"event": "PROFILE_CHILD_STARTED", "owned_pid": process.pid,
                        "ownership_pending": True}), flush=True)
                    try:
                        pgid, sid = os.getpgid(process.pid), os.getsid(process.pid)
                        ownership_confirmed = pgid == process.pid and sid == process.pid
                    except ProcessLookupError:
                        if process.poll() is None:
                            raise
                        early_exit = True
                    finally:
                        _write_json(output_dir / "owned-process.json", {"owned_pid": process.pid,
                            "owned_process_group": pgid, "owned_session": sid,
                            "ownership_confirmed": ownership_confirmed,
                            "exited_before_ownership_inspection": early_exit,
                            "start_new_session_requested": True, "core_dump_limit_bytes": 0})
                        print(json.dumps({"event": "PROFILE_CHILD_OWNERSHIP_OBSERVED", "owned_pid": process.pid,
                            "owned_process_group": pgid, "owned_session": sid,
                            "ownership_confirmed": ownership_confirmed}), flush=True)
                    if not ownership_confirmed and not early_exit:
                        reason = "ownership_error"
                        raise RuntimeError("Owned worker did not acquire its own group/session")
                    while True:
                        if process.poll() is not None:
                            reason = "completed" if process.returncode == 0 else "worker_failed"
                            break
                        now = time.monotonic()
                        if now >= deadline:
                            reason = "deadline"
                            break
                        current = _cgroup_sample(cgroup_dir)
                        try:
                            status = _owned_status(process.pid)
                        except MonitorUnavailable:
                            if process.poll() is not None:
                                reason = "completed" if process.returncode == 0 else "worker_failed"
                                break
                            raise
                        if (set(current["events"]) != set(baseline["events"])
                                or any(current["events"][key] < value for key, value in baseline["events"].items())):
                            raise MonitorUnavailable("Cgroup memory event counters changed schema or decreased")
                        last_cgroup = current
                        delta = {key: value - baseline["events"][key] for key, value in current["events"].items()}
                        sample = {"sample": sample_count, "elapsed_seconds": now - started,
                                  "cgroup": current, "memory_event_delta": delta, "owned_process": status}
                        samples.write(json.dumps(sample, allow_nan=False) + "\n")
                        samples.flush()
                        sample_count += 1
                        peaks["cgroup_current_bytes"] = max(peaks["cgroup_current_bytes"], current["current_bytes"])
                        peaks["cgroup_peak_bytes"] = max(peaks["cgroup_peak_bytes"], current["peak_bytes"])
                        peaks["owned_rss_bytes"] = max(peaks["owned_rss_bytes"], status["rss_bytes"])
                        peaks["owned_rss_peak_bytes"] = max(peaks["owned_rss_peak_bytes"], status["rss_peak_bytes"])
                        if current["current_bytes"] >= memory_cap_bytes:
                            reason = "memory_cap"
                            break
                        if delta["oom"] or delta["oom_kill"] or delta.get("oom_group_kill", 0):
                            reason = "cgroup_oom_event"
                            break
                        time.sleep(min(poll_seconds, max(0., deadline - time.monotonic())))
            except MonitorUnavailable as exc:
                reason = "missing_monitor"
                error = {"type": type(exc).__name__, "message": str(exc)}
            except BaseException as exc:
                if reason != "ownership_error":
                    reason = ("interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit))
                              else "launch_error" if process is None else "supervisor_error")
                error = {"type": type(exc).__name__, "message": str(exc)}
            finally:
                if process is not None:
                    try:
                        signal_owned(signal.SIGTERM)
                    except BaseException as exc:
                        cleanup_errors.append({"type": type(exc).__name__, "message": str(exc)})
                    try:
                        process.wait(timeout=_TERM_SECONDS)
                    except subprocess.TimeoutExpired:
                        try:
                            signal_owned(signal.SIGKILL)
                        except BaseException as exc:
                            cleanup_errors.append({"type": type(exc).__name__, "message": str(exc)})
                        try:
                            process.wait(timeout=_KILL_SECONDS)
                        except BaseException as exc:
                            cleanup_errors.append({"type": type(exc).__name__, "message": str(exc)})
                    except BaseException as exc:
                        cleanup_errors.append({"type": type(exc).__name__, "message": str(exc)})
    except BaseException as exc:
        reason = "supervisor_error"
        error = {"type": type(exc).__name__, "message": str(exc)}

    try:
        final_cgroup = _cgroup_sample(cgroup_dir)
    except MonitorUnavailable as exc:
        final_cgroup = None
        if reason == "completed":
            reason = "missing_monitor"
            error = {"type": type(exc).__name__, "message": str(exc)}
    final_event_delta = None
    if final_cgroup is not None:
        peaks["cgroup_current_bytes"] = max(peaks["cgroup_current_bytes"], final_cgroup["current_bytes"])
        peaks["cgroup_peak_bytes"] = max(peaks["cgroup_peak_bytes"], final_cgroup["peak_bytes"])
        if (baseline is not None and set(final_cgroup["events"]) == set(baseline["events"])
                and all(final_cgroup["events"][key] >= value for key, value in baseline["events"].items())):
            final_event_delta = {key: value - baseline["events"][key]
                                 for key, value in final_cgroup["events"].items()}
            if reason == "completed" and any(final_event_delta.get(key, 0)
                                             for key in ("oom", "oom_kill", "oom_group_kill")):
                reason = "cgroup_oom_event"
        elif baseline is not None and reason == "completed":
            reason = "missing_monitor"
            error = {"type": "MonitorUnavailable", "message": "Final cgroup counters lost monotonic binding"}
        if reason == "completed" and final_cgroup["current_bytes"] >= memory_cap_bytes:
            reason = "memory_cap_after_exit"
    reaped = process is None or process.poll() is not None
    group_released = process is None
    if process is not None and (ownership_confirmed or early_exit):
        group_deadline = time.monotonic() + _GROUP_SECONDS
        group_signaled = False
        while True:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                group_released = True
                break
            except OSError as exc:
                cleanup_errors.append({"type": type(exc).__name__, "message": str(exc)})
                break
            if not ownership_confirmed or time.monotonic() >= group_deadline:
                break
            if not group_signaled:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    group_released = True
                    break
                except OSError as exc:
                    cleanup_errors.append({"type": type(exc).__name__, "message": str(exc)})
                    break
                group_signaled = True
            time.sleep(.01)
    code = process.returncode if process is not None else None
    cpu_release = reaped and group_released
    complete = reason == "completed" and code == 0 and cpu_release and sample_count > 0
    report = {"schema_version": 1, "reason": reason, "returncode": code,
        "status": "COMPLETED_SAMPLED_PROFILE" if complete else "STOPPED_OR_INCOMPLETE_NO_PROFILE_CLAIM",
        "measurement_complete": complete, "sample_count": sample_count,
        "owned_pid": process.pid if process is not None else None,
        "owned_process_group": pgid, "owned_session": sid, "ownership_confirmed": ownership_confirmed,
        "owned_process_reaped": reaped, "owned_group_released": group_released, "cpu_release": cpu_release,
        "max_seconds": max_seconds, "memory_cap_bytes": memory_cap_bytes, "poll_seconds": poll_seconds,
        "cleanup_grace_seconds_maximum": _TERM_SECONDS + _KILL_SECONDS + _GROUP_SECONDS,
        "elapsed_seconds_including_cleanup": time.monotonic() - started, "observed_peaks": peaks,
        "cgroup_baseline": baseline, "last_cgroup_sample": last_cgroup,
        "final_cgroup_sample": final_cgroup,
        "final_memory_event_delta": final_event_delta,
        "sampled_memory_guard_only": True, "oom_avoidance_guaranteed": False,
        "limitation": "Polling can miss allocation jumps or OOM between samples; cgroup memory includes other workloads and its peak is historical. Owned RSS covers only this PID.",
        "error": error, "cleanup_errors": cleanup_errors}
    _write_json(output_dir / "supervisor.json", report)
    _write_json(output_dir / "cpu-release.json", {"released": cpu_release, **report})
    print(json.dumps({"event": "PROFILE_CPU_RELEASED", "cpu_release": cpu_release,
        "owned_pid": report["owned_pid"], "reason": reason}), flush=True)
    return report
