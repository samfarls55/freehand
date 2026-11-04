#!/usr/bin/env python3
"""Select a reproducible family-stratified pilot from frozen training only."""
import argparse
from collections import defaultdict, Counter
import hashlib
import json
from pathlib import Path
import random


def sha(data):
    return hashlib.sha256(data).hexdigest()


def round_robin(rows, count, seed):
    groups = defaultdict(list)
    for row in rows:
        groups[row["family"]].append(row)
    rng = random.Random(seed)
    for group in groups.values():
        rng.shuffle(group)
    selected = []
    names = sorted(groups)
    while len(selected) < count:
        progressed = False
        for name in names:
            if groups[name] and len(selected) < count:
                selected.append(groups[name].pop())
                progressed = True
        if not progressed:
            raise ValueError("Not enough training rows in selection stratum")
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=512)
    parser.add_argument("--unchanged-fraction", type=float, default=.36)
    args = parser.parse_args()
    raw = args.train.read_bytes()
    rows = [json.loads(line) for line in raw.splitlines()]
    assert all(row["split"] == "train" for row in rows)
    unchanged_count = round(args.count * args.unchanged_fraction)
    selected = round_robin([row for row in rows if not row["edit_needed"]],
                           unchanged_count, 20261103)
    selected += round_robin([row for row in rows if row["edit_needed"]],
                           args.count - unchanged_count, 20261104)
    random.Random(20261105).shuffle(selected)
    assert len(selected) == len({row["id"] for row in selected}) == args.count
    result = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                     for row in selected).encode("utf-8")
    with args.output.open("xb") as stream:
        stream.write(result)
    manifest = {
        "schema_version": 1,
        "source": {"path": str(args.train), "sha256": sha(raw), "rows": len(rows)},
        "selection": "Unchanged/edited strata; deterministic round-robin over task families",
        "seed": [20261103, 20261104, 20261105],
        "split": "train", "evaluation_or_development_rows_used": False,
        "artifact": {"path": str(args.output), "sha256": sha(result), "bytes": len(result),
                     "rows": len(selected), "unchanged_rows": unchanged_count,
                     "family_counts": dict(sorted(Counter(r["family"] for r in selected).items()))},
        "selected_ids": [row["id"] for row in selected],
        "limitations": "Pilot subset for engineering, not independent accuracy evidence.",
    }
    manifest_path = args.output.with_suffix(".manifest.json")
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    print(json.dumps(manifest["artifact"], indent=2))


if __name__ == "__main__":
    main()
