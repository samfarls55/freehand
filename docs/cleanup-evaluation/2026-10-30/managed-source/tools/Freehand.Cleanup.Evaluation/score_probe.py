#!/usr/bin/env python3
"""Grade real Core probe outputs separately from raw model returns and fallback."""
import argparse
import json
from pathlib import Path
import sys

from benchmark import HERE, apply_normalization, grade, persist, sha256_file, summarize


def score(probe: dict, fixtures: list[dict], candidate_id: str) -> tuple[dict, list[dict], list[dict]]:
    source = {case["id"]: case for case in fixtures}
    selected = []
    seen = set()
    for row in probe["cases"]:
        if row["id"] in seen:
            raise ValueError(f"Duplicate probe result: {row['id']}")
        seen.add(row["id"])
        selected.append(source[row["id"]])
    cases = apply_normalization(selected, probe)
    normalized = {case["id"]: case for case in cases}
    rows = []
    accepted = []
    fallback = []
    counts = {status: 0 for status in ("Disabled", "Applied", "Unchanged", "Rejected", "Failed", "TimedOut")}
    for item in probe["cases"]:
        case = normalized[item["id"]]
        status = item["cleanup_status"]
        if status not in counts:
            raise ValueError(f"Unrecognized cleanup status: {status}")
        counts[status] += 1
        common = {"case_id": item["id"], "category": case["category"], "split": case["split"], "repetition": 1,
                  "cleanup_status": status, "insertion_count": item.get("insertion_count"),
                  "delivered_count": item.get("delivered_count"), "delivery_outcome": item.get("delivery_outcome")}
        baseline = {**common, "candidate": "Core-normalized-no-cleanup", "status": "completed",
                    "output": item["normalized_input"], "complete_response_seconds": 0.0,
                    "grade": grade(case, item["normalized_input"])}
        rows.append(baseline)
        native = item.get("candidate_text")
        native_row = {**common, "candidate": candidate_id + ".model-return",
                      "complete_response_seconds": (item.get("cleanup_time_ms") or 0) / 1000}
        if isinstance(native, str):
            native_row.update({"status": "completed", "output": native, "grade": grade(case, native)})
        else:
            native_row.update({"status": "not_attempted" if status == "Disabled" else "not_returned", "error": item.get("error"),
                               "note": "Cleanup disabled; no inference attempted." if status == "Disabled" else "No candidate text returned by provider; this is not a quality pass."})
        rows.append(native_row)
        final_row = {**common, "candidate": candidate_id + ".app-final", "status": "completed",
                     "output": item["output"], "complete_response_seconds": (item.get("elapsed_ms") or 0) / 1000,
                     "grade": grade(case, item["output"])}
        rows.append(final_row)
        if status in ("Applied", "Unchanged"):
            accepted.append(final_row)
        elif status != "Disabled":
            fallback.append(final_row)
    names = list(dict.fromkeys(row["candidate"] for row in rows))
    report = {"schema_version": 1, "candidate": candidate_id, "probe_metadata": probe.get("metadata"),
              "scope": "Core probe output grading; consult probe metadata for runtime and measurement scope.",
              "candidates": [{"id": name, "summary": summarize([row for row in rows if row["candidate"] == name])} for name in names],
              "cleanup_status_counts": counts,
              "accepted_coverage": len(accepted) / len(cases) if cases else None,
              "accepted_only_quality": summarize(accepted),
              "fallback_only_quality": summarize(fallback),
              "limits": ["Candidate quality, accepted coverage, and final fallback quality are separate quantities.",
                         "A good final fallback output does not establish that the model edited it correctly.",
                         "Provider parsing failures may not expose candidate_text; native HTTP replay retains those raw responses separately.",
                         "Automatic assertions and target similarity cannot establish semantic fidelity; review all outputs.",
                         "Core probe elapsed time is not native HTTP completion time or physical Windows delivery latency."]}
    return report, rows, cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=HERE / "fixtures.json")
    parser.add_argument("--candidate-id", default="cleanup")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    from benchmark import load_corpus
    try:
        probe = json.loads(arguments.input.read_text(encoding="utf-8"))
        report, rows, cases = score(probe, load_corpus(arguments.corpus), arguments.candidate_id)
        report.update({"probe_report_sha256": sha256_file(arguments.input), "fixture_sha256": sha256_file(arguments.corpus)})
        arguments.output.mkdir(parents=True, exist_ok=False)
        (arguments.output / "source-probe.json").write_bytes(arguments.input.read_bytes())
        (arguments.output / "source-corpus.json").write_bytes(arguments.corpus.read_bytes())
        report["input_snapshots"] = {"probe": "source-probe.json", "corpus": "source-corpus.json"}
        persist(arguments.output, report, rows, cases)
        print(json.dumps({"output": str(arguments.output.resolve()), "coverage": report["accepted_coverage"], "statuses": report["cleanup_status_counts"]}))
        return 0
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(f"Probe scoring error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
